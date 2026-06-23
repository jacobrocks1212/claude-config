# Spin-off: `assert_mirror_ready` functional-readiness dimension in `ensure_runtime`

**Status:** Open (spun off 2026-06-23)
**Origin:** AlgoBooth bug `docs/bugs/adhoc-statepush-bridge-boot-init-flaky` (Phase 2 of its PHASES.md / plan `plans/all-phases-statepush-boot-init-flaky.md`, WU-4/WU-5/WU-6)
**Repo:** claude-config (`user/scripts/lazy_core.py`, `user/scripts/lazy-state.py`, + harness test suite)

## Why this is a spin-off

The AlgoBooth bug `adhoc-statepush-bridge-boot-init-flaky` had two compounding causes in two repos:

- **Cause 1 (primary, frontend) — AlgoBooth repo.** Hoist `setupStatePush()` to app-lifetime so the Vue→Rust mirror is no longer gated on the lazy `/studio` route mount. **DONE** — landed on AlgoBooth `main` as Phase 1 of that bug. This is the load-bearing, user-facing fix; it alone resolves the symptom.
- **Cause 2 (secondary, harness) — THIS repo (claude-config).** A defense-in-depth functional-readiness dimension in `ensure_runtime`. Strictly secondary to Phase 1.

Phase 2's deliverables modify `user/scripts/lazy_core.py` (which `~/.claude/scripts/lazy_core.py` symlinks to) — **not** the AlgoBooth tree. The AlgoBooth bug pipeline that drove Phase 1 commits only to the AlgoBooth work repo (`main`); committing the harness change into claude-config from that single-cycle dispatch is out of its work-repo scope. Per the bug's plan §Plan Notes cross-repo special case, Phase 2 is therefore **spun off here** rather than dropped, and Phase 1 lands + closes the symptom independently.

## Scope (carried verbatim from the origin PHASES.md Phase 2)

Add a FUNCTIONAL-readiness dimension to `ensure_runtime`, parallel to the existing `assert_sidecar_connected` dimension: after HTTP/pipe health passes, optionally assert the Vue→Rust mirror is live (a harness-driven `scene_create` → `get_scene_state` round-trip reflects the minted id), routing a functionally-dead-but-HTTP-200 runtime through recovery → BLOCKED (`mcp-runtime-unready`) instead of a bare READY. Default OFF / opt-in, mirroring the `assert_sidecar_connected` / `frontend_health_url` / `boot_liveness` back-compat pattern (read every new config key via `.get()`).

### Deliverables

1. **`assert_mirror_ready` config key** in `_ENSURE_RUNTIME_DEFAULT_CONFIG` (default absent/False — byte-identical to today for non-opt-in repos) + a `mirror_probe_*` URL/round-trip config (mirror the `sidecar_status_url` shape). Read via `.get()` everywhere.
2. **`mirror_check` injectable callable** added to `ensure_runtime`'s signature (mirroring `sidecar_check` / `frontend_probe` / `boot_alive`): when the config opts in, bind a real `scene_create` → `get_scene_state` probe against `:3333` returning True iff the mirror reflects the minted id; otherwise bind `lambda: True`. Wire it into the M4 Health phase AFTER the HTTP-200 / sidecar checks, routing a mirror-dead runtime through the same recovery→BLOCKED(`mcp-runtime-unready`) path the sidecar dimension uses.
3. **Production opt-in wiring** (WU-5): prefer enabling in the base default like `boot_liveness` IFF it is fail-safe-by-construction for non-AlgoBooth repos (no `scene_create` ⇒ probe degrades to SKIP, never a false BLOCKED); else pass an AlgoBooth opt-in config from `lazy-state.py --ensure-runtime`. Record the chosen path.
4. **Cold-build retry-window confirmation** (WU-5): confirm the `restart()` closure's `range(90)` × 5s ≈ 7.5 min ceiling is adequate for the cold audio-feature `tauri dev` build (~3m48s) given the `boot_liveness`/two-port patient-wait; widen only if it still trips a spurious BLOCKED. Record `adequate` or `widened-to-N`.
5. **Hermetic `--test` coverage** (WU-6): inject `mirror_check` exactly as existing tests inject `sidecar_check`/`boot_alive` (never the real probe). Cases: (a) default-off byte-identical; (b) opt-in + `mirror_check → False` against HTTP-200 → `BLOCKED` / `mcp-runtime-unready`; (c) opt-in + `mirror_check → True` → `READY`; (d) non-AlgoBooth repo (no `scene_create`) → degrades to skip, never a false BLOCKED.

## How to resume

Run `/harden-harness` (or implement directly) in the claude-config repo against `user/scripts/lazy_core.py`. Phase 1 being live in AlgoBooth is what makes the real probe pass once enabled — the dimension is only *meaningful* against a post-Phase-1 runtime. This work is non-blocking for the AlgoBooth fix and can land any time.
