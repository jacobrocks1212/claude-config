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
