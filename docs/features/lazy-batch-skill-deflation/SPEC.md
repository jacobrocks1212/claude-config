# Lazy-Batch Skill Deflation — Feature Specification

> `user/skills/lazy-batch/SKILL.md` is 251,832 B / 1,597 lines (re-measured 2026-07-11) and
> growing ~30KB/week: 160KB (06-13) → 188KB (06-16) → 224KB (06-24) → 252KB (07-11), +57% in
> four weeks across 126 commits. 146 single-line paragraphs over 500 chars carry 144KB — 57% of
> the file (longest line 3,976 chars) — and an estimated ~25–35% (~65–85KB) is driftable
> RESTATEMENT of script behavior the state scripts already own and emit as verdict JSON.
> Excise mechanism narration down to verdict-field routing rules, relocate dated
> "Motivating incident" narratives to a HISTORY sidecar, and add a size + long-line lint
> ratchet so re-bloat fails a gate instead of accreting silently. The dispatcher tier proves
> the target shape: `/lazy` is 292 lines of pure dispatch glue over the same state machine.

**Status:** Draft
**Friction-reduction feature:** yes
**Priority:** P2
**Last updated:** 2026-07-12

## Locked Decisions

Research integrated (this SPEC's own inline recon — reproduced/re-verified 2026-07-12; see
`RESEARCH_SUMMARY.md`). Per SPEC recommendations:

- **D1 — Excision principle** (`mechanical-internal`): **LOCKED as recommended** — route on
  verdict fields, never narrate the machinery; keep trigger/invocation/routing-table/hard-
  constraints/one-line-incident-citation, delete internal-state-ladder restatement.
- **D3 — Size + long-line ratchet lint** (`mechanical-internal`): **LOCKED as recommended** —
  extend the skill-lint family with a per-file byte-ceiling + long-line-count ratchet over a
  committed baseline JSON; opt-in per file; `--lock-in` is the only way to lower a ceiling.
- **D4 — Coupled-pair mirroring strategy** (`mechanical-internal`): **LOCKED as recommended,
  FALLBACK path** — `coupled-pair-generation` landed as a byte-faithful generator substrate, but
  its premise (token-substituted derived bodies) is refuted: most derived-file blocks are
  `verbatim` overlay entries. This feature therefore hand-mirrors each canonical excision into
  `lazy-batch-cloud` / `lazy-bug-batch` per their existing divergence tables, then regenerates
  overlays (`generate-coupled-skills.py --extract`) so `--check` stays green — the fallback
  D4 explicitly priced in as "the expensive path."
- **D2 — Motivating-incident narratives relocate to a HISTORY sidecar** (`product-behavior`):
  **PARKED — provisionally accepted** on recommendation (option A, HISTORY.md sidecar) per
  `NEEDS_INPUT_PROVISIONAL.md` in this feature dir. Implementation proceeds against option A;
  Status stays Draft and completion is mechanically blocked until the operator ratifies or
  redirects.
**Source:** repo-exploration proposal session 2026-07-11 (line anchors and sizes re-verified
against the working tree the same day — the file was modified today; all numbers below are
live measurements)

**Depends on:**

- coupled-pair-generation — soft — do after (or with): today every canonical deflation edit is
  a 3-way edit (canonical + `lazy-bug-batch` 99,316 B + `lazy-batch-cloud` 206,395 B + the
  748-line parity manifest); once generation lands, deflating the canonical is a single-file
  edit and the derived variants deflate for free. Implementable first, but then this feature
  must hand-mirror every excision into both derived whales and re-key the manifest's
  `headings[]` evidence — roughly tripling the mechanical work and drift risk.

