# `--ensure-runtime` recovery loop starves a cold `tauri dev` compile — Investigation Spec

> The M4 runtime recovery loop (`_recover_runtime`, ≤5 kill+restart with 1·2·4·8·16s backoff) kill-restarts a runtime that is only "DEAD" because its **cold Rust compile hasn't finished yet**. Each `restart()` (`npm run dev:restart` = `kill-dev && tauri dev`) kills the in-flight compile, so it never completes; all 5 attempts fail and the orchestrator writes a **false** `BLOCKED.md blocker_kind: mcp-runtime-unready`, halting the pipeline.

**Status:** Investigating
**Severity:** P2
**Discovered:** 2026-06-21
**Placement:** docs/bugs/ensure-runtime-recovery-starves-cold-compile
**Related:** `docs/features/long-build-and-runtime-ownership/` (SPEC LD3 bounded-recovery contract; the M4 verdict; `run_transient_build` Transient Build contract; `long-build-ownership-guard.sh`); `user/scripts/CLAUDE.md` → `--ensure-runtime` CLI doc; `docs/bugs/env-transient-counts-against-validation-retry-budget` (sidecar-pipe readiness — same `_recover_runtime` loop); `lazy-batch/SKILL.md` Step 1d.0 (sole consumer)

<!-- Status lifecycle: Investigating → root cause PROVEN below, but the FIX DIRECTION is
     a deliberate human decision (3 candidates, see Open Questions). Operator chose
     "investigate further before locking" the direction; leaving Investigating so
     /plan-bug does not fabricate phases against an undecided fix scope. -->

---

## Verified Symptoms

1. **[VERIFIED]** During an AlgoBooth `/lazy-batch` run, the orchestrator reported *"Confirmed dead: nothing on :3333 or :1420, no runtime lock. The runtime genuinely failed all 5 boot attempts."* — operator screenshot + session log (`…/C--Users-Jacob-repos-AlgoBooth/ea0c2bf8-5ac3-4778-ac28-ff47ac055c73.jsonl`, line 154, `2026-06-22T01:25:41.824Z`).
2. **[VERIFIED]** **No fresh boot logs were produced** by the 5 attempts — the retry loop interrupted the cold compile before it could emit anything (session log line 160). This is the smoking gun: a real boot failure produces logs; a *starved* compile produces none.
3. **[VERIFIED]** The runtime was **not actually broken**: a follow-up `cargo check` passed in **27s** (warnings only, no errors) — the backend compiles cleanly (session log line 165, `01:27:28Z`). The "failure" was the loop killing the cold build, not a build error.
4. **[VERIFIED]** Manual recovery worked: after `cargo check` warmed the cache, a single **orchestrator-owned** `tauri dev` (backgrounded) booted normally and :3333 came up — exactly the "long-build-ownership" hand-off the operator diagnosed live.
5. **[VERIFIED]** Severity is **P2** — real autonomy friction with a working manual workaround (warm the cache + boot an owned dev), not a correctness/data-loss defect — confirmed via AskUserQuestion.
6. **[VERIFIED — multi-session]** The pattern is **not a one-off**: an independent earlier run (`3b08f4e8`, 2026-06-21 03:03Z) hit the identical starvation after a feature added `tauri-plugin-fs` + `smol_str` crates, forcing a cold recompile that "exceeds the retry window" — confirming the warm-runtime-with-new-crates trigger (Theory 3), not just first-boot.

## Reproduction Steps

1. From a **cold Rust build state** (fresh checkout, `target/` cleaned, or a large `src-tauri/crates/**` change), start a `/lazy-batch` run that reaches the Step 1d.0 mcp-test pre-boot.
2. The orchestrator calls `lazy-state.py --ensure-runtime`. No `.runtime.lock.json` (or a dead-PID lock) ⇒ M4 classifies **DEAD** ⇒ `_recover_runtime`.
3. The loop runs ≤5 iterations: `sleep(backoff)` → `restart()` (`npm run dev:restart` = `kill-dev && tauri dev`) → `probe()` `/health` on :3333 **immediately**.
4. Each `restart()`'s `kill-dev` terminates the in-progress cold compile; the fresh `tauri dev` gets at most the *next* backoff window (max 16s) before the following iteration kills it again.

**Expected:** ensure-runtime recognizes "backend still compiling (cold build), not dead" and **waits** for first boot (or hands the boot to orchestrator ownership with a cold-compile-sized budget), then returns READY.
**Actual:** A cold compile (minutes) can never finish inside the cumulative 31s backoff window; all 5 attempts probe a not-yet-serving :3333, the loop exhausts → `state: BLOCKED` → orchestrator writes `BLOCKED.md blocker_kind: mcp-runtime-unready` and dispatches no subagent. **False negative.**
**Consistency:** Deterministic for any boot whose compile exceeds ~16s of uninterrupted progress (every cold/first build; large warm STALE rebuilds with Rust changes).

