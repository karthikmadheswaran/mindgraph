-- ============================================================================
-- MindGraph prod cleanup — DRAFT prepared 2026-07-15 (Task 4, pre-demand-test)
-- STATUS: NOT EXECUTED. Founder runs this manually in the Supabase SQL editor.
-- Inventory source: read-only sweep of prod on 2026-07-15 (20 auth users,
-- 310 public.users rows, service-role SELECT/count only).
--
-- HOW TO RUN
--   1. Run the PREVIEW section first; sanity-check every count.
--   2. Run the DELETE section inside the provided transaction; check the
--      returned counts match the previews; COMMIT (or ROLLBACK).
--   3. Delete the corresponding AUTH users from the Supabase dashboard
--      (Authentication → Users) LAST — the data deletes below do not touch
--      auth.users.
--
-- ============================================================================
-- SUMMARY TABLE — every account seen in prod (auth.users) on 2026-07-15
-- Row counts: entries / intentions / deadlines / projects / entities,
-- last activity = newest entry (or last sign-in where no entries).
--
-- | # | user (email)                    | classification    | rows (e/i/d/p/ent)| last activity | in script |
-- |---|---------------------------------|-------------------|-------------------|---------------|-----------|
-- | 1 | krithikb4u@gmail.com            | FOUNDER (live     | 81/45/32/9/105    | 2026-07-10    | N — PRESERVE |
-- |   |                                 | dogfood, 45-int.  |                   |               |           |
-- |   |                                 | seed, allowlisted)|                   |               |           |
-- | 2 | mt-eval+0f33e1b74b@example.invalid | TEST/SYNTHETIC (eval seed) | 1/0/3/0/0 | 2026-06-08 | Y |
-- | 3 | mt-eval+aca25391fb@example.invalid | TEST/SYNTHETIC (eval seed) | 1/0/3/0/0 | 2026-06-08 | Y |
-- | 4 | mt-eval+fdbc4d1011@example.invalid | TEST/SYNTHETIC (eval seed) | 1/0/3/0/0 | 2026-06-08 | Y |
-- | 5 | mt-eval+3d1a9618cf@example.invalid | TEST/SYNTHETIC (eval seed) | 2/0/0/1/2 | 2026-06-10 | Y |
-- | 6 | mt-eval+1f67a68597@example.invalid | TEST/SYNTHETIC (eval seed) | 2/0/0/1/2 | 2026-06-10 | Y |
-- | 7 | mt-eval+2b8491ab48@example.invalid | TEST/SYNTHETIC (eval seed) | 1/0/5/0/0 | 2026-06-09 | Y |
-- | 8 | mt-eval+dc4eeb4965@example.invalid | TEST/SYNTHETIC (eval seed) | 1/0/5/0/0 | 2026-06-09 | Y |
-- | 9 | mt-eval+60a282a220@example.invalid | TEST/SYNTHETIC (eval seed) | 1/0/2/0/0 | 2026-06-08 | Y |
-- |10 | testemail@gmail.com             | TEST/SYNTHETIC (never confirmed, 0 data) | 0/0/0/0/0 | never | Y |
-- |11 | karthik.madheswaran20@gmail.com | UNKNOWN — looks like founder's earlier real/dogfood account (31 entries, git email match) | 31/0/18/13/53 | 2026-06-05 sign-in | N — founder decides |
-- |12 | surreykarthik@gmail.com         | UNKNOWN — founder-named; March-era test? | 13/0/13/3/8 | 2026-03-31 | N — founder decides |
-- |13 | ka41h1k@gmail.com               | UNKNOWN — founder-named; 1 entry but 38 entities / 32 projects (graph-seeding pattern) | 1/0/0/32/38 | 2026-03-30 | N — founder decides |
-- |14 | synthara808@gmail.com           | UNKNOWN — founder-adjacent (session email); zero data rows | 0/0/0/0/0 | 2026-03-31 sign-in | N — zero data anyway |
-- |15 | kteh393@gmail.com               | UNKNOWN — recent stranger-looking signup | 1/0/0/0/0 | 2026-07-02 | N — founder decides |
-- |16 | zzbmbbmz@gmail.com              | UNKNOWN — throwaway-looking | 1/0/0/1/21 | 2026-05-29 | N — founder decides |
-- |17 | gokulvasa2495@gmail.com         | UNKNOWN — real-name-looking; asks only, 0 entries | 0/0/0/0/0 | 2026-05-19 | N — founder decides |
-- |18 | proxymaxturbo@gmail.com         | UNKNOWN — throwaway-looking | 1/0/0/0/1 | 2026-05-14 | N — founder decides |
-- |19 | mohanramparameswaran@gmail.com  | UNKNOWN — real-name-looking | 1/0/0/0/1 | 2026-04-06 | N — founder decides |
-- |20 | qbee1298@gmail.com              | UNKNOWN — 4 entries, April | 4/1(dl)/0/0/0 | 2026-04-08 | N — founder decides |
--
-- NON-ACCOUNT CLEANUP (all in script, Y):
-- | orphaned public.users rows (id NOT IN auth.users)      | 290 rows — 287 mt-eval+<hex>@example.invalid, 1 test@example.com, 1 mt-eval-probe, 1 store-test-<hex>@mindgraph.test (2026-02-25 → 2026-06-15) | Y |
-- | data rows of DELETED auth user e5e611e2-7618-43e2-be84-bf1fc3296382 | 5 entries, 20 entities, 7 deadlines, 27 projects, 1 users row | Y |
-- | data rows of DELETED auth user 9f686c65-aeba-4853-a604-22141510c4a0 | 8 entities, 8 projects, 1 users row | Y |
-- | access_requests: coldstart-audit-20260715@example.com  | 1 row (today's Task-3 synthetic probe) | Y |
-- | rate_limit_usage rows keyed to script-target users     | subset of 94 rows (also 21 user-keyed rows total; IP-keyed rows left alone) | Y |
--
-- ORPHAN-CHECK RESULTS (2026-07-15): entry_entities / entry_tags have ZERO
-- dangling FK rows. Embeddings are pgvector COLUMNS on entries/entities (no
-- separate embeddings table), so they die with their rows — no dangling
-- vectors possible. allowed_emails contains ONLY the founder — no stale test
-- emails. NOTE: migration 022 (RLS lockdown) is applied in prod but the file
-- is missing from migrations/ — unrelated to cleanup, flagged for the repo.
-- ============================================================================


-- ────────────────────────────────────────────────────────────────────────────
-- STEP 0 — target set. Edit this list to add/remove accounts before running.
-- Currently: the 8 mt-eval auth users + testemail@gmail.com + the 2 already-
-- deleted auth users whose data rows linger. UNKNOWN accounts are NOT here.
-- ────────────────────────────────────────────────────────────────────────────
CREATE TEMP TABLE cleanup_targets (user_id uuid PRIMARY KEY, email text);
INSERT INTO cleanup_targets (user_id, email) VALUES
  ('38ba71e3-112f-4427-8109-4d7486d02701', 'mt-eval+0f33e1b74b@example.invalid'),
  ('5500aea7-1092-4193-b8a7-f174534b12d0', 'mt-eval+aca25391fb@example.invalid'),
  ('38685cd2-d0f1-42eb-b267-8a8280bb28a4', 'mt-eval+fdbc4d1011@example.invalid'),
  ('31bf26cc-c4c8-461b-9f18-c4757f68f974', 'mt-eval+3d1a9618cf@example.invalid'),
  ('195a348d-78b7-479f-8811-e88c5d5959c5', 'mt-eval+1f67a68597@example.invalid'),
  ('88bd6672-7825-4890-bc1c-f3ddc2bbdbef', 'mt-eval+2b8491ab48@example.invalid'),
  ('86125f93-fd65-4cbd-bd93-8bef00c596c1', 'mt-eval+dc4eeb4965@example.invalid'),
  ('18034d76-a229-4c00-aa72-edc85fab1091', 'mt-eval+60a282a220@example.invalid'),
  ('6d2d96b2-05c0-4a08-9bf2-bb8242523bee', 'testemail@gmail.com'),
  -- data-only orphans (auth user already deleted):
  ('e5e611e2-7618-43e2-be84-bf1fc3296382', '(deleted auth user — data orphans)'),
  ('9f686c65-aeba-4853-a604-22141510c4a0', '(deleted auth user — data orphans)');

-- OPTIONAL — founder-owned candidates. Uncomment ONLY after founder decision:
-- INSERT INTO cleanup_targets VALUES ('c6b52484-1800-4194-a87b-c370a6105baf', 'surreykarthik@gmail.com');
-- INSERT INTO cleanup_targets VALUES ('0f5acdab-736f-4f44-883e-c897145a5ff2', 'ka41h1k@gmail.com');
-- INSERT INTO cleanup_targets VALUES ('22d092ac-8c0e-4262-bb33-89a89c88e119', 'zzbmbbmz@gmail.com');
-- INSERT INTO cleanup_targets VALUES ('76888dcd-8527-48c7-9213-aac2f1e9a896', 'proxymaxturbo@gmail.com');
-- karthik.madheswaran20@gmail.com deliberately NOT listed even as optional —
-- 31 entries of what looks like real dogfood data; decide separately.

-- Hard safety net: refuse to proceed if the founder id ever lands in targets.
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM cleanup_targets
             WHERE user_id = 'e7bcef72-a66c-4ebe-9c5e-0a98b5f696d8') THEN
    RAISE EXCEPTION 'FOUNDER ACCOUNT (krithikb4u) IN CLEANUP TARGETS — ABORTING';
  END IF;
