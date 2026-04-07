import asyncio
import uuid
from datetime import datetime

from app.nodes.store import supabase, store_entities

USER_ID = "0f5acdab-736f-4f44-883e-c897145a5ff2"
RUN_ID = f"entitytest_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"

def should_accept_semantic_match(incoming_name: str, matched_name: str, similarity: float) -> bool:
    incoming = incoming_name.strip().lower()
    matched = matched_name.strip().lower()

    if similarity >= 0.95:
        return True

    if incoming in matched or matched in incoming:
        return similarity >= 0.90

    return False

def normalize_name(name: str) -> str:
    return " ".join(name.strip().lower().split())


def print_header(title: str):
    print("\n" + "=" * 120)
    print(title)
    print("=" * 120)


def print_check(label: str, passed: bool, detail: str = ""):
    status = "PASS" if passed else "FAIL"
    print(f"[{status}] {label}" + (f" -> {detail}" if detail else ""))


async def fetch_entities_case_insensitive(name: str, entity_type: str):
    result = (
        supabase.table("entities")
        .select("*")
        .eq("user_id", USER_ID)
        .eq("entity_type", entity_type)
        .ilike("name", name.strip())
        .execute()
    )
    return result.data or []


async def fetch_entity_by_id(entity_id: str):
    result = supabase.table("entities").select("*").eq("id", entity_id).limit(1).execute()
    return result.data[0] if result.data else None


async def count_entities_case_insensitive(name: str, entity_type: str) -> int:
    rows = await fetch_entities_case_insensitive(name, entity_type)
    return len(rows)


def unique_ids(ids: list[str]) -> list[str]:
    return list(set(ids))


async def run_case_insensitive_exact_match_test():
    print_header("TEST 1: case-insensitive exact match should reuse same entity row")

    canonical_name = f"MindGraph_{RUN_ID}"
    case_variant = canonical_name.lower()
    summary_1 = f"First summary for {canonical_name}"
    summary_2 = f"Second summary for {case_variant}"

    before_count = await count_entities_case_insensitive(canonical_name, "project")

    ids_first = await store_entities(
        [{"name": canonical_name, "type": "project"}],
        USER_ID,
        summary_1,
    )
    after_first_count = await count_entities_case_insensitive(canonical_name, "project")

    ids_second = await store_entities(
        [{"name": case_variant, "type": "project"}],
        USER_ID,
        summary_2,
    )
    after_second_count = await count_entities_case_insensitive(canonical_name, "project")

    same_id_reused = len(ids_first) == 1 and len(ids_second) == 1 and ids_first[0] == ids_second[0]
    entity_row = await fetch_entity_by_id(ids_first[0]) if ids_first else None

    checks = {
        "first_call_returned_one_id": len(ids_first) == 1,
        "second_call_returned_one_id": len(ids_second) == 1,
        "same_entity_id_reused": same_id_reused,
        "row_count_after_first_is_one_more_than_before": after_first_count == before_count + 1,
        "row_count_after_second_did_not_increase": after_second_count == after_first_count,
        "mention_count_incremented_to_at_least_2": entity_row is not None and entity_row.get("mention_count", 0) >= 2,
        "entity_type_preserved": entity_row is not None and entity_row.get("entity_type") == "project",
    }

    print(f"before_count={before_count}, after_first_count={after_first_count}, after_second_count={after_second_count}")
    print(f"ids_first={ids_first}, ids_second={ids_second}")
    if entity_row:
        print(f"stored_row_name={entity_row.get('name')}, mention_count={entity_row.get('mention_count')}")

    for k, v in checks.items():
        print_check(k, v)

    return {
        "name": "case_insensitive_exact_match",
        "passed": all(checks.values()),
        "checks": checks,
        "tp": int(checks["same_entity_id_reused"]),
        "fp": int(not checks["row_count_after_second_did_not_increase"]),
        "fn": int(not checks["same_entity_id_reused"]),
    }


