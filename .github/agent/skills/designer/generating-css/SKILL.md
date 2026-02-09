---
name: generating-css
description: Generate production CSS from design tokens using Tailwind CSS or vanilla CSS. Maps tokens to Tailwind theme config and establishes CSS architecture.
---

# Generating CSS

## Goal

Transform design tokens into usable CSS — either as a Tailwind theme configuration or as vanilla CSS custom properties with utility classes. The output should be production-ready, connected to the token system, and free of redundant or dead styles.

## When to Use

- After design tokens have been defined (via `designing-ui-system`).
- When scaffolding a new frontend project that needs its styling foundation.
- When migrating from ad-hoc styles to a token-based CSS architecture.

## Instructions

### 1. Establish CSS Architecture Layers

CSS flows through four layers, each building on the previous:

```
Tokens → Utilities → Components → Layouts
```

- **Tokens**: raw design values (colors, spacing, type sizes) as CSS custom properties or Tailwind config.
- **Utilities**: single-purpose classes (Tailwind provides these; in vanilla CSS, define sparingly).
- **Components**: multi-property styles for repeated UI patterns (button, card, badge). Only extract when a pattern repeats 3+ times.
- **Layouts**: page-level grid and container styles.

### 2. Map Tokens to Tailwind Configuration

Extend the Tailwind theme — do not override defaults wholesale. This preserves useful defaults while adding project-specific tokens:

```typescript
// tailwind.config.ts
import type { Config } from 'tailwindcss';

export default {
  content: ['./src/**/*.{ts,tsx,html}'],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        // Map token names to HSL values from the design system
        primary: {
          50:  'hsl(var(--color-primary-50)  / <alpha-value>)',
          100: 'hsl(var(--color-primary-100) / <alpha-value>)',
          200: 'hsl(var(--color-primary-200) / <alpha-value>)',
          300: 'hsl(var(--color-primary-300) / <alpha-value>)',
          400: 'hsl(var(--color-primary-400) / <alpha-value>)',
          500: 'hsl(var(--color-primary-500) / <alpha-value>)',
          600: 'hsl(var(--color-primary-600) / <alpha-value>)',
          700: 'hsl(var(--color-primary-700) / <alpha-value>)',
          800: 'hsl(var(--color-primary-800) / <alpha-value>)',
          900: 'hsl(var(--color-primary-900) / <alpha-value>)',
        },
        // Repeat for secondary, neutral, semantic colors
      },
      fontFamily: {
        sans: ['Source Sans 3', 'system-ui', 'sans-serif'],
        heading: ['Fraunces', 'Georgia', 'serif'],
      },
      fontSize: {
        xs:   ['0.75rem',  { lineHeight: '1.6' }],
        sm:   ['0.875rem', { lineHeight: '1.5' }],
        base: ['1rem',     { lineHeight: '1.6' }],
        lg:   ['1.25rem',  { lineHeight: '1.4' }],
        xl:   ['1.563rem', { lineHeight: '1.3' }],
        '2xl': ['1.953rem', { lineHeight: '1.2' }],
      },
      spacing: {
        // Extend with project tokens if Tailwind defaults don't match
        '4.5': '1.125rem', // 18px, if needed
      },
      borderRadius: {
        sm: '4px',
        md: '8px',
        lg: '16px',
      },
      boxShadow: {
        // Use brand-hue-tinted shadows, not pure black
        subtle: '0 1px 3px hsl(var(--color-primary-900) / 0.08)',
        medium: '0 4px 12px hsl(var(--color-primary-900) / 0.12)',
        strong: '0 8px 24px hsl(var(--color-primary-900) / 0.16)',
      },
    },
  },
  plugins: [],
} satisfies Config;
```

### 3. Store Token Values in CSS Custom Properties

Even with Tailwind, define tokens as CSS custom properties so they can be consumed by non-Tailwind contexts (third-party components, canvas rendering, emails):

```css
/* tokens.css — imported before Tailwind layers */
:root {
  --color-primary-50:  262 50% 95%;
  --color-primary-100: 262 52% 90%;
  /* ... full palette ... */

  --color-surface: var(--color-neutral-50);
  --color-on-surface: var(--color-neutral-900);
}

.dark {
  --color-surface: var(--color-neutral-900);
  --color-on-surface: var(--color-neutral-50);
  /* Reduce saturation for dark mode primary */
  --color-primary-500: 262 55% 60%;
}
```

### 4. Component Class Extraction

Only extract a component class when the same combination of utilities appears 3+ times AND the instances are semantically the same component:

