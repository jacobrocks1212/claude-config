# Cycle subagents violate the turn-end contract — uncommitted deliverables, unticked plan boxes, half-flipped frontmatter — Investigation Spec

> Across multiple `/lazy-batch` runs, cycle subagents do the real work but fail to finish the turn cleanly: deliverables are left uncommitted (HEAD unchanged), PHASES.md/plan-file checkboxes are left unticked, and SPEC/plan frontmatter is flipped to Complete without the body ledger being reconciled. The `verify-ledger` step catches these every time, but each catch forces an extra recovery-cycle dispatch — pure meta overhead. This was the most consistent cross-session friction pattern in the audit.

**Status:** Concluded
**Severity:** P1
**Discovered:** 2026-06-19
**Placement:** docs/bugs/cycle-subagent-leaves-work-uncommitted-or-unticked
**Source:** `/lazy-batch` session-log audit 2026-06-19 (AlgoBooth — 19 sessions, last 2 weeks)
**Related:** `user/skills/_components/lazy-batch-prompts/cycle-base-prompt.md` (`turn-end` section — the contract); `user/skills/lazy-batch/SKILL.md` Step 1e.4a (post-cycle ledger guard + recovery dispatch); `user/scripts/lazy_core.py` `verify_ledger` + `detect_cycle_bracket_friction`; `user/skills/_components/lazy-batch-prompts/dispatch-recovery.md`. Sibling friction items: `docs/bugs/cycle-subagent-leaves-work-uncommitted-or-unticked`'s peers under `docs/bugs/` (cycle-subagent-* family).

---

## Verified Symptoms

<!-- "VERIFIED" here = directly evidenced in session logs (the audit is the ground truth for this harness-repo bug; there is no interactive user to confirm against in --batch). -->

1. **[VERIFIED]** Truncated cycle committed WU-1 but left WU-2's residue uncommitted (DEFERRED_NON_CLOUD.md, PHASES.md, the mcp-tests entry, the plan-Complete flip) — session `deb9f0cf` @ `2026-06-16T23:37:34Z`. A *partial* commit within one cycle.
2. **[VERIFIED]** Write-plan cycle left its deliverable uncommitted with HEAD unchanged (`?? phase-9-analyzer-subscribe-wire.md`, HEAD still at 5b79bafc) — session `5d4b6c93` @ `2026-06-17T04:59:23`.
3. **[VERIFIED]** Execute-plan subagent flipped frontmatter Complete but did not tick body boxes (the `deliverables_done` failure) — session `5d4b6c93` @ `2026-06-17T14:25:19`.
4. **[VERIFIED]** Plan ledger left half-flipped — plan-file frontmatter `In-progress` with 5 unticked plan-file boxes despite all three WUs landing; PHASES.md deliverables ticked but the plan ledger left stale — session `61d6ddcf` @ `2026-06-09T17:14:42`.
5. **[VERIFIED]** Orphaned cycle left an entire cycle's output uncommitted (fix `looper/voice.rs` + a new storm regression test + scenario doc updates + WU checkboxes); HEAD == origin so nothing of the cycle was committed — session `5c33b6ba` @ `2026-06-11T19:11:45`.

## Reproduction Steps

1. Dispatch a cycle subagent (`/execute-plan`, `/write-plan`, `/mcp-test`, or a bug-pipeline analog) via `/lazy-batch`.
2. The subagent performs the real work (edits source/tests/docs, may commit some artifacts).
3. The subagent's turn ends — either truncated mid-sequence (token/length limit, an auto-backgrounded gate that died) or after self-asserting "done" without walking the pre-return checklist.
4. **Observed:** the working tree is dirty / HEAD is unpushed / plan-file boxes are unticked / plan frontmatter is half-flipped. The orchestrator's Step 1e.4a `--verify-ledger` guard catches it and dispatches a **recovery cycle** (a `meta_cycles` dispatch).

