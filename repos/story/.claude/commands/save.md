# Save: $ARGUMENTS

Finalizes a scene or chapter outline by writing it to disk and updating reference documents.

## Argument Format

The argument should specify what to save:

**Scenes:**
- `4.1` — Chapter 4, Scene 1
- `4 scene 2` — Chapter 4, Scene 2
- *(no argument)* — Use the scene currently in conversation

**Outlines:**
- `outline 6` — Chapter 6 outline
- `chapter 6 outline` — Chapter 6 outline
- `6 outline` — Chapter 6 outline

## Your Task

### If Saving an Outline

1. **Identify the chapter** — From argument or current conversation
2. **Determine file path:** `Chapters/[N]-[chapter-name]/outline.md`
3. **Create directory if needed** — Ensure `Chapters/[N]-[chapter-name]/` exists
4. **Write the outline file** — Save using the standard outline format (see below)
5. **Confirm:** "✓ Saved outline to `Chapters/[N]-[chapter-name]/outline.md`"
6. **Done** — Outlines don't require pattern analysis; skip to completion

### If Saving a Scene

#### Phase 1: Write Scene to Disk

1. **Identify the scene** — From argument or current conversation
2. **Determine file path:** `Chapters/[N]-[chapter-name]/scenes/scene-[N].md`
3. **Create directory if needed** — Ensure `Chapters/[N]-[chapter-name]/scenes/` exists
4. **Write the scene file** — Save the final scene content
5. **Confirm:** "Saved to `Chapters/[N]-[chapter-name]/scenes/scene-[N].md`"

#### Phase 2: Analyze Patterns (from /analyze-edits)

Load reference docs and scan the scene for generalizable patterns:

1. **Load current reference docs:**
   - `Docs/writing-rules.md`
   - `Docs/used-phrases.md`
   - `Characters/jake.md`
   - `Characters/sadie.md` (if she appears)
   - `Characters/josh.md` (if he appears)
   - `Characters/georgia.md` (if she appears)

2. **Analyze the scene for patterns:**
   - **Dialogue style** — Tight phrasing, word choices, speech patterns
   - **Character voice** — Verbal tics, tone, personality traits
   - **Show vs. tell** — Action over exposition
   - **Physical beats** — How dialogue is grounded
   - **Sensory details** — Specific details worth noting
   - **New phrases** — Distinctive turns of phrase, similes, metaphors

3. **Present findings:**
   ```
   ## Analysis: Chapter [N], Scene [N]

   ### Patterns for writing-rules.md
   - ⊕ [Pattern]: "[example]"

   ### Phrases for used-phrases.md
   - ⊕ "[phrase]" — [context]
   - ⊕ "[simile]" — [what it describes]

   ### Character updates
   - ⊕ sadie.md: [new trait or verbal pattern]

   Apply these updates? (y/n/edit)
   ```

#### Phase 3: Update Reference Docs

Once approved:

1. **Update `used-phrases.md`:**
   - Add new phrases to appropriate sections
   - Include `Ch[N] Sc[N]` location tag
   - Update "Last Updated" line at bottom

2. **Update `writing-rules.md`:** (if applicable)
   - Add new rules with context

3. **Update character sheets:** (if applicable)
   - Add new details to appropriate sections

4. **Confirm completion:**
   ```
   ✓ Scene saved to Chapters/[N]-[name]/scenes/scene-[N].md
   ✓ used-phrases.md updated (added X items)
   ✓ [other updates]

   Ready for next scene.
   ```

## Quick Mode

If invoked as `/save quick` or `/save [scene] quick`:
- Write scene to disk
- Auto-apply all detected ref updates (no prompts)
- Show summary of what was added

## When to Use

Run `/save` when you're done with:
- **Outlines:** After `/refine-chapter` finalizes the chapter structure
- **Scenes:** After `/write-scene` or `/revise-scene` completes

## Workflow Position

```
/refine-chapter → /save outline → /write-scene → /revise-scene → ... → /save
                       ↓                              ↑                    ↓
                  (outline)                      (edit loop)        (scene + refs)
```

## Begin

**For outlines:**
1. Get the outline content from conversation
2. Write to disk at `Chapters/[N]-[name]/outline.md`
3. Confirm and done

**For scenes:**
1. Get the scene content from conversation or load from file
2. Write to disk at `Chapters/[N]-[name]/scenes/scene-[N].md`
3. Load refs and analyze for patterns
4. Present and apply updates to reference docs

---

## Outline Format Template

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
