# incident-scan.py re-reports already-adjudicated evidence from an archived incident into its recurrence stub — Investigation Spec

> `incident-scan.py`'s recurrence detection (D5-A) re-sweeps the FULL signal history for a
> signature and re-counts + re-prints every raw evidence line, including ones a PRIOR archived
> incident's own `INCIDENT.md` capsule already reported. Live evidence: the archived
> `docs/bugs/_archive/adhoc-incident-hook-deny-19343d-r2` re-reported the 3 byte-identical
> timestamps `docs/bugs/_archive/adhoc-incident-hook-deny-19343d` had already investigated and
> closed Won't-fix, alongside 4 genuinely new ones — inflating `occurrences: 7` when only 4 were
> new, and duplicating already-adjudicated evidence in the new capsule. The collector's dedup keys
> on `incident_key` (whether a stub already exists) but never on the ARCHIVED incident's own
> covered evidence timestamps.

**Status:** Fixed
**Severity:** P3
**Discovered:** 2026-07-12
**Placement:** docs/bugs/adhoc-incident-scan-rereports-archived-evidence
**Related:** `docs/bugs/_archive/adhoc-incident-hook-deny-19343d` (the original investigation,
Won't-fix, 3 denies 14:24→15:59Z); `docs/bugs/_archive/adhoc-incident-hook-deny-19343d-r2` (the
recurrence stub this bug is traced from — its own "Runtime Evidence — dedup-gap finding" section
names this exact defect and explicitly defers the fix to "a future harden-harness pass", scoping
it out of its own HOOKS-lane investigation as a `user/scripts/*.py` state-script concern); feature
`incident-auto-capture` (the collector's SPEC, D4 clustering + D5 dedup surface).

## Verified Symptom

Cited verbatim from the already-Concluded `adhoc-incident-hook-deny-19343d-r2` SPEC (Verified
Symptoms #2, Runtime Evidence, Proven Finding #2): of 7 reported `hook-deny`
(`lazy-cycle-containment|loop-formation-flag`) timestamps in the `-r2` capsule, the first 3
(`1783866248.959019 / 1783870103.2058947 / 1783871964.723208`) are byte-identical to the 3
timestamps the archived `-19343d` incident's own `INCIDENT.md` already captured and closed
Won't-fix. Only 4 (`1783878330.213758 / 1783879031.1656086 / 1783887102.6213408 /
1783892567.6568422`) were genuinely new. The `-r2` capsule's frontmatter reported
`occurrences: 7` — the true "new since the archived close" count was 4.

## Root Cause

**Classification: `missing-dedup-surface`.** `incident-scan.py`'s dedup (D5, `scan_incident_keys`)
answers "does an open or archived stub already exist for this `incident_key`" — a PRESENCE check.
It never reads WHAT an archived incident's own evidence capsule already covered. `collect_clusters`
re-sweeps the raw ledger/events history unconditionally on every scan, so any timestamp that was
in-window at the time of the ORIGINAL (now-archived) incident and is STILL in-window at a LATER
scan (denies/events are never deleted; a 24h window naturally re-covers a timestamp that recurs
within roughly a day of the original close) is re-counted and re-printed verbatim in the new
capsule, alongside genuinely new occurrences.

This is a real gap, not user error: recurrence detection (D5-A) is supposed to answer "is this
STILL happening" for a NEW capsule reviewers can trust at face value; a capsule that silently
mixes stale re-reported evidence with fresh evidence overstates the recurrence and wastes a
reviewer's time re-confirming lines already adjudicated.

## Fix Scope

1. **`scan_archived_evidence_timestamps(repo_root)`** (`user/scripts/incident-scan.py`): reads
   every `docs/bugs/_archive/*/INCIDENT.md`'s fenced evidence block, unions the raw `"ts"` values
   per `incident_key`. Read-only, best-effort (malformed/missing capsules degrade to an empty set
   for that key — never raises), mirroring `scan_incident_keys`'s existing discipline.
2. **`_exclude_archived_evidence(cluster, covered)`**: given a cluster and its `incident_key`'s
   covered-timestamp set, drops any evidence row whose exact `ts` is already covered, then
   RECOMPUTES `lines`/`occurrences`/`first_ts`/`last_ts`/`cleared` from the SURVIVING rows only.
   Applied in `main()` to every cluster, keyed by `incident_key`, BEFORE the bar filter — so a
   cluster whose ONLY occurrences are re-reports of already-archived evidence correctly drops
   below the bar (no re-flagging a signature off evidence it was already investigated and closed
   against), while a cluster with genuinely new occurrences reports ONLY those.
   **Byte-identical when no archived incidents exist for a key** (the common case pays nothing).
3. This is the exact-timestamp-set shape of the SPEC's two named options ("exclude ledger entries
   at-or-before the newest archived incident's covered window" vs "extend the dedup to evidence
   timestamps") — the exact-set form was chosen (over an at-or-before cutoff) because it is
   strictly more precise: it can never accidentally exclude a genuinely-new occurrence that happens
   to share a timestamp boundary with the archived window, and it directly targets the observed
   defect (byte-identical re-reported timestamps), not a broader recency heuristic.
4. TDD in `test_incident_scan.py`: (a) an archived incident's 3 old timestamps STILL present in
   the ledger alongside 4 genuinely-new ones → recurrence capsule reports `occurrences: 4`, its
   evidence lines contain the 4 new timestamps and NONE of the 3 old ones, `recurrence_of` still
   set correctly, archive untouched (reproduces the live `-19343d`/`-19343d-r2` shape exactly); (b)
   a signature whose ENTIRE occurrence set is a pure re-report of archived evidence (zero
   genuinely-new activity) does not re-clear the bar at all; (c) a repo with no archived incidents
   (or an empty `_archive/`) is byte-identical to before the fix.

## Decisions

None outstanding — this is a mechanical, uncontested fix matching the `-r2` SPEC's own named
options; no locked-decision conflict, no design fork.
