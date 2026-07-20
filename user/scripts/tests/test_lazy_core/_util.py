#!/usr/bin/env python3
"""
_util.py — split shard of test_lazy_core.py (lazy-core-package-decomposition
WU-2). One of 12 per-seam test files under user/scripts/tests/test_lazy_core/;
see conftest.py and the sibling files for the rest of the split.

Run under pytest (collected automatically), or standalone via:
    python3 user/scripts/tests/test_lazy_core/_util.py
Exit 0 on pass, non-zero on any failure. No third-party dependencies.
"""

from __future__ import annotations

import ast
import difflib
import inspect
import json
import os
import platform
import re
import subprocess
import sys
import tempfile
from pathlib import Path

# This file lives 2 directories deeper than the original flat
# test_lazy_core.py (user/scripts/tests/test_lazy_core/ vs. user/scripts/),
# so parents[2] is the scripts dir where lazy_core/ actually lives:
# parents[0]=test_lazy_core/, parents[1]=tests/, parents[2]=user/scripts.
_SCRIPTS_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_SCRIPTS_DIR))



_IMPORT_ERROR: Exception | None = None
lazy_core = None

try:
    import lazy_core  # type: ignore[import]
except ImportError as exc:
    _IMPORT_ERROR = exc


def _guard() -> None:
    """Raise _ModuleMissing if lazy_core hasn't been extracted yet."""
    if _IMPORT_ERROR is not None:
        raise _ModuleMissing(f"lazy_core not importable: {_IMPORT_ERROR}")


def _collect_registered_test_names(module_source: str) -> set:
    """AST-extract the string-literal names registered in a module's `_TESTS =
    [...]` / `_TESTS = _TESTS + [...]` assignments — used by
    test_no_orphaned_test_functions (test_misc.py) to check each SIBLING
    file's own registry without importing it (imports would re-run every
    module-level side effect across the whole split package)."""
    import ast
    tree = ast.parse(module_source)
    names: set = set()
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if len(node.targets) != 1 or not isinstance(node.targets[0], ast.Name):
            continue
        if node.targets[0].id != "_TESTS":
            continue
        # RHS is either a List literal, or BinOp(List + List) for the
        # `_TESTS = _TESTS + [...]` accretion form. Walk all List nodes.
        for sub in ast.walk(node.value):
            if isinstance(sub, ast.List):
                for elt in sub.elts:
                    if (isinstance(elt, ast.Tuple) and elt.elts
                            and isinstance(elt.elts[0], ast.Constant)
                            and isinstance(elt.elts[0].value, str)):
                        names.add(elt.elts[0].value)
    return names




# ---------------------------------------------------------------------------
# Cross-platform smoke-output normalization helper (Task A)
# ---------------------------------------------------------------------------

def _normalize_smoke_output(text: str) -> str:
    """Canonicalize smoke-harness output so Windows and POSIX runs produce
    byte-identical results after normalization.

    Three transforms are applied in order:

    1. Replace the platform-specific absolute temp-root prefix that precedes a
       ``…-fixtures-<suffix>`` directory with the stable placeholder ``<TMP>/``.
       This covers:
         • POSIX form: ``/tmp/claude-1000/lazy-state-fixtures-<suffix>``
           (any ``/…/`` prefix ending just before the fixtures dir name)
         • Windows form (single-backslash, as printed by Python directly):
           ``C:\\Users\\…\\Temp\\lazy-state-fixtures-<suffix>``
         • Windows form (double-backslash, as emitted inside JSON strings):
           ``C:\\\\Users\\\\…\\\\Temp\\\\lazy-state-fixtures-<suffix>``
       The replacement preserves the fixtures-dir name so that step 2 can
       still match and canonicalize its random suffix.

    2. Replace the random fixtures suffix for BOTH scripts:
       ``(lazy-state-fixtures-|bug-state-fixtures-)[A-Za-z0-9_]+``
       → ``\\1XXXXXXXX``

    3. Canonicalize path separators **inside** the normalized temp path tail
       (the segment after ``<TMP>/…-fixtures-XXXXXXXX``): both single and
       double backslashes → forward slashes.  Only tokens that follow
       ``<TMP>/`` are touched, so normal prose is unaffected.

    Applying this function to already-normalized text is idempotent:
    ``<TMP>/`` is not a valid OS temp root, so step 1 is a no-op; step 2
    only rewrites the suffix pattern which after normalization is ``XXXXXXXX``
    (no match); step 3 only applies to segments following ``<TMP>/``.
    """
    # Step 1 — strip the platform-specific temp-root prefix.
    #
    # Character-class note: inside [...] a single \ must be written as \\
    # in a Python raw string.  We use r'...' throughout to keep the regex
    # readable without extra escaping.
    #
    # Windows paths use \ (or \\, when JSON-encoded) as separators.
    # The path segments themselves contain letters, digits, spaces (rare in
    # temp paths), hyphens — but NOT quotes, /, or \.
    # We match: drive-letter colon, then one or more separator chars, then
    # one-or-more (segment + separators) groups, ending immediately before
    # the fixtures dir name.
    #
    # POSIX paths use / and contain no quotes or whitespace.
    _TEMP_ROOT_RE = re.compile(
        r'(?:[A-Za-z]:[/\\]+(?:[^/"\\<>\s]+[/\\]+)+|/(?:[^/\s"]+/)+)'
        r'(?=(?:lazy-state-fixtures-|bug-state-fixtures-))'
    )
    text = _TEMP_ROOT_RE.sub("<TMP>/", text)

    # Step 2 — replace the random fixtures suffix.
    _SUFFIX_RE = re.compile(r'(lazy-state-fixtures-|bug-state-fixtures-)[A-Za-z0-9_]+')
    text = _SUFFIX_RE.sub(r'\1XXXXXXXX', text)

    # Step 3 — canonicalize path separators in the normalized path tail.
    # After steps 1+2 the tail looks like:
    #   <TMP>/lazy-state-fixtures-XXXXXXXX\\sub\\path  (Windows double-bs)
    #   <TMP>/lazy-state-fixtures-XXXXXXXX\sub\path    (Windows single-bs)
    #   <TMP>/lazy-state-fixtures-XXXXXXXX/sub/path    (POSIX — already clean)
    # Replace \\ first (two chars), then any remaining lone \.
    def _fix_sep(m: re.Match) -> str:
        s = m.group(0)
        s = s.replace('\\\\', '/')   # double-backslash (JSON-encoded Windows)
        s = s.replace('\\', '/')     # single-backslash (direct Windows print)
        return s

    # Match from <TMP>/ through to the end of the contiguous path token
    # (no spaces, no " boundary — paths appear inside JSON strings or prose).
    _PATH_TOKEN_RE = re.compile(r'<TMP>/[^\s"]+')
    text = _PATH_TOKEN_RE.sub(_fix_sep, text)

    return text




class _ModuleMissing(Exception):
    """Raised inside a test body when lazy_core is not yet importable."""




# ---------------------------------------------------------------------------
# Tests: derive_stage — maps artifact ladder to a stage label
# ---------------------------------------------------------------------------

def _make_laddered_dir(td: str) -> Path:
    """Helper: build a fully-laddered item dir (spec→research→phases→plan→implement)."""
    d = Path(td)
    (d / "SPEC.md").write_text("# Feature Spec\n", encoding="utf-8")
    (d / "RESEARCH.md").write_text("# Research\n", encoding="utf-8")
    (d / "PHASES.md").write_text(
        "# Phases\n\n- [x] Phase 1 done\n- [ ] Phase 2 todo\n",
        encoding="utf-8",
    )
    plans_dir = d / "plans"
    plans_dir.mkdir()
    (plans_dir / "plan-phase-1.md").write_text(
        "---\nkind: implementation-plan\nstatus: Complete\nphases:\n  - 1\n---\n",
        encoding="utf-8",
    )
    return d




# ---------------------------------------------------------------------------
# Tests: track_open / track_touch / track_close
# ---------------------------------------------------------------------------

_NOW1 = "2026-06-03T10:00:00Z"




# ---------------------------------------------------------------------------
# Tests: verify_ledger — WU-1 completion-ledger verdict
# ---------------------------------------------------------------------------

def _make_git_repo_with_origin(td: str) -> tuple:
    """Helper: create a real git repo with a bare-repo origin so @{u} resolves.

    Returns (repo_root: Path, origin_path: Path).

    Steps:
      1. git init <repo_root>
      2. git init --bare <origin_path>
      3. git remote add origin <origin_path>
      4. set user.email + user.name in repo config
      5. create a minimal initial commit
      6. git push -u origin <branch>  so @{u} is set

    After this call the working tree is clean, HEAD == @{u}.
    """
    root = Path(td) / "repo"
    origin = Path(td) / "origin.git"
    root.mkdir()
    origin.mkdir()

    def _run(cmd: list, cwd=None) -> None:
        result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=cwd)
        if result.returncode != 0:
            raise RuntimeError(
                f"git fixture setup failed (cmd={cmd!r}): {result.stderr.strip()}"
            )

    _run(["git", "init", "-q", str(root)])
    _run(["git", "init", "--bare", "-q", str(origin)])
    _run(["git", "-C", str(root), "remote", "add", "origin", str(origin)])
    _run(["git", "-C", str(root), "config", "user.email", "test@test.local"])
    _run(["git", "-C", str(root), "config", "user.name", "Test"])

    # Create a minimal initial file and commit so the branch exists.
    (root / "README.md").write_text("# Repo\n", encoding="utf-8")
    _run(["git", "-C", str(root), "add", "README.md"])
    _run(["git", "-C", str(root), "commit", "-q", "-m", "init"])

    # Detect branch name (could be "main" or "master" depending on git config).
    branch_result = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "--abbrev-ref", "HEAD"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    branch = branch_result.stdout.strip() or "main"

    _run(["git", "-C", str(root), "push", "-u", "origin", branch])
    return root, origin




# ---------------------------------------------------------------------------
# Tests: apply_pseudo — WU-2 shared deterministic sentinel/receipt dispatcher
# ---------------------------------------------------------------------------

