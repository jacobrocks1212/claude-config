---
kind: fixed
feature_id: adhoc-incident-scan-rereports-archived-evidence
date: 2026-07-12
provenance: operator-directed-interactive
validated_via: pytest (test_incident_scan.py — black-box subprocess harness, NOT MCP-gated)
auto_ticked_rows: 0
---

# Completion Receipt

adhoc-incident-scan-rereports-archived-evidence marked fixed on 2026-07-12 by an operator-directed
interactive subagent session. This receipt was written by the session directly, not the pipeline's
`__mark_fixed__` gate — provenance is deliberately `operator-directed-interactive`.

## Notes

Implemented per the traced cause (cited from the already-Concluded `docs/bugs/_archive/adhoc-
incident-hook-deny-19343d-r2` investigation's own dedup-gap finding): `incident-scan.py` gained
`scan_archived_evidence_timestamps()` (unions every archived `INCIDENT.md` capsule's raw evidence
`ts` values, keyed by `incident_key`) and `_exclude_archived_evidence()` (drops any cluster row
whose exact `ts` an archived incident already reported, recomputing occurrences/lines/first_ts/
last_ts/cleared from the surviving rows), applied in `main()` before the recurrence bar filter.

Chose the exact-timestamp-set exclusion form (over an at-or-before cutoff) as the most conservative
shape: it can never accidentally exclude a genuinely-new occurrence sharing a boundary timestamp,
and it targets the exact observed defect (byte-identical re-reported timestamps). Discovered and
preserved an important invariant while writing tests: a recurrence must be justified by GENUINELY
NEW occurrences (never re-flag a signature off purely already-adjudicated evidence), while a
signature with genuinely new activity still clears the bar regardless of stale evidence
coexisting in the same window. Byte-identical when no archived incidents exist for a key (the
common case).

4 new/adjusted pytest fixtures added to `test_incident_scan.py`: reproduces the exact live
19343d/19343d-r2 shape (3 old + 4 new → occurrences: 4, only new evidence lines printed); a
pure-re-report cluster never re-clears the bar; the fix is byte-inert with no archived incidents;
the pre-existing D5-A recurrence-mechanics test's fixture adjusted (3 fresh denies instead of 1) to
stay compatible with the new semantics, with an added assertion proving the exclusion. Gate:
`python -m pytest user/scripts/test_incident_scan.py -q` → 18 passed.
