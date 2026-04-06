import asyncio
from copy import deepcopy

from app.nodes.extract_entities import extract_entities


BASE_STATE = {
    "raw_text": "",
    "user_id": "0f5acdab-736f-4f44-883e-c897145a5ff2",
    "cleaned_text": "",
    "auto_title": "",
    "summary": "",
    "input_type": "text",
    "attachment_url": "",
    "classifier": [],
    "core_entities": [],
    "deadline": [],
    "relations": [],
    "trigger_check": False,
    "duplicate_of": None,
    "dedup_check_result": None,
}


TEST_CASES = [
    {
        "name": "happy_path_multiple_entities",
        "cleaned_text": "Had a meeting with Rahul and Priya at Google office about ProjectX using Figma",
        "expected": [
            {"name": "Rahul", "type": "person"},
            {"name": "Priya", "type": "person"},
            {"name": "Google", "type": "organization"},
            {"name": "ProjectX", "type": "project"},
            {"name": "Figma", "type": "tool"},
        ],
        "bad_should_not_contain": ["meeting", "office"],
    },
    {
        "name": "generic_words_should_not_be_entities",
        "cleaned_text": "I need to work on project and continue the conversation in my own mind",
        "expected": [],
        "bad_should_not_contain": ["project", "conversation", "my own mind", "mind"],
    },
    {
        "name": "date_should_not_be_entity",
        "cleaned_text": "On 2026-03-31 I thought a lot about life and work",
        "expected": [],
        "bad_should_not_contain": ["2026-03-31", "life", "work"],
    },
    {
        "name": "project_tool_person_mix",
        "cleaned_text": "Spent the evening improving MindGraph with LangGraph and Gemini after talking to Daniel",
        "expected": [
            {"name": "MindGraph", "type": "project"},
            {"name": "LangGraph", "type": "tool"},
            {"name": "Gemini", "type": "tool"},
            {"name": "Daniel", "type": "person"},
        ],
        "bad_should_not_contain": ["evening"],
    },
    {
        "name": "organization_place_tool",
        "cleaned_text": "Visited the Microsoft office in Bangalore and tested Power BI dashboards",
        "expected": [
            {"name": "Microsoft", "type": "organization"},
            {"name": "Bangalore", "type": "place"},
            {"name": "Power BI", "type": "tool"},
        ],
        "bad_should_not_contain": ["office", "dashboards"],
    },
    {
        "name": "event_extraction_specific_event_only",
        "cleaned_text": "Booked tickets for WWDC and noted I should watch the keynote with Arun",
        "expected": [
            {"name": "WWDC", "type": "event"},
            {"name": "Arun", "type": "person"},
        ],
        "bad_should_not_contain": ["keynote", "tickets"],
    },
    {
        "name": "task_should_be_specific_not_generic",
        "cleaned_text": "Need to submit the Surrey County Council quarterly provider report on 2026-04-03",
        "expected": [
            {"name": "Surrey County Council", "type": "organization"},
            {"name": "quarterly provider report", "type": "task"},
        ],
        "bad_should_not_contain": ["2026-04-03", "report"],
    },
    {
        "name": "abstract_reflection_no_entities",
        "cleaned_text": "I was just sitting with my thoughts, feelings, fear, and my own mind tonight",
        "expected": [],
        "bad_should_not_contain": ["thoughts", "feelings", "fear", "my own mind", "tonight"],
    },
    {
        "name": "duplicate_entity_should_not_repeat",
        "cleaned_text": "Rahul called Rahul again about MindGraph and MindGraph planning in Figma",
        "expected": [
            {"name": "Rahul", "type": "person"},
            {"name": "MindGraph", "type": "project"},
            {"name": "Figma", "type": "tool"},
        ],
        "bad_should_not_contain": [],
    },
    {
        "name": "normalized_date_from_upstream_should_not_leak",
        "cleaned_text": "I need to finish the deck by 2026-04-05 for Google",
        "expected": [
            {"name": "Google", "type": "organization"},
        ],
        "bad_should_not_contain": ["2026-04-05", "deck"],
    },
    {
        "name": "multi_org_project_tool",
        "cleaned_text": "Prepared JPMorgan Chase migration notes for Delta Lake in Databricks",
        "expected": [
            {"name": "JPMorgan Chase", "type": "organization"},
            {"name": "Delta Lake", "type": "tool"},
            {"name": "Databricks", "type": "tool"},
            {"name": "migration notes", "type": "task"},
        ],
        "bad_should_not_contain": [],
    },
    {
        "name": "place_person_organization",
        "cleaned_text": "Had lunch with Kiran near Oxford University in London",
        "expected": [
            {"name": "Kiran", "type": "person"},
            {"name": "Oxford University", "type": "organization"},
            {"name": "London", "type": "place"},
        ],
        "bad_should_not_contain": ["lunch"],
    },
]


def normalize_name(value: str) -> str:
    return " ".join(value.strip().lower().split())


def entity_to_key(entity: dict) -> tuple[str, str]:
    return (
        normalize_name(entity["name"]),
        entity["type"].strip().lower(),
    )


