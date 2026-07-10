# MindGraph Security & Privacy Audit — July 2026

**Date:** 2026-07-10
**Scope:** Pre-trial hardening for a closed demand-test (15–20 invited strangers).
**Branch:** `feat/invite-allowlist-and-audit`
**Deployed SHA at audit time:** `9b50040f`
**Repo posture:** PUBLIC. Everything here is written assuming the repo, the
frontend bundle, and the anon key are world-readable.

---

## TL;DR

One **P0** dominates everything else: **Supabase Row-Level Security is not
effective on the core user-data tables, so the public `anon` key reads every
user's journal directly from the Supabase REST API — bypassing the backend
entirely.** Verified live against prod: the anon key returned 148 real entries
across multiple distinct user IDs, including raw `cleaned_text` (e.g. a
therapist-appointment reminder).

**The invite allowlist shipped in this PR does NOT close this hole.** The
allowlist gates the *backend API*; the data leak is a *direct-to-database* read
that never touches the backend. Both must be fixed for the trial to be safe.
The RLS fix is a schema change and — per this session's safety rules — is
**reported, not applied**. SQL is provided below and needs one human apply.

---

## Findings

| ID | Sev | Finding | Status |
|----|-----|---------|--------|
| F1 | **P0** | RLS ineffective on core tables → public anon key reads all users' journal data directly from Supabase REST | **needs-human** (schema change; SQL below) |
| F2 | P1 | Real personal journal content in committed eval-result JSONs and fixtures | **needs-human** (SHA-stamped history; scrub-vs-gitignore decision) |
| F3 | P1 | Historical `.env` with live-format API keys in git history (2 commits) | **needs-human** (rotate, then decide on history) |
| F4 | P2 | `PyJWT 2.11.0` (auth verification path) has known advisories; fix in 2.13.0 | **fixed-in-PR** (bumped → 2.13.0, 2026-07-10) |
| F5 | P2 | `langgraph` / `langgraph-checkpoint` pinned at CVE-affected versions | **fixed-in-PR** (bumped); `langchain` CVE-2026-55443 needs-human (langgraph-matrix jump) |
| F6 | P3 | `aiohttp 3.13.3` (transitive) carries many CVEs; pin constrained by langchain | accepted-risk (version-locked) |
| F7 | P3 | No invite-only gate existed before this PR (any Supabase signup got full API access) | **fixed-in-this-PR** |
| F8 | P3 | `POST /payments/verify` returns `str(e)` in a 400 detail | accepted-risk (Razorpay validation text; no stack/SQL) |

Clean / verified-good (no action): CORS locked to rawtxt.in + localhost with no
wildcard; Swagger `/docs` + `/openapi.json` public but carry **no** secrets in
schema examples; `.env*` and all local secret files are gitignored and untracked
(tracked-tree secret scan = clean); no `DEBUG=true` in prod config; every
Vertex/LLM-invoking route is covered by both `check_cost_cap` and a rate-limit
guard; every authenticated route now inherits the allowlist gate via the single
`get_current_user` choke point.

---

## F1 (P0) — RLS ineffective; anon key reads all user data

**RLS verified closed 2026-07-10 — anon reads return zero rows on all tables.**

### What
The frontend anon key (`role: anon`, published in the JS bundle and referenced
in `README.md` / `mindgraph-frontend/src/supabaseClient.js` — this is normal;
anon keys are *designed* to be public) can read core tables directly:

```
GET {SUPABASE_URL}/rest/v1/entries?select=cleaned_text&limit=1
Authorization: Bearer <anon key>
→ 200  [{"cleaned_text": "create a reminder for 2026-04-08 where I have to meet a therapist at ..."}]
```

Anon-readable (verified live, returned real rows): `entries`, `entities`,
`entity_relations`, `deadlines`, `projects`, `insights`, `ask_messages`,
`rate_limit_usage`, `daily_llm_costs`, `extraction_edits`, `users`,
`suppressed_project_entities`. `entries` alone exposed **148 rows across
multiple distinct `user_id`s**.

Correctly protected (anon returned 0 rows — RLS working): `user_memory` (006),
`user_synthesis` (019), `intentions`, `subscriptions`.

### Why it happens
The app connects with the **service-role** key, which bypasses RLS, and enforces
per-user isolation purely in application code (`.eq("user_id", ...)`). That
protects the *backend* path, but leaves the tables themselves world-readable to
anyone holding the public anon key. RLS was only ever enabled by migration on
four tables — and even `ask_messages` (migration 005 defines an
`auth.uid() = user_id` policy) returns rows to anon, so **migration 005's RLS
block appears never to have been applied to the live DB** while 006/019 were —
an environment/migration-drift inconsistency in its own right.