**Expected:** the cycle returns a clean, consistent ledger in-turn — `git status --short` empty, branch pushed, plan/PHASES checkboxes reconciled to the work that landed — so the orchestrator's guard reports `ok` and no recovery dispatch is needed.
**Actual:** a clean return is the *exception*; the post-cycle guard catches residue often enough that the recovery dispatch is recurring meta overhead (≥5 distinct sessions in one audit window).
**Consistency:** intermittent per-cycle, but consistent enough across sessions to be the single most-recurring audit friction pattern. Strongly correlated with turn truncation and with multi-artifact "completion" cycles (final execute-plan batch, mark-complete-adjacent flips).

## Evidence Collected

### Source Code

The harness already has BOTH halves it needs — a fully-specified contract AND a deterministic detector — but they are wired **post-hoc**, never as an in-turn gate the subagent must clear before returning.

- **The contract is specified** in `cycle-base-prompt.md` → `@section turn-end` (workstation + cloud variants, lines ~388-423). It states the rule (atomic gate+commit R5) and a **pre-return checklist** (item 3): `(a) no background job still running; (b) git status --short EMPTY; (c) branch pushed; (d) result sentinel / plan-PHASES flip ON DISK`. This is **prose the subagent is asked to self-walk** — nothing executes it. A truncated turn never reaches it; a hasty turn skips it. The checklist is the ONE sanctioned restatement (per the rule inventory header) but it is advisory, not gated.
- **The detector exists** in `lazy_core.py`:
  - `verify_ledger(repo_root, spec_path, plan_path)` (line ~1970) computes the four ledger checks — `clean_tree`, `head_matches_origin`, `plan_complete`, `deliverables_done` — and is exposed as `--verify-ledger`. This is EXACTLY the machine form of the pre-return checklist.
  - `detect_cycle_bracket_friction(...)` (line ~6612) flags a torn cycle bracket / unexpected commits at `--cycle-end`.
- **But the detector runs in the ORCHESTRATOR's turn, after the subagent has already returned** — `lazy-batch/SKILL.md` Step 1e.4a (lines ~770-803): "*The cycle subagent is supposed to leave a clean, consistent ledger via the atomic gate+commit ... but it empirically loses its turn between gates and commit — this guard catches the residue deterministically instead of relying on operator memory.*" On a failing check the orchestrator emits a **recovery dispatch** (`--emit-dispatch recovery` → `dispatch-recovery.md`), which is a whole extra subagent round-trip whose entire job is to stage+commit+push residue or tick a box.

The structural gap: the subagent CAN run `--verify-ledger` itself (it is a read-only command available to a dispatched subagent — confirmed in `user/scripts/CLAUDE.md`: "`--neutralize-sentinel`/`--verify-ledger` + all reads stay callable (a dispatched subagent needs them)"), but the turn-end contract never **tells it to run the check as the final pre-return action**. The checklist is phrased as something to *mentally verify*, not a command to *execute and gate on*. So the same deterministic verdict the orchestrator computes one step later is never computed in-turn where it would let the subagent self-correct before the costly recovery dispatch.

### Runtime Evidence

Five session-log excerpts (Verified Symptoms 1-5 above), spanning 2026-06-09 → 2026-06-17, across distinct features/bugs and distinct sub-skills (`/execute-plan`, `/write-plan`, mark-complete-adjacent). The pattern is sub-skill-agnostic — it is a turn-boundary failure, not a per-skill logic bug.

### Git History

No single regression commit introduced this — it is an absence (a missing in-turn gate), not a defect introduced by a change. The recovery machinery (`verify_ledger`, `dispatch-recovery.md`, Step 1e.4a) was ADDED as a *post-hoc* mitigation (harness-hardening-retro-fixes / hardening-blind-to-process-friction phases), which is why the symptom persists: the mitigation absorbs the cost (recovery dispatch) rather than preventing the cause (no in-turn gate).

### Related Documentation

- `user/scripts/CLAUDE.md` → "Completion is receipt-gated", "`--verify-ledger`" CLI surface, "Cycle-counter advance" — documents the recovery path as `meta_cycles` (uncapped) overhead.
- `cycle-base-prompt.md` rule-inventory header (R5 atomic gate+commit, R13 turn-end contract) — confirms the contract is authored once, in prose.
- `dispatch-recovery.md` — the recovery subagent template; its existence is the cost this bug imposes.

