-- Migration 017: Soft delete for deadlines
--
-- WHY: deadline "delete" was a HARD row delete (deadline_service.delete_deadline:
-- .delete().eq("id", ...)). The 5s client-side undo was the only recovery — once
-- the timer fired the row was gone. Mirror the entries soft-delete (migration 008)
-- so deletes are recoverable: "delete" stamps deleted_at, every read filters it
-- out, and a restore path can clear it. Companion: per-deadline multi-delete undo
-- on the frontend (fix/deadline-soft-delete-multi).
--
-- WHAT:
-- 1. Add a nullable deleted_at column to deadlines. Existing rows -> NULL (active);
--    no data change to live rows.
-- 2. CRITICAL: migration 003 created
--    idx_deadlines_source_entry_description_due_date as a UNIQUE index over ALL
--    rows. Under soft-delete a deleted row would keep occupying that slot, so
--    store_entry_deadlines re-inserting the same logical deadline (entry
--    reprocessed) or a restore would collide on duplicate-key. Recreate it as a
--    PARTIAL unique index over live rows only (WHERE deleted_at IS NULL).
-- 3. Add a partial index for the hot list path (list_deadlines), mirroring
--    idx_entries_live from migration 008.

ALTER TABLE deadlines ADD COLUMN IF NOT EXISTS deleted_at timestamptz;

-- (2) live-only uniqueness — without this, reprocessing/restore breaks on the
-- 003 dedup constraint. This is the highest-risk line in the migration.
DROP INDEX IF EXISTS idx_deadlines_source_entry_description_due_date;
CREATE UNIQUE INDEX IF NOT EXISTS idx_deadlines_source_entry_description_due_date
  ON deadlines (source_entry_id, lower(description), due_date)
  WHERE deleted_at IS NULL;

-- (3) keep the common list path fast as deletions accumulate
CREATE INDEX IF NOT EXISTS idx_deadlines_live
  ON deadlines (user_id, due_date)
  WHERE deleted_at IS NULL;
