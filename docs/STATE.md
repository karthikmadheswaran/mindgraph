# STATE — updated 2026-07-22 (commit 099e09e — signup invite-gate + final copy PUSHED; backend auto-deploying, verify `/health` = 099e09e8. NEXT: founder — manual FRONTEND redeploy, then SMTP/hook/cleanup below, then demand-test.)

Maintained per ADR-0001: fixed/done items are **deleted** (history lives in the changelog DB + git), never struck through. Keep ≤1.5K tokens.

## Now (≤3)
1. **Vertex AI prod migration** live (37fab70). Watch prod stability.
2. **3.1-flash-lite (B) merged 15/06 (PR #2).** Remaining: Railway env flip → watch prod (Next-1).
3. **Launch / demand-test:** put drift + reflection in front of strangers (3+ entries each); watch for the "that's the gap" reaction.

## Founder actions before invites (all founder-only, 07/22)
- **🔴 Manually redeploy the FRONTEND service in Railway** — ships signup UI + copy (099e09e), Ask entry-count fix (77df89b), Patterns v1 UI (dfb7c7a); prod still serves `main.1be98b0b.js`; pushes don't trigger frontend (P3 below). Verify: bundle hash changes. Backend deploys from the 07/22 push — verify `/health` commit = 099e09e8.
- **Custom SMTP in Supabase Auth settings** — built-in quota blocks ALL auth email (confirmations, resets) at ~2 sends/hr; hit live 07/22 (`over_email_send_rate_limit`).
- **Before-User-Created auth hook** (Supabase dashboard) checking `allowed_emails` — closes the direct-to-GoTrue orphan hole (anon key is public; the backend gate only covers the app's signup path).
- **Verify in Railway:** `POSTHOG_API_KEY` set (else events no-op silently) and `DRIFT_THRESHOLD_DAYS=3` — code default is **14** (`intention_service.py:28`); 3 appears nowhere in code.
- **Execute prod cleanup:** `docs/reports/prod-cleanup-2026-07-15.sql` (11 target users, 290 orphaned synthetic `public.users` rows; previews + FK-safe deletes + founder-guard) **+ 07/22's `testemailforrequest@gmail.com` orphan** (signed up unconfirmed; requested access under the different spelling `testemailforrequestaccess@`). Copy observations: `docs/reports/cold-start-audit-2026-07-15.md`.

## Pins — shipped features + spec decisions that must hold
**Trial gating** (07/10, live-verified). `allowed_emails` (021, RLS deny-all, service-role, 60s cache) enforced in `get_current_user` → 403 `invite_only`; founder seeded; fails open if table absent. RLS lockdown 022 (file reconstructed 07/15) + 025 (join tables, verified 07/20) — anon reads 0 rows on ALL tables. **Request access** (023): unauth `POST /access-requests` → deny-read table, anon column-scoped insert; grant = manual dashboard copy into `allowed_emails` (`docs/request-access.md`). **Signup gated server-side** (07/22): `POST /auth/signup` checks the allowlist BEFORE any GoTrue call (403 `not_invited`, 5/hr/IP, fail-open logs "FAILING OPEN"); AuthView proxies signup and flips to request-access on `not_invited`.

**Rate limits** (024 + PR #23, live-verified). `try_rate_limit` enforces (was a no-op). Keying = XFF first hop (707708e), spoof-resistant on Railway (`100.64.x` keying = P3, no fix). **LAUNCH DECISION:** free entries **10/calendar-day (UTC)**; asks 30/day; pro 100/200 unchanged. `cost_cap.py` + 30/hr IP guard backstop; rolling-24h intentionally NOT built. Founder = pro.

**Drift + Home IA** (07/07). One backend-picked Home card (`GET /intentions/drift?pick=true`); Journal v2 = one scrollable view.
- Stickiness = 48h-unacted window; sticky re-serves don't restamp/re-log; acting rotates immediately.
- Drift framing Home-only; "days quiet" is data, not framing.
- **Self-judgment guard (HARD, pick-time only):** identity-judgment intentions never become the Home card; Journal still lists them.
- Deferred (do NOT pre-build): card ranking/categorization; `resolved_at`/`dismissed_at`; time-diff maturation; `_NONCONTENT`; clustering (trigger: >15 pending); pick-score re-tune from `drift_card_served` telemetry.

**Reflection (self-synthesis)** — 02/07 (`synthesis_engine.py`, 019). Per-user pattern doc; first gift ≥ 5 entries; Home shows unopened only (cap 3) → then Journal → Patterns. Gift-level open gating is ACCEPTED launch behavior — no per-insight `opened_at`. Deferred: inactive-regen scheduler; tune `REFLECTION_STALE_DAYS`(3)/`MIN_ENTRIES`(5).

**Patterns v1 (founder-gated, 07/20)** — `docs/designs/graph-v2-patterns.md` committed; components 1-3 live in Journal → Patterns: attention mix (`entry_tags` weekly, first frontend use), gravity top-5 (30d vs prior window), drift ledger (reuses non-pick drift read path + existing resolve/dismiss; pick-mode untouched, regression-locked). Gate = `PATTERNS_ENABLED` env (default OFF) OR founder id — backend 404s `/patterns/*`, frontend renders nothing (`patternsGate.js`); trial users see zero difference. `patterns_viewed` + `graph_viewed` events added. Components 4-5 (communities, surprise edges) DEFERRED per doc. UI needs the manual frontend redeploy (blocker above) to appear in prod.

## Next (ordered)
1. **Flip B on prod** — Railway `ASK_GENERATION_MODEL=gemini-3.1-flash-lite` + `ASK_GENERATION_THINKING=minimal`; rollback = delete both. Then first-prod-reask check (Watching).
2. **Codebase Review 06-05 remaining critical:** sequential-blocking "parallel" retrieval (Notion `3769402f…`).
3. **Edit + archive flows** (entries/deadlines/projects from Journal).

## Known broken / degraded (open only)
- **🔴 P1 — rotate 2 Gemini/Google keys in git history** (89c8d07, 35120fb; F3). Oldest open item; the only audit finding still open.
- **F2 (P1):** eval-output JSONs untracked+gitignored (PR #22); eval-**script** fixtures still carry real journal names — bundle rewrite with the F3 history decision.
- **Local LLM path dead (P3):** `GEMINI_API_KEY` 429s (prepay depleted); prod on Vertex unaffected. Force Vertex locally or top up.
- **Dedup-orphan empty entries (P2):** 9 completed rows with empty `cleaned_text`. Backfill (do NOT run yet): re-embed → `match_entries` → re-pipeline if sim ≤ 0.92.
- **Dedup orphan rows (P2):** a TRUE duplicate leaves a hidden empty `completed` row that never advances `last_seen` — populate from the match or don't persist.
- **Cost-cap flat-estimate fallback (P2):** `record_cost` under-counts without a Langfuse trace cost. Revisit if abuse appears.
- **CI re-ask judge (P1):** needs flash-class judge + fixed rubric (`--no-judge` exists); batch judging non-reproducible.
- **Stored past-event deadlines (P2):** ~8 rows `due_date` < source-entry `created_at`, never closeable. Bulk soft-delete drafted (do NOT run yet; review 2 borderline rows first).
- **Deadline HARD-zero (P3):** `drop_past_event_deadlines` 5/5→0/5 but English-morphology-bound (fails safe). Needs model-based approach; trigger: present-tense/non-English traffic.
- **Vertex quota (P3):** pre-launch, read real QPM/TPM for `gemini-2.5-flash-lite`/`us-central1`; submission spike → backoff/quota bump.
- **Stale deadline Ask eval case (P3):** `rag_test_cases.json` end-of-May case encodes the old prose path — retire or convert (cf. `eval_ask_deadlines.py`).
- Read-after-write lag on `ask_messages` can defeat loop detection under rapid sends (P2).
- Referenced-date indexing gap (P2): date-mentioning entries invisible to temporal queries — needs `entry_referenced_dates` + pipeline node.
- **Railway frontend auto-deploy dead (P3):** pushes never rebuild the frontend service — src-only (77df89b) AND Dockerfile-touch (56f4f35) both ignored; backend redeploys fine. No `railway.json` in repo (config is dashboard-side). Fix the watch path / auto-deploy in the dashboard, else every frontend change silently needs a manual redeploy.
- **Minor (P3):** `ChatVertexAI` deprecation at boot; `normalize_thinking_budget_eval.py:97` broken `model=` kwarg; stale April deadline-eval fixtures; local `.env` UTF-8 BOM breaks `os.getenv`; UI polish (wide-layout space; deadline scroll styling).

## Watching (observation windows)
- **Signup gate first prod exercise:** after both deploys, next stranger signup should 403 `not_invited` → card flip, zero new `auth.users` orphans; watch for the "ALLOWLIST UNREACHABLE — FAILING OPEN" ERROR log (should never fire).
- **Reflection cadence:** confirm the debounced post-entry regen writes a first gift once a real user crosses 5 entries (only krithikb4u seeded).
- **First-prod-reask (after B flip):** pull a real multi-turn re-ask from Langfuse; confirm turn-2 acks + re-presents. Watch Ask gen p95 vs the >25s alert.
- **Entity-gate advisory decision overdue (09/06):** promote `question_entity_known` to active gating if false-positive rate < 1%, else tune.
- **PostHog first live events:** drift_card_served / intention_resolved / intention_dismissed should appear once real usage resumes (fix live 5d2c97f2; needs `POSTHOG_API_KEY` in Railway).
