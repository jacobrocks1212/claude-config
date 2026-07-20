---
kind: investigation-spec
bug_id: adhoc-incident-hook-deny-19343d-r3
---

# Repeated hook deny: lazy-cycle-containment loop-formation-flag (4x/24h) — Investigation Spec

> incident-scan auto-captured a THIRD cluster of `lazy-cycle-containment` `loop-formation-flag`
> denies in claude-config (4 events, 2026-07-13 08:11→16:18Z), flagged as a recurrence of the
> archived Won't-fix `adhoc-incident-hook-deny-19343d-r2`. Investigation reconfirms the deny class
> is **categorically correct-by-design** (r1 + r2, unchanged) and is NOT a fix site. The genuine,
> newly-traced harness defect this third recurrence surfaces is in the COLLECTOR: `incident-scan.py`
> re-enqueues a NEW `-rN` bug stub on EVERY post-archive recurrence of a signature **without
> consulting the archived incident's disposition**, so a provably working-as-designed / Won't-fix
> signature churns the bug queue unboundedly (r1 → r2 → r3 → …). The disposition (fix the collector
> churn, and by which mechanism, vs. Won't-fix again) is an operator product-class call — surfaced in
> `NEEDS_INPUT.md`.

**Status:** Investigating
**Severity:** Low
**Discovered:** 2026-07-19
**Placement:** docs/bugs/adhoc-incident-hook-deny-19343d-r3
**Related:** `docs/bugs/_archive/adhoc-incident-hook-deny-19343d-r2` (r2 — Won't-fix, working-as-designed; noted the collector dedup/down-weight gap as a future harden pass); `docs/bugs/_archive/adhoc-incident-hook-deny-19343d` (r1 — Won't-fix; its Affected Area already flagged "may warrant dedup/down-weight of never-false-positive containment signatures"); `user/hooks/lazy-cycle-containment.sh` (the deny site, unchanged); `user/scripts/incident-scan.py` (the collector — the newly-traced fix site); feature `incident-auto-capture` (the collector's SPEC)

---

## Verified Symptoms

1. **[REPORTED]** incident-scan captured 4 `hook-deny` events with hook `lazy-cycle-containment` +
   signature `loop-formation-flag` for repo claude-config between 2026-07-13T08:11:31Z and
   2026-07-13T16:18:28Z (`incident_key claude-config|hook-deny|lazy-cycle-containment|loop-formation-flag`,
   `recurrence_of: adhoc-incident-hook-deny-19343d-r2`). Source: this dir's `INCIDENT.md` capsule
   (ts 1783930291 / 1783930299 / 1783949213 / 1783959508). Not a user-observed symptom — an
   autonomous-run signal captured by the harness; there is no interactive human symptom to confirm.
2. **[VERIFIED]** The 4 r3 timestamps are **genuinely new** — none appears in any
   `docs/bugs/_archive/*/INCIDENT.md` capsule (grep-verified), so `scan_archived_evidence_timestamps`
   / `_exclude_archived_evidence` (the `adhoc-incident-scan-rereports-archived-evidence` fix)
   correctly did NOT suppress them. r2's window was 2026-07-12; r3's is a distinct day. This is a
   TRUE recurrence, not the archived-evidence re-report class r2 partially was.
3. **[VERIFIED]** This is the THIRD investigation of the identical `incident_key`, both prior
   dispositions **Won't-fix / working-as-designed** with NO `FIXED.md` receipt (r1 `19343d`, r2
   `19343d-r2` — both archived; `find … -iname FIXED.md` returns none). The containment hook's
   `loop-formation-flag` deny branch is byte-unchanged across all three (r2 Evidence: only
   segment-anchoring + background-dispatch-deny commits touched the hook, neither on this branch).

## Reproduction Steps

**Symptom under investigation for root cause = the recurrence ENQUEUE (the collector churn), not the
deny.** To reproduce the collector re-enqueuing a NEW stub for an already-Won't-fixed signature:

1. Have an archived bug dir `docs/bugs/_archive/<slug>/INCIDENT.md` carrying an `incident_key`, whose
   SPEC.md is `**Status:** Won't-fix` (working-as-designed, no code change) — e.g.
   `adhoc-incident-hook-deny-19343d-r2`.
2. Let the SAME signature fire again on a later day (new deny-ledger / `hook-events.jsonl` timestamps
   NOT present in any archived capsule), enough to clear the `hook-deny` bar (≥3 in 24h).
3. Run `python3 user/scripts/incident-scan.py --repo-root . --dry-run`.

**Expected (the fix target):** the collector recognizes the signature was already adjudicated
**Won't-fix / working-as-designed** and SUPPRESSES the re-enqueue (or requires an explicit
"expected-signature" opt-out), so a correct-by-design deny does not generate a fourth (fifth, …)
investigation cycle.
**Actual:** the collector emits `➕ would-enqueue ad-hoc bug … (adhoc-incident-hook-deny-19343d-r3)
recurrence_of=adhoc-incident-hook-deny-19343d-r2` — a NEW `-rN` stub, because the D5-A post-archive
branch mints `-r{N+1}` unconditionally, never reading the archived disposition.
**Consistency:** deterministic given the archived-key + new-timestamp + cleared-bar inputs.

