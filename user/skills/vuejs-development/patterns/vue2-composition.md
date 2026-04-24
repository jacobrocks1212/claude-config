# Vue 2.7 Composition API Patterns

This document extends the Vue.js Development skill for Vue 2.7 Composition API compatibility.

## Critical Differences from Vue 3

Vue 2.7 backports Composition API but has important limitations:

### Features NOT Available in Vue 2.7

```javascript
// AVOID - Vue 3 only features:
// - <Teleport> component (use portal-vue instead)
// - <Suspense> component
// - Multi-root components (fragments)
// - defineCustomElement()
// - createRenderer()
// - v-memo directive
```

### Setup Function Pattern (Recommended for Vue 2.7)

```vue
<script>
import { ref, computed, onMounted, defineComponent } from 'vue'

// Always wrap in defineComponent for TypeScript support
export default defineComponent({
  name: 'MyComponent',
  props: {
    title: {
      type: String,
      required: true
    },
    initialCount: {
      type: Number,
      default: 0
    }
  },
  emits: ['update', 'delete'],
  setup(props, { emit }) {
    // Reactive state
    const count = ref(props.initialCount)
    const message = ref('Hello Vue 2.7!')

    // Computed
    const doubledCount = computed(() => count.value * 2)

    // Methods
    function increment() {
      count.value++
      emit('update', count.value)
    }

    // Lifecycle
    onMounted(() => {
      console.log('Component mounted')
    })

    // MUST return everything used in template
    return {
      count,
      message,
      doubledCount,
      increment
    }
  }
})
</script>

<template>
  <!-- Vue 2.7: Single root element required -->
  <div class="my-component">
    <h2>{{ title }}</h2>
    <p>{{ message }}</p>
    <p>Count: {{ count }} (Doubled: {{ doubledCount }})</p>
    <button @click="increment">Increment</button>
  </div>
</template>
```

### Script Setup (Available in Vue 2.7.14+)

```vue
<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'

// Props - use defineProps macro
const props = defineProps<{
  title: string
  initialCount?: number
}>()

// Emits - use defineEmits macro
const emit = defineEmits<{
  (e: 'update', value: number): void
  (e: 'delete', id: string): void
}>()

// Reactive state
const count = ref(props.initialCount ?? 0)

// Computed
const doubledCount = computed(() => count.value * 2)

// Methods
function increment() {
  count.value++
  emit('update', count.value)
}

// Lifecycle
onMounted(() => {
  console.log('Mounted with count:', count.value)
})
</script>

<template>
  <div>
    <h2>{{ title }}</h2>
    <p>Count: {{ count }}</p>
    <button @click="increment">+</button>
  </div>
</template>
```

## Cognito Forms Patterns

### Standard Component Structure

```vue
<script lang="ts">
import { defineComponent, ref, computed, watch, onMounted, PropType } from 'vue'
import type { Form, Entry } from '@/types'

export default defineComponent({
  name: 'FormEntry',
  props: {
    form: {
      type: Object as PropType<Form>,
      required: true
    },
    entry: {
      type: Object as PropType<Entry>,
      default: null
    },
    isEditing: {
      type: Boolean,
      default: false
    }
  },
  emits: ['save', 'cancel', 'delete'],
  setup(props, { emit }) {
    // Local state
    const isLoading = ref(false)
    const errorMessage = ref<string | null>(null)
    const formData = ref<Partial<Entry>>({})

    // Computed
    const canSave = computed(() => {
      return !isLoading.value && formData.value.name?.trim()
    })

    const displayTitle = computed(() => {
      return props.isEditing
        ? `Edit: ${props.entry?.name}`
        : 'New Entry'
    })

    // Watchers
    watch(() => props.entry, (newEntry) => {
      if (newEntry) {
        formData.value = { ...newEntry }
      }
    }, { immediate: true })

    // Methods
    async function handleSave() {
      if (!canSave.value) return

      isLoading.value = true
      errorMessage.value = null

      try {
        emit('save', formData.value)
      } catch (error) {
        errorMessage.value = error instanceof Error
          ? error.message
          : 'An error occurred'
      } finally {
        isLoading.value = false
      }
    }

    function handleCancel() {
      emit('cancel')
    }

    // Lifecycle
    onMounted(() => {
      // Initialize component
    })

    return {
      isLoading,
      errorMessage,
      formData,
      canSave,
      displayTitle,
      handleSave,
      handleCancel
    }
  }
})
</script>
```

### Composables for Vue 2.7