# ---- Helpers shared across apply_pseudo tests ----

def _write_skip_mcp_test(spec_dir: Path) -> Path:
    """Write a minimal valid SKIP_MCP_TEST.md (kind: skip-mcp-test) into spec_dir."""
    p = spec_dir / "SKIP_MCP_TEST.md"
    p.write_text(
        "---\n"
        "kind: skip-mcp-test\n"
        "feature_id: test-feature\n"
        "reason: no audio path to test\n"
        "date: 2026-06-10\n"
        "---\n\n"
        "# Skip MCP Test\n",
        encoding="utf-8",
    )
    return p




def _write_mcp_test_results(
    spec_dir: Path,
    scenarios: list,
    *,
    kind: str = "mcp-test-results",
    result: str | None = "all-passing",
    pass_count="auto",
    total_count="auto",
    validated_commit: str | None = None,
) -> Path:
    """Write an MCP_TEST_RESULTS.md per the sentinel-frontmatter.md schema.

    Defaults produce a canonical PASSING run (``result: all-passing``,
    ``pass_count == total_count == len(scenarios)``) so happy-path fixtures
    satisfy the ``__write_validated_from_results__`` result-literal and count
    gates.  Keyword overrides shape the refusal fixtures:

    - ``kind`` — frontmatter ``kind:`` value (wrong-kind gate fixtures).
    - ``result=None`` / ``pass_count=None`` / ``total_count=None`` — OMIT the
      corresponding frontmatter line entirely (missing-field fixtures).
    - ``pass_count`` / ``total_count`` default to the sentinel string
      ``"auto"`` meaning ``len(scenarios)``.
    - ``validated_commit`` — omitted unless given (legacy results files
      predate the sha-freshness anchor; the schema requires it going forward).
    """
    p = spec_dir / "MCP_TEST_RESULTS.md"
    scenarios_yaml = "".join(f"  - {s}\n" for s in scenarios)
    if pass_count == "auto":
        pass_count = len(scenarios)
    if total_count == "auto":
        total_count = len(scenarios)
    lines = [
        "---",
        f"kind: {kind}",
        "feature_id: test-feature",
        f"scenarios:\n{scenarios_yaml.rstrip()}".rstrip(),
        "date: 2026-06-10",
    ]
    if result is not None:
        lines.append(f"result: {result}")
    if pass_count is not None:
        lines.append(f"pass_count: {pass_count}")
    if total_count is not None:
        lines.append(f"total_count: {total_count}")
    if validated_commit is not None:
        # Quoted: an UNQUOTED all-zeros sha would YAML-parse as int 0 (falsy),
        # silently downgrading freshness fixtures to the legacy-absent path.
        lines.append(f'validated_commit: "{validated_commit}"')
    lines += ["---", "", "# MCP Test Results"]
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return p




def _git_fixture_commit(root: Path) -> str:
    """Init a git repo at ``root``, commit the current tree, return HEAD's sha.

    Mirrors bug-state.py's ``step9-fresh-mcp-results`` fixture setup (init -q,
    add -A, commit -q with inline identity; ``commit.gpgsign=false`` added for
    robustness on hosts with global signing enabled) so the freshness-gate
    tests run against a genuine ``git rev-parse HEAD`` resolution.
    """
    for cmd in [
        ["git", "-C", str(root), "init", "-q"],
        ["git", "-C", str(root), "-c", "user.email=t@t", "-c", "user.name=t",
         "add", "-A"],
        ["git", "-C", str(root), "-c", "user.email=t@t", "-c", "user.name=t",
         "-c", "commit.gpgsign=false", "commit", "-q", "-m", "fixture"],
    ]:
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
        if r.returncode != 0:
            raise RuntimeError(
                f"git fixture setup failed (cmd={cmd!r}): {r.stderr.strip()}"
            )
    head = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if head.returncode != 0 or not head.stdout.strip():
        raise RuntimeError(f"git fixture rev-parse failed: {head.stderr.strip()}")
    return head.stdout.strip()




def _write_validated_md(spec_dir: Path) -> Path:
    """Write a minimal valid VALIDATED.md (kind: validated) into spec_dir."""
    p = spec_dir / "VALIDATED.md"
    p.write_text(
        "---\n"
        "kind: validated\n"
        "feature_id: test-feature\n"
        "date: 2026-06-10\n"
        "mcp_scenarios: []\n"
        "result: all-passing\n"
        "---\n\n"
        "# Validated\n",
        encoding="utf-8",
    )
    return p




def _write_spec_md(spec_dir: Path, status: str = "In-progress") -> Path:
    """Write a minimal SPEC.md with the given **Status:** line."""
    p = spec_dir / "SPEC.md"
    p.write_text(
        f"# Feature Spec\n\n"
        f"**Status:** {status}\n\n"
        "## Overview\n\n"
        "Some content.\n",
        encoding="utf-8",
    )
    return p




# ---- Gap 1: observation-gap scoped-validated disposition --------------------
# (harness-mcp-observation-gap-disposition-and-hijacked-runtime, Phase 1)
# A run whose every MCP-driveable assertion passed but whose remaining surfaces
# are SPEC-locked observation gaps (no MCP control-API tool exists to drive them;
# locked to the unit/WDIO tier per docs/features/mcp-testing/SPEC.md) honestly
# carries `result: partial`. The binary all-passing/refuse gate looped mcp-test
# forever. The scoped-validated disposition promotes such a `partial` to
# VALIDATED.md ONLY when every non-driveable assertion maps to a documented
# `observation_gap_exemptions` entry (each carrying a `spec_class` provenance,
# mirroring the SKIP_MCP_TEST.md spec_class discipline) AND the MCP-driveable
# scope is fully passing — while a genuinely-failing `partial` still refuses.


def _write_mcp_test_results_with_exemptions(
    spec_dir: Path,
    scenarios: list,
    *,
    exemptions: list,
    result: str = "partial",
    pass_count="auto",
    total_count="auto",
) -> Path:
    """Write an MCP_TEST_RESULTS.md carrying an `observation_gap_exemptions:`
    block (a list of {surface, spec_class} mappings) for the Gap-1 disposition
    tests. Kept local to the Gap-1 group so the canonical `_write_mcp_test_results`
    happy/refusal helper stays byte-stable for the existing suite.
    """
    p = spec_dir / "MCP_TEST_RESULTS.md"
    if pass_count == "auto":
        pass_count = len(scenarios)
    if total_count == "auto":
        total_count = len(scenarios)
    scenarios_yaml = "".join(f"  - {s}\n" for s in scenarios)
    exemptions_yaml = "".join(
        f"  - surface: {e['surface']}\n    spec_class: {e['spec_class']}\n"
        for e in exemptions
    )
    body = (
        "---\n"
        "kind: mcp-test-results\n"
        "feature_id: test-feature\n"
        f"scenarios:\n{scenarios_yaml}"
        "date: 2026-06-30\n"
        f"result: {result}\n"
        f"pass_count: {pass_count}\n"
        f"total_count: {total_count}\n"
        f"observation_gap_exemptions:\n{exemptions_yaml}"
        "---\n"
        "\n"
        "# MCP Test Results\n"
    )
    p.write_text(body, encoding="utf-8")
    return p




# ---------------------------------------------------------------------------
# Tests: apply_pseudo completion-coherence enforcement — Phase 9 WU-1
#
# At __mark_complete__ / __mark_fixed__ time (AFTER the evidence gate and the
# already-has-receipt noop check, BEFORE any write):
#   (auto-flip) a phase with >=1 checkbox, zero unchecked, and a present
#     non-Complete/non-Superseded Status line is flipped to Complete in place.
#   (refuse) if any phase would remain incoherent after the auto-flips:
#     - any unchecked checkbox in any non-Superseded phase, OR
#     - any phase whose (post-flip) Status is present but not Complete/Superseded
#       (incl. zero-checkbox phases — no mechanical signal to flip on),
#   the action refuses with ZERO writes (no receipt, no status flips, no
#   sentinel deletions) and a refusal message naming each offending phase.
# Phases with NO Status line are ignored.
# ---------------------------------------------------------------------------

def _write_phases_md(spec_dir: Path, body: str) -> Path:
    """Write a PHASES.md with a top-of-doc Status line + the given phase body."""
    p = spec_dir / "PHASES.md"
    p.write_text(
        "# PHASES — Test Feature\n"
        "\n"
        "**Status:** In-progress\n"
        "\n" + body,
        encoding="utf-8",
    )
    return p




# --- descoped-marker-blind-completion-coherence-gate ------------------------
# The completion-coherence gate must honor the canonical _DESCOPED_MARKER (row-
# AND header-scope) exactly as remaining_unchecked_are_verification_only does
# mid-feature — a deliberately-DEFERRED phase must not deadlock the receipt.

# A DEFERRED-not-attempted phase carrying header-scope + row-scope descope markers
# and NO Status line — the state-cli-contract-registry Phase 4 repro shape.
_DESCOPED_PHASE_4 = (
    "### Phase 4: state_cli extraction — DEFERRED, not attempted\n"
    "\n"
    "**Deliverables:** none attempted (all descoped-in-place). <!-- descoped -->\n"
    "- [ ] `state_cli.py` — NOT created. <!-- descoped -->\n"
    "- [ ] Shared-flag/helper hoist — NOT performed. <!-- descoped -->\n"
)




# ---------------------------------------------------------------------------
# Tests: update_repeat_count — WU-4 persisted probe signature / loop detection
# ---------------------------------------------------------------------------

# Representative state used across several tests.
_STATE_A = {
    "feature_id": "feat-a",
    "sub_skill": "/execute-plan",
    "sub_skill_args": "plan-part-1.md",
    "current_step": "Step 7a: execute plan",
}




# ---------------------------------------------------------------------------
# Tests: update_repeat_count — Phase 9 WU-2 HEAD-aware streak + peek mode
# ---------------------------------------------------------------------------

