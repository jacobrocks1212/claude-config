#!/usr/bin/env python3
"""
track-work.py -- Lightweight WIP sentinel manager for feature/bug items.

Usage:
    track-work.py <open|touch|close> [--repo-root PATH] [--slug SLUG] [--wi-id ID] [--test]

Actions:
    open   -- Create or refresh <item_dir>/WIP.md (liveness sentinel).
    touch  -- Advance last_touched in an existing WIP.md.
    close  -- Remove WIP.md (marks item as no longer active).

After any successful action the work-status dashboard (DASHBOARD.md) is
regenerated against the resolved cog-docs root so the new stage/staleness is
reflected immediately. The refresh shells out to work-status.py --markdown and
is best-effort: it is timeout-guarded and never fails the action. Pass
--no-refresh to skip it.

Resolution order:
    1. --repo-root / COG_DOCS_ROOT env var / sibling cog-docs dir -> cog_docs root
    2. --wi-id / branch pattern ^p/(\\d+)- -> wi_id
    3. --slug / materialized.json feature_id -> item slug -> item dir

All heavy I/O (git, clock, env, socket) is confined to main() so the pure
functions are injectable from tests.

Dependencies: stdlib + lazy_core (sibling module) + PyYAML (for lazy_core).
Run with: PYTHONUTF8=1 python track-work.py <action>
"""
from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import re
import socket
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

# ---------------------------------------------------------------------------
# Bootstrap: add the script's own directory to sys.path so that lazy_core
# is importable regardless of the cwd when the script is invoked.
# ---------------------------------------------------------------------------
_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

import lazy_core  # noqa: E402  (after sys.path surgery)


# ---------------------------------------------------------------------------
# Dashboard refresh (impure I/O — confined here, injected into run() so the
# pure resolution logic stays testable without spawning a subprocess).
# ---------------------------------------------------------------------------

def refresh_dashboard(cog_docs: Path) -> bool:
    """Regenerate DASHBOARD.md against ``cog_docs`` by invoking work-status.py.

    Shells out to the canonical renderer (``work-status.py --markdown
    --repo-root <cog_docs>``) rather than re-implementing the render wiring, so
    the hook-triggered refresh can never drift from the scheduled/manual one.

    Best-effort and hook-safe: captures output, enforces a timeout, and returns
    a bool instead of raising. A failed or slow refresh never blocks the
    tracking action that triggered it.

    Returns:
        True if the renderer exited 0, False on any failure/timeout/exception.
    """
    render_script = _SCRIPT_DIR / "work-status.py"
    if not render_script.exists():
        return False
    env = dict(os.environ)
    env["PYTHONUTF8"] = "1"  # Windows cp1252 crashes on Unicode dashboard glyphs
    try:
        result = subprocess.run(
            [sys.executable, str(render_script), "--markdown",
             "--repo-root", str(cog_docs)],
            capture_output=True,
            text=True,
            env=env,
            timeout=60,
            check=False,
        )
        return result.returncode == 0
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Pure, injectable core functions
# (bodies raise NotImplementedError — implementation agent fills these in)
# ---------------------------------------------------------------------------

def resolve_cog_docs(repo_root_arg: str | None, env: dict, sibling_base: Path) -> Path | None:
    """Resolve the cog-docs root directory.

    Priority:
      1. repo_root_arg — if given and the path exists, use it.
      2. env["COG_DOCS_ROOT"] — if set and the path exists, use it.
      3. sibling_base / "cog-docs" — if that directory exists, use it.
      4. None — cog-docs is not available; caller should no-op.

    Args:
        repo_root_arg: Raw --repo-root argument string, or None.
        env: Environment variable dict (injectable; pass os.environ in main()).
        sibling_base: Base directory for the sibling-probe (the parent of the
                      git repo root in production; any Path in tests).

    Returns:
        Resolved Path if found, else None.
    """
    if repo_root_arg:
        p = Path(repo_root_arg)
        if p.exists():
            return p
    cog_docs_env = env.get("COG_DOCS_ROOT")
    if cog_docs_env:
        p = Path(cog_docs_env)
        if p.exists():
            return p
    sibling = sibling_base / "cog-docs"
    if sibling.exists():
        return sibling
    return None


