# MindGraph viability assessment

## Executive summary

MindGraph is already beyond a “toy” prototype: the GitHub repo shows a full-stack product (React + FastAPI + Supabase + LangGraph) with a defined architecture, a multi-node extraction pipeline, RAG-based Q&A, an interactive force-directed knowledge graph, production deployment, and unusually strong evaluation discipline for an early-stage journal product (e.g., a 41-case entity-extraction harness; broader test coverage reported as 106 total tests; and a small RAG evaluation framework). citeturn3view0turn3view4turn3view3turn8view0

However, as a business, “AI journaling” is already crowded and bifurcated: (a) privacy-first consumer journaling anchored by platform incumbents (especially Apple’s free Journal app with large-scale adoption signals), and (b) AI-first “second brain” products with robust budgets and distribution. citeturn27view0turn26view1turn26view0 MindGraph’s current positioning (“one textbox… your AI organises everything… knowledge graph… projects/tasks/deadlines/patterns”) is differentiable in feature set, but not yet clearly differentiated in *who it is for* and *why it wins vs. existing habits*—the biggest predictor of whether continued investment pays off. citeturn3view0turn3view3

**Recommendation: pivot (continue building, but narrow the wedge + tighten claims and compliance).**  
The most rational next allocation of your time is not “more features”, but (1) a tighter target persona and value proposition where the knowledge-graph + automatic extraction matters weekly, (2) a monetisation design that contains “expensive insights” behind paywalls, and (3) a privacy/compliance posture that can survive user scrutiny (and Google Gemini API terms constraints) for a journaling-adjacent product. citeturn24view0turn24view1turn3view3turn3view1

Key reasons:

1. **Engineering feasibility + cost-efficiency looks strong**: you report a pipeline model switch to Gemini 2.5 Flash-Lite that dramatically reduces latency and per-entry cost, and you have mechanisms for async processing and observability. citeturn3view1turn3view4turn15view1turn13view0  
2. **Differentiation exists, but only if you choose the right job-to-be-done**: automatic entity/relation extraction + project/deadline/people graphs are far more compelling for “work journaling / founder operating system / personal CRM” than for general mood journaling. citeturn3view0turn3view1turn3view3  
3. **Privacy & trust are existential in journaling**: competitors lean hard on end-to-end encryption and/or local-first storage; Apple’s Journal markets privacy and scale; Obsidian markets local storage and E2EE sync. You will need a clear trust model and transparent data handling. citeturn27view0turn16search8turn26view1turn25view1  
4. **Regulatory/terms constraints create real product constraints**: Google’s Gemini API terms and Zero Data Retention mechanics affect what you can safely promise, how you operate in the UK/EU, and how you avoid drifting into “mental health advice”. citeturn24view0turn24view1turn17search10

Primary-source caveat: your linked Notion page could not be retrieved in this environment (HTTP 404), so anything that depends on that page’s content is marked **unspecified**. citeturn4view0

## Current product state and recent changes from primary sources

MindGraph is described in your README as an “AI-powered frictionless journal” with a single textbox input and an LLM pipeline that extracts **people**, **projects**, **deadlines**, and **behavioural patterns**, then visualises them as an interactive knowledge graph. citeturn3view0 The feature set you explicitly claim includes:

- interactive knowledge graph (projects/people focus, with semantic relations) citeturn3view0turn3view1  
- projects & tasks tracking, deadlines extraction, people mapping citeturn3view0  
- “Ask Your Journal” RAG Q&A and semantic search citeturn3view0turn3view3  
- pattern detection (“shiny object syndrome”), forgotten projects detection, weekly digest citeturn3view0turn3view3  

The stated architecture is a React frontend, FastAPI backend, an 8-node LangGraph pipeline, and Supabase (Postgres + pgvector + Auth), with Gemini models for inference and embedding generation. citeturn3view0turn3view1turn3view4 The README also lists observability via entity["company","Langfuse","llm observability platform"]. citeturn3view4turn22view0

Two implementation details matter for business viability because they speak to operational realism:

