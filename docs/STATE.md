# STATE — updated 2026-06-10 (commit d4121ec)

Maintained per ADR-0001: fixed/done items are **deleted** (history lives in the changelog DB + git), never struck through. Keep ≤1.5K tokens.

## Now (≤3)
1. **Vertex AI prod migration just landed** (37fab70 + e2f8a4a; IAM 403 on `mindgraph-vertex` SA fixed 10/06 by granting `roles/aiplatform.user`). Watch prod stability for a few days.
2. **Multi-turn Ask eval — RED baseline complete** (24/33; commit 228c1e5 on `eval/multiturn-ask-harness`, unmerged). Key finding: reask_loop 0/5 — the v13.4 loop fix does not generalize across writing styles.

## Next (ordered)
1. Fix the reask-loop redump: re-ask detector is exact-match (misses rephrased re-asks); ALREADY-ANSWERED only prepends an acknowledgment without transforming the re-presentation. Validate GREEN via the multi-turn harness, then merge `eval/multiturn-ask-harness`.
2. Route "list my deadlines"-class Ask queries through structured `/deadlines` data instead of journal prose (P1 — `retrieve_relevant_entries` never queries the deadlines table; confirmed via code read 08/06).
3. Fix `detect_repetition_loop`: watches wrong signal (compares last two assistant messages, real case is new-answer-vs-previous on re-ask) and its remedy (blanking history) regenerates the same answer. Detect re-asks on the user side; inject an instruction instead of blanking.
4. Codebase Review 2026-06-05 critical findings (Notion page `3769402f…`): paid-tier rate-limit/cost-cap key mismatch (`pro` vs `paid`); `/conversations/messages` bypasses rate limits and cost caps; sequential-blocking "parallel" retrieval.
5. Edit + archive flows (entries/deadlines/projects from dashboard) — longstanding queued milestone.

## Known broken / degraded (open only)
- **Critical (from 05/06 codebase review):** paid-tier rate-limit key mismatch `pro`/`paid`; `/conversations/messages` bypasses limits/caps.
- reask_loop 0/5 across personas — v13.4 doesn't generalize (10/06 eval RED).
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
