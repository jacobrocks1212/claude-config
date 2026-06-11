# Interview Prep Plugin v2 — Deep Research Prompt

## Research Question

How should a personal interview preparation tool be designed to effectively correlate a software engineer's real work history (captured as structured logs) with canonical interview topics, and what formats/patterns produce the most effective personalized study material?

## Context

### Who this is for
A senior software engineer preparing for technical interviews (system design, OOD, behavioral, algorithms) while continuing to work full-time. The tool is a Claude Code plugin that passively captures engineering work during daily sessions, then provides on-demand generation of study materials grounded in the engineer's own experience.

### Tech stack
- **Plugin runtime:** Python MCP server (FastMCP), invoked by Claude Code CLI
- **Data storage:** JSONL append-only logs, YAML knowledge bank (154 curated topic entries across 4 domains)
- **Output format:** Obsidian-compatible Markdown vault with wikilinks, YAML frontmatter, cross-references
- **Interaction model:** Claude Code skills (slash commands) for generation, import, and synthesis. No web UI.

### What exists today (v1)
- **Work log:** 23 JSONL records capturing granular skill completions (bug fixes, feature implementations, specs). Fields: skill, project, title, summary, files_modified, technologies, patterns, technical_context, plus skill-specific extras.
- **Knowledge bank:** 154 YAML files across system-design (44), algorithms (39), ood (36), behavioral (35). Each has: slug, name, domain, tags, description, interview_questions, talking_points, related_topics, difficulty.
- **Dormant subsystems:** Auto-invocation hooks, passive findings writer, encounter history, portfolio writer — all unused. Being removed in v2.

### What v2 adds
1. **Feature-level work log** — synthesized from granular entries, tracking initiatives/features across sessions
2. **Obsidian vault generation** — on-demand creation of interlinked MD study material correlating work → topics
3. **Artifact import** — idempotent ingestion of planning docs (SPEC.md, PHASES.md) from other repos into work log
4. **Version-controlled data** — `~/.interview-prep/` as independent git repo

## Baseline Spec Summary

### Confirmed decisions
- Pivot from passive detection to work-log-first architecture
- Remove dormant tools (record_findings, portfolio_update, history) and their data (findings/, portfolio/, history.jsonl)
- Keep knowledge bank (154 YAML) as interview topic corpus
- Keep `work_log_append` as primary data capture mechanism
- Generate Obsidian vault on-demand via `/interview-generate` skill
- Import planning artifacts via idempotent `/interview-import` skill
- Feature-level synthesis via `/interview-synthesize` skill
- Separate git repo in `~/.interview-prep/` for version control

### Open design decisions
- Feature synthesis approach (tag-at-log-time vs post-hoc synthesis vs hybrid)
- Study material format (interview drill vs reference notes vs hybrid)
- MCP tool surface for v2
- Vault freshness strategy (pre-computed correlations vs generation-time)
- Knowledge bank evolution (static vs user-extensible)
- Work log schema normalization strategy
- Degree of LLM involvement in story/walkthrough generation

## Research Areas

### 1. Personal Knowledge Management for Interview Prep
- What tools/systems exist for correlating professional experience with interview preparation? (e.g., Anki-based systems, spaced repetition for interviews, portfolio generators)
- How do experienced engineers organize their interview prep when they have years of real work to draw from?
- What's the evidence for "grounded" interview prep (using your own examples) vs pure topic study?
- Are there open-source tools or frameworks that generate study material from work history?

### 2. Obsidian Vault Design Patterns
- Best practices for programmatically generating Obsidian vaults (file structure, frontmatter conventions, linking strategies)
- How to structure a vault for both browsing (exploration) and drilling (focused study)?
- Dataview plugin compatibility — what frontmatter properties enable useful dynamic queries?
- Graph view optimization — how to structure links so the graph is useful rather than a hairball?
- How to handle vault regeneration without losing user edits (if the user annotates generated pages)?
- Template patterns for different content types (concept pages, project pages, study guides)

