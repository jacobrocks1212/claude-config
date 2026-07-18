# test_lazy_core apply_pseudo tests read the live cycle marker (no `LAZY_STATE_DIR` isolation)

**Status:** Fixed
**Severity:** P2
**Discovered:** 2026-07-18
**Related:** `docs/specs/turn-routing-enforcement/hardening-log/2026-07.md` (this round);
`user/scripts/CLAUDE.md` → "Hermetic subprocess tests MUST … isolate `LAZY_STATE_DIR`" (the
contributor convention this defect violates at the pytest-package scope);
`docs/bugs/_archive/clear-state-dir-teardown-strips-lazy-state-dir-override/` (the sibling
`_clear_state_dir` restore fix — same isolation surface).

## Trigger

Observed-friction, surfaced by the `merged-head-actionability-oracle` `/execute-plan` cycle: a
cycle subagent runs the invariant gate battery (`pytest user/scripts/tests/test_lazy_core/`)
DURING a live `/lazy-batch` run — which cycle subagents do by design — and gets ~80 spurious
`SystemExit(3)` failures in the `test_pseudo` / `test_misc` `apply_pseudo`/`mark_complete`
family. The identical battery passes clean (1257 passing) when `LAZY_STATE_DIR` is pointed at an
isolated temp dir.

## Reproduction Steps

1. Start (or be inside) a live `/lazy-batch` run so a `lazy-cycle-active.json` marker exists in
   the repo's keyed state dir (`~/.claude/state/<repo_key>/`).
2. Run `python -m pytest user/scripts/tests/test_lazy_core/test_pseudo.py user/scripts/tests/test_lazy_core/test_misc.py -q`.
3. Observe ~80 failures, each a `SystemExit: 3` raised from `lazy_core.apply_pseudo` →
   `refuse_if_cycle_active("apply_pseudo")`.
4. Re-run with `LAZY_STATE_DIR=<fresh temp> python -m pytest …` → all pass.

Confirmed live this round: `80 failed, 194 passed` for the two suites under a live marker.

## Root cause (Concluded)

Root-cause class: **script-defect (test-harness isolation gap)** — not a production-logic defect.

`lazy_core.apply_pseudo` guards its entry with `refuse_if_cycle_active("apply_pseudo")`
(`user/scripts/lazy_core/pseudo.py:482`) — the sole author of every scripted completion write,
guarded so a subagent DIRECT library call is refused (priority 3: a cycle marker present → exit
3, zero side effects). The in-line comment states the assumption: *"In-process test callers run
with no marker and no subagent env → the guard is a silent no-op."*

That assumption holds only when the test's state-dir resolution is isolated. The ~80 failing
tests call `apply_pseudo(Path(td), "__mark_complete__"/…)` with a `tempfile` **repo root** but do
NOT isolate `LAZY_STATE_DIR`. With `LAZY_STATE_DIR` unset, `claude_state_dir()` resolves to the
REAL per-repo keyed dir `~/.claude/state/<repo_key>/`, which during a live run carries the cycle
marker → `refuse_if_cycle_active` fires → `SystemExit(3)`. The tests isolate the repo root but
not the state dir, exactly the gap the `user/scripts/CLAUDE.md` convention warns about
("Isolating `LAZY_STATE_DIR` alone is not enough" — here the inverse: repo-root alone is not
enough either).

The isolation helpers (`_ORIGINAL_LAZY_STATE_DIR`, `_set_state_dir`, `_clear_state_dir`) live in
the shared `tests/test_lazy_core/_util.py`, imported by every shard in BOTH pytest and the
standalone per-shard `__main__` runners — but nothing sets an isolated default for tests that
never call `_set_state_dir` (the whole `apply_pseudo` family).

## Fix scope

Isolate `LAZY_STATE_DIR` at the ONE shared import chokepoint — `tests/test_lazy_core/_util.py`,
immediately before `_ORIGINAL_LAZY_STATE_DIR` is captured — via
`os.environ.setdefault("LAZY_STATE_DIR", <per-process temp dir>)`:

- **`setdefault`, not overwrite** — an operator's documented `LAZY_STATE_DIR=<temp> python3 …`
  override still wins; only the unset (real-keyed-dir) case is redirected to a throwaway temp.
- **Structural, single-chokepoint** — fixes the whole class (any in-process
  `refuse_if_cycle_active`-guarded call), not 80 per-test edits, and covers BOTH pytest and the
  standalone runners (both import `_util`).
- `_ORIGINAL_LAZY_STATE_DIR` is captured AFTER the setdefault, so `_clear_state_dir`'s restore
  path stays isolated too; `test_clear_state_dir_restores_process_launch_override` monkeypatches
  `_util._ORIGINAL_LAZY_STATE_DIR` directly and is unaffected.

No production code changes; no `--test` smoke baseline impact (the byte-pinned baselines are for
`lazy-state.py --test` / `bug-state.py --test`, which do not import `_util`).

## Verification

`pytest user/scripts/tests/test_lazy_core/` green under a LIVE cycle marker (the exact condition
that produced the 80 failures) — the serving-path regression: the battery is runnable mid-run,
which is what cycle subagents require.
