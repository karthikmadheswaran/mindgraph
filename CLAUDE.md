# MindGraph — agent context

Personal AI journal engine, live at https://rawtxt.in (solo project, **public repo**).
Capture → LangGraph entry pipeline (parallel extractor fan-out) → Supabase. Ask → multi-branch retrieval DAG → grounded answers.
Backend FastAPI + LangGraph + Gemini (Vertex AI in prod); frontend React (CRA), nav = Home · Journal · Ask · Graph. Hosted on Railway.

## Read next
- `docs/STATE.md` — current focus + known-broken. Read before any project work.
- `docs/decisions/` — ADRs. 0001 defines this tracking system.

## Repo map
- `app/` — backend: `main.py` (all routes), `nodes/` (entry pipeline), `services/ask_pipeline/` (Ask DAG), `services/ask_service.py` (thresholds, memory), `schemas/` (structured outputs)
- `mindgraph-frontend/` — React app; static landing pages in `public/`
- `evals/` — harnesses + `results/` (SHA-stamped run JSONs; diff via `evals/compare.py`)
- `tests/` — pytest suites · `migrations/` — numbered SQL, applied manually to Supabase
- `scripts/`, `docs/` — utilities, docs, ADRs

## Constants (code-true — verify in code, not memory)
| Constant | Value | Provenance |
|---|---|---|
| Pipeline LLM | gemini-2.5-flash-lite, thinking_budget=0 | eval-driven, 27a74f0 |
| Insights / eval-judge LLM | gemini-2.5-pro | |
| Embeddings | embedding-001, 1536-dim, task_type-aware | c0511dc |
| MIN_SIMILARITY | 0.62 — `app/services/ask_service.py` | sweep 26/05, 2dd3d81 |
| HIGH_CONFIDENCE_THRESHOLD | 0.64 — same file | sweep 26/05, 7382e3b |
| Entity-existence gate | advisory only (logs, doesn't gate) | d01ee80 |
| Prod LLM provider | Vertex AI: USE_VERTEX=1, SA key in GOOGLE_CREDENTIALS_JSON | 37fab70 |
| Ask generation prompt | v13.4 | abd151d |

## Derive, don't trust docs
- Route inventory: grep `@app\.` in `app/main.py`
- Test counts: `pytest --collect-only -q tests/`
- Latest eval scores: newest `evals/results/*.json` → `summary` (metadata carries `git_commit`)
- Deployed commit: `curl https://mindgraph-production.up.railway.app/health`

## Do not
- Hard-delete entries — `DELETE /entries/{id}` is soft delete; read paths must filter `deleted_at IS NULL`
- Modify Supabase schema without a numbered migration + backfill plan
- Add pipeline nodes without checking shared state in `app/state.py`
- Assume Ask is plain RAG — hybrid BM25 + pgvector + Cohere rerank, temporal-routing bypass, conversation memory + compaction all exist
- Use env name SUPABASE_KEY (now SUPABASE_SERVICE_ROLE_KEY) or commit `.env` — public repo, keys were rotated once already
- Remove `https://rawtxt.in` / `https://www.rawtxt.in` from backend CORS
- Rely on CRA build-time env in prod — frontend reads `/env.js` generated at container start
- Hardcode user IDs — per-user isolation via Supabase Auth JWT
- Put strategy/pricing content in repo files — that lives in Notion (private)

## Tracking system (ADR-0001)
- **History**: Notion changelog DB — one row per change, appended via `/wrap` at session end
- **Current state**: `docs/STATE.md` — fixed items are deleted, never struck through
- **Decisions**: commit body (every change: WHY / ALTERNATIVES / OUTCOME) → ADR in `docs/decisions/` (architectural) → Notion row `Category=Decision` (strategy)
- **Eval provenance**: every eval run writes SHA-stamped JSON to `evals/results/` (committed); diff two runs with `evals/compare.py`
- **Commit subjects**: `[Category] description` — Launch / Feature / Pipeline / Eval / Infra / Frontend / Tests / Docs / Strategy / Bug Fix / Decision
- **Notion pointers** (fetch on demand only): Status Hub dashboard `3429402f2bd281e1adb9f71e7f52ac05` · changelog DB `6d26883bed4946768cc1aa15ebe02809` (data source `829daeda-7303-4f7d-b269-75b23adb53ff`) · strategy/Action Plan `3439402f2bd2816fb7d4d8984c4960b1` (only when the task touches strategy) · AI techniques reference `3419402f2bd2815d9832cb45bebf9e8e` (append when shipping a new AI/ML technique)
- **Before ending a work session: run `/wrap`.**
