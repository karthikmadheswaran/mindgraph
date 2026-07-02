# Intention clustering + project-linked drifts (DEFERRED — design only)

Status: do NOT build. Trigger: a real user (not founder) crosses ~15 pending
intentions, OR a project-filtered drift view is requested by a paying user.
Founder's own 50-intention pool is handled by one-time bulk dismiss, not code.

## Problem
Extraction creates near-duplicate intentions ("start working out" / "get gym
membership" / "go to the gym" = 3 rows for 1 intention), which corrupts
reference_count and the Home picker's mention-weighting. Separately, drifts
cannot be filtered by project (active or archived).

## Design A — incremental clustering at extraction time
On each new extracted intention:
1. Embed intention text (existing pgvector setup).
2. Cosine vs user's PENDING intentions:
   - sim >= 0.88  -> merge: reference_count += 1, last_mentioned = now,
     append source entry_id to mentions; keep earliest first_stated; update
     canonical phrasing to most recent mention.
   - 0.75 <= sim < 0.88 -> borderline: one flash-lite call, "same underlying
     intention? yes/no" -> merge or insert.
   - sim < 0.75 -> insert new row.
Rationale: short phrases embed treacherously ("go to the gym" vs "quit the
gym" are cosine-close, semantically opposite). Embeddings propose, model
confirms, only on the narrow band.
Retroactive pass for existing pools: embed all pending, greedy-merge above
threshold.
Eval (RED-first, per house rules): hand-label clusters in the founder's real
50-intention pool BEFORE choosing thresholds; N>=3 runs, variance bands;
confirm current dup rate first, then tune 0.88/0.75 against labels.

## Design B — project linkage, zero new LLM calls
New join table: intention_projects (intention_id, project_id, source_entry_id).
Populate by joining intention -> source entry -> that entry's already-extracted
project entities. Merged intentions carry the union of their mentions' links.
Fallback for unlinked intentions: embed intention text vs project names, link
only above a high threshold, else leave unlinked (life drifts legitimately
have no project).
API: GET /intentions/drift?project_id=...&include_archived=true
UI: Project filter chip in the Journal Intentions view (active + archived);
reverse view on project pages ("quiet intentions for this project").
Bonus: project-linked ~= dev/build, unlinked ~= life -> feeds the Home
picker's dev-vs-life stage with no classifier.

## Interaction with Home drift picker
Clustering makes reference_count truthful (mention-weighting improves for
free). Self-judgment guard (never surface identity-judgment intentions like
"not be a useless guy") is a picker-side hard requirement and is NOT part of
this deferred item — it ships with the picker.
