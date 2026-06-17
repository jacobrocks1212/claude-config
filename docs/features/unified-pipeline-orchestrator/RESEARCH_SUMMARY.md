# Research Summary — unified-pipeline-orchestrator

**Research: intentionally skipped (operator decision, 2026-06-16).** Internal harness mechanics;
no external prior art needed. Evidence base is `LAZY_BATCH_REVIEW_2026-06-16_overview_2.md`
(operator question 2 names the three toolify targets; the toolify bar derives from its
counter-note). This file satisfies the pipeline research gate (`lazy_core.py:739`) and records the
locked baseline.

## Locked Decisions

1. **Unification architecture:** one orchestrator skill + two state scripts (`lazy-state.py`,
   `bug-state.py`) + a thin merged work-list view. Both state machines and their gates stay
   intact; no large-script merge, no nested batch runs.
2. **Cross-queue ordering:** honor each item's priority/tier; equal priority → bug before
   feature.
3. **Toolification bar:** deterministic-only (deterministic + repeated + token-heavy). Judgment
   steps (verdicts, recovery dispatch, `--verify-ledger`) stay agent-driven. The miner proposes;
   promotion is deliberate.
4. **First three consumers:** `--ensure-runtime`, `--gate-coverage` (symlink-target-resolving),
   enhanced `--apply-pseudo __mark_complete__` (ROADMAP strike + `spec_dir`-keyed trim).
5. **Auto-identification** of toolify candidates (harden-harness → `/spec-bug`) is wired by the
   downstream `harness-hardening-retro-fixes` feature; this feature ships the offline miner +
   framework that path plugs into.

## Open (deferred to /spec-phases)

- Whether feature/bug queue items already carry a comparable priority field or need a
  normalization map.
- Miner tool-call signature granularity (tune against real logs).
