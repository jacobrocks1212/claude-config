# Bug: a feature-level VALIDATED.md + un-canonically-marked (shim) verification rows deadlocks __mark_complete__ with no forward route to mcp-test

**Status:** Fixed
**Severity:** P2 (the feature is stuck in a `__mark_complete__` → refuse →
coherence-recovery-can't-fix loop with NO state-machine route back to the mcp-test that would
certify the phase; the run must be stopped and the feature deferred by hand)
**Discovered:** 2026-07-21
**Fixed:** 2026-07-21
**Fix commit:** 59fbdb67
**Reported via:** `/harden-harness` observed-friction dispatch (2026-07-21, item in flight
`waveform-visualization`, AlgoBooth `/lazy-batch`)
**Root-cause class:** `script-defect` — a walk divergence between the completion-coherence gate and
the mcp-test re-route predicate on un-canonically-marked ("shim") Runtime-Verification rows.
**Placement:** docs/bugs/partial-validated-masks-shim-verification-rows-mark-complete-refuse-loop

**Related:**
- `docs/bugs/_archive/decision-2-6-uncovered-row-reroute-to-mcp-test/` — the Step-10 mcp-test
  re-route (`uncovered_verification_rows_remain`) this bug shows is not shim-aware.
- `docs/bugs/_archive/coherence-recovery-loop-no-terminal-on-unrunnable-verification-rows/`
  (hardening Round 44) — the honest-stuck NEEDS_INPUT terminal for verification rows that never ran
  on ANY host. GAP 2's rows are RUNNABLE (a frontend mcp-test can certify them here), so that
  terminal deliberately does NOT fire — leaving this runnable-but-uncovered class routeless.
- `docs/bugs/feature-operator-host-defer-not-honored-over-validated/` — sibling partial-VALIDATED
  friction; cross-references `turn-routing-enforcement/NEEDS_INPUT.md` decisions #5/#6/#9.
- `docs/specs/turn-routing-enforcement/NEEDS_INPUT.md` — decision #6 (corrective-coverage dispatch)
  is the OPEN operator-owned STRUCTURAL fork this bug's residual (canonical-row partial-coverage
  masking) belongs to; this bug fixes only the contained shim-divergence, not that structural fork.

## Symptom (verified)

`waveform-visualization` had a feature-level `VALIDATED.md` written by an mcp-test cycle whose
scenario was Rust-only (39/39 assertions, but ZERO frontend coverage). Phase 3's three frontend
Runtime-Verification rows (animate-on-play, rAF-poll reachability, toggle-off-stops-both) were
never certified and stayed unchecked. Because `VALIDATED.md` exists at the feature level,
`compute_state` routes `__mark_complete__` (Step 10). But `--apply-pseudo __mark_complete__`'s
mechanical per-phase coherence gate REFUSES (Phase 3 has 3 unchecked boxes). A coherence-recovery
cycle correctly could NOT tick them (no evidence exists) and did NOT escalate (it judged them
fixable-with-evidence, not un-runnable-on-any-host). Net: a `__mark_complete__` → refuse →
coherence-recovery-can't-fix loop, with NO state-machine route back to the frontend mcp-test.

## Root cause (proven — reproduced 2026-07-21)

A **three-way walk divergence** on Runtime-Verification rows that are under a recognized
verification subsection header but LACK the canonical `<!-- verification-only -->` marker (the
un-migrated "shim" rows `/spec-phases` inline templates still emit — Round 44 secondary cause).
For such rows:

| Consumer | Shim-aware? | Effect on a shim row |
|---|---|---|
| `docmodel.remaining_unchecked_are_verification_only` | YES (`_VERIFICATION_SECTION_RE` header shim) | treated as verification |
| `docmodel.classify_blocking_unchecked_rows` | YES | classified `shim` (not `genuine`) |
| `docmodel._phase_completion_plan` (the gate) | NO (canonical marker only) | REFUSES — counts the row as blocking |
| `gates.autotick_verification_rows` | NO | ticks NOTHING (correct — never blind-tick) |
| `gates._collect_uncovered_verification_rows` (the re-route predicate) | **NO** | returns 0 rows → **no re-route** |

So the gate REFUSES on the 3 shim rows, but `uncovered_verification_rows_remain` (which drives the
Step-10 mcp-test re-route) collects 0 shim rows → concludes "no uncovered rows" → the state machine
routes the doomed `__mark_complete__` again. There is NO forward route to the mcp-test that would
generate the missing frontend evidence.

A SECOND, compounding masking exists even for CANONICALLY-marked rows:
`uncovered_verification_rows_remain`'s coverage test is `len(rows) <= pass_count` — an unrelated
high `pass_count` (39 Rust assertions) "covers" ≤39 frontend rows by raw count, so a shim row that
IS collected would still be masked. A shim row is NEVER autotickable, so crediting it against
`pass_count` is a category error.

Empirical reproduction (`/tmp` probe, 2026-07-21): a Phase-3 subsection with 3 shim
Runtime-Verification rows → `_phase_completion_plan(exempt=True)` refuses `['### Phase 3: 3
unchecked box(es)']`; `autotick(pass=39)` ticks 0; `_collect_uncovered_verification_rows` returns
0 rows; `classify_blocking_unchecked_rows` reports `shim: [3 rows], genuine: []`. Canonically-marked
rows instead all tick (false-green), confirming the divergence is specific to the shim form.

## Fix scope (contained — restores the invariant; the structural residue stays operator-owned)

Invariant to restore: a feature can never be simultaneously (routed-to-mark-complete) AND
(permanently-refused-by-the-mechanical-gate) with no forward route to generate the missing evidence.

1. Make `gates._collect_uncovered_verification_rows` shim-aware — recognize rows under a
   `_VERIFICATION_SECTION_RE`-matched subsection header (heading- or bold-scope) that lack the
   canonical marker, mirroring `remaining_unchecked_are_verification_only` — and tag each row
   `is_shim`. This is NOT a gate weakening: the completion gate still refuses on shim rows and
   autotick still never blind-ticks them; it only supplies the missing FORWARD ROUTE.
2. In `uncovered_verification_rows_remain`, credit only CANONICAL (autotickable) rows against
   `pass_count` (the `len<=pass` cardinality mirrors autotick, which only ticks canonical rows). A
   shim row is never autotickable → always uncovered → re-routes to mcp-test (unless host-deferred).
3. The re-route instruction directs the mcp-test cycle to run/author the missing scenario AND
   migrate the shim rows to the canonical marker once the verification actually runs — so the loop
   TERMINATES (once migrated + evidenced, the gate autoticks and completes). Un-runnable rows remain
   host-deferred (clause b) and the oscillation tripwire backstops any residual.

**Residual (explicitly OUT of this bug's scope — structural, operator-owned):** the
`len(rows) <= pass_count` masking for CANONICALLY-marked rows (a Rust-only scenario false-greening
frontend rows by raw count) requires per-row / per-scenario coverage attribution and is the OPEN
`turn-routing-enforcement/NEEDS_INPUT.md` decision #6 (corrective-coverage dispatch). Fixing the
shim divergence closes the observed stuck-loop-with-no-forward-route; the canonical masking is a
separate false-green class tracked there.
