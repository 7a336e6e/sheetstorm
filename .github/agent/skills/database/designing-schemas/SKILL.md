---
name: Designing Schemas
description: Design normalized PostgreSQL schemas from tech specs, with proper constraints, naming conventions, and standard columns.
---

## Goal

Translate data entities from a tech spec into well-structured PostgreSQL tables that follow normalization rules, enforce data integrity through constraints, and use consistent naming conventions.

## When to Use

- Starting a new feature that requires new database tables
- Refactoring an existing schema to fix normalization issues
- Reviewing a proposed data model before writing migrations
- Adding relationships between existing entities

## Instructions

## 1. Identify Entities and Relationships

Read the tech spec and extract all data entities, their attributes, and the relationships between them. Map each entity to a table and each relationship to a foreign key or join table.

## 2. Apply Normalization

Normalize to Third Normal Form (3NF) by default. Every non-key column must depend on the key, the whole key, and nothing but the key. Denormalization is acceptable only with explicit justification (e.g., read-heavy access patterns with measured performance impact).

## 3. Define Primary Keys

Prefer `UUID` for distributed systems or `BIGSERIAL` for single-database deployments. Every table must have a column named `id` as its primary key.

## 4. Add Standard Columns

Every table must include these columns:

- `id` — primary key
- `created_at TIMESTAMPTZ NOT NULL DEFAULT now()`
- `updated_at TIMESTAMPTZ NOT NULL DEFAULT now()`

## 5. Define Constraints and Indexes

Add foreign keys for all relationships. Add `NOT NULL` to every column unless there is a clear reason for allowing nulls. Add `CHECK` constraints for value boundaries. Create indexes on all foreign key columns.

## 6. Example Schema

```sql
CREATE TABLE users (
    id            BIGSERIAL PRIMARY KEY,
    email         VARCHAR(255) NOT NULL,
    password_hash VARCHAR(128) NOT NULL,
    display_name  VARCHAR(100) NOT NULL,
    created_at    TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ  NOT NULL DEFAULT now(),

    CONSTRAINT uq_users_email UNIQUE (email),
    CONSTRAINT ck_users_email_format CHECK (email ~* '^.+@.+\..+$')
);

CREATE INDEX ix_users_email ON users (email);
```

```sql
CREATE TABLE task_assignments (
    id         BIGSERIAL   PRIMARY KEY,
    user_id    BIGINT      NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    task_id    BIGINT      NOT NULL REFERENCES tasks (id) ON DELETE CASCADE,
    assigned_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT uq_task_assignments_user_task UNIQUE (user_id, task_id)
);

CREATE INDEX ix_task_assignments_user_id ON task_assignments (user_id);
CREATE INDEX ix_task_assignments_task_id ON task_assignments (task_id);
```

## 7. Follow Naming Conventions

Refer to the naming conventions reference for all naming decisions. Use snake_case throughout. Table names are plural, column names are singular.

## Constraints

### ✅ Do
- Use NOT NULL by default on every column; allow NULL only with explicit justification
- Add CHECK constraints for value ranges and formats
- Define indexes on all foreign key columns
- Include id, created_at, and updated_at on every table
- Use TIMESTAMPTZ for all timestamp columns
- Add ON DELETE behavior (CASCADE, SET NULL, or RESTRICT) to every foreign key
- Document denormalization decisions with comments in the SQL


### ❌ Don&#x27;t
- Use VARCHAR without a length limit; always specify a max length
- Skip foreign key constraints for convenience
- Use reserved SQL words (user, order, group) as table or column names
- Create circular foreign key dependencies
- Use floating point types for monetary values; use NUMERIC instead
- Add surrogate keys to pure join tables unless they need independent identity


## Output Format

Produce a SQL file containing all `CREATE TABLE`, `CREATE INDEX`, and `ALTER TABLE` statements. Group related tables together. Include comments explaining non-obvious design decisions. End with a summary listing all tables and their relationships.

## Dependencies

- [Task Tracking](../../shared/task-tracking/SKILL.md) — update task status as schema work progresses
- [Naming Conventions](references/naming-conventions.md) — rules for table, column, index, and constraint names
