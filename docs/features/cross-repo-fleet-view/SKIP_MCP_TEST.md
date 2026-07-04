---
kind: skip-mcp-test
feature_id: cross-repo-fleet-view
reason: claude-config is pure harness mechanics — no Tauri app, no src-tauri, no package.json, no MCP-reachable surface exists to drive any MCP HTTP tool against. The feature extends the stdlib pipeline_visualizer package (a local read-only ThreadingHTTPServer + static assets) with a cross-repo fleet mode; none of it reaches an MCP tool surface.
alternative_validation: 'pytest gate suite (test_lazy_core + test_hooks + test_pipeline_visualizer 136 (86 pre-existing green unmodified + 50 new fleet tests) + test_lazy_parity + test_lazy_queue_doc + test_lint_skills + test_surface_resolver + test_stale_binary + test_retro_ro9 + test_project_skills = 1288 passed, 2 sanctioned skips) + test_toolify_miner.py (all passed) + lazy-state.py/bug-state.py/lazy_coord.py --test smoke (all green, no baseline change) + lazy_parity_audit.py (exit 0) + lint-skills.py (clean) + doc-drift-lint.py (0 drift findings). PLUS a live end-to-end smoke: a real --fleet server over a two-repo fixture served /api/fleet (correct badges incl. stale-marker, depths, triage halts), the fleet home page, and /repo/<slug>/ drill-in; the ≥24h marker remained on disk after every read and did NOT lock the reorder route.'
date: 2026-07-04
skipped_by: pipeline
granted_by: mcp-test
spec_class: standalone — no app integration
validated_commit: b8e2362b56ea719d3a5797f9d457077a7de958bd
---

# MCP Test Skip — Cross-Repo Fleet Home Page

## Why this feature has no MCP-reachable surface

`cross-repo-fleet-view` lives entirely in **claude-config**, the Claude Code configuration
harness — NOT an application. There is no Tauri app (`src-tauri/` absent), no frontend build /
`package.json`, and no MCP HTTP server to connect to. The feature is pure harness mechanics:

- `pipeline_visualizer/fleet.py` — D1 discovery (registry glob ∪ `lazy-repos.json` pins/excludes
  ∪ live-marker `repo_root` scan), the raw NEVER-DELETING marker read + D3 badge grading, D5
  shallow rows (queue depth + halt-sentinel presence), D7 slugs, the ThreadPoolExecutor fan-out,
  and the `.git`-plain-file `LAZY_QUEUE.md` GitHub-link derivation.
- `pipeline_visualizer/server.py` — the `--fleet` serving mode: `/api/fleet` behind its own
  `TtlCache`, per-repo views nested at `/repo/<slug>/…`, raw-read reorder refusal.
- `pipeline_visualizer/__main__.py` — the `--fleet` flag.
- `static/fleet.html|js|css` + relative-URL per-repo page — render-only frontend, no build step.

None of this reaches an MCP tool surface — there is no live runtime to probe. This is the
`standalone — no app integration` untestable class.

## Alternative validation performed (all PASSING)

| Suite | Command | Result |
|-------|---------|--------|
| Full pytest gate suite (incl. `test_pipeline_visualizer.py`: 86 pre-existing green UNMODIFIED + 50 new fleet tests — discovery union/dedup/excludes, ≥24h marker survival, badge grading, depths, triage, zero `_run_state_script` on fleet polls, drill-in payload parity, POST-to-fleet 404, 12-repo wall-time bound, parallel fan-out, error rows, GitHub-link derivation) | `python3 -m pytest test_lazy_core.py test_hooks.py test_pipeline_visualizer.py test_lazy_parity.py test_lazy_queue_doc.py test_lint_skills.py test_surface_resolver.py test_stale_binary.py test_retro_ro9.py test_project_skills.py -q` | **1288 passed, 2 skipped** (the two sanctioned environment skips) |
| Toolify miner suite | `python3 test_toolify_miner.py` | All tests passed |
| Smoke baselines | `lazy-state.py --test` / `bug-state.py --test` / `lazy_coord.py --test` | green (no baseline change) |
| State-script parity | `lazy_parity_audit.py --repo-root <root>` | exit 0 |
| Skill projection + lint | `lint-skills.py --skills-dir … --repos-dir …` | clean |
| Doc-drift (edited CLAUDE.md tables) | `doc-drift-lint.py --repo-root <root>` | 4 checks, 0 drift findings |

Every SPEC Validation-Criteria row names `test_pipeline_visualizer.py` fixtures / pytest as its
"Where to Check"; **zero** rows name an MCP surface (every phase's MCP Integration Test
Assertions block is `N/A — no MCP-reachable surface`).

## Live smoke (recorded)

A real `make_server(fleet=True)` instance over a two-repo fixture (one repo with a
NEEDS_INPUT.md halt, one with a 30h-old keyed run marker) served: `/api/fleet` (badges
`idle`+`stale-marker`, depths, triage halt), the fleet home page (`fleet-table` + "Needs
attention"), `/repo/<slug>/` drill-in HTML, and `/repo/<slug>/api/state`. After all reads the
≥24h marker was STILL ON DISK (never-delete invariant) and did not lock the reorder route
(stale ≠ fresh).
