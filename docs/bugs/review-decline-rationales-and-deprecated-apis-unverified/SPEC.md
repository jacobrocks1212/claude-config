# Review Decline Rationales and Deprecated-API Introductions Unverified — Investigation Spec

> `/resolve-review` independently validates a reviewer's *findings* but never validates the pipeline's own *decline rationales*, and no gate anywhere checks that net-new code avoids `[Obsolete]` surfaces — so 57077 Phase 9 declined an async ask with a factually wrong rationale that missed the `[Obsolete]` attribute pointing at the exact fix, and the branch shipped a net-new caller of a deprecated API on the precise axis under review (→ corrective Phase 12).

**Status:** Fixed
**Fixed:** 2026-07-10 — implemented out-of-pipeline (operator-directed subagent orchestration; fix scope in this SPEC)
**Severity:** P2
**Discovered:** 2026-07-10
**Placement:** docs/bugs/review-decline-rationales-and-deprecated-apis-unverified
**Related:** 57077 case study (Phases 9, 12), `repos/cognito-forms/.claude/skills/resolve-review/SKILL.md`, `repos/cognito-forms/.claude/skills/write-plan-cognito/lane-agent-briefing.md`

---

## Verified Symptoms

1. **[VERIFIED]** Phase 9 evaluated Taylor's "Can this be async?" ask on `GetRetainedCognitoPayAccounts` and documented "left synchronous… no async non-generic `Query(Type)` overload… this is the sanctioned resolution, not an omission." The rationale was factually wrong in the way that mattered: `IStorageContext.Query<T>()` is `[Obsolete("Consider using GetAll or GetRange.")]` (`IStorageContext.cs:159`), and the obsoletion message names the async surface (`GetAll<T>`) that IS the fix. — IMPLEMENTATION_NOTES.md:311; PHASES.md:740-749 (Phase 12).
2. **[VERIFIED]** The decline shipped as a documented PR-thread rationale (PR_REVIEW_REPLIES.md §3) and was reversed by Phase 12, whose context block states: "That rationale missed that `Query<T>` is deprecated… the fix is not a non-generic Query overload; it is to stop using Query at all in favor of the (generic, async) `GetAll<T>` the obsoletion notice recommends." — PHASES.md:745-749.
3. **[VERIFIED]** The branch had introduced the deprecated-API usage itself ("net-new in this PR… we are adding a new caller of a deprecated sync API on the precise axis under review") with no gate flagging it at implement or review time. — PHASES.md:745.
4. **[VERIFIED]** Skill-text audit: `/resolve-review` Step 3 validation is finding-existence-oriented and front-loaded before the decline; "Won't fix" only "record[s] the rationale" (SKILL.md:81); `minor`/`nit` findings are "carried forward as-is without independent validation" (:46). No `[Obsolete]`/CS0612/CS0618 check exists in any workflow skill (Q6: NO dedicated provision; the cognito-pr-review rule corpus can surface it only via the ~5-rule-capped guardrail lottery).

## Reproduction Steps

1. Run `/resolve-review` on a PR review containing a low-severity code ask (e.g. "can this be async?").
2. At Step 4, choose a decline path (or accept a "leave as-is with documented rationale" resolution); the rationale makes a factual code claim ("no async overload exists").
3. Observe: no validation pass re-checks the rationale's factual claims against the code; the reply is drafted from the unverified rationale.
4. Separately: have a lane agent introduce a call to an `[Obsolete]`-attributed member; run the Tier-1/Tier-2 gates.
5. Observe: nothing flags the new deprecated-API caller (build warnings CS0612/CS0618 are not scanned for changed files).

**Expected:** (a) any decline/defer rationale making a factual code claim gets the same subagent validation as findings, before the reply is drafted; (b) net-new callers of `[Obsolete]` members in changed files are flagged at the lane/part gate.
**Actual:** declines are recorded verbatim and never re-checked; deprecated-API introductions pass silently.
**Consistency:** structural.

## Evidence Collected

### Serving-path trace (root cause — `traced`)

```
wrong decline shipped to PR thread + net-new [Obsolete] caller shipped on the branch
  → repos/cognito-forms/.claude/skills/resolve-review/SKILL.md:42-46 — validate: yes only for
      critical/important/latent; minor/nit "carried forward as-is"          ← FIX SITE 1
  → resolve-review/SKILL.md:52-69 — Step 3 Sonnet validation targets the FINDING's reality
      (Confirmed/Refuted), runs BEFORE any decline exists; nothing revisits the decline
  → resolve-review/SKILL.md:81 — "Won't fix — record the rationale (capture the user's note)";
      the rationale is held for the report, never validated                  ← FIX SITE 2
  → repos/cognito-forms/.claude/skills/write-plan-cognito/lane-agent-briefing.md +
      execution-contract-cognito-lanes.md:228-236 (Tier gates) — no changed-file scan for
      CS0612/CS0618 / new [Obsolete] callers                                 ← FIX SITE 3
```

Fix-site-on-path: yes — the decline path and the gate checklist are the code that let both defects ship.

## Proven Findings

1. The decline's wrong claim was one attribute-read away — the validation machinery that would have caught it already exists in Step 3; it is simply never pointed at declines.
2. The compiler already emits the deprecation signal (CS0612/CS0618); the gate need only scan it for changed files — no new analysis capability required.

## Affected Area

| Component | Files | Impact |
|-----------|-------|--------|
| Review resolution | `repos/cognito-forms/.claude/skills/resolve-review/SKILL.md` | declines unvalidated |
| Lane gates | `repos/cognito-forms/.claude/skills/write-plan-cognito/lane-agent-briefing.md` | no deprecated-API check (NOTE: file has unrelated uncommitted edits in tree — edit on top, do not revert) |

## Fix Scope (locked with operator, 2026-07-10)

1. **`resolve-review/SKILL.md` — decline-rationale validation:** any resolution other than "Fix now" (Won't fix / Defer / leave-as-is) whose rationale makes a **factual code claim** ("no async overload exists", "X is unreachable", "already handled by Y") gets the same Sonnet validation pass as findings — verify the claim against the live code (including attribute-level facts like `[Obsolete]` messages) BEFORE the rationale is recorded or a PR reply is drafted. A refuted rationale re-opens the resolution question. Name the 57077 Phase-9 "left synchronous" decline as the anti-pattern.
2. **`lane-agent-briefing.md` — deprecated-API rule:** net-new code must not add callers of `[Obsolete]`/deprecated members. Lane self-check: before reporting, scan the lane's changed files' build output for CS0612/CS0618 (or grep the newly-called members' declarations for `[Obsolete]`); a hit is a defect to fix or explicitly escalate — never silent. Keep it compact (a briefing bullet, not a new tier).

## Open Questions

- (none — fix scope locked)