## Evidence Collected

### Source Code

**The containment deny (correct-by-design — NOT the fix site; carried forward from r1/r2, reconfirmed):**
- Deny site `user/hooks/lazy-cycle-containment.sh` `_deny(CORRECTIVE, "loop-formation-flag")`,
  reachable only when a **dispatched subagent** (`agent_id` present) runs a `lazy-state|bug-state.py`
  command carrying a `LOOP_FORMATION_FLAGS` member and NOT an allow-listed flag
  (`--verify-ledger`/`--neutralize-sentinel`). No sanctioned cycle-subagent path reaches a
  loop-formation flag (the C2 hook / C3 `refuse_if_cycle_active` lockstep makes every such op
  orchestrator-only). Therefore a `loop-formation-flag` deny is **categorically the hook working as
  designed** — never a false positive. Relaxing it re-opens the runaway-loop hole the lockstep exists
  to close. (r1 §Proven Findings; r2 reconfirmed unchanged.) The r3 deny lines carry the identical
  fixed CORRECTIVE detail string + `repo_root: C:\Users\Jacob\source\repos\claude-config`, so the
  class finding holds regardless of which run produced them.

**The collector churn (the newly-traced fix site — `user/scripts/incident-scan.py`):**
- `scan_incident_keys()` (`incident-scan.py:323-359`) reads each `docs/bugs/**/INCIDENT.md`'s
  `incident_key:` frontmatter and buckets slugs into `{open: [...], archived: [...]}`. It reads the
  capsule ONLY — **it never opens the sibling `SPEC.md` to read `**Status:** Won't-fix`.** The
  collector has no notion of an archived incident's *disposition*.
- The cleared-cluster loop `for c in cleared:` (`incident-scan.py:659`) dedups at
  `incident-scan.py:663`: `if info["open"] or base_slug in queued:` → skip. An **archived-only** key
  is NOT deduped here.
- The D5-A post-archive branch (`incident-scan.py:668-675`) then mints a NEW recurrence stub
  UNCONDITIONALLY: `recurrence_of = sorted(info["archived"])[-1]; slug =
  f"{base_slug}-r{len(info['archived']) + 1}"` — regardless of whether the most-recent archived
  incident concluded Won't-fix/working-as-designed.
- `_enqueue()` (`incident-scan.py:575`, called at `:700`) then shells
  `lazy-state.py --enqueue-adhoc --type bug` and seeds `INCIDENT.md`.
- **Fix-site-on-path:** the `:668` recurrence branch is literally the code that produces this r3
  stub; adding a disposition-aware suppression there (or at the `:663` dedup) is on the symptom's
  serving path.

### Runtime Evidence

- `INCIDENT.md` (this dir): the 4 verbatim r3 deny lines + `recurrence_of: adhoc-incident-hook-deny-19343d-r2`.
- The specific run that drove the 4 r3 denies is NOT re-correlated this cycle (the deny event stores
  only the fixed CORRECTIVE string, not the offending command — the same traceability gap r1/r2
  documented). **Immaterial to r3's disposition:** the deny class is provably correct-by-design, so
  which run produced them does not change the finding. Re-correlating it would be effort with no
  product-behavior payoff (⚖ policy applied — see the return summary).

### Git History

- No commit touches the `loop-formation-flag` deny branch since r1/r2 closed (r2 Evidence: only
  segment-anchoring + background-dispatch-deny commits, neither on this branch). The collector's D5-A
  recurrence path is likewise unchanged since `incident-auto-capture` shipped; the only later
  collector edit (`scan_archived_evidence_timestamps`, the `adhoc-incident-scan-rereports-archived-evidence`
  fix) addresses a DIFFERENT gap (byte-identical re-report of already-captured timestamps), not the
  disposition-blindness this bug traces.

