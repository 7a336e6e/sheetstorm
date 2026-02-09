---
name: code-review
description: The code-review skill defines review standards, checklists, and comment conventions that agents follow when reviewing pull requests to maintain code quality and knowledge sharing.
---

# Code Review

## Goal
Catch defects, share knowledge, and maintain code quality through structured, timely reviews that focus on correctness, security, and maintainability.

## When to Use
- When a pull request is assigned to you for review
- When you open a PR and want to self-review before requesting others
- When reviewing your own code before marking a task as In Review

## Instructions

### Step 1: Read the PR Description and Diff
Start by understanding the intent. Read the PR summary and linked task before looking at code. Then review the diff file by file, starting with tests to understand expected behavior.

### Step 2: Walk Through the Checklist
Evaluate every PR against these categories:

**Correctness**
- Does the code do what the task description requires?
- Are edge cases handled (null values, empty lists, boundary conditions)?
- Do error paths return meaningful messages?

**Security**
- Is user input validated and sanitized?
- Are secrets kept out of the codebase and logs?
- Are authorization checks in place for protected resources?
- Is SQL parameterized (no string concatenation for queries)?

**Performance**
- Are there N+1 query patterns or unnecessary loops?
- Are large datasets paginated?
- Are expensive operations cached where appropriate?

**Readability**
- Are names descriptive and consistent with project conventions?
- Is complex logic commented or broken into helper functions?
- Are magic numbers replaced with named constants?

**Tests**
- Do tests cover the happy path and at least one failure case?
- Are test names descriptive of the scenario being tested?
- Do tests run independently without shared mutable state?

### Step 3: Run the Code Locally
For non-trivial changes, check out the branch and run the test suite. Verify at least one happy-path scenario manually if the change affects user-facing behavior.

```bash
git fetch origin
git checkout backend/TASK-042-password-reset
npm test        # or pytest, cargo test, etc.
```

### Step 4: Leave Structured Comments
Prefix every review comment with a category tag so the author can prioritize:

| Prefix       | Meaning                                          |
|--------------|--------------------------------------------------|
| `blocker:`   | Must fix before merge — correctness or security issue |
| `suggestion:`| Recommended improvement, open to discussion       |
| `question:`  | Clarification needed to complete the review       |
| `nit:`       | Minor style or preference — optional to address   |

Examples:
```
blocker: This query concatenates user input directly into SQL.
Use parameterized queries to prevent injection.

suggestion: Consider extracting this validation into a shared
utility since the same pattern appears in three endpoints.

question: Is there a reason we're not using the existing
TokenService here? It handles expiry checks already.

nit: Trailing whitespace on line 47.
```

### Step 5: Focus Areas by Change Type
Prioritize your review based on what kind of change the PR introduces:

| Change Type   | Focus On                                          |
|---------------|---------------------------------------------------|
| API changes   | Request validation, response shape, status codes, docs |
| DB changes    | Migrations reversibility, index coverage, data integrity |
| Auth changes  | Token handling, permission checks, session management |
| UI changes    | Accessibility, responsive behavior, loading states |
| Dependencies  | License compatibility, known vulnerabilities, bundle size |

### Step 6: Approve or Request Changes
- **Approve** if there are no blockers and only nits/suggestions remain
- **Request Changes** if any blocker comment exists
- Leave a summary comment with your overall assessment

## Constraints

### ✅ Do
- Review PRs within 24 hours of being assigned
- Explain the "why" behind every blocker and suggestion
- Test the happy path and at least one edge case locally
- Acknowledge good patterns — reviews are for learning too
- Keep review scope limited to what the PR intends to change


### ❌ Don&#x27;t
- Never rubber-stamp a review — read every changed line
- Never nitpick style issues that a linter or formatter should catch
- Never review more than 500 lines of diff in a single session without a break
- Never leave a review with only vague comments like "looks good" or "fix this"
- Never block a PR over personal preference — cite a standard or explain the risk


## Output Format
Review comments posted on the pull request using the category-prefixed format. A final summary comment with the approval decision and any outstanding items.

## Dependencies
- `../git-workflow/SKILL.md` — PR structure and branch conventions referenced during review
