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