### Related Documentation

- r1 §Affected Area already named the collector: "Raised this stub from a provably-working-as-designed
  deny class; **may warrant dedup/down-weight of never-false-positive containment signatures.**"
- r2 §Proven Findings #2 noted the dedup gap "for a future harden-harness pass; not fixed in this bug."
- `user/scripts/CLAUDE.md` — the C2 hook / C3 script lockstep (the deny set is orchestrator-only).

## Theories

### Theory 1: The deny class is a standing false-positive (RULED OUT)
- **Hypothesis:** something now trips `loop-formation-flag` on a legitimate subagent path.
- **Supporting evidence:** none. The deny branch is byte-unchanged; no sanctioned subagent path
  reaches a loop-formation flag (C2/C3 lockstep). Established in r1, reconfirmed r2 + r3.
- **Status:** Ruled Out.

### Theory 2: The recurrence is a collector re-report of already-adjudicated evidence (RULED OUT for r3)
- **Hypothesis:** r3, like r2's first 3 events, re-counts timestamps an archived capsule already held.
- **Supporting evidence:** none — the 4 r3 timestamps are absent from every archived capsule
  (grep-verified). The `scan_archived_evidence_timestamps` fix correctly did not suppress them.
- **Status:** Ruled Out — r3 is a TRUE recurrence of genuinely-new denies.

### Theory 3: The collector re-enqueues Won't-fix/working-as-designed recurrences disposition-blind (CONFIRMED, traced)
- **Hypothesis:** `incident-scan.py` mints a NEW `-rN` stub on every post-archive recurrence without
  consulting whether the prior archived disposition was Won't-fix/working-as-designed, so a
  correct-by-design deny churns the bug queue indefinitely.
- **Supporting evidence:** the traced serving path above (`:323` reads only `incident_key`, never
  `SPEC.md` status; `:663` dedups only on open/queued; `:668` mints `-r{N+1}` unconditionally). Live
  proof: this very r3 stub exists as the third such enqueue.
- **Contradicting evidence:** none. (An intentional design choice to always re-surface a recurrence
  is defensible — hence the disposition is an operator call, not a unilateral fix.)
- **Status:** Confirmed (`traced`, fix-site-on-path shown).

## Proven Findings

1. **The containment deny is correct-by-design and is NOT the fix site** (`traced` — the deny branch
   is unchanged and categorically not a false positive; r1/r2 reconfirmed). Any relaxation re-opens
   the runaway-loop hole. Ruled out as the fix target.
2. **The genuine harness defect is collector disposition-blindness** (`traced` to
   `incident-scan.py:323/663/668`): a post-archive recurrence of a Won't-fix/working-as-designed
   signature is re-enqueued as a fresh `-rN` bug stub, with no read of the archived disposition, so a
   provably-correct deny generates an unbounded r1→r2→r3→… investigation series (redone work — the
   exact inefficiency the harness mission targets).
3. **This was foreseen and deferred twice** — r1's Affected Area and r2's Proven Finding #2 both named
   the collector dedup/down-weight gap and deferred it to a future harden pass. r3 recurring IS the
   signal that the deferral should end.

## Affected Area

| Component | Files | Impact |
|-----------|-------|--------|
| Containment hook (deny site) | `user/hooks/lazy-cycle-containment.sh` | Provably correct — NOT to be relaxed. |
| Incident collector — recurrence path | `user/scripts/incident-scan.py` (`scan_incident_keys` :323; dedup :663; D5-A branch :668) | Disposition-blind: re-enqueues Won't-fix/working-as-designed recurrences as fresh `-rN` stubs. The fix site. |

## Open Questions

- **Disposition + fix mechanism (operator-authority — surfaced in `NEEDS_INPUT.md`).** Whether to fix
  the collector churn now (recommended, given the third recurrence) and, if so, via an explicit opt-in
  "expected-signature" suppression (recommended — preserves a genuinely-new cause reusing the
  signature) vs. an automatic Won't-fix-status read (simpler, but risks silently masking a real future
  recurrence) vs. Won't-fix again (status quo — accept perpetual churn). This is a product-class harness
  behavior + safety-trade-off call on a stub the operator has not shaped, so the SPEC stays
  `Investigating` pending the operator's choice.
