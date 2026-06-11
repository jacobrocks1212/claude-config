# Interview Prep System — Feature Specification

> A Claude Code plugin that passively reinforces SWE interview readiness by analyzing completed work for relevance to system design patterns, behavioral questions, and coding concepts — then surfacing targeted interview insights in real time.

**Status:** Final Draft
**Priority:** P1
**Last updated:** 2026-04-23
**Depends on:** None (standalone plugin, cross-repo)

---

## Executive Summary

The Interview Prep System is a globally-installed Claude Code plugin that makes daily engineering work double as interview preparation. When significant work is completed — features designed, patterns applied, complex debugging done — the system analyzes it against a curated knowledge bank and surfaces relevant interview concepts inline. Over time, it builds a portfolio of real project experience and STAR story outlines, creating a living interview prep reference grounded in actual work rather than abstract study.

The system is designed to be **highly selective** — most interactions produce no output. Only genuine, strong matches warrant a callout. The goal is reinforcement, not noise.

v1 focuses on passive analysis, findings persistence, and portfolio building. Active recall (quiz, spaced repetition scheduling) is deferred to v2 as a separate mobile app, though v1 tracks encounter history to bootstrap v2's FSRS state.

---

## v1 Scope

### Trigger Mechanism: Hook-Enforced
- A `PostToolUse` hook on `Write|Edit` touches a session work marker (`~/.interview-prep/.session-work-marker`) whenever files are edited.
- A `Stop` hook checks whether work occurred recently (<30 min) and whether `interview_relevance_check` already ran. If work happened but no check ran, it **blocks** Claude from stopping with a reason instructing it to invoke the MCP tool.
- The MCP tool touches a check marker (`~/.interview-prep/.last-auto-check`) to prevent re-triggering.
- Feedback appears inline as part of Claude's response — no delayed/deferred display.
- The MCP server pattern-matches against the knowledge bank and returns compact results.
- Findings are persisted to disk by the MCP server as a side effect.

> **Design note:** The original v1 design used passive CLAUDE.md instructions ("Before completing any significant task, invoke..."). This proved unreliable — Claude forgets passive behavioral guidelines. The hook-based enforcement replaced it, using the same pattern as other Claude Code plugins (e.g., warp).

### Selectivity: High-Threshold Smart Filtering
Most prompts should NOT produce an interview artifact. Only genuine, meaningful matches warrant a callout.

**Trigger when:**
- Files were edited/created (features, refactors, bug fixes)
- Architecture decisions were made
- Design patterns were applied
- Complex debugging occurred
- Relevant skills were invoked (`/spec`, `/implement-phase`, `/fix`, etc.)

**Skip when:**
- Pure Q&A / explanation requests
- Config file tweaks
- Single-line fixes / trivial edits (CSS, formatting, etc.)
- Git operations only

### Analysis Scope: All Four Domains
- **System design** — caching, pub/sub, load balancing, DB design, proxy architecture, etc.
- **Behavioral / STAR** — ownership, customer obsession, deep dive, disagree & commit, etc.
- **Algorithms** (when applicable) — implementing a cache → LRU, DAG traversal → topological sort, etc.
- **OOD** (when applicable) — strategy pattern in adapters, builder in config, etc.

### Output Format: Detailed Breakdown
Full analysis block at end of Claude's response for strong matches:
- Pattern/concept name
- What you did (specific to the current work)
- Interview angle (sample question this maps to)
- Key talking points to hit
- STAR story hook (for behavioral matches)
- Saved-to path on disk

**Threshold:** `relevance_score > 0.5`. Matches below this are silently skipped (no output to user at all) but logged to encounter history.

### STAR Story Drafting
- When the system detects a strong behavioral match, it drafts a **STAR outline** — between an outline and first draft, capturing structure and key content (not polished prose).
- Focus on specific notes/topics to address, not writing quality.
- Stories from new projects accumulate alongside existing Cognito Forms stories.
- Existing Notion stories (8 from Cognito Forms) form the baseline.

### Feature Portfolio
- Tracks feature-level work: every `/spec`, `/implement-phase`, and significant architecture decision.
- Each entry is a structured summary: one-line description, key design decisions (with tradeoffs), technologies/patterns used, status, interview angle.
- Organized by project: `~/.interview-prep/portfolio/{project-name}/{feature-slug}.md`
- Enough detail to jog memory and walk through in an interview.
- **Seeding (separate session):** Existing specs from current projects (housing-locator, etc.) will be ingested to bootstrap the portfolio.

### Passive Encounter Tracking
- Every pattern/topic surfaced (whether displayed to user or below threshold) is logged to `history.jsonl` with topic, domain, date, project, and context.
- Passive encounters tracked as type `"passive"` — distinct from active recall (v2).
- This history bootstraps the v2 mobile app's FSRS state.

### Knowledge Bank
- Static reference material seeded in a separate session.
- Baseline: user's Notion interview prep export (8 STAR stories, ~75 LeetCode problems, 7 OOD designs, 10 design patterns, scalability notes).
- Structure and schema defined here; content populated separately.

---

## v2 Scope (Deferred)

