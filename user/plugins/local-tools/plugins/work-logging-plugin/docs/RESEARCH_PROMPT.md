# Research Prompt: Interview Prep Plugin for Claude Code

## Research Question

What are the best practices, prior art, and technical approaches for building an always-on, passive interview preparation system that integrates into a developer's daily coding workflow — specifically as a Claude Code plugin with an MCP server backend?

## Context

**What we're building:** A Claude Code plugin (globally installed, cross-repo) that analyzes a developer's completed work and surfaces relevant SWE interview concepts in real time. The system covers four domains: system design patterns, behavioral/STAR stories, algorithm patterns, and OOD patterns. It also maintains a feature portfolio tracking significant design/implementation work.

**Tech stack:**
- Claude Code plugin (manifest, hooks, skills, MCP server bundle)
- MCP server in Python (knowledge bank queries, relevance analysis, persistence, spaced repetition)
- Local file-based persistence (~/.interview-prep/) — Markdown findings, JSON state, JSONL history
- SM-2 spaced repetition for active recall

**User profile:** Senior SWE, daily Claude Code user across multiple projects. Wants minimal workflow disruption — the system should be highly selective (most tasks should NOT produce an interview artifact).

**Existing materials being integrated:** ~75 LeetCode solutions (C#), 8 STAR stories (Amazon LP-mapped), 7 OOD designs with code, 10 design patterns, scalability notes, algorithm strategy guides. These seed the knowledge bank.

## Baseline Spec Summary

1. **Trigger:** Instruction-driven — plugin CLAUDE.md tells Claude to invoke an MCP `interview_relevance_check` tool before finishing significant tasks. No Stop hook for display (hooks can't output to user). Optional Stop hook for background logging.

2. **Selectivity:** High threshold. Trigger on meaningful code changes, architecture decisions, design pattern application, complex debugging, skill invocations (/spec, /implement-phase). Skip Q&A, config tweaks, trivial edits.

3. **Output:** Detailed breakdown at end of Claude's response — pattern name, what the user did, interview angle (sample question), key talking points, STAR story hook. Only for strong matches.

4. **STAR stories:** System drafts new STAR outlines (structure + content, not polished prose) from real work across projects. Accumulates alongside existing stories.

5. **Feature portfolio:** Tracks feature-level work (/spec, /implement-phase). Structured summaries: description, key decisions, tradeoffs, patterns, interview angle. Organized by project.

6. **Spaced repetition:** SM-2 algorithm tracking encounter frequency. `/interview-quiz` command for on-demand practice. Session-start quiz OFF by default (configurable).

7. **Persistence:** Topic-organized on disk — knowledge-bank/ (static reference), findings/ (real examples from work), portfolio/ (feature summaries), spaced-repetition.json, history.jsonl.

8. **Delivery:** Claude Code plugin in a dedicated repo, globally installed. Bundles MCP server, skills, plugin-level CLAUDE.md, optional hooks.

## Research Areas

### 1. Claude Code Plugin Architecture
- What is the current best practice for structuring Claude Code plugins (2025-2026)?
- How does plugin-level CLAUDE.md interact with user-level and project-level CLAUDE.md? Precedence? Conflicts?
- What are the real-world limitations of instruction-driven auto-invocation (i.e., telling Claude via CLAUDE.md to always call an MCP tool)? How reliable is it? Does Claude "forget" or skip it under context pressure?
- What happens when the MCP server is slow? Does it block Claude's response? Timeout behavior?
- Can a plugin include its own dependencies (Python packages)? Or does the MCP server need a standalone venv/installation?

### 2. MCP Server Design for This Use Case
- What MCP tools should the server expose? Propose a tool API surface (tool names, input/output schemas).
- How should the MCP server handle the knowledge bank — load entirely into memory at startup, or query on demand from disk?
- What's the best way for Claude to pass "what I just did" context to the MCP server? Full conversation summary? File diff? List of modified files?
- How should the MCP server determine relevance — keyword matching against knowledge bank entries? TF-IDF? Embedding similarity? LLM classification? What's the right tradeoff of accuracy vs. latency vs. cost?
- Should the MCP server return raw data for Claude to format, or return pre-formatted Markdown?

### 3. Relevance Matching and Noise Control
- How to calibrate a relevance threshold to be selective enough that most tasks produce no output, but strong matches are never missed?
- Prior art in code-to-concept mapping — how do existing tools (if any) map code changes to abstract CS concepts?
- Should matching happen on the code diff, the conversation context, or both?
- How to distinguish "I used a pattern" (e.g., Strategy pattern in an adapter) from "I used something that superficially resembles a pattern" (e.g., an if/else that isn't really Strategy)?
- What's the risk of the system becoming annoying/ignored over time? How to maintain long-term engagement?

### 4. Spaced Repetition Integration
- SM-2 vs SM-5 vs FSRS (Free Spaced Repetition Scheduler) — which is best for a mixed knowledge domain (concepts + stories + problems)?
- How should the system score user responses in a CLI context? (There's no 0-5 scale card flip like Anki — the user is typing natural language answers.)
- How to handle "passive encounters" (you worked with Observer pattern today) vs. "active recall" (quiz asks about Observer pattern)? Should passive encounters reset/extend the review interval?
- What's the minimum viable spaced repetition implementation that provides real value without over-engineering?

### 5. Knowledge Bank Schema and Structure
- What fields should each knowledge bank entry have? (Name, category, difficulty, related interview questions, key talking points, common follow-ups, code examples?)
- YAML vs JSON vs Markdown frontmatter for entry format — tradeoffs for human readability, machine parsing, and Claude's ability to work with the content?
- How to handle cross-domain entries (e.g., LRU Cache is both an algorithm problem AND an OOD design AND a system design concept)?
- How large can the knowledge bank grow before performance degrades? Hundreds? Thousands of entries?
- Should the knowledge bank be flat files or a structured database (SQLite)?

### 6. Feature Portfolio Design
- Prior art in "project portfolio" tools for developers — especially automated ones that extract summaries from specs/PRs?
- What makes a portfolio entry useful for interview prep vs. just a documentation artifact?
- How to keep entries current as features evolve (spec → implementation → iteration)?
- Should portfolio entries include links/references back to the original spec or repo?

### 7. Prior Art and Competitive Landscape
- Are there existing tools that map daily coding work to interview prep concepts? (Anki integrations, IDE plugins, LLM-powered prep tools?)
- How do existing spaced repetition tools (Anki, SuperMemo, Mochi) handle non-flashcard content (essays, code, stories)?
- What interview prep platforms exist that use AI/LLM analysis? How do they work?
- Any research on "passive learning" or "incidental learning" from professional practice — does it actually work for interview prep?

### 8. Risk Assessment
- What's the risk that this system becomes noise that the user ignores? Mitigation strategies?
- Privacy/security concerns with logging all work to ~/.interview-prep/ — any content that shouldn't be persisted?
- Performance impact of running an MCP server with every Claude Code session (startup time, memory, CPU)?
- What happens when Claude models are updated and instruction-following behavior changes?

## Specific Questions

1. What is the optimal MCP tool API surface for this system? (List specific tools with their purpose.)
2. What relevance-matching approach provides the best accuracy-to-latency ratio for matching code work to ~200-500 knowledge bank entries?
3. How should "passive encounters" (working with a pattern) interact with spaced repetition scheduling — should they count as a review?
4. What is the failure mode when Claude's context window is nearly full — will it skip the interview_relevance_check call? How to make the instruction robust?
5. Is there research on the effectiveness of passive/incidental learning integrated into professional workflows?
6. What's the right knowledge bank entry density — should system design have 20 entries or 200? Where's the diminishing return?
7. How should STAR story outlines be structured for maximum interview utility — what fields/sections matter most?
8. Should the MCP server use embeddings for semantic matching, or is keyword/tag-based matching sufficient for a ~500-entry knowledge bank?
9. What spaced repetition algorithm is best suited for mixed-type content (concepts, stories, code problems) in a CLI context?
10. Are there Claude Code plugins in the wild today that use instruction-driven MCP auto-invocation? What are their lessons learned?

## Output Format

Please provide structured findings organized by research area, with:
- **Key findings** — what the research reveals
- **Actionable recommendations** — specific decisions we should make based on the evidence
- **Examples** — concrete examples, code snippets, or schemas where applicable
- **Risks and mitigations** — anything that could go wrong and how to prevent it
- **Sources** — links to relevant documentation, papers, tools, or projects