> Substantive (non-block) dependencies are **implemented contracts**, not sibling specs:
> - `lazy-state.py` / `lazy_core.py` verdict surfaces — the script-owned JSON the skill should
>   route on instead of restating: the `--ensure-runtime` M4 verdict
>   (`state ∈ {READY, STALE, HIJACKED, DEAD, BLOCKED}` + `terminal_blocker`), the probe's
>   `cycle_prompt`/`cycle_prompt_ref`/`cycle_model`/`sub_skill_args` fields, pseudo-skill
>   `--apply-pseudo`, and the `SANCTIONED_STOP_TERMINAL` terminal vocabulary.
> - `user/scripts/lint-skills.py` — the lint family the new ratchet joins (same invocation
>   path, same projected-skill awareness).
> - `docs/features/execute-plan-skill-diet/SPEC.md` — Complete — the direct precedent: the same
>   operation on `/execute-plan` (44,726 → 22,678 B, −49%) with zero rule loss, validated by a
>   rule-preservation review. This spec reuses its method and its KPI shape.

---

## Executive Summary

The orchestrator skill is the prompt every `/lazy-batch` session runs on — resident from turn 1,
re-paid after every compaction, and mirrored (today by hand) into two derived whales. It has
grown into the repo's largest prose file by a wide margin, and the growth curve is the problem:
**160,045 B (2026-06-13, ffd1745) → 187,912 B (06-16, ce10a52) → 223,810 B (06-24, a919f07) →
251,832 B (07-11 working tree)** — +57% in four weeks, 126 commits touching the file since its
2026-05-20 birth at 10,187 B. Each hardening pass appends narration; nothing ever removes any.

Where the weight is (re-measured 2026-07-11):

- **146 single-line paragraphs >500 chars carry 144,166 B = 57% of the file** (longest line
  3,976 chars). These are the skill's signature failure mode: wall-of-text paragraphs that
  restate script mechanics inline with rationale, incident history, and cross-references.
- **§1d.0 runtime pre-boot (L612–738): 34,493 B**, an estimated ~70% of which restates
  `lazy_core.ensure_runtime`'s *internal* classifier — states, recovery ladders, lock-file
  semantics — even though the script already emits the M4 verdict JSON whose whole purpose is
  that the orchestrator routes on `state` + `terminal_blocker` without knowing the internals.
- **§1c.5 inline pseudo-skill handling (L529–573): 18,525 B**, ~55% restating what
  `--apply-pseudo` does internally rather than what the orchestrator must do with its result.
- **§1b terminal-state handling (L423–452): 13,467 B**, ~50% restating
  `SANCTIONED_STOP_TERMINAL` semantics the state script owns and emits.
