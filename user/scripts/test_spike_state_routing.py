#!/usr/bin/env python3
"""
test_spike_state_routing.py — Tests for the Step 9.5 spike-routing gate in
lazy-state.py::compute_state (docs/specs/spike-pipeline-role Phase 2, WU-1),
PLUS its coupled bug-pipeline mirror in bug-state.py::compute_state (WU-3).

WU-1 adds a gate BETWEEN the end of the Step 9 MCP-gate block (the
workstation branch's last `return`, "Step 9: run MCP tests") and the Step 10
mark-complete block ("Step 10: Mark complete."). Control reaches that seam
only when VALIDATED.md exists (Step 9's workstation `if not
validated_file.exists():` guard fell through). The new gate:

  - If `phases_spike_required(spec_path)` is True AND the spike verdict at
    `{spec_path}/SPIKE_VERDICT.md` is not `verdict: PASS` (case-insensitive)
    → route to `sub_skill: "spike"`, `current_step: "Step 9.5: spike verdict
    pending"`.
  - Else → fall through to Step 10 byte-identically (today's behavior).

RED STATE (today): compute_state has no Step 9.5 gate — a feature whose
PHASES.md declares `**Spike:** required` with no PASS SPIKE_VERDICT.md falls
straight through Step 9 into Step 10 (`sub_skill: "__mark_complete__"`)
instead of being routed to `sub_skill: "spike"`. The two
`test_spike_required_*` cases below FAIL until WU-1 lands; the no-spike-line
and PASS-verdict cases already pass today (they assert the "must NOT route
to spike" invariant, true both before and after WU-1).

WU-3 mirrors BOTH signals into bug-state.py::compute_state (the coupled bug
axis — `__mark_fixed__`/`FIXED.md` in place of `__mark_complete__`/
`COMPLETED.md`). The ROUTING (`sub_skill: "spike"`, both `current_step`
strings) is IDENTICAL to the feature axis; only the receipt/terminal names
differ. RED STATE (today, bug axis): bug-state.py has no Step 9.5 gate and no
`blocker_kind: runtime-spike-verdict-pending` Step-3 resolver — a bug reaches
`__mark_fixed__` / the generic terminal `blocked` instead of routing to
`spike`. The `test_bug_spike_required_no_verdict_routes_to_spike` and
`test_bug_blocker_runtime_spike_verdict_pending_routes_to_spike` cases below
FAIL until WU-3 lands; the pass-verdict / other-blocker-kind / no-spike-line
bug-axis cases already pass today (regression guards, true before and after).

Run with: python3 user/scripts/test_spike_state_routing.py   (exit 0 on pass)
Also pytest-discoverable (every `test_*` function is a standalone test).
No third-party dependencies — stdlib only.
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).parent


def _load_hyphenated(module_name: str, filename: str):
    spec = importlib.util.spec_from_file_location(
        module_name, str(_SCRIPTS_DIR / filename)
    )
    mod = importlib.util.module_from_spec(spec)
    # Register before exec so dataclass type-resolution can find the module.
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


# ---------------------------------------------------------------------------
# Import the hyphenated module under a clean name.
# ---------------------------------------------------------------------------
_IMPORT_ERROR = None
lazy_state = None
try:
    lazy_state = _load_hyphenated("lazy_state_for_spike_tests", "lazy-state.py")
except Exception as exc:  # noqa: BLE001
    _IMPORT_ERROR = exc

_BUG_IMPORT_ERROR = None
bug_state = None
try:
    bug_state = _load_hyphenated("bug_state_for_spike_tests", "bug-state.py")
except Exception as exc:  # noqa: BLE001
    _BUG_IMPORT_ERROR = exc


# A minimal, valid VALIDATED.md (kind: validated, result: all-passing) —
# mirrors tests/test_lazy_core/_util.py::_write_validated_md. Writing this
# directly (rather than driving a full /mcp-test dispatch) is what lets the
# fixture satisfy Step 9's `if not validated_file.exists():` guard so control
# reaches the Step 9.5 seam.
_VALIDATED_MD = (
    "---\n"
    "kind: validated\n"
    "feature_id: test-feature\n"
    "date: 2026-07-17\n"
    "mcp_scenarios: []\n"
    "result: all-passing\n"
    "---\n\n"
    "# Validated\n"
)


def _spike_verdict_md(feature_id: str, verdict: str) -> str:
    return (
        "---\n"
        "kind: spike-verdict\n"
        f"feature_id: {feature_id}\n"
        f"verdict: {verdict}\n"
        "---\n\n"
        "# Spike Verdict\n"
    )


def _build_fixture(
    tmpdir: Path,
    *,
    feature_id: str,
    spike_required: bool,
    spike_goal: str = "prove projector holds 30fps",
    verdict: str | None = None,
) -> Path:
    """Build a minimal fixture repo that reaches the Step-9.5 seam.

    Modeled on lazy-state.py::_build_fixture's "phases-complete-no-retro-done"
    case (all phases complete, no other sentinels) plus a directly-written
    VALIDATED.md so control reaches the seam between the end of Step 9 and
    Step 10 (non-cloud). Optionally declares `**Spike:** required` in
    PHASES.md and/or writes a SPIKE_VERDICT.md.
    """
    root = tmpdir / feature_id
    features = root / "docs" / "features"
    features.mkdir(parents=True)
    (features / "queue.json").write_text(json.dumps({
        "queue": [
            {"id": feature_id, "name": f"Feature {feature_id}",
             "spec_dir": feature_id, "tier": 1},
        ]
    }))
    (features / "ROADMAP.md").write_text("# Roadmap\n")
    p = features / feature_id
    p.mkdir()
    (p / "SPEC.md").write_text(
        "# Spec\n\n**Status:** Draft\n\n**Depends on:** (none)\n"
    )
    (p / "RESEARCH.md").write_text("# R\n")
    (p / "RESEARCH_SUMMARY.md").write_text("# S\n")
    phases_body = "# Phases\n\n"
    if spike_required:
        phases_body += f"**Spike:** required — {spike_goal}\n\n"
    phases_body += "### Phase 1\n- [x] Done\n"
    (p / "PHASES.md").write_text(phases_body)
    (p / "VALIDATED.md").write_text(_VALIDATED_MD)
    if verdict is not None:
        (p / "SPIKE_VERDICT.md").write_text(_spike_verdict_md(feature_id, verdict))
    return root


def _blocked_md(
    feature_id: str,
    *,
    blocker_kind: str | None,
    phase: str = "MCP Validation",
    blocked_at: str = "2026-07-17T12:00:00Z",
    retry_count: int = 0,
) -> str:
    """Canonical BLOCKED.md frontmatter (kind: blocked), modeled on
    lazy-state.py::_write_yaml_blocked_sentinel's production shape. When
    blocker_kind is None, the field is omitted entirely (the
    no-blocker_kind-still-terminal regression fixture)."""
    lines = ["---", "kind: blocked", f"feature_id: {feature_id}", f"phase: {phase}"]
    if blocker_kind is not None:
        lines.append(f"blocker_kind: {blocker_kind}")
    lines.append(f"blocked_at: {blocked_at}")
    lines.append(f"retry_count: {retry_count}")
    lines.append("---")
    lines.append("")
    lines.append("# Blocked")
    lines.append("")
    return "\n".join(lines)


def _build_blocked_fixture(
    tmpdir: Path,
    *,
    feature_id: str,
    blocker_kind: str | None,
) -> Path:
    """Minimal fixture reaching the Step-3 BLOCKED.md check directly (no
    PHASES.md / VALIDATED.md needed — that check fires right after the
    queue walk lands on the current item, well before Step 9.5)."""
    root = tmpdir / feature_id
    features = root / "docs" / "features"
    features.mkdir(parents=True)
    (features / "queue.json").write_text(json.dumps({
        "queue": [
            {"id": feature_id, "name": f"Feature {feature_id}",
             "spec_dir": feature_id, "tier": 1},
        ]
    }))
    (features / "ROADMAP.md").write_text("# Roadmap\n")
    p = features / feature_id
    p.mkdir()
    (p / "SPEC.md").write_text(
        "# Spec\n\n**Status:** Draft\n\n**Depends on:** (none)\n"
    )
    (p / "BLOCKED.md").write_text(
        _blocked_md(feature_id, blocker_kind=blocker_kind)
    )
    return root


def _compute(root: Path):
    """Call compute_state with an isolated LAZY_STATE_DIR so the fixture
    never touches real repo state (belt-and-suspenders — each fixture's
    repo_root is already unique, giving natural repo_key isolation, but the
    explicit pin matches the discipline used elsewhere in lazy-state.py's
    own --test harness, e.g. the `_pf_prev_env`/`_bg_prev_env` save-restore
    blocks around lines ~7251 and ~7357)."""
    with tempfile.TemporaryDirectory(prefix="spike-state-dir-") as sd:
        prev = os.environ.get("LAZY_STATE_DIR")
        os.environ["LAZY_STATE_DIR"] = sd
        try:
            return lazy_state.compute_state(root, cloud=False, real_device=True)
        finally:
            if prev is None:
                os.environ.pop("LAZY_STATE_DIR", None)
            else:
                os.environ["LAZY_STATE_DIR"] = prev


# ---------------------------------------------------------------------------
# WU-3: bug-axis fixture builders — the coupled mirror of _build_fixture /
# _build_blocked_fixture above, driving bug-state.py::compute_state instead
# of lazy-state.py's. Bug-pipeline shapes (docs/bugs/, SPEC.md **Status:**
# In-progress / Investigating, no **Depends on:** block) modeled on the
# nearest existing bug-state.py --test fixtures ("ready-to-mark-fixed" for
# the header-gate seam, "blocked" for the Step-3 seam) — see
# bug-state.py::_build_bug_fixture around line 2470 for the production
# convention this mirrors. VALIDATED.md / SPIKE_VERDICT.md / BLOCKED.md are
# written via bug_state's OWN sentinel-writer helpers
# (_write_yaml_sentinel / _write_yaml_blocked_sentinel) rather than
# hand-formatted strings, so the fixtures can never drift from the real
# on-disk schema those helpers produce.
# ---------------------------------------------------------------------------


def _build_bug_spike_fixture(
    tmpdir: Path,
    *,
    bug_id: str,
    spike_required: bool,
    spike_goal: str = "prove projector holds 30fps",
    verdict: str | None = None,
) -> Path:
    """Build a minimal bug fixture that reaches the bug-axis Step-9.5 seam.

    Modeled on bug-state.py::_build_bug_fixture's "ready-to-mark-fixed" case
    (phases complete, VALIDATED.md present — RETRO_DONE.md is NOT required;
    retro is unwired on the bug pipeline, see bug-state.py's "phases-
    complete-no-retro" fixture) plus an optional `**Spike:** required`
    PHASES.md line and/or a SPIKE_VERDICT.md.
    """
    root = tmpdir / bug_id
    bugs_dir = root / "docs" / "bugs"
    bugs_dir.mkdir(parents=True)
    (bugs_dir / "queue.json").write_text(json.dumps({
        "queue": [
            {"id": bug_id, "name": f"Bug {bug_id}", "spec_dir": bug_id},
        ]
    }))
    bdir = bugs_dir / bug_id
    bdir.mkdir()
    (bdir / "SPEC.md").write_text(
        f"# Bug {bug_id}\n\n"
        "**Status:** In-progress\n\n"
        "**Severity:** P1\n\n"
        "**Discovered:** 2026-07-17\n"
    )
    phases_body = "# Phases\n\n"
    if spike_required:
        phases_body += f"**Spike:** required — {spike_goal}\n\n"
    phases_body += (
        "### Phase 1\n"
        "- [x] Root cause identified\n"
        "- [x] Implement fix\n"
    )
    (bdir / "PHASES.md").write_text(phases_body)
    bug_state._write_yaml_sentinel(
        bdir / "VALIDATED.md", "validated",
        bug_id=bug_id, date="2026-07-17", result="all-passing",
    )
    if verdict is not None:
        bug_state._write_yaml_sentinel(
            bdir / "SPIKE_VERDICT.md", "spike-verdict",
            bug_id=bug_id, verdict=verdict,
        )
    return root


def _build_bug_blocked_fixture(
    tmpdir: Path,
    *,
    bug_id: str,
    blocker_kind: str,
) -> Path:
    """Minimal bug fixture reaching the bug-axis Step-3 BLOCKED.md check
    directly (no PHASES.md / VALIDATED.md needed — mirrors the feature-axis
    _build_blocked_fixture above). Modeled on bug-state.py::_build_bug_fixture's
    "blocked" case + the canonical _write_yaml_blocked_sentinel helper (the
    same one the host-capability-unknown fail-fast fixture uses)."""
    root = tmpdir / bug_id
    bugs_dir = root / "docs" / "bugs"
    bugs_dir.mkdir(parents=True)
    (bugs_dir / "queue.json").write_text(json.dumps({
        "queue": [
            {"id": bug_id, "name": f"Bug {bug_id}", "spec_dir": bug_id},
        ]
    }))
    bdir = bugs_dir / bug_id
    bdir.mkdir()
    (bdir / "SPEC.md").write_text(
        f"# Bug {bug_id}\n\n"
        "**Status:** Investigating\n\n"
        "**Severity:** P2\n\n"
        "**Discovered:** 2026-07-17\n"
    )
    bug_state._write_yaml_blocked_sentinel(
        bdir / "BLOCKED.md",
        feature_id=bug_id, phase="Investigation", blocker_kind=blocker_kind,
        blocked_at="2026-07-17T12:00:00Z", retry_count=0,
    )
    return root


def _compute_bug(root: Path):
    """Call bug_state.compute_state with an isolated LAZY_STATE_DIR — the
    bug-axis mirror of _compute above."""
    with tempfile.TemporaryDirectory(prefix="spike-bug-state-dir-") as sd:
        prev = os.environ.get("LAZY_STATE_DIR")
        os.environ["LAZY_STATE_DIR"] = sd
        try:
            return bug_state.compute_state(root, cloud=False, real_device=True)
        finally:
            if prev is None:
                os.environ.pop("LAZY_STATE_DIR", None)
            else:
                os.environ["LAZY_STATE_DIR"] = prev


def test_import_ok():
    assert _IMPORT_ERROR is None, f"lazy-state.py import failed: {_IMPORT_ERROR!r}"


def test_bug_import_ok():
    assert _BUG_IMPORT_ERROR is None, f"bug-state.py import failed: {_BUG_IMPORT_ERROR!r}"


def test_spike_required_no_verdict_routes_to_spike():
    """PHASES.md declares `**Spike:** required` and NO SPIKE_VERDICT.md
    exists → must route to sub_skill 'spike' at the Step 9.5 seam."""
    with tempfile.TemporaryDirectory(prefix="spike-fixture-") as td:
        root = _build_fixture(
            Path(td), feature_id="feat-spk-t1", spike_required=True, verdict=None,
        )
        result = _compute(root)
        assert result.get("sub_skill") == "spike", (
            "expected sub_skill='spike' (spike required, no verdict on "
            f"disk) — WU-1 Step 9.5 gate looks unimplemented; got {result!r}"
        )
        assert result.get("current_step") == "Step 9.5: spike verdict pending", (
            f"expected the Step 9.5 pending current_step; got {result!r}"
        )


def test_spike_required_fail_verdict_routes_to_spike():
    """A SPIKE_VERDICT.md with verdict: FAIL must still route to spike —
    only a PASS verdict falls through."""
    with tempfile.TemporaryDirectory(prefix="spike-fixture-") as td:
        root = _build_fixture(
            Path(td), feature_id="feat-spk-t2", spike_required=True, verdict="FAIL",
        )
        result = _compute(root)
        assert result.get("sub_skill") == "spike", (
            "a FAIL verdict must still route to spike (only PASS falls "
            f"through); got {result!r}"
        )


def test_spike_required_pass_verdict_falls_through():
    """A SPIKE_VERDICT.md with verdict: PASS must fall through to Step 10 —
    never routed to spike."""
    with tempfile.TemporaryDirectory(prefix="spike-fixture-") as td:
        root = _build_fixture(
            Path(td), feature_id="feat-spk-t3", spike_required=True, verdict="PASS",
        )
        result = _compute(root)
        assert result.get("sub_skill") != "spike", (
            "a PASS verdict must fall through to Step 10, not route to "
            f"spike; got {result!r}"
        )


def test_no_spike_line_byte_identical():
    """No `**Spike:**` line in PHASES.md at all → routes to Step 10 exactly
    as today (never routed to spike)."""
    with tempfile.TemporaryDirectory(prefix="spike-fixture-") as td:
        root = _build_fixture(
            Path(td), feature_id="feat-spk-t4", spike_required=False, verdict=None,
        )
        result = _compute(root)
        assert result.get("sub_skill") != "spike", (
            "no **Spike:** line must route to Step 10 exactly as today; "
            f"got {result!r}"
        )


# ---------------------------------------------------------------------------
# WU-2: the BLOCKED.md `blocker_kind: runtime-spike-verdict-pending` resolver
# route. Distinct from the Step 9.5 gate above (WU-1) — this fires at Step 3,
# BEFORE phases/research/VALIDATED.md are ever read. RED today: the Step-3
# BLOCKED block always returns terminal_reason="blocked" with no sub_skill
# routing, regardless of blocker_kind.
# ---------------------------------------------------------------------------


def test_blocker_runtime_spike_verdict_pending_routes_to_spike():
    """A BLOCKED.md carrying blocker_kind: runtime-spike-verdict-pending must
    route to sub_skill 'spike' as a NON-terminal (routed) state — no
    terminal_reason — at the dedicated Step 3 current_step label."""
    with tempfile.TemporaryDirectory(prefix="spike-blocker-fixture-") as td:
        root = _build_blocked_fixture(
            Path(td), feature_id="feat-spkb-t1",
            blocker_kind="runtime-spike-verdict-pending",
        )
        result = _compute(root)
        assert result.get("sub_skill") == "spike", (
            "expected sub_skill='spike' for blocker_kind: "
            f"runtime-spike-verdict-pending — got {result!r}"
        )
        assert result.get("terminal_reason") is None, (
            "the spike blocked-resolver route must be NON-terminal "
            f"(sub_skill routes onward); got terminal_reason={result.get('terminal_reason')!r}"
        )
        assert result.get("current_step") == "Step 3: spike verdict pending (blocked resolver)", (
            f"expected the Step 3 spike blocked-resolver current_step; got {result!r}"
        )


def test_blocker_other_kind_still_terminal():
    """A DIFFERENT blocker_kind (e.g. mcp-validation) must still halt as
    today — terminal_reason='blocked', never routed to spike. Regression
    guard for the pre-existing Step-3 BLOCKED behavior."""
    with tempfile.TemporaryDirectory(prefix="spike-blocker-fixture-") as td:
        root = _build_blocked_fixture(
            Path(td), feature_id="feat-spkb-t2", blocker_kind="mcp-validation",
        )
        result = _compute(root)
        assert result.get("terminal_reason") == "blocked", (
            f"a non-spike blocker_kind must stay terminal_reason='blocked'; got {result!r}"
        )
        assert result.get("sub_skill") != "spike", (
            f"a non-spike blocker_kind must never route to spike; got {result!r}"
        )


def test_blocker_no_blocker_kind_still_terminal():
    """A BLOCKED.md with NO blocker_kind field at all must still halt as
    today — terminal_reason='blocked', never routed to spike."""
    with tempfile.TemporaryDirectory(prefix="spike-blocker-fixture-") as td:
        root = _build_blocked_fixture(
            Path(td), feature_id="feat-spkb-t3", blocker_kind=None,
        )
        result = _compute(root)
        assert result.get("terminal_reason") == "blocked", (
            f"a missing blocker_kind must stay terminal_reason='blocked'; got {result!r}"
        )
        assert result.get("sub_skill") != "spike", (
            f"a missing blocker_kind must never route to spike; got {result!r}"
        )


# ---------------------------------------------------------------------------
# WU-3: bug-axis mirror of the WU-1/WU-2 tests above, driving
# bug-state.py::compute_state. Same routing assertions; the bug pipeline uses
# __mark_fixed__/FIXED.md in place of __mark_complete__/COMPLETED.md, but
# that receipt-name divergence never appears in these assertions — only the
# ROUTING (sub_skill == "spike", the two current_step strings) is checked,
# which is IDENTICAL across both axes by design.
# ---------------------------------------------------------------------------


def test_bug_spike_required_no_verdict_routes_to_spike():
    """Bug-axis mirror: PHASES.md declares `**Spike:** required` and NO
    SPIKE_VERDICT.md exists → must route to sub_skill 'spike' at the bug
    pipeline's Step 9.5 seam."""
    with tempfile.TemporaryDirectory(prefix="spike-bug-fixture-") as td:
        root = _build_bug_spike_fixture(
            Path(td), bug_id="bug-spknv", spike_required=True, verdict=None,
        )
        result = _compute_bug(root)
        assert result.get("sub_skill") == "spike", (
            "expected sub_skill='spike' (spike required, no verdict on "
            f"disk) — WU-3 bug-state.py Step 9.5 gate looks unimplemented; "
            f"got {result!r}"
        )
        assert result.get("current_step") == "Step 9.5: spike verdict pending", (
            f"expected the Step 9.5 pending current_step; got {result!r}"
        )


def test_bug_spike_required_pass_verdict_falls_through():
    """Bug-axis mirror: a SPIKE_VERDICT.md with verdict: PASS must fall
    through toward __mark_fixed__ — never routed to spike."""
    with tempfile.TemporaryDirectory(prefix="spike-bug-fixture-") as td:
        root = _build_bug_spike_fixture(
            Path(td), bug_id="bug-spkpv", spike_required=True, verdict="PASS",
        )
        result = _compute_bug(root)
        assert result.get("sub_skill") != "spike", (
            "a PASS verdict must fall through toward __mark_fixed__, not "
            f"route to spike; got {result!r}"
        )


def test_bug_no_spike_line_byte_identical():
    """Bug-axis mirror: no `**Spike:**` line in PHASES.md at all → routes
    toward __mark_fixed__ exactly as today (never routed to spike)."""
    with tempfile.TemporaryDirectory(prefix="spike-bug-fixture-") as td:
        root = _build_bug_spike_fixture(
            Path(td), bug_id="bug-spknl", spike_required=False, verdict=None,
        )
        result = _compute_bug(root)
        assert result.get("sub_skill") != "spike", (
            "no **Spike:** line must route toward __mark_fixed__ exactly as "
            f"today; got {result!r}"
        )


def test_bug_blocker_runtime_spike_verdict_pending_routes_to_spike():
    """Bug-axis mirror: a BLOCKED.md carrying blocker_kind:
    runtime-spike-verdict-pending must route to sub_skill 'spike' as a
    NON-terminal (routed) state — no terminal_reason — at the dedicated
    bug-pipeline Step 3 current_step label."""
    with tempfile.TemporaryDirectory(prefix="spike-bug-blocker-fixture-") as td:
        root = _build_bug_blocked_fixture(
            Path(td), bug_id="bug-spkbr",
            blocker_kind="runtime-spike-verdict-pending",
        )
        result = _compute_bug(root)
        assert result.get("sub_skill") == "spike", (
            "expected sub_skill='spike' for blocker_kind: "
            f"runtime-spike-verdict-pending — got {result!r}"
        )
        assert result.get("terminal_reason") is None, (
            "the spike blocked-resolver route must be NON-terminal "
            f"(sub_skill routes onward); got terminal_reason={result.get('terminal_reason')!r}"
        )
        assert result.get("current_step") == "Step 3: spike verdict pending (blocked resolver)", (
            f"expected the Step 3 spike blocked-resolver current_step; got {result!r}"
        )


def test_bug_blocker_other_kind_still_terminal():
    """Bug-axis mirror: a DIFFERENT blocker_kind (e.g. mcp-validation) must
    still halt as today — terminal_reason='blocked', never routed to spike.
    Regression guard for the pre-existing bug-pipeline Step-3 BLOCKED
    behavior."""
    with tempfile.TemporaryDirectory(prefix="spike-bug-blocker-fixture-") as td:
        root = _build_bug_blocked_fixture(
            Path(td), bug_id="bug-spkok", blocker_kind="mcp-validation",
        )
        result = _compute_bug(root)
        assert result.get("terminal_reason") == "blocked", (
            f"a non-spike blocker_kind must stay terminal_reason='blocked'; got {result!r}"
        )
        assert result.get("sub_skill") != "spike", (
            f"a non-spike blocker_kind must never route to spike; got {result!r}"
        )


if __name__ == "__main__":
    import traceback

    tests = [
        test_import_ok,
        test_spike_required_no_verdict_routes_to_spike,
        test_spike_required_fail_verdict_routes_to_spike,
        test_spike_required_pass_verdict_falls_through,
        test_no_spike_line_byte_identical,
        test_blocker_runtime_spike_verdict_pending_routes_to_spike,
        test_blocker_other_kind_still_terminal,
        test_blocker_no_blocker_kind_still_terminal,
        test_bug_import_ok,
        test_bug_spike_required_no_verdict_routes_to_spike,
        test_bug_spike_required_pass_verdict_falls_through,
        test_bug_no_spike_line_byte_identical,
        test_bug_blocker_runtime_spike_verdict_pending_routes_to_spike,
        test_bug_blocker_other_kind_still_terminal,
    ]
    failures = 0
    for t in tests:
        try:
            t()
            print(f"PASS: {t.__name__}")
        except AssertionError as exc:
            failures += 1
            print(f"FAIL: {t.__name__}: {exc}")
        except Exception:  # noqa: BLE001
            failures += 1
            print(f"ERROR: {t.__name__}")
            traceback.print_exc()
    print(f"\n{len(tests) - failures}/{len(tests)} passed")
    sys.exit(1 if failures else 0)
