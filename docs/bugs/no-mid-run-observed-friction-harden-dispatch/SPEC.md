# No sanctioned mid-run observed-friction harden dispatch — Investigation Spec

> The lazy-* orchestrator has no required, guard-allowed path to dispatch `/harden-harness`
> when it OBSERVES harness friction mid-run (through its own reasoning), only for the four
> automatic triggers. Observed friction is stranded: surface-and-defer, or an out-of-band manual fix.

**Status:** Concluded
**Priority:** P2
**Last updated:** 2026-07-11
**Related:** `docs/specs/turn-routing-enforcement/` (owns the dispatch guard + `--emit-dispatch`); `docs/specs/turn-routing-enforcement/NEEDS_INPUT.md` #5/#6 (surfaced from the same run); the `auto-invoke-harden-harness` operator rule (CLAUDE.md `<auto-invoke>`); `docs/bugs/efficacy-future-check-unenforced-orchestrator-prose/` (the loop-closer — the other half of fix-scope §6).

## Verified Symptom

During a live AlgoBooth `/lazy-batch` run (managed-llm-credits, 2026-07-11) the orchestrator, through its own reasoning, identified **four** harness gaps mid-run (scenario-yaml drift carve-out; gate-coverage `#`-header + missing SPEC-exemption path; the verification-row recognizer inconsistency; a stranded corrective-coverage dispatch). NONE of these arrived via an automatic harden trigger (no guard deny, no no-route, no hook error, no process-friction) — they were *observed*, not signalled. The orchestrator had no sanctioned way to dispatch `/harden-harness` for them mid-run:

- A hand-composed `Agent` dispatch to run `/harden-harness` would be **DENIED** by the validate-deny guard while the run marker is present (unregistered prompt).
- `coherence-recovery` / other emit classes do not cover harness self-hardening.
- Result: the friction was surfaced to the operator and hardened out-of-band AFTER the run ended — the run itself could not self-heal, and non-blocking gaps could not be fixed while the run continued.

## Root Cause

**Classification: `missing-contract`.** The harden dispatch mechanism (`--emit-dispatch hardening`, `lazy_core.build_hardening_emit_command`) is bound to the four automatic triggers (`validate-deny` / `no-route` / `inject-hook-error` / `process-friction`), each carrying denial/friction-specific `--context` keys. There is:

1. **No `observed-friction` trigger_kind** — a manually/reasoning-observed harness gap has no emit path, so its prompt cannot be registered, so the guard denies it mid-run.
2. **No orchestrator contract** requiring a harden dispatch on observed friction (the auto-invoke CLAUDE.md rule covers the general case but the coupled-trio SKILLs do not encode the mid-run REQUIREMENT or the dispatch mechanics).
3. **No background/wait policy** — even with a path, a mid-run harden must either block the run (bad for a non-blocking latent gap) or be fire-and-forget (unsafe for a run-blocking gap). No rule distinguishes them.

## Fix Scope (Concluded)

A required, guard-allowed, mid-run observed-friction harden dispatch with a block/background policy:

1. **`lazy-state.py --emit-dispatch hardening` gains `trigger_kind=observed-friction`** — accepts `friction_summary` / `friction_detail` / `blocking` (bool) / `item_id` / `cwd` context (in place of the denial-specific keys); emits a registered, guard-allowed hardening prompt whose body carries the observed-friction evidence + the Step-2.5 spec-bug-first instruction. `build_hardening_emit_command` extended; the `hardening` class tag (guard never blocks) is unchanged.

2. **Coupled-trio SKILL contract (REQUIRED)** — `lazy-batch` / `lazy-bug-batch` / `lazy-batch-cloud` gain a rule: when the orchestrator OBSERVES harness friction mid-run (a gate/state-script/routing defect it can name, not already an auto-trigger), it MUST emit + dispatch an observed-friction harden — it is required, not optional, matching the auto-invoke standing rule. The dispatched harden authors a claude-config bug spec first (Step 2.5), then fixes.

3. **Background vs wait — block-THIS-cycle rule (operator-confirmed 2026-07-11):**
   - **Run-blocking** (the friction stalls / loops / mis-routes the CURRENT cycle — forward progress depends on the fix): dispatch **foreground**, await it, re-probe, continue. `blocking=true`.
   - **Non-blocking** (a latent inconsistency not stalling this cycle): dispatch **backgrounded** (`Agent run_in_background`); the run continues on current behavior; the fix auto-refreshes on a later probe (fresh `python3` reads the patched `lazy_core`); the orchestrator checks the bg harden at cycle boundaries (harness-tracked, mirroring long-build ownership).

4. **Concurrency safety (background case):** a backgrounded harden edits **claude-config** only; cycle subagents edit the **target repo** → different trees, no one-writer conflict. EXCEPTION: `self_edit_mode` (the run is editing its own governing files) — force **foreground/await** when the observed friction overlaps self-edited files. The orchestrator re-reads governing files only at a cycle boundary AFTER the bg harden completes (never mid-edit), so no half-written-script probe race.

5. **Coupled-pair mirroring** (cloud keeps its `--cloud` / inline-override deltas) + `test_lazy_core.py` coverage for the new emit path + full gates.

6. **Efficacy-loop feed (self-improving-harness observability — operator-directed 2026-07-11):** an auto-invoked observed-friction harden MUST close the measurement loop — its dispatched harden records an intervention (harden-harness Step 4) with a **MEASURABLE** `target_signal` wherever the fix targets a countable ledger signal (e.g. the observed friction's own recurrence event), `expected_direction: decrease`, so the fix's effect on FUTURE runs is asserted (CONFIRMED / REFUTED / INCONCLUSIVE) rather than assumed. The observed-friction `--emit-dispatch hardening` prompt must PROMPT the harden to declare a measurable signal first (fall back to `undeclared` only for a genuinely-immeasurable diagnostic). This is HALF the loop; the other half — GUARANTEEING the efficacy/canary check actually fires at the future condition (run-end) — is `docs/bugs/efficacy-future-check-unenforced-orchestrator-prose/` (the check is currently skippable orchestrator prose). Both must land for the loop to be sound: a recorded intervention that is never evaluated, or an evaluated fix that declared no measurable signal, each leaves the loop open.

## Decisions

- **D1 — Block criterion (RESOLVED, operator 2026-07-11):** foreground-await iff the friction blocks THIS cycle's forward progress; everything else backgrounds so the run keeps moving. (Not "will block an imminent cycle", not "always background".)
- **D2 — Build vehicle (RESOLVED, operator 2026-07-11):** build inline, spec-first (this document is the spec-first gate).
- **D3 — Concurrency model:** the claude-config-vs-target-repo tree separation + the `self_edit_mode` force-await carve-out (fix scope §4). If implementation reveals a genuine race the separation does not cover, surface it as a NEEDS_INPUT rather than baking it.
