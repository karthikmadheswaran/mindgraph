## Section A - Profile Headline Options

1. AI/LLM Engineer | LangGraph, RAG Pipelines, FastAPI, Production AI
2. LangGraph + RAG Engineer | Eval-Driven AI Systems | FastAPI + Supabase
3. Production AI Engineer | LLM Apps, Hybrid RAG, Knowledge Graphs, Evals

## Section B - Profile Overview

I build production-grade AI systems that turn messy user input into structured, searchable, and useful product experiences. Clients hire me when they need more than a chatbot: reliable LLM pipelines, measurable retrieval quality, fast APIs, and deployments that hold up in production.

My flagship project is MindGraph, a live personal AI engine at https://rawtxt.in. It captures unstructured thoughts, extracts entities and deadlines, builds a knowledge graph, and answers questions through a hybrid RAG system backed by real evaluation harnesses.

What I specialise in:

- LangGraph pipeline architecture: designed an 8-node parallel fan-out/fan-in pipeline with typed state, async background processing, and per-stage progress polling. Four extraction nodes run concurrently, reducing entry processing to under 7 seconds.
- Model and cost optimization: benchmarked the pipeline model mid-project and switched from a preview model to gemini-2.5-flash-lite, improving latency 10x from 67s to 6.66s and reducing cost 30x from $0.009 to $0.0003 per entry.
- Hybrid RAG systems: built retrieval with pgvector cosine search, Postgres BM25 through tsvector/GIN, Cohere Rerank v3.5, and temporal query routing. The RAG harness improved from F1 0.369 to 0.782 and MRR 0.759 to 0.957, with zero hallucinations across all RAG eval runs.
- Eval-driven prompt engineering: tuned entity extraction across a 41-case harness covering 10 failure families, moving pass rate from 75.6% to 100%. Tuned Ask generation through a 32-case LLM-as-judge harness using Gemini Pro, improving Inference Quality from 4.00 to 4.53 and Conversational Intelligence from 3.87 to 4.47.
- Production deployment: shipped FastAPI + Uvicorn on Railway with Supabase Auth JWT verification, React frontend hosting through Docker + Nginx, custom domain routing on rawtxt.in, runtime env injection through /env.js, and CORS hardening for authenticated browser requests.
- Observability and maintainability: integrated Langfuse for per-node traces, latency, cost, token usage, and trace replay. The codebase includes 225 tests across 9 harnesses covering extraction, storage, relation parsing, normalization, RAG, memory compaction, and generation quality.

My working style is evaluation-first and metric-driven. I start by defining what "good" means, build the smallest production path that can be measured, and then iterate with test cases, traces, and real user behavior. I document the engineering decisions that matter: model choice, retrieval design, prompt rules, data schema, auth boundaries, and deployment tradeoffs.

I am strongest on projects where the AI has to do real work: extract structure, retrieve the right context, reason over product data, and ship behind a usable web app. If you are building an AI product and need someone who ships production-grade pipelines, let's talk.

## Section C - Portfolio Project Entry

MindGraph is my live personal AI engine: https://rawtxt.in. It turns unstructured thought capture into structured memory, deadlines, entity extraction, an interactive knowledge graph, progress insights, and grounded Ask responses through a production LangGraph + FastAPI system.

I designed an 8-node LangGraph pipeline with parallel fan-out/fan-in, Supabase Auth, async background processing, pgvector storage, BM25 search, Cohere Rerank v3.5, and Gemini 2.5 models. The system improved pipeline latency 10x from 67s to 6.66s and reduced cost 30x from $0.009 to $0.0003 per entry. Hybrid RAG evaluation improved F1 from 0.369 to 0.782 and MRR from 0.759 to 0.957, with zero hallucinations across RAG and Ask eval runs. I also hardened the public deployment with Docker, Nginx, runtime env injection, custom-domain auth routing, and CORS. The project is backed by 225 tests across 9 harnesses.

Stack: LangGraph · FastAPI · React · Supabase · Gemini · Cohere · Railway

Live URL: https://rawtxt.in
GitHub: https://github.com/karthikmadheswaran/mindgraph
