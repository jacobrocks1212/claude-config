---
name: vue-composition-api
description: Vue 3 Composition API patterns and best practices. Use when working with Vue 3 components, refs, reactive, computed, watchers, composables, and lifecycle hooks. Covers both Vue 3 and Vue 2.7 Composition API usage.
triggers:
  - "*.vue"
  - "<script setup"
  - "ref("
  - "reactive("
  - "computed("
  - "watch("
  - "watchEffect("
  - "onMounted"
  - "onUnmounted"
  - "defineProps"
  - "defineEmits"
  - "composables/"
---

# Vue Composition API Patterns

## When to Use This Skill
- Creating or modifying Vue 3 components
- Working with `<script setup>` syntax
- Building composables (reusable logic)
- Managing reactive state with refs and reactive
- Setting up watchers and computed properties
- Handling component lifecycle

## Core Patterns

### Script Setup (Preferred)
```vue
<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue';

// Props with TypeScript
const props = defineProps<{
  title: string;
  count?: number;
}>();

// Emits with TypeScript
const emit = defineEmits<{
  update: [value: string];
  close: [];
}>();

// Reactive state
const isOpen = ref(false);
const items = ref<string[]>([]);

// Computed
const itemCount = computed(() => items.value.length);

// Methods
function toggle() {
  isOpen.value = !isOpen.value;
}
</script>
```

### Refs vs Reactive
```typescript
// Use ref() for primitives and when you need to reassign
const count = ref(0);
const name = ref('');
const items = ref<Item[]>([]);

// Use reactive() for objects that won't be reassigned
const state = reactive({
  loading: false,
  error: null as Error | null,
  data: [] as Item[]
});

// Access ref values with .value in script, automatic in template
count.value++;
```

### Composables Pattern
```typescript
// composables/useCounter.ts
import { ref, computed } from 'vue';

export function useCounter(initial = 0) {
  const count = ref(initial);

  const doubled = computed(() => count.value * 2);

  function increment() {
    count.value++;
  }

  function decrement() {
    count.value--;
  }

  return {
    count: readonly(count),
    doubled,
    increment,
    decrement
  };
}
```

### Watchers
```typescript
import { watch, watchEffect } from 'vue';

// Watch specific source
watch(count, (newVal, oldVal) => {
  console.log(`Changed from ${oldVal} to ${newVal}`);
});

// Watch multiple sources
watch([firstName, lastName], ([newFirst, newLast]) => {
  fullName.value = `${newFirst} ${newLast}`;
});

// Deep watch for objects
watch(state, (newState) => {
  // Triggered on any nested change
}, { deep: true });

// Immediate execution
watch(userId, async (id) => {
  user.value = await fetchUser(id);
}, { immediate: true });

// watchEffect - auto-tracks dependencies
watchEffect(() => {
  console.log(`Count is: ${count.value}`);
});
```

### Lifecycle Hooks
```typescript
import { onMounted, onUnmounted, onBeforeMount } from 'vue';

onMounted(() => {
  // DOM is ready
  window.addEventListener('resize', handleResize);
});

onUnmounted(() => {
  // CRITICAL: Always clean up
  window.removeEventListener('resize', handleResize);
  clearInterval(intervalId);
  clearTimeout(timeoutId);
});
```

### Provide/Inject for Dependency Injection
```typescript
// Parent component
import { provide } from 'vue';
provide('theme', theme);
provide('api', apiService);

// Child component (any depth)
import { inject } from 'vue';
const theme = inject('theme');
const api = inject<ApiService>('api')!;
```

### Template Refs
```typescript
import { ref, onMounted } from 'vue';

const inputRef = ref<HTMLInputElement | null>(null);

onMounted(() => {
  inputRef.value?.focus();
});
```

```vue
<template>
  <input ref="inputRef" />
</template>
```

## Critical Rules

1. **Always use `.value` for refs in script** - Template unwraps automatically
2. **Clean up in onUnmounted** - Prevent memory leaks from timers, listeners, subscriptions
3. **Use `shallowRef` for large objects** - Avoids deep reactivity overhead
4. **Prefer `readonly()` for exposed state** - Prevents external mutation
5. **Use `toRefs()` when destructuring reactive objects** - Maintains reactivity

## Vue 2.7 Differences
- Same Composition API, but imported from 'vue'
- No `<script setup>` in some configurations
- Use `defineComponent()` wrapper for TypeScript

## Anti-Patterns to Avoid
- Destructuring props without `toRefs()` - loses reactivity
- Forgetting `.value` in script blocks
- Not cleaning up side effects in `onUnmounted`
- Using `reactive()` for primitives
- Mutating props directly
