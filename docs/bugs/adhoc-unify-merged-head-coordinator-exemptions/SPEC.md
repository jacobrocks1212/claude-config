# Unify merged-head coordinator-emission exemptions — Investigation Spec

> The `--emit-prompt` merged-head divergence guard carries two separately-computed
> coordinator-emission exemption booleans (`_emit_is_lane`, `_emit_is_lease_held`),
> duplicated verbatim across both state scripts. Generalize to one predicate before a
> third near-neighbor (demoted-serial-rerun) accretes its own carve-out.

**Status:** Concluded
**Severity:** Low
**Discovered:** 2026-07-18
**Placement:** docs/bugs/adhoc-unify-merged-head-coordinator-exemptions
**Related:** `docs/bugs/dispatch-probe-and-inject-bypass-merged-head` (the guard's origin), `parallel-worktree-batch-execution` / `lazy-batch-parallel-run-harness-gaps` (round-1 gap 1 = lane exemption; round-2 gap 8 = serial-tail lease exemption), `merged-head-actionability-oracle`

---

## Verified Symptoms

<!-- This is a harness code-hygiene / maintainability spin-off (harden round 94), NOT a
     runtime-behavior defect. There is no user-facing broken behavior — the product output
     of the state scripts is CORRECT today. The "symptom" is a structural one, directly
     observable in source (no user round needed to confirm), so it is recorded as
     [PROVEN-IN-SOURCE] rather than a user-confirmed [VERIFIED] runtime symptom. -->

1. **[PROVEN-IN-SOURCE]** The merged-head divergence guard's skip condition is gated on TWO
   ad-hoc booleans combined inline — `if _emit_marker is not None and not _emit_is_lane and
   not _emit_is_lease_held:` — one per accreted coordinator-emission exemption
   (`lazy-state.py:14838`, `bug-state.py:10089`).
2. **[PROVEN-IN-SOURCE]** Each exemption is a separately-computed local with its own
   fail-safe block and its own observability `elif`:
   - `_emit_is_lane` (`parent_run` set → coordinator-authorized lane probe; round-85 / gap 1) —
     `lazy-state.py:14803-14805`, `bug-state.py:10062-10064`.
   - `_emit_is_lease_held` (probe's own `feature_id` holds a live coordinator lease → serial-tail
     in-flight completion; round-94 / gap 8) — `lazy-state.py:14828-14836`, `bug-state.py:10079-10087`.
3. **[PROVEN-IN-SOURCE]** The pattern is DUPLICATED across the coupled pair (both state scripts
   carry byte-parallel copies of both booleans + both observability `elif` branches), and the
   ADHOC_BRIEF anticipates a THIRD near-neighbor exemption (demoted-serial-rerun) that would,
   under the current shape, add a third `not _emit_is_<X>` conjunct + a third fail-safe block +
   a third `elif` in FOUR places (2 scripts × {compute, observability}).

## Reproduction Steps

<!-- A structural/maintainability defect has no runtime repro; the "repro" is reading the
     current source and observing the fragmentation + duplication the fix removes. The
     symptom-reproduction gate at completion binds to the regression net named in Recommended
     Fix Scope (the state scripts' `--test` baselines byte-unchanged = product behavior
     preserved), not a runtime symptom. -->

1. Open `user/scripts/lazy-state.py` at the `--emit-prompt` merged-head guard (~line 14790-14965).
2. Observe `_emit_is_lane` and `_emit_is_lease_held` computed as two independent booleans, ANDed
   into the guard condition at 14838, each with its own `elif` observability branch (14944, 14954).
3. Open `user/scripts/bug-state.py` (~line 10055-10225) and observe the byte-parallel duplicate.
4. Confirm both are semantically ONE question — *"is this a coordinator-arbitrated emission the
   serial merged-head divergence premise does not apply to?"* — expressed as N ad-hoc booleans.

**Expected:** One named predicate answers "is this a coordinator-arbitrated emission?"; adding a
new coordinator exemption is a one-line edit in ONE place, with the diagnostic reason carried by
the predicate's return value.
**Actual:** N booleans ANDed inline, duplicated across two scripts, each new exemption touching 4
sites; the third (demoted-serial-rerun) would extend the accretion.
**Consistency:** always (structural).

## Evidence Collected

### Source Code

The guard lives in the `--emit-prompt` handler of each state script and calls the shared
`lazy_core.dispatch.merged_head_override` (`lazy_core/dispatch.py:358`). The withhold-skipping
logic that this bug targets is NOT in the shared helper — it is the per-script CALLER prologue
that decides whether to RUN the override at all:

```python
# lazy-state.py:14803  (bug-state.py:10062 — verbatim mirror)
_emit_is_lane = bool(isinstance(_emit_marker, dict) and _emit_marker.get("parent_run"))
# lazy-state.py:14828  (bug-state.py:10079 — verbatim mirror)
_emit_is_lease_held = False
if _emit_marker is not None and not _emit_is_lane and state.get("feature_id"):
    try:
        _emit_is_lease_held = lazy_coord.has_live_lease(
            lazy_core.claude_state_dir() / "leases.json", state.get("feature_id"))
    except Exception:
        _emit_is_lease_held = False
_merged_override = None
if _emit_marker is not None and not _emit_is_lane and not _emit_is_lease_held:   # ← the guard
    ...run merged_head_override...
elif _emit_is_lane:      # observability diag (parent_run)
    ...
elif _emit_is_lease_held:  # observability diag (live lease)
    ...
```

The `lazy_coord` import in each script is ALREADY annotated as existing solely "for the
read-only `has_live_lease()` helper used by the `--emit-prompt` merged-head divergence guard's
serial-tail lease exemption" (`lazy-state.py:77-82`, `bug-state.py:97-100`) — confirming the two
exemptions are one conceptual surface.

### Git History

The two exemptions landed in separate `lazy-batch-parallel-run-harness-gaps` rounds: round-1 gap
1 added the lane (`parent_run`) exemption; round-2 gap 8 added the serial-tail live-lease
exemption. Both are coupled-pair mirrored into `bug-state.py` (feature-pipeline-only feature, but
the mirror keeps the pair from drifting — documented in the mirror comments). This bug was spun
off by harden round 94 as the anti-accretion generalization.

### Related Documentation

`user/scripts/CLAUDE.md` → "Concurrency plane — sanctioned parallel worktree lanes" documents the
lane/lease/coordinator machinery; the merged-head guard is documented at `dispatch.py`'s
`merged_head_override` docstring. Both exemptions are the "the serial premise (only one item is
active and it must be the global head) is void under coordinator arbitration" carve-out.

