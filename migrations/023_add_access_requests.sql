-- Migration 023: access_requests table (invite request intake)
--
-- WHAT: an intake box for strangers who hit the invite gate (InviteOnlyView /
-- signup card) and want in. The frontend posts to the unauthenticated backend
-- route POST /access-requests, which writes here with the service-role key.
--
-- GRANTING is manual: Karthik reads new rows in the Supabase dashboard and
-- copies chosen emails into `allowed_emails` (021). There is deliberately NO
-- approval workflow, no email, no admin UI (see docs/request-access.md).
--
-- SECURITY POSTURE (mirrors 021/022 — deny by default):
--   * RLS enabled.
--   * NO SELECT policy → anon/authenticated cannot read the table back. This
--     matters: the rows are inbound leads (emails + free-text notes); they must
--     not be world-readable the way the F1/P0 leak exposed user data.
--   * ONE anon INSERT policy, column-scoped to (email, note) via GRANT, so a
--     direct REST insert can only ever set those two fields; id/requested_at/
--     status fall to their defaults and cannot be spoofed (WITH CHECK pins
--     status='pending'). The backend path uses service-role and bypasses RLS.
--   * Unique index on lower(email) → duplicate requests collapse to one row
--     (the route swallows the conflict and stays idempotent — no enumeration).

CREATE TABLE IF NOT EXISTS access_requests (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  email        text NOT NULL,
  note         text,
  requested_at timestamptz DEFAULT now(),
  status       text DEFAULT 'pending'
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_access_requests_email_lower
  ON access_requests (lower(email));

ALTER TABLE access_requests ENABLE ROW LEVEL SECURITY;

-- Column-scoped insert privilege: anon may only supply email + note.
GRANT INSERT (email, note) ON access_requests TO anon;

-- The single permissive policy — insert only, and only pending rows.
-- No USING clause and no SELECT/UPDATE/DELETE policy ⇒ reads/edits denied.
CREATE POLICY "anon can submit access request"
  ON access_requests FOR INSERT TO anon
  WITH CHECK (status = 'pending');
