#!/usr/bin/env python3
"""
test_spike_tooling_loop.py — Tests for the bounded tooling-existence loop
guard (docs/specs/spike-pipeline-role Phase 4, WU-2).

Three contracts under test, all currently ABSENT/UNWIRED (RED today):

  A. ``lazy_core.spike_tooling_cap_exceeded(meta, cap=None) -> bool`` — a new
     shared helper (destined for ``user/scripts/lazy_core/gates.py``, exported
     via ``lazy_core/__init__.py``) mirroring the existing
     ``lazy_core.spike_escalation`` tolerance shape. Defaults ``cap`` to a
     module constant ``_SPIKE_TOOLING_ROUNDS_CAP = 3``; ``rounds >= cap``.

  B. ``lazy_core.write_spike_tooling_cap_needs_input(spec_dir, item_name,
     rounds) -> None`` — a new shared writer (destined for
     ``lazy_core/docmodel.py``) that writes a valid ``NEEDS_INPUT.md`` per
     ``~/.claude/skills/_components/sentinel-frontmatter.md``, carrying
     ``written_by: spike`` (CRITICAL — this is what makes
     ``lazy_core.provisional_eligibility`` refuse to auto-accept the halt
     under park-provisional, per the existing Spike-FAIL carve-out at
     ``docmodel.py``).

  C. Routing wiring in BOTH ``lazy-state.py`` and ``bug-state.py``
     ``compute_state`` — two seams per axis:
       - Blocked-resolver seam (Step 3): a BLOCKED.md with
         ``blocker_kind: runtime-spike-verdict-pending`` AND
         ``spike_tooling_rounds: 3`` (at/above cap) must route to
         ``terminal_reason == "needs-input"``, NOT ``sub_skill == "spike"``.
         ``spike_tooling_rounds: 2`` (below cap) or the field absent must
         still route to ``sub_skill == "spike"`` (today's behavior,
         unchanged — a regression guard).
       - Step-9.5 header-gate seam: PHASES.md declares ``**Spike:**
         required`` + VALIDATED.md present + a SPIKE_VERDICT.md with
         ``verdict: PENDING`` (not PASS) carrying
         ``spike_tooling_rounds: 3`` must route to
         ``terminal_reason == "needs-input"``, NOT ``sub_skill == "spike"``.
         ``spike_tooling_rounds: 2`` must still route to
         ``sub_skill == "spike"`` (regression guard).

     Tested on BOTH the feature axis (lazy-state.py::compute_state) and the
     bug axis (bug-state.py::compute_state) — the coupled-pair body-parity
     guard for this feature.

RED STATE (today): ``lazy_core.spike_tooling_cap_exceeded`` and
``lazy_core.write_spike_tooling_cap_needs_input`` do not exist
(AttributeError). Neither state script's Step-3 BLOCKED resolver nor its
Step-9.5 header gate consults ``spike_tooling_rounds`` at all — a
cap-exceeded fixture still routes to ``sub_skill == "spike"`` instead of
``terminal_reason == "needs-input"``, so the "at cap" / "above cap" Contract-C
assertions FAIL until WU-2 lands. The "below cap" / "absent" Contract-C cases
are regression guards — true both before and after the fix.

Run with: python3 user/scripts/test_spike_tooling_loop.py   (exit 0 on pass)
Also pytest-discoverable (every `test_*` function is a standalone test).
No third-party dependencies — stdlib only (PyYAML is already a hard
dependency of lazy_core / the state scripts, imported transitively).
"""

from __future__ import annotations

import importlib
import importlib.util
import json
import os
import re
import sys
import tempfile
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).parent

# ---------------------------------------------------------------------------
# lazy_core — imported directly (Contracts A + B), $HOME/repo-anchored via
# Path(__file__).parent, never a hardcoded absolute path.
# ---------------------------------------------------------------------------
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

_CORE_IMPORT_ERROR = None
lazy_core = None
try:
    lazy_core = importlib.import_module("lazy_core")
except Exception as exc:  # noqa: BLE001
    _CORE_IMPORT_ERROR = exc


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
# Import the hyphenated state-script modules under clean names (Contract C).
# ---------------------------------------------------------------------------
_IMPORT_ERROR = None
lazy_state = None
try:
    lazy_state = _load_hyphenated("lazy_state_for_tooling_loop_tests", "lazy-state.py")
