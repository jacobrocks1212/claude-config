# On-disk bug pickup routes Superseded SPECs into the merged head → universal dispatch withhold

**Status:** Fixed
**Severity:** P0
**Discovered:** 2026-07-18
**Fixed:** 2026-07-18
**Fix commit:** 04ecf963
**Related:** `docs/features/merged-head-actionability-oracle/` (the generalization this is the
7th/8th facet of); `docs/bugs/_archive/merged-head-excludes-parked-not-operator-deferred-deadlocks/`
(Round 57 — operator-defer exclusion); `docs/bugs/_archive/merged-head-includes-parked-items-deadlocks-park-run/`
(Round 56 — park exclusion); `docs/bugs/_archive/dispatch-probe-and-inject-bypass-merged-head/`
(Round 54 — the `merged-head-diverged` withhold this interacts badly with); `lazy-state.py::_find_open_feature_dirs`
(the feature-side loader that ALREADY excludes `Superseded` — the parity this restores);
`docs/specs/turn-routing-enforcement/` (hardening stage).

## Trigger

Orchestrator-observed friction during a live `/lazy-batch` run in claude-config (2026-07-18).
The run wedged: **every** bug probe — scoped (`--bug-id <id>`) and unscoped — returned
`route_overridden_by: merged-head-diverged` with
`merged_head: {block-terminal-kill-matches-separators-inside-quoted-args, bug}` and WITHHELD the
cycle prompt (`cycle_prompt` / `cycle_prompt_ref` / `cycle_model` all `null`), so the unified
`/lazy-batch` driver could not emit a dispatchable prompt for ANY item.

The named merged head, `docs/bugs/block-terminal-kill-matches-separators-inside-quoted-args`, is
`**Status:** Superseded` (its successor fix shipped 2026-07-13) and carries a `DEFERRED.md`, but is
NOT archived — it still lives under `docs/bugs/` (not `docs/bugs/_archive/`).

## Reconstructed route (divergence point)

`bug-state.py::load_bug_queue` merges on-disk open bug dirs (`_find_open_bug_dirs`) into the work
list. That list feeds `lazy_core.depdag.merged_worklist` / `next_merged` (the merged ordering behind
`--next-merged` and the emit-path `merged-head-diverged` override). Because
`block-terminal-kill-matches-separators-inside-quoted-args` is returned as an "open" bug dir, it
enters `bug_items`, ranks as the highest-priority merged head, and — since no scoped/computed head
ever equals it — the Round-54 `merged-head-diverged` withhold fires **universally**, wedging the run.

The divergence point is the **loader**: `_find_open_bug_dirs` (bug-state.py) does NOT treat
`Superseded` as a closed disposition. Its done-status filter skips only `Won't-fix` (receipt-exempt)
and receipted `Fixed`; a `Superseded` dir falls straight through to `candidates.append(...)` and is
returned as open work.

This is a **loader-parity asymmetry**: the feature-side analog `lazy-state.py::_find_open_feature_dirs`
ALREADY excludes `Superseded` unconditionally (`if status == "Superseded": continue`, receipt-exempt —
"retired without completion"). The bug loader was never given the same branch.

Why the downstream actionability oracle (`dispatch.merged_head_nondispatchable_ids`, the Round-57
generalization) did not catch it: for a SAME-pipeline bug probe the oracle folds the probe's own
`probe_skipped_ids` + `parked[]` and then walks the merged ordering, breaking on the first
same-pipeline id (`iid in same_ids`) as "the first dispatchable same head" WITHOUT scoped-probing
it. A `Superseded` dir is not in `probe_skipped_ids` and is not parked, so the walk breaks on it and
never excludes it. The correct place to stop a resolved-but-unarchived spec is at the loader — before
it ever enters the work list or merged view — exactly as the feature side does.

## Root cause

**script-defect** — `bug-state.py::_find_open_bug_dirs` omits the `Superseded` done-status filter that
its feature-pipeline mirror `_find_open_feature_dirs` already has. A `**Status:** Superseded`
resolved-but-unarchived bug dir is therefore auto-discovered as open work, enters
`merged_worklist`, becomes the merged head, and triggers the universal `merged-head-diverged`
withhold. For bugs, both `Won't-fix` AND `Superseded` are receipt-exempt terminal-resolved
dispositions (the dep DAG already treats a `Superseded` bug upstream as "retired without the work
happening" — `depdag.py`), so a `Superseded` bug is as non-actionable as a `Won't-fix` one and must
be excluded from pickup identically.

## Verified symptom

- `docs/bugs/block-terminal-kill-matches-separators-inside-quoted-args/SPEC.md` → `**Status:** Superseded`,
  `DEFERRED.md` present, not archived.
- `_find_open_bug_dirs` returns that dir (no `Superseded` filter) → merged head → every
  `--emit-prompt` probe withholds `route_overridden_by: merged-head-diverged`.
- The in-flight item `containment-hook-inline-python-exceeds-windows-cmdline-limit` (`**Status:** Concluded`)
  cannot route to `/plan-bug`.

## Fix scope (mechanical, loader-parity)

Bring `_find_open_bug_dirs` into parity with `_find_open_feature_dirs`:

1. Add a `BUG_STATUS_SUPERSEDED = "Superseded"` status token.
2. In `_find_open_bug_dirs`, skip a `Superseded` dir unconditionally (receipt-exempt, like
   `Won't-fix`) — placed beside the existing `Won't-fix` branch, BEFORE the `Fixed` receipt-aware
   branch. A `Superseded` dir is thereby never returned as open, so it never enters `bug_items`,
   `merged_worklist`, or the merged head.
3. Regression fixture: a `Superseded` on-disk bug dir must be absent from `_find_open_bug_dirs`'
   result (and therefore never surface as a merged head).

**Out of scope** (consistent with the existing `Won't-fix` precedent): no new sanctioned archive
route for `Superseded` bugs — like `Won't-fix`, a `Superseded` bug simply sits unqueued-and-skipped
on disk. Introducing a `--archive-superseded` route is a separate, non-blocking operator decision.

**Verification:** after the fix,
`bug-state.py --bug-id containment-hook-inline-python-exceeds-windows-cmdline-limit --emit-prompt --probe`
emits a real `cycle_prompt` (route `plan-bug`) with `route_overridden_by: null`.
