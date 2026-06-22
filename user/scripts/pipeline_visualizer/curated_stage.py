"""curated_stage — the static display-mapping rollup.

Pure function mirroring the SPEC "Curated-node rollup (display mapping)" table.
Maps each literal `current_step` / `terminal_reason` emitted by lazy-state.py /
bug-state.py to ONE curated node:

    Pending | Spec | Research | Plan | Implement | Validate | Complete
    Blocked | Needs-input | Deferred   (side-states)

This module does NOT shell or re-infer anything. The state scripts remain the
single source of truth; this is a display concern only.

Mapping authority (verified against source 2026-06-15):
  - lazy-state.py current_step literals (feature track)
  - bug-state.py STEP_* constants (bug track — omits Research)
  - shared terminal_reason values (side-states)
"""

from __future__ import annotations

from typing import Optional

# --- Side-state rollup (terminal_reason → curated node). Shared feature/bug. ---
# terminal_reason DOMINATES: a side-state terminal wins over any workflow step.
_SIDE_STATE_BY_TERMINAL = {
    "blocked": "Blocked",
    "needs-input": "Needs-input",
    "needs-research": "Needs-input",
    "needs-spec-input": "Needs-input",
    "cloud-queue-exhausted": "Deferred",
    "device-queue-exhausted": "Deferred",
    # Deferred rollup (bug-state-scoped-query-loses-deferred-bug-identity P3).
    # The global unscoped bug deferral terminal — fixes the rollup even on the
    # UNSCOPED display path that the original symptom exercised.
    "all-remaining-deferred": "Deferred",
    # Host-capability axis (the host-axis mirror of device-queue-exhausted).
    "host-capability-saturated": "Deferred",
    # Scoped per-bug / per-feature deferred terminals introduced in Parts 1 & 2
    # (literals matched VERBATIM to the TR_* constants in bug-state.py /
    # lazy-state.py). operator-deferred is bug-side only; cloud/device scoped
    # are shared; host-capability scoped is feature-side only.
    "operator-deferred": "Deferred",
    "cloud-queue-exhausted-scoped": "Deferred",
    "device-queue-exhausted-scoped": "Deferred",
    "host-capability-saturated-scoped": "Deferred",
    # Scoped PARK terminals — a parked match is in a blocked / needs-input
    # side-state, NOT a deferred one.
    "blocked-scoped": "Blocked",
    "needs-input-scoped": "Needs-input",
}

# --- Workflow rollup: literal current_step → curated node. ---
# Feature track (lazy-state.py current_step literals).
_FEATURE_STEP_TO_STAGE = {
    # Spec
    "Step 4: no SPEC, no research": "Spec",
    "Step 4: ad-hoc brief → spec": "Spec",
    "Step 4: SPEC missing, research files present": "Spec",
    "Step 4.5: stub-spec detected": "Spec",
    "Step 4.6: upstream realign needed": "Spec",
    # Research (feature-only)
    "Step 5: generate research prompt": "Research",
    "Step 5: prompt exists, awaiting research": "Research",
    "Step 5: integrate research": "Research",
    "Step 5: needs-research (persistent)": "Research",
    # Plan
    "Step 6: plan feature (phases + plan)": "Plan",
    "Step 7a: write plan": "Plan",
    # Implement
    "Step 7a: execute plan": "Implement",
    "Step 7a: flip plan Complete (cloud-saturated)": "Implement",
    "Step 7a: flip plan Complete (stale — all referenced implementation deliverables already checked)": "Implement",
    # Validate
    "Step 9: run MCP tests": "Validate",
    "Step 9b: write validated": "Validate",
    "Step 9: skip-mcp-test → validated": "Validate",
    "Step 9: stale MCP results — re-verify": "Validate",
    "Step 9: cloud defers MCP test": "Validate",
    "Step 9: device-deferred (no real device on this host)": "Validate",
    "Step 9: re-open device-deferred scenarios (real-device host)": "Validate",
    "Step 9: pipeline-granted skip needs operator confirmation": "Validate",
    # Complete
    "Step 10: mark complete": "Complete",
}

