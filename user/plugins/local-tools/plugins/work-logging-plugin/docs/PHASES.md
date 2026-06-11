# Implementation Phases — Interview Prep Plugin

> Phases for [`SPEC.md`](./SPEC.md)

---

### Phase 1: Plugin Scaffold + MCP Server Skeleton

**Scope:** Create the new `work-logging-plugin` repository with the full directory layout from the spec, wire up the Python MCP server with stdio transport, register all four tool stubs (returning not-implemented), and establish the test infrastructure.

**Deliverables:**
- [x] Repository at `~/source/repos/work-logging-plugin/` with the spec's directory layout
- [x] `.claude-plugin/plugin.json` manifest (name, description, version)
- [x] `.mcp.json` transport config (stdio, Python entry point)
- [x] `servers/work_logging_mcp/server.py` — MCP server that starts, registers 4 tools, each returns a structured "not yet implemented" response
- [x] `servers/work_logging_mcp/__init__.py`, `requirements.txt` (mcp SDK, pydantic, pyyaml)
- [x] `pyproject.toml` with dev dependencies (pytest, mypy, ruff)
- [x] Placeholder `CLAUDE.md` at plugin root (draft auto-invocation instructions)
- [x] Tests: server starts without error, all 4 tools are registered and callable

**Prerequisites:** None (first phase)

**Files likely created:**
- `.claude-plugin/plugin.json` — plugin manifest
- `.mcp.json` — MCP server transport config
- `servers/work_logging_mcp/server.py` — tool registration + stubs
- `servers/work_logging_mcp/__init__.py` — package init
- `servers/work_logging_mcp/requirements.txt` — runtime deps
- `pyproject.toml` — project config + dev deps
- `CLAUDE.md` — placeholder plugin instructions
- `tests/conftest.py` — shared fixtures
- `tests/test_server.py` — server startup + tool registration tests

**Testing Strategy:**
Test that the MCP server process starts, exposes the expected tool names via the MCP protocol, and that each stub returns a well-formed response. No knowledge bank or persistence needed — pure wiring verification.

**Integration Notes for Next Phase:**
- The `server.py` tool handlers will be thin dispatchers — Phase 2+ fills in the actual logic modules they delegate to.
- `requirements.txt` must include `pyyaml` and `pydantic` from the start since Phase 2 uses them immediately.
- Choose an MCP SDK early (e.g., `mcp` PyPI package) — the tool registration pattern established here is reused by all subsequent phases.

#### Implementation Notes (Phase 1)
**Completed:** 2026-04-21
**Work completed:**
- Repo scaffolded at `C:/Users/JacobMadsen/source/repos/work-logging-plugin/` with git + GitHub remote
- All 4 tool stubs registered with spec-matching signatures, each returning `{"status": "not_implemented"}`
- `mcp` SDK v1.27.0 installed; `FastMCP` used for tool registration
- 3 tests: tool listing, stub responses, required params validation
**Integration notes:**
- MCP test pattern: `from mcp.shared.memory import create_connected_server_and_client_session` — use `mcp._mcp_server` as arg
- `pytest-asyncio` with `asyncio_mode = "auto"` — plain `async def test_*` functions work, no decorator needed
- `json.loads(result.content[0].text)` to parse tool call responses in tests (type ignore `union-attr`)
- Build backend: `setuptools.build_meta` with explicit `[tool.setuptools.packages.find]` include
**Pitfalls & guidance:**
- Python 3.14 venv works fine with `mcp>=1.0` — no compatibility issues
- `pyproject.toml` needs `[tool.setuptools.packages.find] include = ["servers*", "tests*"]` or setuptools can't discover packages
**Files created/modified:**
- `.claude-plugin/plugin.json` — plugin manifest
- `.mcp.json` — MCP stdio transport config (uses `uv run`)
- `pyproject.toml` — project config, deps, tool config
- `servers/work_logging_mcp/server.py` — FastMCP server with 4 tool stubs
- `tests/test_server.py` — 3 server wiring tests
- `tests/conftest.py` — fixtures_dir fixture

---

### Phase 2: Knowledge Bank Schema + Loader

**Scope:** Define the Pydantic models for knowledge bank entries (matching the YAML schema in the spec), build a directory loader that validates all YAML files under `~/.interview-prep/knowledge-bank/`, and implement tag-based keyword matching for relevance queries.

