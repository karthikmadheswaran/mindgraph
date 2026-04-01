# 🧠 MindGraph — AI-Powered Frictionless Journal

**One textbox. Zero friction. Your AI organizes everything.**

MindGraph is a full-stack AI journal application that automatically extracts people, projects, deadlines, emotions, and behavioral patterns from your thoughts — using a 7-node LangGraph pipeline powered by Gemini.

🔗 **[Live Demo](https://mindgraph-frontend-production.up.railway.app)** · 📊 **[API Docs](https://mindgraph-production.up.railway.app/docs)**

---

## What It Does

Write freely in a single textbox. MindGraph's AI pipeline processes your entry in under 7 seconds:

- **🎯 Projects & Tasks** — Automatically tracks what you're working on
- **📅 Deadlines** — Extracts real commitments with dates
- **👥 People** — Maps who you mention and how often
- **🔍 Ask Your Journal** — RAG-powered Q&A over all your entries
- **🧠 Pattern Detection** — Finds emotional patterns, recurring themes, and shiny object syndrome
- **⚡ 7-Second Pipeline** — LangGraph + Gemini for real-time processing

---

## Architecture

```
React Frontend (Write + Dashboard + Ask + Insights)
         ↓
FastAPI Backend (10 endpoints, JWT auth, async processing)
         ↓
LangGraph Pipeline (7 nodes, parallel execution)
         ↓
Supabase (Postgres + pgvector + Auth)
         ↓
Gemini API (gemini-2.5-flash-lite + gemini-2.5-pro for insights)
```

### Pipeline Graph

```
START → normalize → dedup ──→ classify      ─┐
                             → entities      ├→ store → END
                             → deadline      │
                             → title_summary ┘
```

All four extraction nodes (classify, entities, deadline, title_summary) run **in parallel** after dedup, then fan-in to the store node.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | React, react-markdown |
| Backend | FastAPI, Uvicorn |
| AI Pipeline | LangGraph, LangChain |
| LLM | Gemini 2.5 Flash-Lite (pipeline), Gemini 2.5 Pro (insights) |
| Embeddings | Gemini embedding-001 (1536 dimensions) |
| Database | Supabase (Postgres + pgvector) |
| Auth | Supabase Auth (email/password, JWT/ES256/JWKS) |
| Observability | Langfuse (per-node tracing, cost tracking) |
| Deployment | Railway (backend + frontend), Docker |

---

## Key Engineering Decisions

### Model Optimization — 10x Faster, 30x Cheaper
Switched all pipeline nodes from `gemini-3-flash-preview` to `gemini-2.5-flash-lite`. Total pipeline latency dropped from **1m 7s to 6.66s**, cost from **$0.009 to $0.0003** per entry.

### Async Background Processing
Railway's proxy breaks long SSE connections. Switched to a "acknowledge fast, process slow" pattern — the frontend gets an instant response while the pipeline runs in the background. Dashboard polls for status with silent background sync.

### Entity Linking with Semantic Gating
Case-insensitive exact-name lookup first, then embedding similarity with an acceptance gate. Prevents both duplicates ("MindGraph" vs "Mindgraph") and false merges (unrelated entities with high similarity scores).

### RAG Evaluation — 4 Runs, Data-Driven Decisions
Built a 15-test-case evaluation framework measuring retrieval F1, keyword accuracy, and hallucination rate. Used it to:
- Diagnose NULL embedding failures (F1: 0.0 → 0.333 after backfill)
- Evaluate query rewriting (+8.3% F1 but 50x latency — reverted)
- Validate that basic vector search is optimal for current data size

### Insight Engine — Hybrid Caching
Dashboard reads cached insights from the database (instant load). Fresh insights regenerate in the background after each new journal entry. Pattern detection powered by Gemini 2.5 Pro.

### Prompt Engineering with Evaluation Harnesses
Each LLM node (deadline, entity extraction) has its own test suite with precision/recall/F1 metrics. Entity extraction: 100% precision, F1=0.981. Deadline detection: tightened prompt eliminated false positives like "new possibilities" and "hope for a better day".

---

## RAG Evaluation Results

| Metric | Run 1 | Run 2 (backfill) | Run 3 (query rewrite) | Run 4 (final) |
|---|---|---|---|---|
| Retrieval F1 | 0.483 | 0.504 | 0.523 | 0.504 |
| Keyword Score | 0.922 | 0.911 | 0.933 | 0.933 |
| Hallucination | 1.000 | 1.000 | 1.000 | **1.000** |
| Retrieval Latency | 622ms | 799ms | 42,000ms | 1,011ms |

**Zero hallucinations across all 4 evaluation runs.**

---

## API Endpoints

| Method | Path | Description |
|---|---|---|
| POST | `/entries/async` | Submit entry with async background processing |
| GET | `/entries` | Fetch stored entries for authenticated user |
| POST | `/ask` | RAG — ask questions about your journal |
| GET | `/deadlines` | Fetch upcoming deadlines |
| GET | `/entities` | Fetch extracted entities |
| GET | `/entries/{id}/status` | Poll pipeline status for a processing entry |
| GET | `/insights/patterns` | Read cached behavioral patterns |
| GET | `/insights/weekly` | Read cached weekly digest |
| GET | `/search` | Semantic similarity search on entries |
| GET | `/health` | Health check |

All endpoints (except `/health`) require JWT authentication via Supabase Auth.

---

## Observability

Integrated with **Langfuse** for full pipeline tracing:
- Per-node latency and cost tracking
- Token usage per LLM call
- Pipeline graph visualization
- Trace replay for debugging

---

## Running Locally

### Prerequisites
- Python 3.12+
- Node.js 18+
- Supabase project (Postgres + pgvector)
- Gemini API key

### Backend
```bash
cd "Mindgraph - Frictionless AI journal app"
pip install -r requirements.txt
uvicorn app.main:app --reload
```

### Frontend
```bash
cd mindgraph-frontend
npm install
npm start
```

### Environment Variables

**Backend (`.env`)**
```
GEMINI_API_KEY=your_key
GOOGLE_API_KEY=your_key
SUPABASE_URL=your_url
SUPABASE_KEY=your_service_role_key
LANGFUSE_PUBLIC_KEY=your_key
LANGFUSE_SECRET_KEY=your_key
LANGFUSE_HOST=https://cloud.langfuse.com
```

**Frontend (`mindgraph-frontend/.env`)**
```
REACT_APP_SUPABASE_URL=your_url
REACT_APP_SUPABASE_ANON_KEY=your_anon_key
```

### Docker
```bash
docker-compose up
```

---

## Project Structure

```
├── app/
│   ├── main.py              # FastAPI endpoints + auth
│   ├── auth.py              # Supabase JWT validation (ES256/JWKS)
│   ├── graph.py             # LangGraph pipeline wiring
│   ├── state.py             # Pipeline state definition
│   ├── embeddings.py        # Gemini embedding generation
│   ├── retrieval.py         # Advanced retrieval module
│   ├── insights_engine.py   # Pattern detection + weekly digest
│   └── nodes/
│       ├── normalize.py     # Text cleanup + date resolution
│       ├── dedup.py         # Semantic duplicate detection
│       ├── classify.py      # Multi-label categorization
│       ├── extract_entities.py  # Entity extraction
│       ├── deadline.py      # Deadline detection
│       ├── title_summary.py # Auto title + summary
│       └── store.py         # Supabase storage + entity linking
├── mindgraph-frontend/
│   └── src/
│       ├── App.js           # Full React app (landing, auth, dashboard)
│       └── supabaseClient.js
├── rag_evaluation.py        # 15-test-case RAG evaluation framework
├── Dockerfile
├── docker-compose.yml
└── requirements.txt
```

---

## What I Learned

This project was built as a hands-on learning exercise for LangGraph and AI pipeline development. Key learnings:

- **LangGraph**: State management, parallel fan-out/fan-in, conditional routing, checkpointing
- **RAG**: Vector embeddings, semantic search, evaluation with metrics, query rewriting trade-offs
- **Entity Linking**: Exact match first, then gated semantic fallback — embedding similarity alone isn't reliable for entity identity
- **Production**: Observability matters (Langfuse), model selection matters (10x speed difference), async processing for reliability
- **Prompt Engineering**: Tighter prompts > more detailed prompts; evaluation harnesses catch regressions

---

## License

MIT