# MindGraph: Deep Strategic and Technical Research Report
Prepared for Karthik, April 2026

This is a long, blunt, no-hype briefing. The headline up front: the AI journaling consumer space is crowded and increasingly capital-intensive, but it is not closed — there is still a wedge for a graph-native, "patterns of self" product if you ship fast and pick a sharp niche. The bigger asymmetric opportunity for someone with your exact stack is a B2B knowledge-graph product in a regulated or high-cost-of-error vertical, where Glean is too horizontal and Hebbia is too document-centric. The most rational plan is to do BOTH, but stage them: ship MindGraph as a paid SaaS to one tight niche over 90 days, treat it simultaneously as the public proof artifact, and use that traction (or its absence) to decide whether month four is full-time on B2B or back into a high-paying role. Detail follows.

---

## 1. The real problem MindGraph solves

The clinical and academic literature is unambiguous that structured reflective writing produces measurable mental-health outcomes. James Pennebaker's expressive-writing paradigm has been replicated for nearly four decades; the Baikie & Wilhelm review (cited in VA Whole Health Library materials) found that 3–5 sessions of 15–20 minutes produced measurable improvements, with average effect sizes around d = 0.16 across more than 200 studies. A 2012 meta-analysis (Emmerik, Reijntjes, Kamphuis) found significant short-term reductions in PTSD and depressive symptoms. The Burton & King (2004) study reported roughly a 30 percent reduction in depression scores over eight weeks of expressive writing. Importantly, Ullrich and Lutgendorf (2002) showed that the "cognitive processing" component of writing — turning experience into a coherent narrative — predicted outcomes far more than emotional venting. That is the exact thing a graph-with-typed-relations, like MindGraph's V1 7-type taxonomy, mechanically supports: it is structured cognitive processing, not catharsis.

So the "people don't see their own patterns" claim is real and has both clinical and behavioral-economic backing. People keep journals; they do not re-read them. They notice acute emotion; they do not notice second-order recurring entities (the same boss, the same intrusive thought, the same time-of-day low). That gap — between writing and re-experiencing your own corpus — is the actual job MindGraph does. The visualization piece is not decoration; it is the only widely usable interface for surfacing entity-level patterns in longitudinal text.

The market size numbers vary wildly because analysts are measuring different things, and you should mistrust any single figure. The narrowly defined "journal app" market is reported around USD 3.2B (2024) growing at ~12 percent CAGR (DataHorizon Research), USD 5.1B (Straits Research) growing 11.5 percent, and as low as USD 0.11B (Business Research Insights). The wider "wellness and mental health apps" category is reported at USD 4.97B in 2025 with a 16 percent CAGR through 2035. The honest read: this is a real but mid-sized consumer category, dominated in revenue terms by a handful of apps with most of the rest being long-tail. It is not the next Notion. It is plausibly a 5,000-paying-user, $300K–$1M ARR business for a sharp solo founder, with Rosebud at the upper bound of what a venture-funded competitor has built.

Competitor pricing is converging on $5–$13/month with $40–$70/year:

- Rosebud: free tier; $12.99/month premium (TechCrunch confirmed). Earlier tiers were $4.99 and a Bloom plan. Raised $6M seed from Bessemer in June 2025; reports 7,500+ paying customers as of that announcement, 500M words journaled cumulatively.
- Reflection.app: free tier; $8/month or $69/year.
- Stoic: free tier; $6.99/month or $49.99/year.
- Day One: roughly $35/year premium; introduced an AI assistant in January 2025.
- Mindsera: subscription, mid-tier pricing, mental-models framing.
- Life Note: similar structure, positioning around historical wisdom.
- Mem.ai: pivoted toward an enterprise/work positioning.
- Reflect: $10/month; positions as a Roam/Notion-AI hybrid.

Unmet needs that current tools genuinely do not solve well, and which a graph-native product can:

- Re-readability. None of Rosebud, Reflect, Day One, or Stoic give you a navigable map of your own life. They give summaries and prompts. A graph is the only structure that lets a user click "my mother" and see every entity, theme, and emotional context connected to her over two years.
- Cross-entity reasoning ("which projects am I always anxious before — what do they share?"). LLM chat over journal entries hallucinates this. Typed relations + retrieval over the graph do not.
- Data portability. Most apps lock data in proprietary stores. Day One and Reflection offer export, but few ship a true "your data is yours, in JSON-LD or markdown, anytime, signed" experience. This is a wedge for a developer-credibility brand.
- Long-horizon memory. Rosebud's premium feature is "long-term memory" precisely because most apps do not do it. The graph + pgvector hybrid is exactly the right primitive for it.

The willingness-to-pay question: Rosebud charging $12.99/month with thousands of subs is the proof. People with mental-health-adjacent needs pay; the $4.99 tier exists for a reason — it converts. The harder question is retention, not initial conversion.

---

## 2. Architecture improvements needed immediately

You already have the right spine: 7-node LangGraph + Gemini + Langfuse + FastAPI + pgvector + Supabase Auth + Railway. The gaps that show up the moment you have 50 paying users on it:

Multi-tenant isolation. Supabase RLS is fine for the API layer, but checkpointed LangGraph state lives in your own tables. Make every checkpoint thread_id and store namespace tenant-prefixed (e.g. `tenant-{user_id}:session-{session_id}`), and add a hard constraint on every entity, embedding, and edge table that includes user_id, with a CHECK or RLS policy preventing cross-user reads. Add a nightly job that samples 1 percent of queries and asserts no cross-tenant leakage. This is the single biggest disaster waiting to happen and the thing that will end any B2B sale.

Background job queue. A 7-node fan-out pipeline run synchronously inside an HTTP request is a footgun. Move entity extraction, relation extraction, embedding generation, and graph rebuilds to a background worker. The cheapest production-grade option is `arq` (Redis-based, async-native, fits FastAPI) or `Celery` if you want a richer ecosystem. Railway can run worker services. Make every entry creation return immediately, with a "processing" state surfaced in the UI; finalize via WebSocket or polling.

Rate limiting per user. Use SlowAPI or fastapi-limiter (Redis backend). Three buckets: per-IP (anti-abuse), per-user (fair use), per-LLM-call (cost cap). Hard daily token budget per free user, soft monthly budget per paid user — surface the remaining quota in the UI.

Cost controls on Gemini. You should not be calling Gemini 2.5 Pro from anywhere except deeply reasoned graph synthesis. Default everything else to Gemini 2.5 Flash ($0.30/$2.50 per million in/out tokens) or Flash-Lite ($0.10/$0.40). Enable context caching for any prompt longer than ~500 tokens that repeats across calls (your system prompt for relation extraction is the obvious candidate); cache hit rates of 60–90 percent reduce effective input cost by an order of magnitude. Set a thinkingBudget of 0 on Flash unless you specifically want reasoning, otherwise output costs balloon. Tag every Langfuse trace with a `cost_center` (extraction / relation / synthesis / chat) so you can see where money goes per user per day.

Observability beyond Langfuse. Langfuse covers LLM traces. You also need: Sentry for application errors; PostHog or a self-hosted Plausible for product analytics (DAU, streak length, retention cohorts — these are the metrics that actually predict revenue); Prometheus + Grafana or Better Stack for infra; structured logs with request_id, user_id, session_id on every line. Add a dedicated /healthz endpoint that checks Postgres, Redis, and Gemini reachability; Railway's healthchecks will use it for safe restarts.

Embedding refresh. pgvector indexes degrade as your taxonomy evolves. Two principles. First, store the model name and version on every embedding row so you can do partial migrations. Second, build a backfill job that re-embeds in batches when you change embedding model — never an in-place mutation. You will change models within 12 months; design for it now.

RAG reliability. Plain cosine over pgvector is brittle. Add at minimum: hybrid retrieval (BM25 via `tsvector` + vector, with reciprocal rank fusion), a small cross-encoder reranker (bge-reranker-base is fast on CPU), and MMR diversity to avoid retrieving 10 chunks from one entry. Add knowledge-graph-aware retrieval: when a user asks a question, expand the query to include entities from a 1-hop neighborhood and retrieve over the union.

