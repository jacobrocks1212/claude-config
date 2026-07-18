# /lazy-batch has no clean operator-authorized mid-run budget or park controls

**Status:** Fixed
**Discovered:** 2026-07-16 (operator-directed observed-friction, AlgoBooth `/lazy-batch` run; the operator approved extending `max_cycles` 10→20 mid-run and there was no clean path)
**Fixed:** 2026-07-18
**Fix commit:** cb940efb
**Related:** `docs/specs/turn-routing-enforcement/` (hardening stage + `--operator-authorized` authorization discipline + the run marker); `docs/specs/turn-routing-enforcement/hardening-log/2026-07.md`; coupled pair `lazy-batch` ↔ `lazy-bug-batch` (+ `lazy-batch-cloud`).

## Summary

Two operating-mode parameters of a live `/lazy-batch(-cloud)` / `/lazy-bug-batch` run — the
whole-run cycle budget (`max_cycles`) and park mode (`--park` / `--park-provisional`) — are
fixed at invocation time (Step 0) with **no first-class operator-authorized mechanism to change
them mid-run**. The `Standing-directive echo-back protocol` (lazy-batch/SKILL.md Deliverable C)
already RECOGNIZES both operator intents — "(a) Budget change" and the park toggle — but there
is no atomic, marker-consistent way to ENACT either.

1. **MID-RUN BUDGET CHANGE — no clean path.** `--run-start --max-cycles 20` REFUSES against an
   active marker (the double-walker clobber guard `refuse_run_start_clobber`:
   *"REFUSED: would CLOBBER an ACTIVE run marker … with NO checkpoint waiting"*).
   `--run-end` + `--run-start` fires the heavy run-end flush (efficacy / incident / canary / KPI
   + `dev:kill` + commit) AND semantically ENDS the run. The only workaround is passing
   `--max-cycles N` to each probe — but that is **cosmetic**: the header `[fwd/N]` reads
   `args.max_cycles` (`lazy-state.py` ~13519 / `bug-state.py` ~9134
   `format_cycle_header(..., max_cycles=args.max_cycles, ...)`) while the MARKER's stored
   `max_cycles` stays stale, and the per-feature budget guard reads the STALE marker value
   (`markers.py` ~1801 `_bg_max_cycles = int((_bg_marker or {}).get("max_cycles", 0) or 0)`).
   So the header, the Step-1c cap the orchestrator enforces, and the persisted marker DIVERGE.

2. **MID-RUN PARK TOGGLE — impossible.** `--park` (arms both `--park-needs-input` and
   `--park-blocked`; lazy-batch/SKILL.md Step 1a line ~415) and `--park-provisional` are parsed
   ONLY at invocation (Step 0). The probe passes `park_needs_input=args.park_needs_input` etc.
   into `compute_state` — these values live NOWHERE in the marker, so there is no run-scoped
   state an operator can flip mid-run and no field the orchestrator can read each cycle. Park
   mode cannot be turned on or off during a live run.

## Verified symptom / reconstruction

- **Route.** Operator, mid-run, approves "extend to 20 cycles". Orchestrator (Deliverable-C
  echo-back) confirms the intent but has no enactment command:
  - `lazy-state.py --run-start --max-cycles 20` → `refuse_run_start_clobber("feature")` REFUSES
    (active marker, no checkpoint) — exit non-zero, zero side effects. (`lazy-state.py` ~12425.)
  - `--run-end` then `--run-start` → the `--run-end` path runs the full flush + `dev:kill` +
    commit and ENDS the run (a checkpoint is not what the operator asked for).
  - passing `--max-cycles 20` to each subsequent probe → header shows `[fwd/20]` but
    `read_run_marker()["max_cycles"]` is still `10`; the budget guard and any marker consumer
    read `10`.
- **Divergence point.** Deliverable-C recognizes the operator's budget/park intent but the
  harness offers no atomic, marker-updating command to enact it. The operator's authorization
  (`--operator-authorized`, the exact discipline already used for `--run-end --reason
  checkpoint`) has no budget/park counterpart.
