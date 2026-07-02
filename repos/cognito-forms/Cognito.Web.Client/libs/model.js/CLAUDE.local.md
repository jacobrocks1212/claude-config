# model.js — Core Reactive Model Framework

## Gotchas
- **NEVER** `new Entity()` — use `type.create()` or `Type.newInstance()` (constructor guards with `ctorDepth`)
- Entity lifecycle: constructor -> initialized (Promise) -> ready. `InitializationContext` batches events during init
- Property access fires `accessed` event; change fires `changed` event — this drives both rules and Vue reactivity
- `ObservableArray.batchUpdate(fn)` for atomic array mutations — individual push/splice fires events per-op
- `ConditionType` instances are singletons in `allConditionTypes` — never create duplicates
- `EventScope` can be paused to batch initialization; rules don't execute until scope exits

## Type System
```
Type
  ├── baseType, derivedTypes
  ├── __pool__ (instance cache by ID)
  ├── __properties__ (PropertyDefinition[])
  ├── create(data?) -> Entity (async-aware construction)
  └── newInstance(data?) -> Entity
```

### Property
- `PropertyDefinition` with name, type, format, label, rules
- Access triggers `accessed` event via `EventSubscriber`
- Change triggers `changed` event -> runs dependent rules

### Entity
- Has `meta.type` (back-reference to Type), `meta.id`
- `serialize()` / `deserialize()` for JSON roundtrip
- `meta.isNew`, `meta.isModified`, `meta.destroyed`

## Rule System
```
Rule (base)
  ├── CalculatedPropertyRule   — computed values (predicates = onChangeOf)
  ├── ValidationRule           — ConditionType with message
  ├── AllowedValuesRule        — constrained value sets
  └── RequiredRule, etc.
```
- Rules have `predicates` (onChangeOf paths) and `returnValues` (target properties)
- `ConditionType` categories: Error, Warning, Permission
- Rules register on Type via `type.addRule(rule)`

## ObservableArray
- Wraps native Array with change tracking events
- `batchUpdate(fn)` — suppresses individual events, fires single batch event at end
- Supports `changed` event subscription

## EventScope / EventSubscriber
- `new EventScope().perform(fn)` — batches all events during `fn`, dispatches after (instance method, not static)
- `EventSubscriber` manages per-property event handlers
- Pause/resume for initialization batching

## Key Source Files
`src/` contains ~55 files. Key ones:
- `type.ts`, `entity.ts`, `property.ts` — core type system
- `rule.ts`, `calculated-property-rule.ts`, `validation-rule.ts` — rule engine
- `observable-array.ts` — reactive array wrapper
- `event-scope.ts`, `event-subscriber.ts` — event batching
- `condition-type.ts` — validation condition singletons
- `initialization-context.ts` — async entity init

---

## Maintaining This Document

Update this file when:
- Adding new architectural patterns or service hierarchies
- Discovering non-obvious gotchas that would trip up future developers
- Renaming or restructuring directories/files mentioned here

Do NOT add: version numbers, line numbers, test counts, or other specifics that change frequently.