- You explicitly changed from long-lived streaming to an “acknowledge-fast / process-slow” background task pattern due to entity["company","Railway","pvt ltd | hosting platform"] proxy behaviour, and you persist pipeline stage for progress polling. citeturn3view1turn3view4  
- You describe a three-stage entity linking pipeline (exact normalised match → project-normalised match → embedding similarity gating) to reduce duplicate entities and false merges. citeturn3view1turn8view0  

The repo history shows very recent iteration (commits on April 6–7, 2026), including: replacing a dashboard “mind map” with an interactive knowledge graph; adding semantic entity relations; focusing the graph on people/projects; and improving entity extraction accuracy and store matching. citeturn7view0turn8view0 This is consistent with a product moving from “demo” to “usable daily”, but it also implies core UX and data-model churn that may still be stabilising.

Evidence of engineering discipline is unusually strong for an early product: the README claims a 41-test entity extraction harness, additional test suites for storage/matching and relation extraction, and a total of 106 tests; and your April 7 commit message explicitly describes moving the entity extraction harness from ~75.6% to 100% pass rate via prompt changes and added negative examples. citeturn3view3turn8view0 Separately, you report a small RAG evaluation framework with retrieval F1 around ~0.50 in the final run and a retrieval latency around ~1 second (after rejecting a high-latency query rewriting approach). citeturn3view3turn3view1

Unspecified from primary sources: active users, retention, conversion, revenue, churn, acquisition channels, and the precise “insights” prompt sizes/costs per user—none of these are visible from the GitHub README/commits. citeturn3view0turn7view0

## Market, target personas, and product–market fit potential

### Market signals and user demand

The existence and traction of large journaling and note-taking incumbents is the clearest market signal that “capture + reflection” is a large, long-lived category—while also indicating that generic journaling is hard to differentiate.

- Apple’s *Journal* is free and shows very large App Store engagement (hundreds of thousands of ratings), and it positions itself around reflection, suggestions, and privacy controls. citeturn27view0turn16search0  
- The Day One ecosystem markets itself as “trusted” journaling at scale and claims “over 15 million downloads” and “200,000 5-star ratings globally” in its App Store copy, suggesting both deep competition and a willingness to pay (it has multiple paid tiers). citeturn25view1turn0search20  
- Mood/wellbeing journal apps show similar scale signals: Daylio claims “trusted by 20,000,000+” on its website; Reflectly claims 13M+ downloads/usage and includes subscription pricing; and Reflection markets AI coaching + a premium plan. citeturn25view0turn25view2turn16search3turn25view3  

These signals support a conclusion that **journaling is not a niche**, but they do *not* guarantee PMF for an additional entrant; the category is competitive, habit-based, and trust-sensitive. citeturn27view0turn25view1turn25view2

### Where MindGraph is “naturally” strong

MindGraph’s feature emphasis (projects, tasks, deadlines, people mapping, “forgotten projects”, “shiny object syndrome”, knowledge graph) is closer to a **work journal / founder operating system / personal CRM** than to a mood diary. citeturn3view0turn3view3 This matters because:

- General-purpose mood journaling competitors already provide prompts, mood tracking, and guided reflection with highly polished consumer UX. citeturn25view2turn25view3  
- Your differentiator is *structure extraction* (entities/relations/deadlines) and its downstream value (graph, reminders, “forgotten projects”), which is much more legible to users who want to reduce “context loss” across workstreams. citeturn3view0turn3view1turn3view3  

### Target personas that fit the current product

Based on the README and the recent commits, the most plausible high-fit personas are:

1. **Founder/indie hacker / solo builder**: writes daily “what I did / what I’m stuck on / who I spoke to / what I’m building”, and benefits from automatic recall of projects/people/deadlines and weekly digests. citeturn3view0turn3view3  
2. **Consultant / PM / staff+ engineer**: has many parallel threads; needs a private “work log” that can answer “when did we decide X?” and rebuild the stakeholder map from memory. citeturn3view0turn3view3  
3. **ADHD / “too many ideas” operator (non-medical framing)**: the “shiny object syndrome” and “forgotten projects” concepts suggest a behavioural/productivity use case. This must be positioned carefully to avoid medical claims. citeturn3view0turn24view0  