## Evidence Collected

### Source Code

- **The recovery loop — `user/scripts/lazy_core.py:6896-6980` (`_recover_runtime`).** `for attempt in range(_RUNTIME_RECOVERY_MAX_ATTEMPTS)`: `sleep(BACKOFF_BASE * 2**attempt)` → `restart()` → `code, payload = probe()`; `code == 200` ⇒ READY, else loop; on exhaustion ⇒ `BLOCKED` with `terminal_blocker`. **Crucially, `probe()` is called immediately after `restart()` with no wait for the compile**, and the backoff `sleep` precedes the *next* `restart()` (whose `kill-dev` then kills the compile). The compile's max uninterrupted window is therefore the largest single backoff (16s) — never the full 31s, and never minutes.
- **Constants — `lazy_core.py:6458,6461`.** `_RUNTIME_RECOVERY_MAX_ATTEMPTS = 5`, `_RUNTIME_RECOVERY_BACKOFF_BASE = 1.0` ⇒ schedule `1, 2, 4, 8, 16` (Σ = 31s).
- **The restart command — `lazy_core.py:6325`** (`_ENSURE_RUNTIME_DEFAULT_CONFIG`): `"restart_command": "npm run dev:restart"`. In AlgoBooth, `dev:restart` = `kill-dev && tauri dev` — a **full backend build** from whatever the cache state is. The health probe is `http://localhost:3333/health` (`lazy_core.py:6324`).
- **The classifier — `lazy_core.py:6783-6894` (`_ensure_runtime_m4`).** Routes into `_recover_runtime` on: (a) no lock + nothing on :3333 (**DEAD** — the fresh/first-boot case, `:6819`); (b) lock present but recorded PID dead (`live_start is None` ⇒ **DEAD**, `:6842`); (c) ownership-verified but `stale_check()` true (**STALE** rebuild, `:6858`); (d) owned+alive but `/health` refused (**DEAD**, `:6888`). All four feed the same starvation-prone loop.

### Runtime Evidence (session log)

Session `ea0c2bf8-5ac3-4778-ac28-ff47ac055c73`, AlgoBooth project dir:
- L154 `01:25:41Z` — "Confirmed dead: nothing on :3333 or :1420, no runtime lock. The runtime genuinely failed all 5 boot attempts."
- L160 — "No fresh boot logs were produced — the `--ensure-runtime` retry loop (5× kill+restart with backoff) most likely kept interrupting `tauri dev`'s cold Rust compile before it could finish (`dev:restart` = `kill-dev && tauri dev`, a full backend build). That's a long-build-ownership case: the bounded retry loop is the wrong tool for a slow cold compile."
- L165 `01:27:28Z` — "`cargo check` passed in 27s (warnings only, no errors) … The boot failure was the bounded retry loop interrupting the cold build, not a real error. The cache is now warm. Booting one orchestrator-owned `tauri dev` in the background."

### Related Documentation

- **`long-build-and-runtime-ownership` (feature, Status: Complete 2026-06-20)** established the M4 verdict and the **LD3 bounded-recovery contract: STALE/DEAD auto-recover via `restart()` in a bounded exponential-backoff loop capped at ≤5 attempts**. The contract is **silent on the case where `restart()` itself spawns a long compile** — it was designed for *crash-loop* recovery (a runtime that died and restarts fast), not for *first-boot-of-a-cold-tree* (a runtime that has never come up because its build is still running). This is the design gap, not a regression.
- **`long-build-ownership-guard.sh`** (PreToolUse Bash, request-time) redirects `tauri build` / `cargo build --release` / `npm run build` to orchestrator ownership via the `LONG-BUILD-OWNERSHIP-TAKEOVER` signature. It does **not** cover `tauri dev` / `dev:restart` — those are the Persistent Service runtime (LD5: one spawn primitive, two contracts), so the cold compile *hidden inside* `dev:restart` gets none of the ownership/patience the guard gives explicit long builds.
- **No existing/duplicate bug** covers ensure-runtime starving a cold compile (grep of `docs/bugs/` for `ensure-runtime`/`cold compile`/`boot attempt`/`starve` → no matches). `env-transient-counts-against-validation-retry-budget` touches the *same loop* (sidecar-pipe readiness) but a different failure mode.

### Additional Evidence — Multi-Session Mining (2026-06-21)

