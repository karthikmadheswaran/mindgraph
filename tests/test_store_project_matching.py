import asyncio
import io
import sys
import uuid
from dataclasses import dataclass, asdict
from datetime import datetime
from contextlib import redirect_stdout
from typing import Optional

from app.nodes.store import (
    supabase,
    resolve_entities,
    get_match_key,
)

USER_ID = "0f5acdab-736f-4f44-883e-c897145a5ff2"
RUN_ID = f"projmatch-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}"
TEST_PREFIX = f"__STORE_TEST__::{RUN_ID}::"


# -----------------------------
# Seed fixtures
# -----------------------------
# These are the canonical projects we insert into your testing account.
# They are namespaced so cleanup is safe and won't touch your real data.
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
class TestCase:
    case_id: str
    incoming_name: str
    summary: str
    expected_exact_match: bool
    expected_normalized_candidate: bool
    family: str
    difficulty: str
    note: str


@dataclass
class CaseResult:
    case_id: str
    incoming_name: str
    family: str
    difficulty: str
    expected_exact_match: bool
    expected_normalized_candidate: bool
    exact_match_logged: bool
    normalized_candidate_logged: bool
    semantic_accepted_logged: bool
    semantic_rejected_logged: bool
    new_entity_logged: bool
    entity_count_before: int
    entity_count_after: int
    delta_entities: int
    matched_names_from_log: list[str]
    raw_log: str


TEST_CASES = [
    # Easy spacing / case / hyphen variants that SHOULD surface normalized candidates
    TestCase("T01", f"{TEST_PREFIX}Mind Graph", "Worked on login and dashboard for the app", False, True,  "spacing_variant", "easy",   "space split"),
    TestCase("T02", f"{TEST_PREFIX}mindgraph", "Refined onboarding flow",                      True,  False, "case_variant",    "easy",   "exact ilike should catch"),
    TestCase("T03", f"{TEST_PREFIX}MINDGRAPH", "Fixed journal insights bug",                   True,  False, "case_variant",    "easy",   "exact ilike should catch"),
    TestCase("T04", f"{TEST_PREFIX}Mind-Graph", "Shipped auth work",                           False, True,  "hyphen_variant",  "easy",   "hyphen variant"),
    TestCase("T05", f"{TEST_PREFIX}Mind_Graph", "Improved graph card",                         False, True,  "underscore_var",  "easy",   "underscore variant"),
    TestCase("T06", f"  {TEST_PREFIX}MindGraph  ", "Whitespace around name",                   True,  False, "trim_variant",    "easy",   "strip then ilike"),

    # Similar patterns on other seeded projects
    TestCase("T07", f"{TEST_PREFIX}AB-Test", "Experiment design and rollout",                  False, True,  "hyphen_variant",  "easy",   "AB Test hyphenated"),
    TestCase("T08", f"{TEST_PREFIX}AB_Test", "Reviewed experiment results",                    False, True,  "underscore_var",  "easy",   "AB Test underscored"),
    TestCase("T09", f"{TEST_PREFIX}Project X2", "Planning next release",                       False, True,  "separator_loss",  "medium", "x-2 vs x2"),
    TestCase("T10", f"{TEST_PREFIX}Node JS Migration", "Upgraded backend stack",               False, True,  "punct_variant",   "medium", "node.js vs node js"),
    TestCase("T11", f"{TEST_PREFIX}Daily-Journal", "UI polish for the writing flow",           False, True,  "hyphen_variant",  "easy",   "daily journal hyphenated"),
    TestCase("T12", f"{TEST_PREFIX}Alpha Beta", "Worked on edge cases",                        False, True,  "separator_loss",  "easy",   "alpha_beta vs alpha beta"),

    # Risky collisions: candidate generation may still fire, which is why we do NOT auto-merge on normalize alone
    TestCase("T13", f"{TEST_PREFIX}C Notes", "Took notes about the C language",                False, False, "risky_collision", "hard",   "should ideally not candidate-match C++ Notes"),
    TestCase("T14", f"{TEST_PREFIX}Rework", "Restructured tasks and docs",                     False, True,  "risky_collision", "hard",   "re-work vs rework"),
    TestCase("T15", f"{TEST_PREFIX}ProjectX2", "Backend cleanup",                              False, True,  "risky_collision", "hard",   "project x-2 vs projectx2"),

    # Clearly different names: should not exact-match, should not normalized-candidate match
    TestCase("T16", f"{TEST_PREFIX}Inspiral", "Medicine mention in health context",            False, False, "different_name",  "easy",   "should not look like a project variant"),
    TestCase("T17", f"{TEST_PREFIX}Figma", "Design work in tool context",                      False, False, "different_name",  "easy",   "different project entirely"),
    TestCase("T18", f"{TEST_PREFIX}Databricks", "Data engineering learning",                   False, False, "different_name",  "easy",   "different project entirely"),
    TestCase("T19", f"{TEST_PREFIX}MindGraphs", "Pluralized weird variant",                    False, False, "different_name",  "medium", "extra trailing s"),
    TestCase("T20", f"{TEST_PREFIX}Mind Graphs", "Pluralized with spaces",                     False, True, "different_name",  "medium", "pluralized spaced"),
    TestCase("T21", f"{TEST_PREFIX}Node Migration", "Migration work",                          False, False, "different_name",  "medium", "missing js"),
    TestCase("T22", f"{TEST_PREFIX}AlphaBeta2", "Versioned suffix",                            False, False, "different_name",  "medium", "extra number suffix"),

    # Additional exact matches to prove baseline still works
    TestCase("T23", f"{TEST_PREFIX}Daily Journal", "Journal product planning",                 True,  False, "exact_match",     "easy",   "baseline exact"),
    TestCase("T24", f"{TEST_PREFIX}Node.js Migration", "Backend migration tasks",              True,  False, "exact_match",     "easy",   "baseline exact"),
]


