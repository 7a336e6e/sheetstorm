---
name: Orchestrating Workflow
description: Manage sequential and parallel execution across specialist agents, maximizing throughput while respecting task dependencies.
---

# Orchestrating Workflow

## Goal

Determine the correct execution order for delegated tasks, maximize parallelism where dependencies allow, monitor progress, and handle blocked or failing tasks so the overall workflow completes efficiently.

## When to Use

- After tasks have been delegated via `agent-manager/delegating-tasks/SKILL.md` and are ready for execution.
- When a running workflow needs re-evaluation because a task is blocked, failed, or completed early.
- When a new batch of tasks is added mid-workflow and must be merged into the current execution plan.

## Instructions

### 1. Build the Dependency Graph

Read `tasks.md` and identify every dependency relationship. Construct a directed acyclic graph (DAG) where each node is a task and each edge represents a "must complete before" relationship.

Example graph for a "user profile" feature:

```
Architect: Define data model (T1)
    +--> Backend: Implement API (T2)
    +--> Frontend: Build ProfilePage (T3)
    +--> Storage: Add migration (T4)
              +--> Auth: Add profile permissions (T5)
                        +--> Designer: Final polish (T6)
```

### 2. Identify Parallelizable Work

Tasks that share the same dependency but have no dependency on each other can run in parallel. Above, T2, T3, and T4 can all start as soon as T1 is done. Group tasks into execution waves where each wave contains all tasks whose dependencies are satisfied.

### 3. Workflow Patterns

**Sequential Pipeline** -- tasks form a straight line: `T1 -> T2 -> T3 -> T4`

**Parallel Fan-Out** -- one task unlocks several independent tasks that run simultaneously:

```
T1 --> (T2 || T3 || T4)
```

**Fan-In Aggregation** -- several tasks must all complete before a downstream task begins:

```
(T2, T3, T4) --> T5
```

**Combined (most common)** -- a mix of the above: `T1 --> (T2 || T3 || T4) --> T5 --> T6`

### 4. Execute in Waves

Walk the DAG in topological order. For each wave:

1. Verify all dependencies for the wave's tasks are marked `Done` in `tasks.md`.
2. Start all tasks in the wave. Update each task's status to `In Progress`.
3. Wait for all tasks in the wave to complete before moving to the next wave.

Example execution plan:

```
Wave 1: Architect — Define data model
Wave 2: Backend — Implement API  |  Frontend — Build page  |  Storage — Add migration
Wave 3: Auth — Add profile permissions
Wave 4: Designer — Final polish
```

### 5. Monitor Progress

Continuously check `tasks.md` for status changes. Track which tasks are `In Progress`, which have moved to `Done` or `Blocked`, and whether any wave is stalled.

### 6. Handle Blocked Tasks

When a task is marked `Blocked`:

1. **Identify the blocker.** Read the task's notes for the reason.
2. **Attempt to unblock.** Check whether the blocker can be fast-tracked or an alternative approach exists.
3. **Reassign if needed.** If the assigned agent cannot proceed, consider whether a different agent can resolve the blocker.
4. **Escalate.** If no agent can resolve it, surface it to the user with context and options.

Never leave a blocked task unaddressed for more than one wave cycle.

### 7. Complete the Workflow

Once all tasks are `Done`, trigger the review process via `agent-manager/reviewing-agent-output/SKILL.md` to validate the combined output before marking the feature as complete.

## Constraints

### ✅ Do
- Maximize parallelism — run independent tasks simultaneously whenever possible.
- Verify all dependencies are satisfied before starting any task.
- Update task statuses in tasks.md at every transition (Todo -> In Progress -> Done/Blocked).
- Keep execution waves small and focused — ideally 2-3 tasks per wave.
- Re-evaluate the execution plan when a task completes or becomes blocked.
- Document the execution plan before starting.


### ❌ Don&#x27;t
- Start a task before all of its dependencies are marked Done.
- Run more than 3 agents in parallel — coordination overhead grows exponentially.
- Ignore blocked tasks — every block must be addressed before the next wave begins.
- Skip the dependency check — even if you "know" a task is ready, verify in tasks.md.
- Reorder the DAG without re-evaluating downstream impacts.
- Assume completion — always confirm status in tasks.md rather than assuming a task finished.


## Output Format

Produce an execution plan before starting and a status summary after each wave.

```
Execution Plan:
  Wave 1: T1 (Architect)
  Wave 2: T2 (Backend) | T3 (Frontend) | T4 (Storage)
  Wave 3: T5 (Auth)
  Wave 4: T6 (Designer)

Wave 2 complete:
  - T2 (Backend): Done
  - T3 (Frontend): Done
  - T4 (Storage): Blocked — missing seed data format, escalating
Next: Resolving T4 block before starting Wave 3.
```

## Dependencies

- `../../shared/task-tracking/SKILL.md` — for reading and updating task statuses.
- `../delegating-tasks/SKILL.md` — tasks must be delegated before they can be orchestrated.
