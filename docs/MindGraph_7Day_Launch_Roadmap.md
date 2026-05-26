# MindGraph 7-Day Launch Roadmap
**April 30 – May 6, 2026 · For Karthik + coding agents**

---

## Reality check: where you actually are (post-GitHub audit)

After auditing the GitHub repo on April 30, you are much further along than a "ship MVP" plan would assume. Already shipped and working in production:

- 8-node LangGraph pipeline (normalize → dedup → fan-out [classify, entities, deadline, title_summary] → extract_relations → store), 6.66s end-to-end, $0.0003 per entry on Gemini 2.5 Flash-Lite
- FastAPI backend with 14 endpoints, JWT auth via Supabase, async background processing (acknowledge-fast/process-slow with pipeline_stage polling)
- Supabase Postgres with pgvector, 1536-dim Gemini embeddings
- Knowledge graph frontend with react-force-graph, semantic edges from `extract_relations`
- Dashboard, Ask (RAG), insights engine (patterns, weekly digest, forgotten projects, hybrid caching)
- Langfuse observability, Docker, Railway deployment, Sidebar nav, landing page, auth view
- 106 tests across entity extraction, store, project matching, RAG eval — 100% pass rate on entity extraction, zero hallucinations across 4 RAG eval runs
- Live: mindgraph-frontend-production.up.railway.app

What this means: **you are not building an MVP this week. You are turning a working product into a monetized one with a sharp niche position.** That's a different kind of week.

---

## Week-1 mission

By end of Tuesday May 6:
1. Paddle (or Stripe) live with $9/month and $79/year, Pro paywall functional
2. Niche position chosen and landing page rewritten for it (recommended: ADHD adults)
3. Streaks, daily reminder email, and weekly digest email shipped
4. Data export (JSON-LD + Markdown) live, mental health disclaimer + privacy basics shipped
5. PostHog + Sentry instrumented, hard rate limits and cost caps in place
6. 50 hand-picked beta users invited, first 3 paying users ideally onboarded
7. Public build-in-public momentum started on X with a daily cadence

### What you are explicitly NOT doing this week
Voice journaling, mobile native app, B2B exploration, community features, AI coaching chat, integrations, additional graph features, additional insight types, refactoring the pipeline, hiring a designer, building a notification center, complex consent UI, A/B testing infrastructure.

---

## Cadence and discipline

- 7 days, 12 hrs/day, ~84 hours total. Aim for 65–70 productive hrs and 14–19 hrs slack/recovery.
- Hard rule: one 24-hour break (your call which day, but take it).
- Sleep 7.5 hrs minimum. Decision quality on 6 hrs is measurably worse than 7.5 across every published study.
- Daily standup with yourself: 15 min at 8 AM IST writing yesterday's done / today's intent / blockers in Notion.
- Daily public tweet at end of day with a screenshot or metric. Non-negotiable for the build-in-public thread.
- Pre-commit decisions: niche (Wed), payment provider (Wed), pricing (Wed). Once decided, do not re-litigate this week.

---

## Niche decision (lock by Wednesday end-of-day)

Three candidates ranked by fit:

1. **ADHD adults** — best fit for graph thesis ("I never see my own patterns"), large engaged Reddit community (r/ADHD ~2M members), high willingness-to-pay, low CAC channels available. **Recommended.**
2. **Founders / solo operators** — pays without thinking, you have credibility here, smaller TAM but easier conversion.
3. **Therapy clients (between sessions)** — high LTV but higher liability messaging risk; defer to week 4+ once base is stable.

Default to ADHD unless you have a specific reason otherwise.

---

## Payment provider decision (lock by Wednesday)

- **Paddle** (Merchant of Record, 5% + $0.50): handles all global VAT/tax, single payout to India, FEMA-clean. Best for a Bangalore founder selling globally. **Recommended.**
- **Stripe Managed Payments** (5% + $0.50, MoR via Stripe): equivalent option, slightly newer.
- **Stripe direct** (2.9% + $0.30): cheaper headline but you handle global tax compliance — adds a CA cost of ₹40–80K/year.

Default to Paddle unless you already have a Stripe entity set up.

---

# Day 1 — Wednesday April 30 (Today): Strategy, niche, payments groundwork

**Theme:** Decisions, accounts, killable scope. Light on code.

