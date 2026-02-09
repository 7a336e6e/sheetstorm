---
name: Writing Queries
description: Write SQLAlchemy ORM models and queries following repository patterns, with guidance on when to use raw SQL.
---

## Goal

Implement data access using SQLAlchemy ORM for standard CRUD operations and raw SQL for complex reporting queries. Follow the repository pattern to keep database logic isolated from business logic.

## When to Use

- Defining SQLAlchemy models for new or existing tables
- Writing CRUD operations for a feature
- Building complex queries with joins, aggregations, or subqueries
- Deciding between ORM and raw SQL for a specific use case

## Instructions

## 1. Define the SQLAlchemy Model

Models must match the schema defined in the designing-schemas skill. Use the declarative base and include all constraints.

```python
from datetime import datetime
from sqlalchemy import Column, BigInteger, String, DateTime, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
```

## 2. Implement the Repository Pattern

Encapsulate all database operations in a repository class. This keeps SQL logic out of service and route layers.

```python
from sqlalchemy import select
from sqlalchemy.orm import Session


class UserRepository:
    def __init__(self, session: Session):
        self.session = session

    def get_by_id(self, user_id: int) -> User | None:
        return self.session.get(User, user_id)

    def get_by_email(self, email: str) -> User | None:
        stmt = select(User).where(User.email == email)
        return self.session.scalars(stmt).first()

    def create(self, email: str, password_hash: str, display_name: str) -> User:
        user = User(
            email=email,
            password_hash=password_hash,
            display_name=display_name,
        )
        self.session.add(user)
        self.session.flush()
        return user

    def update(self, user: User, **kwargs) -> User:
        for key, value in kwargs.items():
            setattr(user, key, value)
        self.session.flush()
        return user

    def delete(self, user: User) -> None:
        self.session.delete(user)
        self.session.flush()
```

## 3. Manage Sessions Properly

Use scoped sessions with explicit commit and rollback boundaries. Never leave sessions open across request boundaries.

```python
from contextlib import contextmanager
from sqlalchemy.orm import sessionmaker, Session


@contextmanager
def get_session(session_factory: sessionmaker) -> Session:
    session = session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
```

## 4. Prevent N+1 Queries

Use eager loading when you know related data will be accessed. Choose `joinedload` for single-valued relationships and `selectinload` for collections.

```python
from sqlalchemy.orm import joinedload, selectinload

# Load user with their profile (one-to-one)
stmt = select(User).options(joinedload(User.profile)).where(User.id == user_id)

# Load project with all tasks (one-to-many)
stmt = select(Project).options(selectinload(Project.tasks)).where(Project.id == project_id)
```

## 5. Use Raw SQL for Complex Queries

For reporting, analytics, or queries that are awkward in the ORM, use raw SQL with parameterized queries.

```python
from sqlalchemy import text

stmt = text("""
    SELECT u.display_name, COUNT(t.id) AS task_count
    FROM users u
    JOIN task_assignments ta ON ta.user_id = u.id
    JOIN tasks t ON t.id = ta.task_id
    WHERE t.status = :status
    GROUP BY u.display_name
    ORDER BY task_count DESC
    LIMIT :limit
""")

result = session.execute(stmt, {"status": "completed", "limit": 10})
rows = result.mappings().all()
```

## 6. When to Use ORM vs Raw SQL

| Use Case               | Approach  | Reason                                    |
|------------------------|-----------|-------------------------------------------|
| CRUD operations        | ORM       | Clear, type-safe, easy to maintain        |
| Simple filters/joins   | ORM       | Readable and composable                   |
| Complex aggregations   | Raw SQL   | ORM syntax becomes unwieldy               |
| Bulk updates/deletes   | Raw SQL   | ORM loads every row; raw SQL is faster    |
| Reporting queries      | Raw SQL   | Multiple joins, CTEs, window functions    |

## Constraints

### ✅ Do
- Use parameterized queries for all user-supplied values
- Close sessions properly using context managers
- Use eager loading (joinedload, selectinload) to prevent N+1 queries
- Return plain data objects (dicts, dataclasses, Pydantic models) from repositories at the service boundary
- Use flush() inside repositories and commit() at the service/transaction boundary


### ❌ Don&#x27;t
- Build SQL strings with f-strings or string concatenation
- Ignore N+1 query warnings; profile with echo=True or SQLAlchemy event listeners
- Return ORM model instances across the data layer boundary into HTTP handlers
- Call session.commit() inside repository methods; let the caller control the transaction
- Use session.execute() without parameterized bindings for dynamic values


## Output Format

Produce a Python module containing the SQLAlchemy model class, a repository class with CRUD methods, and a session management utility. Include docstrings on all public methods. Add inline comments for non-obvious query logic.

## Dependencies

- [Designing Schemas](../designing-schemas/SKILL.md) — defines the table structures that models must match
- [Writing Migrations](../writing-migrations/SKILL.md) — migrations must exist before models can be used
