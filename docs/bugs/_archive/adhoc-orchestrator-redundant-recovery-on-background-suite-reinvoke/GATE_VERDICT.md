---
kind: gate-verdict
feature_id: adhoc-orchestrator-redundant-recovery-on-background-suite-reinvoke
gate_version: 1
date: 2026-07-19
scope_hit:
  - user/hooks/cycle-subagent-bg-gate-guard.sh
  - user/scripts/bug-state.py
  - user/scripts/lazy-state.py
  - user/scripts/lazy_core/__init__.py
  - user/scripts/lazy_core/markers.py
  - user/settings.json
  - user/skills/lazy-batch/SKILL.md
  - user/skills/lazy-bug-batch/SKILL.md
checks:
  overfit: flag-justified
  tautology: flag-justified
  gate_weakening: pass
  complexity: declared
retires: the unenforced prose-only foreground-await mandate in cycle-base-prompt.md turn-end §1 (the "never background a long test/build suite inside a cycle subagent" instruction, previously convention-only) — retired in favor of its mechanical backstop, the net-new permissionDecision:deny hook `cycle-subagent-bg-gate-guard.sh` plus the `execute_plan_liveness` discriminator, which closes the traced Step-1e serving-path gap where a backgrounded suite's ambiguous "holding, will re-invoke" return caused the orchestrator to dispatch a redundant recovery cycle (one-writer risk on the same worktree).
override: absent
---

## Adversarial answers

### overfit

`python3 user/scripts/harness-gate.py --repo-root . --range 8dded98a~1..18bd6350 --feature-dir docs/bugs/adhoc-orchestrator-redundant-recovery-on-background-suite-reinvoke --json`
flagged the alternation literals appended in `user/hooks/cycle-subagent-bg-gate-guard.sh` (the
`|vitest`, `|cargo test`, `|dotnet test`, `|npm run qg`, `|npm run test`, `|gate-battery` command
tokens; the `powershell`/`pwsh -Command` and heredoc-introducer regexes) plus the deny-message
literal string appended as a membership element.

**Nearest recurrence this rule does NOT catch:** a differently-shaped aggregate/meta gate command
not in the enumerated alternation — e.g. `make check`, `npm run test:all`, `./scripts/ci.sh`, or a
project-local wrapper script that itself shells one of the enumerated commands. None of these
literal tokens match the hook's alternation, so a cycle subagent backgrounding one of THOSE would
not be denied by this hook.

**Why flag-justified, not a reshape.** The matcher keys on the STRUCTURAL class this hook exists to
cover: the closed set of long-running test/build invocations that `cycle-base-prompt.md`'s turn-end
§1 foreground-await mandate already enumerates by name (the same set the mandate has always named
prose-side — this hook is the mechanical projection of an EXISTING enumerated list, not a novel
literal invented from one incident). It is not an incident-shaped literal (no `docs/{features,bugs}`
slug, no date, no session id) — it is a command-vocabulary alternation, the same shape as
`build-queue-enforce.sh`'s manifest-driven op alternation and `long-build-ownership-guard.sh`'s
exact-invocation set, both accepted precedents in this repo. A novel aggregate gate name that the
alternation misses is NOT silently ungated: it still falls under the SURVIVING prose foreground-await
mandate in `cycle-base-prompt.md` (never retired — only its enforcement gap is retired, see
`complexity` below), and any RECURRING miss is independently caught by the Gap-2
`execute_plan_liveness` discriminator, which detects the paused-vs-terminal state regardless of
which command produced the backgrounding. The structural property the rule keys on: "a
long-running test/build command, from the closed vocabulary the turn-end contract already names,
launched with `run_in_background: true` from inside a dispatched cycle subagent." Extending the
vocabulary to a newly observed aggregate-gate name (e.g. adding `make check`) is a routine,
low-risk vocabulary extension of an already-justified structural class — not scope creep.

### tautology

**If this change were broken, how would its success metric look?** A broken bg-gate-guard hook
(e.g. a discriminator that always reports "terminal" even mid-suite, or a hook silently disabled)
would produce IDENTICAL surface symptoms to a working one in the one place that's easy to check —
the deny count would simply be lower (fewer/no denies is what both "working, subagents comply" and
"broken, hook doesn't fire" look like from inside the hook's own emission stream). That is exactly
the canonical tautology trap named in `harness-change-gate.md`: a deny-count metric is
self-emitted and can't distinguish "prevented" from "never checked."

**Independent signal declared (`signal_independence: independent`).** This change's actual claim —
that a backgrounded long suite no longer causes the orchestrator to dispatch a REDUNDANT recovery
cycle — is verified by two signals neither emitted nor suppressed by the hook itself: (1) the
`execute_plan_liveness` discriminator is unit-tested against REAL on-disk run/cycle markers
(`marker_present`, `plan_status`) in `lazy_core`/`bug-state.py` test fixtures — an independent
ground truth the hook does not control; and (2) recovery-suppression is observable downstream via
the deny-ledger's `process-friction`/`unexpected-commits` counters and a future retro's
cycles-per-completion count (`lazy-batch-retro`, `efficacy-eval.py` REFUTED/CONFIRMED verdicts on
this item's intervention hypothesis) — a signal the hook neither emits nor reads. If the fix were
broken (discriminator misclassifying paused-as-terminal, or the guard not firing), the independent
telemetry would show continued redundant-recovery dispatches / repeat-count churn on the same
feature — a signal distinguishable from "working."

No `## Intervention Hypothesis` block exists in this bug's `SPEC.md` (the checker's literal flag
trigger) because the bug pipeline's SPEC template does not carry that section by default; the
justification above is the recorded declaration this check requires in lieu of that block.

### gate_weakening

No weakening. The diff is a **pure enforcement addition**: a net-new
`permissionDecision: deny`-emitting PreToolUse hook (`cycle-subagent-bg-gate-guard.sh`) registered
in `user/settings.json`, plus a net-new read-only discriminator
(`execute_plan_liveness`/`--execute-plan-liveness`) added to `lazy_core`, `lazy-state.py`, and
`bug-state.py`. No `def test_*` was deleted, no numeric gate-line literal was loosened, no
exemption/sanction-set gained a member, no `*_BYPASS` env-var was introduced, and no existing
`permissionDecision: deny` / `refuse_*` / `exit 3` branch was removed or narrowed. The checker's
own `gate_weakening` result is `pass` with empty evidence — no operator sign-off is required.

### complexity

**Net-new surface, and it pays for itself by retiring an unenforced mandate.** This change adds one
new hook file (`cycle-subagent-bg-gate-guard.sh`) and one new read-only discriminator
(`execute_plan_liveness`) shared by both state scripts. What it RETIRES: the prose-only foreground-
await mandate in `cycle-base-prompt.md` turn-end §1 previously had NO mechanical backstop — a cycle
subagent that backgrounded a long test/build suite and returned an ambiguous "holding, will
re-invoke" message was invisible to any gate, and the orchestrator's only recourse was to
(incorrectly) interpret the ambiguous return as a stall and dispatch a redundant recovery cycle
against the same worktree (a one-writer-per-file violation risk this bug exists to close). The new
hook makes the mandate ENFORCED (deny-at-source, before the ambiguous return can happen), and the
discriminator gives the orchestrator a deterministic paused-vs-terminal read instead of guessing
from an ambiguous string, so the redundant-dispatch failure mode this bug reports is structurally
closed, not just documented against harder. The retired rule genuinely stops firing as a *silent*
mandate: going forward, an attempted violation is denied at the tool-call boundary instead of
depending on subagent compliance with unenforced prose.