```css
/* components.css */
@layer components {
  .btn-primary {
    @apply inline-flex items-center justify-center rounded-md px-4 py-2
           bg-primary-600 text-white font-medium text-sm
           hover:bg-primary-700 focus-visible:outline-2
           focus-visible:outline-offset-2 focus-visible:outline-primary-600
           transition-colors;
  }
}
```

Three buttons with the same style = extract. A button and a link that happen to share some padding = don't extract.

### 5. Dark Mode Implementation

Use the `class` strategy (not `media`) for dark mode in Tailwind. This allows programmatic toggling:

```html
<!-- Toggle class on <html> or <body> -->
<html class="dark">
```

```css
/* Tailwind handles dark: variants automatically */
/* For CSS custom properties, use the .dark selector */
.dark {
  --color-surface: 262 8% 10%;
  --color-on-surface: 262 7% 90%;
}
```

Dark mode rules:
- Swap the token values at the custom property level, not in individual components.
- Reduce color saturation by 10-20% for dark mode.
- Don't use pure black (#000) as dark background — use neutral-900 (slightly tinted).
- Shadows are ineffective on dark backgrounds; use subtle borders or elevation instead.

### 6. Responsive Utilities

For project-specific responsive patterns that Tailwind doesn't cover, add custom utilities:

```css
@layer utilities {
  .text-fluid-lg {
    font-size: clamp(1.25rem, 1rem + 1vw, 1.563rem);
  }

  .container-prose {
    max-width: 65ch;
    margin-inline: auto;
    padding-inline: var(--space-4);
  }
}
```

## Constraints

### ✅ Do
- Use design tokens as the single source of truth. Every color, size, and spacing value in CSS should trace back to a token.
- Extend the Tailwind theme rather than overriding it. Use `theme.extend` so default utilities remain available.
- Store token values as CSS custom properties so they work outside Tailwind contexts.
- Prefer Tailwind utility classes in markup over custom CSS for one-off styles.
- Extract component classes only when a utility pattern repeats 3+ times for the same semantic component.
- Use the class strategy for dark mode so it can be toggled programmatically.
- Include line-height in font-size token definitions so they travel together.
- Use HSL values without the `hsl()` wrapper in custom properties so Tailwind's opacity modifier syntax works.


### ❌ Don&#x27;t
- DO NOT write vanilla CSS that duplicates what Tailwind utilities already provide. If you're writing `.mt-4 { margin-top: 1rem; }` alongside Tailwind, something has gone wrong.
- DO NOT use `@apply` for everything. Extracting every element into an `@apply` class defeats the purpose of utility-first CSS — you end up maintaining a parallel stylesheet with none of the benefits.
- DO NOT generate CSS without connecting it to the design token system. Hardcoded hex values, pixel sizes, or magic numbers in CSS files mean the tokens are being bypassed.
- DO NOT use `!important`. If specificity conflicts exist, fix the cascade order or layer structure instead. The only acceptable `!important` is inside utility definitions (which Tailwind handles internally).
- DO NOT create a component class for a pattern that appears only once or twice. Use utilities inline instead. Premature extraction creates classes no one remembers exist.
- DO NOT override Tailwind's default `theme` (without `extend`). This removes useful defaults like `auto`, `full`, `screen`, and fractional spacing values.
- DO NOT generate a massive CSS file with "just in case" component classes. Every class should correspond to a component that exists in the UI right now.
- DO NOT mix design paradigms: pick either utility-first (Tailwind) or BEM/SMACSS (vanilla). Mixing both creates confusion about where styles live and which approach to use for new components.
- DO NOT use Tailwind's `@apply` with responsive or state variants (`@apply hover:bg-blue-500`). This doesn't work as expected and creates brittle CSS. Apply state styles as separate declarations or use utilities in markup.
- DO NOT ignore the CSS cascade order. Load styles in order: reset/base -> tokens -> utilities -> components -> layouts. Misordered layers cause specificity fights that lead to `!important` hacks.


## Output Format

1. `tailwind.config.ts` (or `.js`) with theme extensions mapped to design tokens.
2. `tokens.css` with CSS custom properties for all design tokens.
3. `components.css` (if needed) with extracted component classes using `@layer components`.
4. Brief notes explaining which tokens map to which Tailwind utilities.

## Dependencies

- `designer/designing-ui-system/SKILL.md` — provides the design tokens that this skill consumes.
- `../../frontend/scaffolding-frontend/SKILL.md` — provides the project structure where these CSS files live.
