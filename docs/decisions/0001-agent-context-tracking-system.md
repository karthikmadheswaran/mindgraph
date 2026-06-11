# ADR-0001: Agent-Context Tracking System for MindGraph

- **Status:** ACCEPTED 2026-06-10 — System B as scoped; Phase 2 includes scripted backfill of the 95 historical changelog entries (approver chose backfill over freeze-and-link)
- **Date:** 2026-06-10
- **Decides:** where project state, history, and agent context live; how they stay true to code; how every change records what/why/alternatives/outcome
- **Inputs read:** Notion Status Hub (`3429402f…`), Notion Changelog (`3449402f…`), repo root, README, `.claude/`, git history (181 commits since 2026-03-23)

> **Why this document lives here (in the repo, not Notion):** it is a decision about repo-adjacent infrastructure, it must be versioned alongside the thing it governs, and it is itself the first instance of the decision-record convention it proposes. A Notion copy would immediately re-create the duplication problem this ADR exists to kill. The public repo also makes it a portfolio artifact: a visible, dated record of context-engineering reasoning. (Strategy-sensitive content — pricing, consulting plans — is deliberately excluded and stays in Notion.)

---

## 1. Findings: the current system, measured

The loop today: read Notion Status Hub → draft Claude Code prompt → execute → paste results back → update Status Hub + Changelog (+ summary + banner + tables).

| Artifact | Size | Role today | Condition |
|---|---|---|---|
| Notion **Status Hub** | ~72K chars ≈ **18K tokens** | "read this first" boot context | ~9 content types interleaved; multiple internal contradictions |
| Notion **Changelog** page | ~93K chars ≈ **23K tokens** | full history, 95 entries / 36 days (01/04 → 10/06) | append requires fetching the whole page first (its own instructions say so) |
| Notion **Evaluation Log**, Action Plan, daily logs, roadmaps | — | strategy + specialized history | daily logs dead since 10/04 but instructions still mandate them |
| **README.md** | ~12K chars ≈ 3K tokens | public portfolio | metrics frozen at Phase-2 values |
| **git log** | 181 commits | the actual record | every commit already `[Category] subject`; recent bodies are full decision records (what/why/root-cause/alternatives/verification) |
| `.claude/` in repo | empty | — | no CLAUDE.md, no AGENTS.md, no skills |

### Measured drift (one fact, three values)

| Claim | README | Status Hub | Actual code |
|---|---|---|---|
| API endpoint count | **15** (architecture diagram) | **34** (endpoints table) | **36** routes in `app/main.py` |
| Test count | 225 | 225 (heading) and **229** (same page, table total) | derivable via `pytest --collect-only -q` |

Other observed drift: two "Current Focus" sections (one frozen at 29 April, one undated with items marked Open that other sections record as fixed in May/June); "Today/Dashboard NOT pushed yet" vs "Dashboard polish shipped 01/05" on the same page; Agent Handoff Summary still sequencing "Paddle billing" though Razorpay superseded Paddle; prompt version cited as v13.1, v13.2, and v13.4 in different sections.

### Root-cause diagnosis (not "Notion is bad")

1. **Write amplification.** One change is recorded in up to **six places**: commit message, Changelog child page, 5-entry summary, "Last updated" banner blob, one or more status tables, sometimes README. Drift is guaranteed at fan-out > 1 unless every write beyond the first is mechanical.
2. **Snapshots restating history.** The "✅ Complete" status grids re-encode what git already proves, in a form that rots. *State is a cache of history* — and this cache has no invalidation.
3. **Process-as-prose.** The update ritual exists as imperative prose inside a Notion page, re-executed from memory by each agent session. Prose process drifts exactly like prose state (daily logs died; their instructions survive).
4. **No archival line.** Append-at-top with no hot/cold boundary → 18K- and 23K-token always-read pages.
5. **Wrong-substrate placement.** Code-true facts (endpoint inventory, test counts, thresholds) live where code cannot reach them.

The substrate question is secondary. **Any design that leaves >1 manual write per fact will drift regardless of where the writes land.**

---

## 2. Design space

### 2.1 Decomposition — content types are not one thing

