---
name: mcp-test
description: Resolve a YAML scenario, ensure MCP runtime readiness, run the deterministic engine (scripts/mcp-test/run.ts), read the compact verdict.json, forward the engine-written sentinel, and reconcile PHASES — haiku happy path, Sonnet only on failure
argument-hint: <test description — e.g. "test mix knob crossfade" or "verify queue fire sequence" or a scenario id>
---

# MCP Test — Informed Dispatcher (deterministic engine)

> **This skill was rewritten to the Informed Dispatcher pattern (deterministic-runner Phase 8).**
> The model NO LONGER drives the MCP API by hand, improvises curl calls, or *judges* assertions.
> A unit-tested TypeScript engine (`scripts/mcp-test/`) executes the declarative YAML scenario,
> evaluates every assertion **in code**, and writes a compact `verdict.json` PLUS the terminal
> pipeline sentinel. The model's role collapses to: **resolve a scenario → ensure runtime
> readiness → run the engine → read the small verdict → forward the sentinel the engine wrote →
> reconcile PHASES.** Raw MCP payloads (sample arrays, log dumps) NEVER enter model context — the
> verdict carries scalars + reasons + `heals[]`, and the engine writes any raw artifact to disk
> cited by path. Because the inputs are small and structured, **the happy path is haiku-steerable;
> Sonnet is pulled in ONLY to diagnose a Gate-3 assertion failure or repair the harness.**

