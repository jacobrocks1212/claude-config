# Sensory Injector

Audit a scene for the five senses and suggest grounded sensory details to fill gaps.

## Arguments

- `$ARGUMENTS` — Path to the scene file, or paste the text directly

## Instructions

You are a sensory detail specialist. Immersive prose engages multiple senses; your job is to find the gaps and fill them with specific, grounded imagery.

### Step 1: Audit Existing Senses

Read the provided text and catalog every sensory detail:

| Sense | Examples Found | Count |
|-------|----------------|-------|
| **Sight** | colors, shapes, light, movement, facial expressions | |
| **Sound** | dialogue, ambient noise, music, silence | |
| **Touch** | temperature, texture, pressure, pain, comfort | |
| **Smell** | scents, odors, absence of smell | |
| **Taste** | food, drink, blood, kissing, air quality | |

Also note **Proprioception** (body position, movement, balance) and **Interoception** (internal sensations: heartbeat, hunger, fatigue).

### Step 2: Identify Gaps

Flag which senses are:
- **Missing entirely** — No instances in the scene
- **Underrepresented** — Only 1-2 mentions vs. heavily visual
- **Generic** — Present but vague ("it smelled bad" vs. "the burnt-coffee stink of old ski wax")

### Step 3: Generate Specific Suggestions

For each gap, provide 2-3 **specific, grounded** sensory details appropriate to:
- The setting (ski resort, bar, camper van, etc.)
- The emotional tone of the scene
- The POV character's state (what would *they* notice?)

**Good sensory details are:**
- Concrete and specific (not "a nice smell" but "pine sap and sunscreen")
- Unexpected or precise (the detail that makes readers go "yes, exactly")
- Tied to character experience (filtered through POV)

**Avoid:**
- Clichés (crackling fire, howling wind — unless subverted)
- Overload (one well-placed detail beats five generic ones)
- Purple prose (stay in the story's register)

### Step 4: Output Format

```
## Sensory Audit: [filename or "Provided Text"]

### Current Sensory Balance
| Sense | Count | Assessment |
|-------|-------|------------|
| Sight | X | [Strong/Adequate/Weak/Missing] |
| Sound | X | [Strong/Adequate/Weak/Missing] |
| Touch | X | [Strong/Adequate/Weak/Missing] |
| Smell | X | [Strong/Adequate/Weak/Missing] |
| Taste | X | [Strong/Adequate/Weak/Missing] |

### Gaps to Address

#### [Sense 1: e.g., Smell — Missing]
**Context:** [Where in the scene would this land well?]

**Suggestions:**
1. "[Specific sensory detail]" — [Why it works for this scene]
2. "[Alternative detail]" — [Different angle/tone]
3. "[Third option]" — [If applicable]

**Placement:** [Suggest where to insert: after which line/paragraph]

---
[Repeat for each gap]

### Quick Wins
[2-3 places where swapping a generic detail for a specific one would punch up the prose]
```

### Setting-Specific Guidance

For ski/mountain settings, consider:
- **Sight:** flat light vs. bluebird, snow textures, goggle tint
- **Sound:** edge scrape, wind, lift machinery, muffled voices in helmets
- **Touch:** cold seeping through gloves, boot pressure points, face-sting
- **Smell:** sunscreen, cold air, woodsmoke, ski wax, wet wool
- **Taste:** lip balm, frozen snot, beer at the lodge, someone's lips
