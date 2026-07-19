---
kind: fixed
feature_id: park-provisional-parks-claude-config-auto-generated-stubs
date: 2026-07-19
provenance: backfilled-unverified
validated_via: pytest tests/test_lazy_core/ (1300 passed, incl. 4 new provisional-eligibility cases) + test_efficacy_eval.py (53) + both state scripts' --test + lint-skills.py + lazy_parity_audit.py exit 0 + bug-state.py --fsck ok; NOT pipeline-gated
auto_ticked_rows: 0
---

# Completion Receipt

park-provisional-parks-claude-config-auto-generated-stubs marked Fixed on 2026-07-19 during a
standalone (no run marker) `/harden-harness` round (hardening-log Round 103). This receipt was
written by the hardening round, not the bug pipeline's `__mark_fixed__` gate — provenance is
`backfilled-unverified`.

## Notes

Fix commit: `9aa8f8a5` (`harden(script): park-provisional carve-out for auto-generated stubs + canary band-only confound guard`).

Implemented the operator directive: retain the general `stub_origin` provisional exclusion, but
carve out claude-config HARNESS-AUTO-GENERATED stubs so `--park-provisional` auto-accepts their
recommended options. Three seams: (1) durable `auto_generated: true` + `auto_generated_origin`
stamped on the generation sites' capsule frontmatter (`efficacy-eval.py` EVIDENCE.md,
`incident-scan.py` INCIDENT.md); (2) propagation onto the spec-bug pre-conclusion NEEDS_INPUT.md
(spec-bug prose + input-audit backstop); (3) a claude-config-scoped carve-out in the shared
`lazy_core.provisional_eligibility` (both pipelines inherit — no parity mirror owed). Structural
origin tag, never an id prefix; genuine operator stubs still park. `GATE_VERDICT.md` in this dir
records the anti-overfit verdict (overfit/gate_weakening/tautology pass; complexity net-new).

Verification: `pytest user/scripts/tests/test_lazy_core/` → 1300 passed (4 new provisional-
eligibility regression tests: eligible-in-claude-config / genuine-operator-stub-still-parks /
outside-claude-config-parks / unrecognized-origin-parks). `lazy-state.py --test` +
`bug-state.py --test` all pass. `lazy_parity_audit.py --repo-root .` exit 0.
`bug-state.py --repo-root . --fsck` ok. `harness-gate.py --staged`: gate_weakening/overfit/
tautology pass, complexity declared via GATE_VERDICT.md.
