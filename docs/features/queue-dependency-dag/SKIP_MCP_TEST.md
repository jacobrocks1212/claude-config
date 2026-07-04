---
kind: skip-mcp-test
feature_id: queue-dependency-dag
reason: claude-config is pure harness mechanics — no Tauri app, no src-tauri, no package.json, no MCP-reachable surface exists to drive any MCP HTTP tool against. The feature adds the machine-enforced queue `deps` field to the two Python state scripts (loader validation, the compute_state dep-gate, the --sync-deps feeder, probe keys/terminals) plus docs/skill prose; none of it reaches an MCP tool surface.
alternative_validation: pytest (test_lazy_core 894 incl. 16 new dep-DAG tests, test_hooks, test_pipeline_visualizer, test_lazy_parity 31 incl. the new sync-deps surface fixtures, test_lazy_queue_doc, test_lint_skills, test_surface_resolver, test_stale_binary, test_retro_ro9, test_project_skills — 1217 passed, 2 sanctioned skips) + lazy-state.py --test / bug-state.py --test smoke suites (18 new dep-gate/feeder fixture assertions across both; baselines re-pinned via _normalize_smoke_output, purely additive diffs) + lazy_coord.py --test + test_toolify_miner.py + lazy_parity_audit.py --repo-root . (exit 0 with the new sixth surface) + project-skills.py lane-local projection + lint-skills.py (clean).
date: 2026-07-04
skipped_by: pipeline
granted_by: mcp-test
spec_class: standalone — no app integration
validated_commit: 64da7c60e74e0835f8caa7da49d22f8a51730f87
---

# MCP Test Skip — First-Class Dependency DAG in queue.json

## Why this feature has no MCP-reachable surface

`queue-dependency-dag` lives entirely in **claude-config**, the Claude Code configuration
harness — NOT an application. There is no Tauri app (`src-tauri/` absent), no frontend /
`package.json`, and no MCP HTTP server to connect to. The feature is pure harness mechanics:

- `lazy_core.py` — `parse_dep_block` (relocated), `dep_ids`, `detect_dep_cycle`,
  `validate_dep_id_list`, `validate_queue_deps`, `dep_completion_status` (receipt-gated,
  archive-aware for bugs), `format_unknown_dependency_blocker`, `sync_deps`, and the
  `queue-exhausted-dependency-gated` sanctioned terminal.
- `lazy-state.py` / `bug-state.py` — loader validation, the walk-loop dep-gate + `dep_gated`
  probe key + unknown-dependency fail-fast + terminal, the probe-time drift diagnostic, the
  `--sync-deps` CLI, `--enqueue-adhoc --deps`, and (feature-only) the skip-ahead key-1 union.
- `lazy_parity_audit.py` — the sixth state-script parity surface (`--sync-deps`).
- Docs/skill prose — `/spec-phases` Step 1.6, `adhoc-enqueue.md`, `dep-block-schema.md`
  "Queue projection", `user/scripts/CLAUDE.md`, root `CLAUDE.md`, `docs/features/CLAUDE.md`.

None of this reaches an MCP tool surface — there is no live runtime to probe. This is the
`standalone — no app integration` untestable class.

## Alternative validation performed (all PASSING)

| Suite | Command | Result |
|-------|---------|--------|
| Core unit tests (dep-block parser relocation, dep_ids shapes, Kahn's cycle detection, load-time validation die-cases, receipt-gated dep-completion classifier incl. archive-aware bug resolution + spec_dir hints, unknown-dependency blocker body, sanctioned terminal membership, sync_deps write/noop/byte-stability/empty-set-key-removal/self-dep + written-cycle refusal) | `python3 -m pytest test_lazy_core.py -q` | **894 passed, 1 skipped** (sanctioned Windows cold-boot skip) |
| State-script parity (sixth surface: `--sync-deps` on both scripts; lockstep stub fixtures + fires-when-missing case) | `python3 -m pytest test_lazy_parity.py -q` + `python3 lazy_parity_audit.py --repo-root .` | **31 passed**, audit exit 0 |
| Full pytest gate (hooks, visualizer, queue-doc, lint-skills, surface-resolver, stale-binary, retro-ro9, project-skills incl. the above) | `python3 -m pytest <10 files> -q` | **1217 passed, 2 skipped** (the two sanctioned skips) |
| Feature smoke (hold+advance, transitive hold, strict-flag independence, completion unlock, reorder-composes, dangling + Superseded unknown-dependency fail-fast, all-gated terminal, skip-ahead union seam + layering, drift diagnostic, enqueue --deps + reserved-prefix refusal, --sync-deps write/noop/cycle-subagent exit-3 refusal) | `python3 lazy-state.py --test` | **All smoke tests passed** (baseline re-pinned via `_normalize_smoke_output`; diff purely additive) |
| Bug smoke (mirrored hold+advance, ARCHIVE-AWARE dep resolution, Won't-fix + dangling fail-fast, all-gated terminal, --sync-deps write/noop/refusal, drift diagnostic, enqueue --deps) | `python3 bug-state.py --test` | **All smoke tests passed** (baseline re-pinned; diff purely additive) |
| Concurrency plane + miner (unaffected-surface regression) | `python3 lazy_coord.py --test` + `python3 test_toolify_miner.py` | **All tests passed** |
| Skill projection + lint (spec-phases Step 1.6, adhoc-enqueue --deps, dep-block-schema queue-projection paragraph) | `project-skills.py --output-dir /tmp/proj-queue-dependency-dag` + `lint-skills.py` | clean |

Every SPEC Validation-Criteria row names a probe-JSON fixture, CLI exit/stderr check, on-disk
sentinel, or test suite as its "Where to Check"; **zero** rows name an MCP surface (every phase's
MCP Integration Test Assertions block is `N/A — no MCP-reachable surface`).

## Byte-identity contract (the load-bearing negative)

Both `--test` baselines changed ONLY by the new fixtures' printed lines (verified additive-only at
each re-pin); every pre-existing fixture line is byte-identical, proving queues without `deps`
behave exactly as before on load, walk, probe, and terminal paths.
