# vuemodel — Vue 2 Reactivity Bridge for model.js

## Gotchas
- Does **NOT** use Vue's property-walking — subscribes to entity `accessed`/`changed` events instead
- `preventVueObservability()` marks objects with a symbol to prevent Vue's Observer from walking them
- Must be installed as plugin: `Vue.use(VueModel)`
- Tightly coupled to Vue 2 internals (`Observer`, `Dep`) — not portable to Vue 3

## Architecture
```
VueModel extends Model
  └── Installed via Vue.use() — registers global components and hooks

EntityObserver extends Vue's internal Observer
  └── Hooks into entity change events instead of Vue's defineProperty walking

CustomObserver (base class)
  └── Manages per-property Dep objects for Vue dependency tracking
```

### EntityObserver
- Extends Vue 2's `Observer` class (from `vue/src/core/observer`)
- On entity `accessed` event: calls `dep.depend()` to register Vue watcher dependency
- On entity `changed` event: calls `dep.notify()` to trigger Vue re-renders
- Bridges model.js reactivity with Vue's virtual DOM update cycle

### preventVueObservability
- Marks objects with a symbol so Vue's `observe()` skips them
- Use on objects that are already reactive via model.js (prevents double-observation overhead)

## Source Adapters
- `SourceRootAdapter` — binds an entity as the root data source for a component
- `SourcePathAdapter` — binds a nested property path within an entity
- Global components: `vm-root`, `vm-source` (registered by plugin install)

## Plugin Install
```typescript
Vue.use(VueModel)  // registers components, patches Observer
```

---

## Maintaining This Document

Update this file when:
- Adding new architectural patterns or service hierarchies
- Discovering non-obvious gotchas that would trip up future developers
- Renaming or restructuring directories/files mentioned here

Do NOT add: version numbers, line numbers, test counts, or other specifics that change frequently.
