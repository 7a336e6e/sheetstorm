---
name: Database Naming Conventions
description: Reference for consistent naming of tables, columns, indexes, constraints, and types in PostgreSQL.
---

# Database Naming Conventions

All database objects follow snake_case naming. Consistency in naming reduces ambiguity and makes queries easier to read and maintain.

## Tables

Use **plural snake_case** for table names. The table name represents the collection of records it holds.

| Good              | Bad               |
|-------------------|-------------------|
| `users`           | `User`            |
| `task_assignments`| `taskAssignment`  |
| `order_items`     | `OrderItems`      |
| `api_keys`        | `apikeys`         |

## Columns

Use **singular snake_case** for column names. Each column represents a single attribute of one record.

| Good            | Bad              |
|-----------------|------------------|
| `email`         | `Email`          |
| `created_at`    | `createdAt`      |
| `display_name`  | `DisplayName`    |
| `is_active`     | `isActive`       |

## Primary Keys

Every table must use `id` as the primary key column name. Do not prefix with the table name.

```sql
-- Correct
CREATE TABLE users (
    id BIGSERIAL PRIMARY KEY
);

-- Incorrect
CREATE TABLE users (
    user_id BIGSERIAL PRIMARY KEY
);
```

## Foreign Keys

Name foreign key columns as `{referenced_table_singular}_id`. This makes the relationship immediately clear.

| Column Name   | References       |
|---------------|------------------|
| `user_id`     | `users.id`       |
| `task_id`     | `tasks.id`       |
| `project_id`  | `projects.id`    |
| `parent_comment_id` | `comments.id` |

## Indexes

Use the prefix `ix_` followed by the table name and column name(s).

| Pattern                          | Example                              |
|----------------------------------|--------------------------------------|
| Single column                    | `ix_users_email`                     |
| Composite (multi-column)         | `ix_task_assignments_user_id_task_id`|
| Partial (with WHERE)             | `ix_users_email_active`              |

```sql
CREATE INDEX ix_users_email ON users (email);
CREATE INDEX ix_task_assignments_user_id_task_id ON task_assignments (user_id, task_id);
```

## Constraints

Use a prefix indicating the constraint type, followed by table name and a description.

| Type        | Prefix | Example                                |
|-------------|--------|----------------------------------------|
| Check       | `ck_`  | `ck_users_email_format`                |
| Unique      | `uq_`  | `uq_users_email`                       |
| Foreign key | `fk_`  | `fk_task_assignments_user_id`          |
| Primary key | `pk_`  | `pk_users` (usually implicit)          |

```sql
ALTER TABLE users ADD CONSTRAINT ck_users_email_format CHECK (email ~* '^.+@.+\..+$');
ALTER TABLE users ADD CONSTRAINT uq_users_email UNIQUE (email);
ALTER TABLE task_assignments ADD CONSTRAINT fk_task_assignments_user_id
    FOREIGN KEY (user_id) REFERENCES users (id);
```

## Enum Types

Use **singular PascalCase** for the type name and **lowercase** for the enum values.

```sql
CREATE TYPE TaskStatus AS ENUM ('pending', 'in_progress', 'completed', 'cancelled');
CREATE TYPE UserRole AS ENUM ('admin', 'member', 'viewer');
```

## Timestamps

Use the following standard names for timestamp columns. All timestamps must use `TIMESTAMPTZ`.

| Column       | Purpose                          |
|--------------|----------------------------------|
| `created_at` | When the record was created      |
| `updated_at` | When the record was last modified|
| `deleted_at` | Soft delete marker (NULL = active)|

```sql
created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
deleted_at TIMESTAMPTZ          -- NULL means not deleted
```

For soft deletes, always filter with `WHERE deleted_at IS NULL` in application queries and consider a partial index:

```sql
CREATE INDEX ix_users_active ON users (id) WHERE deleted_at IS NULL;
```
