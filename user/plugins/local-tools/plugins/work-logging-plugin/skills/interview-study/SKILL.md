---
name: interview-study
description: Interactive interview topic study session grounded in your real engineering work
---

# /interview-study

Start an interactive study session for a specific interview topic, using your real work as context.

## Usage

```
/interview-study <topic-slug>           # Study a specific topic (e.g., rate-limiting)
/interview-study <domain>               # Browse topics in a domain (e.g., system-design)
/interview-study                        # Show coverage dashboard, pick a topic
```

## What it does

### 1. Load Context

Call `get_study_context` with the topic slug and domain to load:
- Full KB entry (description, key concepts, interview questions, related topics)
- All features from your work that correlate to this topic
- Relevant work log entries referenced by those features

If no slug is provided, call `get_kb_index` and present topics grouped by domain with coverage indicators (topics with correlated features marked as ready to study).

If a domain name is provided instead of a slug, filter the KB index to that domain and let the user pick.

### 2. Present Study Brief

Summarize what was loaded:
- Topic name, domain, difficulty
- Key concepts (from talking_points)
- Number of correlated features with brief titles
- Interview questions from the KB entry

### 3. Enter Study Mode

Shift into a Socratic Q&A persona. The goal is to help the user practice answering interview questions using their real work as evidence.

**Study mode behaviors:**
- Ask one interview question at a time from the KB entry's `interview_questions` list
- After the user answers, provide feedback: what was strong, what could be sharper, suggest specific details from their features/work log they could weave in
- When the user is satisfied with a story, offer to write it into the corresponding story page's managed block using `write_managed_block`
- Generate domain-appropriate narratives:
  - **system-design**: ADR format (Context & Constraints → Baseline → Bottleneck → Decision & Tradeoffs → Operational Reality)
  - **behavioral**: (I)STAR(T) format (Introduction → Situation → Task → Action → Result → Takeaway)
  - **ood**: Entity-Pattern-Extensibility format
  - **algorithms**: Problem → Approach → Complexity → Your Usage
- Include an SRS flashcard (`Question\n:: Answer`) at the end of each managed block
- Track which stories have been elaborated vs. still placeholder during the session

### 4. Wrap Up

At the end of the session, summarize:
- Topics studied
- Stories elaborated and saved
- Suggested next topics to study (from related_topics or uncovered gaps)

## MCP Tools Used

| Tool | Purpose |
|------|---------|
| `get_study_context` | Load full context for a topic (KB + features + work log) |
| `get_kb_index` | Browse all topics when no specific topic given |
| `get_kb_topic` | Get details for related topics during study |
| `read_features` | Query additional feature context if needed |
| `write_managed_block` | Save elaborated stories to vault pages |

## Tips

- Study topics where you have strong correlated features first — you'll have concrete examples to draw from
- The managed blocks in story pages persist across vault regeneration, so your elaborated stories won't be lost
- Use `/interview-generate` to regenerate the vault after importing new work, then study the new stories
- Related topics shown at the bottom of KB pages are good candidates for your next study session