except Exception as exc:  # noqa: BLE001
    _IMPORT_ERROR = exc

_BUG_IMPORT_ERROR = None
bug_state = None
try:
    bug_state = _load_hyphenated("bug_state_for_tooling_loop_tests", "bug-state.py")
except Exception as exc:  # noqa: BLE001
    _BUG_IMPORT_ERROR = exc


# ---------------------------------------------------------------------------
# Fixture builders — copied + extended from the sibling
# test_spike_state_routing.py (self-contained by directive; not imported).
# ---------------------------------------------------------------------------

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


def _spike_verdict_md(feature_id: str, verdict: str, spike_tooling_rounds: int | None = None) -> str:
    lines = [
        "---",
        "kind: spike-verdict",
        f"feature_id: {feature_id}",
        f"verdict: {verdict}",
    ]
    if spike_tooling_rounds is not None:
        lines.append(f"spike_tooling_rounds: {spike_tooling_rounds}")
    lines += ["---", "", "# Spike Verdict", ""]
    return "\n".join(lines)


def _build_fixture(
    tmpdir: Path,
    *,
    feature_id: str,
    spike_required: bool,
    spike_goal: str = "prove projector holds 30fps",
    verdict: str | None = None,
    spike_tooling_rounds: int | None = None,
) -> Path:
    """Build a minimal fixture repo that reaches the Step-9.5 seam.

    Extends the sibling's _build_fixture with an optional
    ``spike_tooling_rounds`` frontmatter line on SPIKE_VERDICT.md.
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
        (p / "SPIKE_VERDICT.md").write_text(
            _spike_verdict_md(feature_id, verdict, spike_tooling_rounds)
        )
    return root


def _blocked_md(
    feature_id: str,
    *,
    blocker_kind: str | None,
    phase: str = "MCP Validation",
    blocked_at: str = "2026-07-17T12:00:00Z",
    retry_count: int = 0,
    spike_tooling_rounds: int | None = None,
) -> str:
    """Canonical BLOCKED.md frontmatter (kind: blocked). Extends the
    sibling's _blocked_md with an optional spike_tooling_rounds line."""
    lines = ["---", "kind: blocked", f"feature_id: {feature_id}", f"phase: {phase}"]
    if blocker_kind is not None:
        lines.append(f"blocker_kind: {blocker_kind}")
    lines.append(f"blocked_at: {blocked_at}")
    lines.append(f"retry_count: {retry_count}")
    if spike_tooling_rounds is not None:
        lines.append(f"spike_tooling_rounds: {spike_tooling_rounds}")
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
    spike_tooling_rounds: int | None = None,
) -> Path:
    """Minimal fixture reaching the Step-3 BLOCKED.md check directly."""
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
        _blocked_md(feature_id, blocker_kind=blocker_kind,
                    spike_tooling_rounds=spike_tooling_rounds)
    )
    return root


def _compute(root: Path):
    """Call compute_state with an isolated LAZY_STATE_DIR (feature axis)."""
    with tempfile.TemporaryDirectory(prefix="spike-tooling-state-dir-") as sd:
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
# Bug-axis fixture builders — coupled mirror of the feature-axis builders
# above, driving bug-state.py::compute_state.
# ---------------------------------------------------------------------------

def _build_bug_spike_fixture(
    tmpdir: Path,
    *,
    bug_id: str,
    spike_required: bool,
    spike_goal: str = "prove projector holds 30fps",
    verdict: str | None = None,
    spike_tooling_rounds: int | None = None,
) -> Path:
    """Bug-axis mirror of _build_fixture, reaching the bug Step-9.5 seam."""
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
        kwargs = dict(bug_id=bug_id, verdict=verdict)
        if spike_tooling_rounds is not None:
            kwargs["spike_tooling_rounds"] = spike_tooling_rounds
        bug_state._write_yaml_sentinel(
            bdir / "SPIKE_VERDICT.md", "spike-verdict", **kwargs
        )
    return root


