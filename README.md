# MindGraph — AI-Powered Frictionless Journal

**One textbox. Zero friction. Your AI organizes everything.**

MindGraph is a full-stack AI journal that automatically extracts people, projects, deadlines, and behavioural patterns from your thoughts — and visualizes them as an interactive knowledge graph. Built on an 8-node LangGraph pipeline powered by Gemini.

🔗 **[Live Demo](https://mindgraph-frontend-production.up.railway.app)** · 📊 **[API Docs](https://mindgraph-production.up.railway.app/docs)**

---

## What It Does

Write freely in a single textbox. MindGraph's AI pipeline processes your entry in under 7 seconds and builds a living model of your work:

- **Knowledge Graph** — Interactive force-directed graph of your people, projects, and how they connect. Edges are LLM-extracted semantic relations: "Karthik works on MindGraph", "MindGraph uses Gemini".
- **Projects & Tasks** — Tracks named efforts and actionable items automatically
- **Deadlines** — Extracts real commitments with dates
- **People** — Maps who you mention and how often
- **Ask Your Journal** — RAG-powered Q&A over all your entries
- **Pattern Detection** — Finds emotional patterns, recurring themes, and shiny object syndrome
- **Forgotten Projects** — Detects named projects you haven't mentioned recently
- **Weekly Digest** — AI-generated summary of your week's themes and momentum

---

## Architecture

```
React Frontend (Write + Dashboard + Knowledge Graph + Ask + Insights)
         ↓
FastAPI Backend (14 endpoints, JWT auth, async background processing)
         ↓
LangGraph Pipeline (8 nodes, parallel fan-out + fan-in)
         ↓
Supabase (Postgres + pgvector + Auth)
         ↓
Gemini API (gemini-2.5-flash-lite pipeline · gemini-2.5-pro insights)
```

### Pipeline Graph

```
START → normalize → dedup ──→ classify        ─┐
                    │        → entities        ├→ extract_relations → store → END
                    │        → deadline        │
                    │        → title_summary   ┘
                    └──→ END  (duplicate detected)
```

Four extraction nodes (classify, entities, deadline, title_summary) run **in parallel** after dedup, fan-in to the relation extraction node, then store. Duplicate entries are short-circuited at the dedup stage.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | React, react-force-graph |
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
Railway's proxy breaks long SSE connections. Switched to acknowledge-fast/process-slow: the frontend gets an instant response while the pipeline runs as a FastAPI `BackgroundTask`. Dashboard polls for status with silent background sync. Each node updates a `pipeline_stage` column so the UI can show real-time progress.

### Interactive Knowledge Graph with Semantic Relations
Replaced a static mind map with a force-directed graph (react-force-graph) driven by two data layers:
1. **Nodes** — entities extracted per entry (people, projects, tools, places, organizations)
2. **Edges** — LLM-extracted semantic relations (`extract_relations` node) such as "works on", "uses", "collaborates with", "manages". Each relation is stored with a confidence score and source entry reference, deduplicated on upsert.

The graph is filtered to projects and people (the highest-signal entity types) and styled by entity type for fast visual scanning.

### Entity Linking — 3-Stage Matching Pipeline
Three-tier matching to handle real-world name variants without creating duplicate rows:
1. **Base-normalized exact match** — case-insensitive, whitespace-collapsed comparison. Catches "MindGraph" vs "mindgraph".
2. **Project-normalized match** — for `project` entities only: dots, hyphens, and underscores treated as spaces, punctuation stripped, words joined. Catches "Node.js Migration" vs "Node JS Migration" vs "Node-JS-Migration".
3. **Semantic embedding match** with acceptance gating — cosine similarity with a substring-aware threshold (≥0.95 always accepted; ≥0.90 if one name is a substring of the other; otherwise a new entity is created). Catches paraphrased references while blocking false merges.

### Prompt Engineering — Eval-Driven to 100% Pass Rate
Entity extraction uses a Gemini prompt developed against a **41-test harness** across 10 failure families. Iterated from **75.6% → 100% pass rate (F1: 0.90 → 1.0)** without bloating the prompt. Key technique: targeted invalid-output examples for stubborn edge cases (e.g. "I took Inspiral" → should not extract Inspiral as project/tool) were far more effective than abstract rule descriptions for steering model behaviour.

Specific rules added to reach 100%:
- Reflective/medical context signal phrases block false project/tool extraction
- Unknown words in tool-usage context are only extracted if they are recognizable technologies
- Comparison-only tool mentions ("tested X to compare it with Y") extract only the tested entity
- Trailing UI/feature words (dashboard, auth, onboarding, page) are stripped from project names
- Standalone generic role words (council, team, proposal) are blocked from extraction

### Date Normalization — Timezone-Aware Calendar Grounding
The `normalize` node now receives the browser's IANA timezone with each journal entry, computes the user's local "today" in Python, and injects a Monday-anchored calendar reference into the Gemini prompt. The prompt explicitly tells Gemini not to calculate dates itself and to look every relative date up from the provided calendar block, which removes the original `next monday` off-by-one bug and stabilizes month-end, year-end, and timezone rollover cases.

Latest live normalize evaluation (`normalize_evaluation.py`, 25 diverse Gemini-backed cases):
- Functional pass rate: **64% → 96%**
- Date case accuracy: **68% → 100%**
- Date F1: **0.72 → 1.00**
- No-date hallucination rate: **66.7% → 100%**
- Average latency: **1039ms → 829ms**

### RAG Evaluation — 4 Runs, Data-Driven Decisions
Built a 15-test-case evaluation framework measuring retrieval F1, keyword accuracy, and hallucination rate. Used it to:
- Diagnose NULL embedding failures (F1: 0.0 → 0.333 after backfill)
- Evaluate query rewriting (+8.3% F1 but 50x latency — reverted)
- Validate that basic vector search is optimal for current data size

### Ask Memory Compaction - Eval-Driven Prompt Tuning
Refactored Ask memory into reusable prompt builders and built a **50-case synthetic evaluation harness** for both long-term memory compaction and downstream Ask memory usage. The tuned prompt now stores sectioned long-term memory, applies clearer evidence precedence in `/ask`, and makes unsupported-question honesty measurable instead of anecdotal.

Latest live memory evaluation (`memory_compaction_evaluation.py`, 36 compaction cases + 14 Ask cases):
- Compaction format compliance: **36.1% -> 91.7%**
- Compaction section placement accuracy: **44.4% -> 77.8%**
- Compaction forbidden-fact leakage: **9.7% -> 11.1%**
- Compaction deterministic pass rate: **25.0% -> 52.8%**
- Ask memory keyword recall: **85.7% -> 100%**
- Ask hallucination score: **0.893 -> 1.000**
- Ask precedence correctness: **71.4% -> 100%**
- Ask unsupported-question honesty: **85.7% -> 100%**

### Insight Engine — Hybrid Caching
Dashboard reads cached insights from the database (instant load). Fresh insights regenerate in the background after each new journal entry. Pattern detection and forgotten project analysis powered by Gemini 2.5 Pro.

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

## Test Coverage

| Harness | Tests | Coverage |
|---|---|---|
| `test_extract_entities.py` | 41 | 10 families: happy_path, negative_generic, date_leaks, dedup, disambiguation, false_project_promotion, formatting, project_positive, task_boundary, ambiguous |
| `test_store_entities.py` | 6 | Case-insensitive dedup, same-batch dedup, type separation, mention count updates |
| `test_store_project_matching.py` | 24 | Spacing/case/hyphen/underscore variants, risky collisions, clearly-different names |
| `test_extract_relations.py` | 16 | Relation parsing: multi-entity, symmetric relations, confidence scoring, edge cases |
| `test_store_relations.py` | 4 | Insert, upsert dedup, unresolved entity skip, symmetric relation normalization |
| `normalize_evaluation.py` | 25 | Live Gemini normalize evaluation: weekday lookups, offsets, month/year boundaries, slang cleanup, no-date hallucination resistance, timezone rollover |
| `rag_evaluation.py` | 15 | Retrieval F1, keyword accuracy, hallucination rate |
| `memory_compaction_evaluation.py` | 50 | Synthetic Ask memory evaluation: stable_fact_extraction, ignore_assistant_filler, existing_memory_dedup, contradiction_update, newer_replaces_stale, multi_topic_merge, preference_vs_transient, goals_vs_vague_wishes, tools_people_project_separation, negative_no_durable_fact, formatting_robustness, resolved_or_changed, memory_only_answer, recent_history_override, journal_evidence_override, unsupported_question_honesty |
| **Total** | **181** | |

---

## API Endpoints

| Method | Path | Description |
|---|---|---|
| POST | `/entries/async` | Submit entry — instant response, background processing |
| GET | `/entries` | Fetch stored entries for authenticated user |
| GET | `/entries/{id}/status` | Poll pipeline stage for a processing entry |
| POST | `/ask` | RAG + conversation memory - ask questions about your journal |
| GET | `/ask/history` | Fetch recent Ask conversation history for the authenticated user |
| GET | `/ask/memory` | Inspect compacted long-term Ask memory for the authenticated user |
| GET | `/search` | Semantic similarity search on entries |
| GET | `/deadlines` | Fetch upcoming deadlines |
| GET | `/entities` | Fetch extracted entities ranked by mention count |
| GET | `/entity-relations` | Fetch LLM-extracted semantic relations between entities |
| GET | `/insights` | Read all cached insights |
| GET | `/insights/patterns` | Read cached behavioural pattern analysis |
| GET | `/insights/weekly` | Read cached weekly digest |
| GET | `/insights/forgotten` | Read cached forgotten projects detection |
| GET | `/health` | Health check |

All endpoints except `/health` require JWT authentication via Supabase Auth.

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
SUPABASE_SERVICE_ROLE_KEY=your_service_role_key
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
│   ├── insights_engine.py   # Pattern detection + weekly digest + forgotten projects
│   └── nodes/
│       ├── normalize.py         # Text cleanup + date resolution
│       ├── dedup.py             # Semantic duplicate detection
│       ├── classify.py          # Multi-label categorization
│       ├── extract_entities.py  # Entity extraction (41-test prompt)
│       ├── extract_relations.py # Semantic relation extraction
│       ├── deadline.py          # Deadline detection
│       ├── title_summary.py     # Auto title + summary
│       └── store.py             # Supabase storage + 3-stage entity linking
├── mindgraph-frontend/
│   └── src/
│       ├── App.js                    # Route controller + authenticated app shell
│       ├── supabaseClient.js         # Supabase client singleton
│       ├── components/
│       │   ├── LandingPage.js        # Marketing landing page
│       │   ├── AuthView.js           # Login / signup form
│       │   ├── Dashboard.js          # Main dashboard: entries, insights, deadlines
│       │   ├── InputView.js          # Journal entry input with pipeline status
│       │   ├── KnowledgeGraph.js     # Interactive force-directed entity graph
│       │   ├── AskView.js            # RAG-powered Q&A over journal entries
│       │   ├── Sidebar.js            # Navigation sidebar
│       │   ├── AnimatedView.js       # Page transition wrapper
│       │   └── Toast.js              # Notification toasts
│       ├── styles/
│       │   ├── variables.css         # Design tokens (colours, spacing, typography)
│       │   ├── global.css            # Reset + base styles
│       │   ├── app-shell.css         # Layout + sidebar shell
│       │   ├── landing.css           # Landing page styles
│       │   ├── auth.css              # Auth form styles
│       │   ├── dashboard.css         # Dashboard layout + cards
│       │   ├── input.css             # Entry input + pipeline progress
│       │   ├── knowledge-graph.css   # Graph canvas + legend + controls
│       │   ├── ask.css               # Ask view + chat bubbles
│       │   ├── sidebar.css           # Sidebar + nav items
│       │   ├── toast.css             # Toast notification styles
│       │   └── responsive.css        # Mobile breakpoints
│       └── utils/
│           ├── auth.js               # Auth helpers (session, redirect)
│           ├── constants.js          # App-wide constants
│           └── dateHelpers.js        # Date formatting utilities
├── test_extract_entities.py     # 41-case entity extraction harness
├── test_store_entities.py       # 6-case store integration tests
├── test_store_project_matching.py  # 24-case project normalization harness
├── rag_evaluation.py            # 15-test-case RAG evaluation framework
├── reset_and_reextract.py       # Full entity reset + re-extraction for all users (FK-safe)
├── backfill_relations.py        # One-time relation backfill for entries with 2+ entities
├── backfill_embeddings.py       # Backfill entity embeddings for existing rows
├── backfill_entry_embeddings.py # Backfill entry-level embeddings for RAG retrieval
├── Dockerfile
├── docker-compose.yml
└── requirements.txt
```

---

## License

MIT