- **Model-selection prose (L677–687, L737):** ~80% restates that `cycle_model`/`cycle_prompt`
  come from the probe — the rule is one sentence ("copy the probe's fields verbatim; never
  hand-bind"), the current text is paragraphs.

Summed with the smaller instances of the same pattern, **~25–35% of the file (~65–85KB) is
driftable restatement**: prose describing script internals that the scripts already express as
verdict fields. Restatement is not just weight — it is the drift surface. When
`ensure_runtime`'s ladder changes, the skill's 34KB narration silently lies until someone
notices (the exact failure class the parity audit can't see either, per the
coupled-pair-generation sibling).

Two proofs the target shape works: `/lazy` — the dispatcher tier over the *same* state machine —
is **292 lines** of pure dispatch glue; and `execute-plan-skill-diet` (Complete) halved
`/execute-plan` with zero rule loss using exactly the method proposed here (dedupe restatements,
compress incident rationale to rules + citations, relocate non-resident content).

This is a **content** diet, not a mechanism change: every HARD CONSTRAINT, gate, terminal
route, and incident citation survives; what goes is the narration of machinery the orchestrator
is already forbidden to re-implement. Mission criteria: **efficient** (tens of KB off every
orchestrator session's resident context, on both derived whales too) and **effective**
(routing rules that cannot drift from the scripts they route on, plus a ratchet so the curve
cannot silently resume).

## KPI Declaration

Drafted row (full schema; same signal shape as `execute-plan-resident-skill-bytes` from the
Complete `execute-plan-skill-diet` precedent):

```json
{
  "id": "lazy-batch-resident-skill-bytes",
  "system": "lazy-batch",
  "title": "Bytes of /lazy-batch skill body resident per orchestrator session",
  "friction": "The canonical orchestrator skill is 251,832 B (~60K tokens of prose) resident in every /lazy-batch session and re-paid across compactions, +57% in four weeks; ~25-35% is driftable restatement of script behavior the state scripts already emit as verdict JSON, and every edit to it is a 3-way coupled-pair edit.",
  "signal": { "source": "session-log-mining", "selector": "predispatch-skill-body-bytes" },
  "unit": "bytes",
  "direction": "down-is-good",
  "baseline": { "value": 251832, "captured_at": "2026-07-11", "window": "1d", "provenance": "measured" },
  "band": null,
  "review_by": "2026-10-01",
  "repo_scope": "claude-config",
  "notes": "Baseline = on-disk canonical body bytes (user/skills/lazy-batch/SKILL.md, working tree 2026-07-11) — the deterministic proxy for the resident body, per the execute-plan-skill-diet precedent; the session-log-mining channel (attribute_predispatch.py) is honest NO-DATA until a collector is wired. Companion deterministic measures tracked in this SPEC's validation: long-line count (146 paragraphs >500 chars / 144,166 B today) and the derived whales (lazy-batch-cloud 206,395 B, lazy-bug-batch 99,316 B) which shrink with the canonical once coupled-pair generation lands. Target: canonical <= ~150KB (-40%) with zero rule loss; the ratchet lint (this feature's Phase 3) locks the achieved size as a ceiling."
}
```

## Design Decisions

### D1. Excision principle: route on verdict fields, never narrate the machinery

- **Classification:** `mechanical-internal (recommend auto-accept)`
- **Question:** What is the editing rule that distinguishes load-bearing prose from excisable
  restatement, so the diet is repeatable and reviewable?
- **Design:** for every section that fronts a script call, the skill keeps exactly: (1) when to
  invoke (trigger), (2) the invocation (command + required env/flags), (3) the routing table
  over the *emitted* fields (each verdict value → orchestrator action), (4) the hard
  constraints that bind the orchestrator's behavior around it, (5) one-line incident citations
  (`(burned: <slug>)`) where a rule exists because of a named incident. It deletes: internal
  state ladders, recovery sequences the script performs itself, restated flag semantics,
  duplicated rationale already present in the cited incident/feature docs. Applied to the four
  measured hotspots: §1d.0 becomes a trigger + one `--ensure-runtime` call + a 5-row routing
  table over `state` (READY/STALE/DEAD proceed; HIJACKED/BLOCKED → `BLOCKED.md` with
  `blocker_kind: mcp-runtime-unready` and the verdict's `terminal_blocker` as body) + the
  guard-takeover rule — an estimated ~34.5KB → ~8–10KB. §1c.5 and §1b get the same treatment
  against `--apply-pseudo` and the terminal vocabulary (~18.5KB → ~6–8KB, ~13.5KB → ~6KB);
  model/prompt-binding prose collapses to the copy-verbatim rules (~4KB → <1KB).
- **Non-negotiable:** the OUTPUT CONTRACT, HARD CONSTRAINTS, gate sequences, marker lifecycle,
  sentinel schemas, and every terminal's routing survive verbatim-or-tighter. Rule-preservation
  review (the execute-plan-skill-diet validation pattern) is the acceptance gate: a named
  checklist of every rule/citation in the pre-diet file, each ticked as present post-diet.

### D2. Motivating-incident narratives relocate to a HISTORY sidecar

- **Classification:** `product-behavior (needs operator confirmation)`
- **Question:** The file is dense with dated "Motivating incident (2026-06-XX): ..." paragraphs
  — valuable as audit trail, dead weight as resident prompt. Where do they go?
- **Options:**
  - **A — HISTORY.md sidecar in the skill directory (recommended):**
    `user/skills/lazy-batch/HISTORY.md`, keyed by rule id/section; the skill keeps the rule +
    `(burned: <slug>)` citation; the sidecar keeps the narrative. Not runtime-loaded; grep-able
    when a rule's provenance is questioned.
  - **B — the hardening log / claude-config bug specs:** many incidents already have
    `docs/bugs/` or feature-spec homes; pure pointers from the skill would suffice — but a
    non-trivial subset exists ONLY as in-skill narrative today, and scattering those across
    retroactive bug docs fabricates history.
  - **C — delete outright:** loses the audit trail that justifies each hard rule; rules without
    provenance get "simplified" away by future editors — the exact rot the citations prevent.
- **Recommendation:** A, with B opportunistically: where a doc already exists, the sidecar entry
  is a pointer, not a copy. Needs operator sign-off because it changes where incident
  provenance lives for the harness's most safety-critical skill.

### D3. Size + long-line ratchet lint on SKILL.md

- **Classification:** `mechanical-internal (recommend auto-accept)`
- **Question:** The curve (+57%/four weeks) shows deflation without a gate is a temporary
  state. What mechanically prevents re-bloat?
- **Design:** extend the existing skill-lint family (invoked alongside
  `user/scripts/lint-skills.py`; implementation may live in that script or a sibling — same
  invocation path either way) with a per-file ratchet over a small committed baseline JSON:
  (1) **total bytes** — fail when the file exceeds its recorded ceiling; (2) **long-line
  budget** — fail when the count of >500-char lines exceeds its recorded ceiling (today 146;
  post-diet expected well under half that). Ratchet semantics mirror the AlgoBooth
  composite-score gate: growth past baseline fails; improvement lowers the recorded ceiling via
  an explicit `--lock-in` (never automatically, so a transient deletion can't set an
  unreachable bar). Scope: the coupled-pair canonical skills first (`lazy-batch`, `lazy`,
  `lazy-status` + derived once generated); opt-in per file via the baseline JSON rather than a
  blanket rule, so ordinary small skills carry no ceremony.
- **Why not a soft warning:** the file's history is 126 commits of well-intentioned additions;
  advisory output demonstrably does not hold this line.

### D4. Coupled-pair mirroring strategy

- **Classification:** `mechanical-internal (recommend auto-accept)`
- **Question:** How do the excisions reach `lazy-bug-batch` (99,316 B) and `lazy-batch-cloud`
  (206,395 B)?
- **Design:** sequence behind `coupled-pair-generation` (soft dep above): deflate the canonical
  once, regenerate the derived files, done — the derived whales shrink by construction and the
  manifest needs no heading-evidence re-keying. Fallback if this feature is pulled forward:
  hand-mirror per the existing parity contract (run `lazy_parity_audit.py` per the skills'
  parity notes; update `headings[]` evidence for every excised/reworded section) — explicitly
  the expensive path, priced in the dep note. Either way the ratchet (D3) covers the derived
  files only after they are generated (hand-maintained whales get baselines at their post-diet
  sizes).

## Technical Design

- **Deliverables:** rewritten `user/skills/lazy-batch/SKILL.md` (target ≤ ~150KB, −40%; every
  rule preserved); `user/skills/lazy-batch/HISTORY.md` (D2); ratchet lint + committed baseline
  (D3); regenerated/mirrored derived files (D4); re-projection (`project-skills.py`) +
  `lint-skills.py` green, per house rule.
- **Method (per hotspot):** extract the section's rule inventory → verify each rule's
  script-side owner (verdict field, guard, or gate) → rewrite as trigger/invocation/routing
  table/constraints/citations (D1) → diff the rule inventory pre/post (rule-preservation
  review) → mirror per D4.
- **Explicit non-goals:** no state-script changes; no change to any gate's semantics; no
  reordering of steps; no touching the OUTPUT CONTRACT's operator-facing format. Anything that
  *needs* a script change to become excisable (e.g. a verdict field that doesn't exist yet) is
  recorded as a follow-up, not smuggled in.
- **Measurement hooks:** the section/line measurements in this SPEC are reproducible one-liners
  (byte-slice by heading anchors; `>500`-char line census) — the Phase 1 plan records them so
  post-diet numbers are computed the same way.

## Implementation Phases

- **Phase 1 — Hotspot excision (~1–2 sessions).** §1d.0, §1c.5, §1b, model/prompt-binding
  prose per D1; rule-preservation checklist authored BEFORE editing, verified after. Proven
  done: checklist 100% ticked; canonical ≤ ~185KB from these four alone.
- **Phase 2 — HISTORY sidecar + long-line sweep (~1 session).** D2 relocation; sweep the
  remaining >500-char paragraphs (rewrap rule-bearing ones into structured lists; excise
  restatement per D1). Proven done: long-line count under the post-diet target; canonical at
  target size; sidecar carries every relocated narrative keyed to its rule.
- **Phase 3 — Ratchet lint (~1 session).** D3 lint + baselines locked at achieved sizes;
  wired into the same invocation path as `lint-skills.py`; pytest fixtures (over-ceiling file
  fails; improvement + `--lock-in` lowers). Proven done: lint red on a fixture regression,
  green on the tree.
- **Phase 4 — Derived-pair propagation (~0.5–1 session; shape depends on
  coupled-pair-generation's status).** Regenerate (preferred) or hand-mirror + manifest re-key
  (fallback); parity audit green. Proven done: derived whales at their reduced sizes; audit
  exit 0.

## Validation Criteria

| Behavior | Trigger | Expected Evidence | Where to Check |
|----------|---------|-------------------|----------------|
| Zero rule loss | Rule-preservation checklist review | Every pre-diet rule/gate/citation present post-diet | checklist artifact in plans/ |
| Size target | Byte count post-Phase 2 | Canonical ≤ ~150KB (from 251,832 B) | `wc -c` |
| Long-line burden broken | >500-char line census | Count well under 146; bytes-in-long-lines ≪ 144KB | census one-liner |
| Routing fidelity | Next real `/lazy-batch` run over an `mcp-test` cycle | §1d.0 routing table drives ensure-runtime handling identically (READY proceeds; HIJACKED → BLOCKED.md) | run transcript + sentinels |
| Re-bloat fails loudly | Fixture SKILL.md over its ceiling | Ratchet lint exit non-zero naming file + metric | lint pytest |
| Parity preserved | `lazy_parity_audit.py` post-propagation | Exit 0 across all pairs | audit run |
| Incident provenance intact | Spot-check 5 relocated narratives | Each reachable from its rule's citation via HISTORY.md | manual review |

## Open Questions

- **D2 operator confirmation:** HISTORY.md sidecar as the home for incident narratives.
- Exact post-diet ceiling for the ratchet baseline (lock at achieved size vs achieved+small
  headroom) — recommend achieved size, headroom via explicit future `--lock-in` only.
- Whether `/lazy-batch-parallel` and `lazy-worker` (outside the parity manifest) get the same
  D1 treatment in this feature or a follow-up — recommend follow-up; keep this scope on the
  measured whale and its coupled pair.

## Cross-links

- `docs/features/execute-plan-skill-diet/SPEC.md` — Complete — the method precedent (−49%,
  zero rule loss, rule-preservation review as acceptance gate); this SPEC deliberately reuses
  its KPI shape and validation style. Scope dedupe: that feature also moved repo-specific
  policy to skill-config injections — `/lazy-batch` has no equivalent repo-specific block
  (its AlgoBooth-only sections are already runtime-conditional), so no LD2-style relocation
  here.
- `docs/features/lean-plan-files/SPEC.md` — Complete — the pointer/contract architecture and
  the "compaction is served by re-reading from disk, not re-inlining" principle this diet
  relies on.
- `docs/features/coupled-pair-generation/SPEC.md` — the soft dependency; owns the mirroring
  mechanism (D4) and the manifest; this feature owns the canonical's content.
- `docs/features/friction-kpi-registry/SPEC.md` — the measurability gate this KPI Declaration
  satisfies.