Each row has a different change velocity and a different *ground truth*, which dictates its natural home:

| # | Content type | Velocity | Ground truth | Examples |
|---|---|---|---|---|
| C1 | Agent behavioral rules | slow | user intent | the ⛔ Do-Nots |
| C2 | Architecture constants | slow | **code** (with tuning provenance) | thresholds 0.62/0.64, model names |
| C3 | Stable references | ~static | external | URLs, Notion page IDs |
| C4 | Code-derivable inventories | medium | **code** | endpoint table, test counts |
| C5 | Status snapshots | fast-rotting | code + reality | "✅ Complete" grids |
| C6 | Current focus / task queue | fast | user's head | P1/P2 lists |
| C7 | Known-broken registry | medium | reality | open bugs, observation windows |
| C8 | History / changelog | append-only | events | 95 entries |
| C9 | Decision provenance | append-only | reasoning | commit bodies (already exist) |
| C10 | Eval history | append-only | eval runs | Evaluation Log |
| C11 | Strategy / roadmap | slow | user's head; **private** | pricing, niche, consulting |

### 2.2 Substrate options per part

**Boot context (C1–C3, what an agent always reads):**
- (a) Notion page (status quo) — needs an MCP fetch per session; drifts from code; 18K tokens today.
- (b) **Repo `CLAUDE.md`, slim (~1–1.5K tokens)** — auto-loaded by Claude Code at zero ceremony; versioned; reviewable in diffs; next-to-code.
- (c) `AGENTS.md` (cross-vendor standard) with `CLAUDE.md` importing it — relevant because a `.gemini/` dir exists in the repo; cheap rename later, not a now-decision.
- (d) Path-scoped nested files (`evals/CLAUDE.md`, `app/CLAUDE.md`) — progressive disclosure by directory; only worth it when the root file outgrows ~2K tokens. Deferred.

**Current state (C5–C7):**
- (a) Slimmed Status Hub section — keeps reading habit; still needs fetch + manual prune.
- (b) **Repo `docs/STATE.md`** (≤1.5K tokens): Now / Next / Known-broken. Pruned at session close — fixed items get *deleted* (history already holds them), not struck through. Strikethrough accumulation is how the current page got to 18K.
- (c) Notion DB with status columns — queryable, but splits state from code and adds fetch latency for the highest-frequency read.
- (d) GitHub Issues — a fourth surface; not in the user's loop; rejected.
- On C5 specifically (status grids): **the recommendation is deletion, not relocation.** At solo-project scale, "current focus + known-broken + git history" fully determines status. The grids are negative-value: they cost maintenance and actively mislead when stale.

**Changelog (C8):**
- (a) Notion page with toggles (status quo) — 23K-token read to append one entry; not queryable; mobile-friendly.
- (b) **Notion database** — one row per change (Date, Category select, Title, What, Impact, Commit URL, Decision link). Append = create-row, **no page fetch**. Filterable views by category/month. The Status Hub's "Latest 5" becomes a **linked DB view** — the 5-entry summary ritual disappears as a category of work, not as a discipline to remember.
- (c) Repo `CHANGELOG.md` (Keep-a-Changelog) — versioned, but manually duplicates git log; on a public repo it also can't carry anything sensitive.
- (d) **Generated from git** — commits already follow `[Category] subject`; a script could emit the changelog. Elegant, but: non-code events (e.g. "Razorpay KYC approved" — 3 such entries exist) have no commit; `--allow-empty` commits for life events is substrate abuse; and the user's reading surface is Notion/mobile, not git log.
- (e) **Hybrid (chosen):** git canonical for code changes (the detail layer); one Notion DB row per change as the human-facing index, written mechanically at close-out by distilling the commit subject/body. Fan-out = 2, but the second write is scripted, not remembered.

**Decision provenance (C9):**
- (a) **Commit bodies** — already excellent in this repo; attached to the change; immutable; free. Canonical for tactical decisions.
- (b) **ADR-lite files** (`docs/decisions/NNNN-*.md`) — for the handful of architectural/cross-cutting decisions per year (provider switches, threshold philosophy, this system itself). Public = portfolio signal.
- (c) Notion Decision rows — for strategy decisions with no commit and/or private content (pricing, niche). Same changelog DB, `Category = Decision`.
- (d) PR descriptions — workflow commits mostly straight to main; rejected.
- Chosen: **three tiers by weight and privacy** — commit body (every change) → ADR (architectural) → Notion Decision row (strategic/private).

