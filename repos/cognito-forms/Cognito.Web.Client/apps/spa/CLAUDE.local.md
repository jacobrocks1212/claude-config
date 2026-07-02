# spa — Form Builder & Admin Interface

## Gotchas
- `GlobalState.ready` is a `Deferred<void>` — must await it before accessing state like `forms` or `organization`
- Composable naming: `use-*` prefix = reactive composable, `create-*` prefix = factory/async creator
- Element UI is a **forked** `@cognitoforms/element-ui` — not the standard element-ui package
- `GlobalState.forms` is `Record<string, UserFormMeta>` — metadata objects, not full Form entities
- Person-form auto-create action IDs are deterministic **per type** but NOT uniform across types (e.g. Guest's Submit can have a different Id than Contact/User). Source action pickers from `Cognito.config.personFormTemplateActions[type]` (server-projected via `SystemTemplateService.GetTemplateActions`) — never hardcode action Ids or borrow from an arbitrary existing person form
- `CCallout` (`src/components/content/Callout.vue`) renders its root with `v-show="visible"`, so a bare `<CCallout>` is always present in the DOM (just hidden). When a callout should be conditionally *absent* — e.g. asserting `findComponent({name:'CCallout'}).exists()` is false, or `querySelector('.callout--error')` is null — gate it with `v-if` on your own condition, not on the component's internal visibility. Use `type="error"` (validator-accepted) for the error variant; content goes in the default slot.
- Callout/toast handlers (e.g. `showPersonFieldToast` in `identify-submitter.ts`) must **re-resolve live tokens at click time** inside the handler, not close over a snapshot captured at open time. A callout is opened once and its options are refreshed in place via `updateCalloutOptions` (the handler is NOT re-registered), so a captured token list goes stale when fields are added afterward — selecting a newer option then silently falls back to the first. Resolve the selected token from a fresh `getSingleSelectTokens()` and treat a provided-but-unmatched id as a no-op rather than defaulting to the first token (bug 56579)
- Auto-create submitters has a persisted **`CreateNewPersonEntries`** bool on `SubmitterPersonSettings` (server) surfaced as the "Create New Person Entries" checkbox in `IdentifySubmitterSettings.vue`. **The server honors this flag**: `EntryIndexService.UpdateSubmitterPersonEntryByFieldMappingAsync` auto-creates only when `AutoCreateActionId.HasValue && CreateNewPersonEntries`, so unchecking the toggle actually disables runtime auto-create. The checkbox **defaults ON for viable forms** (≥1 non-`WillAlwaysFail` action) while honoring an explicit OFF — hydration is `noViableActions ? !!CreateNewPersonEntries : (CreateNewPersonEntries !== false || AutoCreateActionId != null)`. (A brand-new and an explicitly-turned-off viable form both persist as `false`, so they can't be fully distinguished without a nullable flag — accepted residual gap.) The Action picker gates on the checkbox **and** a non-empty action list (`showAutoCreateAction = showContactFieldDropdowns && internalCreateNewPersonEntries && autoCreateActionOptions.length > 0`), so a zero-action form never shows an empty enabled picker. The save path can never persist the toggle ON without an action id (`handleIdentifySubmitterDialogSave` and the `IdentifySubmitterDialog` emit both gate on `actionId != null`). The zero-viable error callout is **deferred** — it shows only when the toggle is on (`IdentifySubmitterSettings`) or `autoCreateBehavior === 'create'` (`IdentifySubmitterDialog`), never unconditionally.
- The "Create New Person Form" inline flow seeds its action from the **new form's** viable set: `handlePersonFormCreated` → `selectDefaultActionValue(filterViableActionOptions(mapActionOptions(actions)), null)` → `handleIdentifySubmitterDialogSave(formId, defaultActionId)`, setting `CreateNewPersonEntries` true iff a viable action exists. Changing the target form in the Settings panel re-seeds the same pair: `SubmitterTargetFormChanged` derives the action from the new form's viable set (preserving a still-valid current id) and sets the flag iff an action resolved — atomically in the same `updateSettingsAndMarkDirty` round-trip as the form change. All four surfaces (Settings checkbox, Settings target-form change, Dialog create/skip, create-new-form) persist through the shared `identify-submitter.ts` wiring — do NOT re-implement filter/default logic; any new surface must seed both values together, never the flag alone. Unchecking the Settings "Create New Person Entries" checkbox clears the action id too (`createNewPersonEntriesChanged` emits `auto-create-action-change(null)` alongside `create-new-person-entries-change(false)`), so an explicit OFF persists as `{ CreateNewPersonEntries: false, AutoCreateActionId: null }` and the viable-branch hydration evaluates `false || false → false` — the toggle stays off after the persist round-trip instead of re-stomping back on (it previously kept a stale `AutoCreateActionId`, forcing the checkbox back on). The Settings checkbox emit `create-new-person-entries-change` is bound in `Cognito.Services/Views/Shared/build.htm` → `Cognito.Forms.SubmitterCreateNewPersonEntriesChanged` (build.js) → `identify-submitter.ts` API; runtime persistence of that checkbox is verified manually (no automated runtime coverage).
- `CExpandable` (`src/components/interaction/Expandable.vue`) skips its max-height animation when the measured content height is 0 (e.g. expanding/collapsing while a `display:none` ancestor hides it) — it settles state immediately instead of waiting for a `transitionend` that never fires on a 0→0 height change. It still emits `'expanded'` (with `0`) on the skip path, so `@expanded` listeners must tolerate a zero height.

## State Management
`stores/global-store.ts` — single reactive `GlobalState` object (no Vuex/Pinia).

### GlobalState Key Fields
```typescript
{
  user,              // current user
  organization,      // current org
  folders,           // folder tree
  forms,             // Record<string, UserFormMeta> — form metadata
  currentFormId,     // active form being edited
  ready,             // Deferred<void> — signals async init complete
}
```

### Deferred<T> Pattern
Promise wrapper with external `resolve()`/`reject()` — used for async initialization signals.
```typescript
const ready = new Deferred<void>();
// ... later, after async init:
ready.resolve();
// consumers: await globalState.ready;
```

## Composables
`composables/` directory with consistent naming:
- `use-*` — reactive composables (e.g., `use-form`, `use-entries`)
- `create-*` — factory/async creators

## Component Organization
```
components/
  app/              App shell, layout
  auth/             Authentication flows
  form-controls/    Reusable builder controls (Checkbox, Select, etc.) with v-model
  integrations/     Third-party integration UIs
  lists/            List/grid views
  navigation/       Nav bars, sidebars
  pricing/          Plan/billing UI
  publish/          Form publishing settings
  website/          Website builder components
```

## Element UI Integration
Forked `@cognitoforms/element-ui` — used for dialogs, dropdowns, tooltips, form inputs.
Import from `@cognitoforms/element-ui` (not `element-ui`).

---

## Maintaining This Document

Update this file when:
- Adding new architectural patterns or service hierarchies
- Discovering non-obvious gotchas that would trip up future developers
- Renaming or restructuring directories/files mentioned here

Do NOT add: version numbers, line numbers, test counts, or other specifics that change frequently.
