# Bug: merged-head oracle deadlocks on a parked-but-UNREACHED same-pipeline head

**Status:** Concluded
**Discovered:** 2026-07-19
**Severity:** P1 (run-blocking deadlock; recurrence of a closed class)
**Pipeline surface:** `lazy_core/dispatch.py` merged-head actionability oracle + both state scripts' `--emit-prompt` wiring
**Related:**
- `docs/bugs/_archive/merged-head-includes-parked-items-deadlocks-park-run/` (original park-fold fix)
- `docs/bugs/_archive/merged-head-excludes-parked-not-operator-deferred-deadlocks/`
- `docs/features/merged-head-actionability-oracle/` (the oracle that replaced the file predicate)
- `docs/specs/turn-routing-enforcement/` (hardening stage; this round's log entry)

## Symptom (verified)

A live claude-config bug-pipeline run (`--park-needs-input --park-blocked --park-provisional`)
DEADLOCKED: no dispatchable prompt was emitted (`cycle_prompt_ref: null`) for ANY probe even
though a dispatchable bug (`adhoc-harness-gate…`, Step 4 `/spec-bug`) sat in the queue, and the
run could NOT reach the clean `queue-exhausted-all-parked` terminal.

Observed probe JSON at failure:

```json
{"merged_probe":{"route_target":"adhoc-harness-gate…","sub_skill":"spec-bug",
  "route_overridden_by":"merged-head-diverged",
  "merged_head":{"item_id":"byref-updatedinput-unapplied-on-background-agent-dispatch","type":"bug"},
  "cycle_prompt_ref":null,"parked":[]},
 "scoped_byref":{"current_step":"Needs-input, parked (scoped)","terminal_reason":"needs-input-scoped"},
 "scoped_adhoc_harness_gate":{"route_overridden_by":"merged-head-diverged","cycle_prompt_ref":null}}
```

`byref-updatedinput-unapplied-on-background-agent-dispatch` had written a **structural-divergence
`NEEDS_INPUT.md` mid-`/execute-plan`** (Phase 1 landed, Phase 2 halted). Its SCOPED probe
(`bug-state.py --bug-id byref`) classifies it `needs-input-scoped` / parked CORRECTLY. But the
merged head stayed byref (highest severity) and every emit probe's `merged-head-diverged` withhold
suppressed `cycle_prompt_ref` — behind an undriveable (parked) head.

## Root cause (class: script-defect)

The merged-head exclude set is built by `lazy_core.dispatch.merged_head_nondispatchable_ids`. Its
same-pipeline contribution (SPEC L2) folds TWO sources into `exclude` BEFORE walking the merged
ordering: `probe_skipped_ids(state, items)` and the emit probe's own `state["parked"]` list. Any
same-pipeline id already in `exclude` is dropped from the worklist. Then the loop classifies each
remaining candidate above the emitted item:

```python
if iid == current_item_id:            break
if iid in same_ids:                   break   # <-- the defect
if is_dispatchable(scoped_probe(iid)): break
exclude.add(iid)
```

The `if iid in same_ids: break` fast-path assumes **any same-pipeline item ranked above current
that the probe did not explicitly skip is dispatchable** ("by the probe's own choice"). That
assumption holds ONLY when the emit probe's queue-order walk reached and classified every
higher-priority same-pipeline item. It BREAKS for a **parked-but-UNREACHED** head:

- The emit probe's `compute_state` walk returns the FIRST workable item it reaches in queue order
  (`adhoc-harness-gate`), and RETURNS before parking `byref` — so `byref` is absent from
  `state["parked"]` (`parked: []`) and absent from `probe_skipped_ids`.
- `byref` is therefore NOT folded into `exclude`, stays in the worklist, and — being a same-pipeline
  (bug) id — hits `if iid in same_ids: break`. The loop treats the parked head as "the first
  dispatchable head" and never excludes it.
- `next_merged(exclude_ids=...)` then still ranks `byref` (highest severity) as the head →
  `merged_head_override` fires the `merged-head-diverged` withhold on EVERY probe → deadlock; the
  run never reaches `queue-exhausted-all-parked`.

Discovering `byref`'s parked state requires **per-item state re-inference** (a scoped
`compute_state`), which the same-pipeline fast-path deliberately skips. This is a recurrence of
`merged-head-includes-parked-items-deadlocks-park-run`, now on the bug pipeline for the
mid-`/execute-plan` root-`NEEDS_INPUT` case the earlier `state["parked"]` fold does not cover.

**Why the STATELESS path is immune (and the emit path is not).** The `--next-merged` handler
(`lazy-state.py`) already builds the exclude set with `same_pipeline_state=None` and a TYPE-AWARE
`scoped_probe`, so its loop scope-probes EVERY at-or-above candidate (no `same_ids` fast-path) and
correctly excludes `byref`. The emit path passes `same_pipeline_state=state` + a cross-pipeline-only
probe, so the `same_ids` fast-path re-arms the deadlock. The two divergent implementations of the
same oracle walk are the structural defect.

## Fix scope (Concluded)

Unify the emit path with the already-correct stateless path — a STRUCTURAL fix, not a matcher patch:

1. `lazy_core/dispatch.py::merged_head_nondispatchable_ids` — REMOVE the `if iid in same_ids: break`
   fast-path (and the now-dead `same_ids` computation). The loop then classifies every worklist
   candidate above current via `is_dispatchable(scoped_probe(iid))`. Items the probe already decided
   on (parked/skipped) are still folded into `exclude` before the worklist is built and so are never
   re-probed — L2's "don't lose the live probe's ordering context" invariant is preserved for
   probe-reached items; only items the probe NEVER reached get per-item re-inference.
2. The three `--emit-prompt` callers that pass `same_pipeline_state` now scope-probe same-pipeline
   candidates too, so their `scoped_probe` must be TYPE-AWARE (dispatch each candidate to the
   correct pipeline's `compute_state` via an id→type map, mirroring the stateless `_nm_scoped_probe`):
   - `bug-state.py` merged-override emit path (same_pipeline="bug"),
   - `lazy-state.py` research-halt emit path (same_pipeline="feature"),
   - `lazy-state.py` merged-override emit path (same_pipeline="feature").
3. Regression test in `test_dispatch.py`: a parked, highest-severity, same-pipeline head ABSENT from
   `state["parked"]` is scope-probed and excluded (no withhold); a genuinely dispatchable
   same-pipeline head above current is NOT excluded (byte-identity — a real P0 jumping the queue
   still fires the withhold).

**Byte-identity:** a dispatchable merged head is probed once and short-circuits (unchanged); the
already-correct stateless path is untouched (its `exclude` starts empty). No gate weakened, no
threshold softened, no marker/registry write.
