---
description: "View and manually adjust rule weights for the review system"
argument-hint: "[view|set RULE_ID WEIGHT|reset RULE_ID]"
allowed-tools: ["Read", "Edit", "AskUserQuestion"]
---

# Rule Weights

View and manually adjust the per-rule weight system used by the review pipeline.

**Input:** "$ARGUMENTS"

**Plugin root:** `~/.claude/plugins/local-tools/plugins/cognito-pr-review`

**Weights file:** `{plugin_root}/knowledge/weights.yaml`

**Rules files:** `{plugin_root}/knowledge/rules/`

## Mode Selection

Parse `$ARGUMENTS`:
- Empty or `view` → **Mode 1: View**
- Starts with `set ` → **Mode 2: Set** (format: `set {rule_id} {weight}`)
- Starts with `reset ` → **Mode 3: Reset** (format: `reset {rule_id}`)

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

Read `{plugin_root}/knowledge/weights.yaml` and display the following sections.

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

### 3. Rule Weights Table

To build this table:
1. Read `{plugin_root}/knowledge/weights.yaml` to get all `rule_weights` entries.
2. Read each YAML file in `{plugin_root}/knowledge/rules/` to determine which file each rule ID lives in, then map to a category key using the table above.
3. Compute `effective_weight = weight × category_multiplier` for each rule.
4. Sort rows by `effective_weight` descending.

Display:

| Rule ID | Weight | Data Points | Category | Cat. Multiplier | Effective Weight |
|---------|--------|-------------|----------|-----------------|------------------|
| ... | ... | ... | ... | ... | ... |

Round effective weights to 4 decimal places.

### 4. Summary Statistics

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

Parse `$ARGUMENTS` as `set {rule_id} {weight}`.

**Steps:**

1. **Validate rule ID** — check that `{rule_id}` exists as a key under `rule_weights` in weights.yaml. If not found, output an error: `Rule "{rule_id}" not found in weights.yaml` and stop.

2. **Validate weight** — parse `{weight}` as a float. If it is not between 0.0 and 1.0 inclusive, output: `Weight must be between 0.0 and 1.0` and stop.

3. **Read current value** — note the existing `weight` value for `{rule_id}`.

4. **Confirm via AskUserQuestion:**
   ```
   Set {rule_id} weight from {old_weight} to {new_weight}? This is a manual override.
   ```
   Options: `Yes, update it` / `Cancel`

5. **If confirmed:** Edit weights.yaml — update the `weight` field for `{rule_id}` to `{new_weight}`. Do not change `data_points`.

6. **Report:**
   ```
   Updated {rule_id}:
     Weight:           {old_weight} → {new_weight}
     Category:         {category}
     Cat. Multiplier:  {multiplier}
     Effective Weight: {new_weight × multiplier}
   ```

---

## Mode 3: Reset

Parse `$ARGUMENTS` as `reset {rule_id}`.

**Steps:**

1. **Validate rule ID** — check that `{rule_id}` exists under `rule_weights` in weights.yaml. If not found, output: `Rule "{rule_id}" not found in weights.yaml` and stop.

2. **Read current values** — note the existing `weight` and `data_points`.

3. **Confirm via AskUserQuestion:**
   ```
   Reset {rule_id} to default (weight: 0.7, data_points: 0)?
   Current values: weight={current_weight}, data_points={current_data_points}
   ```
   Options: `Yes, reset it` / `Cancel`

4. **If confirmed:** Edit weights.yaml — set `weight: 0.7` and `data_points: 0` for `{rule_id}`.

5. **Report:**
   ```
   Reset {rule_id}:
     Weight:           {old_weight} → 0.7
     Data Points:      {old_data_points} → 0
     Category:         {category}
     Cat. Multiplier:  {multiplier}
     Effective Weight: {0.7 × multiplier}
   ```

---

## Notes

- **Effective weight** = rule weight × category multiplier. This is what the review pipeline uses to prioritize findings.
- **Weight range:** 0.0 (never surface) to 1.0 (always surface when detected).
- **Default weight** for new rules: 0.7.
- **EMA calibration** updates weights automatically via `/cognito-pr-review:calibrate` or `/cognito-pr-review:learn-from-pr`. Manual `set` overrides are preserved until the next calibration run replaces them.
- **Category multipliers** are defined in `weights.yaml` under `category_multipliers` and apply uniformly to all rules in that category. They are not editable via this command — edit `weights.yaml` directly.