Backups and DR. Supabase has automated backups but only restores at the project level; that is not a recovery plan. Add a nightly pg_dump to S3 or B2, encrypted with age or sops. Test restore quarterly. Add a Railway → off-platform DB replica (Neon, Render, or Crunchy) so the bus-factor on Railway is not 1.

Data export and portability. This is non-negotiable for a journaling product. Ship JSON-LD export of the full graph (entries, entities, relations, mood, timestamps) and Markdown export of entries. Make it a clear UI affordance, not an email request flow. This single feature buys disproportionate trust.

Privacy and encryption at rest. Supabase encrypts at rest by default at the disk layer; that is not enough for journaling. Implement application-level encryption for entry body text using a per-user data-encryption key wrapped by a tenant-master key (envelope encryption pattern, AES-GCM). Use libsodium or `cryptography` for Python. Document this clearly in your privacy page; it is a brand asset.

GDPR specifics for a wellness journaling app:

- Lawful basis: consent (Art. 6) plus, because mental-health data is "special category" under Art. 9, you need explicit consent and a clear "we are not a medical device" disclaimer.
- Right to erasure: a one-click delete that nukes Postgres rows, vector embeddings, Langfuse traces (Langfuse has API endpoints for this), and any LLM provider logs. Critically, Gemini retains data unless you use a paid Vertex AI configuration with logging disabled — verify your current Gemini API tier; the free tier trains on your data.
- DPA: you need a Data Processing Addendum from Google (Vertex AI provides one), Supabase (provides one), Railway (provides one), Langfuse (provides one). Collect and store these.
- Records of Processing Activities (RoPA) — a one-page document. Templated, do once, ship.
- For UK/EU residents: a clear "report a concern" route. Add a Privacy@ inbox.

Mental health disclaimers. Big bold copy on first run and on every "insight" surface: "MindGraph is a self-reflection tool, not a medical device, not therapy, not a substitute for professional mental-health care. If you are in crisis, please contact ..." with region-specific hotlines. This is both ethical and legally protective.

---

## 3. One-week ship plan with Claude Code

Assume 7 days, 12 hours/day, Claude Code as implementer with you architecting. Skip everything that is not on the conversion or retention path.

Day 1 — payments, plans, paywall. Stripe + Stripe Tax (or Paddle if you go MoR — see section 4). Two plans only: Free (5 entries/week, basic graph, no long-term memory) and Pro at $9/month or $79/year (unlimited entries, long-term memory, weekly insights, full graph, exports). Annual plan must be there day one — it changes LTV economics dramatically.

Day 2 — streaks, reminders, daily prompt. Streaks are the single most retention-correlated feature in journaling apps; Rosebud, Stoic, and Day One all over-invest in them for a reason. Ship a streak counter, a "freeze" mechanic (1 free skip per week), a configurable daily reminder via email (Resend or Postmark), and a daily prompt that pulls from the user's graph ("You mentioned X three weeks ago — has anything changed?"). The personalized prompt is a wedge versus generic-prompt apps.

Day 3 — weekly insight email. A scheduled job that runs every Sunday morning and sends each user a digest: top 3 entities you wrote about, mood trend chart, one surfaced pattern ("anxiety entries cluster on Sundays"), one suggested reflection. This is the single feature that makes journaling apps "sticky" because it pulls users back even when they have lapsed. Use Gemini 2.5 Flash for synthesis, pre-render the email as HTML, send via Resend.

Day 4 — search and timeline. A unified search box that queries entries by full text, entity, date range, and mood. A timeline view that scrolls all entries with entity chips. This is table-stakes; without it the product feels incomplete.

Day 5 — exports and audit log. JSON-LD export, Markdown export, "download my data" page. Add a simple audit log of what the AI inferred and when, with a "this is wrong" feedback button on each relation. The feedback button doubles as your data quality signal for entity dedup.

Day 6 — onboarding and first-entry magic. A 90-second onboarding: name, one goal, one prompt to write. After the first entry, animate the graph being built in real time — this is your "wow" moment. Add three sample prompts ("a hard conversation this week", "something you've been avoiding", "what made you laugh"). First-entry-to-second-entry retention is the funnel you must instrument and obsess over.