**Code-derivable inventories (C4):**
- (a) Hand-maintained tables — measured failure (15 vs 34 vs 36).
- (b) Script-generated sections (marker-bounded blocks in README regenerated from `app.routes` / `pytest --collect-only` / latest `evals/results/*.json`).
- (c) **Don't track; derive on demand** — CLAUDE.md documents the one-liner commands. Zero maintenance, zero drift, costs one command per use.
- Chosen: (c) for agent consumption; (b) later, only for the README's public-facing metrics block.

**Eval provenance (C10):** the Status Hub already specifies the right design as a P2 item — SHA-stamped JSON into `evals/results/` (committed) + `evals/compare.py`. This ADR adopts it unchanged and wires changelog rows to link result files. The Notion Evaluation Log stops growing (kept as archive); narrative interpretation goes in the changelog row / commit body.

**Strategy (C11):** stays in Notion, untouched. It is private (the repo is public), it is the user's reading/thinking surface, and it is not code-true so repo storage buys nothing.

**Sync mechanism:**
- (a) Prose instructions (status quo) — empirically failed.
- (b) **A close-out skill** (`.claude/skills/wrap/`) — one command at session end: prompts for/derives the changelog row from the session's commits, updates STATE.md (add/prune), creates the Notion DB row, touches the Status Hub banner one-liner. Process-as-code: versioned, diffable, improvable.
- (c) CI/git hooks for drift checks and generated blocks — Phase-2 automation, additive.
- (d) Scheduled weekly rollup session (cron) — optional later for monthly archive rollups.

### 2.3 Cross-part candidate systems

- **System A — "Notion, structured."** Changelog → Notion DB; Status Hub slimmed; everything else stays Notion. Minimal habit change; drift on code-true facts remains (they still live only in Notion); portfolio-invisible.
- **System B — "Repo-canonical hybrid"** *(recommended)*. Code-true + agent-boot + current-state in repo (CLAUDE.md, STATE.md, ADRs, eval JSONs); history human-index in a Notion DB; strategy stays Notion; one close-out skill does all secondary writes; Status Hub becomes a thin dashboard of links + linked DB views.
- **System C — "All-repo, Notion strategy-only."** CHANGELOG.md generated from git; no Notion changelog. Maximum purity; loses the mobile/at-a-glance reading loop, awkward for non-code events, and the public repo forces strategy back into Notion anyway — so it's hybrid with worse ergonomics.
- **System D — "Git-maximalist."** Structured trailers (`Category:`, `Impact:`, `Decision:`), tags as releases, changelog = `git log --grep`. Provenance physically attached to changes; zero drift. Worst loop fit: unreadable on mobile, hostile to non-code events, trailer discipline on every commit. Harvested for parts (commit conventions), rejected as a system.

---

## 3. Comparison

Scores 1–5 (5 = best). Justifications below the table.

| Criterion | A: Notion-structured | B: Repo-canonical hybrid | C: All-repo | D: Git-max |
|---|---|---|---|---|
| Always-read token cost | 3 | **5** | 5 | 4 |
| Retrieval efficiency | 4 | **5** | 4 | 3 |
| Drift resistance | 2 | **4** | 5 | 5 |
| Maintenance burden | 3 | **4** | 3 | 2 |
| Loop fit (Notion → Code → Notion) | **5** | 4 | 2 | 1 |
| Portfolio signal | 1 | **5** | 4 | 3 |
| Migration cost | **4** | 3 | 2 | 2 |
| **Total (unweighted)** | 22 | **30** | 25 | 20 |

