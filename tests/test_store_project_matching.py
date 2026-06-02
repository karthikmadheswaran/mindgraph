"""
Contract test for project-name entity matching in resolve_entities.

History: this test previously scraped redirect_stdout for marker strings
("EXACT MATCH:", "[store] normalized project candidates", ...) while the
implementation had moved to logger.info with different wording — so every
flag read False and F1 was 0.0 across all 24 cases, with exit 0. It was
vacuous (see investigation 2026-06-01).

Now it asserts on database state instead of log strings: after running
resolve_entities for each case, we check the entity-count delta and which
seed's mention_count got bumped. That contract survives log-wording and
log-channel refactors.

Isolation: a dedicated, freshly-created user holds ONLY the 8 canonical
seed projects, reset before every case. Seeds are inserted without
embeddings, so the match_entities semantic path returns nothing and the
outcome is fully determined by the exact + normalized string matching that
this test is about. (resolve_entities' semantic fallback is exercised by
the live-pipeline evals, not here, because it isn't deterministic.)
"""

import asyncio
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

import pytest

from app.nodes.store import (
    supabase,
    resolve_entities,
    get_match_key,
)

RUN_ID = f"projmatch-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}"
TEST_PREFIX = f"__STORE_TEST__::{RUN_ID}::"


# The canonical projects seeded into the dedicated test user before each case.
SEED_PROJECTS = [
    f"{TEST_PREFIX}MindGraph",
    f"{TEST_PREFIX}AB Test",
    f"{TEST_PREFIX}C++ Notes",
    f"{TEST_PREFIX}Project X-2",
    f"{TEST_PREFIX}Node.js Migration",
    f"{TEST_PREFIX}Daily Journal",
    f"{TEST_PREFIX}Re-Work",
    f"{TEST_PREFIX}Alpha_Beta",
]


@dataclass
class ProjectMatchCase:
    case_id: str
    incoming_name: str
    summary: str
    expected_exact_match: bool
    expected_normalized_candidate: bool
    # expected_merge: does this incoming name resolve onto an EXISTING seed
    # (True → no new entity, a seed's mention_count is bumped) or become a
    # NEW entity (False → entity count grows by one)? Derived from the exact +
    # normalized matching contract against the 8 seeds, with the semantic path
    # inert (seeds have no embeddings). This is the field the assertions gate on.
    expected_merge: bool
    family: str
    difficulty: str
    note: str


# 24 cases preserved verbatim from the original suite (inputs, families,
# difficulties, notes, and the original expectation flags are unchanged). The
# expected_merge column is the DB-observable contract derived for each case.
#
# Note on T20 ("Mind Graphs"): its original expected_normalized_candidate=True
# only holds under ordered accumulation where a prior case created a
# "MindGraphs" entity for it to match. Under per-case isolation it correctly
# becomes a NEW entity, so expected_merge is False. The original flag is kept
# verbatim for traceability; assertions gate on expected_merge.
TEST_CASES = [
    # Easy spacing / case / hyphen variants that SHOULD merge onto a seed
    ProjectMatchCase("T01", f"{TEST_PREFIX}Mind Graph", "Worked on login and dashboard for the app", False, True,  True,  "spacing_variant", "easy",   "space split"),
    ProjectMatchCase("T02", f"{TEST_PREFIX}mindgraph", "Refined onboarding flow",                      True,  False, True,  "case_variant",    "easy",   "exact ilike should catch"),
    ProjectMatchCase("T03", f"{TEST_PREFIX}MINDGRAPH", "Fixed journal insights bug",                   True,  False, True,  "case_variant",    "easy",   "exact ilike should catch"),
    ProjectMatchCase("T04", f"{TEST_PREFIX}Mind-Graph", "Shipped auth work",                           False, True,  True,  "hyphen_variant",  "easy",   "hyphen variant"),
    ProjectMatchCase("T05", f"{TEST_PREFIX}Mind_Graph", "Improved graph card",                         False, True,  True,  "underscore_var",  "easy",   "underscore variant"),
    ProjectMatchCase("T06", f"  {TEST_PREFIX}MindGraph  ", "Whitespace around name",                   True,  False, True,  "trim_variant",    "easy",   "strip then ilike"),

    # Similar patterns on other seeded projects
    ProjectMatchCase("T07", f"{TEST_PREFIX}AB-Test", "Experiment design and rollout",                  False, True,  True,  "hyphen_variant",  "easy",   "AB Test hyphenated"),
    ProjectMatchCase("T08", f"{TEST_PREFIX}AB_Test", "Reviewed experiment results",                    False, True,  True,  "underscore_var",  "easy",   "AB Test underscored"),
    ProjectMatchCase("T09", f"{TEST_PREFIX}Project X2", "Planning next release",                       False, True,  True,  "separator_loss",  "medium", "x-2 vs x2"),
    ProjectMatchCase("T10", f"{TEST_PREFIX}Node JS Migration", "Upgraded backend stack",               False, True,  True,  "punct_variant",   "medium", "node.js vs node js"),
    ProjectMatchCase("T11", f"{TEST_PREFIX}Daily-Journal", "UI polish for the writing flow",           False, True,  True,  "hyphen_variant",  "easy",   "daily journal hyphenated"),
    ProjectMatchCase("T12", f"{TEST_PREFIX}Alpha Beta", "Worked on edge cases",                        False, True,  True,  "separator_loss",  "easy",   "alpha_beta vs alpha beta"),

    # Risky collisions: candidate generation may still fire, which is why we do NOT auto-merge on normalize alone
    ProjectMatchCase("T13", f"{TEST_PREFIX}C Notes", "Took notes about the C language",                False, False, False, "risky_collision", "hard",   "should ideally not candidate-match C++ Notes"),
    ProjectMatchCase("T14", f"{TEST_PREFIX}Rework", "Restructured tasks and docs",                     False, True,  True,  "risky_collision", "hard",   "re-work vs rework"),
    ProjectMatchCase("T15", f"{TEST_PREFIX}ProjectX2", "Backend cleanup",                              False, True,  True,  "risky_collision", "hard",   "project x-2 vs projectx2"),

    # Clearly different names: should not merge, should become new entities
    ProjectMatchCase("T16", f"{TEST_PREFIX}Inspiral", "Medicine mention in health context",            False, False, False, "different_name",  "easy",   "should not look like a project variant"),
    ProjectMatchCase("T17", f"{TEST_PREFIX}Figma", "Design work in tool context",                      False, False, False, "different_name",  "easy",   "different project entirely"),
    ProjectMatchCase("T18", f"{TEST_PREFIX}Databricks", "Data engineering learning",                   False, False, False, "different_name",  "easy",   "different project entirely"),
    ProjectMatchCase("T19", f"{TEST_PREFIX}MindGraphs", "Pluralized weird variant",                    False, False, False, "different_name",  "medium", "extra trailing s"),
    ProjectMatchCase("T20", f"{TEST_PREFIX}Mind Graphs", "Pluralized with spaces",                     False, True,  False, "different_name",  "medium", "pluralized spaced"),
    ProjectMatchCase("T21", f"{TEST_PREFIX}Node Migration", "Migration work",                          False, False, False, "different_name",  "medium", "missing js"),
    ProjectMatchCase("T22", f"{TEST_PREFIX}AlphaBeta2", "Versioned suffix",                            False, False, False, "different_name",  "medium", "extra number suffix"),

    # Additional exact matches to prove baseline still works
    ProjectMatchCase("T23", f"{TEST_PREFIX}Daily Journal", "Journal product planning",                 True,  False, True,  "exact_match",     "easy",   "baseline exact"),
    ProjectMatchCase("T24", f"{TEST_PREFIX}Node.js Migration", "Backend migration tasks",              True,  False, True,  "exact_match",     "easy",   "baseline exact"),
]


