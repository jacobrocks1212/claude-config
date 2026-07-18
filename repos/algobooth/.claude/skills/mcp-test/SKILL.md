---
name: mcp-test
description: Resolve a YAML scenario, ensure MCP runtime readiness, run the deterministic engine (scripts/mcp-test/run.ts), read the compact verdict.json, forward the engine-written sentinel, and reconcile PHASES — haiku happy path, Sonnet only on failure
argument-hint: <test description — e.g. "test mix knob crossfade" or "verify queue fire sequence" or a scenario id>
model: haiku
# adhoc-derive-multi-commit-budget-from-dispatch-sites: the Step-9 validation
# cycle commits the audited self-heal separately from the terminal sentinel +
# PHASES reconcile (documented worst case: self-heal + 2-part reconcile +
# sentinel correction = 4, see lazy_core._MULTI_COMMIT_CEILING_OVERRIDE). Read by
# lazy_core.skill_declares_multi_commit (repo-scoped resolution) for the budget.
commit-cadence: multi
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
| Ready converted-YAML scenario: engine invocation, verdict read, sentinel forward, PHASES reconcile | **Haiku** | Mechanical; inputs small and structured (the whole happy path) |
| Scenario authoring / first-run `.md`→YAML conversion / diagnosis | **Sonnet** | Judgment / construction work — routed by DEFAULT, not by a per-run override |
| Gate-3 failure classification (flake vs genuine) | **Sonnet** | Judgment over the engine's evidence bundle; conservative *uncertain → genuine* bias |
| Harness-hardening repair (mechanics only) | **Sonnet** | Edits scenario data / engine under full gates |

The happy path runs on haiku end-to-end. The frontmatter stays `model: haiku` — haiku is the
happy-path default; the tier ESCALATES to Sonnet on a **script-derived signal**, not a per-run
human/orchestrator call.

**The tier is chosen by `route_mcp_test_tier`** in `user/scripts/surface_resolver.py` (symlinked to
`~/.claude/scripts/surface_resolver.py`) — `route_mcp_test_tier(scenario_path, prior_verdict=None,
yaml_exists=None) -> "haiku" | "sonnet"`, a pure function over script-observable state. It returns
`sonnet` for ANY of these conditions WITHOUT needing a human or orchestrator override:

1. **Unconverted scenario** — the resolved scenario is a legacy `.md` with NO converted
   `corpus/live/*.yaml` counterpart (first-run conversion needed) → `sonnet`.
2. **Non-definitive prior verdict** — the recorded prior verdict (from `verdict.json` /
   `MCP_TEST_RESULTS.md`) is `uncertain`, an unrepaired `harness` fault, or a post-heal `genuine`
   failure (anything outside the definitive `all-passing` allow-list) → `sonnet`.
3. **No scenario at all** — scenario-authoring is needed → `sonnet`.

