---
name: designing-ui-system
description: Create a unique, soulful design system that avoids generic "AI Slop." Defines tokens for color, typography, spacing, and motion that feel handcrafted and intentional.
---

# Designing a UI System

## Goal
Produce a visual identity that feels *human*, distinct, and premium. The system must reject the "default bootstrap/tailwind" look. It should have "soul"—intentionality in every curve, color, and gap.

## When to Use
- Starting a new project.
- Rebranding an existing application.
- When a UI looks "too generic" or "like a template."

## Instructions

### 1. The "Anti-Slop" Color Palette
Avoid the "Safe Blue" (#3B82F6) and "Cool Gray" default.
- **Input**: Extract the "Vibe" (e.g., "Cyber-Noir", "Organic-Calm", "Swiss-Brutalist").
- **Process**:
  - **Primary**: Pick a distinct hue. If Blue, make it Electric Ultramarine or Deep Indigo, not "Link Blue".
  - **Neutrals**: NEVER use pure gray. Tint them with the primary hue or a complementary hue (e.g., Warm Sand, Cool Slate, Blue-Black).
  - **Accents**: Use unusual combinations (e.g., Olive Green + Acid Yellow, Navy + Coral).
  - **Dark Mode**: Don't just invert. Use deep, rich backgrounds (Charcoal, Midnight, Deep Forest), not pure #000000.

### 2. Typography with Character
Stop using Inter/Roboto/System-UI by default. They are the "Times New Roman" of 2026.
- **Headings**: Choose a font with *flavor*. A sharp serif (Fraunces), a wide grotesque (Space Grotesk), or a monospaced display (JetBrains Mono).
- **Body**: Readable but distinct (e.g., Plus Jakarta Sans, Satoshi, IBM Plex Sans).
- **Scale**: Use a dramatic scale (Major Third or Perfect Fourth). Huge headings, readable body.

### 3. Spacing & Rhythm (The "Breath")
- **Micro-Whitepace**: Tight packing for data-heavy areas.
- **Macro-Whitespace**: Enormous gaps for marketing/editorial areas.
- **Rule**: If in doubt, double the padding. "Air" is luxury.

### 4. Radius & Depth
- **Radius**: Be opinionated. Either Fully Round (Pill), Soft (16px+), or Sharp (0px). Don't do the generic 4px.
- **Depth**: Stop using default drop shadows. Use:
  - **Glows**: Colored shadows (`box-shadow: 0 10px 30px -10px var(--brand-color-alpha)`).
  - **Borders**: 1px solid borders in low-opacity for that "technical" look.
  - **Glass**: Backdrop-filter blur (carefully).

### 5. Motion Tokens
Static UIs feel dead. Define:
- `--ease-elastic`: `cubic-bezier(0.68, -0.6, 0.32, 1.6)` (Bouncy, playful).
- `--ease-squish`: `cubic-bezier(0.25, 1, 0.5, 1)` (Premium, snappy).

## Constraints

### ✅ Do
- **BAN** the default Tailwind color palette. You MUST generate a custom `tailwind.config.ts` theme.
- **BAN** "Inter" as the primary font unless the brand specifically demands "invisible" type.
- **ENFORCE** a "Tinted Neutral" system. Grays must have a hue.
- **ENFORCE** 4.5:1 contrast for body text, but allow lower contrast for "decorative" large text (if accessible alternatives exist).
- Use `clamp()` for fluid typography that scales with the viewport.


### ❌ Don&#x27;t
- DO NOT use the "Start-up Blue" (#3B82F6).
- DO NOT use pure black (#000000) or pure white (#FFFFFF) for backgrounds. It harms eye comfort.
- DO NOT mix more than 2 sans-serifs. (One Serif + One Sans is the classic "Soulful" pairing).
- DO NOT forget focus states. Custom focus rings (offset, colored) are a hallmark of quality.


## Output Format
- `tailwind.config.ts`: Fully customized theme.
- `global.css`: CSS Variables for non-Tailwind contexts.
- `typography.md`: Rationale for font choices.

## Dependencies
- `designer/brand-identity/SKILL.md` (Source of the "Vibe")

