# Research Summary — multi-repo-concurrent-runs

**Research: intentionally skipped (operator decision, 2026-06-16).** Internal harness mechanics;
no external prior art needed. Evidence base is the live stale-marker incident (2026-06-17) and
`LAZY_BATCH_REVIEW_2026-06-16_overview_2.md`. This file exists to satisfy the pipeline's research
gate (`lazy_core.py:739`) and record the locked baseline.

## Locked Decisions

1. **Scoping model:** one run per repo, marker keyed by `repo_root`. A registry of per-repo
   marker files (`~/.claude/state/run-markers/<repo-key>.json`). Cross-repo concurrency enabled;
   same-repo second run refused by construction (shared git tree / queue.json).
2. **Hooks resolve current repo** and consult only that repo's marker; a foreign-repo marker is
   invisible. `--run-end` clears its own repo's marker; staleness horizon covers interrupted runs.
3. **Legacy singleton migrates** to the registry on first `--run-start`, then is removed.
4. `bug-state.py` shares the per-repo slot (feature/bug runs in one repo remain mutually
   exclusive — correct; cross-repo isolated).

## Open (deferred to /spec-phases)

- Exact staleness horizon (ended-flag only vs wall-clock bound).
- Repo-key derivation algorithm (must match byte-for-byte between Python writers and bash hook
  readers).
