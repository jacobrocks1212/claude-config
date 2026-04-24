# Refine Chapter: $ARGUMENTS

You are helping refine the outline for **Chapter $ARGUMENTS** of "Fresh Tracks & Fire."

## Your Task

1. **Load Context** — Read the following files to understand the chapter's place in the story:
   - `Docs/outline.md` — Find the entry for Chapter $ARGUMENTS
   - `Chapters/*/scenes/*.md` — All scenes from previous chapters (for continuity — established details like vehicles, logistics, character facts, potential callbacks)
   - `Docs/writing-rules.md` — Writing guidelines to inform scene planning
   - `Docs/used-phrases.md` — Review to avoid planning beats that would rehash overused patterns
   - `Characters/jake.md` and `Characters/sadie.md` — Main characters
   - `Characters/josh.md` and `Characters/georgia.md` — If they appear in this chapter
   - `Docs/short-story.md` — If this chapter adapts existing scenes

2. **Present Current State** — Summarize what the outline currently says about this chapter:
   - The chapter's purpose in the overall story
   - Key beats and moments
   - Which characters are present
   - Any source material being adapted

3. **Collaborate on Refinement** — Work with the user to develop a detailed, scene-by-scene breakdown:
   - Break the chapter into discrete scenes (3-6 typically)
   - For each scene, define:
     - **Setting** — Where and when
     - **Characters present** — Who's in the scene
     - **Emotional beat** — What the reader should feel
     - **Key moments** — Specific actions, dialogue beats, or reveals
     - **Transition** — How it leads to the next scene
   - Flag any decisions needed (e.g., "What specifically interrupts the almost-kiss?")

4. **Save the Refined Outline** — Once aligned, create or update the chapter's detailed outline:
   - Create directory: `Chapters/[chapter-number]-[chapter-name]/`
   - Save to: `Chapters/[chapter-number]-[chapter-name]/outline.md`

## Output Format

The refined chapter outline should follow this structure:

```markdown
# Chapter [N]: "[Title]"

## Overview
[2-3 sentences on what this chapter accomplishes]

## Scene 1: [Scene Title]
- **Setting:** [Where/when]
- **Characters:** [Who's present]
- **Beat:** [Emotional purpose]
- **Key Moments:**
  - [Moment 1]
  - [Moment 2]
- **Ends with:** [Transition to next scene]

## Scene 2: [Scene Title]
...

## Notes
- [Any open questions or decisions]
- [Source material being adapted]
- [Character details to emphasize]
```

## Related Skills

**Workflow:**
```
/refine-chapter → /write-scene → /revise-scene → ... → /save
```

- **`/write-scene`** — Draft each scene (stays in memory)
- **`/revise-scene`** — Surgical line-by-line edits (stays in memory)
- **`/save`** — Write to disk + update all refs

**Optional refinement:**
- **`/beat-sheet-expander`** — Break vague plot points into granular, writeable beats
- **`/continuity-policing`** — Verify consistency against character sheets and story canon

## Begin

Start by reading the relevant files, then present what you find and ask clarifying questions to refine the chapter structure.
