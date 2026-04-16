## The Problem

I built MindGraph to solve the gap between fast, messy thought capture and structured AI memory: people can write thoughts quickly, but most tools still require manual organization before those thoughts become searchable, connected, or useful.

## What I Built

I built MindGraph as a production personal AI engine that turns unstructured text into entities, deadlines, knowledge graph relationships, grounded answers, and progress insights. It runs an 8-node LangGraph pipeline, hybrid RAG retrieval, and an interactive knowledge graph, live at https://rawtxt.in.

## Technical Highlights

- Designed an 8-node LangGraph pipeline with parallel fan-out — 4 extraction nodes run concurrently, reducing latency to under 7 seconds per entry
- Switched LLM mid-project after benchmarking: 10x latency improvement (67s → 6.66s), 30x cost reduction ($0.009 → $0.0003 per entry)
- Built a hybrid RAG retrieval system (pgvector cosine + BM25 + Cohere Rerank v3.5) and ran 4 evaluation rounds to lift F1 from 0.369 to 0.782 — zero hallucinations across all runs
- Eval-driven prompt engineering: entity extraction tuned across a 41-case harness (10 failure families) from 75.6% → 100% pass rate; Ask generation tuned across a 32-case LLM-as-judge harness (Gemini Pro) over 6 iterations
- Shipped production auth hardening for a custom domain (rawtxt.in): Nginx static serving, runtime env injection via /env.js, CORS configuration, and Railway port binding — all verified with auth routing tests

## Stack

LangGraph · FastAPI · React · Supabase (pgvector + tsvector) · Gemini 2.5 · Cohere Rerank · Railway · Langfuse

## Live Demo

https://rawtxt.in — API docs: https://mindgraph-production.up.railway.app/docs — GitHub: https://github.com/karthikmadheswaran/mindgraph
