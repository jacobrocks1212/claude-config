# Operator Per-Feature Host-Defer Not Machine-Enforced Over a VALIDATED Feature — Investigation Spec

> An operator who answers a completion-integrity `NEEDS_INPUT.md` halt with "defer the
> whole feature to a capability-bearing host" has NO machine-honored representation for that
> decision on the FEATURE pipeline. The apply-resolution subagent authored
> `docs/features/managed-llm-credits/DEFERRED_REQUIRES_HOST.md`
> (`missing_capabilities: [credits-proxy-host, live-oauth-host]`, `deferred_by: operator`),
> but it drives NO state-machine skip for two independent reasons: (1) both capability ids
> are absent from the closed `lazy_core.hostcaps._HOST_CAPABILITY_REGISTRY`, so naming them
> in a `requires_host:` set would trip the unknown-capability BLOCKED.md fail-fast, not a
> defer; and (2) the host-capability defer branch requires `not VALIDATED.md`, but this
> feature carries a `VALIDATED.md` (`result: validated-modulo-observation-gaps`). The
> deferral is therefore documentation-only: the next probe re-routes to `__mark_complete__`,
> the mechanical `--apply-pseudo` completion gate re-refuses on the 4 unchecked
> Runtime-Verification rows, `coherence-recovery` reconciles nothing (the rows never ran on
> this host), and the loop re-writes `NEEDS_INPUT.md` — re-asking the operator a decision
> they already made.

**Status:** Concluded
**Severity:** P2 (degraded — the run is not hard-blocked; the operator can defer by hand every
cycle, and Round 44's honest-stuck terminal keeps the loop from spinning silently. But the
operator's ALREADY-MADE "defer whole feature" decision is discarded on every subsequent probe,
so the feature never reaches a clean Deferred/host-saturated terminal — it re-asks indefinitely)
**Discovered:** 2026-07-16
**Placement:** docs/bugs/feature-operator-host-defer-not-honored-over-validated
**Related:**
- `docs/specs/turn-routing-enforcement/NEEDS_INPUT.md` — **decision 9** (the design fork this
  spec surfaces), tightly coupled to the OPEN **decisions #5** (per-row host-capability deferral
  marker) and **#6** (corrective-coverage dispatch) — all three name the SAME managed-llm-credits
  rows (Phase 1 live-OAuth JWT, Phase 4 credits-proxy reachability, Phase 7 Purchase CTA, Phase 8
  auto-refill toggle persistence).
- `docs/bugs/coherence-recovery-loop-no-terminal-on-unrunnable-verification-rows/` — the prior
  round (hardening Round 44) that gave this exact loop a `NEEDS_INPUT.md` terminal. This spec is
  the NEXT layer: the terminal exists, but the operator's RESOLUTION of it is not machine-honored.
- `docs/specs/host-capability-declaration-for-gated-features/` — the host-capability axis
  (`requires_host:` parse, closed registry, `DEFERRED_REQUIRES_HOST.md` writer + skip branch) this
  friction stresses.
- `docs/specs/turn-routing-enforcement/hardening-log/2026-07.md` — Round 44 (the terminal) and
  Round 47 (this investigation).

---

## Verified Symptoms

*(Provenance: relayed as a blocking observed-friction report from the live AlgoBooth
`/lazy-batch` run for `managed-llm-credits`. No probe JSON was captured at the friction point —
it is an orchestrator-observed mid-run harness gap — so the primary evidence is the on-disk
harness code paths, quoted with file+line below, which DETERMINISTICALLY produce the reported
behavior given the described on-disk state.)*

1. **[VERIFIED — code-path]** The host-capability defer branch cannot fire for this feature.
   `lazy-state.py:2087-2091` gates the whole capability-miss defer on
   `host_validated = (spec_path / "VALIDATED.md").exists()` → `if not host_validated and
   _phases_effectively_complete(spec_path):`. With `VALIDATED.md` present the branch is skipped
   entirely, so no `DEFERRED_REQUIRES_HOST.md` is (re)written by the machine and no
   host-capability-saturated skip/terminal is produced. The feature falls through to Step 9.

