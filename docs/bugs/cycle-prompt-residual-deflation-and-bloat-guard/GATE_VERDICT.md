---
kind: gate-verdict
feature_id: cycle-prompt-residual-deflation-and-bloat-guard
gate_version: 1
date: 2026-07-20
scope_hit:
  - docs/gate/control-surfaces.json
  - user/scripts/skill-size-ratchet.py
  - user/skills/_components/lazy-batch-prompts/cycle-base-prompt.md
  - user/skills/_components/lazy-batch-prompts/dispatch-hardening.md
  - user/skills/_components/lazy-batch-prompts/dispatch-recovery.md
checks:
  overfit: flag-justified
  tautology: pass
  gate_weakening: pass
  complexity: declared
retires: net-new
---

## Adversarial answers

### overfit

`harness-gate.py` flagged the war-story shape regexes as "alternation literal appended
to a matcher" (plus two finding-dict literals `{"section": key, "metric": ...}` in the new
`check_sections`, which are result-dict shapes mirroring the existing `check`/`check_profiles`,
not matcher allow-lists).

**Nearest recurrence the rules do NOT catch:** a novel *undated* incident codename — e.g.
`hydra-overlay`, `q3-latency-spike` — used as narrative provenance. The detector deliberately
does NOT catch that class. This is the **operator-LOCKED D2 decision** ("CONFIRMED SHAPES ONLY";
loose narrative phrasing is "a DELIBERATE accepted miss — caught by the per-section byte ceiling +
the D2b CLAUDE.md contract instead"). So the accepted miss is by design, and it is covered by
defense-in-depth (the new per-section byte ceiling refuses the *bytes* a novel narrative adds even
when the assembled profile nets under its ceiling; the `lazy-batch-prompts/CLAUDE.md` contract
states the rule at the edit site).

**Structural property each rule keys on** (the class GENERATOR, not an instance):
- `iso-date` → the date SHAPE `\b20\d\d-\d\d-\d\d\b` (any incident date, not one date).
- `issue-round-marker` → the counter SHAPE `(?:ISSUE|Round)\s+\d+` (any issue/round number) plus the
  ONE named token `d8-effect-chains` — the single literal, which the operator explicitly enumerated
  as a confirmed shape (D2), a recurring cross-round narrative marker, not a one-off `docs/<slug>`
  incident dir. It is the sole named literal and is documented as such.
- `live-incident` → the fixed narrative-LEAD literal `Live incident:` — a structural prose lead-in,
  not an incident identity.
- `docs-incident-literal` → the incident-dir PATH SHAPE `docs/(bugs|features)/<slug>` restricted to
  a BARE dir reference (negative-lookahead `(?![/\w-])`), so an operational doc-FILE path
  (`docs/features/mcp-testing/SPEC.md`) is structurally excluded WITHOUT an incident-specific literal
  or an inline allowlist — the reshape that keeps the rule keyed on structure, not on the observed
  instance. (The reason-required `war-story-allow` inline allowlist (D4) exists for the residual
  case of a genuinely load-bearing bare-dir literal; no real family file currently needs one.)

The `_WS_COMMENT_STRIP_RE` flag is a comment-span regex (`<!-- ... -->` with a negative-lookahead
for the allowlist token) — it keys on HTML-comment STRUCTURE, carries no incident literal.

No literal fits a single observed incident: the shapes generate the war-story class, the one named
token is operator-confirmed, and the bare-dir refinement is a structural (not literal) exclusion.

### tautology

`tautology: pass` (no `## Intervention Hypothesis` required for this bug; the ship seam supplies
the SPEC). Were the detector BROKEN (matched nothing), its "success" would NOT look identical to
working: re-accreted dated/incident prose would land in dispatched templates and surface via TWO
INDEPENDENT signals the detector does not itself emit or suppress — (1) the per-section byte ceiling
firing on the added bytes, and (2) a future family byte-census / retro audit observing the
re-accretion. The guard's pass is cross-checked by the size ratchet + human review, not by the
detector asserting its own clean.

### gate_weakening

`gate_weakening: pass`. No `def test_*` deleted (19 tests ADDED), no numeric gate threshold changed,
no exemption/sanction set grown to weaken an existing gate, no `*_BYPASS` env-var, no
`permissionDecision: deny` / `refuse_*` / `exit 3` branch removed. The `war-story-allow` allowlist is
a NEW, reason-required (non-empty-reason-enforced) escape hatch that is part of the new gate — it
does not soften any pre-existing check.

### complexity

`retires: net-new`. This adds two NEW checks (a war-story pattern detector + a per-`@section` byte
ceiling) and does not retire an existing rule. Justification the added surface pays for itself: the
parent feature's whole-assembled-profile byte ratchet gates GROSS prompt size but is blind to (a)
per-section growth under a net-passing total and (b) the war-story PATTERN (dated/incident narrative
rides through as long as total bytes fit). The two new checks close exactly those two blind spots and
COMPOSE with — never duplicate — the profile ratchet. They are the standing-guard half of a
cleanup+guard pair (a one-time cleanup without a guard re-accretes; SPEC Proven Findings); the guard
is the deliverable that makes the deflation durable.
