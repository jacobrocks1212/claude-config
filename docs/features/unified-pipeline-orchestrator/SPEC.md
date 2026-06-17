# Unified Pipeline Orchestrator + Toolification Framework — Feature Specification

> One lazy-batch run that drains features AND bugs from a merged work-list, plus a framework that mines session logs to promote the orchestrator's repeated deterministic dances into script subcommands.

**Status:** Draft
**Priority:** P1
**Last updated:** 2026-06-16

**Depends on:** (none)

---

## Executive Summary

Two coupled improvements to the autonomous orchestrator, bundled because they share the same
goal — fewer orchestrator tokens, less drift — and the same surface (`lazy-state.py` /
`bug-state.py` + the batch skills).

**1. Unified orchestrator.** Today `/lazy-batch` drains `docs/features/queue.json` (feature
pipeline: `/spec → /plan-feature → /execute-plan → /mcp-test → __mark_complete__`) and
`/lazy-bug-batch` drains `docs/bugs/queue.json` (bug pipeline: `/spec-bug → /plan-bug → /fix
→ … → __mark_fixed__`) as two separate runs. The operator wants a single run that processes
**both** — by explicit request ("work these features and bugs") and to absorb harness
self-improvement spin-offs, which may be either a `/spec` (feature) or `/spec-bug` (bug)
enqueued to the front. The unified orchestrator interleaves a merged work-list across both
queues, dispatching the correct per-item pipeline per item, ordered by priority with bugs
breaking ties.

**2. Toolification framework.** The retro found the orchestrator hand-runs the same
deterministic multi-tool sequences every run — booting/health-checking the runtime, the
Gate-1 coverage audit, the `__mark_complete__` ROADMAP-strike + queue-trim. Each is a
token-heavy dance the agent re-derives from prose. This feature ships (a) an **offline
session-log miner** that ranks recurring deterministic tool-call sequences as toolify
candidates, (b) a **deterministic-only bar** governing what may be toolified, and (c) the
**three retro-named subcommands** as the framework's first proven consumers. The *automatic*
in-run identification of candidates (harden-harness detecting a dance and spinning off a
`/spec-bug` to toolify it) is wired by the downstream `harness-hardening-retro-fixes` feature;
this feature ships the framework that path plugs into.

## User Experience

### Unified orchestrator

- `/lazy-batch` (unified mode) drains a merged work-list. Each cycle the orchestrator asks the
  merged-queue layer for the next item; the layer returns `{item_id, type: feature|bug,
  repo_root}` honoring priority (bugs break ties). The orchestrator dispatches via the matching
  state script. Terminal actions stay type-correct: `__mark_complete__` for features,
  `__mark_fixed__` for bugs.
- **Ad-hoc enqueue extends to bugs.** The shared `adhoc-enqueue.md` protocol gains a
  `--type bug` path so "process these features and bugs" (or a harden-harness spin-off) lands
  the item in the correct queue and the unified run picks it up.
- **No regression for single-type runs.** With only one queue populated, the unified run
  behaves exactly like today's `/lazy-batch` or `/lazy-bug-batch`.

### Toolification framework

- An operator (or a retro) runs `toolify-miner.py` over the session logs and gets a ranked
  table of candidate dances: sequence signature, occurrence count, estimated tokens saved,
  and a determinism verdict. Candidates above the bar are promoted to `lazy-state.py`
  subcommands by a deliberate step (not auto-applied).
- The three shipped subcommands collapse multi-call dances into one call each:
  - `lazy-state.py --ensure-runtime` → `{ready|booted|stale-rebuilt, mcp_tools_present}`.
  - `lazy-state.py --gate-coverage <spec_path>` → deterministic Gate-1 verdict (resolves
    `mcp-tests/*.md` symlink targets, fixing the Windows pointer-file blindspot).
  - `lazy-state.py --apply-pseudo __mark_complete__ <spec_path>` → now also strikes ROADMAP and
    trims the queue by **resolved `spec_dir`** (not dir basename), killing the `-followups`
    queue-trim-miss recovery class.

## Technical Design

### Unified orchestrator — one skill, two state scripts, merged work-list (chosen architecture)

Rather than merge the two large state machines (`lazy-state.py` 340KB, `bug-state.py` 217KB)
or nest batch runs, the unification lives at the **orchestrator layer**:

- A thin **merged work-list view** (a `lazy-state.py --next-merged` style probe, or a small
  `merged_queue.py` helper) reads both `queue.json` files, applies the ordering rule
  (priority desc; equal priority → bug before feature), and returns the next actionable item
  with its `type`. It does not re-infer per-item state — it asks each state script for that.
- The unified batch skill loops: probe merged head → dispatch via `lazy-state.py` (feature) or
  `bug-state.py` (bug) using each script's existing `--emit-prompt`/`--probe`/`--cycle-*`
  contract → commit → push. Both state machines and their gates run unchanged.
- **Coupled-pair impact.** `/lazy-batch ↔ /lazy-bug-batch` parity is currently enforced by
  `lazy_parity_audit.py`. The unified skill becomes the shared driver; the parity audit grows
  to assert the merged-view dispatch branch stays consistent across feature/bug handling.
  Per CLAUDE.md's coupled-pair rule, orchestration-shape changes are mirrored.