Personas that are *lower fit* unless you make major changes:

- **Privacy-maximalist diarists**, because they will compare you to on-device or end-to-end encrypted incumbents (Apple Journal; Obsidian local-first) and will ask hard questions about external LLM processing. citeturn27view0turn16search8turn26view1turn24view0  
- **Clinical mental health users**, because Gemini API terms explicitly restrict clinical practice/medical advice use, and because compliance obligations expand rapidly. citeturn24view0turn17search0  

### PMF potential (reasoned assessment)

MindGraph’s PMF potential is **real but conditional**:

- Conditional on finding a wedge where the knowledge graph is not a “cool dashboard”, but a **weekly utility** (e.g., “stakeholder memory”, “commitment tracking”, “project drift detection”). citeturn3view0turn3view3  
- Conditional on building trust quickly through product choices (data minimisation, clear data-use policy, exportability, optional self-host, possibly a “work-only” positioning to reduce sensitivity). citeturn24view0turn24view1turn26view1  
- Conditional on distribution: the repo currently shows 0 stars/0 forks, implying traction is currently small/early and you cannot rely on organic GitHub discovery alone. citeturn2view0  

## Competitive landscape and differentiation

image_group{"layout":"carousel","aspect_ratio":"16:9","query":["Apple Journal app screenshot iPhone","Day One journal app screenshot","Obsidian graph view screenshot","AI journaling knowledge graph visualization"],"num_per_query":1}

### Competitor comparison table

The table below focuses on adjacent products that a target user would plausibly substitute for MindGraph. (Traction figures are taken from public marketing/App Store copy where available; absence means “not found in sources used”.)

| Product (category) | Core strengths (from sources) | Pricing signal (from sources) | Traction signal (from sources) | Where MindGraph differentiates (today) |
|---|---|---|---|---|
| entity["company","Apple Journal","ios journaling app"] (consumer journal) | Free journal app with suggestions, rich media, insights/streaks, iCloud sync, and device locking; designed around reflection and prompting. citeturn27view0turn16search21turn16search0 | Free. citeturn27view0 | 256K ratings (App Store page). citeturn27view0 | MindGraph’s automatic entity/relation extraction + work-oriented “projects/people/deadlines graph” is not the same as Apple’s reflection-first UX. citeturn3view0turn3view1 |
| entity["company","Day One","digital journaling app"] (premium journal) | Cross-platform journaling; privacy and security claims; rich features; long-standing brand. citeturn25view1turn0search20 | Silver $49.99/yr, Gold $74.99/yr (pricing docs). citeturn0search20turn0search4 | “15 million downloads” + “200,000 5-star ratings” claimed in App Store copy. citeturn25view1 | MindGraph’s structured extraction (entities/relations/deadlines) and graph-first dashboard are materially different from “best-in-class journaling UX”. citeturn3view0turn3view4 |
| entity["company","Reflectly","ai journaling app"] (AI mood journal) | AI prompts, mood tracking/analytics, wellbeing framing; subscription-based. citeturn25view2 | $9.99 monthly / $59.99 annually (as described in source). citeturn25view2 | 13M+ downloads/usage and 135K+ ratings claimed. citeturn25view2 | MindGraph is less “CBT/mood coach” and more “knowledge extraction into a work graph” (if positioned as such). citeturn3view0turn3view3 |
| entity["company","Reflection","ai journal app"] (AI journal + coach) | AI coach positioning; guided journals; cross-device; premium plan with “AI search & insights” and writing support. citeturn25view3turn16search3turn16search38 | Premium $5.75/month billed annually + trial (premium page). citeturn16search3 | Marketing claims “3K+ reviews” and “750K+ entries written” badges. citeturn25view3 | MindGraph’s “entity relations knowledge graph” is a sharper structural artefact; you also emphasise evaluation harnesses and retrieval evaluation, which can become a quality lever. citeturn3view1turn3view3 |
| entity["company","Mem","ai notes app"] (AI notes / second brain) | AI-organised notes/search; “thought partner” positioning; freemium to pro. citeturn26view0 | Pro $12/month (pricing page). citeturn26view0 | Unspecified in sources used. citeturn26view0 | MindGraph’s competitive move is a *journal-first capture loop* + explicit “projects/people/deadlines” schema and graph, not generic notes. citeturn3view0turn3view4 |
| entity["company","Obsidian","local-first note app"] (local-first PKM) | Local storage; optional E2EE sync; strong user trust posture (“data stored locally… we don’t collect telemetry”); graph search/publish options. citeturn26view1 | Sync $4/user/month billed annually; Publish $8/site/month billed annually (pricing page). citeturn26view1 | Unspecified in sources used. citeturn26view1 | MindGraph’s advantage is automatic extraction and “zero organisation” beyond writing; Obsidian’s advantage is trust + local-first. citeturn3view0turn26view1 |
| entity["company","Journey","journal app"] (cross-platform journal) | Cross-platform diary with memberships; subscription unlocks features across devices. citeturn18search7turn18search12 | $6.99/month or $49.99/year (App Store listing text). citeturn18search7 | “Over 100,000 5-star reviews” is claimed on Journey’s site (marketing claim). citeturn18search28 | MindGraph’s differentiator is the automatic graph + RAG Q&A over entries, rather than classic diary features. citeturn3view0turn3view3 |
| entity["company","Diarium","cross-platform diary app"] (one-time purchase journal) | Positions as non-subscription; cross-platform; sync via user-controlled clouds. citeturn18search19turn18search4turn18search14 | “One-time purchase per platform, no subscription” (official site / Play listing text). citeturn18search19turn18search4 | Unspecified in sources used. citeturn18search19 | MindGraph differentiates via LLM-based structuring (entities/deadlines/relations) and insights, not pricing model. citeturn3view0turn3view1 |

