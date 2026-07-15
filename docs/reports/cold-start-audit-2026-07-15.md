# Cold-start audit — 2026-07-15 (pre-demand-test)

Scope: brand-new demand-test user, fresh account → request-access → first login →
0 entries → Home / Journal / Ask / Graph → entry #1 → revisit. Per ground rules:
crashes/errors/hard blanks fixed; ALL copy observations are report-only (founder
writes user-facing copy).

**Method + limits.** Live checks against prod (`https://rawtxt.in`, backend
commit `22a180a9` per `/health`) for every unauthenticated surface, plus the
unauth API. The authenticated 0-entry / 1-entry states were audited at code
level (all four surface components + their backend endpoints) and via the
frontend test suites (44/44 pass, 6 suites) — account creation / password login
is outside what the audit agent may do, so no live authed session was driven.
Screenshots unavailable in the audit browser; DOM text captured instead.

## Verdict

**No crashes, no 404s, no hard blanks, no infinite spinners found on any
surface at 0 or 1 entries. Nothing required a fix.** Every surface has an
explicit empty state, every fetch failure degrades to a handled state, and
every spinner has a terminating condition (Home's entry poll gives up after
200s with a toast). One wrong-stat bug and several copy observations are
listed for founder decision.

## Stage 1 — stranger arrives (live-verified on prod)

| Surface | What renders | Issues |
|---|---|---|
| `rawtxt.in` landing | Full static landing (React shell renders it in a full-viewport iframe at `/landing/` — looks blank to naive DOM text extraction but renders correctly; not a bug). Nav, hero, feature grid, CTAs all present. | None. Zero console errors. |
| `?view=auth` | Auth card: brand, "Your AI-powered journal", invite-only notice, Log in / Sign up tabs, email+password form. | None. |
| Sign up tab | Same card + "Not invited yet? Request access" link revealing the inline form (email + optional note). | None. |
| `POST /access-requests` (unauth) | Live-tested with synthetic email `coldstart-audit-20260715@example.com` → 200 `{"status":"received"}`. **This row is now in prod `access_requests` — included in the Task-4 cleanup script.** | None. |
| Post-signup, not yet allowlisted | Any API call 403s `invite_only` → global fetch-wrapper (`inviteGate.js`) fires → `InviteOnlyView`: explanation, request-access form pre-filled with the signed-in email, Log out. (Code-verified.) | None. |

Signup requires an email-confirmation click before first login
(`AuthView.js:26`) — expected Supabase behavior, but it is a real step in the
stranger funnel; worth remembering when walking testers through onboarding.

## Stage 2 — first login, 0 entries (code-audited)

| Surface | What renders at 0 entries | Crash risk found |
|---|---|---|
| **Home** | Greeting + composer; first-run promise card ("After a few entries, MindGraph starts noticing…") because `totalEntries < 3` and no drift card; Recent shows "Nothing yet. Start writing."; Noticed section absent (no drift pick — `pick_drift` returns `pick: null` on an empty pool; no unopened reflection). | None. Skeletons only while `recentEntries === null`; settled-count gate stops the promise card flashing. |
| **Journal** | All sections collapse (plate/patterns/intentions/entries each gated on content); single empty state: "Nothing here yet — write your first entry and it all fills in." | None. Snapshot-load failure exits the spinner (`loadingData` set false in catch). |
| **Ask** | Header "MEMORY · 0 ENTRIES", welcome empty state ("Write a thought or ask a question to get started"), composer with Ask/Journal toggle. Memory panel: "No saved memory yet…" empty state. | None. Conversation fetch has a double fallback (`/ask/history`, then `[]`). Asking with 0 entries is safe server-side: every Ask-pipeline retrieval branch is empty-tolerant (`(no entities yet)` / `(no recent entries)` placeholders, `entries = []` fallbacks) — the LLM answers from nothing rather than 500ing. |
| **Graph** | "Your connected mind" header + `KnowledgeGraph` with the empty note "Keep journaling about projects and people to grow this map." (`hasData` requires >1 node). | None. All four fetches must succeed or a single handled error state shows; no unbounded spinner. |

Backend cold-start endpoints verified null-safe: `GET /insights/synthesis` with
no row → `{data: null}`; `GET /intentions/drift?pick=true` with no intentions →
`{pick: null}`; `/entities`, `/deadlines`, `/entity-relations` return empty
lists.

## Stage 3 — entry #1 and revisit (code-audited)

- Submit → `POST /entries/async` → DispatchReveal processing state (rotating
  status phrases) → poll `entries/{id}/status` every 2.5s. **Bounded**: 80
  polls (200s) then a gentle toast ("Processing is taking a while. Check back
  soon.") and return to idle — no infinite spinner. Pipeline `status=error` →
  error toast + idle. `dispatch_payload` null-safety throughout
  (`dispatch?.discoveries`, reveal gated on `phase === "revealing" && dispatch`).
- Home after entry #1: promise card persists (< 3 entries), Recent shows the
  entry. Journal: Entries section appears with 1 row; other sections still
  collapsed. Ask: "MEMORY · 1 ENTRIES" (grammar note below). Graph: nodes appear
  once entities extracted; note requires >1 node.
- Reflection ("gift") correctly absent until 5 entries (`REFLECTION_MIN_ENTRIES`).
- Drift card correctly absent: a brand-new user's intentions have
  `days_since < threshold`, so no drift pick — witness surfaces stay quiet, as
  designed.

## Bug (not fixed — founder call; not a crash/blank)

1. **Ask header entry count caps at 10.** `AskView.js:606-613` sets the stat
   from `(data.entries || []).length` of a default `GET /entries` — backend
   default `page_size=10` (`main.py:145`). Any user with >10 entries sees
   "MEMORY · 10 ENTRIES" forever. Fix is one line (use `data.total_count`),
   deliberately not applied under today's verification-only rules.

## Copy observations (REPORT ONLY — numbered for founder review)

1. Home nudge: "What's been on your mind that you **haven't** said out loud?" —
   literal "you haven't…" construction, though the tone is invitational rather
   than guilt-tinged. Founder judgment call.
2. Home empty Recent: "Nothing yet. **Start writing.**" — bare imperative;
   mildest possible manager-voice.
3. Journal project meta: "**Stalled** · N days quiet" (`Journal.js:85`) — the
   "days quiet" data framing is per spec, but the "Stalled" label is a judgment
   word on a Journal surface.
4. Ask suggestion pill: "What have I been **avoiding**?" — self-judgment-adjacent
   phrasing, though it's a question the user chooses to ask.
5. Graph empty note: "**Keep journaling** about projects and people to grow this
   map." — imperative, gentle.
6. Ask header grammar: "MEMORY · **1 ENTRIES**" at exactly one entry.
7. Landing copy states the Shiny Object Detector flags "**after 14 days** of
   silence" — if the demand test runs `DRIFT_THRESHOLD_DAYS=3`, the landing
   promise and observed behavior will disagree.
8. Witness-tone positives worth keeping: first-run promise card, "Nothing here
   yet — write your first entry and it all fills in.", no streaks/red urgency
   anywhere on the four surfaces.

## Side observation (security, not cold-start)

`MemoryPanel` (`AskView.js:456-471`) renders memory markdown via
`dangerouslySetInnerHTML` with regex-only inline formatting (no HTML escaping).
Content is LLM-generated from the user's own entries, so exposure is
self-XSS-shaped and low — but worth a sanitizer pass someday.
