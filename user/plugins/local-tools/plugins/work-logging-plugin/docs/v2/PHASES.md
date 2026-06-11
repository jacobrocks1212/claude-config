# Implementation Phases — Interview Prep Plugin v2

> Phases for [`SPEC.md`](./SPEC.md)

---

### Phase 1: v1 Cleanup & Data Foundation

**Scope:** Remove all dormant v1 subsystems (3 tools, 3 persistence classes, hook system, relevance module). Normalize work-log schema. Add optional `feature` field to work_log_append. Init git repo in ~/.interview-prep/ with auto-commit on writes.

**Risk:** Low — mostly deletions and small additions to well-understood code.

**Deliverables:**
- [ ] Remove `interview_record_findings`, `interview_portfolio_update`, `interview_history` tools from server.py
- [ ] Remove `FindingsWriter`, `PortfolioWriter`, `HistoryLogger` classes from persistence.py
- [ ] Delete hooks/ directory references (already deleted in working tree, just ensure no references remain)
- [ ] Delete relevance.py references (already deleted)
- [ ] Remove test_tools_portfolio_history.py entirely
- [ ] Update test_tools_core.py to remove record_findings tests
- [ ] Update test_server.py to reflect reduced tool set (interview_kb_index, interview_detail, work_log_append)
- [ ] Update test_persistence.py to remove tests for deleted writers
- [ ] Add optional `feature: str | None = None` parameter to `work_log_append` tool
- [ ] Add `feature` field handling in WorkLogWriter.append()
- [ ] Tests: work_log_append with feature field, work_log_append without feature field (backward compat)
- [ ] Create scripts/normalize_work_log.py — normalize old records (date/repo → timestamp/project fields)
- [ ] Create scripts/init_data_repo.py — init git repo in ~/.interview-prep/, create .gitignore (exclude vault/), initial commit
- [ ] Add auto-commit to WorkLogWriter.append() (git add + git commit after successful write)
- [ ] Tests: auto-commit creates git commit after append (use tmp dir with git init)
- [ ] Update persistence.py module docstring to reflect v2 scope
- [ ] Update CLAUDE.md to reflect v2 tool surface

**Prerequisites:** None (first phase)

**Files likely modified:**
- `servers/work_logging_mcp/server.py` — remove 3 tools, add feature param, remove unused imports
- `servers/work_logging_mcp/persistence.py` — remove 3 classes, add auto-commit to WorkLogWriter, update docstring
- `tests/test_server.py` — update EXPECTED_TOOLS, remove record_findings/portfolio/history param tests
- `tests/test_persistence.py` — remove FindingsWriter/PortfolioWriter/HistoryLogger tests, add auto-commit tests
- `tests/test_tools_core.py` — remove interview_record_findings tests
- `tests/test_tools_portfolio_history.py` — DELETE
- `tests/test_tools_work_log.py` — add feature field tests
- `scripts/normalize_work_log.py` — NEW
- `scripts/init_data_repo.py` — NEW
- `CLAUDE.md` — update tool surface documentation

**Testing Strategy:**
Run full quality gates. Verify tool count is 3 (kb_index, detail, work_log_append). Verify work_log_append accepts feature field. Verify auto-commit creates git objects in a test repo. All existing work_log tests still pass (backward compat).

**Integration Notes for Next Phase:**
- persistence.py is now clean: only `WorkLogWriter` and `ConfigReader` remain as active writers
- `feature` field on work log entries enables Phase 3 tagged synthesis
- Auto-commit pattern in WorkLogWriter should be extracted into a reusable `_git_commit()` helper for FeaturesWriter and ImportIndexWriter to use in Phase 2
- server.py imports are reduced — only `WorkLogWriter` needed from persistence

---

### Phase 2: Features Data Layer & Import Pipeline

**Scope:** Build features.jsonl persistence (UUID-based, append-only with upsert-by-id), import-index.jsonl with SHA-256 content hash dedup, the artifact import MCP tool, and the /interview-import skill.

**Risk:** Medium — file scanning and metadata extraction from markdown have edge cases (encoding, nested dirs, missing files).

