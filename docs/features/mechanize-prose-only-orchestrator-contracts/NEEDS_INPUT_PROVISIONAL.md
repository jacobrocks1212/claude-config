---
kind: needs-input
feature_id: mechanize-prose-only-orchestrator-contracts
written_by: spec
decisions:
  - D1 — guard-side model-tier pinning: rewrite-in-place vs deny-on-mismatch
date: 2026-07-13
next_skill: none
class: product
divergence: isolated
audit_divergence: isolated
---

# mechanize-prose-only-orchestrator-contracts — Needs Input

D2/D3/D4/D5 are `mechanical-internal` and are auto-accepted per their SPEC `**Recommendation:**`
lines — see `RESEARCH_SUMMARY.md` "Locked decisions". D1 is the SPEC's own explicitly-flagged
`product-behavior (open — recommendation below)` decision, gating full ratification.

## Decision Context

### 1. D1 — Guard-side model-tier pinning: rewrite vs deny

**Problem:** When a registered Agent dispatch reaches the validate-deny guard with a `model:` field
that differs from (or omits) the script-selected tier, should the guard silently correct it in
place, or deny the dispatch and force a re-probe/re-dispatch cycle?

**Options:**
- **A — pin-by-rewrite (Recommended):** `register_emission` gains a `model` field; every guard
  ALLOW path (fresh-consumption, F2a by-reference, idempotent re-fire, F1b auto-readmit) that
  already supports `updatedInput` corrects `model` to the registered tier in place, noting the
  rewrite in `permissionDecisionReason`. Zero new deny/retry loops; heals the observed 41%
  post-compaction model-drop incident instead of punishing it. An orchestrator that intended a
  different model is silently overridden — acceptable, since model selection is script-owned by
  contract.
- **B — deny on mismatch:** stricter, but converts a transcription slip into a
  deny→re-probe→re-dispatch cycle (~1 wasted meta-turn each); reserves the guard's deny vocabulary
  for a case (an omitted field) that isn't really an unregistered/stale prompt.

**Recommendation:** A — the guard already replaces the entire `tool_input` dict via `updatedInput`
on several ALLOW paths; pinning `model` is a one-field addition to an existing mechanism, matching
the field's script-owned nature (like `queue.json` deps).

## Resolution

resolved_by: auto-provisional
decision_commit: (recorded at the commit that lands this NEEDS_INPUT_PROVISIONAL.md)

**Provisionally accepted** under the operator's overnight park-provisional blanket directive
(this session, 2026-07-13). Option A is adopted and has been IMPLEMENTED against — `register_emission`
carries `model`, and all four guard ALLOW paths in `lazy_guard.py` (`_pinned_model_update`, wired
into the fresh-consumption path, the F2a by-reference path, the idempotent re-fire path, and
`_try_auto_readmit`) correct a mismatched/missing `model:` field in place, with the
`permissionDecisionReason` noting the rewrite (`"model pinned: 'opus'→'haiku'"`). A registry entry
with no `model` field (legacy/pre-migration) fails open — no pin, no error. Full hermetic test
coverage: `test_guard_pins_model_on_fresh_allow` (mismatch / missing / already-correct /
legacy-fail-open) and `test_guard_pins_model_on_by_reference_and_auto_readmit_allows` in
`user/scripts/test_lazy_core.py`.

SPEC.md's Status stays **Draft** and NO `COMPLETED.md` is written — completion is mechanically
blocked while this unratified `NEEDS_INPUT_PROVISIONAL.md` exists. The operator ratifies or
redirects this choice (rewrite vs deny) before the feature can complete.

**Divergence graded `isolated`** — the choice affects only WHETHER a model-tier drift is silently
corrected vs denied; it does not change which tier is selected, any gate, terminal route, or any
other guard behavior. A later redirect to option B touches only the four ALLOW-path pin sites
(replace the `updatedInput` correction with a deny call), not the tier-selection logic
(`emit_cycle_prompt`/`emit_dispatch_prompt`) or the `model` field's presence on the registry schema
— the two-key eligibility predicate (`divergence` + `audit_divergence` both `isolated`) is
satisfied, consistent with the low-risk shape `park-provisional-acceptance` is designed for.

**Choice:** A — pin-by-rewrite, implemented and tested; awaiting operator ratification.
