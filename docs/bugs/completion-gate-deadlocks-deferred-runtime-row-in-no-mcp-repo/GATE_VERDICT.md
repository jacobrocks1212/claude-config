---
kind: gate-verdict
bug_id: completion-gate-deadlocks-deferred-runtime-row-in-no-mcp-repo
written_by: harden-harness
date: 2026-07-14
mechanical_checker: user/scripts/harness-gate.py --staged --json
verdict: APPROVED
signed_off_by: operator
signed_off_date: 2026-07-14
---

# Harness-change design-gate verdict

## Mechanical checker output (`harness-gate.py --staged`, exit 1, `in_scope: true`)

| Detector | Result | Disposition |
|---|---|---|
| `gate_weakening` | **pass** (`gate_weakening_hit: false`) | Not tripped — see analysis. |
| `overfit` | **flag** | False positives — justified below, `spinoff: none`. |
| `complexity` | **declaration-required** | `retires: net-new` (below). |
| `tautology` | pass | — |

`scope_hit`: `lazy_core/{__init__,docmodel,gates,pseudo}.py` (control surfaces).

## `gate_weakening` — mechanically PASS, but substantively a gate relaxation

The four structural detectors (`def test_*` deletion, numeric-literal-only change
on a gate line, exemption/sanction-SET membership add, `*_BYPASS` env-var,
`permissionDecision: deny`/`refuse_*`/`exit 3` removal) did **not** fire: the fix
ADDS a new keyword-gated branch (`verification_only_exempt=`) plus two new pure
helpers — it removes nothing, edits no threshold, and touches no exemption set
literal. So the mechanical gate-weakening signal is honestly absent.

**However**, the change substantively RELAXES the completion-integrity gate: it
makes `__mark_complete__` / `__mark_fixed__` reachable in a state (an unchecked
`<!-- verification-only -->` row) where it previously refused. That is exactly the
class of change the operator asked to sign off on. Rather than self-approve a
load-bearing-gate relaxation on a mechanically-clean gate_weakening result, this
verdict routes to **operator sign-off** (NEEDS_INPUT.md) — the conservative,
honest reading of the design gate for a completion-gate change.

Why it is a DISCIPLINED relaxation (the argument for sign-off, not a blank check):
- The new route fires ONLY when the MCP-evidence auto-tick is **structurally
  impossible** — a `granted_by: pipeline-structural` skip whose no-app-surface
  predicate RE-VERIFIES against the live repo (`skip_waiver_refusal` → None). An
  app repo re-verifies False and the route never fires (pinned by
  `test_deferred_runtime_exemption_app_repo_refuses` +
  `test_apply_pseudo_deferred_runtime_no_exemption_in_app_repo`).
- The deferred rows are **not ticked** — they stay `- [ ]` (the deferred run
  genuinely has not happened); the exemption is coupled by construction to writing
  an honest `RUNTIME_GATES.md` ledger (mirroring the existing `/execute-plan`
  pending-runtime-gates contract).
- Strict behavior is preserved for every real case: a genuine unchecked
  implementation row still blocks; a verification-only row in an MCP repo still
  needs real MCP evidence; forged/missing-VSA still refuses; the
  `LAZY_STRICT_EVIDENCE_GATE` kill-switch restores the byte-identical strict path.

## `overfit` — flag is entirely FALSE POSITIVES (no spin-off)

Every `overfit` evidence line is one of:
- "literal element appended to a membership construct" — the checker misreads the
  multi-line `reason` strings in `evaluate_deferred_runtime_exemption`, the
  `lines = [...]` ledger-body list in `write_runtime_gates_ledger`, and the test
  fixtures' YAML string literals as list/set appends. None is a matcher
  alternation / keyword-set / allow-list append.
- "incident-shaped literal added: 2026-07-14" — the fixture date in the new tests.

The fix keys on STRUCTURE (the `pipeline-structural` provenance + the
`repo_has_no_app_surface` re-verification predicate + the canonical
`_VERIFICATION_ONLY_MARKER`), NOT on any incident literal. **No literal-phrase-to-
matcher smell; class has not recurred → `spinoff: none`.**

## `complexity` — `retires: net-new`

`retires: net-new` — this fix introduces net-new surface (2 pure helpers
`evaluate_deferred_runtime_exemption` / `write_runtime_gates_ledger`, 1 keyword-only
param on `_phase_completion_plan`, 1 additive per-phase parse sub-count
`unchecked_verification_only`, 1 enumerator `enumerate_deferred_verification_rows`).
It retires no existing rule — there was no prior mechanism for a deferred-runtime
row in a no-MCP repo (the deadlock is the absence). Justification: it closes a real
completion no-route class and aligns the lazy completion gate with the harness's
own `pending-runtime-gates.md` contract; the alternative (misusing `<!-- descoped -->`)
is a factual misrepresentation of a deferred row.

## Disposition

Mechanical fix LANDED (harden-harness never blocks; the run is not left broken).
Because the change relaxes a load-bearing completion gate, this verdict is
**NEEDS-OPERATOR-SIGNOFF** — the exact question is in `NEEDS_INPUT.md`.

## Operator sign-off (2026-07-14)

**APPROVED** by operator via interactive AskUserQuestion (2026-07-14) — "Approve
(Recommended)". The disciplined relaxation is accepted as-designed: the route fires
only when MCP-evidence auto-tick is structurally impossible (`pipeline-structural`
skip re-verifying no-app-surface), rows stay unchecked, the `RUNTIME_GATES.md` ledger
is the honest tracker, every real refusal case is preserved, and
`LAZY_STRICT_EVIDENCE_GATE=1` restores the byte-identical strict path. NEEDS_INPUT.md
neutralized.
