# client — Form Rendering App

## Gotchas
- Renders forms for **end users** (submission, save, resume) — NOT the builder/admin
- Extensions are plain objects with `this: EntityOfType<T>` typing, attached via `model.extend({ "FormEntry": FormEntryExtensions })` — not class inheritance
- `FormsModelOptions` fields are `$`-prefixed (`$locale`, `$culture`, `$namespace`, `$version`, `$utcOffset`, `$disableWorkflowActions`, `$disableLookupFiltering`)
- Serialization converters are critical for correct data roundtrip — one per field type in `framework/model/serialization/converters/`

Maintenance: record non-obvious gotchas and pattern/structure changes here; do NOT add version numbers, line numbers, or test counts.
