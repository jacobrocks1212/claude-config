# Feedback Patterns Reference

User actions should have immediate, clear feedback.

## Optimistic Updates

Update UI immediately, revert on error:

```typescript
async function savePattern(pattern: Pattern) {
  // 1. Optimistic update
  const previousPatterns = [...patterns.value];
  patterns.value.push(pattern);

  try {
    // 2. Server request
    await api.savePattern(pattern);
    // 3. Success: toast optional for saves
    toast.success('Pattern saved');
  } catch (error) {
    // 4. Revert on failure
    patterns.value = previousPatterns;
    toast.error('Failed to save pattern');
  }
}
```

## Loading States

### Button Loading

```vue
<template>
  <button :disabled="isSubmitting" class="relative min-w-[80px]">
    <span :class="{ 'opacity-0': isSubmitting }">Save</span>
    <Transition name="fade">
      <span v-if="isSubmitting" class="absolute inset-0 flex items-center justify-center">
        <LoadingSpinner class="w-4 h-4" />
      </span>
    </Transition>
  </button>
</template>
```

### Skeleton Screens

Replace content shape, not just a spinner:

```vue
<template>
  <div v-if="isLoading" class="space-y-3">
    <!-- Pattern card skeleton -->
    <div class="animate-pulse bg-[var(--bg-tertiary)] rounded-lg p-4">
      <div class="h-4 bg-[var(--bg-secondary)] rounded w-3/4 mb-2"></div>
      <div class="h-3 bg-[var(--bg-secondary)] rounded w-1/2"></div>
    </div>
  </div>
  <PatternList v-else :patterns="patterns" />
</template>
```

### Inline Loading

For refreshing existing content:

```vue
<div class="relative">
  <PatternList :patterns="patterns" :class="{ 'opacity-50': isRefreshing }" />
  <div v-if="isRefreshing" class="absolute top-2 right-2">
    <LoadingSpinner class="w-4 h-4" />
  </div>
</div>
```

## Toast Notifications

Use `toastStore` for feedback:

```typescript
import { useToastStore } from '@/stores/toastStore';

const toast = useToastStore();

// Success (auto-dismiss 3s)
toast.success('Pattern loaded');

// Error (stays until dismissed)
toast.error('Evaluation failed: syntax error on line 5');

// Warning (auto-dismiss 5s)
toast.warning('Audio context suspended, click to resume');

// Info (auto-dismiss 3s)
toast.info('Transition scheduled');
```

### Toast Guidelines

| Type | Use Case | Duration |
|------|----------|----------|
| `success` | Completed actions | 3s auto |
| `error` | Failures, need attention | Manual dismiss |
| `warning` | Needs user action soon | 5s auto |
| `info` | Informational | 3s auto |

## Error Feedback

### Inline Errors (Preferred)

Show errors close to the source:

```vue
<div>
  <CodeEditor
    :code="code"
    :error-line="errorLine"
    :error-message="errorMessage"
  />
  <div v-if="hasError" class="mt-2 p-2 bg-[rgba(var(--state-error-rgb),0.1)] rounded flex items-start gap-2">
    <AlertIcon class="w-4 h-4 text-[var(--state-error)] flex-shrink-0 mt-0.5" />
    <span class="text-sm text-[var(--state-error)]">{{ errorMessage }}</span>
  </div>
</div>
```

### HUD Error Indicator

For non-blocking errors (pattern evaluation):

```vue
<!-- In DynamicIslandHUD -->
<div v-if="hasEvaluationError" class="flex items-center gap-1 text-[var(--state-error)]">
  <AlertIcon class="w-3 h-3" />
  <span class="text-xs">Error</span>
</div>
```

## Success Feedback

### Subtle Confirmation

For frequent actions, use subtle visual feedback:

```vue
<button @click="copy" class="group">
  <CopyIcon v-if="!copied" class="w-4 h-4" />
  <CheckIcon v-else class="w-4 h-4 text-[var(--state-success)]" />
</button>
```

### Save Indicator

Show save status inline:

```vue
<span class="text-xs text-[var(--text-tertiary)]">
  <span v-if="isSaving">Saving...</span>
  <span v-else-if="lastSaved">Saved {{ formatRelative(lastSaved) }}</span>
</span>
```

## Progress Feedback

### Determinate Progress

When you know the total:

```vue
<div class="w-full h-1 bg-[var(--bg-secondary)] rounded-full overflow-hidden">
  <div
    class="h-full bg-[var(--accent-primary)] transition-all duration-300"
    :style="{ width: `${progress}%` }"
  />
</div>
```

### Indeterminate Progress

When duration is unknown:

```vue
<div class="w-full h-1 bg-[var(--bg-secondary)] rounded-full overflow-hidden">
  <div class="h-full w-1/3 bg-[var(--accent-primary)] animate-indeterminate" />
</div>

<style>
@keyframes indeterminate {
  0% { transform: translateX(-100%); }
  100% { transform: translateX(400%); }
}
.animate-indeterminate {
  animation: indeterminate 1.5s ease-in-out infinite;
}
</style>
```

## Disabled State Feedback

Explain why something is disabled:

```vue
<button
  :disabled="!canSubmit"
  :title="!canSubmit ? 'Fix errors before submitting' : undefined"
  class="disabled:opacity-50 disabled:cursor-not-allowed"
>
  Submit
</button>
```

Or show inline:

```vue
<p v-if="!canSubmit" class="text-xs text-[var(--text-tertiary)] mt-1">
  Fix syntax errors to enable evaluation
</p>
```
