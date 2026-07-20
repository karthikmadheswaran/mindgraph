# Design: Graph v2 / Patterns view

**Status:** DEFERRED except components explicitly authorized per session.
**Trigger for full build:** demand test complete AND ≥5 real users with 10+ entries each.
**Drafted:** 2026-07-20. Idea sources: existing deferred-insight list + concept review of Graphify-Labs/graphify (dev tool, not integrated — ideas only).

## Principle constraints (locked, from product philosophy)

- **Witness, not manager.** Everything here is pull-based: the user navigates to it. Nothing in this doc ever becomes a Home card, notification, or push surface.
- **Home stays untouched.** One drift card + one gift card. This view lives in Journal → Patterns.
- Quietness over density applies *within* the view too: default to the strongest few signals, expand on demand.
- Dashboard sections are framed as questions the user asks about themselves. Test for every element: if it answers "am I doing well?" (score/target/streak/judgment), it is out; if it answers "what's true about me that I couldn't see?", it is in.

## Problem

The pipeline extracts far more than the product surfaces. `entry_tags` (nine-category classifier) has zero frontend references. Entity co-occurrence, per-entity attention share, and cross-entity structure are computed or trivially computable but invisible.

## Components (all pull-based)

### 1. Attention Mix — "Where has my attention been going?"
- Source: `entry_tags` (already written on every entry; no backend extraction work).
- Stacked area chart of the nine categories over time, bucketed weekly.
- Framing: "where your words have been going." No targets, no ideal mix.

### 2. Gravity / god-nodes — "What's taking up the most space?"
- Rank entities by share of entries mentioning them (30-day window) with prior-window share as trend.
- Ranked strip, top 5: "Rahul — in 38% of your entries, up from 12%." Trend is data, never good/bad styling. Never suggests actions ("reach out to X").

### 3. Drift ledger — "What did I say I wanted that's gone quiet?"
- Full list of pending intentions with days-quiet, reusing existing drift computation (read path only). Sorted by days quiet. Resolve/dismiss reuse existing endpoints + events.
- Self-judgment guard is pick-time/Home-only by spec; Journal listing of identity-class intentions is existing behavior — preserve exactly.

### 4. Entity communities (DEFERRED — do not build)
- Louvain/Leiden clustering on entity co-mention graph; shares mechanism with docs/designs/intention-clustering.md. Build the shared utility once, when either triggers.

### 5. Surprise edges (DEFERRED — do not build)
- Cross-community co-occurrences; EXTRACTED vs INFERRED confidence labels (idea from graphify). Requires eval of INFERRED links first.

## Explicitly NOT in scope, ever, under this doc
- Home surface changes. Embedding graphify itself (wrong runtime/domain; MindGraph's evaled Gemini/LangGraph extraction stays). New extraction pipeline work. Streaks, scores, balance targets, compliance framing.

## Open questions (answer with real-user data)
1. Does anyone open the Graph page? (`graph_viewed` event added with Patterns v1.)
2. Which components do trial users ask for unprompted?
3. Minimum entries per user before each component is non-embarrassing (est.: Attention Mix ~10, communities ~20, gravity ~15, surprises ~25 — validate against founder account).
