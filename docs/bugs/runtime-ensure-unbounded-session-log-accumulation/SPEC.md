# Bug: runtime-ensure mints unbounded dev-runtime session-log dirs (no retention cap)

**Status:** Concluded
**Discovered:** 2026-07-20
**Trigger:** observed-friction (harden-harness dispatch; item in flight `inspector-track-dashboard`, Step 9 mcp-test)
**Related:** `docs/specs/turn-routing-enforcement/hardening-log/2026-07.md` (Round 134);
`user/scripts/lazy_core/runtimeplane.py` (`ensure_runtime`); AlgoBooth adhoc bug
`session-log-dirs-no-app-level-rotation` (cross-referenced — the app-level home)

## Symptom (verified)

Measured on the workstation: **719 `logs/session-<ts>/` dirs = ~15 GB** accumulated in the
AlgoBooth repo's `logs/` over ~6 weeks — a third of free disk on a 90%-full drive, with
individual sessions up to 1.2 GB (fattened by `ALGOBOOTH_AUDIO_TRACE=1` per-frame audio-trace
JSONL).

## Reconstructed route (Step 1 — divergence point)

Not a validate-deny / no-route — an **observed operational friction** surfaced from the
`Step 9: run MCP tests` (`sub_skill=mcp-test`, `feature_id=inspector-track-dashboard`) probe.

The pipeline drives `npm run dev:restart` from two boundaries:
1. `lazy-batch --ensure-runtime` boots (the Step-1d.0 runtime-ensure dance), and
2. **every** `mcp-test` cycle restarts the runtime to get a clean fixture.

Each `dev:restart` mints a fresh `logs/session-<ts>/` dir. Over a multi-week autonomous run
the restart count is large, and **nothing in the runtime-ensure or dev-restart path prunes
old session dirs** — so they accumulate without bound.

## Root cause (Step 2 — classification)

**`missing-contract`.** There is no retention / rotation contract anywhere in the
runtime-ensure path. `ensure_runtime` (and its default `restart()` closure in
`user/scripts/lazy_core/runtimeplane.py`) writes a boot stamp and polls `/health` to 200, but
never caps the on-disk session-log dirs it is responsible for minting. A grep of `user/scripts`
for any session-dir prune / retention / rotate logic returns nothing — the harness was simply
never designed to bound this growth. This is a legitimately novel situation with no current
contract, not a script defect in existing logic.

## Fix scope

**Primary (this repo — claude-config, self-contained):** add a session-dir retention cap at the
pipeline boundary. In `runtimeplane.py`:
- Add two **parameterized** keys to `_ENSURE_RUNTIME_DEFAULT_CONFIG` (NOT hard-coded into the
  control flow, mirroring `restart_command` / `native_globs` / `boot_liveness`):
  `session_logs_glob` (default `logs/session-*`) and `session_logs_keep` (default `10`).
- Add a best-effort, never-raises `prune_session_dirs(repo_root, *, glob_pattern, keep, lister,
  remover)` helper: list matching dirs, sort newest-first by mtime, keep the newest `keep`,
  remove the rest via `shutil.rmtree`. Injected `lister`/`remover` keep `--test` hermetic.
- Call it from the default `restart()` closure **after a successful boot** (the `/health` 200
  point) so every pipeline-driven restart prunes as it mints — covering the M4, legacy, and
  bounded-recovery callers uniformly (they all share this one `restart` closure).

Fail-safe: a falsy glob or `None`/`<=0` keep **disables** the cap (never wipes all logs); any
FS error is swallowed so a prune failure can never abort or fail a boot. Repo-agnostic: a repo
whose config carries no session-log dirs matches nothing (no-op).

**Additional home (target repo — spun off, NOT fixed here):** an app-level rotation in AlgoBooth
(`scripts/kill-dev.js`, which already runs on every restart, or the dev logger) is a **better /
additional** home because it also covers (a) failed boots where `/health` never reaches 200 so
the pipeline-boundary prune never runs, and (b) manual `npm run dev` outside the pipeline. The
harden agent may not edit target-repo source, so this is filed as a cross-referenced AlgoBooth
adhoc bug rather than implemented here. The claude-config cap caps the bloat regardless of
whether the app-side home lands.

## Measurable target signal

Future-run `logs/session-*` dir count stays **bounded** (does not grow unboundedly across runs).
Ledger proxy for the efficacy evaluator: the friction's own recurrence surfaces as `dispatch`
events (an observed-friction harden re-dispatch on this same cause) — expected direction
**decrease** (this cause should not re-dispatch once the cap is in place).
