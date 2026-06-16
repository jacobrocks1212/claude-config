<!-- COMPONENT: change-walkthrough
Reusable "teach me this set of code changes" mechanic. Extracted from the
cognito-pr-review plugin's review-pr-buddy Phase 1 per-chunk loop (Teach +
Socratic Prompt steps), generalized to any repo/language and decoupled from
the PR-review findings/verdict/synthesis machinery.

Consumers supply:
  - {change_set}: the diff/files to explain (already resolved to chunks or a raw diff)
  - {goal}: optional — what the change is trying to accomplish (PR objective,
    commit message, task description), used to ground the "why it matters" framing.
  - {pacing}: "continuous" (default) — explain every chunk in one pass without
    pausing; or "interactive" — pause after each chunk for the reader's response
    before advancing. Consumers that don't set it get "continuous".
Inject into a consumer skill with a cat directive referencing this file
(see explain/SKILL.md Step 2 for the canonical usage).
-->

## Change Walkthrough Protocol

Walk the reader through a set of code changes the way a senior engineer would
explain them over the shoulder: chunk-by-chunk, teaching what changed and *why*,
and prompting the reader to reason — not dumping the raw diff.

### Chunking

Group the changes into logical units before teaching anything. A chunk is a
coherent concern, not necessarily one file:

- Group by what the change *accomplishes* (a behavior, a refactor, a new type, a
  fix), pulling together edits that span multiple files when they serve one purpose.
- Split a single large file into multiple chunks when it touches unrelated concerns.
- Order chunks so earlier ones build the context later ones depend on (data model →
  the logic that uses it → the call sites → tests). Lead with the chunk that best
  explains the change's intent.

Compose a short, semantically logical **title** for each chunk (≈ 2–6 words) that
captures what the chunk *does* — e.g. "Core fallback logic", "API + client-state
sync", "Test coverage for the revert path". You create these titles; don't just
echo file names.

Announce the chunk plan up front: a short ordered list of
`{n}. {chunk title} — {files}` so the reader knows the shape of the walk before it
starts.

### Pacing

How you move between chunks depends on `{pacing}`:

- **continuous** (default) — Explain **every** chunk in a single pass, in order,
  without stopping to ask the reader to continue. Do not say "say next" or wait for
  input between chunks. The whole walkthrough (chunk plan → all chunks → closing) is
  one complete response. The Socratic questions still appear per chunk (see step 2),
  but they're left open for the reader to consider — they do not gate progression.
- **interactive** — Pause after each chunk's Socratic prompt and wait for the
  reader's response before advancing. Discuss if they engage; advance on "next."

### Per-Chunk Loop

For each chunk, in order:

#### 0. Header

Open the chunk with a titled header carrying the chunk's title and the files it
covers:

```
### {chunk title} — {file list}
```

List **every** file that belongs to the chunk. For a file that lives entirely in
this chunk, the bare path is enough; for a file that is **shared across more than
one chunk**, append this chunk's line range (`path:start-end`, or multiple ranges
comma-separated) so the reader knows which portion of the file this chunk is about.
Use the same title here as in the chunk plan.

#### 1. Teach

Give a senior-engineer explanation of this chunk:

- **What changed** — the substance of the edit, in plain terms. Reference
  `file:line` so the reader can follow along, but do **not** paste the raw diff at
  them. Summarize and interpret.
- **Why it matters** — connect the change to `{goal}` (or, if no goal was given, to
  the apparent intent inferred from the surrounding code). What problem does it
  solve, what does it enable, what would break without it.
- **How the author approached it** — the design choice, the pattern used, the
  trade-off taken. Note anything subtle: an invariant being upheld, an edge case
  handled, a convention being followed (or broken).

Ground every claim in the actual changed code and its real context. If you're
unsure why something was done, say so — don't invent a rationale. Tone: concise,
insightful, contextual. A peer explaining, not a doc generator.

#### 2. Socratic Prompt

After teaching, pose 2–4 questions that make the reader reason about the chunk
rather than passively accept it. Good questions probe:

- correctness / edge cases the change might miss
- whether this is the right layer/abstraction for the change
- ripple effects on callers, tests, or adjacent systems
- alternatives the author could have taken and why this one wins (or doesn't)

Do **not** answer your own questions — leave them open for the reader to reason
through. Whether you pause here for a response is governed by `{pacing}` (see
above): in **interactive** mode, pause and wait; in **continuous** mode, pose the
questions and move straight on to the next chunk.

### Going Deeper

At any point the reader may ask to dig into a file, symbol, or concept. Answer
using the changed code plus the surrounding codebase for context (read adjacent
files, callers, definitions as needed). State plainly when you're reading code
*outside* the change set to provide background, versus describing the change itself.

### Closing

After the last chunk, give a one-paragraph synthesis: the through-line of the whole
change set, how the chunks fit together, and the one or two things most worth the
reader's attention.
