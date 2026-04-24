# Color System Reference

AlgoBooth uses a **theme-agnostic** color system. Components reference CSS variables; themes define the actual values.

## 4-Layer Depth Hierarchy

| Layer | Variable | Purpose | Example |
|-------|----------|---------|---------|
| Base | `--bg-primary` | App background | Main canvas |
| Panels | `--bg-secondary` | Containers | Sidebars, panels |
| Raised | `--bg-tertiary` | Elevated surfaces | Cards, dropdowns |
| Elevated | `--bg-elevated` | Top-level overlays | Modals, popovers |

### Depth Principle

Each layer should be visibly distinct from its parent. In dark themes, layers typically progress from darker to lighter. In light themes, the reverse.

```css
/* Theme authors: ensure visual distinction between layers */
:root {
  --bg-primary: /* darkest */;
  --bg-secondary: /* slightly lighter */;
  --bg-tertiary: /* noticeably lighter */;
  --bg-elevated: /* lightest, often with blur */;
}
```

## Text Color Variables

| Variable | Purpose |
|----------|---------|
| `--text-primary` | Main content, headings |
| `--text-secondary` | Labels, descriptions |
| `--text-tertiary` | Placeholder, disabled |
| `--text-inverse` | Text on inverted backgrounds |

## Accent Colors

| Variable | Purpose |
|----------|---------|
| `--accent-primary` | Primary actions, focus rings |
| `--accent-cue` | Cue channel indicator |
| `--accent-master` | Master channel indicator |

## State Colors

| Variable | Purpose |
|----------|---------|
| `--state-error` | Errors, destructive actions |
| `--state-error-rgb` | RGB components for overlays |
| `--state-warning` | Warnings, cautions |
| `--state-warning-rgb` | RGB components for overlays |
| `--state-success` | Success, confirmations |
| `--state-success-rgb` | RGB components for overlays |

### State Overlays

For semi-transparent state backgrounds:

```css
.error-bg {
  background: rgba(var(--state-error-rgb), 0.1);
}
```

## Overlay System

| Variable | Opacity | Use Case |
|----------|---------|----------|
| `--overlay-xs` | 5% | Subtle hover |
| `--overlay-sm` | 8% | Light hover |
| `--overlay-md` | 12% | Selected state |
| `--overlay-lg` | 15% | Active/pressed |

```css
.hover-overlay:hover {
  background: var(--overlay-sm);
}
```

## Backdrop Blur

| Context | Tailwind | CSS |
|---------|----------|-----|
| Subtle | `backdrop-blur-sm` | 4px |
| Standard | `backdrop-blur-md` | 12px |
| HUD | `backdrop-blur-lg` | 16px |

Combine with semi-transparent backgrounds:

```css
.modal-overlay {
  background: rgba(0, 0, 0, 0.5);
  backdrop-filter: blur(12px);
}
```

## Shadow Tokens

| Variable | Use Case |
|----------|----------|
| `--shadow-sm` | Subtle lift (buttons) |
| `--shadow-md` | Cards, dropdowns |
| `--shadow-lg` | Modals, popovers |

## Syntax Highlighting (Diff)

| Variable | Purpose |
|----------|---------|
| `--syntax-new` | Added lines |
| `--syntax-removed` | Deleted lines |
| `--syntax-changed` | Modified lines |

## Anti-Patterns

**Never hardcode colors in components:**

```css
/* BAD */
.card { background: #1a1a2e; }
.error { color: #ff6b6b; }

/* GOOD */
.card { background: var(--bg-tertiary); }
.error { color: var(--state-error); }
```

**Exception:** Canvas/WebGL rendering may need to read CSS variables via `getComputedStyle()`:

```typescript
const style = getComputedStyle(document.documentElement);
const color = style.getPropertyValue('--accent-cue').trim();
```
