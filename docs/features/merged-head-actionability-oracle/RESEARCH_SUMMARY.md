---
kind: research-summary
feature_id: merged-head-actionability-oracle
provenance: operator-waived
date: 2026-07-18
---

# Research Summary — Merged-head actionability oracle

## Provenance

Deep (Gemini) external research was **explicitly waived by the operator** on 2026-07-18 during the
overnight `/lazy-batch-parallel` wind-down ("mark the NEEDS RESEARCH work such that research is not
required (operator approved skip research)"). This is an internal harness routing change with rich
in-repo prior art and no external-source question gating the baseline, so the waiver is sound. This
summary is authored from the existing SPEC.md, the `RESEARCH_PROMPT.md` question inventory (used as
a design checklist, not an answered survey), and verified in-repo evidence.

## Key findings relevant to the baseline

- **The recurring class is real and enumerated in-code as inherently incomplete.** Five facet bugs
  (parked, operator-deferred, device-deferred, dep-unready, research-skipped) each hand-added one
  category to `nondispatchable_item_ids`, and the helper's own "Scope boundary" docstring names
  cloud-deferral, `completion-unverified`, `stale_upstream`, and `needs-ratification` as categories
  a pure file-predicate *cannot* classify — explicitly deferring them to "the scoped `compute_state`
  dispatch oracle." This feature is that named generalization; the premise is grounded, not
  speculative.
- **The authoritative decision already exists per-item.** `compute_state` answers "would this item
  dispatch?" via the existing `--feature-id` / `--bug-id` single-item scoping (concurrency-plane
  flag). Replacing the file-predicate approximation with the decision it approximates collapses all
  five (and every future) facet into one oracle — byte-identical for dispatchable heads *by
  construction* (the oracle IS the dispatch decision the withhold already trusts).
- **Same-pipeline skips must NOT be replaced.** `probe_skipped_ids` carries cross-item skip-ahead
  *ordering* context (two-key readiness predicate, `--strict-research-halt`, fully-gated terminal)
  that a per-item oracle would lose. The correct shape is a hybrid: keep `probe_skipped_ids` for the
  same-pipeline queue, apply the oracle only to the cross-pipeline queue the current probe never
  walked. This is captured as Locked Decision L2.

## Ideas adopted from prior art (in-repo)

- **In-process scoped probe with global snapshot/restore** over subprocess spawn (cheaper; no
  interpreter start) — but only if in-process isolation of `compute_state`'s module-level
  accumulators (`_SKIP_AHEAD_BLOCKED`, `_GATED_HEADS`, `_DIAGNOSTICS`, `_DEP_GATED`) proves robust;
  subprocess (`bug-state.py --bug-id`) is the documented fallback. Left as Open Question 1 →
  resolve in `/spec-phases` Phase 1, NOT locked (see L4 note).
- **Derive the `is_dispatchable` non-dispatch `terminal_reason` set exhaustively from
  `compute_state`'s terminal vocabulary** rather than hand-listing — avoids re-introducing the very
  drift-prone enumeration this feature eliminates (Open Question 3).

## Pitfalls / concerns to address in phases

- **In-process cross-probe corruption** is the primary implementation risk: the oracle runs N scoped
  `compute_state` calls AFTER the primary emit probe's `state` is captured; each call resets and
  mutates module globals. The oracle must snapshot/restore (or read only the returned dict, never the
  globals) so the primary `state` is not corrupted. Covered by the "No cross-probe corruption"
  Validation Criteria row.
- **Coupled-pair parity:** the merged marker is shared across `lazy-state.py` / `bug-state.py`; the
  three exclude-set construction sites must be mirrored and `lazy_parity_audit.py` kept green (L6).
- **Research-surface preservation:** a `needs-research` head classifies non-dispatchable (it halts)
  and is excluded here, but `research_halt_head` must RE-INCLUDE it exactly as today so the operator
  still sees the needs-research halt — a byte-identity invariant, not a behavior change (L3 tail).

## Baseline decisions revisited

None reversed. Research waiver + in-repo evidence confirm the baseline SPEC as drafted. The only
finalization change is documentation self-consistency: the inline `Locked Decision L2..L7`
references are consolidated into a canonical `## Locked Decisions` section (they were described
inline but never defined in one parseable surface). No design decision changed.