The engine, not the model, talks to `localhost:3333`. See
[`docs/features/mcp-testing/deterministic-runner/SPEC.md`](../../docs/features/mcp-testing/deterministic-runner/SPEC.md)
(§Components #6 "Thin skill dispatcher", §Model orchestration, Locked Decision #8) and the engine
reference at [`scripts/mcp-test/CLAUDE.md`](../../scripts/mcp-test/CLAUDE.md).

---

## Model tier (Locked Decision #8 — HARD)

| Work | Tier | Why |
|------|------|-----|
| Scenario resolution, engine invocation, verdict read, sentinel forward, PHASES reconcile | **Haiku** | Mechanical; inputs small and structured (the whole happy path) |
| Gate-3 failure classification (flake vs genuine) | **Sonnet** | Judgment over the engine's evidence bundle; conservative *uncertain → genuine* bias |
| Harness-hardening repair (mechanics only) | **Sonnet** | Edits scenario data / engine under full gates |

The happy path runs on haiku end-to-end. Escalate to Sonnet ONLY when the verdict's classification
is `uncertain` (Gate 3) or `harness` repair beyond the engine's own self-heal is needed (see Step 5).
A clean pass that escalates to Sonnet is a defect — the success metric is "single pass on haiku".

---

## Step 0: Precondition — all implementation phases must be complete

`/mcp-test` is Step 9 in the lazy state machine; it runs after all implementation phases are
complete. (The `/retro` Step 8 was unwired — 2026-06. `RETRO_DONE.md` is no longer a gate.)

1. If `$ARGUMENTS` is `tier:N`, the precondition does not apply (tier batch mode is not scoped to a
   single feature) — skip Step 0.
2. Otherwise map `$ARGUMENTS` to a feature dir under `docs/features/` using the same correlation
   logic as `lazy-state.py` (match against `queue.json`, or `$ARGUMENTS` names the dir directly).
   Ambiguous/empty → skip Step 0 (ad-hoc run, not under the state machine).
3. If a feature dir resolves, confirm its phases are complete before proceeding.

This check is enforced even on a direct human invocation. If phases are clearly incomplete, surface
the gap and stop — MCP validation before implementation is complete is the wrong order. There is
intentionally no `--force` bypass.

---

## Step 0.5: Task Tracking (MANDATORY)

Load task tools and create tasks for compaction recovery:

```
ToolSearch: "select:TaskCreate,TaskUpdate,TaskGet,TaskList"
```

Create tasks immediately:
1. `TaskCreate({ subject: "Resolve scenario", description: "Map $ARGUMENTS to a corpus/live YAML scenario (or create one)" })`
2. `TaskCreate({ subject: "Ensure runtime readiness", description: "Orchestrated: confirm health==200. Standalone: boot + wait." })`
3. `TaskCreate({ subject: "Run the engine", description: "npx tsx scripts/mcp-test/run.ts <scenario> — pre-flight → scored run → verdict + sentinel" })`
4. `TaskCreate({ subject: "Read verdict.json", description: "Read the compact verdict — counts, reasons, heals[], classification" })`
5. `TaskCreate({ subject: "Forward sentinel + reconcile PHASES", description: "The engine wrote the sentinel; reconcile PHASES via reconcile-phases.ts" })`
6. `TaskCreate({ subject: "Escalate if needed", description: "Gate-3 uncertain → Sonnet diagnosis; harness → self-heal/repair" })`

Update each to `in_progress` when starting, `completed` when done. After compaction, `TaskList`
first to find your position.

---

## Step 1: Resolve the Scenario

The engine consumes a declarative **YAML** scenario (the locked v1 format — see
`scripts/mcp-test/CLAUDE.md` and `scripts/check-mcp-scenarios.ts`).

### tier:N batch mode

If `$ARGUMENTS` matches `tier:N`, run each scenario in that tier sequentially (Steps 2–5 per
scenario), then report a per-scenario summary table and stop. The engine's `reset_state` discipline
between runs keeps a clean slate.

| Tier | Scenarios (under `docs/testing/mcp-tests/corpus/live/` if converted, else the legacy `.md`) |
|------|------|
| 0 | infra-health-readiness, infra-session-telemetry, infra-screenshot-capture, infra-state-reset |
| 1 | play-stop-lifecycle, test-tone-loading, code-evaluation, tempo-control |
| 2 | channel-muting, mix-knob-crossfade, dual-channel-isolation |

(See the legacy tier map in git history for the full set; the curated live corpus is the
regression-validated subset — `docs/testing/mcp-tests/corpus/live/*.yaml`.)

### Single scenario

1. **Prefer a converted YAML scenario.** Scan `docs/testing/mcp-tests/corpus/live/*.yaml` (and
   `corpus/mock/` for engine-logic-only runs) for a name matching `$ARGUMENTS`. A YAML scenario is
   the engine's native input — no conversion needed.
2. **If only a legacy `.md` scenario exists** (`docs/testing/mcp-tests/*.md`), it is grandfathered
   (the lint warns, never fails). Convert the curated behavior to a YAML scenario following the
   format in `scripts/mcp-test/CLAUDE.md` (Phase 1 grammar: `version`, `name`, `requires`, `steps`,
   `assertions`), then lint it:
   ```bash
   npx tsx scripts/check-mcp-scenarios.ts docs/testing/mcp-tests/corpus/live
   python ~/.claude/scripts/surface_resolver.py --repo-root . --lint docs/testing/mcp-tests/corpus/live/<name>.yaml
   ```
   Both must pass (schema + JSONPath cardinality + audio-tolerance rules; every asserted tool
   registered) before running.
3. **If no scenario exists at all**, author one from the feature's SPEC behavior. Keep assertions on
   **scalar** observables (the engine evaluates them in code) — `get_audio_buffer`'s `rms` /
   `scheduler_playing` / `max_discontinuity` / `dc_offset`, the audio-quality scalar fields, state
   snapshot fields. Do NOT design assertions that need raw sample arrays.

> **Do NOT hand-drive the MCP API to "explore" behavior in the happy path.** The old skill probed
> tools by curl before writing assertions; that is now the engine's pre-flight job (field-path
> dry-run resolves every assertion path against a live read). Author the scenario, run the engine,
> and let pre-flight surface an unresolvable path as a `harness` miss to self-heal.

---

## Step 2: Ensure Runtime Readiness

The engine needs the dev runtime up and MCP-ready (`GET http://localhost:3333/health` == 200) before
the live run. **Who owns the boot depends on the invocation:**

