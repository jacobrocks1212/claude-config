# Step-10 → mcp-test re-route on uncovered non-exempt verification rows — Investigation Spec

> A completion cycle that reaches Step 10 with `VALIDATED.md` present but a matrix-incomplete
> PHASES.md unconditionally dispatches `__mark_complete__`, which the completion-coherence gate
> then refuses — with NO re-route back to `mcp-test` to finish (or author) the missing coverage.
> This produces a VALIDATED→refuse→coherence-recovery→VALIDATED oscillation (decision 2) and
> strands newly-discovered-at-completion coverage (decision 6).

**Status:** Fixed
**Severity:** P2
**Discovered:** 2026-07-18
**Placement:** docs/bugs/decision-2-6-uncovered-row-reroute-to-mcp-test
**Related:** `docs/specs/turn-routing-enforcement/NEEDS_INPUT.md` decisions **2** (partial-VALIDATED oscillation, harden Round 45), **6** (corrective-coverage dispatch, harden Round 22), and **5** (per-row host-defer marker); the interacting sibling bug `docs/bugs/feature-operator-host-defer-not-honored-over-validated/` (decision 5, **Concluded, unimplemented**); the completion-coherence machinery in `docs/features/.../completion-coherence-gate-reconciliation`.

<!-- Status lifecycle:
  - Investigating → active investigation; bug-state.py routes to /spec-bug.
  - Concluded     → root cause traced surface→source, fix site + scope understood; ready for /plan-bug.
-->

---

## Verified Symptoms

<!-- Both symptoms were confirmed by the operator (Jacob) in the interactive AskUserQuestion
     round that RESOLVED turn-routing-enforcement decisions 2 and 6 on 2026-07-18. The
     resolution text (option-1 / option-2 accepted) IS the operator confirmation that the
     observed behavior is real and unwanted. -->

1. **[VERIFIED]** *Partial-VALIDATED oscillation (decision 2).* A Step-9 `/mcp-test` cycle that
   ran a legitimate SUBSET of scenarios (e.g. after fixing a bug it found) writes a partial
   `MCP_TEST_RESULTS.md` (`result: all-passing`, `pass==total` for the subset). That mints
   `VALIDATED.md`, so routing treats validation as DONE and dispatches `__mark_complete__` — but
   the completion-coherence gate REFUSES because most PHASES `Runtime Verification` rows were
   never exercised. `coherence-recovery` ticks only the evidenced rows and re-opens phases to
   In-progress, yet the next probe STILL routes to `__mark_complete__` (VALIDATED.md still
   present) → refuse → loop. Observed live on AlgoBooth `algorithmic-fill-buffer`;
   `step_repeat_count` reached the oscillation tripwire (3); operator broke it MANUALLY by
   dropping the marker and running a comprehensive validation cycle. — *confirmed via the
   decision-2 resolution.*

2. **[VERIFIED]** *Newly-discovered-coverage stranding (decision 6).* When Gate 1 / Gate 2 at
   Step 10 reveal a genuinely-untested-but-MCP-testable-HERE behavior needing a NEW scenario
   authored + run (managed-llm-credits Purchase-CTA `ui_action` + auto-refill toggle-persistence),
   there is NO legitimate dispatch path: `coherence-recovery` correctly refuses implementation
   work, a hand-composed mcp-test prompt is guard-DENIED (no registered emission), and the state
   machine will not re-route Step 10 → mcp-test while `VALIDATED.md` + `MCP_TEST_RESULTS.md`
   already exist. The operator had to choose between deferring or a manual out-of-band cycle. —
   *confirmed via the decision-6 resolution.*

3. **[REPORTED]** The two symptoms share ONE mechanism — an unchecked, non-exempt,
   non-host-deferred verification row that the recorded evidence does not cover, with `VALIDATED.md`
   present at Step 10 — which is why the operator resolved both to ONE shared predicate.

## Reproduction Steps

<!-- Deterministic state-machine reproduction — no live app needed; drive lazy-state.py against a
     fixture feature dir. -->

1. Create a feature dir with a PHASES.md whose phases are all `Status: Complete` EXCEPT ≥1
   unchecked `- [ ]` runtime-verification row that carries the verification-only marker (so
   `remaining_unchecked_are_verification_only` returns True and routing falls through to the MCP
   gate), and that is NOT observation-gap-exempt and NOT host-deferred.
2. Place a `VALIDATED.md` (`kind: validated`) and a `MCP_TEST_RESULTS.md` (`result: all-passing`,
   `pass_count == total_count`, `validated_commit == HEAD`) that together certify only a SUBSET of
   those rows.
3. Run `python3 user/scripts/lazy-state.py --repo-root <fixture> --feature-id <id>` (or `--probe`).
4. **Observed:** the probe returns `current_step="Step 10: mark complete"`, `sub_skill="__mark_complete__"`.
   Applying it (`--apply-pseudo __mark_complete__`) REFUSES on the unchecked verification rows;
   after a `coherence-recovery` reconcile (ticks only evidenced rows, re-opens phases In-progress),
   the very next probe returns `Step 10: mark complete → __mark_complete__` AGAIN.

