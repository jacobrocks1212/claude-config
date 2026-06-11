# Interview Prep Plugin — Research Summary

**Source:** Gemini Deep Research, 2026-04-21
**Full research:** [RESEARCH.md](./RESEARCH.md)

---

## Key Findings That Impact Our Design

### 1. FSRS Should Replace SM-2

The research makes a strong case for the **Free Spaced Repetition Scheduler (FSRS)** over SM-2. SM-2's single "Ease Factor" is a blunt heuristic — it over-reviews well-retained items and resets completely on failure. FSRS uses three continuous variables (Difficulty, Retrievability, Stability) modeled via ML, targeting reviews precisely at the forgetting threshold.

**Impact:** Reduces daily review burden by 20-30% vs SM-2 with equal or better retention. Python implementation exists: **py-fsrs** on PyPI. Implementations also available in TypeScript, Rust, Go.

**Recommendation:** Switch from SM-2 to FSRS. The py-fsrs library is production-ready and decoupled from any UI framework.

### 2. Passive Encounters ≠ Active Recall

Research on incidental learning (Marsick & Watkins model) and desirable difficulties (Bjork) confirms a critical distinction:

- **Passive encounters** (seeing a pattern while working) create weak, transient neural encodings — the "illusion of competence."
- **Active recall** (reconstructing knowledge without assistance) is what actually strengthens memory.

The system's end-of-task callouts are passive encounters. They build awareness but don't build retention by themselves. Only the quiz/active-recall component builds durable memory.

**Recommendation:** Track passive encounters and active recall separately in FSRS state. Passive encounters should extend the review window slightly (you were reminded) but should NOT reset the interval the way a successful active recall does. This prevents the system from thinking you "know" something just because you saw it while working.

### 3. Three-Tier Knowledge Retrieval (claude-mem Pattern)

The claude-mem plugin demonstrates an efficient pattern for MCP knowledge queries:
1. **Compact index** — return IDs, titles, categories (50-100 tokens per result)
2. **Timeline/context** — chronological surrounding context (100-200 tokens)
3. **Full detail** — complete entry only when strictly necessary

This prevents context window bloat from dumping the entire knowledge bank into Claude's context.

**Recommendation:** The MCP server's `interview_relevance_check` tool should return a compact, pre-formatted result — not the full knowledge bank entry. A separate `interview_detail` tool can return the full entry if Claude or the user wants to go deeper.

### 4. Cognitive Forcing for Quiz Mode

Research on LLM-powered coding assistants (LeetCoach study, AAAI 2026) shows that providing scaffolded guidance rather than complete answers leads to substantially better learning outcomes. The key: force the user to bridge the final conceptual gap independently.

**Recommendation:** Quiz mode should present the question and wait for the user's response before revealing key points. Don't show the answer alongside the question — that's passive review, not active recall.

### 5. LLM-Based Response Scoring

Traditional spaced repetition relies on self-reported difficulty ratings (1-5 scale), which introduces subjective bias. Research shows LLMs can objectively score free-text responses using semantic similarity, enabling automated FSRS difficulty/retrievability updates without self-assessment friction.

**Recommendation:** In quiz mode, Claude evaluates the user's natural language answer against the knowledge bank entry and assigns a score. This score feeds directly into FSRS. No manual "how hard was that?" step.

### 6. Prior Art: Case Study Maker (Portfolio Validation)

The **case-study-maker** Cursor plugin (julieclarkson/case-study-maker) uses post-commit hooks and session-end triggers to capture the build process into portfolio case studies. It writes to an append-only `.case-study/events.json` file and uses AI to draft reflection questions.

**Validation:** Our feature portfolio concept is validated by real prior art. Key differences: we focus on interview utility (decisions, tradeoffs, interview angles) rather than marketing case studies.

### 7. Design Pattern Detection from Code Diffs

Research (SVM + LLM approaches) confirms that design patterns can be detected from code diffs. However, for our use case, Claude is already analyzing the work contextually — a separate ML classifier would be redundant. The instruction-driven approach (Claude checks the knowledge bank via MCP tool) is the right architecture.

**Recommendation:** No separate pattern detection layer. Claude's native understanding of the work, combined with the structured knowledge bank, is sufficient for relevance matching.

### 8. Plugin Architecture Confirmed

The research confirms the plugin manifest schema:
- `.claude-plugin/plugin.json` — required manifest
- `skills/`, `agents/`, `hooks/`, `commands/` — at plugin root
- `.mcp.json` — MCP server configuration
- Plugin-level CLAUDE.md instructs Claude's behavior

CLAUDE.md precedence: Managed Policy > Global User > Project > Path-Gated > Local. Plugin instructions load at session initialization.

**One concern:** The research notes that write hooks can occasionally block legitimate `.md` file creation. If the MCP server writes findings to `~/.interview-prep/`, this should not be an issue since it's outside the project directory.

---

## Spec Adjustments Based on Research

| Decision | Before Research | After Research | Rationale |
|---|---|---|---|
| SRS algorithm | SM-2 | **FSRS (py-fsrs)** | 20-30% more efficient, predictive vs heuristic |
| Passive encounter tracking | Counted same as active recall | **Tracked separately** — extends but doesn't reset review interval | Passive ≠ active recall; prevents false confidence |
| MCP result format | TBD | **Compact pre-formatted result** from MCP, separate detail tool | Prevents context bloat (claude-mem pattern) |
| Quiz answer scoring | Self-reported difficulty | **Claude evaluates response** → FSRS score | Removes subjective bias, zero friction |
| Quiz answer display | TBD | **Cognitive forcing** — question first, wait for response, then reveal | Maximizes desirable difficulty |
| Pattern detection | TBD | **Claude's native understanding** via instruction-driven MCP call | Separate ML classifier is redundant |
| Portfolio approach | Original design | **Validated by case-study-maker prior art** | Same pattern, interview-focused instead of marketing |

---

## Ideas to Consider (Not Yet Decided)

1. **Load balancing for FSRS** — FSRS Helper supports dispersing due items across days and subjects. Useful if the queue gets large.
2. **Leech detection** — items persistently forgotten should be flagged for breakdown into smaller atomic concepts (per medical education practice).
3. **Separate MCP tools vs. single tool** — research suggests multiple focused tools (relevance check, quiz, detail lookup, portfolio update) rather than one monolithic tool.
4. **Privacy model** — findings are stored locally, but should we exclude certain content types (credentials, proprietary code snippets) from persistence?
