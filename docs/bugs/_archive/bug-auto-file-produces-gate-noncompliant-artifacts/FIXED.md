---
kind: fixed
feature_id: bug-auto-file-produces-gate-noncompliant-artifacts
date: 2026-07-20
provenance: backfilled-unverified
completed_commit: a7a04ea6
auto_ticked_rows: 0
---

# Completion Receipt

Fixed OUT-OF-PIPELINE by a manual `/harden-harness` round (Round 135, 2026-07).
The auto-file/ad-hoc bug enqueue now (a) omits the `severity` key when no explicit
override is supplied (no more `severity: null`) and (b) seeds a gate-compliant stub
`SPEC.md` beside `ADHOC_BRIEF.md`, so the target repo's `qg:bugs-consistency` gate
(queue-schema + queue-dangling-id + bug-status/severity-canonical) stays green.

Fix commit: `a7a04ea6` (bug spec `7f3b4788` predates it). Regression evidence:
`test_lazy_core/` 1347/1347, `test_hooks.py` 288/288, `lint-skills.py` OK,
`lazy-state.py --test` OK, `bug-state.py --test` OK, `test_incident_scan.py` 18/18,
`bug-state.py --fsck` clean. Not MCP-validated (harness-only change); provenance
backfilled-unverified.