### Orchestrated (lazy-pipeline / `--batch`) — the runtime is ALREADY up

When driven by `/lazy-batch` (or `/lazy`), the **orchestrator** pre-boots the dev runtime in its
own long-lived session and BLOCKS on `health == 200` BEFORE dispatching this cycle. So:

- **Do NOT kill/restart, do NOT `npx kill-port`, do NOT background a `tauri:dev`.** Treat the
  runtime as ready and go straight to Step 3.
- **Why the orchestrator owns the boot:** this skill runs INLINE inside a cycle subagent with no
  `Agent` tool, and a background process it starts does NOT survive the subagent's turn boundary —
  a subagent that backgrounded the build and ended its turn produced a resultless, sentinel-less
  return (a contract violation). The orchestrator's session persists; the subagent's does not.
- If the runtime appears dead mid-cycle, do NOT try to boot it yourself — surface `NEEDS_RUNTIME`
  in your return one-liner so the orchestrator re-boots.

### Standalone (a human ran `/mcp-test` directly) — boot it here

Prior sessions leave the Strudel sidecar in an unpredictable state (a stuck cycle counter survives
`reset_state`). The reliable fix is a full restart:

```bash
npx kill-port 3333
npm run tauri:dev    # run_in_background: true
```

`npx kill-port 3333` is the reliable stop (NOT `taskkill /F /IM algobooth.exe` — the watcher
respawns). The build takes 3–5 min — use that time for Step 1 scenario resolution. Then BLOCK on
readiness (foreground `until`-loop, never a fire-and-forget background wait):

```bash
for delay in 5 10 20 30 30 30 30 30 30 30 30 30 30 30 30; do
  curl -s http://localhost:3333/health && echo "HEALTH OK" && break
  sleep $delay
done
# then confirm the session logger + sidecar are up:
curl -s -X POST http://localhost:3333/tools/get_session_events -H "Content-Type: application/json" -d '{"limit":1}'   # total_lines > 10
curl -s http://localhost:3333/tools/get_sidecar_status   # is_connected: true
```

> **Skip the restart ONLY when ALL hold:** health 200, sidecar connected, NO Rust code changed since
> boot, and the user explicitly says the server is known-good. Any Rust-side change (new/modified
> tools, registrations, feature flags) requires a full recompile + restart — MCP routes register at
> compile time via `inventory::submit!`; hot-reload covers only frontend changes.