**Deliverables:**
- [x] `servers/work_logging_mcp/knowledge_bank.py` — `KnowledgeBankEntry` Pydantic model, `KnowledgeBank` loader class, `query_by_tags()` method
- [x] Pydantic model fields: `slug`, `name`, `domain` (enum: system-design, behavioral, algorithms, ood), `tags` (list[str]), `description`, `interview_questions` (list[str]), `talking_points` (list[str]), `related_topics` (list[str]), `difficulty` (enum: beginner, intermediate, advanced)
- [x] YAML validation on load — malformed files logged and skipped, not fatal
- [x] `query_by_tags(tags: list[str], threshold: int)` — returns entries sorted by tag-overlap count, filtered by minimum threshold
- [x] 3-5 sample YAML fixtures for testing (covering each domain)
- [x] Tests: schema validation (valid + invalid YAML), loader (directory scan), query matching (exact, partial, no-match)

**Prerequisites:** Phase 1 (package structure, dependencies)

**Files likely created/modified:**
- `servers/work_logging_mcp/knowledge_bank.py` — schema + loader + query
- `tests/test_knowledge_bank.py` — unit tests
- `tests/fixtures/knowledge-bank/` — sample YAML files per domain

**Testing Strategy:**
Unit tests with sample YAML fixtures in the test directory. Test the full load → validate → query pipeline. Edge cases: empty directory, malformed YAML (should skip gracefully), duplicate slugs, entries with no tags.

**Integration Notes for Next Phase:**
- `KnowledgeBankEntry` is the canonical type that flows through the entire system — findings reference it, history logs its slug, portfolio links to it.
- `query_by_tags()` is what `interview_relevance_check` calls in Phase 4. The threshold parameter is configurable (spec default: 0.7, but tag-overlap scoring may use a count threshold instead — calibrate during Phase 4).
- The loader accepts a configurable `base_path` (default `~/.interview-prep/knowledge-bank/`) for testability — tests pass a tmp_path fixture.

#### Implementation Notes (Phase 2)
**Completed:** 2026-04-21
**Work completed:**
- `Domain(StrEnum)` and `Difficulty(StrEnum)` enums with kebab-case values
- `KnowledgeBankEntry(BaseModel)` with all spec fields, Pydantic validation
- `KnowledgeBank(base_path)` loader — walks `{domain}/*.yaml`, validates, indexes by `(slug, domain)`
- `query_by_tags()` — set intersection, sorted desc by overlap count, filtered by threshold
- `get(slug, domain)` — O(1) dict lookup
- 5 fixture YAML files (4 valid + 1 malformed), 11 passing tests
**Integration notes:**
- Import: `from servers.work_logging_mcp.knowledge_bank import KnowledgeBank, KnowledgeBankEntry, Domain, Difficulty`
- `KnowledgeBank(base_path)` — the constructor does all loading; no separate `.load()` call
- `query_by_tags()` returns `list[tuple[KnowledgeBankEntry, int]]` (entry, overlap_count)
- Duplicate slug+domain entries are logged and skipped
- Test fixtures at `tests/fixtures/knowledge-bank/{domain}/*.yaml`
**Pitfalls & guidance:**
- `Domain` enum values are kebab-case strings (`"system-design"`, not `"SYSTEM_DESIGN"`) — use `.value` when constructing paths
**Files created/modified:**
- `servers/work_logging_mcp/knowledge_bank.py` — schema + loader + query
- `tests/test_knowledge_bank.py` — 11 unit tests
- `tests/fixtures/knowledge-bank/` — 5 fixture YAML files

---

### Phase 3: Persistence Layer

**Scope:** Build the writers and readers for all persistent data: findings (topic-organized Markdown files), portfolio (project/feature Markdown files), encounter history (JSONL), and user config (JSON). Auto-create the `~/.interview-prep/` directory tree on first write.

**Deliverables:**
- [x] `servers/work_logging_mcp/persistence.py` — `FindingsWriter`, `PortfolioWriter`, `HistoryLogger`, `ConfigReader`
- [x] `FindingsWriter.append(domain, topic_slug, finding)` — appends a structured Markdown section to `~/.interview-prep/findings/{domain}/{topic_slug}.md`, creating the file if needed
- [x] `PortfolioWriter.upsert(project, feature_slug, entry)` — creates or overwrites `~/.interview-prep/portfolio/{project}/{feature_slug}.md`
- [x] `HistoryLogger.log(encounter)` — appends a JSON line to `~/.interview-prep/history.jsonl` with fields: topic, domain, date (ISO), project, context, type ("passive")
- [x] `HistoryLogger.query(date_range?, topic?, domain?)` — reads and filters history.jsonl
- [x] `ConfigReader.load()` — reads `~/.interview-prep/config.json` (threshold, preferences), returns defaults if missing
- [x] Directory tree auto-creation on first write operation
- [x] Tests: write/read round-trips for each writer, directory auto-creation, history filtering, config defaults