def _bug_blocked_md(
    bug_id: str,
    *,
    blocker_kind: str,
    phase: str = "Investigation",
    blocked_at: str = "2026-07-17T12:00:00Z",
    retry_count: int = 0,
    spike_tooling_rounds: int | None = None,
) -> str:
    """Hand-formatted BLOCKED.md for the bug axis (mirrors
    bug_state._write_yaml_blocked_sentinel's shape but adds an optional
    spike_tooling_rounds field the fixed-signature writer cannot carry)."""
    lines = [
        "---", "kind: blocked", f"feature_id: {bug_id}", f"phase: {phase}",
        f"blocker_kind: {blocker_kind}", f"blocked_at: {blocked_at}",
        f"retry_count: {retry_count}",
    ]
    if spike_tooling_rounds is not None:
        lines.append(f"spike_tooling_rounds: {spike_tooling_rounds}")
    lines += ["---", "", "# Blocked", ""]
    return "\n".join(lines)


def _build_bug_blocked_fixture(
    tmpdir: Path,
    *,
    bug_id: str,
    blocker_kind: str,
    spike_tooling_rounds: int | None = None,
) -> Path:
    """Bug-axis mirror of _build_blocked_fixture."""
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
    (bdir / "BLOCKED.md").write_text(
        _bug_blocked_md(bug_id, blocker_kind=blocker_kind,
                         spike_tooling_rounds=spike_tooling_rounds)
    )
    return root


def _compute_bug(root: Path):
    """Call bug_state.compute_state with an isolated LAZY_STATE_DIR."""
    with tempfile.TemporaryDirectory(prefix="spike-tooling-bug-state-dir-") as sd:
        prev = os.environ.get("LAZY_STATE_DIR")
        os.environ["LAZY_STATE_DIR"] = sd
        try:
            return bug_state.compute_state(root, cloud=False, real_device=True)
        finally:
            if prev is None:
                os.environ.pop("LAZY_STATE_DIR", None)
            else:
                os.environ["LAZY_STATE_DIR"] = prev


# ===========================================================================
# Import sanity
# ===========================================================================

def test_core_import_ok():
    assert _CORE_IMPORT_ERROR is None, f"lazy_core import failed: {_CORE_IMPORT_ERROR!r}"


def test_import_ok():
    assert _IMPORT_ERROR is None, f"lazy-state.py import failed: {_IMPORT_ERROR!r}"


def test_bug_import_ok():
    assert _BUG_IMPORT_ERROR is None, f"bug-state.py import failed: {_BUG_IMPORT_ERROR!r}"


# ===========================================================================
# Contract A — lazy_core.spike_tooling_cap_exceeded(meta, cap=None) -> bool
# ===========================================================================

def test_cap_exceeded_rounds_absent_false():
    assert lazy_core.spike_tooling_cap_exceeded({}) is False, (
        "spike_tooling_rounds absent must never exceed the cap — is "
        "lazy_core.spike_tooling_cap_exceeded unimplemented?"
    )


def test_cap_exceeded_empty_meta_false():
    assert lazy_core.spike_tooling_cap_exceeded({}) is False


def test_cap_exceeded_meta_none_false():
    assert lazy_core.spike_tooling_cap_exceeded(None) is False


def test_cap_exceeded_rounds_below_default_cap_false():
    assert lazy_core.spike_tooling_cap_exceeded({"spike_tooling_rounds": 2}) is False


def test_cap_exceeded_rounds_at_default_cap_true():
    assert lazy_core.spike_tooling_cap_exceeded({"spike_tooling_rounds": 3}) is True


def test_cap_exceeded_rounds_above_default_cap_true():
    assert lazy_core.spike_tooling_cap_exceeded({"spike_tooling_rounds": 4}) is True


def test_cap_exceeded_rounds_digit_string_coerced_true():
    assert lazy_core.spike_tooling_cap_exceeded({"spike_tooling_rounds": "3"}) is True


def test_cap_exceeded_rounds_bool_rejected_false():
    # bool is an int subclass in Python — YAML `true` must NOT coerce to 1,
    # exactly like lazy_core.spike_escalation's retry_count tolerance.
    assert lazy_core.spike_tooling_cap_exceeded({"spike_tooling_rounds": True}) is False


def test_cap_exceeded_rounds_malformed_string_false():
    assert lazy_core.spike_tooling_cap_exceeded({"spike_tooling_rounds": "not-a-number"}) is False


def test_cap_exceeded_custom_cap_below_false():
    assert lazy_core.spike_tooling_cap_exceeded({"spike_tooling_rounds": 3}, cap=5) is False


