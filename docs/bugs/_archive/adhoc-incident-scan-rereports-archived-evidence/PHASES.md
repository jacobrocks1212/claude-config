# Implementation Phases — incident-scan.py re-reports already-adjudicated evidence into a recurrence stub

**Status:** Fixed

> Phases for [`SPEC.md`](./SPEC.md)

**MCP runtime:** not-required — claude-config has no Tauri/MCP app surface; verified via
`pytest user/scripts/test_incident_scan.py` (the repo's established black-box subprocess harness
for `incident-scan.py`).

## Validated Assumptions

- **The exact defect is already fully traced in an archived sibling investigation.**
  `docs/bugs/_archive/adhoc-incident-hook-deny-19343d-r2`'s own "Runtime Evidence — dedup-gap
  finding" section names this precisely: 3 of 7 reported timestamps are byte-identical re-reports
  of the already-archived `adhoc-incident-hook-deny-19343d` incident's own evidence, and its Proven
  Finding #2 explicitly defers the fix to "a future harden-harness pass" as out of that session's
  HOOKS lane. This bug IS that deferred pass.
- **A naive fix (exclude archived timestamps from the occurrence count unconditionally) would break
  legitimate low-volume recurrence detection**, discovered while writing the regression test suite:
  a signature whose only NEW activity is a handful of events (below the bar on its own) still
  needs the still-in-window OLD evidence to justify re-flagging a genuinely ongoing problem. The
  fix must therefore require GENUINELY NEW occurrences to clear the bar — never re-flag a
  signature off PURELY already-adjudicated evidence, but always let genuinely new activity clear
  the bar on its own (matching the real 19343d-r2 shape: 4 new events cleared the ≥3 deny bar
  without needing the 3 old ones at all).

## Cross-feature Integration Notes

No `**Depends on:**` block in the SPEC. This bug modifies ONLY `incident-scan.py` (a
`user/scripts/*.py` state script, the STATE lane) — no hook, skill, or other pipeline surface is
touched. The pre-existing `test_archived_recurrence_end_to_end_capsule_carries_recurrence_of`
regression test's fixture was adjusted (3 fresh denies instead of 1) to remain compatible with the
new "genuinely new occurrences required" semantics while preserving its actual guarantee (D5-A
recurrence mechanics: fresh slug, `recurrence_of` set, archive untouched) unchanged.

---

### Phase 1: Archived-evidence timestamp exclusion in `collect_clusters` / recurrence reporting

**Status:** Complete

**Scope:** Add a read-only archived-evidence-timestamp scanner and apply it to every cluster BEFORE
the recurrence bar filter, so a cluster's occurrence count / evidence lines never include a
timestamp an archived incident's own `INCIDENT.md` capsule already reported.

**TDD:** yes — every new behavior (the exclusion itself, the "genuinely new required" bar semantics,
the byte-identical no-op when no archived incidents exist) is covered by a new pytest fixture in
`test_incident_scan.py` before being relied upon.

**Deliverables:**
- [x] `scan_archived_evidence_timestamps(repo_root)` (`user/scripts/incident-scan.py`) — read-only,
  best-effort scan of every `docs/bugs/_archive/*/INCIDENT.md`'s fenced evidence block, unioning the
  raw `"ts"` values per `incident_key`. Malformed/missing capsules degrade to an empty set for that
  key, mirroring `scan_incident_keys`'s existing tolerance.
- [x] `_exclude_archived_evidence(cluster, covered)` — drops any cluster row whose exact `ts` is in
  `covered`, recomputing `lines`/`occurrences`/`first_ts`/`last_ts`/`cleared` from the SURVIVING
  rows only. Returns the SAME object (no-op, zero extra work) when nothing was excluded.
- [x] `main()` applies the exclusion to every cluster (keyed by its own `incident_key`) BEFORE the
  `cleared = [...]` bar filter — so a cluster whose only occurrences are pure re-reports of archived
  evidence correctly drops below the bar, while a cluster with genuinely new occurrences (regardless
  of whether old evidence also happens to still be in-window) reports ONLY the new ones. Byte-inert
  when `docs/bugs/_archive/` has no matching incidents (the common case, and every repo without this
  bug's specific recurrence shape).
- [x] Tests (`user/scripts/test_incident_scan.py`):
  `test_archived_evidence_excluded_from_recurrence_occurrence_count` (reproduces the exact live
  19343d/19343d-r2 shape: 3 old + 4 new → `occurrences: 4`, evidence lines contain only the 4 new
  timestamps, `recurrence_of` still correct, archive untouched);
  `test_pure_rereport_with_no_new_evidence_does_not_reclear_bar` (zero genuinely-new activity → the
  cluster never re-clears the bar); `test_no_archived_incidents_byte_identical_to_before` (no
  archived incidents → byte-identical dry-run output, proving the common case pays nothing).
  `test_archived_recurrence_end_to_end_capsule_carries_recurrence_of`'s fixture was adjusted (3
  fresh denies instead of 1, matching the ≥3 deny bar) to stay compatible with the new
  "genuinely-new-required" semantics, with an added assertion (`occurrences == "3"`) proving the
  exclusion fires even on the pre-existing D5-A recurrence-mechanics test.

**Implementation Notes (2026-07-12):** Landed exactly as scoped. The exact-timestamp-set exclusion
form (over an at-or-before cutoff) was chosen per the SPEC's own reasoning: it can never accidentally
exclude a genuinely-new occurrence sharing a boundary timestamp with the archived window, and it
directly targets the observed defect (byte-identical re-reported timestamps) rather than a broader
recency heuristic. Files: `user/scripts/incident-scan.py`, `user/scripts/test_incident_scan.py`.

**Minimum Verifiable Behavior:** `python -m pytest user/scripts/test_incident_scan.py -q` is GREEN
(18/18, all pre-existing + 4 new/modified fixtures).

**Runtime Verification:** N/A — pure Python state-script logic, no app runtime; verified by the
black-box subprocess pytest fixtures above (the harness's established verification method for this
script, per `user/scripts/CLAUDE.md`).

**MCP Integration Test Assertions:** N/A — no MCP tool surface in this repo.

**Prerequisites:** None (single phase).

**Files likely modified:**
- `user/scripts/incident-scan.py` — `scan_archived_evidence_timestamps`,
  `_exclude_archived_evidence`, the `main()` wiring.
- `user/scripts/test_incident_scan.py` — 3 new fixtures + 1 adjusted fixture.

**Testing Strategy:** Black-box subprocess testing (the file's established convention — every test
drives `incident-scan.py` as a real subprocess against a hermetic temp `docs/bugs/`/state-dir tree
and asserts stdout + on-disk artifacts), consistent with every other test in this suite.

**Integration Notes for Next Phase:** None — final phase. The `__mark_fixed__` gate (applied here
directly per the operator-directed-interactive protocol) flips `**Status:**` and writes `FIXED.md`.

---

## Review Notes

_(Populated by the /spec-phases Step 6 review gate and by later /execute-plan batch reviews — N/A
for this operator-directed-interactive close-out.)_
