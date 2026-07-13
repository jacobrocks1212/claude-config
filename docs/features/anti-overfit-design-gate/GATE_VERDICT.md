---
kind: gate-verdict
feature_id: anti-overfit-design-gate
gate_version: 1
date: 2026-07-13
scope_hit:
  - docs/gate/control-surfaces.json
  - user/scripts/harness-gate.py
  - user/skills/_components/harness-change-gate.md
  - user/skills/_components/sentinel-frontmatter.md
  - user/skills/harden-harness/SKILL.md
checks:
  overfit: flag-justified
  tautology: flag-justified
  gate_weakening: pass
  complexity: declared
retires: net-new — adds the harness-change design gate (checker + manifest + component). Retires /harden-harness Step-3's ad-hoc, judgment-only overfit/weakening smell detection, which now delegates to harness-gate.py.
---

## Adversarial answers

Commit range analyzed: `6aef028f..2cf3289f` (the feature's sole `feat(...)` commit).
`harness-gate.py` self-run over that range: overfit=flag, tautology=flag, gate_weakening=hit,
complexity=declaration-required. This is the self-referential case — the gate's own source trips
its own detectors — worked honestly below.

### overfit
The overfit flags land on `harness-gate.py`'s OWN detector regex definitions (`_ALTERNATION_ADD_RE`,
`_DENY_BRANCH_RE`, `_BYPASS_ENV_RE`, `_QUOTED_RE` all literally contain `|`), on the
`control-surfaces.json` manifest globs (a list of surface paths), and on PHASES.md prose. These are
NOT incident-fitted literals: the detectors key on diff SHAPES (an alternation-append, a
list-element-into-a-membership-construct, a `def test_*` deletion), and the manifest entries are
structural surface globs the operator owns — the manifest is itself on the manifest so widening it
is a gated change. Nearest recurrence a literal-keyed version would MISS: a novel verification-header
phrasing (the `_VERIFICATION_ONLY_MARKER` precedent — the reason the detectors key on the
HTML-comment marker structure, not the header text). Structural property the rules key on: the
generative SHAPE of the change (matcher-append / membership-add / test-deletion / refusal-removal),
never a slug/date/session literal. This is precisely why the checker passes its own overfit check.

### tautology
No formal `## Intervention Hypothesis` block (the SPEC discusses the concept in prose describing
its own tautology detector) → checker flags. This IS the canonical tautology risk: a deny/flag gate
"works" when nothing fires, which is indistinguishable from a broken gate that CAN'T fire. If this
gate were broken it would silently stop flagging and the field would look clean. Independent signal:
`test_harness_gate.py`'s 22 named regression fixtures assert each detector FIRES on known-bad shapes
(the `_VERIFICATION_SECTION_RE` phrase-append and the GAP-2 exemption-add fixtures), plus the
downstream `intervention-efficacy-tracking` REFUTED verdict that would indict a passed-then-failed
change. Neither is a signal this gate emits about itself — the fixtures are external red-team
assertions. `signal_independence: independent`.

### gate_weakening
Verified: the only `*_BYPASS` token in the diff is inside `test_gate_weakening_new_bypass_env_var()`
in `test_harness_gate.py` — a regression fixture that asserts the checker DETECTS a bypass env-var,
NOT a bypass introduced into a real gate. No `def test_*` deleted, no `permissionDecision: deny` /
`refuse_*` / `exit 3` removed, no sanction/exemption set grown. This feature ADDS a gate; it weakens
none. Pass.

### complexity
Net-new control surface (the checker, manifest, and adversarial component). It does retire one thing:
`/harden-harness` Step 3's ad-hoc, judgment-only smell detection now delegates to `harness-gate.py`
(Step 3 references the checker), so the previously-unstructured "does this overfit?" judgment gains a
mechanical floor. The added surface pays for itself: it makes three failure modes (overfit, silent
gate-weakening, self-graded metrics) mechanical + recorded rather than retro-only. NOTE: this feature
is PROVISIONAL (D1/D3/D4/D7 accepted under the park-provisional directive; `NEEDS_INPUT_PROVISIONAL.md`,
ratification pending).