### Differentiation summary

MindGraph’s strongest differentiation (as implemented) is **turning free-form journaling into a structured, queryable “work memory graph”**:

- You explicitly store semantic relations between extracted entities (edges with confidence + references), which is not a default capability in most journaling apps. citeturn3view1turn3view4  
- You have a “fan-out/fan-in” pipeline where multiple extraction nodes run in parallel after deduplication, which is a sound design approach for latency and modular iteration. citeturn3view0turn3view1  
- You are measuring extraction quality via harnesses and retrieval behaviour via an evaluation script, which is a potential quality moat if you keep it tied to user-relevant outcomes. citeturn3view3turn8view0  

The main “non-differentiation risk” is that AI journaling and AI knowledge apps increasingly converge on similar primitives: prompts, summaries, search, and “ask your notes”. If your graph is primarily a visual novelty and not a retention engine, you will be outcompeted on distribution and trust. citeturn25view3turn26view0turn27view0

## Unit economics, operational costs, and cost model

### What you pay for in this architecture

From the repo README, the principal cost drivers are:

- LLM inference for the pipeline (Gemini 2.5 Flash-Lite) and deeper “insights” (Gemini 2.5 Pro). citeturn3view1turn15view4turn13view0  
- Embedding generation (gemini-embedding-001) and vector storage (Supabase pgvector). citeturn3view1turn14view2turn3view4  
- Hosting for backend/frontend (Railway) and DB/Auth (Supabase). citeturn3view0turn21view0turn20search0  
- Observability (Langfuse), if enabled in production at meaningful volume. citeturn22view0turn22view1  

### Pricing inputs (official/primary sources)

- Gemini 2.5 Flash-Lite: $0.10 / 1M input tokens and $0.40 / 1M output tokens (standard), per Google’s pricing page. citeturn13view0  
- Gemini 2.5 Pro: $1.25 / 1M input tokens and $10.00 / 1M output tokens (≤200k context), per Google’s pricing page. citeturn15view4  
- Gemini Embedding (gemini-embedding-001): $0.15 / 1M input tokens (standard). citeturn14view2  
- Railway pricing includes usage-based CPU/RAM rates and minimum monthly commitments (e.g., Hobby $5 minimum, Pro $20 minimum), plus published per-second unit prices. citeturn21view0  
- Supabase Pro: $25/month with included usage quotas (as shown on the pricing page snippet). citeturn20search0turn20search10  
- Langfuse Core (production baseline) $29/month, with usage-based overage pricing on “units”. citeturn22view0turn22view1  

