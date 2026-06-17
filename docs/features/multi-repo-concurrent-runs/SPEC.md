# Multi-Repo Concurrent Runs — Feature Specification

> Make the lazy run-marker and its enforcement hooks per-repo, so a lazy-batch run in one repo neither blocks nor is blocked by a run in another repo.

**Status:** Draft
**Priority:** P1
**Last updated:** 2026-06-16

**Depends on:** (none)

---

## Executive Summary

The lazy pipeline's run state lives in a **single global file** —
`~/.claude/state/lazy-run-marker.json` — and the three enforcement hooks
(`lazy-dispatch-guard.sh`, `lazy-route-inject.sh`, `lazy-cycle-containment.sh`) key off
the *mere existence* of that marker rather than the repo it belongs to. The marker already
records its origin (`"repo_root": "C:/Users/Jacob/repos/AlgoBooth"`), but nothing consults
it. Two consequences fall out of this singleton design:

1. **No cross-repo concurrency.** A live run in repo A arms the dispatch guard for *every*
   session on the machine. You cannot run a lazy-batch in `claude-config` while one runs in
   `AlgoBooth` — the second run's script-emitted dispatches are denied because the guard is
   reading the first run's marker.
2. **Stale markers block unrelated work.** When a run ends without clearing the marker (or a
   run is interrupted), the orphaned marker keeps the guard armed indefinitely. Observed live
   on 2026-06-17: a completed AlgoBooth run (`forward_cycles:19/20`) left its marker in place,
   and it denied subagent dispatches in an unrelated `claude-config` `/spec` session.

This feature scopes run state **per repo**. The marker becomes a registry of per-repo runs
keyed by `repo_root`; every hook resolves the *current* repo and consults only that repo's
marker; `--run-end` clears its own repo's entry. Cross-repo concurrency is enabled; a second
run in the *same* repo is refused by construction (it would race the same `queue.json`, git
tree, and ROADMAP). The result: run isolation per repo, no global blocking, no stale-marker
contagion.

## User Experience

The operator runs `/lazy-batch` in repo A and, in a separate session, `/lazy-batch` in
repo B. Both proceed independently — each cycle's script-emitted dispatch passes the guard
because the guard matches each session's dispatch against *its own repo's* marker. Neither run
sees the other's state.

- **Cross-repo:** concurrent runs in different repos are fully isolated. No change to the
  operator's commands — the isolation is automatic.
- **Same-repo second run:** if the operator starts a second run in a repo that already has a
  live run, `--run-start` refuses with a clear message naming the in-flight run
  (`started_at`, `forward_cycles`) and instructs how to clear it if it is stale.
- **Stale marker:** a marker whose run has ended (or is older than a staleness horizon) no
  longer blocks anything in *other* repos. Within its own repo, `--run-start` reports it as
  stale and offers to reclaim. `--run-end` always clears the current repo's marker on a clean
  stop.

## Technical Design

### Current state (the singleton)

- **Marker:** `~/.claude/state/lazy-run-marker.json` — one JSON object, fields include
  `pipeline`, `cloud`, `repo_root`, `session_id`, `started_at`, `max_cycles`,
  `forward_cycles`, `meta_cycles`, `attended`.
- **Writers:** `lazy-state.py` / `bug-state.py` (`--run-start`, `--run-end`, `--cycle-begin`,
  `--cycle-end` mutate it).
- **Readers (enforcement):** `lazy-dispatch-guard.sh` (PreToolUse on `Agent` — denies
  non-script-emitted dispatches while a marker is present), `lazy-route-inject.sh`
  (UserPromptSubmit — injects the LAZY-ROUTE banner while a marker is present),
  `lazy-cycle-containment.sh` (PreToolUse — denies lifecycle/recursive-dispatch ops while the
  cycle-subagent marker is present).

### Target state (per-repo registry)

1. **Marker storage becomes per-repo.** Two viable encodings — pick during `/spec-phases`:
   - **(chosen baseline) Per-repo marker files** in a directory:
     `~/.claude/state/run-markers/<repo-key>.json`, where `<repo-key>` is a stable hash/slug
     of the normalized `repo_root` (mirrors how the claude.ai projects dir slugs paths). One
     file per active run; absence = no run for that repo.
   - **(alternative) Single registry file** mapping `<repo-key> → marker-object`. Simpler to
     enumerate, but concentrates write contention and corruption risk on one file.
   The per-file encoding is the baseline: lock-free for concurrent distinct repos (different
   files), and a stale file is trivially attributable to one repo.

2. **Repo resolution in every hook.** Each hook computes the current `repo_root` (git
   top-level of the hook's cwd / the tool call's cwd) and consults only
   `run-markers/<repo-key>.json`. If that file is absent, the hook is a no-op (allow / no
   inject). A marker for a *different* repo is invisible to it.