END $$;


-- ────────────────────────────────────────────────────────────────────────────
-- STEP 1 — PREVIEW. Run all of these; verify counts before any DELETE.
-- Expected (from 2026-07-15 inventory, default target set): entries 15,
-- entities 32, deadlines 28, projects 37, ask_messages 30, user_memory 8,
-- entry-FK children per child-table previews, public.users(targets) 11,
-- public.users(orphans) 290, access_requests 1.
-- ────────────────────────────────────────────────────────────────────────────
SELECT 'entry_tags'      AS tbl, count(*) FROM entry_tags      WHERE entry_id  IN (SELECT id FROM entries WHERE user_id IN (SELECT user_id FROM cleanup_targets));
SELECT 'entry_entities'  AS tbl, count(*) FROM entry_entities  WHERE entry_id  IN (SELECT id FROM entries WHERE user_id IN (SELECT user_id FROM cleanup_targets))
                                                                   OR entity_id IN (SELECT id FROM entities WHERE user_id IN (SELECT user_id FROM cleanup_targets));
SELECT 'extraction_edits' AS tbl, count(*) FROM extraction_edits WHERE user_id IN (SELECT user_id FROM cleanup_targets);
SELECT 'entity_relations' AS tbl, count(*) FROM entity_relations WHERE user_id IN (SELECT user_id FROM cleanup_targets);
SELECT 'suppressed_project_entities' AS tbl, count(*) FROM suppressed_project_entities WHERE user_id IN (SELECT user_id FROM cleanup_targets);
SELECT 'deadlines'       AS tbl, count(*) FROM deadlines       WHERE user_id IN (SELECT user_id FROM cleanup_targets);
SELECT 'intentions'      AS tbl, count(*) FROM intentions      WHERE user_id IN (SELECT user_id FROM cleanup_targets);
SELECT 'projects'        AS tbl, count(*) FROM projects        WHERE user_id IN (SELECT user_id FROM cleanup_targets);
SELECT 'insights'        AS tbl, count(*) FROM insights        WHERE user_id IN (SELECT user_id FROM cleanup_targets);
SELECT 'ask_messages'    AS tbl, count(*) FROM ask_messages    WHERE user_id IN (SELECT user_id FROM cleanup_targets);
SELECT 'user_memory'     AS tbl, count(*) FROM user_memory     WHERE user_id IN (SELECT user_id FROM cleanup_targets);
SELECT 'user_synthesis'  AS tbl, count(*) FROM user_synthesis  WHERE user_id IN (SELECT user_id FROM cleanup_targets);
SELECT 'entities'        AS tbl, count(*) FROM entities        WHERE user_id IN (SELECT user_id FROM cleanup_targets);
SELECT 'entries'         AS tbl, count(*) FROM entries         WHERE user_id IN (SELECT user_id FROM cleanup_targets);
SELECT 'daily_llm_costs' AS tbl, count(*) FROM daily_llm_costs WHERE user_id IN (SELECT user_id FROM cleanup_targets);
SELECT 'subscriptions'   AS tbl, count(*) FROM subscriptions   WHERE user_id IN (SELECT user_id FROM cleanup_targets);
SELECT 'rate_limit_usage' AS tbl, count(*) FROM rate_limit_usage WHERE key IN (SELECT 'user:' || user_id::text || ':entries' FROM cleanup_targets
                                                                               UNION SELECT 'user:' || user_id::text || ':asks' FROM cleanup_targets);
