# Typography Reference

## Font Families

| Variable | Family | Use Case |
|----------|--------|----------|
| `--font-sans` | Inter | UI text, labels, buttons |
| `--font-mono` | Fira Code | Code, numbers, technical |

```css
:root {
  --font-sans: 'Inter', system-ui, -apple-system, sans-serif;
  --font-mono: 'Fira Code', 'JetBrains Mono', 'Consolas', monospace;
}
```

## Font Weights

| Weight | Name | Use Case |
|--------|------|----------|
| 400 | Regular | Body text, descriptions |
| 500 | Medium | Labels, buttons, emphasis |
| 600 | Semibold | Headings, important values |
| 700 | Bold | Strong emphasis (rare) |

## Type Scale

| Class | Size | Line Height | Use Case |
|-------|------|-------------|----------|
| `text-xs` | 12px | 1.5 | Captions, timestamps |
| `text-sm` | 14px | 1.5 | Secondary text, labels |
| `text-base` | 16px | 1.5 | Body text |
| `text-lg` | 18px | 1.5 | Section headings |
| `text-xl` | 20px | 1.4 | Panel titles |
| `text-2xl` | 24px | 1.3 | Page headings |

## Text Colors

| Variable | Purpose | Opacity (typical) |
|----------|---------|-------------------|
| `--text-primary` | Main content | 90-100% |
| `--text-secondary` | Labels, descriptions | 60-70% |
| `--text-tertiary` | Placeholders, hints | 40-50% |
| `--text-inverse` | On accent backgrounds | 100% |

## Mono Text Patterns

### Code Display

```html
<code class="font-mono text-sm bg-[var(--bg-secondary)] px-1.5 py-0.5 rounded">
  pattern.code
</code>
```

### Numeric Values

```html
<span class="font-mono tabular-nums text-sm">
  {{ formattedValue }}
</span>
```

Use `tabular-nums` for numbers that change (timers, counters) to prevent layout shift.

### BPM/Tempo Display

```html
<span class="font-mono text-lg font-semibold tabular-nums tracking-tight">
  {{ bpm }}
</span>
<span class="text-xs text-[var(--text-secondary)] ml-1">BPM</span>
```

## Label Patterns

### Form Label

```html
<label class="text-sm font-medium text-[var(--text-secondary)]">
  Parameter Name
</label>
```

### Section Header

```html
<h3 class="text-sm font-semibold text-[var(--text-primary)] uppercase tracking-wider">
  Section Title
</h3>
```

### Helper Text

```html
<p class="text-xs text-[var(--text-tertiary)] mt-1">
  Optional description or hint
</p>
```

## Truncation

### Single Line

```html
<p class="truncate">Long text that will be truncated...</p>
```

### Multi-line (2 lines)

```html
<p class="line-clamp-2">
  Long text that spans multiple lines and will be truncated after two lines...
</p>
```

## Accessibility

- Minimum contrast ratio: 4.5:1 for normal text, 3:1 for large text
- Minimum font size: 12px (use sparingly, prefer 14px+)
- Line length: 60-80 characters max for readability
- Don't rely on color alone to convey meaning

```html
<!-- Good: icon + color + text -->
<span class="text-[var(--state-error)] flex items-center gap-1">
  <WarningIcon />
  Error message
</span>
```
