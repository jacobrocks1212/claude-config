---
name: build-js
description: Index and navigation aid for build.js (22K+ lines). Invoke before editing build.js to find existing code, avoid duplicates, and understand structure.
triggers:
  - build.js
  - "form.meta.addProperty"
  - "form.meta.addRule"
  - "Cognito.Forms.*Changed"
  - "Cognito.ready"
---

# build.js Navigation Skill

This skill provides an auto-generated index of build.js structures to help you:
- Find existing code before proposing changes
- Avoid creating duplicates
- Understand the file's organization
- Locate HasChanges rules and event handlers

## Index Location

The index is stored at: `~/.claude/skills/build-js/build-js-index.json`

## Before Making Changes

1. **Check index freshness**: Compare `meta.sourceModified` with actual file mtime
2. **Regenerate if stale**: Run `node ~/.claude/skills/build-js/tools/generate-index.mjs`
3. **Search the index** for existing patterns before adding new code

## Regeneration Command

```bash
node ~/.claude/skills/build-js/tools/generate-index.mjs
```

**Worktree support**: The script automatically detects git worktrees via `git rev-parse --show-toplevel`. When running in a worktree, it indexes that worktree's build.js, not the main repo.

## Index Structure

### imports
ES6 imports at file start with source paths and symbols.

### readyBlocks
`Cognito.ready("name", [...deps], fn)` blocks - the main initialization structure.

### regions
`//#region Name` to `//#endregion` pairs for file organization.

### properties
`form.meta.addProperty({ name: "..." })` calls with:
- `line`: Line number
- `name`: Property name
- `type`: Property type
- `isList`: Whether it's a list property
- `isCalculated`: Has `.calculated()` chain
- `onChangeOf`: Dependency array for calculated properties

### rules
`form.meta.addRule({ ... })` calls with:
- `line`: Line number
- `onChangeOf`: Change triggers
- `isHasChangesRule`: Whether this rule affects form dirty state
- `description`: Human-readable purpose

### eventHandlers
`Cognito.Forms.XyzChanged = function` handlers that respond to Vue component events.

### functions
Top-level functions and Cognito.Forms methods (excluding Changed handlers).

## Common Tasks

### Adding a New Computed Property for Vue Binding

1. Search `properties` for similar existing properties
2. Find the property insertion area (~line 1262-1800)
3. Add `form.meta.addProperty({ name: "...", type: Object }).calculated({ ... })`
4. Add to HasChanges rule if needed (search for `isHasChangesRule: true`)

### Adding a New Event Handler

1. Search `eventHandlers` to verify it doesn't exist
2. Find the event handler section (~line 18865+)
3. Add `Cognito.Forms.XyzChanged = function(val) { ... }`
4. Remember to call `form.set_HasChanges(true)` if the change should mark the form dirty

### Modifying the HasChanges Rule

1. Search for rules where `isHasChangesRule: true`
2. There are typically 2-3 rules at lines ~18164 and ~18181
3. Add your property to the appropriate `onChangeOf` array

### Finding Existing Patterns

Before adding new code, search the index:

```javascript
// Example: Find all properties related to "email"
properties.filter(p => p.name.toLowerCase().includes('email'))

// Example: Find event handlers for "People"
eventHandlers.filter(h => h.name.includes('People'))

// Example: Find all rules that affect HasChanges
rules.filter(r => r.isHasChangesRule)
```

## Key Line References (approximate)

| Structure | Line Range |
|-----------|------------|
| Imports | 1-25 |
| Export default function | 23-36 |
| initialize() function | 38-107 |
| Build Init ready block | 109-148 |
| Main "build" ready block | 194-18188 |
| Global Variables region | 228-311 |
| Element Types region | 458-1191 |
| Model Type Definitions region | 1193-5408 |
| Properties (form.meta.addProperty) | 1262-1800+ |
| HasChanges rules | 18164-18187 |
| Event handlers | 18865-19300+ |

## Gotchas

1. **String enum values**: Vue components send enum values as strings. Use `Cognito.getEnumWithName()` to convert.
2. **Missing computed property**: `{binding propertyName}` in build.htm requires a computed property in build.js.
3. **Change tracking**: Add properties to HasChanges rule's `onChangeOf` array or changes won't mark the form dirty.
4. **Nullable settings objects and `onChangeOf`**: ExoModel's `onChangeOf` path subscriptions (e.g., `"MySettings{Enabled}"`) don't re-run `calculate()` when the parent property transitions from null → object. The compute's `calculate()` function must **never see a null parent**. Use a helper that creates a default via `Cognito.deserialize()` if null — see `getPeopleFormSettings()` (~line 18940) and `getSubmitterPersonSettings()` (~line 18947) for the established pattern:
   ```javascript
   function getMySettings() {
       var settings = Cognito.Forms.model.currentForm.get_MySettings();
       if (!settings)
           settings = Cognito.deserialize(Cognito.Forms.MySettings, {});
       return settings;
   }
   ```
