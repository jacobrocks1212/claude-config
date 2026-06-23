# `ensure_runtime` starves the pre-Vite `sidecar:build` window of a cold boot — Investigation Spec

> `lazy-state.py --ensure-runtime` kill-restarts a cold AlgoBooth dev runtime into a false `mcp-runtime-unready` BLOCKED, because the cold-compile discriminator's only "still booting" signal is Vite (`:1420`) being up — which is false during the multi-minute `BeforeDevCommand` (`npm run sidecar:build && vite`) phase, when BOTH ports are down and the boot is misclassified `dead`.

**Status:** Fixed
**Severity:** P1
**Discovered:** 2026-06-22
**Fixed:** 2026-06-22
**Fix commit:** f579df8
**Placement:** `docs/bugs/_archive/ensure-runtime-starves-pre-vite-sidecar-build/`
**Related:** `docs/bugs/_archive/ensure-runtime-recovery-starves-cold-compile` (prior fix — covered only the Vite-up window; this is the uncovered pre-Vite sibling); `lazy_core.ensure_runtime` / `_classify_compile_state` / `_route_legacy_non_serving` / `_recover_runtime`; AlgoBooth memory `ensure-runtime-cold-compile-starvation`; the run that surfaced it — AlgoBooth `docs/features/audio/audio-vision/domains/d2-sample-import-ui/BLOCKED.md` (Resolution UPDATE).

---

## Verified Symptoms

<!-- All confirmed by DIRECT runtime observation during the 2026-06-22 AlgoBooth /lazy-batch run, not user report. -->

1. **[VERIFIED]** `python3 ~/.claude/scripts/lazy-state.py --ensure-runtime --repo-root <AlgoBooth>` returns `{state: BLOCKED, status: "booted", health_code: 0, mcp_tools_present: false, ownership_verified: false, terminal_blocker: "Runtime recovery exhausted — restart() retried 5 times (bounded cap 5) with exponential backoff without restoring a healthy, owned runtime."}` against a cold (not-yet-running) dev runtime — observed TWICE (once at the start of the run, once after an unrelated build fix).
2. **[VERIFIED]** The AlgoBooth dev runtime is **NOT broken**. A manual `ALGOBOOTH_AUDIO_TRACE=1 npx tauri dev` (env set inline; `cross-env` is only on PATH under `npm run`) boots cleanly when left alone: `BeforeDevCommand` ran `npm run sidecar:build && vite` (tsc + esbuild bundle + native capnp addon + integrity manifest, all OK), Vite came up on `:1420`, the Rust app compiled in **3m26s**, `algobooth.exe` launched, the MCP server started on `:3333` with **229 tools**, and the sidecar connected (`get_sidecar_status` → `{is_connected: true, ready: true}`, `/health` → 200).
3. **[VERIFIED]** `ownership_verified: false` in the verdict ⇒ the failing path is **legacy mode** (`ensure_runtime` called without Identity callables), i.e. `_route_legacy_non_serving` → `_recover_runtime`.
4. **[VERIFIED]** The false BLOCKED is load-bearing: it fabricated an `mcp-runtime-unready` `BLOCKED.md` on a feature whose implementation was complete, and that false blocker kicked off an entire downstream bug chain before the runtime was proven healthy.

## Reproduction Steps

1. Ensure no AlgoBooth dev runtime is running (`npm run dev:kill`; both `:1420` and `:3333` down).
2. Run `python3 ~/.claude/scripts/lazy-state.py --ensure-runtime --repo-root <AlgoBooth-repo>`.
3. Observe: returns `state: BLOCKED` (`mcp-runtime-unready`) within a few minutes.
4. Separately, run `npx tauri dev` (or `npm run dev:restart`) in the same cold state and **leave it alone** → it reaches `:3333`/health 200 + sidecar connected in ~4 min.

