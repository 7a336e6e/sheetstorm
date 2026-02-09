---
name: Delegating Tasks
description: Decompose requirements into discrete tasks and delegate them to the most appropriate specialist agents based on their capabilities.
---

# Delegating Tasks

## Goal

Break down user requirements into well-scoped tasks, match each task to the best-fit specialist agent, and write those tasks to `tasks.md` with clear acceptance criteria so every agent knows exactly what to deliver.

## When to Use

- A new feature request or user story arrives that requires work from multiple agents.
- A bug report needs investigation and fixes across several system layers.
- A refactoring effort must be coordinated across the codebase.
- Any time work needs to be assigned to one or more specialist agents.

## Instructions

### 1. Understand the Team

Read `AGENTS.md` at the project root and the reference file at `agent-manager/delegating-tasks/references/agent-capabilities.md` to understand which agents are available and what each one can do.

### 2. Clarify Ambiguity First

Before decomposing anything, check whether the requirement is clear enough to act on. If not, ask the user targeted clarifying questions. Never guess at intent when the scope is ambiguous.

Example clarifying questions:

- "Should user authentication use OAuth or email/password?"
- "Is the data model additive, or does it replace the existing schema?"
- "Which pages need this component: just the dashboard, or site-wide?"

### 3. Decompose the Requirement

Break the requirement into 3-5 discrete tasks. Each task must be independently completable by a single agent.

Example — decomposing a feature request for "Add user profile page":

```
Task 1 (Architect):    Define the profile page data model, API contract, and component hierarchy.
Task 2 (Backend):      Implement GET /api/users/:id and PATCH /api/users/:id endpoints per the API contract.
Task 3 (Frontend):     Build the ProfilePage component consuming the API contract from Task 1.
Task 4 (Storage):      Add the user_profiles table migration and seed data.
Task 5 (Designer):     Create the profile page layout, responsive breakpoints, and design tokens.
```

### 4. Match Tasks to Agents

Use `agent-capabilities.md` to select the right agent for each task. Consider:

- The agent's listed skills and technologies.
- The agent's key strengths.
- Whether the task falls squarely within one agent's domain.

### 5. Write Tasks to tasks.md

For every task, record the following fields in `tasks.md`:

```markdown
## Task: <short title>
- **Assigned to:** <agent name>
- **Status:** Todo
- **Depends on:** <task ID or "none">
- **Acceptance criteria:**
  1. <specific, testable criterion>
  2. <specific, testable criterion>
  3. <specific, testable criterion>
- **Notes:** <any additional context the agent needs>
```

### 6. Set Dependencies Between Tasks

Explicitly declare which tasks block other tasks. For example, the Architect's data model task should be marked as a dependency for the Backend, Frontend, and Storage tasks.

### 7. Hand Off

Once all tasks are written to `tasks.md`, notify the orchestration workflow so execution can begin.

## Constraints

### ✅ Do
- Assign exactly one agent per task.
- Include at least two acceptance criteria per task.
- Set explicit dependency links between tasks.
- Scope each task so it can be completed independently once dependencies are met.
- Ask clarifying questions when requirements are ambiguous.
- Reference the API contract or data model by name so agents share a single source of truth.


### ❌ Don&#x27;t
- Assign tasks outside an agent's documented skill set.
- Create tasks without clearly defined scope and acceptance criteria.
- Assign multiple agents to a single task.
- Decompose into more than 7 tasks for a single feature — break the feature into phases instead.
- Guess at requirements when you can ask the user.
- Skip reading agent-capabilities.md before assigning work.


## Output Format

The output is a set of task entries written to `tasks.md`. Each entry follows the template in the instructions above. After writing, produce a short summary listing each task title, the assigned agent, and any dependency relationships.

Example summary:

```
Delegated 4 tasks:
  1. Define profile data model      -> Architect       (no dependencies)
  2. Implement profile API           -> Backend         (depends on 1)
  3. Build ProfilePage component     -> Frontend        (depends on 1)
  4. Add user_profiles migration     -> Storage         (depends on 1)
```

## Dependencies

- `../../shared/task-tracking/SKILL.md` — for the canonical task format and status lifecycle.
- `references/agent-capabilities.md` — the master reference of agent skills used for task-to-agent matching.