def resolve_wi_id(branch: str | None, wi_id_arg: str | None) -> str | None:
    """Derive the work-item ID from explicit arg or branch name.

    Priority:
      1. wi_id_arg if truthy.
      2. Branch pattern ^p/(\\d+)- — returns the captured digit string.
      3. None if neither applies.

    Args:
        branch: Current branch name (or None if not on a branch / detached).
        wi_id_arg: Explicit --wi-id argument, or None.

    Returns:
        WI id string or None.
    """
    if wi_id_arg:
        return str(wi_id_arg)
    m = re.match(r"^p/(\d+)-", branch or "")
    if m:
        return m.group(1)
    return None


def resolve_item_dir(
    cog_docs: Path,
    materialized: list[dict],
    wi_id: str | None = None,
    slug: str | None = None,
) -> Path | None:
    """Locate the feature/bug directory for a work item.

    Slug resolution:
      - If ``slug`` is given, use it directly.
      - Else, find the record in ``materialized`` whose ``wi_id`` matches
        (compare as str on both sides); take its ``feature_id`` as the slug.
      - If no slug can be resolved, return None.

    Directory probe (first match wins):
      1. cog_docs / "docs" / "features" / slug  — if it exists as a dir
      2. cog_docs / "docs" / "bugs"     / slug  — if it exists as a dir
      3. None — item directory not found

    Args:
        cog_docs: Resolved cog-docs root Path.
        materialized: List of materialized records (each a dict with at least
                      ``wi_id`` and ``feature_id`` keys).
        wi_id: Work-item ID string, or None.
        slug: Explicit slug override, or None.

    Returns:
        Path to the item directory, or None.
    """
    # Resolve slug
    resolved_slug = slug
    if not resolved_slug and wi_id is not None:
        for rec in materialized:
            if str(rec.get("wi_id")) == str(wi_id):
                resolved_slug = rec.get("feature_id")
                break
    if not resolved_slug:
        return None

    # Probe features dir first, then bugs dir
    features_path = cog_docs / "docs" / "features" / resolved_slug
    if features_path.is_dir():
        return features_path
    bugs_path = cog_docs / "docs" / "bugs" / resolved_slug
    if bugs_path.is_dir():
        return bugs_path
    return None


def run(
    action: str,
    *,
    repo_root_arg: str | None,
    slug: str | None,
    wi_id_arg: str | None,
    branch: str | None,
    env: dict,
    sibling_base: Path,
    host: str,
    now: str,
    materialized: list[dict] | None = None,
    refresh: Callable[[Path], bool] | None = None,
) -> int:
    """Orchestrate a track-work action end-to-end.

    Resolves cog_docs, wi_id, item_dir and dispatches to the appropriate
    lazy_core helper.  Every "can't find it" case emits a diagnostic line
    and returns 0 (safe no-op) — this script is invoked from git hooks and
    must never block the developer.

    Args:
        action: One of "open", "touch", "close".
        repo_root_arg: Raw --repo-root CLI argument or None.
        slug: Explicit --slug override or None.
        wi_id_arg: Explicit --wi-id override or None.
        branch: Current git branch (injected; None if unavailable).
        env: os.environ dict (injected).
        sibling_base: Parent of the git-repo root to use for sibling probe.
        host: Hostname string (injected).
        now: ISO-8601 timestamp string (injected).
        materialized: Injectable list of materialized records.  When None,
                      the function reads from disk via
                      lazy_core.read_materialized(cog_docs / "docs" / "work").
        refresh: Optional callback invoked with the resolved cog_docs Path
                 after a successful dispatch, to regenerate DASHBOARD.md.
                 None (the default, used by tests) skips the refresh entirely.
                 main() wires this to refresh_dashboard. The no-op resolution
                 paths return before dispatch, so refresh is never called there.

    Returns:
        0 always (never a failure exit code — hook-safe).
    """
    # 1. Resolve cog_docs
    cog_docs = resolve_cog_docs(repo_root_arg, env, sibling_base)
    if cog_docs is None:
        print("track-work: no cog-docs root resolvable — no-op")
        return 0

    # 2. Resolve wi_id (only needed when slug absent)
    wi_id = resolve_wi_id(branch, wi_id_arg)

    # 3. Load materialized if not injected
    if materialized is None:
        materialized = lazy_core.read_materialized(cog_docs / "docs" / "work")

    # 4. Resolve item_dir; also capture the slug used for dispatch
    # Determine slug_used inline (mirrors resolve_item_dir logic so we capture it)
    slug_used = slug
    if not slug_used and wi_id is not None:
        for rec in materialized:
            if str(rec.get("wi_id")) == str(wi_id):
                slug_used = rec.get("feature_id")
                break

    item_dir = resolve_item_dir(cog_docs, materialized, wi_id=wi_id, slug=slug)
    if item_dir is None:
        print(f"track-work: could not resolve item dir (wi_id={wi_id} slug={slug}) — no-op")
        return 0

    # 5. Dispatch
    if action == "open":
        lazy_core.track_open(item_dir, wi_id, slug_used, branch, host, now)
    elif action == "touch":
        lazy_core.track_touch(item_dir, now)
    elif action == "close":
        lazy_core.track_close(item_dir)

    # 6. Success diagnostic
    print(f"track-work: {action} on {item_dir.name} (wi_id={wi_id} slug={slug_used})")

    # 7. Refresh the dashboard so the new stage/staleness is reflected at once.
    #    Best-effort: a failed refresh must not turn a successful action into a
    #    failure, so the result is reported but never changes the return code.
    if refresh is not None:
        ok = refresh(cog_docs)
        print(f"track-work: dashboard refresh {'ok' if ok else 'skipped/failed'}")

    return 0


