---
kind: skip-mcp-test
feature_id: cross-platform-setup
reason: claude-config is pure harness mechanics — no Tauri app, no src-tauri, no package.json, no MCP-reachable surface exists to drive any MCP HTTP tool against. The feature is a stdlib-only Python CLI at the repo root (setup.py) porting setup.ps1's symlink bootstrap/check/repair over the existing manifest.psd1; none of it reaches an MCP tool surface.
alternative_validation: pytest (test_setup_py 66 — psd1 parser incl. the REAL manifest.psd1 pinned, mapping expansion incl. alias repos + --repos-root + skip-absent, bootstrap/check/repair parity rows, mocked-platform Windows link selection, temp-HOME subprocess end-to-end) + full repo gate suite (test_lazy_core, test_hooks, test_pipeline_visualizer, test_lazy_parity, test_lazy_queue_doc, test_lint_skills, test_surface_resolver, test_stale_binary, test_retro_ro9, test_project_skills, test_setup_py = 1268 passed, 2 sanctioned skips) + test_toolify_miner.py (all passed) + lazy-state.py/bug-state.py/lazy_coord.py --test smoke (all green, no baseline change) + lazy_parity_audit.py --repo-root . (exit 0) + lint-skills.py (clean). PLUS a live end-to-end in THIS cloud container — a fresh temp HOME, `python3 setup.py bootstrap --target User` materialized all 11 User-scope symlinks into the clone and `check --target User` exited 0; full-manifest `check` honestly reported the absent Windows repos as skips (never broken).
date: 2026-07-04
skipped_by: pipeline
granted_by: mcp-test
spec_class: standalone — no app integration (no Tauri/MCP surface; a root-level Python CLI validated by hermetic pytest fixtures + a real container self-host run)
validated_commit: c1b358a11d1347809bc1e816c9985704468b5ff3
---

# MCP Test Skip — Cross-Platform Setup

## Why this feature has no MCP-reachable surface

`cross-platform-setup` lives entirely in **claude-config**, the Claude Code configuration
harness — NOT an application. There is no Tauri app (`src-tauri/` absent), no frontend /
`package.json`, and no MCP HTTP server to connect to. The feature is a repo-root CLI:

- `setup.py` — minimal tolerant psd1 parser over the EXISTING `manifest.psd1` (single source
  of truth, SPEC D1), `expand_mappings` (scopes, alias repos, RootFiles/DotClaudeFiles/
  DotClaudeDirs, `--repos-root`, skip-absent), per-platform link primitives (POSIX symlinks;
  Windows symlink-first with junction fallback, SPEC D3), and the `bootstrap`/`check`/`repair`
  verbs mirroring `setup.ps1`'s parity table.
- `setup.ps1` / `manifest.psd1` — byte-untouched (SPEC D4; `git diff` empty).

None of this reaches an MCP tool surface — there is no live runtime to probe. This is the
`standalone — no app integration` untestable class.

## Alternative validation performed (all PASSING)

| Suite | Command | Result |
|-------|---------|--------|
| Feature suite (parser incl. real-manifest pin, expansion, link primitives incl. mocked-Windows selection, verb parity rows, CLI, e2e) | `python3 -m pytest user/scripts/test_setup_py.py -q` | **66 passed** |
| Full pytest gates (10 existing suites + the new one) | `python3 -m pytest test_lazy_core.py … test_setup_py.py -q` | **1268 passed, 2 sanctioned skips** (Windows cold-boot spawn; WSL pipe) |
| Toolify miner | `python3 test_toolify_miner.py` | All tests passed |
| Smoke baselines | `lazy-state.py --test` / `bug-state.py --test` / `lazy_coord.py --test` | green (no baseline change) |
| State-script parity | `lazy_parity_audit.py --repo-root .` | exit 0 |
| Skill projection lint | `lint-skills.py --skills-dir user/skills --repos-dir repos` | clean (exit 0) |

Every SPEC Validation-Criteria row names `test_setup_py.py` (or `git`) as its "Where to
Check"; **zero** rows name an MCP surface (every phase's MCP Integration Test Assertions block
is `N/A — no MCP-reachable surface`).

## Live container validation (recorded)

This lane runs in the exact environment the feature targets (a Linux cloud container on a bare
clone). At `validated_commit`, with a fresh temp `HOME`:

- `python3 setup.py bootstrap --target User` → `Bootstrap: 0 moved, 11 linked, 0 skipped,
  0 warnings` (all 11 User-scope links materialized into the clone — skills, hooks, scripts,
  templates, both plugins, CLAUDE.md, CLAUDE.local.md, settings.json, settings.local.json,
  keybindings.json).
- `python3 setup.py check --target User` → `Check: 11 OK, 0 broken, 0 absent`, exit 0.
- Full-manifest `python3 setup.py check` → absent Windows repos rendered as
  `SKIP … (repo absent: C:/Users/…)` — counted absent, never broken (SPEC D5) — while the
  unlinked Personal/Workspace rows reported MISSING honestly.

i.e. a cloud session can now self-host the harness layout — the exact capability this feature
adds, demonstrated in the target environment rather than a fixture.
