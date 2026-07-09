---
description: "View and manually adjust rule weights for the review system"
argument-hint: "[view|set RULE_ID WEIGHT|reset RULE_ID]"
allowed-tools: ["Read", "Edit", "AskUserQuestion"]
---

# Rule Weights

View and manually adjust the per-rule weight system used by the review pipeline.

**Input:** "$ARGUMENTS"

**Plugin root:** `~/.claude/plugins/local-tools/plugins/cognito-pr-review`

**Weights file (mutable state):** `~/.claude/state/cognito-pr-review/weights.yaml` — this is the file ALL modes read and edit. It is seeded from the plugin's `knowledge/weights.yaml` on first use; the knowledge copy is the shipped-defaults seed and is **never** edited by this command. If the state file does not exist yet, copy the seed there first, then proceed.

**Seed file (read-only defaults):** `{plugin_root}/knowledge/weights.yaml`

**Rules files:** `{plugin_root}/knowledge/rules/`

## Mode Selection

Parse `$ARGUMENTS`:
- Empty or `view` → **Mode 1: View**
- Starts with `set ` → **Mode 2: Set** (format: `set {id} {weight}` — `{id}` is a rule ID under `rule_weights` or a source key under `source_weights`)
- Starts with `reset ` → **Mode 3: Reset** (format: `reset {id}` — same ID resolution)

**ID resolution (Set/Reset):** look up `{id}` first under `rule_weights`; if not found there, look under `source_weights` (source keys: `investigation`, `sweep`, `reuse`, `intrafile`). If found in neither, error: `"{id}" not found under rule_weights or source_weights` and stop.

---

## Category-to-File Mapping

To determine a rule's category, look at which YAML file it lives in:

| YAML File | Category Key |
|-----------|-------------|
| api-design.yaml | api_design |
| csharp-architecture.yaml | architecture |
| code-consistency.yaml | consistency |
| frontend-vue.yaml | frontend |
| performance.yaml | performance |
| security.yaml | security |
| template-binding.yaml | template_binding |
| testing.yaml | testing |

---

## Mode 1: View (default)

Read the state file (`~/.claude/state/cognito-pr-review/weights.yaml`) and display the following sections.

### 1. Metadata

Display a summary block:
```
Version:            {version}
Last Calibrated:    {last_calibrated or "never"}
Calibration PRs:    {count of calibration_prs}
EMA Alpha:          {ema_alpha}
```

### 2. Category Multipliers

Display as a table:

| Category | Multiplier |
|----------|-----------|
| architecture | {multiplier} |
| frontend | {multiplier} |
| api_design | {multiplier} |
| consistency | {multiplier} |
| testing | {multiplier} |
| security | {multiplier} |
| performance | {multiplier} |
| template_binding | {multiplier} |

### 3. Source Weights Table

Display the `source_weights` entries (the per-source lane weights post-process applies to non-sweep findings):

| Source | Weight | Data Points |
|--------|--------|-------------|
| investigation | {weight} | {data_points} |
| sweep | {weight} | {data_points} |
| reuse | {weight} | {data_points} |
| intrafile | {weight} | {data_points} |

**Schema note:** `source_weights` entries are nested objects `{weight, data_points}`. A legacy scalar entry (e.g. `investigation: 0.9`) is still accepted — display it as `weight: {scalar}, data_points: 0`.

### 4. Rule Weights Table

To build this table:
1. Read the state file to get all `rule_weights` entries.
2. Read each YAML file in `{plugin_root}/knowledge/rules/` to determine which file each rule ID lives in, then map to a category key using the table above.
3. Compute `effective_weight = weight × category_multiplier` for each rule.
4. Sort rows by `effective_weight` descending.

Display:

| Rule ID | Weight | Data Points | Category | Cat. Multiplier | Effective Weight |
|---------|--------|-------------|----------|-----------------|------------------|
| ... | ... | ... | ... | ... | ... |

Round effective weights to 4 decimal places.

### 5. Summary Statistics

Display:
```
Total rules:                    {count}
Rules with calibration data:    {count where data_points > 0}
Average weight:                 {avg weight, 4 decimal places}
Average effective weight:       {avg effective_weight, 4 decimal places}

Lowest effective weight (bottom 5):
  {rule_id}: {effective_weight}
  ...

Highest effective weight (top 5):
  {rule_id}: {effective_weight}
  ...
```

---

## Mode 2: Set

Parse `$ARGUMENTS` as `set {id} {weight}`.

**Steps:**

1. **Resolve the ID** — per the ID-resolution rule above (rule_weights first, then source_weights). If found in neither, error and stop.

