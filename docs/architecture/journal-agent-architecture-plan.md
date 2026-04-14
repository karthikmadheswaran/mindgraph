# Journal Agent — Complete Architecture Plan

> **One textbox. Zero friction. AI does all the organizing.**
>
> A LangGraph-powered journal agent for people with messy thoughts who want one place to dump everything and get structured insights about their life, projects, and patterns.

---

## Table of Contents

- [Vision & Core Philosophy](#vision--core-philosophy)
- [Key Decisions](#key-decisions)
- [High-Level Architecture](#high-level-architecture)
- [System Design (Detailed)](#system-design-detailed)
- [The User Experience](#the-user-experience)
- [LangGraph Processing Pipeline](#langgraph-processing-pipeline)
- [Memory Architecture (No Amnesia System)](#memory-architecture-no-amnesia-system)
- [Insight & Pattern Engine](#insight--pattern-engine)
- [Database Schema](#database-schema)
- [Tech Stack](#tech-stack)
- [1-Month MVP Roadmap](#1-month-mvp-roadmap)
- [Learning Path](#learning-path)
- [Risks & Mitigations](#risks--mitigations)
- [Design Principles to Protect](#design-principles-to-protect)

---

## Vision & Core Philosophy

The problem: Existing journals and project management tools add friction — titles, categories, project structures, tags, options everywhere. People with messy, fast-moving thoughts use them for one day and stop.

The solution: One text box. You dump your thoughts — messy, unstructured, stream-of-consciousness. An AI agent processes everything behind the scenes: categorizes, tracks projects, detects deadlines, finds patterns, reminds you of forgotten things, and gives you a structured view of your life.

**What this is:** A personal intelligence layer for your messy brain.
**What this is NOT:** A therapeutic agent. It observes and reports patterns factually — never gives mental health advice or emotional guidance.

---

## Key Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Deployment | Cloud-hosted (accessible anywhere, phone too) | Dump thoughts from anywhere — phone, laptop, tablet |
| Input types | Text + Voice + Photos/Screenshots | Maximum flexibility, minimum friction |
| Skill level | Strong Python, new to LangGraph/LLMs | Shapes the learning path and MVP scope |
| Target users | Personal first, multi-user eventually | Multi-tenant architecture from day one |
| Budget | Best experience, cost no concern | Use strongest models, managed infrastructure |
| MVP timeline | 1 month, steady pace | Balanced between speed and quality |

---

## High-Level Architecture

```
┌─────────────────────────────────────────────────────┐
│                    CLIENT (PWA)                       │
│  ┌───────────────────────────────────────────────┐   │
│  │         Single Text Box + Mic + Camera         │   │
│  └───────────────────────────────────────────────┘   │
│  ┌───────────────────────────────────────────────┐   │
│  │         Dashboard (auto-generated)             │   │
│  └───────────────────────────────────────────────┘   │
└──────────────────────┬──────────────────────────────┘
                       │ HTTPS / WebSocket
                       ▼
┌─────────────────────────────────────────────────────┐
│                  FastAPI Backend                      │
│                                                      │
│  POST /entries    ← text, audio, image               │
│  GET  /dashboard  ← structured life overview         │
│  GET  /search     ← "what was that thing about..."   │
│  GET  /insights   ← patterns, reminders, warnings    │
│  WS   /stream     ← real-time processing status      │
└──────────┬──────────────────────────┬───────────────┘
           │                          │
     Sync (fast ack)          Async (background)
           │                          │
           ▼                          ▼
┌──────────────────┐    ┌──────────────────────────┐
│ Input Preprocessor│    │   LangGraph Pipeline      │
│                   │    │                           │
│ Voice → Deepgram  │    │  [Normalize & Enrich]     │
│ Image → Claude    │    │          │                │
│   Vision          │    │  [Semantic Dedup]         │
│ Text → passthru   │    │          │                │
│                   │    │  [Classify & Tag]         │
│ Returns: unified  │    │          │                │
│ text + metadata   │    │  [Extract Entities]       │
│                   │    │          │                │
└──────────────────┘    │  [Detect Deadlines]        │
                        │          │                  │
                        │  [Auto-Title & Summarize]   │
                        │          │                  │
                        │  [Store & Index]            │
                        │          │                  │
                        │  [Trigger Alerts?]          │
                        └──────────────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────┐
│              Postgres + pgvector (Supabase)           │
│                                                      │
│  entries, projects, entities, deadlines, tags,       │
│  summaries, insights, usage_log                      │
└─────────────────────────────────────────────────────┘
                                   │
                        ┌──────────┴──────────┐
                        ▼                     ▼
             ┌──────────────────┐  ┌──────────────────┐
             │  Insight Engine   │  │  Summary Engine   │
             │  (scheduled)      │  │  (scheduled)      │
             │                   │  │                   │
             │  Daily: quick     │  │  Weekly: by       │
             │  scan for         │  │  category          │
             │  forgotten items  │  │                   │
             │                   │  │  Monthly: roll up │
             │  Weekly: deep     │  │  weeklies          │
             │  pattern analysis │  │                   │
             │  (Claude Opus)    │  │  Per-project:     │
             │                   │  │  on every mention  │
             └──────────────────┘  └──────────────────┘
```

---

## System Design (Detailed)

### Layer 1: Input Gateway

Everything enters through one endpoint, but preprocessing differs by type:

- **Text** → passes straight through
- **Voice** → Deepgram Nova-2 for speech-to-text, then passes as text
- **Image/Screenshot** → Claude Vision extracts text and describes content, then passes as text

**Critical design principle:** By the time input hits the LangGraph pipeline, everything is text with metadata (`input_type`, `timestamp`, `raw_attachment_url`). This keeps the downstream agent simple.

### Layer 2: LangGraph Processing Pipeline

Multi-step graph that processes every incoming entry:

1. **Normalize & Enrich** — clean text, resolve relative dates ("tomorrow" → actual date), fix obvious typos
2. **Semantic Dedup Check** — vector search against recent entries. "Did I already say this?" If duplicate, link to existing entry and skip.
3. **Multi-Label Classifier** — work / personal / health / family / hobby / finance. Multiple tags per entry.
4. **Entity Extractor** — projects, people, tools, places. Links to existing entities or creates new ones automatically.
5. **Deadline & Commitment Detector** — "by Friday", "next week", "need to finish"
6. **Auto-Title & Summary Generator** — short title and one-line summary for the structured view.
7. **Store & Index** — write to Postgres + vector DB.
8. **Trigger Check** — should we alert about forgotten projects? Any pattern worth surfacing right now?

Each step is a **node** in LangGraph. The state object passed between them accumulates all extracted info. Conditional edges allow skipping irrelevant steps (e.g., skip deadline detection for pure reflections).

### Layer 3: Memory Architecture

See [dedicated section below](#memory-architecture-no-amnesia-system).

### Layer 4: Insight & Pattern Engine

See [dedicated section below](#insight--pattern-engine).

### Layer 5: Frontend (PWA)

Progressive Web App — one codebase, works on all devices, installable on phone home screen, works offline (queue entries, sync later).

**Two views only:**

1. **Input view (default):** One text box. A mic button. A camera/upload button. That's it. Placeholder: "what's on your mind?" When you hit send, brief acknowledgment: "Got it. Tagged: work, Project Alpha. Deadline noted: Friday."

2. **Dashboard view:** Auto-generated, never manually maintained. Shows active projects, upcoming deadlines, recent patterns, abandoned items, weekly summary.

---

## The User Experience

### Posting an Entry

You open the app on your phone. One text box. You type:

> "met with rahul about the api redesign, he wants to use graphql but i think rest is fine for now. also need to call mom this week. been having headaches again maybe its the screen time. oh and i saw this cool rust wasm project might try it this weekend"

You hit send. In under 2 seconds you see:

> ✓ Got it. Work: API Redesign (with Rahul). Personal: Call mom. Health: Headaches noted. New interest: Rust + WASM.

Behind the scenes, the pipeline is:
- Creating/updating an "API Redesign" project, linking Rahul as a collaborator
- Adding "call mom" as a soft deadline for this week
- Logging a health entry about headaches, checking if this is a pattern
- Noting Rust+WASM as a new interest, starting a watch — if you never mention it again, it surfaces in "shiny objects you dropped"

### The Dashboard (Auto-Generated)

```
📋 Active Projects
  API Redesign — last mentioned today, ongoing with Rahul
  LangGraph Journal App — last mentioned 3 days ago
  ⚠️ Freelance Client Website — not mentioned in 12 days, deadline was Feb 20

⏰ Upcoming
  Call mom — this week
  API Redesign decision — no explicit deadline but seems time-sensitive

🔍 Patterns Detected
  Headaches: 3 mentions in last month, correlating with weeks you
  mentioned late-night coding sessions
  You tend to start new tech interests on weekends and abandon by Wednesday

💡 Insights
  You've mentioned Rahul in 14 entries — he's your most frequent
  work collaborator but you've expressed frustration 4 times
```

### Asking the Agent

You type: "what happened with that client project?"

The agent searches your entries via RAG, finds the freelance client website project, and gives you a chronological summary of everything you've said about it, including the deadline you forgot.

---

## LangGraph Processing Pipeline

### Graph Structure

```
START
  │
  ▼
[Normalize & Enrich]  ← clean text, resolve "tomorrow" to actual date
  │
  ▼
[Semantic Dedup Check] ← vector search against recent entries
  │
  ├── duplicate → link to existing entry, skip rest
  │
  ▼
[Multi-Label Classifier] ← work / personal / health / family / hobby / finance
  │
  ▼
[Entity Extractor] ← projects, people, tools, places
  │                   links to existing entities or creates new ones
  │
  ▼
[Deadline & Commitment Detector] ← "by Friday", "next week", "need to finish"
  │
  ▼
[Auto-Title & Summary Generator]
  │
  ▼
[Store & Index] ← write to Postgres + vector DB
  │
  ▼
[Trigger Check] ← should we alert about forgotten projects?
  │                 any pattern worth surfacing right now?
  │
  ▼
END → return brief acknowledgment to user
```

### Key Implementation Notes

- **State object** flows through all nodes, accumulating extracted information
- **Conditional edges** allow skipping nodes (e.g., no deadline extraction for pure reflections)
- **Error handling** at each node — if entity extraction fails, the entry still gets stored with whatever was extracted
- **Async processing** — the user gets an acknowledgment immediately, the full pipeline runs in the background
- The acknowledgment is generated after the classifier node (fast), while deeper processing continues

---

## Memory Architecture (No Amnesia System)

This is the most critical technical layer. As entries grow to thousands over months/years, you can't stuff them all into LLM context windows. The solution is hierarchical memory.

### Dual Storage in Postgres + pgvector

- **Structured tables:** entries, projects, entities, deadlines, tags, patterns — for precise queries ("show me all deadlines this week", "entries tagged health in last 30 days")
- **Vector column on entries:** embedding of each entry for semantic search ("what was I thinking about that Rust side project?" finds it even if you never said "Rust")

### Hierarchical Summarization

Four levels of memory, from granular to compressed:

1. **Raw entries** — everything, forever, never deleted
2. **Weekly auto-summaries** — LLM summarizes each week's entries per category ("This week in Work: shipped feature X, started exploring LangGraph...")
3. **Monthly roll-ups** — summarize the weekly summaries into monthly overviews
4. **Project-level running summaries** — for each detected project, a living document that updates every time you mention it

### Retrieval Strategy

When the insight engine or user asks a question:

1. First search the **appropriate summary level** (weekly/monthly/project) for broad context
2. Then drill into **raw entries** only when specific detail is needed
3. Use **vector similarity** for fuzzy queries ("that thing about APIs") and **structured queries** for precise ones ("deadlines this week")

This keeps context windows manageable even after a year of daily entries.

---

## Insight & Pattern Engine

### Two Operating Modes

**Scheduled (cron jobs):**

| Frequency | Task | Model |
|---|---|---|
| Daily | Scan for stale projects (not mentioned in 7+ days), upcoming deadline warnings | Claude Sonnet |
| Weekly | Deep pattern analysis — behavioral patterns, repeated mistakes, mood/energy trends, abandoned interests | Claude Opus |
| Monthly | Life overview — major themes, project progress, personal growth areas | Claude Opus |
| On entry | Update project running summary if relevant project mentioned | Claude Haiku |

**On-demand (user asks):**

- RAG query across summaries and raw entries
- Generates structured answers to questions like "what's going on with my life?" or "when did I last exercise?"
- Can produce a "state of your life" report on request

### What the Insight Engine Detects

- **Forgotten projects:** "You mentioned Project X five times in the last two weeks but haven't touched it in 10 days."
- **Shiny object pattern:** "You started learning Rust two months ago, mentioned it excitedly for a week, then never again."
- **Repeated mistakes:** "You've committed to deadlines you missed 4 out of 6 times — you might be overcommitting."
- **Health correlations:** "You complained about sleep three times this month, always after late-night coding sessions."
- **Relationship patterns:** "You've mentioned Rahul in 14 entries — most frequent collaborator, but frustration expressed 4 times."
- **Interest cycles:** "Your weekend interests average 5 days of engagement before dropping off."
- **Commitment tracking:** "You said you'd call mom — it's been 6 days."

---

## Database Schema

```sql
-- Users
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email VARCHAR(255) UNIQUE NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    settings JSONB DEFAULT '{}'
);

-- Core entries - the sacred raw data
CREATE TABLE entries (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id),
    raw_text TEXT NOT NULL,
    cleaned_text TEXT,
    auto_title VARCHAR(200),
    summary TEXT,
    input_type VARCHAR(20) DEFAULT 'text',  -- text, voice, image
    attachment_url TEXT,                      -- original voice/image file
    embedding vector(1536),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    source_metadata JSONB                    -- device, location if permitted
);

-- Auto-detected projects
CREATE TABLE projects (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id),
    name VARCHAR(200),
    status VARCHAR(20) DEFAULT 'active',     -- active, stale, completed, abandoned
    first_mentioned_at TIMESTAMPTZ,
    last_mentioned_at TIMESTAMPTZ,
    mention_count INT DEFAULT 1,
    running_summary TEXT,                    -- updated by summary engine
    detected_deadline TIMESTAMPTZ,
    related_entities JSONB
);

-- People, tools, places, topics
CREATE TABLE entities (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id),
    name VARCHAR(200),
    entity_type VARCHAR(50),                 -- person, tool, place, topic, hobby
    first_seen_at TIMESTAMPTZ,
    last_seen_at TIMESTAMPTZ,
    mention_count INT DEFAULT 1,
    context_summary TEXT
);

-- Many-to-many relationships
CREATE TABLE entry_projects (
    entry_id UUID REFERENCES entries(id),
    project_id UUID REFERENCES projects(id),
    PRIMARY KEY (entry_id, project_id)
);

CREATE TABLE entry_entities (
    entry_id UUID REFERENCES entries(id),
    entity_id UUID REFERENCES entities(id),
    PRIMARY KEY (entry_id, entity_id)
);

-- Category tags per entry
CREATE TABLE entry_tags (
    entry_id UUID REFERENCES entries(id),
    category VARCHAR(50),                    -- work, personal, health, family, hobby, finance
    confidence FLOAT,                        -- model's confidence in this tag
    PRIMARY KEY (entry_id, category)
);

-- Deadlines extracted from entries
CREATE TABLE deadlines (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id),
    source_entry_id UUID REFERENCES entries(id),
    description TEXT,
    due_date TIMESTAMPTZ,
    status VARCHAR(20) DEFAULT 'pending',    -- pending, completed, missed
    project_id UUID REFERENCES projects(id)
);

-- Hierarchical summaries for memory management
CREATE TABLE summaries (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id),
    summary_type VARCHAR(20),                -- weekly, monthly, project
    category VARCHAR(50),                    -- work, personal, health, etc. (null for project type)
    period_start DATE,
    period_end DATE,
    project_id UUID REFERENCES projects(id), -- non-null only for project summaries
    content TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Generated insights and patterns
CREATE TABLE insights (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id),
    insight_type VARCHAR(50),                -- pattern, reminder, warning, observation
    content TEXT,
    severity VARCHAR(20) DEFAULT 'info',     -- info, attention, urgent
    related_project_id UUID REFERENCES projects(id),
    is_read BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Track API costs per user from day one
CREATE TABLE usage_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id),
    model VARCHAR(50),
    input_tokens INT,
    output_tokens INT,
    cost_usd DECIMAL(10,6),
    operation VARCHAR(50),                   -- classify, extract, summarize, insight
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes
CREATE INDEX idx_entries_user_created ON entries(user_id, created_at DESC);
CREATE INDEX idx_projects_user_status ON projects(user_id, status);
CREATE INDEX idx_deadlines_user_due ON deadlines(user_id, due_date) WHERE status = 'pending';
CREATE INDEX idx_insights_user_unread ON insights(user_id, created_at DESC) WHERE is_read = FALSE;
CREATE INDEX idx_entities_user_type ON entities(user_id, entity_type);
```

---

## Tech Stack

| Component | Choice | Why |
|---|---|---|
| **Agent Orchestration** | LangGraph | Multi-step processing with state, conditional logic, perfect for the pipeline |
| **LLM (heavy tasks)** | Claude Opus | Weekly/monthly deep insight generation, complex pattern finding |
| **LLM (medium tasks)** | Claude Sonnet | Entry classification, entity extraction, daily insights |
| **LLM (light tasks)** | Claude Haiku | Auto-titling, simple summarization, project summary updates |
| **Speech-to-text** | Deepgram Nova-2 | Best accuracy for messy/fast speech |
| **Image understanding** | Claude Vision (Sonnet) | Extract text from screenshots, understand photos |
| **Database** | Postgres + pgvector (Supabase) | Single DB for structured data + vector search, managed hosting, built-in auth |
| **Backend** | FastAPI | Python-native, async, great for APIs |
| **Frontend** | Next.js or SvelteKit (PWA) | Responsive, installable on phone, minimal UI |
| **Hosting** | Railway or Fly.io | Simple deployment, scales fine, Postgres support |
| **Background Jobs** | Celery + Redis or APScheduler | For periodic insight engine and async processing |
| **Auth** | Supabase Auth | Comes free with Supabase, supports multi-tenant |
| **File Storage** | Supabase Storage or S3 | For voice recordings and images |
| **Embeddings** | OpenAI text-embedding-3-small or Anthropic | For vector search (1536 dimensions) |

---

## 1-Month MVP Roadmap

### Week 1: Foundation

- [ ] Set up Supabase project (Postgres + pgvector + auth + storage)
- [ ] Create database schema (all tables above)
- [ ] Set up FastAPI project structure with auth middleware
- [ ] Basic entry creation endpoint (text only)
- [ ] Integrate Anthropic SDK — call Claude Sonnet to classify, extract entities, auto-title a raw entry
- [ ] Write the LangGraph pipeline with initial nodes: normalize → classify → store
- [ ] Verify entries are stored with embeddings and metadata

### Week 2: Intelligence

- [ ] Add entity linking (detect if "Rahul" is the same Rahul from last week using fuzzy matching + context)
- [ ] Add project detection and tracking (create/update projects table automatically)
- [ ] Add deadline extraction from natural language
- [ ] Implement semantic dedup using vector similarity search
- [ ] Expand LangGraph to full pipeline (all 8 nodes)
- [ ] Build the "ask a question about my entries" RAG endpoint
- [ ] Test with 50+ sample entries to verify quality

### Week 3: Frontend + Multimodal

- [ ] Build PWA: input view (one textbox + mic + camera buttons)
- [ ] Build PWA: dashboard view (projects, deadlines, recent entries, insights)
- [ ] Integrate Deepgram for voice-to-text input
- [ ] Integrate Claude Vision for image/screenshot input
- [ ] WebSocket connection for real-time processing feedback
- [ ] Dashboard auto-generation from database state
- [ ] Mobile-responsive design, test on phone

### Week 4: Insight Engine + Polish

- [ ] Daily scheduled job: stale project detection, deadline warnings
- [ ] Weekly scheduled job: deep pattern analysis with Claude Opus
- [ ] "Shiny object" detector (interests mentioned once then dropped)
- [ ] Repeated mistake/complaint pattern detection
- [ ] Health correlation detection
- [ ] Deploy to Railway/Fly.io with production Supabase
- [ ] Start using it yourself daily
- [ ] Bug fixes and prompt tuning based on real usage

---

## Learning Path

Since you're strong in Python but new to LangGraph/LLMs:

### Phase 1 — LLM Fundamentals (Days 1-4)

Get comfortable with calling LLM APIs directly using the Anthropic SDK. Build a simple script that takes messy text and returns structured JSON (title, category, entities, deadlines). No LangGraph yet — just raw API calls. This builds intuition for prompt engineering.

Key resources:
- Anthropic SDK documentation
- Anthropic prompt engineering guide
- Practice: write prompts that classify messy text into categories

### Phase 2 — LangGraph Basics (Days 5-9)

Go through the official LangGraph tutorials. Build the processing pipeline as a graph. State management, nodes, edges, conditional routing.

Key concepts to learn:
- StateGraph and state schemas
- Node functions and edge routing
- Conditional edges
- Checkpointing (built-in memory for graph runs)

### Phase 3 — Embeddings & RAG (Days 10-14)

Set up Postgres with pgvector. Build the embedding + retrieval system. Implement the dedup check. This is where you'll spend the most debugging time — getting retrieval quality right is iterative.

Key concepts:
- How text embeddings work
- Similarity search (cosine distance)
- Chunking strategies
- RAG pipeline: retrieve → augment → generate

### Phase 4 — Build the MVP (Days 15-24)

Follow the week-by-week roadmap above. You'll have enough knowledge to build and iterate.

### Phase 5 — Iterate on Quality (Days 25-30)

Use it yourself. Tune prompts. Fix edge cases. Add the insight engine.

---

## Risks & Mitigations

### 1. Retrieval Quality Degradation Over Time

**Risk:** After 6 months of entries, finding the right context becomes harder. Semantic search returns less relevant results.

**Mitigation:** Hierarchical summarization from day one. Weekly/monthly summaries compress old entries. Project-level summaries maintain focused context. Don't rely on searching raw entries alone for old data.

### 2. Latency on Entry Submission

**Risk:** If every entry triggers 5-6 LLM calls and takes 10+ seconds, it feels laggy and adds friction.

**Mitigation:** Return acknowledgment to user in under 2 seconds using a fast classifier call. Process the rest asynchronously in the background. Update dashboard via WebSocket when processing completes.

### 3. Cost Creep at Scale

**Risk:** Multimodal (vision, speech) + multiple LLM calls per entry adds up. At 5-10 entries/day for multiple users, costs grow.

**Mitigation:** Use model tiering aggressively — Haiku for routine tasks, Sonnet for classification, Opus only for weekly deep analysis. Track costs per user in usage_log table from day one. Estimated cost: $50-100/month for a single active user at current prices.

### 4. Entity Resolution Errors

**Risk:** The agent thinks "Rahul from work" and "Rahul (cousin)" are the same person, or treats "the project" references ambiguously.

**Mitigation:** Use context-aware entity linking — compare surrounding text, not just names. Allow users to correct entity merges (minimal friction: just a "these aren't the same" button on the dashboard). Over time, the corrections improve accuracy.

### 5. Over-Engineering Before Validation

**Risk:** You build a complex multi-model insight engine before confirming the basic input → organize loop is valuable.

**Mitigation:** MVP is text input + basic classification + storage + simple dashboard. Use it for 2 weeks before adding insight engine. If the core dump-and-organize flow doesn't stick, insights won't save it.

### 6. The Builder's Shiny Object Problem

**Risk:** You described yourself as someone who chases shiny things. Building this tool is itself a shiny thing.

**Mitigation:** Commit to the 4-week roadmap. Week 1 is boring (database setup, basic API). That's intentional. If you get through Week 1, you'll have momentum. Scope the MVP ruthlessly — no voice or image input until Week 3.

---

## Design Principles to Protect

These are non-negotiable. Print them out if you have to.

1. **The input must stay one textbox.** Every time you're tempted to add a dropdown, a tag selector, a "choose project" button — don't. That's the agent's job.

2. **Acknowledge fast, process slow.** The user gets confirmation in under 2 seconds. Heavy processing happens async. Never make the user wait for the full pipeline.

3. **The agent's job is to reduce chaos, not add structure the user has to maintain.** Projects, tags, categories — all auto-managed. The user can correct things but never has to create or organize.

4. **Never be therapeutic.** The agent observes patterns and reports them factually. "You mentioned headaches 3 times this month" — NOT "Have you considered that your headaches might be related to stress?" Big difference.

5. **Messy in, structured out.** The entire value proposition is this transformation. Never ask the user to be more structured. Handle the mess.

6. **No amnesia.** The agent must remember everything, forever. Hierarchical summarization is how you achieve this technically. The user should be able to ask "what was that thing I mentioned 6 months ago about..." and get an answer.

7. **Friction is the enemy.** Every UI element, every extra tap, every "are you sure?" dialog is friction. If you can remove it, remove it. If the agent can handle it, let the agent handle it.

---

## What's Next After MVP

Once the MVP is working and you're using it daily:

- **Smart notifications** — push notifications for missed deadlines, forgotten projects, weekly summaries
- **Natural language queries** — conversational interface: "what have I been stressed about lately?"
- **Export & sharing** — generate formatted reports of project timelines, life summaries
- **Integrations** — pull in calendar events, GitHub commits, email subjects for richer context
- **Multi-user infrastructure** — billing, onboarding, data isolation, admin dashboard
- **Fine-tuned models** — train on your own journal style for better classification accuracy

---

*Architecture plan created: February 2026*
*Status: Pre-development — architecture discussion complete*
