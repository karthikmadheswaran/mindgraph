-- Migration 007: Add full-text search (BM25-like) to entries table
--
-- WHY: MindGraph's Ask feature uses pgvector cosine similarity for retrieval,
-- but semantic embeddings miss entries where the topic is mentioned in passing
-- (e.g. "MindGraph tools" doesn't match an entry that mentions tools briefly).
-- Postgres full-text search (tsvector/tsquery) provides BM25-like keyword matching
-- that complements the dense vector search — together they form a hybrid retrieval
-- pipeline that catches both semantic and lexical matches.
--
-- WHAT:
-- 1. Adds a tsvector column (text_search) to the entries table
-- 2. Populates it from existing cleaned_text
-- 3. Creates a GIN index for fast full-text search
-- 4. Adds a trigger to auto-update tsvector on insert/update
-- 5. Creates an RPC function (search_entries_fulltext) for the Python backend to call

-- 1. Add tsvector column
ALTER TABLE entries ADD COLUMN IF NOT EXISTS text_search tsvector;

-- 2. Populate for existing entries
UPDATE entries SET text_search = to_tsvector('english', COALESCE(cleaned_text, ''));

-- 3. Create GIN index for fast full-text search
CREATE INDEX IF NOT EXISTS idx_entries_text_search ON entries USING gin(text_search);

-- 4. Auto-update trigger: keeps text_search in sync when cleaned_text changes
CREATE OR REPLACE FUNCTION entries_text_search_trigger()
RETURNS trigger AS $$
BEGIN
  NEW.text_search := to_tsvector('english', COALESCE(NEW.cleaned_text, ''));
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS entries_text_search_update ON entries;
CREATE TRIGGER entries_text_search_update
  BEFORE INSERT OR UPDATE OF cleaned_text ON entries
  FOR EACH ROW
  EXECUTE FUNCTION entries_text_search_trigger();

-- 5. Full-text search RPC function
-- Uses plainto_tsquery for natural language queries and ts_rank_cd for ranking.
-- Returns empty if the query produces an empty tsquery (all stop words).
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
    AND e.text_search @@ tsquery_val
  ORDER BY ts_rank_cd(e.text_search, tsquery_val) DESC
  LIMIT match_count;
END;
$$;
