-- 020: drift pick v1 — add surfaced_at to intentions.
--
-- Tracks when an intention was last served as the single Home "Noticed" drift
-- card (GET /intentions/drift?pick=true). Used for:
--   * pick cooldown  — an intention surfaced within the last 14 days is not
--     re-picked (surfaced_at IS NULL OR surfaced_at < now() - interval '14 days')
--   * pick stickiness — the same pick is re-served (without restamping) for up
--     to 48h while unacted, then rotates
--   * never-surfaced bonus — +0.5 score for rows with surfaced_at IS NULL
--
-- NULL = never surfaced. Backfill: none needed — all existing rows start NULL
-- (never surfaced), which is correct.
--
-- Apply manually in the Supabase SQL editor (per house rules).

ALTER TABLE intentions
  ADD COLUMN IF NOT EXISTS surfaced_at timestamptz NULL;

COMMENT ON COLUMN intentions.surfaced_at IS
  'Last time this intention was served as the Home drift pick (drift pick v1, migration 020). NULL = never surfaced.';

-- ── Rollback ──────────────────────────────────────────────────────────────────
-- ALTER TABLE intentions DROP COLUMN IF EXISTS surfaced_at;
-- (No index or constraint depends on it; the pick endpoint degrades gracefully —
-- selects would 400 on the missing column, so redeploy the pre-020 backend
-- first, then drop.)
