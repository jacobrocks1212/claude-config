# `merged-head-diverged` withholds behind a research-skipped head under `--skip-needs-research`

**Status:** Fixed
**Severity:** P1
**Discovered:** 2026-07-18 (harden-harness no-route dispatch during a `/lazy-batch-parallel`
serial-degrade run on claude-config; item in flight `shared-hook-lib`)
**Related:** `docs/bugs/merged-head-diverged-stalls-on-gated-head` (excluded parked/gated heads the
per-pipeline skip-ahead surfaces — the direct predecessor); `docs/bugs/_archive/merged-head-excludes-parked-not-operator-deferred-deadlocks`
(the file-predicate exclude set + the SPUN-OFF "make the merged head fully actionability-aware"
generalization this bug IS the 5th facet of); `docs/bugs/research-gated-head-buried-by-skip-ahead-and-merged-fallthrough`
(the `research_gated_heads` surfacing this bug is the `--skip-needs-research` complement of).

## Trigger

harden-harness **no-route** auto-trigger during a `/lazy-batch-parallel` serial-degrade run on
claude-config, launched `--park --park-provisional` with **allow-research-skip** (operator: no
research gate). `subagent-wedge-backstop-hook` generated `RESEARCH_PROMPT.md`, then hit terminal
needs-research; per the Step-4 opt-in path the orchestrator wrote `NEEDS_RESEARCH.md` and continued
with `--skip-needs-research`.

But `subagent-wedge-backstop-hook` REMAINS the `--next-merged` head, so both the unscoped probe
(routing `shared-hook-lib`) and a scoped `--feature-id shared-hook-lib` probe returned:

```
scoped shared-hook-lib probe: sub_skill=spec, cycle_prompt_ref=null,
  route_overridden_by=merged-head-diverged, merged_head=subagent-wedge-backstop-hook(feature)
scoped subagent-wedge probe:  terminal_reason=needs-research
```

`cycle_prompt` / `cycle_prompt_ref` WITHHELD → the run is feature-side stalled with **no
dispatchable route** even though `shared-hook-lib` is a ready downstream feature.

## Reconstructed route (divergence point)

The `--emit-prompt` merged-head withhold (`lazy-state.py` line ~14040) builds its exclude set from
`lazy_core.nondispatchable_item_ids(...)` ∪ `lazy_core.dispatch.probe_skipped_ids(state, ...)`,
then calls `merged_head_override`. A research-pending head skipped under `--skip-needs-research`
falls through BOTH inputs:

1. **`nondispatchable_item_ids`** covers only park families + unconditional operator-defer
   (`DEFERRED.md`). Its own docstring "Scope boundary" explicitly puts `needs-research` OUT of
   scope. Correct WITHOUT the flag (a needs-research head then HALTS — it is the dispatched
   terminal, not skippable); WRONG WITH `--skip-needs-research`, where the head IS skipped and is a
   pure file-classifiable non-dispatchable, exactly like a parked head.

2. **`probe_skipped_ids(state, ...)`** reads the probe's surfaced skip lists (`gated_heads`,
   `research_gated_heads` ⊆ `gated_heads`, `host_deferred_features`, `dep_gated`, …). But under
   `--skip-needs-research` the research-pending head is skipped by the DEDICATED
   `if skip_needs_research:` branch (`lazy-state.py` line ~2204) which appends to the LOCAL
   `research_pending_skipped` and `continue`s **before** the default-on skip-ahead branch that
   populates `_GATED_HEADS` / `_RESEARCH_GATED_HEADS`. So the skipped head is never surfaced in
   `gated_heads`, and `probe_skipped_ids` cannot fold it into the exclude set.

   For a **scoped** `--feature-id shared-hook-lib` probe the gap is even more direct: the scoped
   walk `continue`s past every non-matching id (`lazy-state.py` line ~1957) so it never visits
   `subagent-wedge-backstop-hook` at all — `gated_heads` is empty by construction. This is why the
   fix must live in the full-queue file re-scan (`nondispatchable_item_ids`), not the walk.

**Divergence point:** the Step-1a `--emit-prompt` merged-head divergence check — the merged head
(`subagent-wedge-backstop-hook`, research-pending, priority-1) ≠ the dispatched item
(`shared-hook-lib`), so `merged_head_override` WITHHOLDS the forward route, stalling the
feature side behind a head the pipeline will never dispatch this run (research is skipped by
operator choice).

## Root cause

**`root_cause_class: script-defect`** — `nondispatchable_item_ids` is a NARROWER predicate than the
set of items the driver actually skips this run. Under `--skip-needs-research` a research-pending
head is skipped but not excluded from the merged head, so the merged-head-diverged withhold fires
behind an undriveable head — the same structural class as the parked (`merged-head-includes-parked-items-deadlocks-park-run`),
operator-deferred (`merged-head-excludes-parked-not-operator-deferred-deadlocks`), gated
(`merged-head-diverged-stalls-on-gated-head`), and dep-unready
(`merged-head-diverged-withholds-on-not-skip-ahead-ready-milestone`) facets. This is the **5th**
facet of the "the merged-head exclude set must agree with what compute_state actually skips"
recurring class.

## Verified symptom

Reproduced deterministically at the `nondispatchable_item_ids` / `merged_head_override` seam
(`tests/test_lazy_core/test_dispatch.py`): a research-pending head (`NEEDS_RESEARCH.md`, no
`RESEARCH.md`) + a ready downstream feature, with `skip_needs_research=True`. Pre-fix: the head is
NOT in the exclude set → `merged_head_override` for the downstream item returns a
`merged-head-diverged` withhold. Post-fix: the head is excluded → merged head is the downstream
item → override returns `None` (route emitted).

## Fix scope (mechanical, `script-defect`)

1. **`lazy_core/docmodel.py`** — add `spec_dir_research_pending(spec_dir)`: a pure, fail-safe file
   predicate matching the `compute_state` research-pending peek (`NEEDS_RESEARCH.md` present, OR
   `RESEARCH_PROMPT.md` present with neither `RESEARCH.md` nor `RESEARCH_SUMMARY.md`).
2. **`lazy_core/depdag.py` `nondispatchable_item_ids`** — add a `skip_needs_research: bool = False`
   kwarg; when True, OR in `spec_dir_research_pending(spec_dir)` alongside the park / operator-defer
   predicates. Default False → byte-identical. Update the docstring category list + the "Scope
   boundary" paragraph (needs-research is in scope ONLY under the flag).
3. **`lazy-state.py`** — the `--emit-prompt` merged-head override caller passes
   `skip_needs_research=args.skip_needs_research`. Feature-pipeline only: research gating is a
   documented feature/bug divergence (`bug-state.py` has no `--skip-needs-research`, so its caller
   stays byte-identical — default False — and the shared helper is the "coupled mirror").
4. **Regression** — `tests/test_lazy_core/test_dispatch.py`: a `spec_dir_research_pending` predicate
   test + a `nondispatchable_item_ids` / `merged_head_override` regression (research-skipped head +
   ready downstream feature emits the downstream route WITH the flag; withhold present WITHOUT it).

## Non-goals / boundary

- Does NOT change behavior without `--skip-needs-research`: a needs-research head still HALTS
  (surfaces its research prompt) — unchanged.
- Does NOT alter the research-halt SURFACING path (`research_halt_head`, gated on
  `research_gated_heads`, which is empty under `--skip-needs-research`).
- The broader "make the merged-head exclude set a single per-item `would compute_state dispatch
  this?` oracle" is the recurring-class generalization (this is its 5th instance) — spun off
  separately, does not block this instance fix.