def test_cap_exceeded_custom_cap_at_true():
    assert lazy_core.spike_tooling_cap_exceeded({"spike_tooling_rounds": 5}, cap=5) is True


# ===========================================================================
# Contract B — lazy_core.write_spike_tooling_cap_needs_input(spec_dir,
#              item_name, rounds) -> None
# ===========================================================================

def test_write_spike_tooling_cap_needs_input_writes_valid_sentinel():
    with tempfile.TemporaryDirectory(prefix="spike-tooling-write-") as td:
        spec_dir = Path(td) / "feat-tcap-w1"
        spec_dir.mkdir()
        lazy_core.write_spike_tooling_cap_needs_input(spec_dir, "feat-tcap-w1", 3)

        needs_input = spec_dir / "NEEDS_INPUT.md"
        assert needs_input.exists(), (
            "expected NEEDS_INPUT.md to be written by "
            "write_spike_tooling_cap_needs_input"
        )
        meta = lazy_core.parse_sentinel(needs_input)
        assert meta is not None, "expected a parseable sentinel"
        assert meta.get("kind") == "needs-input", f"got kind={meta.get('kind')!r}"
        assert meta.get("feature_id") == "feat-tcap-w1", (
            f"got feature_id={meta.get('feature_id')!r}"
        )
        assert meta.get("written_by") == "spike", (
            "CRITICAL: written_by must be 'spike' — the Spike-FAIL carve-out "
            f"in provisional_eligibility keys on this exact value; got "
            f"{meta.get('written_by')!r}"
        )
        decisions = meta.get("decisions")
        assert isinstance(decisions, list) and len(decisions) >= 1, (
            f"expected a non-empty decisions list; got {decisions!r}"
        )
        joined = " ".join(str(d) for d in decisions)
        assert "tooling gap persists after" in joined, (
            f"expected the decisions text to mention 'tooling gap persists "
            f"after'; got {joined!r}"
        )
        assert "3" in joined, (
            f"expected the decisions text to mention the round count (3); "
            f"got {joined!r}"
        )
        date_val = str(meta.get("date", ""))
        assert re.match(r"^\d{4}-\d{2}-\d{2}$", date_val), (
            f"expected a YYYY-MM-DD date; got {date_val!r}"
        )


def test_write_spike_tooling_cap_needs_input_body_has_decision_context():
    with tempfile.TemporaryDirectory(prefix="spike-tooling-write-") as td:
        spec_dir = Path(td) / "feat-tcap-w2"
        spec_dir.mkdir()
        lazy_core.write_spike_tooling_cap_needs_input(spec_dir, "feat-tcap-w2", 4)
        text = (spec_dir / "NEEDS_INPUT.md").read_text(encoding="utf-8")
        assert re.search(r"^## Decision Context\s*$", text, re.MULTILINE), (
            "expected a '## Decision Context' H2 in the sentinel body per "
            "sentinel-frontmatter.md's Rich Body Convention"
        )


def test_write_spike_tooling_cap_needs_input_idempotent_overwrite():
    with tempfile.TemporaryDirectory(prefix="spike-tooling-write-") as td:
        spec_dir = Path(td) / "feat-tcap-w3"
        spec_dir.mkdir()
        lazy_core.write_spike_tooling_cap_needs_input(spec_dir, "feat-tcap-w3", 3)
        lazy_core.write_spike_tooling_cap_needs_input(spec_dir, "feat-tcap-w3", 5)
        meta = lazy_core.parse_sentinel(spec_dir / "NEEDS_INPUT.md")
        joined = " ".join(str(d) for d in (meta.get("decisions") or []))
        assert "5" in joined, (
            f"expected the second (overwriting) call's round count (5) to "
            f"win; got decisions={joined!r}"
        )


