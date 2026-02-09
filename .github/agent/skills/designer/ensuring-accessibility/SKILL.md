---
name: ensuring-accessibility
description: Ensure WCAG 2.2 AA compliance covering color contrast, keyboard navigation, screen reader support, accessible forms, and motion preferences.
---

# Ensuring Accessibility

## Goal

Make every UI component and page meet WCAG 2.2 AA standards. Accessibility is a design constraint applied from the start, not an audit bolted on after implementation.

## When to Use

- Always. Every component, page, and interaction should be evaluated against these standards.
- Specifically invoke this skill when building forms, interactive widgets, navigation, modals, or any component with state changes.

## Instructions

### 1. Color Contrast

Check every text/background combination against WCAG AA thresholds:

- **Normal text** (below 24px regular or 18.66px bold): minimum 4.5:1 contrast ratio.
- **Large text** (24px+ regular or 18.66px+ bold): minimum 3:1.
- **UI components** (borders, icons, form controls): minimum 3:1 against adjacent colors.

Check contrast for ALL states: default, hover, focus, disabled, active. Disabled elements are exempt from contrast requirements but should still be distinguishable.

### 2. Keyboard Navigation

Every interactive element must be:

- **Focusable**: reachable via Tab (or Shift+Tab for reverse). Custom components need `tabindex="0"`.
- **Operable**: activatable via Enter or Space. Custom click handlers need `onKeyDown` handling.
- **Visible when focused**: a visible focus ring (minimum 2px, 3:1 contrast against adjacent background). Never use `outline: none` without a replacement.

Tab order must follow visual reading order. Use the DOM order to establish logical flow — don't rely on CSS `order` or `tabindex` values greater than 0.

### 3. Screen Reader Support

Use semantic HTML as the foundation. The correct element communicates its role without ARIA:

```html
<!-- Good: semantic HTML communicates role -->
<button>Save changes</button>
<nav aria-label="Main navigation">
  <ul>
    <li><a href="/dashboard">Dashboard</a></li>
  </ul>
</nav>

<!-- Bad: div soup requiring ARIA to compensate -->
<div role="button" tabindex="0" onclick="save()">Save changes</div>
<div role="navigation" aria-label="Main navigation">
  <div role="list">
    <div role="listitem"><span onclick="navigate()">Dashboard</span></div>
  </div>
</div>
```

Use ARIA only when HTML semantics are insufficient:

- `aria-label`: when visible text doesn't adequately describe the element (e.g., an icon-only button: `<button aria-label="Close dialog">`).
- `aria-describedby`: to link supplementary descriptions (error messages, help text).
- `aria-live="polite"`: for dynamic content updates (toast notifications, loading states). Use `assertive` only for critical, time-sensitive alerts.
- `aria-expanded`, `aria-controls`: for disclosure widgets (accordions, dropdowns).

### 4. Accessible Forms

```html
<form novalidate>
  <fieldset>
    <legend>Shipping address</legend>

    <div>
      <label for="street">Street address</label>
      <input
        id="street"
        type="text"
        autocomplete="street-address"
        aria-required="true"
        aria-invalid="true"
        aria-describedby="street-error"
      />
      <p id="street-error" role="alert">
        Street address is required.
      </p>
    </div>

    <div>
      <label for="city">City</label>
      <input
        id="city"
        type="text"
        autocomplete="address-level2"
        aria-required="true"
      />
    </div>
  </fieldset>

  <button type="submit">Continue to payment</button>
</form>
```

Key form rules:
- Every input has an associated `<label>` via `for`/`id` pairing. Placeholder text is NOT a label.
- Group related fields with `<fieldset>` and `<legend>`.
- Error messages are linked to their field via `aria-describedby`.
- Use `aria-invalid="true"` on fields that have validation errors.
- Use `aria-required="true"` (or the `required` attribute) for mandatory fields.
- Use `autocomplete` attributes for common fields (name, email, address, phone).

### 5. Motion and Animation

Respect user preferences for reduced motion:

```css
@media (prefers-reduced-motion: reduce) {
  *,
  *::before,
  *::after {
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.01ms !important;
    scroll-behavior: auto !important;
  }
}
```

