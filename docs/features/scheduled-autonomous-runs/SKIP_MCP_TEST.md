---
kind: skip-mcp-test
feature_id: scheduled-autonomous-runs
reason: claude-config is pure harness mechanics — no Tauri app, no src-tauri, no package.json, no MCP-reachable surface. This feature is furthermore docs/configuration glue ONLY (trigger prompt template, platform-trigger recipes, failure/recovery playbook, workspace/CLAUDE.md pointer) with ZERO state-script or skill code changes; there is no runtime surface of its own to drive.
alternative_validation: doc-completeness cross-checks against the real contracts — every flag/behavior/terminal the docs cite verified at file+line in RESEARCH_SUMMARY.md (--run-start --unattended at lazy-state.py:9159-9177; write_run_marker(attended=...) at lazy_core.py:9289/9297; refuse_run_start_clobber at lazy_core.py:10694 with exit-3 refusals at 10808/10819; _MARKER_STALE_SECONDS=24h at lazy_core.py:6459; park flags + queue-exhausted-all-parked at lazy-batch-cloud SKILL.md:337/360 + lazy-state.py:2532; mandatory --run-end at SKILL.md:389; LAZY_QUEUE.md regen at lazy-batch SKILL.md:489-497; platform trigger op schemas verbatim) — PLUS the full harness gate suite green confirming no accidental breakage — pytest 1202 passed / 2 sanctioned skips (test_lazy_core + test_hooks + test_pipeline_visualizer + test_lazy_parity + test_lazy_queue_doc + test_lint_skills + test_surface_resolver + test_stale_binary + test_retro_ro9 + test_project_skills), test_toolify_miner.py all passed, lazy-state.py --test / bug-state.py --test / lazy_coord.py --test all smoke-green, lazy_parity_audit.py exit 0, lint-skills.py exit 0.
date: 2026-07-04
skipped_by: pipeline
granted_by: mcp-test
spec_class: standalone — no app integration (docs-only scheduling glue over already-validated harness contracts; validated by contract cross-checks + the full harness gate suite)
validated_commit: 54d909cb1c1a48be347d551eba01e6f2fca9ee43
---

# MCP Test Skip — Scheduled Autonomous Runs (Overnight Builder)

## Why this feature has no MCP-reachable surface

`scheduled-autonomous-runs` lives entirely in **claude-config** (no Tauri app, no MCP HTTP
server) and — per its own locked scope — ships **documentation only**:

- `TRIGGER_TEMPLATE.md` — the canonical fresh-session trigger prompt + per-repo parameterization.
- `RECIPES.md` — copy-paste platform trigger ops (create/pilot/fire-now/list/update/delete).
- `PLAYBOOK.md` — failure/recovery playbook + morning triage flow.
- One additive pointer paragraph in `workspace/CLAUDE.md`.

Zero code changes: no `lazy_core.py`/`lazy-state.py`/`bug-state.py` edits, no SKILL.md edits, no
hooks, no new scripts. Every behavior the docs describe is an ALREADY-implemented contract
(`--run-start --unattended`, `refuse_run_start_clobber` arbitration, `--park`/flush, mandatory
`--run-end`, per-cycle `LAZY_QUEUE.md` commits, the platform trigger ops). This is the
`standalone — no app integration` untestable class.

## Alternative validation performed (all PASSING)

| Suite | Command | Result |
|-------|---------|--------|
| Contract cross-checks | every doc citation traced to file+line (ledger: `RESEARCH_SUMMARY.md` anchor table) | all anchors resolved; 2 honest caveats documented (repo-scoped `/lazy-batch-cloud`; cloud-skill `LAZY_QUEUE.md` wiring) |
| Harness unit/integration tests | `python3 -m pytest test_lazy_core.py test_hooks.py test_pipeline_visualizer.py test_lazy_parity.py test_lazy_queue_doc.py test_lint_skills.py test_surface_resolver.py test_stale_binary.py test_retro_ro9.py test_project_skills.py -q` | **1202 passed, 2 skipped** (the two sanctioned skips: Windows cold-boot spawn; WSL pipe) |
| Toolify miner | `python3 test_toolify_miner.py` | All tests passed |
| Smoke baselines | `lazy-state.py --test` / `bug-state.py --test` / `lazy_coord.py --test` | All smoke tests passed (×3; no baseline change) |
| State-script parity | `lazy_parity_audit.py --repo-root <worktree>` | exit 0 |
| Skill lint | `lint-skills.py --skills-dir user/skills --repos-dir repos` | OK (exit 0) |

Note: pytest fixture commits were run with `GIT_CONFIG_*` env overriding `commit.gpgsign=false`
for the test subprocesses only — the cloud sandbox's injected commit-signing helper
(`/tmp/code-sign`) was intermittently failing environment-wide ("too many open files" /
signing-server dial errors), which is sandbox infrastructure, not repo behavior; fixture commits
in hermetic temp repos carry no signing requirement. Lane commits themselves remain signed.

## Live validation intentionally deferred to the operator

The SPEC's own Phases 1–3 (one-shot pilot fire, collision & recovery drills, weeklong nightly
cron rollout) are the feature's live validation and REQUIRE live platform triggers, the
operator's phone, and real overnight wall-clock — recorded as PHASES.md Phase 5 deferred rows
(with `RECIPES.md` as the copy-paste input and `PLAYBOOK.md` defining each drill's expected
evidence). No live trigger was created by this lane (operator action per D9 and lane constraint).
