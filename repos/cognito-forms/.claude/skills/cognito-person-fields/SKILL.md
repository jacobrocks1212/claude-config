# Person Field Detection Architecture

## Overview

In Cognito Forms, "Person" is a **runtime distinction**, not a stored field type. Both Person and Lookup fields store `FieldType.Lookup` in data. The `FieldType.Person` enum value exists but is only used in the new `FieldDefinition` system (not yet fully implemented).

## Server-Side Detection

### Two `MatchesPersonField` Overloads (they differ!)

**1. `PeopleFormSettings.MatchesPersonField(FieldLookup)`** — used by `FieldInfoGenerator`
- Location: `Cognito.Core\Model\Forms\PeopleFormSettings.cs`
- Checks: Enabled, Name/Email mapped, LabelFormat == `[{Name}]`, no Price/QuantityAvailable, Sort empty or by Name ASC
- Sets `MappedEmailPath` on `FieldInfo`

**2. `LookupView.MatchesPersonField(PeopleFormSettings)`** — used by `FormBuilderController`
- Location: `Cognito.Core\Model\Forms\LookupView.cs`
- Has additional `Invalid` check
- Populates `Cognito.config.personFields`

### FieldInfo Properties
- `MappedEmailPath` — path to the mapped email field (set when `MatchesPersonField` is true). A non-null `MappedEmailPath` indicates this is a person field.
- Set in `FieldInfoGenerator.VisitEntityField()` in `Cognito.Core\Services\FieldInfoGenerator.cs`

## Client-Side Detection

### LHS (Form Builder Field List)
- `Cognito.config.personFields[lookupId]` → sets `isPerson` on `FieldLookup` entity
- Populated per-form by:
  - `FormBuilderController` (`Cognito.Services\Controllers\SvcControllers\FormBuilderController.cs:513-535`)
  - `EntriesPageController` (`Cognito.Services\Controllers\SvcControllers\EntriesPageController.cs:490-524`)
- Person field defaults (LabelFormat, HasImage, etc.) applied when `isPerson` is true (`build.js:6135-6142`)

### RHS (Linked Lookup Dialog - Linkable Fields)
- Uses `FieldInfo.MappedEmailPath` (non-null indicates person field) to determine if field type should display as 'Person'
- Location: `Cognito.Web.Client\apps\spa\src\composables\linked-lookup.ts` — `linkableFieldOptions` calculated property

## Important Distinction

`MappedEmailPath` on FieldInfo != "is a Person field" — it means "this lookup's config matches person field criteria" which can include regular lookups pointing to person-configured forms. If the matching logic needs refinement, adjust `MatchesPersonField()` itself.

## Key File Locations

| File | What |
|------|------|
| `Cognito\Model\Field.cs` | `FieldType` enum (includes `Person` and `Lookup`) |
| `Cognito\Model\FieldInfo.cs` | FieldInfo model — `MappedEmailPath` property |
| `Cognito.Core\Model\Forms\PeopleFormSettings.cs` | `MatchesPersonField(FieldLookup)` |
| `Cognito.Core\Model\Forms\LookupView.cs` | `MatchesPersonField(PeopleFormSettings)` |
| `Cognito.Core\Services\FieldInfoGenerator.cs` | Sets `MappedEmailPath` on FieldInfo |
| `Cognito.Services\Controllers\SvcControllers\FormBuilderController.cs` | Populates `Cognito.config.personFields` |
| `Cognito.Services\Controllers\SvcControllers\EntriesPageController.cs` | Populates `Cognito.config.personFields` (entries) |
| `Cognito.Services\Views\Shared\build.js` | Client-side `isPerson` property + rule |
| `Cognito.Web.Client\libs\types\server-types\model\field-info.ts` | TypeScript FieldInfo type |
| `Cognito.Web.Client\apps\spa\src\composables\linked-lookup.types.ts` | `LinkableFieldInfo` interface |
| `Cognito.Web.Client\apps\spa\src\composables\linked-lookup.ts` | RHS person detection logic |