### Blast radius
Any person on the internet — including any reader of this public repo — can pull
every user's complete journal, entities, deadlines, and Ask history. For a
journal product this is the maximum-severity privacy failure. The invite
allowlist does **not** mitigate it (see TL;DR).

### Recommended fix (human to apply — schema change, not applied per rules)
Enable RLS + a deny-by-default posture on every user-data table. Because the
backend uses the service-role key (bypasses RLS), enabling RLS **with no
permissive anon/authenticated policy** is safe for the app and closes the leak.
Proposed migration `022` (review before applying):

```sql
-- Migration 022: enable RLS on all user-data tables (close anon read exposure).
-- Backend uses the service-role key (bypasses RLS), so enabling RLS with NO
-- anon/authenticated policy denies direct REST access without touching the app.
-- Re-assert 005's ask_messages RLS (drifted: not enforced in live DB).
ALTER TABLE entries                    ENABLE ROW LEVEL SECURITY;
ALTER TABLE entities                   ENABLE ROW LEVEL SECURITY;
ALTER TABLE entity_relations           ENABLE ROW LEVEL SECURITY;
ALTER TABLE deadlines                  ENABLE ROW LEVEL SECURITY;
ALTER TABLE projects                   ENABLE ROW LEVEL SECURITY;
ALTER TABLE insights                   ENABLE ROW LEVEL SECURITY;
ALTER TABLE extraction_edits           ENABLE ROW LEVEL SECURITY;
ALTER TABLE suppressed_project_entities ENABLE ROW LEVEL SECURITY;
ALTER TABLE rate_limit_usage           ENABLE ROW LEVEL SECURITY;
ALTER TABLE daily_llm_costs            ENABLE ROW LEVEL SECURITY;
ALTER TABLE ask_messages               ENABLE ROW LEVEL SECURITY;  -- re-assert
ALTER TABLE users                      ENABLE ROW LEVEL SECURITY;
-- Intentionally NO CREATE POLICY: deny-all for anon/authenticated;
-- service-role continues to bypass. Verify the app still works end-to-end in a
-- staging project before prod, then re-run the anon probe (must return 401/empty).
```

**Verification after apply:** re-run the anon REST probe against each table —
every one must return `[]` or 401. (Probe script kept out of the repo; see the
audit session transcript.)

---

## F2 (P1) — Real personal content in committed eval fixtures/results

Founder's real journal-derived content is committed. This is not a *secret*, but
it is personal data in a public repo, and it was explicitly in scope to find.

- **Answer text (real journal-derived):** `evals/rag_evaluation_results.json`,
  `evals/rag_evaluation_results_v2.json`, `evals/generation_evaluation_results.json`,
  and result JSONs with `"answer"` fields:
  `evals/results/rag_eval_pipeline_reroute_*.json`,
  `rag_eval_post_backfill_tasktype_*.json`, `rag_eval_pre_backfill*.json`,
  `rag_eval_sweep_060/062/065/070_*.json`.
- **`cleaned_text` (raw entry text):**
  `evals/results/trace_inspect_83cd7552d62b160c20d63ad1948a9cc1.json` (real names:
  "naveen marriage … erode"), `evals/results/extract_relations_thinking_budget_*.json`.
- **Test fixtures with plausibly-real content:** `tests/test_store_node.py`
  (knee surgery, medicines, ProjectX), `tests/test_classify.py`,
  `evals/rag_test_cases.json` (names: Aditi, Vivek, Naveen, Sneha, Anjali; places:
  Erode), `docs/architecture/journal-agent-architecture-plan.md` (headaches, "call mom").
- No stray real emails found in fixtures (only `karthik@rawtxt.in` /
  `test@rawtxt.in` placeholders in public marketing HTML, and
  `krithikb4u@gmail.com` in a script usage example).

**Blocked by rule 2** (never modify `evals/results/`). These are SHA-stamped eval
provenance. Recommended human decision: (a) scrub-and-recommit the top-level
`evals/*.json` answer files + fixtures with synthetic content, and (b) decide
scrub-vs-gitignore for the `evals/results/*.json` set together (they are eval
history; losing them breaks `compare.py` provenance). No files were deleted or
modified.

---

## F3 (P1) — API keys in git history

`.env` was committed in two historical commits before being removed:

| Commit | Date | Keys (redacted) |
|--------|------|-----------------|
| `89c8d073` | 2026-03-25 | `GEMINI_API_KEY=AIzaSyDA9T…`, `GOOGLE_API_KEY=AIzaSyDA9T…`, `SUPABASE_KEY=sb_publish…` |
| `35120fb2` | 2026-03-23 | `GEMINI_API_KEY=AIzaSyBiUO…`, `GOOGLE_API_KEY=AIzaSyBiUO…`, `SUPABASE_KEY=sb_publish…` |