**Prerequisites:** Phase 2 (`KnowledgeBankEntry` model referenced by findings and history)

**Files likely created/modified:**
- `servers/work_logging_mcp/persistence.py` — all writers/readers
- `tests/test_persistence.py` — unit tests
- (tests use `tmp_path` fixture — no real `~/.interview-prep/` touched)

**Testing Strategy:**
All tests use pytest's `tmp_path` to create an isolated `~/.interview-prep/` equivalent. Test write → read round-trips, append behavior (findings should accumulate, not overwrite), history JSONL line format, config defaults when file is missing, and directory auto-creation from scratch.

**Integration Notes for Next Phase:**
- Each writer accepts a `base_path` parameter (same pattern as knowledge bank loader) for testability.
- `FindingsWriter.append()` returns the file path it wrote to — this becomes `persisted_to` in the MCP tool response.
- `HistoryLogger` is called as a side effect by `interview_relevance_check` (Phase 4) and directly by `interview_history` (Phase 5).
- The Markdown format for findings should be stable — it accumulates examples over time. Use `## {date} — {project}` as section headers for each appended finding.

#### Implementation Notes (Phase 3)
**Completed:** 2026-04-21
**Work completed:**
- `FindingsWriter` — append-only Markdown with `## date — project` sections, `mode="a"`
- `PortfolioWriter` — full overwrite Markdown with `mode="w"`, structured sections
- `HistoryLogger` — JSONL append + streaming query with date/topic/domain filters
- `ConfigReader` — JSON loader with defaults `{"relevance_threshold": 0.7, "stale_days": 30}`
- 15 passing tests covering all write/read round-trips
**Integration notes:**
- Import: `from servers.work_logging_mcp.persistence import FindingsWriter, PortfolioWriter, HistoryLogger, ConfigReader`
- All classes accept `base_path: Path` (default `Path.home() / ".interview-prep"`)
- `FindingsWriter.append()` returns `Path` to the file — use `str(path)` for `persisted_to` in tool responses
- `HistoryLogger.query()` uses keyword args: `date_from`, `date_to`, `topic`, `domain`
- `PortfolioWriter.upsert()` entry dict uses `Any` typed values — lists for `key_decisions`, `tradeoffs`, `patterns_used`
**Pitfalls & guidance:**
- Date filtering is lexicographic ISO string comparison — works correctly for ISO dates
- `ConfigReader.load()` returns a fresh `dict` copy of defaults (safe to mutate)
**Files created/modified:**
- `servers/work_logging_mcp/persistence.py` — all 4 classes
- `tests/test_persistence.py` — 15 unit tests

---

### Phase 4: Core MCP Tools — `interview_relevance_check` + `interview_detail`

**Scope:** Replace the Phase 1 stubs for the two read-side tools with real implementations. `interview_relevance_check` accepts a work summary + changed files, queries the knowledge bank by extracted tags, persists findings + history as side effects, and returns compact match objects. `interview_detail` returns the full knowledge bank entry for a given topic.

**Deliverables:**
- [x] `servers/work_logging_mcp/relevance.py` — tag extraction from work summary (keyword splitting + normalization), relevance scoring (tag overlap + optional domain weighting), result formatting (compact ~200 tokens per match)
- [x] `interview_relevance_check` tool handler wired to: relevance.py → knowledge_bank.py → persistence.py (findings + history side effects)
- [x] `interview_detail` tool handler wired to knowledge_bank.py (full entry lookup by slug + domain)
- [x] Compact result schema: `{topic, domain, relevance_score, summary, interview_angle, talking_points, star_hook?, persisted_to}`
- [x] Tests: tag extraction, scoring, end-to-end tool call with mock KB (assert output shape + side effects)

**Prerequisites:** Phase 2 (knowledge bank) + Phase 3 (persistence)

**Files likely created/modified:**
- `servers/work_logging_mcp/relevance.py` — matching logic + result formatting
- `servers/work_logging_mcp/server.py` — replace stubs with real handlers
- `tests/test_relevance.py` — unit tests for matching logic
- `tests/test_tools_core.py` — integration tests for the two tools

