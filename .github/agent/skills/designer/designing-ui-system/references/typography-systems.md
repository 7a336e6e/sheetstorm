# Typography Systems Reference

## Modular Scales

A modular scale creates a harmonious set of font sizes by multiplying a base size by a fixed ratio. Start with a base of 1rem (16px) and multiply up or divide down.

### Common Ratios

| Name | Ratio | Character |
|------|-------|-----------|
| Minor Second | 1.067 | Very subtle, almost flat |
| Major Second | 1.125 | Gentle, good for dense UIs |
| Minor Third | 1.200 | Balanced, widely useful |
| Major Third | 1.250 | Clear hierarchy, recommended default |
| Perfect Fourth | 1.333 | Strong contrast, editorial feel |
| Golden Ratio | 1.618 | Dramatic, use for display-heavy layouts |

### Recommended: Major Third (1.25)

```
Step -2: 0.64rem  (10.24px) — use sparingly (captions, legal)
Step -1: 0.80rem  (12.80px) — small labels, metadata
Step  0: 1.00rem  (16.00px) — body text (base)
Step  1: 1.25rem  (20.00px) — large body, subheadings
Step  2: 1.563rem (25.00px) — section headings (h3)
Step  3: 1.953rem (31.25px) — page headings (h2)
Step  4: 2.441rem (39.06px) — hero/display (h1)
Step  5: 3.052rem (48.83px) — display only, rare use
```

Limit the scale to 5-6 sizes that the project actually needs. Having 10 named sizes creates decision fatigue and inconsistency.

## Font Pairing Rules

### Contrast + Harmony

Good font pairings have **contrast in style** but **similarity in proportions**:

- **Serif heading + Sans-serif body**: classic, high readability. Example: Fraunces + Source Sans 3.
- **Geometric sans heading + Humanist sans body**: modern, clean. Example: Outfit + Inter.
- **Slab serif heading + Geometric sans body**: bold, editorial. Example: Zilla Slab + IBM Plex Sans.

### What Makes Pairings Fail

- **Same classification**: two geometric sans-serifs look redundant, not complementary.
- **Mismatched x-height**: if the body font has a tall x-height and the heading font has a short one, they'll feel disjointed even at different sizes. Compare the lowercase "x" of both fonts at the same point size.
- **Too many families**: never use more than 2 font families. If you need a monospace for code, that's a third — but it should complement the other two.

### Weight Strategy

Limit to 3 weights maximum:

- **Regular (400)**: body text, descriptions, default.
- **Medium (500)**: labels, navigation, emphasis within body text.
- **Bold (700)**: headings, buttons, strong emphasis.

If a design needs Semi-bold (600), drop either Medium or Bold — don't use all four. Each added weight is an additional font file download.

## Responsive Typography

### The clamp() Approach

Use CSS `clamp()` for fluid scaling between breakpoints without media queries:

```css
/* Minimum 1rem, preferred 1rem + 0.5vw, maximum 1.25rem */
--text-base: clamp(1rem, 0.95rem + 0.25vw, 1.125rem);

/* Headings scale more aggressively */
--text-2xl: clamp(1.563rem, 1.2rem + 1.5vw, 2.441rem);
```

### Guidelines

- Body text: scale minimally (16px mobile to 18px desktop at most).
- Headings: scale more aggressively (25px mobile to 40px+ desktop).
- Never let text drop below 14px (0.875rem) for readability.
- Test at 320px viewport width — if text wraps badly or overflows, sizes are too large.

## Line Height Rules

Line height should decrease as font size increases:

| Font Size | Line Height | Reasoning |
|-----------|-------------|-----------|
| 12-14px (small text) | 1.6 - 1.75 | Small text needs generous leading for readability |
| 16-18px (body) | 1.5 - 1.6 | Standard comfortable reading height |
| 20-24px (large body, h4) | 1.3 - 1.4 | Starting to tighten |
| 25-32px (headings, h2-h3) | 1.2 - 1.3 | Tight but clear |
| 36px+ (display, h1) | 1.05 - 1.2 | Very tight; large text has built-in visual space |

Apply `line-height` at the token level alongside `font-size` so they always travel together.

### Measure (Line Length)

Optimal line length for body text: **45-75 characters** per line. This translates roughly to `max-width: 65ch` on the text container. Going wider causes eye strain; going narrower feels choppy.

## Font Loading

### Performance Best Practices

1. **Format**: serve WOFF2 only (all modern browsers support it). WOFF/TTF fallbacks add payload for near-zero benefit.
2. **font-display: swap**: shows fallback text immediately, swaps to custom font when loaded. Prevents invisible text (FOIT).
3. **Subset**: if only using Latin characters, subset the font file (saves 30-70% file size on fonts with large character sets).
4. **Preload critical fonts**: `<link rel="preload" href="font.woff2" as="font" type="font/woff2" crossorigin>` for the body regular weight. Don't preload every weight.
5. **Self-host**: avoids third-party network dependency and privacy concerns. Google Fonts is convenient but adds a DNS lookup + connection to fonts.gstatic.com.

### Fallback Stack

Always include a fallback stack that approximates the custom font's metrics:

```css
--font-sans: 'Source Sans 3', 'Segoe UI', Roboto, 'Helvetica Neue', sans-serif;
--font-serif: 'Fraunces', 'Georgia', 'Times New Roman', serif;
--font-mono: 'JetBrains Mono', 'Cascadia Code', 'Fira Code', monospace;
```

## Anti-Patterns

- **Using 3+ font families**: adds download weight, creates visual noise, and signals indecision.
- **Inconsistent weight usage**: using 400 in one component and 450 in another. Stick to the defined weight set.
- **Ignoring x-height differences**: pairing fonts with different x-heights makes size tokens unreliable — "text-base" will look different sizes in each font.
- **Hardcoding px values**: always use rem for font sizes so users who change their browser default font size are respected.
- **No fallback stack**: if the custom font fails to load, the browser picks a default that may have wildly different metrics, causing layout shift.
- **Loading all weights upfront**: only load the weights you actually use. If headings use 700 and body uses 400, don't load 300, 500, 600, 800, 900.