### Cost model assumptions (explicit)

Because the Notion page is unavailable and the repo does not include production usage telemetry, the following are *assumptions for modelling*, not claims:

- “Active user” means **monthly active user (MAU)**.  
- Each MAU writes **15 entries/month** (roughly every other day).  
- Pipeline LLM processing cost is **$0.0003 per entry** as stated in the README after switching to Flash-Lite (treated as the all-in pipeline LLM cost baseline). citeturn3view1  
- Each entry averages **500 tokens** for embedding. Embed cost uses Gemini Embedding pricing. citeturn14view2  
- Each MAU asks **3 “Ask Your Journal” questions/month**, answered using Flash-Lite pricing (token assumptions stated in table). citeturn13view0turn3view3  
- Insights/pattern detection using Gemini 2.5 Pro are modelled in two modes:  
  - **Lite mode**: no Pro insights (or paid-only).  
  - **Premium mode**: Pro insights generated weekly (4×/month), with conservative token estimates. citeturn3view3turn15view4  

### Estimated monthly run-rate (100 / 1k / 10k MAU)

All amounts USD/month; infra costs are approximate because Railway billing is usage-based and depends on deployed resources, but the unit prices are sourced from Railway. citeturn21view0

| MAU | LLM variable cost (Lite mode) | LLM variable cost (Premium mode: weekly Pro insights) | Fixed-ish infra baseline (indicative) | Total (Lite) | Total (Premium) |
|---:|---:|---:|---:|---:|---:|
| 100 | ~$0.68 | ~$13.68 | ~$75–$120 | ~$76–$121 | ~$89–$134 |
| 1,000 | ~$6.83 | ~$136.83 | ~$90–$180 | ~$97–$187 | ~$227–$317 |
| 10,000 | ~$68.25 | ~$1,368.25 | ~$180–$450 | ~$248–$518 | ~$1,548–$1,818 |

**What’s inside “fixed-ish infra baseline”:**

- entity["company","Supabase","backend-as-a-service"] Pro ~$25/month (base subscription) citeturn20search0turn20search10  
- entity["company","Langfuse","llm observability platform"] Core $29/month (if enabled for production). citeturn22view0turn22view1  
- entity["company","Railway","pvt ltd | hosting platform"] usage (example always-on services): using Railway’s published CPU/RAM price-per-second, an always-on 1 vCPU + 1 GB service is on the order of tens of dollars/month; larger instances scale roughly linearly. citeturn21view0  

**Interpretation:** Your Flash-Lite pipeline makes “per-entry structuring” extremely cheap at scale; the economic risk is not the extraction pipeline but **any Pro-powered insight workflows** that run per entry or at high frequency. If you make Pro insights part of a free tier, your burn can scale quickly; if you gate them behind paid plans, your gross margins can remain strong. citeturn3view1turn15view4turn13view0

A second-order cost risk is **database growth**: storing raw entries plus embeddings (1536-d vectors) for 10k MAU who write frequently can push you beyond included database storage; Supabase pricing beyond included quotas is usage-based and not fully specified in the sources captured here, so overage costs remain **unspecified**. citeturn3view1turn20search0turn20search10

## Technical moat, engineering risks, and scaling challenges

### Technical moat: what you have that can compound

MindGraph’s most credible “moat ingredients” visible from the repo are:

- **An explicit information model** (entities, typed relations, deadlines, projects/people focus) derived from journal text, not just embeddings and summaries. citeturn3view0turn3view1turn3view4  
- **A quality pipeline discipline** (unit-like tests for LLM extractors; expanded test families; RAG evaluation runs), which can translate into better user trust (“this doesn’t miss my commitments” / “this doesn’t create junk nodes”). citeturn3view3turn8view0  
- **Latency + cost optimisation**: the Flash-Lite switch with measured latency/cost impact indicates you are taking unit economics seriously early, which is strategically correct for consumer-ish products. citeturn3view1turn13view0  

Even if LLM capabilities commoditise, a compounding moat can emerge from: (a) personalised entity resolution over time, (b) user-specific ontologies (“my projects”), (c) product loops (“forgotten projects” actually causes re-engagement), and (d) trust and privacy posture. citeturn3view3turn24view0turn26view1