def count_test_entities() -> int:
    resp = (
        supabase.table("entities")
        .select("id", count="exact")
        .eq("user_id", USER_ID)
        .ilike("name", f"{TEST_PREFIX}%")
        .execute()
    )
    return resp.count or 0


def fetch_test_entities() -> list[dict]:
    resp = (
        supabase.table("entities")
        .select("id, name, entity_type, mention_count, first_seen_at, last_seen_at")
        .eq("user_id", USER_ID)
        .ilike("name", f"{TEST_PREFIX}%")
        .order("name")
        .execute()
    )
    return resp.data or []


def cleanup_test_entities() -> None:
    existing = fetch_test_entities()
    if not existing:
        return

    ids = [row["id"] for row in existing]

    # Delete relations and links first to avoid FK issues if your schema has them
    try:
        supabase.table("entry_entities").delete().in_("entity_id", ids).execute()
    except Exception:
        pass

    try:
        supabase.table("entity_relations").delete().or_(
            ",".join([f"source_entity_id.eq.{eid}" for eid in ids] + [f"target_entity_id.eq.{eid}" for eid in ids])
        ).execute()
    except Exception:
        pass

    # Finally delete entities
    supabase.table("entities").delete().in_("id", ids).execute()


def seed_projects() -> None:
    rows = []
    now = datetime.now().isoformat()

    for name in SEED_PROJECTS:
        rows.append(
            {
                "user_id": USER_ID,
                "name": name,
                "entity_type": "project",
                "first_seen_at": now,
                "last_seen_at": now,
                "mention_count": 1,
                "context_summary": "seed fixture for store matching tests",
            }
        )

    supabase.table("entities").insert(rows).execute()


