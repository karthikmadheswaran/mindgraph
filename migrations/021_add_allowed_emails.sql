-- Migration 021: allowed_emails table (invite-only trial gating)
--
-- WHAT: email allowlist for the closed demand-test. Every authenticated API
-- request checks the verified JWT's email against this table (case-insensitive,
-- 60s in-process cache — see app/services/allowlist.py). Absent → 403
-- {"detail": "invite_only"}.
--
-- ADMIN-MANAGED ONLY: rows are added/removed via the Supabase dashboard.
-- There are deliberately NO API write paths and NO RLS policies — RLS is
-- enabled with zero policies, so anon/authenticated roles can neither read
-- nor write. The backend reads it with the service-role key (bypasses RLS),
-- same pattern as user_memory (006) / user_synthesis (019).
--
-- Emails are stored lowercase (enforced by trigger-free CHECK) so membership
-- is a simple lower(jwt_email) IN (...) test on the app side.

CREATE TABLE IF NOT EXISTS allowed_emails (
  email      text PRIMARY KEY CHECK (email = lower(email)),
  note       text,
  invited_at timestamptz DEFAULT now()
);

ALTER TABLE allowed_emails ENABLE ROW LEVEL SECURITY;
-- No policies on purpose: deny-all for anon/authenticated; service-role only.

-- Seed the founder account so the gate never locks out the admin.
INSERT INTO allowed_emails (email, note)
VALUES ('krithikb4u@gmail.com', 'founder')
ON CONFLICT (email) DO NOTHING;
