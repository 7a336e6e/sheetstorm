# Layout Patterns Reference

These are **pattern descriptions with constraints**, not templates to copy verbatim. Adapt each pattern to the specific content and context.

## Dashboard Layout

### Structure
- **Sidebar navigation** (fixed or collapsible): 14-18rem wide, contains primary nav links and user/org context.
- **Top header bar**: breadcrumbs, search, user menu. Thin (48-64px).
- **Content area**: CSS Grid for widget/card arrangement. Variable columns based on content density.

### Constraints
- Sidebar collapses to a hamburger menu below `lg` (1024px). On mobile, it becomes a slide-over or bottom sheet — not a top horizontal nav crammed with links.
- Dashboard cards should use a responsive grid (`auto-fill, minmax(280px, 1fr)`) so the number of columns adapts to available width.
- The most important metric or action goes top-left (in LTR layouts). Don't bury it in a grid of equal-weight cards.
- Avoid the "12 identical cards in a 4x3 grid" pattern. Real dashboards have a hierarchy: 1-2 large summary cards, then smaller detail cards.

### Common Mistakes
- Making every card the same size regardless of content importance.
- Sidebar that takes up 25%+ of the viewport on smaller laptops, leaving cramped content.
- Fixed sidebar that prevents content from reflowing on resize.

## Content / Article Page

### Structure
- **Main content column**: max-width 65ch-75ch (for readability). Centered or offset left with optional sidebar.
- **Table of contents sidebar**: appears at `xl` (1280px+). Sticky-positioned, scrolls independently. Below `xl`, use an inline collapsible TOC at the top of the article.
- **No footer clutter**: content pages should let the content breathe. Minimal footer.

### Constraints
- Body text line length must stay within 45-75 characters. This is the single most important layout constraint for readability.
- Headings, images, and code blocks can break out of the text column width for visual variety (wider than the text measure).
- Spacing between paragraphs: `--space-4` (16px). Between sections (h2): `--space-8` (48px). This creates clear section grouping.
- Images should be responsive (`max-width: 100%`) and have consistent aspect ratios or at least consistent horizontal alignment.

### Common Mistakes
- Full-width text with no max-width — causes 120+ character lines on desktop, unreadable.
- TOC sidebar that takes space on medium screens where it isn't needed.
- Equal spacing between all elements, destroying visual grouping.

## Form Page

### Structure
- **Narrow centered container**: max-width 32rem-40rem. Forms don't need wide layouts.
- **Logical field grouping**: related fields in fieldsets with legends. Visual grouping via spacing or subtle background.
- **Action buttons**: left-aligned (LTR), primary action first, secondary (cancel) second. Not centered, not right-aligned.

### Constraints
- Single-column forms are almost always better than multi-column. The only exception is closely related short fields (city + state + zip).
- Labels above inputs (not beside) for mobile compatibility and faster scanning.
- Error messages appear directly below the relevant field, not in a summary banner at the top (unless also shown inline).
- Form width should be proportional to expected input length. An email field can be wide; a zip code field should be narrow.

### Common Mistakes
- Using a full-width layout for a 5-field form — the fields stretch to absurd widths.
- Putting all error messages in a banner at the top with no inline indicators.
- Right-aligning or center-aligning the submit button.
- Equal-width columns for unequal-importance fields (e.g., first name and middle initial in the same-width columns).

## List / Detail (Master-Detail)

### Structure
- **Desktop** (`lg`+): side-by-side. List panel (25-35% width) on the left, detail panel (65-75%) on the right.
- **Mobile**: stacked. List view is the default; tapping an item navigates to a full-screen detail view with a back button.

### Constraints
- List panel: each item shows minimal info (title + 1-2 metadata fields). Don't cram full details into list items.
- Detail panel: full content with scrolling independent of the list.
- Selected state in the list must be visually obvious (background color, left border accent, not just bold text).
- On mobile, the transition between list and detail should feel like navigation, not a layout shift.

### Common Mistakes
- Showing the detail panel empty on first load with no guidance (use an empty state with a prompt to select an item).
- List items that are too tall, requiring excessive scrolling to browse.
- Not handling the mobile view at all — just shrinking the side-by-side layout until it's unusable.

## Empty States

### Structure
- Centered vertically and horizontally within the content area.
- **Illustration or icon**: optional, but if used, keep it simple and relevant (not a generic "empty box" clipart).
- **Message**: clear, specific to the context. "No projects yet" is better than "Nothing to see here."
- **Primary action**: one clear CTA button to resolve the empty state ("Create your first project").

### Constraints
- The message should tell the user what they can do, not just describe the emptiness.
- Don't use empty states as an excuse for decorative illustration overload. One small visual is enough.
- The CTA should be the same action available elsewhere in the UI (e.g., the same "New Project" button that's in the header). Don't introduce a special action only visible in the empty state.

## Anti-Patterns Across All Layouts

- **Identical padding on all sides**: content areas usually need more vertical padding than horizontal, or more top padding than bottom. Use asymmetric padding intentionally.
- **Orphaned headings**: a heading at the bottom of a visible area with its content scrolled below. Ensure headings stay with their first content element (use `break-after: avoid` or structural grouping).
- **Floating elements without alignment anchors**: a button or badge that doesn't align to any grid line, text baseline, or other element. Every element should have a clear alignment relationship.
- **Symmetric layouts for asymmetric content**: forcing two columns of equal width when one has a paragraph and the other has a single stat. Let content dictate proportions.
- **Decorative symmetry**: mirroring layout elements purely for visual balance when the content doesn't support it. Asymmetry with purpose looks more intentional than forced symmetry.
- **The "AI section parade"**: a page that's just a vertical stack of full-width sections with alternating background colors (white, gray, white, gray). This pattern signals automated generation. Vary section structure, column counts, and visual rhythm instead.
