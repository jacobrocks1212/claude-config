# Research Summary — harness-hardening-retro-fixes

**Research: intentionally skipped (operator decision, 2026-06-16).** Internal harness mechanics;
no external prior art needed. Evidence base is `LAZY_BATCH_REVIEW_2026-06-16_overview_2.md` (HIGH:
haiku-tier punts; MEDIUM: recurring harness bugs + verification-detector whack-a-mole; operator
question 3: over-fitting is mild and self-flagged, durable fix is structural). This file satisfies
the pipeline research gate (`lazy_core.py:739`) and records the locked baseline.

## Locked Decisions

1. **Anti-overfit trigger:** fix-instance-now + spin off a generalized `/spec`/`/spec-bug`
   (front-enqueued) on over-fit smell — narrow phrase-match patch, class recurred ≥2, or
   self-detected. The instance fix always lands first so the run is never blocked.
2. **Generalization bound:** target the smallest class subsuming the observed instance + near
   neighbors; cite concrete evidence; name the class boundary. No speculative rewrites.
3. **Verification-section detector:** structural — producers (`/spec-phases`,
   `/blocked-resolution`) emit one canonical verification-only marker; detector keys off it; the
   growing regex retires (deprecation shim surfaces un-migrated producers).
4. **Also in scope:** `plan_complete` false-alarm fix (plan-less features), mcp-test haiku-tier
   re-scope (script-derived routing of diagnosis/scenario-authoring to sonnet by default), and a
   dead-coverage guard (orphaned, uncollected test files fail gates).
5. **Out of scope (owned elsewhere, cross-referenced):** `-followups` queue-trim miss + `mcp-tests`
   symlink blindspot → `unified-pipeline-orchestrator`; stale-marker-arms-guard-globally →
   `multi-repo-concurrent-runs`.

## Dependency

Hard-depends on `unified-pipeline-orchestrator` — consumes its toolify miner + deterministic-only
bar so harden-harness can auto-identify a repeated dance and spin off a `/spec-bug` to toolify it.

## Open (deferred to /spec-phases)

- Over-fit recurrence threshold (first-occurrence for phrase-match patches vs ≥2 for others).
- Canonical marker form (per-row comment vs canonical subsection header) — pick what
  `check-docs-consistency.ts` validates cleanly.
- Exact script-observable haiku→sonnet routing conditions.
