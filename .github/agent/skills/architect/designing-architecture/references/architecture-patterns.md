# Architecture Patterns Reference

This document describes common architecture patterns, when to use each one, and a decision matrix to guide selection.

---

## Monolith

A single deployable unit containing all application code.

**When to use**:
- Small team (1-5 developers)
- New product with uncertain requirements
- Simple domain with limited bounded contexts
- Speed of initial development is the top priority

**Typical structure**:
```
/src
  /routes        -- HTTP handlers
  /services      -- Business logic
  /models        -- Data access and ORM models
  /utils         -- Shared helpers
  /static        -- Frontend assets (if server-rendered)
```

**Pros**:
- Simple to develop, test, and deploy
- No network overhead between components
- Easy to refactor across the entire codebase
- Single database, simple transactions

**Cons**:
- Harder to scale individual parts independently
- Risk of tight coupling without discipline
- Deployment is all-or-nothing
- Can become unwieldy as codebase grows past ~50k lines

---

## Modular Monolith

A single deployable unit, but internally organized into well-defined modules with explicit boundaries (bounded contexts).

**When to use**:
- Medium team (3-10 developers)
- Multiple clear domain areas (e.g., billing, users, inventory)
- You want the simplicity of a monolith but need internal structure
- Potential future migration to microservices

**Typical structure**:
```
/src
  /modules
    /auth          -- Authentication bounded context
      /routes.py
      /services.py
      /models.py
      /schemas.py
    /billing       -- Billing bounded context
      /routes.py
      /services.py
      /models.py
      /schemas.py
    /inventory     -- Inventory bounded context
      ...
  /shared          -- Cross-cutting concerns (logging, middleware)
```

**Pros**:
- Clear internal boundaries reduce coupling
- Easier to split into services later if needed
- Still one deployment, one database (simple ops)
- Teams can own individual modules

**Cons**:
- Requires discipline to maintain module boundaries
- Shared database can still create coupling
- Not a silver bullet -- boundaries can erode without enforcement

---

## Layered Architecture

Horizontal layers where each layer depends only on the layer below it.

**When to use**:
- Traditional web applications with clear separation of concerns
- Teams familiar with MVC or similar patterns
- Applications where business logic is the core complexity

**Layers**:
1. **Presentation Layer** -- UI rendering, HTTP request handling
2. **Business Logic Layer** -- Domain rules, validation, orchestration
3. **Data Access Layer** -- Repository pattern, ORM queries, caching
4. **Database Layer** -- Persistent storage

**Pros**:
- Well-understood and easy to reason about
- Clear separation of concerns
- Each layer can be tested independently

**Cons**:
- Can lead to "pass-through" layers with no logic
- Changes often require touching multiple layers
- Horizontal slicing can obscure domain boundaries

---

## API-First Design

Design the API contract before writing any implementation code. The contract becomes the source of truth for both frontend and backend.

**When to use**:
- Separate frontend and backend teams
- Multiple clients consuming the same API (web, mobile, third-party)
- Projects where API stability is critical
- Public-facing APIs

**Approach**:
1. Write an OpenAPI (Swagger) specification
2. Generate server stubs and client SDKs from the spec
3. Frontend and backend develop against the contract in parallel
4. Use contract tests to verify both sides conform

**Pros**:
- Frontend and backend can develop in parallel
- Clear, versioned contract reduces integration bugs
- Enables automatic documentation and client generation
- Forces explicit design of the interface

**Cons**:
- Upfront investment in spec writing
- Spec can drift from implementation without CI enforcement
- Over-specification can slow down early exploration

---

## Event-Driven Architecture

Components communicate through asynchronous events rather than direct calls.

**When to use**:
- Operations that do not need an immediate response (email sending, report generation)
- Multiple consumers need to react to the same event
- You need to decouple producers from consumers
- High throughput with bursty workloads

**Components**:
- **Event Producers** -- emit events when something happens
- **Message Broker** -- queues or topics (e.g., RabbitMQ, Redis Streams, Kafka)
- **Event Consumers** -- subscribe and react to events

**Pros**:
- Loose coupling between components
- Natural fit for async workflows
- Improved resilience (producers and consumers fail independently)
- Easy to add new consumers without changing producers

**Cons**:
- Harder to trace and debug (no simple request-response)
- Eventual consistency introduces complexity
- Requires infrastructure for message broker
- Error handling and retry logic add operational overhead

---

## Decision Matrix

Use this matrix to select a starting pattern based on project characteristics.

| Factor                  | Monolith        | Modular Monolith | Microservices     |
|-------------------------|-----------------|-------------------|-------------------|
| **Team size**           | 1-5             | 3-10              | 10+               |
| **Domain complexity**   | Low-Medium      | Medium-High       | High              |
| **Scale requirements**  | Moderate        | Moderate-High     | Very High         |
| **Deployment frequency**| Weekly-Monthly  | Weekly            | Daily per service |
| **Ops maturity**        | Low             | Low-Medium        | High              |
| **Time to first deploy**| Fastest         | Fast              | Slowest           |

**Decision flow**:

1. **Default to Monolith** if you are a small team building a new product.
2. **Upgrade to Modular Monolith** when you have 3+ developers and distinct domain areas that benefit from internal boundaries.
3. **Consider Microservices** only when you have a large team, proven domain boundaries, and the operational maturity to manage distributed systems.
4. **Layer in Event-Driven patterns** selectively for specific async use cases -- do not adopt it as the primary architecture unless the domain is inherently event-driven.
5. **Always use API-First Design** regardless of the overall pattern when the frontend and backend are developed by different people or teams.

---

_End of architecture patterns reference._