## Theories

### Theory 1: Two exemptions are one predicate expressed as N booleans (CONFIRMED)
- **Hypothesis:** `_emit_is_lane` and `_emit_is_lease_held` both answer a single question —
  *"is this emission coordinator-arbitrated, so the serial merged-head divergence premise does
  not apply?"* — and should be one predicate.
- **Cause label:** `traced`. The symptom (fragmented + duplicated skip logic) appears at the
  guard condition (`lazy-state.py:14838` / `bug-state.py:10089`); it is produced directly by the
  two separately-computed booleans cited above. The fix changes exactly those nodes — fix-site
  is ON the traced path (there is no runtime indirection to trace; the code IS the surface).
- **Supporting evidence:** the two mirror-comment blocks each describe the SAME "serial premise
  void under coordinator arbitration" rationale; the shared `lazy_coord` import comment already
  treats them as one surface; the ADHOC_BRIEF names a third near-neighbor.
- **Contradicting evidence:** none. (The lane check is pure marker read; the lease check does I/O
  via `has_live_lease` — but both fail-safe to False and both feed the identical skip decision,
  so a unifying predicate subsumes both without behavior change.)
- **Status:** Confirmed.

## Proven Findings

- The fix is a **pure refactor** — a behavior-preserving extraction. The product output of both
  state scripts (`--emit-prompt` / `--probe` JSON, terminal routing) MUST be byte-identical
  before and after; the `--test` baselines (`tests/baselines/{lazy,bug}-state-test-baseline.txt`)
  are the regression net and must stay green/unchanged.
- The natural home is the shared `lazy_core/dispatch.py`, alongside `merged_head_override` — a
  new pure predicate `coordinator_arbitrated_emission(marker, feature_id, leases_path) ->
  None | "<reason>"` returning the exemption reason (or `None`) so the caller both skips the
  guard AND emits the correct observability diagnostic from one return value. Extracting to the
  shared module ALSO removes the cross-script duplication (both scripts call one helper), not
  just the two-boolean fragmentation — the strongest anti-accretion form, and the one that gives
  the anticipated demoted-serial-rerun exemption a single one-line home.

⚖ policy: predicate placement (local-mirror vs shared) → shared `lazy_core.dispatch` helper

## Affected Area

| Component | Files | Impact |
|-----------|-------|--------|
| Merged-head guard caller prologue (feature) | `user/scripts/lazy-state.py` (~14803-14965) | Replace 2 booleans + inline AND + 2 observability `elif`s with one predicate call |
| Merged-head guard caller prologue (bug, coupled mirror) | `user/scripts/bug-state.py` (~10062-10225) | Same replacement, parity-mirrored |
| Shared dispatch helpers | `user/scripts/lazy_core/dispatch.py` (next to `merged_head_override`) | Add pure `coordinator_arbitrated_emission(...)` predicate returning the exemption reason or `None` |
| Regression net | `tests/baselines/{lazy,bug}-state-test-baseline.txt`, `tests/test_lazy_core/test_dispatch.py`, both scripts' `--test` | Baselines UNCHANGED (behavior preserved); add a `test_dispatch.py` case for the new predicate (lane / lease / neither / future-reason) |
| Parity | `user/scripts/lazy_parity_audit.py` | Coupled-pair edit — run the parity audit after |

## Open Questions

- None blocking. The demoted-serial-rerun exemption named in the brief is OUT of scope for this
  bug (it does not exist yet); this refactor's deliverable is the single home that makes adding
  it a one-line edit. If `/plan-bug` finds the third exemption is trivially addable in the same
  change, that is a scope-class call for the plan cycle, not a product fork.