SELECT 'users (targets)' AS tbl, count(*) FROM public.users    WHERE id IN (SELECT user_id FROM cleanup_targets);
SELECT 'users (all orphans vs auth)' AS tbl, count(*) FROM public.users u WHERE NOT EXISTS (SELECT 1 FROM auth.users a WHERE a.id = u.id);
SELECT 'access_requests (probe)' AS tbl, count(*) FROM access_requests WHERE email = 'coldstart-audit-20260715@example.com';

-- Eyeball the orphan users being deleted (should be ONLY *.invalid /
-- example.com / mindgraph.test synthetics):
SELECT email, count(*) FROM public.users u
WHERE NOT EXISTS (SELECT 1 FROM auth.users a WHERE a.id = u.id)
GROUP BY email ORDER BY count(*) DESC LIMIT 20;


-- ────────────────────────────────────────────────────────────────────────────
-- STEP 2 — DELETE (FK-safe order: children → parents). Runs in ONE
-- transaction; verify each returned count against Step 1, then COMMIT.
-- NOTE these are HARD deletes — appropriate here because the target rows are
-- synthetic; the app's soft-delete convention applies to live user data only.
-- ────────────────────────────────────────────────────────────────────────────
BEGIN;

-- entry-scoped children first
DELETE FROM entry_tags       WHERE entry_id IN (SELECT id FROM entries WHERE user_id IN (SELECT user_id FROM cleanup_targets));
DELETE FROM entry_entities   WHERE entry_id IN (SELECT id FROM entries WHERE user_id IN (SELECT user_id FROM cleanup_targets))
                                OR entity_id IN (SELECT id FROM entities WHERE user_id IN (SELECT user_id FROM cleanup_targets));
