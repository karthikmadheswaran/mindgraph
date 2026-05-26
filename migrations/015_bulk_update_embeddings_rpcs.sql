-- Migration 015: RPCs for bulk embedding backfill in a single transaction
-- Run against: Supabase Postgres
--
-- Context: backfilling task_type-aware embeddings for entries (RETRIEVAL_DOCUMENT)
-- and entities (SEMANTIC_SIMILARITY). Supabase's Python client does not expose
-- explicit transactions, so we wrap the update set in a server-side function.

CREATE OR REPLACE FUNCTION bulk_update_entry_embeddings(updates jsonb)
RETURNS int
LANGUAGE plpgsql AS $$
DECLARE
  r jsonb;
  cnt int := 0;
BEGIN
  FOR r IN SELECT * FROM jsonb_array_elements(updates)
  LOOP
    UPDATE entries
    SET embedding = (r->>'embedding')::vector
    WHERE id = (r->>'id')::uuid;
    cnt := cnt + 1;
  END LOOP;
  RETURN cnt;
END;
$$;

CREATE OR REPLACE FUNCTION bulk_update_entity_embeddings(updates jsonb)
RETURNS int
LANGUAGE plpgsql AS $$
DECLARE
  r jsonb;
  cnt int := 0;
BEGIN
  FOR r IN SELECT * FROM jsonb_array_elements(updates)
  LOOP
    UPDATE entities
    SET embedding = (r->>'embedding')::vector
    WHERE id = (r->>'id')::uuid;
    cnt := cnt + 1;
  END LOOP;
  RETURN cnt;
END;
$$;