### Engineering risks that can derail retention (and what the repo suggests)

1. **RAG quality plateau**: your final reported retrieval F1 around ~0.50 suggests Q&A usefulness may be “hit or miss” unless you improve retrieval and/or answer synthesis (and your earlier attempt to add query rewriting massively increased latency and was reverted). citeturn3view3turn3view1  
2. **Background processing limits**: FastAPI BackgroundTasks are workable at small scale, but for 10k MAU with bursts you will likely need a durable queue (retries, idempotency, dead letters, rate-limit smoothing). Your repo already signals this concern via the pipeline-stage persistence pattern. citeturn3view1turn3view4  
3. **Entity graph drift and merge errors**: you have implemented multi-stage matching and embedding similarity gating, which is the right direction, but as user history grows, false merges or over-splitting will directly harm trust (“my graph is wrong”). citeturn3view1turn8view0  
4. **Multi-tenant security**: journaling content is sensitive. Supabase can be secure, but the security model heavily depends on correct row-level security policies and key handling; a single misconfiguration becomes a reputationally fatal incident in this category. citeturn17search32turn23search5turn23search15  
5. **Observability cost creep**: Langfuse is highly useful, but it is a metered service based on ingested units; if you log every node for every entry at scale, observability becomes a non-trivial budget line. citeturn22view0turn22view1  

### Scaling challenges to anticipate

- **Model rate limits and compliance-by-region**: Gemini terms state you may use only paid services when making API clients available in the UK/EEA/Switzerland, which pushes you toward billing-enabled usage even in early growth if you serve those markets. citeturn24view0  
- **Data volume**: storing full text + embeddings + relation edges grows linearly with entries; long-term retention (multi-year journaling) pushes you into DB/storage and backup considerations earlier than typical SaaS logs. citeturn3view1turn20search0  

## Legal, privacy, and regulatory risks

### Privacy expectations in journaling are unusually high

Competitors frame journaling as “private, secure, end-to-end encrypted,” and users are increasingly trained to expect this. Day One’s App Store copy positions the product as “trusted” and explicitly mentions end-to-end encryption; Obsidian markets local-first storage and E2EE sync; Apple provides granular Journal privacy controls and states E2EE conditions for Journal entries in iCloud in its privacy materials. citeturn25view1turn26view1turn16search8turn16search0

MindGraph currently processes entries through Google Gemini API calls (Flash-Lite/Pro) and stores data in Supabase; that can be entirely acceptable in a “work journal / productivity” market, but you must clearly communicate and minimise what is sent, stored, logged, and retained. citeturn3view1turn24view0turn24view2

### Gemini API terms and data-use constraints are material

Google’s Gemini API Additional Terms (effective March 23, 2026) include constraints that are directly relevant:

- Paid services: Google states it does **not** use your prompts/responses to improve products and processes them under a data processing addendum. citeturn24view0  
- Unpaid services: Google may use submitted content to improve products and may involve human review, with advice not to submit sensitive/personal information. citeturn24view0  
- Region restriction: for EEA/UK/Switzerland, the terms state you may use only paid services when making API clients available. citeturn24view0  
- Medical/clinical restriction: you may not use the services in clinical practice or to provide medical advice. This constrains “mental health coach” positioning. citeturn24view0  
- Logging/retention: Google documents how “logs” exist for billing-enabled projects and how dataset sharing can opt-in logs for training; logs have default expiration (55 days) unless retained in datasets. citeturn24view2  
- Zero Data Retention: Google documents ZDR mechanics, including default abuse monitoring logs and 30-day storage for certain grounding features, and notes that ZDR requires specific actions/approvals and avoiding features like grounding. citeturn24view1  

For MindGraph, the practical implication is: **operate billing-enabled from day one**, disable/avoid any optional data-sharing/log dataset contribution, avoid grounding features if you want lower retention disclosures, and ensure your privacy policy matches Google’s actual retained artefacts. citeturn24view0turn24view1turn24view2

### Data protection regimes (UK, EU, India) are relevant