**Testing Strategy:**
Unit-test the relevance module in isolation (tag extraction, scoring). Integration-test the full tool handler with a fixture knowledge bank and tmp_path persistence. Assert: correct matches returned, findings file created, history line appended, detail tool returns full entry. Edge cases: no matches (empty result, no side effects), work summary with no extractable tags.

**Integration Notes for Next Phase:**
- The relevance scoring threshold (spec suggests 0.7) controls what gets returned vs silently logged. Below-threshold matches should still be logged to history as type "passive" with a "below_threshold" flag — this feeds v2 FSRS.
- The compact result format established here is the contract Claude's CLAUDE.md instructions rely on — changes to it require updating the plugin CLAUDE.md in Phase 6.
- `interview_detail` is intentionally simple (slug + domain → full entry) — the three-tier retrieval pattern means Claude calls `relevance_check` first, then `detail` only if needed.

#### Implementation Notes (Phase 4)
**Completed:** 2026-04-21
**Work completed:**
- `relevance.py` — `extract_tags()` (regex split, stop words, dedup), `score_matches()` (normalized scoring), `MatchResult` TypedDict
- `server.py` refactored to `create_server(kb_path, data_path)` factory pattern; module-level `mcp = create_server()` for production
- `interview_relevance_check` — extracts tags → scores KB → persists findings + history → returns matches with `persisted_to`
- `interview_detail` — KB lookup by slug+domain, returns full entry or error
- 8 relevance unit tests + 7 integration tests
**Integration notes:**
- `create_server(kb_path=Path, data_path=Path)` — use for testing; KB and persistence scoped to provided paths
- Test helper: `async with create_connected_server_and_client_session(server._mcp_server) as client`
- `relevance_score = overlap / max(len(entry.tags), 1)` — normalized, sorted desc
- `star_hook` is `"STAR: {first_talking_point}"` for behavioral entries, None otherwise
- No-match case logs `{"below_threshold": True}` to history
**Pitfalls & guidance:**
- `server.py` closures capture `bank`, `findings`, `history` — they persist across tool calls within a server instance
- Existing `test_server.py::test_stub_returns_not_implemented` was updated to only test the 2 remaining stubs (portfolio + history)
**Files created/modified:**
- `servers/work_logging_mcp/relevance.py` — tag extraction + scoring
- `servers/work_logging_mcp/server.py` — factory pattern + 2 real handlers + 2 stubs
- `tests/test_relevance.py` — 8 unit tests
- `tests/test_tools_core.py` — 7 integration tests
- `tests/test_server.py` — updated stub test

---

### Phase 5: Portfolio + History MCP Tools — `interview_portfolio_update` + `interview_history`

**Scope:** Replace the Phase 1 stubs for the two remaining tools. `interview_portfolio_update` creates or updates feature portfolio entries. `interview_history` queries encounter history with filtering and gap analysis.

**Deliverables:**
- [x] `interview_portfolio_update` tool handler — accepts project name, feature slug, description, key decisions, tradeoffs, patterns used, status, interview angle; delegates to `PortfolioWriter.upsert()`; returns persisted path
- [x] `interview_history` tool handler — accepts optional date range, topic filter, domain filter; delegates to `HistoryLogger.query()`; returns encounter counts by topic/domain, gap analysis (topics not seen in 30+ days), timeline
- [x] Gap analysis logic: cross-reference knowledge bank entries against history to find topics with zero or stale encounters
- [x] Tests: portfolio upsert (create + update), history query with various filters, gap analysis against mock KB + history

**Prerequisites:** Phase 3 (persistence layer) + Phase 4 (tool handler patterns established)

**Files likely created/modified:**
- `servers/work_logging_mcp/server.py` — replace remaining stubs
- `servers/work_logging_mcp/persistence.py` — add gap analysis method to `HistoryLogger`
- `tests/test_tools_portfolio_history.py` — integration tests

**Testing Strategy:**
Integration tests with tmp_path. Portfolio: create new entry, update existing (verify overwrite), verify Markdown structure. History: seed history.jsonl with fixture data, query with each filter combination, verify gap analysis identifies untouched KB entries. Edge case: empty history (all KB entries should appear as gaps).

**Integration Notes for Next Phase:**
- `interview_portfolio_update` is called by the plugin CLAUDE.md instructions after `/spec` and `/implement-phase` — Phase 6 needs to finalize those trigger conditions.
- Gap analysis output format should be concise enough for Claude to present inline without context bloat.

