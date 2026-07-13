---
kind: investigation-spec
bug_id: adhoc-incident-hook-deny-19343d-r2
---

# Repeated hook deny: lazy-cycle-containment loop-formation-flag (7x/24h) — Investigation Spec

> incident-scan auto-captured 7 `lazy-cycle-containment` `loop-formation-flag` denies in
> claude-config within 24h (2026-07-12T14:24:08Z→21:42:47Z), flagged as a recurrence of the
> archived Won't-fix `adhoc-incident-hook-deny-19343d` (3 denies, 2026-07-12T14:24→15:59Z).
> Investigation finds: (a) the first 3 of the 7 reported timestamps are **byte-identical** to the
> already-investigated archived cluster — a re-report, not new occurrences (an `incident-scan.py`
> dedup gap); (b) the 4 genuinely-new denies fall entirely within the lifetime of **one
> abnormally long-lived continuous `/lazy(-bug)-batch` run** (session `6474bd32`) that dispatched
> item after item from midday through the small hours of the next day before a commit-ceiling
> backstop forced teardown; (c) the containment mechanism itself is unchanged and remains
> provably correct-by-design, exactly as the archived investigation established. No standing code
> defect.

**Status:** Won't-fix
**Severity:** Low
**Discovered:** 2026-07-12
**Placement:** docs/bugs/adhoc-incident-hook-deny-19343d-r2
**Related:** `docs/bugs/_archive/adhoc-incident-hook-deny-19343d` (the prior investigation this
recurs from — same deny mechanism, same working-as-designed disposition); `user/hooks/lazy-cycle-containment.sh` (the deny site, unchanged since the prior investigation); `docs/bugs/_archive/legacy-tool-input-env-hooks-dead` (the last feature this session's run dispatched before teardown)

---

## Verified Symptoms

1. **[REPORTED]** incident-scan captured 7 `hook-deny` events with hook `lazy-cycle-containment`
   + signature `loop-formation-flag` for repo claude-config between 2026-07-12T14:24:08Z and
   2026-07-12T21:42:47Z (`incident_key claude-config|hook-deny|lazy-cycle-containment|loop-formation-flag`,
   `recurrence_of: adhoc-incident-hook-deny-19343d`). Source: `INCIDENT.md` capsule + the keyed
   `hook-events.jsonl` (`~/.claude/state/853ac81…/hook-events.jsonl`).
2. **[VERIFIED]** Of the 7 reported timestamps, the first 3
   (`1783866248.959019 / 1783870103.2058947 / 1783871964.723208` = 14:24:08 / 15:28:23 /
   15:59:24Z) are **byte-identical** to the 3 timestamps already investigated and closed
   Won't-fix in `docs/bugs/_archive/adhoc-incident-hook-deny-19343d`. Only 4 are genuinely new:
   `1783878330.213758 / 1783879031.1656086 / 1783887102.6213408 / 1783892567.6568422`
   (17:45:30 / 17:57:11 / 20:11:42 / 21:42:47Z).

## Reproduction Steps

Identical mechanism to the archived investigation — no new trigger path found:

1. Ensure `lazy-cycle-containment.sh` is registered (it is; re-registered by
   `live-settings-split-brain-disarms-enforcement-plane`, the run whose re-arm produced the
   original 3 denies).
2. From inside a dispatched cycle subagent (PreToolUse payload carries `agent_id`), run a Bash
   command invoking `lazy-state.py`/`bug-state.py` with a `LOOP_FORMATION_FLAGS` member
   (`--probe, --emit-prompt, --repeat-count[-peek], --run-start, --run-end, --apply-pseudo,
   --enqueue-adhoc, --emit-dispatch, --cycle-begin, --cycle-end`).
3. Observe the deny + a `deny`/`loop-formation-flag` line appended to `hook-events.jsonl`.

**Expected:** the hook denies the op (orchestrator-only). Intended containment behavior,
unchanged since the prior investigation.
**Actual:** identical. The "bug" is the *recurrence count* (7 vs. 3), not a new mis-fire.
**Consistency:** deterministic given the trigger.

## Evidence Collected

### Source Code

**No change since the archived investigation.** `user/hooks/lazy-cycle-containment.sh`'s
`loop-formation-flag` deny site, `LOOP_FORMATION_FLAGS` set, and the `--verify-ledger` allow-list
carve-out are byte-identical to what the archived SPEC traced. Re-confirmed this session: the
containment hook's git history since the archived investigation
(`git log --oneline -- user/hooks/lazy-cycle-containment.sh`) shows only segment-anchoring
(`8494a4f0`) and the background-dispatch deny addition (`a43808ee`, this session's item 1) —
neither touches the `loop-formation-flag` branch or its `LOOP_FORMATION_FLAGS` set. **The deny
mechanism is unchanged and remains categorically not a false positive** (no legitimate
cycle-subagent path reaches a loop-formation flag; see the archived SPEC's full trace).

### Runtime Evidence — dedup-gap finding (new)

- The r2 `ADHOC_BRIEF.md`/`INCIDENT.md` stub reports "7 occurrences ... between
  2026-07-12T14:24:08Z and 2026-07-12T21:42:47Z" with `recurrence_of: adhoc-incident-hook-deny-19343d`.
  The archived bug's own evidence cites the **identical first 3 timestamps**
  (`1783866248 / 1783870103 / 1783871964`) as its full evidence set, already investigated and
  disposed Won't-fix. `incident-scan.py`'s recurrence detection re-swept the full lookback window
  and re-counted those 3 already-adjudicated events alongside the 4 new ones, rather than
  excluding timestamps already covered by the archived incident's own evidence capsule. **This is
  a collector dedup gap** (an observation, not a hook defect — `incident-scan.py` is a
  `user/scripts/*.py` state script, outside this session's HOOKS lane), noted here for a future
  harden-harness pass rather than fixed in this bug.
- **The 4 genuinely-new denies correlate to one continuous, abnormally long-lived pipeline run**
  (session `6474bd32`), via the same bracketing method the archived investigation used
  (`lazy-deny-ledger.jsonl` dispatch/`worker_subdispatch` entries immediately before/after each
  deny timestamp):
  - `17:45:30Z` (d4) — brackets the tail of the `adhoc-incident-hook-deny-19343d` investigation
    cycle itself (dispatch `16:56:25Z`) and the first dispatch of
    `descoped-row-recognition-needs-canonical-marker` (`17:47:20Z`).
  - `17:57:11Z` (d5) — 26s after a `descoped-row-recognition-needs-canonical-marker` dispatch
    (`17:56:45Z`), before its next dispatch (`18:05:45Z`).
  - `20:11:42Z` (d6) — between an `interventions-telemetry-repo-scope-split-brain` dispatch
    (`20:07:52Z`) and its next `worker_subdispatch` (`20:24:07Z`, `sub_skill: execute-plan`).
  - `21:42:47Z` (d7) — between an `interventions-telemetry-repo-scope-split-brain`
    `worker_subdispatch` (`21:34:44Z`) and its next dispatch (`21:59:41Z`).
  - All 4 denies thus occur **mid-cycle on ordinary queue items**, not on any anomalous or
    unrelated main-thread work — consistent with Theory 1 of the archived investigation
    (a subagent occasionally overreaches into an orchestrator-only op; the hook correctly denies
    it), simply observed more often because this run had far more cycles than the 24h window the
    prior 3-event cluster was drawn from.
  - **Full run span:** the keyed `lazy-deny-ledger.jsonl` shows continuous dispatch activity
    (`item_id` sequence: `live-settings-split-brain-disarms-enforcement-plane` →
    `adhoc-incident-hook-deny-19343d` → `descoped-row-recognition-needs-canonical-marker` →
    `interventions-telemetry-repo-scope-split-brain` →
    `hardening-intervention-records-unmeasurable-or-missing` → `legacy-tool-input-env-hooks-dead`)
    from before `13:xx` UTC through this last feature's landing commits
    (`53c3c024`/`030531c7`/`2f1e3eda`/`b9b43ea1`, all 2026-07-12T20:19:55–20:59:15 **local**
    (`-06:00`) = 2026-07-13T02:19:55–02:59:15Z) — a single unbroken run of many hours, matching
    this session's operator-supplied context (a stale run from earlier in the day, armed straight
    through the evening, torn down by the commit-ceiling backstop roughly an hour before this
    investigation began).

### Git History

No commits touch `loop-formation-flag` deny logic since the archived investigation closed. The
only containment-hook commits since then (`8494a4f0` segment-anchoring, `a43808ee` background-
dispatch deny) are unrelated deny classes.

### Related Documentation

- `docs/bugs/_archive/adhoc-incident-hook-deny-19343d` — the prior investigation; its Proven
  Findings ("the deny mechanism is correct-by-design and is NOT the fix site") are reconfirmed
  unchanged.
- `user/scripts/CLAUDE.md` — the C2 hook / C3 script lockstep (unchanged).

## Theories

### Theory 1: Working-as-designed containment during an abnormally long continuous run (CONFIRMED)
- **Hypothesis:** the operator's stated hypothesis — most/all of the 7 denies are artifacts of one
  phantom-armed marker state (a stale run left armed across the evening).
- **Supporting evidence:** all 7 reported timestamps (3 re-reported + 4 new) fall inside the
  provable lifetime of one continuous `/lazy(-bug)-batch` run (dispatch-ledger bracketing, above).
  The containment hook itself is unchanged and remains provably correct-by-design (no new
  code path, no false-positive class found). The higher count (7 vs. the prior 3) is explained
  structurally by run duration — more cycles → more chances for a subagent to attempt an
  orchestrator-only op — not by any new defect.
- **Refinement vs. the operator's framing:** "phantom" should be read precisely — these are not
  denies misfiring against *unrelated* work after a marker should have been torn down; each of the
  4 new denies occurred **mid-cycle on an actively-dispatched queue item** within the long-lived
  run's own normal operation. The anomaly is the run's *duration* (it should have ended much
  earlier per typical cadence and instead ran continuously for many hours until the commit-ceiling
  backstop intervened), not a stale-marker false-positive class distinct from the archived
  investigation's finding.
- **Status:** Confirmed (`traced`, via deny-ledger bracketing).

### Theory 2: A new/different code path now trips the deny (RULED OUT)
- **Hypothesis:** something changed in `lazy-cycle-containment.sh` since the archived
  investigation that broadened the `loop-formation-flag` trigger.
- **Supporting evidence:** none. `git log` since the archived closure shows only unrelated
  changes (segment-anchoring, background-dispatch deny).
- **Status:** Ruled Out.

## Proven Findings

1. **The deny mechanism is unchanged and remains correct-by-design** — reconfirmed against the
   current `lazy-cycle-containment.sh`; not the fix site (same finding as the archived
   investigation).
2. **3 of the 7 reported occurrences are a re-report of already-adjudicated events** — an
   `incident-scan.py` recurrence-detection dedup gap (does not exclude timestamps already covered
   by an archived incident's own evidence capsule). Noted as a residual observation for a future
   harden-harness pass; not fixed in this bug (out of the HOOKS lane; `incident-scan.py` is a
   state script).
3. **The 4 genuinely-new denies are fully explained by one abnormally long-lived, continuous
   `/lazy(-bug)-batch` run** (session `6474bd32`) dispatching many ordinary queue items in
   sequence — each deny occurred mid-cycle on a live, legitimate item, not on stale/orphaned
   marker state misapplied to unrelated work.
4. **Prevention already in place:** the run that produced this cluster was itself eventually
   torn down by the commit-ceiling backstop (`--run-end`/`--cycle-end`), and the marker-teardown
   playbook this session's context describes is the standing mitigation for a run that overstays
   its intended cadence — bounding (not eliminating) future recurrence risk of this same
   working-as-designed signature.

## Affected Area

| Component | Files | Impact |
|-----------|-------|--------|
| Containment hook (deny site) | `user/hooks/lazy-cycle-containment.sh` | Unchanged, provably correct — not to be relaxed. |
| Incident collector (residual) | `user/scripts/incident-scan.py` | Dedup gap re-reports already-adjudicated timestamps under the same `incident_key` on recurrence; candidate for a future harden-harness pass (STATE lane, out of scope here). |

## Open Questions

None outstanding for this recurrence. The disposition mirrors the archived investigation's
operator-resolved Won't-fix (working-as-designed, no code change); this SPEC additionally
resolves the "is this the SAME phenomenon or a new one" question the recurrence stub raised —
it is the same phenomenon, observed more often due to one run's abnormal duration, plus a
partial re-report of already-closed evidence.

## Disposition

**Won't-fix.** `recurrence_of: adhoc-incident-hook-deny-19343d`. The containment hook is working
exactly as designed (same Proven Finding as the archived investigation); the elevated count is
structurally explained by one long-lived run's duration plus a collector dedup gap, not a new
defect. **Prevention note:** the commit-ceiling backstop + marker-teardown playbook that already
ended this run's abnormal duration is the standing mitigation — no further code change is
warranted. Receipt-exempt (Won't-fix close; no `FIXED.md`).