3. **`--run-start` refuses a same-repo second run.** If `run-markers/<repo-key>.json` exists
   and is not stale, refuse with a diagnostic (the in-flight run's `started_at` /
   `forward_cycles`). Staleness horizon: a marker is stale if its run ended (a `--run-end`
   was recorded) or `started_at` is older than a configurable bound AND no cycle advanced
   within it. A stale marker may be reclaimed (overwritten) by a new `--run-start`.

4. **`--run-end` clears its own repo's marker.** On any terminal stop (clean, checkpoint,
   max-cycles), remove `run-markers/<repo-key>.json`. This closes the stale-marker class for
   clean stops; the staleness horizon covers interrupted runs.

5. **`bug-state.py` mirrors the same registry.** Feature and bug runs in the *same* repo
   still collide (same git tree) and so share one `<repo-key>` slot — a bug run and a feature
   run in one repo remain mutually exclusive (correct: they'd race the tree). Cross-repo, both
   are isolated. (Note: the unified orchestrator — `unified-pipeline-orchestrator` — makes the
   feature/bug exclusivity moot by draining both from one run; this feature only needs the
   key to be shared per repo.)

6. **Cloud variants.** `lazy-batch-cloud` uses the same marker mechanism; the per-repo key
   applies identically. No cloud-specific divergence beyond what already exists.

### Backward compatibility / migration

- On first `--run-start` after this lands, if a legacy singleton
  `~/.claude/state/lazy-run-marker.json` exists, migrate it into
  `run-markers/<repo-key>.json` for its recorded `repo_root`, then remove the singleton. A
  legacy singleton with no resolvable `repo_root` is treated as stale and removed.
- The hooks fall back to the legacy singleton path only if the registry directory does not yet
  exist, so a partially-migrated machine never hard-errors.

## Implementation Phases

1. **Marker registry core (`lazy-state.py`/`lazy_core.py`).** Per-repo key derivation,
   read/write of `run-markers/<repo-key>.json`, `--run-start` same-repo refusal + staleness,
   `--run-end` clears own marker, legacy-singleton migration. Unit tests in
   `test_lazy_core.py`.
2. **Hook repo-scoping.** Update `lazy-dispatch-guard.sh`, `lazy-route-inject.sh`,
   `lazy-cycle-containment.sh` to resolve current `repo_root` and consult only that repo's
   marker. Extend `test_hooks.py` with a two-repo isolation harness.
3. **`bug-state.py` parity.** Mirror the registry mechanism; `lazy_parity_audit.py` updated to
   cover the shared marker surface.
4. **Cleanup + docs.** Remove the stale marker currently on disk; document the registry in
   `CLAUDE.md` (Hooks table + a state-layout note); update `turn-routing-enforcement` spec
   notes.

## Validation Criteria

| Behavior | Trigger | Expected Evidence | Where to Check |
|----------|---------|-------------------|----------------|
| Cross-repo concurrency works | Start `/lazy-batch` in repo A and repo B concurrently | Both runs' script-emitted dispatches pass the guard; each cycle advances independently | Two-repo `test_hooks.py` harness; live dual-run dispatch logs |
| Repo A run does not block repo B | Live marker present for repo A | A guard check in repo B (different cwd) allows dispatch | `test_hooks.py`: marker for repo-key A, hook invoked with cwd in repo B → allow |
| Same-repo second run refused | `--run-start` with a live non-stale marker for the same repo-key | Refusal naming the in-flight run's `started_at`/`forward_cycles` | `test_lazy_core.py` |
| `--run-end` clears own marker | Clean / checkpoint / max-cycles stop | `run-markers/<repo-key>.json` removed after `--run-end` | `test_lazy_core.py` |
| Stale marker doesn't block others | An ended/aged marker for repo A | Guard/inject in repo B = no-op; in repo A, `--run-start` reports stale + reclaims | `test_lazy_core.py`, `test_hooks.py` |
| Legacy singleton migrates | Legacy `lazy-run-marker.json` present at first `--run-start` | Migrated to `run-markers/<repo-key>.json`; singleton removed; no hard error | `test_lazy_core.py` |
| Bug + feature run share per-repo slot | Bug run live in repo A, start feature run in repo A | Refused (same repo-key) | `test_lazy_core.py` (cross-script) |

## Open Questions

- **Staleness horizon value.** What wall-clock bound (or "ended-flag only") defines a stale
  marker for same-repo reclaim? Default proposal: ended-flag OR no cycle advance for a
  generous bound; finalize in `/spec-phases`. (estimated — verify during Phase 1)
- **Repo-key derivation.** Hash vs path-slug of normalized `repo_root`; must match between
  Python writers and bash hook readers. Lock the exact algorithm in Phase 1 so both sides
  agree byte-for-byte.

## Research References

None — internal harness mechanics; no external research. Evidence base: the live stale-marker
incident (2026-06-17) and `LAZY_BATCH_REVIEW_2026-06-16_overview_2.md`.