- **Token cost:** A still requires an MCP fetch of a (slimmed) hub each session (~2–3K tokens + latency); B/C auto-load ~1.2K from CLAUDE.md with zero ceremony; D still needs a boot file.
- **Retrieval:** B layers three good fetch-on-demand surfaces (filesystem for code-truth, DB views for history, `git show` for deep detail). A's DB is queryable but prose pages stay fuzzy. D's `git log --grep` is powerful but opaque and desktop-bound.
- **Drift:** C/D maximal (single substrate, next-to-code). B near-maximal: code-true facts can no longer drift (they live in the repo or are derived on demand); residual risk is the repo→Notion mirror, which is mechanical (skill-written) and low-stakes (history index, not state). A keeps hand-synced code facts in Notion — the measured failure mode.
- **Maintenance:** B = run one skill at close-out; A = same rituals, still manual; C = manual changelog upkeep or script babysitting + "where does this go?" friction for non-code events; D = per-commit trailer discipline (highest friction, applied at the worst moment).
- **Loop fit:** A preserves the exact current habit. B keeps Notion as the *reading* surface (status dashboard + changelog views on phone) while moving the *boot* surface into the tool that executes; the prompt-drafting step gets cheaper (no 18K-token paste-in). C/D remove the reading surface the user demonstrably uses.
- **Portfolio:** B exposes public ADRs, a skills directory, SHA-stamped eval provenance, and a deliberately minimal CLAUDE.md — context engineering made visible. A is invisible (private workspace). C visible but less articulated; D visible only to git archaeologists.
- **Migration:** A is mostly one Notion restructure. B is phased but each phase is small and independently shippable. C/D require changing where *everything* lives plus habit change.

**Uncertainty flags:** token estimates are chars÷4 approximations. Notion-MCP database-row creation is assumed reliable (used widely, but verify in Phase 2 before deleting anything). Scores are unweighted; if the user weights "loop fit" 2× and "portfolio" 0, A closes to 27 vs B's 29 — B still wins, but it's closer; stating this so the weighting is an explicit choice, not smuggled in.

---

## 4. Recommendation — System B, end to end

**One sentence:** put every code-true and agent-boot fact in the repo where it cannot drift, keep Notion as the human dashboard and the single human-facing history index (a database, not a page), generate or derive everything derivable, and make the one remaining cross-substrate write a scripted close-out step instead of a remembered ritual.

### Component map

| Component | Lives | Size budget | Written by | Read when |
|---|---|---|---|---|
| `CLAUDE.md` | repo root | ≤1.5K tokens | human + agent, rarely | **always** (auto-loaded) |
| `docs/STATE.md` | repo | ≤1.5K tokens | close-out skill | start of work session |
| `docs/decisions/NNNN-*.md` (ADRs) | repo | ~½ page each | agent at decision time | on demand |
| Commit messages (`[Category] subject` + decision-record body) | git | — | already the norm | on demand (`git show`) |
| `evals/results/*.json` + `evals/compare.py` | repo | — | eval harness | on demand |
| **Changelog DB** | Notion database | 1 row/change | close-out skill | human reading; agent queries by column |
| Status Hub (rebuilt) | Notion page | ~1–2K tokens | close-out skill touches 1 line | human at-a-glance; mobile |
| Strategy pages | Notion | — | human | agent fetches only when task touches strategy |
| Auto-memory (`~/.claude/.../memory/`) | Claude Code | — | agent | cross-session, personal/env facts (e.g. GCP SA names) — already working; unchanged |

### CLAUDE.md contents (and *only* these)

1. One-paragraph project identity + deployed URLs.
2. Repo map (one line per top-level dir).
3. The ⛔ Do-Nots (C1) — ported from the Status Hub, pruned of stale ones.
4. Architecture constants table (C2) with value + tuning date + commit SHA.
5. **Derive-on-demand commands** (C4): route inventory, test counts, latest eval scores.
6. **Pointer table**: STATE.md, decisions/, changelog DB ID, Status Hub ID, strategy page IDs — with one-line "fetch when…" guidance per pointer.
7. Close-out contract: "before ending a work session, run `/wrap`."

Explicitly *not* in CLAUDE.md: status grids, history, eval narratives, strategy. That is what keeps it ≤1.5K tokens. This deliberately follows the progressive-disclosure principle from the AGENTS.md/Skills conventions: the always-read layer is an index, not an encyclopedia. (Divergence from convention, recorded: skipping nested per-directory CLAUDE.md files for now — repo is small enough that one root file + pointers wins; revisit if root exceeds budget.)

