# Research — Anti-Overfit + Tautology Design Gate for Harness Changes

**Status: Gemini deep research intentionally skipped (operator directive, 2026-07-04).** This
feature was fleshed out via internal desk research instead: a survey of the in-repo prior art it
builds on, plus prior-art knowledge of comparable external systems. This file is the canonical
"research satisfied" marker for this repo (direct RESEARCH.md drop, per claude-config/CLAUDE.md),
so the pipeline routes Step 5 → /spec Phase 3 (integrate research + finalize) — which surfaces the
SPEC's OPEN product-behavior decisions to the operator via NEEDS_INPUT.md before planning starts.

## In-repo prior art

- **The `/harden-harness` over-fit detector (`user/skills/harden-harness/SKILL.md`, Step 3)** —
  the shipped prose-level ancestor from `harness-hardening-retro-fixes` (Complete). It already
  encodes: four smell signals (literal-phrase-to-matcher; class recurred ≥2; agent self-flags
  narrow; repeated deterministic dance), the first-occurrence rule for phrase-match patches
  ("over-fit by construction"), the generalization bound ("smallest class that subsumes the
  observed instance and its near neighbors"), and the non-blocking spin-off protocol. This
  feature's job is generalization, not invention: the reflex sees only hardening rounds today,
  while most control-surface changes ship through pipeline items.
- **Prohibition #2 ("Never weakens a gate", same file)** — the gate-weakening check is this
  prohibition made mechanical. The canonical caught instance is already logged:
  `docs/specs/turn-routing-enforcement/hardening-log/2026-07.md:44` records the operator
  declining a proposed exemption that "would reverse [a passing gate test] and require deleting
  a passing gate test" — exactly the diff shape (exemption-add + test-deletion) the D2
  detectors flag. The detector has a named, real positive fixture from day one.
- **Tautology instances in the wild:** the repo's own docs name the pattern — a deny-hook
  "working" because denies stopped, which is also what a broken hook looks like (fail-OPEN
  hooks fail silently, `user/hooks/CLAUDE.md`). The `signal_independence` field this gate
  consumes is specified in `intervention-efficacy-tracking`'s record schema (shared
  vocabulary, per the dep verdict).
- **Seam patterns:** `_components/phases-runtime-validation.md` (a planning-time audit injected
  BEFORE drafting, with per-repo overrides) and `_components/mcp-coverage-audit.md` (a
  completion-time gate on `__mark_complete__`/`__mark_fixed__`) are the two shipped seams this
  design copies — including the root `CLAUDE.md`'s description of them as a deliberate
  "two-seam contract" (planning-time + completion-time defense in depth).
- **Sign-off shape:** `/harden-harness` already writes `NEEDS_INPUT.md`
  (`_components/sentinel-frontmatter.md` rich-body convention) for contract/policy forks —
  "Never bake a harness-design fork in silently." Gate-weakening sign-off reuses that exact
  channel rather than inventing one.
- **Why not a hook:** `user/hooks/CLAUDE.md` and the root `CLAUDE.md` establish fail-OPEN as
  the hook-layer convention (every lazy enforcement hook is documented fail-OPEN). A blocking
  design gate cannot live there without either violating the convention or being silently
  skippable — the completion gates (receipt-gated completion, `user/scripts/CLAUDE.md`) are the
  repo's established fail-closed layer.

## External prior art & concepts

(Training-knowledge, not live research.)

- **Goodhart's law / Campbell's law:** a measure that doubles as the control surface stops
  measuring. The tautology check is Goodhart applied reflexively — the harness must not grade
  itself with signals it emits or suppresses.
- **Overfitting and regularization (ML):** a rule fitted to observed instances rather than the
  generating structure fails on the nearest unseen variant. The adversarial prompt "construct
  the nearest recurrence this rule does NOT catch" is a manual adversarial-example probe; the
  complexity budget is a regularization term (net rule count must justify itself).
- **Policy-as-code review gates (OPA/Conftest, Semgrep custom rules, danger.js):** mechanical
  diff/structure checks wired into the change path, with human escalation for policy-class
  findings. Validates the split: deterministic detectors for detectable shapes, recorded human
  judgment for the rest.
- **Four-eyes principle / change advisory (lightweight):** privileged-surface changes require a
  second authority. Single-operator reality maps "second pair of eyes" to an explicit,
  recorded operator sign-off rather than a reviewer pool — the NEEDS_INPUT round.
- **Safety-interlock practice:** disabling or bypassing an interlock is itself a controlled
  operation, logged and authorized. The rule that an approved override is per-change and never
  standing comes from here, as does refusing an env-var bypass (C option in D4).
