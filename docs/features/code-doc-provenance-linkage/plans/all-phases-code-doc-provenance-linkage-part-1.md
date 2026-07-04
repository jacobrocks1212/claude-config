---
kind: implementation-plan
feature_id: code-doc-provenance-linkage
status: In Progress
created: 2026-07-04
complexity: complex
phases: [1, 2, 3, 4, 5]
---

> **Plan** — generated inline (lane implementation session) on 2026-07-04.
> To execute: inline in this lane (no `/lazy*` invocation — lane protocol).
> Single self-contained part covering all 5 phases.

# Implementation Plan — code-doc-provenance-linkage (Phases 1–5)

**PHASES.md:** `docs/features/code-doc-provenance-linkage/PHASES.md` (5 phases)
**SPEC.md:** `docs/features/code-doc-provenance-linkage/SPEC.md`

## EXECUTION MODEL

> **INLINE-EXECUTION:** This plan is executed INLINE with `Read`/`Edit`/`Write` (no `Agent`
> delegation), **test-first** for every TDD work unit — write the failing test before the
> implementation. Never invoke `/lazy` or `/lazy-batch` recursively.

**Gate suite (run after each phase; ALL green before marking a phase's WUs done):**
```
python3 -m pytest test_lazy_core.py test_hooks.py test_pipeline_visualizer.py \
  test_lazy_parity.py test_lazy_queue_doc.py test_lint_skills.py \
  test_surface_resolver.py test_stale_binary.py test_retro_ro9.py \
  test_project_skills.py -q
python3 test_toolify_miner.py
python3 lazy-state.py --test && python3 bug-state.py --test && python3 lazy_coord.py --test
python3 lazy_parity_audit.py --repo-root <worktree-root>
python3 lint-skills.py --skills-dir <worktree-root>/user/skills --repos-dir <worktree-root>/repos
```

## Key design contract (read before WU-1.1) — ONE WRITER, TWO TRIGGERS

- **`lazy_core.write_provenance(...)`** is the SOLE author of `IMPLEMENTED.md` and
  `docs/provenance-index.json`. The `__mark_complete__`/`__mark_fixed__` branch and the
  `--link-provenance` / `--backfill-provenance` handlers all call it — never a second writer.
- **Every file write via `lazy_core._atomic_write`**; diagnostics via `_diag`; stdlib-only.
- **Gate containment:** a provenance failure inside `apply_pseudo` degrades to `warnings[]`
  (malformed-queue-trim policy) — completion is never blocked by its own bookkeeping.
- **Derivation honesty (D4):** `derivation: commit-brackets` (pipeline primary) |
  `commit-range` (manual) | `message-grep` (fallback/backfill) — always recorded, never silent.
- **Provenance enum (D9):** `pipeline-gated` | `manual` (+ `linked_by:`) | `backfilled`.
- **Index determinism:** repo-relative POSIX keys, keys sorted, entry lists sorted — re-runs are
  byte-stable; an item's rows are REPLACED on re-link (no duplicates).
- **Coupled pair:** `--cycle-end` bracket append + all four CLI subcommands mirrored on
  `bug-state.py`; `lazy_parity_audit.py --repo-root .` must stay exit 0.
- **HARD:** all new pytest functions appended to `_TESTS` in `test_lazy_core.py`; in-file `--test`
  fixtures registered in each script's test list; baselines re-pinned ONLY via
  `_normalize_smoke_output`.

---

## Phase 1 — Commit-bracket ledger + receipt anchor

- [x] WU-1.1 — Failing tests first: `test_append_commit_bracket_roundtrip`,
  `test_append_commit_bracket_fail_open`, `test_record_cycle_commit_bracket_skips_empty`,
  `test_cycle_end_records_bracket_cli` (registered in `_TESTS`).
- [x] WU-1.2 — `lazy_core.append_commit_bracket` / `read_commit_brackets` /
  `record_cycle_commit_bracket` (fail-open, `claude_state_dir()`-resident JSONL).
- [x] WU-1.3 — Wire `record_cycle_commit_bracket` into BOTH `--cycle-end` handlers (mirrored).
- [x] WU-1.4 — Failing test: `test_mark_complete_receipt_carries_completed_commit` (+ non-git
  absent case); then thread `completed_commit=_current_head(repo_root)` at the
  `write_completed_receipt` mark-complete call site.
- [x] WU-1.5 — In-file `--test` fixture on both scripts (fail-open cycle-end); re-pin baselines
  via `_normalize_smoke_output`; full gate suite green.

## Phase 2 — Producer + gate wiring

- [x] WU-2.1 — Failing tests first: distillate byte-stability + decision ids + index-key match
  with `git diff` union; refused-gate-writes-nothing; induced-index-failure-degrades-to-warning;
  receipt-noop-writes-nothing; empty-decisions honesty.
- [x] WU-2.2 — `lazy_core.write_provenance` (+ `_provenance_index_path`, index merge/replace,
  distillate assembly from SPEC `>` summary + `_parse_locked_decisions` + receipt facts).
- [x] WU-2.3 — Derivation helpers: `derive_touched_from_brackets` / `derive_touched_from_range` /
  `derive_touched_from_grep`.
- [x] WU-2.4 — `apply_pseudo` mark-complete/mark-fixed wiring (`provenance_written` +
  `warnings[]` degradation).
- [x] WU-2.5 — `sentinel-frontmatter.md` `kind: implemented` registration; gate suite green.

## Phase 3 — Manual path

- [x] WU-3.1 — Failing tests first: manual-link shape parity vs pipeline entries; `--dry-run`
  purity; re-link replace-not-duplicate; unresolvable-range refusal; CLI on both scripts.
- [x] WU-3.2 — `lazy_core.link_provenance` (+ `--pr` → range resolution via `gh`, clean refusal
  when absent; minimal decision-record dir creation per D8).
- [x] WU-3.3 — `--link-provenance --id/--commits/--pr/--body-file/--dry-run` handlers on BOTH
  scripts (mirrored).
- [x] WU-3.4 — `user/skills/link-provenance/SKILL.md` (draft-then-approve, writes through the
  producer); projection + lint clean; gate suite green.

## Phase 4 — Consumption

- [x] WU-4.1 — Failing tests first: seeded-index lookup correctness; purity (bytes + mtime);
  missing-index no-op; CLI on both scripts.
- [x] WU-4.2 — `lazy_core.provenance_lookup` + `--provenance-lookup <path>` handlers (mirrored).
- [x] WU-4.3 — Prompt wiring: `cycle-base-prompt.md` lookup step; `/spec-phases` step; coupled
  `/lazy*` wrapper notes (`lazy`↔`lazy-cloud`, `lazy-batch`↔`lazy-batch-cloud`, mirrors diffed).
- [x] WU-4.4 — `project-skills.py` (lane-local output dir) + `lint-skills.py` clean; parity audit
  exit 0; gate suite green.

## Phase 5 — Backfill + lint

- [x] WU-5.1 — Failing tests first: backfill honesty (`backfilled` + `message-grep`) +
  idempotency; lint catches planted dead row / hot un-provenanced file / cross-orphan; lint
  purity.
- [x] WU-5.2 — `lazy_core.backfill_provenance` + `lazy_core.lint_provenance` (+ churn threshold
  constants).
- [x] WU-5.3 — `--backfill-provenance` / `--lint-provenance` handlers on BOTH scripts (mirrored).
- [x] WU-5.4 — Live claude-config backfill run (commit the generated index + distillates; record
  actual counts); `user/scripts/CLAUDE.md` CLI rows; FULL gate suite green.
