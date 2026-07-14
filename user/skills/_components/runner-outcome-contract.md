### Runner-Outcome Contract — the one documented banner + await + turn-end grammar

This is the ONE generalization of the Cognito/AlgoBooth build/test outcome system: a single
documented contract that any per-repo runner conforms to independently. The cross-repo seam is
**this documented grammar, not shared code** — the PowerShell build-queue plane and the
stdlib-Python gate-battery runner each emit conforming output on their own, sharing no
implementation. A runner "conforms" when it satisfies all four legs below.

The contract is surface-neutral: it constrains the *output shape and exit semantics*, never the
language, transport, or internal design of a conforming runner.

#### Leg 1 — Authoritative LAST-stdout-line banner

Every conforming runner prints, as its **LAST stdout line**, a single machine-parseable outcome
banner of the shape:

```
<runner>: <run-key> [op=<op>] RESULT=<PASS|FAIL|...> [counts] [(fidelity)] [-> next-action]
```

Agents **trust this banner and NEVER grep the runner's log output or result files to disambiguate
an exit code**. The banner is the only parse surface; whatever the runner streamed above it is
diagnostics for humans, not a machine surface.

Three conforming instances exist (the grammar strings below are the SSOT — a conforming runner's
tests quote them verbatim from this file):

- **`build-queue:`** (Cognito + AlgoBooth builds — existing, `Format-BuildQueueBanner` in
  `user/scripts/build-queue-hygiene.ps1`):

  ```
  build-queue: seq=<N> op=<op> RESULT=<PASS|FAIL|NO-TESTS-MATCHED> [tests=<T> failed=<F>] (result_fidelity=...) [-> next-action]
  ```

- **`QG_VERDICT:`** (AlgoBooth `npm run qg` — existing, in
  `repos/algobooth/.claude/skill-config/quality-gates.md`; **grandfathered verbatim** — the
  contract documents it as conforming rather than renaming a working surface):

  ```
  QG_VERDICT: PASS|FAIL (exit N)
  ```

- **`gate-battery:`** (claude-config's stdlib-Python battery runner — new,
  `user/scripts/gate-battery.py`):

  ```
  gate-battery: run=<id> op=battery RESULT=<PASS|FAIL> cmds=<n> failed=<k> (elapsed=<s>s) [-> first failing gate: <id>]
  ```

#### Leg 2 — Followable await (124/125 reserved)

A backgrounded run is re-acquirable by key from any later turn via an await entrypoint that
**re-emits the same Leg-1 banner as ITS last stdout line and exits with the run's own exit code**.
Two exit codes are reserved (semantics mirror `user/scripts/build-queue-await.ps1` byte-for-byte):

- **124** — the result is **not yet present** (the run may still be going). An await timeout is
  **NEVER success**; re-await or check the runner's status view. Do not treat 124 as a pass.
- **125** — the result file is present but **malformed / unreadable** after bounded retries.

Any other exit code is the awaited run's own exit code, faithfully reported (if a gate's own
process exited 124/125, the await reports it as-is — the same accepted ambiguity the build-queue
awaiter carries).

#### Leg 3 — Turn-end gate (BY REFERENCE, never copied)

A conforming skill carries the turn-end gate **by reference** to
`~/.claude/skills/_components/turn-end-gate.md` — a launch/enqueue echo is not an outcome, and an
owned in-flight run must be driven to its Leg-1 banner and consumed before the turn ends. This
contract does not restate that gate's text; the canonical statement lives in that component alone,
and a conforming skill injects it (`!cat`) rather than duplicating it.

#### Leg 4 — Never pipe the runner through `tail`/`head`

A shell pipeline returns the exit status of the *last* command in the pipe (`tail`/`head` — always
0), masking the runner's real non-zero exit so a failing run reads as green. Read the guaranteed
final Leg-1 banner line, or the process exit code — **never a piped tail's status**. (Generalized
from AlgoBooth's `quality-gates.md` never-pipe-through-tail rule.)

#### Seam statement

The composition seam between repos is exactly this documented grammar. The PowerShell queue plane
(`build-queue.ps1` + `Format-BuildQueueBanner`, workstation-only) and the Python battery runner
(`gate-battery.py`, cross-platform / cloud-capable) conform to Legs 1–4 **independently** — they
share no code, do not shell one another, and do not import each other's state. A repo opts into the
contract by committing a conforming runner + its manifest; a manifest-less repo is unaffected by
construction.

#### Note — AlgoBooth path discovery (D8)

AlgoBooth lives at a non-standard path (`C:\Users\Jacob\repos\AlgoBooth`), deliberately outside
`~/source/repos`, so `~/source/repos/*` globs (fleet discovery) do not see it. This does **not**
affect the contract: hook enforcement and queue/battery state keying resolve from the payload
cwd's git toplevel, so per-repo keying is correct regardless of the checkout path. Fleet
visibility is the only thing a glob misses — to surface AlgoBooth in the cross-repo fleet view,
add a one-line pin to `~/.claude/lazy-repos.json` (documented here, not implemented by this
feature):

```json
{ "pins": ["C:/Users/Jacob/repos/AlgoBooth"] }
```