DELETE FROM extraction_edits WHERE user_id IN (SELECT user_id FROM cleanup_targets);

-- entity-scoped children
DELETE FROM entity_relations            WHERE user_id IN (SELECT user_id FROM cleanup_targets);
DELETE FROM suppressed_project_entities WHERE user_id IN (SELECT user_id FROM cleanup_targets);

-- user-scoped feature tables
DELETE FROM deadlines       WHERE user_id IN (SELECT user_id FROM cleanup_targets);
DELETE FROM intentions      WHERE user_id IN (SELECT user_id FROM cleanup_targets);
DELETE FROM projects        WHERE user_id IN (SELECT user_id FROM cleanup_targets);
DELETE FROM insights        WHERE user_id IN (SELECT user_id FROM cleanup_targets);
DELETE FROM ask_messages    WHERE user_id IN (SELECT user_id FROM cleanup_targets);
DELETE FROM user_memory     WHERE user_id IN (SELECT user_id FROM cleanup_targets);
DELETE FROM user_synthesis  WHERE user_id IN (SELECT user_id FROM cleanup_targets);

-- parents
DELETE FROM entities        WHERE user_id IN (SELECT user_id FROM cleanup_targets);
DELETE FROM entries         WHERE user_id IN (SELECT user_id FROM cleanup_targets);

-- metering / billing
DELETE FROM daily_llm_costs  WHERE user_id IN (SELECT user_id FROM cleanup_targets);
DELETE FROM subscriptions    WHERE user_id IN (SELECT user_id FROM cleanup_targets);
DELETE FROM rate_limit_usage WHERE key IN (SELECT 'user:' || user_id::text || ':entries' FROM cleanup_targets
                                           UNION SELECT 'user:' || user_id::text || ':asks' FROM cleanup_targets);

-- app-side user rows: script targets + ALL auth-orphaned synthetic rows
DELETE FROM public.users WHERE id IN (SELECT user_id FROM cleanup_targets);
DELETE FROM public.users u WHERE NOT EXISTS (SELECT 1 FROM auth.users a WHERE a.id = u.id);

-- today's synthetic access-request probe
DELETE FROM access_requests WHERE email = 'coldstart-audit-20260715@example.com';

-- >>> Verify the counts above, then run COMMIT; (or ROLLBACK;) manually. <<<
-- COMMIT;


-- ────────────────────────────────────────────────────────────────────────────
-- STEP 3 — AFTER COMMIT, in the Supabase dashboard (Authentication → Users),
-- delete these 9 auth users (the 2 data-orphan ids have no auth user left):
--   mt-eval+0f33e1b74b@example.invalid   mt-eval+aca25391fb@example.invalid
--   mt-eval+fdbc4d1011@example.invalid   mt-eval+3d1a9618cf@example.invalid
--   mt-eval+1f67a68597@example.invalid   mt-eval+2b8491ab48@example.invalid
--   mt-eval+dc4eeb4965@example.invalid   mt-eval+60a282a220@example.invalid
--   testemail@gmail.com
-- allowed_emails needs NO cleanup (contains only the founder).
-- ────────────────────────────────────────────────────────────────────────────