# ---------------------------------------------------------------------------
# Self-tests  (run_self_tests is fully implemented; stubs surface RED)
# ---------------------------------------------------------------------------

def run_self_tests() -> int:
    """Run five built-in fixtures. Returns number of failures (0 = all pass)."""
    failures = 0

    # ------------------------------------------------------------------
    # Fixture 1 — branch resolution + open writes WIP.md
    # Build cog_docs/docs/features/my-slug/ and a materialized.json.
    # Call run("open", ..., branch="p/56618-foo", slug=None, wi_id_arg=None).
    # Assert: returns 0, WIP.md exists, frontmatter has correct kind/wi_id/branch.
    # ------------------------------------------------------------------
    try:
        tmp1 = tempfile.mkdtemp(prefix="tw_test1_")
        cog_docs1 = Path(tmp1) / "cog-docs"
        feat_dir1 = cog_docs1 / "docs" / "features" / "my-slug"
        feat_dir1.mkdir(parents=True, exist_ok=True)
        work_dir1 = cog_docs1 / "docs" / "work"
        work_dir1.mkdir(parents=True, exist_ok=True)

        materialized1 = [
            {"wi_id": "56618", "feature_id": "my-slug", "materialized_changedDate": "x"}
        ]

        rc = run(
            "open",
            repo_root_arg=str(cog_docs1),
            slug=None,
            wi_id_arg=None,
            branch="p/56618-foo",
            env={},
            sibling_base=Path(tmp1),
            host="h",
            now="2026-06-03T10:00:00Z",
            materialized=materialized1,
        )
        assert rc == 0, f"expected 0, got {rc}"

        wip_path1 = feat_dir1 / "WIP.md"
        assert wip_path1.exists(), "WIP.md not written under features/my-slug"

        fm1 = lazy_core.parse_sentinel(wip_path1)
        assert fm1 is not None and fm1, "WIP.md frontmatter is empty or None"
        assert fm1.get("kind") == "wip", f"expected kind=wip, got {fm1.get('kind')}"
        assert str(fm1.get("wi_id")) == "56618", f"expected wi_id=56618, got {fm1.get('wi_id')}"
        assert fm1.get("branch") == "p/56618-foo", f"expected branch p/56618-foo, got {fm1.get('branch')}"

        print("PASS fixture_1_branch_resolution_open_writes_wip")
    except Exception as exc:
        print(f"FAIL fixture_1_branch_resolution_open_writes_wip: {exc}")
        failures += 1

    # ------------------------------------------------------------------
    # Fixture 2 — --slug bypasses branch
    # Same tree; call run("open", slug="my-slug", branch="main").
    # Assert WIP.md written under features/my-slug regardless of branch.
    # ------------------------------------------------------------------
    try:
        tmp2 = tempfile.mkdtemp(prefix="tw_test2_")
        cog_docs2 = Path(tmp2) / "cog-docs"
        feat_dir2 = cog_docs2 / "docs" / "features" / "my-slug"
        feat_dir2.mkdir(parents=True, exist_ok=True)
        work_dir2 = cog_docs2 / "docs" / "work"
        work_dir2.mkdir(parents=True, exist_ok=True)

        materialized2: list[dict] = []

        rc2 = run(
            "open",
            repo_root_arg=str(cog_docs2),
            slug="my-slug",
            wi_id_arg=None,
            branch="main",
            env={},
            sibling_base=Path(tmp2),
            host="h",
            now="2026-06-03T11:00:00Z",
            materialized=materialized2,
        )
        assert rc2 == 0, f"expected 0, got {rc2}"

        wip_path2 = feat_dir2 / "WIP.md"
        assert wip_path2.exists(), "WIP.md not written under features/my-slug with --slug"

        fm2 = lazy_core.parse_sentinel(wip_path2)
        assert fm2 is not None and fm2, "WIP.md frontmatter empty or None"
        assert fm2.get("kind") == "wip", f"expected kind=wip, got {fm2.get('kind')}"

        print("PASS fixture_2_slug_bypasses_branch")
    except Exception as exc:
        print(f"FAIL fixture_2_slug_bypasses_branch: {exc}")
        failures += 1

    # ------------------------------------------------------------------
    # Fixture 3 — no cog-docs resolvable → no-op exit 0 + diagnostic
    # sibling_base has NO cog-docs child; repo_root_arg=None; env={}.
    # Assert: returns 0, no WIP.md anywhere, diagnostic line emitted.
    # ------------------------------------------------------------------
    try:
        tmp3 = tempfile.mkdtemp(prefix="tw_test3_")
        sibling3 = Path(tmp3)  # no cog-docs child

        captured3 = io.StringIO()
        with contextlib.redirect_stdout(captured3):
            rc3 = run(
                "open",
                repo_root_arg=None,
                slug=None,
                wi_id_arg=None,
                branch="p/1-x",
                env={},
                sibling_base=sibling3,
                host="h",
                now="2026-06-03T12:00:00Z",
                materialized=None,
            )

        assert rc3 == 0, f"expected 0 (no-op), got {rc3}"

        # Verify nothing was written under tmp3
        wip_files3 = list(sibling3.rglob("WIP.md"))
        assert len(wip_files3) == 0, f"unexpected WIP.md files created: {wip_files3}"

        # Verify a diagnostic line was emitted
        output3 = captured3.getvalue()
        assert len(output3.strip()) > 0, "expected a diagnostic line but got no stdout output"

        print("PASS fixture_3_no_cog_docs_noop")
    except Exception as exc:
        print(f"FAIL fixture_3_no_cog_docs_noop: {exc}")
        failures += 1

    # ------------------------------------------------------------------
    # Fixture 4 — branch no-match + no slug → no-op exit 0
    # Valid cog_docs tree, branch="main" (no p/<digits>- prefix), no slug.
    # Assert: returns 0, no WIP.md created anywhere under cog_docs.
    # ------------------------------------------------------------------
    try:
        tmp4 = tempfile.mkdtemp(prefix="tw_test4_")
        cog_docs4 = Path(tmp4) / "cog-docs"
        feat_dir4 = cog_docs4 / "docs" / "features" / "some-feature"
        feat_dir4.mkdir(parents=True, exist_ok=True)
        work_dir4 = cog_docs4 / "docs" / "work"
        work_dir4.mkdir(parents=True, exist_ok=True)

        rc4 = run(
            "open",
            repo_root_arg=str(cog_docs4),
            slug=None,
            wi_id_arg=None,
            branch="main",
            env={},
            sibling_base=Path(tmp4),
            host="h",
            now="2026-06-03T13:00:00Z",
            materialized=[],
        )
        assert rc4 == 0, f"expected 0 (no-op), got {rc4}"

        wip_files4 = list(cog_docs4.rglob("WIP.md"))
        assert len(wip_files4) == 0, f"unexpected WIP.md files: {wip_files4}"

        print("PASS fixture_4_branch_no_match_noop")
    except Exception as exc:
        print(f"FAIL fixture_4_branch_no_match_noop: {exc}")
        failures += 1

    # ------------------------------------------------------------------
    # Fixture 5 — bug-route probe
    # Build only cog_docs/docs/bugs/bug-slug/ (no features dir).
    # materialized has wi_id="77" → feature_id="bug-slug".
    # run("open", wi_id_arg="77", branch=None) → WIP.md under docs/bugs/bug-slug.
    # ------------------------------------------------------------------
    try:
        tmp5 = tempfile.mkdtemp(prefix="tw_test5_")
        cog_docs5 = Path(tmp5) / "cog-docs"
        bug_dir5 = cog_docs5 / "docs" / "bugs" / "bug-slug"
        bug_dir5.mkdir(parents=True, exist_ok=True)
        work_dir5 = cog_docs5 / "docs" / "work"
        work_dir5.mkdir(parents=True, exist_ok=True)

        materialized5 = [
            {"wi_id": "77", "feature_id": "bug-slug", "materialized_changedDate": "y"}
        ]

        rc5 = run(
            "open",
            repo_root_arg=str(cog_docs5),
            slug=None,
            wi_id_arg="77",
            branch=None,
            env={},
            sibling_base=Path(tmp5),
            host="h",
            now="2026-06-03T14:00:00Z",
            materialized=materialized5,
        )
        assert rc5 == 0, f"expected 0, got {rc5}"

        wip_path5 = bug_dir5 / "WIP.md"
        assert wip_path5.exists(), "WIP.md not written under docs/bugs/bug-slug"

        fm5 = lazy_core.parse_sentinel(wip_path5)
        assert fm5 is not None and fm5, "WIP.md frontmatter empty or None"
        assert fm5.get("kind") == "wip", f"expected kind=wip, got {fm5.get('kind')}"

        print("PASS fixture_5_bug_route_probe")
    except Exception as exc:
        print(f"FAIL fixture_5_bug_route_probe: {exc}")
        failures += 1

    # ------------------------------------------------------------------
    # Fixture 6 — refresh callback fires once with cog_docs after success
    # Successful open must invoke the injected refresh exactly once, with the
    # resolved cog_docs Path.
    # ------------------------------------------------------------------
    try:
        tmp6 = tempfile.mkdtemp(prefix="tw_test6_")
        cog_docs6 = Path(tmp6) / "cog-docs"
        feat_dir6 = cog_docs6 / "docs" / "features" / "my-slug"
        feat_dir6.mkdir(parents=True, exist_ok=True)
        (cog_docs6 / "docs" / "work").mkdir(parents=True, exist_ok=True)

        refresh_calls6: list[Path] = []

        rc6 = run(
            "open",
            repo_root_arg=str(cog_docs6),
            slug="my-slug",
            wi_id_arg=None,
            branch="main",
            env={},
            sibling_base=Path(tmp6),
            host="h",
            now="2026-06-03T15:00:00Z",
            materialized=[],
            refresh=lambda p: (refresh_calls6.append(p) or True),
        )
        assert rc6 == 0, f"expected 0, got {rc6}"
        assert len(refresh_calls6) == 1, \
            f"expected refresh called once, got {len(refresh_calls6)}"
        assert refresh_calls6[0] == cog_docs6, \
            f"expected refresh arg {cog_docs6}, got {refresh_calls6[0]}"

        print("PASS fixture_6_refresh_fires_after_success")
    except Exception as exc:
        print(f"FAIL fixture_6_refresh_fires_after_success: {exc}")
        failures += 1

    # ------------------------------------------------------------------
    # Fixture 7 — refresh NOT fired when cog-docs is unresolvable (no-op)
    # ------------------------------------------------------------------
    try:
        tmp7 = tempfile.mkdtemp(prefix="tw_test7_")  # no cog-docs child
        refresh_calls7: list[Path] = []

        with contextlib.redirect_stdout(io.StringIO()):
            rc7 = run(
                "open",
                repo_root_arg=None,
                slug=None,
                wi_id_arg=None,
                branch="p/1-x",
                env={},
                sibling_base=Path(tmp7),
                host="h",
                now="2026-06-03T16:00:00Z",
                materialized=None,
                refresh=lambda p: (refresh_calls7.append(p) or True),
            )
        assert rc7 == 0, f"expected 0, got {rc7}"
        assert len(refresh_calls7) == 0, \
            f"refresh must NOT fire on no-cog-docs no-op; got {refresh_calls7}"

        print("PASS fixture_7_refresh_not_fired_on_noop")
    except Exception as exc:
        print(f"FAIL fixture_7_refresh_not_fired_on_noop: {exc}")
        failures += 1

    # ------------------------------------------------------------------
    # Fixture 8 — a refresh that returns False does not change the rc
    # A failing dashboard refresh must never turn a successful action into a
    # failure exit code.
    # ------------------------------------------------------------------
    try:
        tmp8 = tempfile.mkdtemp(prefix="tw_test8_")
        cog_docs8 = Path(tmp8) / "cog-docs"
        feat_dir8 = cog_docs8 / "docs" / "features" / "my-slug"
        feat_dir8.mkdir(parents=True, exist_ok=True)
        (cog_docs8 / "docs" / "work").mkdir(parents=True, exist_ok=True)

        with contextlib.redirect_stdout(io.StringIO()):
            rc8 = run(
                "open",
                repo_root_arg=str(cog_docs8),
                slug="my-slug",
                wi_id_arg=None,
                branch="main",
                env={},
                sibling_base=Path(tmp8),
                host="h",
                now="2026-06-03T17:00:00Z",
                materialized=[],
                refresh=lambda p: False,
            )
        assert rc8 == 0, f"failing refresh must not change rc; got {rc8}"

        print("PASS fixture_8_failing_refresh_keeps_rc_zero")
    except Exception as exc:
        print(f"FAIL fixture_8_failing_refresh_keeps_rc_zero: {exc}")
        failures += 1

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    total = 8
    passed = total - failures
    print(f"\n{passed}/{total} fixtures passed, {failures} failed.")
    return failures


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Track WIP sentinel state for feature/bug work items."
    )
    parser.add_argument(
        "action",
        nargs="?",
        choices=["open", "touch", "close"],
        help="Lifecycle action: open (create/refresh WIP.md), touch (advance timestamp), close (remove WIP.md)",
    )
    parser.add_argument(
        "--repo-root",
        default=None,
        help="Explicit path to the cog-docs repository root (overrides COG_DOCS_ROOT and sibling probe)",
    )
    parser.add_argument(
        "--slug",
        default=None,
        help="Feature/bug slug (e.g. 'is-target-action-filtering'); bypasses materialized lookup",
    )
    parser.add_argument(
        "--wi-id",
        default=None,
        help="Work-item ID (e.g. '56618'); bypasses branch-name extraction",
    )
    parser.add_argument(
        "--test",
        action="store_true",
        help="Run built-in self-tests and exit with failure count",
    )
    parser.add_argument(
        "--no-refresh",
        action="store_true",
        help="Skip regenerating DASHBOARD.md after the action (debugging/perf)",
    )
    args = parser.parse_args()

    if args.test:
        sys.exit(run_self_tests())

    if not args.action:
        parser.error("action (open|touch|close) is required unless --test is passed")

    # --- Gather environment / clock / network (injected into pure run()) ---
    branch: str | None
    try:
        import subprocess
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            check=False,
        )
        branch = result.stdout.strip() or None
    except Exception:
        branch = None

    git_root: str | None
    try:
        import subprocess  # noqa: F811 (re-import is harmless)
        result2 = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=False,
        )
        git_root = result2.stdout.strip() or None
    except Exception:
        git_root = None

    sibling_base = Path(git_root).parent if git_root else Path.cwd().parent

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    host = socket.gethostname()

    rc = run(
        args.action,
        repo_root_arg=args.repo_root,
        slug=args.slug,
        wi_id_arg=args.wi_id,
        branch=branch,
        env=dict(os.environ),
        sibling_base=sibling_base,
        host=host,
        now=now,
        refresh=None if args.no_refresh else refresh_dashboard,
    )
    sys.exit(rc)


if __name__ == "__main__":
    main()
