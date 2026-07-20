-- Migration 022: RLS lockdown — enable row-level security on every user-data
-- table (closes security-audit finding F1/P0: anon key read all journal data).
--
-- RECONSTRUCTED 2026-07-15. The lockdown SQL was applied directly in the
-- Supabase SQL editor on 2026-07-10 (from the proposal in
-- docs/security-audit-2026-07.md §F1) and — like 018 before it — was never
-- committed as a numbered migration; this file backfills it so a fresh
-- 001→024 build reproduces the live security posture. ALTER TABLE ... ENABLE
-- ROW LEVEL SECURITY is idempotent, so applying this against the live DB is a
-- no-op. Verified against live behavior 2026-07-15: anon REST probe returns
-- zero rows on every table below (probe method: docs/security-audit-2026-07.md
-- §F1 "Verification after apply").
--
-- WHY THIS WORKS WITH NO POLICIES: the backend connects with the service-role
-- key, which BYPASSES RLS; per-user isolation on the API path is enforced in
-- app code (user_id scoping from the verified JWT). Enabling RLS with NO
-- anon/authenticated policy therefore denies all direct REST access without
-- touching the app. Deny-by-default posture; 021/023 follow the same pattern.
--
-- The 12 tables from the audit proposal:
ALTER TABLE entries                     ENABLE ROW LEVEL SECURITY;
ALTER TABLE entities                    ENABLE ROW LEVEL SECURITY;
ALTER TABLE entity_relations            ENABLE ROW LEVEL SECURITY;
ALTER TABLE deadlines                   ENABLE ROW LEVEL SECURITY;
ALTER TABLE projects                    ENABLE ROW LEVEL SECURITY;
ALTER TABLE insights                    ENABLE ROW LEVEL SECURITY;
ALTER TABLE extraction_edits            ENABLE ROW LEVEL SECURITY;
ALTER TABLE suppressed_project_entities ENABLE ROW LEVEL SECURITY;
ALTER TABLE rate_limit_usage            ENABLE ROW LEVEL SECURITY;
ALTER TABLE daily_llm_costs             ENABLE ROW LEVEL SECURITY;
ALTER TABLE ask_messages                ENABLE ROW LEVEL SECURITY;  -- re-assert 005 (drifted: never enforced live)
ALTER TABLE users                       ENABLE ROW LEVEL SECURITY;

-- intentions + subscriptions were ALREADY RLS-enabled in the live DB before
-- the lockdown (dashboard-created with RLS on; the 07/10 audit verified both
-- denied anon) but NO migration records that — asserted here for rebuild
-- fidelity, same reconstruction rationale as 018.
ALTER TABLE intentions                  ENABLE ROW LEVEL SECURITY;
ALTER TABLE subscriptions               ENABLE ROW LEVEL SECURITY;

-- Intentionally NO CREATE POLICY here: deny-all for anon/authenticated;
-- service-role continues to bypass. (user_memory 006, user_synthesis 019,
-- allowed_emails 021, access_requests 023 carry their own RLS in their own
-- migrations. entry_entities/entry_tags were MISSED by the 07/10 lockdown —
-- discovered still anon-readable 2026-07-15 — and are fixed in 025, NOT here:
-- this file reproduces the historical applied state.)
