## Testing Pyramid & Audio Quality Contracts (AlgoBooth)

When writing the Validation Criteria table, consider every level of AlgoBooth's testing pyramid:

| Level | Scope | How to Validate | When to Include |
|-------|-------|-----------------|-----------------|
| **Unit tests** | Pure functions, data transforms, DSP primitives | `cargo test -p algobooth-audio-core`, `npm run qg -- ts` | Always — every phase should have unit tests |
| **Integration tests** | Sidecar IPC, audio engine pipeline | `npm run qg -- integration`, `npm run qg -- full-integration` | When touching sidecar, IPC, or audio routing |
| **Audio quality tests** | Golden snapshots, real-time budget, multichannel | `npm run qg:golden`, `npm run qg:realtime`, `npm run qg:multichannel` | When modifying DSP, effects, gain, mixing |
| **Visual regression** | Viz component rendering | `npm run qg:visual`, `npm run qg:perf` | When modifying visualizer or UI layout |
| **MCP integration tests** | End-to-end runtime behavior via `/mcp-test` | `docs/testing/mcp-tests/{scenario}.md` | When adding observable runtime behavior |

### Audio Quality Contracts

If the feature affects audio output (new DSP, effects, gain changes, routing, mixing), the spec MUST include an `## Audio Quality Contracts` section. Each row defines a measurable assertion that `/mcp-test` can verify at runtime using the audio quality MCP tools:

```markdown
## Audio Quality Contracts

| ID | Condition | Channel | Tool | Measurement | Assert |
|----|-----------|---------|------|-------------|--------|
| AQ-XX-01 | {Strudel pattern or control state} | main/cue/mix | audio_pitch / audio_filter / audio_distortion / audio_lufs / audio_spectrum / audio_reverb / audio_stereo / audio_dynamics / audio_modulation / audio_artifact_scan | {response field} | {range, threshold, or boolean} |
```

**Required-but-possibly-missing tooling (capture as a Locked Decision).** The `Tool` column above is the menu of EXISTING audio-quality tools to assert against. Separately, if a contract row (or any Validation Criteria row) names an MCP tool that does NOT yet exist in AlgoBooth's surface — a new control-tier tool for a new store/substrate, a new template-binding tool, etc. — capture it as a **Locked Decision** naming the required tool (so `/spec-phases`' MCP tool-existence audit greps the catalog, finds it absent, and auto-authors a build phase up front rather than discovering it late at `/mcp-test`). Land the capture in the SPEC's `## Locked Decisions` table (the gate-parseable surface), e.g. `| L4 | Required MCP tooling: \`set_slip_pad_template\` must be registered before /mcp-test (absent today — build). |`. See `docs/bugs/mcp-tooling-not-predetermined-at-planning`.

**Available audio quality tools and their key measurements:**

| Tool | Key Measurements |
|------|-----------------|
| `audio_pitch` | `dominant_frequency_hz`, `confidence`, `cents_error` |
| `audio_spectrum` | `spectral_centroid_hz`, `noise_floor_dbfs`, `harmonic_ratio` |
| `audio_filter` | `cutoff_hz`, `rolloff_db_per_octave` |
| `audio_distortion` | `thd_percent`, `aliasing_ratio_db`, `aliasing_audible` |
| `audio_lufs` | `integrated_lufs` |
| `audio_reverb` | `rt60_seconds`, `edt_seconds`, `c80_db`, `ned_score` |
| `audio_stereo` | `balance`, `mid_side_ratio_db`, `mean_correlation` |
| `audio_dynamics` | `attack_ms`, `release_ms` |
| `audio_modulation` | `detected`, `rate_hz`, `depth` |
| `audio_artifact_scan` | `clean`, `clicks.count`, `clipping.clip_count`, `dropouts.count` |

### MCP Test Scenario

If the feature introduces new MCP tools or observable behaviors, the spec should note that a `/mcp-test` scenario will be created or updated during implementation. Reference the scenario path: `docs/testing/mcp-tests/{feature-slug}.md`.

## AGPL / IP Placement (AlgoBooth — required SPEC section)

AlgoBooth ships AGPL-3.0 code in **public sidecars** — currently `strudel-sidecar/` (Strudel: `@strudel/*`, `superdough`) and `hydra-sidecar/` (`hydra-synth`), plus any future one. Every file in a public sidecar is disclosed at release, so where code lands is an IP decision — keep business-differentiating AlgoBooth IP host-side in the proprietary app.

Any SPEC for a feature touching **pattern/visual evaluation, a public AGPL sidecar, or IPC** MUST include an `## AGPL / IP Placement` section answering, in order:

- **(a)** Does any part need a sidecar's AGPL library (`@strudel/*`/`superdough`, `hydra-synth`, …), its live objects (e.g. Strudel `Pattern` objects), or the eval scheduler? If **no** → all code lands host-side in the proprietary app; state that and move on (the remaining questions are N/A).
- **(b)** For each sidecar-side piece: why can't it be host-side computation over data that already crosses the wire? (Every public sidecar — `strudel-sidecar/`, `hydra-sidecar/` — is public AGPL code, see `docs/legal/AGPL_PUBLICATION_MANIFEST.md`.)
- **(c)** Does it add a new kind of payload to `audio_event.capnp`? → `docs/legal/AGPL_ISOLATION.md` must be updated in the same commit.
- **(d)** Does it introduce a new AGPL dependency (e.g. `hydra-synth`) or any server-side execution of a sidecar's AGPL library (Strudel, hydra, …)? → manifest entry first.

Features with no contact with pattern/visual evaluation, a public AGPL sidecar, or IPC may omit the section. Downstream gates enforce this: `/spec-phases`' AGPL / IP Placement audit refuses to draft phases against a touching SPEC that lacks the section, and the planning/fix touchpoint gate refuses unjustified new files under any public AGPL sidecar (`strudel-sidecar/`, `hydra-sidecar/`).

## Runtime-Proof Spikes (when behavior rests on an unproven runtime fact)

When a SPEC's design rests on a runtime fact that is not yet PROVEN — a sustained
measurement (fps/latency/throughput), a GO/NO-GO architectural fork whose choice depends on
real runtime cost, or a confirm/deny of how the running system actually behaves — do NOT bake
the assumption into the design silently. Note in the SPEC that a **Spike** (the pipeline's
runtime-proof stage) will prove it at runtime, and document the two courses the proof selects
between:

- **On PASS** — the prescribed baseline design proceeds (name it).
- **On FAIL / NO-GO** — the prescribed fallback (name it); the Spike halts with a
  `NEEDS_INPUT.md` presenting exactly this fork, and is NEVER auto-accepted.

A Spike verdict MUST be backed by REAL observed evidence (a measured number, a test result, an
`/investigate` ledger) — NEVER an inferred or fabricated value, NEVER a static-trace substitute
for the real measurement. Spike is the general "prove it at runtime, honestly" role; a
behavior-confirmation spike may use `/investigate`. See
`docs/specs/spike-pipeline-role/SPEC.md` (originating incident:
`docs/features/visuals/hydra-overlay/SPIKE_PROJECTOR_FPS.md`, where a missing runtime-proof
stage dead-ended into a manual block). `/spec-phases` turns this into a `**Spike:** required`
phase declaration.
