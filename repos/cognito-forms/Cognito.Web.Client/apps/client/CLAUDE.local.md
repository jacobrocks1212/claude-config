# client — Form Rendering App

## Gotchas
- Renders forms for **end users** (submission, save, resume) — NOT the builder/admin
- Extensions use plain objects with `this: EntityOfType<T>` typing — they're attached via `model.extend()`, not class inheritance
- `FormsModelOptions` fields are prefixed with `$` (`$locale`, `$culture`, `$namespace`, etc.)
- Serialization converters are critical for correct data roundtrip — each field type has its own converter

## Entry Point
`framework/forms-model.ts` — `FormsModel` bootstraps the model with extensions and converters.

### FormsModelOptions
```typescript
{
  $locale, $culture, $namespace, $version,
  $utcOffset, $disableWorkflowActions,
  $disableLookupFiltering
}
```

## Extensions Pattern
```typescript
// Plain object with typed `this`
const FormEntryExtensions = {
  get Page_Index(this: EntityOfType<FormEntry>) { ... },
  get Form_Available(this: EntityOfType<FormEntry>) { ... }
};

model.extend({ "FormEntry": FormEntryExtensions });
```
Key extensions: `AddressExtensions`, `NameExtensions`, `FormEntryExtensions` (Page_Index, Form_Available pseudo-properties)

## Serialization Converters
`framework/model/serialization/converters/` — one per field type:
Date, Time, Calculation, Lookup, FileUpload, Signature, Address, Name, etc.

## Web API Layer
```
web-api/
  BaseService      Axios-based HTTP client
  EntryService     submit/save/resume/delete entry operations
  Custom error classes for typed error handling
```
- `BaseService` interceptors: model serialization, server time sync, session token refresh

## Components
`components/` — 50+ Vue components for form fields:
Address, Choice, Date, FileUpload, Name, Number, Rating, Repeating Section, Signature, Table, etc.
Each component handles its own validation display and field-type-specific UX.

---

## Maintaining This Document

Update this file when:
- Adding new architectural patterns or service hierarchies
- Discovering non-obvious gotchas that would trip up future developers
- Renaming or restructuring directories/files mentioned here

Do NOT add: version numbers, line numbers, test counts, or other specifics that change frequently.
