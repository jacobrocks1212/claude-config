---
kind: skip-mcp-test
feature_id: doc-drift-linter
reason: claude-config is pure harness mechanics — no Tauri app, no src-tauri, no package.json, no MCP-reachable surface exists to drive any MCP HTTP tool against. The feature is a pure-read stdlib lint script (doc-drift-lint.py) plus doc-table fixes; none of it reaches an MCP tool surface.
alternative_validation: pytest (combined suite 1238 passed / 2 sanctioned skips — incl. the NEW test_doc_drift_lint.py 36 tests, hermetic drift/clean/exemption/malformed fixtures per check class + the repo self-check) + test_toolify_miner.py (all passed) + lazy-state.py/bug-state.py/lazy_coord.py --test smoke (green, no baseline change) + lazy_parity_audit.py --repo-root . (exit 0) + lint-skills.py --skills-dir/--repos-dir (clean). PLUS a live production validation — the linter detected 7 real drift findings in this repo's docs at pre-fix HEAD aea2b59 (3 hooks-table, 3 coupled-pairs, 1 manifest) which were fixed/annotated in Phase 2; final run is exit 0 with exactly 1 marker-exempted deliberate divergence (algobooth).
date: 2026-07-04
skipped_by: pipeline
granted_by: mcp-test
spec_class: standalone — no app integration (no Tauri/MCP surface; harness doc-lint mechanics validated by pytest + smoke harnesses + a live drift-detection run against the repo itself)
validated_commit: 14d0d0f52411739827cf152687c426fbd6b0d76a
---

# MCP Test Skip — Doc-Drift Linter (CLAUDE.md vs. Reality)

## Why this feature has no MCP-reachable surface

`doc-drift-linter` lives entirely in **claude-config**, the Claude Code configuration harness —
NOT an application. There is no Tauri app (`src-tauri/` absent), no frontend / `package.json`,
and no MCP HTTP server to connect to. The feature is pure harness mechanics:

- `user/scripts/doc-drift-lint.py` — stdlib-only, pure-read cross-checker (hooks / scripts /
  coupled-pairs / manifest), exit 0/1/2, `DIVERGENCE_MARKER` exemptions.
- Root `CLAUDE.md` + `manifest.psd1` doc fixes (Phase 2) and script-table rows (Phase 3).

None of this reaches an MCP tool surface — there is no live runtime to probe. This is the
`standalone — no app integration` untestable class.

## Alternative validation performed (all PASSING)

| Suite | Command | Result |
|-------|---------|--------|
| Doc-drift linter unit + CLI tests (drift/clean per check class, marker exemption, malformed exit 2, byte-stability, repo self-check) | `python3 -m pytest user/scripts/test_doc_drift_lint.py -q` | **36 passed** |
| Full existing pytest gate suite (unperturbed) | `python3 -m pytest test_lazy_core.py … test_project_skills.py test_doc_drift_lint.py -q` | **1238 passed, 2 sanctioned skips** |
| Toolify miner | `python3 user/scripts/test_toolify_miner.py` | all passed |
| Smoke baselines | `lazy-state.py --test` / `bug-state.py --test` / `lazy_coord.py --test` | green (no baseline change) |
| State-script parity | `python3 user/scripts/lazy_parity_audit.py --repo-root .` | exit 0 |
| Skill lint | `python3 user/scripts/lint-skills.py --skills-dir user/skills --repos-dir repos` | clean |
| Final linter self-run | `python3 user/scripts/doc-drift-lint.py --repo-root .` | **exit 0** — 0 drift, 1 exempted divergence (algobooth) |

Every SPEC Validation-Criteria row names `test_doc_drift_lint.py` or the linter run as its
"Where to Check"; **zero** rows name an MCP surface (every phase's MCP Integration Test
Assertions block is `N/A — no MCP surface`).

## Live production validation (recorded — the feature proving itself)

At pre-fix HEAD `aea2b59`, `doc-drift-lint.py --repo-root .` detected **7 genuine drift
findings** in this repo's own docs — `block-work-repo-git-writes.sh` documented as registered
but wired nowhere; `pr-review-cache-guard.sh` documented on the wrong matcher (Bash vs Read);
`load-branch-docs-context.sh` registered with no Hooks-table row; the three bug-axis coupled
pairs missing from the Coupled Skill Pairs table; and `repos/algobooth/` with no `manifest.psd1`
entry. Phase 2 fixed the six genuine ones as doc commits and annotated the deliberate algobooth
divergence with the `doc-drift:deliberate-divergence` marker — i.e. real drift detected and
eliminated on the linter's first production run, demonstrated against the live tree rather than
a fixture.
