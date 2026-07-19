# Orchestrator Redundant-Recovery on Background-Suite Re-invoke — Investigation Spec

> A cycle /execute-plan subagent backgrounds its long verification suite and returns "holding, will re-invoke" instead of foreground-awaiting; the orchestrator, unable to distinguish that pause from a resultless return, dispatches a redundant recovery cycle that collides (one-writer) with the harness-re-invoked agent.

**Status:** Investigating
**Severity:** P1
**Discovered:** 2026-07-19
**Placement:** docs/bugs/adhoc-orchestrator-redundant-recovery-on-background-suite-reinvoke
**Related:** `user/skills/_components/dispatched-agent-liveness.md` · `user/skills/_components/turn-end-gate.md` · `user/skills/_components/lazy-batch-prompts/cycle-base-prompt.md` (turn-end §1) · `docs/specs/turn-routing-enforcement/` (dispatched-agent liveness decision #12, HARD-PARKED)

<!-- Status lifecycle:
  - Investigating → active investigation; root cause not yet locked OR a human decision is
    still required before planning. bug-state.py routes to /spec-bug.
  - Concluded → root cause proven AND fix direction settled; bug-state.py routes to /plan-bug.
  This SPEC's root cause is TRACED (see Proven Findings), but the fix-APPROACH is a baseline-
  gating product fork surfaced to the operator in NEEDS_INPUT.md — hence Status stays
  Investigating (pre-conclusion, stub_origin) until the operator picks the fix direction.
-->

---

## Verified Symptoms

<!-- Batch/park-mode run: no AskUserQuestion is permitted, so these are labeled REPORTED
     from the first-hand run observation captured in ADHOC_BRIEF.md (the operator watched the
     incident happen twice this run), not upgraded to VERIFIED via an interactive round. -->

1. **[REPORTED]** A cycle `/execute-plan` subagent backgrounded its long verification suite and returned a non-result — e.g. *"suite at 44%, the background waiter will re-invoke me, holding"* — instead of foreground-awaiting it. Observed **twice** in one run. Source: `ADHOC_BRIEF.md` (operator run observation).
2. **[REPORTED]** The orchestrator, receiving that "holding, will re-invoke" return with a **dirty working tree**, could not distinguish a *will-re-invoke hold* from a *genuine resultless/terminal return*, and dispatched a redundant `--emit-dispatch recovery` cycle. Source: `ADHOC_BRIEF.md`.
3. **[REPORTED]** The recovery cycle overlapped the harness-re-invoked `/execute-plan` agent on the **same files** — a one-writer-per-file violation; the recovery had to be `TaskStop`-ped. In the process-friction case the harness *did* re-invoke the original agent on suite completion and it finished cleanly. Source: `ADHOC_BRIEF.md`.

## Reproduction Steps

<!-- Followable recipe binding the completion-time symptom-reproduction gate. The trigger is an
     over-cap aggregate gate inside a dispatched cycle subagent; the two coupled defects then
     compose deterministically. -->

1. Run `/lazy-batch` (or `/lazy-bug-batch`) on a feature/bug whose `/execute-plan` batch ends in an **aggregate verification suite that exceeds the ~10-min Bash cap** (so the harness auto-backgrounds it).
2. The dispatched `/execute-plan` cycle subagent launches the aggregate gate; it auto-backgrounds; the subagent ends its turn returning a "suite at N%, the background waiter will re-invoke me, holding" summary (its `Agent`-tool result to the orchestrator) with an uncommitted (dirty) tree.
3. The orchestrator enters its post-cycle path (`lazy-batch/SKILL.md` Step 1e → guardrail D at 4a), fetches, and runs `--verify-ledger`; `clean_tree` fails on the dirty tree; it emits `--emit-dispatch recovery` and dispatches the recovery agent.
4. Meanwhile the harness re-invokes the backgrounded `/execute-plan` agent when its suite completes.

**Expected:** The orchestrator either never sees a "holding" return (the subagent foreground-awaits its gate), OR it detects the paused/will-re-invoke agent deterministically and does NOT dispatch recovery — so exactly one writer touches the plan's files.
**Actual:** Two writers (recovery agent + re-invoked execute-plan agent) run concurrently on the same files; the recovery must be `TaskStop`-ped.
**Consistency:** Reproduced twice in one run; deterministic given an over-cap aggregate gate in a cycle subagent.

## Evidence Collected

### Source Code

**The foreground-await mandate exists but is prose-only (Gap 1).**
- `user/skills/_components/lazy-batch-prompts/cycle-base-prompt.md`, `@section turn-end` item 1 (≈L648–657): *"Never background a long gate from inside this cycle subagent — its process tree is torn down when your turn ends… PREVENT the auto-background… Run its individual UNDER-cap sub-components synchronously in the foreground instead."* This is the exact contract the subagent violated. There is **no mechanical enforcement** — nothing denies a `run_in_background` gate launched inside a cycle subagent.
- `user/skills/_components/turn-end-gate.md` L23–30 repeats the same over-cap-aggregate prevention rule for any dispatched agent.

**The orchestrator's synchronous-await path has no pause-vs-terminal discriminator (Gap 2).**
- `user/skills/lazy-batch/SKILL.md` Step 1e L982 — *"After the subagent returns:"* — treats the returned `Agent` result as a completed cycle unconditionally.
- Guardrail D (4a) L989–1024: it fetches, runs `--verify-ledger`, and on `clean_tree`/`head_matches_origin` failure (L1006) emits `--emit-dispatch recovery` (L1012–1024). No step consults whether the just-returned agent is *paused and about to be re-invoked* before dispatching recovery.

**The receiver-side discriminator already exists — but only for the notification path.**
- `user/skills/_components/dispatched-agent-liveness.md` L29–42 defines the AUTHORITATIVE completion signal: the `/execute-plan` run marker (`~/.claude/state/execute-plan/<md5(repo_root)[:12]>.json`) present ⇒ NOT done, combined with plan frontmatter `status:`. L43–56 give the decision procedure: marker present ⇒ orchestrator is PAUSED, not done → do NOT `TaskStop`, do NOT edit its files, do NOT act on its dirty tree. This is precisely the signal Gap-2's recovery path lacks — but the component governs the `<task-notification>` `completed` case, NOT the awaited-`Agent`-result path Step 1e uses.
- `user/skills/execute-plan/SKILL.md` Step 1d L103–111 writes that run marker at execution start; L190 removes it only at genuine completion / halt. So the marker IS present (and consultable) throughout a paused/backgrounded cycle.

### Runtime Evidence
`ADHOC_BRIEF.md`: two occurrences in one run; the re-invoked agent finished cleanly in the process-friction case; the redundant recovery required a manual `TaskStop`. (First-hand operator run observation.)

### Git History
Recent commits are canary/incident-flush and hook-revocation housekeeping (`cde04dd5`, `2f02797f`, `563c6231`); none touch the orchestrator post-cycle path or the cycle turn-end contract. This is a latent design gap, not a regression from a recent edit.

### Related Documentation
- `dispatched-agent-liveness.md` — the receiver-side "a `completed` notification is not proof of completion" contract; its authoritative-signal recipe is directly reusable by Gap 2.
- `turn-end-gate.md` — the sender-side in-flight-work gate; source of the contradiction below.

## Theories

### Theory 1: The foreground-await mandate is prose-only and gets violated because backgrounding empirically "works" — Confirmed
- **Hypothesis:** Cycle subagents background over-cap aggregate gates despite the ban because the harness re-invokes them on background completion, so the ban's stated deterrent ("your process tree is torn down") is contradicted by observed behavior.
- **Supporting evidence:** `ADHOC_BRIEF.md` states the harness DID re-invoke the agent and the suite finished cleanly. `turn-end-gate.md` L13–18 explicitly claims dispatched agents CANNOT get background-completion re-invocation ("Only a top-level interactive session gets background-completion re-invocation; never rely on it from inside any `Agent` dispatch") — yet the run shows re-invocation happening for a dispatched cycle subagent. The contract's premise and the observed behavior conflict.
- **Contradicting evidence:** None observed; the contradiction may be that cycle subagents run at a dispatch depth/mode that does receive re-invocation, or that the behavior is inconsistent/undocumented.
- **Status:** Confirmed (the mandate exists, is prose-only, and was violated; the re-invocation contradiction is documented and load-bearing for fix selection).

### Theory 2: The orchestrator lacks a deterministic pause-vs-terminal signal on the synchronous-await path — Confirmed
- **Hypothesis:** Step 1e/guardrail-D dispatches recovery on any dirty-tree `--verify-ledger` failure without checking whether the returned cycle agent is paused-and-will-re-invoke, causing the dual-writer race.
- **Supporting evidence:** Serving-path trace below — recovery dispatch (L1006/L1012–1024) has no upstream pause check; the discriminator that WOULD prevent it (`dispatched-agent-liveness.md`'s marker+status signal) is wired only to the notification path, not to Step 1e.
- **Contradicting evidence:** None.
- **Status:** Confirmed.

## Proven Findings

**Root cause = two coupled defects, both `traced`:**

**Serving-path trace for the redundant-recovery symptom (Symptom 2/3):**
```
symptom: orchestrator dispatches redundant recovery that collides with the re-invoked agent
  → --emit-dispatch recovery dispatched          user/skills/lazy-batch/SKILL.md:1012-1024
  → guardrail D routes clean_tree failure → recovery   user/skills/lazy-batch/SKILL.md:1006
  → guardrail D runs unconditionally post-return       user/skills/lazy-batch/SKILL.md:989 (entered from :982)
  → returned Agent result was a "holding, will re-invoke" PAUSE, not terminal,
    but Step 1e has NO pause-vs-terminal discriminator on the await path
      ← the discriminator EXISTS but only for the notification path:
        user/skills/_components/dispatched-agent-liveness.md:29-56
      ← the authoritative signal it prescribes is available on disk throughout the pause:
        execute-plan run marker written at  user/skills/execute-plan/SKILL.md:103-111,
        removed only at completion/halt      user/skills/execute-plan/SKILL.md:190
```
Fix-site-on-path (Gap 2): a pause-vs-terminal check inserted in `lazy-batch/SKILL.md` Step 1e/4a BEFORE the recovery emit (L1006/L1012), consulting the execute-plan run marker + plan `status:` per `dispatched-agent-liveness.md` — this node is *on* the traced path (it gates the read that produces the recovery dispatch). `traced`.

**Serving-path trace for the backgrounding symptom (Symptom 1):**
```
symptom: cycle /execute-plan subagent returns "holding, will re-invoke" on a backgrounded suite
  → over-cap aggregate gate auto-backgrounded inside the cycle subagent's turn
  → foreground-await mandate is prose-only, no mechanical enforcement:
       user/skills/_components/lazy-batch-prompts/cycle-base-prompt.md turn-end §1 (≈:648-657)
       user/skills/_components/turn-end-gate.md:23-30
  → mandate's deterrent ("process tree is torn down") contradicted by observed re-invocation:
       user/skills/_components/turn-end-gate.md:13-18  vs  ADHOC_BRIEF.md run observation
```
Fix-site-on-path (Gap 1): the enforcement seam for "no backgrounded long gate in a cycle subagent" (a guard/hook, or a hardened contract) sits on the path that produces the "holding" return. `traced`.

**Why the two are coupled:** Gap 1 produces the ambiguous "holding" return; Gap 2 mis-handles it. The harness's re-invocation of the dispatched agent (contradicting `turn-end-gate.md` L13–18) is what turns the mis-handling into an *active collision* rather than a harmless redundant no-op — the re-invoked agent and the recovery agent both write.

**Runtime-coupled note:** the re-invocation-races-recovery timing is runtime-coupled; it is backed by the first-hand run observation in `ADHOC_BRIEF.md` (two occurrences), not by static reading alone.

## Affected Area

| Component | Files | Impact |
|-----------|-------|--------|
| Orchestrator post-cycle recovery dispatch (Gap 2, load-bearing) | `user/skills/lazy-batch/SKILL.md` Step 1e/4a (L982, L989–1024); coupled `user/skills/lazy-bug-batch/SKILL.md` | Dispatches recovery against a paused/re-invoking agent → dual-writer collision |
| Cycle turn-end foreground contract (Gap 1) | `user/skills/_components/lazy-batch-prompts/cycle-base-prompt.md` (turn-end §1); `user/skills/_components/turn-end-gate.md` | Prose-only mandate violated; deterrent premise contradicted by observed re-invocation |
| Receiver-side liveness discriminator (reuse target) | `user/skills/_components/dispatched-agent-liveness.md` | Already encodes the authoritative pause signal — Gap 2's fix should reuse it, not reinvent |
| Enforcement hook surface (only if fix approach A/both) | `user/hooks/` (a new cycle-subagent background-gate guard) | New control surface if mechanical enforcement is chosen |

## Open Questions

- **Fix approach (baseline-gating — surfaced in `NEEDS_INPUT.md`):** mechanically enforce foreground gate-running (Gap 1), give the orchestrator a deterministic pause-vs-terminal signal (Gap 2), or both. Product-class fork on a stub the operator has never seen → parked.
- **Harness re-invocation truth (informs the fix, not blocking):** does a dispatched cycle subagent reliably get background-completion re-invocation (contradicting `turn-end-gate.md` L13–18), or is it inconsistent/undocumented? If re-invocation is UNreliable, Gap 1 backgrounding also risks a genuine resultless stall — strengthening the case for mechanical prevention. `/plan-bug` should confirm the documented behavior before finalizing the fix.

## Locked Decisions

1. **Fix approach — Gap 1 vs Gap 2 vs both** (`NEEDS_INPUT.md`, operator-accepted 2026-07-19,
   recorded via `bug-state.py --record-decision`): **Both** — the deterministic orchestrator
   pause signal (Gap 2, load-bearing: consult the existing `dispatched-agent-liveness.md` marker
   + plan-status signal in `lazy-batch`/`lazy-bug-batch` Step 1e before dispatching recovery) AND
   mechanical foreground enforcement (Gap 1: a `user/hooks/` PreToolUse guard denying a
   `run_in_background` long-gate launch inside an armed cycle subagent). Locked for `/spec-bug` to
   conclude against and `/plan-bug` to phase — do not ship Gap 2 alone or Gap 1 alone.
