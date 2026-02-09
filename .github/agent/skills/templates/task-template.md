# Task Template

Copy this template when creating new tasks in `tasks.md`.

---

```markdown
### TASK-NNN: Short description in imperative mood
- **Status**: Todo | In Progress | Done | Blocked
- **Difficulty**: Easy | Medium | Hard | Critical
- **Assigned Agent**: agent-manager | architect | frontend | backend | storage | auth | designer
- **Dependencies**: TASK-NNN or None
- **Created**: YYYY-MM-DD
- **Updated**: YYYY-MM-DD

#### Description
2-5 sentences explaining the work in detail. Include the business context and technical scope. Mention which parts of the codebase will be affected.

#### Acceptance Criteria
- [ ] Specific, testable criterion 1
- [ ] Specific, testable criterion 2
- [ ] Specific, testable criterion 3

#### Notes
Implementation notes, blockers, decisions, links to relevant specs or skills.
```

---

## Field Guidelines

### Status
- **Todo**: Not started, requirements are clear
- **In Progress**: Agent is actively working on this task
- **Done**: All acceptance criteria met, output reviewed
- **Blocked**: Cannot proceed — document the blocker in Notes

### Difficulty
- **Easy**: Single file change, well-defined scope, < 30 min
- **Medium**: Multiple files, some design decisions, 30 min - 2 hours
- **Hard**: Cross-agent coordination, architectural decisions, 2+ hours
- **Critical**: Blocking other work, security-sensitive, or production-impacting

### Task IDs
- Sequential integers: TASK-001, TASK-002, etc.
- Never reuse a task ID, even if the task is deleted
- Reference other tasks by ID in Dependencies and Notes

### Imperative Mood
Write task titles as commands:
- "Implement user registration endpoint" (correct)
- "User registration endpoint" (incorrect — not imperative)
- "Implemented user registration endpoint" (incorrect — past tense)
