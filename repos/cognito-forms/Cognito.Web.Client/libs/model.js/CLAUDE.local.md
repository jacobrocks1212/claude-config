# model.js — Core Reactive Model Framework

## Gotchas
- **NEVER** `new Entity()` — use `type.create()` or `Type.newInstance()` (constructor guards with `ctorDepth`)
- Entity lifecycle: constructor -> initialized (Promise) -> ready. `InitializationContext` batches events during init
- Property access fires `accessed` event; change fires `changed` event — this drives both rules and Vue reactivity
- `ObservableArray.batchUpdate(fn)` for atomic array mutations — individual push/splice fires events per-op
- `ConditionType` instances are singletons in `allConditionTypes` — never create duplicates
- `EventScope` can be paused to batch initialization; rules don't execute until scope exits
- `new EventScope().perform(fn)` batches all events during `fn` and dispatches after (instance method, not static)

Maintenance: record non-obvious gotchas and pattern/structure changes here; do NOT add version numbers, line numbers, or test counts.
