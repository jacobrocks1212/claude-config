---
kind: fixed
feature_id: runtime-ensure-unbounded-session-log-accumulation
date: 2026-07-20
provenance: backfilled-unverified
validated_via: pytest (user/scripts/tests/test_lazy_core/ — 1347 passed, incl. 6 new prune_session_dirs tests) + test_hooks.py (288) + lazy-state.py/bug-state.py --test + lint-skills.py; NOT pipeline-gated
auto_ticked_rows: 0
---

# Completion Receipt

runtime-ensure-unbounded-session-log-accumulation marked Fixed on 2026-07-20 during a
`/harden-harness` observed-friction round (Round 134, item in flight `inspector-track-dashboard`).
This receipt was written by the harden agent OUT-OF-PIPELINE (a `harden(script):` commit, not the
bug pipeline's `__mark_fixed__` gate) — provenance is `backfilled-unverified`.

## Notes

Fix commit: **4ffee124** — `harden(script): cap dev-runtime session-log accumulation in
ensure_runtime`. Spec commit: 573071fa.

Implemented the SPEC's primary (claude-config, self-contained) fix scope:
- Two parameterized keys added to `_ENSURE_RUNTIME_DEFAULT_CONFIG` in
  `user/scripts/lazy_core/runtimeplane.py` — `session_logs_glob` (default `logs/session-*`) and
  `session_logs_keep` (default `10`) — NOT hard-coded into the control flow.
- New best-effort, never-raises `prune_session_dirs(repo_root, *, glob_pattern, keep, lister,
  remover)` helper (exported from `lazy_core`): lists matching dirs, sorts newest-first by mtime,
  keeps the newest `keep`, removes the rest via `shutil.rmtree`. Disabled by a falsy glob or a
  `None`/`<=0` keep (fail-safe — never wipes all logs). Injected `lister`/`remover` keep `--test`
  hermetic.
- Wired into the default `restart()` closure at the `/health` 200 success point, so every
  pipeline-driven restart prunes as it mints — covering the M4, legacy, and bounded-recovery
  callers uniformly (they share the one `restart` closure).

Six regression tests added + registered in `test_runtimeplane.py::_TESTS`: keep-newest-prune-rest,
disabled-when-glob-falsy-or-keep-none, non-positive-keep-never-wipes-all,
never-raises-on-remover-error, default-config-carries-keys, and a wiring test asserting the
production `restart()` closure calls `prune_session_dirs` with the config glob+keep on a successful
boot (guards against a false-green where the helper exists but is never called).

**Additional home (NOT fixed here — cross-referenced recommendation):** an app-level rotation in
AlgoBooth (`scripts/kill-dev.js` or the dev logger) is a better/additional home (covers failed
boots where `/health` never reaches 200, and manual `npm run dev` outside the pipeline). The harden
agent may not edit target-repo source, and filing into AlgoBooth's live feature-run pipeline from a
background harden risks corrupting the active run's git/commit-bracket accounting — so it is
surfaced to the operator (SPEC "Additional home" + hardening-log Round 134 + PushNotification)
rather than enqueued mid-run. The claude-config cap caps the bloat regardless.

## Verification

- `python -m pytest user/scripts/tests/test_lazy_core/` → 1347 passed (0 failed).
- `python user/scripts/test_hooks.py` → 288/288 passed.
- `python user/scripts/lazy-state.py --test` / `bug-state.py --test` → all smoke tests passed.
- `python user/scripts/lint-skills.py --check-projected --check-capabilities` → OK.
- `python user/scripts/bug-state.py --repo-root . --fsck` → ok, no violations.
- `harness-gate.py` → `gate_weakening: pass`; `overfit: flag` is a mechanical false-positive (it
  read the new parameterized config-dict keys as "literals appended to a membership construct" — a
  tunable config surface, not a matcher/regex/allow-list), so no genuine over-fit spin-off.