async def run_same_batch_duplicate_ids_test():
    print_header("TEST 2: same batch with duplicate case variants should return duplicate IDs but only one unique entity")

    name_a = f"MindGraphBatch_{RUN_ID}"
    name_b = name_a.lower()
    before_count = await count_entities_case_insensitive(name_a, "project")

    returned_ids = await store_entities(
        [
            {"name": name_a, "type": "project"},
            {"name": name_b, "type": "project"},
        ],
        USER_ID,
        f"Batch duplicate summary {RUN_ID}",
    )

    after_count = await count_entities_case_insensitive(name_a, "project")
    unique_returned_ids = unique_ids(returned_ids)

    entity_row = await fetch_entity_by_id(unique_returned_ids[0]) if unique_returned_ids else None

    checks = {
        "two_ids_returned_from_two_inputs": len(returned_ids) == 2,
        "both_inputs_resolved_to_same_entity_id": len(unique_returned_ids) == 1,
        "only_one_entity_row_exists_in_db": after_count == before_count + 1,
        "mention_count_incremented_to_at_least_2": entity_row is not None and entity_row.get("mention_count", 0) >= 2,
    }

    print(f"before_count={before_count}, after_count={after_count}")
    print(f"returned_ids={returned_ids}, unique_returned_ids={unique_returned_ids}")
    if entity_row:
        print(f"stored_row_name={entity_row.get('name')}, mention_count={entity_row.get('mention_count')}")

    for k, v in checks.items():
        print_check(k, v)

    return {
        "name": "same_batch_duplicate_ids",
        "passed": all(checks.values()),
        "checks": checks,
        "tp": int(checks["both_inputs_resolved_to_same_entity_id"]),
        "fp": int(not checks["only_one_entity_row_exists_in_db"]),
        "fn": int(not checks["both_inputs_resolved_to_same_entity_id"]),
    }


async def run_type_separation_test():
    print_header("TEST 3: same name but different entity_type should remain separate")

    shared_name = f"Phoenix_{RUN_ID}"
    before_project = await count_entities_case_insensitive(shared_name, "project")
    before_org = await count_entities_case_insensitive(shared_name, "organization")

    ids = await store_entities(
        [
            {"name": shared_name, "type": "project"},
            {"name": shared_name, "type": "organization"},
        ],
        USER_ID,
        f"Type separation summary {RUN_ID}",
    )

    after_project = await count_entities_case_insensitive(shared_name, "project")
    after_org = await count_entities_case_insensitive(shared_name, "organization")

    checks = {
        "two_ids_returned": len(ids) == 2,
        "different_types_got_different_ids": len(set(ids)) == 2,
        "project_row_created": after_project == before_project + 1,
        "organization_row_created": after_org == before_org + 1,
    }

    print(f"ids={ids}")
    print(f"project_count: {before_project} -> {after_project}")
    print(f"organization_count: {before_org} -> {after_org}")

    for k, v in checks.items():
        print_check(k, v)

    return {
        "name": "type_separation",
        "passed": all(checks.values()),
        "checks": checks,
        "tp": int(checks["different_types_got_different_ids"]),
        "fp": int(not checks["different_types_got_different_ids"]),
        "fn": 0,
    }


async def run_existing_entity_update_test():
    print_header("TEST 4: existing exact-match entity should update mention_count and context_summary")

    name = f"Databricks_{RUN_ID}"
    summary_1 = f"Initial summary {RUN_ID}"
    summary_2 = f"Updated summary {RUN_ID}"

    first_ids = await store_entities(
        [{"name": name, "type": "tool"}],
        USER_ID,
        summary_1,
    )

    row_after_first = await fetch_entity_by_id(first_ids[0]) if first_ids else None

    second_ids = await store_entities(
        [{"name": name.upper(), "type": "tool"}],
        USER_ID,
        summary_2,
    )

    row_after_second = await fetch_entity_by_id(second_ids[0]) if second_ids else None

    same_id = len(first_ids) == 1 and len(second_ids) == 1 and first_ids[0] == second_ids[0]

    checks = {
        "same_id_reused": same_id,
        "mention_count_increased": (
            row_after_first is not None
            and row_after_second is not None
            and row_after_second.get("mention_count", 0) > row_after_first.get("mention_count", 0)
        ),
        "context_summary_updated": row_after_second is not None and row_after_second.get("context_summary") == summary_2,
        "entity_type_still_tool": row_after_second is not None and row_after_second.get("entity_type") == "tool",
    }

    print(f"first_ids={first_ids}, second_ids={second_ids}")
    if row_after_first:
        print(f"mention_count_after_first={row_after_first.get('mention_count')}")
    if row_after_second:
        print(f"mention_count_after_second={row_after_second.get('mention_count')}")
        print(f"context_summary_after_second={row_after_second.get('context_summary')}")

    for k, v in checks.items():
        print_check(k, v)

    return {
        "name": "existing_entity_update",
        "passed": all(checks.values()),
        "checks": checks,
        "tp": int(checks["same_id_reused"]),
        "fp": int(not checks["context_summary_updated"]),
        "fn": int(not checks["same_id_reused"]),
    }


async def run_empty_entities_test():
    print_header("TEST 5: empty input should return empty list")

    ids = await store_entities([], USER_ID, f"Empty summary {RUN_ID}")

    checks = {
        "returns_empty_list": ids == [],
    }

    print(f"returned_ids={ids}")

    for k, v in checks.items():
        print_check(k, v)

    return {
        "name": "empty_entities",
        "passed": all(checks.values()),
        "checks": checks,
        "tp": 0,
        "fp": 0,
        "fn": 0,
    }


