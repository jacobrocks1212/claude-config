# Multi-Repo Concurrent Runs — Feature Specification

> Make the lazy run-marker and its enforcement hooks per-repo, so a lazy-batch run in one repo neither blocks nor is blocked by a run in another repo.

**Status:** Complete
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

### Target state (per-repo state subdir — the chokepoint design)

The key realization: every piece of run-scoped state (marker, prompt registry, deny-ledger,
cycle-subagent marker, checkpoint) resolves its path through **one function** —
`claude_state_dir()` (24 call sites in `lazy_core.py`). Rather than thread `repo_root` through
the ~25 `read_run_marker()` / registry / ledger call sites, scope the **entire state
directory** per repo at that single chokepoint. All run-scoped state becomes per-repo for free.

1. **`claude_state_dir()` becomes repo-scoped (the one change that does the work).**
   - When `LAZY_STATE_DIR` is **set** (hermetic unit tests + hook pipe-tests) → return it
     **exactly as today**. The env override means "use this precise dir" — preserving every
     existing test's path semantics byte-for-byte (no raw-path assertion breaks).
   - When `LAZY_STATE_DIR` is **unset** (production) → return
     `~/.claude/state/<repo-key>/`, where `<repo-key>` is a stable SHA-1 of the normalized
     real `repo_root`. The active repo is set once at `main()` entry from `--repo-root`
     (cwd git-toplevel fallback); a module-level `_active_repo_root` carries it so the 24
     internal `claude_state_dir()` callers need no signature change.
   A single process operates on exactly one repo, so the module-level active repo is
   unambiguous; concurrent runs in different repos are different processes with different
   subdirs and never collide on marker, registry, ledger, or counters.

2. **Hooks route their check through a thin script query.** The three hooks currently read the
   *base* dir (`$STATE_DIR/lazy-run-marker.json`) directly — which would now be empty. They
   are changed to call `lazy-state.py --marker-present --repo-root <cwd>`, so Python owns ALL
   repo-key derivation (no bash re-implementation) and the hooks stay thin. A marker for a
   *different* repo resolves to a different subdir → `absent` → the hook is a no-op (allow /
   no inject). Fail-OPEN preserved: a query error falls back to current behavior.

3. **`--run-start` refuses a same-repo second run.** If a live (non-stale) marker exists in
   *this repo's* state subdir, refuse with a diagnostic (the in-flight run's `started_at` /
   `forward_cycles`). Staleness: a marker is stale if age > 24h (existing path A) — reclaimable
   by overwrite. A different repo's run is a different subdir and never triggers the refusal.

4. **`--run-end` clears only this repo's state.** `delete_run_marker` already removes the
   marker (+ registry) from `claude_state_dir()`, which is now this repo's subdir — so it
   touches no other repo's state with no signature change.

5. **`bug-state.py` inherits it automatically.** It imports `claude_state_dir` from the shared
   `lazy_core.py`, so the bug pipeline becomes per-repo with zero `bug-state.py` path changes.
   A feature run and a bug run in the *same* repo share the subdir (mutually exclusive —
   correct, same git tree); cross-repo isolated.

6. **Bonus — deny-ledger + registry isolation.** Because the deny-ledger and prompt registry
   live in `claude_state_dir()` too, they become per-repo for free. This fixes the cross-repo
   contamination observed live this session (an AlgoBooth run's marker arming the guard in a
   claude-config session, and its denials surfacing as claude-config's `pending_hardening`).

### Backward compatibility / migration

- On first `claude_state_dir()` resolution in production (env unset), if legacy base-dir files
  exist (`~/.claude/state/{lazy-run-marker.json, lazy-prompt-registry.json,
  lazy-deny-ledger.jsonl, lazy-cycle-active.json, lazy-run-checkpoint.json}`), migrate them
  into the keyed subdir for the marker's recorded `repo_root`, then remove the base-dir copies.
  A legacy marker with no resolvable `repo_root` is treated as stale and removed.
- Migration is idempotent and runs once; a partially-migrated machine never hard-errors.

### Consumers to update

- The three hooks (via `--marker-present`).
- `pipeline_visualizer` reads the marker for display — it must enumerate the per-repo subdirs
  (or accept a repo argument) rather than read the base dir.

## Implementation Phases

1. **Repo-scoped `claude_state_dir()` core (`lazy_core.py`/`lazy-state.py`).** `repo_key`
   derivation, module-level active-repo set at `main()`, env-set→exact / env-unset→keyed
   resolution, `--run-start` same-repo refusal, legacy base-dir migration. Unit tests in
   `test_lazy_core.py` (existing `LAZY_STATE_DIR` tests stay green by construction).
2. **Hook repo-scoping.** Add `lazy-state.py --marker-present --repo-root <cwd>`; route
   `lazy-dispatch-guard.sh`, `lazy-route-inject.sh`, `lazy-cycle-containment.sh` through it.
   Extend `test_hooks.py` with a two-repo isolation harness.
3. **`bug-state.py` parity + pipeline_visualizer.** Confirm bug pipeline inherits the keyed
   dir; `lazy_parity_audit.py` covers the surface; update `pipeline_visualizer` to enumerate
   per-repo subdirs.
4. **Cleanup + docs.** Document the keyed state-dir layout in `user/scripts/CLAUDE.md` + root
   `CLAUDE.md` Hooks table; update `turn-routing-enforcement` notes.

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

- **Staleness horizon value.** Reuse the existing 24h age staleness (path A) for same-repo
  reclaim — no new horizon needed. (resolved — reuse existing path A.)
- **Repo-key derivation.** Resolved by the chokepoint design: key derivation lives ONLY in
  Python (`repo_key` in `lazy_core.py`); the bash hooks never re-derive it — they call
  `--marker-present`. No byte-for-byte cross-language matching required.

## Research References

None — internal harness mechanics; no external research. Evidence base: the live stale-marker
incident (2026-06-17) and `LAZY_BATCH_REVIEW_2026-06-16_overview_2.md`.
