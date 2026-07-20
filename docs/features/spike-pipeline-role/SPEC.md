# Spike — Runtime-Proof Pipeline Role — Feature Specification

> A first-class lazy-pipeline stage that definitively PROVES things about the running
> system (a runtime measurement, a GO/NO-GO verdict, a confirm/deny of real behavior),
> instead of dead-ending into a manual operator block.

**Status:** Complete
**Priority:** P1
**Owner:** harden-harness (originated Round 80, 2026-07-17)
**Last updated:** 2026-07-17

**Depends on:** (none)
<!-- All reused machinery (unified-pipeline-orchestrator; the mcp-test runner/verdict shape;
long-build-and-runtime-ownership's --ensure-runtime) is already Complete, so there is no blocking
upstream ordering constraint. Spike composes with that machinery but is gated by none of it. -->

## Origin — the motivating incident

`hydra-overlay` became BLOCKED with `blocker_kind: runtime-spike-verdict-pending`: a runtime
FPS measurement was needed to choose a frame-delivery architecture (single-render
frame-shipping vs. independent-render second-sidecar), but **the pipeline had no stage that
could perform a runtime proof.** It dead-ended into a manual operator block. Worse, running
the spike required MCP tooling that did not yet exist (`hydra_set_enabled`,
`hydra_projector_spike_open`), forcing the operator to hand-run a "add corrective phase →
build tooling → then run the spike" loop by hand.

The exact spike this generalizes: `AlgoBooth:docs/features/visuals/hydra-overlay/SPIKE_PROJECTOR_FPS.md`.

Spike makes that a first-class, automated pipeline capability. Its true purpose: **definitively
prove things — usually with runtime — in an HONEST, COMPLETE, and AUDITABLE way**, usable both
PRESCRIBED (declared in a SPEC/phase) and AD-HOC (invoked when a situation needs such a proof).

## Root-cause classification (harden-harness Step 2)

- **Class:** `missing-contract` — a legitimately novel pipeline situation (a phase whose
  completion rests on a runtime proof) had no emit path, no routing, no resolver. The harness
  was never designed for the "prove it at runtime" case; the only terminals were `mcp-validation`
  (a specific pass/fail assertion suite) and a manual `BLOCKED.md`.
- **Verified symptom:** `hydra-overlay/SPIKE_PROJECTOR_FPS.md` VERDICT: PENDING; a BLOCKED.md
  with a `blocker_kind` (`runtime-spike-verdict-pending`) the state machine has no branch for
  (confirmed: `grep blocker_kind` across `lazy_core/` + `lazy-state.py` enumerates only
  `mcp-validation`, `mcp-runtime-unready`, `unknown-host-capability`, `unknown-dependency`,
  `plan-structural-invalid` — no spike resolver).

## The five requirements (operator brief, verbatim intent)

1. **Purpose** — fill exactly the gap that caused hydra-overlay to block: a stage that proves
   things about the running system, instead of dead-ending into a manual block.

2. **Tooling-existence loop** — Spike FIRST ensures the tooling to execute the spike exists.
   If NOT, it redirects back to the **`/add-phase` corrective path** ("add a corrective phase
   to expose the tooling"), which builds the tooling; then control RETURNS to Spike to run the
   proof. This LOOPs if a tooling gap is discovered again — with a **bound / loop guard** so it
   cannot spin forever. This is exactly the loop the operator hand-performed for hydra-overlay
   (needed `hydra_set_enabled` / `hydra_projector_spike_open` → added corrective Phase 9.5 →
   built it → then ran the spike).

3. **Structured report consumed by the lazy pipeline** — Spike returns a STRUCTURED report the
   orchestrator presents to the operator AND uses to direct the pipeline to the pre-documented
   course prescribed by the SPEC/plan. For a PASS/FAIL-form Spike:
   - **PASS** → continue to the prescribed next cycle (the spec/plan documents what comes next
     on PASS).
   - **FAIL** → update the relevant documentation (the spike's results doc + the gated phase),
     write `NEEDS_INPUT.md`, HALT, present to the operator.
   - **NO provisional auto-accept for a Spike FAIL.** Even under `--park --park-provisional` a
     Spike FAIL must NEVER be auto-accepted on recommendation. Under `--park --park-provisional`
     the feature is PARKED (surfaced at the flush); under plain mode it halts at needs-input.
     This is a deliberate carve-out from the normal park-provisional path — encoded explicitly
     in the provisional-eligibility predicate AND the Spike handler.

4. **Works like `/mcp-test`; reuse its parts** — model Spike on `/mcp-test` and REUSE where
   applicable: scenario resolution, the ensure-runtime / runtime-readiness pattern, verdict.json
   writing, sentinel forwarding. Runtime is **ORCHESTRATOR-OWNED** (exactly like mcp-test's
   runtime — the orchestrator boots/owns the dev runtime and the Spike cycle drives it), NOT
   sub-subagent-owned.

5. **Not only fps-style measurement** — a Spike may also be writing tests, or investigating real
   runtime behavior to confirm/deny an assumption via `/investigate`. Spike is the general
   "prove it at runtime, honestly" role; `/investigate` is one of its tools.

6. **Prescription in the authoring skills (AlgoBooth-scoped ONLY)** — `/spec`, `/spec-phases`,
   and `/add-phase` KNOW about Spike and PRESCRIBE it where appropriate (a phase whose completion
   rests on a runtime proof carries a Spike stage). ESPECIALLY for CORRECTIVE phases: where
   multiple corrective phases have occurred against the same runtime-coupled assumption,
   prescribing a Spike to definitively prove the assumption is the right move instead of another
   blind corrective. These updates are AlgoBooth-scoped (the `repos/algobooth/.claude/skill-config/`
   addenda the generic skills `!cat` with a repo-override), NOT the generic cross-repo skills.

7. **Honesty + auditability are load-bearing** — a Spike verdict MUST be backed by real observed
   evidence (runtime numbers, test results, an `/investigate` ledger), NEVER inferred or
   fabricated. This mirrors the discipline `SPIKE_PROJECTOR_FPS.md` already states: no fabricated
   fps number, no static-trace substitute for the real measurement.

## Architecture

Spike is a **dispatched cycle** (like `/investigate`), driven by an **orchestrator-owned
runtime** (like `/mcp-test`). It is a new registered dispatch class `spike`, always Opus (the
verdict is judgment work: it weighs real evidence, decides GO/NO-GO honestly, and detects a
tooling gap).

### Reuse map (from the mcp-test machinery)

| Concern | Reuse target |
|---|---|
| Orchestrator-owned runtime boot + readiness | `lazy-state.py --ensure-runtime` (`lazy_core.ensure_runtime`, the M4 state machine); route on the full `{state, health_code, mcp_tools_present}` JSON |
| Compact verdict (model-context budget) | `scripts/mcp-test/verdict.ts` shape — a compact verdict + raw payloads to a sibling artifact |
| Deterministic engine entry (where a spike has a scenario) | `scripts/mcp-test/run.ts` `executeRun()` pattern |
| Scenario grammar/parse | `schema.ts` + `loader.ts` (`loadScenario`) |
| Sentinel forwarding | engine-written sentinel pattern (`sentinel.ts` `emitSentinel()`) |
| PHASES reconcile (gate-boundary-safe) | `reconcile-phases.ts` `reconcilePhase()` |
| Prescription header | `**MCP runtime:**` PHASES header read by `emit_cycle_prompt` — the model for `**Spike:**` |
| Dispatch class + registry-validated prompt | `--emit-dispatch investigation` (the closest analog: on-demand, orchestrator-judgment, hash/nonce guard-allowed) |

### The routing signals

Spike is entered by EITHER of two signals (mirroring how mcp-test is both prescribed via a
header and re-requested via a sentinel):

1. **Prescribed — a `**Spike:**` phase-declaration line** (analogous to `**MCP runtime:**`). A
   phase whose completion rests on a runtime proof carries `**Spike:** required — <one-line
   proof goal>`. The state machine routes that phase's completion through a `spike` cycle before
   the phase is considered done / before the MCP gate.

2. **Ad-hoc / blocked — `blocker_kind: runtime-spike-verdict-pending`.** A `BLOCKED.md` carrying
   this `blocker_kind` names Spike as its resolver: the state machine routes to a `spike` cycle
   instead of the generic manual-block terminal. This is the exact `blocker_kind` hydra-overlay
   dead-ended on.

### The structured report / verdict schema

Spike's verdict is carried by a **plain results/audit markdown doc** (the pattern
`SPIKE_PROJECTOR_FPS.md` already uses — NOT a new recognized sentinel filename, so no
cross-repo `check-docs-consistency.ts SENTINEL_SCHEMAS` lockstep is required, keeping the whole
role inside claude-config per harden-harness Prohibition #1). Routing rides on ALREADY-recognized
sentinels: `BLOCKED.md` (`blocker_kind: runtime-spike-verdict-pending`) on entry, and
`NEEDS_INPUT.md` on FAIL.

The results doc (canonical name `SPIKE_VERDICT.md` in the feature dir, or the prescribed
per-spike doc named by the `**Spike:**` line) carries a compact structured header the orchestrator
parses:

```yaml
---
spike_id: <feature-or-proof id>
verdict: PASS | FAIL | PENDING     # PENDING only while the proof has not yet run
method: runtime-measurement | investigate | tests | mixed
evidence:                          # >=1 — NEVER empty on a PASS/FAIL verdict
  - kind: measurement | test-result | investigation-ledger
    value: <the real observed number / result / artifact path>
    source: <how it was observed — HUD read, log heartbeat, test id, INVESTIGATION.md path>
tooling_ok: true | false           # false ⇒ the tooling-existence loop fired (see below)
date: <YYYY-MM-DD>
---
```

**Honesty invariant (enforced by the Spike subagent contract):** a `verdict: PASS|FAIL` with an
empty `evidence:` list, or evidence whose `value` is inferred/fabricated rather than observed,
VOIDS the cycle — the Spike returns `PENDING` + a NEEDS_RUNTIME/tooling signal instead. No
fabricated number, no static-trace substitute for a real measurement.

### The tooling-existence loop (bounded)

Before running the proof, the Spike cycle asserts the tooling it needs exists (e.g. the MCP
tools the measurement calls — cross-checked against the repo's live tool registry, the same
`mcp-tool-catalog.md` audit `/spec-phases` uses). On a gap:

1. The Spike writes `tooling_ok: false` + names the missing tooling in its report.
2. It routes to the `/add-phase` corrective path: a corrective phase is authored to expose the
   tooling (tagged `**Phase kind:** corrective`, carrying a `**Spike:**` line so control RETURNS
   to Spike once the tooling phase completes).
3. The corrective phase is built by the normal pipeline; when it completes, the `**Spike:**`
   signal re-routes to the Spike cycle to run the proof.

**Loop guard (bound):** a `spike_tooling_rounds` counter on the entry sentinel / feature state
is incremented each time the tooling loop fires for the same spike. On exceeding a hard cap
(**default 3**), Spike STOPS looping and writes a `NEEDS_INPUT.md` ("tooling gap persists after
N corrective rounds — operator decision needed") — the loop can NEVER spin forever. This mirrors
the retry-count discipline the validation gate already uses.

### PASS/FAIL orchestrator-loop branching

- **PASS** → the Spike ticks the gated phase's spike deliverable (gate-boundary-safe reconcile,
  never flipping top status / never writing a receipt), records the verdict in the results doc,
  and the pipeline continues to the prescribed next cycle (whatever the SPEC/plan documents on
  PASS — e.g. "Phase 10 proceeds on the single-render architecture").
- **FAIL** → the Spike updates the results doc + the gated phase docs, writes `NEEDS_INPUT.md`
  (`written_by: spike`), and HALTS. Under `--park --park-provisional` the feature is PARKED
  (surfaced at the flush), NEVER auto-accepted.

### The provisional-eligibility carve-out (Spike FAIL never auto-accepted)

`lazy_core.provisional_eligibility(sentinel_path)` (docmodel.py) gains an exclusion mirroring the
existing `written_by == "completion-integrity-gate"` line: a `NEEDS_INPUT.md` written by Spike
(`written_by: spike`) OR carrying `spike_verdict: fail` is NEVER provisional-eligible
(fail-closed). Both callers (the park-mode routing peek and the `--provisionalize-sentinel` CLI
action) re-run this single predicate, so the carve-out is airtight.

## Integration surface (concrete)

| Surface | Change |
|---|---|
| Dispatch registry | `spike` added to `DISPATCH_CLASSES` (before `hardening`, keeping it last), `DISPATCH_MODELS` (`opus`), `DISPATCH_STEP_NAMES` (`Spike`) — `lazy_core/dispatch.py` |
| Dispatch template | new `user/skills/_components/lazy-batch-prompts/dispatch-spike.md` (the Opus subagent contract) |
| Orchestrator component | new `user/skills/_components/spike-dispatch.md` (emit-reference, like `investigation-dispatch.md`) |
| Validate-deny guard | **NO CHANGE** — the guard validates by prompt hash/nonce, not a per-class allowlist; a registry-emitted `spike` prompt is allowed automatically (confirmed: `lazy_guard.py` consults `class` only for the depth-1 hardening cap) |
| Header parse | `phases_spike_required(spec_path)` + `_read_spike_decision(spec_path)` in `docmodel.py`, exported via `__init__.py` — anchored regex mirroring `phases_mcp_runtime_not_required` |
| State-machine routing | Step 9.5 in `compute_state` (`lazy-state.py`) emitting `sub_skill="spike"` on the `**Spike:**` header / `runtime-spike-verdict-pending` blocker; gate Step 10 `entry_ok` on the spike verdict — **coupled mirror into `bug-state.py`** |
| Blocker escalation | a `runtime-spike-verdict-pending` branch beside `validation_escalation` (`gates.py` / `lazy-state.py:~3055`) |
| Provisional carve-out | Spike-FAIL exclusion in `provisional_eligibility` (`docmodel.py`) |
| Orchestrator loop | a Spike Step in `lazy-batch/SKILL.md` (ensure-runtime pre-boot for spike cycles + PASS/FAIL branch) — **coupled mirror into `lazy-bug-batch` + `lazy-batch-cloud` via the overlay generator** |
| Authoring-skill prescription | AlgoBooth-scoped addenda: `/spec` (`spec-testing-guidance.md`), `/spec-phases` (`phases-runtime-verification.md`), `/add-phase` (`phases-runtime-validation.md`) — `repos/algobooth/.claude/skill-config/` |

## Non-goals / explicit out-of-scope

- **A new recognized sentinel filename** (`SPIKE_VERDICT` as a schema in
  `sentinel-frontmatter.md` + AlgoBooth `check-docs-consistency.ts SENTINEL_SCHEMAS`). Deliberately
  avoided: it would require a target-repo (AlgoBooth) edit, which harden-harness may not make
  (Prohibition #1). The verdict rides on a plain audit doc + already-recognized sentinels. If a
  recognized sentinel is later wanted, it is an AlgoBooth-repo change outside harden-harness scope
  (surfaced in PHASES).
- **Editing the generic cross-repo `/spec` / `/spec-phases` / `/add-phase` prose.** Prescription
  is AlgoBooth-scoped per requirement 6.
- **A bespoke deterministic spike engine** beyond reusing the mcp-test runner shape — a spike is
  often an `/investigate` or a manual measurement with no scenario, so an engine is optional and
  phased.

## Open questions (surfaced for the operator, non-blocking)

1. **Spike verdict doc — recognized sentinel or plain audit doc?** This spec chooses a plain
   audit doc to stay inside harden-harness scope. If the operator wants full lint/gate coverage
   of the verdict schema, promoting it to a recognized sentinel is a follow-up AlgoBooth-repo
   change.
2. **Tooling-loop cap value.** Defaulted to 3 (mirrors the validation retry discipline). Operator
   may tune.
3. **Does a prescribed Spike gate the MCP step, run after it, or interleave?** This spec routes
   Spike as Step 9.5 (after implementation phases, at/around the MCP gate). The precise ordering
   vs. `/mcp-test` is settled in the routing phase (Phase 2) and may itself warrant a Spike-style
   confirmation on a real feature.
