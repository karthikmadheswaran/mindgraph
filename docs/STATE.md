# STATE — updated 2026-06-15 (commit 5f5d6da)

Maintained per ADR-0001: fixed/done items are **deleted** (history lives in the changelog DB + git), never struck through. Keep ≤1.5K tokens.

## Now (≤3)
1. **Vertex AI prod migration just landed** (37fab70 + e2f8a4a; IAM 403 on `mindgraph-vertex` SA fixed 10/06 by granting `roles/aiplatform.user`). Watch prod stability for a few days.
2. **Metering PR open — fixed-pending-merge, DO NOT MERGE pending review (15/06, `fix/meter-conversation-routes`).** Closes both 05/06 Critical items: (a) tier mismatch — read-time alias `{"paid":"pro"}` in `tier_service` so paying users get pro limits (DB keeps `paid`; pre-deploy query: 309 users all `free`, no paid yet); (b) the unmetered `/conversations/messages` — metered **inside** the handler (deps can't branch on body mode): ask → `ask_rate_limit`+`check_cost_cap`+**`record_cost`** (ask-mode was triply unmetered: no limit/cap/cost-recording, bypassing `ask_service.ask()`; frontend sends all chat Asks here, `/ask` is fallback-only), journal → `entry_rate_limit`+`check_cost_cap` (cost already recorded downstream). Free asks 20→30. All behind `METER_CONVERSATION_ROUTES` (default ON) — Railway kill switch, no redeploy. Regression test (`test_conversation_metering.py`) drives the real route via TestClient, confirms the in-handler IP guard fires. Hermetic tests green.
3. **3.1-flash-lite (B) accepted — merge pending (11/06, `eval/multiturn-ask-harness`).** B (3.1-flash-lite, thinking_level=minimal, generation node only): reask transforms 13/15, judge mean 4.47 (0.03 under the 4.5 bar), overlap 0.286 vs A 0.487; C (low) fails (3.2). **External concordance audit** (gemini-3.1-pro-preview, 12 blind stratified cases, new seed) = **12/12 pass/fail agreement → external concordance confirmed (12/12)**. **clarifier_commit pre-check 15/15 PASS.** **Full 33-case run (Vertex) vs re-judged 85adc57 baseline, SAME fixed rubric: 32/33 vs 24/33 (+8); reask_loop 0→4/5, clarifier_commit 2→5/5, zero regressions, negatives hold → clears the ±4 noise band.** (Re-judging both neutralized the original Pro confounds: baseline reask 3/5 was trailing-Q luck → 0/5; want_all 2/5 was judge-noise → 5/5.) **Merged to main 15/06** (PR #2, merge `5f5d6da`; `cfaca4c`+`422df32` now on main). **Remaining: Railway env flip → watch prod** (Next-1). **Cost:** generation node $0.0008→$0.0018/conv measured (~2.25×); Batch API (−50%) for eval/offline; context caching ($0.025/M) a post-launch offset for the static prompt prefix. Results: `fullgrid_compare_B_vs_85adc57_*`, `concordance_audit_e7ef0b8e6ac3_*`, `clarifier_precheck_judged_*`, `blindjudge_reask_ABC_*`.

## Next (ordered)
1. **Flip B on prod** — set Railway env `ASK_GENERATION_MODEL=gemini-3.1-flash-lite` + `ASK_GENERATION_THINKING=minimal` (gated on the 15/06 merge — satisfied). Rollback: delete both vars → reverts to `flash` (gemini-2.5-flash-lite, thinking_budget=0). Then run the first-prod-reask check (Watching).
2. Route "list my deadlines"-class Ask queries through structured `/deadlines` data instead of journal prose (P1 — `retrieve_relevant_entries` never queries the deadlines table; confirmed via code read 08/06).
3. Codebase Review 2026-06-05 — **remaining** critical finding (Notion page `3769402f…`): sequential-blocking "parallel" retrieval. (The two metering findings are fixed-pending-merge — see Now-3.)
4. Edit + archive flows (entries/deadlines/projects from dashboard) — longstanding queued milestone.

## Known broken / degraded (open only)
- **Deferred metering follow-up (P2):** `POST /entries` + `/entries/stream` are unmetered (no rate limit, no cost cap) but have **no frontend caller** — direct-API surface only. Mirror `/entries/async`: add `entry_rate_limit` + `check_cost_cap`. **Trigger: close before any public/ungated API exposure.** (Carved out of the 15/06 metering PR.)
  - Cost cap meters on flat $0.0008 estimate, not measured cost; under-counts expensive calls; revisit with real per-call cost if abuse appears.
- **CI needs a programmatic re-ask judge with the fixed rubric** (P1): inline gemini-2.5-pro judging dropped 11/06 (quota troughs) and the session-agent batch judging used for the B experiment is non-reproducible. Candidate: flash-class judge + fixed rubric; harness `--no-judge` flag exists.
- Ask answers deadline-list queries from prose, not the deadlines table (P1).
- Read-after-write lag on `ask_messages` can defeat loop detection under rapid back-to-back sends (P2; not hit at human pace).
- Referenced-date indexing gap (Layer 3): entries mentioning a date aren't visible to temporal queries about that date — needs `entry_referenced_dates` table + pipeline extraction node (P2, ~4–6h).
- `ChatVertexAI` deprecation warning at every boot — migrate Vertex branch of `app/llm.py` to maintained class before LangChain 4.0 (P3).
- `normalize_thinking_budget_eval.py:97` calls `normalize()` with outdated `model=` kwarg — eval silently broken since ~23/05 (P3).
- Deadline live eval has stale April fixtures — F1 0.32/0.38 is a scoring artifact, not real signal (P3).
- Local `.env` has UTF-8 BOM breaking `os.getenv` locally; prod unaffected (P3).
- UI polish: desktop dashboard wasted space in wide layouts; deadline list scroll styling (P3).

## Watching (observation windows)
- **First-prod-reask check (after the B env flip, Next-1):** pull one real multi-turn re-ask from Langfuse and confirm turn-2 transforms (acknowledges + re-presents, not a redump). The synthetic grid predicts it (reask 0→4/5); prod confirms it on real retrieval. Also watch the Ask generation span p95 vs the >25s alert (harness p95 ~21.7s).
- **Vivek-class entity-gate advisory period — review date 09/06 has passed, decision overdue:** promote `question_entity_known` to active gating if logged false-positive rate < 1%; else tune the high-signal filter (shipped d01ee80).
- `want_all_not_subset` multi-turn eval category is judge-noise (inconsistent pass/fail on identical behavior) — review judge guidance before trusting its signal.
- `formal` persona produced no unique failures in the multi-turn grid — candidate for collapse to cut eval cost.
- **B's residual re-ask redumps** (the 2 reask fails in the audit subset — flat re-lists with an ack, e.g. frustrated/formal): known boundary of the model-swap fix, not a blocker (B 4/5 reask vs baseline 0/5). Candidate for a future fresh-branch prompt pass.
- **Context caching ($0.025/M)** — post-launch cost offset for the static Ask prompt prefix; revisit once B is live and traffic justifies it.
