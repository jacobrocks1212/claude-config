# Implementation Phases — Coupled-Pair Generation

> Phases for [`SPEC.md`](./SPEC.md). See [`RESEARCH_SUMMARY.md`](./RESEARCH_SUMMARY.md) for the
> decisive recon and [`NEEDS_INPUT_PROVISIONAL.md`](./NEEDS_INPUT_PROVISIONAL.md) for the product
> fork the measurement forced.

**Status:** Complete

**MCP runtime:** not-required — pure claude-config harness mechanics (a stdlib generator, JSON
overlay build-inputs, an additive manifest key, and a pytest suite). No Tauri app, no
MCP-reachable surface; validation is `pytest test_generate_coupled_skills.py`, the existing
`lazy_parity_audit.py` + `doc-drift-lint.py` + parity/doc-drift pytest suites staying green, and
`lint-skills.py` + `project-skills.py`. This is the `standalone — no app integration` untestable
class → `SKIP_MCP_TEST.md` at the MCP gate.

## Design delta from SPEC (measurement-driven; see RESEARCH_SUMMARY + provisional record)

The SPEC assumed derived files are token-substituted copies with ~11 divergences. Measurement
refuted this: derived files are independently-authored variants (0–3 of N blocks byte-reproduce).
The generation mechanism is byte-faithful regardless, so Phases 1–3 below deliver the mechanism +
the freshness gate + tests. The SPEC's D3 audit-demotion, D4 state-script-surface relocation, and
D2 provenance headers are **deferred to a follow-up** (Phase 4, gated on the provisional decision):
demoting the audit and rewriting the manifest heading model only pays off once re-canonicalization
has actually reduced the verbatim surface — doing it now would rip out the working C1–C6 audit for
no efficiency gain. The derived files are kept **byte-identical** on this landing (no provenance
headers) to maximize the safety rail.

---

### Phase 1: Generator + byte-faithful extraction

- [x] `user/scripts/generate-coupled-skills.py` (stdlib; imports `apply_tokens` from
  `lazy_parity_audit` — one substitution implementation). Modes: `--extract` / `--write` /
  `--check` (default, the drift gate) / `--report`; `--pair`, `--repo-root`.
- [x] Directive model: `canonical` (restate a canonical block via token subs — content-free,
  auto-propagating) / `verbatim` (stored divergent/inserted block, byte-exact); deletion by
  omission. Extract classifies a block `canonical` ONLY when `apply_tokens(canonical_block)`
  reproduces the derived block byte-for-byte → **byte-faithful by construction**.
- [x] CRLF-safe IO (no newline translation) + verbatim storage as `"\n"`-split line arrays.
- [x] Extract all 5 pairs → `user/scripts/coupled-overlays/<pair>.overlay.json` (centralized
  under `scripts/`, NOT under the skills tree — keeps `project-skills.py`/`lint-skills.py` from
  double-projecting build inputs).
- **MVB:** `--extract` writes overlays; `--report` shows per-pair canonical/verbatim/deleted
  accounting.
- Proven done: `generate-coupled-skills.py --report` prints the block accounting for all 5 pairs.

### Phase 2: Byte-faithful migration + drift gate

- [x] `--check` regenerates each derived in memory and byte-diffs against the committed file;
  exit 1 naming the pair + first divergent section on any mismatch.
- [x] Byte-identical migration proof: `--write` regenerates all 5 derived files; `git status`
  shows **zero** changes to any derived SKILL.md (byte-identical — the CRITICAL SAFETY RAIL).
- [x] Additive `"overlay"` key per pair in `lazy-parity-manifest.json` (build-input reference).
  `lazy_parity_audit.py` (exit 0) and `doc-drift-lint.py` (exit 0) unaffected — the pair set is
  unchanged, so the coupled-pair-table cross-check still holds.
- **MVB:** `--check` is green on the committed tree; a hand-edit to a derived file makes it red.
- Proven done: `generate-coupled-skills.py --check` exit 0; parity audit + doc-drift-lint exit 0.

### Phase 3: Test coverage

- [x] `user/scripts/test_generate_coupled_skills.py` (34 tests): `split_blocks` round-trip
  identity + verbatim inverse; **golden** byte-identical regen for every real pair (committed
  overlay AND fresh extract); `--check` clean-tree + hand-edit-drift detection + write-repairs;
  determinism; overlay schema validation (unknown op / stale canonical heading / missing keys);
  canonical-edit propagation through a `canonical` directive.
- **MVB:** `pytest test_generate_coupled_skills.py` green.
- Proven done: 34 passed; `test_lazy_parity.py` + `test_doc_drift_lint.py` (81) still green.

### Phase 4 (DEFERRED — gated on the provisional decision): audit demotion + re-canonicalization

- [ ] <!-- descoped --> ~~SPEC D3 — demote `lazy_parity_audit.py` to a freshness verifier (regen-byte-diff subsumes C2 for generated content; C1/C4/C5 re-target overlay hygiene). DEFERRED: only pays off after re-canonicalization shrinks the verbatim surface; ripping out C1–C6 now removes a working audit for no gain. (STATE-lane / audit-owner coordination — see report.)~~ **DEFERRED** (operator complete-all directive, 2026-07-13; Phase 4 gated-on-provisional follow-up, tracked in SPEC D3)
- [ ] <!-- descoped --> ~~SPEC D4 — relocate `audit_state_script_parity` compiled-regex surfaces into a manifest `state_script_surfaces` list. DEFERRED with the audit demotion.~~ **DEFERRED** (operator complete-all directive, 2026-07-13; Phase 4 gated-on-provisional follow-up, tracked in SPEC D4)
- [ ] <!-- descoped --> ~~SPEC D2 — add `<!-- GENERATED … -->` provenance headers to derived files (the one intentional byte-delta). DEFERRED so first landing stays byte-identical.~~ **DEFERRED** (operator complete-all directive, 2026-07-13; Phase 4 gated-on-provisional follow-up, tracked in SPEC D2)
- [ ] <!-- descoped --> ~~Re-canonicalization campaign — incrementally convert `verbatim` directives back to `canonical` where the divergence is unintentional drift (a genuine bug fix present in only one file is ported to the canonical; a real variant stays verbatim). Each conversion is a measurable step on the `parity-restated-heading-entries` KPI. DEFERRED — this is the actual efficiency work, and it is per-block editorial judgment, not mechanization.~~ **DEFERRED** (operator complete-all directive, 2026-07-13; per-block editorial follow-up, tracked in SPEC re-canonicalization campaign)

## Integration Notes

- **Coupled-pairs registry unchanged:** the manifest's `pairs[]` set (5 pairs) is untouched, so
  the root `CLAUDE.md` Coupled Skill Pairs table ↔ manifest cross-check (`doc-drift-lint.py`)
  stays exit 0 with no doc edit owed on this landing.
- **`apply_tokens` single-sourcing:** the generator imports it from `lazy_parity_audit`; a future
  audit demotion must keep the symbol importable (or move it to a shared module and re-point both).
- **Overlays are build inputs, not skills:** placed under `user/scripts/coupled-overlays/`, so no
  skills-tree tooling touches them. The derived SKILL.md files remain the runtime-loaded artifacts
  at their unchanged paths (SPEC D2-A) and the human review surface.
