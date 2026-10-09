/**
 * Incident detail tables (W1-TBL).
 *
 * Every incident entity row carries the optimistic-concurrency `version`
 * (backend `version_id_col`, W0-RT-CORE). Mutations echo it back as
 * `If-Match` (`api.put(..., { ifMatch: row.version })`); a stale version
 * answers 409 `conflict`.
 */
export interface Versioned {
  version?: number
}

/** An entity row as served by the paginated list endpoints. */
export type VersionedRow<T> = T & Versioned
