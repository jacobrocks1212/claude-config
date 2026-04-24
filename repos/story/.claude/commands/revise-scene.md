# Revise Scene: $ARGUMENTS

You are making surgical edits to a scene draft, then analyzing patterns for reference doc updates.

## Argument Format

The argument should specify the scene file, e.g.:
- `4.1` — Chapter 4, Scene 1
- `4 scene 2` — Chapter 4, Scene 2
- `the-shuttle scene 1` — Scene 1 of "The Shuttle"
- *(no argument)* — Use the most recently modified scene file

## Edit Markup Syntax

The user can request edits using any of these formats:

### Line-Based Edits
```
line 15: "said" → "murmured"
line 23: "She smiled." → "Her eyebrows lifted—Loss got a smile on you.."
lines 22-25: tighten this
```

### Paragraph-Based Edits
```
p3: add a physical beat where she looks away
p5-6: combine these, too choppy
```

### Search-and-Replace
```
"He wasn't sure why, but" → delete
"the mountain" → "Baldy" (all instances)
```

### Natural Language
```
The dialogue in the middle section feels too on-the-nose — make it more subtle
Add more sensory detail when they step outside
Her response feels too eager — dial it back
```

### Deletions
```
delete line 45
delete "He paused, thinking about..."
cut p3
```

## Your Task

### Phase 1: Load & Present

1. **Find the scene file** — Locate `Chapters/[chapter]/scenes/scene-[N].md`
2. **Load reference context:**
   - `Docs/writing-rules.md`
   - `Docs/used-phrases.md` — Check for phrases to avoid when making edits
   - Relevant character sheets for characters in the scene
3. **Display the current scene** with line numbers for easy reference
4. **Ask for edits** — "What would you like to change?"

### Phase 2: Edit Loop

1. **Parse the edit requests** — Understand what changes are requested
2. **Apply the edits** — Make the changes to the scene
3. **Show the diff** — Display what changed (use `>` for removed, `+` for added, or show before/after blocks)
4. **Ask for more** — "More edits, or done?"
5. **Repeat** until user says "done", "good", "save", etc.

### Phase 3: Hand Off to /save

Once the user says "done", "good", "save", etc.:

1. **Confirm the final state** — Show the complete scene as it now stands
2. **Prompt for /save** — "Ready to finalize? Run `/save` to write to disk and update refs."
3. **Do not write to file** — `/save` handles file writing and ref updates

## Diff Display Format

When showing changes, use this format for clarity:

```
Lines 22-25:
━━━ Before ━━━
"I don't know," she said. "I guess I just felt like it was the right thing to do at the time."
━━━ After ━━━
She shrugged. "Felt right."
```

Or for single-line changes:
```
Line 15: "said softly" → "murmured"
```

## Quick Commands

The user can also use these shortcuts:
- `show` or `current` — Display the current state of the scene with line numbers
- `diff` — Show all changes made this session
- `undo` — Revert the last edit
- `done` / `good` — Exit edit loop and show final scene (then run `/save` to finalize)

## Example Session

```
User: /revise-scene 4.1

Claude: [Displays scene with line numbers]
        What would you like to change?

User: line 15: "said" → "murmured"
      lines 22-25: tighten this, too wordy
      p7: she sounds too eager, dial it back

Claude: Applied 3 edits:

        Line 15: "said" → "murmured"

        Lines 22-25:
        ━━━ Before ━━━
        "I don't know," she said. "I guess I just felt like it was
        the right thing to do at the time, you know?"
        ━━━ After ━━━
        She shrugged. "Felt right."

        Paragraph 7:
        ━━━ Before ━━━
        "Yes! I'd love that." She grabbed her poles...
        ━━━ After ━━━
        "Sure." She grabbed her poles...

        More edits, or done?

User: done

Claude: Here's the final scene:

        [Shows complete scene]

        Ready to finalize? Run `/save 4.1` to write to disk and
        update refs.
```

## Begin

1. **If scene is in conversation** (from `/write-scene`): Work with the current draft directly.
2. **If argument provided:** Load the specified scene from `Chapters/[chapter]/scenes/scene-[N].md`.
3. **If no argument and no scene in conversation:** Find the most recently modified scene file, confirm with user.
4. **Keep the original in memory** so you can show cumulative diffs throughout the session.