# Skill Template

Copy this template when creating new SKILL.md files.

---

```markdown
---
name: skill-name-in-kebab-case
description: Third-person description of what this skill does and when an agent should use it.
---

# Skill Title (Title Case)

## Goal
One sentence describing what success looks like when this skill is applied correctly.

## When to Use
- Bullet list of specific triggers, contexts, or conditions
- When [specific situation] requires [specific action]
- After [prerequisite] is complete and [condition] is met

## Instructions

### Step 1: Title
Explanation of what to do and why.

```language
// Code example demonstrating the step
```

### Step 2: Title
Explanation of what to do and why.

```language
// Code example demonstrating the step
```

### Step 3: Title
Explanation of what to do and why.

## Constraints

### ✅ Do
- **DO**: Explicit best practice 1
- **DO**: Explicit best practice 2
- **DO**: Explicit best practice 3

### ❌ Don't
- **DON'T**: Explicit anti-pattern 1 — why it's bad
- **DON'T**: Explicit anti-pattern 2 — why it's bad
- **DON'T**: Explicit anti-pattern 3 — why it's bad

## Output Format
Describe what the agent should produce: file(s), structure, format, naming.

## Dependencies
- `relative/path/to/prerequisite/SKILL.md` — why it's needed
- `relative/path/to/another/SKILL.md` — why it's needed
```

---

## Guidelines

- **Target 80-140 lines** per SKILL.md — be concise but complete
- **Max 150 lines** — move reference material to `references/` subdirectory
- **Use real code examples** — not pseudocode, not placeholders
- **3-6 constraints** in each section
- **Link dependencies by relative path** from the skill file's location
- **Gerund naming** for the parent directory (e.g., `building-components/SKILL.md`)