```typescript
// composables/useFormValidation.ts
import { ref, computed, Ref } from 'vue'

interface ValidationRule {
  validate: (value: unknown) => boolean
  message: string
}

interface UseFormValidationOptions {
  rules: Record<string, ValidationRule[]>
}

export function useFormValidation<T extends Record<string, unknown>>(
  formData: Ref<T>,
  options: UseFormValidationOptions
) {
  const errors = ref<Record<string, string>>({})
  const touched = ref<Record<string, boolean>>({})

  const isValid = computed(() => {
    return Object.keys(errors.value).length === 0
  })

  function validate(field?: keyof T): boolean {
    const fieldsToValidate = field
      ? [field as string]
      : Object.keys(options.rules)

    for (const fieldName of fieldsToValidate) {
      const rules = options.rules[fieldName] || []
      const value = formData.value[fieldName as keyof T]

      for (const rule of rules) {
        if (!rule.validate(value)) {
          errors.value[fieldName] = rule.message
          break
        } else {
          delete errors.value[fieldName]
        }
      }
    }

    return isValid.value
  }

  function touch(field: keyof T) {
    touched.value[field as string] = true
    validate(field)
  }

  function reset() {
    errors.value = {}
    touched.value = {}
  }

  return {
    errors,
    touched,
    isValid,
    validate,
    touch,
    reset
  }
}
```

### API Composable Pattern

```typescript
// composables/useApi.ts
import { ref, Ref } from 'vue'

interface UseApiOptions<T> {
  immediate?: boolean
  initialData?: T
}

interface UseApiReturn<T> {
  data: Ref<T | null>
  error: Ref<Error | null>
  isLoading: Ref<boolean>
  execute: (...args: unknown[]) => Promise<T>
  reset: () => void
}

export function useApi<T>(
  apiFunc: (...args: unknown[]) => Promise<T>,
  options: UseApiOptions<T> = {}
): UseApiReturn<T> {
  const data = ref<T | null>(options.initialData ?? null) as Ref<T | null>
  const error = ref<Error | null>(null)
  const isLoading = ref(false)

  async function execute(...args: unknown[]): Promise<T> {
    isLoading.value = true
    error.value = null

    try {
      const result = await apiFunc(...args)
      data.value = result
      return result
    } catch (e) {
      error.value = e instanceof Error ? e : new Error(String(e))
      throw error.value
    } finally {
      isLoading.value = false
    }
  }

  function reset() {
    data.value = options.initialData ?? null
    error.value = null
    isLoading.value = false
  }

  return {
    data,
    error,
    isLoading,
    execute,
    reset
  }
}

// Usage
// const { data: forms, isLoading, execute: fetchForms } = useApi(api.getForms)
```

## Migration from Options API

### Before (Options API)
```vue
<script>
export default {
  data() {
    return {
      count: 0,
      message: ''
    }
  },
  computed: {
    doubled() {
      return this.count * 2
    }
  },
  methods: {
    increment() {
      this.count++
    }
  },
  mounted() {
    console.log('mounted')
  }
}
</script>
```

### After (Composition API)
```vue
<script>
import { defineComponent, ref, computed, onMounted } from 'vue'

export default defineComponent({
  setup() {
    const count = ref(0)
    const message = ref('')

    const doubled = computed(() => count.value * 2)

    function increment() {
      count.value++
    }

    onMounted(() => {
      console.log('mounted')
    })

    return {
      count,
      message,
      doubled,
      increment
    }
  }
})
</script>
```

## TypeScript Integration

### Prop Types
```typescript
import { PropType } from 'vue'

interface User {
  id: string
  name: string
  email: string
}

props: {
  user: {
    type: Object as PropType<User>,
    required: true
  },
  items: {
    type: Array as PropType<string[]>,
    default: () => []
  }
}
```

### Ref Types
```typescript
import { ref, Ref } from 'vue'

// Explicit typing
const count: Ref<number> = ref(0)
const user: Ref<User | null> = ref(null)

// Type inference (preferred when possible)
const count = ref(0)  // Ref<number>
const user = ref<User | null>(null)
```

## Common Gotchas in Vue 2.7

1. **Single Root Element Required**
   ```vue
   <!-- WRONG in Vue 2.7 -->
   <template>
     <h1>Title</h1>
     <p>Content</p>
   </template>

   <!-- CORRECT -->
   <template>
     <div>
       <h1>Title</h1>
       <p>Content</p>
     </div>
   </template>
   ```

2. **Return Statement Required**
   ```javascript
   // MUST return everything used in template
   setup() {
     const count = ref(0)
     const increment = () => count.value++

     return { count, increment }  // Required!
   }
   ```

3. **Reactive Object Destructuring**
   ```javascript
   // WRONG - loses reactivity
   const { name, email } = props

   // CORRECT - use toRefs
   const { name, email } = toRefs(props)
   ```

4. **Watch Cleanup**
   ```javascript
   import { watch, onUnmounted } from 'vue'

   const stop = watch(source, callback)

   // Cleanup if needed
   onUnmounted(() => {
     stop()
   })
   ```