Only a **ready converted YAML with no adverse prior verdict** routes to `haiku`. This retires the
old reliance on an orchestrator override for the diagnosis/authoring case — a `.md`-unconverted or
prior-non-definitive scenario routes to Sonnet by construction. A clean pass that escalates to
Sonnet is still a defect — the success metric remains "single pass on haiku" for the happy path.

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
  in your return one-liner so the orchestrator re-boots. **"Appears dead" includes the
  HTTP-healthy-but-pipe-dead case:** the dev HTTP server boots independently of the MCP sidecar
  named pipe, so `health == 200` does NOT prove the sidecar is connected. A zombie node process
  holding the `:3333` pipe after a `dev:restart` leaves the runtime HTTP-healthy but
  MCP-functionally dead — a self-inflicted ENV transient, NOT a code failure. Probe
  `GET http://localhost:3333/tools/get_sidecar_status` (the `is_connected: true` discriminator
  used by the standalone path below); if `is_connected: false`, surface `NEEDS_RUNTIME` — do NOT
  run the engine and do NOT write an `mcp-validation` `BLOCKED.md` (that would charge the env
  transient to the feature's validation-retry budget). The orchestrator re-boots cleanly, reaping
  the zombie, and re-dispatches.

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
   with `validated_commit`. The ONE documented exception to "the model never authors sentinels" is the
   narrow `observation_gap_exemptions` amendment on an all-exempt `partial` — see **Scoped-validated
   partial** under the Sentinel reference below.

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
route (ZERO model judgment was needed — the engine classified it deterministically). EVERY
`BLOCKED.md` with `blocker_kind: mcp-validation` — at ANY `retry_count`, starting at the FIRST
failure — MUST carry a `## Seam Enumeration` section (every boundary in the failing chain: user
surface → sidecar/IPC → command queue → engine apply → state machine → final observable, each
`probed-OK`/`probed-FAIL`/`unprobed` with one line of evidence, PLUS any obviously-adjacent unwired
seam) — you just drove the runtime, so you are the cheapest place to enumerate it, and probing one
more boundary costs a single tool call, not a full pipeline loop; `blocked-resolution` / `/add-phase`
consume it as the corrective phase's seam-audit checklist. At `retry_count >= 2` (repeated failure
despite an already-batched seam fix), enumeration alone is no longer sufficient — `/investigate` is
mandatory before the next corrective phase (see `blocked-resolution.md` step 1a).

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
| Some passed, some un-runnable | `MCP_TEST_RESULTS.md` (`kind: mcp-test-results`, `result: partial`, `validated_commit`) | Honest partial — does NOT complete the feature, UNLESS every uncovered row is a documented-untestable class → see **Scoped-validated partial** below |
| Residual failures real-device-only but certifiable on a real device | `DEFERRED_REQUIRES_DEVICE.md` (`kind: deferred-requires-device`), scoped `deferred_scenarios[]` | Sustained-timing / dropout / jitter under the headless pump |
| Residual failures need a host CAPABILITY this machine lacks | declare `requires_host: <id>` (SPEC frontmatter / queue.json) → `lazy-state.py compute_state` writes `DEFERRED_REQUIRES_HOST.md` (`kind: deferred-requires-host`), terminal `host-capability-saturated` | A 2nd network peer (e.g. 2nd Ableton Link peer), a different OS (Linux/macOS), an external binary/GPU/MIDI surface — NOT an audio device |
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

**DEVICE vs HOST-CAPABILITY — do not conflate (a misroute here LOOPS):**
- **`DEFERRED_REQUIRES_DEVICE` = real-device-TESTABLE.** The assertion fails ONLY because this host
  runs the `HeadlessPumpDriver` (sustained-timing / dropout / jitter). A real AUDIO device ON THIS
  MACHINE would certify it. Cycle-written.
- **HOST-CAPABILITY gap = this machine fundamentally LACKS something, regardless of its audio device** —
  a 2nd network peer (e.g. a 2nd Ableton Link peer), a different OS (Linux/macOS), or an external
  binary/GPU/MIDI surface. A real audio device here would NOT help. This is **NOT** a device deferral.
  The feature must declare `requires_host: <capability-id>` (SPEC frontmatter / queue.json) so
  `lazy-state.py compute_state` defers it DECLARATIVELY to a capability-bearing host (terminal
  `host-capability-saturated`, sentinel `DEFERRED_REQUIRES_HOST.md`) — instead of the cycle writing
  `DEFERRED_REQUIRES_DEVICE`, which **re-opens on any real-audio-device host and LOOPS** (Step 9
  re-opens it, the cycle still can't certify it, the step-repeat tripwire trips, the queue never
  drains).
- **Litmus test:** *Would a real audio device on THIS machine certify it? Yes → DEVICE. No, it needs a
  peer/OS/binary this machine lacks → HOST-CAPABILITY (declare `requires_host`; do NOT device-defer).*
