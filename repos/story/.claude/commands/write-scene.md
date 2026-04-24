# Write Scene: $ARGUMENTS

You are writing a specific scene from "Fresh Tracks & Fire."

## Argument Format

The argument should specify the chapter and scene, e.g.:
- `4.1` — Chapter 4, Scene 1
- `4 scene 2` — Chapter 4, Scene 2
- `the-shuttle scene 1` — Chapter "The Shuttle", Scene 1
- *(no argument)* — Automatically continue with the next unwritten scene

## Inferring the Next Scene (No Arguments)

If no argument is provided, determine the next scene to write:

1. **Scan existing scenes** — Look at `Chapters/*/scenes/scene-*.md` to find what's been written
2. **Find the current chapter** — Identify the chapter with the most recent scene files
3. **Check the chapter outline** — Read `Chapters/[chapter]/outline.md` to see total scenes in chapter
4. **Determine next scene:**
   - If current chapter has more scenes in outline → next scene in same chapter
   - If current chapter is complete → first scene of next chapter
   - If no scenes exist → Chapter 1, Scene 1
5. **Confirm with user** — State which scene you're about to write and ask for confirmation before proceeding

## Your Task

1. **Load Context** — Read the following files:
   - `Chapters/[chapter]/outline.md` — The refined chapter outline (find the specific scene)
   - `Chapters/*/scenes/*.md` — ALL scenes from previous chapters (for continuity — look for established details like vehicles, logistics, callbacks, character facts)
   - `Chapters/[chapter]/scenes/scene-[N-1].md` — The previous scene in this chapter (if not Scene 1)
   - `Docs/writing-rules.md` — Writing guidelines (always read this)
   - `Docs/used-phrases.md` — **Phrases to avoid repeating** (always read this)
   - `Characters/jake.md` — Jake's voice and traits (always, since he's POV)
   - `Characters/sadie.md` — If Sadie is in the scene
   - `Characters/josh.md` — If Josh is in the scene
   - `Characters/georgia.md` — If Georgia is in the scene
   - `Docs/short-story.md` — If adapting existing material

2. **Confirm Understanding** — Before writing, briefly confirm:
   - Which scene you're writing
   - The emotional beat to hit
   - Key moments to include
   - Any source material being adapted
   - Ask if there's anything specific the user wants emphasized

3. **Write the Scene** — Draft the scene following these guidelines:
   - **POV:** First person, Jake's voice (casual, clever, observant)
   - **Tone:** Match the established style in `Docs/short-story.md`
   - **Length:** Appropriate to the scene's weight (action scenes longer, transitions shorter)
   - **Sensory detail:** Ground in the ski/mountain setting
   - **Character voice:** Reference character sheets for dialogue
   - **Sadie's eyebrows:** Use as emotional shorthand when she's present

4. **Present for Review** — Share the draft and ask:
   - Does this hit the right beat?
   - Any moments to expand or trim?
   - Dialogue adjustments?

5. **Iterate Until Satisfied** — The scene stays in conversation until `/save`:
   - Continue revising here for broad changes
   - Use `/revise-scene` for surgical line-by-line edits
   - Use `/save` when ready to write to disk and update refs
   - **Do not save to file** — `/save` handles that

## Writing Reminders

From `Docs/writing-rules.md`:
- Show, don't explain — let character details emerge through action/dialogue
- Keep dialogue tight — trim redundant words
- Use real brands (Google Maps, Taco Bell) not generic terms
- Ground dialogue in physical beats (eye rolls, sighs, fidgeting)
- Banter is two-way — characters dish it back

From `Docs/used-phrases.md`:
- **Check before writing** — Avoid reusing distinctive phrases, similes, and structural patterns
- Watch for overused patterns: "the kind of [X] that [Y]", "[body part] did something"
- Vary Sadie's eyebrow descriptions — many variations already used
- Character visual identifiers can repeat: grey fuzz (Sadie), rainbow bun (Josh), sunflower pack (Jake)

From CLAUDE.md:
- Jake's voice: Casual, conversational, funny in a clever way, observant, honest but careful with words
- Sadie: Confident, playful, slightly teasing, highly skilled but modest
- No interpersonal conflict between Jake and Sadie
- Build tension through external obstacles and anticipation
- Two intimate scenes should feel distinct (smoke shack = raw/adrenaline, van = intentional/savoring)

## Related Skills

**Primary next steps:**
- **`/revise-scene`** — Make surgical edits with line/paragraph markup. Scene stays in memory.
- **`/save`** — Write scene to disk and update all refs. Run this when done.

**Optional refinement passes (before /save):**
- **`/show-dont-tell-sweep`** — Scan the draft for abstract "telling" language and get concrete "showing" alternatives
- **`/sensory-injector`** — Audit the scene for sensory balance and get specific details to fill gaps (especially useful for ski/mountain settings)
- **`/prose-voice-aligner`** — Check that the new scene matches Jake's established narrative voice from `short-story.md`
- **`/continuity-policing`** — Verify consistency against character sheets and prior scenes

## Begin

- **If argument provided:** Read the refined chapter outline to find the specified scene, then confirm your understanding before writing.
- **If no argument:** Scan existing scene files to infer the next scene, confirm with the user, then proceed with the standard workflow.
