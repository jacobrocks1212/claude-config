# Research Summary — Cycle-Prompt Deflation

**Skip-research path (operator-directed, 2026-07-19).** No external deep-research pass; the
feature is internal harness plumbing grounded in the claude-config codebase. This summary exists
to satisfy the Step 5 research gate and unblock PHASES decomposition (`/plan-feature`).

## Key grounding (all in-repo)

- **Assembly surface:** `emit_cycle_prompt` + the `@section` grammar in `lazy_core/dispatch.py`
  own the cycle-prompt assembly this feature deflates. Edits target its OUTPUT, never fork the
  emitter (per the `mechanize-prose-only-orchestrator-contracts` soft dep).
- **Measured target:** ~16.8 KB assembled-field ceiling; ~13–14 KB boilerplate. Working target
  ~9–10 KB assembled; achievable floor is decided per-section in Phase 3 with evidence
  (conservative default: trim-only, no selector change, for any section whose exclusion safety is
  uncertain).
- **Playbook reuse:** extends `lazy-batch-skill-deflation`'s prose→verdict-rule deflation and its
  `skill-size-ratchet.py` gate from whole-file skills to the assembled cycle prompt.
- **Coupling constraint:** `cycle-base-prompt.md` is mirrored into bug/cloud SKILL variants via
  `generate-coupled-skills.py` + overlays (hard dep `coupled-pair-generation`); every section edit
  must flow through that machinery or break coupled-pair parity. Preserve the
  `cycle-prompt-environment-dialect` `@section env-dialect-*` boundaries + selection attributes.

## Decisions deferred to PHASES/planning

- The exact assembled-KB floor (ratchet locks whatever Phase 3 achieves, no upfront number).
- Which `skills=all` sections are provably safe to narrow (decided per-section in Phase 3 with
  evidence).