def test_write_spike_tooling_cap_needs_input_never_provisionally_eligible():
    """Proves the cap-halt is never auto-accepted under park-provisional —
    the Spike-FAIL carve-out at lazy_core.docmodel.provisional_eligibility
    refuses any NEEDS_INPUT.md with written_by: spike."""
    with tempfile.TemporaryDirectory(prefix="spike-tooling-write-") as td:
        spec_dir = Path(td) / "feat-tcap-w4"
        spec_dir.mkdir()
        lazy_core.write_spike_tooling_cap_needs_input(spec_dir, "feat-tcap-w4", 3)
        result = lazy_core.provisional_eligibility(spec_dir / "NEEDS_INPUT.md")
        assert isinstance(result, tuple) and len(result) == 2, (
            f"expected a (eligible, reason) tuple; got {result!r}"
        )
        eligible, reason = result
        assert eligible is False, (
            "expected the Spike-FAIL carve-out (written_by: spike) to refuse "
            f"provisional eligibility for the cap-halt sentinel; got "
            f"eligible={eligible!r} reason={reason!r}"
        )


# ===========================================================================
# Contract C — routing wiring, feature axis (lazy-state.py::compute_state)
# ===========================================================================

# --- Blocked-resolver seam (Step 3) ----------------------------------------

def test_blocked_spike_tooling_rounds_at_cap_routes_needs_input():
    with tempfile.TemporaryDirectory(prefix="spike-tooling-blocked-") as td:
        root = _build_blocked_fixture(
            Path(td), feature_id="feat-tcap-b1",
            blocker_kind="runtime-spike-verdict-pending",
            spike_tooling_rounds=3,
        )
        result = _compute(root)
        assert result.get("terminal_reason") == "needs-input", (
            "expected the cap-halt to route to terminal_reason='needs-input' "
            "at spike_tooling_rounds=3 (at the default cap) — the WU-2 "
            f"blocked-resolver cap gate looks unimplemented; got {result!r}"
        )
        assert result.get("sub_skill") != "spike", (
            f"a cap-exceeded blocked resolver must NOT route to spike; got {result!r}"
        )


def test_blocked_spike_tooling_rounds_above_cap_routes_needs_input():
    with tempfile.TemporaryDirectory(prefix="spike-tooling-blocked-") as td:
        root = _build_blocked_fixture(
            Path(td), feature_id="feat-tcap-b2",
            blocker_kind="runtime-spike-verdict-pending",
            spike_tooling_rounds=4,
        )
        result = _compute(root)
        assert result.get("terminal_reason") == "needs-input", (
            f"expected needs-input at spike_tooling_rounds=4 (above cap); got {result!r}"
        )
        assert result.get("sub_skill") != "spike"


def test_blocked_spike_tooling_rounds_below_cap_still_routes_spike():
    """Regression guard: below-cap rounds must keep today's behavior."""
    with tempfile.TemporaryDirectory(prefix="spike-tooling-blocked-") as td:
        root = _build_blocked_fixture(
            Path(td), feature_id="feat-tcap-b3",
            blocker_kind="runtime-spike-verdict-pending",
            spike_tooling_rounds=2,
        )
        result = _compute(root)
        assert result.get("sub_skill") == "spike", (
            f"below-cap spike_tooling_rounds=2 must still route to spike; got {result!r}"
        )
        assert result.get("terminal_reason") is None, (
            f"the spike blocked-resolver route must stay NON-terminal below "
            f"the cap; got terminal_reason={result.get('terminal_reason')!r}"
        )


def test_blocked_spike_tooling_rounds_absent_still_routes_spike():
    """Regression guard: no spike_tooling_rounds field at all → today's
    behavior (unconditional route to spike, byte-identical to before WU-2)."""
    with tempfile.TemporaryDirectory(prefix="spike-tooling-blocked-") as td:
        root = _build_blocked_fixture(
            Path(td), feature_id="feat-tcap-b4",
            blocker_kind="runtime-spike-verdict-pending",
            spike_tooling_rounds=None,
        )
        result = _compute(root)
        assert result.get("sub_skill") == "spike", (
            f"no spike_tooling_rounds field must still route to spike; got {result!r}"
        )


# --- Step-9.5 header-gate seam ----------------------------------------------

def test_step95_spike_tooling_rounds_at_cap_routes_needs_input():
    with tempfile.TemporaryDirectory(prefix="spike-tooling-fixture-") as td:
        root = _build_fixture(
            Path(td), feature_id="feat-tcap-s1", spike_required=True,
            verdict="PENDING", spike_tooling_rounds=3,
        )
        result = _compute(root)
        assert result.get("terminal_reason") == "needs-input", (
            "expected the Step-9.5 cap-halt to route to "
            "terminal_reason='needs-input' at spike_tooling_rounds=3 — the "
            f"WU-2 header-gate cap check looks unimplemented; got {result!r}"
        )
        assert result.get("sub_skill") != "spike", (
            f"a cap-exceeded Step-9.5 gate must NOT route to spike; got {result!r}"
        )


