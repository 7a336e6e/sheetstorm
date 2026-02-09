---
name: Reviewing Agent Output
description: Quality gates and output validation — verify that agent deliverables meet acceptance criteria, maintain cross-agent consistency, and are ready for integration.
---

# Reviewing Agent Output

## Goal

Ensure every task deliverable meets its acceptance criteria, is consistent with work from other agents, and passes integration checks before being marked as Done.

## When to Use

- An agent marks a task as `In Review` in `tasks.md`.
- A workflow wave completes and outputs need validation before the next wave begins.
- Final integration review after all tasks for a feature are complete.
- When a previously rejected task is resubmitted with fixes.

## Instructions

### 1. Gather Context

Before reviewing, collect everything you need:

- Read the task entry in `tasks.md` — especially the acceptance criteria and dependencies.
- Read the agent's output files (code, config, documentation).
- Read related tasks to understand cross-agent contracts (API shapes, data models, shared types).

### 2. Run the Review Checklist

Evaluate every deliverable against these four dimensions:

- **Completeness** — Walk through each acceptance criterion one by one. A single failing criterion means the task cannot be approved.
- **Correctness** — Check for off-by-one errors, null handling, edge cases. Verify business logic matches the requirement and error handling covers expected failure modes.
- **Consistency** — Naming conventions match project standards, code style follows established patterns, shared types are used (not redefined).
- **Test Coverage** — Unit tests exist for core logic, integration tests for cross-boundary interactions, and edge cases and error paths are tested.

### 3. Verify Cross-Agent Contracts

This is the most critical step. Check these integration points:

**Frontend / Backend:** The frontend calls the exact endpoints the backend implemented. Request and response shapes match. Error format is handled consistently on both sides.

**Backend / Storage:** Queries reference columns and tables that exist in the migration. ORM field types match the database schema. Indexes exist for fields used in WHERE clauses and JOINs.

**Auth integration:** Protected endpoints have the correct middleware guards. Frontend sends tokens in the expected format. Permission checks reference roles that exist in the auth system.

**Designer / Frontend:** Components use the design tokens defined by the designer. Responsive breakpoints match the layout spec. Interaction states (hover, focus, disabled) are implemented.

### 4. Deliver the Review Verdict

Every review results in one of three outcomes:

**Approve** — All acceptance criteria met, integration checks pass. Set status to `Done`.

```markdown
## Review: T3 — Build ProfilePage component
**Verdict:** Approved
**Notes:** All 4 acceptance criteria met. API contract matches backend. Responsive breakpoints match designer spec.
```

**Request Changes** — One or more issues need fixing. List every issue with specific, actionable feedback. Set status to `Changes Requested`.

```markdown
## Review: T3 — Build ProfilePage component
**Verdict:** Changes Requested
**Issues:**
1. AC #2: Component does not render error message on 404. Add fallback UI.
2. The `userName` prop should be `username` to match the API response shape.
3. No test for loading state. Add a test verifying the skeleton renders while fetching.
```

**Reject** — Output is fundamentally misaligned with the requirement or contract. Set status to `Rejected`.

```markdown
## Review: T3 — Build ProfilePage component
**Verdict:** Rejected
**Reason:** Component fetches from /api/profiles/:id but backend implements /api/users/:id. Data-fetching layer must match the API contract from T1.
```

### 5. Final Integration Review

After all tasks for a feature are individually approved, run one final check: verify the full user flow end-to-end, confirm no agent's changes broke another agent's work, and check that shared types and contracts are consistent across all files. Only then mark the feature as complete.

## Constraints

### ✅ Do
- Check every acceptance criterion individually — do not batch-approve.
- Verify integration points between agents before approving downstream tasks.
- Provide specific, actionable feedback when requesting changes.
- Test the output yourself when possible — do not rely solely on reading the code.
- Re-review after changes are applied — never auto-approve a resubmission.
- Record all review verdicts in tasks.md for traceability.


### ❌ Don&#x27;t
- Approve a task without checking every acceptance criterion.
- Skip integration verification between agents — contract mismatches are the most common source of bugs.
- Modify the agent's code directly — always send it back to the assigned agent with feedback.
- Approve a task that has no tests, unless the task explicitly does not require them.
- Batch-approve an entire wave without checking each task individually.
- Provide vague feedback like "needs improvement" — always specify what and why.


## Output Format

Each review produces a verdict block recorded in `tasks.md`:

```markdown
## Review: <Task ID> — <Task Title>
**Verdict:** Approved | Changes Requested | Rejected
**Checklist:**
  - Completeness: Pass/Fail
  - Correctness: Pass/Fail
  - Consistency: Pass/Fail
  - Test Coverage: Pass/Fail
**Issues:** (if any)
  1. <specific issue with actionable fix>
**Notes:** <any additional context>
```

## Dependencies

- `../../shared/code-review/SKILL.md` — for general code review conventions and feedback format.
- `../delegating-tasks/SKILL.md` — for reading acceptance criteria and task context.
