# Stale runtime behind health=200 mints false BLOCKED verdicts — Investigation Spec

> The Step-9 dispatch bar is `GET /health == 200`, but the running Tauri binary + sidecar
> bundle routinely predates the code under test — so `/mcp-test` reports genuine-looking
> failures against a pre-fix binary, burns `retry_count` on non-defects, and forces the
> orchestrator to hand-invent restart rituals. The F7 freshness predicate that would catch
> this (`stale_binary.py`) exists but is wired to NOTHING: the production `--ensure-runtime`
> call never binds a `stale_check`, so the STALE verdict state is unreachable, while the
> lazy-batch SKILL prose claims it works.

**Status:** Concluded
**Priority:** P1
**Last updated:** 2026-07-11
**Related:** `docs/features/long-build-and-runtime-ownership/` (Complete — owns `ensure_runtime` M4 ownership verdicts + the long-build ownership contract the fix routes rebuilds through); `docs/specs/lazy-validation-readiness/` (F7 — authored `stale_binary.py`, the never-wired predicate); `docs/bugs/_archive/ensure-runtime-recovery-starves-cold-compile/` + `docs/bugs/_archive/ensure-runtime-starves-pre-vite-sidecar-build/` (prior ensure-runtime liveness fixes — all liveness, none freshness); `docs/bugs/mcp-validation-peels-one-seam-per-loop/` (sibling — stale-runtime confounds inflate its `retry_count` escalation on non-defects); AlgoBooth memory notes `hijacked-runtime-after-mcp-test-cycle`, `ensure-runtime-corrupted-incremental-relink`.

## Verified Symptom

Transcript mining of real AlgoBooth `/lazy-batch` runs (session JSONLs under
`~/.claude/projects/C--Users-Jacob-repos-AlgoBooth/`):

- **Session `e076ed30-8dcf-429a`, `d8-stem-management` (saga turns ~49–278, ~230 turns, 8
  dispatches):** `retry_count` burned to 3 on pure stale-runtime confounds. Orchestrator's own
  conclusion (~turn 202, string verified in the JSONL): *"cycle 6's two 'open bugs' were both
  stale-runtime artifacts — the fixes were landed, the live sidecar just predated them."*
  Those false failures are indistinguishable from genuine `blocker_kind: mcp-validation`
  failures to every downstream consumer (retry budget, escalation predicate, operator).
- **Session `e076ed30`, `d7-multi-timbral` cycle 19:** BLOCKED at retry 4 on a wedged voice
  fixable only by a restart cycle — which cycle subagents are forbidden to perform (turns
  ~3520–3529) — so the run halted on a condition the orchestrator could have cleared.
- **Restart ritual cost:** ~20 `dev:restart` invocations in `e076ed30` and ~10 in `5c33b6ba`
  (grep: 217 and 48 mentioning lines respectively), each a full multi-minute Rust recompile.
  Late in `e076ed30` the orchestrator **hand-invented** the mitigation — *"runtime stale
  (pre-Phase-10 binary) → dev:restart"* (string verified in the JSONL) — i.e. the model
  re-derived, per run, a policy the harness should own.

## Root Cause

**Classification: `unwired mechanism` + `prose–code divergence`.** Runtime readiness is
classified on process/health/MCP-tool **liveness**, never on build **freshness vs HEAD** —
and the freshness predicate that was built for exactly this (F7) was never connected to the
production call path. Verified in the current tree (2026-07-11, including uncommitted
changes):

1. **The dispatch bar is health=200.**
   `user/skills/_components/lazy-batch-prompts/cycle-base-prompt.md` (~lines 394–405,
   "RUNTIME IS ALREADY UP"): the orchestrator *"pre-booted the dev runtime and BLOCKED on
   `GET http://localhost:3333/health == 200`"* before dispatching `/mcp-test`; the subagent is
   told to skip its own boot/health steps. Nothing in that contract compares the running
   binary to the commits under test. (The adjacent sidecar-pipe readiness check is liveness,
   not freshness.)

2. **`ensure_runtime` HAS a STALE state — with a defaulted-off predicate.**
   `user/scripts/lazy_core.py` — `ensure_runtime()` (~line 8319) returns
   `{"state": "READY"|"STALE"|"HIJACKED"|"DEAD"|"BLOCKED", ...}`; the docstring's phase 2 is
   *"Staleness — for an owned runtime, injected `stale_check(artifact_hash)` True ⇒ STALE"*,
   and STALE routes to rebuild at every classification site (~8674, ~8979, ~9070, ~9090). But
   at ~8515–8520: `if stale_check is None: stale_check = lambda: False`, with the comment
   *"The orchestrator binds a real stale_check when it knows the boot stamp."* **No caller
   ever does.**

3. **The single production call site binds no `stale_check`.**
   `user/scripts/lazy-state.py` (~11604): `lazy_core.ensure_runtime(Path(args.repo_root),
   live_session_id=live_session_id)` — the only non-test `ensure_runtime(` call in the
   scripts. `stale_check` (and `recover_identity`) default off ⇒ **the STALE verdict is
   unreachable in production**. `bug-state.py` has no call at all.

