---
kind: skip-mcp-test
feature_id: code-doc-provenance-linkage
reason: claude-config is pure harness mechanics — no Tauri app, no src-tauri, no package.json, no MCP-reachable surface exists to drive any MCP HTTP tool against. The feature adds a provenance producer inside the state scripts (lazy_core.write_provenance + four CLI subcommands), a commit-bracket ledger at --cycle-end, sentinel-schema/skill/prompt prose, and a committed reverse index; none of it reaches an MCP tool surface.
alternative_validation: 'pytest (gate suite 1237 passed + 2 sanctioned skips, incl. 35 NEW code-doc-provenance-linkage tests in test_lazy_core.py) + lazy-state.py/bug-state.py --test smoke (baselines re-pinned via _normalize_smoke_output for the new fail-open fixture, then green) + lazy_coord.py --test + test_toolify_miner.py + lazy_parity_audit.py exit 0 + lint-skills.py clean + projection to a lane-local dir. PLUS a live production validation — --backfill-provenance ran against this repo itself — 50 receipted items (10 features + 1 bug + 39 archived bugs) distilled to IMPLEMENTED.md (provenance: backfilled, derivation: message-grep) and merged into docs/provenance-index.json (625 file keys, 896 rows); --provenance-lookup user/scripts/lazy_core.py returns the governing records; --lint-provenance reports 232 dead rows / 43 churn hotspots / 0 cross-orphans without mutating anything.'
date: 2026-07-04
skipped_by: pipeline
granted_by: mcp-test
spec_class: standalone — no app integration (no Tauri/MCP surface; harness mechanics validated by pytest + smoke baselines + parity audit + skill lint, and live-validated by the claude-config backfill run)
validated_commit: 02b705146071e0f0b4fd2fc29a56878f28d7b344
---

# MCP Test Skip — Code↔Doc Provenance Linkage

## Why this feature has no MCP-reachable surface

`code-doc-provenance-linkage` lives entirely in **claude-config**, the Claude Code configuration
harness — NOT an application. There is no Tauri app (`src-tauri/` absent), no frontend /
`package.json`, and no MCP HTTP server to connect to. The feature is pure harness mechanics:

- `lazy_core.py` — `write_provenance` (the ONE producer), the commit-bracket ledger
  (`append_commit_bracket` / `read_commit_brackets` / `record_cycle_commit_bracket`), the
  derivation helpers (brackets / range / message-grep), `link_provenance`, `provenance_lookup`,
  `lint_provenance`, `backfill_provenance`, and the `apply_pseudo` completion-gate wiring
  (+ the `completed_commit` receipt anchor).
- `lazy-state.py` / `bug-state.py` — the mirrored `--cycle-end` bracket append + the four mirrored
  CLI subcommands (`--link-provenance`, `--provenance-lookup`, `--lint-provenance`,
  `--backfill-provenance`).
- Prose surfaces — `sentinel-frontmatter.md` (`kind: implemented`), the cycle-base-prompt
  `provenance-lookup` section, `/spec-phases` Step 2.8, the `/lazy`↔`/lazy-cloud` +
  `/lazy-batch`↔`/lazy-batch-cloud` mirrored notes, and the new `/link-provenance` skill.

None of this reaches an MCP tool surface — there is no live runtime to probe. This is the
`standalone — no app integration` untestable class.

## Alternative validation performed (all PASSING)

| Suite | Command | Result |
|-------|---------|--------|
| Core unit tests (producer byte-stability, gate wiring incl. refused-gate/receipt-noop/warnings degradation, manual-link shape parity, lookup purity, lint rot detection, backfill honesty + idempotency, CLI parity on both scripts) | `python3 -m pytest test_lazy_core.py …` (full gate set) | **1237 passed, 2 sanctioned skips** |
| Smoke baselines (incl. the NEW mirrored `cycle-end-bracket-fail-open` fixture) | `lazy-state.py --test` / `bug-state.py --test` | green (baselines re-pinned via `_normalize_smoke_output`) |
| Concurrency plane / miner | `lazy_coord.py --test` / `test_toolify_miner.py` | green |
| State-script parity | `lazy_parity_audit.py --repo-root .` | exit 0 |
| Skill projection + lint | `project-skills.py` (lane-local out dir) + `lint-skills.py` | clean |

## Live production validation (this repo)

`--backfill-provenance --repo-root .` distilled all **50** receipted items (10 feature
`COMPLETED.md` + 1 in-place bug `FIXED.md` + 39 archived `FIXED.md`) into `IMPLEMENTED.md`
distillates and built `docs/provenance-index.json` (**625** file keys, **896** rows) — the SPEC's
estimated counts (10 / 39) verified. Read-side proof: `--provenance-lookup
user/scripts/lazy_core.py` lists the governing records with archive-resident doc paths;
`--lint-provenance` reports dead rows (232 — path-literal rows over renamed/deleted history, the
D5-expected staleness surface), 43 churn hotspots, 0 cross-orphans, and mutates nothing.