async def run_mixed_diverse_entities_test():
    print_header("TEST 6: diverse entities with one case-duplicate should create correct unique rows")

    project_name = f"MindGraphMixed_{RUN_ID}"
    org_name = f"GoogleMixed_{RUN_ID}"
    tool_name = f"FigmaMixed_{RUN_ID}"
    person_name = f"RahulMixed_{RUN_ID}"

    before_project = await count_entities_case_insensitive(project_name, "project")
    before_org = await count_entities_case_insensitive(org_name, "organization")
    before_tool = await count_entities_case_insensitive(tool_name, "tool")
    before_person = await count_entities_case_insensitive(person_name, "person")

    returned_ids = await store_entities(
        [
            {"name": project_name, "type": "project"},
            {"name": project_name.lower(), "type": "project"},
            {"name": org_name, "type": "organization"},
            {"name": tool_name, "type": "tool"},
            {"name": person_name, "type": "person"},
        ],
        USER_ID,
        f"Mixed summary {RUN_ID}",
    )

    after_project = await count_entities_case_insensitive(project_name, "project")
    after_org = await count_entities_case_insensitive(org_name, "organization")
    after_tool = await count_entities_case_insensitive(tool_name, "tool")
    after_person = await count_entities_case_insensitive(person_name, "person")

    unique_returned_ids = set(returned_ids)

    checks = {
        "five_inputs_returned_five_ids": len(returned_ids) == 5,
        "unique_ids_count_is_four": len(unique_returned_ids) == 4,
        "project_row_created_once": after_project == before_project + 1,
        "org_row_created_once": after_org == before_org + 1,
        "tool_row_created_once": after_tool == before_tool + 1,
        "person_row_created_once": after_person == before_person + 1,
    }

    print(f"returned_ids={returned_ids}")
    print(f"unique_returned_ids={unique_returned_ids}")
    print(f"project_count: {before_project} -> {after_project}")
    print(f"org_count: {before_org} -> {after_org}")
    print(f"tool_count: {before_tool} -> {after_tool}")
    print(f"person_count: {before_person} -> {after_person}")

    for k, v in checks.items():
        print_check(k, v)

    return {
        "name": "mixed_diverse_entities",
        "passed": all(checks.values()),
        "checks": checks,
        "tp": int(checks["unique_ids_count_is_four"]),
        "fp": int(not checks["project_row_created_once"]),
        "fn": int(not checks["unique_ids_count_is_four"]),
    }


def summarize(results: list[dict]):
    print_header("OVERALL SUMMARY")

    total_tests = len(results)
    passed_tests = sum(1 for r in results if r["passed"])
    failed_tests = [r["name"] for r in results if not r["passed"]]

    total_checks = sum(len(r["checks"]) for r in results)
    passed_checks = sum(sum(1 for v in r["checks"].values() if v) for r in results)

    test_pass_rate = passed_tests / total_tests if total_tests else 0.0
    check_pass_rate = passed_checks / total_checks if total_checks else 0.0

    total_tp = sum(r["tp"] for r in results)
    total_fp = sum(r["fp"] for r in results)
    total_fn = sum(r["fn"] for r in results)

    precision = total_tp / (total_tp + total_fp) if (total_tp + total_fp) > 0 else 1.0
    recall = total_tp / (total_tp + total_fn) if (total_tp + total_fn) > 0 else 1.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0.0

    print(f"Run ID: {RUN_ID}")
    print(f"User ID: {USER_ID}")
    print(f"Total tests: {total_tests}")
    print(f"Passed tests: {passed_tests}")
    print(f"Test pass rate: {test_pass_rate:.2%}")
    print(f"Total checks: {total_checks}")
    print(f"Passed checks: {passed_checks}")
    print(f"Check pass rate: {check_pass_rate:.2%}")
    print()
    print("Entity-linking metrics:")
    print(f"  Precision: {precision:.4f}")
    print(f"  Recall:    {recall:.4f}")
    print(f"  F1 score:  {f1:.4f}")

    print("\nPer-test summary:")
    for result in results:
        passed_count = sum(1 for v in result["checks"].values() if v)
        total_count = len(result["checks"])
        print(
            f" - {result['name']}: "
            f"{'PASS' if result['passed'] else 'FAIL'} "
            f"({passed_count}/{total_count} checks passed)"
        )

    if failed_tests:
        print("\nFailed tests:")
        for name in failed_tests:
            print(f" - {name}")


async def main():
    results = []

    results.append(await run_case_insensitive_exact_match_test())
    results.append(await run_same_batch_duplicate_ids_test())
    results.append(await run_type_separation_test())
    results.append(await run_existing_entity_update_test())
    results.append(await run_empty_entities_test())
    results.append(await run_mixed_diverse_entities_test())

    summarize(results)


if __name__ == "__main__":
    asyncio.run(main())