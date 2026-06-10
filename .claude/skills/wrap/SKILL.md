---
name: wrap
description: Session close-out for MindGraph per ADR-0001. Distills this session's commits into Changelog DB rows, prunes docs/STATE.md, and updates the Status Hub banner. Run at the end of any session that changed code, docs, or project state ("wrap up", "close out the session", "log this session").
---

# /wrap — session close-out

Single scripted pass that replaces the old multi-page Notion update ritual. Fan-out
beyond git is exactly this skill. Defined by ADR-0001
(`docs/decisions/0001-agent-context-tracking-system.md`).

## Constants
- Changelog DB data source: `829daeda-7303-4f7d-b269-75b23adb53ff` (DB page `6d26883bed4946768cc1aa15ebe02809`)
- Status Hub page: `3429402f2bd281e1adb9f71e7f52ac05`
- Commit URL prefix: `https://github.com/karthikmadheswaran/mindgraph/commit/`
- The OLD changelog page `3449402f2bd281a6afbdfb0397d8f10b` is FROZEN — never write to it.

## Steps

1. **Gather the session's changes.**
   `git log --format="%h|%ad|%s" --date=short` for commits made this session (fall
   back to `--since=midnight` if session start is unclear). Cross-check the DB's
   newest rows (query the data source, sort Date desc, ~10 rows) so nothing is
   double-logged — a commit already linked in a row is done.
   Also collect **non-code events** from the session (account approvals, infra/IAM
   changes, strategy decisions) — they get rows with no Commit URL.

2. **Draft one row per changelog-worthy change.** Skip pure chores (gitignore noise,
   formatting). Shape (schema is authoritative in the data source):
   - `Title` — the commit subject verbatim (`[Category] description`)
   - `date:Date:start` — YYYY-MM-DD
   - `Category` — select: Launch/Feature/Pipeline/Eval/Infra/Backend/Frontend/Tests/Docs/Strategy/Bug/Bug Fix/Decision
   - `What` — ≤600 chars distilled from the commit body's substance
   - `Impact` — ≤400 chars: outcome/verification (the body's OUTCOME line)
   - `Commit` — URL (omit for non-code events)
   - `Eval delta` — only when a metric moved (e.g. `F1 0.364 → 0.818`)
   - `Decision` — URL of ADR file on GitHub, only when an ADR was created/changed

3. **Show the drafts to the user** in one compact message for confirm/edit. On
   confirmation, create the rows via Notion MCP `create-pages` against the data
   source ID above.

4. **Prune `docs/STATE.md`.** Items completed this session: DELETE them (history
   now lives in the DB + git — never strikethrough). New bugs/observations: add to
   Known broken or Watching. Adjust Now/Next if the session changed direction.
   Update the header line: `# STATE — updated YYYY-MM-DD (commit <head sha>)`.
   Keep the file ≤1.5K tokens; if it's growing, prune harder, don't summarize.

5. **Update the Status Hub banner** (one line only): replace the text of the
   `> 🕐 **Last updated: ...**` blockquote with date + one sentence naming the
   session's headline change. Use `update-page` `update_content` with the old
   banner text as `old_str`. Touch nothing else on the hub — summaries live in the
   linked DB views.

6. **Commit any STATE.md change** as part of the session's final commit (or a
   small `[Docs] STATE close-out` commit), following the commit template in
   CLAUDE.md (WHY / ALTERNATIVES / OUTCOME).

## Do not
- Do not write to the frozen changelog page or re-create per-day toggle structure.
- Do not re-type "latest N" summaries anywhere — the hub's linked views render those.
- Do not log to Google Calendar — the repo's post-commit hook already does that on
  every commit (`.git/hooks/post-commit`).
- Do not put strategy/pricing detail in DB rows beyond what a public observer could
  infer from the repo; deep strategy notes stay in the strategy pages.
