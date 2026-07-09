# model.js — Core Reactive Model Framework

## Gotchas
- **NEVER** `new Entity()` — use `type.create()` or `Type.newInstance()` (constructor guards with `ctorDepth`)
- Entity lifecycle: constructor -> initialized (Promise) -> ready. `InitializationContext` batches events during init
- Property access fires `accessed` event; change fires `changed` event — this drives both rules and Vue reactivity
- `ObservableArray.batchUpdate(fn)` for atomic array mutations — individual push/splice fires events per-op
- `ConditionType` instances are singletons in `allConditionTypes` — never create duplicates
- `EventScope` can be paused to batch initialization; rules don't execute until scope exits

## Type System
- `Type`: `baseType`/`derivedTypes`, `__pool__` (instance cache by ID), `__properties__` (PropertyDefinition[])
- `type.create(data?)` — async-aware construction; `type.newInstance(data?)`

### Property
- `PropertyDefinition` with name, type, format, label, rules
- Access/change events routed via `EventSubscriber`; `changed` runs dependent rules

### Entity
- `meta.type` (back-reference to Type), `meta.id`, `meta.isNew`, `meta.isModified`, `meta.destroyed`
- `serialize()` / `deserialize()` for JSON roundtrip

## Rule System
- `Rule` subclasses: `CalculatedPropertyRule` (computed values; predicates = onChangeOf), `ValidationRule` (ConditionType with message), `AllowedValuesRule`, `RequiredRule`, etc.
- Rules have `predicates` (onChangeOf paths) and `returnValues` (target properties); register via `type.addRule(rule)`
- `ConditionType` categories: Error, Warning, Permission

## ObservableArray
- Wraps native Array with change-tracking events; `batchUpdate(fn)` suppresses per-op events, fires single batch event at end

## EventScope / EventSubscriber
- `new EventScope().perform(fn)` — batches all events during `fn`, dispatches after (instance method, not static)
- `EventSubscriber` manages per-property event handlers; pause/resume for initialization batching