**Expected:** at Step 10, before dispatching `__mark_complete__`, if an In-progress phases state has
unchecked, non-exempt, non-host-deferred runtime-verification rows the recorded evidence does not
cover, the probe re-routes to `mcp-test` to finish (or author) the matrix, and TERMINATES (no
re-trigger once every such row is covered / host-deferred / exempt).
**Actual:** the probe unconditionally dispatches `__mark_complete__`, which refuses → oscillation
(symptom 1) / stranded coverage (symptom 2).
**Consistency:** always, whenever `VALIDATED.md` is present at Step 10 over a matrix-incomplete
PHASES.md with an uncovered non-exempt non-host-deferred verification row.

## Evidence Collected

### Source Code (serving-path trace — `traced`, fix-site-on-path)

The symptom surface is the orchestrator observing `Step 10: mark complete` re-dispatching
`__mark_complete__` (oscillation) / a stranded coverage gap. Serving path, surface → source:

```
surface: probe returns current_step="Step 10: mark complete", sub_skill="__mark_complete__"
  → entry gate: entry_ok = validated_file.exists() or (cloud and deferred_file.exists())   lazy-state.py:4034   ← VALIDATED.md present ⇒ True
  → unconditional dispatch: return _state(... sub_skill="__mark_complete__" ...)            lazy-state.py:4087-4092   ← FIX SITE (no re-route branch here)
  → __mark_complete__ → lazy_core.apply_pseudo → _phase_completion_plan completion gate      lazy_core/pseudo.py → _phase_completion_plan (lazy_core.py:~2740)   ← REFUSES on unchecked non-exempt verification rows
  → orchestrator routes coherence-recovery: ticks only evidenced rows, re-opens In-progress   (VALIDATED.md untouched)
  → next probe: In-progress + only-verification-rows-unchecked ⇒ remaining_unchecked_are_verification_only(True)   docmodel.py:1183   ← falls through Step 9 (VALIDATED.md present) back to the entry gate ⇒ LOOP
```

- **Fix-site-on-path:** the routing decision at `lazy-state.py:4087` is the exact node that
  produces the surface (the `__mark_complete__` dispatch). Inserting the re-route branch
  immediately before it changes a value (`sub_skill`) that is READ on the symptom's serving path —
  not a related-but-off-path value. Cause label: **`traced`** (not `asserted`).
- **Why the loop is stable, not transient:** `coherence-recovery` re-opens phases to In-progress
  but the only remaining unchecked rows are verification rows, so `remaining_unchecked_are_verification_only`
  (`docmodel.py:1183`) keeps returning True and routing keeps falling through Step 9 (VALIDATED.md
  present, no re-run) back to the Step-10 entry gate. Nothing in the loop ever finishes the matrix.
- **Reusable predicate ingredients already on disk** (the re-route should COMPOSE these, not
  re-implement): `remaining_unchecked_are_verification_only` (`docmodel.py:1183`),
  `observation_gap_promotable` (`gates.py:608`, the exempt check), `autotick_verification_rows`
  (`gates.py:781`, which ticks exactly the evidence-covered rows — so an unchecked verification
  row is, by construction, one the recorded evidence did NOT cover).

### Git History
No regression — this is a MISSING branch, not a broken one. The Step-9→Step-10 routing has always
dispatched `__mark_complete__` unconditionally once `VALIDATED.md` exists; the partial-results
contract (a `/mcp-test` cycle legitimately validating a subset, per its D5 discipline) is what
first made a matrix-incomplete `VALIDATED.md` reachable, exposing the gap.

### Related Documentation
- `docs/specs/turn-routing-enforcement/NEEDS_INPUT.md` decisions 2, 5, 6 — the operator resolutions
  (all RESOLVED 2026-07-18) that scope this fix. Decision 2 accepts the conservative predicate form;
  decision 6 accepts the Step-10→mcp-test re-route (option 2, no new dispatch class); both mandate
  ONE shared predicate that must TERMINATE.
- `docs/bugs/feature-operator-host-defer-not-honored-over-validated/` (decision 5, **Concluded**) —
  introduces the per-row `<!-- requires-host: <cap> -->` marker the "non-host-deferred" predicate
  clause depends on. **Not yet implemented** → a hard dependency for termination on host-blocked
  rows (see Open Questions).

## Theories

### Theory 1: Missing Step-10 re-route branch (the whole cause)
- **Hypothesis:** the state machine lacks a branch, between the Step-10 entry gate and the
  `__mark_complete__` dispatch, that routes back to `mcp-test` when uncovered non-exempt
  non-host-deferred verification rows remain. Absent it, `VALIDATED.md` unconditionally forces the
  completion route, which the coherence gate refuses.
