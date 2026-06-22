---
kind: needs-input
feature_id: ensure-runtime-recovery-starves-cold-compile
written_by: spec-bug
decisions:
  - Lock the fix direction for ensure-runtime cold-compile starvation (A surgical / B ownership / B+A combined)
next_skill: plan-bug
class: product
date: 2026-06-21
---

## Decision Context

### 1. Lock the fix direction for ensure-runtime cold-compile starvation (A surgical / B ownership / B+A combined)

**Problem:** The investigation is **concluded at the root-cause level** — Theories 1, 2, 3, and 4 are all CONFIRMED and the affected area is fully mapped (see SPEC `## Proven Findings`). The single remaining decision is *which fix direction to lock*, and the SPEC author deliberately reserved this as a human call ("do **not** let `/plan-bug` pick" — SPEC Open Question 1). It is genuinely PRODUCT-class: the three directions diverge in how the harness boots/recovers a runtime and which machinery owns that boot (a `.runtime.lock.json`-owned long build vs. a patient in-loop wait), which changes observable recovery behavior and the sentinel/ownership model — not merely effort or sequencing. The root cause: `_recover_runtime` (`lazy_core.py:6896-6980`) kill-restarts then immediately re-probes :3333, so a `restart()` whose command is a cold `tauri dev` compile (minutes) is structurally starved inside the 31s cumulative backoff and writes a **false** `BLOCKED.md blocker_kind: mcp-runtime-unready`. Two hard constraints from the evidence bound the choice: (i) direction **C alone is ruled out** — in run `3b08f4e8` a fully warm rebuild was *still* BLOCKED because :3333 never bound (Theory 4); (ii) the `long-build-and-runtime-ownership` ownership stack was verified live on `main` before that run (commits `fecf84d`→`11c9b01`, `11e10fe`), so any fix MUST assert **owned-and-actually-serving** readiness, not merely "compile finished."

**Options:**
- **B + A's two-port readiness check (Recommended)** — Treat the first cold boot AND a new-crate STALE rebuild as an orchestrator-owned long build (cold-compile-sized timeout, routed through the existing `long-build-ownership` takeover path + `run_transient_build`), and reserve the ≤5×backoff loop strictly for recovering an already-healthy runtime that later crashes. Pair it with A's cheapest compiling-vs-dead discriminator — the **`:1420`-up / `:3333`-down two-port split** (`:1420` Vite comes up fast; `:3333` `/health` only serves after the Rust compile finishes) — used as the patient-wait *and* serving-readiness signal so the wait ends on "actually serving," not "compile done." Reuses shipped machinery; the operator independently arrived at B manually in BOTH confirmed sessions (`ea0c2bf8`, `3b08f4e8`). Cost: touches both `_ensure_runtime_m4` routing and `_recover_runtime`, plus a new :1420 probe in `_ENSURE_RUNTIME_DEFAULT_CONFIG`; larger blast radius than A-alone but provably sufficient.
- **A alone — distinguish compiling-vs-dead inside `_recover_runtime`** — Before each kill+restart, detect an in-progress cold compile via the :1420-up/:3333-down split; if compiling, **wait** rather than kill, and only kill+restart a genuinely crashed/absent runtime. Most surgical — directly fixes the misclassification with the smallest diff. Risk: it patches the loop but leaves first-boot routed through a *recovery* budget rather than an ownership hand-off; absent the serving-readiness assertion it does not by itself close Theory 4's "warm build, still never serves" mode, so it may need B's ownership pairing anyway.
- **C alone — adaptive/extended backoff — RULED OUT** — Widen the 31s window to a cold-compile-sized budget. Provably insufficient as a standalone fix: `3b08f4e8` BLOCKED *after* a warm build completed (the runtime never bound :3333), so more waiting changes nothing. May survive only as a *component* of A/B (sizing the patient wait), never the whole answer. Listed for completeness; do not pick alone.

**Recommendation:** B + A's two-port readiness check — it reuses the shipped ownership machinery, satisfies both hard constraints (covers the new-crate STALE rebuild AND asserts owned-and-actually-serving readiness), and matches the fix the operator reached manually in both confirmed sessions.

---

## Why this halts (batch-mode disposition)

Root cause is PROVEN — but locking the SPEC to a single fix direction is a PRODUCT-class decision the SPEC author explicitly reserved for a human ("operator chose to investigate before locking"). Marking `Concluded` now would let `/plan-bug` fabricate phases against an undecided fix scope (the exact failure the SPEC's status-lifecycle comment warns against). `**Status:**` therefore stays `Investigating`. One open investigation thread — Theory 4's relationship to shipped `long-build-and-runtime-ownership` — was **resolved inline this cycle** (the ownership stack was live on `main` before `3b08f4e8`; outcome (b) holds), and that finding is folded into this decision as a hard constraint. After the operator picks a direction, re-run advances to `/plan-bug`.

## Resolution

*Recorded on 2026-06-22 02:18:00 UTC.*

### 1. Lock the fix direction for ensure-runtime cold-compile starvation (A surgical / B ownership / B+A combined)

**Choice:** B + A's two-port readiness check
**Notes:** Operator confirmed the recommended direction. The fix MUST (1) treat the first cold boot AND a new-crate STALE rebuild as an orchestrator-owned long build (cold-compile-sized timeout, routed through the existing `long-build-ownership` takeover + `run_transient_build`), reserving the ≤5×backoff loop strictly for recovering an already-healthy runtime that later crashes; and (2) add the `:1420`-up / `:3333`-down two-port split as both the patient-wait signal AND the serving-readiness assertion, so the wait ends on "actually serving" not "compile finished" — satisfying both hard constraints (covers the new-crate STALE rebuild; C-alone remains ruled out).
