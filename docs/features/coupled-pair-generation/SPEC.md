# Coupled-Pair Generation — Feature Specification

> The five coupled skill pairs (`lazy-batch`→{`lazy-bug-batch`, `lazy-batch-cloud`},
> `lazy`→{`lazy-bug`, `lazy-cloud`}, `lazy-status`→`lazy-bug-status`) are maintained by
> hand-duplication plus a regex-presence parity audit: of the manifest's 129 audited heading
> entries, 112 (~87%) are `restated` — manually duplicated prose, ~306KB across the two derived
> whales alone — and every canonical edit is a 3-way edit (canonical + derived + 748-line
> manifest). Replace hand-duplication with generation: a derived SKILL.md becomes a build output
> of (canonical text × the manifest's existing `token_substitutions` × an authored
> divergence-overlay set), the manifest becomes build input instead of audit ledger, and
> `lazy_parity_audit.py` demotes to a freshness verifier (generated output byte-matches the
> committed derived file). 112 hand-maintained restatements collapse into ~11 authored
> divergences.

**Status:** Complete
**Friction-reduction feature:** yes
**Priority:** P1
**Last updated:** 2026-07-11
**Source:** repo-exploration proposal session 2026-07-11 (evidence re-verified against the
working tree the same day — sizes below are live measurements, not the proposal's estimates)

> Substantive (non-block) dependencies are **implemented mechanisms**, not sibling specs:
> - `user/scripts/lazy-parity-manifest.json` (748 lines) — already carries the full pair map
>   (`canonical`/`derived`/`token_substitutions`/`mechanic_overrides`/`headings[]` with
>   per-heading `coverage` ∈ {restated, divergence, inherited}); this feature repurposes it as
>   build input.
> - `user/scripts/lazy_parity_audit.py` (623 lines) — `apply_tokens()` (L45–70) already
>   mechanizes the canonical→derived vocabulary mapping (literal + regex-escaped forms, ordered
>   substitution); checks C1–C6 define today's parity contract; `audit_state_script_parity()`
>   (L360–456) carries the hand-coded state-script surface checks D4 relocates into data.
> - `user/scripts/project-skills.py` — the house precedent for template expansion: recursively
>   resolves `!cat` component references into fully-projected skill copies, including per-repo
>   projections under `skills-projected/<repo>/`. Generation extends the same
>   deterministic-expansion discipline to whole-file derivation.
> - `docs/features/lazy-batch-skill-deflation/SPEC.md` — downstream sibling (soft-depends on
>   this feature): once derived files are generated, deflating the canonical is a single-file
>   edit instead of a 3-way one.

---

## Executive Summary

The lazy pipeline deliberately ships as coupled skill pairs — one canonical skill per axis
(feature-workstation) and derived variants per flavor (bug pipeline, cloud environment). The
coupling contract is real and worth keeping: a fix to the canonical MUST reach the derived
variants or the pipelines drift apart in behavior. But the *mechanism* is hand-duplication
audited by regex presence, and the numbers (re-measured 2026-07-11, working tree) say the
mechanism has become the friction:

- `user/scripts/lazy-parity-manifest.json` — 748 lines, 129 heading entries across 5 pairs:
  **112 `restated`** (manually duplicated content), **11 `divergence`** (genuine authored
  deltas), **6 `inherited`**. ~87% of the audited surface is duplication, not divergence.
- The derived whales: `repos/algobooth/.claude/skills/lazy-batch-cloud/SKILL.md` **206,395 B**
  restating 37/43 canonical headings; `user/skills/lazy-bug-batch/SKILL.md` **99,316 B**
  restating 33/43 — **~306KB of derived prose** whose overwhelming majority is a
  token-substituted copy of `user/skills/lazy-batch/SKILL.md` (251,832 B). The full derived
  set (adding `lazy-bug` 19,810 B, `lazy-cloud` 29,044 B, `lazy-bug-status` 8,806 B) is ~363KB.
- `lazy_parity_audit.py` checks C1–C6 are **all regex-presence** (its own docstring, L4–10):
  C2 verifies a heading's `evidence` regex still matches in the derived file; nothing verifies
  the *content* of a restated section. A restated section can rot arbitrarily — stale
  step numbers, obsolete flag names, contradicting routing rules — while its evidence regex
  still matches. The audit catches *deletion*, not *drift*.
- Every canonical edit is therefore a 3-way edit: canonical SKILL.md + each derived SKILL.md +
  the manifest's `headings[]`/`evidence` entries. The lazy-batch canonical took 126 commits in
  eight weeks (see the deflation sibling's growth data); each one that touched a restated
  section owed this tax or silently skipped it.

The ingredients for generation already exist. The manifest's `token_substitutions` arrays are a
complete, ordered, machine-applied vocabulary map (`apply_tokens()`, audit L45–70 — it already
handles regex-escaped forms). `project-skills.py` already proves the house pattern of committed
sources → deterministic expansion → verified output. What's missing is only the inversion:
instead of *auditing* that a human performed the substitution correctly section-by-section,
*perform* the substitution mechanically and audit only the ~11 authored divergences.

After this feature: a canonical edit is a one-file edit; `generate` rebuilds the derived files;
the audit's job shrinks to "committed derived == regenerated derived" (byte-diff freshness) plus
divergence-overlay hygiene. Content drift in restated sections becomes structurally impossible
rather than regex-invisible.

Mission criteria: **efficient** (one edit instead of three; ~87% of the parity ledger becomes
machine-owned) and **effective** (drift-proof by construction, replacing a presence check that
provably cannot see content rot).

## KPI Declaration

Drafted row (full schema). The direct measure is deterministic and trivially re-measurable — a
one-line count of `coverage: "restated"` entries in the committed manifest:

```json
{
  "id": "parity-restated-heading-entries",
  "system": "lazy-parity",
  "title": "Hand-restated heading entries across the coupled-pair manifest",
  "friction": "112 of 129 audited headings (~87%) are manually duplicated prose across ~306KB of derived-whale skill bodies; every canonical edit is a 3-way edit (canonical + derived + 748-line manifest), and the C1-C6 regex-presence audit cannot detect content rot inside a restated section.",
  "signal": { "source": "deny-ledger", "selector": "process-friction-count" },
  "unit": "manifest-entries",
  "direction": "down-is-good",
  "baseline": { "value": 112, "captured_at": "2026-07-11", "window": "1d", "provenance": "measured" },
  "band": null,
  "review_by": "2026-10-01",
  "repo_scope": "claude-config",
  "notes": "Baseline = count of headings[] entries with coverage 'restated' in user/scripts/lazy-parity-manifest.json (re-measured 2026-07-11: 112 restated / 11 divergence / 6 inherited of 129). Target after generation: 0 restated entries (all become machine-generated), with only authored divergence overlays remaining (~11). The registered machine signal (deny-ledger process-friction-count) is the coarse channel today — parity-drift incidents surface there via incident-scan; implementation SHOULD register a dedicated selector (e.g. a repo-file source counting restated entries) and re-point this row, the same registry follow-up pattern as lean-plan-files' drafted row. Until then the manual count above is the measurement of record."
}
```

## Design Decisions

### D1. Generation model: derived = canonical × token map × divergence overlays

- **Classification:** `mechanical-internal (recommend auto-accept)`
- **Question:** What is the derivation function, and where does divergent content live?
- **Options:**
  - **A — overlay files per pair (recommended):** a new generator
    (`user/scripts/generate-coupled-pairs.py`, stdlib-only, sibling of `project-skills.py`)
    computes each derived file as: canonical text → `apply_tokens()` (the audit's existing
    L45–70 function, imported or lifted — one implementation, never two) → apply the pair's
    divergence overlays. Overlays live as authored files per pair (e.g.
    `user/skills/lazy-bug-batch/OVERLAY.md` or `user/scripts/parity-overlays/<pair>/`), each
    block keyed by canonical heading with an operation ∈ {replace-section, insert-after,
    delete-section}. The manifest's `headings[]` entries lose their duplication-tracking role:
    `restated`/`inherited` become implicit (generated), and each `divergence` entry points at
    its overlay block.
  - **B — inline conditional markers in the canonical** (`<!-- pair:lazy-bug-batch ... -->`
    regions): single file, but the canonical — already the repo's largest skill and itself a
    deflation target — absorbs every variant's divergent prose, and 5 pairs × conditional
    regions makes the canonical unreadable in exactly the way skills must not be (they are
    runtime-loaded prose).
  - **C — manifest-embedded overlay text:** keeps everything in one JSON file, but multi-KB
    markdown inside JSON string values is unreviewable and undiffable — the manifest is already
    748 lines of metadata; making it carry content would recreate the review problem this
    feature removes.
- **Recommendation:** A. Overlays are markdown files reviewed as markdown; the manifest stays
  metadata (pair map + token maps + overlay references); the generator stays a pure function.
  Heading-keyed `replace-section` granularity matches the audit's existing section model
  (`_enumerate_headings`, `##`/`###`).

### D2. Generated files are committed at their current paths (runtime-loaded skills)

- **Classification:** `product-behavior (needs operator confirmation)`
- **Question:** Do derived SKILL.md files remain committed in-repo, or become
  projection-time-only artifacts?
- **Options:**
  - **A — committed generated output at the existing paths (recommended):** derived files stay
    exactly where the runtime loads them (`user/skills/lazy-bug-batch/SKILL.md`,
    `repos/algobooth/.claude/skills/lazy-batch-cloud/SKILL.md`, ...). Claude Code and the
    `.claude/skills` symlink machinery load these paths directly — they cannot move without
    changing skill discovery. A generated-file header comment (`<!-- GENERATED from
    user/skills/lazy-batch/SKILL.md — edit the canonical or the overlay, never this file -->`)
    marks them. Pros: zero runtime change; diffs of generated output remain reviewable in PRs
    (the operator reads what the orchestrator will read). Cons: committed generated code — the
    freshness verifier (D3) exists precisely to keep it honest.
  - **B — generate at projection time only:** removes generated files from git, but skills are
    NOT loaded from `skills-projected/` at runtime — that directory is a verification aid. This
    option would require re-pointing runtime skill discovery, a much larger blast radius than
    the maintenance problem justifies.
- **Recommendation:** A. Readability-in-repo is a hard requirement (these files ARE the prompt
  the derived orchestrators run on); the generator must emit clean markdown, not
  template-scarred output. This is the named risk from the proposal session — accepted and
  mitigated by D3, not designed away.

### D3. The parity audit demotes to a freshness verifier

- **Classification:** `mechanical-internal (recommend auto-accept)`
- **Question:** What does `lazy_parity_audit.py` check once derived files are generated?
- **Design:** the audit's core check becomes: regenerate each derived file in memory and
  **byte-diff against the committed file** — any mismatch is a finding naming the pair and the
  first divergent section (stale generated output, or a hand-edit to a generated file). C1–C6
  collapse accordingly: C1 (canonical-heading completeness) is enforced by construction; C2/C3
  (evidence/mechanic presence) are subsumed by the byte-diff for generated content and retained
  only over divergence overlays; C4/C5 (stale entries / reason hygiene) re-target overlay
  hygiene (every overlay block must key a live canonical heading and carry a reason). C6's
  doc-anchor soft check is retained for overlays. The existing invocation surface
  (`--pair`, default full run, exit-nonzero-on-findings) is preserved so every caller — skill
  parity notes, pre-edit checks — keeps working. A `--write` mode on the *generator* (not the
  audit) regenerates in place; the audit itself stays read-only.

### D4. Hand-coded state-script surfaces move into manifest data

- **Classification:** `mechanical-internal (recommend auto-accept)`
- **Question:** `audit_state_script_parity()` (L360–456) hard-codes the state-script parity
  surfaces as compiled regex constants + per-surface finding prose — re-measured 2026-07-11:
  **8 surface checks over 9 compiled patterns** (`set_active_repo_root`, `--reorder-queue`,
  `--reassert-owner`, `--record-intervention`, host-capability fail-fast [2 patterns],
  `--sync-deps`, `cycle_prompt_ref`, `notify_halt`). Every new coupled state-script surface is
  a code edit to the audit.
- **Design:** relocate them to a `state_script_surfaces` list in the manifest
  (`{id, patterns: [...], reason}` — patterns stay regexes; the audit loop becomes generic).
  Adding a surface becomes a manifest edit, symmetrical with how `mechanic_sets` already work
  for SKILL.md mechanics. The merged-view dispatch parity block (audit L459+) is reviewed for
  the same relocation during implementation; it moves only if it fits the same shape without
  contortion.

### D5. Migration is validated by byte-diff against today's derived files

- **Classification:** `mechanical-internal (recommend auto-accept)`
- **Question:** How do we prove generation reproduces the current, known-good derived files?
- **Design:** bootstrap in three steps, each verifiable: (1) for each pair, compute
  token-mapped canonical and diff against the committed derived file — the diff hunks ARE the
  divergence set; (2) author each hunk as an overlay block (expect ~11 per the manifest's
  divergence entries, plus whatever undeclared drift the diff exposes — surfacing that drift is
  itself a win: it is exactly the content rot C2 could not see); (3) `generate` must reproduce
  the committed derived files **byte-identically** before the audit demotion (D3) lands — any
  intentional cleanup of exposed drift happens as explicit follow-up commits *after* the
  byte-identical baseline, never silently inside the migration. Undeclared drift found in step
  (1) that is a genuine bug fix present in only one file gets triaged: port it (canonical) or
  declare it (overlay) — never dropped.

## Technical Design

```
user/skills/lazy-batch/SKILL.md            (canonical — the ONLY hand-edited prose per axis)
user/scripts/lazy-parity-manifest.json     (build input: pairs, token_substitutions,
        │                                   overlay refs, state_script_surfaces)
        ▼
user/scripts/generate-coupled-pairs.py     (stdlib; pure function; --check / --write)
        │  canonical → apply_tokens() → divergence overlays (heading-keyed ops)
        ▼
user/skills/lazy-bug-batch/SKILL.md        (committed GENERATED output, runtime-loaded
repos/algobooth/.claude/skills/...          at unchanged paths; header marks provenance)
        ▲
        │ byte-diff (freshness)
user/scripts/lazy_parity_audit.py          (demoted: regen-and-diff + overlay hygiene +
                                            data-driven state_script_surfaces)
```

- **One substitution implementation:** the generator and the audit share `apply_tokens()`
  (module import, or extraction into a small shared module) — the substitution semantics that
  exist today (ordered, literal + regex-escaped) are the compatibility contract.
- **Determinism:** the generator is a pure function of (canonical, manifest, overlays); no
  wall-clock, no environment reads; byte-stable output (the `LAZY_QUEUE.md` /
  `kpi-scorecard.py` renderer discipline).
- **Overlay syntax (named risk):** heading-keyed blocks with explicit ops; the exact fence
  syntax is an implementation choice, but it must fail loudly on an overlay keying a heading
  the canonical no longer has (C4's successor) and must be lintable by `lint-skills.py`'s
  existing pass without new false positives.
- **Parity notes in skill prose:** the derived skills' "Parity note: run lazy_parity_audit.py
  before editing" headers become "GENERATED — edit canonical/overlay"; the canonical's parity
  note re-points at the generator workflow.
- **House invariants honored:** script-owned deterministic artifacts (an LLM never hand-edits a
  generated derived file); stdlib-only Python; read-only audit vs explicit `--write` generator;
  loud failure over silent skip.

## Implementation Phases

- **Phase 1 — Generator + bootstrap diff (~1 session).** `generate-coupled-pairs.py` with
  token-substitution reuse; run the D5 step-(1) diff for all 5 pairs; triage report of
  undeclared drift. Proven done: for each pair, `generate --check` output equals
  (committed derived − authored overlays) with every hunk accounted for.
- **Phase 2 — Overlay authoring + byte-identical migration (~1–2 sessions).** Author overlays
  from the diff hunks; land manifest v2 (overlay refs; `restated`/`inherited` entries removed);
  regenerate; commit byte-identical derived files (plus provenance headers as the single
  intentional delta). Proven done: `generate --check` exits 0 across all pairs.
- **Phase 3 — Audit demotion + state_script_surfaces (~1 session).** D3 audit rewrite; D4 data
  relocation; update every skill-prose parity note; pytest coverage for generator + demoted
  audit (fixture pair with a drifted derived file → finding; hand-edit to generated file →
  finding; stale overlay key → finding). Proven done: full audit green on the migrated tree,
  red on each fixture violation.

## Validation Criteria

| Behavior | Trigger | Expected Evidence | Where to Check |
|----------|---------|-------------------|----------------|
| Generation reproduces reality | `generate --check` post-migration | Byte-identical for all 5 pairs | CI / pre-commit run |
| Drift becomes impossible-by-construction | Edit a restated section in a derived file by hand | Freshness audit finding naming pair + section | `lazy_parity_audit.py` |
| Canonical edit is one edit | Edit a canonical section, run `generate --write` | All derived files updated; no manifest heading edit needed | git diff |
| Divergences stay authored + audited | Overlay keying a deleted canonical heading | Loud finding (C4 successor) | audit fixture test |
| State-script surfaces data-driven | Add a surface to `state_script_surfaces` | Audit enforces it with no Python edit | fixture test |
| Runtime unaffected | Load `/lazy-bug-batch`, `/lazy-batch-cloud` post-migration | Skills load and read as clean markdown from unchanged paths | manual skill invocation |

## Open Questions

- **D2 operator confirmation:** committed generated output at runtime paths (recommended) —
  confirm the operator accepts generated-file diffs in PRs as the review surface.
- Overlay file placement: co-located with the derived skill (`<skill>/OVERLAY.md`, visible next
  to what it modifies) vs centralized (`user/scripts/parity-overlays/`) — implementation-time
  choice; co-location is the working recommendation.
- Whether `lazy-batch-cloud`'s `inherited` entries (5 of its 43) need a third overlay op
  (`inherit-verbatim`, skipping token substitution) — determined by the Phase 1 diff.
- KPI registry follow-up: registering a dedicated selector for the restated-entry count and
  re-pointing the drafted row (see KPI Declaration notes).

## Cross-links

- `docs/features/lazy-batch-skill-deflation/SPEC.md` — downstream sibling; soft-depends on this
  feature so canonical deflation is a single-file edit. Scope split: THIS feature changes the
  *mechanism* of derivation (no intentional prose changes beyond provenance headers); the
  deflation sibling changes the *content* of the canonical.
- `docs/features/execute-plan-skill-diet/SPEC.md`, `docs/features/lean-plan-files/SPEC.md` —
  the single-sourcing precedent family (dedupe by pointer/contract); this feature is the same
  principle where pointers cannot work because each variant must remain a complete standalone
  runtime-loaded skill — so single-sourcing happens at build time instead of read time.
- `docs/features/friction-kpi-registry/SPEC.md` — the measurability gate this spec's KPI
  Declaration satisfies.
