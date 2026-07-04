---
kind: skip-mcp-test
feature_id: harness-telemetry-ledger
reason: claude-config is pure harness mechanics — no Tauri app, no src-tauri, no package.json app surface, no MCP-reachable surface exists to drive any MCP HTTP tool against. The feature adds a telemetry JSONL ledger emitted by the Python state scripts, a pure-read trends aggregator + /api/trends route on the local pipeline_visualizer, and skill prose; none of it reaches an MCP tool surface.
alternative_validation: pytest (ten-suite gate run 1227 passed / 2 sanctioned skips — incl. 10 new telemetry-emitter tests in test_lazy_core.py and 15 new trends tests in test_pipeline_visualizer.py) + lazy-state.py --test and bug-state.py --test smoke harnesses (each with the new telemetry-ledger-chokepoints fixture; baselines regenerated via _normalize_smoke_output) + lazy_coord.py --test + test_toolify_miner.py + lazy_parity_audit.py --repo-root . (exit 0) + lint-skills.py (clean) + a manual dry-run of the exact D8 retro CLI (python3 -m pipeline_visualizer.trends --run-id <id> --repo-root <repo>) against a fixture ledger.
date: 2026-07-04
skipped_by: pipeline
granted_by: mcp-test
spec_class: standalone — no app integration (no Tauri/MCP surface; harness mechanics validated by pytest + in-file smoke harnesses + parity audit + skill projection/lint)
validated_commit: bb18150c6c319a7bfa79f332abea6cf27eb2adea
---

# MCP Test Skip — Harness Telemetry Ledger + Trends

## Why this feature has no MCP-reachable surface

`harness-telemetry-ledger` lives entirely in **claude-config**, the Claude Code configuration
harness — NOT an application. There is no Tauri app (`src-tauri/` absent), no frontend app
`package.json`, and no MCP HTTP server to connect to. The feature is pure harness mechanics:

- `lazy_core.py` — `append_telemetry_event` / `read_telemetry_events` /
  `_TELEMETRY_LEDGER_FILENAME` + rotation constants / `TELEMETRY_HALT_TERMINAL_REASONS` /
  `flush_cloud_telemetry_segment`, plus `containment-refusal` emission inside the three shared
  exit-3 refusal helpers.
- `lazy-state.py` / `bug-state.py` — mirrored chokepoint emission (run/cycle brackets,
  `--emit-prompt` dispatch + halt, `--apply-pseudo`, `--verify-ledger`, `--gate-coverage`
  (feature-only), `--neutralize-sentinel`) + the D5-B cloud run-end flush.
- `pipeline_visualizer/trends.py` + `/api/trends` + the static Trends tab — a LOCAL analysis
  page over recorded facts (pure read; `probe.py` stays the state authority).
- Skill prose: `/lazy-batch-retro` "Ledger deltas" step; `/lazy-batch-cloud` telemetry-segment
  commit + Differences row.

None of this reaches an MCP tool surface — there is no live runtime to probe. This is the
`standalone — no app integration` untestable class.

## Alternative validation performed (all PASSING, at `validated_commit`)

| Suite | Command | Result |
|-------|---------|--------|
| Ten-suite pytest gate (envelope, marker-gating, fail-open, torn-line/unknown-v tolerance, rotation shift, non-destructive marker read, cloud flush; trends aggregates vs hand-computed values, halt-dwell pairing, empty-ledger honesty, /api/trends route + cache debounce, retro-CLI shape + citations) | `python3 -m pytest test_lazy_core.py test_hooks.py test_pipeline_visualizer.py test_lazy_parity.py test_lazy_queue_doc.py test_lint_skills.py test_surface_resolver.py test_stale_binary.py test_retro_ro9.py test_project_skills.py -q` | **1227 passed, 2 skipped** (the two sanctioned platform skips) |
| Toolify miner | `python3 test_toolify_miner.py` | All tests passed |
| Feature-pipeline smoke (incl. new `telemetry-ledger-chokepoints` fixture: bracket/dispatch/purity/refusal/cloud-flush) | `python3 lazy-state.py --test` | All smoke tests passed (baseline regenerated via `_normalize_smoke_output`) |
| Bug-pipeline smoke (mirrored fixture) | `python3 bug-state.py --test` | All smoke tests passed (baseline regenerated via `_normalize_smoke_output`) |
| Concurrency plane | `python3 lazy_coord.py --test` | All smoke tests passed |
| Coupled-pair parity | `python3 lazy_parity_audit.py --repo-root .` | exit 0 |
| Skill projection + lint (retro + cloud skill edits) | `python3 project-skills.py … --output-dir /tmp/proj-harness-telemetry-ledger` + `python3 lint-skills.py …` | clean |
| D8 retro CLI dry-run | `LAZY_STATE_DIR=<fixture> python3 -m pipeline_visualizer.trends --repo-root <repo> --run-id 2026-07-04T09:00:00Z` | per-run summary with `found: true`, cycle counts, duration, and `ledger_lines` citation window |

Every SPEC Validation-Criteria row names a pytest suite / `--test` fixture / the parity audit as
its "Where to Check"; **zero** rows name an MCP surface. The two deferred rows (manual browser
check of the Trends tab; a live retro + live cloud-segment landing) need a workstation browser /
a real instrumented batch run and are recorded as deferred in PHASES.md — their mechanical data
paths are covered by the `/api/trends` + static-serving tests and the cloud-flush fixture.
