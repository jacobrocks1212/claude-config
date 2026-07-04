---
kind: implementation-plan
feature_id: skill-usage-miner
status: In Progress
created: 2026-07-04
complexity: medium
phases: [1, 2, 3, 4]
---

> **Plan** — generated inline (lane `lane/skill-usage-miner`) on 2026-07-04.
> To execute: `/execute-plan docs/features/skill-usage-miner/plans/all-phases-skill-usage-miner-part-1.md`
> Single self-contained part covering all 4 phases.

# Implementation Plan — skill-usage-miner (Phases 1–4)

**PHASES.md:** `docs/features/skill-usage-miner/PHASES.md` (4 phases)
**SPEC.md:** `docs/features/skill-usage-miner/SPEC.md`

## EXECUTION MODEL

> **INLINE-EXECUTION:** This plan is executed INLINE with `Read`/`Edit`/`Write` (no `Agent`
> delegation), **test-first** for every TDD work unit — write the failing test before the
> implementation. Never invoke `/lazy` or `/lazy-batch` recursively.

**Gate suite (run after each phase; ALL green before marking a phase's WUs done):**
```
python3 user/scripts/test_skill_usage_miner.py
python3 user/scripts/test_toolify_miner.py          # sibling untouched — must stay green
python3 -m pytest user/scripts/test_lazy_core.py user/scripts/test_hooks.py \
  user/scripts/test_pipeline_visualizer.py user/scripts/test_lazy_parity.py \
  user/scripts/test_lazy_queue_doc.py user/scripts/test_lint_skills.py \
  user/scripts/test_surface_resolver.py user/scripts/test_stale_binary.py \
  user/scripts/test_retro_ro9.py user/scripts/test_project_skills.py -q   # full suite at end
python3 user/scripts/lazy-state.py --test ; python3 user/scripts/bug-state.py --test
python3 user/scripts/lazy_coord.py --test
python3 user/scripts/lazy_parity_audit.py --repo-root .
python3 user/scripts/lint-skills.py --skills-dir user/skills --repos-dir repos
```

## Key design contract (read before WU-1.1)

- **D1:** sibling script; import `toolify-miner.py` via
  `importlib.util.spec_from_file_location` (pattern: `test_toolify_miner.py:44-52`) and reuse
  ONLY `_iter_log_files`. Own value-preserving extractor (never `_normalize_call`).
- **D2:** two detectors, separate columns — assistant `tool_use` `name=="Skill"` →
  `input["skill"]` (normalize: strip leading `/`, strip `plugin:`-style prefix up to the last
  `:`); user-turn text → `re.findall(r"<command-name>(/[\w:-]+)</command-name>", txt)`
  (verbatim `digest_sessions.py:125`). Standing Caveats block in every report.
- **Session identity:** a `subagents/agent-*.jsonl` file attributes to its PARENT session
  (`<encoded-cwd>/<parent-uuid>/subagents/agent-<id>.jsonl` → parent-uuid); top-level files are
  their own session. Project dir = first path component under the logs dir.
- **D3:** `--since YYYY-MM-DD`; recency window = 30 days anchored to the NEWEST corpus timestamp
  (byte-stable, no wall clock); never-invoked gate = git creation date
  (`git log --follow --diff-filter=A --format=%cs`, LAST output line) < observation floor AND
  corpus span ≥ 30 days; git failure → "age unknown — age gate not applied".
- **D5/D8:** hygiene sweep + proposal blocks are REPORT CONTENT; the miner writes nothing but
  stdout/`--out` (two-tree `_dir_hash` test is the load-bearing invariant, D9).
- **Determinism:** all orderings fixed (usage: total desc then name asc; every other section:
  name/path asc). JSON built in fixed key order.
- **Renderers:** `--markdown` / `--json`; BOTH when neither (SPEC UX — deliberate divergence from
  toolify's markdown-only default).

---

## Phase 1 — Corpus walk + detectors + user-level inventory + ranked table

- [ ] WU-1.1 — `test_skill_usage_miner.py` (RED): import guard, fixture builders
      (`_write_jsonl`, `_assistant_skill_turn`, `_user_slash_turn`, `_mk_skill`, `_dir_hash`),
      detector tests (per-skill counts, separate columns, subagent attribution, distinct
      sessions, plugin/leading-`/` normalization), two-tree read-only test, malformed-line test,
      missing-corpus message test, determinism test, CLI smoke + `--out` test. Run → RED
      (module not importable).
- [ ] WU-1.2 — `skill-usage-miner.py`: importlib reuse of `_iter_log_files`; `extract_hits`
      (value-preserving; per-line timestamp/session/project); user-level `build_inventory`
      (full-frontmatter `name:` scan, dir-name fallback recorded); report assembly + markdown/JSON
      renderers (ranked table, Caveats, empty-corpus message); CLI (`--logs/--markdown/--json/--out`).
      Run tests → GREEN.
- [ ] WU-1.3 — Gates: `test_skill_usage_miner.py` green; `test_toolify_miner.py` still green.


## Phase 2 — Scope + windows

- [ ] WU-2.1 — Tests (RED): repo-scoped inventory row (`repo:<name>` scope) + heuristic
      attribution note; `*-cloud` annotation; `--since` exclusion; 30d-column boundary (anchored
      to corpus max); age gate — old zero-count skill flagged with age, young NOT flagged,
      non-git checkout → age unknown + not flagged; corpus span <30d → gate not met.
- [ ] WU-2.2 — Implement: `repos/*/.claude/skills` inventory glob; attribution
      (project-dir slug substring, case-insensitive); cloud-suffix annotation; `--since` filter +
      observation floor; recency column; `skill_added_date()` git subprocess + the age-gated
      never-invoked split (`never_invoked` vs `zero_unaged` with explicit reasons). GREEN.
- [ ] WU-2.3 — Gates re-run green.


## Phase 3 — Hygiene sweep + archival proposal blocks

- [ ] WU-3.1 — Tests (RED): fixture tree with all four hygiene classes (stray file, dangling
      symlink, lowercase `skill.md`, dispatcher-less dir) each flagged + healthy skill not
      flagged + repo-tree sweep; proposal block contains exact `git mv` + `archived/CLAUDE.md`
      row + evidence line; repo-scoped proposal uses `archived/repo-skills/<repo>/<name>`.
- [ ] WU-3.2 — Implement `hygiene_sweep()` (both trees, classified, deterministic) + proposal
      block assembly on never-invoked rows. GREEN.
- [ ] WU-3.3 — Live-repo validation: run the miner against THIS checkout with a fixture logs
      dir → `## Hygiene` lists exactly `sh.exe.stackdump` (stray file), `remotion` (dangling
      symlink), `local-site/` + `teach/` (case-variant `skill.md`); zero repo-tree findings;
      `git status` clean afterward.


## Phase 4 — Toolify cross-links + Unknown invocations + docs

- [ ] WU-4.1 — Tests (RED): `TOOLIFY_CANDIDATE_THRESHOLD` boundary (>= listed with bar-doc
      cross-link; below not); unknown invocation surfaced with detector counts, not dropped.
- [ ] WU-4.2 — Implement `## Toolify candidates` + `## Unknown invocations`. GREEN.
- [ ] WU-4.3 — Docs rows: `user/scripts/CLAUDE.md` files table, root `CLAUDE.md` scripts table,
      `user/skills/CLAUDE.md` pointer (tightly scoped adds).
- [ ] WU-4.4 — Demonstration run (fixture logs dir + this checkout) recorded below;
      live-corpus run **workstation-deferred** (no `~/.claude/projects` in the cloud lane).
- [ ] WU-4.5 — FULL gate suite green (counts in SKIP_MCP_TEST.md).

