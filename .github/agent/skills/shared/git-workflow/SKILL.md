---
name: git-workflow
description: The git-workflow skill defines branching conventions, commit message formats, and pull request standards that all agents must follow for consistent version control.
---

# Git Workflow

## Goal
Ensure every code change is traceable, reviewable, and cleanly integrated through consistent branching, commit messages, and pull request practices.

## When to Use
- When creating a new branch for a task
- When committing code changes
- When opening or updating a pull request
- When merging completed work back to main

## Instructions

### Step 1: Create a Branch
Branch from an up-to-date `main`. Use the naming convention:

```
{agent}/{task-id}-short-description
```

Examples:
```bash
git checkout main && git pull origin main
git checkout -b backend/TASK-042-password-reset
git checkout -b frontend/TASK-051-login-form
git checkout -b infra/TASK-019-ci-pipeline
```

### Step 2: Make Atomic Commits
Each commit should represent one logical change. Use conventional commit prefixes with an optional scope in parentheses:

| Prefix     | Use For                              |
|------------|--------------------------------------|
| `feat:`    | New feature or capability            |
| `fix:`     | Bug fix                              |
| `refactor:`| Code restructuring, no behavior change|
| `test:`    | Adding or updating tests             |
| `docs:`    | Documentation changes                |
| `chore:`   | Build config, dependencies, tooling  |

Format: `prefix(scope): short imperative description`

```bash
git commit -m "feat(auth): implement password reset endpoint"
git commit -m "fix(api): handle null user in profile lookup"
git commit -m "test(auth): add reset token expiry edge cases"
git commit -m "refactor(db): extract query builder into utility"
```

Keep the subject line under 72 characters. Add a body separated by a blank line for complex changes:

```bash
git commit -m "fix(auth): prevent timing attack on token comparison

Use constant-time comparison for reset tokens to avoid
leaking token validity through response timing."
```

### Step 3: Push and Open a Pull Request
Pull the latest main before pushing to catch conflicts early:

```bash
git pull origin main --rebase
git push -u origin backend/TASK-042-password-reset
```

Open a PR with this structure in the description:

```markdown
## Summary
Brief description of what this PR does and why.
Closes TASK-042.

## Changes
- Added POST /api/auth/reset-password endpoint
- Added token validation middleware
- Added bcrypt hashing for new passwords

## Testing
- [ ] Unit tests pass locally
- [ ] Manual test with valid and expired tokens
- [ ] Verified 400 response for invalid tokens

## Checklist
- [ ] Code follows project style guidelines
- [ ] Tests cover happy path and edge cases
- [ ] No secrets or credentials in the diff
- [ ] Task status updated to In Review
```

### Step 4: Address Review Feedback
Push new commits for review feedback rather than force-pushing amended commits. This preserves review context. Squash on merge if the repository is configured for it.

## Constraints

### ✅ Do
- Branch from an up-to-date main for every new task
- Write atomic commits — one logical change per commit
- Pull and rebase before pushing to catch conflicts early
- Reference the task ID in the PR description
- Keep PRs under 500 lines of diff when possible


### ❌ Don&#x27;t
- Never commit directly to main — always use a feature branch
- Never force push to a shared branch that others are reviewing
- Never mix unrelated changes in a single commit or PR
- Never include generated files, build artifacts, or secrets in commits
- Never leave a PR description empty


## Output Format
Branches, commits, and PRs created in the project's git repository following the conventions above.

## Dependencies
- `../task-tracking/SKILL.md` — task IDs referenced in branch names and PR descriptions
