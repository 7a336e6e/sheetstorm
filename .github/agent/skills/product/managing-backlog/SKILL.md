---
name: Managing Backlog
description: Refine, prioritize, and clean the product backlog to ensure the team is always working on the highest-value tasks.
---

# Managing Backlog

## Goal
Maintain a healthy, prioritized list of work items that are ready for development ("Definition of Ready"), preventing bottlenecks and "garbage in, garbage out."

## When to Use
- Before sprint planning.
- When the backlog grows too large (> 50 items).
- When stakeholders add new requests.

## Instructions

### 1. Prioritization Frameworks
Don't just use "High/Medium/Low". Use a model:
- **RICE**: Reach * Impact * Confidence / Effort.
- **MoSCoW**: Must have, Should have, Could have, Won't have.
- **Cost of Delay**: "If this waits a month, how much do we lose?"

### 2. Refinement (Grooming)
Make tasks actionable.
- **Clarify**: Does everyone understand the "Why"?
- **Estimate**: Is it a 1-day task or a 2-week task?
- **Split**: If it's big, break it down.

### 3. Definition of Ready (DoR)
A task can only move to "Todo" if:
- It has a clear user story.
- It has acceptance criteria.
- It has dependencies identified.
- It has an estimate.

### 4. Backlog Hygiene
- **Delete**: If it's been in the backlog for 6 months and nobody cares, delete it.
- **Archive**: Don't let the "Icebox" become a graveyard.

## Constraints

### ✅ Do
- **DO**: Re-prioritize regularly. Priorities change.
- **DO**: Say "No". A backlog is not a wishlist; it's a plan.
- **DO**: Link backlog items to strategic goals (OKRs).

### ❌ Don't
- **DON'T**: Let stakeholders push items to "In Progress" directly.
- **DON'T**: Estimate in hours. Use points or T-shirt sizes (S, M, L) for relative complexity.
- **DON'T**: Allow "Zombie tickets" (tasks with no clear owner or value) to survive.

## Output Format
- Updates to `tasks.md` (priority ordering, new tags).
- `backlog_refinement_report.md`.

## Dependencies
- `product/defining-user-stories/SKILL.md`
- `planner/project-planning/SKILL.md`