2. **[VERIFIED — code-path]** With `VALIDATED.md` present, Step 9 (`lazy-state.py:3489`,
   `entry_ok = validated_file.exists()`, line 3727) routes straight to Step 10
   `__mark_complete__`. Note that the Step 9-pre re-open guard at `lazy-state.py:3520` checks
   ONLY `DEFERRED_REQUIRES_DEVICE.md`, NOT `DEFERRED_REQUIRES_HOST.md` — the host sentinel is
   invisible to the completion path.

3. **[VERIFIED — code-path]** The two operator-named capability ids are unregistered. The closed
   registry `lazy_core.hostcaps._HOST_CAPABILITY_REGISTRY` (`hostcaps.py:74-110`) contains only
   `real-audio-device`, `zimtohrli-toolchain`, `gpu`, `midi-controller`, `link-multi-peer`,
   `non-windows-host`. `credits-proxy-host` and `live-oauth-host` are absent, so
   `unknown_capability_ids({credits-proxy-host, live-oauth-host})` (`hostcaps.py:213-220`) returns
   both, and the Phase-4 fail-fast (`lazy-state.py:2045-2078`) would write a
   `blocker_kind: unknown-host-capability` BLOCKED.md — a HARD blocked terminal, the OPPOSITE of a
   clean defer. The operator literally cannot express "defer for credits-proxy / live-oauth" via
   `requires_host:` today.

4. **[VERIFIED — code-path]** `DEFERRED_REQUIRES_HOST.md` is a WRITE-ONLY sentinel on the routing
   side. A repo-wide grep shows its only consumers are the writer
   (`lazy_core.hostcaps.write_deferred_requires_host`), the sentinel enumeration in
   `docmodel.py:2042` (recognized as a valid re-open sentinel for hygiene/lint), and test
   fixtures. NOTHING READS a pre-existing `DEFERRED_REQUIRES_HOST.md` to DRIVE a skip — the
   Step-2 branch re-derives `missing = required_host - host.present` from scratch each probe
   (`lazy-state.py:2092-2094`). So an operator-authored sentinel has no effect on routing.

5. **[VERIFIED — code-path]** The completion gate (`lazy_core.gates.verify_ledger`,
   `gates.py:1253+`) never consults `DEFERRED_REQUIRES_HOST.md` (grep of `gates.py` for the
   sentinel returns zero hits). Its `deliverables_done` check refuses while non-exempt unchecked
   rows remain (`gates.py:1520-1533`). Combined with Round 44's honest-stuck terminal, the routed
   `coherence-recovery` cycle reconciles 0 rows (they never ran on THIS host) and re-writes
   `NEEDS_INPUT.md` — the observed re-ask loop.

6. **[VERIFIED — design intent]** The feature pipeline DELIBERATELY has NO operator-defer branch.
   `lazy-state.py:353-356` documents: "the feature side … has NO operator-DEFERRED.md branch
   (bug-pipeline-only — JUSTIFIED divergence)." `bug-state.py:980-988` records the mirror-side
   parity note: the capability-MISS defer is "queue-selection/curation-shaped on the feature side"
   and NOT mirrored to the bug side. So the apply-resolution subagent invoked an operator-defer
   affordance that structurally does not exist on the feature side — it authored a sentinel the
   feature state machine has no contract to honor.

---

## Root Cause

**Classification: `missing-contract`.** The feature pipeline has no contract for an
operator-directed per-feature host-deferral of runtime-verification rows when (a) the required
host capability is not in the closed registry AND/OR (b) a `VALIDATED.md`
(`validated-modulo-observation-gaps`) already exists. Three structural facts compose the gap:

