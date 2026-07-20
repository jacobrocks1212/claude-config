# Consumed Fence Dies on Re-Emit After `--cycle-begin` — Investigation Spec

> The workstation sub-subagent exemption's **consumed fence** binds its nonce at
> `--cycle-begin` to "the newest unconsumed `class==cycle` emission then present"
> (`resolve_cycle_worker_nonce`). But `/lazy-batch`'s freshness rule REQUIRES the
> orchestrator to RE-EMIT the cycle prompt if a turn boundary intervenes before the
> worker dispatch. When the re-emit lands AFTER `--cycle-begin`, the worker consumes
> a DIFFERENT emission than the fence was bound to, so `emission_consumed_by_nonce(cycle.nonce)`
> reads False for the entire cycle — the exemption never fires and every worker-composed
> test-agent/impl-agent sub-subagent dispatch is DENIED as false hardening debt. This is a
> RECURRENCE of the Round-16 shipped-exemption-mis-wiring class at the same symbol
> (`resolve_cycle_worker_nonce` / the consumed fence), uncovered because Round 16's fix (and
> its `_arm_worker_in_flight` regression test) only handle the emit-BEFORE-cycle-begin order.

**Status:** Concluded
**Severity:** P2 (degraded — the run is not hard-blocked; the worker's documented inline
fallback lets it proceed, but the structural TDD test-agent/impl-agent separation the exemption
exists to protect is nullified for the affected cycle, and each denial books a false hardening
debt that costs a full `/harden-harness` round to retire)
**Discovered:** 2026-07-16
**Placement:** docs/bugs/consumed-fence-dies-on-reemit-after-cycle-begin
**Related:**
- `docs/specs/turn-routing-enforcement/NEEDS_INPUT.md` — **decision 8** (the design fork this
  spec surfaces: how to make the operator-blessed consumed fence robust to a re-emit after
  `--cycle-begin` without weakening the integrity guard)
- `docs/bugs/_archive/dispatch-guard-denies-workstation-subsubagent-split/` — the origin bug;
  decision 4 (RESOLVED 2026-07-10) blessed the consumed-fence discriminator, implemented in
  hardening Round 16 (`e3f5702`)
- `docs/specs/turn-routing-enforcement/hardening-log/2026-07.md` — Round 16 (the mechanical
  `resolve_cycle_worker_nonce` fix whose ordering assumption this recurrence violates) and
  Round 46 (this investigation)

---

## Verified Symptoms

*(Provenance: reconstructed from the live AlgoBooth `/lazy-batch` run's per-repo state dir
`~/.claude/state/37850b6e…/` — deny ledger, prompt registry, and telemetry — relayed as a
second-hand observed-friction report from the part-8 `/execute-plan` cycle subagent. The raw
probe JSON was not captured at denial time, so the ledger/registry/telemetry ARE the primary
evidence and are quoted verbatim below.)*