Day 7 — polish, instrument, ship. PostHog events on every meaningful action. Sentry on. Privacy policy, ToS, mental-health disclaimer drafted (use Termly, Iubenda, or a $300 lawyer review on Fiverr/PeoplePerHour — do not write these yourself). Set up status page. Soft-launch to 50 hand-picked beta users on Twitter, your own network, and a single relevant subreddit.

Things to consciously not ship in week 1, despite the temptation: voice journaling, mobile native app, a community feature, AI "coaching" chat, integrations. Each is a 2-week project on its own and none will move week-1 conversion.

Table-stakes for a paid AI journaling product in 2026, validated against Rosebud / Reflection / Day One / Stoic: streaks, reminders, voice input (you can defer this to month 2 with browser MediaRecorder + Whisper API for cheap), weekly insights, full search, exports, encryption messaging, one-click cancel.

---

## 4. Payments and monetization

You are a Bangalore-based founder selling globally. The arithmetic genuinely changes the answer.

Stripe (with Stripe Tax at 0.5% per transaction): cheaper headline rate (~2.9% + $0.30) but you remain Merchant of Record. Selling into the EU triggers VAT obligations from euro one; UK VAT, Australian GST, Canadian GST/HST, and US state sales tax all stack as you grow. As a foreign (non-EU) seller of digital services to EU consumers, you must register for VAT-MOSS (or use the EU OSS scheme via a representative). The CA in Bangalore who can do this competently will charge ₹40–80K/year minimum. Stripe also requires a US/EU/UK/SG entity for many features; Stripe India for an Indian entity routes through Razorpay-like rails and is awkward for B2C SaaS to a global audience.

Paddle / Lemon Squeezy (Merchant of Record): 5% + $0.50. Paddle and Lemon Squeezy take legal seller status, handle all global tax. Lemon Squeezy was acquired by Stripe in 2023; as of early 2026 Stripe has launched "Stripe Managed Payments" (5% + $0.50) which is essentially MoR-as-a-service inside Stripe. Lemon Squeezy continues to operate; Paddle remains the most mature option with B2B invoicing and SEPA/iDEAL.

Razorpay: domestic India only for serious volume; do not use it for global B2C.

Recommendation: Paddle or Stripe Managed Payments for global. The 2 percent fee differential vanishes once you account for one CA-hour per month of GST/VAT compliance. As an Indian founder, this also lets you receive a single consolidated payout into a domestic account without multiple foreign tax registrations.

GST / Indian tax reality. As a Bangalore-based proprietorship or LLP exporting digital services, you can claim "export of services" treatment with zero-rated GST under the LUT (Letter of Undertaking) route — file an LUT each fiscal year so you do not have to charge IGST. You will still need GST registration (turnover threshold considerations notwithstanding, registration is recommended for OIDAR/digital export evidence). FEMA compliance: payments must come through banking channels with proper FIRC/eBRC documentation; Paddle/Stripe both produce export-compliant remittance trails. Income tax: this is business income, not capital gains — set aside ~30 percent for tax. Consider whether to incorporate as a private limited company once revenue clears ~$2K MRR; it cleans up future fundraising and limits liability.

Pricing tiers — concrete recommendation for MindGraph:

