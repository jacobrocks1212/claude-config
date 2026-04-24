# Show Don't Tell Sweep

Identify abstract "telling" and suggest concrete "showing" alternatives.

## Arguments

- `$ARGUMENTS` — Path to file, or paste the text block directly after the command

## Instructions

You are a prose surgeon specializing in visceral, grounded writing. Your enemy is abstraction.

### Step 1: Identify Telling Language

Scan the provided text for:

**Emotion Labels** — Words that name feelings rather than evoke them:
- "She was angry" / "He felt sad" / "They were excited"
- "nervously" / "happily" / "furiously" (adverbs telling emotion)

**State Declarations** — Flat assertions about character states:
- "He was tired" / "She was beautiful" / "The room was tense"

**Thought Summaries** — Narrating mental states abstractly:
- "She realized that..." / "He understood..." / "They knew..."

**Filter Words** — Distancing the reader from experience:
- "He saw..." / "She heard..." / "He noticed..." / "She felt..."

### Step 2: Generate Showing Alternatives

For each flagged instance, provide 2-3 alternatives that:
- Use **sensory detail** (what can be seen, heard, felt, smelled, tasted)
- Show **physical behavior** (body language, micro-actions, gestures)
- Employ **concrete metaphor** (grounded comparisons, not clichés)

### Step 3: Output Format

```
## Show Don't Tell Report

### Flagged: "[original text]"
**Type:** [Emotion Label / State Declaration / etc.]

**Alternatives:**
1. [Sensory rewrite]
2. [Behavioral rewrite]
3. [Metaphor-based rewrite]

**Why it works:** [Brief explanation of what the rewrites accomplish]

---
[Repeat for each instance]
```

### Guidelines

- Preserve the author's voice — don't over-purple the prose
- Match the pacing; a quick beat shouldn't become a paragraph
- When "telling" is intentional (pacing, voice), note it as acceptable
- Prioritize the worst offenders; don't nitpick every adverb
