# vuemodel — Vue 2 Reactivity Bridge for model.js

## Gotchas
- Does **NOT** use Vue's property-walking — subscribes to entity `accessed`/`changed` events instead
- `preventVueObservability()` marks objects with a symbol so Vue's `observe()` skips them — use on objects already reactive via model.js (prevents double-observation overhead)
- Must be installed as plugin: `Vue.use(VueModel)` — registers global components, patches Observer
- Tightly coupled to Vue 2 internals (`Observer`, `Dep`) — not portable to Vue 3

## Architecture
- `VueModel extends Model` — installed via `Vue.use()`
- `EntityObserver` extends Vue 2's internal `Observer` (`vue/src/core/observer`) — hooks entity change events instead of Vue's defineProperty walking: `accessed` -> `dep.depend()` (register watcher dependency); `changed` -> `dep.notify()` (trigger re-render)
- `CustomObserver` (base class) manages per-property `Dep` objects for Vue dependency tracking

## Source Adapters
- `SourceRootAdapter` — binds an entity as the root data source for a component
- `SourcePathAdapter` — binds a nested property path within an entity
- Global components: `vm-root`, `vm-source` (registered by plugin install)