**Deliverables:**
- [ ] `FeaturesWriter` class in persistence.py:
  - UUID generation for new features
  - Append-only JSONL with query support (by slug, project, id)
  - Upsert by ID (append new record with same UUID, updated timestamp)
  - Required fields: slug, project, title, summary
  - Optional fields: work_log_refs, technologies, patterns, topic_correlations, status
  - Auto-commit after writes (reuse git helper from Phase 1)
- [ ] Tests: FeaturesWriter CRUD, UUID generation, upsert-by-id, query filters, auto-commit
- [ ] `ImportIndexWriter` class in persistence.py:
  - SHA-256 content hash computation
  - Dedup check: exact hash match → skip
  - Evolution check: same path, different hash → new entry with same UUID
  - New entry: new path + new hash → fresh UUID
  - Record schema: uuid, source_path, content_hash, imported_at, project, artifact_type
  - Auto-commit after writes
- [ ] Tests: ImportIndexWriter dedup (same hash skips), evolution (same path new hash), new entry, hash computation
- [ ] `import_artifacts` tool in server.py:
  - Required params: directory (str), project (str)
  - Optional params: artifact_types (list[str] = ["spec", "phases", "research"]), dry_run (bool = False)
  - Scans directory recursively for SPEC.md, PHASES.md, RESEARCH.md files
  - Extracts metadata: title (from first H1), technologies (from content heuristics), file path
  - Checks import-index for dedup before creating entries
  - In dry_run mode, returns proposed entries without writing
  - Creates Feature entries in features.jsonl for each imported artifact
  - Returns: { imported: [...], skipped: [...], total: int }
- [ ] Tests: import tool with fixture directory containing sample SPEC.md files, dedup on re-import, dry_run mode
- [ ] Create `skills/interview-import/SKILL.md` — skill definition for interactive import workflow
- [ ] Update test_server.py EXPECTED_TOOLS to include import_artifacts

**Prerequisites:**
- Phase 1: Clean persistence layer with auto-commit git helper

**Files likely modified:**
- `servers/work_logging_mcp/persistence.py` — add FeaturesWriter, ImportIndexWriter
- `servers/work_logging_mcp/server.py` — add import_artifacts tool, import new writers
- `tests/test_persistence.py` — add FeaturesWriter and ImportIndexWriter tests
- `tests/test_tools_import.py` — NEW, integration tests for import tool
- `tests/test_server.py` — update EXPECTED_TOOLS
- `tests/fixtures/sample-artifacts/` — NEW, fixture SPEC.md/PHASES.md files for testing
- `skills/interview-import/SKILL.md` — NEW

**Testing Strategy:**
Create fixture directory with sample SPEC.md and PHASES.md files. Test import pipeline end-to-end: scan → extract → hash → dedup → write. Verify idempotency by running import twice on same fixtures. Test dry_run returns proposals without writing. Test evolution detection (modify fixture, re-import).