def _count_entities(user_id: str) -> int:
    resp = (
        supabase.table("entities")
        .select("id", count="exact")
        .eq("user_id", user_id)
        .execute()
    )
    return resp.count or 0


def _fetch_entities(user_id: str) -> list[dict]:
    resp = (
        supabase.table("entities")
        .select("id, name, entity_type, mention_count")
        .eq("user_id", user_id)
        .order("name")
        .execute()
    )
    return resp.data or []


@pytest.fixture(scope="session")
def test_user():
    """A dedicated, throwaway user so the only project entities in play are the
    8 seeds — keeps the match_entities RPC from matching unrelated rows."""
    user_id = str(uuid.uuid4())
    email = f"store-test-{user_id[:8]}@mindgraph.test"
    supabase.table("users").insert({"id": user_id, "email": email}).execute()
    try:
        yield user_id
    finally:
        supabase.table("entities").delete().eq("user_id", user_id).execute()
        supabase.table("users").delete().eq("id", user_id).execute()


@pytest.fixture
def seeded(test_user):
    """Reset to exactly the 8 canonical seeds before each case (no embeddings,
    so the semantic path stays inert and outcomes are deterministic)."""
    supabase.table("entities").delete().eq("user_id", test_user).execute()
    now = datetime.now(timezone.utc).isoformat()
    rows = [
        {
            "user_id": test_user,
            "name": name,
            "entity_type": "project",
            "first_seen_at": now,
            "last_seen_at": now,
            "mention_count": 1,
            "context_summary": "seed fixture for store matching tests",
        }
        for name in SEED_PROJECTS
    ]
    supabase.table("entities").insert(rows).execute()
    return test_user


@pytest.mark.parametrize("case", TEST_CASES, ids=[c.case_id for c in TEST_CASES])
def test_project_match_contract(case: ProjectMatchCase, seeded: str):
    user_id = seeded

    pre_count = _count_entities(user_id)
    assert pre_count == len(SEED_PROJECTS), (
        f"{case.case_id}: seeding precondition failed "
        f"(expected {len(SEED_PROJECTS)} seeds, found {pre_count})"
    )

    result = asyncio.run(
        resolve_entities(
            [{"name": case.incoming_name, "type": "project"}],
            user_id,
            case.summary,
        )
    )
    assert len(result["ids"]) == 1, f"{case.case_id}: expected exactly one resolved id"

    post_count = _count_entities(user_id)
    after = _fetch_entities(user_id)
    bumped = [r for r in after if (r.get("mention_count") or 0) > 1]

    if case.expected_merge:
        assert post_count == pre_count, (
            f"{case.case_id} ({case.incoming_name!r}): expected merge onto an "
            f"existing seed (no new entity) but entity count changed "
            f"{pre_count} -> {post_count}"
        )
        assert len(bumped) == 1, (
            f"{case.case_id}: expected exactly one seed bumped, got "
            f"{[(b['name'], b['mention_count']) for b in bumped]}"
        )
        assert get_match_key(bumped[0]["name"], "project") == get_match_key(
            case.incoming_name, "project"
        ), (
            f"{case.case_id}: merged onto the wrong seed "
            f"({bumped[0]['name']!r} vs incoming {case.incoming_name!r})"
        )
    else:
        assert post_count == pre_count + 1, (
            f"{case.case_id} ({case.incoming_name!r}): expected a NEW entity "
            f"(count + 1) but entity count went {pre_count} -> {post_count}"
        )
        assert not bumped, (
            f"{case.case_id}: expected no seed bumped, but these were: "
            f"{[(b['name'], b['mention_count']) for b in bumped]}"
        )
