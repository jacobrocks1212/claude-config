# Lazy-Pipeline Ergonomics (post-e076ed30 retro refinements) — Feature Specification

> Three small, orthogonal ergonomics refinements to the hook-enforced lazy pipeline, distilled from the `/lazy-batch-retro` of AlgoBooth session `e076ed30`: make the validate-deny guard cheaper to recover from, stop the double-probe artifact from tripping a false `LOOP DETECTED`, and give runtime-reboot status zones their own glyph so the park glyph stops being overloaded.

**Status:** Draft
**Priority:** P2
**Last updated:** 2026-06-13

**Depends on:** (none)

> Formally no dep-block entries (this repo's specs have no queue.json). Substantive relationships:
> - **turn-routing-enforcement** (`docs/specs/turn-routing-enforcement/SPEC.md`, Complete) is the substrate: it built the run marker, the prompt registry (`register_emission`/`lookup_emission`/`prompt_sha256`), the validate-deny guard (`lazy_guard.py`, `_CORRECTIVE_RECIPE`), the deny ledger + routed hardening debt (Phase 7/8), and the persisted streak counters. All three refinements here extend that machinery rather than introduce new subsystems. This spec was split out of turn-routing-enforcement deliberately: appending these as a Phase 10 there would have pushed it to 67% over its tracked 6-phase baseline, re-firing the add-phase circuit breaker (operator decision 2026-06-13 — "split into a new spec").
> - **lazy-hardening Phase 10** (`docs/specs/lazy-hardening/PHASES.md`, Complete) introduced `step_repeat_count` (the step-level oscillation counter that the debounce here targets) in `lazy_core.update_repeat_counts`.

---

## Evidence base

All three findings are from the read-only audit recorded in AlgoBooth `docs/features/_index/LAZY_BATCH_REVIEW_2026-06-13_overview.md` (session `e076ed30`, graded `A−`). The run was clean — every harness guard that fired was recovered by its sanctioned path — so these are *ergonomics* refinements (reduce recovery cost, reduce false signals), not integrity fixes. They do not change what the guard enforces; they change how cheaply and clearly it does so.

## Findings → mechanisms

### F1 — Validate-deny recovery is expensive for the common accident

A cycle dispatch had an "ORCHESTRATOR NOTE" appended to the script-emitted `cycle_prompt` (the recurring "append-a-note" accident). The guard correctly **denied** it (full-prompt hash miss), but recovery cost a meta-cycle plus a full `/harden-harness` round (re-probe → `--emit-dispatch hardening` → hardening subagent → re-probe → verbatim re-dispatch). Overview cross-cutting finding #1.

**Mechanism:**
- **F1a (pure win):** the deny `permissionDecisionReason` (`_CORRECTIVE_RECIPE`) names the exact sanctioned customization invocation — `--context KEY=VALUE` and `--emit-dispatch <class>` — so the orchestrator's next action routes through the right tool instead of re-appending. No integrity tradeoff.
- **F1b (tradeoff-flagged):** when the denied prompt is a **pure trailing-suffix superset** of an *unconsumed, fresh, cycle-class* registry entry (`dispatched_norm.startswith(registered_norm)` after `normalize_prompt_for_hash`, remainder non-empty), the guard **auto-readmits** it — strips the suffix, consumes the nonce, ALLOWS, and records an explicit `auto_readmit: true` telemetry/ledger event (never silent; graded by retro). Turns the common accident into a zero-cost allow. **Tradeoff (decide at implementation):** a trailing suffix is read LAST by the subagent, so it can override the verbatim prompt's tail clauses — this softens turn-routing's "hand-composed prompts are unexecutable" guarantee. Scope strictly: cycle-class only (never hardening-class), pure suffix only (any in-body edit still denies), and auditable. If the integrity cost is judged too high at implementation time, ship F1a alone and drop F1b (recorded as the phase's one open decision).

### F2 — Double-probe trips a false `LOOP DETECTED`

Several routes were probed twice (an inspection probe, then the dispatch-bound `--emit-prompt` probe) with no commit or dispatch between them. Because `step_repeat_count` is HEAD-blind and increments on any unchanged `(feature_id, current_step)`, the re-read inflated it and tripped 7 benign `LOOP DETECTED` blocks (`repeat_count` stayed low / HEAD advanced → not real stalls). Overview cross-cutting finding #2.

**Mechanism:** debounce `step_repeat_count` in `lazy_core.update_repeat_counts` — do NOT increment when the step signature is unchanged from the immediately-preceding **advancing** probe AND no dispatch occurred between the two probes (i.e. a re-read, not a re-attempt). The "did a dispatch happen" oracle is the registry consume-count delta when a run marker is present (the guard consumes a nonce on every allow); marker-gated so unmarked runs and `--test` baselines are byte-identical. A genuine stall still trips because it involves a real dispatch (and consume) between repeats. (Behavioral complement, documented in the SKILLs: probe ONCE with the dispatch-bound `--emit-prompt`; use `--repeat-count-peek` for inspection.)

### F3 — `⏸` glyph overloaded for runtime-reboot zones

With `park off`, the orchestrator reused the park glyph `⏸` for 5 runtime-reboot foreground-wait status zones (`⏸ runtime rebooting…`) plus the budget-guard briefing. Legible, but it overloads the glyph the R-V voice rules reserve for park (T5). Overview R-V-3 advisory.

**Mechanism:** assign a distinct glyph (e.g. `⟳`) to runtime-reboot / blocking-foreground-wait status zones in `orchestrator-voice.md`, reserve `⏸` strictly for park, and mirror the distinction in the `lazy-batch-retro` R-V grader so the new glyph is recognized and the overload no longer reads as a (benign) deviation.

## Non-goals

- No change to what the guard enforces, what counts as a stall threshold (`≥3`), or the park feature itself.
- No new subsystem — every change extends existing `lazy_core` / `lazy_guard` / `orchestrator-voice` / `lazy-batch-retro` surfaces.
- Not coupled to the bug pipeline beyond the standing coupled-pair mirror (F2 touches shared `lazy_core`, so `bug-state.py` inherits it for free; F1/F3 are guard/voice/retro surfaces).

## Verification posture

`**MCP runtime:** not-required` — this targets the claude-config harness (scripts, guard, voice contract, retro grader); no AlgoBooth app surface. Verified via `test_lazy_core.py`, `test_hooks.py`, both state-script `--test` smokes (baselines byte-identical), `lint-skills.py --check-projected --check-capabilities`, and a next-marked-run live check.
