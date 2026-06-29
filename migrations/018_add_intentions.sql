-- Migration 018: intentions table (drift detection — P0)
--
-- RECONSTRUCTED 2026-06-29 from the live Supabase schema. The original DDL was
-- applied directly in the Supabase SQL editor during P0 (commit 61b05c6) and was
-- never committed as a numbered migration; this file backfills it so the schema
-- is reproducible from the repo. Column names/types/defaults verified against
-- the live PostgREST OpenAPI; the two partial indexes verified via the SQL
-- editor (29/06). IF NOT EXISTS throughout → applying against the live DB is a
-- no-op. Mirrors the entries soft-delete shape (008 / deadlines 017).
--
-- WHAT: bottom-up drift detection persists stated intentions extracted from
-- entry prose (P1, extract_intentions) and resolved + clock-wound in store_node
-- (P2, intention_resolver). Read path: GET /intentions/drift (P4) computes
-- days_since(last_referenced_at) LIVE per request — nothing about drift is stored.
--
-- Two partial (live-only) indexes mirror 017:
--   - idx_intentions_user_entry_text — UNIQUE (user_id, source_entry_id,
--     lower(text)) WHERE deleted_at IS NULL: makes reprocess/backfill idempotent
--     (re-extracting the same intention from the same entry is a no-op, not a
--     duplicate) and frees the slot when a row is soft-deleted so restore /
--     reprocess don't collide on duplicate-key.
--   - idx_intentions_live — (user_id, status) WHERE deleted_at IS NULL: the hot
--     read path (live intentions per user for the drift endpoint).
--
-- NOTE: the source_entry_id FK to entries(id) is reconstructed without an
-- explicit ON DELETE (PostgREST introspection does not expose the action); the
-- live constraint name is likewise not reproduced. Functionally equivalent for a
-- fresh build.

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS intentions (
    id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id            uuid NOT NULL,
    text               text NOT NULL,
    status             text NOT NULL DEFAULT 'active',
    source_entry_id    uuid REFERENCES entries (id),
    first_stated_at    timestamptz NOT NULL DEFAULT now(),
    last_referenced_at timestamptz NOT NULL DEFAULT now(),
    reference_count    integer NOT NULL DEFAULT 1,
    embedding          vector(1536),
    deleted_at         timestamptz,
    created_at         timestamptz NOT NULL DEFAULT now(),
    updated_at         timestamptz NOT NULL DEFAULT now()
);

-- Live-only uniqueness — the load-bearing predicate is WHERE deleted_at IS NULL.
CREATE UNIQUE INDEX IF NOT EXISTS idx_intentions_user_entry_text
  ON intentions (user_id, source_entry_id, lower(text))
  WHERE deleted_at IS NULL;

-- Hot read path for the drift endpoint: live intentions for a user.
CREATE INDEX IF NOT EXISTS idx_intentions_live
  ON intentions (user_id, status)
  WHERE deleted_at IS NULL;
