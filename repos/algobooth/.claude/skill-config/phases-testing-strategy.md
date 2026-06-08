### Testing Strategy Guidance (AlgoBooth)

Each phase's **Testing Strategy** section must specify coverage across the testing pyramid. Not every phase needs every level — select what's appropriate:

| Level | Gate Command | Include When |
|-------|-------------|--------------|
| Unit tests (Rust) | `cargo test -p algobooth-audio-core` / `cargo test -p algobooth-audio-engine` | New Rust functions, DSP algorithms, data structures |
| Unit tests (TS) | `npm run qg -- ts` | New composables, store logic, utils |
| Sidecar integration | `npm run qg -- integration` | Changes to sidecar IPC, pattern evaluation |
| Full audio pipeline | `npm run qg -- full-integration` | Changes to audio routing, callback, mixing |
| Audio quality | `npm run qg:golden` / `qg:realtime` / `qg:multichannel` | DSP changes, effect chains, gain/mix changes |
| Visual regression | `npm run qg:visual` | Visualizer, waveform, UI component changes |
| MCP integration | `/mcp-test {scenario}` | New runtime-observable behavior, new MCP tools |

**MCP Test Scenarios:** If a phase adds observable runtime behavior (new MCP tools, new session events, changed audio behavior), the phase deliverables MUST include:
- [ ] MCP test scenario: `docs/testing/mcp-tests/{scenario-name}.md` (create or update)
- [ ] `/mcp-test {scenario-name}` passes with all assertions verified

**Audio Quality Contracts:** If the spec contains an `## Audio Quality Contracts` section, each phase that modifies audio behavior must reference the relevant contract IDs (e.g., `AQ-EQ-01`) and include them in the phase's MCP Integration Test Assertions block. The `/mcp-test` subagent validates these contracts automatically when present in the scenario file.

---

## Production-Faithful Integration Tests (HARD REQUIREMENT)

> **Why this exists.** "All unit tests green" is the single most dangerous false signal in this codebase. A feature can pass every isolated unit test at every layer and still be completely inert end-to-end, because the unit tests feed *synthetic* inputs the live pipeline never produces. The canonical case study: the Hardware Override Protocol cutoff stamp passed TS serializer tests, Rust resolver tests, and capnp round-trip tests across **four** implementation attempts — yet the override never actuated, because the live sidecar emitted `parameter_id = None` on every hap while every test hand-built `Some(0)`. Only a runtime/MCP check ever caught it. See `docs/features/mixer/hardware-override-protocol/ANALYSIS-actuation-root-cause.md`.

A phase whose deliverables cross **any** boundary — process (sidecar ↔ Rust), serialization (capnp encode/decode, N-API), IPC (Tauri commands), or thread (audio-callback handoff) — MUST include at least one **integration test that drives the real production path end-to-end across that boundary** and asserts the far-side observable. The phase's **Testing Strategy** section must name that test explicitly. Unit-green at each isolated layer is **necessary but NOT sufficient** evidence that a cross-boundary feature works — never let a phase claim a cross-boundary behavior "done" on unit tests alone.

> Consolidated planning-antipattern checklist (grep-before-cite + these smells + the
> bug-vs-feature scoring gap): `docs/development/PLANNING_ANTIPATTERNS.md`.

### The five false-green smells (reject any phase test plan that exhibits these)

1. **Self-referential assertion.** `expect(x).toBe(computeX())` — both sides call the function under test, so `A === A` passes even when `A` is wrong. **Fix:** assert against a concrete ground-truth literal (`expect(parameterId).toBe(0)`, the actual engine constant), never against the resolver/computation being tested.
2. **Hand-injected field across the boundary.** If the risk is "field X is dropped or mangled crossing boundary B," a test that *constructs* `X = correct` on the far side of B never exercises B. **Fix:** drive X from the real upstream source (evaluate a real pattern, send a real IPC message) and assert X survives at the far side.
3. **Fixtures hardcoding the default/none for the field under test.** If every round-trip fixture sets the field to its `None`/default sentinel, the meaningful (`Some(0)`) path has zero coverage. **Fix:** add a fixture that round-trips the *real* non-default value the feature produces.
4. **Test-path ≠ live-path.** A test that reaches production code via a shortcut route (e.g. calling `serializeHaps` directly) can pass while the actual route (`QUERY_ARC → queryArcById → serializeHaps`, with the resolver installed by `StrudelRuntime.initialize()`) fails — different module instance, different value shape, different timing. **Fix:** drive the test through the *same entry point production uses*, or add an explicit parity assertion that both routes produce identical output. A "real evaluation" test that still bypasses the live entry point is not faithful.
5. **Telemetry/register state mistaken for the observable.** Asserting an internal register or telemetry event reflects the change is NOT the same as asserting the *rendered/user-visible* output changed. These are often disjoint code paths. **Fix:** assert the actual observable (rendered audio via `audio_filter`/`get_audio_buffer`, UI state, emitted event payload), not the bookkeeping register that feeds it.

### Per-phase requirement

For each phase, the **Testing Strategy** must answer, in one line each:
- **Entry point:** which production entry point does the integration test drive, and is it the same one production uses? (If not, justify and add a parity check.)
- **Ground-truth assertion:** what concrete literal / observable is asserted at the far side of the boundary (not a re-computation of the value under test)?
- **Boundary coverage:** which boundary(ies) does this test actually cross, and is the field-under-test driven from the real source rather than hand-injected past the boundary?
- **Runtime gate:** if the behavior is runtime-observable, the MCP scenario (per the table above) is the gating test — name it. The phase is not "done" until that scenario passes against the real wire.

If a phase genuinely cannot be integration-tested below the MCP layer, say so explicitly in its Testing Strategy and make the MCP scenario a hard deliverable — do not silently fall back to unit tests and call the boundary covered.
