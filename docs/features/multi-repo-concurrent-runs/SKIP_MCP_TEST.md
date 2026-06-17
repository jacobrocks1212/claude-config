---
kind: skip-mcp-test
feature_id: multi-repo-concurrent-runs
reason: claude-config is pure harness mechanics — no Tauri app, no src-tauri, no package.json, no MCP-reachable surface exists to drive any MCP HTTP tool against. The feature scopes the lazy state directory per repo (Python state-script chokepoint + bash hooks); none of it reaches an MCP tool surface.
alternative_validation: pytest (test_lazy_core 412, test_hooks 69, test_pipeline_visualizer 65, test_lazy_parity 23) + lazy-state.py/bug-state.py --test smoke (baselines green) + lint-skills.py --check-projected --check-capabilities (clean) + lazy_parity_audit.py (exit 0). PLUS a live production validation — the feature isolated a concurrent AlgoBooth /lazy-batch run (its marker migrated into its own keyed subdir; --marker-present returns present for AlgoBooth, absent for claude-config).
date: 2026-06-16
skipped_by: pipeline
granted_by: mcp-test
spec_class: standalone — no app integration (no Tauri/MCP surface; harness mechanics validated by pytest + bash hook harness + projection/skill lint, and live-validated against a real concurrent run)
validated_commit: 80e4b403964b94efcb30bc2cbeed5afcf2d57fd6
---

# MCP Test Skip — Multi-Repo Concurrent Runs

## Why this feature has no MCP-reachable surface

`multi-repo-concurrent-runs` lives entirely in **claude-config**, the Claude Code configuration
harness — NOT an application. There is no Tauri app (`src-tauri/` absent), no frontend /
`package.json`, and no MCP HTTP server to connect to. The feature is pure harness mechanics:

- `lazy_core.py` — `repo_key`, the active-repo binding (`set_active_repo_root` / `active_repo_root`),
  the keyed `claude_state_dir()` chokepoint, and `migrate_legacy_state_dir`.
- `lazy-state.py` / `bug-state.py` — the `--marker-present` read-only query + the `main()` active-repo binding.
- The three `PreToolUse` hooks (`lazy-dispatch-guard.sh`, `lazy-route-inject.sh`,
  `lazy-cycle-containment.sh`) — now gate by the current repo via `--marker-present`.
- `pipeline_visualizer` — reads the per-repo keyed marker.

None of this reaches an MCP tool surface — there is no live runtime to probe. This is the
`standalone — no app integration` untestable class.

## Alternative validation performed (all PASSING)

| Suite | Command | Result |
|-------|---------|--------|
| Core unit tests (repo_key, keyed claude_state_dir, migration, per-repo marker independence, --marker-present, cross-script refusal) | `python user/scripts/test_lazy_core.py` | **412 passed** |
| Hook-test harness (two-repo isolation: guard/inject no-op in repo B, deny/inject in repo A) | `python user/scripts/test_hooks.py` | **69 passed** |
| Pipeline-visualizer (keyed-marker lookup) | `python user/scripts/test_pipeline_visualizer.py` | **65 passed** |
| State-script parity (both bind active repo at main()) | `python user/scripts/test_lazy_parity.py` + `lazy_parity_audit.py --repo-root .` | **23 passed**, audit exit 0 |
| Smoke baselines | `lazy-state.py --test` / `bug-state.py --test` | green (no baseline change) |
| Skill projection + lint | `lint-skills.py --check-projected --check-capabilities` | clean |

Every SPEC Validation-Criteria row names `pytest` / `test_hooks.py` / `test_lazy_core.py` as its
"Where to Check"; **zero** rows name an MCP surface (every phase's MCP Integration Test
Assertions block is `N/A — no MCP surface`).

## Live production validation (recorded — not a defect)

During implementation, a **concurrent AlgoBooth `/lazy-batch` run** was live (session
`5d4b6c93…`, `d8-track-pattern-interaction`, cycle 1/40). The Phase-1 migration moved that run's
singleton base marker into its keyed subdir (`repo_key(AlgoBooth) = 37850b6e…`); the run continued
transparently on the keyed code. Read-only proof of isolation at `validated_commit`:

- `lazy-state.py --marker-present --repo-root C:/Users/Jacob/repos/AlgoBooth` → exit 0 (present)
- `lazy-state.py --marker-present --repo-root <claude-config>` → exit 1 (absent)

i.e. the two repos' runs coexist without cross-blocking — the exact capability this feature adds,
demonstrated against a real run rather than a fixture.