## Theories

### Theory 1: Contract is specified but unenforced at the turn boundary (CONFIRMED)
- **Hypothesis:** the turn-end contract is fully written but exists only as prose the subagent self-polices; there is no deterministic in-turn gate, so truncation or haste lets a dirty ledger return, and enforcement is deferred to the orchestrator's post-cycle `--verify-ledger` guard which pays for it with a recovery dispatch.
- **Supporting evidence:** the contract prose (`turn-end` section) IS present and detailed; the identical machine check (`verify_ledger`) IS present but invoked by the ORCHESTRATOR at Step 1e.4a, not by the subagent before return; Step 1e.4a's own comment says the subagent "empirically loses its turn between gates and commit"; the subagent has read access to `--verify-ledger` but is never instructed to run it as its terminal action.
- **Contradicting evidence:** none. The recovery machinery's existence is itself proof the contract is not self-enforcing.
- **Status:** Confirmed.

### Theory 2: Partial commits come from non-atomic multi-artifact completion sequences (CONFIRMED)
- **Hypothesis:** within-cycle partial commits (Symptom 1) occur because a "completion" cycle has SEVERAL artifacts to land (state doc + plan ledger + mcp-tests entry + Complete flip) committed across multiple steps rather than one atomic gate+commit, so a turn that dies mid-sequence strands the rest.
- **Supporting evidence:** Symptom 1 lists exactly such a multi-artifact residue after WU-1 committed; R5 (atomic gate+commit) is specified as ONE chained command but only for the *gate/test/build* final action — the non-gated reconciliation writes (tick boxes, flip plan status, write sentinel) are NOT folded into that one atomic command, so they are separate, individually-abortable steps.
- **Contradicting evidence:** none material — even a single atomic gate+commit cannot protect writes issued after it, which is why an in-turn verify-then-finalize ordering (not just "commit the gate atomically") is needed.
- **Status:** Confirmed.

### Theory 3: The pre-return checklist is unreachable on truncation (CONFIRMED, sub-case of T1)
- **Hypothesis:** because the checklist sits at the END of the prompt ("read LAST because it is checked LAST") and is self-walked, a turn truncated before reaching it never runs it; ordering it last guarantees it is the first thing dropped under length pressure.
- **Supporting evidence:** Symptoms 2 and 5 are pure truncation/orphan cases (HEAD unchanged, entire cycle uncommitted) — the checklist plainly never ran.
- **Status:** Confirmed (refines T1 — the placement makes the advisory checklist maximally fragile exactly when it is most needed).

## Proven Findings

1. **Root cause: no in-turn deterministic turn-end gate.** The turn-end contract is fully specified (`cycle-base-prompt.md` `turn-end` section) and a deterministic verifier of that exact contract exists (`lazy_core.verify_ledger`, exposed as `--verify-ledger`, callable by subagents), but the subagent is never instructed to RUN the verifier as its final pre-return action. Enforcement is purely post-hoc in the orchestrator (Step 1e.4a), which pays for every miss with a `recovery` subagent dispatch.
2. **The mitigation absorbs cost rather than preventing cause.** The recovery dispatch path (`dispatch-recovery.md` + `--emit-dispatch recovery`) reliably *repairs* the residue, but each repair is an extra (uncapped `meta_cycles`) round-trip — the recurring overhead this bug is about.
3. **Partial-commit sub-class needs verify-before-finalize ordering, not just atomic gate+commit.** R5's single chained gate+commit cannot protect reconciliation writes issued after the gate; the fix must order the in-turn self-check so the subagent verifies AND finalizes (commit + push + box ticks) as the last action, then re-checks clean before returning.
4. **Checklist placement amplifies fragility.** Ordering the pre-return checklist last (so it is the first content dropped under truncation) makes the only existing safeguard maximally likely to be skipped exactly in the truncation cases (Symptoms 2, 5).

