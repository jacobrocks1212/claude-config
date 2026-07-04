---
kind: implementation-plan
feature_id: scheduled-autonomous-runs
status: In Progress
created: 2026-07-04
complexity: simple
phases: [1, 2, 3, 4, 5]
---

> **Plan** — generated inline (lane batch) on 2026-07-04.
> To execute: `/execute-plan docs/features/scheduled-autonomous-runs/plans/all-phases-scheduled-autonomous-runs-part-1.md`
> Single self-contained part covering all 5 phases (Phase 5 operator-deferred).

# Implementation Plan — scheduled-autonomous-runs (Phases 1–5)

**PHASES.md:** `docs/features/scheduled-autonomous-runs/PHASES.md` (5 phases; Phase 5 deferred)
**SPEC.md:** `docs/features/scheduled-autonomous-runs/SPEC.md`

## EXECUTION MODEL

> **INLINE-EXECUTION:** This plan is executed INLINE with `Read`/`Edit`/`Write` (no `Agent`
> delegation). Never invoke `/lazy` or `/lazy-batch` recursively. **Docs-only feature — the
> TDD test-first pairs are replaced by contract cross-checks:** every flag/behavior a doc cites
> must first be located in the real skill/script (the "failing test" analogue is a grep MISS —
> a cited surface that does not exist halts authoring), recorded file+line in
> `RESEARCH_SUMMARY.md`, and only then written into the doc.

**Gate suite (run once at the end; ALL green before finishing — docs-only, so nothing should
change):**
```
cd user/scripts
python3 -m pytest test_lazy_core.py test_hooks.py test_pipeline_visualizer.py \
  test_lazy_parity.py test_lazy_queue_doc.py test_lint_skills.py \
  test_surface_resolver.py test_stale_binary.py test_retro_ro9.py \
  test_project_skills.py -q
python3 test_toolify_miner.py
python3 lazy-state.py --test
python3 bug-state.py --test
python3 lazy_coord.py --test
python3 lazy_parity_audit.py --repo-root <worktree-root>
python3 lint-skills.py --skills-dir <worktree-root>/user/skills --repos-dir <worktree-root>/repos
```

## Key design contract (read before WU-1.1)

- ZERO code changes: no `lazy_core.py` / `lazy-state.py` / `bug-state.py` / SKILL.md /
  `_components/` edits. All deliverables live in `docs/features/scheduled-autonomous-runs/`
  except one additive paragraph in `workspace/CLAUDE.md`.
- NO live triggers created — recipes are copy-paste ready for the operator (D9 / lane constraint).
- Approved decision set (2026-07-04): D1→A, D2→A, D3→A, D4→A, D5→A; D6–D9 locked as recommended.
- The two honest caveats from RESEARCH_SUMMARY (repo-scoped `/lazy-batch-cloud` availability;
  cloud-skill `LAZY_QUEUE.md` wiring) MUST appear in the docs as preconditions, not be silently
  papered over.

---

## Phase 0 — Decisions + research (lane bookkeeping)

- [x] WU-0.1 — SPEC.md: D1–D9 converted to resolved form (operator-approved 2026-07-04 —
  recommended options), Open Questions collapsed to the deferred empirical checks; Status stays
  Draft (Complete flip is `__mark_complete__`-owned).
- [x] WU-0.2 — RESEARCH_SUMMARY.md: verified-anchor table (file+line for `--run-start
  --unattended`, `write_run_marker(attended=...)`, `refuse_run_start_clobber` + exit 3 +
  `_MARKER_STALE_SECONDS`, park flags + `queue-exhausted-all-parked`, §1c.6 mandatory
  `--run-end`, `LAZY_QUEUE.md` regen block, platform trigger schemas) + the two caveat findings
  + the `--run-end` unacked-debt branch.

## Phase 1 — TRIGGER_TEMPLATE.md

- [x] WU-1.1 — Cross-check (test-first analogue): every surface the template will cite resolved
  to file+line (RESEARCH_SUMMARY table rows: Step 0 command, budget default 10, `--park`,
  terminal set, refusal semantics). A grep miss = halt. DONE via RESEARCH_SUMMARY.
- [x] WU-1.2 — Author `TRIGGER_TEMPLATE.md`: canonical fresh-session prompt (parameterized
  `{repo}` / `{budget}`), conduct rules, per-terminal-class instructions, per-repo
  parameterization table (claude-config / AlgoBooth, staggered slots), preconditions section
  (cloud env, push-to-`main`, skill availability, notify env var when sibling lands).
- [x] WU-1.3 — Tick PHASES.md Phase 1 boxes; commit.

## Phase 2 — RECIPES.md

- [x] WU-2.1 — Cross-check: recipe parameter names against the live platform tool schemas
  (`create_trigger` / `update_trigger` / `delete_trigger` / `fire_trigger` / `list_triggers` /
  `list_environments`). DONE via RESEARCH_SUMMARY platform row.
- [x] WU-2.2 — Author `RECIPES.md`: nightly create (cron + fresh-session + push notifications),
  one-shot pilot (`run_once_at`), fire-now (`fire_trigger` [+ `text`]), registry view
  (`list_triggers`), enable/disable/re-slot (`update_trigger`), teardown (`delete_trigger`),
  constraint notes (hourly min, UTC 5-field cron, notifications fresh-session-only,
  `run_once_fired` self-disable).
- [x] WU-2.3 — Tick PHASES.md Phase 2 boxes; commit.

## Phase 3 — PLAYBOOK.md

- [x] WU-3.1 — Cross-check: recovery-path commands (`--run-end` incl. unacked-debt refusal +
  `--ack-unhardened`, `--marker-present`, exit-3 stderr shape) resolved to file+line. DONE via
  RESEARCH_SUMMARY.
- [ ] WU-3.2 — Author `PLAYBOOK.md`: live-run refusal collision, crashed-marker recovery,
  needs-research halt overnight, nothing-to-do night, morning triage flow (incl. D7 workstation
  flush + the `LAZY_QUEUE.md` cloud-wiring caveat/fallback), expected-evidence sections for the
  operator drills.
- [ ] WU-3.3 — Tick PHASES.md Phase 3 boxes; commit.

## Phase 4 — workspace/CLAUDE.md pointer + validation

- [ ] WU-4.1 — Additive pointer paragraph in `workspace/CLAUDE.md` (no reflow of other text).
- [ ] WU-4.2 — Doc cross-check pass complete (RESEARCH_SUMMARY table is the ledger; every doc
  citation traces to a row).
- [ ] WU-4.3 — Full gate suite green (verbatim tails recorded in SKIP_MCP_TEST.md); tick
  PHASES.md Phase 4 boxes; commit.

## Phase 5 — Live pilot, drills & rollout (OPERATOR-DEFERRED)

- [ ] WU-5.1 — One-shot pilot fire (claude-config). *(deferred — operator: requires live
  platform trigger + phone; see PHASES.md Phase 5)*
- [ ] WU-5.2 — Collision & recovery drills. *(deferred — operator: requires live trigger + a
  live interactive run)*
- [ ] WU-5.3 — Weeklong nightly cron rollout + morning-routine exercise. *(deferred — operator:
  requires a calendar week of live fires)*
