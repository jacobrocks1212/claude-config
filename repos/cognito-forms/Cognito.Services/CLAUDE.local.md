# Cognito.Services — Web/API Layer

## Gotchas
- **ASP.NET MVC** (System.Web.Mvc) — NOT Web API, NOT .NET Core (in net472 mode)
- **Dual-target framework**: builds `net472` by default, `net10.0` for NETCORE Debug. Use `*.Framework.cs` / `*.Core.cs` suffix pattern for platform-specific code.
- Controllers inherit `BaseController` (extends `Controller`), NOT `ApiController`; main API controllers live under `Controllers/SvcControllers/`
- Return types: `JsonNetResult<T>`, `SerializeToResponseStream()`, NOT `IActionResult`
- SvcControllers take `Module<IXyzService>` as constructor parameter (Autofac DI)
- **Static assets (JS/CSS/HTML) don't need backend builds** — files in `Views/` like `build.js`, `build.htm`, `build.scss` are served directly by IIS. Only `.cs` changes require a build.

## build.js — MANDATORY Skill Invocation
**BEFORE editing `Views/Shared/build.js` (22K+ lines), you MUST invoke the `/build-js` skill** — an auto-generated index for finding existing code before proposing changes (avoid duplicates), locating HasChanges rules / event handlers / computed properties, and insertion points. If stale, regenerate (worktree-aware):
```bash
node ~/.claude/skills/build-js/tools/generate-index.mjs
```

## build.js Vue Integration Pattern
Adding a new Form property that needs Vue binding in build.htm requires **ALL THREE** steps:

### 1. Computed property for the Vue binding
The `{binding propertyName}` syntax in build.htm requires a computed property in build.js — without it, the binding returns `undefined` silently. Search `form.meta.addProperty` for the insertion point:
```javascript
form.meta.addProperty({ name: "myNewSettings", type: Object }).calculated({
    calculate: function () {
        var settings = Cognito.Forms.model.currentForm.get_MyNewSettings();
        if (!settings) return null;
        return Cognito.serialize(settings);
    },
    onChangeOf: [
        "MyNewSettings{Property1}",
        "MyNewSettings{Property2}",
        // List ALL nested properties for change tracking
    ]
});
```

### 2. Add to HasChanges rule
Add the property to the `onChangeOf` array in the HasChanges rule (search `"HasChanges"` and `onChangeOf`) — without it, changes won't mark the form dirty.

### 3. Event handler
```javascript
Cognito.Forms.MyNewSettingsChanged = function (settings) {
    var form = Cognito.Forms.model.currentForm;
    if (!form) return;
    // ... apply settings ...
    form.set_MyNewSettings(existingSettings);
    form.set_HasChanges(true);  // CRITICAL: Mark form dirty
}
```

### Setting Enum Properties in ExoModel
Vue components send enum values as strings; passing one straight to a setter throws "a value of type X was expected". Convert with `Cognito.getEnumWithName(Cognito.Forms.EnumTypeName, stringValue)` — the enum type name must match the C# enum type (e.g. `PeopleLinkingMode`, `PeopleUpdateBehavior`, `FieldType`, `FieldSubType`):
```javascript
// WRONG
existingSettings.set_LinkingMode(settings.LinkingMode);  // string "PersonField"
// CORRECT
existingSettings.set_LinkingMode(
    Cognito.getEnumWithName(Cognito.Forms.PeopleLinkingMode, settings.LinkingMode)
);
```

## build.js Token Field Rewriting
`convertFieldInfosToTokens()` transforms server `FieldInfo` objects into client-side tokens. It **rewrites several fields** — the client token shape differs from the server shape:

| Field | Server value | Client value after conversion |
|-------|-------------|-------------------------------|
| `InternalName` | Field's own name (never dotted) | **Overwritten:** `= token.Path` (logical dotted path) for non-container fields; `= ""` for containers (Entity, RatingScale, EntityList including sections) |
| `FieldPath` | *(not present on server)* | Set to original `token.Path` before Path is overwritten |
| `Path` | Logical dotted path (e.g., `"Section.PersonField"`) | **Overwritten:** indented display name (e.g., `"    PersonField"`) |

### Filtering person-field-nested tokens
Because sections get `InternalName = ""`, they are invisible in the person field token list. To filter out person fields nested under OTHER person fields (without filtering section-nested person fields), check whether any other person field token's `InternalName` is a prefix of the current token's `InternalName + '.'`. Do NOT use `Id.includes('.')` — that conflates section nesting with person-field nesting. The shared utility `filterDirectPersonFields` in `identify-submitter.ts` implements this correctly.

Maintenance: record non-obvious gotchas and pattern/structure changes here; do NOT add version numbers, line numbers, or test counts.