**Integration Notes for Next Phase:**
- FeaturesWriter.query() returns features without topic_correlations populated — Phase 3 fills these
- ImportIndexWriter tracks what's been imported — Phase 3's synthesis should NOT re-process imported artifacts (they're already Features)
- The `artifact_type` field in import-index distinguishes spec/phases/research imports — Phase 3 can use this to weight correlation confidence
- Feature slugs from import use the source file's parent directory name (e.g., `cognito-pay` from `cognito-pay/SPEC.md`)

---

### Phase 3: Feature Synthesis & Topic Correlation

**Scope:** Build LLM-driven feature synthesis (cluster orphaned work log entries into Features) and two-stage topic correlation (semantic candidate retrieval + LLM-as-a-judge evaluation). Wire up /interview-synthesize skill.

**Risk:** High — LLM integration quality is hard to test deterministically. Correlation accuracy depends on prompt engineering.

**Deliverables:**
- [ ] `servers/work_logging_mcp/correlation.py` — NEW module:
  - `get_candidate_topics(feature_summary: str, kb_entries: list, top_k: int = 10) -> list[dict]` — semantic similarity ranking against KB topic descriptions, returns top-k candidates
  - `evaluate_topic_match(feature: dict, topic: dict) -> int` — LLM-as-a-judge scoring (0=irrelevant, 1=tangential, 2=strong match) with strict rubric prompt
  - `correlate_feature(feature: dict, kb: KnowledgeBank) -> list[dict]` — orchestrates candidate retrieval → judge evaluation → returns Score 2 matches only
- [ ] Tests: candidate retrieval returns sorted results, evaluate_topic_match returns valid scores (0-2), correlate_feature filters to Score 2 only (mock LLM responses)
- [ ] `synthesize_features` tool in server.py:
  - Optional params: project (str | None), include_correlations (bool = True)
  - Reads work log entries, identifies orphaned (untagged) entries
  - Groups orphaned entries by project + overlapping file paths
  - Proposes feature groupings with titles and summaries (LLM-generated)
  - If include_correlations=True, runs topic correlation on each proposed feature
  - Writes approved features to features.jsonl with topic_correlations populated
  - Returns: { features_created: [...], orphaned_remaining: int, correlations_added: int }
- [ ] Tests: synthesis with mock work log entries, grouping by project, correlation integration (mocked)
- [ ] Create `skills/interview-synthesize/SKILL.md` — interactive synthesis workflow with user approval step
- [ ] Update test_server.py EXPECTED_TOOLS to include synthesize_features

**Prerequisites:**
- Phase 2: FeaturesWriter for persisting synthesized features, ImportIndexWriter to exclude already-imported work

**Files likely modified:**
- `servers/work_logging_mcp/correlation.py` — NEW
- `servers/work_logging_mcp/server.py` — add synthesize_features tool
- `tests/test_correlation.py` — NEW
- `tests/test_tools_synthesize.py` — NEW
- `tests/test_server.py` — update EXPECTED_TOOLS
- `skills/interview-synthesize/SKILL.md` — NEW

**Testing Strategy:**
Heavy use of mocking for LLM calls. Test correlation.py with deterministic mock responses to verify the two-stage pipeline logic. Test synthesis tool with fixture work log entries and mocked LLM grouping. Verify Score 2 filtering. Verify orphaned entry detection (entries without feature tag that aren't covered by existing features).

**Integration Notes for Next Phase:**
- `topic_correlations` in features.jsonl is the primary input for vault Interview Story generation
- The `evaluate_topic_match` function's rubric prompt is critical — Phase 4's narrative templates reference the correlation score context
- `correlation.py` exposes `get_candidate_topics` which Phase 5 re-uses as an atomic tool
- Features with zero correlations are still valid (they appear in vault 03_Features/ but generate no Interview Stories)

---

### Phase 4: Vault Generation

**Scope:** Build the Obsidian vault generation engine: managed block read/write, domain-specific narrative templates (ISTART for behavioral, ADR for system design, Entity-Pattern-Extensibility for OOD), full vault generator producing 5 collections + Meta, with DAG link topology, Dataview frontmatter, and SRS flashcard formatting.

**Risk:** Medium — largest phase by code volume but well-defined templates and structure. Managed block regex parsing needs careful testing.

**Deliverables:**
- [ ] `servers/work_logging_mcp/managed_blocks.py` — NEW module:
  - `read_managed_block(file_path: Path) -> str | None` — extract content between `<!-- BEGIN MANAGED -->` and `<!-- END MANAGED -->` delimiters
  - `write_managed_block(file_path: Path, content: str) -> None` — replace only managed block content, preserving everything outside delimiters. Create file with delimiters if it doesn't exist.
  - `has_managed_block(file_path: Path) -> bool` — check if file contains managed block delimiters
- [ ] Tests: managed block read/write round-trip, user content preservation, file creation with delimiters, malformed delimiter handling
- [ ] `servers/work_logging_mcp/vault_generator.py` — NEW module:
  - `VaultGenerator` class orchestrating full vault generation
  - `generate_knowledge_bank(kb: KnowledgeBank, features: list, output_dir: Path)` — 154 topic pages with frontmatter + correlated story links
  - `generate_work_history(work_log: list, features: list, output_dir: Path)` — granular log pages linking to parent Feature
  - `generate_features(features: list, output_dir: Path)` — initiative-level pages with outbound links to stories
  - `generate_interview_stories(features: list, kb: KnowledgeBank, output_dir: Path)` — domain-specific narratives using templates
  - `generate_meta(kb: KnowledgeBank, features: list, output_dir: Path)` — dashboard.md with Dataview queries + coverage data
  - DAG link enforcement: Work History → Feature → Story → KB Topic (no shortcuts)
  - Dataview-compatible YAML frontmatter on all generated pages
  - SRS flashcard formatting (:: syntax) in Interview Story managed blocks
  - `#review` tag injection for SRS plugin compatibility
- [ ] Domain-specific narrative template functions:
  - `format_behavioral_istart(feature: dict, topic: dict) -> str` — (I)STAR(T) framework
  - `format_system_design_adr(feature: dict, topic: dict) -> str` — Architecture Decision Record
  - `format_ood_pattern(feature: dict, topic: dict) -> str` — Entity → Pattern → Extensibility
  - `format_algorithm_usage(feature: dict, topic: dict) -> str` — Problem → Approach → Complexity → Your Usage
  - All templates enforce Rule of Three (max 3 challenges per narrative)
- [ ] Tests: vault generator produces correct directory structure, KB pages have correct frontmatter, stories use correct template per domain, DAG links are valid (no Work→KB shortcuts), SRS flashcard syntax present, managed blocks preserve user content
- [ ] `generate_vault` tool in server.py:
  - Optional params: output_dir (str | None = None, defaults to ~/.interview-prep/vault/)
  - Orchestrates full vault generation: reads all data sources, generates all collections
  - Returns: { pages_generated: int, stories_generated: int, topics_covered: int, output_dir: str }
- [ ] Create `skills/interview-generate/SKILL.md` — skill definition for on-demand vault generation
- [ ] Update test_server.py EXPECTED_TOOLS to include generate_vault

**Prerequisites:**
- Phase 3: topic_correlations populated in features.jsonl, correlation module for score context

**Files likely modified:**
- `servers/work_logging_mcp/managed_blocks.py` — NEW
- `servers/work_logging_mcp/vault_generator.py` — NEW
- `servers/work_logging_mcp/server.py` — add generate_vault tool
- `tests/test_managed_blocks.py` — NEW
- `tests/test_vault_generator.py` — NEW
- `tests/test_server.py` — update EXPECTED_TOOLS
- `skills/interview-generate/SKILL.md` — NEW

**Testing Strategy:**
Generate vault into tmp directory. Verify directory structure matches spec (01_Knowledge_Bank/, 02_Work_History/, 03_Features/, 04_Interview_Stories/, Meta/). Parse generated markdown to verify frontmatter schema, link topology (no DAG violations), SRS syntax. Test managed block preservation by generating, adding user content outside blocks, regenerating, verifying user content survives.

**Integration Notes for Next Phase:**
- vault_generator.py's individual generate_* methods become the backing logic for Phase 5's atomic tools
- managed_blocks.py's read/write functions are directly exposed as atomic tools
- The vault generation orchestration pattern (read data → correlate → generate) is what Phase 5's progress reporting wraps

---

### Phase 5: Atomic Tools & Progress Reporting

**Scope:** Expose 7 fine-grained LLM-callable tools for ad-hoc queries and debugging. Add MCP progress notifications for long-running operations. Evolve /interview-check skill to use new infrastructure.

**Risk:** Low — thin wrappers over logic built in Phases 1-4. Progress reporting is the only new concept.

**Deliverables:**
- [ ] 7 atomic MCP tools in server.py:
  - `read_work_log(project: str | None, date_from: str | None, date_to: str | None, feature: str | None) -> dict` — query work-log.jsonl with filters
  - `read_features(project: str | None, slug: str | None, has_correlations: bool | None) -> dict` — query features.jsonl with filters
  - `get_kb_topic(slug: str, domain: str) -> dict` — full KB entry (replaces interview_detail)
  - `get_kb_index() -> dict` — compact topic index (replaces interview_kb_index)
  - `evaluate_topic_match(feature_summary: str, topic_slug: str, topic_domain: str) -> dict` — run LLM judge on a single Feature×Topic pair
  - `write_managed_block(file_path: str, content: str) -> dict` — write to managed block in vault file
  - `calculate_hash(file_path: str) -> dict` — SHA-256 hash for import dedup
- [ ] Rename/replace existing interview_kb_index and interview_detail with the new atomic versions (get_kb_index, get_kb_topic) — ensure backward compatibility or update all references
- [ ] MCP progress notifications for long-running operations:
  - Add progress token support to generate_vault
  - Add progress token support to import_artifacts
  - Add progress token support to synthesize_features
  - Yield progress updates: current count, total count, human-readable message
- [ ] Tests: each atomic tool returns correct shape, progress notifications are yielded during generation (mock verification)
- [ ] Update `skills/interview-check/SKILL.md` — evolve to use KB index + atomic tools for quick topic lookups against recent work
- [ ] Update test_server.py EXPECTED_TOOLS to include all 11 tools (4 composite + 7 atomic)
- [ ] Update CLAUDE.md with final v2 tool surface and MCP tool name mappings

**Prerequisites:**
- Phase 4: vault infrastructure, managed blocks module, all composite tools

**Files likely modified:**
- `servers/work_logging_mcp/server.py` — add 7 atomic tools, add progress notification support to 3 composite tools, rename kb_index/detail
- `tests/test_atomic_tools.py` — NEW
- `tests/test_progress.py` — NEW
- `tests/test_server.py` — update EXPECTED_TOOLS to full 11-tool set
- `skills/interview-check/SKILL.md` — update
- `CLAUDE.md` — final v2 documentation update

**Testing Strategy:**
Test each atomic tool returns expected shape for valid inputs and appropriate errors for invalid inputs. Mock progress token to verify notifications are yielded. Verify final tool count (11 tools). Run full quality gates one final time.

**Integration Notes:**
- This is the final phase. After completion, the full v2 tool surface is: 4 composite + 7 atomic = 11 tools
- The evolved /interview-check can now do quick lookups without vault regeneration
- Progress reporting enables the CLI to display status during long operations

---

### Phase 6: Headless Claude Code Correlation

**Scope:** Replace the placeholder keyword-overlap judge with headless Claude Code invocations (`claude -p --model haiku --output-format json`). First, enrich the 113 imported features with real summaries extracted from their source SPEC/PHASES files (currently all say "Imported from spec: SPEC.md" which gives the judge nothing to work with). Then build a standalone orchestrator script that bulk-processes features through the two-stage correlation pipeline using a real LLM judge. This is a one-time bulk operation — features already correlated are skipped unless `--force` is passed. Also wire the headless judge into the existing `TopicJudge` protocol so future `/interview-synthesize` calls can optionally use it for newly created features.

**Risk:** Medium — subprocess management, JSON parsing from LLM output, and graceful error handling. Haiku is cheap (~113 calls for the full backlog) but malformed responses need retry logic.

**Deliverables:**
- [x] `scripts/enrich_features.py` — pre-processing script to populate real summaries:
  - Reads features.jsonl, filters to features with thin summaries ("Imported from spec/phases/research: ...")
  - For each feature with `source_path`: reads the source file, extracts executive summary section (content between `## Executive Summary` and next `##`, or first ~500 words if no such heading)
  - Constructs a 2-4 sentence summary capturing: what was built, key technical decisions, technologies used, core challenge
  - Can use headless Claude (`claude -p --model haiku`) for summarization, OR extract heuristically (headline + first paragraph under Executive Summary)
  - Upserts enriched summary back to features.jsonl via `FeaturesWriter` (preserves UUID)
  - CLI flags: `--dry-run` (print proposed summaries), `--project` (filter), `--heuristic` (no LLM, just extract text)
  - Progress output: feature N/total, characters extracted per feature
  - Skips features that already have a summary longer than 100 chars (unless `--force`)
- [x] `servers/work_logging_mcp/headless_judge.py` — reusable module:
  - `HeadlessJudge` class implementing `TopicJudge` protocol
  - Constructs strict rubric prompt: feature summary + topic description → score 0/1/2
  - Invokes `claude -p --model haiku --output-format json` via subprocess
  - Parses JSON output, extracts integer score
  - Returns 0 on failure (malformed output, subprocess error), logs warning
  - `BatchHeadlessJudge` class: evaluates multiple candidates in a single Claude call (5-10 per batch)
  - Configurable model (default: haiku) and timeout (default: 30s)
- [x] `scripts/correlate_headless.py` — standalone bulk orchestrator:
  - Reads features.jsonl, skips features that already have `topic_correlations` (unless `--force`)
  - Stage 1: existing `get_candidate_topics()` with word-overlap scorer → top 10 candidates per feature
  - Stage 2: `BatchHeadlessJudge` evaluates candidates via headless Claude, 5 per call
  - Filters to Score 2 only, upserts `topic_correlations` to features.jsonl via `FeaturesWriter`
  - CLI flags: `--dry-run` (print without writing), `--project` (filter), `--force` (re-correlate all)
  - Progress output: feature N/total, scores per batch, final summary
  - Retry: up to 2 retries per batch on malformed JSON or subprocess failure
- [x] Integration with `synthesize_features`:
  - Add optional `use_headless: bool = False` parameter to the tool
  - When True, uses `HeadlessJudge` instead of placeholder judge for newly synthesized features
  - Existing behavior unchanged when False (backward compat, placeholder judge)
- [x] Tests:
  - `test_enrich_extracts_executive_summary` — fixture SPEC with ## Executive Summary, verify extraction
  - `test_enrich_skips_already_rich_summaries` — feature with >100 char summary is skipped
  - `test_enrich_handles_missing_source_file` — logs warning, skips gracefully
  - `test_headless_judge_parses_valid_json` — mock subprocess, verify score extraction
  - `test_headless_judge_handles_malformed_output` — returns 0 on garbage
  - `test_headless_judge_handles_subprocess_failure` — returns 0, logs warning
  - `test_batch_judge_constructs_prompt_correctly` — verify rubric prompt includes feature + all candidates
  - `test_batch_judge_parses_multi_score_response` — verify multiple scores extracted from single response
  - `test_correlate_script_skips_already_correlated` — features with existing correlations are skipped
  - `test_correlate_script_dry_run` — no writes to features.jsonl
- [x] Update CLAUDE.md: document `scripts/enrich_features.py` and `scripts/correlate_headless.py` usage

**Prerequisites:**
- Phase 3: `correlation.py` with `TopicJudge` protocol and `correlate_feature()` pipeline
- Phase 5: `synthesize_features` tool, `FeaturesWriter` with upsert-by-id

**Files likely modified:**
- `scripts/enrich_features.py` — NEW (summary enrichment)
- `servers/work_logging_mcp/headless_judge.py` — NEW
- `scripts/correlate_headless.py` — NEW
- `servers/work_logging_mcp/server.py` — add `use_headless` param to `synthesize_features`
- `tests/test_headless_judge.py` — NEW
- `tests/test_enrich_features.py` — NEW
- `CLAUDE.md` — document script usage

**Testing Strategy:**
Test enrichment with fixture SPEC files containing `## Executive Summary` sections — verify correct extraction and upsert. Mock `subprocess.run` to return known JSON payloads simulating Claude's output for judge tests. Test the full correlation pipeline with fixture features and mocked responses. Integration test both scripts in `--dry-run` mode against the real `~/.interview-prep/features.jsonl`. Manual validation: enrich 5 features, then correlate them, review quality of results.

**Execution order:** Run `enrich_features.py` first (populates summaries), then `correlate_headless.py` (uses enriched summaries for correlation). The enrichment step is idempotent — re-running skips features with >100 char summaries.

**Context from prior phases:**
- `TopicJudge` protocol (correlation.py:13-14): `__call__(self, feature: dict, topic: dict) -> int`
- `correlate_feature()` accepts a `judge` parameter — pass `HeadlessJudge()` instance directly
- `synthesize_features` uses `_judge_impl` (line 360-362 in server.py) — the placeholder returning 1 for all
- `FeaturesWriter.append()` supports upsert-by-id: same UUID → latest record wins in query
- 113 features already imported (99 algobooth + 14 cognito-forms), all with empty `topic_correlations`
- All 113 imported features have thin summaries ("Imported from spec: SPEC.md") — enrichment is prerequisite for correlation
- Features have `source_path` field pointing to original SPEC/PHASES file on disk
- Stage 1 word-overlap scorer is adequate as a cheap narrowing step (154 → 10 candidates) before the expensive LLM call
- Validated via manual test: haiku produces accurate 0/1/2 scores when given a rich feature summary (producer-consumer: 2, pipes-and-filters: 2, observer: 0, strategy: 0, adapter: 1 for audio-pipeline-v2)

**Implementation Notes:**
- `HeadlessJudge` parses Claude CLI's outer `{"type":"result","result":"..."}` envelope, strips markdown fences, extracts `score` key
- `BatchHeadlessJudge.evaluate()` returns `dict[str, int]` mapping slug→score in a single subprocess call
- `extract_summary()` uses regex to find `## Executive Summary` section, falls back to first ~500 words after title
- `correlate_features()` loads KB entries at runtime (graceful failure in test context since `get_candidate_topics` is mocked)
- Judge selection in `synthesize_features` moved outside per-project loop — selected once before iteration
- All 133 tests pass, mypy strict clean, ruff clean
- New files: `scripts/enrich_features.py`, `scripts/correlate_headless.py`, `servers/work_logging_mcp/headless_judge.py`
- New test files: `tests/test_enrich_features.py` (4 tests), `tests/test_headless_judge.py` (6 tests), `tests/test_correlate_headless.py` (4 tests)
- Modified: `servers/work_logging_mcp/server.py` (`use_headless` param), `tests/test_tools_synthesize.py` (2 tests), `CLAUDE.md`

---

### Phase 7: Rich Knowledge Bank Pages

**Scope:** Render the `talking_points` and `related_topics` data that already exists in KB YAML entries but is currently dropped by the vault generator. Pure rendering fix — no LLM calls, no new modules.

**Deliverables:**
- [x] Render `talking_points` as a `## Key Concepts` section on KB pages (bulleted list, each point as a paragraph under a bold sub-heading extracted from the first sentence)
- [x] Render `related_topics` as a `## Related Topics` section with Obsidian `[[wikilinks]]` to sibling KB pages
- [x] Pass `related_topics` from `server.py` into `kb_data` dict (currently omitted)
- [x] Tests: verify `generate_knowledge_bank()` output includes talking points and related topics when present, and gracefully omits sections when data is empty
- [ ] Regenerate vault to verify rendering

**Implementation Notes:**
- KB page section order: Title → Description → Key Concepts → Related Stories → Interview Questions → Related Topics
- 4 new tests in `test_vault_generator.py`: renders talking_points, omits when empty, renders related_topics with wikilinks, omits when empty
- All 139 tests pass, mypy strict clean, ruff clean

**Prerequisites:**
- Phase 4: `vault_generator.py` with `generate_knowledge_bank()` method
- Phase 5: `generate_vault` tool

**Files likely modified:**
- `servers/work_logging_mcp/vault_generator.py` — add Key Concepts and Related Topics sections to `generate_knowledge_bank()`
- `servers/work_logging_mcp/server.py` — add `related_topics` to `kb_data` dict construction (~line 415)
- `tests/test_vault_generator.py` — new tests for talking points and related topics rendering

**Testing Strategy:**
Unit test `generate_knowledge_bank()` with fixture KB data containing talking_points and related_topics. Verify markdown output contains expected sections. Test edge case: KB entry with no talking_points or no related_topics should not render empty sections. Manual validation: regenerate vault, open a KB page in Obsidian, confirm Key Concepts and Related Topics render correctly with working wikilinks.

**Context from prior phases:**
- `talking_points` is a list of strings in the KB YAML, typically 3-5 paragraphs of ~150 words each
- `related_topics` is a list of slug strings (e.g., `[message-queues, microservices, cap-theorem]`)
- `server.py` lines 407-420 build `kb_data` dict — currently includes `talking_points` but NOT `related_topics`
- `vault_generator.py` `generate_knowledge_bank()` receives `kb_data` but only renders `description`, `interview_questions`, and related stories — ignores `talking_points` entirely
- KB page path format: `vault/01_Knowledge_Bank/{domain}/{slug}.md`
- Related topic wikilinks should resolve to `[[{slug}]]` which Obsidian will find across subdirectories

---

### Phase 8: Interactive Study Sessions

**Scope:** Replace pre-generated LLM narratives with an interactive study workflow. Generate a vault-level CLAUDE.md during vault generation that teaches Claude Code the vault structure and study persona. Add an `/interview-study` skill that bootstraps topic-focused study sessions using the user's real work as context. Stories are elaborated on-demand during study, written into managed blocks via `write_managed_block`.

**Why this over pre-generated narratives:** Pre-generated text is stale the moment it's written. An interactive session adapts depth to the target role, drills into weak areas, and lets the user refine talking points conversationally. The managed block pattern already supports this — Claude writes into `<!-- BEGIN MANAGED -->` blocks during study and the content persists across vault regenerations.

**Deliverables:**
- [x] Generate `vault/CLAUDE.md` during `generate_meta()` — explains vault structure, collection purposes, navigation patterns, study persona, and how to use MCP tools for context loading
- [x] `/interview-study` skill — accepts topic slug, domain, or "all" for guided study
  - Loads KB entry + correlated features + work log refs via MCP tools
  - Presents context summary and enters Socratic Q&A mode
  - Can generate domain-specific narratives on demand (STAR, ADR, Entity-Pattern, etc.)
  - Writes elaborated stories into managed blocks when user is satisfied
  - Tracks which stories have been elaborated vs. still placeholder
- [x] `get_study_context` MCP tool — bundles KB entry + correlated features with summaries + relevant work log entries into a single response (reduces round-trips during study)
- [x] Tests: `test_study_context.py` — verify study context tool aggregates data correctly, handles missing correlations, returns empty gracefully
- [x] Tests: verify `generate_meta()` produces vault CLAUDE.md with expected sections
- [ ] Manual validation: open vault in Claude Code, run `/interview-study rate-limiting`, verify context loads and study flow works

**Prerequisites:**
- Phase 5: Atomic MCP tools (`get_kb_topic`, `read_features`, `read_work_log`, `write_managed_block`)
- Phase 7: Rich KB pages (so study flow makes sense end-to-end)

**Files likely modified:**
- `servers/work_logging_mcp/vault_generator.py` — add vault CLAUDE.md generation to `generate_meta()`
- `servers/work_logging_mcp/server.py` — add `get_study_context` tool
- `skills/interview-study/SKILL.md` — NEW skill definition
- `tests/test_study_context.py` — NEW
- `tests/test_vault_generator.py` — test for vault CLAUDE.md generation
- `CLAUDE.md` — document `/interview-study` skill and study context tool

**Testing Strategy:**
Unit test `get_study_context` with fixture data: KB entry with correlations → returns bundled context. Test missing topic → error. Test topic with no correlations → returns KB entry only. Test vault CLAUDE.md generation: verify it contains vault structure description and navigation patterns. Manual validation: start Claude Code session in vault directory, run `/interview-study`, confirm context loads and managed block writes work.

**Context from prior phases:**
- `write_managed_block` (Phase 5) writes content between `<!-- BEGIN MANAGED -->` delimiters
- `get_kb_topic` returns full KB entry with talking_points, related_topics, interview_questions
- `read_features` returns features with `topic_correlations` linking features to KB topics
- Current story pages have placeholder templates in managed blocks — interactive study replaces these with real narratives
- SRS flashcard `::` syntax in managed blocks — study sessions should generate better flashcard answers from actual discussion
- Domain-specific templates exist in `vault_generator.py` (`_format_behavioral`, `_format_system_design`, etc.) — the skill can reference these formats as guidance
