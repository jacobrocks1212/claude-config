---
kind: fixed
feature_id: coupled-overlays-drift-from-committed-skills
date: 2026-07-19
provenance: backfilled-unverified
validated_via: generate-coupled-skills.py --check (exit 0) + test_generate_coupled_skills.py 34/34 + full harden gate battery; NOT pipeline-gated
auto_ticked_rows: 0
---

# Completion Receipt

`coupled-overlays-drift-from-committed-skills` marked Fixed on 2026-07-19 during a dispatched
`/harden-harness` round (Round 116, observed-friction). This receipt was written by the harden
subagent, not the bug pipeline's `__mark_fixed__` gate — provenance is `backfilled-unverified`
(out-of-pipeline `harden(...)` fix).

## Notes

Root cause (proven): three commits (`ca7f2c8b`, `f79c1a12`, `4ba985f4`) edited a canonical +
coupled SKILL.md without re-extracting the per-pair overlays, so `generate-coupled-skills.py
--check` was red on the committed tree for `lazy-bug-batch`, `lazy-batch-cloud`, and `lazy-cloud`.
Commit bisect confirmed the tree was clean at `4cee96e3` (DRIFT=0) and went red at `ca7f2c8b`
(DRIFT=2) → `f79c1a12` (DRIFT=3). In every case the committed derived SKILL.md is the intended
hand-authored state; only the overlay re-extraction was missed.

Fix: `python3 user/scripts/generate-coupled-skills.py --extract --repo-root .` rewrote ONLY the
three drifted overlays (`user/scripts/coupled-overlays/{lazy-batch-cloud,lazy-bug-batch,lazy-cloud}.overlay.json`)
to record the current hand-authored divergences — ZERO SKILL.md changes — honoring the PROVISIONAL
hand-authoring contract. Fix commit: `96f938ae`.

Verification: `generate-coupled-skills.py --check --repo-root .` → exit 0 (all pairs byte-identical).
`pytest user/scripts/test_generate_coupled_skills.py` → 34/34. Full harden gate battery green:
test_lazy_core 1336/1336, test_hooks 285/285, lint-skills OK, lazy-state/bug-state --test OK,
bug-state --fsck clean, lazy_parity_audit exit 0, doc-drift-lint 0 findings.

Durable prevention (the advisory drift gate `generate-coupled-skills.py --check` is not in the
mandatory gate list, so this class recurs) is out of scope for this instance fix and is
front-enqueued as a separate `/spec-bug` over-fit spin-off (see hardening-log Round 116).
