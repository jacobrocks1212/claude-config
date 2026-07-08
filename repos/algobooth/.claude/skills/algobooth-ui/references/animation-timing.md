# Animation Timing Reference

## Duration Scale

| Duration | Use Case | Example |
|----------|----------|---------|
| 75-100ms | Immediate feedback | Button press, pad trigger |
| 150ms | Micro-interactions | Hover states, tooltips |
| 180ms | Panel transitions | Sidebar, dropdown, menu |
| 250ms | Modal transitions | Dialog open/close |
| 300ms | Complex transitions | Page transitions, large reveals |

## Easing Functions

| Name | CSS | Use Case |
|------|-----|----------|
| Standard | `ease-out` | Most UI transitions |
| Pop | `cubic-bezier(0.22, 1, 0.36, 1)` | Modal open, pad trigger feedback |
| Smooth | `cubic-bezier(0.4, 0, 0.2, 1)` | Crossfade, gradual reveals |
| Bounce | `cubic-bezier(0.34, 1.56, 0.64, 1)` | Playful emphasis (use sparingly) |

## Performance Rules

1. **GPU-accelerated only** — `opacity`, `transform` (translate, scale, rotate)
2. **Never animate** — `width`, `height`, `margin`, `padding`, `top`, `left`
3. **Will-change sparingly** — Add `will-change: transform, opacity` only when needed
4. **Reduced motion** — Respect `prefers-reduced-motion: reduce`

```css
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: 0.01ms !important;
    transition-duration: 0.01ms !important;
  }
}
```

## Vue Transition Examples

### Fade (180ms panel)

```vue
<Transition name="fade">
  <div v-if="isOpen">Panel content</div>
</Transition>

<style>
.fade-enter-active,
.fade-leave-active {
  transition: opacity 180ms ease-out;
}
.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
</style>
```

### Scale + Fade (250ms modal)

```vue
<Transition name="modal">
  <div v-if="isOpen" class="modal">Modal content</div>
</Transition>

<style>
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
</style>
```

### Slide (180ms dropdown)

```vue
<Transition name="dropdown">
  <ul v-if="isOpen">Menu items</ul>
</Transition>

<style>
.dropdown-enter-active,
.dropdown-leave-active {
  transition: opacity 180ms ease-out, transform 180ms ease-out;
}
.dropdown-enter-from,
.dropdown-leave-to {
  opacity: 0;
  transform: translateY(-8px);
}
</style>
```

## Tailwind Transition Classes

```html
<!-- Hover state (150ms) -->
<div class="transition-colors duration-150">

<!-- Press feedback (75ms) -->
<button class="transition-transform duration-75 active:scale-[0.98]">

<!-- Panel (180ms) -->
<div class="transition-all duration-[180ms] ease-out">

<!-- Modal (250ms with custom easing) -->
<div class="transition-all duration-250 [transition-timing-function:cubic-bezier(0.22,1,0.36,1)]">
```

## Stagger Pattern

For lists, stagger enter animations:

```vue
<TransitionGroup name="list" tag="ul">
  <li v-for="(item, i) in items" :key="item.id" :style="{ transitionDelay: `${i * 30}ms` }">
    {{ item.name }}
  </li>
</TransitionGroup>
```

Max stagger: 150ms total (5 items × 30ms). Beyond that, use a single group animation.