### STATE.md shape

```markdown
# STATE — updated 2026-06-10 (commit e2f8a4a)
## Now (≤3 items)
## Next (≤5 items, ordered)
## Known broken / degraded (open only — fixed items are DELETED, history holds them)
## Watching (observation windows with review dates, e.g. Vivek-class advisory → review 09/06)
```

### Changelog DB schema (Notion)

| Property | Type | Notes |
|---|---|---|
| Title | title | `[Category] short description` (mirrors commit subject) |
| Date | date | |
| Category | select | Launch / Feature / Pipeline / Eval / Infra / Frontend / Tests / Docs / Strategy / Bug Fix / Decision |
| What | text | 1–3 sentences |
| Impact | text | 1–2 sentences |
| Commit | url | GitHub commit link (empty for non-code events) |
| Decision | url | ADR file or Notion decision row, when applicable |
| Eval delta | text | optional, e.g. "F1 0.364 → 0.818", link to results JSON |

Status Hub embeds two linked views: "Latest 10" and "By category". **No summary is ever manually re-typed.**

### The decision log going forward (template — deliverable #6)

Tier 1 — **every change**, in the commit body (already current practice, now codified):

```text
[Category] What changed, in one subject line

WHY: the problem / trigger, 1–3 sentences.
ALTERNATIVES: what else was considered and why it lost (1 line each; "none obvious" is allowed but must be typed).
OUTCOME: verification — eval delta, deploy check, test results.
Decision: docs/decisions/NNNN (only when an ADR exists)
```

Tier 2 — **architectural decisions** (~monthly at most), `docs/decisions/NNNN-slug.md`:

```markdown
# ADR-NNNN: Title
- Status: PROPOSED | ACCEPTED | SUPERSEDED-BY-NNNN   - Date:   - Commits:
## Context (what forced a choice)
## Options considered (each: 1–3 lines + why rejected)
## Decision
## Consequences (incl. what becomes harder)
```

Tier 3 — **strategy decisions** (no commit, possibly private): a Changelog DB row with `Category = Decision`, What = the decision, Impact = why + alternative considered.

### The close-out skill (`/wrap`)

At session end, one invocation: reads session commits → drafts changelog row(s) (subject → Title, body → What/Impact/Eval-delta) → shows the user for a yes/edit → writes the Notion row → updates STATE.md (new known-broken in, fixed items out, "Now/Next" adjusted) → updates the Status Hub "Last updated" one-liner. The write fan-out beyond git is thereby 1 scripted step. The skill file is versioned in `.claude/skills/wrap/` — when the process needs to change, the *skill* is edited, not nine agents' memories.

### How the parts interact (the loop, after)

1. **Session start:** Claude Code auto-loads CLAUDE.md (~1.5K). Agent reads STATE.md if doing project work (~1.5K). Total boot ≈ 3K tokens vs ~18K+ today, with zero manual pasting.
2. **During work:** detail fetched on demand — `git show` for past changes, ADRs for architecture, Notion only when strategy/history context is genuinely needed.
3. **Session end:** `/wrap`.
4. **Human reading (phone/anywhere):** Status Hub dashboard + changelog DB views — same habit, now backed by something that can't silently rot, because nothing on it is hand-maintained state.

---

## 5. Runner-ups and why they lost (on record)

- **System A (Notion, structured)** — lost on *drift resistance* (code-true facts would still be hand-synced into Notion; the 15/34/36 endpoint discrepancy is the empirical refutation) and *portfolio signal* (private workspace, invisible). It is the right choice only if repo files are unacceptable for some reason; nothing found suggests that.
- **System C (all-repo)** — lost on *loop fit*: it deletes the user's actual reading surface (Notion, mobile) and handles non-code events (3 of 95 changelog entries, incl. Razorpay KYC) awkwardly. The public-repo privacy constraint forces strategy back into Notion anyway, so C converges to B with worse ergonomics. Would become right if the Notion habit is abandoned later — B leaves that door open (drop the DB mirror, keep everything else).
- **System D (git-maximalist)** — lost on *maintenance burden at the worst moment* (trailer discipline per commit) and *loop fit* (git log is not a human dashboard). Its best ideas — structured subjects, decision-record bodies — are already practice here and are codified in Tier 1 above.
- **Status quo** — rejected on measurement: 41K tokens of always-read-ish context, fan-out 6, and multiple live contradictions after only 10 weeks of history.

