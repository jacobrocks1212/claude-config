#### Runtime Assumption Validation Gate (AlgoBooth — BEFORE DRAFTING PHASES)

> **Why this gate exists.** The Hardware Override Protocol was planned and re-planned FOUR times against a code-read assumption (`parameter_id` is stamped correctly) that the *running* sidecar contradicted — it emitted `None` on every hap. Every code review and unit test agreed with the wrong assumption; only live runtime observation at the capnp decode boundary exposed it. When a phase plan rests on how the running system actually behaves, confirm it against the running system before committing the plan. See `docs/features/mixer/hardware-override-protocol/ANALYSIS-actuation-root-cause.md`.

**Step A — Enumerate the plan's runtime-coupled assumptions.** From the boundary analysis (Step 2) and the SPEC, list every assumption the phases depend on that is NOT provable from source alone. Runtime-coupled smells (any of these → validate):
- the runtime shape/contents of data crossing a boundary — what a function/closure actually receives at call time (e.g. the `value` a sidecar resolver sees), not what the type or a unit-test fixture says;
- whether an existing production code path actually fires / is reached (vs. merely exists in source);
- the live output a separate process emits — the sidecar's serialized haps over the capnp / named-pipe wire;
- a rendered/observable audio or effect result (cutoff, gain, routing, mix);
- timing/ordering across the audio-callback thread or IPC.

**Step B — Validate the load-bearing ones against the running app (where appropriate).** AlgoBooth is MCP-testable — use it. Cheap runtime checks available from the orchestrator session:
- Boot/reuse the dev app per `docs/development/CLAUDE.md` (resolve the CURRENT `logs/session-*/` dir fresh — NEVER cache it).
- Drive real input: `update_code` to load a real pattern; `inject_midi` for hardware events; `load_test_tone` for synthetic audio.
- Observe real output: `audio_filter` / `get_audio_buffer` (POST, `capture` feature) for rendered audio + `rms`/`dc_offset`/`scheduler_playing`; `get_console_logs` / `get_session_events` for sidecar/runtime signals; the override/telemetry tools for register state. Authoritative tool list + HTTP methods: `MCP_USAGE_GUIDE.md` + `src-tauri/src/ipc/mcp/registrations.rs` (several `get_*` tools are POST — do not infer from the name).
- For a data-shape assumption at a process boundary, a one-off `tracing::warn!` / `console.error('[DIAG] …')` at a **non-hot-path** boundary (e.g. the capnp decode site, sidecar stderr — **NEVER the audio-callback hot path**), then rebuild + short run + grep the session log, is the decisive check. Revert the instrumentation afterward and leave the tree clean.

Record the OBSERVED ground truth (the actual tool calls + numbers, or the logged value) in a `## Validated Assumptions` note at the top of PHASES.md and in the affected phase's Integration Notes. That note MUST contain a **per-assumption ledger table**:

| assumption | how-confirmed (`grep` / `runtime` / `spike`) | evidence |
|---|---|---|
| … | … | … |

"Code-read" is **not** an allowed `how-confirmed` value for any assumption that carries a runtime-coupled smell (from Step A). An assumption may be marked code-provable only if it carries NONE of those smells — state that determination explicitly in the ledger row, not in free text.

**Boundary-reachability rule (sidecar plans):** for any plan touching the sidecar, the confirmation MUST read the **spawn site / transport wiring** (where the sidecar process is actually launched and how messages reach it), NOT merely a handler `match` arm. `sidecar-watchdog` and `save-form-validation` both planned against code paths that exist in source but are never reached in production — that is the four-attempt trap in a different costume.

**Architecture-topology rule (per-channel / per-cue audio processing):** any plan that proposes per-channel or per-cue data-structure widening MUST cite the actual bus declarations in `callback/mod.rs` (the real fixed bus count) BEFORE proposing that widening. `eq-filter-ui` planned an array-widening the fixed 2-bus engine could never deliver.

**Step C — If validating now is premature** (the behavior doesn't exist until the feature is built), schedule it as an explicit **early runtime spike** deliverable in Phase 0 / the first phase ("instrument and confirm X at the live boundary before building on it") with a `- [ ]` checkbox under **Runtime Verification**. Never let a load-bearing runtime assumption ride unverified into a later phase.

**When to skip (record the reason):** an assumption may be marked code-provable in the ledger ONLY if it carries none of the runtime-coupled smells from Step A — pure logic, types, config, UI layout, or a behavior-preserving refactor with snapshot/golden coverage, with no sidecar/IPC/audio-observable behavior in play. The skip is stated in the ledger row itself; free-text notes outside the ledger are not sufficient.

**Anti-pattern (the four-attempt trap):** reading source to "confirm" a runtime assumption that crosses a boundary. Unit-green and a plausible code read are NOT runtime confirmation. For cross-boundary or runtime-observable behavior, observe the running system before planning on it. This gate pairs with the production-faithful **Testing Strategy** guidance (what you then test) — this gate governs what you *confirm before planning*, that one governs what you *assert when implementing*.
