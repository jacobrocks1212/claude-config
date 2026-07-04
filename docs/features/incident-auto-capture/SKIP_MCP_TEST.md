---
kind: skip-mcp-test
feature_id: incident-auto-capture
reason: claude-config is pure harness mechanics — no Tauri app, no src-tauri, no package.json, no MCP-reachable surface exists to drive any MCP HTTP tool against. The feature is a stdlib read-only collector (incident-scan.py), additive fail-open hook-event appender lines in five bash hooks + lazy_guard.py, and orchestrator/skill prose; none of it reaches an MCP tool surface.
alternative_validation: pytest full gate suite (test_lazy_core 851 + test_hooks 130 incl. 10 new test_events_* + test_incident_scan 15 new + test_pipeline_visualizer/test_lazy_parity/test_lazy_queue_doc/test_lint_skills/test_surface_resolver/test_stale_binary/test_retro_ro9/test_project_skills = 1228 passed, 2 sanctioned skips) + test_hooks.py self-runner (all passed, WSL skip only) + test_toolify_miner.py + lazy-state.py/bug-state.py/lazy_coord.py --test smoke (baselines green, byte-unchanged) + lazy_parity_audit.py --repo-root . (exit 0, coupled-pair prose mirrored) + lint-skills.py + project-skills.py (lane-local projection, no errors) + a live read-only smoke on this repo (incident-scan.py --repo-root . --dry-run → "0 clusters observed", exit 0).
date: 2026-07-04
skipped_by: pipeline
granted_by: mcp-test
spec_class: standalone — no app integration (no Tauri/MCP surface; harness mechanics validated by pytest + the bash hook pipe-test harness + smoke baselines + parity/lint gates)
validated_commit: 3f62464a87c543b9710862e31c80d9246bdababc
---

# MCP Test Skip — Incident Auto-Capture → Bug Stubs

## Why this feature has no MCP-reachable surface

`incident-auto-capture` lives entirely in **claude-config**, the Claude Code configuration
harness — NOT an application. There is no Tauri app, no frontend, and no MCP HTTP server to
connect to. The feature is pure harness mechanics:

- `user/scripts/incident-scan.py` — the deterministic read-only collector (clusters deny-ledger /
  hook-event recurrence, dedups against `incident_key`s, enqueues bug stubs via the sanctioned
  `--enqueue-adhoc --type bug` subprocess + `INCIDENT.md` capsules).
- `lazy_core.append_hook_event` + additive deny/error-site appender lines in
  `lazy-cycle-containment.sh`, `block-noncanonical-blocker-write.sh`,
  `block-sentinel-write-on-stray-branch.sh`, `long-build-ownership-guard.sh`,
  `build-queue-enforce.sh`, `lazy_guard.py` (fail-open `hook-events.jsonl`).
- `/incident-scan` skill + the `/lazy-batch` / `/lazy-batch-cloud` §1c.6 end-of-run step (prose).

None of this reaches an MCP tool surface — there is no live runtime to probe. This is the
`standalone — no app integration` untestable class.

## Alternative validation performed (all PASSING at `validated_commit`)

| Suite | Command | Result |
|-------|---------|--------|
| Full pytest gate suite (incl. 10 new `test_events_*` hook pipe-tests + 15 new `test_incident_scan.py` fixtures: bars, dedup open/archived, recurrence_of, cap, dry-run inertness, read-only hash guards) | `python3 -m pytest test_lazy_core.py test_hooks.py test_pipeline_visualizer.py test_lazy_parity.py test_lazy_queue_doc.py test_lint_skills.py test_surface_resolver.py test_stale_binary.py test_retro_ro9.py test_project_skills.py test_incident_scan.py -q` | **1228 passed, 2 skipped** (the two sanctioned skips: Windows cold-boot spawn; WSL pipe test) |
| Hook harness self-runner | `python3 user/scripts/test_hooks.py` | all passed (WSL skip only) |
| Toolify-miner suite | `python3 user/scripts/test_toolify_miner.py` | all passed |
| Smoke baselines (byte-unchanged) | `lazy-state.py --test` / `bug-state.py --test` / `lazy_coord.py --test` | green |
| Coupled-pair parity after the §1c.6 mirror | `python3 user/scripts/lazy_parity_audit.py --repo-root .` | exit 0 |
| Skill projection + lint (new `/incident-scan` skill) | `project-skills.py --output-dir /tmp/proj-incident-auto-capture` + `lint-skills.py` | clean |
| Live read-only smoke on this repo | `python3 user/scripts/incident-scan.py --repo-root . --dry-run` | `incident-scan: 0 clusters observed, 0 cleared the bar, 0 would-enqueue, 0 deduped`, exit 0 |

Every SPEC Validation-Criteria row names `test_hooks.py` / pytest fixtures as its "Where to
Check" except the two manual rows (`/spec-bug` pickup; live end-of-run flush review), which
require a live batch run and are recorded as the PHASES Phase-4 deferred verification row.
