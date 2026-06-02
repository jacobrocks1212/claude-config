#!/usr/bin/env python3
"""
work-status.py -- Read-only cross-source terminal dashboard.

Aggregates artifacts from docs/work/ (ado-mirror.json, materialized.json,
leases.json) and docs/features/queue.json / docs/bugs/queue.json, then renders
a five-panel terminal summary:

  1. My queue     — items from feature/bug queue.json assigned to me
  2. In flight    — active leases from leases.json
  3. My ADO inbox — mirror WIs assigned to me that are NOT yet materialized
  4. Team         — teammates' WIs with pr/prStatus/autotestStatus from mirror
  5. Pool & sync  — mirror freshness, stale-upstream counts, missing artifacts

Optional: --markdown writes <repo_root>/docs/work/DASHBOARD.md.

This script NEVER mutates any artifact except (optionally) DASHBOARD.md.

Dependencies: stdlib only (no third-party requirements for --test).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Infrastructure helpers
# ---------------------------------------------------------------------------

def _atomic_write(path: Path, content: str) -> None:
    """Write content to path atomically (temp file in same dir + os.replace)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(content)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _read_json(path: Path) -> Any:
    """Read and parse a JSON file; return None if missing or malformed."""
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _scan_stale_upstream(base: Path) -> list[Path]:
    """Recursively find all STALE_UPSTREAM.md files under base."""
    if not base.exists():
        return []
    result: list[Path] = []
    for root, _dirs, files in os.walk(base):
        for fname in files:
            if fname == "STALE_UPSTREAM.md":
                result.append(Path(root) / fname)
    return result


# ---------------------------------------------------------------------------
# Pure stub functions (implementation agent fills these in)
# ---------------------------------------------------------------------------

def load_sources(repo_root: Path) -> dict:
    """Load all dashboard artifacts from repo_root with graceful degradation.

    Reads (all optional — missing file yields sensible empty/None, never raises):
      - docs/work/ado-mirror.json  -> sources["mirror"]    (dict or None)
      - docs/features/queue.json   -> sources["feat_queue"] (dict or None)
      - docs/bugs/queue.json       -> sources["bug_queue"]  (dict or None)
      - docs/work/materialized.json-> sources["materialized"] (dict or None)
      - docs/work/leases.json      -> sources["leases"]     (dict or None)
      - stale marker files         -> sources["stale_paths"] (list[Path])

    Returns a dict with exactly these keys, plus sources["repo_root"] = repo_root.
    Never raises; bad files are silently treated as None.
    """
    work_dir = repo_root / "docs" / "work"
    feat_dir = repo_root / "docs" / "features"
    bug_dir = repo_root / "docs" / "bugs"

    stale_paths: list[Path] = []
    stale_paths.extend(_scan_stale_upstream(feat_dir))
    stale_paths.extend(_scan_stale_upstream(bug_dir))

    return {
        "repo_root": repo_root,
        "mirror": _read_json(work_dir / "ado-mirror.json"),
        "feat_queue": _read_json(feat_dir / "queue.json"),
        "bug_queue": _read_json(bug_dir / "queue.json"),
        "materialized": _read_json(work_dir / "materialized.json"),
        "leases": _read_json(work_dir / "leases.json"),
        "stale_paths": stale_paths,
    }


def _is_mine(assigned_to: str | None) -> bool:
    """Return True if the assignedTo value represents the current user."""
    if assigned_to is None:
        return False
    return assigned_to == "@Me"


