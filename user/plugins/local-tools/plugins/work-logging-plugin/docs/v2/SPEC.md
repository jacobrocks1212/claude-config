# Interview Prep Plugin v2 — Feature Specification

> Work-log-grounded interview preparation with Obsidian vault generation, feature-level synthesis, and domain-specific narrative templates.

**Status:** Final Draft
**Priority:** P1
**Last updated:** 2026-05-01
**Depends on:** None

---

## Executive Summary

The interview-prep plugin started as a passive relevance detection system (v1) but real-world usage revealed that only the work logging MCP tool (`work_log_append`) provides consistent value. The 5 other tools and the hook-based auto-invocation system were never adopted.

v2 pivots to a **work-log-first architecture**: passively capture granular work records during daily engineering (already working), then provide on-demand tools to **synthesize feature-level summaries**, **correlate work to interview topics via a two-stage LLM-as-a-judge pipeline**, and **generate an Obsidian vault** with domain-specific narrative templates for structured study.

The approach is grounded in the **Self-Reference Effect (SRE)** from cognitive psychology — information encoded through self-related processing is retained with significantly higher accuracy. Mapping abstract interview concepts to the engineer's own architectural decisions, tradeoffs, and production experiences produces higher fidelity recall, greater credibility, and reduced interview anxiety.

### Key changes from v1

- Remove dormant tools, passive detection system, findings, history, and portfolio subsystems
- Add feature-level work log (hybrid: optional tagging at log time + LLM post-hoc synthesis)
- Add Obsidian vault generation with domain-specific templates: (I)STAR(T) for behavioral, ADR for system design, Entity-Pattern-Extensibility for OOD
- Add idempotent artifact import with content hashing for backfilling from planning docs
- Add spaced repetition compatibility via Obsidian SRS plugin formatting
- Version-control `~/.interview-prep/` as independent git repo
- Two-layer MCP tool surface: composite user skills + atomic LLM-callable primitives

## Current State (v1)

### What works
- `work_log_append` — called at end of skill sessions, 23 records across 5 projects
- Knowledge bank — 154 curated YAML entries across 4 domains (system-design, algorithms, ood, behavioral)
- `/log` skill — manual work logging

### What's dormant/unused
- `interview_kb_index`, `interview_detail` — available but never auto-invoked
- `interview_record_findings`, `interview_portfolio_update`, `interview_history` — dormant
- Hook-based auto-invocation — abandoned
- Findings (71 auto-generated MD files) — low-value copies of KB descriptions
- History log (229 passive exposure records) — noise
- Portfolio (20 auto-generated MD files) — right concept, wrong mechanism

### Uncaptured work
- **Cognito Forms**: 268 planning artifacts in `.claude.local/` (7 SPECs, 3 PHASES, 40+ mockups, meeting notes Jan-Mar 2026)
- **algobooth**: 223 planning artifacts in `docs/features/` (61 SPECs, 29 RESEARCH, 9 PHASES)
- None of this work is reflected in the work log

---

## v2 Architecture

### Data Model

```
~/.interview-prep/                          # Independent git repo
├── work-log.jsonl                          # Granular session-level log (KEEP)
├── features.jsonl                          # Feature-level synthesized log (NEW)
├── import-index.jsonl                      # Content hash registry for idempotent import (NEW)
├── knowledge-bank/                         # 154 YAML topic entries (KEEP)
│   ├── system-design/   (44 entries)
│   ├── algorithms/      (39 entries)
│   ├── ood/             (36 entries)
│   └── behavioral/      (35 entries)
├── vault/                                  # Obsidian vault (GENERATED, gitignored)
│   ├── 01_Knowledge_Bank/{domain}/{slug}.md
│   ├── 02_Work_History/{date}-{slug}.md
│   ├── 03_Features/{slug}.md
│   ├── 04_Interview_Stories/{slug}.md
│   └── Meta/
│       ├── dashboard.md
│       └── templates/
├── config.json                             # User preferences (KEEP)
└── .git/                                   # Version control (NEW)
```

### Removed in v2
- `findings/` directory — replaced by vault Interview Stories
- `history.jsonl` — replaced by work log as sole activity record
- `portfolio/` directory — replaced by features.jsonl + vault Feature pages
- `.classify-prompt.txt`, `.last-auto-check`, `.session-work-marker` — hook artifacts
- Hook system (`hooks/` directory in plugin repo)
- `servers/work_logging_mcp/relevance.py` — dormant module
- MCP tools: `interview_record_findings`, `interview_portfolio_update`, `interview_history`

### Data Flow