- Free: 5 entries/week, basic graph (entities only, no advanced relations), 30-day history view, no long-term memory.
- Pro $9/month or $79/year ($6.58/month equivalent — keeping it just under the $9.99 psychological barrier and below Rosebud's $12.99): unlimited entries, full typed-relation graph, long-term memory, weekly insights, voice journaling (when shipped), exports.
- (Later) Founder/Lifetime $199 one-time during a launch promo: classic indie-hacker tactic; converts price-sensitive early adopters into evangelists, generates upfront cash.

Free tier strategy. Be more generous than Rosebud on entries per week (5 is enough for the value loop to fire) but ruthlessly gate the long-term memory and the full graph. The graph is your differentiator; users who feel its absence in free convert. Do not gate exports — that is a trust signal.

Annual vs monthly. Annual conversion among users who try monthly is typically 20–30 percent in this category, and annual subs reduce churn-driven CAC pressure dramatically. Default the pricing page to annual (this single change typically lifts ARPU by 30–50 percent in indie SaaS).

MRR benchmarks for solo-founder AI wellness/journaling. Public numbers are scarce because most solo founders in this category do not disclose. Reasonable bands from observed indie hackers and from Rosebud's trajectory: $0–$1K MRR is the first three months for nearly everyone; $1–$5K MRR by month 6 is a good outcome and signals product-market-fit potential; $5–$15K MRR by month 12 is realistic for a sharp niche; the long tail of solo journaling apps clusters around $2–$10K MRR. Anything beyond $20K MRR for a solo founder in this category typically requires a TikTok/Instagram organic break or a venture-style growth investment, neither of which is on the cards on day one.

---

## 5. Go-to-market strategy

The honest read for a solo Indian founder selling global B2C in a saturated category: you are not winning on Product Hunt and you are not winning on paid ads. You win on (a) niche targeting, (b) build-in-public on X/LinkedIn, (c) one earned-media moment, (d) SEO compounding from month 3 onward.

Niche first, broad later. The four candidate niches with high willingness-to-pay and low marketing cost:

- ADHD users. Highest engagement with self-tracking, very active subreddit (r/ADHD, ~2M members), strong word-of-mouth, narrative around "I can never see my own patterns" maps perfectly to your graph thesis. Best fit for MindGraph's actual capability.
- Founders / solo operators. They will pay $9/month without thinking; the "patterns in my own decisions" framing resonates; you have credibility and a network here. Smaller TAM but easier conversion.
- Therapy clients (between sessions). Position as "the journal your therapist asked you to keep, that actually shows you patterns to bring to your next session". Risky on liability messaging but high LTV.
- Students preparing for high-stakes exams (IIT, GRE, USMLE). Smaller relevance to graph thesis, more obvious for a habit/streak product. Skip.

Pick one, probably ADHD. Brand the landing page accordingly. You can always broaden.

Channels that actually work for indie B2C launch in 2026:

- Build-in-public on X. Daily 1-tweet update; weekly screenshot of the graph improving; share the cost numbers, the architecture, the failures. This compounds slowly but is your most durable owned channel. Expect 0 → 500 followers in 90 days if consistent.
- Reddit. r/ADHD, r/Journaling, r/selfimprovement, r/getdisciplined. Don't drop links cold. Comment helpfully for 2 weeks first, then post a thoughtful "I built this for myself, here's what I learned about my own patterns" — show before tell. Single Reddit post done well = 200–1,000 sign-ups.
- Hacker News Show HN. One shot. Post on a Tuesday or Wednesday morning Pacific. Lead with the architecture (LangGraph + knowledge graph + d3-force) — HN respects technical depth in journaling more than therapeutic claims.
- Product Hunt. Submit, but expect modest. PH is a sub-1,000-signup launch in this category in 2026 unless you've cultivated hunters. Worth doing for the "PH-launched" badge and the SEO backlink.
- SEO. Pick 5 long-tail keywords like "journal app for adhd patterns", "knowledge graph journaling", "alternative to rosebud". Write one 1500-word post per week on each. Compounds at month 3+.
- Threads / LinkedIn. Underused for this audience. LinkedIn is unusually effective for the "founder/operator" niche.

Things that won't work and you should skip: paid ads (CAC will exceed LTV; $9/month with 6-month average retention is $54 LTV — paid ads in wellness are $30–$80 CPI minimum, you lose money), influencer outreach without budget, TikTok unless you personally enjoy making short video.

Rosebud's trajectory is instructive but not replicable as a solo founder. Chrys Bader brought a Y Combinator network and the Secret co-founder credential; their initial traction came from Tim Ferriss's network and a Bessemer-led seed, not from cold launch. You are not them. Plan for the slower, niche-first path.

---

## 6. Portfolio vs product question — honest assessment

Honest answer: ship as paid SaaS, but plan for both outcomes. The portfolio value of MindGraph is highest if it has paying users and revenue, even small revenue. "I built and run a paid AI SaaS, currently at $X MRR, here is the architecture" is a much stronger hiring signal than "I built an AI journaling app and it's live". Hiring managers see portfolio projects every day; they see operating products with revenue rarely. The paid-SaaS framing also improves freelance pricing by 2–3x on contract day rates.

Pivot signals — set these in advance and commit. After 90 days of full-time effort:

- If MRR < $500 and weekly signups < 30, pivot. Either to a different niche, to the B2B opportunity, or to a hybrid mode (part-time on MindGraph, accept a freelance/full-time role). Do not "give it another month".
- If MRR is $500–$2K, continue but cap full-time effort at another 60 days. The product is showing signs but not enough to justify burn. Take a part-time freelance gig in parallel.
- If MRR ≥ $2K and growing 15 percent month-over-month, this is your business — keep going.
- If MRR ≥ $5K, hire one part-time contractor, double down on retention metrics.

Concrete examples of AI engineers who used flagship side-projects to land roles. The pattern that consistently works in 2024–2026: build something with non-trivial production architecture (LangGraph + observability + multi-tenant qualifies), open-source the architecture (not the data), write 3–5 blog posts walking through technical decisions, link them prominently from GitHub. The flagship-project-as-resume signal is most powerful for senior IC and Staff-level AI engineering roles ($200K–$400K equivalent globally; $40–80 LPA in India for top AI roles), and it consistently doubles freelance day rates from $300 to $600+ for AI engineers with depth.

You can do both portfolio and product without compromise if you discipline what counts as "for the product" and what counts as "for the portfolio". Public architecture writeups, the GitHub repo, a clean README, the Notion status hub: portfolio value is high and product cost is low. Don't open-source things that would let a competitor clone you (your prompts, your taxonomy, your eval set).

---

## 7. B2B enterprise opportunity (the most important section)

This is where the asymmetric upside is for someone with your exact stack. Glean is at $200M ARR and a $7.2B valuation; Hebbia is well-funded but document-centric; Mem.ai is in flux. The market for "structured AI over unstructured org content" is growing 50–100 percent year-over-year in dollar terms. The genuine gap that MindGraph's tech maps to is not enterprise search — Glean owns that — but **typed-relation knowledge graphs over user-generated text in vertical-specific contexts**.

Vertical-by-vertical assessment, ranked by fit to your stack and skills:

a) Therapist tools — clinical notes pattern recognition. Crowded but not closed. Mentalyc claims 30,000+ therapists; Upheal, Blueprint, Supanote, AutoNotes, TheraPro all compete on note generation. None of them does longitudinal pattern recognition across a therapist's entire client caseload as a primary feature. The gap: a therapist treating 25 clients over 18 months has no tool that surfaces "your Monday-evening clients consistently regress in week 4" or "this client's themes cluster around career identity, not relationships as you've been treating". Pricing in this space: $69–$89/month per therapist (Upheal $1/session, Mentalyc $39–79/month, Blueprint $0.99/session). HIPAA is non-negotiable, requires a BAA (Business Associate Agreement) with every sub-processor including Gemini (Vertex AI offers HIPAA BAA; Gemini Developer API generally does not). 12-month timeline to compliance and first paying customer; high LTV ($1000+/year/therapist) and good organic growth via therapist communities (r/therapists, Psychotherapy Networker). Best fit for your tech, but heavy compliance lift.

