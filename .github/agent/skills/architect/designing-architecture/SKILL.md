---
name: Designing Architecture
description: Turn structured requirements into a system architecture with defined components, boundaries, API contracts, and data storage strategy.
---

# Designing Architecture

## Goal

Transform a structured requirements document into a system architecture that defines components, their boundaries, communication patterns, data storage, and key technology choices -- all documented with rationale.

## When to Use

- Requirements have been analyzed and a requirements document exists
- You need to decide on system structure before implementation begins
- A significant new feature requires architectural changes to an existing system
- You need to evaluate trade-offs between different architectural approaches

## Instructions

### 1. Review Requirements

Read the requirements document produced by the `analyzing-requirements` skill. Pay close attention to:
- Scale and performance targets (non-functional requirements)
- Number of distinct user roles and their permission models
- Data entities and their relationships
- Workflows that cross domain boundaries

### 2. Select an Architecture Pattern

Consult `references/architecture-patterns.md` and choose a pattern based on the decision matrix. Start simple -- a monolith or modular monolith is the right default for most projects.

### 3. Define System Components

Break the system into components. Each component should:
- Own a single domain or bounded context
- Have a clear public interface (API, event contract, or function signature)
- Be independently testable

**Example** -- a typical web application:

```
[Browser] --> [React Frontend (SPA)]
                  |
                  v
            [Flask API Server]
                  |
          +-------+-------+
          |               |
          v               v
   [PostgreSQL DB]   [Redis Cache]
```

Components:
1. **React Frontend**: Renders UI, manages client state, calls API
2. **Flask API Server**: Handles HTTP requests, enforces business logic, manages auth
3. **PostgreSQL Database**: Persists entities and relationships
4. **Redis Cache**: Stores sessions and frequently accessed data

### 4. Design API Contracts

Define the API surface between frontend and backend (and between backend services if applicable). For each endpoint, specify:
- Path, method, and description
- Request shape (body, params, query)
- Response shape (success and error)
- Authentication requirements

Use the OpenAPI (Swagger) format as the canonical contract when possible.

### 5. Choose Data Storage Strategy

Based on the data entities from the requirements document:
- Select a primary database (relational vs document vs key-value)
- Define indexing strategy for common query patterns
- Plan for migrations and schema evolution
- Decide on caching layers if performance requirements demand them

### 6. Plan Authentication and Authorization

- Choose an auth mechanism (session-based, JWT, OAuth2)
- Define the permission model (RBAC, ABAC, or simple role checks)
- Map user roles from requirements to permission sets
- Identify which endpoints or components need which level of access

### 7. Document Decisions with ADRs

For every significant choice, write a brief Architecture Decision Record:
- **Context**: What is the situation or constraint?
- **Decision**: What did you choose?
- **Consequences**: What are the trade-offs?

### 8. Produce the Architecture Document

Compile the architecture into a clear document with diagrams (described in text or ASCII), component descriptions, API contracts, and ADRs.

## Constraints

### ✅ Do
- Start with the simplest architecture that satisfies requirements
- Define clear boundaries between components
- Document trade-offs for every significant decision
- Specify API contracts before implementation starts
- Consider failure modes and error handling at the architecture level
- Plan for observability (logging, monitoring, health checks)
- Revisit the architecture if requirements change significantly


### ❌ Don&#x27;t
- Over-engineer the initial architecture for hypothetical future scale
- Choose microservices unless the team size and complexity clearly demand it
- Skip API contract definition and let frontend/backend evolve independently
- Introduce distributed systems patterns (event sourcing, CQRS) without strong justification
- Ignore security architecture and defer it to implementation
- Make technology choices based on novelty rather than fitness for the problem


## Output Format

A Markdown document containing:

1. **Architecture Overview** -- 1-2 paragraph summary with an ASCII component diagram
2. **Component Descriptions** -- table or list with responsibility, tech stack, interfaces
3. **API Contracts** -- endpoint definitions with request/response shapes
4. **Data Storage** -- database choice, schema overview, caching strategy
5. **Auth Architecture** -- mechanism, permission model, token flow
6. **Architecture Decision Records** -- one ADR per significant choice
7. **Open Risks** -- known risks and mitigation strategies

## Dependencies

- `../analyzing-requirements/SKILL.md` -- provides the requirements document as input
- `references/architecture-patterns.md` -- reference for choosing the right pattern
