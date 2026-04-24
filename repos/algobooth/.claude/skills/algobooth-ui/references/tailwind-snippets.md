# Tailwind Snippets Reference

Copy-paste patterns using CSS variables for consistent styling.

## Buttons

### Primary Button

```html
<button class="
  px-4 py-2
  bg-[var(--accent-primary)]
  text-[var(--text-inverse)]
  font-medium
  rounded-lg
  transition-all duration-150
  hover:opacity-90
  focus:outline-none
  focus-visible:ring-2
  focus-visible:ring-[var(--accent-primary)]
  focus-visible:ring-offset-2
  focus-visible:ring-offset-[var(--bg-primary)]
  active:scale-[0.98]
  disabled:opacity-50
  disabled:pointer-events-none
">
  Primary Action
</button>
```

### Secondary Button

```html
<button class="
  px-4 py-2
  bg-[var(--bg-tertiary)]
  text-[var(--text-primary)]
  font-medium
  rounded-lg
  border border-[var(--border-primary)]
  transition-all duration-150
  hover:bg-[var(--overlay-sm)]
  focus:outline-none
  focus-visible:ring-2
  focus-visible:ring-[var(--accent-primary)]
  focus-visible:ring-offset-2
  focus-visible:ring-offset-[var(--bg-primary)]
  active:scale-[0.98]
  disabled:opacity-50
  disabled:pointer-events-none
">
  Secondary Action
</button>
```

### Ghost Button

```html
<button class="
  px-3 py-1.5
  text-[var(--text-secondary)]
  font-medium
  rounded-md
  transition-colors duration-150
  hover:bg-[var(--overlay-sm)]
  hover:text-[var(--text-primary)]
  focus:outline-none
  focus-visible:ring-2
  focus-visible:ring-[var(--accent-primary)]
  active:bg-[var(--overlay-md)]
">
  Ghost Action
</button>
```

### Icon Button

```html
<button class="
  p-2
  rounded-lg
  text-[var(--text-secondary)]
  transition-all duration-150
  hover:bg-[var(--overlay-sm)]
  hover:text-[var(--text-primary)]
  focus:outline-none
  focus-visible:ring-2
  focus-visible:ring-[var(--accent-primary)]
  active:scale-[0.95]
">
  <IconName class="w-5 h-5" />
</button>
```

## Cards

### Basic Card

```html
<div class="
  bg-[var(--bg-tertiary)]
  rounded-xl
  p-4
  border border-[var(--border-primary)]
  shadow-[var(--shadow-sm)]
">
  Card content
</div>
```

### Interactive Card

```html
<button class="
  w-full
  bg-[var(--bg-tertiary)]
  rounded-xl
  p-4
  border border-[var(--border-primary)]
  text-left
  transition-all duration-150
  hover:bg-[var(--overlay-sm)]
  hover:border-[var(--border-hover)]
  focus:outline-none
  focus-visible:ring-2
  focus-visible:ring-[var(--accent-primary)]
  active:scale-[0.99]
">
  Clickable card content
</button>
```

### Selected Card

```html
<div :class="[
  'bg-[var(--bg-tertiary)] rounded-xl p-4 border transition-all duration-150',
  isSelected
    ? 'border-[var(--accent-primary)] bg-[var(--overlay-sm)]'
    : 'border-[var(--border-primary)]'
]">
```

## Inputs

### Text Input

```html
<input
  type="text"
  class="
    w-full
    px-3 py-2
    bg-[var(--bg-secondary)]
    text-[var(--text-primary)]
    placeholder:text-[var(--text-tertiary)]
    border border-[var(--border-primary)]
    rounded-lg
    transition-colors duration-150
    hover:border-[var(--border-hover)]
    focus:outline-none
    focus:border-[var(--accent-primary)]
    focus:ring-1
    focus:ring-[var(--accent-primary)]
    disabled:opacity-50
    disabled:cursor-not-allowed
  "
  placeholder="Enter value..."
/>
```

### Input with Error

```html
<input
  type="text"
  :class="[
    'w-full px-3 py-2 bg-[var(--bg-secondary)] rounded-lg border transition-colors',
    hasError
      ? 'border-[var(--state-error)] focus:ring-[var(--state-error)]'
      : 'border-[var(--border-primary)] focus:ring-[var(--accent-primary)]'
  ]"
/>
<p v-if="hasError" class="text-sm text-[var(--state-error)] mt-1">
  {{ errorMessage }}
</p>
```

## Badges

### Status Badge

```html
<span class="
  inline-flex items-center
  px-2 py-0.5
  text-xs font-medium
  rounded-full
  bg-[rgba(var(--state-success-rgb),0.15)]
  text-[var(--state-success)]
">
  Active
</span>
```

### Tag Badge

```html
<span class="
  inline-flex items-center
  px-2 py-0.5
  text-xs
  rounded-md
  bg-[var(--overlay-sm)]
  text-[var(--text-secondary)]
">
  Tag
</span>
```

## Dropdown/Menu

```html
<Transition name="dropdown">
  <div v-if="isOpen" class="
    absolute z-50
    mt-1
    w-48
    bg-[var(--bg-elevated)]
    rounded-lg
    border border-[var(--border-primary)]
    shadow-[var(--shadow-lg)]
    py-1
    backdrop-blur-md
  ">
    <button class="
      w-full
      px-3 py-2
      text-left text-sm
      text-[var(--text-primary)]
      transition-colors duration-150
      hover:bg-[var(--overlay-sm)]
      focus:outline-none
      focus:bg-[var(--overlay-sm)]
    ">
      Menu Item
    </button>
  </div>
</Transition>
```

## Modal

```html
<Transition name="modal">
  <div v-if="isOpen" class="fixed inset-0 z-50 flex items-center justify-center">
    <!-- Backdrop -->
    <div
      class="absolute inset-0 bg-black/50 backdrop-blur-sm"
      @click="close"
    />

    <!-- Modal -->
    <div class="
      relative
      w-full max-w-md
      bg-[var(--bg-elevated)]
      rounded-2xl
      border border-[var(--border-primary)]
      shadow-[var(--shadow-lg)]
      p-6
    ">
      Modal content
    </div>
  </div>
</Transition>
```

## Vue Transitions

### Fade Transition

```css
.fade-enter-active,
.fade-leave-active {
  transition: opacity 180ms ease-out;
}
.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
```

### Dropdown Transition

```css
.dropdown-enter-active,
.dropdown-leave-active {
  transition: opacity 180ms ease-out, transform 180ms ease-out;
}
.dropdown-enter-from,
.dropdown-leave-to {
  opacity: 0;
  transform: translateY(-8px);
}
```

### Modal Transition

```css
.modal-enter-active,
.modal-leave-active {
  transition: opacity 250ms cubic-bezier(0.22, 1, 0.36, 1),
              transform 250ms cubic-bezier(0.22, 1, 0.36, 1);
}
.modal-enter-from,
.modal-leave-to {
  opacity: 0;
  transform: scale(0.95);
}
```

## Utility Classes

### Truncate with Tooltip

```html
<span class="truncate max-w-[200px]" :title="fullText">
  {{ fullText }}
</span>
```

### Scrollable Container

```html
<div class="
  overflow-y-auto
  scrollbar-thin
  scrollbar-thumb-[var(--bg-tertiary)]
  scrollbar-track-transparent
">
```

### Divider

```html
<div class="h-px bg-[var(--border-primary)] my-2" />
```