If MindGraph users include UK/EU residents, journaling content can easily include “data concerning health” (including mental health), which regulators treat as sensitive/special category data requiring additional conditions and safeguards. citeturn17search4turn17search0 The UK ICO explicitly describes special category data requirements (Article 6 lawful basis + Article 9 condition; likely DPIA if high risk). citeturn17search0

For the EU, the official EU timeline states the AI Act entered into force on August 1, 2024, with staggered applicability (full applicability for many obligations by August 2, 2026; GPAI model obligations applicable earlier). citeturn17search10 Even if MindGraph is not “high-risk AI” in the AI Act sense, your use of a general-purpose LLM provider and your handling of sensitive personal data can trigger enhanced compliance work in the EU market. citeturn17search10turn24view0

For India, the Digital Personal Data Protection Act, 2023 is an enacted framework for processing digital personal data, and the Ministry has published related materials/rules (as per the government press note and the act text sources). citeturn17search1turn17search13 If you serve Indian users (likely given your founder context), the DPDP compliance surface is non-trivial: consent, purpose limitation, data security safeguards, and user rights handling. citeturn17search1turn17search5

### Bottom line for risk posture

MindGraph can be run compliantly, but you must treat privacy and terms compliance as **core product features**, not later paperwork—particularly because journaling is a “trust-first” category and because your differentiator (deep personal context) amplifies harm if mishandled. citeturn26view1turn16search8turn17search0turn24view0

## Roadmap, milestones, risks, and next steps

### A 6–12 month roadmap that targets viability (not just completeness)

The roadmap below assumes the pivot is toward **work journaling / personal CRM / founder operating system**, not general mood journaling, and that “Pro insights” are monetised rather than free. It also assumes you keep the current core stack (React/FastAPI/Supabase/Gemini) but harden the architecture for scale. citeturn3view0turn3view4turn13view0turn15view4

```mermaid
timeline
  title MindGraph 6–12 month viability roadmap (Apr 2026 → Mar 2027)
  Apr–May 2026 : Positioning pivot + onboarding that proves value in 1 session
              : Instrumentation: activation, D7/D30 retention, cost per retained user
              : Privacy & terms hardening (billing-only, no dataset sharing, clear disclosures)
  Jun–Jul 2026 : “Work memory” killer flows (commitments/deadlines, people/stakeholder memory)
              : Reliability: job queue + retries + idempotency; alerting on pipeline failures
              : Export + data portability (leave no lock-in fear)
  Aug–Sep 2026 : Monetisation: tiered plans; Pro-insights as paid feature
              : Acquisition loop: founder/PM communities + content + lightweight referrals
              : Quality: improve RAG usefulness (targeted evals tied to user questions)
  Oct–Dec 2026 : Team / shared workspace experiments (optional): “project memory” for small teams
              : Security/compliance: DPIA templates, region controls, data retention controls
              : Scale test: 10k MAU load model + cost controls
  Jan–Mar 2027 : Decide: double-down (if retention + revenue hit thresholds) or stop
              : If double-down: expand integrations (calendar/email/Slack) cautiously
```

### Viability milestones and measurable success metrics

Because PMF is habit-driven, the milestones should be retention-led rather than feature-led:

- **Activation** (within 1 week of signup):  
  - ≥60% of signups create ≥3 entries and view at least one “useful artefact” (graph edge, extracted deadline, or “forgotten project”) within the first week. (Unspecified today.)  
- **Retention**:  
  - D7 retention ≥25% and D30 retention ≥10% for the target persona, as a first-pass threshold; journaling products often fail here due to low habit formation. (These thresholds are strategic targets, not sourced claims.)  
- **Value proof** (qualitative + quantitative):  
  - Users report that MindGraph answers specific recall questions (“When did I decide X?”, “Which project is stalled?”, “Who did I promise what to?”) better than their existing note/journal method; instrument “successful answer” feedback on /ask. citeturn3view3turn24view2  
- **Unit economics**:  
  - Keep “Lite pipeline” cost near the reported $0.0003/entry and ensure Pro-insight spend is covered by paid ARPU; this aligns with the Flash-Lite optimisation described in the README and with Gemini pricing differentials. citeturn3view1turn13view0turn15view4  