`.env` was removed from tracking in `55da085` / `8587737` and is now gitignored;
the **current tracked tree is clean** (dedicated gitleaks scan of `git archive
HEAD` = no leaks). A PostHog key also appears in a commit *message* (`01a4861`),
not in tracked file content.

**Blocked by rule 1** (never rewrite history / force-push). Recommended human
actions, in order: (1) **rotate** the two Gemini/Google API keys
(`AIzaSyDA9T…`, `AIzaSyBiUO…`) — treat as compromised since they are in public
history; the CLAUDE.md note says Supabase keys were already rotated once. (2)
Then decide together whether to rewrite history (BFG/`git filter-repo`) or accept
it post-rotation. Nothing was rotated, rewritten, or force-pushed.

---

## F4/F5/F6 — Dependencies (criticals only; no mass-upgrade)

Reported from `pip-audit` / `npm audit`. **Targeted bumps applied in the
request-access PR** (2026-07-10); the rest stay constrained by the langchain
matrix or are accepted-risk.

- **F4 (P2, auth-relevant) — FIXED in PR:** `PyJWT 2.11.0 → 2.13.0`, clearing
  PYSEC-2026-120/175/176/177/178/179. This is the library verifying every
  Supabase JWT in `app/auth.py`, so it was the highest-value bump. Full auth +
  rate-limit test set green after the bump.
- **F5 (P2) — PARTIALLY FIXED in PR:** `langgraph 1.0.9 → 1.0.10` (PYSEC-2026-83)
  and `langgraph-checkpoint 4.0.0 → 4.1.1` (CVE-2026-48775) applied. `langsmith
  0.7.6` is **not** flagged by pip-audit (no action). **`langchain` (1.2.10,
  CVE-2026-55443, fix 1.3.9) NOT taken** — 1.3.9 requires `langgraph>=1.2.4`,
  which conflicts with the pinned `langgraph 1.0.10`; taking it would force a
  langgraph 1.2.x jump + langchain-core re-verify (a mass upgrade, out of the
  targeted-bump scope). **needs-human:** bump langchain+langgraph together and
  re-run the eval matrix, or wait for the constraint to relax.
- **F6 (P3, accepted-risk):** `aiohttp 3.13.3` transitive, ~21 CVEs, but the pin
  is locked by `langchain-google-genai 4.2.1`. Revisit when that constraint lifts.
  (`python-dotenv 1.2.1`, `python-multipart 0.0.22` also flagged; low-severity,
  left for the same constraint-driven pass.)
- **npm:** 58 advisories, 1 critical (`picomatch` ReDoS) — all in the CRA
  dev/build toolchain (`react-scripts`), not shipped to users. Accepted-risk for
  the trial; a future CRA-eject/Vite migration clears most.

---

## F8 (P3, accepted-risk) — Error detail in payments route

`app/payments/router.py:31` returns `detail=str(e)` in a 400. The exception is
Razorpay order-creation validation, not a DB/stack trace, so leak surface is
low. Elsewhere errors are clean (`main.py:494` echoes a user-supplied timezone
string only). Left as-is; tighten to a generic message if payments expand.

---

## Route → Auth → Scope table

Auth = passes through `get_current_user` (now allowlist-gated). Scope = query is
filtered by `user_id` in application code. All authenticated routes are
user-scoped via service-role + `.eq("user_id", …)`; **note F1** — DB-level
isolation is *not* enforced, only app-level.