# Bug track (bug-state.py STEP_* constants). Bug pipeline omits Research.
_BUG_STEP_TO_STAGE = {
    # Spec (investigation is the bug-track spec equivalent)
    "Step 4: investigate bug": "Spec",
    # Plan
    "Step 6: spec phases": "Plan",
    "Step 7a: write plan": "Plan",
    # Implement
    "Step 7a: execute plan": "Implement",
    # Validate
    "Step 9: run MCP tests": "Validate",
    "Step 9b: write validated": "Validate",
    "Step 9: skip-mcp-test → validated": "Validate",
    "Step 9: stale MCP results — re-verify": "Validate",
    "Step 9: cloud defers MCP test": "Validate",
    "Step 9: device-deferred (no real device on this host)": "Validate",
    "Step 9: re-open device-deferred scenarios (real-device host)": "Validate",
    "Step 9: pipeline-granted skip needs operator confirmation": "Validate",
    # Complete (bug terminal is archive-on-fix)
    "Step 10: mark fixed": "Complete",
}

# Prefix-based fallback for workflow steps not enumerated above. Keeps the rollup
# resilient to new step-name variants within a known phase WITHOUT collapsing an
# unknown step onto Spec (an unknown step → Pending, per the SPEC default).
# Prefixes are colon/dot-anchored to a specific phase so an unknown step like
# "Step 99: ..." does NOT match the "Step 9" phase (it falls through to Pending).
_FEATURE_PREFIX_RULES = (
    ("Step 4.5", "Spec"),
    ("Step 4.6", "Spec"),
    ("Step 4:", "Spec"),
    ("Step 5:", "Research"),
    ("Step 6:", "Plan"),
    ("Step 7a: write plan", "Plan"),
    ("Step 7a: execute plan", "Implement"),
    ("Step 7a: flip plan", "Implement"),
    ("Step 9:", "Validate"),
    ("Step 9b", "Validate"),
    ("Step 10: mark", "Complete"),
)

_BUG_PREFIX_RULES = (
    ("Step 4:", "Spec"),
    ("Step 6:", "Plan"),
    ("Step 7a: write plan", "Plan"),
    ("Step 7a: execute plan", "Implement"),
    ("Step 9:", "Validate"),
    ("Step 9b", "Validate"),
    ("Step 10: mark", "Complete"),
)

DEFAULT_STAGE = "Pending"


def curated_stage(
    current_step: Optional[str],
    terminal_reason: Optional[str],
    pipeline: str = "feature",
) -> str:
    """Roll a literal (current_step, terminal_reason) up to a curated node.

    Args:
        current_step: the script's `current_step` literal (may be None/"").
        terminal_reason: the script's `terminal_reason` literal (may be None).
        pipeline: "feature" or "bug" — selects the per-track table.

    Returns one of:
        Pending | Spec | Research | Plan | Implement | Validate | Complete
        Blocked | Needs-input | Deferred

    Rules:
      1. A side-state `terminal_reason` (blocked/needs-*/deferral) DOMINATES.
      2. Otherwise the literal `current_step` maps via the per-pipeline table,
         then a prefix fallback for unenumerated in-phase variants.
      3. An unknown / None / empty step falls back to Pending (the dedicated
         entry node) — NEVER Spec. Queued-but-unstarted items live on Pending
         and animate into Spec only once /spec runs.
    """
    # Rule 1: side-state terminal_reason dominates.
    if terminal_reason:
        side = _SIDE_STATE_BY_TERMINAL.get(terminal_reason)
        if side is not None:
            return side

    if not current_step:
        return DEFAULT_STAGE

    table = _BUG_STEP_TO_STAGE if pipeline == "bug" else _FEATURE_STEP_TO_STAGE
    if current_step in table:
        return table[current_step]

    # Rule 2: prefix fallback for in-phase variants not exactly enumerated.
    prefix_rules = _BUG_PREFIX_RULES if pipeline == "bug" else _FEATURE_PREFIX_RULES
    for prefix, stage in prefix_rules:
        if current_step.startswith(prefix):
            return stage

    # Rule 3: unknown step → Pending.
    return DEFAULT_STAGE
