-- Migration 008: Soft delete for entries
--
-- WHY: Users need to remove journal entries from the dashboard without
-- irreversibly destroying the raw_text. A soft delete keeps the row
-- recoverable while hiding it from all read paths. Extracted artifacts
-- (entity links, relations, deadlines, tags) are still hard-deleted at
-- the application layer because they can be regenerated from raw_text if
-- the entry is ever restored.
--
-- WHAT:
-- 1. Adds a nullable deleted_at column to the entries table
-- 2. Adds a partial index on (user_id, created_at) WHERE deleted_at IS NULL
--    so the common list-entries path stays fast as deletions accumulate

ALTER TABLE entries ADD COLUMN IF NOT EXISTS deleted_at timestamptz;

CREATE INDEX IF NOT EXISTS idx_entries_live
  ON entries (user_id, created_at DESC)
  WHERE deleted_at IS NULL;