- **Corroborating precedent.** `--reassert-owner` (`lazy-state.py` ~13119 / `bug-state.py`
  ~8759) is an existing orchestrator-only, `refuse_if_cycle_active`-gated CLI action that
  mutates the SHARED marker in place via a `lazy_core` helper and echoes JSON. It is the exact
  shape a `--set-max-cycles` / `--set-park` action should take, with `--operator-authorized`
  added on top (parallel to the `--run-end` checkpoint gate).

## Root cause

**Class: `missing-contract`** (a legitimately novel operating-mode change — mid-run — that has
no current CLI action or marker field). Two coupled gaps:

- `max_cycles` IS persisted in the marker (`write_run_marker`, `markers.py` ~745) but there is
  **no in-place mutator** and the header/budget consumers read `args.max_cycles`, not the
  marker — so the marker was never the authoritative live budget.
- park mode is **not persisted at all** — `park_needs_input` / `park_blocked` /
  `park_provisional` are pure invocation args threaded per probe, so there is no run-scoped
  toggle surface.

## Fix scope (mechanical — operator-directed design, 2026-07-16)

Mirror the existing `--reassert-owner` / `--operator-authorized` disciplines; keep the coupled
trio (`lazy-batch` / `lazy-bug-batch` / `lazy-batch-cloud`) in lockstep.

1. **Marker schema (`lazy_core/markers.py`).** `write_run_marker` gains
   `park_needs_input` / `park_blocked` / `park_provisional` (bool, default `False`) — seeded at
   `--run-start` from the invocation flags; classified `RUN_FRESH_FIELDS` (re-supplied at
   run-start, like `max_cycles`). Two in-place mutators, `_atomic_write` like
   `bind_marker_session` / `reassert_marker_owner`:
   - `set_marker_max_cycles(new_max)` — update the active marker's `max_cycles`; no clobber, no
     restart, no run-end flush.
   - `set_marker_park(needs_input, blocked, provisional)` — update the park fields, enforcing
     the standing invariant *`park_provisional` requires `park_needs_input`* (refuse an
     inconsistent result; zero writes on refusal).
2. **CLI actions (both state scripts, coupled-pair mirror).**
   - `--set-max-cycles N --operator-authorized` — `refuse_if_cycle_active` FIRST, require
     `--operator-authorized`, require an active marker, mutate, echo
     `{max_cycles, prior_max_cycles, max_cycles_updated}`.
   - `--set-park on|off --operator-authorized` — toggles BOTH `park_needs_input` and
     `park_blocked` (the `--park` umbrella); `off` also clears `park_provisional`.
   - `--set-park-provisional on|off --operator-authorized` — toggles `park_provisional`;
     `on` requires park already on (else refuse, echoing the invariant).
   All three refuse without `--operator-authorized` (parallel to the checkpoint gate).
3. **Probe read (both scripts).** When a NEW-schema marker is present it is AUTHORITATIVE for
   park (marker fields drive `compute_state` / `emit_cycle_prompt`); legacy markers lacking the
   fields and the no-marker path fall back to the invocation args (byte-identical back-compat).
   The header folds `max_cycles` from the marker when present (`fold_max_cycles`) so the
   `--set-max-cycles` update is reflected immediately without re-passing `--max-cycles`. The
   effective park state is surfaced in the probe JSON (`park_active`) when a marker is present.
4. **SKILL prose (coupled trio).** Document the new mid-run enactment commands in the
   Standing-directive echo-back protocol: after the echo-back confirmation, the orchestrator
   ENACTS the budget/park change atomically via the new `--set-*` CLI (marker is now the
   authoritative live budget/park surface).
5. **Regression tests** (`tests/test_lazy_core/test_markers.py`) for the schema fields,
   partition classification, both mutators (incl. the invariant refusal), and the max_cycles
   fold; CLI-level coverage in the state-script smoke suites.

## Measurable target signal

The friction's own recurrence event is a `gate-refusal` — the clobber-guard REFUSAL an
operator's mid-run budget change currently triggers (`--run-start` against an active marker).
With a first-class `--set-max-cycles` the operator never routes a budget change through
`--run-start`, so that refusal should stop recurring. Target: `event:gate-refusal`,
expected-direction `decrease`.