def test_step95_spike_tooling_rounds_below_cap_still_routes_spike():
    """Regression guard: below-cap rounds must keep today's behavior (a
    non-PASS verdict routes to spike regardless of round count, below cap)."""
    with tempfile.TemporaryDirectory(prefix="spike-tooling-fixture-") as td:
        root = _build_fixture(
            Path(td), feature_id="feat-tcap-s2", spike_required=True,
            verdict="PENDING", spike_tooling_rounds=2,
        )
        result = _compute(root)
        assert result.get("sub_skill") == "spike", (
            f"below-cap spike_tooling_rounds=2 must still route to spike; got {result!r}"
        )


def test_step95_spike_tooling_rounds_absent_still_routes_spike():
    """Regression guard: a PENDING verdict with no spike_tooling_rounds field
    at all must still route to spike (byte-identical to before WU-2)."""
    with tempfile.TemporaryDirectory(prefix="spike-tooling-fixture-") as td:
        root = _build_fixture(
            Path(td), feature_id="feat-tcap-s3", spike_required=True,
            verdict="PENDING", spike_tooling_rounds=None,
        )
        result = _compute(root)
        assert result.get("sub_skill") == "spike", (
            f"no spike_tooling_rounds field must still route to spike; got {result!r}"
        )


# ===========================================================================
# Contract C — routing wiring, bug axis (bug-state.py::compute_state)
# Same assertions as the feature axis above — the coupled-pair body-parity
# guard for this feature.
# ===========================================================================

# --- Blocked-resolver seam (Step 3) ----------------------------------------

def test_bug_blocked_spike_tooling_rounds_at_cap_routes_needs_input():
    with tempfile.TemporaryDirectory(prefix="spike-tooling-bug-blocked-") as td:
        root = _build_bug_blocked_fixture(
            Path(td), bug_id="bug-tcap-b1",
            blocker_kind="runtime-spike-verdict-pending",
            spike_tooling_rounds=3,
        )
        result = _compute_bug(root)
        assert result.get("terminal_reason") == "needs-input", (
            "bug-axis mirror: expected the cap-halt to route to "
            "terminal_reason='needs-input' at spike_tooling_rounds=3 — the "
            f"WU-2 bug-state.py blocked-resolver cap gate looks "
            f"unimplemented; got {result!r}"
        )
        assert result.get("sub_skill") != "spike", (
            f"a cap-exceeded blocked resolver must NOT route to spike; got {result!r}"
        )


def test_bug_blocked_spike_tooling_rounds_below_cap_still_routes_spike():
    """Regression guard, bug axis."""
    with tempfile.TemporaryDirectory(prefix="spike-tooling-bug-blocked-") as td:
        root = _build_bug_blocked_fixture(
            Path(td), bug_id="bug-tcap-b2",
            blocker_kind="runtime-spike-verdict-pending",
            spike_tooling_rounds=2,
        )
        result = _compute_bug(root)
        assert result.get("sub_skill") == "spike", (
            f"below-cap spike_tooling_rounds=2 must still route to spike; got {result!r}"
        )
        assert result.get("terminal_reason") is None, (
            f"the spike blocked-resolver route must stay NON-terminal below "
            f"the cap; got terminal_reason={result.get('terminal_reason')!r}"
        )


def test_bug_blocked_spike_tooling_rounds_absent_still_routes_spike():
    """Regression guard, bug axis: no field at all → today's behavior."""
    with tempfile.TemporaryDirectory(prefix="spike-tooling-bug-blocked-") as td:
        root = _build_bug_blocked_fixture(
            Path(td), bug_id="bug-tcap-b3",
            blocker_kind="runtime-spike-verdict-pending",
            spike_tooling_rounds=None,
        )
        result = _compute_bug(root)
        assert result.get("sub_skill") == "spike", (
            f"no spike_tooling_rounds field must still route to spike; got {result!r}"
        )


# --- Step-9.5 header-gate seam ----------------------------------------------

