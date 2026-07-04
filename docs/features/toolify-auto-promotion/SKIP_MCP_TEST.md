---
kind: skip-mcp-test
feature_id: toolify-auto-promotion
reason: claude-config is pure harness mechanics — no Tauri app, no src-tauri, no package.json, no MCP-reachable surface exists to drive any MCP HTTP tool against. The feature is a stdlib Python materializer (toolify-promote.py) + an additive miner field + two additive enqueue flags on lazy-state.py + a git-tracked JSON ledger + one report-only skill-prose step; none of it reaches an MCP tool surface.
alternative_validation: pytest (test_lazy_core + test_hooks + test_pipeline_visualizer + test_lazy_parity + test_lazy_queue_doc + test_lint_skills + test_surface_resolver + test_stale_binary + test_retro_ro9 + test_project_skills + test_toolify_promote = 1220 passed, 2 sanctioned skips) + test_toolify_miner.py 22/22 + test_toolify_promote.py 18/18 (self-contained runners) + lazy-state.py --test / bug-state.py --test / lazy_coord.py --test smoke baselines green (lazy-state baseline regenerated via _normalize_smoke_output for the new [enqueue-flags] fixture) + lazy_parity_audit.py --repo-root . exit 0 + lint-skills.py clean + lane-local project-skills.py projection clean. PLUS a scratch-repo integration probe — a real promote materializes queue entry + stub SPEC, and lazy-state.py dispatches /spec at "Step 4.5: stub-spec detected" (the interactive baseline-lock), pinned by test_materialized_stub_routes_step_4_5_probe.
date: 2026-07-04
skipped_by: pipeline
granted_by: mcp-test
spec_class: standalone — no app integration (no Tauri/MCP surface; harness mechanics validated by pytest + self-contained script runners + smoke baselines + parity audit + skill lint/projection)
validated_commit: 89cd14a96108bd8fa5d45564a47a3e3533d88295
---

# MCP Test Skip — Auto-Promotion Pipeline for Toolify Candidates

## Why this feature has no MCP-reachable surface

`toolify-auto-promotion` lives entirely in **claude-config**, the Claude Code configuration
harness — NOT an application. There is no Tauri app (`src-tauri/` absent), no frontend /
`package.json`, and no MCP HTTP server to connect to. The feature is pure harness mechanics:

- `toolify-miner.py` — the additive `candidate_id` field (`sha256(signature)[:12]`) on the
  candidate schema and both renderers (READ-ONLY invariant untouched, dir-hash tests green).
- `lazy-state.py` — the additive default-off `--stub` / `--at {head,tail}` flags on
  `--enqueue-adhoc` (byte-identical defaults, pinned by the regenerated `--test` baseline).
- `toolify-promote.py` (new) — the materializer + ledger (promote / decline / status /
  acceptance-report), shelling the state script for every queue write.
- `docs/features/unified-pipeline-orchestrator/toolify-ledger.json` (new) — the central
  git-tracked promotion ledger.
- `user/skills/lazy-batch-retro/SKILL.md` — the report-only Step 6d resurface (prose only).

None of this reaches an MCP tool surface — there is no live runtime to probe. This is the
`standalone — no app integration` untestable class.

## Alternative validation performed (all PASSING)

| Suite | Command | Result |
|-------|---------|--------|
| Core + harness pytest suites (incl. the new `test_toolify_promote.py`) | `python3 -m pytest test_lazy_core.py test_hooks.py test_pipeline_visualizer.py test_lazy_parity.py test_lazy_queue_doc.py test_lint_skills.py test_surface_resolver.py test_stale_binary.py test_retro_ro9.py test_project_skills.py test_toolify_promote.py -q` | **1220 passed, 2 sanctioned skips** |
| Miner (candidate_id stability/uniqueness/renders + READ-ONLY dir-hash) | `python3 test_toolify_miner.py` | **22/22 passed** |
| Materializer (D5 marker round-trip vs the REAL detector, refusal chain, failure ordering, Step-4.5 probe, status join, acceptance report) | `python3 test_toolify_promote.py` | **18/18 passed** |
| Smoke baselines (incl. the new `[enqueue-flags]` fixture; baseline regenerated ONLY via `_normalize_smoke_output`) | `lazy-state.py --test` / `bug-state.py --test` / `lazy_coord.py --test` | green |
| State-script parity (feature-only enqueue flags confirmed un-audited — justified divergence) | `lazy_parity_audit.py --repo-root .` | exit 0 |
| Skill projection + lint (retro Step 6d edit) | `project-skills.py --output-dir /tmp/proj-toolify-auto-promotion` + `lint-skills.py` | clean |

Every SPEC Validation-Criteria row names a pytest/self-contained-runner/smoke surface as its
"Where to Check"; **zero** rows name an MCP surface (every phase's MCP Integration Test
Assertions block is `N/A — no MCP-reachable surface`).

## Deferred (workstation-only, recorded in PHASES.md Phase 1)

Running the miner over the operator's REAL session-log corpus (`~/.claude/projects`) to confirm
the top above-bar candidates still map to nameable dances at current log volume is not possible in
this cloud container (no corpus exists). This is the bar doc's pre-existing manual runtime
verification, unchanged by this feature; it re-opens on any workstation session.
