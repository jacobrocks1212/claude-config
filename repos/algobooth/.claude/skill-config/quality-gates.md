### algobooth Quality Gates

Determine which gates are relevant based on the files modified:
- TypeScript changes → `npm run qg -- ts`
- Rust changes → `npm run qg -- rust`
- Sidecar changes → `npm run qg -- sidecar`
- Docs / SPEC / PHASES changes → `npm run qg -- docs` (`check-docs-consistency.ts`)
- Mixed → `npm run qg` (all gates)

### Pending `qg:docs-consistency` rules

Four new rules pending implementation in `scripts/check-docs-consistency.ts` per the 2026-05-28 audit-walk retrospective: `phases.coherence.phases-complete-but-spec-draft`, `spec.resolved-research-checklist-drift`, `phases.deliverables.duplicates`, `spec.status-stale-vs-last-updated`. Spec at `.claude/skill-config/docs-consistency-rules-pending.md`. Delete the spec file when the AlgoBooth-side PR lands the rules.
