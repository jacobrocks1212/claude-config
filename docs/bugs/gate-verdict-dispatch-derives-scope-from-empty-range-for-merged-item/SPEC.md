# Bug: gate-verdict dispatch derives scope from `origin/main..HEAD`, deadlocking an already-merged item

> The completion-time `gate-verdict` dispatch template derives design-gate scope from
> `origin/main..HEAD`, which is EMPTY for a pipeline item whose fix commits are already merged to
> `origin/main`. The template then reports `in_scope: false` and authors nothing — while the ship
> seam (`lazy_core.gate_verdict_ok`) derives scope from the item's OWN commit set (merge-independent)
> and still refuses `__mark_fixed__`/`__mark_complete__` for a missing `GATE_VERDICT.md`. The two
> seams disagree → permanent completion deadlock for any previously-parked/blocked control-surface
> item driven to completion on a LATER run.

**Status:** Concluded

**Fixed:** 2026-07-19 — implemented out-of-pipeline via `/harden-harness` (see Reconciliation below).

## Scope / classification

- **Root-cause class:** `script-defect` — the mechanical checker step of the `gate-verdict`
  dispatch template selects the wrong commit basis (a git RANGE) versus the ship seam's item-own
  commit-set derivation, so the same "is this change in scope for the design gate?" question is
  answered two different ways.
- **Control surface:** yes — the fix touches `user/scripts/lazy_core/gates.py`,
  `user/scripts/{lazy-state,bug-state}.py`, `user/scripts/lazy_core/dispatch.py`, and the
  `dispatch-gate-verdict.md` template (all on `docs/gate/control-surfaces.json`).

## Verified symptom (empirical, at HEAD `33bf3ed4`)

Repro item: `docs/bugs/adhoc-plan-bug-no-guard-for-fixed-annotated-specs` — its fix is
implemented/tested and its 3 fix commits (`66195d8`, `b70b0dd`, `39b4851`) are ALL ancestors of
`origin/main`. `origin/main..HEAD` = 0 commits.

- `harness-gate.py --repo-root . --range origin/main..HEAD --feature-dir <repro> --json`
  → `in_scope: false`, `scope_hit: []` (empty range → no diff → out of scope).
- `lazy_core.gate_verdict_ok(<repro>, .)` → `{ok: False, in_scope: True, reason: "scoped change
  missing GATE_VERDICT.md"}`.
- `lazy_core.gates._item_commit_touched_files(<repro>, .)` → 12 files incl.
  `user/scripts/bug-state.py`, `user/scripts/lazy_core/{__init__,docmodel,gates}.py`
  (control surfaces).

Per the template's own step 2 ("If `in_scope: false` the completion refusal was spurious — report
that and STOP, author nothing"), the dispatched subagent authors NOTHING and stops → the ship seam
keeps demanding a verdict the authoring seam refuses to produce → permanent deadlock (the repro's
`BLOCKED.md` records this as the 6th occurrence this run).

## Root cause (traced, surface → source)

The two seams derive design-gate scope from DIFFERENT commit bases:

1. **Ship seam (correct, merge-independent).** `lazy_core.gate_verdict_ok`
   (`user/scripts/lazy_core/gates.py:108`) → `_item_commit_touched_files`
   (`gates.py:218`) → `derive_touched_from_brackets` (commit-bracket ledger) primary,
   `derive_touched_from_grep` (git-log message-grep) fallback. Both find an item's own commits
   whether or not they are merged, because the bracket ledger persists and `git log` reachability
   includes merged commits.

2. **Authoring seam (wrong for a merged item).**
   `user/skills/_components/lazy-batch-prompts/dispatch-gate-verdict.md` step 2 runs
   `harness-gate.py --range origin/main..HEAD`. For an already-merged item `origin/main..HEAD` is
   EMPTY, so `harness-gate.py` sees no diff → `in_scope: false` → the subagent stops.

The mechanical checker needs an actual DIFF (to run the overfit/gate_weakening/tautology/complexity
detectors), not just a file list — so the fix must yield a diff over the item's OWN commits.

## Fix (implemented — option (a), share ONE derivation)

Make the authoring seam's scope derivation AGREE with the ship seam by REUSING the same
item-commit derivation, so the two cannot drift:

- **`lazy_core/gates.py`:** extract `_item_commit_derivation(spec_path, repo_root)` (the shared
  commit-selection the ship seam already uses — brackets→grep, foreign-harden-excluded), refactor
  `_item_commit_touched_files` onto it byte-identically, and add `item_scoped_gate_report(spec_path,
  repo_root)` — a PURE-READ that builds a diff over the item's OWN non-foreign commits
  (`_diff_from_commits`, the `git show` analog of `_files_from_commits`) and runs
  `harness_gate.run_checker` in-process. Its `changed` file list is `_item_commit_touched_files`
  (the ship-seam list), so `in_scope`/`scope_hit` AGREE with `gate_verdict_ok` by construction.
- **`lazy-state.py` + `bug-state.py`:** new read-only `--gate-verdict-check <spec_path>` CLI
  (coupled-pair mirror) printing the report JSON — callable by a cycle subagent (like
  `--verify-ledger`).
- **`lazy_core/dispatch.py`:** bind a `{state_script}` token in `emit_dispatch_prompt` so the shared
  feature+bug template names the right script deterministically.
- **`dispatch-gate-verdict.md`:** step 2 now calls `{state_script} --gate-verdict-check {spec_path}`
  instead of `harness-gate.py --range origin/main..HEAD`.

harness-gate.py is left UNTOUCHED (it deliberately does not import `lazy_core`; the item-commit
derivation lives in `lazy_core`, which already imports harness-gate's `run_checker` — the existing
dependency direction). This keeps the checker engine reused with zero duplication.

## Reproduction Steps (regression)

A hermetic git fixture with a merged control-surface item + committed `GATE_VERDICT.md`-less spec:
`item_scoped_gate_report` and `gate_verdict_ok` MUST agree on `in_scope`/`scope_hit` even when
`origin/main..HEAD` is empty — pinned by `test_gates.py`
(`test_item_scoped_gate_report_agrees_with_ship_seam_for_merged_item`).
