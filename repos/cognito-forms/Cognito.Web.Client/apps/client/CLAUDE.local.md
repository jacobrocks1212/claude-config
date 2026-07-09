# client — Form Rendering App

## Gotchas
- Renders forms for **end users** (submission, save, resume) — NOT the builder/admin
- Extensions are plain objects with `this: EntityOfType<T>` typing, attached via `model.extend({ "FormEntry": FormEntryExtensions })` — not class inheritance. Key extensions: `AddressExtensions`, `NameExtensions`, `FormEntryExtensions` (Page_Index, Form_Available pseudo-properties)
- `FormsModelOptions` fields are `$`-prefixed (`$locale`, `$culture`, `$namespace`, `$version`, `$utcOffset`, `$disableWorkflowActions`, `$disableLookupFiltering`)
- Serialization converters are critical for correct data roundtrip — one per field type in `framework/model/serialization/converters/` (Date, Time, Calculation, Lookup, FileUpload, Signature, Address, Name, etc.)

## Entry Point
`framework/forms-model.ts` — `FormsModel` bootstraps the model with extensions and converters.

## Web API Layer (`web-api/`)
- `BaseService` — Axios-based HTTP client; interceptors handle model serialization, server time sync, session token refresh
- `EntryService` — submit/save/resume/delete entry operations
- Custom error classes for typed error handling

## Components
`components/` — one Vue component per field type (Address, Choice, Date, FileUpload, Signature, Table, …); each handles its own validation display and field-type-specific UX.
