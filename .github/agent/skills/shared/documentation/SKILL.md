---
name: Writing Documentation
description: Create clear, maintainable documentation for APIs, codebases, and end-users. Treat documentation as code.
---

# Writing Documentation

## Goal
Ensure the system is understandable, usable, and maintainable by humans (developers and users) through high-quality, up-to-date documentation.

## When to Use
- Adding a new feature (update User Guide / README).
- Changing an API (update OpenAPI/Swagger).
- Onboarding new team members (update Setup Guide).
- Before "finishing" a task.

## Instructions

### 1. The README.md
The front page of the project.
- **Hook**: What does this do? (1 sentence).
- **Start**: How to run it? (3 commands max).
- **Stack**: What tech is used?

### 2. API Documentation
Auto-generate where possible, but curate the descriptions.
- **OpenAPI**: Use comments/decorators to generate Swagger specs.
- **Examples**: Provide real JSON request/response examples.
- **Errors**: Document all possible error codes, not just 200 OK.

### 3. Architecture Decision Records (ADRs)
Document *why* a decision was made.
- "We chose PostgreSQL over MongoDB because..."
- Keep them immutable.

### 4. Code Comments
- **Why, not What**: Don't explain syntax (`i++ // increment i`). Explain intent (`// retry 3 times to handle network blips`).
- **Public Interface**: Document public functions/classes with docstrings.

## Constraints

### ✅ Do
- **DO**: Keep docs close to code (README in repo, Swagger in code).
- **DO**: Update docs *in the same PR* as the code change.
- **DO**: Use "Mermaid.js" for diagrams in Markdown.

### ❌ Don't
- **DON'T**: Let docs drift from code (incorrect docs are worse than no docs).
- **DON'T**: Use jargon without definition.
- **DON'T**: Write wall-of-text paragraphs; use lists and headers.

## Output Format
- `README.md`
- `docs/*.md`
- Code comments / Docstrings.

## Dependencies
- `shared/git-workflow/SKILL.md`
