# Implementation Phases — Skill Usage Miner + Dead-Weight Audit

> Phases for [`SPEC.md`](./SPEC.md)

**Status:** In Progress

**MCP runtime:** not-required — pure claude-config harness tooling (a stdlib-only, read-only
Python analysis script + its test file + doc rows). No Tauri app, no MCP-reachable surface;
validation is `test_skill_usage_miner.py` (fixture corpora + fixture skills trees), the existing
gate suite, and a demonstration run against a fixture logs dir. This is the
`standalone — no app integration` untestable class → `SKIP_MCP_TEST.md` at the MCP gate.

## Cross-feature Integration Notes

`**Depends on:** (none)`. Substantive dependencies are implemented contracts, not sibling specs:

- **`toolify-miner.py` (shipped, unified-pipeline-orchestrator Phase 4):** this feature imports
  its `_iter_log_files` corpus walk via `importlib.util.spec_from_file_location` (D1) and mirrors
  its read-only invariant + test shape (`_dir_hash`, D9). The sibling is untouched except as an
  import source.
- **`mine-sessions` skill (shipped):** transcript anatomy (encoded-cwd project dirs, subagent
  transcripts at `<parent>/subagents/agent-*.jsonl`, per-line ISO `timestamp`) and the
  field-proven slash-marker regex at `scripts/digest_sessions.py:125`, reused verbatim (D2).
- **`archived/CLAUDE.md` convention:** the D8 proposal blocks emit its exact row format; this
  miner never executes an archival.
- **`toolify-auto-promotion` (sibling spec, decoupled):** the `## Toolify candidates` section
  cross-links `docs/features/unified-pipeline-orchestrator/toolify-bar.md` (D7, annotate-only);
  this miner never invokes the sequence miner or the promotion pipeline.

