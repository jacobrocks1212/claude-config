### Turn-End Gate — in-flight work is not an outcome (MANDATORY)

Your turn may not end while work you own is still in flight. "In flight" means any of:

1. **A backgrounded shell job** — a gate battery, build, test run, or chained gate+commit
   launched with `run_in_background: true` (or auto-backgrounded by the harness) that has not
   yet printed its terminal result.
2. **A dispatched inner agent** whose final report you have not consumed — including an agent
   you "resumed" (e.g. via `SendMessage`) and are now "awaiting".
3. **A queue-routed build/test** that has only echoed an enqueue/launch line
   (`build-queue: enqueued as seq=N`, `build started`) — an enqueue is NOT a result.

**Why this is structural, not stylistic.** Inside a dispatched agent, ending your turn ENDS the
agent. Background-job completion callbacks, transcript "watchers", and inner-agent completions
cannot re-invoke a finished agent — a final message of the form "the job is running; I'll be
notified when it completes" is structurally false there, and the run stalls until a human
manually resumes it. Only a top-level interactive session gets background-completion
re-invocation; never rely on it from inside any `Agent` dispatch.

**Annotation — the mandate does not rest on the teardown premise alone.** In practice, a
dispatched cycle subagent MAY receive background-completion re-invocation (this is
undocumented/inconsistent platform behavior — see `ADHOC_BRIEF.md` in
`docs/bugs/adhoc-orchestrator-redundant-recovery-on-background-suite-reinvoke`), so "the process
tree is torn down" is no longer the sole reason to never background a long gate here. The rule is
now ALSO enforced MECHANICALLY (the `cycle-subagent-bg-gate-guard.sh` PreToolUse hook denies the
launch outright) AND backed by the Gap-2 discriminator — `lazy_core.execute_plan_liveness` /
`--execute-plan-liveness` — which lets the orchestrator tell a genuinely-paused run apart from a
dead one on the rare occasion a background-completion notification does arrive.

**The gate — drive every in-flight item to a terminal result, then consume it, before your
final message:**

- **Backgrounded shell job** → block on it: re-run it foreground, or poll its output in a
  bounded foreground loop, until it exits — then read the real pass/fail. **Over-cap aggregate
  gate (prevention, not just recovery):** if the command itself would exceed the ~10-min Bash
  cap, re-running the *aggregate* in the foreground just re-hits the cap and re-backgrounds.
  Do NOT reach for the aggregate at all — run its individual under-cap sub-components
  synchronously in the foreground instead (each sub-check drives to a real pass/fail within the
  cap). Never background a long gate from inside a dispatched agent, whose process tree is torn
  down when its turn ends. **This is now MECHANICALLY enforced for cycle subagents:** the
  PreToolUse hook `cycle-subagent-bg-gate-guard.sh` denies a `run_in_background: true`
  gate/test-suite launch from inside an armed cycle subagent at the tool layer, redirecting to
  this foreground-await mandate.
- **Inner agent dispatch** → dispatch-and-AWAIT: the child's final report arrives as the
  `Agent` tool call's own result — consume it directly. NEVER dispatch asynchronously and end
  your turn expecting a message, watcher, or notification to bring the result back.
- **Build-queue op** → follow to the authoritative `RESULT=` banner:
  `powershell.exe -ExecutionPolicy Bypass -File "$HOME/.claude/scripts/build-queue-await.ps1" -Seq <N>`.
  Its exit `124` means "result not yet present" — the run is STILL GOING; re-await or check
  `/build-queue-status`; never treat an await timeout as success.

"Waiting for X to finish", "awaiting its completion", "the watcher will re-invoke me" are NEVER
valid final messages. If you genuinely cannot drive an item to a result (hard tool-timeout
ceiling, orphaned job), say so explicitly — report verification as INCOMPLETE and name what is
still running; never imply the result will arrive after your turn ends.

**Legitimate parallel fan-out is NOT a turn-end-gate violation.** Dispatching several FOREGROUND
`Agent` calls in one turn and ending that turn to await them IS dispatch-and-await — the harness
re-invokes you as each child completes, and their reports arrive as the `Agent` calls' own
results. That is the mandated pattern (sub-subagents must be foreground; `lazy-cycle-containment.sh`
denies background sub-subagent dispatch). The gate forbids ending your turn on a wait that will
NOT re-invoke you (a backgrounded shell job, a "watcher", a child→parent message a backgrounded
child can never send) — not the ordinary foreground-await pause.

**Receiver counterpart.** Because a fan-out orchestrator has no *background* children at those
foreground-await pauses, the harness fires a `status=completed` `<task-notification>` at each
one. A party that DISPATCHED you (a main/dispatcher session) must not misread that as terminal
completion and interfere with your live lineage. The receiver-side interpretation contract —
`completed` is advisory, the run marker / plan status is authoritative, and how to tell a pause
from a genuine wedge before any `TaskStop`/takeover — is `~/.claude/skills/_components/dispatched-agent-liveness.md`.