b) Customer success — pattern recognition over support tickets and customer interactions. Tools like Decagon, Cresta, Intercom Fin own the "AI agent that responds" layer. The gap: pattern detection across support tickets at the account level — "these 14 tickets across these 6 customers all share an underlying entity (your billing system change)". Gainsight and ChurnZero do account health, but not entity-graph-style. Pricing: $200–$500/seat/month for the analyst tier. Sales cycle: 3–6 months mid-market, 9–18 months enterprise. Sweet fit for your tech, especially the typed relations.

c) Sales intelligence — patterns across sales calls and CRM notes. Gong and Chorus dominate call recording; Clari owns forecasting. The gap: cross-call entity graphs that identify "champions who reference your CTO are 3x more likely to close" or "objections that recur in deals where the buyer mentioned competitor X". Pricing: $1,200–$2,400/seat/year. Crowded; harder to enter as a solo founder without sales-tech credibility.

d) Knowledge management for consulting / law / research firms. Glean's home turf at the horizontal layer. The gap is verticalized: a 50-person law firm doesn't want Glean's $50K/year contract complexity; they want a turnkey "graph of every matter, every party, every precedent we've ever touched" priced at $50–$150/lawyer/month. Specifically: small-mid law firms (5–50 attorneys), consulting boutiques (10–100 consultants), and academic research labs. Phyvant and a few others have noticed this gap; it is not yet won. The "Glean is too horizontal, Hebbia is too document-centric" wedge is real here.

