-- Migration 009: Add status + soft-delete filters to BM25 retrieval function
--
-- WHY: search_entries_fulltext was returning entries that are still being
-- processed by the LangGraph pipeline (status != 'completed') and entries
-- that have been soft-deleted (deleted_at IS NOT NULL, added in migration 008).
-- These two holes caused the candidate pool to be polluted with incomplete or
-- deleted entries, pushing real completed entries out of the top-N results.
--
-- The vector path (match_entries) was already patched directly in the Supabase
-- dashboard. This migration patches the BM25 path to match.
--
-- The Python temporal path (fetch_entries_by_date_range) already had
-- .eq("status", "completed") — the missing .is_("deleted_at", "null") was
-- added in app/services/ask_service.py alongside this migration.

CREATE OR REPLACE FUNCTION search_entries_fulltext(
  query_text text,
  match_count int,
  filter_user_id uuid
)
RETURNS TABLE (
  id uuid,
  user_id uuid,
  raw_text text,
  cleaned_text text,
  auto_title text,
  summary text,
  created_at timestamptz,
  ts_rank real
)
LANGUAGE plpgsql
AS $$
DECLARE
  tsquery_val tsquery;
BEGIN
  tsquery_val := plainto_tsquery('english', query_text);
  IF tsquery_val = ''::tsquery THEN
    RETURN;
  END IF;

  RETURN QUERY
  SELECT
    e.id, e.user_id, e.raw_text::text, e.cleaned_text::text,
    e.auto_title::text, e.summary::text, e.created_at,
    ts_rank_cd(e.text_search, tsquery_val) AS ts_rank
  FROM entries e
  WHERE e.user_id = filter_user_id
    AND e.status = 'completed'
    AND e.deleted_at IS NULL
    AND e.text_search @@ tsquery_val
  ORDER BY ts_rank_cd(e.text_search, tsquery_val) DESC
  LIMIT match_count;
END;
$$;
