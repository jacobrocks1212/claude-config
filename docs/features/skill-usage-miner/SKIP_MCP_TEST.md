---
kind: skip-mcp-test
feature_id: skill-usage-miner
reason: claude-config is pure harness tooling — no Tauri app, no src-tauri, no package.json, no MCP-reachable surface exists to drive any MCP HTTP tool against. The feature is a stdlib-only, read-only Python analysis script (skill-usage-miner.py) + its test suite + doc rows; nothing reaches an MCP tool surface.
alternative_validation: pytest gate suite (12 files) 1248 passed / 2 sanctioned skips — incl. the NEW test_skill_usage_miner.py (27 tests; two-tree read-only hash invariant, both detectors, subagent attribution, --since/recency/age-gate windows, hygiene classes, D8 proposal blocks, toolify threshold, unknown invocations, malformed-JSONL tolerance, determinism, CLI smoke) and the untouched sibling test_toolify_miner.py (19). PLUS lazy-state.py --test / bug-state.py --test / lazy_coord.py --test smoke green, lazy_parity_audit.py exit 0, lint-skills.py exit 0. PLUS a live demonstration run against the real checkout with a fixture corpus — the four SPEC-known hygiene findings reproduced exactly (sh.exe.stackdump, remotion dangling symlink, local-site/teach case-variant skill.md) plus six genuine frontmatter findings; git status clean after every run (proposes, never executes).
date: 2026-07-04
skipped_by: pipeline
granted_by: mcp-test
spec_class: standalone — no app integration (no Tauri/MCP surface; read-only analysis tooling validated by pytest + a live-checkout demonstration run)
validated_commit: cadfd8138e8270d6990280eb7461121d3d7013f0
---

# MCP Test Skip — Skill Usage Miner + Dead-Weight Audit

## Why this feature has no MCP-reachable surface

`skill-usage-miner` lives entirely in **claude-config**, the Claude Code configuration harness —
NOT an application. There is no Tauri app (`src-tauri/` absent), no frontend / `package.json`,
and no MCP HTTP server to connect to. The feature is pure analysis tooling:

- `user/scripts/skill-usage-miner.py` — stdlib-only, READ-ONLY miner over the session-log corpus
  and both skills trees (reuses `toolify-miner.py`'s `_iter_log_files`; emits a markdown/JSON
  report to stdout or `--out`).
- `user/scripts/test_skill_usage_miner.py` — fixture corpora + fixture skills trees + fixture
  git repos (backdated commits for the age gate).
- Doc rows in `user/scripts/CLAUDE.md`, root `CLAUDE.md`, `user/skills/CLAUDE.md`.

None of this reaches an MCP tool surface — the miner is never on the state-script compute path
and writes nothing but its own report. This is the `standalone — no app integration` untestable
class.

## Alternative validation performed (all PASSING, at `validated_commit`)

| Suite | Command | Result |
|-------|---------|--------|
| Full pytest gate suite (12 files incl. the new `test_skill_usage_miner.py`) | `python3 -m pytest test_lazy_core.py test_hooks.py test_pipeline_visualizer.py test_lazy_parity.py test_lazy_queue_doc.py test_lint_skills.py test_surface_resolver.py test_stale_binary.py test_retro_ro9.py test_project_skills.py test_skill_usage_miner.py test_toolify_miner.py -q` | **1248 passed, 2 skipped** (the two sanctioned skips: Windows cold-boot spawn, WSL pipe) |
| New feature suite standalone | `python3 user/scripts/test_skill_usage_miner.py` | **27/27 passed** |
| Sibling miner (untouched import source) | `python3 user/scripts/test_toolify_miner.py` | **19/19 passed** |
| State-script smoke baselines | `lazy-state.py --test` / `bug-state.py --test` / `lazy_coord.py --test` | all green (no baseline change — feature never touches the state scripts) |
| Parity audit | `lazy_parity_audit.py --repo-root <checkout>` | exit 0 |
| Skill lint | `lint-skills.py --skills-dir user/skills --repos-dir repos` | exit 0 (doc-only edits; no projection delta) |

## Live demonstration run (recorded — fixture corpus; live corpus workstation-deferred)

Run against THIS checkout with a fixture logs dir (2 sessions + 1 subagent transcript,
2026-05-01 → 2026-07-01):

- Ranked table: `commit` skill-tool 1 (from the subagent file, attributed to its parent
  session), slash 12, sessions 2, 30d 12; repo-scoped rows annotated
  (`cloud-biased undercount`, heuristic repo-attribution shares).
- `## Hygiene` reproduced the four SPEC-known findings EXACTLY (`sh.exe.stackdump` stray file,
  `remotion` dangling symlink, `local-site`/`teach` case-variant `skill.md`) plus six genuine
  frontmatter findings (three name-mismatches incl. `error-resolver` → `Error Resolver`; two
  repo-scoped SKILL.md files with no frontmatter at all) — zero false positives.
- 65 age-gated never-invoked proposals with valid `git mv` + `archived/CLAUDE.md` row text;
  `git status` clean after every run — **proposes, never executes**, proven live.
- `--since 2026-06-01` raised the observation floor; toolify candidate (`commit`, 13 ≥ 10) and
  the unknown invocation (`ghost-skill`) surfaced.

The run against the real `~/.claude/projects` corpus (incl. wall-time measurement and the
SPEC's transcript-format empirical checks) is **workstation-deferred** — that corpus does not
exist in the cloud lane.
