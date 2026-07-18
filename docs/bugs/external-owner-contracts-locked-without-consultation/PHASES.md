# Implementation Phases — External-Owner Contracts Locked Without Consultation

> Phases for [`SPEC.md`](./SPEC.md)

**MCP runtime:** not-required — docs/skills-only change (a prose decision-protocol rule in `user/skills/spec/SKILL.md` + a repo-convention line in `repos/cognito-forms/Cognito/CLAUDE.local.md`); no app runtime surface, no MCP-reachable behavior (mcp-testing SPEC "non-code / documentation" class).

## Validated Assumptions

- **Runtime Assumption Validation gate: SKIPPED — every load-bearing assumption is code-provable.** This fix adds prose to two markdown/skill files (a decision-protocol rule and a repo-knowledge line). There is no running system to observe, no boundary data shape, no user-facing serving path — the reachability axiom does not apply (the "surface" is a rule an LLM reads at `/spec` decision time, verifiable by reading the file). Nothing here is runtime-coupled.
- **Fix already landed out-of-pipeline (2026-07-10).** Both Fix Scope items are already present on disk, verified by grep at planning time:
  - `user/skills/spec/SKILL.md:401-410` — the **External-owner surface rule** (MANDATORY block, tags `external-owner: <team/repo>`, bans locking such a decision on in-repo evidence alone, offers the "lock WITHOUT owner confirmation — risk accepted" path, names the 57077 LD4 anti-pattern). Matches Fix Scope #1 verbatim.
  - `repos/cognito-forms/Cognito/CLAUDE.local.md:8` — the **Overwatch integration convention** line (new columns surface via OW sync / `[Overwatch]` mirroring; classic `CognitoEvent`s being phased out; consult OW team before adding one; source George Perez, Slack 2026-07-10). Matches Fix Scope #2 verbatim.
  - Consequence for execution: `/execute-plan` should **verify-and-tick**, not re-implement — the content is already correct. If a grep confirms the exact text below, the deliverable is satisfied.

## Touchpoint Audit Table (verified inline — dispatch not warranted for a 2-file docs fix already on disk)

| Planned file | Exists? | Real symbols (verified) | Action | Reuse / refactor directive |
|--------------|---------|-------------------------|--------|----------------------------|
| `user/skills/spec/SKILL.md` | yes | External-owner surface rule, lines 401–410 | verify (already done) | Rule already authored per Fix Scope #1 — confirm presence, do NOT duplicate. Shares this file with sibling bug `premise-contradictions-demoted-not-escalated` (one-writer-per-file). |
| `repos/cognito-forms/Cognito/CLAUDE.local.md` | yes | Overwatch integration convention, line 8 | verify (already done) | Convention line already authored per Fix Scope #2 — confirm presence, do NOT duplicate. |

## Cross-feature Integration Notes

No hard deps on Complete upstream *features*. There is a sibling **bug** ordering constraint (not a feature dep, so no `**Depends on:**` block projection): `user/skills/spec/SKILL.md` is shared with `premise-contradictions-demoted-not-escalated`. Per the SPEC's "Implementation ordering" note, the external-owner edit is sequenced AFTER that bug's edits land (one writer per file). Since the external-owner rule is already present on disk, that ordering has already been honored in the out-of-pipeline fix.

---

### Phase 1: External-owner consultation gate + Cognito OW-sync convention knowledge

**Scope:** Close the "external-owner contract locked without consultation" gap with the two-layer fix the investigation proved is required (Proven Finding #3): (a) a generic decision-protocol rule in `/spec` that refuses to lock an externally-consumed contract on in-repo evidence alone, and (b) a Cognito-specific repo-knowledge line so the wrong default (a new classic CognitoEvent) is never even drafted. Both edits are prose additions; both are already present on disk from the 2026-07-10 out-of-pipeline fix — this phase's execution VERIFIES their presence and content rather than re-authoring.

**Deliverables:**
- [x] `user/skills/spec/SKILL.md` carries the **External-owner surface rule** in the decision/brainstorm protocol: a candidate decision that creates or changes a contract consumed OUTSIDE this repo (events, sync schemas, queue messages, exported columns/APIs) is tagged `external-owner: <team/repo>` and is NOT lockable on in-repo evidence alone — either (a) the owning team's current conventions are confirmed (cited in the SPEC) before the lock, or (b) the operator explicitly picks a "lock WITHOUT owner confirmation — risk accepted" option, recorded verbatim in the Locked Decision. Trigger keys on the model's own recognition ("external contract change" / "other-team work" / "downstream consumer"). The 57077 LD4 anti-pattern is named. (Verified present at lines 401–410.)
- [x] `repos/cognito-forms/Cognito/CLAUDE.local.md` carries the **Overwatch integration convention** line: new Cognito columns surface in Overwatch via OW **sync** (`[Overwatch]` attribute mirroring — added automatically); classic `CognitoEvent`s are being **phased out** — consult the OW team before adding a new classic event (source: OW team / George Perez, Slack 2026-07-10). (Verified present at line 8.)
- [x] Tests: no automated test — these are prose rules an LLM reads at decision time (a SKILL.md protocol rule + a repo-knowledge line). Verification is a grep confirming each text is present and a read confirming the rule's semantics match Fix Scope #1/#2 (see Testing Strategy). No unit/integration test is applicable or authored.

**Minimum Verifiable Behavior:** `grep -n "external-owner" user/skills/spec/SKILL.md` returns the rule block, and `grep -ni "phased out\|OW sync\|Overwatch.*sync" repos/cognito-forms/Cognito/CLAUDE.local.md` returns the convention line — both already true on disk. (This fix has no runtime-observable surface; the "behavior" is a rule present in the file for the model to consult, which grep proves directly.)

**MCP Integration Test Assertions:** N/A — no runtime-observable behavior in this phase (prose rule + repo-convention line; nothing crosses a process/IPC/serialization boundary).

**Prerequisites:** None (single-phase fix). Ordering constraint on the shared `spec/SKILL.md` (sibling bug `premise-contradictions-demoted-not-escalated`) already honored by the out-of-pipeline fix.

**Files likely modified:**
- `user/skills/spec/SKILL.md` — External-owner surface rule (already present, lines 401–410; verify, do not duplicate)
- `repos/cognito-forms/Cognito/CLAUDE.local.md` — Overwatch integration convention line (already present, line 8; verify, do not duplicate)

**Testing Strategy:**
Docs/skills prose — no runtime harness. Verify in isolation by (1) grepping each file for the required text, and (2) reading the surrounding context to confirm the rule's semantics match Fix Scope #1 (tag + non-lockable-on-in-repo-evidence + risk-accepted escape hatch + 57077 anti-pattern named) and Fix Scope #2 (OW sync mechanism + classic-events-being-phased-out + consult-first + Slack source cited). Because both edits are already on disk, execution is a confirmation pass: if the greps hit and the semantics match, tick the deliverables; if any text is missing, author it per the Fix Scope wording (one writer per file — respect the sibling-bug ordering on `spec/SKILL.md`).

**Integration Notes for Next Phase:**
- No next phase — this is the terminal (and only) phase. Implementation is complete on disk; the pipeline's job here is verification + reconciliation, then routing to the validation tail. The gate owns the final Status flip.

**Completion (gate-owned):** the `__mark_fixed__` gate flips SPEC.md **Status:** to `Fixed`, writes `FIXED.md`, and archives once this phase's deliverables are verified and the validation tail passes. Do NOT author a Status-flip / receipt-write / archive checkbox row.

---
