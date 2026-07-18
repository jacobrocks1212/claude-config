---
kind: implemented
feature_id: merged-head-actionability-oracle
date: 2026-07-18
provenance: pipeline-gated
derivation: commit-brackets
commits: [d473691, a4a9c1a, ac389f6, f8bc122, c051f03, 9d4be13, 68eeb7e, ff7873e, b37f40f]
decisions: [L1, L2, L3, L4, L5, L6, L7]
---

# Implementation Ledger

**What shipped:** Replace the ever-growing category-enumerated merged-head exclude set with a single per-item "would `compute_state` dispatch this item right now?" oracle, so the NEXT non-dispatchable category cannot re-introduce a merged-head-diverged stall.

**Decisions that drove it:**
- L1 — Replace the category-enumerated `nondispatchable_item_ids` file-predicate (five facets + an in-code-admitted incomplete "Scope boundary") with the authoritative per-item actionability oracle it approximates — the scoped `compute_state` dispatch decision. This ends the recurring `merged-head-diverged-withholds-on-<X>` class by construction.
- L2 — Same-pipeline exclude source stays `probe_skipped_ids(state, same_pipeline_items)` — NOT replaced by the oracle. It carries cross-item skip-ahead *ordering* context (two-key readiness predicate, `--strict-research-halt`, fully-gated terminal) a per-item oracle would lose. The oracle applies ONLY to the cross-pipeline queue the current probe never walked.
- L3 — `is_dispatchable(scoped_state)` is a small closed predicate: dispatchable iff `sub_skill` is a non-empty, non-`__`-prefixed real skill AND `terminal_reason` is not a skip/defer/park/gate/halt reason. A `needs-research` head (without `--skip-needs-research`) classifies non-dispatchable and is excluded here; `research_halt_head` RE-INCLUDES it so the operator still sees the needs-research halt (byte-identity invariant).
- L4 — *(Open — not locked; see Open Question 1.)* In-process scoped `compute_state` with module-global snapshot/restore is PREFERRED over subprocess spawn, but isolation robustness is resolved in `/spec-phases` Phase 1; subprocess (`--bug-id` / `--feature-id`) is the documented fallback.
- L5 — Bound the oracle to candidates ranked at-or-above the emitted item in the merged ordering, short-circuiting at the first dispatchable head — a lower-priority item can never be the diverging merged head, so it never needs an oracle evaluation.
- L6 — Coupled-pair: the merged marker is shared across `lazy-state.py` / `bug-state.py`; the three exclude-set construction sites (`--emit-prompt` merged override, `--next-merged`, `research_halt`) must be mirrored and `lazy_parity_audit.py --repo-root .` kept exit 0.
- L7 — `nondispatchable_item_ids` is retired from the merged-head path once all three consumers migrate; it is deleted outright only if no non-merged consumer survives (confirm via usage grep, Open Question 2). The retiring change carries a `retires:` declaration for the anti-overfit complexity check.

**Validated via: mcp. Receipt: COMPLETED.md (provenance: gated).**