| Feature | Notes |
|---|---|
| Active recall / quiz | Separate mobile app, not CLI |
| FSRS scheduling | py-fsrs library; bootstraps from v1 encounter history |
| Cognitive forcing | Question first → wait → reveal key points |
| LLM-based response scoring | Claude evaluates answers, feeds FSRS |
| Session-start quiz prompts | Configurable, off by default |
| Leech detection | Requires retention signal from quiz |
| FSRS load balancing | Disperse due items across days/subjects |

---

## Technical Design

### Delivery: Claude Code Plugin

Globally installed plugin in a dedicated repository (`~/source/repos/work-logging-plugin/`).

```
work-logging-plugin/
├── .claude-plugin/
│   └── plugin.json              # Plugin manifest
├── CLAUDE.md                    # Plugin-level instructions (documents hook behavior)
├── hooks/
│   ├── hooks.json               # Hook declarations (PostToolUse + Stop)
│   ├── track-work.sh            # PostToolUse: touches session work marker
│   └── stop-interview-check.sh  # Stop: blocks if work happened but check didn't
├── servers/
│   └── work_logging_mcp/           # Python MCP server package
│       ├── __init__.py
│       ├── server.py            # MCP tool definitions
│       ├── knowledge_bank.py    # Knowledge bank loader/query
│       ├── relevance.py         # Relevance matching logic
│       ├── persistence.py       # Findings/portfolio/history writer
│       └── requirements.txt
├── skills/
│   └── interview-check/
│       └── SKILL.md             # Manual /interview-check command
├── tests/
│   ├── test_hooks.py            # Hook script tests (all branches)
│   └── test_server.py           # MCP server tests
├── .mcp.json                    # MCP server transport config
└── docs/
    └── SPEC.md                  # This file
```

### MCP Server: Four Focused Tools

The MCP server (Python, stdio transport) exposes four tools:

#### 1. `interview_relevance_check`
**Purpose:** Analyze completed work against the knowledge bank and return matches.
**Input:** Work summary (string), files changed (list of paths), skill invoked (optional string)
**Output:** Compact match objects with topic, domain, relevance score, summary, interview angle, talking points, STAR hook. Also returns `persisted_to` path.
**Side effects:** Persists findings to disk, logs encounter to history.jsonl.

#### 2. `interview_detail`
**Purpose:** Retrieve the full knowledge bank entry for a specific topic.
**Input:** Topic slug (string), domain (string)
**Output:** Complete knowledge bank entry — description, interview questions, key points, code examples, related topics.

#### 3. `interview_portfolio_update`
**Purpose:** Create or update a feature portfolio entry.
**Input:** Project name, feature slug, description, key decisions, tradeoffs, patterns used, status, interview angle.
**Output:** Persisted portfolio entry path.

#### 4. `interview_history`
**Purpose:** Query encounter history and stats.
**Input:** Optional date range, topic filter, domain filter.
**Output:** Encounter counts by topic/domain, gap analysis (topics not seen recently), timeline.

### Relevance Matching

Claude's native understanding of the work (via the instruction-driven invocation) is the primary relevance signal. The MCP server provides the structured knowledge bank for Claude to match against. No separate ML classifier or embedding layer — Claude does the semantic matching, the MCP server does the lookup and persistence.

The `interview_relevance_check` tool accepts Claude's summary of the work and returns matching knowledge bank entries based on keyword/tag overlap. Compound tag matching ensures hyphenated entry tags (e.g., `cache-invalidation`, `pub-sub`) match when all constituent parts appear in the query — so a summary containing "cache" and "invalidation" counts as matching `cache-invalidation`. Claude then determines which matches are strong enough to present.

### Compact Results (Three-Tier Retrieval)

Following the claude-mem pattern:
1. **`interview_relevance_check`** returns compact results (~200 tokens per match): topic, score, summary, talking points.
2. **`interview_detail`** returns the full knowledge bank entry (~2000 tokens) only when explicitly requested.
3. This prevents context window bloat while giving Claude enough to generate the detailed breakdown.

### Persistence Structure

```
~/.interview-prep/
├── knowledge-bank/              # Static reference material (seeded separately)
│   ├── system-design/           # e.g., observer-pattern.yaml
│   ├── behavioral/              # e.g., ownership.yaml
│   ├── algorithms/              # e.g., dynamic-programming.yaml
│   └── ood/                     # e.g., strategy-pattern.yaml
├── findings/                    # Real examples from your work, by topic
│   ├── system-design/
│   │   └── observer-pattern.md  # Accumulates examples over time
│   ├── behavioral/
│   │   └── deep-dive.md         # STAR outlines from real work
│   ├── algorithms/
│   └── ood/
├── portfolio/                   # Feature-level work, by project
│   └── housing-locator/
│       ├── stop-composition.md
│       └── ranking.md
├── config.json                  # User preferences
└── history.jsonl                # Chronological encounter log
```

### Knowledge Bank Entry Schema (TBD — seeding session)