- **The registry is closed.** Valid ids live in `lazy_core._HOST_CAPABILITY_REGISTRY` (currently:
  `real-audio-device`, `midi-controller`, `gpu`, `zimtohrli-toolchain`, `link-multi-peer`,
  `non-windows-host`). An unregistered id is a loud fail-fast — REGISTER it (a one-line harness change
  in `lazy_core.py`) rather than falling back to the device axis. Canonical DEFERRED_REQUIRES_HOST
  schema: `~/.claude/skills/_components/sentinel-frontmatter.md`.

### Scoped-validated partial — the all-exempt escape hatch (avoid the mcp-test forever-loop)

A `result: partial` whose MCP-driveable scope FULLY passes (`pass_count == total_count`) but whose
ONLY uncovered `Runtime Verification` rows are each a **documented-untestable class** is NOT a dead
end. Left as a bare `partial` it loops forever — `__write_validated_from_results__` refuses any
non-`all-passing` result, so the state machine re-dispatches `/mcp-test` every cycle and the item
never reaches `__mark_complete__` / `__mark_fixed__` (the deadlock behind
`docs/bugs/_archive/partial-mcp-results-all-exempt-rows-no-authorable-validated-path/`). There is a shipped
escape hatch, and this is the ONE narrow case where you author onto the engine-written results file.

- **The mechanism.** `observation_gap_promotable` (`lazy_core/gates.py`) promotes such a partial to a
  scoped `VALIDATED.md` (`result: validated-modulo-observation-gaps`) when the results file carries a
  non-empty `observation_gap_exemptions: [ { surface, spec_class }, ... ]` list AND **every** entry
  carries a non-empty `spec_class` provenance string. It is wired to the apply gate
  (`pseudo.py`), the completion-integrity gate, and Step-9 routing, so a promoted partial validates
  and completes coherently. Canonical schema: `_components/sentinel-frontmatter.md`
  ("`observation_gap_exemptions`").
- **`observation_gap_exemptions` vs `carve_outs` — do not confuse them (this is what loops).**
  `carve_outs` SOFTENS an *otherwise-`all-passing`* run (a host-artifact like capture-ring jitter) —
  it does **NOT** promote a `partial`. Stamping a `carve_outs` block on a `partial` leaves it a
  `partial`, the apply gate correctly refuses, and the loop continues. The PROMOTING block is
  `observation_gap_exemptions`. If your uncovered rows are documented-untestable and you want the
  partial to validate, you need `observation_gap_exemptions`, not `carve_outs`.
- **The narrow authoring carve-out (the ONE exception to "the engine writes sentinels").** The engine
  cannot make the `spec_class` judgment (which uncovered row maps to which documented-untestable
  class), so when the engine writes a `result: partial` whose uncovered rows are all
  documented-untestable, you MAY amend the engine-written `MCP_TEST_RESULTS.md` to add the
  `observation_gap_exemptions` block — **scoped to that block only**. Do NOT touch `result`,
  `pass_count`, `total_count`, or `validated_commit` — those stay engine-owned; you are adding the
  provenance the engine structurally cannot. Every entry MUST cite a real `spec_class` (see below).
- **The gate's refusals are UNCHANGED — this is not a way to launder a failure.** A `partial` with a
  genuine MCP-scope failure (`pass_count < total_count`), with no exemptions, or with a
  provenance-less exemption **still refuses** (the genuine-failure refusal is never relaxed). The
  block only supplies provenance for a scope that already fully passed; it cannot green a real
  failure.
- **Valid `spec_class` values** are the documented-untestable classes in
  `docs/features/mcp-testing/SPEC.md` — e.g. a control surface with **no registered MCP-tool mirror**
  ("Cannot Prove"), a behavior **SPEC-locked to the unit/WDIO test tier**, and
  **`build-artifact-deferred`**: an assertion that IS MCP-driveable in principle but is only reachable
  against a **packaged production build** absent from the dev session (a `Mismatch`/reachability
  branch already covered by the unit/Rust tier and pre-classified in PHASES). Cite the specific class
  per row; a bare/empty `spec_class` does not promote.

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