Mined all 58 AlgoBooth session logs (39 carried the signature); 4 parallel read-only passes. Hard, quote-grounded findings (keyword-frequency inference was discarded as too weak to cite):

- **Second confirmed starvation — `3b08f4e8` (2026-06-21 03:03:52–03:09:49Z).** Independent of the screenshot run. Verbatim:
  - L335 — `--ensure-runtime` returned **BLOCKED**, `health_code: 0` (dev HTTP server never reached 200) after 5 bounded retries.
  - L339 — *"The likely cause is a cold Rust debug build: the feature just added tauri-plugin-fs + smol_str crates, so tauri dev must recompile, which exceeds the retry window."*
  - L347 — *"Warming the Rust debug build in the background (orchestrator-owned long build) so the subsequent tauri dev boot is incremental"* ⇒ the operator independently reached **fix-direction B** as the manual workaround (the second session to do so).
  - L355/358 — background build completes (exit 0, ~3 min).
  - **L362 — *"Still BLOCKED after a warm build — so it's not build time; the MCP server (3333) genuinely never comes up."*** ⇒ a **co-occurring failure mode beyond compile time** (Theory 4): pre-warming alone did not restore READY.
- **Distinct failure class — `--ensure-runtime` false-positive READY + background-process teardown** (`e076ed30` ×3 incl. `adhoc-mcp-slip-pad-binding-tools`, `f1-global-scale`; `80dbeeaf` L103). The verdict reports `booted/ready` (or the orchestrator probes and finds) **nothing listening on :3333/:1420 and no dev process** — the backgrounded `dev:restart` child was torn down when the Bash call returned (the subagent turn-boundary reaping that `long-build-and-runtime-ownership` was built to fix). Recovery in every case was an **orchestrator-owned, harness-tracked** re-boot. This is the *inverse* of starvation (false READY vs. false BLOCKED) but the **same root family**: ensure-runtime cannot tell "owned + actually serving" from "torn down / still compiling."
- **`:1420` instrumentation blind spot.** Across all mined sessions, `:1420` (Vite) is probed almost never — the current ensure-runtime checks only `:3333`. So the logs can **neither confirm nor refute** the two-port discriminator; it has simply never been instrumented. This is a *gap to close*, not evidence against the signal.
- **Frequency (honest):** ≥2 hard-confirmed cold-compile starvations (`ea0c2bf8`, `3b08f4e8`), both recent, both triggered by new-crate / cold-tree builds; the false-READY/teardown class recurs more often. Both classes always required manual orchestrator-owned recovery — **zero** cases of the bounded loop self-recovering a cold compile.

## Theories

### Theory 1: The recovery loop's restart-and-immediately-probe shape starves any restart whose command is a long compile — **CONFIRMED (root cause)**
- **Hypothesis:** `_recover_runtime` assumes `restart()` produces a fast-booting process; `probe()` fires immediately and the next `kill-dev` lands before a cold compile (minutes) can finish, so the runtime is structurally unable to recover within the 5×backoff budget.
- **Supporting evidence:** Code at `lazy_core.py:6930-6942` (immediate probe, kill-before-compile-completes); 31s cumulative cap vs. a minutes-long cold compile; "no fresh boot logs" (compile never finished); `cargo check` proving the build is healthy; manual owned-boot succeeding once uninterrupted.
- **Contradicting evidence:** None found.
- **Status:** **Confirmed.**

### Theory 2: First/cold boot is conflated with crash recovery — **CONFIRMED (contributing design gap)**
- **Hypothesis:** The DEAD verdict (no lock, nothing serving) on a *never-yet-booted* cold tree routes into the same bounded crash-recovery loop as a runtime that died after running. First-boot of a cold tree needs a cold-compile-sized budget (or orchestrator ownership), not a 31s crash-retry.
- **Supporting evidence:** `_ensure_runtime_m4:6819` (no-lock DEAD) and `:6842` (dead-PID DEAD) both call `_recover_runtime` with the crash-recovery backoff; LD3 contract written for crash-loops; the long-build guard already exists for *explicit* long builds but not for the dev-server's hidden compile.
- **Status:** **Confirmed** — the fix surface centers here.