Each entry is a YAML file with (at minimum):
- `slug`: kebab-case identifier
- `name`: display name
- `domain`: system-design | behavioral | algorithms | ood
- `tags`: list of keywords for matching
- `description`: concise explanation
- `interview_questions`: list of sample questions
- `talking_points`: key points to hit in an answer
- `related_topics`: cross-domain links
- `difficulty`: beginner | intermediate | advanced

### Hook-Based Enforcement Architecture

Auto-invocation is enforced by three components working together:

```
PostToolUse(Write|Edit)  →  touches ~/.interview-prep/.session-work-marker
                                    ↓
Stop                     →  checks work marker (recent?) + check marker (stale?)
                             if work && !checked → block + reason
                                    ↓
interview_relevance_check →  touches ~/.interview-prep/.last-auto-check
                             (prevents Stop hook from re-triggering)
```

**Key design details:**
- **30-minute window**: Markers older than 30 minutes are considered stale, preventing re-triggering across sessions.
- **Infinite loop prevention**: The Stop hook touches the check marker *before* outputting the block decision, so the next Stop event sees a fresh marker and allows stop.
- **Plugin-scoped hooks**: Declared in `hooks/hooks.json` (auto-discovered by Claude Code), not in global settings. Hooks activate/deactivate with the plugin.
- **POSIX-only**: Hook scripts use only `date`, `stat`, `touch`, `mkdir`, `cat` — no jq or other dependencies.

### Plugin-Level CLAUDE.md

The plugin's CLAUDE.md documents the hook behavior and presentation rules. It does NOT contain passive invocation instructions (those proved unreliable). Key rules:
- When the Stop hook blocks, Claude invokes `interview_relevance_check` with work summary, files changed, and skill invoked.
- If no matches exceed `relevance_score > 0.5`, Claude says nothing — does not mention the check ran.
- Only genuinely relevant matches are presented (detailed breakdown format).
- After `/spec` or `/implement-phase`, also invoke `interview_portfolio_update`.

---

## Existing Materials (Notion Export Baseline)

| Domain | Content | Status |
|---|---|---|
| Behavioral/STAR | 8 detailed stories (all Cognito Forms), LP cross-reference guide, all 16 Amazon LPs | Strong |
| Algorithms | ~75 LeetCode problems (C#), 17 pattern categories, strategy guides, DP/Dijkstra deep dives | Strong |
| OOD | 7 complete designs with code, 10 design patterns, SOLID principles, interview framework | Strong |
| System Design | Scalability basics (load balancing, caching, replication, partitioning) | Shallow — biggest gap |
| Coach Prompts | LeetCode + OOD mock interview system prompts | Complete |
| Company Prep | Securely.io + Amazon L4 process | Context-specific |

---

## Implementation Phases

See [`PHASES.md`](./PHASES.md) for the detailed 7-phase breakdown.

---

## Decisions Log

| Decision | Rationale |
|---|---|
| 7 phases (not fewer) | Persistence layer and knowledge bank are distinct testable units; merging them would create a phase with too many mock boundaries |
| Seeding as Phase 7 (not Phase 0) | Schema must exist first (Phase 2); plugin should be functional before content work begins |
| Core tools (Phase 4) before portfolio/history tools (Phase 5) | `interview_relevance_check` is the primary tool and establishes the handler pattern; portfolio/history follow it |
| Plugin integration last (Phase 6) | CLAUDE.md auto-invocation instructions depend on the actual tool contracts being stable |
| Hook enforcement over passive CLAUDE.md | Passive instructions ("Before completing, invoke...") proved unreliable — Claude forgets behavioral guidelines. Stop hooks with block decisions physically prevent Claude from finishing without running the check. |
| Threshold 0.5 (not 0.7) | 0.7 was too aggressive — genuine matches were being suppressed. 0.5 balances signal vs noise. |
| Silent on no-match | When no matches exceed 0.5, Claude says nothing at all. Avoids "no matches found" noise that adds no value. |

---

## Resolved Questions

| Question | Resolution |
|---|---|
| Knowledge bank entry schema | YAML files with slug, name, domain, tags, description, interview_questions, talking_points, related_topics, difficulty. Populated during seeding. |
| Relevance threshold | 0.5 (lowered from initial 0.7 — too many genuine matches were being suppressed) |
| Server-side vs Claude-side filtering | Server does keyword/tag matching and returns candidates; Claude determines final relevance and presentation. |
| Auto-invocation enforcement | Hook-based (Stop + PostToolUse). Passive CLAUDE.md instructions proved unreliable — Claude forgets them. |

---

## Research References

- [RESEARCH.md](./RESEARCH.md) — Full Gemini Deep Research output
- [RESEARCH_SUMMARY.md](./RESEARCH_SUMMARY.md) — Key findings and spec adjustments

Key research that shaped decisions:
- **FSRS over SM-2** (deferred to v2 but architecture chosen): py-fsrs, predictive 3-variable model
- **Passive vs active recall distinction** (Marsick/Watkins, Bjork): passive encounters tracked separately
- **Three-tier retrieval** (claude-mem pattern): compact results prevent context bloat
- **Case Study Maker** (julieclarkson/case-study-maker): validates portfolio feature approach
- **Design pattern detection from diffs** (SVM/LLM research): Claude's native understanding is sufficient
