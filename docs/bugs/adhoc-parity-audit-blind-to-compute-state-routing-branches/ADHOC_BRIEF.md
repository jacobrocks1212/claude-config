---
kind: adhoc-brief
bug_id: adhoc-parity-audit-blind-to-compute-state-routing-branches
enqueued_by: lazy-adhoc
date: 2026-07-18
---

# Ad-hoc bug: Parity audit misses compute_state routing-branch asymmetry between the state scripts

Recurred class (Rounds 92 + 93 this run): a lazy-state.py compute_state routing fix ships without its bug-state.py mirror - Round 92's research-pending exclusion was flag-gated feature-only, Round 93's Step-7 verification-only bypass kept an over-narrow conjunct the feature side had dropped in 2026-06-15, despite a comment claiming to mirror it. lazy_parity_audit.py audits skill-prose headings via the parity manifest but is blind to compute_state ROUTING-BRANCH symmetry in the scripts themselves. Fix shape per Round 93's operator finding: extend lazy_parity_audit.py (or a sibling check) to assert routing-branch symmetry across the coupled compute_state implementations - e.g. a per-branch structural census (bypass predicates, exclude-set members, step-routing conjuncts) diffed between the two scripts with tabulated deliberate divergences, so an unmirrored routing fix fails the audit instead of surfacing as a live run stall weeks later.
