# Color Systems Reference

## HSL-Based Palette Generation

HSL (Hue, Saturation, Lightness) is the most intuitive model for building palettes programmatically.

### Generating Shades from a Single Hue

Fix the hue. Then create a 10-step scale by varying lightness from ~95% (near-white tint) down to ~10% (near-black shade). Adjust saturation at the extremes:

- **Light end (lightness > 80%)**: reduce saturation by 10-20% to avoid washed-out neon tints.
- **Dark end (lightness < 25%)**: reduce saturation by 5-15% to avoid muddy over-saturated darks.
- **Mid-range (40-60% lightness)**: keep saturation at or near the brand value — this is where the color is most "itself."

```
/* Example: brand hue 262 (purple), saturation 65% */
--color-primary-50:  hsl(262, 50%, 95%);   /* tint: lower sat */
--color-primary-100: hsl(262, 52%, 90%);
--color-primary-200: hsl(262, 56%, 80%);
--color-primary-300: hsl(262, 60%, 70%);
--color-primary-400: hsl(262, 63%, 60%);
--color-primary-500: hsl(262, 65%, 50%);   /* brand value */
--color-primary-600: hsl(262, 63%, 42%);
--color-primary-700: hsl(262, 58%, 34%);
--color-primary-800: hsl(262, 52%, 24%);
--color-primary-900: hsl(262, 45%, 14%);   /* shade: lower sat */
```

### Warm vs Cool Neutrals

Never use pure gray (saturation 0). Desaturate the brand hue to 5-12% saturation. This produces neutrals that feel intentionally connected to the brand:

- Brand hue 262 (purple) at 8% saturation yields cool-purple grays.
- Brand hue 30 (orange) at 10% saturation yields warm grays.

This single technique prevents the "generic corporate gray" look.

### Complementary / Analogous Secondary Colors

- **Analogous** (hue +/- 30): safe, harmonious, low contrast between primary and secondary.
- **Complementary** (hue + 180): high contrast, energetic, but requires care to avoid clashing.
- **Split-complementary** (hue + 150 and hue + 210): balanced contrast with more variety.

Pick one strategy and stick with it. Don't mix approaches.

## Accessible Color Pairs

### WCAG 2.2 AA Requirements

| Context | Minimum Contrast Ratio |
|---------|----------------------|
| Normal text (< 24px regular, < 18.66px bold) | 4.5:1 |
| Large text (>= 24px regular, >= 18.66px bold) | 3:1 |
| UI components and graphical objects | 3:1 |
| Non-text decorative elements | No requirement |

### Practical Pairing Rules

- Text on **light backgrounds**: use shade 700-900 of any hue for body text. Shade 500-600 often fails on white.
- Text on **colored backgrounds**: white text works on shades 600+ of most hues. Test every combination.
- **Never rely on color alone** to convey information (e.g., red = error). Always pair with an icon, label, or pattern.

## Semantic Colors

Map semantic meaning to palette ranges, but choose values deliberately:

- **Success**: hue 140-160 (green), but not #00FF00. Use muted, accessible greens like hsl(152, 55%, 38%).
- **Warning**: hue 35-50 (amber/gold), not bright yellow (fails contrast on white). Use hsl(42, 90%, 42%).
- **Error**: hue 0-10 (red), desaturated enough to not feel alarming in mild contexts. Use hsl(4, 70%, 48%).
- **Info**: hue 200-220 (blue). Be careful this doesn't clash with a blue primary.

Each semantic color needs at minimum: base, a light variant (for backgrounds), and a dark variant (for text on light bg).

## Dark Mode Strategy

Dark mode is NOT "invert all colors." Key principles:

1. **Background layers**: use neutral-900 as base surface, neutral-800 as elevated surface, neutral-700 for borders. Never use pure black (#000) as the base — it causes eye strain and halation on OLED.
2. **Reduce saturation**: colors that look good on white look garish on dark backgrounds. Reduce saturation by 10-20% and increase lightness by 5-10% for dark mode variants.
3. **Flip the shade scale for text**: body text that was neutral-900 on light becomes neutral-100 on dark. But don't go pure white — use neutral-50 or neutral-100 for primary text, neutral-300 for secondary.
4. **Shadows become less effective**: on dark surfaces, shadows are nearly invisible. Use subtle borders (1px neutral-700) or slightly lighter elevation surfaces instead.
5. **Semantic colors need adjustment**: error-red at the same value will feel much more intense on a dark surface. Lighten and desaturate.

## Common AI Pitfalls

### The "Corporate Blue + Light Gray" Trap

The most common AI-generated palette: primary blue (#3B82F6 or similar), neutral gray (#F3F4F6 background, #111827 text), green success, red error. This palette appears in virtually every AI-generated UI. It looks "fine" but is completely devoid of brand identity.

**Fix**: start from the user's actual brand color. If they don't have one, propose 3 distinct directions (warm, cool, vibrant) and let them choose.

### Oversaturated Accent Colors

AI models tend to produce fully saturated accent colors (100% saturation) that vibrate against backgrounds. Real design systems use restrained saturation (50-75%) for most UI contexts.

### Ignoring the Relationship Between Colors

AI often generates colors independently. A good palette has clear relationships: the secondary is derived from the primary, neutrals carry the brand hue, semantic colors don't fight the primary.

## Tool References

- **Contrast checking**: WebAIM Contrast Checker, Chrome DevTools CSS Overview.
- **Palette generation from brand color**: Huetone (HSL-based, good for systematic scales), OKLCH Color Picker.
- **Visualization**: apply the palette to a real UI mockup, not just swatches. Colors behave differently at scale.