- **Relationship to `multi-repo-concurrent-runs`:** orthogonal. That feature isolates runs
  *across repos*; this one interleaves item *types within one repo's run*. The shared per-repo
  marker slot means a unified run holds one repo's slot for both types — correct, since they
  share the git tree.

### Toolification framework

- **Miner (`toolify-miner.py`, stdlib-only).** Parses `~/.claude/projects/**/*.jsonl` (+
  `subagents/agent-*.jsonl`). Extracts orchestrator-turn tool-call sequences, normalizes them
  into signatures (tool + argument-shape, values elided), and ranks by `occurrences ×
  est_tokens_per_occurrence`. Emits a markdown table + JSON. Read-only; never mutates logs.
- **The deterministic-only bar.** A candidate is toolify-eligible iff: (a) **deterministic** —
  no LLM judgment between steps (the sequence's branches are computable from observable state,
  not from the agent's reasoning); (b) **repeated** — occurs across multiple runs; (c)
  **token-heavy** — the dance's reasoning+calls materially exceed a single subcommand. Steps
  requiring judgment (verdicts, recovery-dispatch decisions, whether output is salvageable)
  are **explicitly out of scope** — per the retro's counter-note, `--verify-ledger` and
  recovery dispatch are already the right shape and must stay agent-driven.
- **Promotion is deliberate.** The miner *proposes*; turning a candidate into a real
  subcommand is a reviewed change (and, once `harness-hardening-retro-fixes` lands, can be
  auto-initiated as a `/spec-bug` by harden-harness). The framework defines the candidate
  schema and the promotion checklist; it does not auto-write code.
- **First three consumers** (promote `mcp-coverage-audit.md`'s algorithm + the runtime-ensure
  and mark-complete dances to code):
  - `--ensure-runtime`: probe `/health` → staleness check → `dev:restart` (bg) →
    curl-until-200 → assert MCP tool present; returns a structured status.
  - `--gate-coverage <spec_path>`: read SPEC Locked-Decisions surface, grep
    `mcp-tests/*.md` (resolving symlink targets), return covered/uncovered per decision.
  - `--apply-pseudo __mark_complete__`: existing flip + **ROADMAP strike** + **`spec_dir`-keyed
    queue trim**.

## Implementation Phases

1. **Merged work-list view + ordering.** `--next-merged` probe (or `merged_queue.py`), ordering
   rule, unit tests. No skill change yet.
2. **Unified batch skill.** Single driver looping over the merged view, type-dispatching to the
   two state scripts; mirror into the cloud variant; extend `lazy_parity_audit.py`.
3. **Ad-hoc enqueue `--type bug`.** Extend `adhoc-enqueue.md` + `--enqueue-adhoc` to route by
   type into the correct queue.
4. **Toolify miner.** `toolify-miner.py` + candidate schema + the deterministic-only bar doc;
   tests over fixture transcripts.
5. **First three subcommands.** `--ensure-runtime`, `--gate-coverage`, enhanced
   `--apply-pseudo __mark_complete__`; promote `mcp-coverage-audit.md` to code; rewire the
   batch skills to call them instead of hand-running the dances. Full harness gates.

## Validation Criteria

| Behavior | Trigger | Expected Evidence | Where to Check |
|----------|---------|-------------------|----------------|
| Merged run drains both types | Both queues populated; run `/lazy-batch` unified | Items processed in priority order, bugs breaking ties; correct terminal action per type | `test_lazy_core.py` merged-view tests; live run cycle log |
| Single-type unchanged | Only features (or only bugs) queued | Behaves identically to today's per-type batch | Parity audit; regression run |
| Ad-hoc bug enqueue | `--enqueue-adhoc --type bug` | Item lands in `docs/bugs/queue.json`; unified run picks it up | `test_lazy_core.py` |
| `--ensure-runtime` collapses the dance | Call it with runtime down / stale / up | One call returns correct `{ready\|booted\|stale-rebuilt, mcp_tools_present}` | `lazy-state.py --test`; live mcp-test cycle |
| `--gate-coverage` is deterministic + symlink-safe | Call on a SPEC with `mcp-tests/*.md` symlinks | Correct covered/uncovered verdict even when pointers are 64-byte text on Windows | `lazy-state.py --test` with symlink fixture |
| `__mark_complete__` strikes ROADMAP + trims by spec_dir | Mark a `-followups` feature complete | ROADMAP row struck; queue trimmed by resolved `spec_dir`; no `queue.no-completed` error | `test_lazy_core.py`; the `-followups` regression case |
| Miner ranks real candidates | Run `toolify-miner.py` over fixture logs | Ranked table; deterministic dances surface above the bar, judgment steps below it | `toolify-miner` tests |

## Open Questions

- **Ordering field source.** Do feature/bug `queue.json` items already carry a comparable
  `tier`/`priority`, or does the merged view need a normalization map? (estimated — verify
  during Phase 1)
- **Miner signature granularity.** How coarse should tool-call signatures be to cluster "the
  same dance" without over-merging distinct sequences? Tune against real logs in Phase 4.

## Research References

None — internal harness mechanics; no external research. Evidence base:
`LAZY_BATCH_REVIEW_2026-06-16_overview_2.md` (operator question 2 names the three toolify
targets; the toolify bar derives from its counter-note).