### 3. Interview Story Formats
- **STAR format** (Situation, Task, Action, Result) — best practices for technical interviews specifically
- **System design walkthrough format** — how to structure design narratives from real project experience
- **OOD pattern format** — how to present pattern usage with concrete examples
- What level of detail is optimal for interview stories? Too brief = not credible, too detailed = loses the interviewer
- How should behavioral stories be structured differently from system design stories?
- Research on the effectiveness of pre-written vs improvised interview stories

### 4. Work Log → Feature Synthesis Strategies
- **Approach A: Tag at log time** — add an optional `feature` field to work log entries. Pros: clean data, no post-hoc guessing. Cons: requires discipline, may not know the feature name at log time.
- **Approach B: Post-hoc LLM synthesis** — Claude reads N work log entries and proposes feature groupings. Pros: zero friction during work. Cons: may group incorrectly, requires review.
- **Approach C: Hybrid** — tag when known, synthesize when not. What are the best practices for this kind of semi-structured data aggregation?
- How do engineering teams track "initiatives" that span multiple PRs/sessions? Any patterns from project management tools (Linear, Jira epics, etc.) that apply here?

### 5. Topic Correlation Quality
- How to effectively correlate unstructured work descriptions to structured topic taxonomies?
- Keyword matching vs semantic similarity vs LLM-as-judge — what works best for this use case?
- How many work examples per topic is "enough" for credible interview answers? (1? 3? 5?)
- Should correlations be bidirectional (topic → work AND work → topic) or unidirectional?
- How to handle partial matches (work touches a topic tangentially)?

### 6. Idempotent Import Design
- Patterns for idempotent document ingestion in append-only logs
- Content hashing vs path-based dedup vs timestamp-based — tradeoffs for each
- How to extract meaningful metadata from Markdown planning documents (SPEC.md, PHASES.md) programmatically
- Handling evolution — what if a SPEC.md is updated after initial import?

### 7. MCP Tool Design for LLM-Driven Workflows
- What's the right granularity for MCP tools? Many small tools vs fewer composite tools?
- Should vault generation be an MCP tool (callable by LLM) or a skill (user-invoked only)?
- How to design tools that support both programmatic (LLM) and interactive (human) workflows?
- Error handling and progress reporting for long-running generation tasks in MCP

## Specific Questions

1. What Obsidian vault structures have been proven effective for technical interview prep? Are there community templates or published approaches?
2. How should STAR stories be adapted for system design interviews vs behavioral interviews? Is there a better format than STAR for system design narratives?
3. What's the recommended approach for LLM-generated study material that needs to stay accurate — fully regenerate each time, or incremental updates with checksums?
4. Are there existing tools (open source or commercial) that solve the "correlate work history to interview topics" problem? What can we learn from them?
5. What Obsidian plugins (beyond Dataview) would enhance a programmatically generated interview prep vault?
6. How do spaced repetition principles apply to interview prep? Should the vault/dashboard incorporate spaced repetition scheduling?
7. For behavioral interviews specifically, what's the recommended number of prepared stories, and how should they map to common behavioral dimensions (leadership, conflict, failure, etc.)?
8. What's the best schema design for a feature-level work log that needs to support both human browsing and LLM-driven correlation?
9. How should the system handle the "cold start" problem — generating useful study material when the work log has only 23 entries but there are 491 planning artifacts to import?
10. What are the failure modes of LLM-based topic correlation (false positives, missed correlations) and how to mitigate them?

## Output Format Request

Structure findings as:

1. **Executive Summary** — Key recommendations in 3-5 bullet points
2. **Prior Art** — Existing tools and approaches, with links and brief assessments
3. **Obsidian Vault Design** — Recommended structure, templates, and plugins with concrete examples
4. **Interview Story Formats** — Recommended templates for each domain (behavioral, system design, OOD, algorithms) with examples
5. **Feature Synthesis** — Recommended approach with tradeoff analysis
6. **Topic Correlation** — Recommended strategy with accuracy considerations
7. **Tool/Skill Design** — Recommended MCP tool surface and skill interactions
8. **Spaced Repetition & Study Planning** — Whether and how to incorporate SR principles
9. **Risk Analysis** — Potential pitfalls and mitigations
10. **Recommendations Matrix** — Decision table for each open question with recommended choice and confidence level
