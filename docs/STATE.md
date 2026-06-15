# STATE — updated 2026-06-11 (commit 7852402)

Maintained per ADR-0001: fixed/done items are **deleted** (history lives in the changelog DB + git), never struck through. Keep ≤1.5K tokens.

## Now (≤3)
1. **Vertex AI prod migration just landed** (37fab70 + e2f8a4a; IAM 403 on `mindgraph-vertex` SA fixed 10/06 by granting `roles/aiplatform.user`). Watch prod stability for a few days.
2. **3.1-flash-lite (B) accepted — merge pending (11/06, `eval/multiturn-ask-harness`).** B (3.1-flash-lite, thinking_level=minimal, generation node only): reask transforms 13/15, judge mean 4.47 (0.03 under the 4.5 bar), overlap 0.286 vs A 0.487; C (low) fails (3.2). **External concordance audit** (gemini-3.1-pro-preview, 12 blind stratified cases, new seed) = **12/12 pass/fail agreement → external concordance confirmed (12/12)**. **clarifier_commit pre-check 15/15 PASS.** **Full 33-case run (Vertex) vs re-judged 85adc57 baseline, SAME fixed rubric: 32/33 vs 24/33 (+8); reask_loop 0→4/5, clarifier_commit 2→5/5, zero regressions, negatives hold → clears the ±4 noise band.** (Re-judging both neutralized the original Pro confounds: baseline reask 3/5 was trailing-Q luck → 0/5; want_all 2/5 was judge-noise → 5/5.) **Remaining: merge** (config swap depends on cfaca4c family-aware routing — Next-2). **Cost:** generation node $0.0008→$0.0018/conv measured (~2.25×); Batch API (−50%) for eval/offline; context caching ($0.025/M) a post-launch offset for the static prompt prefix. Results: `fullgrid_compare_B_vs_85adc57_*`, `concordance_audit_e7ef0b8e6ac3_*`, `clarifier_precheck_judged_*`, `blindjudge_reask_ABC_*`.

## Next (ordered)
1. **Merge B** — all gates cleared (audit 12/12, clarifier pre-check 15/15, full grid 32/33 / +8 vs re-judged baseline). The prod swap is `ASK_GENERATION_MODEL=gemini-3.1-flash-lite` + `ASK_GENERATION_THINKING=minimal` (Railway env), which **requires cfaca4c family-aware routing + 422df32 on main first (Next-2)**. Sequence: land Next-2 cherry-picks → set Railway env → watch prod. (Merge scope/push not yet executed — awaiting go-ahead.)
2. Cherry-pick/merge to main regardless of experiment outcome: 422df32 (Vertex thinking_budget=0 enforcement) + family-aware `build_chat_model`/per-node override in `app/llm.py` (cfaca4c) — both affect prod.
3. Route "list my deadlines"-class Ask queries through structured `/deadlines` data instead of journal prose (P1 — `retrieve_relevant_entries` never queries the deadlines table; confirmed via code read 08/06).
4. Fix `detect_repetition_loop`: watches wrong signal (compares last two assistant messages, real case is new-answer-vs-previous on re-ask) and its remedy (blanking history) regenerates the same answer. Detect re-asks on the user side; inject an instruction instead of blanking.
5. Codebase Review 2026-06-05 critical findings (Notion page `3769402f…`): paid-tier rate-limit/cost-cap key mismatch (`pro` vs `paid`); `/conversations/messages` bypasses rate limits and cost caps; sequential-blocking "parallel" retrieval.
6. Edit + archive flows (entries/deadlines/projects from dashboard) — longstanding queued milestone.

## Known broken / degraded (open only)
- **Critical (from 05/06 codebase review):** paid-tier rate-limit key mismatch `pro`/`paid`; `/conversations/messages` bypasses limits/caps.
- reask_loop: 2.5-flash-lite ignores the v13.4 transform clause — blind re-judge under the fixed rubric scores it 2/15 (earlier ~3/5 pro-judge scores were trailing-question luck, not partial compliance).
- Multi-turn eval judge: gemini-2.5-pro inline judging dropped 11/06 (quota troughs; us-central1 hard-throttled, global/us-east4 intermittent) — session-agent blind batch judging used for the experiment. CI still needs a programmatic judge (candidate: flash-class judge with the fixed rubric; harness `--no-judge` flag exists).
- Ask answers deadline-list queries from prose, not the deadlines table (P1).
- `detect_repetition_loop` wrong signal + counterproductive remedy (P1).
- Read-after-write lag on `ask_messages` can defeat loop detection under rapid back-to-back sends (P2; not hit at human pace).
- Referenced-date indexing gap (Layer 3): entries mentioning a date aren't visible to temporal queries about that date — needs `entry_referenced_dates` table + pipeline extraction node (P2, ~4–6h).
- `ChatVertexAI` deprecation warning at every boot — migrate Vertex branch of `app/llm.py` to maintained class before LangChain 4.0 (P3).
- `normalize_thinking_budget_eval.py:97` calls `normalize()` with outdated `model=` kwarg — eval silently broken since ~23/05 (P3).
- Deadline live eval has stale April fixtures — F1 0.32/0.38 is a scoring artifact, not real signal (P3).
- Local `.env` has UTF-8 BOM breaking `os.getenv` locally; prod unaffected (P3).
- UI polish: desktop dashboard wasted space in wide layouts; deadline list scroll styling (P3).

## Watching (observation windows)
- **Vivek-class entity-gate advisory period — review date 09/06 has passed, decision overdue:** promote `question_entity_known` to active gating if logged false-positive rate < 1%; else tune the high-signal filter (shipped d01ee80).
- `want_all_not_subset` multi-turn eval category is judge-noise (inconsistent pass/fail on identical behavior) — review judge guidance before trusting its signal.
- `formal` persona produced no unique failures in the multi-turn grid — candidate for collapse to cut eval cost.
