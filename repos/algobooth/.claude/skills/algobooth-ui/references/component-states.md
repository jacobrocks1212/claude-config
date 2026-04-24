# Component States Reference

All interactive components should have consistent state styling.

## State Progression

```
default → hover → focus → active → disabled
```

## Button States

```vue
<button
  class="
    bg-[var(--bg-tertiary)]
    text-[var(--text-primary)]
    transition-all duration-150

    hover:bg-[var(--overlay-sm)]

    focus-visible:outline-none
    focus-visible:ring-2
    focus-visible:ring-[var(--accent-primary)]
    focus-visible:ring-offset-2
    focus-visible:ring-offset-[var(--bg-primary)]

    active:scale-[0.98]
    active:bg-[var(--overlay-md)]

    disabled:opacity-50
    disabled:pointer-events-none
  "
>
  Button
</button>
```

## Focus Ring Pattern

The focus ring should be visible on keyboard navigation but not mouse clicks:

```css
/* Base: hide outline */
.interactive {
  outline: none;
}

/* Focus-visible: show ring on keyboard focus */
.interactive:focus-visible {
  box-shadow:
    0 0 0 2px var(--bg-primary),      /* Gap */
    0 0 0 4px var(--accent-primary);  /* Ring */
}
```

Or with Tailwind:

```html
<button class="
  focus:outline-none
  focus-visible:ring-2
  focus-visible:ring-[var(--accent-primary)]
  focus-visible:ring-offset-2
  focus-visible:ring-offset-[var(--bg-primary)]
">
```

## Input States

```vue
<input
  class="
    bg-[var(--bg-secondary)]
    text-[var(--text-primary)]
    border border-[var(--border-primary)]
    rounded-md px-3 py-2
    transition-colors duration-150

    placeholder:text-[var(--text-tertiary)]

    hover:border-[var(--border-hover)]

    focus:outline-none
    focus:border-[var(--accent-primary)]
    focus:ring-1
    focus:ring-[var(--accent-primary)]

    disabled:opacity-50
    disabled:cursor-not-allowed
  "
/>
```

## Error States

Error state should not replace focus state — combine them:

```vue
<input
  :class="[
    'base-input-classes',
    hasError && 'border-[var(--state-error)] focus:ring-[var(--state-error)]'
  ]"
/>
<p v-if="errorMessage" class="text-sm text-[var(--state-error)] mt-1">
  {{ errorMessage }}
</p>
```

## Loading States

### Disabled + Spinner

```vue
<button :disabled="isLoading" class="relative">
  <span :class="{ 'opacity-0': isLoading }">Submit</span>
  <span v-if="isLoading" class="absolute inset-0 flex items-center justify-center">
    <Spinner />
  </span>
</button>
```

### Skeleton

```vue
<div v-if="isLoading" class="animate-pulse">
  <div class="h-4 bg-[var(--bg-tertiary)] rounded w-3/4 mb-2"></div>
  <div class="h-4 bg-[var(--bg-tertiary)] rounded w-1/2"></div>
</div>
<div v-else>
  {{ content }}
</div>
```

## Pad/Grid Item States

Pads have special tactile feedback:

```vue
<button
  class="
    bg-[var(--bg-tertiary)]
    rounded-lg
    transition-all
    duration-75  /* Faster for pads */

    hover:bg-[var(--overlay-sm)]

    active:scale-[0.95]  /* More pronounced for pads */
    active:bg-[var(--overlay-md)]

    focus-visible:ring-2
    focus-visible:ring-[var(--accent-primary)]
  "
  :class="{
    'ring-2 ring-[var(--accent-cue)]': isActive,
    'opacity-50': isMuted
  }"
>
```

## Selected State

For selectable items (lists, grids):

```vue
<div
  :class="[
    'transition-colors duration-150',
    isSelected
      ? 'bg-[var(--overlay-md)] border-[var(--accent-primary)]'
      : 'bg-[var(--bg-tertiary)] border-transparent'
  ]"
>
```

## Drag States

```vue
<div
  :class="{
    'opacity-50 scale-105': isDragging,
    'ring-2 ring-[var(--accent-primary)] ring-dashed': isDragOver
  }"
>
```

## State Combinations

When states overlap, later states should enhance, not replace:

| Base | + Hover | + Focus | + Active |
|------|---------|---------|----------|
| `bg-tertiary` | `+ overlay-sm` | `+ ring` | `+ scale + overlay-md` |

Never lose the focus ring when other states are active.
