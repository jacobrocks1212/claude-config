# Prose Voice Aligner

Ensure new writing matches the established narrative voice.

## Arguments

- `$ARGUMENTS` — Path to the new scene/chapter to analyze

## Instructions

You are a style editor ensuring voice consistency across a manuscript. The author has an established voice; your job is to identify drift.

### Step 1: Load Voice Reference

Read `Docs/short-story.md` (the original source material) to internalize the target voice. Also reference `Characters/jake.md` for POV voice specifics. Analyze for:

**Sentence Architecture**
- Average sentence length and variance
- Simple vs. compound vs. complex sentence ratio
- Characteristic rhythms (punchy? flowing? staccato?)

**Vocabulary Profile**
- Register (casual, literary, technical, colloquial)
- Recurring word choices and pet phrases
- Avoidance patterns (words the author never uses)

**Narrative Habits**
- POV distance (deep interiority vs. observational)
- Use of metaphor and simile (frequent? sparse? what domains?)
- Dialogue tag style (said-only? action beats? variety?)
- Paragraph length and white space usage

### Step 2: Analyze New Writing

Read the file specified in `$ARGUMENTS`. Compare against the voice profile.

### Step 3: Flag Voice Drift

Identify passages where the new writing diverges from established patterns:

**Register Shifts** — Suddenly more formal or casual than baseline
**Rhythm Breaks** — Sentence structures atypical for this voice
**Vocabulary Outliers** — Words that feel imported from a different author
**POV Drift** — Shifting closer or further from character interiority
**Tonal Inconsistency** — Humor, sarcasm, earnestness levels off-baseline

### Step 4: Output Format

```
## Voice Alignment Report: [filename]

### Voice Profile Summary
[2-3 sentences summarizing the target voice from style-samples.md]

### Aligned Passages
[Quote 1-2 passages that nail the voice, explaining why]

### Drift Detected

#### [Passage 1]
> "[quoted text]"

**Issue:** [What's off — rhythm, register, vocabulary, etc.]
**Suggestion:** [Revision that realigns with voice]

---
[Repeat for each drift instance]

### Overall Assessment
[Is this fundamentally in-voice with minor fixes, or a larger revision needed?]
```

### Notes

- Some drift is intentional (character growth, tonal shifts). Flag but don't force uniformity.
- The voice reference is `Docs/short-story.md` — the original source material that establishes the project's tone.
