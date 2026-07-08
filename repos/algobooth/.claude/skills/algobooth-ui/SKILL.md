---
name: algobooth-ui
description: USE WHEN creating or modifying Vue components in src/components/. USE WHEN adding animations, transitions, hover states, or visual feedback. USE WHEN working with theme CSS variables or Tailwind styling.
triggers:
  - "src/components/**/*.vue"
  - "*.vue"
  - "animation"
  - "hover state"
  - "focus ring"
  - "transition"
  - "skeleton"
  - "loading"
  - "theme"
  - "backdrop-blur"
  - "--bg-"
  - "--text-"
  - "--accent-"
---

# AlgoBooth UI Design System

Design patterns for achieving "Notion app feeling" in AlgoBooth — polished, responsive, and consistent.

## Core Principles

1. **Animate only opacity and transform** — Never width/height/margin. GPU-accelerated only.
2. **4-layer depth hierarchy** — `--bg-primary` → `--bg-secondary` → `--bg-tertiary` → `--bg-elevated`
3. **Use CSS variables** — Themes define colors, components use variables
4. **Consistent timing** — 75-100ms press, 150ms hover, 180ms panel, 250ms modal
5. **Error resilience** — Never stop playback on errors. Show inline highlighting + HUD indicator.

## Quick Reference

### Animation Durations

| Element | Duration | Easing |
|---------|----------|--------|
| Button/pad press | 75-100ms | `ease-out` |
| Hover states | 150ms | `ease-out` |
| Panel/menu | 180ms | `ease-out` |
| Modal | 250ms | `cubic-bezier(0.22, 1, 0.36, 1)` |
| Slider feedback | Immediate | — |

### Focus Rings

```css
:focus-visible {
  outline: none;
  box-shadow: 0 0 0 2px var(--bg-primary), 0 0 0 4px var(--accent-primary);
}
```

### CSS Variable Naming

| Layer | Variable | Purpose |
|-------|----------|---------|
| Base | `--bg-primary` | App background |
| Panels | `--bg-secondary` | Sidebars, panels |
| Raised | `--bg-tertiary` | Cards, dropdowns |
| Elevated | `--bg-elevated` | Modals, overlays |

### Backdrop Blur

| Context | Value |
|---------|-------|
| Subtle overlay | `backdrop-blur-sm` (4px) |
| Modal | `backdrop-blur-md` (12px) |
| HUD | `backdrop-blur-lg` (16px) |

## Reference Files

Detailed patterns in `references/`:

- **animation-timing.md** — Duration tables, easing functions, Vue Transition examples
- **color-system.md** — Theme-agnostic depth layering, CSS variable conventions
- **component-states.md** — Default/hover/focus/active/disabled patterns
- **typography.md** — Font families, weights, sizes, text color variables
- **feedback-patterns.md** — Optimistic UI, skeletons, spinners, toasts
- **tailwind-snippets.md** — Copy-paste patterns for buttons, cards, inputs

## Vue Transition Pattern

```vue
<Transition name="fade">
  <div v-if="show">...</div>
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

## Tactile Press Feedback

Add to all interactive elements:
```html
<button class="transition-transform duration-75 active:scale-[0.98]">
```