#### Implementation Notes (Phase 5)
**Completed:** 2026-04-21
**Work completed:**
- `HistoryLogger.gap_analysis(bank, stale_days=30)` — cross-references KB entries against history, returns `never_seen` or `stale` entries
- `interview_portfolio_update` — delegates to `PortfolioWriter.upsert()`, returns `{"persisted_to": str, "status": "ok"}`
- `interview_history` — returns `{encounters, counts_by_domain, gap_analysis, total}`
- 9 integration tests; all stubs replaced (old stub test removed)
**Integration notes:**
- All 4 tools are now fully functional — no stubs remain
- `gap_analysis()` accepts a `KnowledgeBank` instance (imported via TYPE_CHECKING to avoid circular deps at runtime)
- `interview_history` response includes `counts_by_domain` dict and `gap_analysis` list
**Pitfalls & guidance:**
- `persistence.py` uses `from __future__ import annotations` + `TYPE_CHECKING` guard for `KnowledgeBank` import
**Files created/modified:**
- `servers/work_logging_mcp/persistence.py` — added `gap_analysis()` to HistoryLogger
- `servers/work_logging_mcp/server.py` — replaced last 2 stubs with real handlers
- `tests/test_tools_portfolio_history.py` — 9 integration tests
- `tests/test_server.py` — removed obsolete stub test

---

### Phase 6: Plugin Integration + CLAUDE.md Finalization

**Scope:** Finalize the plugin CLAUDE.md with calibrated auto-invocation instructions, create the manual `/interview-check` skill, end-to-end smoke test by installing the plugin in a real Claude Code session, and write a minimal README.

**Deliverables:**
- [x] `CLAUDE.md` — finalized auto-invocation instructions with selectivity rules (trigger when / skip when from spec), threshold guidance, portfolio update triggers
- [x] `skills/interview-check/SKILL.md` — manual skill for on-demand analysis (user types `/interview-check` to force a relevance check regardless of auto-invocation rules)
- [ ] End-to-end smoke test: install plugin globally, run a real task in another project, verify relevance check fires and findings are persisted
- [x] `README.md` — installation, configuration, what it does, example output
- [ ] Verify plugin loads correctly in Claude Code (plugin.json + .mcp.json recognized)

**Prerequisites:** All prior phases (fully functional MCP server)

**Files likely created/modified:**
- `CLAUDE.md` — rewrite from placeholder to final
- `skills/interview-check/SKILL.md` — manual invocation skill
- `README.md` — user-facing docs

**Testing Strategy:**
Manual end-to-end: install plugin globally (`claude plugin add ~/source/repos/work-logging-plugin`), open a project session, complete a task, verify the interview callout appears. Check `~/.interview-prep/` for persisted findings, portfolio entry, and history line. Also test that trivial tasks (config edits, git operations) do NOT trigger the check.

**Integration Notes for Next Phase:**
- The CLAUDE.md wording is critical for selectivity — too aggressive and every interaction gets a callout, too conservative and it never fires. Expect iteration.
- The `/interview-check` skill is the escape hatch for manual invocation when auto-invocation doesn't fire.

#### Implementation Notes (Phase 6)
**Completed:** 2026-04-21
**Work completed:**
- `CLAUDE.md` — full auto-invocation rules (trigger/skip conditions, threshold 0.7, detailed breakdown format, portfolio update triggers)
- `skills/interview-check/SKILL.md` — manual `/interview-check` skill showing ALL matches
- `README.md` — installation, config, 4 tools described, KB structure, development setup
- JSON manifest validation verified
- E2E smoke test and plugin load verification deferred to manual session (requires interactive Claude Code session)
**Integration notes:**
- Plugin is code-complete — all 4 tools functional, CLAUDE.md has auto-invocation rules
- End-to-end testing requires `claude plugin add` in a live session
**Files created/modified:**
- `CLAUDE.md` — finalized from placeholder
- `skills/interview-check/SKILL.md` — new skill
- `README.md` — new

---

### Phase 7: Knowledge Bank Seeding

**Scope:** Populate `~/.interview-prep/knowledge-bank/` with YAML entries derived from the existing Notion export (8 STAR stories, ~75 LeetCode problems, 7 OOD designs, 10 design patterns, scalability notes). This is a content session, not a code session — the schema is already defined in Phase 2.