```
Daily work sessions
       │
       ▼
work_log_append ──► work-log.jsonl ──► git auto-commit
  (optional feature tag)          │
                                  │
       ┌──────────────────────────┤
       ▼                          ▼ (on-demand)
/interview-import             /interview-synthesize
  │ Scan SPEC/PHASES              │ Hybrid: tagged entries + LLM clustering
  │ from other repos              │ of orphaned logs
  │ Content hash dedup            │
  ▼                               ▼
work-log.jsonl ◄────────── features.jsonl
       │                          │
       └──────────┬───────────────┘
                  ▼ (on-demand)
          /interview-generate
                  │
                  ├─ Stage 1: Semantic candidate retrieval (top 10 topics per feature)
                  ├─ Stage 2: LLM-as-a-judge evaluation (strict 0-2 rubric)
                  ├─ Generate domain-specific narratives:
                  │    ├── Behavioral: (I)STAR(T) framework
                  │    ├── System Design: Architecture Decision Records (ADRs)
                  │    ├── OOD: Entity → Pattern → Extensibility
                  │    └── Algorithms: Problem → Approach → Complexity → Your Usage
                  ├─ Managed Block pattern (preserve user annotations)
                  ├─ SRS flashcard formatting (:: syntax)
                  └─ DAG link topology (Work → Feature → Story → Topic)
                  │
                  ▼
          vault/ (Obsidian)
                  │
                  ▼
          Study in Obsidian (graph view, Dataview dashboards, SRS drilling)
```

---

## Feature Details

### 1. Version-Controlled Data Directory

`~/.interview-prep/` becomes an independent git repository.

- **Auto-commit** after `work_log_append`, `import`, and `synthesize` operations
- **Private GitHub remote** for backup (manual setup by user)
- **`.gitignore`** excludes `vault/` (derived artifact, regenerated on demand)
- **Migration**: init git repo, normalize existing work-log.jsonl schema (old `date`/`repo` fields → `timestamp`/`project`), initial commit

### 2. Feature-Level Work Log (`features.jsonl`)

Append-only JSONL storing **feature/initiative-level** summaries synthesized from granular work log entries.

**Record schema:**
```json
{
  "id": "uuid-v4",
  "slug": "cognito-pay",
  "project": "cognito-forms",
  "title": "Cognito Pay — Payment Processing Integration",
  "summary": "Designed and implemented multi-provider payment processing...",
  "work_log_refs": ["2026-04-15T18:32:00Z", "2026-04-18T20:15:00Z"],
  "technologies": ["C#", "Stripe API", "Vue.js"],
  "patterns": ["strategy-pattern", "event-driven-architecture"],
  "topic_correlations": [
    {"slug": "api-design", "domain": "system-design", "score": 2},
    {"slug": "strategy-pattern", "domain": "ood", "score": 2}
  ],
  "status": "in-progress",
  "created": "2026-05-01T00:00:00Z",
  "updated": "2026-05-01T00:00:00Z"
}
```

**Hybrid synthesis approach:**
1. **Tag at log time (optional):** Add `feature` field to `work_log_append`. When the engineer knows the feature context, they tag it. Zero friction when they don't.
2. **LLM post-hoc clustering:** `/interview-synthesize` reads orphaned (untagged) work log entries, proposes feature groupings via semantic clustering, presents for user review before committing.
3. **Cold start path:** `/interview-import` ingests planning artifacts (SPEC.md, PHASES.md) directly as Features via map-reduce summarization, bypassing the granular log stage. Instantly populates the feature log with years of work.

### 3. Obsidian Vault Generation

On-demand generation via `/interview-generate`. Produces an interlinked Obsidian vault optimized for both exploration (graph view) and drilling (SRS flashcards).

#### Vault Collections

| Collection | Content | Source | Links To |
|------------|---------|--------|----------|
| `01_Knowledge_Bank/{domain}/{slug}.md` | Canonical topic reference + correlated stories list + Dataview query | Knowledge bank YAML | Interview Stories (inbound) |
| `02_Work_History/{date}-{slug}.md` | Granular work log entry as browsable MD | work-log.jsonl | Parent Feature (outbound only) |
| `03_Features/{slug}.md` | Initiative-level narrative: summary, decisions, tradeoffs, technologies | features.jsonl | Interview Stories (outbound), Work History (inbound) |
| `04_Interview_Stories/{slug}.md` | Study artifact: domain-specific narrative with managed blocks + flashcards | LLM-generated from Feature + Topic correlation | Knowledge Bank topic (outbound), Source Feature (outbound) |
| `Meta/dashboard.md` | Coverage heatmap, gap analysis, study plan, recent activity | All data sources | All collections |

