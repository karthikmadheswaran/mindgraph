# STATE — updated 2026-07-10 (Invite gating + RLS + request-access + rate-limit fix all live-verified; security audit closed except F3 key rotation. NEXT: launch / demand-test.)

Maintained per ADR-0001: fixed/done items are **deleted** (history lives in the changelog DB + git), never struck through. Keep ≤1.5K tokens.

## Now (≤3)
1. **Vertex AI prod migration** live (37fab70). Watch prod stability. (Conversation-route metering shipped — PR #5.)
2. **3.1-flash-lite (B) merged 15/06 (PR #2).** Remaining: Railway env flip → watch prod (Next-1). Details: changelog + `fullgrid_*` results.
3. **Launch / demand-test** (not another backend phase): put drift + reflection in front of strangers (3+ entries each); watch for the "that's the gap" reaction.

## Pins — shipped features + spec decisions that must hold
**Trial gating** (shipped 07/10, all migrations applied + live-verified 07/10). `allowed_emails` (021, RLS deny-all, service-role, 60s cache); enforced in `get_current_user` → 403 `{"detail":"invite_only"}`; founder seeded; fails open if table absent. RLS lockdown (022) — anon reads 0 rows on all tables. **Request access** (023): unauth `POST /access-requests` → `access_requests` (RLS deny-read, anon column-scoped insert, fail-safe); verified row-persists/idempotent/RLS/422; grant = manual dashboard copy into `allowed_emails` (`docs/request-access.md`).

**Rate limits** (024 + PR #23, live-verified 07/10). `try_rate_limit` RPC fixed (was a no-op — never rejected; now enforces). Keying = X-Forwarded-For first hop (707708e), **verified spoof-resistant on Railway** (forged XFF ignored; occasional Railway-internal `100.64.x` keying is a P3 note, no fix). **LAUNCH DECISION:** free entries **10/calendar-day (UTC)** (was 5/ISO-week — a keen demand-test user must never hit a week-long entry wall); asks 30/day, pro 100/200/day unchanged. `cost_cap.py` + 30/hr IP guard remain the abuse backstop; rolling-24h intentionally NOT built (`_window_start` is tumbling). Founder confirmed **pro** (won't hit the free cap).

**Drift + Home IA** (shipped 07/07). One backend-picked Home card, scored at read time (`GET /intentions/drift?pick=true`); Journal v2 = one scrollable life view, no sub-tabs.
- **Stickiness = 48h-unacted window** (not same-calendar-day); sticky re-serves don't restamp/re-log; acting rotates immediately.
- **Drift framing = po-card/Drifting pill, Home-only; "days quiet" is data, not framing.**
- **Self-judgment guard (HARD, pick-time only):** identity / "useless guy"-class intentions can never be the Home card; Journal still lists them.
- Deferred (do NOT pre-build): card ranking + dev-vs-life categorization; `resolved_at`/`dismissed_at` column; time-diff maturation; time-adverb `_NONCONTENT`; intention clustering (docs/designs/intention-clustering.md — trigger: user >15 pending); pick-score re-tune from `drift_card_served` telemetry once serves accumulate.

**Reflection (self-synthesis)** — SHIPPED 02/07 (`synthesis_engine.py`, migration 019). Per-user doc of non-obvious behavioural patterns from full journal text; first gift ≥ 5 entries. Home shows it only while unopened (capped 3); opened → lives in Journal → Patterns. `generate_patterns` retired.
- **Gift-level open gating is the ACCEPTED launch behavior** — do NOT build per-insight `opened_at` (needs a migration; out of scope).
- Deferred (do NOT pre-build): a scheduler for inactive-user regen; tune `REFLECTION_STALE_DAYS`(3)/`REFLECTION_MIN_ENTRIES`(5) once traffic shows cadence.

## Next (ordered)
1. **Flip B on prod** — Railway `ASK_GENERATION_MODEL=gemini-3.1-flash-lite` + `ASK_GENERATION_THINKING=minimal`. Rollback: delete both → reverts to `flash`. Then run the first-prod-reask check (Watching).
2. **Codebase Review 06-05 remaining critical:** sequential-blocking "parallel" retrieval (Notion `3769402f…`). (Metering findings shipped.)
3. **Edit + archive flows** (entries/deadlines/projects from Journal) — longstanding queued milestone.

## Known broken / degraded (open only)
- **🔴 P1 — rotate 2 Gemini/Google keys in git history** (commits 89c8d07, 35120fb; F3). Working tree is clean; history untouched per rules. **Oldest open item on the project; the only audit finding still open.**
- **F2 (P1) — HEAD-scrubbed 07/10** (PR #22): eval-output JSONs (`evals/results/*`, `*_evaluation_results.json`) untracked + gitignored. Eval-**script** fixtures (`eval_generation.py` et al) still carry real journal names — rewrite deferred, bundle with any F3 history decision. History not rewritten.
- **AI Studio prepay depleted — local LLM path dead (P3):** local `GEMINI_API_KEY` 429s; prod unaffected (Vertex). Force Vertex locally or top up.
- **Dedup-orphan empty entries — backfill pending (P2):** 9 completed entries have empty `cleaned_text`, all dedup-flagged; 1 real false positive. Backfill (do NOT run yet): re-embed, re-run `match_entries`, if sim ≤ 0.92 re-run the pipeline.
- **Dedup orphan rows — populate open (P2):** a TRUE duplicate still leaves an empty `completed` row (now hidden) that never advances `last_seen`. Fix: populate from the matched entry or don't persist it.
- **Cost-cap flat-estimate fallback (P2):** `record_cost` uses the Langfuse trace cost when available, else a fixed per-type estimate (`cost_cap.py`) that can under-count. Revisit if abuse appears.
- **CI needs a programmatic re-ask judge + fixed rubric (P1):** inline Pro judging dropped (quota); B-experiment batch judging non-reproducible. Candidate: flash-class judge + fixed rubric (`--no-judge` exists).
- **Stored past-event deadlines — cleanup pending (P2):** ~8 deadlines have `due_date` < source entry `created_at` (mis-extracted past activities, `status=missed`, never closeable). Open: bulk cleanup (do NOT run yet) — soft-delete where `due_date < source_entry.created_at` AND description is a completed-activity pattern; review 2 borderline rows first. (Delete/restore already shipped.)
- **Deadline HARD-zero (P3, residual):** `drop_past_event_deadlines` took the leak 5/5→0/5 but isn't a hard guarantee (English-morphology-bound; fails safe — never drops a real obligation). Do NOT extend with language rules — needs the model-based approach. Trigger: real present-tense/non-English traffic.
- **Vertex quota — pre-launch check (P3):** eval 429s were an eval-burst artifact, not a prod risk (`thinking_budget=0`; 429 → `status=error`, retryable). Pre-launch: read real Vertex QPM/TPM for `gemini-2.5-flash-lite`/`us-central1`. Scale trigger: a submission spike (no concurrency cap) → backoff / quota bump.
- **Stale deadline Ask eval case (P3):** `rag_test_cases.json` "deadlines for the end of May?" is `temporal`, scored on prose-entry F1 — encodes the old prose path, not the fixed structured-table one. Retire or convert to an answer-content assertion (cf. `eval_ask_deadlines.py`).
- Read-after-write lag on `ask_messages` can defeat loop detection under rapid sends (P2; not at human pace).
- Referenced-date indexing gap (Layer 3): date-mentioning entries invisible to temporal queries — needs `entry_referenced_dates` + a pipeline node (P2).
- **Minor (P3):** `ChatVertexAI` deprecation warning at boot (migrate `app/llm.py` Vertex branch before LangChain 4.0); `normalize_thinking_budget_eval.py:97` outdated `model=` kwarg (broken since ~23/05); deadline live eval stale April fixtures (F1 = scoring artifact); local `.env` UTF-8 BOM breaks `os.getenv` locally (prod fine); UI polish (desktop wide-layout space; deadline scroll styling).

## Pre-demand-test blockers (added 07/15 trial-readiness sweep)
- **🔴 Deploy the PostHog capture fix.** ALL backend events (drift_card_served, intention_resolved/dismissed, entry_submitted, rate_limit_hit, cost_cap_hit) were silently dropped in prod: posthog-python ≥6 changed `capture()` to keyword-only `distinct_id` and the old positional call errors *inside* the library. Fixed in `app/services/analytics.py` + `posthog==7.14.0` pin + regression `tests/test_analytics_capture.py`; prod (`22a180a9`) still runs the broken call.
- **Verify in Railway (can't be read from repo):** `POSTHOG_API_KEY` set (else events no-op with zero errors) and `DRIFT_THRESHOLD_DAYS=3` for the demand test — the code default is **14** (`intention_service.py:28`) and 3 appears nowhere in code.
- **Prod cleanup ready, founder-executed:** `docs/reports/prod-cleanup-2026-07-15.sql` (11 target users incl. 2 data-orphans of deleted auth users, 290 synthetic `public.users` rows, probe access-request; previews + FK-safe deletes, founder-guard). Cold-start audit: `docs/reports/cold-start-audit-2026-07-15.md` — no crashes/blanks; copy observations for founder; Ask "MEMORY · N ENTRIES" caps at 10 (page-size artifact, unfixed by design).
- **Migration 022 (RLS lockdown) file missing from `migrations/`** — applied in prod, referenced by STATE/021-history, but not committed (P3 repo hygiene).

## Watching (observation windows)
- **Reflection cadence:** confirm the debounced post-entry regen writes a first gift once a real user crosses 5 entries (only krithikb4u seeded).
- **First-prod-reask (after B flip):** pull a real multi-turn re-ask from Langfuse; confirm turn-2 acks + re-presents (not a redump). Watch Ask gen p95 vs the >25s alert.
- **Entity-gate advisory decision overdue (09/06 passed):** promote `question_entity_known` to active gating if false-positive rate < 1%, else tune.
