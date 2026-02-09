---
name: task-tracking
description: Manage the `tasks.md` ledger with strict locking and collision avoidance protocols to allow multiple agents to work in parallel safely.
---

# Task Tracking

## Goal
Maintain a conflict-free, "Single Source of Truth" ledger (`tasks.md`). Prevent multiple agents from working on the same task or stomping on each other's updates.

## When to Use
- **STARTING**: Before writing a single line of code.
- **UPDATING**: When you hit a blocker or finish a sub-step.
- **COMPLETING**: When acceptance criteria are met.

## Instructions

### 1. Collision Avoidance (The "Check-Lock-Act" Loop)
1.  **Check**: Read `tasks.md`. Look for `Assigned Agent`.
    *   If `Assigned Agent` is `Unassigned` or `null`: You may take it.
    *   If `Assigned Agent` is SOMEONE ELSE: **STOP**. Do not touch it.
    *   If `Assigned Agent` is YOU: Proceed.
2.  **Lock**: Immediately update the task to `Status: In Progress` and `Assigned Agent: <your-agent-name>`.
    *   *Critical*: Write this change to disk BEFORE doing the actual work. This signals to other agents "I am here."
3.  **Act**: Perform the work.

### 2. Task Structure (Aerospace Standard)
Every task must strictly follow the format.

```markdown
### TASK-042: Implement password reset endpoint
- **Status**: In Progress  <-- The "Lock"
- **Difficulty**: Medium
- **Assigned Agent**: Backend Engineer <-- The "Owner"
- **Dependencies**: TASK-038
- **Created**: 2026-02-05
- **Updated**: 2026-02-06 <-- MUST be today

#### Description
Build the POST /api/auth/reset-password endpoint.

#### Acceptance Criteria
- [x] Endpoint accepts token + new password
- [ ] Invalid/expired tokens return 400
```

### 3. Creating Tasks (Decomposition)
- **Granularity**: A task should take 10-60 minutes. If it takes longer, break it down.
- **Linking**: If Task B needs Task A, list `TASK-XXX` in "Dependencies".
- **No Duplicates**: Grep for keywords before creating.

### 4. Status Transitions
- `Todo` -> `In Progress`: **The Lock**.
- `In Progress` -> `Blocked`: If waiting on another agent/task. **Explain WHY in Notes.**
- `In Progress` -> `In Review`: Code is written, tests pass.
- `In Review` -> `Done`: Code is merged.

## Constraints

### ✅ Do
- **ATOMIC UPDATES**: Update `tasks.md` in a separate tool call from your code changes if possible, or at least be very careful not to hallucinate the file content.
- **TIMESTAMP**: You MUST update the `Updated: YYYY-MM-DD` field every time you touch a task.
- **RESPECT LOCKS**: Never edit a task assigned to another agent unless you are the `Agent Manager`.
- **SELF-ASSIGN**: Never work on a task labeled `Status: Todo` without first changing it to `In Progress` and assigning yourself.


### ❌ Don&#x27;t
- DO NOT "infer" you have the task. Claim it explicitly.
- DO NOT delete tasks. Mark them as `Status: Cancelled` instead.
- DO NOT leave `Assigned Agent` empty for `In Progress` tasks.


## Output Format
- Updates to `tasks.md`.

## Dependencies
- `templates/task-template.md`
