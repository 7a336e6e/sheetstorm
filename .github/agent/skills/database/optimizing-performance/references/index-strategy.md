---
name: Index Strategy Reference
description: Decision tree and reference for selecting the right PostgreSQL index type based on query patterns.
---

# Index Strategy Reference

Use this reference to select the correct index type for a given query pattern. Always verify with EXPLAIN ANALYZE after creating an index.

## Decision Tree

```
What does your query do?
│
├─ Equality (WHERE col = value)
│  ├─ Scalar column ──────────────> B-tree
│  ├─ Array (WHERE col @> ARRAY[v]) > GIN
│  └─ JSONB (WHERE col @> '{}')  ──> GIN
│
├─ Range (WHERE col > value)
│  └─ Scalar column ──────────────> B-tree
│
├─ ORDER BY col
│  └─ Any column ─────────────────> B-tree (match sort direction)
│
├─ LIKE 'prefix%'
│  └─ Text column ────────────────> B-tree (with text_pattern_ops)
│
├─ LIKE '%substring%'
│  └─ Text column ────────────────> GIN (with pg_trgm)
│
├─ Full-text search (tsvector)
│  ├─ Read-heavy ─────────────────> GIN
│  └─ Write-heavy ────────────────> GiST
│
├─ Geometric / spatial
│  └─ Geometry column ────────────> GiST
│
└─ Range types (tstzrange, int4range)
   └─ Range column ───────────────> GiST
```

## B-tree Index

The default and most common index type. Supports equality, range, sorting, and prefix matching.

```sql
-- Equality
CREATE INDEX ix_users_email ON users (email);

-- Range and sorting
CREATE INDEX ix_tasks_created_at ON tasks (created_at DESC);

-- Prefix LIKE
CREATE INDEX ix_users_display_name_pattern ON users (display_name text_pattern_ops);
```

**Best for:** Primary key lookups, foreign key joins, range scans, ORDER BY, LIKE 'prefix%'.

**Limitations:** Cannot handle containment queries on arrays or JSONB. Not suitable for full-text search.

## Hash Index

Supports equality comparisons only. Since PostgreSQL 10, hash indexes are WAL-logged and crash-safe, but B-tree is almost always a better choice.

```sql
CREATE INDEX ix_sessions_token ON sessions USING hash (token);
```

**Best for:** Exact equality lookups on long values where B-tree overhead is high (rare).

**Limitations:** No range queries, no sorting, no partial matching.

## GIN Index (Generalized Inverted Index)

Designed for values that contain multiple elements: arrays, JSONB, full-text search vectors.

```sql
-- JSONB containment
CREATE INDEX ix_products_metadata ON products USING gin (metadata);

-- Array containment
CREATE INDEX ix_articles_tags ON articles USING gin (tags);

-- Full-text search
CREATE INDEX ix_documents_search ON documents USING gin (search_vector);

-- Trigram matching (LIKE '%substring%')
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE INDEX ix_users_name_trgm ON users USING gin (display_name gin_trgm_ops);
```

**Best for:** Arrays, JSONB, full-text search, trigram similarity.

**Limitations:** Slower to update than B-tree. Higher storage overhead. Not suitable for range queries on scalar values.

## GiST Index (Generalized Search Tree)

Supports geometric types, range types, and full-text search (as an alternative to GIN).

```sql
-- Range type: find overlapping time ranges
CREATE INDEX ix_bookings_period ON bookings USING gist (period);

-- Geometric: nearest-neighbor search
CREATE INDEX ix_locations_point ON locations USING gist (coordinates);

-- Full-text (alternative to GIN, better for write-heavy workloads)
CREATE INDEX ix_documents_search_gist ON documents USING gist (search_vector);
```

**Best for:** Geometric data, range overlaps, nearest-neighbor, write-heavy full-text search.

**Limitations:** Slower reads than GIN for full-text search. Less efficient than B-tree for simple equality/range.

## Composite Indexes

When a query filters or sorts on multiple columns, a composite index can satisfy the entire condition in one lookup.

**Rule: put the most selective column first.** The column that eliminates the most rows should be leftmost.

```sql
-- Query: WHERE status = 'active' AND created_at > '2025-01-01'
-- If status has 5 distinct values and created_at has millions, status is more selective per-value
-- but created_at eliminates more rows. Benchmark both orders.
CREATE INDEX ix_tasks_status_created ON tasks (status, created_at);
```

The index supports queries that use a **leftmost prefix** of its columns:
- `WHERE status = 'active'` — uses the index
- `WHERE status = 'active' AND created_at > '2025-01-01'` — uses the index
- `WHERE created_at > '2025-01-01'` — does NOT use the index (missing leftmost column)

## Partial Indexes

Include a WHERE clause in the index definition to index only the rows that matter. Smaller index, faster lookups, less write overhead.

```sql
-- Only index active tasks (80% of queries filter on this)
CREATE INDEX ix_tasks_active ON tasks (created_at)
    WHERE status != 'archived';

-- Only index unprocessed items
CREATE INDEX ix_queue_pending ON job_queue (created_at)
    WHERE processed_at IS NULL;
```

**Best for:** Tables where queries consistently filter on the same condition. Reduces index size significantly.

## Covering Indexes

Use `INCLUDE` to add columns to an index without affecting the sort order. This enables index-only scans, avoiding a heap lookup entirely.

```sql
-- Query: SELECT email, display_name FROM users WHERE email = 'user@example.com'
CREATE INDEX ix_users_email_covering ON users (email) INCLUDE (display_name);
```

The included columns are stored in the index leaf pages but are not part of the search key. This means the query can be answered entirely from the index.

## When NOT to Index

Not every column benefits from an index. Avoid indexing when:

- **Small tables** (under ~10,000 rows): Sequential scan is often faster than an index lookup
- **Rarely queried columns**: The write overhead is not justified
- **High-write, low-read tables** (e.g., log tables): Indexes slow down every INSERT
- **Low-cardinality columns** alone (e.g., boolean): B-tree on a boolean is rarely useful unless combined with other columns or used as a partial index condition
- **Columns updated frequently**: Every update rewrites the index entry