- Never auto-play animations or videos without user consent.
- Avoid animations that cover more than 1/3 of the screen area.
- Provide pause/stop controls for any animation that lasts more than 5 seconds.
- Parallax scrolling and motion-heavy transitions should be disabled entirely under `prefers-reduced-motion`.

### 6. Images and Media

- Every informative `<img>` needs a descriptive `alt` attribute. Describe the content, not the decoration ("Chart showing revenue growth from $2M to $5M" not "chart image").
- Decorative images: use `alt=""` (empty string, NOT omitting the attribute) or CSS `background-image`.
- Videos need captions. Audio needs transcripts.
- SVG icons: use `aria-hidden="true"` when the icon is decorative or paired with visible text.

### 7. Testing Checklist

1. **Automated**: run axe-core or Lighthouse accessibility audit. Fix all critical and serious issues.
2. **Keyboard**: navigate the entire page using only Tab, Shift+Tab, Enter, Space, Escape, Arrow keys. Every interactive element must be reachable and operable.
3. **Screen reader**: test with VoiceOver (macOS/iOS) or NVDA (Windows). Listen to the page being read — does the reading order make sense? Are interactive elements announced with their role and state?
4. **Zoom**: zoom to 200% and 400%. Content must remain readable and functional without horizontal scrolling at 400%.
5. **Color**: use a color blindness simulator (e.g., Chrome DevTools). Ensure information isn't conveyed by color alone.

## Constraints

### ✅ Do
- Use semantic HTML elements first: button, a, nav, main, header, footer, section, article, aside, fieldset, legend, label, h1-h6.
- Test every interactive component with keyboard-only navigation before considering it done.
- Check color contrast for all element states (default, hover, focus, active, disabled, selected).
- Provide text alternatives for all non-decorative images, icons, and media.
- Link error messages to form fields with aria-describedby.
- Use landmark elements (main, nav, header, footer) so screen reader users can jump between page sections.
- Include a skip-to-content link as the first focusable element on pages with complex headers.
- Set the lang attribute on the html element.


### ❌ Don&#x27;t
- DO NOT use ARIA attributes where native HTML semantics already communicate the role. A `<button>` does not need `role="button"`. A `<nav>` does not need `role="navigation"`. Adding redundant ARIA is a code smell that suggests the developer doesn't understand when ARIA is needed.
- DO NOT rely solely on color to communicate state or information. Red text for errors needs an icon or a label too. Green for success needs a checkmark or the word "Success."
- DO NOT trap keyboard focus inside a component unless it's a modal dialog (and even then, return focus to the trigger when the modal closes).
- DO NOT use `tabindex` values greater than 0. This overrides the natural DOM order and creates unpredictable tab sequences. Use `tabindex="0"` to make elements focusable in DOM order, or `tabindex="-1"` for programmatic focus only.
- DO NOT disable browser zoom with `user-scalable=no` or `maximum-scale=1`. Users with low vision depend on zoom.
- DO NOT hide focus rings with `outline: none` or `outline: 0` without providing a visible alternative. The default browser focus ring is better than no focus ring. If you style custom focus rings, ensure they have at least 3:1 contrast.
- DO NOT use `aria-label` on elements that already have visible text content. The aria-label overrides the visible text for screen readers, creating a disconnect between what sighted and non-sighted users perceive.
- DO NOT auto-play audio, video, or animation. Users with cognitive disabilities, vestibular disorders, or who are in screen-reader mode are disrupted by unexpected media.
- DO NOT use `title` attributes as the primary accessible name for interactive elements. Title tooltips are inconsistent across browsers and not accessible via keyboard.


## Output Format

1. Semantic HTML with ARIA attributes only where necessary.
2. Inline comments explaining accessibility decisions (e.g., `<!-- aria-live region for async validation messages -->`).
3. A brief testing note listing what to verify manually (keyboard flow, screen reader announcement, contrast).

## Dependencies

- `designer/designing-ui-system/SKILL.md` — color tokens must meet contrast requirements.
- `../../frontend/building-components/SKILL.md` — component implementation must follow these accessibility patterns (cross-agent contract).