### Theory 3: Scope is broader than first-boot — warm STALE rebuilds with new/large Rust deltas hit the same wall — **CONFIRMED**
- **Hypothesis:** The `stale_check()` → STALE → `_recover_runtime` path (`:6858`) triggers `dev:restart` after a source change; a new-crate or large `src-tauri/crates/**` delta produces a multi-minute (near-cold) compile that the same loop starves identically.
- **Supporting evidence:** `3b08f4e8` L339 — a previously-running runtime, after the feature added `tauri-plugin-fs` + `smol_str`, recompiled long enough to "exceed the retry window" and BLOCKED. Same loop, same `restart_command`, same immediate-probe shape; only the compile's warmth differs.
- **Contradicting evidence:** Most STALE rebuilds are incremental (seconds) and recover fine — so this is the *new-dependency* tail of STALE, not every rebuild. The most frequent deterministic trigger remains cold/first boot.
- **Status:** **Confirmed** — any fix must cover the new-crate STALE rebuild, not only first-boot.

### Theory 4: A co-occurring failure mode survives a warm build — pre-warming alone is insufficient — **CONFIRMED (scoping caveat)**
- **Hypothesis:** Even when the compile is removed as a variable, `--ensure-runtime` can still return BLOCKED because the booted runtime is torn down / never binds :3333 — the same false-READY/teardown class seen in `e076ed30`/`80dbeeaf`, where the backgrounded `dev:restart` child dies at the Bash/subagent turn boundary.
- **Supporting evidence:** `3b08f4e8` L362 — *"Still BLOCKED after a warm build … the MCP server (3333) genuinely never comes up"*; the false-positive-READY teardown events in the mining (`e076ed30` ×3, `80dbeeaf` L103), all recovered only by an **orchestrator-owned, harness-tracked** re-boot.
- **Contradicting evidence:** This overlaps the *already-shipped* `long-build-and-runtime-ownership` work (ownership sentinel + `run_transient_build`), so part of it may already be addressed on current `main`; `3b08f4e8` predates verifying which ownership fixes were live in that run.
- **Status:** **Confirmed as a real, distinct mode** — it means a backoff-only fix (direction C) is provably insufficient (the warm rebuild finished and it was *still* blocked), and even direction B (pre-warm) must be paired with an **owned-and-actually-serving** readiness check, not just "compile done."

## Proven Findings

- **Root cause (confirmed):** `_recover_runtime` kill-restarts and immediately re-probes, so a `restart()` whose command is a long compile (`dev:restart` cold) is structurally starved — the compile never gets more than one backoff window (≤16s) of uninterrupted runtime before the next `kill-dev`. Cumulative budget 31s ≪ a cold Tauri/Rust compile.
- **Why it surfaces as a false BLOCKED:** loop exhaustion ⇒ `state: BLOCKED` + `terminal_blocker` ⇒ Step 1d.0 orchestrator writes `BLOCKED.md blocker_kind: mcp-runtime-unready` (verdict text verbatim) and halts — indistinguishable, to the pipeline, from a genuinely dead runtime.
- **The missing signal:** ensure-runtime cannot today tell "backend still compiling" from "backend dead." The cheapest cross-platform discriminator is the **two-port split**: `tauri dev` brings Vite up on **:1420** fast, but **:3333** (`/health`) only starts serving *after* the Rust compile finishes. `:1420 reachable && :3333 refused` ⇒ **compiling/booting — be patient, do NOT kill**. The current probe checks only :3333, so it reads a still-compiling backend as "dead." Mining confirms :1420 is essentially never probed today (instrumentation blind spot), so adding it is net-new signal.
- **Reproduced across runs (not a one-off):** ≥2 independent cold-compile starvations (`ea0c2bf8` 2026-06-22, `3b08f4e8` 2026-06-21), both new-crate/cold-tree triggered; the bounded loop self-recovered a cold compile in **zero** mined cases.
- **A backoff-only fix is provably insufficient (Theory 4):** in `3b08f4e8` the warm rebuild completed and ensure-runtime was *still* BLOCKED — the runtime never bound :3333. The fix must also guarantee an **owned, harness-tracked, actually-serving** runtime (overlapping the shipped `long-build-and-runtime-ownership` ownership/teardown work), not merely "wait longer for the compile."
- **The operator's manual fix is consistent across both sessions:** warm/own the build, then boot **one orchestrator-owned** `tauri dev` and watch readiness — i.e. fix-direction B was independently arrived at twice.

## Affected Area

