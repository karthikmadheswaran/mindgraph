-- Migration 014: dispatch_payload column + extraction_edits table
-- Run against: Supabase Postgres

-- A. Add dispatch_payload JSONB column to entries
ALTER TABLE entries ADD COLUMN IF NOT EXISTS dispatch_payload JSONB;

-- B. Extraction edits table for user correction capture (eval signal)
CREATE TABLE IF NOT EXISTS extraction_edits (
  edit_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id        UUID NOT NULL REFERENCES auth.users(id),
  entry_id       UUID NOT NULL REFERENCES entries(id) ON DELETE CASCADE,
  stamp_kind     TEXT NOT NULL,
  field_path     TEXT NOT NULL,
  original_value TEXT,
  edited_value   TEXT NOT NULL,
  edit_type      TEXT NOT NULL CHECK (edit_type IN ('correction', 'deletion', 'addition')),
  pipeline_version TEXT,
  created_at     TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_extraction_edits_user
  ON extraction_edits(user_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_extraction_edits_entry
  ON extraction_edits(entry_id);

-- C. Performance indexes for compute_discoveries queries
CREATE INDEX IF NOT EXISTS idx_entries_user_created_status
  ON entries(user_id, created_at DESC)
  WHERE deleted_at IS NULL AND status = 'completed';

CREATE INDEX IF NOT EXISTS idx_entry_tags_entry_category
  ON entry_tags(entry_id, category);

CREATE INDEX IF NOT EXISTS idx_entry_entities_entity_id
  ON entry_entities(entity_id);
