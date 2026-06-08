### algobooth Quality Gates

Determine which gates are relevant based on the files modified:
- TypeScript changes → `npm run qg -- ts`
- Rust changes → `npm run qg -- rust`
- Sidecar changes → `npm run qg -- sidecar`
- Docs / SPEC / PHASES changes → `npm run qg -- docs` (`check-docs-consistency.ts`)
- Mixed → `npm run qg` (all gates)

### Planning-integrity gates (mechanical — from the 2026-06-08 planning retrospective)

Three `block`-verdict gates convert the previously-advisory planning rules into enforcement
(modeled on `qg:touchpoint-audit`; all diff-scoped vs merge-base, so they only inspect changed
files). The `lazy-batch` / `lazy-bug-batch` completion-integrity gate runs them via their bundles:

- `qg:unwired-markers` (arch bundle) — blocks `TODO(WU-*` / `// not yet wired` / `// TODO: wire`
  on changed production-path files (`src-tauri/src/**`, `crates/**/src/**`,
  `src/{services,stores,composables}/**`). Backs the "production wiring is a deliverable" gotcha +
  `implement-phase-batch` S4 wiring-receipt rule.
- `qg:plan-anchors` (arch bundle) — blocks plan citations whose `path` / `path::Symbol` /
  `Type.method` anchor resolves to zero hits. Backs the `write-plan` `[VERIFY: <grep>]` discipline.
- `qg:sentinel-triage` (docs bundle) — advisory-grade lint flagging content-free blanket
  `SKIP_MCP_TEST` / `DEFERRED_*` sentinels (no per-assertion observability granularity).

Consolidated checklist + the five false-green smells: `docs/development/PLANNING_ANTIPATTERNS.md`.

### Pending `qg:docs-consistency` rules

Four new rules pending implementation in `scripts/check-docs-consistency.ts` per the 2026-05-28 audit-walk retrospective: `phases.coherence.phases-complete-but-spec-draft`, `spec.resolved-research-checklist-drift`, `phases.deliverables.duplicates`, `spec.status-stale-vs-last-updated`. Spec at `.claude/skill-config/docs-consistency-rules-pending.md`. Delete the spec file when the AlgoBooth-side PR lands the rules.