**Expected:** `--ensure-runtime` patiently waits for the cold boot to finish and returns `READY` (the runtime boots fine on its own).
**Actual:** It kill-restarts the in-progress cold boot up to 5× and returns a false `BLOCKED` (`mcp-runtime-unready`).
**Consistency:** Deterministic for any cold boot whose pre-Vite `BeforeDevCommand` (`sidecar:build`) phase outlasts the bounded-recovery window.

## Evidence Collected

### Source Code (`user/scripts/lazy_core.py`)

- **`_classify_compile_state(backend_code, frontend_up)` (line 6432).** The cold-compile discriminator. Returns:
  - `"serving"` when `backend_code == 200`;
  - `"compiling"` when `backend_code != 200 AND frontend_up`;
  - **`"dead"` when `backend_code != 200 AND NOT frontend_up`.**
  The ONLY signal distinguishing a still-booting cold runtime from a genuinely crashed one is `frontend_up` (a probe of Vite `:1420`).
- **`ensure_runtime` legacy path (line 6842+).** `probe()` → non-200 → `restart()` once → re-`probe()` → still non-200 → `_route_legacy_non_serving(...)` (line 6855).
- **`_route_legacy_non_serving` (line 6891).** Probes `frontend_up` (line 6913); `_classify_compile_state(code, frontend_up) == "compiling"` ⇒ patient-wait via `_await_compile_serving` (line 6921). **Otherwise** (`"dead"`) ⇒ `_recover_runtime(cfg, "DEAD", ...)` (line 6932) — the bounded ≤5×-backoff crash-recovery loop.
- **`restart()` default (line 6739).** Fires `cfg["restart_command"]` = `"npm run dev:restart"` (`_ENSURE_RUNTIME_DEFAULT_CONFIG`, line 6325) in the background, then polls `/health` for up to 90×5s. `dev:restart` is `node scripts/kill-dev.js && cross-env … tauri dev` — **every restart begins with `kill-dev`, which terminates any in-progress boot.**

### Runtime Evidence (2026-06-22 AlgoBooth run)

- `--ensure-runtime` verdict: `BLOCKED` / `health_code: 0` / `terminal_blocker: recovery exhausted (5 retries)` — twice.
- Manual cold `tauri dev` log: `Running BeforeDevCommand (npm run sidecar:build && vite)` → sidecar build (bundle 1.1mb, native `algobooth-sidecar-native.win32-x64-msvc.node`, integrity manifest) → `VITE v6.4.1 ready` on `:1420` → `Running DevCommand (cargo run --no-default-features --features audio,…)` → `Finished dev profile … in 3m 26s` → `algobooth.exe` → `MCP Tool Registry: 229 tools registered` → `MCP server listening on http://127.0.0.1:3333`. Sidecar `is_connected: true` shortly after.

### Related Documentation

- `docs/bugs/_archive/ensure-runtime-recovery-starves-cold-compile` — the prior fix that introduced `_classify_compile_state` / `_await_compile_serving`. It correctly handles the **Vite-up, backend-compiling** window but, by construction (`frontend_up` is its only "compiling" signal), does **not** cover the **pre-Vite** window where Vite has not yet bound.
- `_ENSURE_RUNTIME_DEFAULT_CONFIG` (line 6323): `restart_command: "npm run dev:restart"`, `assert_sidecar_connected: False` (AlgoBooth opts the sidecar assertion in via a config override).

## Theories

### Theory 1: Pre-Vite `sidecar:build` window misclassified `dead` (CONFIRMED)
- **Hypothesis:** A cold boot spends its first ~1–2 min in `BeforeDevCommand` (`npm run sidecar:build`) BEFORE Vite binds `:1420`. During that window both ports are down, so `frontend_up = False` and `_classify_compile_state` returns `"dead"`, routing the boot into `_recover_runtime`'s bounded kill-restart loop instead of the patient-wait. Each `restart()` runs `dev:restart` → `kill-dev` → terminates the prior in-progress boot, so the boot never survives to the Vite-up "compiling" state the prior fix waits on. The 5-attempt cap is reached and a false `BLOCKED` is returned.
- **Supporting evidence:** the code path (6891→6913→6921/6932); `frontend_up` is the sole compiling signal; `dev:restart` begins with `kill-dev`; manual boot proves the runtime is healthy; verdict `terminal_blocker` names the 5-retry exhaustion; `ownership_verified:false` pins it to the legacy path.
- **Contradicting evidence:** none found.
- **Status:** **Confirmed.**

