---
name: Generating Technical Spec
description: Break a system architecture into implementable work packages with clear tasks, dependencies, and integration contracts.
---

# Generating Technical Spec

## Goal

Transform a system architecture document into a detailed technical specification that defines every implementable task, assigns work to the appropriate agent, specifies integration contracts, and establishes a dependency graph so that work can proceed in parallel where possible.

## When to Use

- An architecture document exists and implementation is about to begin
- You need to coordinate work across multiple agents or team members
- A large feature requires decomposition into smaller, trackable units
- You need to estimate effort and identify the critical path for delivery

## Instructions

### 1. Review the Architecture Document

Read the architecture produced by the `designing-architecture` skill. Identify:
- Every component and its responsibility
- All API contracts and integration points
- The data model and storage decisions
- Authentication and authorization boundaries

### 2. Decompose into Work Packages

Break each component into atomic tasks. A good task:
- Can be completed in a single working session
- Has a clear definition of done
- Produces a testable artifact (code, config, migration, test suite)

Group tasks by component, then order them by dependency.

### 3. Assign Tasks to Agents

Map each task to the agent best suited to implement it based on domain:
- **Frontend Agent** -- UI components, client state, routing
- **Backend Agent** -- API endpoints, business logic, middleware
- **Database Agent** -- Schema design, migrations, seed data
- **DevOps Agent** -- CI/CD, infrastructure, deployment config
- **Testing Agent** -- Test plans, integration tests, e2e tests

### 4. Define Integration Points

For every boundary where two components interact, define:
- The contract (API schema, event format, shared type)
- Which task produces the contract and which tasks consume it
- How to verify the integration (contract tests, integration tests)

### 5. Set Dependencies and Estimate Difficulty

Build a dependency graph:
- Tasks that can run in parallel should have no dependency link
- Tasks that block other tasks must be completed first
- Estimate each task as Low, Medium, or High difficulty

**Example** -- turning a web app architecture into tasks:

| Task ID | Description                           | Agent    | Difficulty | Dependencies |
|---------|---------------------------------------|----------|------------|--------------|
| T-001   | Define database schema                | Database | Medium     | None         |
| T-002   | Create migration scripts              | Database | Low        | T-001        |
| T-003   | Implement user registration endpoint  | Backend  | Medium     | T-001        |
| T-004   | Implement login endpoint with JWT     | Backend  | Medium     | T-001        |
| T-005   | Add auth middleware                   | Backend  | Low        | T-004        |
| T-006   | Implement profile CRUD endpoints      | Backend  | Medium     | T-005        |
| T-007   | Build registration form component     | Frontend | Medium     | T-003        |
| T-008   | Build login form component            | Frontend | Medium     | T-004        |
| T-009   | Build profile page                    | Frontend | Medium     | T-006        |
| T-010   | Set up CI pipeline                    | DevOps   | Medium     | None         |
| T-011   | Write auth integration tests          | Testing  | Medium     | T-003, T-004 |
| T-012   | Write e2e test for registration flow  | Testing  | High       | T-007, T-008 |
| T-013   | Add rate limiting middleware          | Backend  | Low        | T-005        |
| T-014   | Seed database with test data          | Database | Low        | T-002        |
| T-015   | Configure production deployment       | DevOps   | High       | T-010        |

### 6. Identify the Critical Path

Trace the longest chain of dependent tasks from start to finish. This is the critical path -- any delay on these tasks delays the entire project.

### 7. Produce the Technical Spec

Compile everything into a document following `references/spec-template.md`. The spec should be the single source of truth for what gets built, by whom, and in what order.

## Constraints

### ✅ Do
- Make every task atomic and completable in a single session
- Define clear inputs and outputs for each task
- Set realistic dependencies -- do not over-serialize independent work
- Include integration tasks explicitly (they are often forgotten)
- Include testing tasks for every component and integration point
- Specify the contract format for each integration boundary
- Identify the critical path and flag it clearly


### ❌ Don&#x27;t
- Create tasks too large or vague to complete in one session
- Skip integration tasks between components
- Forget testing tasks (unit, integration, e2e)
- Assign all tasks to a single agent when work can be parallelized
- Create circular dependencies in the task graph
- Leave difficulty estimates out -- they are needed for planning
- Assume agents share implicit context; make everything explicit in the spec


## Output Format

A Markdown document following the structure defined in `references/spec-template.md`.

Key sections:
1. System Overview (architecture summary)
2. Component Specifications
3. API Contracts
4. Data Model
5. Task Breakdown (table with ID, description, agent, difficulty, dependencies)
6. Integration Points
7. Testing Strategy

## Dependencies

- `../designing-architecture/SKILL.md` -- provides the architecture document as input
- `../../shared/task-tracking/SKILL.md` -- for tracking task progress during implementation
- `references/spec-template.md` -- structural template for the output document
