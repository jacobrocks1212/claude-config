---
kind: implementation-plan
feature_id: doc-drift-linter
status: In Progress
created: 2026-07-04
complexity: moderate
phases: [1, 2, 3]
---

> **Plan** — generated inline on 2026-07-04.
> To execute: `/execute-plan docs/features/doc-drift-linter/plans/all-phases-doc-drift-linter-part-1.md`
> Single self-contained part covering all 3 phases.

# Implementation Plan — doc-drift-linter (Phases 1–3)

**PHASES.md:** `docs/features/doc-drift-linter/PHASES.md` (3 phases)
**SPEC.md:** `docs/features/doc-drift-linter/SPEC.md`

## EXECUTION MODEL

> **INLINE-EXECUTION:** This plan is executed INLINE with `Read`/`Edit`/`Write` (no `Agent`
> delegation), **test-first** for every TDD work unit — write the failing test before the
> implementation. Never invoke `/lazy` or `/lazy-batch` recursively.

**Gate suite (run after each phase; ALL green before marking a phase's WUs done):**
```
cd user/scripts && python3 -m pytest test_doc_drift_lint.py -q
python3 -m pytest test_lazy_core.py test_hooks.py test_pipeline_visualizer.py \
  test_lazy_parity.py test_lazy_queue_doc.py test_lint_skills.py \
  test_surface_resolver.py test_stale_binary.py test_retro_ro9.py test_project_skills.py -q
python3 test_toolify_miner.py && python3 lazy-state.py --test && python3 bug-state.py --test
python3 lazy_coord.py --test && python3 lazy_parity_audit.py --repo-root <repo-root>
python3 lint-skills.py --skills-dir <repo-root>/user/skills --repos-dir <repo-root>/repos
python3 doc-drift-lint.py --repo-root <repo-root>          # Phase 2 onward: must exit 0
```

## Key design contract (read before WU-1.1)

- Stdlib-only, pure-read, no `lazy_core` import, no state writes, byte-stable output.
- `DIVERGENCE_MARKER = "doc-drift:deliberate-divergence"` is the SSOT constant; markdown rows
  carry it in an HTML comment on the row line, `manifest.psd1` carries it in a `#` comment
  naming the exempted subject.
- Exit contract: 0 clean (exempted divergences allowed), 1 ≥1 drift finding, 2 malformed input.
- psd1 parser is shape-bound to THIS manifest (single-quoted strings, `@()` arrays, one nesting
  level under `Repos`); anything else → malformed, exit 2, never a silent guess.
- Hooks-reality extraction only sees commands referencing a `hooks/<name>.(sh|ps1)` path; inline
  `bash -c` commands are documented as invisible.
- Scripts check is doc→disk existence only (both tables are curated).

---

## Phase 1 — Linter core + hermetic tests

- [ ] WU-1.1 — Test scaffolding + finding/CLI contract: `test_doc_drift_lint.py` fixture
  builders (minimal repo tree per check); failing tests for exit 0/1/2 + summary line; then
  `doc-drift-lint.py` skeleton (finding model, `main`, `--repo-root`, output).
- [ ] WU-1.2 — Markdown table extractor: tests for pipe-table parse (separator skip, raw line
  per row, backtick token extraction, section-anchored lookup, missing-heading → malformed);
  then `parse_markdown_tables` + `find_section_table`.
- [ ] WU-1.3 — Hooks check (TDD): documented-unregistered, registered-undocumented,
  matcher-mismatch (incl. `Write|Edit` and `startup|resume|clear|compact` set normalization),
  NOT-registered rows asserted both ways, missing hook file on disk, marker exemption on a row.
- [ ] WU-1.4 — Scripts check (TDD): missing documented file, trailing-slash dir row, clean case,
  both tables scanned (root `## Scripts` + scripts-dir `## Files in this directory`), marker
  exemption.
- [ ] WU-1.5 — Coupled-pairs check (TDD): manifest-pair-missing-from-doc,
  doc-pair-missing-from-manifest, unordered pair matching, section-comment marker exemption for
  a missing row, malformed manifest JSON → exit 2.
- [ ] WU-1.6 — Manifest check (TDD): psd1 mini-parser (entries, Alias, comments; out-of-shape →
  malformed), entry-without-dir, alias-to-missing-key, dir-without-entry, psd1 `#`-comment
  marker exemption.
- [ ] WU-1.7 — Phase gates: new suite green; full existing gate suite unperturbed. Commit.

## Phase 2 — Fix the live drift

- [ ] WU-2.1 — Baseline evidence run: `doc-drift-lint.py --repo-root .` BEFORE fixes; record the
  finding list (expected: RESEARCH_SUMMARY items 1–5) in the phase notes below.
- [ ] WU-2.2 — Doc fixes: hooks-table corrections (pr-review-cache-guard → `(Read)`;
  block-work-repo-git-writes → NOT-registered row; + `load-branch-docs-context.sh` row);
  Coupled Skill Pairs table + 3 bug-axis rows; `manifest.psd1` algobooth marker comment.
- [ ] WU-2.3 — Self-check test `test_this_repo_is_clean` (runs the linter against this repo
  root, asserts exit 0); phase gates green. Commit.

## Phase 3 — Docs rows + finalize

- [ ] WU-3.1 — Script-table rows for `doc-drift-lint.py` in root `CLAUDE.md` and
  `user/scripts/CLAUDE.md`; linter still exit 0 (the rows are themselves under the scripts
  check).
- [ ] WU-3.2 — FULL gate suite + final linter run; `SKIP_MCP_TEST.md`; PHASES/plan finalize.
  Commit.

## Phase notes

- *(WU-2.1 baseline evidence recorded here during Phase 2.)*