def test_bug_step95_spike_tooling_rounds_at_cap_routes_needs_input():
    with tempfile.TemporaryDirectory(prefix="spike-tooling-bug-fixture-") as td:
        root = _build_bug_spike_fixture(
            Path(td), bug_id="bug-tcap-s1", spike_required=True,
            verdict="PENDING", spike_tooling_rounds=3,
        )
        result = _compute_bug(root)
        assert result.get("terminal_reason") == "needs-input", (
            "bug-axis mirror: expected the Step-9.5 cap-halt to route to "
            "terminal_reason='needs-input' at spike_tooling_rounds=3 — the "
            f"WU-2 bug-state.py header-gate cap check looks unimplemented; "
            f"got {result!r}"
        )
        assert result.get("sub_skill") != "spike", (
            f"a cap-exceeded Step-9.5 gate must NOT route to spike; got {result!r}"
        )


def test_bug_step95_spike_tooling_rounds_below_cap_still_routes_spike():
    """Regression guard, bug axis."""
    with tempfile.TemporaryDirectory(prefix="spike-tooling-bug-fixture-") as td:
        root = _build_bug_spike_fixture(
            Path(td), bug_id="bug-tcap-s2", spike_required=True,
            verdict="PENDING", spike_tooling_rounds=2,
        )
        result = _compute_bug(root)
        assert result.get("sub_skill") == "spike", (
            f"below-cap spike_tooling_rounds=2 must still route to spike; got {result!r}"
        )


def test_bug_step95_spike_tooling_rounds_absent_still_routes_spike():
    """Regression guard, bug axis: no field at all → today's behavior."""
    with tempfile.TemporaryDirectory(prefix="spike-tooling-bug-fixture-") as td:
        root = _build_bug_spike_fixture(
            Path(td), bug_id="bug-tcap-s3", spike_required=True,
            verdict="PENDING", spike_tooling_rounds=None,
        )
        result = _compute_bug(root)
        assert result.get("sub_skill") == "spike", (
            f"no spike_tooling_rounds field must still route to spike; got {result!r}"
        )


if __name__ == "__main__":
    import traceback

    tests = [
        test_core_import_ok,
        test_import_ok,
        test_bug_import_ok,
        # Contract A
        test_cap_exceeded_rounds_absent_false,
        test_cap_exceeded_empty_meta_false,
        test_cap_exceeded_meta_none_false,
        test_cap_exceeded_rounds_below_default_cap_false,
        test_cap_exceeded_rounds_at_default_cap_true,
        test_cap_exceeded_rounds_above_default_cap_true,
        test_cap_exceeded_rounds_digit_string_coerced_true,
        test_cap_exceeded_rounds_bool_rejected_false,
        test_cap_exceeded_rounds_malformed_string_false,
        test_cap_exceeded_custom_cap_below_false,
        test_cap_exceeded_custom_cap_at_true,
        # Contract B
        test_write_spike_tooling_cap_needs_input_writes_valid_sentinel,
        test_write_spike_tooling_cap_needs_input_body_has_decision_context,
        test_write_spike_tooling_cap_needs_input_idempotent_overwrite,
        test_write_spike_tooling_cap_needs_input_never_provisionally_eligible,
        # Contract C — feature axis
        test_blocked_spike_tooling_rounds_at_cap_routes_needs_input,
        test_blocked_spike_tooling_rounds_above_cap_routes_needs_input,
        test_blocked_spike_tooling_rounds_below_cap_still_routes_spike,
        test_blocked_spike_tooling_rounds_absent_still_routes_spike,
        test_step95_spike_tooling_rounds_at_cap_routes_needs_input,
        test_step95_spike_tooling_rounds_below_cap_still_routes_spike,
        test_step95_spike_tooling_rounds_absent_still_routes_spike,
        # Contract C — bug axis
        test_bug_blocked_spike_tooling_rounds_at_cap_routes_needs_input,
        test_bug_blocked_spike_tooling_rounds_below_cap_still_routes_spike,
        test_bug_blocked_spike_tooling_rounds_absent_still_routes_spike,
        test_bug_step95_spike_tooling_rounds_at_cap_routes_needs_input,
        test_bug_step95_spike_tooling_rounds_below_cap_still_routes_spike,
        test_bug_step95_spike_tooling_rounds_absent_still_routes_spike,
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