## 9:00 AM – 11:00 AM · Strategic decisions, locked
- [ ] Niche: lock to ADHD (or alternative with explicit reasoning written in Notion)
- [ ] Payment provider: open Paddle account (`paddle.com/signup`), submit business verification (you'll need PAN, address proof, GST cert if available, bank account). Verification typically 1–3 days — start now.
- [ ] Pricing: $9/month and $79/year for Pro. Free tier = 5 entries/week, basic graph (entities only, no semantic relations rendered), 30-day history view.
- [ ] Domain: ensure mindgraph.app or similar custom domain points at Railway frontend (your current URL is fine for beta but you need a custom domain by Day 5 for public launch).

## 11:00 AM – 1:00 PM · Niche positioning + landing page rewrite spec
Write a spec in Notion for the landing page rewrite. Hand to coding agent on Day 5. Spec includes:
- Headline: "See the patterns in your own life. Built for ADHD minds."
- Subheadline: "MindGraph reads what you write and shows you the people, projects, and themes you keep returning to — so you can finally see what's actually going on."
- Three feature cards (graph, weekly insights, ask your journal — drop generic feature lists)
- One screenshot of the actual graph (not a placeholder)
- Social proof section (placeholder for now; will fill in by Day 6)
- FAQ targeting ADHD-specific objections ("I've tried journaling and dropped it", "Will the AI judge me?", "Is my data private?")
- CTA: "Try free for 14 days" → email signup or direct signup
- Footer: privacy, terms, mental health disclaimer

## 2:00 PM – 5:00 PM · Code: kill list and rate limits
The single biggest risk on launch day is one bad actor running through your Gemini budget. Ship hard limits today.

### Coding agent prompt — copy this verbatim:
> Add per-user rate limiting to the FastAPI backend in `app/main.py`. Use `slowapi` with Redis backend (provision Redis on Railway as a service). Three tiers:
> 1. Per-IP: 30 entry submissions per hour (anti-abuse)
> 2. Per-user free tier: 5 entry submissions per rolling 7-day window, 20 ask requests per day, 50 search requests per day
> 3. Per-user paid tier: 100 entry submissions per day, 200 ask requests per day, unlimited search
>
> Add a `subscription_tier` column to the `users` profile table (values: 'free' | 'pro') defaulting to 'free'. Read this column in the rate limit decorator. Return HTTP 429 with a clear JSON body: `{"error": "rate_limit", "limit": <int>, "reset_at": <iso8601>, "tier": "<tier>"}`. Add a `Retry-After` header.
>
> Also add a hard daily LLM-cost cap: if a user's accumulated Langfuse trace cost exceeds $0.10/day on free or $1.00/day on paid, block further pipeline calls and return HTTP 429 with `{"error": "cost_limit_exceeded"}`. Read cost from a new `daily_llm_costs` table updated by a Langfuse webhook or polled hourly.
>
> Add tests in `test_rate_limits.py`: 6 cases covering free-tier exceed, paid-tier exceed, IP exceed, cost cap, headers correctness, reset_at timing.
>
> Acceptance: `pytest test_rate_limits.py` passes. Manual curl test confirms 6th submission within a week on free tier returns 429.

## 5:00 PM – 7:00 PM · Sentry + PostHog instrumentation

### Coding agent prompt:
> Integrate Sentry SDK (`sentry-sdk[fastapi]`) into the FastAPI backend with `traces_sample_rate=0.2`. Capture environment, release version, user_id (anonymized hash) on every request. Wire `@sentry_sdk.capture_exception` into existing exception handlers.
>
> Integrate PostHog (`posthog` Python SDK) into the backend and `posthog-js` into the React frontend. Track these events:
> - Backend: `entry_submitted`, `entry_processed`, `ask_query`, `insight_viewed`, `paywall_shown`, `subscription_started`, `rate_limit_hit`, `pipeline_error`
> - Frontend: `signup_started`, `signup_completed`, `first_entry_written`, `graph_viewed`, `entry_view_clicked`, `export_requested`, `pricing_viewed`, `checkout_started`
>
> Each event should include `user_id` (hashed), `session_id`, and event-specific properties. Add `.env` keys `SENTRY_DSN`, `POSTHOG_API_KEY`, `POSTHOG_HOST`.
>
> Acceptance: ship a deliberate exception, see it in Sentry. Submit an entry, see `entry_submitted` then `entry_processed` in PostHog. Confirm session funnel works.

## 7:00 PM – 8:30 PM · Public commitment + day wrap
- [ ] Tweet 1: "Day 1 of 7. I'm taking MindGraph from working product to paid SaaS in one week. ADHD adults, $9/mo, weekly insights from your own journal. Build-in-public thread starts here. [screenshot of graph]"
- [ ] Daily standup written in Notion: "Done / Not done / Tomorrow / Risks"
- [ ] Tomorrow prep: pin tomorrow's tasks at the top of your task list

## ✓ Day 1 done when
- Niche locked, written down, will not be re-litigated this week
- Paddle account submitted for verification
- Rate limits and cost caps deployed to production
- Sentry + PostHog firing in production
- One tweet out

## 🚫 Day 1 do NOT
- Touch the LangGraph pipeline
- Add any new "insight" type
- Refactor anything

---

# Day 2 — Thursday May 1: Subscription billing + paywall

**Theme:** Money plumbing. The most painful single day of the week — get it done.

## 9:00 AM – 9:30 AM · Standup + tweet planning

## 9:30 AM – 1:00 PM · Paddle integration backend

### Coding agent prompt:
> Integrate Paddle Billing into the FastAPI backend. Paddle uses a hosted checkout (PaddleJS) plus webhooks for subscription lifecycle.
>
> Tasks:
> 1. Create two products in Paddle dashboard: `MindGraph Pro Monthly` ($9/mo) and `MindGraph Pro Annual` ($79/yr). Note their `price_id` values.
> 2. Add `app/billing.py` with three webhook handlers verified via Paddle's signature header:
>    - `subscription.created` → set user's `subscription_tier` to 'pro', store `paddle_customer_id`, `paddle_subscription_id`, `current_period_end` in a new `subscriptions` table
>    - `subscription.updated` → update `current_period_end`, handle plan changes
>    - `subscription.canceled` → set `subscription_tier` to 'free' AT END of current period (not immediate); store `cancel_at`
> 3. Add endpoint `POST /billing/checkout-session` that returns a signed checkout URL for the requesting user
> 4. Add endpoint `GET /billing/portal-url` that returns Paddle customer portal URL (for managing/canceling subscription)
> 5. Add endpoint `GET /billing/status` that returns user's current tier, plan, renewal date, and cancel state
>
> Add `subscriptions` table: id, user_id (FK), paddle_customer_id, paddle_subscription_id, plan (monthly|annual), status (active|canceled|past_due), current_period_start, current_period_end, cancel_at, created_at, updated_at.
>
> Acceptance: from Paddle's sandbox, complete a test purchase. Webhook fires. User's `subscription_tier` flips to 'pro' in Supabase. `GET /billing/status` returns correct data.

## 1:00 PM – 2:00 PM · Lunch + Twitter scroll (you've earned 30 min)

## 2:00 PM – 5:00 PM · Frontend pricing page + paywall component

### Coding agent prompt:
> Build a `Pricing.js` React component routed at `/pricing`. Two cards side by side: Free and Pro. Annual toggle defaults to ON (annual selected). Show "$79/year — 2 months free" prominently. Include a feature comparison table:
>
> | Feature | Free | Pro |
> |---|---|---|
> | Entries per week | 5 | Unlimited |
> | Knowledge graph | Entities only | Full + semantic relations |
> | History | 30 days | Forever |
> | Weekly insights email | — | ✓ |
> | Patterns + forgotten projects | — | ✓ |
> | Ask your journal | 20/day | 200/day |
> | Data export | ✓ | ✓ |
> | Email support | — | ✓ |
>
> CTA "Start free" for free tier (signs up + lands on app), CTA "Start Pro" for paid (calls `POST /billing/checkout-session`, redirects to Paddle checkout).
>
> Build a `Paywall.js` component shown when free user hits a Pro-gated feature. Modal-style with "You're on Free. Upgrade to Pro for unlimited entries and weekly insights." Two buttons: "Upgrade to Pro" (to /pricing) and "Maybe later" (dismiss).
>
> Wire paywall into:
> - Entry submission flow (when free user has hit 5/week)
> - Insight cards (patterns and forgotten projects show locked overlay for free users with paywall on click)
> - Graph filter for "semantic relations" (toggle disabled for free users with paywall on click)
> - History view beyond 30 days (locked entries show paywall)
>
> Track every paywall display via `paywall_shown` PostHog event with `feature` property.
>
> Acceptance: as free user, hit each gate, see paywall. Click upgrade, complete Paddle test purchase, return to app, gate is gone.

## 5:00 PM – 7:00 PM · Manual end-to-end test + bug fix buffer
- [ ] Test signup → free usage → hit gate → paywall → checkout → return → pro user → pro features unlocked
- [ ] Test cancel from Paddle portal → end of period → tier reverts to free
- [ ] Test webhook signature failure (block invalid)
- [ ] Test rate limits firing for free vs pro

## 7:00 PM – 8:00 PM · Tweet 2 + standup
- Tweet: screenshot of pricing page + "Day 2 done. Stripe — sorry, Paddle — wired up. Free vs Pro live. Now I just need users."

## ✓ Day 2 done when
- Paddle test transaction completes end-to-end
- Webhooks correctly flip subscription_tier
- Paywall shows on all four gated features
- PostHog tracks paywall_shown and subscription_started events
- Cancel flow tested

## 🚫 Day 2 do NOT
- Add a third pricing tier (Pro is fine for now)
- Add team/family plans
- Add usage-based pricing
- Build a billing dashboard for users (Paddle portal is fine)

---

# Day 3 — Friday May 2: Streaks + daily reminder + weekly digest email

**Theme:** Retention loops. Streaks bring users back; weekly digests bring lapsed users back.

## 9:00 AM – 9:30 AM · Standup + tweet planning

## 9:30 AM – 12:30 PM · Streak engine

### Coding agent prompt:
> Build a streak system. Define streak as: consecutive days with at least one journal entry written.
>
> Schema additions to `users` table: `current_streak` (int, default 0), `longest_streak` (int, default 0), `last_entry_date` (date), `streak_freeze_count` (int, default 1, replenishes Monday), `streak_freeze_used_dates` (date[] for audit).
>
> On every successful entry write, in `app/main.py` after store node completes:
> 1. Compute today_local in user's timezone (add `timezone` column to users, default 'Asia/Kolkata', let user set in Settings)
> 2. If `last_entry_date == today_local`, do nothing (already counted)
> 3. If `last_entry_date == today_local - 1 day`, increment `current_streak`, update `longest_streak` if needed
> 4. If gap > 1 day AND `streak_freeze_count > 0` AND only one missed day, auto-apply freeze: don't reset, decrement freeze count, add to used_dates
> 5. Otherwise reset `current_streak` to 1
>
> Replenish streak_freeze_count to 1 every Monday via a scheduled job.
>
> Add `GET /me/streak` endpoint returning current streak, longest streak, freeze count, and "danger" flag (true if user wrote yesterday but not today and it's after 8 PM their local time).
>
> Frontend: add streak display in Sidebar (flame icon + number). On Dashboard, show small "X day streak — write today to keep it" banner if danger flag is true.
>
> Acceptance: write entries 3 days in a row, streak shows 3. Skip a day, streak freeze auto-applies, count drops to 0 freezes, streak preserved at 4. Skip 2 days, streak resets.

## 12:30 PM – 1:30 PM · Lunch

## 1:30 PM – 4:30 PM · Daily reminder email

### Coding agent prompt:
> Integrate Resend (`resend` Python SDK) for transactional email. Sign up at resend.com if not already. Verify a sending domain (use mindgraph.app — set up SPF, DKIM, DMARC records in Railway/registrar DNS).
>
> Build a daily reminder email job:
> 1. Use APScheduler or a Railway cron service to run at user's preferred time (default 8 PM in their timezone)
> 2. For each user where `email_reminders_enabled = true` (add this column to users, default true) AND user hasn't written today AND user has streak > 0:
>    - Send email subject: "Your X-day streak is at risk"
>    - Body: brief, ADHD-friendly. "You've written 4 days in a row. Write 1 line right now to keep going. [link to app]"
> 3. For users where streak == 0 but they haven't written in 3+ days:
>    - Send email every 3 days subject: "What's on your mind?"
>    - Body: 1 prompt pulled from their graph ("You wrote about X 3 weeks ago. Has anything changed?") if they have history, else a generic ADHD-friendly prompt
>
> Add Settings page: toggle email_reminders_enabled, choose time (4 options: morning 8 AM, lunch 1 PM, evening 8 PM, night 10 PM in user's timezone), unsubscribe link in email footer.
>
> Acceptance: write entries 2 days, miss day 3 evening, receive reminder email at 8 PM local. Toggle off, no email next day.

## 4:30 PM – 7:00 PM · Weekly digest email

### Coding agent prompt:
> Build a weekly digest email sent every Sunday morning 9 AM in user's timezone, only to users with `subscription_tier = 'pro'`. (Free users see a "Weekly digest is a Pro feature — upgrade" tease in the app every Sunday.)
>
> The digest reuses the existing `insights_engine.py` weekly digest logic which is already cached. Email content:
> - Subject: "Your week in MindGraph: 3 patterns we noticed"
> - Stats row: entries this week, current streak, top 3 mentioned entities
> - Pattern of the week: pulled from cached patterns
> - Mood arc: pulled from cached weekly digest
> - Forgotten project nudge: if any forgotten projects were detected
> - One reflection prompt: generated by Gemini Flash-Lite using their week's content
> - CTA: "Open MindGraph"
>
> If a user has < 3 entries that week, send a different "low-content" digest: "We didn't see much from you this week. Sometimes weeks are like that. Here's a 1-line prompt for tomorrow."
>
> Acceptance: as a Pro user with 7 days of entries, receive Sunday morning digest with all sections populated. As a free user, no email but in-app banner appears.

## 7:00 PM – 8:00 PM · Tweet 3 + standup
- Tweet: screenshot of streak counter + "Day 3 done. Streaks, daily reminders, weekly digest emails. The boring infrastructure of habit, shipped."

## ✓ Day 3 done when
- Streak counter working with auto-freeze
- Daily reminder email sent to test account at expected time
- Weekly digest email rendered correctly for test Pro account
- All emails have unsubscribe link and pass DKIM/SPF/DMARC

## 🚫 Day 3 do NOT
- Build a notifications center in the app
- Build push notifications (browser or otherwise)
- Add SMS reminders
- Add multiple reminder types ("morning gratitude", "evening reflection", etc.) — one is enough this week

---

# Day 4 — Saturday May 3: Data export + privacy/disclaimers + onboarding polish

**Theme:** Trust signals. Make MindGraph feel safe to write your real thoughts into.

## 9:00 AM – 9:30 AM · Standup + tweet

## 9:30 AM – 12:30 PM · Data export

### Coding agent prompt:
> Build comprehensive data export.
>
> Add endpoint `GET /me/export?format=jsonld|markdown` that returns the user's complete data:
> - JSON-LD format: all entries (id, raw text, normalized text, title, summary, classification, mood, created_at), all entities (id, name, type, mention_count, first_seen, last_seen), all relations (subject_id, predicate, object_id, confidence, source_entry_id), all deadlines, basic user metadata
> - Markdown format: one file per entry, frontmatter with metadata, entries grouped by month into folders, plus an `entities.md` index and `relations.md` index — bundle as zip
>
> Implementation: stream large exports as chunked response. For users with 1000+ entries, this should still complete in < 10s.
>
> Frontend: add Settings → "Your Data" section with two buttons "Download as JSON-LD" and "Download as Markdown (zip)". Show last export date.
>
> Add a third button "Delete my account" that opens a 2-step confirmation modal (type your email to confirm) and triggers `DELETE /me` which:
> 1. Deletes all entries, entities, relations, embeddings, deadlines, insights, subscriptions records
> 2. Cancels Paddle subscription if active
> 3. Deletes Langfuse traces for this user via Langfuse API
> 4. Deletes Supabase auth row
> 5. Logs the deletion timestamp for compliance
>
> Acceptance: as test user, export both formats, verify content matches DB. Delete account, verify all rows gone, verify cannot log in. Verify Langfuse traces removed.

## 12:30 PM – 1:30 PM · Lunch

## 1:30 PM – 3:30 PM · Privacy policy + ToS + mental health disclaimer

### Coding agent prompt (this one is mostly content, not code):
> Create three new pages, all linked from footer:
>
> `/privacy` — privacy policy. Use Termly or Iubenda free generator as a starting point, customize for: GDPR, CCPA, India DPDP Act 2023. Specify:
> - What we collect: account info, journal entries, derived metadata (entities, relations)
> - Lawful basis: explicit consent (Art. 9 special category data because journaling can include health info)
> - Sub-processors: list Supabase, Railway, Google (Gemini), Langfuse, Paddle, Resend, PostHog, Sentry with links to each one's privacy policy
> - Retention: data kept until user deletes account; backups purged within 30 days
> - User rights: access, rectification, erasure, portability, restriction, objection
> - Contact: privacy@mindgraph.app (set up this inbox today)
> - Data residency: state where Supabase region is hosted
>
> `/terms` — terms of service. Standard SaaS template with:
> - Subscription terms (auto-renewal, cancellation, refund policy: 14-day refund on first purchase, no refunds after)
> - Acceptable use (no illegal content, no scraping, no reverse engineering)
> - Limitation of liability capped at fees paid in last 12 months
> - Arbitration clause (specify jurisdiction: Bangalore, India)
> - No warranty disclaimer
> - "We are not a medical device" specific clause
>
> `/disclaimer` — mental health disclaimer. Bold, prominent.
> - "MindGraph is a self-reflection tool. It is not a medical device, not therapy, and not a substitute for professional mental health care."
> - "If you are in crisis or considering harming yourself, please contact: India: iCall 9152987821, AASRA 9820466726. US: 988. UK: Samaritans 116 123. International: findahelpline.com"
> - "AI-generated insights may be incorrect, biased, or miss important context. They are prompts for your own reflection, not assessments of your mental state."
>
> Add a small persistent footer text on every insight surface (patterns, forgotten projects, weekly digest): "AI-generated reflection prompt. May be incorrect."
>
> First-run modal during signup: brief disclaimer with "I understand" checkbox required to proceed.
>
> Acceptance: visit each page, content renders, footer link works, signup flow gates on disclaimer checkbox.

## 3:30 PM – 6:00 PM · Onboarding polish

### Coding agent prompt:
> Improve first-run onboarding for new signups. Goal: get user to write their first entry within 90 seconds of signup.
>
> Flow:
> 1. Signup form (email + password) — already exists
> 2. Disclaimer modal (Day 4 above)
> 3. New: 3-screen onboarding carousel
>    - Screen 1: "Welcome. MindGraph reads what you write and shows you the patterns you can't see yourself." + screenshot of graph
>    - Screen 2: "Three ways people use MindGraph: track what you keep returning to, see your week at a glance, ask questions about your own past." (One sentence each, with icons)
>    - Screen 3: "Let's write your first entry. Here are three prompts — pick one."
>      - "Something you've been avoiding"
>      - "A hard conversation this week"
>      - "What made you laugh recently"
>    - Or "Skip and write your own"
> 4. User lands on InputView with chosen prompt prefilled as a hint (not as text), can write
> 5. After first entry submits, show animated "wow" moment: graph being built in real time as nodes pop in over 6 seconds (use the existing pipeline_stage polling — already implemented)
> 6. After graph finishes, prompt "Want to add another?" with one-click "Write again" button
>
> Track funnel events: `onboarding_screen_1_viewed`, `onboarding_screen_2_viewed`, `onboarding_screen_3_viewed`, `prompt_selected`, `first_entry_submitted`, `first_entry_processed`, `second_entry_started`.
>
> Acceptance: signup → disclaimer → onboarding → first entry → graph builds → second-entry CTA, all in < 2 minutes.

## 6:00 PM – 7:30 PM · Buffer / bug fixes / polish

## 7:30 PM – 8:30 PM · Tweet 4 + standup
- Tweet: short clip of onboarding flow ending in graph build animation. "Day 4 done. Onboarding now lands you on your first 'aha' in 90 seconds. Privacy policy live. Disclaimer live. Export your data anytime — it's yours."

## ✓ Day 4 done when
- JSON-LD + Markdown export working
- Account deletion flow working
- Privacy, ToS, disclaimer pages live, footer links work
- First-run onboarding flow tested end-to-end
- Funnel events tracked in PostHog

## 🚫 Day 4 do NOT
- Hire a lawyer this week (templates + your own review is fine for beta)
- Implement SOC 2 anything
- Add multi-language support to legal pages
- Build a complex consent management UI

---

# Day 5 — Sunday May 4: Polish, custom domain, soft beta launch

**Theme:** Make it look real. Get the first 50 humans onto it.

## 9:00 AM – 9:30 AM · Standup + tweet

## 9:30 AM – 12:00 PM · Custom domain + production hardening
- [ ] Buy `mindgraph.app` (or `getmindgraph.com` if `.app` is gone). ~$15/year on Cloudflare or Namecheap.
- [ ] Configure DNS: A/AAAA or CNAME to Railway frontend; subdomain `api.mindgraph.app` → Railway backend
- [ ] Update Supabase auth allowed redirect URLs
- [ ] Update Paddle return/webhook URLs
- [ ] Update CORS origins in FastAPI
- [ ] Add Cloudflare proxy for caching + DDoS protection (free tier is plenty)
- [ ] Verify HTTPS everywhere, no mixed content warnings
- [ ] Run a Lighthouse audit on landing page, fix anything < 90 (perf, accessibility, SEO, best practices)

## 12:00 PM – 1:00 PM · Lunch

## 1:00 PM – 4:00 PM · Landing page rewrite (the spec from Day 1)

### Coding agent prompt:
> Rewrite the LandingPage.js component using the spec from Day 1's Notion doc. Keep the existing styles/landing.css design tokens but adjust copy and layout per spec. Add:
> - Hero with headline + subheadline + CTA "Try free for 14 days" + "See how it works ↓"
> - "How it works" 3-step section: Write → AI extracts → See your graph (with the actual pipeline diagram from the README, simplified)
> - Live demo embed: a short Lottie or 10-second video of the graph being built (record with Loom or Screen Studio)
> - "Built for ADHD minds" section: 3 reasons why this works for ADHD specifically (low friction, no rules, AI does the organizing)
> - Pricing teaser: 2-card minimal version with "See full pricing →" link
> - FAQ: 5–7 questions ADHD-specific
> - Footer with all legal links + privacy + ToS + disclaimer + contact email
>
> Acceptance: landing page reads cleanly to a non-technical ADHD adult. No jargon visible. Page loads < 2s on 4G. Mobile responsive.

## 4:00 PM – 6:00 PM · Soft beta list + invitation
- [ ] Compile soft beta list of 50 people. Mix:
  - 10 personal/professional contacts likely to give feedback
  - 15 ADHD-positioned reach-outs from r/ADHD, ADHD Twitter, ADHD Discord communities (you've been in for at least 2 weeks — DO NOT cold-spam strangers)
  - 10 indie hacker / build-in-public Twitter contacts who'll give honest feedback
  - 10 from your professional network (Surrey, Infosys alumni, AI engineering Twitter)
  - 5 wildcards (existing journaling app users found via Twitter searches)
- [ ] Personal email to each person (template-based but with personal first line). Subject: "Built something for [their context]. Want to try?"
- [ ] Body: 3 sentences max. What it is, why I built it, ask for honest feedback after 1 week. Link.
- [ ] Track invites in a Notion table: name, channel, invited date, signed up Y/N, first entry Y/N, paid Y/N, feedback (paste).

## 6:00 PM – 8:00 PM · Status page + uptime monitoring

### Coding agent prompt:
> Set up uptime monitoring with Better Stack (free tier) or UptimeRobot. Monitor:
> - GET https://mindgraph.app/ (frontend)
> - GET https://api.mindgraph.app/health (backend)
> - POST a synthetic auth-test that signs in to a test account every 15 min
>
> Set up status page at status.mindgraph.app pulling from monitoring data.
> Set up alerts: ping my phone via SMS or Telegram for any > 2 min outage.
>
> Add a `/status` link in the app footer.
>
> Acceptance: trigger a deliberate 503, get alerted within 2 min. Status page reflects within 1 min.

## 8:00 PM – 9:00 PM · Tweet 5 + standup
- Tweet: screenshot of new landing page on mindgraph.app + "Day 5 done. New landing page, new domain, soft beta open to 50 people tonight. Say hi if you want in."

## ✓ Day 5 done when
- mindgraph.app (or chosen domain) live with valid HTTPS
- Landing page rewritten and Lighthouse > 90
- 50 beta invites sent
- Status page live, alerts firing for synthetic outages

## 🚫 Day 5 do NOT
- Set up complex marketing automation
- Pay for ads
- Hire a designer (your existing CSS is fine for beta)
- Add A/B testing infrastructure (no traffic to test on yet)

---

# Day 6 — Monday May 5: Public launch prep + Hacker News + Reddit

**Theme:** Earn one big day of traffic. Don't waste it.

## 9:00 AM – 9:30 AM · Standup + tweet

## 9:30 AM – 12:00 PM · Hacker News Show HN preparation
- Title: "Show HN: MindGraph – Knowledge graph from your journal entries (LangGraph + pgvector)"
- Body (≤ 1500 chars):
  > Hi HN. I'm a Bangalore-based AI engineer and I built MindGraph because I write a lot but never re-read what I write — so I never see my own patterns.
  >
  > MindGraph runs an 8-node LangGraph pipeline over each journal entry. It extracts entities, types semantic relations between them ("works on", "manages", "blocks"), and stores them in Postgres with pgvector for RAG. The frontend renders the result as an interactive d3-force graph so I can actually see who and what I keep returning to.
  >
  > Tech: LangGraph (parallel fan-out → fan-in), Gemini 2.5 Flash-Lite for the pipeline ($0.0003/entry, 6.66s), pgvector for embeddings, Supabase Auth, FastAPI backend, React frontend with react-force-graph. Full pipeline traced in Langfuse.
  >
  > Things I'd love feedback on: (1) the typed-relation taxonomy — currently 7 types, considering more, (2) the "forgotten projects" detection (entropy-based) — does this concept land?, (3) RAG eval ran 4 times, hit 0 hallucinations across 15 test cases — happy to share methodology.
  >
  > Free tier with 5 entries/week, $9/mo or $79/yr for Pro. Built for ADHD adults specifically because the "I never see my own patterns" pain is most acute there.
  >
  > Live: mindgraph.app · Code: github.com/karthikmadheswaran/mindgraph
- Schedule: post **Tuesday 7:30 AM Pacific (Tuesday 8 PM IST)**. NOT today. HN traffic peaks Tuesday/Wednesday morning Pacific.
- Plan to be at your laptop for 6 hours after posting to reply to every comment thoughtfully and quickly.

## 12:00 PM – 1:00 PM · Lunch

## 1:00 PM – 3:00 PM · Reddit r/ADHD post preparation
- DO NOT post today. Read the rules carefully. r/ADHD is moderation-heavy. Self-promo is allowed only in specific contexts.
- Draft a post for Wednesday (after HN), titled something like: "I built a journaling tool for myself because I'd write things and forget them. It might help others with ADHD."
- Post body should: lead with personal story, describe the problem, show the actual tool, mention free tier, ask for feedback, and explicitly state you're the builder.
- Save for Wednesday submission. Today is research only.

## 3:00 PM – 5:30 PM · Twitter/X build-in-public arc
- Compile the week's tweets into a Twitter thread teaser: "I shipped a paid SaaS in 7 days. Here's what I built and what I learned."
- Schedule for Tuesday alongside HN post.
- Make sure your X profile bio mentions MindGraph + ADHD focus + link.
- Pin your best tweet from the week.

## 5:30 PM – 7:30 PM · Beta feedback triage
- Check beta invites: how many signed up? How many wrote a first entry? Which dropped off?
- Reach out personally to anyone who signed up but didn't write — ask why (1 question, no pressure).
- Reach out personally to anyone who wrote 3+ entries — ask if they'd consider Pro and why or why not. Capture in Notion.
- Identify any P0 bugs from feedback. Fix only P0s tonight.

## 7:30 PM – 8:30 PM · Tweet 6 + standup
- Tweet: a real screenshot of an early beta user's graph (with permission, anonymized) + "Day 6 done. Beta has [N] users, [M] paying. Tomorrow I open it to the world."

## ✓ Day 6 done when
- HN post drafted, reviewed, scheduled mentally for Tuesday morning Pacific
- Reddit post drafted, scheduled for Wednesday
- Twitter thread teaser ready
- Beta feedback captured for at least 10 users
- All P0 bugs from beta fixed

## 🚫 Day 6 do NOT
- Post to HN today (Mondays are weak)
- Post to multiple subreddits today
- Reply to PMs from non-beta users with feature requests — capture in a backlog Notion DB
- Add new features in response to beta feedback (capture only)

---

# Day 7 — Tuesday May 6: Public launch day

**Theme:** Earn the day. Stay at your laptop. Convert traffic to signups.

## 7:00 AM – 7:30 AM IST · Wake up, coffee, check beta metrics overnight

## 7:30 AM – 8:00 AM IST (= 7:00–7:30 PM Monday Pacific) · Final pre-launch checks
- [ ] mindgraph.app loads, signup works, first entry processes, graph renders
- [ ] Paddle test purchase one more time
- [ ] Sentry has no critical alerts
- [ ] Status page shows green
- [ ] Tweet thread queued

## 8:00 AM IST · Submit Show HN
- Post HN with the prepared title + body
- Post the Twitter thread teaser linking to the HN post
- Post in 1–2 indie hacker Discords / Slack groups you're already in (do not spam)
- Email the 50 beta users a "we're publicly live today" note with a referral ask

## 8:00 AM – 8:00 PM IST · Reply to every comment
- HN: reply to every comment within 60 minutes for the first 6 hours. Be concise, be honest, do not be defensive. If someone identifies a real issue, thank them and fix it.
- Twitter: reply to every quote tweet, RT thoughtful ones.
- Treat this like a 12-hour customer support shift. Eat at your desk.

## Throughout the day · Real-time monitoring
- Watch PostHog: signups, first entries, paywalls hit, conversions
- Watch Sentry: any new errors at 10x scale
- Watch Langfuse: any cost spikes
- Watch Paddle: any conversions

## 6:00 PM IST onwards · Post to r/ADHD if HN went well
- If HN was well-received and there are no major outstanding issues, post the prepared r/ADHD post Wednesday morning IST.

## 8:00 PM – 9:30 PM IST · Day 7 wrap + week wrap
- Tweet 7: numbers from launch day — visitors, signups, first entries, paid conversions. Honest version, even if numbers are small.
- Notion writeup: what worked, what didn't, what surprised you.
- Plan Week 2 in 30 minutes (what's the next 7 days of focus given the data).
- Sleep early. You've earned it.

## ✓ Day 7 done when
- HN post live and engaged
- Reddit post drafted, scheduled or posted Wednesday
- Twitter thread live with engagement
- Public launch numbers logged
- Week 2 plan drafted

## 🚫 Day 7 do NOT
- Make architectural changes during launch day (only fix bugs)
- Promise features in HN comments you haven't built
- Engage with trolls — ignore, do not reply
- Stay up until 4 AM celebrating one viral comment — sleep is your edge

---

# Backlog (after Week 1 — DO NOT touch this week)

These are real and important but explicitly out of scope for Week 1. Capture only.

- Voice journaling (browser MediaRecorder + Whisper API or Gemini audio input)
- iOS or Android wrapper (PWA first; native later if revenue justifies)
- Sharing / collaboration (graph of graphs)
- More relation types beyond the V1 7 (wait for at least 50 paying users + signal that they want it)
- Therapist-facing PDF export ("share with your therapist")
- Apple Health / Google Fit mood correlation
- Import from Day One, Reflect, Notion, Obsidian
- Multilingual support (start with Hindi + Spanish if 20%+ of users request)
- Browser extension for "save thought from anywhere"
- Slack/Discord integration (more for B2B, not B2C)
- Coach-mode AI chat — DEFERRED, liability risk
- Community feature — defer to month 3
- B2B vertical exploration (therapy-practice or law-firm version)

---

# Failure modes to watch for this week

- **Coding agent generates working but slow code** — measure latency on every new endpoint, keep p95 < 500ms for read endpoints, < 3s for write.
- **Paddle verification takes longer than 3 days** — have a Stripe Managed Payments fallback ready as a contingency.
- **Email deliverability fails** — verify DKIM/SPF/DMARC immediately on Day 3, send test to gmail/outlook/icloud test inboxes.
- **LLM cost runs hot** — daily check on Day 5, Day 6, Day 7. Hard cap is in place from Day 1, but monitor.
- **One viral negative HN comment** — have a thoughtful, non-defensive response ready for predictable critiques: "AI journaling is privacy-violating", "this is just a wrapper", "knowledge graphs are overhyped". Address each honestly.
- **Personal burnout** — if at any point you're awake past midnight three nights in a row, take a 24-hour break. The week is long; your body is not infinite.

---

# Metrics that matter at end of Week 1

Aim for, in order of importance:
1. ≥ 100 unique signups
2. ≥ 50 first-entry completions (50% activation)
3. ≥ 20 users who wrote 3+ entries (40% week-1 retention)
4. ≥ 3 paid conversions (3% conversion of total signups, ≥ 6% of activated)
5. ≥ 5 honest pieces of qualitative feedback captured
6. HN post in top 30 for at least 4 hours
7. Reddit post upvoted positive in r/ADHD
8. ≥ 50 followers gained on X from build-in-public
9. Zero critical incidents (downtime, data loss, billing error)

If you hit 5 of 9, the week was a success. If you hit 7 of 9, you have a real product trajectory.

If you hit only 1 or 2, do not panic. Run Week 2 with niche refinement and content compounding. The 90-day decision point still stands.

---

# Daily prompt-the-coding-agent template

For each day's tasks, hand the coding agent:

1. **Context:** "We are working on MindGraph, a paid AI journaling SaaS. Here's the current state of the codebase: [link to README]. We're on Day X of a 7-day launch."
2. **Goal:** "Today we are shipping [feature]. Here is the spec: [paste the prompt from this doc]."
3. **Constraints:** "Do not modify the LangGraph pipeline. Do not change existing tests. Add new tests for new code. Use existing patterns in `app/` and `mindgraph-frontend/src/`. Write ≤ 200 lines per file."
4. **Acceptance:** "Done = [acceptance from this doc]. Run `pytest` and `npm test` before declaring done."
5. **Format:** "Output: list of files changed/created, brief description of each, the code, then a summary of remaining manual steps."

Keep prompts separate per task. Do not batch.

---

# End-of-week reflection prompts (for your own journal)

Write these in MindGraph itself on May 6 night:

- What surprised me about this week?
- Which assumption was wrong?
- Which user feedback hit hardest?
- If I had to do Week 2 with half the effort, what would I cut?
- Am I energized or depleted? Honest answer.

The graph that emerges from these 7 entries plus your week's worth of building entries is, in itself, the strongest possible proof of MindGraph's value.

Ship it.
