# Requirements Document: [Project Name]

> Version: 0.1
> Last updated: YYYY-MM-DD
> Status: Draft | In Review | Approved

---

## Project Overview

[1-2 paragraphs describing the project purpose, the problem it solves, target users, and high-level scope. This section should be understandable by a non-technical stakeholder.]

---

## User Roles

| Role         | Description                                      | Permissions                              |
|--------------|--------------------------------------------------|------------------------------------------|
| Guest        | Unauthenticated visitor                          | View public content, register            |
| User         | Registered and authenticated individual          | CRUD own resources, view shared content  |
| Admin        | System administrator                             | Full CRUD on all resources, manage users |
| [Role Name]  | [Brief description of who this role represents]  | [List key permissions]                   |

---

## Functional Requirements

### [Domain Group 1, e.g., Authentication]

| ID     | Description                                  | Priority    | Acceptance Criteria                                                   |
|--------|----------------------------------------------|-------------|-----------------------------------------------------------------------|
| FR-001 | [Clear, testable statement of capability]    | Must-have   | [Concrete conditions proving requirement is met]                      |
| FR-002 | [Clear, testable statement of capability]    | Should-have | [Concrete conditions proving requirement is met]                      |

### [Domain Group 2, e.g., Profile Management]

| ID     | Description                                  | Priority    | Acceptance Criteria                                                   |
|--------|----------------------------------------------|-------------|-----------------------------------------------------------------------|
| FR-010 | [Clear, testable statement of capability]    | Must-have   | [Concrete conditions proving requirement is met]                      |
| FR-011 | [Clear, testable statement of capability]    | Could-have  | [Concrete conditions proving requirement is met]                      |

### [Domain Group N]

_Repeat the table structure for each domain area._

---

## Non-Functional Requirements

### Performance

| ID      | Requirement                                          | Target                  |
|---------|------------------------------------------------------|-------------------------|
| NFR-001 | Page load time                                       | < 2 seconds on 3G      |
| NFR-002 | API response time (95th percentile)                  | < 500ms                 |
| NFR-003 | Concurrent users supported                           | [number]                |

### Security

| ID      | Requirement                                          | Details                                |
|---------|------------------------------------------------------|----------------------------------------|
| NFR-010 | Authentication mechanism                             | [e.g., JWT with refresh tokens]        |
| NFR-011 | Password policy                                      | [e.g., min 12 chars, complexity rules] |
| NFR-012 | Data encryption                                      | [e.g., AES-256 at rest, TLS in transit]|
| NFR-013 | Compliance                                           | [e.g., GDPR, SOC 2]                   |

### Scalability

| ID      | Requirement                                          | Target                                 |
|---------|------------------------------------------------------|----------------------------------------|
| NFR-020 | Expected user growth (12 months)                     | [number or range]                      |
| NFR-021 | Data volume growth (12 months)                       | [estimate]                             |

### Accessibility

| ID      | Requirement                                          | Target                                 |
|---------|------------------------------------------------------|----------------------------------------|
| NFR-030 | WCAG conformance level                               | [e.g., AA]                             |
| NFR-031 | Screen reader compatibility                          | [tested readers]                       |
| NFR-032 | Keyboard navigation                                  | All interactive elements reachable     |

---

## Data Entities

### [Entity Name, e.g., User]

| Field        | Type       | Constraints              | Description                    |
|--------------|------------|--------------------------|--------------------------------|
| id           | UUID       | PK, auto-generated       | Unique identifier              |
| email        | String     | Unique, not null         | Login email                    |
| display_name | String     | Max 100 chars            | Public display name            |
| created_at   | Timestamp  | Auto-set                 | Account creation time          |

**Relationships**:
- A User _has many_ Posts
- A User _has one_ Profile

### [Entity Name, e.g., Post]

| Field        | Type       | Constraints              | Description                    |
|--------------|------------|--------------------------|--------------------------------|
| id           | UUID       | PK, auto-generated       | Unique identifier              |
| author_id    | UUID       | FK -> User.id, not null  | Author of the post             |
| title        | String     | Max 200 chars, not null  | Post title                     |
| body         | Text       | Not null                 | Post content                   |
| created_at   | Timestamp  | Auto-set                 | Creation time                  |

**Relationships**:
- A Post _belongs to_ one User
- A Post _has many_ Comments

_Repeat for each entity._

---

## API Surface

> This is a preliminary API surface. Full contracts are defined during the architecture phase.

| Endpoint              | Method | Description                         | Auth Required |
|-----------------------|--------|-------------------------------------|---------------|
| /api/auth/register    | POST   | Create a new user account           | No            |
| /api/auth/login       | POST   | Authenticate and receive token      | No            |
| /api/users/me         | GET    | Get current user profile            | Yes           |
| /api/users/me         | PATCH  | Update current user profile         | Yes           |
| [endpoint]            | [verb] | [description]                       | [Yes/No]      |

---

## Open Questions

| #  | Question                                                    | Impact Area          | Status   |
|----|-------------------------------------------------------------|----------------------|----------|
| 1  | [Unresolved ambiguity or missing information]               | [Which requirements] | Open     |
| 2  | [Unresolved ambiguity or missing information]               | [Which requirements] | Open     |

---

_End of requirements document._
