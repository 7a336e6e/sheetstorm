---
name: Optimizing Performance
description: Diagnose and fix PostgreSQL performance issues using EXPLAIN ANALYZE, indexes, connection pooling, and query optimization.
---

## Goal

Identify and resolve PostgreSQL query performance bottlenecks through systematic analysis with EXPLAIN ANALYZE, strategic index creation, connection pooling configuration, and query rewriting.

## When to Use

- A query takes longer than acceptable thresholds (typically >100ms for OLTP)
- Application logs show slow query warnings
- Database CPU or I/O is unexpectedly high
- Adding a new feature that will query large tables
- Reviewing query patterns before a production deployment

## Instructions

## 1. Diagnose with EXPLAIN ANALYZE

Always start by understanding what PostgreSQL is actually doing. Use `EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT)` to get the execution plan with real timing data.

```sql
EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT)
SELECT u.display_name, COUNT(t.id) AS task_count
FROM users u
JOIN task_assignments ta ON ta.user_id = u.id
JOIN tasks t ON t.id = ta.task_id
WHERE t.status = 'completed'
GROUP BY u.display_name
ORDER BY task_count DESC
LIMIT 10;
```

## 2. Read the Execution Plan

Look for these warning signs in the plan output:

- **Seq Scan** on large tables — indicates a missing index
- **Nested Loop** with high row counts — may need a Hash or Merge join
- **Sort** with high memory usage — consider an index to avoid the sort
- **Buffers: shared read** much higher than **shared hit** — data not cached, table may need vacuuming

Example plan showing a problem:

```
Seq Scan on tasks  (cost=0.00..15432.00 rows=5023 width=18)
  Filter: ((status)::text = 'completed'::text)
  Rows Removed by Filter: 195000
  Buffers: shared read=8320
```

This sequential scan reads 200k rows to return 5k. An index on `status` would fix this.

## 3. Add the Right Index

Choose the index type based on the query pattern. Refer to the index strategy reference for detailed guidance.

```sql
-- Fix the seq scan above with a B-tree index
CREATE INDEX ix_tasks_status ON tasks (status);

-- For a query filtering on status AND ordering by created_at
CREATE INDEX ix_tasks_status_created_at ON tasks (status, created_at DESC);

-- Partial index for a common filtered query
CREATE INDEX ix_tasks_active ON tasks (status, created_at)
    WHERE status != 'archived';
```

After adding the index, re-run EXPLAIN ANALYZE to confirm improvement:

```
Index Scan using ix_tasks_status on tasks  (cost=0.42..1523.15 rows=5023 width=18)
  Index Cond: ((status)::text = 'completed'::text)
  Buffers: shared hit=312
```

## 4. Optimize Query Patterns

Apply these rules to every query:

- Select only the columns you need; avoid `SELECT *`
- Push filters into `WHERE` clauses rather than filtering in application code
- Use `LIMIT` for paginated results
- Use `EXISTS` instead of `IN` for subqueries on large sets
- Avoid functions on indexed columns in WHERE clauses (they prevent index use)

```sql
-- Bad: function on indexed column prevents index use
SELECT * FROM users WHERE LOWER(email) = 'user@example.com';

-- Good: use a functional index or store normalized data
CREATE INDEX ix_users_email_lower ON users (LOWER(email));
SELECT * FROM users WHERE LOWER(email) = 'user@example.com';
```

## 5. Configure Connection Pooling

Avoid opening a new database connection per request. Use connection pooling to reuse connections.

```python
from sqlalchemy import create_engine

engine = create_engine(
    "postgresql://user:pass@localhost/mydb",
    pool_size=10,          # Number of persistent connections
    max_overflow=20,       # Additional connections under load
    pool_timeout=30,       # Seconds to wait for a connection
    pool_recycle=1800,     # Recycle connections after 30 minutes
    pool_pre_ping=True,    # Verify connection health before use
)
```

For high-traffic applications, consider pgBouncer in front of PostgreSQL with transaction-level pooling.

## 6. Monitor Ongoing Performance

Enable the slow query log and review it regularly:

```sql
-- In postgresql.conf
-- log_min_duration_statement = 100   -- Log queries over 100ms
```

Use `pg_stat_statements` to find the most time-consuming queries:

```sql
SELECT query, calls, mean_exec_time, total_exec_time
FROM pg_stat_statements
ORDER BY total_exec_time DESC
LIMIT 20;
```

## Constraints

### ✅ Do
- Run EXPLAIN ANALYZE before and after every optimization to measure impact
- Use partial indexes for queries that always filter on a specific condition
- Monitor the slow query log in all environments
- Vacuum and analyze tables regularly (or ensure autovacuum is properly configured)
- Use covering indexes (INCLUDE) to enable index-only scans for critical queries


### ❌ Don&#x27;t
- Add indexes blindly without first diagnosing the actual bottleneck
- Index every column; each index adds write overhead and storage cost
- Ignore the write performance impact of new indexes on INSERT/UPDATE-heavy tables
- Use OFFSET for deep pagination; use keyset pagination instead
- Cache query results at the application layer without understanding the underlying issue first


## Output Format

Produce a performance analysis report containing: the original query, the EXPLAIN ANALYZE output before optimization, the changes made (new indexes, rewritten query, configuration), and the EXPLAIN ANALYZE output after optimization with measured improvement.

## Dependencies

- [Writing Queries](../writing-queries/SKILL.md) — the queries and models being optimized
- [Index Strategy Reference](references/index-strategy.md) — decision tree for choosing the right index type