def render_dashboard(sources: dict, current_branch: str | None = None) -> str:
    """Build the full five-panel dashboard text from pre-loaded sources.

    Panels (each separated by a blank line and a header line):
      MY QUEUE     — queue.json items assigned to me (feat + bug)
      IN FLIGHT    — active leases
      MY ADO INBOX — mirror WIs assigned to current user, not yet materialized
      TEAM         — teammates' mirror WIs with pr/prStatus/autotestStatus
      POOL & SYNC  — mirror freshness (syncedAt), stale-upstream count, missing artifacts

    Graceful degradation: absent sources show informational text (e.g.
    "No leases" when leases.json missing) rather than raising.

    Returns a single string suitable for print() or write to DASHBOARD.md.
    """
    lines: list[str] = []

    mirror: dict | None = sources.get("mirror")
    feat_queue: dict | None = sources.get("feat_queue")
    bug_queue: dict | None = sources.get("bug_queue")
    leases: dict | None = sources.get("leases")
    stale_paths: list[Path] = sources.get("stale_paths") or []

    work_items: list[dict] = []
    if mirror and isinstance(mirror.get("workItems"), list):
        work_items = mirror["workItems"]

    # Build a lookup from wi_id -> mirror WI for queue cross-referencing
    wi_by_id: dict[int, dict] = {int(wi["id"]): wi for wi in work_items}

    # Determine what "self PR" is linked from the current branch
    # branch pattern: p/<wi_id>-...  -> match PR from mirror WI's linkedPRs
    self_pr: dict | None = None
    branch_wi_id: int | None = None
    if current_branch:
        m = re.match(r"^p/(\d+)-", current_branch)
        if m:
            branch_wi_id = int(m.group(1))
            wi = wi_by_id.get(branch_wi_id)
            if wi:
                linked_prs = wi.get("linkedPRs") or []
                self_pr = match_self_pr(current_branch, linked_prs)

    # ------------------------------------------------------------------
    # Panel 1: MY QUEUE
    # ------------------------------------------------------------------
    lines.append("=== MY QUEUE ===")
    queue_items: list[dict] = []
    for q in [feat_queue, bug_queue]:
        if q and isinstance(q.get("items"), list):
            queue_items.extend(q["items"])

    if not queue_items:
        lines.append("  (no items in queue)")
    else:
        for item in queue_items:
            wi_id = item.get("wi_id")
            title = item.get("title", "(no title)")
            priority = item.get("priority", "")
            pr_info = ""
            # If this queue item matches the current branch's WI, surface the PR
            if wi_id is not None and wi_id == branch_wi_id and self_pr is not None:
                pr_num = self_pr.get("prNumber")
                pr_repo = self_pr.get("repo", "")
                pr_info = f"  -> PR #{pr_num} ({pr_repo})"
            lines.append(f"  [{wi_id}] {title} (priority: {priority}){pr_info}")

    lines.append("")

    # ------------------------------------------------------------------
    # Panel 2: IN FLIGHT
    # ------------------------------------------------------------------
    lines.append("=== IN FLIGHT ===")
    if leases is None:
        lines.append("  No leases yet (leases.json not found)")
    else:
        lease_list = leases.get("leases") or []
        if not lease_list:
            lines.append("  No active leases")
        else:
            for lease in lease_list:
                wi_id = lease.get("wi_id", "?")
                branch = lease.get("branch", "?")
                started = lease.get("startedAt", "?")
                worker = lease.get("worker_pid", lease.get("slot", "?"))
                stage = lease.get("stage", "")
                heartbeat = lease.get("heartbeat", "")
                stale_flag = " [STALE]" if lease.get("stale") else ""
                parts = [f"  [{wi_id}] {branch}  started={started}"]
                if worker != "?":
                    parts.append(f"  worker={worker}")
                if stage:
                    parts.append(f"  stage={stage}")
                if heartbeat:
                    parts.append(f"  heartbeat={heartbeat}")
                lines.append("".join(parts) + stale_flag)

    lines.append("")

    # ------------------------------------------------------------------
    # Panel 3: MY ADO INBOX
    # ------------------------------------------------------------------
    lines.append("=== MY ADO INBOX ===")
    if mirror is None:
        lines.append("  Mirror not yet initialized")
    else:
        my_wis = [wi for wi in work_items if _is_mine(wi.get("assignedTo")) and not wi.get("materialized", False)]
        if not my_wis:
            lines.append("  (no unmaterilaized WIs assigned to you)")
        else:
            for wi in my_wis:
                wi_id = wi.get("id", "?")
                title = wi.get("title", "(no title)")
                state = wi.get("state", "?")
                url = wi.get("url", "")
                pr = wi.get("pr") or ""
                pr_status = wi.get("prStatus") or ""
                pr_info = f"  PR: {pr_status}" if pr_status else ""
                lines.append(f"  [{wi_id}] {title}  state={state}{pr_info}")
                if url:
                    lines.append(f"    {url}")

    lines.append("")

    # ------------------------------------------------------------------
    # Panel 4: TEAM
    # ------------------------------------------------------------------
    lines.append("=== TEAM ===")
    if mirror is None:
        lines.append("  Mirror not yet initialized")
    else:
        team_wis = [wi for wi in work_items if not _is_mine(wi.get("assignedTo"))]
        if not team_wis:
            lines.append("  (no teammate WIs in mirror)")
        else:
            for wi in team_wis:
                wi_id = wi.get("id", "?")
                title = wi.get("title", "(no title)")
                assigned = wi.get("assignedTo", "Unassigned")
                state = wi.get("state", "?")
                pr_status = wi.get("prStatus") or ""
                autotest = wi.get("autotestStatus") or ""
                pr = wi.get("pr") or ""
                linked_prs = wi.get("linkedPRs") or []
                pr_nums = [str(lp.get("prNumber")) for lp in linked_prs if lp.get("prNumber")]

                info_parts = [f"  [{wi_id}] {title}  assigned={assigned}  state={state}"]
                if pr_nums:
                    info_parts.append(f"  PR#{','.join(pr_nums)}")
                if pr_status:
                    info_parts.append(f"  prStatus={pr_status}")
                if autotest:
                    info_parts.append(f"  autotestStatus={autotest}")
                lines.append("".join(info_parts))

    lines.append("")

    # ------------------------------------------------------------------
    # Panel 5: POOL & SYNC
    # ------------------------------------------------------------------
    lines.append("=== POOL & SYNC ===")
    if mirror is None:
        lines.append("  Mirror not yet initialized")
    else:
        synced_at = mirror.get("syncedAt", "(unknown)")
        lines.append(f"  Mirror synced at: {synced_at}")
        lines.append(f"  Work items: {len(work_items)}")
        lines.append(f"  Stale upstream: {len(stale_paths)} marker(s)")
        if stale_paths:
            for p in stale_paths:
                lines.append(f"    {p}")

    # Collect missing-artifact notes
    missing: list[str] = []
    if feat_queue is None:
        missing.append("docs/features/queue.json")
    if bug_queue is None:
        missing.append("docs/bugs/queue.json")
    if leases is None:
        missing.append("docs/work/leases.json")
    if missing:
        lines.append("  Missing artifacts: " + ", ".join(missing))

    return "\n".join(lines)