4. **The freshness predicate exists, orphaned.**
   `user/scripts/stale_binary.py` (F7 / lazy-validation-readiness):
   `native_source_newer_than(boot_iso, repo_root, globs=["src-tauri","crates"])` — newest git
   commit touching native source strictly newer than the boot timestamp ⇒ stale; fail-safe
   False; ships a CLI. Its docstring names the exact failure this spec documents ("Step 1d.0
   historically only checked `GET /health == 200` — which a stale binary passes") and defers
   the wiring to "the lazy-batch SKILL.md". Grep across `user/skills`, `lazy-state.py`,
   `lazy_core.py`, `bug-state.py`, `repos/`: the ONLY references are two **prose** lines in
   `user/skills/lazy-batch/SKILL.md` (~608, ~658). Line 658 tells the orchestrator that
   `state: STALE` means *"the native binary was stale … via the `stale_binary` predicate; the
   subcommand forced a `dev:restart`"* — **narrating machinery that is not wired**. The SKILL
   promises a guarantee the script does not deliver.

5. **Partial adjacent machinery exists — none of it is a freshness gate.**
   - Boot stamp (`lazy_core.py` ~9982–10027): `.runtime.boot.json` persists `spawn_ts` — but
     it feeds only `boot_recently_spawned()`, the cold-boot-in-progress grace window
     (patient-wait vs kill-restart). The timestamp that could feed
     `native_source_newer_than(boot_iso=…)` is ALREADY persisted; nothing connects them.
   - `.runtime.lock.json` has an `artifact_hash` field (`write_runtime_lock` ~9928–9949), but
     no code ever computes one — every writer passes `ident.get("artifact_hash")` from a
     `recover_identity()` callable that is `None` on the production path.
   - `MCP_TEST_RESULTS.md` has a `validated_commit`-vs-HEAD staleness gate (~3231, ~4474) —
     that guards stale *results documents*, not the stale *runtime*.

6. **BLOCKED.md is mintable against a stale runtime.** Nothing in the BLOCKED authoring
   contracts (`cycle-base-prompt.md` R14, `mcp-test/SKILL.md` "On a genuine") requires — or
   even records — runtime build freshness before writing a `blocker_kind: mcp-validation`
   sentinel. A failure observed on a pre-fix binary becomes a first-class blocker with a
   retry-count increment.

## Fix Scope (Concluded)

A script-owned build-fingerprint freshness gate, routed to an orchestrator-owned rebuild —
never to `/mcp-test`, never to BLOCKED:

1. **Wire the freshness predicate into `--ensure-runtime`.** `lazy-state.py --ensure-runtime`
   binds a real `stale_check` built from what already exists: boot timestamp from
   `.runtime.boot.json` (`read_boot_stamp`) — falling back to the runtime-lock/process start
   time — compared via `stale_binary.native_source_newer_than` against the newest HEAD commit
   touching the native globs (per-repo configurable via `_ENSURE_RUNTIME_DEFAULT_CONFIG` /
   repo override; AlgoBooth: `src-tauri`, `crates`, plus the sidecar-bundle inputs
   `strudel-sidecar`). This makes the existing, already-routed STALE verdict reachable —
   no new state machine.
2. **Stale ⇒ orchestrator-owned rebuild step, never mcp-test.** A STALE verdict routes Step 9
   to the long-build-ownership rebuild/restart path (orchestrator session,
   `run_in_background`, harness-tracked — per `docs/features/long-build-and-runtime-ownership/`),
   then re-probes; only a READY-and-fresh runtime may dispatch `/mcp-test`. This deletes the
   hand-invented "runtime stale → dev:restart" ritual by making it the script's job.
3. **BLOCKED.md freshness guard.** A `blocker_kind: mcp-validation` BLOCKED.md must record the
   runtime fingerprint it was observed against (boot stamp + HEAD sha at validation time) in
   its frontmatter, and must NOT be mintable when the fingerprint is stale — the authoring
   contract (cycle-base-prompt R14 / mcp-test SKILL) routes a stale-runtime observation to a
   runtime-readiness terminal (rebuild-and-rerun), not a validation failure; stale-confound
   failures stop consuming the retry budget (cf. the existing
   env-transient-counts-against-validation-retry-budget precedent for the sidecar pipe).
4. **Fix the prose–code divergence.** `lazy-batch/SKILL.md` ~658 becomes true (or is corrected
   until the wiring lands in the same change). Coupled-trio mirroring; `test_lazy_core.py`
   coverage for the bound `stale_check` (including the fail-safe False direction and the
   Windows boot-stamp path); full gates.

## Decisions

- **D1 — Fingerprint mechanism:** boot-timestamp-vs-native-commit comparison (the existing F7
  predicate) over binary hashing. It is already built, fail-safe, and needs no artifact
  enumeration; the lock's unused `artifact_hash` field stays as a future upgrade slot, not a
  dependency of this fix.
- **D2 — Fail-safe direction preserved:** on any freshness-probe error the gate reports FRESH
  (proceed on health=200), per `stale_binary.py`'s documented rationale — a spurious STALE
  costs a ~3–7 min gratuitous Rust rebuild per cycle.
- **D3 — Scope of "stale":** commits touching native/sidecar globs since boot. Pure TS/docs
  commits do not force a rebuild (Vite hot-reloads them); the glob list is the per-repo
  config knob, mirroring how the SKILL's teardown carve-out (~line 608) already reasons.
- **D4 — Wedged-but-fresh runtimes** (the d7 cycle-19 wedged voice) are NOT this bug — that is
  a liveness/recovery concern for the ensure-runtime recovery family; this spec only removes
  the freshness confound so such states are no longer mixed into validation retries.
