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

**The gate — drive every in-flight item to a terminal result, then consume it, before your
final message:**

- **Backgrounded shell job** → block on it: re-run it foreground, or poll its output in a
  bounded foreground loop, until it exits — then read the real pass/fail. **Over-cap aggregate
  gate (prevention, not just recovery):** if the command itself would exceed the ~10-min Bash
  cap, re-running the *aggregate* in the foreground just re-hits the cap and re-backgrounds.
  Do NOT reach for the aggregate at all — run its individual under-cap sub-components
  synchronously in the foreground instead (each sub-check drives to a real pass/fail within the
  cap). Never background a long gate from inside a dispatched agent, whose process tree is torn
  down when its turn ends.
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
