---
name: Defining User Stories
description: Translate high-level requirements into specific, value-focused user stories with acceptance criteria.
---

# Defining User Stories

## Goal
Capture *what* needs to be built from the user's perspective, ensuring every feature delivers specific value.

## When to Use
- After `planner/project-planning`.
- Before `architect/analyzing-requirements`.
- When the "Why" of a feature is unclear.

## Instructions

### 1. The Standard Format
Use the "Connextra" template:
> **As a** \<role>,
> **I want to** \<action>,
> **So that** \<value/benefit>.

### 2. INVEST Criteria
Ensure stories are:
- **I**ndependent
- **N**egotiable
- **V**aluable
- **E**stimable
- **S**mall
- **T**estable

### 3. Acceptance Criteria (Gherkin-ish)
Define "Done" clearly.
- "Verify that the user can see their profile picture."
- "Verify that entering an invalid email shows an error."

### 4. Splitting Stories
If a story is too big (Epic), split it.
- **Workflow Steps**: Create Account -> Verify Email -> Set Password.
- **Data Variations**: Standard User vs Admin User.
- **Interface**: Web vs Mobile.

## Constraints

### ✅ Do
- **DO**: Focus on the *user benefit*, not the technical implementation.
- **DO**: Write acceptance criteria before writing code.
- **DO**: Keep stories small enough to complete in 1-2 days.

### ❌ Don't
- **DON'T**: Write "As a developer, I want to migrate the database..." (That's a chore, not a story).
- **DON'T**: Include technical jargon in the story title ("Implement GET /api/users").
- **DON'T**: Leave acceptance criteria ambiguous ("Make it fast").

## Output Format
- Updates to `tasks.md` (Stories become tasks).
- `requirements/user_stories.md` (optional).

## Dependencies
- `planner/project-planning/SKILL.md`