#### Domain-Specific Narrative Templates

**Behavioral — (I)STAR(T) Framework:**
```markdown
## Introduction
One-sentence hook establishing the theme.

## Situation
Business context and stakes.

## Task
Specific engineering mandate.

## Action
First-person execution. "I decided..." not "We built..."

## Result
Quantifiable metrics where available.

## Takeaway
Retrospective insight demonstrating maturity and adaptability.
```

**System Design — Architecture Decision Record (ADR):**
```markdown
## Context & Constraints
Business requirement, load constraints, data sovereignty, SLAs.

## Baseline Design
Initial/naive approach or legacy system that was failing.

## Bottleneck Identification
Specific point of failure at scale.

## Decision & Tradeoffs
Architectural pivot with explicitly accepted costs.

## Operational Reality
Instrumentation, monitoring, post-deployment maintenance.
```

**OOD — Entity-Pattern-Extensibility:**
```markdown
## Core Entities
Primary objects, actors, and state within the feature.

## Pattern Applied
Canonical GoF or architectural pattern utilized.

## Extensibility Justification
How the design adheres to SOLID principles and enables future expansion.
```

**All domains enforce the Rule of Three:** max 3 core challenges per narrative.

#### Managed Block Pattern

All LLM-generated content is enclosed in HTML comment delimiters:
```markdown
# Rate Limiting via Token Bucket

User's personal thoughts go here. Preserved across regenerations.

<!-- BEGIN MANAGED -->
## Grounded Experience: Auth Service Migration
[LLM-generated content...]
<!-- END MANAGED -->

More user annotations can go here.
```

During regeneration, only content between `<!-- BEGIN MANAGED -->` and `<!-- END MANAGED -->` is replaced. Everything outside is untouched.

#### Graph Topology (DAG)

Strict hierarchical linking to prevent graph hairball:
1. **Work History** → links only to parent Feature (outbound)
2. **Features** → links to Interview Stories generated from them (outbound)
3. **Interview Stories** → links to Knowledge Bank topics they correlate to (outbound)
4. **Knowledge Bank** → receives inbound links only (gravitational hubs in graph view)

No direct links from Work History to Knowledge Bank topics. Max 3 feature correlations per topic.

#### Dataview & SRS Compatibility

**Frontmatter schema** (all generated pages):
```yaml
---
id: story-rate-limiting-auth
type: interview-story
domain: system-design
source_feature: "[[Feature-Cognito-Pay]]"
correlated_topics:
  - "[[rate-limiting]]"
  - "[[api-gateway-design]]"
difficulty: hard
tags:
  - "#review"
  - interview/system-design
created: 2026-05-01
updated: 2026-05-01
---
```

**SRS flashcard syntax** embedded in managed blocks:
```markdown
What tradeoff did you accept when choosing Redis for rate limiting?
:: Accepted operational overhead of managing Redis cluster in exchange for low-latency atomic INCR operations and TTL-based bucket expiration.
```

The Obsidian Spaced Repetition plugin writes `sr-due`, `sr-interval`, `sr-ease` to frontmatter. The managed block pattern preserves these across regeneration since they live outside the managed region.

### 4. Topic Correlation: Two-Stage LLM-as-a-Judge

**Stage 1 — Candidate Retrieval:**
- Generate semantic summary of each Feature
- Compare against 154 Knowledge Bank topic descriptions
- Retrieve top 10 most semantically proximate candidates

**Stage 2 — LLM Judge Evaluation:**
- Evaluate each Feature against its 10 candidate topics using strict rubric:
  - **Score 0 (Irrelevant):** Feature uses the technology but core challenge doesn't map to topic
  - **Score 1 (Tangential):** Feature touches topic but actions weren't primarily focused on it
  - **Score 2 (Strong Match):** Feature demonstrates direct, intentional engagement with topic's principles
- Only Score 2 correlations are persisted and used for vault generation
- Correlations stored in `features.jsonl` (pre-computed, not recomputed per vault generation)

**Density targets:** 1-3 work examples per topic (enough for redundancy, avoids dilution). 8-10 deeply prepared behavioral stories across common dimensions.

### 5. Artifact Import Tool

Idempotent ingestion of planning artifacts from other repos.

**Deduplication: Content Hash + Path UUID:**
1. Read target file, generate SHA-256 hash of contents
2. Check `import-index.jsonl` — if exact hash exists, skip (idempotent)
3. If path matches existing entry but hash differs → document evolved. New entry with same UUID, updated hash and timestamp
4. New path + new hash → new entry with fresh UUID