e) HR / employee feedback analysis. Pattern recognition over engagement-survey responses, Slack sentiment, and 1-on-1 notes. CultureAmp and Lattice cover surveys; nobody does great longitudinal entity graphs over open-text responses (which is where the actual signal is). Higher liability than therapist tools because it touches employment law. Skip unless you partner with an HR-tech founder.

f) Compliance / audit pattern detection. High-stakes, long sales cycle, requires SOC 2 + sometimes ISO 27001. Skip for now.

The single best B2B opportunity for your exact stack and skills: **a verticalized knowledge-graph product for either (a) therapy practices or (b) small-to-mid law firms**. Rationale:

- Both have unstructured longitudinal text as the core asset.
- Both have high willingness-to-pay per seat.
- Both are too small/too vertical for Glean to bother with.
- Both reward the typed-relation graph approach because the relations matter (precedent → matter, client → theme → intervention).
- Both have strong organic communities you can sell into.
- Therapy is a closer fit if you want emotional resonance with the work (continuity from MindGraph); law is a closer fit if you want larger contract values and faster B2B sales cycles.

Tooling differentiation that matters in B2B:

- Auditable provenance on every inferred relation (the Glean Protect angle).
- Per-tenant encryption and clean data residency stories.
- Explicit "we do not train on your data" contractual language.
- Permission-aware retrieval — relations from documents the user cannot see should not surface.
- Self-serve onboarding with sample data — closing the demo→trial gap.

---

## 8. Things you may be missing

LLM cost projections at scale. Back-of-envelope at 1,000 paying users on Pro, average 5 entries/week, average 300 tokens per entry, 7 nodes touching that entry, average 1.5x prompt overhead per node:
- Input tokens per entry processed: 300 * 7 * 1.5 = ~3,150 tokens.
- Output tokens per entry: ~1,000 across nodes.
- Per entry on Gemini 2.5 Flash: 3,150 * $0.30/M + 1,000 * $2.50/M ≈ $0.0034.
- Plus weekly insight generation per user: ~5,000 in / 1,500 out ≈ $0.0053.
- Plus on-demand chat: budget $0.02/user/week.
- Per active user per month: ~$0.20 in LLM costs.
- 1,000 paid users: ~$200/month in LLM. Embeddings on-prem with sentence-transformers, $0. Postgres at Supabase Pro tier ~$25. Railway ~$50. Total infra ~$300–$500/month against ~$8,000–$9,000 MRR. Healthy gross margin (~94 percent) — but only if you cap free-tier abuse aggressively. One bad actor on a 7-node fan-out can cost more than 100 paying users contribute. Hard rate limits day one.

Legal foundations you should not skip:

- Terms of Service: include arbitration clause, limitation of liability cap (the price paid in last 12 months), no-medical-device disclaimer.
- Privacy Policy: GDPR/CCPA compliant, explicit on data retention, deletion, sub-processors listed.
- Cookie consent: required for EU traffic.
- Mental-health disclaimer: bold copy, repeated.
- Crisis-hotline page: India (iCall, AASRA), US (988), UK (Samaritans), with an obvious link.
- AI-output disclaimer: "Insights are generated by AI and may be incorrect" on every insight surface.

Liability for AI insights about mental patterns. The risk profile depends on what you claim. If you say "self-reflection tool", you are low-risk. If you say "diagnose your anxiety" or "your therapist", you cross into FDA medical-device territory in the US (Software as a Medical Device, SaMD) and CE/MDR in EU. Stay firmly in self-reflection language. Never auto-suggest interventions for diagnosed conditions; never use clinical scales (PHQ-9, GAD-7) inside the product without licensing.

