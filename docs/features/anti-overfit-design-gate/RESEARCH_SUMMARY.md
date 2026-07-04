# Research Summary — Anti-Overfit + Tautology Design Gate for Harness Changes

> Distillate of `RESEARCH.md` (internal desk research; Gemini deep research intentionally skipped
> by operator directive 2026-07-04). This file gates the downstream `/spec-phases` → `/write-plan`
> workflow. It records what the research confirms, what to adopt, what to watch, and which baseline
> decisions the research leaves OPEN for operator sign-off (surfaced via `NEEDS_INPUT.md`).

## Key findings relevant to the baseline spec

- **The gate is generalization, not invention.** The `/harden-harness` Step-3 over-fit detector is a
  shipped prose-level ancestor that already encodes the four smell signals, the first-occurrence
  rule for literal-phrase patches, the generalization bound, and the non-blocking spin-off protocol.
  The research confirms the feature's job is to promote that reflex from one skill's prose (which
  sees only hardening rounds) into a repo-wide mechanical checker + recorded-verdict protocol that
  also covers the pipeline items through which most control-surface changes actually ship.
- **The gate-weakening detector has a real, named positive fixture from day one.** The logged
  operator decline at `docs/specs/turn-routing-enforcement/hardening-log/2026-07.md:44` (GAP-2:
  an exemption that "would require deleting a passing gate test") is exactly the diff shape
  (exemption-add + test-deletion) the D2 detectors flag — so the checker's regression suite anchors
  on history, not hypotheticals. This directly supports keying detectors on structural diff shapes
  rather than incident literals.
- **Tautology is Goodhart applied reflexively.** External framing (Goodhart/Campbell, pre-registration)
  confirms the design instinct: the success metric must be declared at design time (the intervention
  record's `signal_independence` field) and produced by a signal the change does not itself emit or
  suppress — the repo's own "deny-hook working because denies stopped, which is also what a broken
  hook looks like" is the canonical in-repo tautology.
- **The completion gate is the correct blocking layer.** Research confirms the house invariant: hooks
  are fail-OPEN by convention, so a blocking design gate cannot live at the hook layer without either
  violating the convention or being silently skippable. The completion gate is where the repo already
  refuses unproven claims (receipts, MCP coverage, ledger checks) — blocking authority belongs there.
- **Policy-as-code precedent validates the mechanical/adversarial split.** OPA/Conftest, Semgrep
  custom rules, and danger.js all pair mechanical diff/structure checks with human escalation for
  policy-class findings — precisely the D2 architecture (deterministic detectors for detectable
  shapes, recorded human judgment for the rest).

## Ideas to adopt from prior art

- **Structural (not literal) detectors, self-included on the manifest.** Detectors key on diff shapes
  (append-to-alternation, set-membership add, deny-branch removal) so the checker passes its own
  overfit standard; the checker + manifest + component are themselves on the manifest.
- **Four-eyes → recorded operator sign-off.** Single-operator reality maps "second pair of eyes" to
  an explicit, durable, structured record of WHO approved WHAT — the existing NEEDS_INPUT.md decision
  round, which is the only override mechanism of the three that produces such a record.
- **Safety-interlock discipline.** An approved override is per-change and never standing; an env-var
  bypass is refused (the detector would flag its own bypass introduction as weakening).
- **Pre-registration.** The tautology check reads a hypothesis declared at design time, not a metric
  chosen at review time — defeating post-hoc metric shopping.
- **Regularization as complexity budget.** The "what does this retire?" declaration is a
  regularization term: net rule count must justify itself.

## Pitfalls & concerns to address (carry into phases)

- **False-positive burden of the numeric-literal-change detector.** Tune context rules during Phase 1
  against the hardening log's committed fixes; the gate's own KPI row (override rate) surfaces creep,
  and loosening the detector is itself a sign-off-gated weakening.
- **Judgment laundering** (pro-forma adversarial justification to clear a justify-or-halt flag).
  Mitigation: verdicts are recorded and cross-checked against `intervention-efficacy-tracking`
  outcomes (a passed-then-REFUTED change indicts its verdict); retro grades verdict quality.
- **Scope creep into ordinary work.** The manifest + `in_scope: false` fast path guarantee ordinary
  feature work and the AlgoBooth/cognito repos stay byte-identical (a validation row).
- **Dead-weight risk.** If control-surface change volume drops, the gate is idle complexity — its own
  complexity-budget declaration must name what it retires (the inline smell-signal prose delegated
  from `/harden-harness` Step 3; ad-hoc operator vigilance on gate-weakening diffs).
- **The gate overfits itself.** Detectors must key on structural diff shapes and carry the two named
  historical instances (`_VERIFICATION_SECTION_RE` phrase-append; GAP-2 exemption-add) as regression
  fixtures.

## Baseline decisions the research leaves OPEN (operator sign-off required)

The research produces strong, high-confidence recommendations but four decisions are
**product-behavior** — they change what the operator experiences (what arms the gate, where it
runs, how sign-off works, what halts an autonomous run). Per the `/spec` Phase-3 always-halt rule
these are surfaced to the operator via `NEEDS_INPUT.md` rather than auto-accepted, even though each
carries a strong recommendation:

| Decision | Recommendation | Confidence |
|----------|----------------|------------|
| D1 scope trigger | Committed glob manifest (`docs/gate/control-surfaces.json`), self-included | High (initial set needs operator eyes) |
| D3 seams | Planning-seam component + completion-gate ship seam + harden-harness delegation; no blocking hook | High |
| D4 override | NEEDS_INPUT.md decision round; approval transcribed to verdict `override:`; per-change only | High |
| D7 blocking semantics | Tiered: weakening halts for sign-off; others justify-or-halt; harden-harness never blocked | Medium-high |

Auto-accepted mechanical-internal decisions (no operator choice): **D2** (mechanical/adversarial
split per check), **D5** (`GATE_VERDICT.md` residency + intervention-record pointer), **D6** (the
gate's own KPI rows + independent-signal intervention record).