## 6. Migration plan (sequenced; nothing here is done yet)

| Phase | What | Effort | Reversible? |
|---|---|---|---|
| 0 | Approve direction (this ADR → ACCEPTED, possibly with edits) | 10 min | — |
| 1 | Write `CLAUDE.md` + `docs/STATE.md` (port Do-Nots, constants, pointers; build Now/Next/Known-broken from Status Hub *with stale items resolved against git*) | 2–3 h | fully (files are additive; Notion untouched) |
| 2 | Create Changelog **database** in Notion; new entries go there from day 1. **Scripted backfill** of all 95 historical entries (parse the frozen page's day/item toggles → one DB row each; spot-check ~10 rows against the source). Old page then frozen with a "see DB" banner — kept as the import source of record, never deleted. *(Approved 2026-06-10: backfill chosen over freeze-and-link.)* | 2–4 h | fully (old page untouched) |
| 3 | Rebuild Status Hub as a thin dashboard: banner one-liner, linked DB views, Deployed URLs, links to STATE.md/ADRs/strategy. Move *everything else* (status grids, endpoint/test tables, old banner blob, daily-log instructions) to a child page `Archive — pre-2026-06` — moved, not deleted. Formally retire the daily-log workflow. | 1–2 h | yes (archive child page preserves all content) |
| 4 | Build `.claude/skills/wrap/` close-out skill; run it for 2–3 real sessions; tune. | 1–2 h | fully |
| 5 | Eval provenance: implement the already-planned `evals/results/` + `compare.py` (P2 item adopted as-is); wire Eval-delta links into changelog rows; freeze Notion Evaluation Log. | 2–4 h | mostly (results JSONs additive) |
| 6 (optional, later) | README generated-metrics block; CI drift check (route/test counts); monthly rollup of DB → archive; `AGENTS.md` standard adoption for the `.gemini` toolchain | 2–4 h | yes |

**One-way doors:** none until Phase 3, and even Phase 3 archives rather than deletes. The only genuinely one-way step would be deleting the old changelog page — which this plan never does.
**Total to full operation:** ~7–12 h across phases 1–5, each independently shippable and valuable on its own (Phase 1 alone removes the 18K-token boot cost).

## 7. Things that reframed the question (surfaced per mandate)

1. **It's a write-amplification problem, not a storage problem.** Fan-out 6 → drift at any substrate. The design's real move is fan-out → 1 manual write (the commit, already habitual) + 1 scripted write.
2. **~70% of the proposed system already exists.** The commit discipline (structured subjects, decision-record bodies) is the provenance layer; eval provenance was already designed in the Known-Broken list. This ADR mostly *deletes* work (status grids, summary rituals, banner blobs) rather than adding it.
3. **Status grids are a cache with no invalidation** — at solo scale, delete them; don't relocate them.
4. **Process must be executable** (a skill), not prose. The daily-log death is the proof: prose process has no enforcement and no versioning.
5. **The public repo is a hard constraint** that by itself rules out all-repo purity (strategy must stay private) — the hybrid isn't a compromise, it's forced.
6. **The meta-system is itself portfolio material.** Public ADRs + a skills directory + SHA-stamped eval provenance demonstrate context engineering more credibly than any private tracker could.

## 8. Open questions — resolved at approval (2026-06-10)

1. ~~System B vs B-minus-DB vs A?~~ → **System B as scoped.**
2. ~~Backfill vs freeze-and-link?~~ → **Scripted backfill** of all 95 entries (Phase 2 updated above).
3. `CLAUDE.md` vs `AGENTS.md`: not raised at approval → default stands (**CLAUDE.md canonical**; AGENTS.md shim deferred to Phase 6, revisit if Gemini-CLI sessions become routine).
4. Criteria weighting: not challenged at approval → portfolio-signal weighting stands as scored.