> **Structural untestability — assess BEFORE booting:** if the feature/bug PHASES.md carries
> `**MCP runtime:** not-required — {reason}`, verify the claim against
> `docs/features/mcp-testing/SPEC.md` (the only genuinely untestable classes are the "What We Cannot
> Prove" observation gaps and raw-PCM injection into the Rust callback thread — "Audio IS
> MCP-testable" via `load_test_tone` + `get_audio_buffer`, so audio claims are usually wrong). If you
> CONCUR, skip Steps 2–5 and the engine's sentinel writer emits the scoped `SKIP_MCP_TEST.md`
> (provenance below). If you DISAGREE, proceed normally; lazy-batch cycles return `NEEDS_RUNTIME`
> rather than booting.

---

## Step 3: Run the Engine (THE execution — not the model)

Invoke the deterministic runner against the resolved scenario, passing the feature id so the engine
emits the terminal sentinel into the feature dir:

```bash
npx tsx scripts/mcp-test/run.ts docs/testing/mcp-tests/corpus/live/<scenario>.yaml <outDir>
```

The engine runs the full pipeline in ONE pass (SPEC §Validation flow):

1. **Pre-flight readiness gate** — docs pre-screen + live `/info` probe + field-path dry-run +
   backend detection. A blocking miss SHORT-CIRCUITS to a `harness` verdict with NO scored run (no
   avoidable rerun — the single-pass guarantee). `backend-deferrable` misses (sustained-timing on a
   headless host) are carried as non-blocking deferrals.
2. **Scored run** — executes each step against `localhost:3333` (per-tool HTTP method from the
   authoritative `tool-methods.ts` map, never inferred from the name), captures responses, and
   evaluates every assertion **in code** via the locked operator set + strict JSONPath (a scalar
   operator on a 0/2+-match path FAILS LOUD — no silent array-flatten false-pass).
3. **Three-gate classification** — Gate 1 (pre-flight miss) → `harness`; Gate 2 (HTTP 5xx / DSP
   error flag) → `genuine` with ZERO model invocation; Gate 3 (valid response, value out of band) →
   `uncertain` (the only case needing Sonnet), biased `uncertain → genuine`; clean → `pass`.
4. **Self-heal** (on a `harness` classification) — mechanics-only, audited repair (field/JSONPath
   drift, threshold *typo* with unchanged value, tool-name casing, pacing/timeout, missing `requires`
   entry, stale-read race, stale-binary restart), re-run, capped retries. Every heal is recorded in
   `verdict.json.heals[]` (before/after + reason) and raises `warning`. **Anti-masking (hard):** a
   change to *what an assertion asserts* (threshold band, expected value, deletion/weakening) is
   SEMANTIC → the engine writes `NEEDS_INPUT.md` and refuses, never an autonomous edit.
5. **Sentinel emission** — on a clean/deferred `pass` the engine writes the TERMINAL sentinel
   directly (the model NEVER authors sentinels): `VALIDATED.md` (clean pass) /
   `DEFERRED_REQUIRES_DEVICE.md` (clean pass with backend deferrals) / `SKIP_MCP_TEST.md` (explicit
   structural skip). `genuine` / `uncertain` / unrepaired `harness` emit NO terminal sentinel here
   (they route to BLOCKED / Sonnet / self-heal). `MCP_TEST_RESULTS.md` carries the partial record
   with `validated_commit`.

The CLI exits 0 on a pass verdict, 1 on a fail verdict, 2 on a load/transport error.

---

## Step 4: Read the Verdict (the ONLY thing in model context)

Read the compact `verdict.json` the engine wrote (`<outDir>/<stem>.verdict.json`). It is a few KB —
the FROZEN schema (`scripts/mcp-test/verdict.ts`):

- `name`, `result` (`pass`|`fail`), `passed`, `failed`
- `assertions[]` — each row: `id`, `subject`, `path`, `operator`, `expected`, `observed` (scalar or
  a compact `{ omitted: "<n> values — see artifact" }` stand-in), `result`, `reason`
- `heals[]` — audited self-heal records (before/after + reason); non-empty → drift was present and
  self-healed, so you SEE it even on a pass
- `warning` — true when any heal applied
- `artifact` — the PATH to the sibling raw-payload file (sample arrays, full step context). **Open
  it ONLY if a scalar already FAILED and deeper localization is genuinely needed** — never pull the
  raw `samples` array into context on a pass.

> **Token-cost contract (the SPEC success metric).** The model reads `verdict.json` only. Raw
> `samples` arrays and unfiltered log dumps are NEVER serialized into context — the engine wrote
> them to the `artifact` path. Measured baseline: the prior LLM-as-runner `/mcp-test` burned ~1.34M
> tokens / 9 cycles on a single feature, dominated by raw `get_audio_buffer` arrays + full log
> dumps the assertions never needed. This rewrite removes that bloat with UNCHANGED verification
> strength (the assertions are still on the scalars).

---

## Step 5: Forward the Sentinel + Reconcile PHASES

The engine ALREADY wrote the terminal sentinel (Step 3.5). Your job is to forward/confirm it and
reconcile `PHASES.md` — both mechanical, both haiku.

### On a clean / deferred `pass`

1. Confirm the engine wrote the expected sentinel (`VALIDATED.md` for a clean pass, or
   `DEFERRED_REQUIRES_DEVICE.md` if the verdict carried backend deferrals). Do NOT re-author it.
2. Reconcile the feature's `PHASES.md` with the deterministic helper — it ticks the validated phase's
   per-deliverable checkboxes + per-phase `**Status:**` (scoped to that phase's section) and NEVER
   flips the top-level `**Status:**` or writes `COMPLETED.md` (both `__mark_complete__`-owned):
   ```bash
   npx tsx scripts/mcp-test/reconcile-phases.ts <PHASES.md> <validated-phase>
   ```
3. Walk every unchecked **Runtime Verification** row in the validated phase: tick the ones this run
   proved (with a one-line evidence annotation naming the scenario/assertion); re-scope any NOT
   covered to an honest follow-up note (and disclose with a `⚖` line). If a genuinely blocking row
   stays unchecked, the outcome is a `MCP_TEST_RESULTS.md` partial, not `VALIDATED.md`.
4. Commit the reconciliation alongside the engine's sentinel write.

### On a `genuine` (Gate 2) or unrepaired `harness`

No terminal sentinel was written. A `genuine` runtime bug routes to `BLOCKED.md` via the normal lazy
route (ZERO model judgment was needed — the engine classified it deterministically). At
`retry_count >= 2` a `BLOCKED.md` with `blocker_kind: mcp-validation` MUST carry a `## Seam
Enumeration` section (every boundary in the failing chain: user surface → sidecar/IPC → command
queue → engine apply → state machine → final observable, each `probed-OK`/`probed-FAIL`/`unprobed`
with one line of evidence) — you just drove the runtime, so you are the cheapest place to enumerate
it; `blocked-resolution` / `/add-phase` consume it as the corrective phase's seam-audit checklist.

### On an `uncertain` (Gate 3) — THE ONLY Sonnet escalation

The engine bundled the failed assertion rows as the evidence bundle and biased `uncertain → genuine`.
Escalate to **Sonnet** to classify flake vs genuine over that evidence. Sonnet may classify
*infrastructure flake* ONLY on proven environmental evidence (e.g. a CPU-starvation/preemption
signature on a `headless` backend — confirm via `get_audio_mode` + a zero-feature-activity control
run); otherwise → genuine. **Sonnet is FORBIDDEN from altering any semantic assertion value** (that
is the anti-masking line — a real threshold/expected-value change is `NEEDS_INPUT`, never an edit).

---

## Sentinel reference (the engine writes these — you forward them)

The distinction is load-bearing: `lazy-state.py` advances the QUEUE on a terminal `VALIDATED.md`, a
permanent `SKIP_MCP_TEST.md`, or a device-axis `DEFERRED_REQUIRES_DEVICE.md` (the last DEFERS —
the feature stays In-progress on a no-device host and re-opens on a real-device host).

| Outcome | Sentinel | When |
|---------|----------|------|
| Every scenario passed | `VALIDATED.md` (`kind: validated`) | Clean pass, nothing environment-blocked |
| Some passed, some un-runnable | `MCP_TEST_RESULTS.md` (`kind: mcp-test-results`, `result: partial`, `validated_commit`) | Honest partial — does NOT complete the feature |
| Residual failures real-device-only but certifiable on a real device | `DEFERRED_REQUIRES_DEVICE.md` (`kind: deferred-requires-device`), scoped `deferred_scenarios[]` | Sustained-timing / dropout / jitter under the headless pump |
| Residual failures un-testable on ANY host | `SKIP_MCP_TEST.md` (`kind: skip-mcp-test`), scoped | Permanent waiver — only raw-PCM injection qualifies |

**`validated_commit` is REQUIRED in every `MCP_TEST_RESULTS.md`** (the engine captures `git rev-parse
HEAD` at validation time via injected deps) — the Step-9 sha-freshness gate compares it to HEAD so
stale results trigger a re-verify.

**`SKIP_MCP_TEST.md` provenance (HARD — the state scripts enforce):** `granted_by: mcp-test` (the
only value a pipeline-written skip may carry) + `spec_class: <the untestable class you verified>`
(the `docs/features/mcp-testing/SPEC.md` class). `lazy_core.skip_waiver_refusal()` REFUSES a grant
without it. The engine's sentinel writer enforces both invariants (and `deferred_scenarios[]`
non-empty — a blanket whole-feature deferral is rejected).

**Deferral vs skip — by re-testability:** a sustained-timing/dropout/jitter assertion that fails
ONLY because the host runs the HeadlessPumpDriver is WSL2-untestable, not un-testable →
`DEFERRED_REQUIRES_DEVICE.md` (a real-device `/lazy` host re-opens it scoped to the deferred IDs; on
pass it deletes the deferral and writes `VALIDATED.md`; a real dropout on real hardware →
`BLOCKED.md`). An assertion NO host can drive through MCP (raw-PCM only) → permanent
`SKIP_MCP_TEST.md`. Canonical schema: `~/.claude/skills/_components/sentinel-frontmatter.md`.

---

## Step 6: Report

Summarize to the user (haiku — small, structured):

1. **Verdict** — `result`, `passed`/`failed`, the classification `kind`, and any `heals[]` (each is
   audited drift the engine self-healed — surface it even on a pass).
2. **Sentinel** — which terminal sentinel the engine wrote (or why none: genuine/uncertain/harness).
3. **PHASES reconcile** — which phase/rows were ticked; any `⚖` re-scope disclosure.
4. **Scenario file** — the YAML scenario used/created.
5. **Escalation** — if Sonnet was pulled in (Gate-3/repair), say so; a clean pass should NOT have
   escalated (single-pass-on-haiku is the success metric).

Do NOT paste raw payloads. If a coverage gap suggests a missing MCP tool that would be
straightforward to add, note it as a candidate for `/spec` or `/add-phase`.

---

## Step 7: Tear Down the Dev Server (standalone path only)

A stray dev runtime is never acceptable. Teardown is UNCONDITIONAL (pass/fail/blocked/skip/deferred),
AFTER the sentinel + reconcile are committed.

- **Standalone (this skill booted it — `server_was_running = false`):** YOU own teardown:
  ```bash
  npm run dev:kill
  ```
  `dev:kill` (`scripts/kill-dev.js`) is the ONLY reliable full teardown — Vite (1420), MCP (3333),
  stale sidecar named-pipe survivors, orphaned Tauri binaries. `npx kill-port 3333` alone leaves the
  sidecar. Run it foreground; then verify `GET http://localhost:3333/health` fails to connect. If
  3333 still answers, re-run and re-verify before returning.
- **Orchestrated (`--batch` — `server_was_running = true`):** do NOT kill it — the ORCHESTRATOR owns
  the runtime across cycles and tears it down at run boundary (`/lazy-batch` `--run-end`
  `npm run dev:kill`). Leave it running + MCP-ready; surface `NEEDS_RUNTIME` only if it looks dead.
- **Cloud (`/lazy-batch-cloud`):** N/A — the cloud variant defers `/mcp-test` (`DEFERRED_NON_CLOUD.md`)
  and never boots a Tauri runtime.

---

## `/lazy-batch` Step-9 integration note (deterministic-runner Phase 8)

The orchestrator-managed runtime pre-boot is UNCHANGED: `/lazy-batch` Step 1d.0 runs
`npm run dev:restart` and BLOCKS on `health == 200` before dispatching the Step-9 `/mcp-test` cycle,
and tears the runtime down at `--run-end` via `npm run dev:kill`. What changed is the cycle body —
the dispatched subagent no longer drives the MCP API by hand; it runs the deterministic engine
(`npx tsx scripts/mcp-test/run.ts <scenario>`), reads `verdict.json`, forwards the engine-written
sentinel, and reconciles PHASES — on **haiku**, escalating to Sonnet only for a Gate-3 `uncertain`
classification or a harness repair beyond the engine's self-heal. No `/lazy-batch` prompt change is
required for the runtime lifecycle; the only behavioral shift is the smaller, cheaper, haiku-tier
cycle (the token-cost contract above). The Phase-7 live-replay corpus
(`npx tsx scripts/mcp-test/replay.ts`) is the regression guard that this skill+engine path keeps
reproducing known-good verdicts across future engine changes.