**Deliverables:**
- [x] `~/.interview-prep/knowledge-bank/behavioral/` — entries for each Amazon LP with STAR-relevant tags (8 existing stories linked)
- [x] `~/.interview-prep/knowledge-bank/algorithms/` — entries for the 17 LeetCode pattern categories (two-pointer, sliding-window, DP, etc.) with problem references
- [x] `~/.interview-prep/knowledge-bank/ood/` — entries for 7 OOD designs + 10 design patterns + SOLID principles
- [x] `~/.interview-prep/knowledge-bank/system-design/` — entries for scalability concepts (caching, load balancing, replication, partitioning, pub/sub, DB design, etc.) — **biggest gap, may need supplemental research**
- [x] Validation: all YAML files pass the Phase 2 loader without errors
- [x] Portfolio seeding: ingest existing housing-locator specs into `~/.interview-prep/portfolio/housing-locator/`

**Prerequisites:** Phase 2 (schema defined), Phase 6 (plugin functional for portfolio seeding)

**Files likely created:**
- `~/.interview-prep/knowledge-bank/{domain}/*.yaml` — 50-100+ entries across all four domains
- `~/.interview-prep/portfolio/housing-locator/*.md` — bootstrapped from existing specs

**Testing Strategy:**
Run the Phase 2 knowledge bank loader against the seeded directory — all entries must parse without validation errors. Spot-check tag coverage by running `interview_relevance_check` against summaries of recent housing-locator work and verifying relevant matches surface.

**Integration Notes:**
- System design is the weakest domain in the Notion baseline — may need a focused research session to fill gaps before seeding.
- The seeding session is intentionally separate from plugin development — it's content work, not code work.
- After seeding, the plugin is fully operational for daily use.

#### Implementation Notes (Phase 7)
**Completed:** 2026-04-21
**Work completed:**
- `scripts/seed_knowledge_bank.py` — CLI with `validate` and `seed-from-notion` subcommands; validates domain coverage, duplicate slugs, empty banks
- 12 template YAML entries in `~/.interview-prep/knowledge-bank/` (3 per domain: system-design, behavioral, algorithms, ood)
- KB validation passes: all 12 entries load without errors
- Portfolio seeded for 3 projects (20 entries total):
  - `housing-locator/` — 8 entries (foundation, ranking, stop-composition, adapter-furnished-finder, auth-bootstrap, itinerary, orchestration, architecture)
  - `algobooth/` — 5 entries (choke-groups, sample-import-ui, audio-quality-analysis, advanced-effects, ableton-link)
  - `cognito-forms/` — 7 entries (audit-log-patch-sections, builder-canvas-modernization, build-page-refactor, attachment-lightbox, l3-ticket-investigator, form-type-model-update, auto-create-submitters)
**Integration notes:**
- `seed_knowledge_bank.py validate <path>` can be run to verify KB health at any time
- Notion export parsing (`seed-from-notion`) is a placeholder — full ingestion deferred to a future interactive session
- Template YAML entries cover common topics but are intentionally minimal — expand with more entries as real work generates encounters
**Pitfalls & guidance:**
- YAML entries are in `~/.interview-prep/` (user data, NOT committed to any repo)
- Portfolio entries are Markdown files written via `PortfolioWriter.upsert()` — same format as tool-generated entries
**Files created/modified:**
- `scripts/seed_knowledge_bank.py` — seeding/validation CLI (committed to plugin repo)
- `~/.interview-prep/knowledge-bank/` — 12 YAML template entries (user data)
- `~/.interview-prep/portfolio/` — 20 portfolio entries across 3 projects (user data)

---

### Bug Fix: Compound Tag Vocabulary Mismatch

**Completed:** 2026-04-24
**Category:** `integration-gap` — Tag extractor and knowledge bank built independently with different assumptions about tag format.

**Problem:** 51% of knowledge bank tags (444/869) are hyphenated compounds (`cache-invalidation`, `event-driven`, `pub-sub`). The tag extractor splits work summaries into individual words, but `query_by_tags` used exact set intersection — so compound tags almost never matched.

**Fix:** Added `_count_overlaps` static method to `KnowledgeBank` that falls back to compound decomposition for hyphenated tags. A hyphenated tag counts as matching when ALL its hyphen-separated parts appear in the query set.

**Files modified:**
- `servers/work_logging_mcp/knowledge_bank.py` — added `_count_overlaps`, replaced `len(query_set & set(entry.tags))` in `query_by_tags`
- `tests/test_knowledge_bank.py` — added `test_query_by_tags_compound_match` and `test_query_by_tags_compound_no_partial`
- `docs/SPEC.md` — documented compound matching in Relevance Matching section
- `CLAUDE.md` — documented compound matching in Relevance scoring section