def _commit_dummy(repo_root: Path, name: str) -> None:
    """Make a real (no-op-ish) commit in a git repo fixture so HEAD advances."""
    (repo_root / name).write_text("x\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo_root), "add", name], check=True,
                   capture_output=True)
    subprocess.run(["git", "-C", str(repo_root), "commit", "-q", "-m", name],
                   check=True, capture_output=True)




# ---------------------------------------------------------------------------
# Tests: update_repeat_counts — Phase 2 (F2) double-probe debounce
#
# A re-read (two ADVANCING probes for the same (feature_id, current_step) with
# NO dispatch between them) must NOT inflate the HEAD-blind step_repeat_count
# and trip a false LOOP DETECTED. The "did a dispatch happen" oracle is the
# registry CONSUME-COUNT DELTA when a run marker is present: the guard consumes
# a nonce on every ALLOW, so an unchanged consumed-count between two identical
# probes means no dispatch landed → HOLD step_count.
#
# MARKER-GATED: with NO run marker present (no registry), behavior is byte-
# identical to today — the debounce is inert and step_repeat_count increments
# on any unchanged step (so `--test` baselines and unmarked callers are
# unchanged). HEAD-blindness is preserved — a real oscillation (a consume
# between the repeats) still trips. peek never persists / never advances.
# ---------------------------------------------------------------------------

def _record_consume(state_dir: "Path") -> None:
    """Register a cycle emission and immediately consume its nonce under the
    given hermetic state dir — i.e. simulate one guard ALLOW (one dispatch).

    Raises the registry's consumed-count by exactly one. Used by the Phase 2
    debounce tests to stand in for "a dispatch landed between two probes."
    """
    _set_state_dir(state_dir)
    try:
        entry = lazy_core.register_emission("dispatch prompt", "cycle")
        consumed = lazy_core.dispatch.consume_nonce(entry["nonce"])
        assert consumed, "pre-condition: the fresh nonce must consume cleanly"
    finally:
        _clear_state_dir()




def _write_marker_in(state_dir: "Path", repo_root: "Path") -> None:
    """Write a fresh, bind-pending run marker into the given hermetic state dir."""
    _set_state_dir(state_dir)
    try:
        lazy_core.write_run_marker(
            pipeline="feature", cloud=False, repo_root=str(repo_root)
        )
    finally:
        _clear_state_dir()




# ---------------------------------------------------------------------------
# Tests: emit_cycle_prompt — Phase 8 WU-2 script-assembled cycle dispatch prompt
# ---------------------------------------------------------------------------
#
# Two flavors of test below:
#   * MATRIX tests run against the REAL template dir (the default — passing
#     template_dir=None) so any drift between the emitter and the on-disk
#     `cycle-base-prompt.md` / `loop-block.md` fails LOUDLY here.
#   * PARSER-BEHAVIOR unit tests write synthetic templates into a tmpdir and
#     pass that dir explicitly, exercising selection/refusal logic in isolation.

import os as _os  # noqa: E402  (module-level import already present; alias for clarity here)



# The real template dir, resolved the same way the emitter's default does
# (validated against the ~/.claude symlink chain in the PHASES Validated
# Assumptions table). Used by the matrix tests.
_REAL_TEMPLATE_DIR = (
    Path(__file__).resolve().parents[2]
    / "skills" / "_components" / "lazy-batch-prompts"
)
# Fallback: when this file lives in the canonical scripts tree, parents[2] IS
# user/scripts, so the template dir is parents[3]/skills/... — match the
# emitter's own default exactly.
if not _REAL_TEMPLATE_DIR.exists():
    _REAL_TEMPLATE_DIR = (
        Path(__file__).resolve().parents[3]
        / "skills" / "_components" / "lazy-batch-prompts"
    )




# ---------------------------------------------------------------------------
# Phase 11 WU-1a — validation_escalation(): BLOCKED.md escalation predicate
# Phase 11 WU-5c/d — retro_staleness(): retro-vs-PHASES staleness predicate
#
# These tests cover the SHARED lazy_core helpers directly, plus end-to-end
# compute_state() routing through both state scripts. The end-to-end tests
# deliberately live HERE (loaded via importlib) rather than as new smoke
# fixtures inside the scripts' own `--test` harnesses: the smoke output is
# byte-pinned to tests/baselines/*.txt, and the flag-gated byte-identity
# discipline forbids regenerating those baselines. Loading the hyphen-named
# scripts as modules lets us drive compute_state() against temp fixtures
# without touching the pinned smoke output.
# ---------------------------------------------------------------------------

# Cache of importlib-loaded state-script modules (filename → module). The
# scripts guard their CLI under `if __name__ == "__main__"`, so exec_module
# only defines functions/constants — no side effects.
_SCRIPT_MODULES: dict = {}




