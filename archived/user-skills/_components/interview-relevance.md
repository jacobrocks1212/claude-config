### Interview Relevance Evaluation (FINAL STEP)

Evaluate whether the work completed in this skill invocation has interview relevance. Use the work-logging MCP server as a source of topics and questions.

#### Step 1: Summarize Work Context

In 2-3 sentences, summarize what was accomplished:
- What was built, designed, fixed, or specified
- Key architectural patterns, design decisions, tradeoffs
- Technologies and concepts involved

#### Step 2: Fetch Knowledge Bank Index

Call `get_kb_index` (work-logging MCP) to retrieve the compact topic index.

#### Step 3: Evaluate Relevance

Scan the topic index against your understanding of the work just completed. For each topic, ask:
1. Does this work **demonstrate** or **exercise** this concept in a non-trivial way?
2. Could this work serve as a **real-world example** when discussing this topic in an interview?
3. Is the connection **substantive** (not superficial keyword overlap)?

A topic is relevant if at least 2 of 3 answers are yes.

#### Step 4: Record and Present Findings

For each relevant topic:
1. Call `interview_detail(slug, domain)` for the full KB entry
2. Call `interview_record_findings(work_summary, skill_invoked, matches)` to persist

Present results:
- **Topic** and domain
- **What you did** — specific to the current work, not generic
- **Interview angle** — sample question this maps to (from KB entry)
- **Talking points** — top 2-3 points to hit
- **STAR hook** (behavioral matches only)
- **Saved to** — persistence path

**SILENCE RULE:** If no topics are relevant, produce ZERO output about this step. No "no matches", no "checking relevance", nothing.

#### Step 5: Portfolio Update (for /spec and /implement-phase only)

If the invoking skill produced a feature spec or completed an implementation phase, also call `interview_portfolio_update` with the feature details.
