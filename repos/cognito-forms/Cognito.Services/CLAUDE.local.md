# Cognito.Services — Web/API Layer

## Gotchas
- **ASP.NET MVC** (System.Web.Mvc) — NOT Web API, NOT .NET Core (in net472 mode)
- **Dual-target framework**: Builds `net472` by default, `net10.0` for NETCORE Debug. Use `*.Framework.cs` / `*.Core.cs` suffix pattern for platform-specific code.
- Check project's .csproj for LangVersion before using newer C# syntax
- Controllers inherit `BaseController` (extends `Controller`), NOT `ApiController`
- Return types: `JsonNetResult<T>`, `SerializeToResponseStream()`, NOT `IActionResult`
- SvcControllers take `Module<IXyzService>` as constructor parameter (Autofac DI)
- **Static assets (JS/CSS/HTML) don't need backend builds** — Files in `Views/` like `build.js`, `build.htm`, `build.scss` are served directly by IIS. Only `.cs` file changes require `dotnet build`.

## Controller Organization
```
Controllers/
  Core/              Admin/internal endpoints (PlanCoreController, TemporaryCoreController)
  SvcControllers/    Main API — the primary controller directory
    Form/            FormsAdminController, FormsPublicController, LoadFormController, SignatureController
    Auth/            Authentication controllers
    Integrations/    FileStorageController, IntegrationController, OauthController
    Payment/         PaymentAdminController, PaymentAccountController
    CognitoPay/      CognitoPayAccountController, CognitoDisputesController, CognitoPayPaymentController
  StripeController   Webhook handler
  PublicSite/        Marketing pages
```

## BaseController
```csharp
public abstract class BaseController : Controller
{
    protected ICoreService CoreService { get; set; }
    protected JsonNetResult<object> JsonResult(object value);
    protected void SerializeToResponseStream(object value);
    protected T Deserialize<T>(string json, IStorageContext context);
    protected string Serialize(object value, ...);
}
```

## DI
- `WebAppModule.cs` (Autofac) — registers web-layer services
- `WebApplication.cs` — app startup, route registration

## Infrastructure/
- `Authentication/` — AuthManager, SessionManager
- `Authorization/` — Authorization logic
- `Integration/` — OAuthService, IOauthService
- `Vue/` — Server-side Vue model/template/CSS builders for form rendering
- `Routes/` — OrgScopedRoute and custom routing
- Also: `Astro/`, `RateLimiting/`, `Square/`, `Telemetry/`

## Views/
Server-rendered MVC views — legacy pages, marketing, email templates, OAuth callbacks.
- `Views/Shared/` — build.js, build.htm, build.scss (form builder UI)
- `Views/Admin/` — entries.js, publish.js (admin pages)
- `Views/LoadForm/` — form rendering pages

## build.js — MANDATORY Skill Invocation

**BEFORE editing `Views/Shared/build.js`, you MUST invoke the `/build-js` skill.**

This skill provides an auto-generated index of the 22K+ line file, helping you:
- Find existing code before proposing changes (avoid duplicates)
- Locate HasChanges rules, event handlers, and computed properties
- Understand file structure and insertion points

If the index is stale, regenerate it:
```bash
node ~/.claude/skills/build-js/tools/generate-index.mjs
```

The script supports git worktrees automatically.

---

## build.js Vue Integration Pattern

When adding a new Form property that needs Vue binding in build.htm, you must complete **ALL THREE** steps:

### 1. Add Computed Property for Vue Binding
The `{binding propertyName}` syntax in build.htm requires a computed property in build.js to serialize the data:

```javascript
// Search for "form.meta.addProperty" to find the insertion point
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

### 2. Add to HasChanges Rule
Add the property to the `onChangeOf` array in the HasChanges rule (search for `"HasChanges"` and `onChangeOf`):

```javascript
onChangeOf: ["...", "PeopleFormSettings", "MyNewSettings", "..."]
```

### 3. Add Event Handler
Create the handler function that updates the form and marks it dirty:

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

When setting C# enum properties from Vue/TypeScript string values, use `Cognito.getEnumWithName()`:

```javascript
// WRONG - will throw "a value of type X was expected"
existingSettings.set_LinkingMode(settings.LinkingMode);  // string "PersonField"

// CORRECT - converts string to ExoModel enum type
existingSettings.set_LinkingMode(
    Cognito.getEnumWithName(Cognito.Forms.PeopleLinkingMode, settings.LinkingMode)
);
```

**Pattern:** `Cognito.getEnumWithName(Cognito.Forms.EnumTypeName, stringValue)`

The enum type name must match the C# enum type (e.g., `PeopleLinkingMode`, `PeopleUpdateBehavior`, `FieldType`, `FieldSubType`).

### Common Mistakes

1. **Missing computed property** — The `{binding propertyName}` syntax requires a computed property in build.js. Without it, the binding returns `undefined` silently.

2. **String enum values** — Vue components send enum values as strings. Use `Cognito.getEnumWithName()` to convert them to proper ExoModel enum types before calling setters.

3. **Missing HasChanges rule** — Without adding the property to the HasChanges rule, changes won't mark the form dirty.

## build.js Token Field Rewriting

`convertFieldInfosToTokens()` (around line 14073) transforms server `FieldInfo` objects into client-side tokens. It **rewrites several fields** — the client token shape differs from the server shape:

| Field | Server value | Client value after conversion |
|-------|-------------|-------------------------------|
| `InternalName` | Field's own name (never dotted) | **Overwritten:** `= token.Path` (logical dotted path) for non-container fields; `= ""` for containers (Entity, RatingScale, EntityList including sections) |
| `FieldPath` | *(not present on server)* | Set to original `token.Path` before Path is overwritten |
| `Path` | Logical dotted path (e.g., `"Section.PersonField"`) | **Overwritten:** indented display name (e.g., `"    PersonField"`) |

### Filtering person-field-nested tokens
Because sections get `InternalName = ""`, they are invisible in the person field token list. To filter out person fields nested under OTHER person fields (without filtering section-nested person fields), check whether any other person field token's `InternalName` is a prefix of the current token's `InternalName + '.'`. Do NOT use `Id.includes('.')` — that conflates section nesting with person-field nesting. The shared utility `filterDirectPersonFields` in `identify-submitter.ts` implements this correctly.

## Queue/
`ProcessQueueTask` — background job dispatch from web tier.

---

## Maintaining This Document

Update this file when:
- Adding new architectural patterns or service hierarchies
- Discovering non-obvious gotchas that would trip up future developers
- Renaming or restructuring directories/files mentioned here

Do NOT add: version numbers, line numbers, test counts, or other specifics that change frequently.
