# MindGraph

**An AI journal that organizes your thoughts automatically.** One textbox, zero friction — the AI handles classification, entity extraction, deadline detection, and semantic search across everything you write.

🔗 **[Live Demo](https://mindgraph-frontend-production.up.railway.app)**

---

## What it does

You write a journal entry in plain text. MindGraph's 7-node AI pipeline processes it in ~6 seconds:

- **Classifies** the entry (work, health, finance, relationships, etc.)
- **Extracts entities** — people, projects, places, tools — and links them to existing records using embedding similarity
- **Detects deadlines** with natural language date resolution
- **Generates** a title and smart summary
- **Deduplicates** against previous entries using semantic similarity (0.85 threshold)
- **Stores** everything with vector embeddings for later retrieval

Then you can **ask your journal questions** in natural language ("What have I been stressed about this month?") and get answers grounded in your actual entries via RAG.

---

## Architecture

```
React Frontend (Write + Dashboard + Ask + Pipeline Status)
         ↓
FastAPI Backend (10 endpoints, JWT auth, async processing + SSE)
         ↓
LangGraph Pipeline (7 nodes, parallel execution, dedup)
         ↓
Supabase (Postgres + pgvector + Row Level Security)
         ↓
Gemini API (classification, extraction, RAG, embeddings)
```

### Pipeline graph

```
START → normalize → dedup ──→ classify      ─┐
                             → entities       ├→ store → END
                             → deadline       │
                             → title_summary  ┘
```

After dedup, four nodes run **in parallel** (classify, entities, deadline, title_summary) and fan back into the store node — a pattern that cut pipeline latency from sequential execution.

---

## Tech stack

| Layer | Technology |
|-------|-----------|
| Frontend | React, Supabase Auth SDK |
| Backend | FastAPI, Python 3.12 |
| AI orchestration | LangGraph (StateGraph, parallel fan-out/fan-in, SSE streaming) |
| LLM | Gemini 2.5 Flash Lite (classification, extraction, RAG generation) |
| Embeddings | Gemini Embedding 001 (1536 dimensions) |
| Database | Supabase Postgres + pgvector |
| Auth | Supabase Auth (JWT/ES256, JWKS verification) |
| Observability | Langfuse (pipeline tracing, token cost tracking) |
| Deployment | Railway (backend + frontend), Docker |

---

## Key engineering decisions

### 10x faster pipeline through model selection
The pipeline originally used `gemini-3-flash-preview` and took **1m 7s** per entry. Switching all nodes to `gemini-2.5-flash-lite` brought it down to **6.66s** — a 10x speed improvement. Cost dropped from $0.009 to $0.0003 per entry (30x cheaper). The quality difference was negligible for classification and extraction tasks.

### Parallel node execution with LangGraph
Classification, entity extraction, deadline detection, and title/summary generation don't depend on each other — only on the cleaned text from the normalize node. Running them in parallel with LangGraph's fan-out/fan-in pattern (`builder.add_edge([list], "store")`) was a natural fit and reduced wall-clock time significantly.

### Entity linking via embeddings, not string matching
When the pipeline extracts an entity like "MindGraph project", it needs to check if this entity already exists. String matching fails on variations ("mindgraph", "the MindGraph app", "my journal project"). Instead, we generate embeddings for both the new entity and existing entities, then match using cosine similarity with a 0.8 threshold + entity type filtering. This handles natural language variations without brittle regex.

### Async processing with live status polling
Journal entries are processed in the background (`BackgroundTasks`). The frontend immediately shows a skeleton entry card with a processing indicator. It polls `/entries/{id}/status` every 2 seconds and displays per-node pipeline progress (normalize → dedup → classify → ...). The user never stares at a blank screen.

### JWT auth with asymmetric key verification
Authentication uses Supabase Auth with ES256 (ECC P-256) JWT signing. The backend verifies tokens by fetching the public key from Supabase's JWKS endpoint — no shared secrets stored in environment variables. A database trigger automatically creates a `public.users` row whenever someone signs up through Supabase Auth.

---

## RAG evaluation results

Ran a formal evaluation with 15 test cases measuring retrieval accuracy, answer quality, and hallucination:

| Metric | Score |
|--------|-------|
| Retrieval F1 | 0.504 |
| Keyword accuracy | 0.933 |
| Hallucination score | 1.000 (zero hallucinations) |
| Retrieval latency | ~1,011ms |

**Key insight**: With ~30 entries, retrieval precision is the bottleneck (irrelevant entries in top-5 results). This improves naturally as the database grows with more diverse entries. Query rewriting improved F1 by 8.3% but added 50x latency — not worth the trade-off at current scale.

---

## API endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/entries/async` | Submit entry with background processing |
| `POST` | `/entries/stream` | Submit with SSE streaming status |
| `POST` | `/entries` | Submit and wait for result |
| `GET` | `/entries` | Fetch user's entries |
| `GET` | `/entries/{id}/status` | Poll pipeline progress |
| `POST` | `/ask` | RAG — ask questions about your journal |
| `GET` | `/search` | Semantic similarity search |
| `GET` | `/deadlines` | Fetch upcoming deadlines |
| `GET` | `/entities` | Fetch extracted entities |
| `GET` | `/health` | Health check (public) |

All endpoints except `/health` require JWT authentication.

---

## Local development

### Prerequisites
- Python 3.12+
- Node.js 18+
- Supabase project with pgvector enabled
- Gemini API key

### Backend

```bash
cd backend
pip install -r requirements.txt

# .env file
SUPABASE_URL=your-supabase-url
SUPABASE_KEY=your-anon-key
GEMINI_API_KEY=your-gemini-key
LANGFUSE_PUBLIC_KEY=your-langfuse-key      # optional
LANGFUSE_SECRET_KEY=your-langfuse-secret   # optional

uvicorn app.main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm install

# .env file
REACT_APP_API_URL=http://localhost:8000
REACT_APP_SUPABASE_URL=your-supabase-url
REACT_APP_SUPABASE_ANON_KEY=your-anon-key

npm start
```

### Docker

```bash
docker-compose up --build
```

---

## Project structure

```
├── app/
│   ├── main.py              # FastAPI endpoints + middleware
│   ├── auth.py              # JWT verification via JWKS
│   ├── graph.py             # LangGraph pipeline wiring
│   ├── state.py             # JournalState (TypedDict + reducers)
│   ├── embeddings.py        # Gemini embedding generation
│   ├── retrieval.py         # Advanced search utilities
│   └── nodes/
│       ├── normalize.py     # Text cleanup + date resolution
│       ├── dedup.py         # Semantic duplicate detection
│       ├── classify.py      # Multi-label categorization
│       ├── extract_entities.py  # Entity extraction + linking
│       ├── deadline.py      # Deadline detection
│       ├── title_summary.py # Auto title + summary
│       └── store.py         # Supabase storage with retry logic
├── frontend/
│   └── src/
│       ├── App.js           # Main app with auth, input, dashboard
│       └── supabaseClient.js
├── Dockerfile
├── docker-compose.yml
└── requirements.txt
```

---

## What I learned building this

- **LangGraph orchestration**: StateGraph, TypedDict with Annotated reducers, parallel fan-out/fan-in, conditional routing, SSE streaming with `workflow.astream()`
- **RAG pipeline design**: Embedding generation, vector similarity search via pgvector, entity linking, formal evaluation methodology with F1 scoring
- **Production patterns**: Async background processing, exponential backoff retry logic, observability with Langfuse, Docker containerization, Railway deployment
- **Auth implementation**: Supabase Auth with asymmetric JWT verification (ES256/JWKS), FastAPI dependency injection, database triggers for user provisioning
- **Model optimization**: Benchmarking different Gemini models for cost/latency/quality trade-offs across different task types

---

## Roadmap

- [ ] Voice input (Deepgram speech-to-text)
- [ ] Image input (Gemini Vision)
- [ ] Insight engine — weekly patterns, forgotten projects, "shiny object" detection
- [ ] External tool use — calendar, GitHub, email integration via function calling
- [ ] Advanced retrieval — hybrid search (semantic + keyword) with reranking

---

## License

MIT