**Cloud-lane note:** `~/.claude/projects` does not exist in this environment; the live-corpus
run (and the SPEC's "deferred empirical checks" over real transcripts) are
**workstation-deferred**. All behavior is fixture-validated; a demonstration run against a
fixture logs dir + the real repo checkout (inventory/hygiene/age-gate side) is recorded in the
plan's implementation notes.

---

### Phase 1: Corpus walk + detectors + user-level inventory + ranked table

**Phase kind:** design

**Scope:** The sibling script `user/scripts/skill-usage-miner.py`: importlib reuse of
`_iter_log_files` (D1), both detectors with separate columns (D2), a value-preserving extractor
(Skill-tool `tool_use` → `input["skill"]`, normalized: leading `/` and `plugin:`-style prefixes
stripped; user-turn text → the `digest_sessions.py:125` regex), per-hit records
(skill, detector, session key, timestamp, project dir), subagent transcripts attributed to their
parent session, the user-level inventory (frontmatter `name:` with dir-name fallback), the ranked
usage table (count desc, then name — deterministic), distinct-session + last-seen columns,
markdown + JSON renderers, the standing Caveats block, the explicit
"no corpus found at <path>" empty-corpus report, and the CLI (`--logs`, `--markdown`, `--json`,
`--out`; both formats when neither flag).

**Deliverables:**
- [x] `user/scripts/skill-usage-miner.py` — corpus walk (imported `_iter_log_files`), detector 1
      (Skill-tool, incl. `subagents/agent-*.jsonl`), detector 2 (slash markers), name
      normalization, session/project/timestamp per hit, malformed-line graceful skip.
- [x] User-level inventory: `user/skills/*/SKILL.md` glob + full-frontmatter `name:` scan
      (dir-name fallback flagged for Phase 3 hygiene).
- [x] Ranked markdown table (`rank | skill | scope | skill-tool | slash | sessions | last seen |
      30d | notes`) + JSON schema; deterministic ordering (total desc, name asc).
- [x] Standing `## Caveats` block (false negatives: component injection, auto-invoke prose,
      off-workstation sessions; zero = investigate, never proof of deadness).
- [x] Empty/missing corpus → explicit `no corpus found at <path>` line, never a bare empty table.
- [x] `user/scripts/test_skill_usage_miner.py` — fixture transcripts (Skill tool_use, command-name
      markers, subagent file, malformed line), per-skill counts + distinct sessions, separate
      detector columns, the two-tree read-only `_dir_hash` test (fixture logs dir AND fixture
      skills tree), deterministic-output diff test, missing-logs-dir message, CLI smoke
      (`--json` parses; logs byte-unchanged; `--out` writes only the named file).

**Minimum Verifiable Behavior:** A fixture corpus with 2 sessions (one Skill-tool invocation of
`commit` in a subagent transcript, two `<command-name>/commit</command-name>` markers) plus a
fixture skills tree containing `commit/SKILL.md` renders a table row for `commit` with
skill-tool=1, slash=2, sessions=2, and both fixture trees hash byte-identical before/after.

**Runtime Verification** *(checked by integration test or manual testing — NOT by the implementation agent):*
- [x] Skill-tool + slash hits counted separately, incl. subagent transcripts; distinct sessions correct. *(Evidence: `test_skill_usage_miner.py` detector tests.)* <!-- verification-only -->
- [x] Read-only over BOTH trees: fixture logs dir + fixture skills tree byte-identical before/after a full run. *(Evidence: mirrored `_dir_hash` test.)* <!-- verification-only -->
- [x] Malformed JSONL tolerated; missing logs dir → explicit message. *(Evidence: `test_skill_usage_miner.py`.)* <!-- verification-only -->

**MCP Integration Test Assertions:** N/A — no MCP-reachable surface (claude-config has no
Tauri/MCP app). Verification is `test_skill_usage_miner.py`.

**Prerequisites:** None (first phase).

**Files likely modified:** `user/scripts/skill-usage-miner.py` (new),
`user/scripts/test_skill_usage_miner.py` (new).

**Testing Strategy:** TDD — the test file lands first (RED: module not importable), then the
script. Fixture builders mirror `test_toolify_miner.py` (`_write_jsonl`, assistant/user turn
builders, `_dir_hash`). All tests both pytest-discoverable and runnable via the in-file `_TESTS`
runner.

**Integration Notes for Next Phase:** Phase 2 extends the same hit records with window filtering
(`--since`), the corpus-max-anchored 30-day recency column, the repo-scoped inventory, and the
git-age gate — no re-parse needed; the extractor already records timestamps + project dirs.

---

### Phase 2: Scope + windows (repo-scoped inventory, `--since`, recency, age gate)

**Phase kind:** design

**Scope:** D4 + D3. Repo-scoped inventory (`repos/<name>/.claude/skills/*/SKILL.md`, scope label
`repo:<name>`), heuristic per-repo attribution (share of a repo-scoped skill's hits whose
encoded-cwd project dir contains the repo slug — labeled heuristic in the notes column),
cloud-variant annotation (`*-cloud` → `cloud-biased undercount`), `--since YYYY-MM-DD` filter,
the 30-day recency column anchored to the newest corpus timestamp (byte-stable), and the
never-invoked gate: zero-count skills get one
`git log --follow --diff-filter=A --format=%cs -- <SKILL.md>` subprocess; flagged never-invoked
only when the creation date predates the observation floor (oldest scanned timestamp, raised by
`--since`) AND the corpus spans ≥ 30 days; git failure degrades to
"age unknown — age gate not applied".

**Deliverables:**
- [x] Repo-scoped inventory rows with `repo:<name>` scope + per-repo heuristic attribution note.
- [x] `*-cloud` skills annotated `cloud-biased undercount` (never ranked naively).
- [x] `--since` filter (hits before the date excluded; observation floor raised accordingly).
- [x] 30-day recency column (`30d`), anchored to newest corpus timestamp.
- [x] Age-gated `## Never invoked` list + `### Zero invocations — age gate not met` subsection
      (young skill / age-unknown / short-corpus reasons made explicit).
- [x] Tests: zero-count skill YOUNGER than the corpus floor NOT flagged; older skill flagged with
      age; non-git checkout → age unknown, not flagged, no crash; `--since` exclusion; recency
      column boundary; repo-scope + attribution + cloud annotation fixtures.

**Minimum Verifiable Behavior:** In a fixture git repo with two zero-count skills — one committed
before the corpus's oldest timestamp, one after — over a ≥30-day fixture corpus, only the old
skill appears under `## Never invoked` (with its age); the young one appears under the
age-gate-not-met subsection.

**Runtime Verification** *(checked by integration test or manual testing — NOT by the implementation agent):*
- [x] Never-invoked age gate: young zero-count skill absent from the archival list; old one present with age. *(Evidence: `test_skill_usage_miner.py` age-gate fixtures.)* <!-- verification-only -->
- [x] `--since` + recency column behave per D3 (deterministic given fixed corpus). *(Evidence: window tests.)* <!-- verification-only -->

**MCP Integration Test Assertions:** N/A — no MCP-reachable surface.

**Prerequisites:** Phase 1 (hit records with timestamps + project dirs; inventory machinery).

**Files likely modified:** `user/scripts/skill-usage-miner.py`,
`user/scripts/test_skill_usage_miner.py`.

**Testing Strategy:** Fixture git repos built with `git init` + backdated
`GIT_AUTHOR_DATE`/`GIT_COMMITTER_DATE` commits; fixture corpora with controlled timestamp spans.

**Integration Notes for Next Phase:** Phase 3's proposal blocks consume the never-invoked rows
(evidence line = sessions + span + age) — the gate's output shape is the contract.

---

### Phase 3: Hygiene sweep + archival proposal blocks

**Phase kind:** design

**Scope:** D5 + D8. The `## Hygiene` section over BOTH trees: top-level entries that are not
`CLAUDE.md`, `_components/`, or a dir containing `SKILL.md` — classified as stray file, dangling
symlink (target unresolvable from the repo — flagged, not auto-classified), case-variant
dispatcher (`skill.md`), or missing dispatcher; plus malformed-frontmatter fallbacks from
Phase 1. The `## Never invoked` entries carry D8 proposal blocks: the ready-to-paste `git mv`
command (`archived/user-skills/<name>` or `archived/repo-skills/<repo>/<name>`), the
`archived/CLAUDE.md` row text in the existing `| Archived | Replaced by | When |` convention, and
the evidence line. The miner never executes any of it (covered by the two-tree hash test).

**Deliverables:**
- [x] Hygiene sweep over `user/skills/` + every `repos/*/.claude/skills/`, with the four
      classifications; deterministic ordering.
- [x] D8 proposal blocks (git mv + archived/CLAUDE.md row + evidence line) attached to each
      never-invoked row; scope-aware destination paths.
- [x] Tests: fixture tree reproducing all four hygiene classes (stray file, dangling symlink,
      lowercase `skill.md`, dir with no dispatcher) all flagged, healthy skill NOT flagged;
      proposal-block text contains the exact `git mv` + row text; nothing executed.
- [x] Live-repo validation: run against this checkout — the four known findings
      (`sh.exe.stackdump`, `remotion`, `local-site/`, `teach/`) appear and no other user-skill
      false positive does. *(Ran 2026-07-04 against the lane checkout: exactly the four expected
      user-tree findings; zero findings across both repo trees — recorded in the plan's
      implementation notes.)*

**Minimum Verifiable Behavior:** A run against the real checkout lists exactly
`sh.exe.stackdump` (stray file), `remotion` (dangling symlink), `local-site/` + `teach/`
(case-variant dispatcher) under `## Hygiene`, and `git status` stays clean.

**Runtime Verification** *(checked by integration test or manual testing — NOT by the implementation agent):*
- [x] The four real hygiene findings appear against the live tree with no other user-skill false positives. *(Evidence: demonstration run, plan implementation notes.)* <!-- verification-only -->
- [x] Proposals never executed: full run leaves the checkout `git status`-clean. *(Evidence: two-tree hash test + demo run.)* <!-- verification-only -->

**MCP Integration Test Assertions:** N/A — no MCP-reachable surface.

**Prerequisites:** Phase 2 (never-invoked rows feed the proposal blocks).

**Files likely modified:** `user/scripts/skill-usage-miner.py`,
`user/scripts/test_skill_usage_miner.py`.

**Testing Strategy:** Fixture skills trees with deliberate defects (symlink creation guarded —
POSIX symlinks available in this environment); string assertions on the proposal block; the
Phase 1 hash test re-covers non-execution.

**Integration Notes for Next Phase:** Phase 4 adds the remaining report sections + docs; the
report assembly function is already section-oriented, so new sections slot in without reshaping.

---

### Phase 4: Toolify cross-links + Unknown invocations + docs

**Phase kind:** integration

**Scope:** D7 annotate-only `## Toolify candidates` section (skills whose total invocations ≥ the
documented `TOOLIFY_CANDIDATE_THRESHOLD`, each cross-linked to
`docs/features/unified-pipeline-orchestrator/toolify-bar.md` with the "run toolify-miner.py over
the invoking sessions" next step); the `## Unknown invocations` section (log-seen names absent
from the inventory — renamed/archived/plugin skills — never silently dropped); doc rows in
`user/scripts/CLAUDE.md` and the root `CLAUDE.md` script table; a pointer from
`user/skills/CLAUDE.md` to the audit tool; the demonstration run.

**Deliverables:**
- [x] `## Toolify candidates` (threshold constant documented in the module; annotate-only).
- [x] `## Unknown invocations` section.
- [x] Doc rows: `user/scripts/CLAUDE.md` files table, root `CLAUDE.md` scripts table,
      `user/skills/CLAUDE.md` pointer.
- [x] Tests: threshold boundary (at/below); unknown invocation surfaced with counts.
- [x] Demonstration run against this repo checkout with a fixture logs dir (output recorded in
      the plan's implementation notes). Live-corpus run: **workstation-deferred** (no
      `~/.claude/projects` in this environment).

**Minimum Verifiable Behavior:** A fixture skill with ≥ threshold total hits appears under
`## Toolify candidates` with the bar-doc cross-link; a fixture invocation of a non-inventory
skill appears under `## Unknown invocations` with its counts.

**Runtime Verification** *(checked by integration test or manual testing — NOT by the implementation agent):*
- [x] Threshold + unknown-invocation behavior per D7/SPEC. *(Evidence: `test_skill_usage_miner.py`.)* <!-- verification-only -->
- [x] Docs/lint consistency green after the doc rows. *(Evidence: `lint-skills.py` clean; gate suite.)* <!-- verification-only -->

**MCP Integration Test Assertions:** N/A — no MCP-reachable surface.

**Prerequisites:** Phases 1–3.

**Files likely modified:** `user/scripts/skill-usage-miner.py`,
`user/scripts/test_skill_usage_miner.py`, `user/scripts/CLAUDE.md`, `CLAUDE.md`,
`user/skills/CLAUDE.md`.

**Testing Strategy:** Section-content string assertions on fixture runs; full gate suite as the
final acceptance; `lint-skills.py` for the doc edits (no SKILL.md/component bodies change, so no
projection change expected).