**Import-index record:**
```json
{
  "uuid": "...",
  "source_path": "C:/Users/JacobMadsen/source/repos/algobooth/docs/features/audio-vision/SPEC.md",
  "content_hash": "sha256:abc123...",
  "imported_at": "2026-05-01T00:00:00Z",
  "project": "algobooth",
  "artifact_type": "spec"
}
```

**Cold start ingestion:**
- Map-reduce: LLM reads each SPEC.md/PHASES.md, extracts title, objectives, technologies, patterns, challenges
- Creates Feature entries directly in `features.jsonl` (bypasses granular work log)
- Interactive curation: presents proposed Features for user review before committing
- Primary target: ~491 artifacts from Cognito Forms (268) and algobooth (223)

### 6. MCP Tool Surface: Two-Layer Architecture

#### Composite Tools (User-Facing)

| Tool | Purpose | Invoked By |
|------|---------|------------|
| `work_log_append` | Log granular work with optional feature tag | Skills (automatic), `/log` (manual) |
| `generate_vault` | Orchestrate full vault generation cycle | `/interview-generate` skill |
| `import_artifacts` | Scan and ingest planning docs from a directory | `/interview-import` skill |
| `synthesize_features` | Cluster orphaned logs into Features, run topic correlation | `/interview-synthesize` skill |

#### Atomic Tools (LLM-Callable Primitives)

| Tool | Purpose |
|------|---------|
| `read_work_log` | Query work-log.jsonl with filters (project, date range, feature tag) |
| `read_features` | Query features.jsonl with filters |
| `get_kb_topic` | Get full Knowledge Bank entry by slug+domain |
| `get_kb_index` | Get compact topic index (slug, name, domain, tags, description) |
| `evaluate_topic_match` | Run LLM-as-a-judge rubric on a Feature × Topic pair, return score 0-2 |
| `write_managed_block` | Write/update content within managed block delimiters in a vault MD file |
| `calculate_hash` | SHA-256 hash of file contents for import dedup |

The composite tools orchestrate the atomic tools. The LLM can also invoke atomic tools directly for ad-hoc queries or debugging.

### 7. Skill Surface

| Skill | Purpose | Status |
|-------|---------|--------|
| `/log` | Manual work log entry | KEEP (unchanged) |
| `/interview-generate` | Generate/regenerate Obsidian vault | NEW |
| `/interview-import` | Import planning artifacts from repos | NEW |
| `/interview-synthesize` | Synthesize feature-level entries from work log | NEW |
| `/interview-check` | Quick topic lookup against recent work | EVOLVE (use KB index + atomic tools) |

### 8. Async Progress Reporting

Long-running operations (vault generation, bulk import) use MCP progress notifications:
- FastMCP yields progress tokens with current/total counts
- Human-readable status messages (e.g., "Synthesizing Feature: Auth Service Migration...")
- Prevents client-side timeouts during large operations
- Enables CLI progress display

---

## Implementation Phases

See [`PHASES.md`](./PHASES.md) for the detailed phase breakdown.

**Summary:** 5 phases progressing from cleanup → data layer → LLM integration → vault generation → atomic tools.

| Phase | Title | Risk | Tools After |
|-------|-------|------|-------------|
| 1 | v1 Cleanup & Data Foundation | Low | 3 |
| 2 | Features Data Layer & Import Pipeline | Medium | 4 |
| 3 | Feature Synthesis & Topic Correlation | High | 5 |
| 4 | Vault Generation | Medium | 6 |
| 5 | Atomic Tools & Progress Reporting | Low | 11 |

---

## Open Questions

1. **Knowledge bank evolution:** Should the 154 YAML entries remain static in v2, or should we support adding/editing topics? (Recommendation: static for v2, revisit if gaps emerge during study.)
2. **Vault regeneration frequency:** How often will the user realistically regenerate? Does the managed block pattern need to handle partial regeneration (single collection) or always full?
3. **Embedding strategy for Stage 1 correlation:** Use a local embedding model (fast, free) or Claude's own semantic understanding (simpler, token cost)?

## Research References

See [RESEARCH.md](./RESEARCH.md) and [RESEARCH_SUMMARY.md](./RESEARCH_SUMMARY.md) for the full Gemini Deep Research analysis that informed this spec.

Key research-driven decisions:
- Self-Reference Effect (SRE) as cognitive foundation
- (I)STAR(T) framework for behavioral narratives (replaces plain STAR)
- ADR format for system design narratives
- Managed Block pattern for vault regeneration safety
- Two-stage LLM-as-a-judge for topic correlation
- Content hash + path UUID for idempotent import
- DAG link topology to prevent graph hairball
- SRS plugin compatibility for spaced repetition