- **Monetisation**:  
  - ≥3–5% free→paid conversion for a self-serve product, or ≥$1k MRR from <250 paying users depending on price point. (Targets; unspecified today.)

### Risks and mitigations

| Risk | Why it matters | Mitigation strategy (practical) |
|---|---|---|
| Privacy trust gap kills adoption | Journaling is sensitive; incumbents emphasise E2EE/local-first. citeturn16search8turn26view1turn25view1 | Publish a clear data-flow diagram; minimise stored raw text; offer strong export; consider optional self-host; avoid “mental health” claims; add “work journal” framing. citeturn24view0turn24view1 |
| Gemini API terms mismatch | Terms restrict clinical use and impose region/paid-service constraints. citeturn24view0 | Run billing-enabled only; add age gating (18+); avoid clinical language; document retention/logging; implement ZDR best practices; avoid grounding features. citeturn24view0turn24view1turn24view2 |
| RAG feels unreliable | Retrieval F1 ~0.50 suggests “ask” may disappoint. citeturn3view3 | Reframe /ask as “search + citations”; add UI that shows source snippets; improve chunking; expand evaluation set based on real user questions; keep latency budgets. citeturn3view3turn3view1 |
| Pipeline failures at scale | BackgroundTasks can drop work; concurrency and retries are limited. citeturn3view1 | Introduce a queue (Redis + worker or managed); idempotent storage; per-stage timeouts; retry policy; backpressure and rate limiting; runbooks. |
| Data breach / RLS misconfig | A single incident can be fatal in journaling. citeturn17search32turn17search0turn23search15 | Security review of RLS; least-privilege keys; separate service role usage; periodic access tests; secrets scanning; add audit logs for data access; consider encryption-at-rest and per-user keying. citeturn23search5turn23search15 |
| Over-investing before validation | Feature creep without retention proof wastes founder time. citeturn7view0 | Timebox experiments; define 2–3 core loops; kill non-retention features; ship instrumentation first; publish weekly retention dashboard. |

### Suggested next steps (ordered for impact)

**Product strategy (next 2–4 weeks):**

1. Lock the positioning to one persona: “work journal that builds a personal CRM + project memory graph” (or equivalent) and remove/soften “mental health” framing to avoid compliance and terms problems. citeturn3view0turn24view0  
2. Redesign onboarding to force a “wow moment” in one session: after the first 2–3 entries, show (a) extracted commitments/deadlines, (b) “people I’m collaborating with”, (c) “forgotten project” signal, and (d) one citation-backed Q&A answer. citeturn3view0turn3view3  

**Technical (next 4–8 weeks):**

1. Replace BackgroundTasks with a real job system (even a simple queue) to make processing durable and scalable; keep the stage-tracking column approach. citeturn3view1turn3view4  
2. Harden privacy defaults: ensure you are operating as “Paid Services” for Gemini; disable any log/dataset sharing; publish retention disclosures aligned with Gemini’s logs/ZDR documentation. citeturn24view0turn24view1turn24view2  
3. Implement export early (JSON + markdown + attachments) to neutralise lock-in fear, especially versus local-first tools. citeturn26view1turn25view1  

**Go-to-market (next 8–12 weeks):**

1. Choose 2 channels where your target persona already congregates (founder communities, indie hacker circles, PM communities) and ship weekly “build-in-public” artefacts that demonstrate *specific outcomes* (e.g., “never forget a commitment you wrote down”). The repo currently shows minimal public traction signals, so you likely need deliberate distribution. citeturn2view0  
2. Price-test early with a simple tiering: free = Flash-Lite pipeline + graph; paid = Pro insights + weekly digest + advanced /ask limits. This aligns cost drivers (Pro) with revenue. citeturn15view4turn3view3turn16search3turn0search20  

**Decision gate (end of 3 months):**  
If you cannot achieve meaningful D30 retention for the chosen persona and at least a small set of paying users, the rational move is to **pause or stop** rather than continue feature expansion—because the engineering base is already “good enough” to test the market; what’s missing is behavioural pull. citeturn3view0turn7view0