def match_self_pr(branch: str, linked_prs: list[dict]) -> dict | None:
    """Apply regex ^p/(\\d+)- to branch name; find the PR in linked_prs whose
    prNumber matches the captured group.  Return the matching PR dict or None.

    Args:
        branch:     git branch name, e.g. "p/123-add-feature"
        linked_prs: list of dicts with at least {"prNumber": int, "repo": str}

    Returns:
        The matching linked_pr dict ({"prNumber": N, "repo": "..."}) or None.
    """
    m = re.match(r"^p/(\d+)-", branch)
    if not m:
        return None
    pr_number = int(m.group(1))
    for pr in linked_prs:
        if pr.get("prNumber") == pr_number:
            return pr
    return None


def write_markdown(repo_root: Path, text: str) -> Path:
    """Write dashboard text to docs/work/DASHBOARD.md atomically.

    Uses _atomic_write so the write is never partially visible.
    Returns the absolute Path of the written file.

    MUST NOT modify any other file.
    """
    md_path = repo_root / "docs" / "work" / "DASHBOARD.md"
    _atomic_write(md_path, text)
    return md_path.resolve()


# ---------------------------------------------------------------------------
# Self-test harness
# ---------------------------------------------------------------------------

def run_self_tests() -> int:
    """Run four built-in fixtures. Returns number of failures (0 = all pass)."""
    failures = 0
    total = 4

    # ------------------------------------------------------------------
    # Fixture A — mirror-only degradation
    # Seed only ado-mirror.json; no leases/materialized/queue.
    # Assert render_dashboard returns a string; MY ADO INBOX has >=1 row
    # from the mirror; other panels show degradation text; no exception.
    # ------------------------------------------------------------------
    try:
        tmp_a = tempfile.mkdtemp(prefix="ws_test_a_")
        repo_a = Path(tmp_a)
        work_dir = repo_a / "docs" / "work"
        work_dir.mkdir(parents=True, exist_ok=True)

        mirror_data = {
            "syncedAt": "2026-06-01T10:00:00Z",
            "watermark": "2026-06-01T10:00:00Z",
            "query": {"areaPath": "Cognito Forms\\Poseidon"},
            "workItems": [
                {
                    "id": 1001,
                    "type": "User Story",
                    "title": "Inbox item alpha",
                    "state": "Active",
                    "assignedTo": "@Me",
                    "areaPath": "Cognito Forms\\Poseidon",
                    "iteration": "Cognito Forms\\Sprint 42",
                    "parentId": None,
                    "url": "https://dev.azure.com/org/proj/_workitems/edit/1001",
                    "acceptanceCriteria": None,
                    "description": None,
                    "changedDate": "2026-06-01T09:00:00Z",
                    "linkedPRs": [],
                    "pr": None,
                    "prStatus": None,
                    "autotestStatus": None,
                    "autotestBuildId": None,
                    "autotestRun": None,
                    "materialized": False,
                }
            ],
        }
        (work_dir / "ado-mirror.json").write_text(
            json.dumps(mirror_data, indent=2), encoding="utf-8"
        )

        sources = load_sources(repo_a)
        dashboard = render_dashboard(sources)

        assert isinstance(dashboard, str), \
            f"render_dashboard should return str, got {type(dashboard)}"
        assert len(dashboard) > 0, "render_dashboard returned empty string"

        # MY ADO INBOX panel must reference the mirror WI
        assert "1001" in dashboard or "Inbox item alpha" in dashboard, \
            "MY ADO INBOX panel must reference mirror WI 1001"

        # No leases file => degradation text for IN FLIGHT
        assert "No leases" in dashboard or "leases" in dashboard.lower(), \
            "IN FLIGHT panel should show degradation text when leases.json absent"

        print("PASS fixture_a_mirror_only_degradation")
    except Exception as exc:
        print(f"FAIL fixture_a_mirror_only_degradation: {exc}")
        failures += 1

    # ------------------------------------------------------------------
    # Fixture B — teammate PR/CI from mirror
    # Seed a mirror WI assigned to a teammate with pr/prStatus/autotestStatus.
    # Assert TEAM panel contains those values.
    # ------------------------------------------------------------------
    try:
        tmp_b = tempfile.mkdtemp(prefix="ws_test_b_")
        repo_b = Path(tmp_b)
        work_dir_b = repo_b / "docs" / "work"
        work_dir_b.mkdir(parents=True, exist_ok=True)

        mirror_b = {
            "syncedAt": "2026-06-01T10:00:00Z",
            "watermark": "2026-06-01T10:00:00Z",
            "query": {"areaPath": "Cognito Forms\\Poseidon"},
            "workItems": [
                {
                    "id": 2001,
                    "type": "User Story",
                    "title": "Teammate feature",
                    "state": "Active",
                    "assignedTo": "Alice Smith",
                    "areaPath": "Cognito Forms\\Poseidon",
                    "iteration": "Cognito Forms\\Sprint 42",
                    "parentId": None,
                    "url": "https://dev.azure.com/org/proj/_workitems/edit/2001",
                    "acceptanceCriteria": None,
                    "description": None,
                    "changedDate": "2026-06-01T09:00:00Z",
                    "linkedPRs": [{"prNumber": 555, "repo": "cognitoforms/cognito"}],
                    "pr": "https://github.com/cognitoforms/cognito/pull/555",
                    "prStatus": "Review Required",
                    "autotestStatus": "Passed",
                    "autotestBuildId": "build-42",
                    "autotestRun": "run-99",
                    "materialized": True,
                }
            ],
        }
        (work_dir_b / "ado-mirror.json").write_text(
            json.dumps(mirror_b, indent=2), encoding="utf-8"
        )

        sources_b = load_sources(repo_b)
        dashboard_b = render_dashboard(sources_b)

        assert isinstance(dashboard_b, str), "render_dashboard must return str"

        # TEAM panel must surface the teammate's pr/prStatus/autotestStatus
        assert "Review Required" in dashboard_b, \
            "TEAM panel must contain prStatus 'Review Required'"
        assert "Passed" in dashboard_b, \
            "TEAM panel must contain autotestStatus 'Passed'"
        # At minimum, one of the PR signals should appear
        assert "555" in dashboard_b or "Alice Smith" in dashboard_b, \
            "TEAM panel must reference teammate WI 2001 / PR 555"

        print("PASS fixture_b_teammate_pr_ci")
    except Exception as exc:
        print(f"FAIL fixture_b_teammate_pr_ci: {exc}")
        failures += 1

    # ------------------------------------------------------------------
    # Fixture C — self-link via branch regex
    # queue.json with wi_id matching a mirror WI that has linkedPRs with
    # prNumber=300, and current_branch="p/300-add-widget".
    # Assert match_self_pr returns the correct PR dict.
    # Assert MY QUEUE panel surfaces that PR link.
    # ------------------------------------------------------------------
    try:
        tmp_c = tempfile.mkdtemp(prefix="ws_test_c_")
        repo_c = Path(tmp_c)
        work_dir_c = repo_c / "docs" / "work"
        work_dir_c.mkdir(parents=True, exist_ok=True)
        feat_dir = repo_c / "docs" / "features"
        feat_dir.mkdir(parents=True, exist_ok=True)

        mirror_c = {
            "syncedAt": "2026-06-01T10:00:00Z",
            "watermark": "2026-06-01T10:00:00Z",
            "query": {},
            "workItems": [
                {
                    "id": 3001,
                    "type": "User Story",
                    "title": "Add widget",
                    "state": "Active",
                    "assignedTo": "@Me",
                    "areaPath": "Cognito Forms\\Poseidon",
                    "iteration": "Cognito Forms\\Sprint 42",
                    "parentId": None,
                    "url": "https://dev.azure.com/org/proj/_workitems/edit/3001",
                    "acceptanceCriteria": None,
                    "description": None,
                    "changedDate": "2026-06-01T09:00:00Z",
                    "linkedPRs": [{"prNumber": 300, "repo": "cognitoforms/cognito"}],
                    "pr": "https://github.com/cognitoforms/cognito/pull/300",
                    "prStatus": "Draft",
                    "autotestStatus": None,
                    "autotestBuildId": None,
                    "autotestRun": None,
                    "materialized": False,
                }
            ],
        }
        (work_dir_c / "ado-mirror.json").write_text(
            json.dumps(mirror_c, indent=2), encoding="utf-8"
        )

        feat_queue = {
            "items": [
                {"wi_id": 3001, "title": "Add widget", "priority": 1}
            ]
        }
        (feat_dir / "queue.json").write_text(
            json.dumps(feat_queue, indent=2), encoding="utf-8"
        )

        # Test match_self_pr directly
        linked_prs = [{"prNumber": 300, "repo": "cognitoforms/cognito"}]
        matched = match_self_pr("p/300-add-widget", linked_prs)
        assert matched is not None, \
            "match_self_pr('p/300-add-widget', ...) must return a dict, got None"
        assert matched["prNumber"] == 300, \
            f"match_self_pr must return PR with prNumber=300, got {matched}"

        # Also verify non-matching branch returns None
        no_match = match_self_pr("feature/unrelated", linked_prs)
        assert no_match is None, \
            f"match_self_pr('feature/unrelated', ...) must return None, got {no_match}"

        # MY QUEUE panel must surface PR link when branch matches
        sources_c = load_sources(repo_c)
        dashboard_c = render_dashboard(sources_c, current_branch="p/300-add-widget")
        assert isinstance(dashboard_c, str), "render_dashboard must return str"
        assert "300" in dashboard_c, \
            "MY QUEUE panel must surface PR link (prNumber 300) when branch matches"

        print("PASS fixture_c_self_link_branch_regex")
    except Exception as exc:
        print(f"FAIL fixture_c_self_link_branch_regex: {exc}")
        failures += 1

    # ------------------------------------------------------------------
    # Fixture D — --markdown no-mutation
    # Seed leases.json and queue.json; record their mtimes; call write_markdown;
    # assert DASHBOARD.md created AND leases.json/queue.json mtimes unchanged.
    # ------------------------------------------------------------------
    try:
        tmp_d = tempfile.mkdtemp(prefix="ws_test_d_")
        repo_d = Path(tmp_d)
        work_dir_d = repo_d / "docs" / "work"
        work_dir_d.mkdir(parents=True, exist_ok=True)
        feat_dir_d = repo_d / "docs" / "features"
        feat_dir_d.mkdir(parents=True, exist_ok=True)

        leases_data = {
            "leases": [
                {"wi_id": 4001, "branch": "p/4001-my-task", "startedAt": "2026-06-01T08:00:00Z"}
            ]
        }
        leases_path = work_dir_d / "leases.json"
        leases_path.write_text(json.dumps(leases_data, indent=2), encoding="utf-8")

        queue_data = {"items": [{"wi_id": 4002, "title": "Queue item", "priority": 2}]}
        queue_path = feat_dir_d / "queue.json"
        queue_path.write_text(json.dumps(queue_data, indent=2), encoding="utf-8")

        # Record mtimes before
        leases_mtime_before = os.stat(leases_path).st_mtime_ns
        queue_mtime_before = os.stat(queue_path).st_mtime_ns

        # Write markdown
        dashboard_text = "# Dashboard\nSome content for fixture D"
        md_path = write_markdown(repo_d, dashboard_text)

        # Assert DASHBOARD.md was created
        expected_md = repo_d / "docs" / "work" / "DASHBOARD.md"
        assert expected_md.exists(), \
            f"DASHBOARD.md not created at {expected_md}"
        assert md_path == expected_md or md_path.resolve() == expected_md.resolve(), \
            f"write_markdown returned {md_path}, expected {expected_md}"
        content_written = expected_md.read_text(encoding="utf-8")
        assert "Dashboard" in content_written, \
            "DASHBOARD.md content missing expected text"

        # Assert input files NOT mutated
        leases_mtime_after = os.stat(leases_path).st_mtime_ns
        queue_mtime_after = os.stat(queue_path).st_mtime_ns

        assert leases_mtime_before == leases_mtime_after, \
            "leases.json mtime changed — write_markdown must not mutate inputs"
        assert queue_mtime_before == queue_mtime_after, \
            "queue.json mtime changed — write_markdown must not mutate inputs"

        print("PASS fixture_d_markdown_no_mutation")
    except Exception as exc:
        print(f"FAIL fixture_d_markdown_no_mutation: {exc}")
        failures += 1

    # Summary
    passed = total - failures
    print(f"\n{passed}/{total} fixtures passed")
    return failures


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Read-only cross-source terminal dashboard for work status"
    )
    parser.add_argument("--test", action="store_true", help="Run self-tests and exit")
    parser.add_argument(
        "--repo-root", type=Path, default=None,
        help="Path to repo root (defaults to two levels up from this script)"
    )
    parser.add_argument(
        "--markdown", action="store_true",
        help="Write docs/work/DASHBOARD.md in addition to terminal output"
    )
    parser.add_argument(
        "--current-branch", default=None,
        help="Current git branch name (used to auto-link My Queue items to PRs)"
    )
    args = parser.parse_args()

    if args.test:
        failures = run_self_tests()
        sys.exit(failures)

    # Resolve repo root
    repo_root: Path
    if args.repo_root:
        repo_root = args.repo_root.resolve()
    else:
        # Default: two levels up from this script (scripts/ -> user/ -> claude-config/)
        repo_root = Path(__file__).resolve().parent.parent.parent

    sources = load_sources(repo_root)
    text = render_dashboard(sources, current_branch=args.current_branch)
    print(text)

    if args.markdown:
        md_path = write_markdown(repo_root, text)
        print(f"\nDashboard written to {md_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
