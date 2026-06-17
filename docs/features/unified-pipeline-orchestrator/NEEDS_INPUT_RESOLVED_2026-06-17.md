---
kind: needs-input
feature_id: unified-pipeline-orchestrator
written_by: completion-integrity-gate
decisions:
  - How to discharge the 4 AlgoBooth-runtime-only acceptance rows blocking completion
class: product
next_skill: lazy
date: 2026-06-17
---

## Decision Context

### 1. How to discharge the 4 AlgoBooth-runtime-only acceptance rows blocking completion

**Problem:** `unified-pipeline-orchestrator` is the claude-config harness feature that turns `/lazy-batch` into a single unified driver over both the feature and bug queues, adds `--type bug` ad-hoc enqueue, the toolify miner, and the three deterministic subcommands (`--next-merged`, `--ensure-runtime`, `--gate-coverage`). All five phases are **implementation-complete and hermetically validated**: `pytest user/scripts/` 786/786, the byte-pinned `lazy-state.py`/`bug-state.py --test` baselines unchanged (single-type behavior provably unperturbed), `lazy_parity_audit.py` exit 0, and `project-skills`/`lint-skills` clean. The completion gate (`--apply-pseudo __mark_complete__`) refuses to write the receipt because PHASES.md still has **4 unchecked Runtime-Verification rows** that, by design, require an environment this repo does not have:
- **Phase 2** — a *live* unified `/lazy-batch` run over a two-type fixture queue, observed cycle-for-cycle (the parity audit asserts the no-regression as a prose predicate, but not a live cycle-sequence execution).
- **Phase 4** — running the toolify miner over the operator's *real* ~700-run session logs and confirming the top candidates surface the three retro-named dances (a granularity-tuning observation; the miner runs and produces a ranked table, but shape-only signatures don't yet distinguish the three named Bash-heavy dances).
- **Phase 5** — `--ensure-runtime` against a live AlgoBooth dev runtime in each state (down/stale/up), and marking a real `-followups` feature complete with no `queue.no-completed` error from AlgoBooth's `check-docs-consistency.ts`.

These are genuine acceptance criteria, not blind boxes — and per claude-config's own mission ("features ship with real, certified evidence, not narrative claims; integrity gates are load-bearing"), I will not tick them without the evidence. But they can only be exercised on an AlgoBooth host (or with your real logs), so the autonomous loop cannot discharge them here. The coherence-recovery cycle already ticked the 2 rows that ARE hermetically provable (Phase 2 single-type no-regression; Phase 5 `--gate-coverage` symlink/pointer resolution) with on-disk test evidence.

**Options:**
- **Re-scope the 4 rows to a tracked AlgoBooth-side validation follow-up and complete now (Recommended)** — Move the 4 live-runtime rows into a dated "Deferred to AlgoBooth-side validation" note in PHASES.md Implementation Notes (and optionally enqueue an `adhoc-validate-unified-pipeline-orchestrator` item so the follow-up is itself queued), tick them as deferred-with-tracking, and let `__mark_complete__` write the receipt. Rationale: implementation + the full hermetic suite are done; the deferred rows are integration *sanity* checks of logic that is already unit-proven, and blocking the entire queue on cross-repo runtime access is disproportionate. Risk: a real integration defect (e.g. `--ensure-runtime` mis-booting AlgoBooth's dev server) would not be caught until the harness is next run on AlgoBooth. Reversible — the follow-up item keeps it visible.
- **Keep the feature In-progress; do not complete until validated on AlgoBooth** — Leave PHASES as-is (4 rows unchecked, phases In-progress, no receipt). The feature stays at the head of the queue and the run halts here; you discharge the 4 rows on an AlgoBooth host later, then re-run `/lazy-batch` to complete. Rationale: strictest integrity — `Complete` is never claimed without every acceptance row genuinely satisfied. Cost: the queue is blocked on this feature until you have AlgoBooth-runtime time.
- **Validate now — you provide the AlgoBooth runtime / real logs this session** — If you can point this session at a live AlgoBooth runtime (and your real session-log corpus), I can run the 4 verifications inline, tick them with real evidence, and complete cleanly. Cost: requires switching context to AlgoBooth and a live dev runtime now.

**Recommendation:** Re-scope to a tracked AlgoBooth-side follow-up and complete now — the implementation and hermetic validation are genuinely finished, the deferred rows are live-runtime sanity checks of already-unit-proven harness logic, and tracking them as a dated deferral (rather than silently ticking) preserves the integrity bar while unblocking the queue.

## Resolution

**Decision 1 — How to discharge the 4 AlgoBooth-runtime-only acceptance rows:** **Defer + complete now** (chosen by operator via AskUserQuestion, 2026-06-17).
resolved_by: operator

Re-scope the 4 live-runtime acceptance rows (Phase 2 live unified two-type run; Phase 4 real-log named-dance surfacing; Phase 5 `--ensure-runtime` against a live AlgoBooth runtime + real `-followups` completion through `check-docs-consistency.ts`) into a dated **"Deferred to AlgoBooth-side validation"** note in PHASES.md Implementation Notes, tick them as deferred-with-tracking so PHASES is coherent for `__mark_complete__`, and write the COMPLETED.md receipt now. The receipt body must record that these 4 rows are deferred to a future AlgoBooth-host run (real, certified evidence pending there — not claimed here).
