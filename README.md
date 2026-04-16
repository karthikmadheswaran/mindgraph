# MindGraph

A production-grade personal AI engine that turns unstructured daily text into searchable memory, entities, deadlines, knowledge graphs, grounded answers, and behavioral insight.

[![Live Demo](https://img.shields.io/badge/Live%20Demo-rawtxt.in-2ea44f?style=for-the-badge)](https://rawtxt.in)
[![API Docs](https://img.shields.io/badge/API%20Docs-Swagger-2563eb?style=for-the-badge)](https://mindgraph-production.up.railway.app/docs)

## What It Does

- Converts messy personal text into structured memory that can be searched, queried, and visualized.
- Extracts people, projects, deadlines, decisions, and relationships without forcing the user into forms.
- Answers natural-language questions with grounded retrieval, conversation memory, and temporal awareness.
- Reveals forgotten projects, recurring patterns, weekly summaries, and progress history.
- Maps entities and semantic relationships as an interactive knowledge graph.
- Keeps each user's data isolated behind Supabase Auth and JWT-protected API access.

## Key Engineering Metrics

- **10x latency improvement:** 67s → 6.66s.
- **30x cost reduction:** $0.009 → $0.0003 per entry.
- **RAG F1:** 0.369 baseline → 0.782 after hybrid BM25 + pgvector + Cohere Rerank v3.5.
- **MRR:** 0.759 → 0.957.
- **Ask generation quality:** Inference Quality 4.00 → 4.53, Conversational Intelligence 3.87 → 4.47, judged by Gemini Pro across a 32-case harness.
- **Zero hallucinations** across all RAG and Ask eval runs.
- **225 tests** across 9 harnesses.
- **Date normalization:** 64% → 96% functional pass rate, 100% date F1.

## Architecture Diagram

```text
React Frontend (Write + Dashboard + Knowledge Graph + Ask + Insights)
         ↓
FastAPI Backend (15 endpoints, JWT auth, async background processing)
         ↓
LangGraph Pipeline (8 nodes, parallel fan-out + fan-in)
         ↓
Supabase (Postgres + pgvector + tsvector/GIN + Auth)
         ↓
Gemini API (gemini-2.5-flash-lite pipeline · gemini-2.5-pro insights + eval judge)
         ↓ (Ask retrieval only)
Cohere Rerank v3.5 (cross-encoder re-ranking of hybrid BM25 + vector candidates)
```

```text
START → normalize → dedup ──→ classify        ─┐
                         │   → entities        ├→ extract_relations → store → END
                         │   → deadline        │
                         │   → title_summary   ┘
                         └──→ END  (duplicate detected)
```

## Tech Stack

| Constant | Value |
| --- | --- |
| Pipeline LLM | gemini-2.5-flash-lite |
| Insights / Eval Judge LLM | gemini-2.5-pro |
| Embedding model | Gemini embedding-001 |
| Embedding dimensions | 1536 |
| Pipeline node count | 8 |
| RAG retrieval | Hybrid: pgvector cosine + Postgres BM25 (tsvector/GIN) + Cohere Rerank v3.5 + temporal query routing (date-range bypass) |
| Database | Supabase Postgres + pgvector + tsvector |
| Auth | Supabase Auth — email/password, JWT ES256/JWKS |
| Observability | Langfuse ([cloud.langfuse.com](http://cloud.langfuse.com)) |
| Hosting | Railway (frontend + backend), Docker |
| Frontend framework | React + react-force-graph |
| Backend framework | FastAPI + Uvicorn |
| Orchestration | LangGraph + LangChain |

## Key Engineering Decisions

### Model Optimization (10x Faster, 30x Cheaper)

**Problem:** The original pipeline model was too slow and expensive for a production personal AI engine.

**Solution:** Switched the pipeline from `gemini-3-flash-preview` to `gemini-2.5-flash-lite`.

**Outcome:** Latency dropped from 67s → 6.66s and cost dropped from $0.009 → $0.0003 per entry.

### Hybrid RAG Pipeline

**Problem:** Pure semantic retrieval missed lexical matches, temporal questions, and semantically distant but relevant entries.

**Solution:** Combined BM25 + pgvector cosine + Cohere Rerank v3.5 + temporal query routing. Time-based queries bypass embedding entirely and hit the database directly with a date-range query.

**Outcome:** RAG F1 improved from 0.369 → 0.782 and MRR improved from 0.759 → 0.957.

### Eval-Driven Prompt Engineering

**Problem:** Entity extraction and Ask generation needed measurable quality gains, not subjective prompt tweaking.

**Solution:** Tuned entity extraction across a 41-case harness, 10 failure families, and Ask generation across a 32-case LLM-as-judge harness using Gemini Pro, 6 iterations, and 8 prompt rules.

**Outcome:** Entity extraction improved from 75.6% → 100% pass rate. Ask generation improved from 4.00 → 4.53 on Inference Quality and 3.87 → 4.47 on Conversational Intelligence.

### 3-Stage Entity Linking

**Problem:** Name variants could create duplicate entity rows, while aggressive fuzzy matching risked false merges.

**Solution:** Linked entities through normalized exact match -> project-normalized match -> semantic embedding match with a substring-aware cosine threshold.

**Outcome:** Prevents duplicate rows for name variants without false merges.

### Async Background Processing + Silent Refresh

**Problem:** Railway's proxy breaks long SSE connections, making slow LLM processing unreliable as a foreground request.

**Solution:** Switched to fast-acknowledge/process-slow with FastAPI BackgroundTask, `pipeline_stage` polling, and silent background sync in the frontend.

**Outcome:** Users get immediate acknowledgement while the pipeline finishes in the background, with stable production behavior on Railway.

## RAG Evaluation Results

| Metric | Baseline | Phase 1 (threshold tuning) | Phase 2 (hybrid BM25 + rerank) |
| --- | ---: | ---: | ---: |
| Retrieval F1 | 0.369 | 0.669 | **0.782** |
| MRR | 0.759 | 0.907 | **0.957** |
| Pass rate | 11/27 (41%) | 20/27 (74%) | **21/27 (78%)** |

## Ask Generation Quality

| Dimension | Baseline | Final | Delta |
| --- | ---: | ---: | ---: |
| Inference Quality | 4.00 | 4.53 | +0.53 |
| Conv. Intelligence | 3.87 | 4.47 | +0.60 |
| Tone | 4.70 | 4.80 | +0.10 |
| Groundedness | 4.93 | 5.00 | +0.07 |
| Noise Resistance | 5.00 | 5.00 | 0.00 |
| Relevance | 4.87 | 4.93 | +0.06 |

## Test Coverage

| Harness | Tests | Scope |
| --- | ---: | --- |
| `test_extract_entities.py` | 41 | 10 families: happy_path, negative_generic, date_leaks, dedup, disambiguation, false_project_promotion, formatting, project_positive, task_boundary, ambiguous |
| `test_store_entities.py` | 6 | Case-insensitive dedup, same-batch dedup, type separation, mention count updates |
| `test_store_project_matching.py` | 24 | Spacing/case/hyphen/underscore variants, risky collisions, clearly-different names |
| `test_extract_relations.py` | 16 | Relation parsing: multi-entity, symmetric relations, confidence scoring, edge cases |
| `test_store_relations.py` | 4 | Insert, upsert dedup, unresolved entity skip, symmetric relation normalization |
| `normalize_evaluation.py` | 25 | Live Gemini normalize eval: weekday lookups, offsets, month/year boundaries, slang, no-date hallucination, timezone rollover |
| `rag_evaluation.py` | 27 | Retrieval F1, MRR, pass rate, pronoun resolution, leakage resistance — 6 categories |
| `memory_compaction_evaluation.py` | 50 | 36 compaction + 14 Ask cases: stable facts, dedup, contradiction update, precedence, honesty |
| `eval_generation.py` | 32 | LLM-as-judge: 7 dimensions × 6 behavioral categories + 7 failure mode detectors. Includes: repetition_ignores_user_answer (v11) + repetition_minimal_reply_idk (v12) |
| **Total** | **225** | Zero hallucinations across all RAG and Ask eval runs |

## API Endpoints

| Method | Path | Description |
| --- | --- | --- |
| POST | `/entries/async` | Submit entry — instant response, background processing |
| GET | `/entries` | Fetch stored entries for authenticated user |
| GET | `/entries/{id}/status` | Poll pipeline stage for a processing entry |
| POST | `/ask` | Hybrid RAG + conversation memory Q&A |
| GET | `/ask/history` | Fetch recent Ask conversation history |
| GET | `/ask/memory` | Inspect compacted long-term Ask memory |
| GET | `/search` | Semantic similarity search on entries |
| GET | `/deadlines` | Fetch upcoming deadlines |
| GET | `/entities` | Fetch extracted entities ranked by mention count |
| GET | `/entity-relations` | Fetch LLM-extracted semantic relations between entities |
| GET | `/insights` | Read all cached insights |
| GET | `/insights/patterns` | Read cached behavioural pattern analysis |
| GET | `/insights/weekly` | Read cached weekly digest |
| GET | `/insights/forgotten` | Read cached forgotten projects detection |
| GET | `/health` | Health check (no auth required) |

## Project Structure

```text
.
|-- app/
|   |-- main.py                  # FastAPI app, auth, CORS, API routing
|   |-- graph.py                 # LangGraph pipeline wiring
|   |-- state.py                 # Shared typed pipeline state
|   |-- auth.py                  # Supabase JWT verification
|   |-- db.py                    # Supabase client
|   |-- retrieval.py             # Hybrid retrieval path
|   |-- nodes/
|   |   |-- normalize.py
|   |   |-- dedup.py
|   |   |-- classify.py
|   |   |-- extract_entities.py
|   |   |-- deadline.py
|   |   |-- title_summary.py
|   |   |-- extract_relations.py
|   |   `-- store.py
|   `-- services/
|       |-- ask_service.py
|       |-- conversation.py
|       |-- deadline_service.py
|       |-- entity_service.py
|       |-- entry_service.py
|       |-- insight_service.py
|       |-- observability.py
|       |-- project_service.py
|       `-- reranker.py
|-- tests/                       # Python test harnesses
|-- evals/                       # RAG, normalize, memory, generation evals
|-- scripts/                     # Backfills and maintenance scripts
|-- docs/                        # Architecture notes and assessments
|-- migrations/                  # Supabase/Postgres migrations
|-- mindgraph-frontend/
|   |-- public/
|   |   |-- index.html
|   |   |-- env.js
|   |   |-- rawtxt-landing.html
|   |   |-- rawtxt-architecture.html
|   |   |-- landing/index.html
|   |   `-- architecture/index.html
|   |-- src/
|   |   |-- App.js
|   |   |-- runtimeConfig.js
|   |   |-- supabaseClient.js
|   |   |-- components/
|   |   |   |-- AuthView.js
|   |   |   |-- InputView.js
|   |   |   |-- Dashboard.js
|   |   |   |-- AskView.js
|   |   |   |-- KnowledgeGraph.js
|   |   |   |-- KnowledgeGraphView.js
|   |   |   |-- MyProgress.js
|   |   |   `-- Sidebar.js
|   |   |-- styles/
|   |   `-- utils/
|   |-- Dockerfile
|   |-- nginx.conf.template
|   `-- railway-listen.envsh
|-- Dockerfile
|-- docker-compose.yml
|-- requirements.txt
`-- README.md
```

Python files are organized into `tests/`, `evals/`, `scripts/`, and `docs/`; the repo root is intentionally not a flat scratchpad. Frontend components live in `mindgraph-frontend/src/components/`.

## Running Locally

### Prerequisites

- Python 3.11+
- Node.js 20+
- Supabase project with Postgres, pgvector, tsvector/GIN, and Auth configured
- Gemini API key
- Cohere API key for reranking

### Backend

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

On Windows PowerShell, activate with:

```powershell
.\.venv\Scripts\Activate.ps1
```

### Frontend

```bash
cd mindgraph-frontend
npm install
npm start
```

### Environment Variables

Backend:

```env
SUPABASE_URL=
SUPABASE_SERVICE_ROLE_KEY=
GEMINI_API_KEY=
COHERE_API_KEY=
LANGFUSE_PUBLIC_KEY=
LANGFUSE_SECRET_KEY=
LANGFUSE_BASE_URL=
CORS_ORIGINS=
```

Frontend:

```env
REACT_APP_SUPABASE_URL=
REACT_APP_SUPABASE_ANON_KEY=
REACT_APP_API_URL=
```

Production on Railway generates `/env.js` at container startup for the frontend. The backend service-role variable is `SUPABASE_SERVICE_ROLE_KEY`.

## License

MIT
