---
kind: fixed
feature_id: canary-band-only-trip-auto-enqueues-without-attribution
date: 2026-07-19
provenance: backfilled-unverified
validated_via: pytest test_efficacy_eval.py (53 passed, incl. 3 new confound-guard cases) + tests/test_lazy_core/ (1300) + both state scripts' --test + lazy_parity_audit.py exit 0 + bug-state.py --fsck ok; NOT pipeline-gated
auto_ticked_rows: 0
---

# Completion Receipt

canary-band-only-trip-auto-enqueues-without-attribution marked Fixed on 2026-07-19 during a
standalone (no run marker) `/harden-harness` round (hardening-log Round 104). This receipt was
written by the hardening round, not the bug pipeline's `__mark_fixed__` gate — provenance is
`backfilled-unverified`.

## Notes

Fix commit: `9aa8f8a5` (`harden(script): park-provisional carve-out for auto-generated stubs + canary band-only confound guard`).

Split canary trip DETECTION (always surfaced — D4 never-silent) from auto-ENQUEUE via a new
`_canary_should_enqueue` confound guard in `efficacy-eval.py`. A band-only trip on a
non-independent (self-emitted / mixed / undeclared) signal with ZERO attributed fresh incidents
is SUPPRESSED (surfaced in `payload.suppressed[]` + `suppressed_notify`, the record left open —
re-surfaces until attribution appears or the operator acts) instead of auto-enqueuing a
`canary-revert-<id>` bug stub. Incident-attributed trips and independent-signal band trips are
unaffected. Keys on structural signals (attribution + declared independence), never on a signal
id. D4 preserved — nothing is auto-reverted, and every trip (enqueued or suppressed) is surfaced.

Design choice (surfaced in the SPEC's Locked Decisions, not provisionalized — operator directed
the fix and offered "attribution/confound guard OR tune the D2 band"): chose the structural guard
over band-tuning. `efficacy-eval.py` is not on `docs/gate/control-surfaces.json`, so the change is
`in_scope: false` for the harness design-gate (no GATE_VERDICT required).

Verification: `pytest user/scripts/test_efficacy_eval.py` → 53 passed (3 new: self-emitted-zero-
attribution suppressed / independent-signal still enqueues / self-emitted-with-1-attribution
enqueues). `pytest user/scripts/tests/test_lazy_core/` → 1300 passed. `lazy-state.py --test` +
`bug-state.py --test` pass. `lazy_parity_audit.py --repo-root .` exit 0. `bug-state.py --fsck` ok.