def parse_log_for_normalized_candidates(log_text: str, incoming_name: str) -> list[str]:
    needle = f"[store] normalized project candidates for '{incoming_name}':"
    for line in log_text.splitlines():
        if needle in line:
            # crude but effective parser for printed Python list
            start = line.find("[", line.find(needle))
            end = line.rfind("]")
            if start != -1 and end != -1 and end > start:
                inner = line[start + 1:end].strip()
                if not inner:
                    return []
                return [part.strip().strip("'").strip('"') for part in inner.split(",")]
    return []


async def run_case(tc: TestCase) -> CaseResult:
    before = count_test_entities()

    payload = [{"name": tc.incoming_name, "type": "project"}]

    buf = io.StringIO()
    with redirect_stdout(buf):
        await resolve_entities(payload, USER_ID, tc.summary)

    log_text = buf.getvalue()
    after = count_test_entities()

    exact_match_logged = "EXACT " in log_text and " MATCH:" in log_text
    normalized_candidate_logged = "[store] normalized project candidates" in log_text
    semantic_accepted_logged = "SEMANTIC MATCH ACCEPTED" in log_text
    semantic_rejected_logged = "SEMANTIC MATCH REJECTED" in log_text
    new_entity_logged = "NEW ENTITY:" in log_text
    matched_names = parse_log_for_normalized_candidates(log_text, tc.incoming_name)

    return CaseResult(
        case_id=tc.case_id,
        incoming_name=tc.incoming_name,
        family=tc.family,
        difficulty=tc.difficulty,
        expected_exact_match=tc.expected_exact_match,
        expected_normalized_candidate=tc.expected_normalized_candidate,
        exact_match_logged=exact_match_logged,
        normalized_candidate_logged=normalized_candidate_logged,
        semantic_accepted_logged=semantic_accepted_logged,
        semantic_rejected_logged=semantic_rejected_logged,
        new_entity_logged=new_entity_logged,
        entity_count_before=before,
        entity_count_after=after,
        delta_entities=after - before,
        matched_names_from_log=matched_names,
        raw_log=log_text,
    )


def safe_div(n: float, d: float) -> float:
    return n / d if d else 0.0


def compute_boolean_metrics(results: list[CaseResult], expected_attr: str, actual_attr: str) -> dict:
    tp = fp = tn = fn = 0
    for r in results:
        expected = getattr(r, expected_attr)
        actual = getattr(r, actual_attr)
        if expected and actual:
            tp += 1
        elif not expected and actual:
            fp += 1
        elif not expected and not actual:
            tn += 1
        else:
            fn += 1

    precision = safe_div(tp, tp + fp)
    recall = safe_div(tp, tp + fn)
    f1 = safe_div(2 * precision * recall, precision + recall)
    accuracy = safe_div(tp + tn, tp + tn + fp + fn)

    return {
        "tp": tp,
        "fp": fp,
        "tn": tn,
        "fn": fn,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "accuracy": round(accuracy, 4),
    }


def print_case_table(results: list[CaseResult]) -> None:
    print("\n" + "=" * 140)
    print("CASE RESULTS")
    print("=" * 140)
    header = (
        f"{'ID':<5} {'difficulty':<8} {'family':<16} {'exp_exact':<10} {'act_exact':<10} "
        f"{'exp_norm':<9} {'act_norm':<9} {'sem_acc':<8} {'sem_rej':<8} {'new':<5} {'delta':<5} incoming"
    )
    print(header)
    print("-" * 140)

    for r in results:
        print(
            f"{r.case_id:<5} {r.difficulty:<8} {r.family:<16} "
            f"{str(r.expected_exact_match):<10} {str(r.exact_match_logged):<10} "
            f"{str(r.expected_normalized_candidate):<9} {str(r.normalized_candidate_logged):<9} "
            f"{str(r.semantic_accepted_logged):<8} {str(r.semantic_rejected_logged):<8} "
            f"{str(r.new_entity_logged):<5} {r.delta_entities:<5} {r.incoming_name}"
        )