- **Supporting evidence:** the serving-path trace above (`lazy-state.py:4034`→`4087` has no such
  branch); two independent hardening rounds (45, 22) hit it on two features across two symptoms.
- **Contradicting evidence:** none.
- **Status:** **Confirmed** (traced).

## Proven Findings

- **Root cause (traced):** `lazy-state.py` dispatches `__mark_complete__` unconditionally at line
  4087 whenever `VALIDATED.md` is present at Step 10, with no coverage-completeness check. A
  matrix-incomplete `VALIDATED.md` (a legitimate partial-results run) therefore forces the
  completion route, which `_phase_completion_plan` refuses on the unchecked verification rows,
  producing the oscillation (symptom 1) and stranding newly-discovered coverage (symptom 2).
- **Fix shape (operator-locked):** insert a SHARED predicate immediately before the line-4087
  dispatch — "at Step 10, with `VALIDATED.md` present, if a non-Superseded phase has an unchecked
  runtime-verification row that is (a) NOT observation-gap-exempt and (b) NOT host-deferred
  (`<!-- requires-host: <cap> -->`, decision 5) and (c) not covered by recorded evidence (i.e. still
  unchecked after `autotick_verification_rows`), route `sub_skill="mcp-test"` to finish/author the
  matrix instead of `__mark_complete__`." Conservative form accepted: one redundant mcp-test pass
  on a genuinely-complete-but-unticked matrix is tolerable. **Termination is the load-bearing
  contract** — the predicate must NOT re-trigger on already-exempt or host-deferred rows, and every
  uncovered row must resolve to covered/ticked, host-deferred-marked, or exempt (else mcp-test
  writes BLOCKED/NEEDS_INPUT, never an infinite loop).

## Affected Area

| Component | Files | Impact |
|-----------|-------|--------|
| Step-10 routing | `user/scripts/lazy-state.py` (~4034–4092, the entry gate → `__mark_complete__` dispatch) | Insert the shared re-route branch before line 4087. |
| Shared predicate | `user/scripts/lazy_core/` (new helper composing `remaining_unchecked_are_verification_only` @ `docmodel.py:1183`, `observation_gap_promotable` @ `gates.py:608`, `autotick_verification_rows` @ `gates.py:781`, and decision-5's per-row host-defer recognizer) | New pure helper; ONE predicate serving both symptoms. |
| Host-deferred clause | `<!-- requires-host: <cap> -->` per-row marker | Dependency on the decision-5 sibling bug (Concluded, unimplemented) — its recognizer is the "non-host-deferred" clause. |
| Coupled pipeline | `user/scripts/bug-state.py` | Bugs also run through the Step-9 mcp-test / VALIDATED gate; verify whether the re-route is owed as a coupled-pair mirror or is a justified feature-axis-only divergence (`lazy_parity_audit.py`). |
| Regression net | `lazy-state.py --test` (+ `bug-state.py --test` if mirrored) | New fixtures: (a) uncovered row + VALIDATED.md ⇒ re-route to mcp-test; (b) all rows covered/host-deferred/exempt ⇒ falls through to `__mark_complete__` (TERMINATION); (c) host-deferred / observation-gap rows never re-trigger. |

## Open Questions

- **Sequencing vs. decision 5 (hard dependency).** The "non-host-deferred" clause needs decision
  5's per-row `<!-- requires-host: <cap> -->` marker recognizer, which does not exist yet (sibling
  bug `feature-operator-host-defer-not-honored-over-validated` is Concluded but unimplemented).
  Without it, a genuinely host-blocked row is "non-host-deferred" forever → the re-route would
  loop mcp-test — violating the termination contract. `/plan-bug` should either declare a queue
  `deps` on the sibling bug, or land the host-defer recognizer as a phase of THIS bug. (⚖ recorded
  here rather than descoped silently — it is a dependency to sequence, not a product fork.)
- **`bug-state.py` coupling.** Confirm at plan time whether the Step-10 re-route is a coupled-pair
  mirror or a justified feature-axis-only divergence (bugs reach the same mcp-test/VALIDATED gate).
- **Coverage-precision dial.** The accepted conservative form treats "still unchecked after
  autotick" as "evidence does not cover." A future tightening could compute precise row↔scenario
  coverage; out of scope for this fix (operator accepted the redundant-pass tradeoff).

## Locked Decisions

1. **Where the per-row host-defer recognizer lives** (`NEEDS_INPUT.md`, operator-accepted
   2026-07-19, recorded via `bug-state.py --record-decision`): **land a minimal per-row
   `<!-- requires-host: <cap> -->` recognizer as a phase of THIS bug** — do NOT declare a hard
   queue `deps` on `feature-operator-host-defer-not-honored-over-validated`, and do NOT ship the
   re-route without clause (b). Locked for `/plan-bug`: all three clauses of the operator-locked
   fix shape (non-observation-gap-exempt, non-host-deferred, not evidence-covered) must be honored
   in one self-contained cycle.
