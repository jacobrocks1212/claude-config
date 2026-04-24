# Continuity Policing

Scan prose for consistency violations against the story bible and character definitions.

## Arguments

- `$ARGUMENTS` — Path to the prose file or chapter to analyze (e.g., `Chapters/chapter-03.md`)

## Instructions

You are a continuity editor. Your job is to catch inconsistencies before they become plot holes.

### Step 1: Load Reference Materials

Read the following files to establish canon:
- `Docs/outline.md` — Master story structure, timeline, chapter beats
- `Docs/short-story.md` — Original source material, established scenes
- `Characters/*.md` — Character physical descriptions, voice, backstories, relationships

### Step 2: Analyze the Target Prose

Read the file specified in `$ARGUMENTS`. Extract and catalog:
- Character physical descriptions mentioned (eye color, hair, height, scars, etc.)
- Timeline references (times, dates, "three days later", etc.)
- Geographic/spatial claims (distances, travel times, room layouts)
- Object states (what characters are carrying, wearing, driving)
- Relationship states (who knows what, who has met whom)

### Step 3: Cross-Reference Against Canon

Compare extracted details against the reference materials. Flag:

**HARD CONFLICTS** — Direct contradictions (e.g., "blue eyes" when canon says "brown")
**SOFT CONFLICTS** — Plausibility issues (e.g., travel time too fast for distance)
**DRIFT WARNINGS** — Details that don't contradict but weren't established (potential retcons)

### Step 4: Report Format

Output a structured report:

```
## Continuity Report: [filename]

### Hard Conflicts
- [Line X]: "[quoted text]" — Conflicts with [source]: [explanation]

### Soft Conflicts
- [Line X]: "[quoted text]" — [plausibility concern]

### Drift Warnings
- [Line X]: "[quoted text]" — Not established in canon; consider adding to story-bible.md

### Clean
[List any major elements that were checked and found consistent]
```

If no issues are found, say so clearly and note what was verified.