## Fix Scope

The fix is a **harness contract + prose change in the cycle prompt**, NOT a state-machine logic change (the verifier already exists). Files in scope:

| Component | Change | Why |
|-----------|--------|-----|
| `user/skills/_components/lazy-batch-prompts/cycle-base-prompt.md` (`@section turn-end`) | Convert the pre-return checklist from *self-walked prose* into a **mandatory executed command**: the subagent's final action MUST be to run `python3 ~/.claude/scripts/{lazy-state.py\|bug-state.py} --repo-root <cwd> --verify-ledger <spec_path> [--plan <plan_file>]`, and if `ok` is false, reconcile in-turn (commit/push residue, tick the landed WU boxes, flip plan status) and re-run until `ok` — only then return. This makes the in-turn gate deterministic, not advisory. | Theory 1 / Finding 1 — the verifier exists; the subagent just never runs it. |
| Same section | Reorder/duplicate the verify-and-finalize step so it is **issued as the atomic final action** (verify → reconcile → re-verify → return), not buried last as droppable prose; make "finalize all reconciliation writes (boxes, plan status, sentinel) BEFORE the terminal verify" explicit so post-gate writes can't strand. | Theories 2 + 3 / Findings 3 + 4. |
| `repos/algobooth/.claude/skills/lazy-batch-cloud/SKILL.md` (coupled pair) + the cloud `turn-end` variant | Mirror the change in the cloud variant (push-each-flip durability already present; add the same in-turn `--verify-ledger` terminal gate). | Coupling rule — `cycle-base-prompt.md` emits both; the cloud variant must stay in lockstep. |
| Orchestrator Step 1e.4a (`lazy-batch/SKILL.md`) | KEEP as the backstop (defense-in-depth — a truncated turn that never reaches the in-turn gate is still caught), but it should become the *exception* path rather than the routine one. No removal. | Finding 2 — the post-hoc guard stays; the in-turn gate removes the routine recovery dispatch. |

Out of scope (NOT this bug): the `verify_ledger` check logic itself (correct), the recovery subagent template (correct, stays as backstop), counter/accounting behavior. This is purely about giving the subagent the same deterministic check the orchestrator already runs, but IN-TURN, as its mandatory terminal action.

## Affected Area

| Component | Files | Impact |
|-----------|-------|--------|
| Cycle prompt contract | `user/skills/_components/lazy-batch-prompts/cycle-base-prompt.md` | Primary — turn-end section becomes an executed gate, not advisory prose. |
| Coupled cloud orchestrator | `repos/algobooth/.claude/skills/lazy-batch-cloud/SKILL.md` | Mirror — cloud turn-end variant. |
| Post-cycle guard (backstop) | `user/skills/lazy-batch/SKILL.md` Step 1e.4a | Unchanged logic; demoted from routine to exception path. |
| Deterministic verifier (reused, not changed) | `user/scripts/lazy_core.py` `verify_ledger` / `--verify-ledger` | Reused in-turn; no code change required. |
| Recovery template (backstop, unchanged) | `user/skills/_components/lazy-batch-prompts/dispatch-recovery.md` | Stays as the exception-path repair. |

## Open Questions

None blocking — root cause confirmed, fix scope is a deterministic prose/contract change reusing the existing verifier. Two design choices remain for `/plan-bug` to settle (both scope-class, not product-class — they do not change product behavior, only the fix's shape):
- Whether to ALSO promote the in-turn gate into a tiny shared helper the prompt references vs. inline command prose in the `turn-end` section (efficiency/maintainability choice; the projection pipeline already injects components, so a referenced helper stays DRY across the workstation/cloud variants).
- Whether the in-turn `--verify-ledger` should be appended to the existing R5 atomic chained command (`<gate> && ... && --verify-ledger`) or run as a separate final step after the chained commit (the latter is simpler and avoids a non-zero exit aborting the commit chain). These are sizing/sequencing only — `/plan-bug` takes the most-complete path.