2. **Validate weight** — parse `{weight}` as a float. If it is not between 0.0 and 1.0 inclusive, output: `Weight must be between 0.0 and 1.0` and stop.

3. **Floor warnings** (non-blocking — the set still proceeds if confirmed):
   - If `{weight}` < **0.3** (`MIN_EFFECTIVE_WEIGHT` in `scripts/weight-constants.ts`): warn that findings gated by this weight can fall below the pipeline's effective-weight threshold and be dropped entirely.
   - Else if `{weight}` < **0.35** (`WEIGHT_FLOOR` in `scripts/weight-constants.ts`): warn that this is below the calibration floor — the EMA writer never goes this low on its own, so this is a stronger override than calibration would ever produce.

4. **Read current value** — note the existing `weight` value for `{id}` (for a legacy scalar `source_weights` entry, the scalar IS the weight).

5. **Confirm via AskUserQuestion:**
   ```
   Set {id} weight from {old_weight} to {new_weight}? This is a manual override.
   {Include any floor warning from step 3 here.}
   ```
   Options: `Yes, update it` / `Cancel`

6. **If confirmed:** Edit the state file — update the `weight` field for `{id}` to `{new_weight}`. Do not change `data_points`. (If the target is a legacy scalar `source_weights` entry, upgrade it to the nested form `{weight: {new_weight}, data_points: 0}`.) Never edit the knowledge seed.

7. **Report:**
   ```
   Updated {id}:
     Weight:           {old_weight} → {new_weight}
     Category:         {category — rule entries only; sources have none}
     Cat. Multiplier:  {multiplier — rule entries only}
     Effective Weight: {new_weight × multiplier — rule entries; new_weight for sources}
   ```

---

## Mode 3: Reset

Parse `$ARGUMENTS` as `reset {id}`.

**Steps:**

1. **Resolve the ID** — per the ID-resolution rule above (rule_weights first, then source_weights). If found in neither, error and stop.

2. **Determine the reset target:**
   - **Rule entry:** default `weight: 0.7`, `data_points: 0`.
   - **Source entry:** the seed value for that source from `{plugin_root}/knowledge/weights.yaml` (shipped default), `data_points: 0`.

3. **Read current values** — note the existing `weight` and `data_points`.

4. **Confirm via AskUserQuestion:**
   ```
   Reset {id} to default (weight: {reset_weight}, data_points: 0)?
   Current values: weight={current_weight}, data_points={current_data_points}
   ```
   Options: `Yes, reset it` / `Cancel`

5. **If confirmed:** Edit the state file — set `weight: {reset_weight}` and `data_points: 0` for `{id}` (nested form for source entries). Never edit the knowledge seed.

6. **Report:**
   ```
   Reset {id}:
     Weight:           {old_weight} → {reset_weight}
     Data Points:      {old_data_points} → 0
     Category:         {category — rule entries only}
     Cat. Multiplier:  {multiplier — rule entries only}
     Effective Weight: {reset_weight × multiplier — rule entries; reset_weight for sources}
   ```

---

## Notes

- **Effective weight** = rule weight × category multiplier. This is what the review pipeline uses to prioritize findings. Source-level weights (`source_weights`) apply per lane instead: `weight × confidence`.
- **Weight range:** 0.0 (never surface) to 1.0 (always surface when detected). Shared pipeline constants live in `scripts/weight-constants.ts`: `MIN_EFFECTIVE_WEIGHT = 0.3` (drop threshold), `WEIGHT_FLOOR = 0.35` / `WEIGHT_CEIL = 1.0` (calibration clamp).
- **Default weight** for new rules: 0.7. Source defaults come from the knowledge seed.
- **State vs seed:** all reads/writes here target the mutable state file `~/.claude/state/cognito-pr-review/weights.yaml`; `{plugin_root}/knowledge/weights.yaml` is the shipped-defaults seed (used to initialize the state file and as the reset source for `source_weights`) and is never edited by this command.
- **Schema:** both `rule_weights` and `source_weights` entries are nested `{weight, data_points}` objects; legacy scalar `source_weights` entries are still readable and are upgraded to the nested form on first write.
- **EMA calibration** updates weights automatically via `/cognito-pr-review:calibrate`, `/cognito-pr-review:learn-from-pr`, or the buddy session close — all through the single helper `scripts/disposition-calibration.ts`. Manual `set` overrides are preserved until the next calibration run replaces them.
- **Category multipliers** are defined under `category_multipliers` and apply uniformly to all rules in that category. They are not editable via this command — edit the state file directly.