1. **[VERIFIED]** Exactly ONE hand-composed sub-subagent `Agent` dispatch was denied across the
   entire multi-day run: deny-ledger `denied_sha12: 8ecb32c73a97` at `ts 1784198590`,
   `reason_head` = the canonical corrective recipe ("dispatch prompt not script-emitted this
   turn — re-run the Step 1a probe …"), `prompt_head` = "You are a TEST-AGENT for one work unit
   of an AlgoBooth feature (d8-signal-flow-viz, Phase 7, WU-2). Write ONLY a failing test file …"
   — i.e. `/execute-plan`'s TDD red-phase test-agent role. `8ecb32c73a97` matches no registry
   `prompt_sha256`. (The relayed report's framing of this as an "unregistered `@@lazy-ref`" is
   imprecise: it was a full hand-composed prompt that hit the DEFAULT corrective deny, not the
   bare-`@@lazy-ref` D-C path — confirmed by the ledger `reason_head`.)

2. **[VERIFIED]** The SAME exemption fired correctly **108 times** across the run — every one an
   `execute-plan` `worker_subdispatch: true` (pre-acked, zero debt) ledger event, including 27 for
   `d8-signal-flow-viz` itself, the last at `ts 1784197418` (`sha 6e5d9916ba79`), inside the
   part-7 `/execute-plan` cycle IMMEDIATELY preceding the denied part-8 cycle. So the exemption is
   live and working; part-8 is a single anomalous miss under otherwise-identical conditions
   (workstation, bound marker, `execute-plan` = `subagent-model: true`).

3. **[VERIFIED]** The denial falls squarely INSIDE a `sub_skill=execute-plan` cycle, so
   condition 3 of the exemption (`cycle.subagent_model is True`) held exactly as it did for the
   108 successes. Telemetry: `cycle-begin` for part-8 at `ts 1784197993` (`sub_skill:
   execute-plan, kind: real`), the worker `dispatch` at `ts 1784198002`, the denied test-agent at
   `ts 1784198590`, `cycle-end` at `ts 1784199546`. The next `cycle-begin` (`ts 1784199694`) is a
   DIFFERENT cycle (`sub_skill: mcp-test`, `subagent_model: false`) — which is why the on-disk
   cycle marker now reads `mcp-test`; it is NOT the cycle the denial belongs to.

4. **[VERIFIED]** The part-8 cycle worker emission (the one the worker's by-reference dispatch
   consumed) is registry entry `nonce 5e508da3a462…`, `class: cycle`, `consumed: True`,
   `consumed_by: toolu_01AKoxsfeXTbtmfA6NkHbpgC` — with **`emitted_at: 1784198002`**, i.e. **9
   seconds AFTER the part-8 `--cycle-begin` at `ts 1784197993`**. The prior `class==cycle`
   emission (`b4b15231ee68`, `emitted_at 1784194061`) was already consumed. So at part-8
   `--cycle-begin`, there was NO unconsumed `class==cycle` emission for `resolve_cycle_worker_nonce`
   to bind to — the worker's own emission did not exist yet.

## Reconstructed Route (divergence point)

**Divergence point:** `/lazy-batch` Step 1d `--cycle-begin` (`write_cycle_marker` →
`resolve_cycle_worker_nonce`) for the part-8 `/execute-plan` cycle → the cycle worker's mandated
TDD **test-agent** sub-subagent dispatch, DENIED by `lazy_guard.py`'s `guard()` because the
workstation sub-subagent exemption (block 2b) did not fire — its **consumed fence** (condition 4,
`emission_consumed_by_nonce(cycle["nonce"])`) read False for the whole cycle.

The exemption (blessed by decision 4, implemented Round 16) ALLOWs an unregistered
worker-composed prompt iff ALL of: (1) workstation (`not marker.cloud`); (2) marker BOUND
(`session_id is not None`); (3) active cycle marker with `subagent_model is True`; (4) **consumed
fence**: `emission_consumed_by_nonce(cycle.nonce)`. Conditions 1–3 held for part-8 (identical to
the 108 successes). Condition 4 failed.

**Why condition 4 failed — the exact mechanism:**

- `write_cycle_marker` (at `--cycle-begin`), for a `subagent_model` cycle, calls
  `resolve_cycle_worker_nonce(passed_nonce)` (`markers.py`) to bind the fence nonce. Its rule:
  keep `passed_nonce` if it is already a registered emission nonce; ELSE rebind to "the newest
  UNCONSUMED `class==cycle` registry entry"; ELSE (no unconsumed cycle emission) **preserve
  `passed_nonce` unchanged — the docstring's explicit "safe pre-fix degradation" branch.**
- At part-8 `--cycle-begin` (`ts 1784197993`) the worker's own emission (`5e508da3`) had not yet
  been registered (it was `emitted_at 1784198002`), and the prior cycle emission (`b4b15231`) was
  already consumed. So the middle branch found no unconsumed `class==cycle` entry and the function
  fell to the third branch: it returned `passed_nonce` — the fresh hex `/lazy-batch` §1d permits
  ("reuse the ref nonce when present, else any fresh hex"), which is NOT a registered emission.
- The cycle marker was therefore stamped with a fresh hex that is absent from the registry.
- The worker was then dispatched **by-reference** (ledger `dispatch_by_reference: true, nonce
  5e508da3, ts 1784198016`), consuming `5e508da3` — NOT the marker's fresh hex.
- At guard time for the test-agent, condition 4 evaluated `emission_consumed_by_nonce(fresh_hex)`
  → the nonce is not in the registry → returns False (fail-closed). Fence permanently closed for
  the cycle → exemption skipped → the test-agent fell through to `_deny_default` (`lazy_guard.py`
  §"No matching entry") → deny + false hardening debt.

**Why the 108 successes worked and part-8 did not** — the ORDER of `--emit-prompt` (cycle emission
registration) relative to `--cycle-begin`:
- Designed / normal order (108×): `--emit-prompt` registers the cycle emission → `--cycle-begin`
  (`resolve_cycle_worker_nonce` binds the fence to that unconsumed emission) → worker dispatch
  consumes it → fence reads True. `resolve_cycle_worker_nonce`'s docstring assumes exactly this:
  "`--emit-prompt` registers the cycle emission IMMEDIATELY before `--cycle-begin`."
- Part-8 order: `--cycle-begin` ran while the newest cycle emission was already consumed and the
  worker's own emission was not yet registered. `/lazy-batch`'s freshness rule (SKILL.md §1d, lines
  ~690/742: "Continuation cycles re-emit"; "a by-reference dispatch is dispatchable ONLY on the
  SAME turn its emission was registered … RE-PROBE with `--emit-prompt` in-turn and dispatch THAT
  fresh ref") REQUIRES a re-emit when a turn boundary/staleness intervenes before the actual worker
  dispatch. That re-emit (`5e508da3`) landed AFTER `--cycle-begin`, so the fence could never have
  been bound to it.

## Root Cause

**Class:** `script-defect` (the `resolve_cycle_worker_nonce` / consumed-fence binding is
under-robust) — but the durable FIX touches the operator-owned integrity-guard allow computation
(the consumed fence's security window, decision 4), so the RESOLUTION is a NEEDS_INPUT design fork
(decision 8), not a second unilateral re-wire.

The consumed fence snapshots a SINGLE nonce at `--cycle-begin` and requires THAT nonce to be the
one the worker later consumes. This couples the fence's correctness to (a) the orchestrator's
`--emit-prompt`↔`--cycle-begin` ordering and (b) nonce identity between the cycle-begin snapshot
and the worker's actual (possibly re-emitted) dispatch. The freshness rule legitimately breaks
both couplings via a re-emit after `--cycle-begin`. A **write-side-only** fix is IMPOSSIBLE: at
`--cycle-begin` the worker's eventual (re-)emission nonce does not yet exist, so no amount of
smarter binding at that moment can point the fence at it. The robust fix must move the fence's
"worker in flight" determination to information available at GUARD time (re-derive), or add a
re-bind at re-emit/dispatch time — either of which modifies the operator-blessed fence semantics.

**Recurrence classification (over-fit signal 2):** this is the 2nd occurrence of the
shipped-exemption-mis-wiring class at the same symbol (`resolve_cycle_worker_nonce` / the consumed
fence). Round 16 fixed the fresh-hex-at-cycle-begin case (emission already present); this fixes the
re-emit-after-cycle-begin case (emission not yet present). The two share a root: the fence binds a
snapshot nonce at cycle-begin that may not match what the worker consumes. Round 16's regression
test `_arm_worker_in_flight` (`test_hooks.py`) hard-codes the emit-BEFORE-`write_cycle_marker`
order (register → consume → write marker), masking the re-emit case exactly as the pre-Round-16
test masked the fresh-hex case (`cycle.nonce == emission.nonce`). Any fix MUST add a regression test
that registers the consumed worker emission AFTER `write_cycle_marker`.

## Verified Symptom vs. NON-symptom (scope fence)

- IN scope: a `subagent_model` cycle whose worker emission is (re-)registered AFTER `--cycle-begin`
  (the freshness-rule re-emit, or any `--cycle-begin`-before-`--emit-prompt` ordering) → fence
  bound to a nonce the worker never consumes → exemption dead → sub-subagent denied.
- OUT of scope: the pre-dispatch window (worker not yet dispatched → fence correctly closed → deny
  is CORRECT); a genuine orchestrator-improvised unregistered cycle prompt (must STILL be denied —
  any fix must preserve this). The security window decision 4 blessed is NOT to be weakened.

## Fix Scope (for `/plan-bug` after operator resolves decision 8)

Operator-owned via NEEDS_INPUT decision 8. Candidate approaches (detailed in decision 8):
1. **Re-derive the fence at guard time** — condition 4 passes iff the NEWEST `class==cycle` registry
   emission is consumed AND its `emitted_at >= cycle.started_at`. Robust to re-emit; preserves the
   pre-dispatch-window closure (before the worker dispatch, no cycle emission registered-since-begin
   is consumed). Changes `lazy_guard.py` §2b condition 4 — the operator-owned surface.
2. **Re-bind the fence nonce at re-emit/dispatch time** rather than only at `--cycle-begin`.
3. **Enforce/keep the emit-before-cycle-begin ordering** and make a violation self-announcing.

Measurable target signal for the eventual fix: the count of hand-composed sub-subagent
`denied_sha12` entries whose `prompt_head` matches a sub-subagent role (`TEST-AGENT` /
`TEST-WRITING` / `IMPL-AGENT` / phase-author) while a `subagent_model` cycle is in flight →
expected to decrease to 0 (ledger-event vocabulary: `event:gate-refusal`).