Should you add coaching/therapy features? No, not yourself. Two safer options. (1) Stay strictly self-reflection and explicitly recommend professional care. (2) Partner — integrate with BetterHelp / Wysa / a regional therapy directory; revenue-share on referrals; you stay out of the regulated zone. Do not add an "AI therapist" mode. The liability surface is enormous and the reputation risk of one bad outcome is existential for a solo founder.

Community building. Worth it but not week 1. Start a Discord by month 3 once you have ~100 paying users. Weekly "pattern of the week" threads where users share (anonymized) insights. This is the highest-leverage retention move in consumer wellness apps and Rosebud has not invested heavily in it.

Burnout risk. Real and the single biggest threat to your plan. Twelve-hours-a-day full-time with no revenue is a 4-month maximum without significant external pressure relief. Mitigations: a hard 1-day-off-per-week rule from week 1; a fixed sleep window (your decision quality at 6 hours sleep is worse than at 7.5, every paper agrees); a revenue date by which you re-evaluate (90 days); a parallel option — accept 1-2 freelance gigs at $80–$150/hour to keep cash incoming so you do not feel forced to optimize MindGraph for short-term revenue. The founders who sustain solo work for 12+ months without burnout are the ones who treated it as a discipline, not a sprint.

Common solo AI SaaS pitfalls in 2026, observed across multiple founder accounts:

- Building agentic features for their own sake instead of solving a sharp problem.
- Single-LLM-provider lock-in (have a Gemini → OpenAI fallback path coded from day one).
- Premature scaling — hiring before $5K MRR is fatal.
- Ignoring unit economics until it's too late — instrument $/user/month from week 1.
- Selling technology, not outcomes — your landing page should say "see your patterns", not "knowledge graph".
- Vague positioning — "AI journal" is not a position; "for ADHD adults who want to see their behavioral patterns" is.

---

## Recommended priority sequence

The next 7 days: ship the product as a paid SaaS to one tight niche (recommend ADHD adults). Stripe Managed Payments or Paddle for billing. Free tier + $9/$79 Pro. Ship streaks, weekly insights, search, exports, encryption, disclaimers. Soft-launch to 50 hand-picked beta users. Instrument PostHog and Sentry. Cap LLM spend with hard rate limits and Gemini 2.5 Flash defaults.

The next 30 days: get to 100 sign-ups and 10 paying users. Run the build-in-public daily-tweet loop. One Reddit post in r/ADHD after two weeks of helpful comments. Hacker News Show HN in week 3. Start a weekly blog post on architecture and findings. Add voice journaling (browser MediaRecorder + Whisper). Add therapist-friendly export ("share with your therapist" PDF). Begin a private 5-conversation user-research loop — call 5 paying users, learn what they actually want next.

The next 90 days: drive to 500 sign-ups, 30–60 paying users, $300–$600 MRR. Decide based on cohort retention curves whether the product has legs. In parallel, run a 5-customer discovery loop on the B2B vertical — pick therapy or law and have 5 hour-long calls with target buyers about their existing tools and gaps. By day 90, you have either (a) a journaling product trajectory worth doubling down on, (b) a clear B2B insight to pivot toward, or (c) a strong portfolio + revenue story to leverage into a $40–80 LPA AI engineering role or $600/day freelance work. Pre-commit to which numbers cause which decision; do not negotiate with yourself in month 4.

Months 4–6 (contingent): if revenue trajectory holds, raise prices, add an annual-default checkout, and add one feature that creates a moat (probably a high-quality voice journal with on-device transcription, or a "graph of graphs" feature that shows patterns across friends/family circles for users who invite collaborators). If trajectory does not hold, pivot to a B2B vertical wedge with the therapist or law-firm hypothesis and use MindGraph's architecture as the foundation, repositioning the same code for a clinical or legal-knowledge-graph product at 10x the price point.

The final word: you have a stack that is genuinely competitive for both the consumer journaling fight and the vertical B2B knowledge-graph fight. You do not have the runway or the CAC budget to compete with Rosebud horizontally. Picking a sharp niche on the consumer side and a sharp vertical on the B2B side, and making the 90-day numbers force a decision, is the only plan that respects both your time and the market reality. Ship in 7 days, instrument relentlessly, and decide in 90.