- **Pre-registration (science):** committing the success metric before outcomes exist defeats
  post-hoc metric shopping — the reason the tautology check reads a hypothesis declared at
  design time, not a metric chosen at review time.

## Alternatives analysis

- **Trigger definition (D1):** manifest vs heuristic. The manifest is diffable, testable, and —
  decisive point — self-referential: changing the trigger IS a control-surface change, which a
  code heuristic cannot naturally arrange. Staleness is the manifest's real cost; the gate's
  KPI row (misses found in retro) measures exactly that.
- **Check split (D2):** all-mechanical vs all-adversarial vs split. All-mechanical cannot judge
  whether a justification is real (tautology substance, retire claims); all-adversarial is
  unauditable vibes. The split assigns each check its strongest decidable layer and records the
  judgment half so it can be graded later — the same philosophy as retro's verdict-plus-
  citation discipline.
- **Seam (D3):** the pre-commit hook is the intuitive place and the wrong one here (fail-OPEN
  convention; no adversarial prose in a deny hook; `git commit` interception is brittle across
  the repo's orchestrated commit paths). The completion gate is where this repo already refuses
  unproven claims (receipts, MCP coverage, ledger checks), so blocking authority lands there;
  the planning seam exists because a design caught at `/spec-phases` time costs one redraft
  while one caught at completion costs the whole implementation.
- **Override (D4):** NEEDS_INPUT round vs new sentinel vs env-var. The repo actively defends
  against hand-written sentinel proliferation (`block-noncanonical-blocker-write.sh`,
  "Don't hand-write completion sentinels"), and an env bypass is self-defeating (the detector
  flags bypass introduction as weakening). The existing decision-round machinery is also the
  only one of the three that produces a durable, structured record of WHO approved WHAT.
- **Blocking semantics (D7):** the tiering follows irreversibility: a wrongly-passed weakening
  silently disarms a defense (worst class); a wrongly-passed overfit rule just under-generalizes
  (self-announcing on recurrence — the harden-harness log proves recurrences do surface). And
  the harden-harness path must keep its never-block-the-run property or the gate would degrade
  live-run recovery — the exact "gate becoming friction" failure the stub warns about.

## Pitfalls & risks

- **The gate overfits:** literal-keyed detectors in the checker would fail the checker's own
  standard. Mitigation: detectors key on structural diff shapes (append-to-alternation,
  set-membership add, deny-branch removal), the checker is on its own manifest, and its named
  regression fixtures are historical instances, not hypotheticals.
- **False-positive burden:** the numeric-literal-change detector especially could nag. If the
  override rate climbs, the gate's own KPI row surfaces it — and tuning it DOWN is itself a
  gate-weakening change requiring sign-off, which is the correct amount of friction for
  loosening a guard.
- **Judgment laundering:** a cycle could write a pro-forma adversarial justification to clear a
  justify-or-halt flag. Mitigation: verdicts are recorded and cross-checked against efficacy
  outcomes (a passed-then-REFUTED change indicts its verdict); retro grades verdict quality the
  way it grades cycle compliance today.
- **Scope creep into ordinary work:** the stub exempts ordinary feature work; the manifest and
  the `in_scope: false` fast path are the guarantee. Watch AlgoBooth/cognito repos remain
  byte-identical (validation row).
- **Dead-weight risk:** if control-surface change volume drops, the gate is idle complexity.
  Its own complexity-budget declaration must name what it retires: the inline smell-signal
  prose in `/harden-harness` Step 3 (delegated to the checker) and ad-hoc operator vigilance on
  gate-weakening diffs.

## Recommendations summary

| Decision | Recommendation | Confidence |
|----------|----------------|------------|
| D1 scope trigger | Committed glob manifest (`docs/gate/control-surfaces.json`), self-included | High (OPEN — initial set needs operator eyes) |
| D2 check split | Mechanical floor per check + recorded adversarial half; weakening never judgment-passable | High (auto-accepted) |
| D3 seams | Planning-seam component + completion-gate ship seam + harden-harness delegation; no blocking hook | High (OPEN) |
| D4 override | NEEDS_INPUT.md decision round; approval transcribed to verdict `override:`; per-change only | High (OPEN) |
| D5 verdict recording | `GATE_VERDICT.md` in item dir + summary pointer on the intervention record | High (auto-accepted) |
| D6 self-audit | KPI rows + own intervention record with independent signal | High (auto-accepted) |
| D7 blocking semantics | Tiered: weakening halts for sign-off; others justify-or-halt; harden-harness never blocked | Medium-high (OPEN) |
