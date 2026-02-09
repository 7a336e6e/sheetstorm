---
name: creating-page-layouts
description: Design immersive, high-end page structures using Bento Grids, Asymmetry, and Sticky Scrolling. Reject the "Generic SaaS Template."
---

# Creating Page Layouts

## Goal
Create layouts that feel "editorial" and "curated." Move beyond the standard "Hero -> 3 Columns -> Footer" stack. The user should feel they are exploring a space, not just scrolling a list.

## When to Use
- Designing landing pages, dashboards, or complex content views.
- When the page feels "boring" or "predictable."

## Instructions

### 1. The "Anti-Template" Structure
Stop using the standard "SaaS Sandwich" (Center Header, Center Hero, 3 Cards).
- **Try Asymmetry**: Put the title on the left, big image on the right (60/40 split).
- **Try Overlap**: Let images bleed behind text. Let cards float over sections (`margin-top: -50px`).
- **Try Horizontal Scroll**: For galleries, break the vertical monotony.

### 2. The Bento Grid (Dashboard & Features)
Organize content into a cohesive "Box Grid" (like Apple/Linear bento slides).
- **Concept**: A unified grid where every cell has a different aspect ratio but fits perfectly.
- **CSS**:
  ```css
  .bento-grid {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    grid-auto-rows: 200px;
    gap: var(--space-4);
  }
  .bento-item-tall { grid-row: span 2; }
  .bento-item-wide { grid-column: span 2; }
  ```
- **Feel**: Dense, information-rich, but organized.

### 3. Sticky & Parallax (The "Feel")
Use `position: sticky` to keep context while scrolling.
- **Split Screen**: Left side text scrolls, right side image stays sticky.
- **Micro-Parallax**: Translate background elements at different speeds (slowly!) during scroll.

### 4. Break the Container
Don't trap everything in `max-w-4xl`.
- **Full Bleed**: Let images hit the edge of the browser.
- **One-Side Bleed**: Text aligns to the center grid, but the image extends to the right edge.

## Constraints

### ✅ Do
- Use CSS Grid for 2D layouts (Bento). Flexbox is for 1D (rows/stacks).
- Design for "Large Screens" (1440px+) too, not just 1024px. Use that extra space.
- Group related items visually using "Surfaces" (subtle background colors), not just lines.
- Use `gap` generously. Dense content needs high gap.


### ❌ Don&#x27;t
- DO NOT build the "3 Cards in a Row" feature section. It is the hallmark of a lazy template. Use a Bento grid or a Z-pattern instead.
- DO NOT center-align long paragraphs. Left-align for readability.
- DO NOT let the page feel static. Something should change as I scroll (sticky headers, active nav, fading elements).


## Output Format
- Semantic HTML structure.
- Tailwind/CSS Grid code.
- "Layout Rationale": Why this structure fits the content.

## Dependencies
- `designer/designing-ui-system/SKILL.md`