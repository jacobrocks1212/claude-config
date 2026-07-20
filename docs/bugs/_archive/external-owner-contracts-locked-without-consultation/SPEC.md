# External-Owner Contracts Locked Without Consultation — Investigation Spec

> `/spec` can lock a decision that creates or changes a contract consumed by another team (events, sync schemas, exported columns) on purely in-repo evidence — the 57077 classic `organization.archived` CognitoEvent was locked this way, then reversed by one OW-team Slack message, deleting Phase 1+6 event work and invalidating an entire sibling Overwatch SPEC authored ~24h earlier.

**Status:** Fixed
**Fixed:** 2026-07-18
**Severity:** P2
**Discovered:** 2026-07-10
**Fix commit:** c32794ca
**Placement:** docs/bugs/external-owner-contracts-locked-without-consultation
**Related:** 57077 case study (Phase 10, Locked Decision 4), sibling bug `premise-contradictions-demoted-not-escalated` (shares `user/skills/spec/SKILL.md` — implementation sequenced AFTER it)

---

## Verified Symptoms

1. **[VERIFIED]** The model detected the mirror-mismatch problem, posed an AskUserQuestion, and its own winning option text flagged the trigger: "Most correct cross-system, but **adds an external contract change and Overwatch-side work**" — yet no option or follow-up said "confirm with the OW team" or "check how Overwatch ingests new events/columns". — Session `c78da220` #60–#62.
2. **[VERIFIED]** The external question was explicitly scoped out at lock time: "External Overwatch-side consumption of the new event is a follow-up, out of this repo's scope" (Locked Decision 4); the write-plan session resolved the sync-state fork unilaterally as "YAGNI, external Overwatch is out-of-repo". — `ed5be46c` #16/#45.
3. **[VERIFIED]** OW-team guidance arrived 2 days later (George Perez, Slack 2026-07-10): "Adding new columns to OW tables for matching Cognito entities is done through OW sync. **We are phasing out classic events as much as possible.** … just rely on the sync process… The column gets added automatically." — `b7828015` #17.
4. **[VERIFIED]** Cost of the reversal: corrective Phase 10 deleted the Phase-1 event + the Phase-6 Cluster A emission-relocation hardening (built, tested, then deleted); the sibling SPEC `57077-overwatch-org-archived` — designed entirely around the `organization.archived` handler — was invalidated within ~24h of authoring (OW PR #678 drops the consumer). — PHASES.md:617-681; `d8f65201` #99; `b7828015` #71-73.
5. **[VERIFIED]** An earlier cross-team consultation impulse in the same feature was substituted with a code read: "someone must confirm **with the Overwatch team** that the downstream sync… doesn't purge the mirrored payment rows" → redirected to a local-repo investigative agent; the narrow question was answered, the broader convention question never asked. — `878aa447` #190/#191/#207.

## Reproduction Steps

1. Run `/spec` on a feature whose design needs a new cross-system signal (event, sync column, queue message, exported schema) consumed by another team's repo.
2. Observe Step 1b (dependency discovery, `user/skills/spec/SKILL.md:237-344`): the dep block captures **feature** dependencies only; nothing tags team-owned surfaces.
3. Observe the brainstorm/decision step: option menus present in-repo mechanism choices; there is no rule that an externally-consumed contract cannot be Locked on in-repo evidence, and no picker option to defer pending an owner check.
4. The decision locks; downstream skills treat it as settled.

**Expected:** a decision creating/changing an externally-consumed contract is tagged `external-owner: <team>` and is not lockable on in-repo evidence alone — either the owner's conventions are confirmed first, or the lock is recorded as "locked WITHOUT owner confirmation — risk accepted" via an explicit operator choice.
**Actual:** "acknowledged external dependency" degrades to "out of this repo's scope"; the lock proceeds silently. (Skill-audit Q4: NO PROVISION anywhere in the pipeline.)
**Consistency:** structural.

## Evidence Collected

### Serving-path trace (root cause — `traced`)

```
reversed Locked Decision 4 (+ invalidated sibling SPEC)
  → user/skills/spec/SKILL.md:237-344 (Step 1b dependency machinery) — mechanically searches
      FEATURE deps (SPEC cross-references, queue DAG); team-owned surfaces are not a dependency
      category, so no consultation obligation is ever generated            ← FIX SITE 1
  → user/skills/spec/SKILL.md (brainstorm/decision protocol) — options are resolved by in-repo
      evidence + operator pick; no rule distinguishes "in-repo reversible" decisions from
      "external-contract" decisions requiring owner confirmation            ← FIX SITE 2
  → c78da220 #61 — the AskUserQuestion whose own option text named the external contract change,
      with no consult path offered (the observable failure at the surface)
  → repos/cognito-forms/Cognito/CLAUDE.local.md — carries no record of the OW convention
      ("columns via OW sync; classic events being phased out"), so nothing in context could have
      warned either                                                          ← FIX SITE 3
```

Fix-site-on-path: yes — the decision protocol that locked LD4 is authored in `spec/SKILL.md`; the missing repo knowledge belongs in the Cognito `CLAUDE.local.md` that was in context at decision time.

## Proven Findings

1. The tell was present *in the option text itself* — the gate need only key on the model's own "external contract change" recognition; no new detection capability is required.
2. No party ever said "we should have asked earlier"; the framing throughout was "a bounded ask from an external team" — i.e., without a rule, this recurs silently.
3. Two layers are needed: a generic protocol rule (any repo) + repo-specific convention knowledge (Cognito/OW), because the generic rule only defers the lock — the knowledge line prevents the wrong default from even being drafted.

## Affected Area

| Component | Files | Impact |
|-----------|-------|--------|
| Spec decision protocol | `user/skills/spec/SKILL.md` | no external-owner rule (SEQUENCED AFTER sibling bug's edits to the same file) |
| Cognito repo knowledge | `repos/cognito-forms/Cognito/CLAUDE.local.md` | missing OW-sync/classic-events convention |

## Fix Scope (locked with operator, 2026-07-10)

1. **`user/skills/spec/SKILL.md` — external-owner surface rule** (in the decision/brainstorm protocol, near the Locked Decisions contract): when a candidate decision creates or changes a contract consumed outside this repo (events, sync schemas, queues, exported columns/APIs), tag it `external-owner: <team/repo>`. Such a decision is NOT lockable on in-repo evidence alone: either (a) the owning team's current conventions are confirmed (Slack/ADO/docs, cited in the SPEC) before the lock, or (b) the operator explicitly picks a "lock WITHOUT owner confirmation — risk accepted" option, recorded verbatim in the Locked Decision. The trigger is the model's own recognition — if an option's honest description contains "external contract change" / "other-team work", the rule fires. Name 57077 LD4 as the anti-pattern.
2. **`repos/cognito-forms/Cognito/CLAUDE.local.md` — convention line:** Overwatch surfaces new Cognito columns via OW **sync** (`[Overwatch]` attribute mirroring); classic CognitoEvents are being **phased out** — consult the OW team before adding a new classic event (source: OW team, Slack 2026-07-10).

**Implementation ordering:** shares `user/skills/spec/SKILL.md` with `premise-contradictions-demoted-not-escalated` — one writer per file: implement AFTER that bug's edits land.

## Open Questions

- (none — fix scope locked)