- **The closed registry is capability-only and probe-shaped.** Every registered id maps (or
  fails-closed) to a deterministic host self-probe (env/binary/platform, or the constant-False
  `link-multi-peer` placeholder). `credits-proxy-host` and `live-oauth-host` are
  SERVICE-REACHABILITY / configuration capabilities with no obvious deterministic self-probe on a
  workstation — registering them is not a mechanical config edit; it requires deciding their probe
  semantics (likely constant-False no-self-probe, like `link-multi-peer`, so they re-open only
  under an explicit operator signal).

- **The host-defer branch is `not VALIDATED.md`-gated by design.** The `validated-modulo-
  observation-gaps` VALIDATED.md is the intended output of the observation-gap path — it attests
  the MCP-driveable scope passed while some rows remain host-unobservable. That is EXACTLY the
  state where an operator wants to host-defer the residual rows, yet it is the exact state the
  defer branch excludes.

- **Honoring the deferral touches the completion-integrity gate.** For the operator's decision to
  actually STOP the loop, either the completion gate must treat the host-deferred rows as
  legitimately-deferred (NOT blocking, NOT false-green ticked), or the router must divert the
  feature to a Deferred/host-saturated terminal before `__mark_complete__`. Both change
  gate/authority semantics — precisely the class the hardening prohibitions (#2: never weaken a
  gate) reserve for the operator.

This is NOT a script bug (every cited path behaves as written and intended); it is a genuinely
novel situation the harness was not designed for: an OPERATOR per-feature host-defer over a
validated-modulo feature naming UNREGISTERED capabilities. It is adjacent to — but distinct from —
open decisions #5 (per-ROW host-capability marker) and #6 (corrective-coverage dispatch): those
concern how the pipeline itself finishes/defers the rows; THIS concerns honoring the operator's
explicit "defer the whole feature" answer without a false-green and without a registry fail-fast.

**Recurrence:** this is the (at least) 3rd distinct harness round spent on the
managed-llm-credits completion honest-stuck class — Round 22 surfaced decisions #5/#6 for these
same four rows; Round 44 added the loop's `NEEDS_INPUT.md` terminal; this round exposes that the
terminal's operator RESOLUTION has no machine-honored path. Over-fit signal 2 (class recurred ≥2 at
the same locus) is met; the durable resolution is operator-owned and surfaced as decision 9.

---

## Fix Scope (proposed — operator-owned, surfaced in NEEDS_INPUT decision 9)

The fix is a contract/authority/gate-semantics fork, so no autonomous mechanical change is made
(Prohibition #2). Decision 9 surfaces the options:

1. **Register the two capability ids as constant-False no-self-probe capabilities** (mirroring
   `link-multi-peer`), AND relax the host-defer branch to honor an operator-authored
   `DEFERRED_REQUIRES_HOST.md` even when a `validated-modulo-observation-gaps` VALIDATED.md is
   present — routing the feature to the host-capability-saturated (Deferred) terminal instead of
   `__mark_complete__`. Requires the completion path (Step 9-pre and/or `verify_ledger`) to
   recognize the host sentinel as a legitimate deferral.

2. **A general operator per-feature host-defer of specific verification ROWS** — the whole-feature
   analog of decision #5's per-row marker, honoring the operator's row-scoped deferral so the
   feature completes-modulo-deferral on the validated scope without ticking (no false-green) and
   without a registry fail-fast for un-probeable service capabilities.

3. **Add an operator-DEFERRED authority branch to the FEATURE pipeline** (the affordance
   `lazy-state.py:353-356` currently reserves to the bug pipeline), scoped to reading an
   operator-authored `DEFERRED_REQUIRES_HOST.md` (`deferred_by: operator`) as a skip driver.

Each option changes gate/authority semantics and interacts with decisions #5/#6; the operator owns
the choice and the load-bearing details (probe semantics for un-probeable service capabilities;
whether an operator deferral may override a completion-gate refusal; the false-green guard).

## Explicitly Out of Scope

- Any autonomous change to `verify_ledger` / `apply_pseudo` completion strictness (Prohibition #2).
- Registering `credits-proxy-host` / `live-oauth-host` without deciding their probe semantics.
- The target repo's source (managed-llm-credits SPEC/PHASES/production code) — harness-only.