| Route | Auth | User-scoped | Notes |
|-------|------|-------------|-------|
| `GET /health` | no | n/a | Intentionally open; exposes only short commit SHA. Must stay open. |
| `POST /entries` | yes | yes | rate-limit + cost-cap |
| `GET /entries` | yes | yes | |
| `POST /entries/stream` | yes | yes | rate-limit + cost-cap |
| `POST /entries/async` | yes | yes | rate-limit + cost-cap |
| `GET /entries/filter-options` | yes | yes | |
| `GET /entries/{id}/status` | yes | yes | |
| `DELETE /entries/{id}` | yes | yes | soft delete |
| `POST /entries/{id}/edits` | yes | yes | |
| `GET /search` | yes | yes | |
| `POST /ask` | yes | yes | rate-limit + cost-cap |
| `GET /ask/history` | yes | yes | |
| `GET /ask/memory` | yes | yes | |
| `POST /ask/new-session` | yes | yes | |
| `GET /conversations/messages` | yes | yes | |
| `POST /conversations/messages` | yes | yes | cost-cap + rate-limit in-handler (mode-branched; kill-switch env) |
| `GET /conversations/messages/{id}/status` | yes | yes | |
| `GET /deadlines` | yes | yes | |
| `PATCH /deadlines/{id}/status` | yes | yes | |
| `PATCH /deadlines/{id}/date` | yes | yes | |
| `DELETE /deadlines/{id}` | yes | yes | soft delete |
| `POST /deadlines/{id}/restore` | yes | yes | |
| `GET /projects` | yes | yes | |
| `PATCH /projects/{id}/status` | yes | yes | |
| `DELETE /projects/{id}` | yes | yes | |
| `GET /progress` | yes | yes | |
| `GET /entities` | yes | yes | |
| `GET /entity-relations` | yes | yes | |
| `GET /intentions/drift` | yes | yes | |
| `POST /intentions/{id}/resolve` | yes | yes | |
| `POST /intentions/{id}/dismiss` | yes | yes | |
| `GET /insights` · `/weekly` · `/patterns` · `/forgotten` · `/synthesis` | yes | yes | |
| `POST /insights/synthesis/open` | yes | yes | |
| `GET /stats/dashboard` | yes | yes | |
| `GET /users/me/timezone` | yes | yes | |
| `PATCH /users/me/timezone` | yes | yes | |
| `POST /payments/create-order` | yes | yes | see F8 |
| `POST /payments/verify` | yes | yes | see F8 |

No unauthenticated data route found. The only open endpoint is `/health`
(by design).

---

## Test results vs baseline

- **Frontend suite: 44 passed / 0 failed** — matches the 44P baseline (my App.js
  intercept + AuthView copy did not regress it).
- **New backend allowlist tests: 10 passed / 0 failed** (`tests/test_allowlist.py`).
- **Rest of backend suite:** the pre-existing environmental failures documented
  in `STATE.md` (local `GEMINI_API_KEY` prepay depleted → 429 on any live-LLM
  test) are present identically on clean `main` (verified via `git stash`).
  8 collection errors + 10 store-node/project-matching failures are **all**
  this environmental cause, **none introduced by this PR**. The mockable subset
  runs 107 passed + my 10 = 117, with 0 new failures.

---

## What this PR shipped (Workstream A)

- Migration `021_add_allowed_emails.sql` — `allowed_emails(email PK, note,
  invited_at)`, RLS enabled with **no policies** (service-role only), founder
  `krithikb4u@gmail.com` seeded. **Applied** (additive/low-risk, per rule 4).
- `app/services/allowlist.py` — case-insensitive membership, 60s in-process
  cache, fail-open-with-loud-log if the table is missing/unreachable (so a
  deploy-before-migration can't lock the founder out).
- `app/auth.py` — single choke point: `get_current_user` now 403s
  `{"detail":"invite_only"}` for non-allowlisted verified emails. `/health` and
  in-process schedulers are unaffected (they don't depend on `get_current_user`).
- Frontend — global `invite_only` 403 intercept (`utils/inviteGate.js`) →
  full-screen `InviteOnlyView` with logout; one line of invite-only copy on the
  auth card. Existing design tokens only.
- `tests/test_allowlist.py` — 10 tests (membership, case-insensitivity, TTL
  refetch, stale-cache-on-error, fail-open, 403 gate).

---

## Human action queue (prioritized)

1. ~~**[P0] Apply RLS migration 022** (F1)~~ — **DONE** (applied + verified closed
   2026-07-10; anon reads return zero rows on all tables).
2. **[P1] Rotate** the two historical Gemini/Google API keys (F3), then decide on
   history rewrite. *(Still open — the only remaining trial-blocker-class item.)*
3. **[P1] Decide** scrub-vs-gitignore for personal content in `evals/` (F2).
   *Partially addressed 2026-07-10:* `evals/results/` is now gitignored (no new
   result JSONs) and the `rag_test_cases.json` input fixture was scrubbed to a
   synthetic persona. Remaining human call: existing committed result JSONs in
   history (scrub-vs-leave).
4. ~~**[P2] PyJWT + langgraph bumps** (F4/F5)~~ — **DONE** 2026-07-10 (PyJWT 2.13.0,
   langgraph 1.0.10, langgraph-checkpoint 4.1.1). Remaining: `langchain`
   CVE-2026-55443 needs a coordinated langgraph 1.2.x jump (F5).
5. **[NEW] Apply migration 023** (`access_requests`) via the Supabase dashboard —
   the request-access route fails safe until it exists, but requests aren't
   stored until applied. SQL in the PR / report.
