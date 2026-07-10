# Invite access — request intake & granting

MindGraph is invite-only during the closed demand-test. Two tables, both
admin-managed via the Supabase dashboard, no admin UI:

| Table | Migration | Purpose | Who writes |
|---|---|---|---|
| `allowed_emails` | 021 | the gate — email here ⇒ can use the app | you, dashboard only |
| `access_requests` | 023 | inbound leads from strangers who want in | app (service-role), via `POST /access-requests` |

## How a request arrives

1. A stranger signs up / logs in with a non-allowlisted email → backend
   `get_current_user` returns `403 {"detail":"invite_only"}` →
   `InviteOnlyView` renders. The signup card shows the same option.
2. They submit email + optional note through the inline "Request access" form.
3. `POST /access-requests` (unauthenticated, rate-limited 3/hour/IP) inserts a
   row into `access_requests` with `status='pending'`. Duplicate emails collapse
   silently (idempotent, no enumeration).

## How to grant (manual, ~30 seconds)

1. Supabase dashboard → **Table editor → `access_requests`**, sort by
   `requested_at desc`. Read the `email` + `note`.
2. Decide. To grant: **Table editor → `allowed_emails` → Insert row**, set
   `email` (lowercase) and a short `note` (e.g. "req 07/10, friend of X").
   The gate's in-process cache refreshes within 60s — no redeploy.
3. Optional bookkeeping: set the `access_requests` row's `status` to
   `granted` / `declined` so the queue stays readable.

That's it. There is deliberately **no** email notification and **no** approval
workflow — granting is a human reading a short list and copying an email.

## Security notes

- `access_requests` has RLS enabled with **no SELECT policy** — the anon key
  cannot read the table back (only a column-scoped INSERT of `email, note` is
  permitted). Verified at deploy time by the audit probe.
- The backend route fails safe: if migration 023 hasn't been applied yet, the
  insert error is captured to Sentry and the user still sees "received" (no
  500 during the deploy→apply window).