### Theory 2: `restart()`'s own 7.5-min `/health` poll should have caught the boot (RULED OUT as a mitigant)
- **Hypothesis:** `restart()` polls `/health` for ~7.5 min, so a single call should outlast a 4-min boot.
- **Why it does not save us:** `_recover_runtime` calls `restart()` repeatedly; each call's leading `kill-dev` kills the boot the previous call started, so no single attempt's poll ever runs against an uninterrupted boot to completion. The classification-as-`dead` is what admits the boot into this repeated-kill loop in the first place — so the root cause is the classification gap, not the poll duration.
- **Status:** Ruled out as a standalone explanation; reinforces Theory 1.

## Proven Findings

The root cause is a **classification gap** in the cold-compile discriminator: `_classify_compile_state` treats "both ports down" as `dead`, but for AlgoBooth a cold boot is legitimately "both ports down" for the entire pre-Vite `BeforeDevCommand`/`sidecar:build` phase. Routed to `_recover_runtime`, the boot is repeatedly kill-restarted (each `dev:restart` begins with `kill-dev`) and never reaches the Vite-up `compiling` state that the prior `ensure-runtime-recovery-starves-cold-compile` fix patiently waits on. Net: a healthy runtime is reported as `mcp-runtime-unready` BLOCKED. This is the **pre-Vite sibling** of the already-fixed Vite-up starvation.

## Affected Area

| Component | Files | Impact |
|-----------|-------|--------|
| Cold-compile discriminator | `user/scripts/lazy_core.py` `_classify_compile_state` (6432) | Returns `dead` for the pre-Vite cold-boot window; needs a "booting" signal that does not depend on Vite being up. |
| Legacy non-serving router | `user/scripts/lazy_core.py` `_route_legacy_non_serving` (6891) + M4 `_route_non_serving` mirror | Routes pre-Vite cold boot to `_recover_runtime` instead of a patient-wait. |
| Bounded recovery | `user/scripts/lazy_core.py` `_recover_runtime` (≤5×) + `restart()` (6739, `dev:restart` = `kill-dev && tauri dev`) | Repeated `kill-dev` terminates the in-progress cold boot every attempt. |
| Consumer | `/lazy-batch`(-cloud) Step 1d.0 runtime pre-boot for every `mcp-test` cycle | False-blocks the MCP-validation tail on ANY cold runtime — the common autonomous-run case. |

## Open Questions (for `/plan-bug` / `/fix`)

- **Which "still booting" signal covers the pre-Vite window** without re-introducing the false-READY risk the prior fix guarded against? Candidates: (a) process-liveness of the orchestrator-spawned `tauri dev`/`dev:restart` process (a live boot process ⇒ "booting", not "dead"); (b) a single patient-wait after the FIRST `restart()` before ever entering the kill-restart loop (give one uninterrupted cold-boot budget); (c) detect the `BeforeDevCommand`/`sidecar:build` phase explicitly (e.g. a marker the boot writes, or log-tailing). Process-liveness (a) is the most general and repo-agnostic.
- **Must any fix preserve the genuine-crash recovery path** (`_recover_runtime` for a real both-ports-down crash that is NOT a fresh cold boot). The discriminator must separate "cold boot in progress" from "crashed and not restarting" — likely via the spawn/process handle the harness already owns, not ports alone.
- **Default-off / repo-agnostic guarantee:** a repo with no long `BeforeDevCommand` must behave byte-identically to today (its cold boot reaches Vite quickly, so the pre-Vite window is negligible).
