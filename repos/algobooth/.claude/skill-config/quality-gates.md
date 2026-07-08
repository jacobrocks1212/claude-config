### algobooth Quality Gates

Determine which gates are relevant based on the files modified:
- TypeScript changes → `npm run qg -- ts`
- Rust changes → `npm run qg -- rust`
- Sidecar changes → `npm run qg -- sidecar`
- Docs / SPEC / PHASES changes → `npm run qg -- docs` (`check-docs-consistency.ts`)
- Mixed → `npm run qg` (all gates)

**NEVER pipe a `qg` invocation through `tail`/`head` (`npm run qg -- ts | tail`).** A shell
pipeline returns the exit status of the *last* command (`tail`, always 0), masking the wrapper's
non-zero exit — a failing gate then reads as green. The wrapper already truncates failure output
for you, so piping buys nothing. If you must limit what you scan, read the guaranteed final
`QG_VERDICT: PASS` / `QG_VERDICT: FAIL (exit N)` line the wrapper emits (survives `| tail`), or
redirect to a file and inspect that (`npm run qg -- ts > qg.log 2>&1; echo $?`). Rely on the exit
code, never the piped tail.

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