| Component | Files | Impact |
|-----------|-------|--------|
| M4 recovery loop | `user/scripts/lazy_core.py:6896-6980` (`_recover_runtime`); constants `:6458,6461` | Kill-restart starves a long-compile `restart()`; immediate-probe shape is the core defect |
| M4 classifier | `lazy_core.py:6783-6894` (`_ensure_runtime_m4`) | Routes first/cold boot (DEAD) into crash-recovery; conflates "never booted" with "crashed" |
| ensure-runtime config | `lazy_core.py:6324-6334` (`_ENSURE_RUNTIME_DEFAULT_CONFIG`) | Health probe is :3333-only; no :1420/compile-in-progress signal; `restart_command` hides a long build |
| Orchestrator consumer | `user/skills/lazy-batch/SKILL.md` Step 1d.0 (workstation-only) | Consumes the verdict; turns false BLOCKED into a pipeline halt |
| Long-build ownership | `user/hooks/long-build-ownership-guard.sh`; `lazy_core` `run_transient_build` | Covers explicit long builds, NOT `dev:restart`'s hidden compile — the candidate hand-off path |
| `--test` harness | in-file `lazy-state.py --test` / `test_lazy_core.py` | Hermetic injected probe/restart/sleep already exists — a starvation/compile-in-progress fixture is addable without a real runtime |

## Open Questions

The root cause is **proven** and the mining settled Q2/Q3 below. The remaining decision is the **fix direction** (operator chose to investigate before locking — captured here as the load-bearing fork for `/plan-bug`):

1. **Which fix direction?** (deliberate human decision — do **not** let `/plan-bug` pick). Mining biases toward **B (+A's readiness check)** and rules out C-alone:
   - **(A) Distinguish compiling-vs-dead in `_recover_runtime`.** Before each kill+restart, detect an in-progress cold compile (the **:1420-up / :3333-down** two-port split is the cheapest cross-platform signal; a live `cargo`/`rustc` child or advancing `target/` mtime are stronger but need cross-platform process/stat probes per the host-capability "probe actively, never `which()`" discipline). If compiling, **wait** on first boot rather than killing; only kill+restart a genuinely crashed/absent runtime. *Most surgical — fixes the actual misclassification.*
   - **(B) First-boot ≠ recovery budget.** Treat the first cold boot (and a new-crate STALE rebuild) as an orchestrator-owned long build (generous, cold-compile-sized timeout, routed through the long-build-ownership takeover path) and reserve the ≤5×backoff loop strictly for recovering an already-healthy runtime that later goes STALE/DEAD. ***Strongly supported*** — the operator independently chose this manually in BOTH confirmed sessions (`ea0c2bf8`, `3b08f4e8`), and it reuses the shipped ownership machinery.
   - **(C) Adaptive/extended backoff — RULED OUT as a standalone fix.** `3b08f4e8` proves a warm build still BLOCKED, so widening the window alone does not fix it (Theory 4). May still be a *component* of A/B (sizing the patient wait), never the whole answer.
2. **~~Cross-platform compile-in-progress detection~~ → settled toward the two-port split.** Lock in **:1420-up / :3333-down** as the primary stdlib signal (no process walk; the host-capability axis warns against process-tree probing). Mining shows :1420 is currently un-instrumented — adding it is the concrete first move. A `target/`-mtime corroborator is optional hardening, not required for v1.
3. **~~Scope: first-boot only?~~ → settled: cover both.** Theory 3 is now **Confirmed** (new-crate STALE rebuild starves identically), so the fix must cover first-boot **and** new-dependency STALE. A compiling-aware wait covers both for free.
4. **Co-occurring teardown/never-serves mode (Theory 4) — relationship to shipped work — RESOLVED (this cycle, 2026-06-21).** `long-build-and-runtime-ownership` is marked **Complete 2026-06-20**, and `3b08f4e8` ran **2026-06-21**. Inline verification this cycle (`git log -- user/scripts/lazy_core.py`) confirms the full ownership stack **was landed on `main` before `3b08f4e8` ran**: commits `fecf84d` (P1 spawn_detached + runtime-lock + verify_runtime_ownership), `cb28c5b` (P2 WU-1 M4 verdict), `8395dd6` (P2 WU-2 bounded recovery), `709d6aa` (P3 long-build guard + transient-build), `a3a3aba`/`11c9b01` (P4), plus the later `11e10fe` (env-transient sidecar-pipe readiness dimension). **Outcome (b) holds:** the warm-build-still-BLOCKED symptom occurred *with ownership machinery live*, so the fix MUST pair the patient compiling-aware wait with an **owned-and-actually-serving** readiness assertion (not merely "compile done"), and this is a standing regression signal against `long-build-and-runtime-ownership`'s readiness contract. This thread is no longer open — it is folded into the fix-direction decision (Q1) as a hard constraint: backoff-only (C) is insufficient, and any direction must assert serving-readiness, not just compile completion.
5. **`BLOCKED` semantics when a compile genuinely never finishes:** after a *patient* wait, should exhaustion still be `mcp-runtime-unready`, or a distinct `cold-compile-timeout` blocker so the operator can tell starvation from a real build hang?
