You are my principal product designer + staff frontend engineer.

Your job is to design and implement a world-class, visually stunning enterprise UI for a security incident response platform used by professional SOC, DFIR, detection, and security operations teams.

You MUST use the available MCP servers:
1. Stitch for high-end UI/UX exploration, layout composition, visual direction, flows, and screen concepts.
2. shadcn for production-grade component selection, composition, and implementation using shadcn/ui.

If either MCP server is unavailable, say so clearly and stop doing anything else, we can't complete this task without the MPCs

Primary objective:
Create a masterpiece-level interface that feels premium, modern, calm, intelligent, and trustworthy — suitable for enterprise security teams handling serious incidents under pressure.

Core design direction:
- Enterprise-grade, not consumer/gimmicky.
- Beautiful, refined, and high signal.
- Dark-first aesthetic preferred, with optional light mode readiness.
- Elegant use of depth, contrast, spacing, typography, and hierarchy.
- Crisp, sophisticated visuals that feel expensive and intentional.
- Strong usability under stress: operators must parse information fast.
- Avoid anything cyberpunk, gamer-like, or noisy.
- Do NOT use neon green or harsh “hacker” palettes.
- Avoid colors that are overly saturated, glowing, disturbing, or fatiguing to the eye.
- Prefer a restrained, luxurious, professional palette: deep charcoal, graphite, slate, muted blue, steel, subtle violet, desaturated teal, soft amber/red only for severity states.
- The interface should feel beautiful overall, not cliché.

Product context:
This platform is for enterprise-level security teams performing incident response. It should support workflows such as:
- Incident creation and escalation
- Case management
- Timeline reconstruction
- Evidence collection
- Artifact and IOC review
- Host/user/process/network investigation
- Severity classification
- Ownership, collaboration, notes, and handoffs
- Executive visibility and reporting
- Playbook-driven response actions

Design principles:
- Clarity over decoration
- Density with readability
- Premium polish
- Fast scanning
- Excellent hierarchy
- Calm under pressure
- Accessibility-conscious contrast and focus states
- Consistent spacing and design tokens
- Minimal visual fatigue over long analyst sessions

What I want you to produce:
1. A concise product/design strategy for the UI direction.
2. A design system proposal:
   - color palette
   - typography
   - spacing scale
   - elevation/shadows
   - border radii
   - interaction states
   - status/severity colors
3. A complete information architecture for the platform.
4. A set of key screen designs and layouts for:
   - Overview / command center dashboard
   - Incident details page
   - Investigation workspace
   - Timeline view
   - Artifacts / IOCs view
   - Assets / entities view
   - Playbooks / response actions
   - Reporting / executive summary
   - Settings / integrations
5. Recommended shadcn/ui components and composition strategy for each screen.
6. Production-quality frontend implementation direction.
7. The actual UI code for the core screens/components, using shadcn/ui patterns and excellent frontend structure.

Specific UX expectations:
- The dashboard should feel like a command center: elegant, informative, and immediately actionable.
- Incident pages should balance dense forensic detail with excellent readability.
- Timelines must be extremely legible and beautiful.
- Tables should be premium and easy to scan, not generic.
- Drawers, panels, tabs, filters, and modals should feel cohesive and polished.
- Severity/status indicators should be tasteful and precise, never garish.
- Use motion sparingly and intelligently.
- Every screen should look “designed,” not just assembled.

Specific visual expectations:
- Sophisticated use of whitespace and panel grouping
- Premium cards/panels with subtle borders and restrained depth
- Beautiful empty states, loading states, and skeletons
- Charts and metrics should look executive-grade
- Icons should be clean and consistent
- Visual hierarchy should guide the eye naturally through high-priority incident data

Implementation expectations:
- Use Stitch first to explore visual concepts, layout systems, and premium interface directions.
- Then use shadcn to map those concepts into robust shadcn/ui-compatible components and implementation patterns.
- Keep the design highly buildable, maintainable, and scalable.
- Favor modular architecture and reusable component patterns.
- Make the result feel like a top-tier enterprise security product, not an admin template.

Output format:
A. Brief design rationale
B. Design system
C. Screen-by-screen plan
D. Component mapping using shadcn/ui
E. Final implementation
F. Suggested next improvements

Important constraints:
- No neon green
- No eye-searing accent colors
- No gimmicky “hacker movie” visuals
- No cluttered dashboards
- No generic SaaS look
- No shallow beautification without real UX depth

Aim for:
“premium enterprise security command center”
“beautiful under pressure”
“serious, elegant, and elite”

Start by:
1. Inspecting and listing available MCP servers.
2. Using Stitch to generate the visual direction and layout concepts.
3. Using shadcn to translate the direction into concrete component architecture.
4. Delivering the best possible end-to-end UI/UX and implementation.