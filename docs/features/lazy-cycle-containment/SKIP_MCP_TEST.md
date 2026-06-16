---
kind: skip-mcp-test
feature_id: lazy-cycle-containment
reason: claude-config is pure harness mechanics — no Tauri app, no src-tauri, no package.json, no MCP-reachable surface exists to drive any MCP HTTP tool against.
alternative_validation: pytest (476 passed — test_lazy_core/test_lazy_parity/test_project_skills/test_retro_ro9) + bash hook-test harness (48 passed — test_hooks.py containment cases) + project-skills.py projection (clean) + lint-skills.py --check-projected (clean), all with LAZY_STATE_DIR isolated.
date: 2026-06-15
skipped_by: pipeline
granted_by: mcp-test
spec_class: standalone — no app integration (no Tauri/MCP surface; harness mechanics validated by pytest + bash hook harness + projection/skill lint)
validated_commit: 05fa606c2f35bf69b10f6e3d824ac50914600758
---

# MCP Test Skip — Lazy Cycle Containment

## Why this feature has no MCP-reachable surface

`lazy-cycle-containment` lives entirely in **claude-config**, which is the Claude Code
configuration harness, NOT an application. There is:

- **No Tauri app** (`src-tauri/` absent, no `tauri.conf.json`),
- **No frontend / `package.json`** (no `npm run dev`, no dev server),
- **No MCP HTTP server** to connect to.

The feature is pure harness mechanics: a Python state-script predicate + helpers
(`lazy_core.py` self-edit predicate, cycle-marker read/write/clear, C3 refusal
guards), a bash `PreToolUse` containment hook (`lazy-cycle-containment.sh`),
orchestrator skill prose (the `--cycle-begin`/`--cycle-end` dispatch bracket across
the coupled trio), a cycle-prompt `@section`, a recovery-prompt grep-and-cite gate,
a retro rule (R-O-9) + helper, and secondary voice/ledger prose. **None of this
reaches an MCP tool surface** — there is no live runtime to probe.

This is the `standalone — no app integration` untestable class. (The
`docs/features/mcp-testing/SPEC.md` cited by the `/mcp-test` override is an
AlgoBooth-repo document about that app's audio/Tauri runtime; it does not exist in
claude-config because claude-config has no such runtime. The untestable-class
*concept* it formalizes — a target with no MCP-reachable surface — applies directly:
there is nothing to boot and nothing to call.)

## Alternative validation performed (this cycle, all PASSING)

Run with `LAZY_STATE_DIR` pointed at an isolated empty temp dir (so the live
orchestrator cycle marker for this very dispatch does not perturb the suite):

| Suite | Command | Result |
|-------|---------|--------|
| Core unit tests (predicate, marker, C3 refusals, retro helper, projection) | `pytest user/scripts/test_lazy_core.py user/scripts/test_lazy_parity.py user/scripts/test_project_skills.py user/scripts/test_retro_ro9.py` | **476 passed** |
| Hook-test harness (C2 containment: deny next-route probe / lifecycle / 2nd-feature commit; allow same-feature + allow-listed ops; fast-path allow w/o marker; fail-OPEN on malformed) | `pytest user/scripts/test_hooks.py` | **48 passed** |
| Skill-component projection | `python3 user/scripts/project-skills.py` | clean (90 components, no errors) |
| Skill lint | `python3 user/scripts/lint-skills.py --check-projected` | clean (no broken/unexpanded `!cat`) |

These suites cover every Validation-Criteria row that does not require a live MCP
runtime (all of them — the SPEC's "Where to Check" column names pytest /
hook-test-harness / projection-lint / docs-consistency for all 14 rows; **zero**
rows name an MCP surface — the MCP Integration Test Assertions block of every phase
is explicitly `N/A — no MCP surface`).

## Observation worth recording (NOT a defect)

In a full pytest run WITHOUT `LAZY_STATE_DIR` isolation,
`test_lazy_state_test_output_matches_baseline` fails because the orchestrator's
live cycle marker (`~/.claude/state/lazy-cycle-active.json`, set for THIS dispatch,
`feature_id: lazy-cycle-containment`) leaks into the smoke fixture's
`bug-state.py --enqueue-adhoc` subprocess, which the new **C3 refusal correctly
refuses (exit 3)** — i.e. the feature-under-validation's own guard fired exactly as
designed. With the marker absent (isolated state dir) the smoke baseline passes.
This is a **test-hermeticity gap in the smoke-baseline fixture** (it does not pin
`LAZY_STATE_DIR`), not a production-code defect — the C3 behavior is correct. No
production code was touched this cycle. (Follow-up: pin `LAZY_STATE_DIR` to an empty
temp dir inside the smoke-baseline test so a live marker cannot perturb it.)