def entities_to_set(entities: list[dict]) -> set[tuple[str, str]]:
    return {entity_to_key(entity) for entity in entities}


def contains_bad_entity(predicted: list[dict], banned_names: list[str]) -> list[str]:
    predicted_names = {normalize_name(entity["name"]) for entity in predicted}
    leaked = []
    for bad in banned_names:
        if normalize_name(bad) in predicted_names:
            leaked.append(bad)
    return leaked


async def run_single_test(test_case: dict) -> dict:
    state = deepcopy(BASE_STATE)
    state["cleaned_text"] = test_case["cleaned_text"]

    result = await extract_entities(state)
    predicted = result.get("core_entities", [])

    expected_set = entities_to_set(test_case["expected"])
    predicted_set = entities_to_set(predicted)

    true_positives = len(expected_set & predicted_set)
    false_positives = len(predicted_set - expected_set)
    false_negatives = len(expected_set - predicted_set)

    precision = (
        true_positives / (true_positives + false_positives)
        if (true_positives + false_positives) > 0
        else 1.0
    )
    recall = (
        true_positives / (true_positives + false_negatives)
        if (true_positives + false_negatives) > 0
        else 1.0
    )
    f1 = (
        2 * precision * recall / (precision + recall)
        if (precision + recall) > 0
        else 0.0
    )

    exact_match = expected_set == predicted_set
    bad_leaks = contains_bad_entity(predicted, test_case.get("bad_should_not_contain", []))

    return {
        "name": test_case["name"],
        "cleaned_text": test_case["cleaned_text"],
        "expected": test_case["expected"],
        "predicted": predicted,
        "tp": true_positives,
        "fp": false_positives,
        "fn": false_negatives,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "exact_match": exact_match,
        "bad_leaks": bad_leaks,
        "passed": exact_match and not bad_leaks,
    }


def print_test_result(result: dict) -> None:
    print("=" * 100)
    print(f"TEST: {result['name']}")
    print(f"CLEANED_TEXT: {result['cleaned_text']}")
    print(f"EXPECTED: {result['expected']}")
    print(f"PREDICTED: {result['predicted']}")
    print(
        f"METRICS -> TP: {result['tp']} | FP: {result['fp']} | FN: {result['fn']} | "
        f"Precision: {result['precision']:.2f} | Recall: {result['recall']:.2f} | F1: {result['f1']:.2f}"
    )
    print(f"EXACT MATCH: {result['exact_match']}")
    print(f"BAD ENTITY LEAKS: {result['bad_leaks'] if result['bad_leaks'] else 'None'}")
    print(f"STATUS: {'PASS' if result['passed'] else 'FAIL'}")


def print_summary(results: list[dict]) -> None:
    total_tests = len(results)
    passed_tests = sum(1 for r in results if r["passed"])
    exact_match_count = sum(1 for r in results if r["exact_match"])
    leak_free_count = sum(1 for r in results if not r["bad_leaks"])

    total_tp = sum(r["tp"] for r in results)
    total_fp = sum(r["fp"] for r in results)
    total_fn = sum(r["fn"] for r in results)

    micro_precision = total_tp / (total_tp + total_fp) if (total_tp + total_fp) > 0 else 1.0
    micro_recall = total_tp / (total_tp + total_fn) if (total_tp + total_fn) > 0 else 1.0
    micro_f1 = (
        2 * micro_precision * micro_recall / (micro_precision + micro_recall)
        if (micro_precision + micro_recall) > 0
        else 0.0
    )

    macro_precision = sum(r["precision"] for r in results) / total_tests
    macro_recall = sum(r["recall"] for r in results) / total_tests
    macro_f1 = sum(r["f1"] for r in results) / total_tests

    print("\n" + "#" * 100)
    print("OVERALL SUMMARY")
    print("#" * 100)
    print(f"Total tests: {total_tests}")
    print(f"Passed tests: {passed_tests}")
    print(f"Pass rate: {passed_tests / total_tests:.2%}")
    print(f"Exact match rate: {exact_match_count / total_tests:.2%}")
    print(f"Leak-free rate: {leak_free_count / total_tests:.2%}")
    print()
    print("Micro metrics:")
    print(f"  Precision: {micro_precision:.4f}")
    print(f"  Recall:    {micro_recall:.4f}")
    print(f"  F1 score:  {micro_f1:.4f}")
    print()
    print("Macro metrics:")
    print(f"  Precision: {macro_precision:.4f}")
    print(f"  Recall:    {macro_recall:.4f}")
    print(f"  F1 score:  {macro_f1:.4f}")

    failed = [r["name"] for r in results if not r["passed"]]
    if failed:
        print()
        print("Failed tests:")
        for name in failed:
            print(f"  - {name}")


async def main():
    results = []
    for test_case in TEST_CASES:
        result = await run_single_test(test_case)
        results.append(result)
        print_test_result(result)

    print_summary(results)


if __name__ == "__main__":
    asyncio.run(main())