def _load_state_script(filename: str):
    """Load a hyphen-named state script (lazy-state.py / bug-state.py) as a module.

    Direct `import` can't resolve hyphenated filenames, so we go through
    importlib.util.spec_from_file_location. The module is cached so repeated
    tests don't re-exec the (large) script bodies. `import lazy_core` inside
    the scripts resolves via the sys.path insertion at the top of this file.
    """
    if filename not in _SCRIPT_MODULES:
        import importlib.util

        modname = filename.replace("-", "_").rsplit(".", 1)[0]
        spec = importlib.util.spec_from_file_location(
            modname, _SCRIPTS_DIR / filename
        )
        assert spec is not None and spec.loader is not None, (
            f"cannot build import spec for {filename}"
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _SCRIPT_MODULES[filename] = mod
    return _SCRIPT_MODULES[filename]




def _build_blocked_feature_repo(root: Path, blocked_frontmatter: str) -> Path:
    """Build a minimal feature repo whose single queue item carries BLOCKED.md.

    `blocked_frontmatter` is the raw YAML body (between the --- fences) so each
    test controls exactly which escalation fields are present/absent.
    Returns the repo root (pass to compute_state).
    """
    features = root / "docs" / "features"
    features.mkdir(parents=True)
    features.joinpath("queue.json").write_text(
        json.dumps({
            "queue": [
                {"id": "feat-esc", "name": "Feature ESC",
                 "spec_dir": "feat-esc", "tier": 1}
            ]
        }),
        encoding="utf-8",
    )
    (features / "ROADMAP.md").write_text("# Roadmap\n", encoding="utf-8")
    fdir = features / "feat-esc"
    fdir.mkdir()
    (fdir / "SPEC.md").write_text(
        "# Spec\n\n**Status:** Draft\n\n**Depends on:** (none)\n",
        encoding="utf-8",
    )
    (fdir / "BLOCKED.md").write_text(
        "---\n" + blocked_frontmatter + "---\n\n# Blocked\n",
        encoding="utf-8",
    )
    return root




def _build_retro_routing_repo(
    root: Path,
    retro_done_frontmatter: str | None,
    phase_count: int = 3,
    phase_kinds: list[str] | None = None,
) -> Path:
    """Build a feature repo that reaches the Step 8/9 retro→MCP gate.

    Shape mirrors the `workstation-verification-only-retro-done` smoke fixture:
    all impl plans Complete + the only unchecked PHASES.md rows are Runtime
    Verification rows, so compute_state falls through Step 7 to the retro gate.
    `phase_count` controls how many `### Phase N` sections PHASES.md carries
    (the quantity retro_staleness compares against phase_count_at_retro).
    `retro_done_frontmatter` is the raw YAML body for RETRO_DONE.md, or None to
    omit the sentinel entirely (→ plain Step 8 retro dispatch).

    `phase_kinds`, when provided, is a list of length `phase_count` giving the
    `**Phase kind:**` tag for each phase (Phase 8 — lazy-validation-readiness);
    an entry of None/"" omits the line (legacy untagged → defaults to design).
    When omitted entirely, no phase-kind lines are written (the back-compat
    untagged shape).
    """
    features = root / "docs" / "features"
    features.mkdir(parents=True)
    features.joinpath("queue.json").write_text(
        json.dumps({
            "queue": [
                {"id": "feat-retro", "name": "Feature RETRO",
                 "spec_dir": "feat-retro", "tier": 1}
            ]
        }),
        encoding="utf-8",
    )
    (features / "ROADMAP.md").write_text("# Roadmap\n", encoding="utf-8")
    fdir = features / "feat-retro"
    fdir.mkdir()
    (fdir / "SPEC.md").write_text(
        "# Spec\n\n**Status:** Draft\n\n**Depends on:** (none)\n",
        encoding="utf-8",
    )
    (fdir / "RESEARCH.md").write_text("# R\n", encoding="utf-8")
    (fdir / "RESEARCH_SUMMARY.md").write_text("# S\n", encoding="utf-8")
    phases_body = "# Phases\n\n"
    for n in range(1, phase_count + 1):
        phases_body += f"### Phase {n}\n"
        if phase_kinds is not None:
            kind = phase_kinds[n - 1]
            if kind:
                phases_body += f"**Phase kind:** {kind}\n"
        phases_body += "- [x] Done\n\n"
    phases_body += "### Runtime Verification\n- [ ] MCP test only\n"
    (fdir / "PHASES.md").write_text(phases_body, encoding="utf-8")
    plans = fdir / "plans"
    plans.mkdir()
    (plans / "all-phases-retro.md").write_text(
        "---\nkind: implementation-plan\nfeature_id: feat-retro\n"
        "status: Complete\ncreated: 2026-06-01\n"
        f"phases: [{', '.join(str(n) for n in range(1, phase_count + 1))}]\n"
        "---\n\n# Plan (complete)\n",
        encoding="utf-8",
    )
    if retro_done_frontmatter is not None:
        (fdir / "RETRO_DONE.md").write_text(
            "---\n" + retro_done_frontmatter + "---\n\n# Retro done\n",
            encoding="utf-8",
        )
    return root




def _build_bug_retro_routing_repo(
    root: Path,
    retro_done_frontmatter: str | None,
    phase_count: int = 3,
) -> Path:
    """Bug-pipeline mirror of _build_retro_routing_repo (docs/bugs layout).

    Builds a bug whose PHASES.md deliverables are ALL checked (unchecked == 0),
    so bug-state's compute_state falls straight through Step 7 to the Step 8
    retro gate — no Complete plan / verification-only carve-out needed.
    `phase_count` controls how many `### Phase N` sections PHASES.md carries
    (the quantity retro_staleness compares against phase_count_at_retro).
    `retro_done_frontmatter` is the raw YAML body for RETRO_DONE.md, or None to
    omit the sentinel entirely (→ plain Step 8 retro dispatch).
    """
    bugs = root / "docs" / "bugs"
    bugs.mkdir(parents=True)
    bugs.joinpath("queue.json").write_text(
        json.dumps({
            "queue": [
                {"id": "bug-retro", "name": "Bug RETRO", "spec_dir": "bug-retro"}
            ]
        }),
        encoding="utf-8",
    )
    bdir = bugs / "bug-retro"
    bdir.mkdir()
    (bdir / "SPEC.md").write_text(
        "# Bug RETRO\n\n"
        "**Status:** In-progress\n\n"
        "**Severity:** P1\n\n"
        "**Discovered:** 2026-06-01\n",
        encoding="utf-8",
    )
    phases_body = "# Phases\n\n"
    for n in range(1, phase_count + 1):
        phases_body += f"### Phase {n}\n- [x] Done\n\n"
    (bdir / "PHASES.md").write_text(phases_body, encoding="utf-8")
    if retro_done_frontmatter is not None:
        (bdir / "RETRO_DONE.md").write_text(
            "---\n" + retro_done_frontmatter + "---\n\n# Retro done\n",
            encoding="utf-8",
        )
    return root




# ---- harden(script) 2026-06-15: no-plans verification-only Step-7 deadlock ----
#
# Regression for the mcp-testing write-plan no-progress loop. A feature
# implemented batch-by-batch via PHASES checkboxes (NO plans/ dir) whose only
# remaining unchecked rows are Runtime Verification rows must route to the
# Step-9 MCP gate, not loop on write-plan. The pre-fix Step-7 bypass required
# _has_any_complete_plan(spec_path) which is False with no plans/ dir, so
# control fell to `elif not plans` -> write-plan; write-plan is banned from
# emitting a verification-only WU, so it wrote nothing and the state repeated.

def _build_no_plans_verification_only_repo(root: Path) -> Path:
    """Build a feature repo with NO plans/ dir whose only unchecked PHASES.md
    rows are verification-only (the mcp-testing deadlock shape).

    All implementation rows are [x]; a trailing `### Runtime Verification`
    subsection holds the single unchecked row. SPEC + RESEARCH + RESEARCH_SUMMARY
    + PHASES exist so compute_state reaches Step 7. Deliberately omits the
    plans/ dir entirely so _has_any_complete_plan() returns False.
    """
    features = root / "docs" / "features"
    features.mkdir(parents=True)
    features.joinpath("queue.json").write_text(
        json.dumps({
            "queue": [
                {"id": "feat-noplan", "name": "Feature NOPLAN",
                 "spec_dir": "feat-noplan", "tier": 1}
            ]
        }),
        encoding="utf-8",
    )
    (features / "ROADMAP.md").write_text("# Roadmap\n", encoding="utf-8")
    fdir = features / "feat-noplan"
    fdir.mkdir()
    (fdir / "SPEC.md").write_text(
        "# Spec\n\n**Status:** In-progress\n\n**Depends on:** (none)\n",
        encoding="utf-8",
    )
    (fdir / "RESEARCH.md").write_text("# R\n", encoding="utf-8")
    (fdir / "RESEARCH_SUMMARY.md").write_text("# S\n", encoding="utf-8")
    phases_body = (
        "# Phases\n\n"
        "### Phase 1\n- [x] Impl one\n\n"
        "### Phase 2\n- [x] Impl two\n\n"
        "### Runtime Verification\n- [ ] MCP test only\n"
    )
    (fdir / "PHASES.md").write_text(phases_body, encoding="utf-8")
    # NOTE: no plans/ dir created — this is the load-bearing condition.
    return root




def _seed_efficacy_breadcrumb(state_dir):
    """Drop the run-scoped efficacy-flush breadcrumb for the marker currently in
    ``state_dir`` so a subsequent subprocess ``--run-end`` PASSES the efficacy
    gate (efficacy-future-check-unenforced-orchestrator-prose).

    These hermetic subprocess tests exercise OTHER --run-end concerns (hardening
    debt, checkpoint, stop-authorization) and do not run the efficacy/canary/
    incident trio; seeding the breadcrumb in-process is the moral equivalent of
    the trio having flushed (it mirrors the in-process ``ack_oldest_deny`` seam
    these same tests already use for the hardening-debt gate).  Keeps the
    ``--run-end`` output byte-identical (no ``--efficacy-skip-authorized``
    override key).  Must be called AFTER the run-start that wrote the marker and
    BEFORE the success ``--run-end`` (run-scoped: keyed to the live marker's
    started_at).

    adhoc-run-end-tests-leak-real-repo-state: the gate ALSO requires the
    breadcrumb's ``interventions_covered`` flag (interventions-telemetry-repo-
    scope-split-brain WU-2), which ``lazy_core.drop_efficacy_breadcrumb`` derives
    from ``_repo_is_interventions_bearing(covered_repo_root)`` — a REAL
    ``docs/interventions/*.md`` presence check.  The bare no-arg call this
    helper used to make only satisfied that check *by accident*: these
    hermetic --run-end subprocess tests never passed ``--repo-root`` to their
    own ``--run-start``, so the live marker's ``repo_root`` field silently
    defaulted to ``os.getcwd()`` — the REAL claude-config checkout, which
    genuinely IS interventions-bearing — and ``drop_efficacy_breadcrumb``'s
    fallback read that REAL directory to compute the flag.  Now that the
    sibling fixture-repo isolation fix means these tests' markers carry a
    hermetic (non-interventions-bearing) temp ``repo_root``, this helper seeds
    its OWN disposable interventions-bearing fixture directory (a sibling of
    ``state_dir``, NEVER the real checkout) and passes it EXPLICITLY as
    ``covered_repo_root`` — so the crumb's coverage flag no longer depends on
    the marker's repo_root, or on the real repo, at all.
    """
    _set_state_dir(state_dir)
    try:
        fixture_repo = state_dir.parent / f"{state_dir.name}-efficacy-fixture"
        interventions_dir = fixture_repo / "docs" / "interventions"
        interventions_dir.mkdir(parents=True, exist_ok=True)
        marker_md = interventions_dir / "adhoc-test-fixture.md"
        if not marker_md.exists():
            marker_md.write_text(
                "# adhoc-test-fixture\n\n"
                "Disposable interventions-bearing marker for hermetic "
                "--run-end subprocess tests (adhoc-run-end-tests-leak-real-"
                "repo-state). Never read by production; satisfies "
                "_repo_is_interventions_bearing's *.md presence check only.\n",
                encoding="utf-8",
            )
        lazy_core.drop_efficacy_breadcrumb(covered_repo_root=str(fixture_repo))
    finally:
        _clear_state_dir()




def _dispatch_requires(cls: str) -> list[str]:
    """Return the @requires keys for a dispatch class's real template."""
    tpl = _REAL_TEMPLATE_DIR / f"dispatch-{cls}.md"
    first = next((ln for ln in tpl.read_text(encoding="utf-8").splitlines() if ln.strip()), "")
    m = re.match(r"^<!--\s*@requires\s+([a-z0-9_,]+)\s*-->", first)
    return [k.strip() for k in m.group(1).split(",") if k.strip()]




# ---------------------------------------------------------------------------
# Tests: Phase 8 — concurrent-session safety
#   (non-destructive path B is tested in the Phase 1 section above;
#    routed hardening debt + guard-allow ack + stderr line live here)
# ---------------------------------------------------------------------------
#
# Hermetic via LAZY_STATE_DIR temp dirs (same discipline as Phase 1/7).


def _build_phase8_fixture_repo(parent: "Path") -> "Path":
    """Build a minimal mid-implementation fixture repo (yields a non-null
    cycle_prompt on --emit-prompt when NOT withholding).  Mirrors the fixture
    built inline by test_subprocess_emit_prompt_with_marker_writes_registry."""
    features = parent / "fixture-repo" / "docs" / "features"
    features.mkdir(parents=True)
    (features / "queue.json").write_text(json.dumps({
        "queue": [{"id": "feat-c", "name": "Feature C", "spec_dir": "feat-c", "tier": 1}]
    }), encoding="utf-8")
    (features / "ROADMAP.md").write_text("# Roadmap\n", encoding="utf-8")
    fdir = features / "feat-c"
    fdir.mkdir()
    (fdir / "SPEC.md").write_text(
        "# Spec\n\n**Status:** Draft\n\n**Depends on:** (none)\n", encoding="utf-8")
    (fdir / "RESEARCH.md").write_text("# Research\n", encoding="utf-8")
    (fdir / "RESEARCH_SUMMARY.md").write_text("# Summary\n", encoding="utf-8")
    (fdir / "PHASES.md").write_text(
        "# Phases\n\n### Phase 1\n- [ ] Build the thing\n- [ ] Tests\n", encoding="utf-8")
    (fdir / "plans").mkdir()
    (fdir / "plans" / "all-phases-c.md").write_text("# Plan\n", encoding="utf-8")
    return parent / "fixture-repo"




def _phase9_guard_module():
    """Import lazy_guard in-process (it imports lazy_core directly)."""
    sys.path.insert(0, str(_SCRIPTS_DIR))
    import importlib
    return importlib.import_module("lazy_guard")




# ---------------------------------------------------------------------------
# F1 (lazy-pipeline-ergonomics Phase 1) — validate-deny recovery ergonomics
# ---------------------------------------------------------------------------
#
# F1a: the default (non-hardening) deny reason names the sanctioned
#      customization path (`--context KEY=VALUE`, `--emit-dispatch <class>`) and
#      the "dispatch verbatim — never append/edit" rule, WITHOUT dropping any of
#      the preexisting recipe substrings the Phase 6/7 tests byte-match.
# F1b: a pure trailing-suffix superset of an unconsumed/fresh/cycle entry is
#      auto-readmitted (nonce consumed, allow, `auto_readmit: true` ledger event).
#      Hardening-class entries and in-body edits are NEVER auto-readmitted; any
#      auto-readmit-path error falls through to the normal deny (fail-open).


def _f1_guard_module():
    """Import lazy_guard in-process (it imports lazy_core directly)."""
    sys.path.insert(0, str(_SCRIPTS_DIR))
    import importlib
    return importlib.import_module("lazy_guard")




def _f1_hook_input(prompt, tool_use_id, session_id=None):
    payload = {"tool_use_id": tool_use_id, "tool_input": {"prompt": prompt}}
    if session_id is not None:
        payload["session_id"] = session_id
    return json.dumps(payload)




# ---------------------------------------------------------------------------
# Test registry — defines run order and test names.
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Tests: Phase 1 — Run-state core (marker, prompt registry, persisted counters)
# ---------------------------------------------------------------------------
#
# ALL tests in this section are RED until lazy_core.py gains the Phase 1
# symbols.  The failure reason for each test is documented inline.
#
# Isolation discipline: every test that touches the state dir MUST set
# LAZY_STATE_DIR in os.environ to a temp dir and delete it afterward so that
# tests are hermetically isolated and never touch ~/.claude/state/.


import os as _os_env  # alias to avoid shadowing the existing `_os` alias


import time as _t  # module-level time alias (mirrors the per-test `import time as _t`)




def _set_state_dir(path: "Path") -> None:
    """Point LAZY_STATE_DIR at the given temp dir for hermetic test isolation."""
    _os_env.environ["LAZY_STATE_DIR"] = str(path)




# Hermetic isolation of the run-state dir for the WHOLE test package — set BEFORE
# _ORIGINAL_LAZY_STATE_DIR is captured so the restore path below stays isolated too.
# Without this, an in-process call into a refuse_if_cycle_active-guarded helper (the
# ~80 apply_pseudo/mark_complete tests call lazy_core.apply_pseudo, which guards at
# its entry) resolves LAZY_STATE_DIR to the REAL per-repo keyed dir
# ~/.claude/state/<repo_key>/ — and DURING a live /lazy-batch run that dir carries the
# cycle marker, so every such test raised SystemExit(3) purely because a real run was
# in flight (docs/bugs/adhoc-lazy-core-tests-not-isolated-from-live-cycle-marker). It
# is the structural form of the user/scripts/CLAUDE.md contributor convention
# ("isolate LAZY_STATE_DIR") applied ONCE at this shared import chokepoint, imported by
# every shard in BOTH pytest and the standalone per-shard __main__ runners.
# setdefault (never overwrite) so the documented operator override
# `LAZY_STATE_DIR=<temp> python3 …` still wins; only the unset (real-keyed-dir) case
# is redirected to a throwaway temp dir a test never populates with a marker.
if not _os_env.environ.get("LAZY_STATE_DIR"):
    import atexit as _atexit
    import shutil as _shutil

    _HERMETIC_STATE_DIR = tempfile.mkdtemp(prefix="test-lazy-core-state-")
    _os_env.environ["LAZY_STATE_DIR"] = _HERMETIC_STATE_DIR
    _atexit.register(_shutil.rmtree, _HERMETIC_STATE_DIR, ignore_errors=True)

# The LAZY_STATE_DIR value present when this test module was imported — i.e. the
# operator's PROCESS-LEVEL override, if any (or the hermetic temp default seeded just
# above). The documented mitigation for running the full suite DURING a live lazy
# cycle is `LAZY_STATE_DIR=<temp> python3 test_lazy_core.py`, so the cycle-active
# guards (`refuse_if_cycle_active` reached via `apply_pseudo`) read a clean temp state
# dir instead of the real ~/.claude/state/<repo>/ carrying the live cycle marker.
# `_clear_state_dir()` must RESTORE this value, not unconditionally delete it —
# otherwise an early cycle-marker test's teardown strips the override mid-suite and
# every later guard reads the REAL state dir and false-fails on the live marker.
# See docs/bugs/clear-state-dir-teardown-strips-lazy-state-dir-override.
_ORIGINAL_LAZY_STATE_DIR = _os_env.environ.get("LAZY_STATE_DIR")




def _clear_state_dir() -> None:
    """Restore LAZY_STATE_DIR to its process-launch value so subsequent tests
    (and the guards they exercise) are unaffected.

    Restores rather than unconditionally deletes: when the suite is launched with
    a process-level LAZY_STATE_DIR override (the documented live-cycle mitigation),
    an unconditional pop would strip that override mid-suite. When no override was
    set at launch (_ORIGINAL_LAZY_STATE_DIR is None — the normal CI case), this
    pops exactly as before, so every existing hermetic test is byte-identical.
    """
    if _ORIGINAL_LAZY_STATE_DIR is None:
        _os_env.environ.pop("LAZY_STATE_DIR", None)
    else:
        _os_env.environ["LAZY_STATE_DIR"] = _ORIGINAL_LAZY_STATE_DIR




# ---------------------------------------------------------------------------
# multi-repo-concurrent-runs — per-repo state-dir scoping (Phase 1)
# ---------------------------------------------------------------------------

def _mrcr_with_temp_home(td: str):
    """Context-free helper: point HOME + USERPROFILE at td, clear LAZY_STATE_DIR,
    and reset the per-process migration + active-repo globals so each keyed-dir
    test starts clean.  Returns a dict of prior env values to restore."""
    prior = {k: os.environ.get(k) for k in ("HOME", "USERPROFILE", "LAZY_STATE_DIR")}
    os.environ["HOME"] = td
    os.environ["USERPROFILE"] = td
    os.environ.pop("LAZY_STATE_DIR", None)
    lazy_core._ctx._legacy_state_migrated = False
    lazy_core.set_active_repo_root(None)
    return prior




def _mrcr_restore_env(prior: dict) -> None:
    for k, v in prior.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    lazy_core._ctx._legacy_state_migrated = False
    lazy_core.set_active_repo_root(None)




# ---------------------------------------------------------------------------
# lint_planner_resolution — D1 planner-resolution gate must resolve the canonical
# internal <claude-config>/repos/ even when the passed --repos-dir (~/source/repos)
# has no sibling working copies checked out.
# Regression for docs/bugs/planner-resolution-lint-blind-to-internal-repos: the
# gate was RED on clean `main` on a machine without sibling repos under
# ~/source/repos, because it anchored D1 resolution to that machine-variable path
# instead of the git-tracked internal source of truth.
# ---------------------------------------------------------------------------
def _lint_skills_module():
    """Load lint-skills.py as a module (hyphenated filename → importlib)."""
    return _load_state_script("lint-skills.py")




# ---------------------------------------------------------------------------
# Phase 3 (lazy-cycle-containment C3) — refuse-by-construction
#
# The orchestrator-only state-script ops REFUSE (exit non-zero, zero side
# effects, corrective message) when the cycle marker is present.  The guard is
# refuse_if_cycle_active(op_name) in lazy_core; the CLI handlers in
# lazy-state.py / bug-state.py invoke it at the top of each guarded op.
# ---------------------------------------------------------------------------

_GUARDED_OPS = ["--run-end", "--run-start", "--apply-pseudo", "--enqueue-adhoc", "--emit-dispatch"]




# ---------------------------------------------------------------------------
# hardening-blind-to-process-friction Phase 1 (D4) — agent_id-aware C3
#
# refuse_if_cycle_active decides subagent-vs-main-thread in priority order:
#   1. LAZY_ORCHESTRATOR truthy → NEVER refuse (orchestrator immunity, even with
#      a stale marker present — fixes the Proven-Finding-#3 self-deny defect).
#   2. LAZY_CYCLE_SUBAGENT truthy → refuse (explicit subagent signal, no marker
#      required).
#   3. else cycle marker present → refuse (legacy backstop carrier).
# ---------------------------------------------------------------------------

def _clear_cycle_env() -> None:
    for k in ("LAZY_ORCHESTRATOR", "LAZY_CYCLE_SUBAGENT"):
        os.environ.pop(k, None)




# ---------------------------------------------------------------------------
# Follow-up: structural MCP-skip short-circuit (no-app-surface repos)
#   repo_has_no_app_surface / phases_mcp_runtime_not_required helpers,
#   skip_waiver_refusal(granted_by: pipeline-structural) re-verification, and
#   the __grant_skip_no_mcp_surface__ pseudo-skill (write / refuse / noop /
#   round-trip into __write_validated_from_skip__).
# ---------------------------------------------------------------------------

def _write_not_required_phases(spec: Path) -> None:
    spec.mkdir(parents=True, exist_ok=True)
    (spec / "PHASES.md").write_text(
        "# Phases\n\n**MCP runtime:** not-required\n\n### Phase 1\n- [x] x\n",
        encoding="utf-8",
    )




# ---------------------------------------------------------------------------
# long-build-and-runtime-ownership Phase 2 — ensure_runtime reworked into the
# M4 liveness/recovery verdict (Identity → Staleness → Health). All external
# interactions remain injected callables (hermetic, no real network/process).
#
# WU-1 (this block): the three-phase verdict superset — state classification
#   {READY, STALE, HIJACKED, DEAD} + the retained {health_code, mcp_tools_present}.
#   (BLOCKED + bounded recovery land in WU-2.)
# ---------------------------------------------------------------------------

_M4_CONFIG = {
    "health_url": "http://localhost:3333/health",
    "restart_command": "npm run dev:restart",
    "mcp_tool_name": "render_chart",
    "native_globs": ["src-tauri", "crates"],
    "lock_filename": ".runtime.lock.json",
    "port": 3333,
}



_SESSION = "session-abc"




def _owned_lock(start_time=111.0, pid=4321):
    """A `.runtime.lock.json` dict owned by _SESSION at the recorded start_time."""
    return {
        "controller_session_id": _SESSION,
        "pid": pid,
        "start_time": start_time,
        "port": 3333,
        "artifact_hash": "deadbeef",
    }




_M4_CONFIG_FRONTEND = {
    **_M4_CONFIG,
    "frontend_health_url": "http://localhost:1420",
    "frontend_port": 1420,
}




# ---------------------------------------------------------------------------
# ensure-runtime-starves-pre-vite-sidecar-build Phase 1 — boot-liveness signal +
# pre-Vite-aware discriminator. _classify_compile_state gains a back-compat
# `boot_alive` parameter so a both-ports-down observation with a LIVE boot
# process (the pre-Vite BeforeDevCommand/sidecar:build window) classifies as the
# patient-wait `compiling` (not `dead`). Default-off byte-identity preserved.
# ---------------------------------------------------------------------------

# A config that ALSO carries the boot-liveness key (the pre-Vite signal), built
# on the frontend-bearing config so the two "still booting" signals compose.
_M4_CONFIG_BOOT = {
    **_M4_CONFIG_FRONTEND,
    "boot_liveness": True,
}




# ---------------------------------------------------------------------------
# long-build-and-runtime-ownership Phase 2 — WU-3: surface the M4 verdict through
# the `lazy-state.py --ensure-runtime` CLI handler. The handler threads the live
# run marker's session_id as live_session_id (the controller_session_id recorded
# into `.runtime.lock.json`) so production emits the verifiable-ownership verdict.
# ---------------------------------------------------------------------------

_M4_KEYS = {"state", "ownership_verified", "health_code", "mcp_tools_present",
            "terminal_blocker"}




# ---------------------------------------------------------------------------
# harness-hardening-retro-fixes Phase 5 (WU-5) — dead-coverage guard.
# ---------------------------------------------------------------------------
#
# The Round-24 dead-coverage class: a `def test_*` function authored but never
# appended to `_TESTS`, so it NEVER executes (caught only by luck in Round 25).
# This guard AST-parses the suite module source, collects every top-level
# `def test_*` name, compares against the names registered across all
# `_TESTS = ... + [...]` assignments, and FAILS naming any orphan. It is itself
# registered in `_TESTS` (self-checking — collected and run by the same harness
# it guards), so `python user/scripts/test_lazy_core.py` fails on any orphan.
#
# GENERALIZATION SEAM (⚖ policy: guard scope — this-module vs all script test
# modules): this guard covers `test_lazy_core.py` — the Round-24 incident's
# module AND the suite Phases 1–3 of harness-hardening-retro-fixes extend (the
# load-bearing case). The pure collector `_collect_orphaned_test_names` takes
# (module_source, registered_names) so it generalizes to ANY `_TESTS`-style
# manually-registered module in `user/scripts/` (e.g. a future
# test_surface_resolver-style registry): a sibling module would add its own
# one-line guard pointing the collector at its own source + registry. We do NOT
# speculatively scan every file here — only the module that needs it today.


def _collect_orphaned_test_names(
    module_source: str, registered_names: set[str]
) -> list[str]:
    """Pure collector: AST-parse ``module_source``, return the sorted list of
    top-level, ZERO-PARAMETER ``def test_*`` function names NOT present in
    ``registered_names``.

    AST (``ast.parse``) is used over regex for robustness — it ignores
    ``def test_*`` strings inside docstrings/comments and only counts genuine
    top-level function definitions. Async defs are included for completeness.
    An empty return list means every manual-runner test is registered.

    PARAMETERIZED tests are EXCLUDED: a ``def test_x(tmp_path)`` /
    ``def test_x(monkeypatch)`` declares a pytest fixture argument and is
    collected + run by pytest (the gate runs ``pytest user/scripts/ -q``), NOT
    by the manual ``_TESTS`` runner (which calls ``fn()`` with no args). Such a
    function is NOT a dead-coverage orphan — it executes under pytest. Only a
    zero-positional-arg ``def test_*`` is a manual-registry candidate, so only
    those can be orphaned by a missing ``_TESTS`` entry.
    """
    tree = ast.parse(module_source)
    defined: set[str] = set()
    for node in tree.body:  # top-level only — registered tests are module-level
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if not node.name.startswith("test_"):
                continue
            # Skip pytest-fixture-parameterized tests — they run under pytest,
            # not the manual _TESTS runner, so absence from _TESTS is correct.
            if node.args.args or node.args.posonlyargs or node.args.kwonlyargs:
                continue
            defined.add(node.name)
    return sorted(defined - registered_names)




# ---------------------------------------------------------------------------
# lazy-batch-unified-driver-parity-and-accounting Phase 2 (item 3) — WU-3.
# ---------------------------------------------------------------------------
#
# _load_bug_queue_for_merged (lazy-state.py) wraps the dynamic bug-state.py
# load_bug_queue in a bare `except Exception: return []` — a bug-side load failure
# silently degrades the merged view to features-only with NO diagnostic. WU-3
# replaces the bare-except with a _diag(...) breadcrumb before degrading, so the
# silent failure becomes observable in the merged-view diagnostics while still
# failing open (returns []).


def _load_lazy_state_module():
    """Import lazy-state.py (hyphenated) in-process for white-box testing."""
    import importlib.util as _ilu
    path = _SCRIPTS_DIR / "lazy-state.py"
    spec = _ilu.spec_from_file_location("_lazy_state_for_test", str(path))
    mod = _ilu.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod




# ===========================================================================
# completion-coherence-gate-reconciliation — Phase 1
#   evaluate_completion_evidence — authoritative-evidence decision table.
# One fixture per row of the SPEC's Technical Design (LOCKED) decision table.
# ===========================================================================

def _cc_write_validated(spec_dir: Path) -> None:
    """Write a minimal kind: validated VALIDATED.md into spec_dir."""
    (spec_dir / "VALIDATED.md").write_text(
        "---\n"
        "kind: validated\n"
        "feature_id: cc-feature\n"
        "date: 2026-06-19\n"
        "---\n\n# Validated\n",
        encoding="utf-8",
    )




def _cc_seed_and_commit(repo_root: Path) -> str:
    """Seed a tracked README then git-commit the tree; return HEAD's sha.

    Wraps ``_git_fixture_commit`` so fixtures whose only other files live in an
    untracked-empty spec dir still produce a non-empty initial commit (git does
    not track empty dirs, so a bare ``add -A`` would stage nothing and the
    commit would fail with "nothing to commit").
    """
    readme = repo_root / "README.md"
    if not readme.exists():
        readme.write_text("seed\n", encoding="utf-8")
    return _git_fixture_commit(repo_root)




# ===========================================================================
# completion-coherence-gate-reconciliation — Phase 3
#   Wire evidence verdict + auto-tick into _phase_completion_plan /
#   __mark_complete__ / __mark_fixed__, with COMPLETED.md auto_ticked_rows and
#   the LAZY_STRICT_EVIDENCE_GATE kill-switch.
# ===========================================================================

def _cc_write_retro_done(spec_dir: Path) -> None:
    """Write a RETRO_DONE.md with NO phase_count field → retro_staleness None
    (grandfathered), matching the existing mark_complete fixtures.
    """
    (spec_dir / "RETRO_DONE.md").write_text(
        "---\nkind: retro-done\nfeature_id: test-feature\ndate: 2026-06-19\n---\n",
        encoding="utf-8",
    )




def _cc_build_validated_feature(repo_root: Path, *, phases_body: str) -> Path:
    """Build a feature dir with VALIDATED.md + passing MCP_TEST_RESULTS.md +
    RETRO_DONE.md + SPEC.md(In-progress) + the given PHASES.md body, all
    committed so validated_commit == HEAD. Returns spec_dir.
    """
    spec_dir = repo_root / "docs" / "features" / "cc-e2e"
    spec_dir.mkdir(parents=True)
    _cc_write_validated(spec_dir)
    _write_spec_md(spec_dir, status="In-progress")
    _cc_write_retro_done(spec_dir)
    (spec_dir / "PHASES.md").write_text(phases_body, encoding="utf-8")
    _write_mcp_test_results(spec_dir, ["s1", "s2"])
    head = _cc_seed_and_commit(repo_root)
    _write_mcp_test_results(spec_dir, ["s1", "s2"], validated_commit=head)
    return spec_dir




# A PHASES.md whose ONLY unchecked rows are verification-marked.
_CC_E2E_PHASES_VERIF_ONLY = (
    "# Phases\n\n"
    "### Phase 1: Impl\n\n"
    "**Status:** Complete\n\n"
    "- [x] implementation done\n\n"
    "**Runtime Verification**\n\n"
    "- [ ] pytest green <!-- verification-only -->\n"
    "- [ ] parity clean <!-- verification-only -->\n"
)




def _make_git_tree(root: Path) -> Path:
    """Create a minimal real git tree under root; return the repo path."""
    repo = root / "repo"
    repo.mkdir()
    subprocess.run(["git", "-C", str(repo), "init", "-q"], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.email", "t@t"], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "t"], check=True)
    (repo / "seed.txt").write_text("seed", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", "seed"], check=True)
    return repo




# ---------------------------------------------------------------------------
# code-doc-provenance-linkage — Phase 1: commit-bracket ledger + receipt anchor
#
# The per-cycle commit-bracket ledger (`lazy-commit-brackets.jsonl` in the keyed
# state dir) is the deterministic raw material for the provenance producer's
# touched-file-set derivation (SPEC D4-A). Append is fail-open (identical
# contract to append_friction_ledger_entry); the receipt anchor threads
# completed_commit at the existing write_completed_receipt call site.
# ---------------------------------------------------------------------------

def _prov_git_fixture_repo(root: "Path") -> str:
    """git init + one seed commit under `root`; return the seed HEAD sha."""
    def g(*args):
        subprocess.run(
            ["git", "-C", str(root)] + list(args),
            check=True, capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
    g("init", "-q")
    g("config", "user.email", "t@t")
    g("config", "user.name", "t")
    # Hermetic: throwaway fixture repos must not depend on the host's
    # commit-signing setup (a network signer outage would flake the suite).
    g("config", "commit.gpgsign", "false")
    (root / "seed.txt").write_text("seed\n", encoding="utf-8")
    g("add", "-A")
    g("commit", "-q", "-m", "seed")
    r = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        check=True, capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    return r.stdout.strip()




def _prov_git_commit_file(root: "Path", relpath: str, message: str) -> str:
    """Write `relpath` under `root`, commit it, return the new HEAD sha."""
    p = root / relpath
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(f"content for {message}\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(root), "add", "-A"],
                   check=True, capture_output=True, text=True, encoding="utf-8", errors="replace")
    subprocess.run(["git", "-C", str(root), "commit", "-q", "-m", message],
                   check=True, capture_output=True, text=True, encoding="utf-8", errors="replace")
    r = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"],
                       check=True, capture_output=True, text=True, encoding="utf-8", errors="replace")
    return r.stdout.strip()




# ---------------------------------------------------------------------------
# code-doc-provenance-linkage — Phase 2: write_provenance producer + gate wiring
# ---------------------------------------------------------------------------

_PROV_SPEC_MD = """# Feature Spec

> Distill each completed item into a durable ledger artifact and a reverse
> index so agents can discover the decisions that govern a file.

**Status:** In-progress

## Locked Decisions

| id | decision |
|----|----------|
| L1 | one writer, two triggers |
| L2 | deterministic distillate assembly |

## Overview

Some content.
"""




def _prov_spec_dir(repo_root: "Path", slug: str, *, docs_kind: str = "features",
                   spec_md: str | None = None) -> "Path":
    spec_dir = repo_root / "docs" / docs_kind / slug
    spec_dir.mkdir(parents=True, exist_ok=True)
    (spec_dir / "SPEC.md").write_text(
        spec_md if spec_md is not None else _PROV_SPEC_MD, encoding="utf-8")
    return spec_dir




# ---------------------------------------------------------------------------
# run-end-gate-refusals-no-telemetry-event — each of the three --run-end gate
# refusals (unacked-hardening / efficacy-coverage-missing / checkpoint-auth) must
# append an observability-only `gate-refusal` telemetry event carrying the
# matching `data.gate`, while the refusal itself is UNCHANGED (exit 1, marker
# kept).  A SUCCESSFUL --run-end must emit `run-end` and NO `gate-refusal`
# (over-emission guard).  Coupled pair: asserted for BOTH lazy-state.py and
# bug-state.py.  Driven via subprocess so the real CLI handlers run; hermetic
# via an isolated LAZY_STATE_DIR (never the live ~/.claude/state/).
# ---------------------------------------------------------------------------

def _run_end_gate_env(state_dir: "Path") -> dict:
    """Env for driving a state script's --run-end as the ORCHESTRATOR (so
    refuse_if_cycle_active never refuses), pinned to an isolated state dir.
    Mirrors lazy-state.py's telemetry-ledger-chokepoints `_tl_env`."""
    e = {k: v for k, v in os.environ.items()
         if k not in ("LAZY_ORCHESTRATOR", "LAZY_CYCLE_SUBAGENT")}
    e["LAZY_STATE_DIR"] = str(state_dir)
    e["LAZY_ORCHESTRATOR"] = "1"
    return e




def _drive_run_end(script: str, pipeline: str, extra_args, *, seed_deny: bool,
                   state_dir: "Path"):
    """Arm a live run marker (+ optionally seed the deny ledger so
    pending_hardening() > 0), drive `<script> --run-end <extra_args>` via
    subprocess, and return (result, events, marker_exists)."""
    _set_state_dir(state_dir)
    lazy_core.write_run_marker(
        pipeline=pipeline, cloud=False, repo_root=str(state_dir),
    )
    if seed_deny:
        assert lazy_core.append_deny_ledger_entry(
            "tid-x", "abcabcabcabc", "guard deny (fixture)", "prompt head",
        ) is True
    r = subprocess.run(
        [sys.executable, str(_SCRIPTS_DIR / script),
         "--repo-root", str(state_dir), "--run-end", *extra_args],
        capture_output=True, text=True, encoding="utf-8", errors="replace", env=_run_end_gate_env(state_dir),
    )
    events = lazy_core.read_telemetry_events()
    marker_exists = (state_dir / lazy_core._MARKER_FILENAME).exists()
    return r, events, marker_exists




def _assert_run_end_refusal_emits(script, pipeline, extra_args, *, seed_deny,
                                  expected_gate):
    _guard()
    with tempfile.TemporaryDirectory() as td:
        try:
            r, events, marker_exists = _drive_run_end(
                script, pipeline, extra_args, seed_deny=seed_deny,
                state_dir=Path(td),
            )
            # Behavior UNCHANGED: refusal exits 1 and keeps the marker.
            assert r.returncode == 1, (r.returncode, r.stdout, r.stderr)
            assert marker_exists, "a refused --run-end must keep the marker"
            # New observability: exactly one gate-refusal for this gate.
            assert events, "expected a gate-refusal telemetry event, got none"
            last = events[-1]
            assert last.get("event") == "gate-refusal", last
            assert last.get("data", {}).get("gate") == expected_gate, last
            assert last.get("data", {}).get("op") == "--run-end", last
        finally:
            _clear_state_dir()




def _fresh_started_at(now: float | None = None) -> str:
    """A `started_at` timestamp within the last hour (LIVE per _MARKER_STALE_SECONDS)."""
    import time as _time
    import datetime as _datetime
    if now is None:
        now = _time.time()
    return _datetime.datetime.fromtimestamp(
        now, tz=_datetime.timezone.utc
    ).strftime("%Y-%m-%dT%H:%M:%S") + "Z"




def _write_target_marker(base: "Path", target_root: "Path", *,
                          started_at: str) -> "Path":
    """Write a minimal run marker into the keyed sibling subdir for
    `target_root`, under `base` (the LAZY_STATE_DIR override). Returns the
    keyed subdir path."""
    keyed_dir = base / lazy_core.repo_key(str(target_root))
    keyed_dir.mkdir(parents=True, exist_ok=True)
    marker_path = keyed_dir / lazy_core._MARKER_FILENAME
    marker_path.write_text(
        json.dumps({"repo_root": str(target_root), "started_at": started_at}),
        encoding="utf-8",
    )
    return keyed_dir




# ---------------------------------------------------------------------------
# drop_efficacy_breadcrumb — COVERAGE-BEARING breadcrumb (WU-2).
#
# The breadcrumb today records only that the efficacy trio was INVOKED
# ({run_started_at, ts}) — not WHICH repo-scope it covered. A flush that never
# covers the interventions-bearing repo (claude-config) still discharges the
# --run-end gate. The new contract:
#   drop_efficacy_breadcrumb(covered_repo_root=None, *, now=None) -> bool
# resolves the LIVE run marker's keyed dir (active dir first, else the
# most-recent live marker in a keyed sibling subdir of the state base), then
# READ-MERGE-WRITEs ONE breadcrumb carrying {run_started_at, ts,
# covered_scopes: sorted([...]), interventions_covered: bool}, ACCUMULATING
# across calls for the SAME run_started_at.
# ---------------------------------------------------------------------------

def _make_interventions_bearing_repo(root: "Path") -> None:
    """Mark `root` interventions-bearing via the queue.json opt-in flag."""
    features_dir = root / "docs" / "features"
    features_dir.mkdir(parents=True, exist_ok=True)
    (features_dir / "queue.json").write_text(
        json.dumps({"interventions": True, "queue": []}), encoding="utf-8"
    )




# ---------------------------------------------------------------------------
# anti-overfit-design-gate D3 — completion-gate ship seam
# (lazy_core.gate_verdict_ok + its apply_pseudo wiring). SEAM-DEFERRED from
# the authoring feature's PHASES.md Phase 3 (exact recorded diff applied
# here). Reuses the existing provenance-fixture git helpers
# (_prov_git_fixture_repo / _prov_git_commit_file / _prov_spec_dir) so the
# item's touched-file derivation exercises the REAL commit-brackets /
# message-grep machinery, never a hand-rolled shape.
# ---------------------------------------------------------------------------

def _gate_write_manifest(repo_root: "Path", globs: "list[str]") -> None:
    gate_dir = repo_root / "docs" / "gate"
    gate_dir.mkdir(parents=True, exist_ok=True)
    (gate_dir / "control-surfaces.json").write_text(
        json.dumps({"control_surfaces": globs, "gate_own": []}, indent=2) + "\n",
        encoding="utf-8",
    )




def _gate_write_verdict(spec_dir: "Path", checks: dict, *, override: str | None = None) -> None:
    body = "---\nkind: gate-verdict\nchecks:\n"
    for k, v in checks.items():
        body += f"  {k}: {v}\n"
    if override:
        body += f'override: "{override}"\n'
    body += "---\n\n# Gate Verdict\n"
    (spec_dir / "GATE_VERDICT.md").write_text(body, encoding="utf-8")




# ---------------------------------------------------------------------------
# Group C — vocabulary drift guard: _INTERVENTION_EVENT_VOCABULARY must equal
# the LIVE emit set (every string literal passed as the first positional arg
# to append_telemetry_event(...) across lazy_core.py, lazy-state.py, and
# bug-state.py). Mirrors the `_collect_orphaned_test_names` AST-collector
# idiom (pure collector + a self-checking test), pinned to THIS module's
# directory so the test is CWD-independent.
# ---------------------------------------------------------------------------

def _collect_telemetry_event_literals(source: str) -> "set[str]":
    """Pure AST collector: return the set of string literals passed as the
    FIRST POSITIONAL argument to every ``append_telemetry_event(...)`` call
    in ``source`` (bare ``Name`` calls and ``obj.append_telemetry_event(...)``
    ``Attribute`` calls alike). Only ``args[0]`` is inspected — keyword
    arguments (e.g. ``data={...}``) are NEVER inspected, so incidental string
    literals inside a call's ``data=`` dict (e.g. ``"pseudo"``) can never be
    wrongly folded into the collected event-type set.
    """
    tree = ast.parse(source)
    literals: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        is_target = (
            (isinstance(func, ast.Name) and func.id == "append_telemetry_event")
            or (isinstance(func, ast.Attribute)
                and func.attr == "append_telemetry_event")
        )
        if not is_target:
            continue
        if not node.args:
            continue
        first = node.args[0]
        if isinstance(first, ast.Constant) and isinstance(first.value, str):
            literals.add(first.value)
    return literals




# ---------------------------------------------------------------------------
# production-sentinel-writes-bypass-atomic-write — mechanical bare-write lint
# gate (Fix Scope item 2: "a check ... that FAILS on `.write_text(` / `open(...,
# 'w'` outside the designated test/fixture regions ... so the NEXT bare write
# cannot land silently"). Pure AST collector + a self-checking meta-test +  a
# negative-fixture non-vacuity proof, mirroring the `_collect_orphaned_test_names`
# / `_collect_telemetry_event_literals` idiom already established in this file.
# ---------------------------------------------------------------------------

# Per-file exempt-region marker: every write AT OR AFTER the line carrying this
# substring is inside the designated fixture/test region (hermetic temp-dir
# writers whose mid-write failure has no machine-visible consequence — SPEC
# D1). `None` means the file has NO exempt region at all (100% production-
# scoped) — lazy_core.py's own writers already all route through _atomic_write.
_BARE_WRITE_EXEMPT_REGION_MARKERS: dict = {
    "lazy-state.py": "# Fixture smoke tests",
    "bug-state.py": "SMOKE FIXTURES + --test",
    "lazy_core.py": None,
}




def _bare_write_exempt_line(source: str, filename: str) -> int:
    """Return the 1-based line number at/after which writes are exempt (the
    fixture-region banner). A declared-but-missing marker, or a filename with no
    declared marker, returns 0 (nothing exempt — fail LOUD via over-flagging,
    never silently under-scope)."""
    marker = _BARE_WRITE_EXEMPT_REGION_MARKERS.get(filename)
    if marker is None:
        return 0
    for i, line in enumerate(source.splitlines(), start=1):
        if marker in line:
            return i
    return 0




def _collect_bare_production_writes(source: str, filename: str) -> list:
    """Pure AST collector: return a sorted list of ``(lineno, kind)`` for every
    bare ``<expr>.write_text(...)`` call OR ``open(<path>, "w"/"a"...)`` call
    that appears BEFORE ``filename``'s fixture-exempt-region marker line (i.e.
    in production code). ``_atomic_write(...)`` calls are never flagged — that
    IS the sanctioned primitive. A read-mode/mode-less ``open(...)`` is never
    flagged (only an explicit write/append mode is the corruption class this
    guards). Pure (source, filename) — no I/O — so a negative fixture can feed
    synthetic source under a synthetic filename.
    """
    exempt_from = _bare_write_exempt_line(source, filename)
    tree = ast.parse(source)
    hits: list = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        lineno = getattr(node, "lineno", 0)
        if exempt_from and lineno >= exempt_from:
            continue  # inside the fixture-exempt region
        func = node.func
        if isinstance(func, ast.Attribute) and func.attr == "write_text":
            hits.append((lineno, "write_text"))
        elif isinstance(func, ast.Name) and func.id == "open":
            mode_arg = None
            if len(node.args) >= 2:
                mode_arg = node.args[1]
            else:
                for kw in node.keywords:
                    if kw.arg == "mode":
                        mode_arg = kw.value
            if (isinstance(mode_arg, ast.Constant)
                    and isinstance(mode_arg.value, str)
                    and mode_arg.value.strip("bt").startswith(("w", "a"))):
                hits.append((lineno, "open-write-mode"))
    return sorted(hits)




# ---------------------------------------------------------------------------
# production-sentinel-writes-bypass-atomic-write — F811-class duplicate
# top-level-def guard (Fix Scope item 3: "adopt an F811-class gate", substituted
# here with a stdlib AST duplicate-definition collector rather than adding a
# ruff dependency — SPEC D2's documented "grep/AST-based check alone still
# closes the contract gap" latitude). Catches the exact defect class the bug's
# "bonus finding" identified: `_current_head` was defined twice in lazy_core.py
# with the second definition silently shadowing the first at module load.
# ---------------------------------------------------------------------------

def _collect_duplicate_top_level_defs(source: str) -> list:
    """Pure AST collector: return a sorted list of names defined more than once
    as a top-level ``def``/``async def``/``class`` in ``source`` (the F811
    shadowing class — a later definition silently replaces an earlier one at
    module load, with no import-time signal). Pure (source only, no I/O) so a
    negative fixture can feed synthetic source.
    """
    tree = ast.parse(source)
    names: list = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.append(node.name)
    from collections import Counter
    counts = Counter(names)
    return sorted(name for name, n in counts.items() if n > 1)




# ---------------------------------------------------------------------------
# cp1252-fragile-subprocess-and-fixture-captures — mechanical guard against a
# recurring Windows-cp1252 defect class: a test/fixture-context subprocess text
# capture (`subprocess.run(..., text=True)` etc.) with NO `encoding="utf-8"`
# decodes the child's UTF-8 stdout with the parent's LOCALE default (cp1252 on
# this machine) → mojibake mismatch OR a hard UnicodeDecodeError that CRASHES a
# `--test` run; and a bare `Path(...).write_text("...—...")` with non-ASCII
# content and no encoding= writes a cp1252 byte a later `read_text("utf-8")`
# cannot decode. Production paths route through the shared UTF-8-safe readers;
# this collector guards the TEST/FIXTURE surface the merge-round sweep fixed.
# Pure (source, filename) AST collector — no I/O — mirroring the
# `_collect_bare_production_writes` / `_collect_duplicate_top_level_defs` idiom.
# ---------------------------------------------------------------------------

def _cp1252_is_test_context_file(filename: str) -> bool:
    """A dedicated pytest module (whole-file test context) — its basename starts
    ``test_``, it is ``_util.py``, or a ``tests`` path component is present."""
    parts = re.split(r"[\\/]", filename)
    base = parts[-1] if parts else filename
    return base.startswith("test_") or base == "_util.py" or "tests" in parts


def _cp1252_call_name(call: "ast.Call") -> "str | None":
    f = call.func
    if isinstance(f, ast.Attribute):
        return f.attr
    if isinstance(f, ast.Name):
        return f.id
    return None


def _cp1252_has_kw(call: "ast.Call", name: str) -> bool:
    return any(k.arg == name for k in call.keywords)


def _cp1252_is_subprocess_text_capture(call: "ast.Call") -> bool:
    """A ``subprocess.<run|check_output|Popen|call|check_call>(...)`` call that
    decodes child output as TEXT (``text=True`` / ``universal_newlines=True``)."""
    if _cp1252_call_name(call) not in ("run", "check_output", "Popen", "call", "check_call"):
        return False
    f = call.func
    if not (isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name)
            and f.value.id in ("subprocess", "sp")):
        return False
    for k in call.keywords:
        if k.arg in ("text", "universal_newlines") and isinstance(k.value, ast.Constant) and k.value.value is True:
            return True
    return False


def _cp1252_node_has_nonascii(node: "ast.AST") -> bool:
    for n in ast.walk(node):
        if isinstance(n, ast.Constant) and isinstance(n.value, str) and any(ord(c) > 127 for c in n.value):
            return True
    return False


def _collect_cp1252_fragile_captures(source: str, filename: str) -> list:
    """Pure AST collector: return a sorted list of ``(lineno, kind)`` for every
    cp1252-fragile capture/write in ``source``'s TEST/FIXTURE context.

    ``kind`` is ``"subprocess"`` (a text-decoding ``subprocess.*`` capture with
    no ``encoding=``) or ``"write_text"`` (a ``write_text(...)`` with non-ASCII
    positional content and no ``encoding=``).

    TEST/FIXTURE context is: the WHOLE file for a dedicated pytest module
    (``_cp1252_is_test_context_file``), else every function transitively
    reachable — by direct-name call graph — from ``run_smoke_tests`` or a
    ``test_*``/``_smoke*`` root (the in-file ``--test`` harness of the state
    scripts / ``lazy_coord.py``). Production subprocess captures are OUT of
    scope (they route through the shared UTF-8-safe readers). Pure — no I/O — so
    a synthetic negative fixture can drive it."""
    tree = ast.parse(source)
    whole_file = _cp1252_is_test_context_file(filename)

    test_funcs: "set | None" = None
    if not whole_file:
        defs: dict = {}
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                defs[node.name] = node
        roots = {n for n in defs
                 if n == "run_smoke_tests" or n.startswith("test_") or n.startswith("_smoke")}
        if not roots:
            return []
        # transitive closure over direct-name calls
        seen: set = set()
        stack = list(roots)
        while stack:
            fn = stack.pop()
            if fn in seen or fn not in defs:
                continue
            seen.add(fn)
            for c in ast.walk(defs[fn]):
                if isinstance(c, ast.Call):
                    cn = _cp1252_call_name(c)
                    if cn and cn in defs and cn not in seen:
                        stack.append(cn)
        test_funcs = seen

    hits: list = []
    stack_names: list = []

    def in_ctx() -> bool:
        if whole_file:
            return True
        return any(fn in test_funcs for fn in stack_names)

    class _V(ast.NodeVisitor):
        def visit_FunctionDef(self, node):
            stack_names.append(node.name)
            self.generic_visit(node)
            stack_names.pop()
        visit_AsyncFunctionDef = visit_FunctionDef

        def visit_Call(self, node):
            if in_ctx():
                if _cp1252_is_subprocess_text_capture(node) and not _cp1252_has_kw(node, "encoding"):
                    hits.append((node.lineno, "subprocess"))
                elif (_cp1252_call_name(node) == "write_text"
                        and not _cp1252_has_kw(node, "encoding")
                        and node.args and _cp1252_node_has_nonascii(node.args[0])):
                    hits.append((node.lineno, "write_text"))
            self.generic_visit(node)

    _V().visit(tree)
    return sorted(hits)
