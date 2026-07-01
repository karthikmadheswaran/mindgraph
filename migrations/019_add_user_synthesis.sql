-- Migration 019: user_synthesis table (Reflection feature — self-synthesis engine, Phase 1)
--
-- WHAT: a per-user, single-row EVOLVING "self-understanding" document. Unlike the
-- insights table (clear-and-replace on every run), this row is READ-MODIFY-WRITTEN:
-- each synthesis run reads the existing doc + entries since last_processed_at and
-- REWRITES a bounded doc that surfaces non-obvious behavioural/psychological
-- patterns the user never explicitly stated. Mirrors the user_memory shape (006);
-- the Ask conversation-memory compaction (compact_old_messages / build_compaction_
-- prompt) is the structural precedent for the read-modify-write loop.
--
-- DISTINCT from drift (intentions table, 018): reflection = patterns the user never
-- stated (emotional cadence, within-entry contradictions, correlations they wouldn't
-- self-report); drift = stated-intention-vs-behaviour gaps. They do not overlap.
--
-- watermark:  last_processed_at is the newest entry.created_at folded into the doc,
--             so an incremental run reads only entries since then (bounds cost).
-- opened_at:  gift UX (Phase 2). Column added NOW so Phase 2 needs no migration;
--             Phase 1 never writes it.
--
-- The app connects with the service-role key (bypasses RLS), same as user_memory;
-- the RLS policies below mirror 006 for direct-client parity.

CREATE TABLE IF NOT EXISTS user_synthesis (
  id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id           uuid NOT NULL UNIQUE REFERENCES auth.users(id) ON DELETE CASCADE,
  synthesis_text    text NOT NULL DEFAULT '',      -- the evolving self-understanding doc
  last_processed_at timestamptz,                    -- watermark: newest entry.created_at folded in
  generated_at      timestamptz,                    -- when this version was written
  opened_at         timestamptz,                    -- gift UX (Phase 2); unused in Phase 1
  updated_at        timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_user_synthesis_user_id ON user_synthesis(user_id);

ALTER TABLE user_synthesis ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can read own synthesis"
  ON user_synthesis FOR SELECT
  USING (auth.uid() = user_id);

CREATE POLICY "Users can upsert own synthesis"
  ON user_synthesis FOR INSERT
  WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can update own synthesis"
  ON user_synthesis FOR UPDATE
  USING (auth.uid() = user_id);