def print_metrics(results: list[CaseResult]) -> None:
    print("\n" + "=" * 140)
    print("METRICS")
    print("=" * 140)

    exact_metrics = compute_boolean_metrics(results, "expected_exact_match", "exact_match_logged")
    norm_metrics = compute_boolean_metrics(results, "expected_normalized_candidate", "normalized_candidate_logged")

    print("\n1) Exact-match branch quality")
    print(exact_metrics)

    print("\n2) Normalized-candidate detection quality")
    print(norm_metrics)

    # Useful slice: only the cases where exact match was NOT expected
    non_exact = [r for r in results if not r.expected_exact_match]
    norm_metrics_non_exact = compute_boolean_metrics(non_exact, "expected_normalized_candidate", "normalized_candidate_logged")
    print("\n3) Normalized-candidate quality on non-exact cases only")
    print(norm_metrics_non_exact)

    risky = [r for r in results if r.family == "risky_collision"]
    if risky:
        risky_metrics = compute_boolean_metrics(risky, "expected_normalized_candidate", "normalized_candidate_logged")
        print("\n4) Risky-collision slice")
        print(risky_metrics)

    created = sum(1 for r in results if r.delta_entities > 0)
    sem_acc = sum(1 for r in results if r.semantic_accepted_logged)
    sem_rej = sum(1 for r in results if r.semantic_rejected_logged)
    print("\n5) Outcome counts")
    print(
        {
            "total_cases": len(results),
            "entities_created": created,
            "semantic_accepted": sem_acc,
            "semantic_rejected": sem_rej,
        }
    )


def print_failures(results: list[CaseResult]) -> None:
    print("\n" + "=" * 140)
    print("MISMATCHES / REVIEW REQUIRED")
    print("=" * 140)

    mismatches = [
        r for r in results
        if r.expected_exact_match != r.exact_match_logged
        or r.expected_normalized_candidate != r.normalized_candidate_logged
    ]

    if not mismatches:
        print("No expectation mismatches detected.")
        return

    for r in mismatches:
        print(f"\n[{r.case_id}] {r.incoming_name}")
        print(f"family={r.family}, difficulty={r.difficulty}")
        print(f"expected_exact={r.expected_exact_match}, actual_exact={r.exact_match_logged}")
        print(f"expected_norm={r.expected_normalized_candidate}, actual_norm={r.normalized_candidate_logged}")
        print(f"semantic_accepted={r.semantic_accepted_logged}, semantic_rejected={r.semantic_rejected_logged}, new_entity={r.new_entity_logged}, delta={r.delta_entities}")
        if r.matched_names_from_log:
            print(f"normalized_candidates={r.matched_names_from_log}")
        print("log:")
        print(r.raw_log.strip() or "<empty log>")


async def main() -> None:
    print(f"RUN_ID: {RUN_ID}")
    print(f"USER_ID: {USER_ID}")
    print("Cleaning previous namespaced test data...")
    cleanup_test_entities()

    print("Seeding canonical test projects...")
    seed_projects()

    seeded = fetch_test_entities()
    print(f"Seeded {len(seeded)} canonical projects:")
    for row in seeded:
        print(f"  - {row['name']}")

    print("\nRunning test cases...\n")
    results: list[CaseResult] = []
    for tc in TEST_CASES:
        result = await run_case(tc)
        results.append(result)
        print(
            f"{tc.case_id}: exact={result.exact_match_logged}, "
            f"norm={result.normalized_candidate_logged}, "
            f"sem_acc={result.semantic_accepted_logged}, "
            f"new={result.new_entity_logged}, delta={result.delta_entities}"
        )

    print_case_table(results)
    print_metrics(results)
    print_failures(results)

    print("\nFinal namespaced entities still present:")
    final_entities = fetch_test_entities()
    for row in final_entities:
        print(f"  - {row['name']} (mentions={row.get('mention_count')})")

    print("\nCleanup recommendation:")
    print("If you want to clean test-created rows now, uncomment the cleanup call below.")
    # cleanup_test_entities()


if __name__ == "__main__":
    asyncio.run(main())