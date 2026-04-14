import asyncio
from copy import deepcopy
from collections import defaultdict

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
    # ------------------------------------------------------------------
    # EASY / HAPPY PATH
    # ------------------------------------------------------------------
    {
        "name": "happy_path_multiple_entities",
        "family": "happy_path",
        "difficulty": "easy",
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
        "name": "project_tool_person_mix",
        "family": "happy_path",
        "difficulty": "easy",
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
        "family": "happy_path",
        "difficulty": "easy",
        "cleaned_text": "Visited the Microsoft office in Bangalore and tested Power BI dashboards",
        "expected": [
            {"name": "Microsoft", "type": "organization"},
            {"name": "Bangalore", "type": "place"},
            {"name": "Power BI", "type": "tool"},
        ],
        "bad_should_not_contain": ["office", "dashboards"],
    },
    {
        "name": "place_person_organization",
        "family": "happy_path",
        "difficulty": "easy",
        "cleaned_text": "Had lunch with Kiran near Oxford University in London",
        "expected": [
            {"name": "Kiran", "type": "person"},
            {"name": "Oxford University", "type": "organization"},
            {"name": "London", "type": "place"},
        ],
        "bad_should_not_contain": ["lunch"],
    },
    {
        "name": "multi_org_project_tool",
        "family": "happy_path",
        "difficulty": "medium",
        "cleaned_text": "Prepared JPMorgan Chase migration notes for Delta Lake in Databricks",
        "expected": [
            {"name": "JPMorgan Chase", "type": "organization"},
            {"name": "Delta Lake", "type": "tool"},
            {"name": "Databricks", "type": "tool"},
            {"name": "migration notes", "type": "task"},
        ],
        "bad_should_not_contain": [],
    },

    # ------------------------------------------------------------------
    # GENERIC / ABSTRACT SHOULD BE EMPTY
    # ------------------------------------------------------------------
    {
        "name": "generic_words_should_not_be_entities",
        "family": "negative_generic",
        "difficulty": "easy",
        "cleaned_text": "I need to work on project and continue the conversation in my own mind",
        "expected": [],
        "bad_should_not_contain": ["project", "conversation", "my own mind", "mind", "work"],
    },
    {
        "name": "date_should_not_be_entity",
        "family": "negative_generic",
        "difficulty": "easy",
        "cleaned_text": "On 2026-03-31 I thought a lot about life and work",
        "expected": [],
        "bad_should_not_contain": ["2026-03-31", "life", "work"],
    },
    {
        "name": "abstract_reflection_no_entities",
        "family": "negative_generic",
        "difficulty": "easy",
        "cleaned_text": "I was just sitting with my thoughts, feelings, fear, and my own mind tonight",
        "expected": [],
        "bad_should_not_contain": ["thoughts", "feelings", "fear", "my own mind", "tonight"],
    },
    {
        "name": "generic_dashboard_words_should_not_leak",
        "family": "negative_generic",
        "difficulty": "medium",
        "cleaned_text": "The dashboard, system, project, work, meeting and notes are all over the place",
        "expected": [],
        "bad_should_not_contain": ["dashboard", "system", "project", "work", "meeting", "notes"],
    },
    {
        "name": "vague_productivity_reflection_should_be_empty",
        "family": "negative_generic",
        "difficulty": "medium",
        "cleaned_text": "I need more focus and structure in life, not more apps or random ideas",
        "expected": [],
        "bad_should_not_contain": ["focus", "structure", "life", "apps", "ideas"],
    },

    # ------------------------------------------------------------------
    # DATE / TIME / TEMPORAL LEAKS
    # ------------------------------------------------------------------
    {
        "name": "normalized_date_from_upstream_should_not_leak",
        "family": "date_leaks",
        "difficulty": "easy",
        "cleaned_text": "I need to finish the deck by 2026-04-05 for Google",
        "expected": [
            {"name": "Google", "type": "organization"},
        ],
        "bad_should_not_contain": ["2026-04-05", "deck"],
    },
    {
        "name": "weekday_month_year_should_not_be_entities",
        "family": "date_leaks",
        "difficulty": "medium",
        "cleaned_text": "On Monday in April 2026 I reviewed the Microsoft partnership",
        "expected": [
            {"name": "Microsoft", "type": "organization"},
        ],
        "bad_should_not_contain": ["Monday", "April", "2026"],
    },
    {
        "name": "time_and_year_should_not_be_entities",
        "family": "date_leaks",
        "difficulty": "medium",
        "cleaned_text": "At 8 pm in 2027 I was still debugging MindGraph",
        "expected": [
            {"name": "MindGraph", "type": "project"},
        ],
        "bad_should_not_contain": ["8 pm", "2027"],
    },

    # ------------------------------------------------------------------
    # DUPLICATES / DEDUP WITHIN ONE EXTRACTION
    # ------------------------------------------------------------------
    {
        "name": "duplicate_entity_should_not_repeat",
        "family": "dedup",
        "difficulty": "easy",
        "cleaned_text": "Rahul called Rahul again about MindGraph and MindGraph planning in Figma",
        "expected": [
            {"name": "Rahul", "type": "person"},
            {"name": "MindGraph", "type": "project"},
            {"name": "Figma", "type": "tool"},
        ],
        "bad_should_not_contain": [],
    },
    {
        "name": "duplicate_tool_should_not_repeat",
        "family": "dedup",
        "difficulty": "medium",
        "cleaned_text": "Used Figma in Figma while reviewing Figma mockups for MindGraph",
        "expected": [
            {"name": "Figma", "type": "tool"},
            {"name": "MindGraph", "type": "project"},
        ],
        "bad_should_not_contain": ["mockups"],
    },
    {
        "name": "duplicate_org_should_not_repeat",
        "family": "dedup",
        "difficulty": "medium",
        "cleaned_text": "Google asked Google Cloud team to review the Google proposal",
        "expected": [
            {"name": "Google", "type": "organization"},
            {"name": "Google Cloud", "type": "organization"},
        ],
        "bad_should_not_contain": ["proposal", "team"],
    },

    # ------------------------------------------------------------------
    # FALSE PROJECT PROMOTION (MOST IMPORTANT)
    # ------------------------------------------------------------------
    {
        "name": "medicine_should_not_be_project",
        "family": "false_project_promotion",
        "difficulty": "hard",
        "cleaned_text": "I took Inspiral and felt calmer today",
        "expected": [],
        "bad_should_not_contain": ["Inspiral"],
    },
    {
        "name": "tool_should_not_be_project_when_tool_context_is_clear",
        "family": "false_project_promotion",
        "difficulty": "hard",
        "cleaned_text": "I used Figma to design the onboarding screen for MindGraph",
        "expected": [
            {"name": "Figma", "type": "tool"},
            {"name": "MindGraph", "type": "project"},
        ],
        "bad_should_not_contain": ["onboarding screen"],
    },
    {
        "name": "databricks_should_be_tool_not_project",
        "family": "false_project_promotion",
        "difficulty": "hard",
        "cleaned_text": "I learned Databricks and Delta Lake today for my data engineering work",
        "expected": [
            {"name": "Databricks", "type": "tool"},
            {"name": "Delta Lake", "type": "tool"},
        ],
        "bad_should_not_contain": ["data engineering work"],
    },
    {
        "name": "gemini_should_be_tool_not_project",
        "family": "false_project_promotion",
        "difficulty": "medium",
        "cleaned_text": "I tested Gemini to compare it with Claude for my workflow",
        "expected": [
            {"name": "Gemini", "type": "tool"},
        ],
        "bad_should_not_contain": ["workflow", "Claude"],
    },
    {
        "name": "random_capitalized_word_should_not_be_project",
        "family": "false_project_promotion",
        "difficulty": "hard",
        "cleaned_text": "Inspiral came up in my mind again and I kept overthinking it",
        "expected": [],
        "bad_should_not_contain": ["Inspiral"],
    },
    {
        "name": "brand_like_unknown_word_without_project_context_should_be_omitted",
        "family": "false_project_promotion",
        "difficulty": "hard",
        "cleaned_text": "I kept thinking about Velora all evening but it was just a passing thought",
        "expected": [],
        "bad_should_not_contain": ["Velora", "evening"],
    },

    # ------------------------------------------------------------------
    # PROJECT POSITIVE CASES (STRICT)
    # ------------------------------------------------------------------
    {
        "name": "clear_named_project_should_extract",
        "family": "project_positive",
        "difficulty": "easy",
        "cleaned_text": "Worked on MindGraph auth flow and dashboard polish",
        "expected": [
            {"name": "MindGraph", "type": "project"},
        ],
        "bad_should_not_contain": ["auth flow", "dashboard polish"],
    },
    {
        "name": "named_workstream_should_extract_as_project",
        "family": "project_positive",
        "difficulty": "medium",
        "cleaned_text": "We are planning Project Atlas for next quarter",
        "expected": [
            {"name": "Project Atlas", "type": "project"},
        ],
        "bad_should_not_contain": ["next quarter"],
    },
    {
        "name": "feature_build_should_still_extract_named_project",
        "family": "project_positive",
        "difficulty": "medium",
        "cleaned_text": "Built onboarding analytics for MindGraph using React",
        "expected": [
            {"name": "MindGraph", "type": "project"},
            {"name": "React", "type": "tool"},
        ],
        "bad_should_not_contain": ["onboarding analytics"],
    },
    {
        "name": "client_workstream_should_extract",
        "family": "project_positive",
        "difficulty": "hard",
        "cleaned_text": "Spent the afternoon fixing SurreyCare migration issues for the council team",
        "expected": [
            {"name": "SurreyCare", "type": "project"},
        ],
        "bad_should_not_contain": ["afternoon", "council team"],
    },

    # ------------------------------------------------------------------
    # PERSON / ORG / PLACE DISAMBIGUATION
    # ------------------------------------------------------------------
    {
        "name": "event_extraction_specific_event_only",
        "family": "disambiguation",
        "difficulty": "easy",
        "cleaned_text": "Booked tickets for WWDC and noted I should watch the keynote with Arun",
        "expected": [
            {"name": "WWDC", "type": "event"},
            {"name": "Arun", "type": "person"},
        ],
        "bad_should_not_contain": ["keynote", "tickets"],
    },
    {
        "name": "task_should_be_specific_not_generic",
        "family": "disambiguation",
        "difficulty": "medium",
        "cleaned_text": "Need to submit the Surrey County Council quarterly provider report on 2026-04-03",
        "expected": [
            {"name": "Surrey County Council", "type": "organization"},
            {"name": "quarterly provider report", "type": "task"},
        ],
        "bad_should_not_contain": ["2026-04-03", "report"],
    },
    {
        "name": "university_should_be_org_city_should_be_place",
        "family": "disambiguation",
        "difficulty": "medium",
        "cleaned_text": "I spoke at Stanford University in San Francisco",
        "expected": [
            {"name": "Stanford University", "type": "organization"},
            {"name": "San Francisco", "type": "place"},
        ],
        "bad_should_not_contain": [],
    },
    {
        "name": "office_should_not_be_place_without_specific_name",
        "family": "disambiguation",
        "difficulty": "medium",
        "cleaned_text": "Went back to the office and met Daniel from Google",
        "expected": [
            {"name": "Daniel", "type": "person"},
            {"name": "Google", "type": "organization"},
        ],
        "bad_should_not_contain": ["office"],
    },
    {
        "name": "brand_and_city_mixed",
        "family": "disambiguation",
        "difficulty": "medium",
        "cleaned_text": "Met the Microsoft team in Bangalore and later used Excel",
        "expected": [
            {"name": "Microsoft", "type": "organization"},
            {"name": "Bangalore", "type": "place"},
            {"name": "Excel", "type": "tool"},
        ],
        "bad_should_not_contain": ["team"],
    },

    # ------------------------------------------------------------------
    # TASK BOUNDARY
    # ------------------------------------------------------------------
    {
        "name": "task_specific_phrase_should_extract",
        "family": "task_boundary",
        "difficulty": "medium",
        "cleaned_text": "Need to finish provider renewal summary for Surrey County Council",
        "expected": [
            {"name": "provider renewal summary", "type": "task"},
            {"name": "Surrey County Council", "type": "organization"},
        ],
        "bad_should_not_contain": ["finish"],
    },
    {
        "name": "generic_task_word_should_not_extract",
        "family": "task_boundary",
        "difficulty": "easy",
        "cleaned_text": "I have a task and some work to do tomorrow",
        "expected": [],
        "bad_should_not_contain": ["task", "work", "tomorrow"],
    },
    {
        "name": "specific_report_task_should_extract_once",
        "family": "task_boundary",
        "difficulty": "hard",
        "cleaned_text": "Finish the provider quality assurance report and send it to Priya",
        "expected": [
            {"name": "provider quality assurance report", "type": "task"},
            {"name": "Priya", "type": "person"},
        ],
        "bad_should_not_contain": ["send"],
    },

    # ------------------------------------------------------------------
    # CAPITALIZATION / FORMATTING ROBUSTNESS
    # ------------------------------------------------------------------
    {
        "name": "mindgraph_lowercase_should_still_extract",
        "family": "formatting",
        "difficulty": "medium",
        "cleaned_text": "worked on mindgraph auth page using figma",
        "expected": [
            {"name": "mindgraph", "type": "project"},
            {"name": "figma", "type": "tool"},
        ],
        "bad_should_not_contain": ["auth page"],
    },
    {
        "name": "mixed_case_tool_names",
        "family": "formatting",
        "difficulty": "medium",
        "cleaned_text": "Used power bi and databricks for the dashboard refresh",
        "expected": [
            {"name": "power bi", "type": "tool"},
            {"name": "databricks", "type": "tool"},
        ],
        "bad_should_not_contain": ["dashboard refresh"],
    },
    {
        "name": "punctuated_project_name_should_still_extract_cleanly",
        "family": "formatting",
        "difficulty": "hard",
        "cleaned_text": "Worked on MindGraph, then used LangGraph, then shipped the fix",
        "expected": [
            {"name": "MindGraph", "type": "project"},
            {"name": "LangGraph", "type": "tool"},
        ],
        "bad_should_not_contain": ["fix"],
    },

    # ------------------------------------------------------------------
    # EDGE / AMBIGUOUS CASES
    # ------------------------------------------------------------------
    {
        "name": "ambiguous_capitalized_person_name_only",
        "family": "ambiguous",
        "difficulty": "hard",
        "cleaned_text": "Daniel helped me think through the architecture",
        "expected": [
            {"name": "Daniel", "type": "person"},
        ],
        "bad_should_not_contain": ["architecture"],
    },
    {
        "name": "unknown_brand_like_word_with_clear_project_context",
        "family": "ambiguous",
        "difficulty": "hard",
        "cleaned_text": "We are building Velora onboarding and fixing bugs in Velora dashboard",
        "expected": [
            {"name": "Velora", "type": "project"},
        ],
        "bad_should_not_contain": ["onboarding", "dashboard", "bugs"],
    },
    {
        "name": "unknown_brand_like_word_with_tool_context",
        "family": "ambiguous",
        "difficulty": "hard",
        "cleaned_text": "I used Velora to generate wireframes for the app",
        "expected": [],
        "bad_should_not_contain": ["Velora", "wireframes", "app"],
    },
    {
        "name": "organization_and_project_in_same_sentence",
        "family": "ambiguous",
        "difficulty": "hard",
        "cleaned_text": "Google asked us to demo MindGraph to their internal team",
        "expected": [
            {"name": "Google", "type": "organization"},
            {"name": "MindGraph", "type": "project"},
        ],
        "bad_should_not_contain": ["internal team", "demo"],
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


def find_duplicate_predictions(predicted: list[dict]) -> list[tuple[str, str]]:
    counts = defaultdict(int)
    for entity in predicted:
        counts[entity_to_key(entity)] += 1
    return [key for key, count in counts.items() if count > 1]


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
    duplicate_predictions = find_duplicate_predictions(predicted)

    return {
        "name": test_case["name"],
        "family": test_case["family"],
        "difficulty": test_case["difficulty"],
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
        "duplicate_predictions": duplicate_predictions,
        "passed": exact_match and not bad_leaks and not duplicate_predictions,
    }


def print_test_result(result: dict) -> None:
    print("=" * 120)
    print(f"TEST: {result['name']}")
    print(f"FAMILY: {result['family']} | DIFFICULTY: {result['difficulty']}")
    print(f"CLEANED_TEXT: {result['cleaned_text']}")
    print(f"EXPECTED: {result['expected']}")
    print(f"PREDICTED: {result['predicted']}")
    print(
        f"METRICS -> TP: {result['tp']} | FP: {result['fp']} | FN: {result['fn']} | "
        f"Precision: {result['precision']:.2f} | Recall: {result['recall']:.2f} | F1: {result['f1']:.2f}"
    )
    print(f"EXACT MATCH: {result['exact_match']}")
    print(f"BAD ENTITY LEAKS: {result['bad_leaks'] if result['bad_leaks'] else 'None'}")
    print(
        f"DUPLICATE PREDICTIONS: "
        f"{result['duplicate_predictions'] if result['duplicate_predictions'] else 'None'}"
    )
    print(f"STATUS: {'PASS' if result['passed'] else 'FAIL'}")


def print_family_summary(results: list[dict]) -> None:
    grouped = defaultdict(list)
    for r in results:
        grouped[r["family"]].append(r)

    print("\n" + "#" * 120)
    print("SUMMARY BY FAMILY")
    print("#" * 120)

    for family, rows in sorted(grouped.items()):
        total = len(rows)
        passed = sum(1 for r in rows if r["passed"])
        avg_f1 = sum(r["f1"] for r in rows) / total
        exact_rate = sum(1 for r in rows if r["exact_match"]) / total
        print(
            f"{family:<28} total={total:<3} "
            f"passed={passed:<3} "
            f"pass_rate={passed/total:.2%} "
            f"exact_rate={exact_rate:.2%} "
            f"avg_f1={avg_f1:.4f}"
        )


def print_difficulty_summary(results: list[dict]) -> None:
    grouped = defaultdict(list)
    for r in results:
        grouped[r["difficulty"]].append(r)

    print("\n" + "#" * 120)
    print("SUMMARY BY DIFFICULTY")
    print("#" * 120)

    for difficulty, rows in sorted(grouped.items()):
        total = len(rows)
        passed = sum(1 for r in rows if r["passed"])
        avg_f1 = sum(r["f1"] for r in rows) / total
        print(
            f"{difficulty:<10} total={total:<3} "
            f"passed={passed:<3} "
            f"pass_rate={passed/total:.2%} "
            f"avg_f1={avg_f1:.4f}"
        )


def print_summary(results: list[dict]) -> None:
    total_tests = len(results)
    passed_tests = sum(1 for r in results if r["passed"])
    exact_match_count = sum(1 for r in results if r["exact_match"])
    leak_free_count = sum(1 for r in results if not r["bad_leaks"])
    duplicate_free_count = sum(1 for r in results if not r["duplicate_predictions"])

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

    print("\n" + "#" * 120)
    print("OVERALL SUMMARY")
    print("#" * 120)
    print(f"Total tests: {total_tests}")
    print(f"Passed tests: {passed_tests}")
    print(f"Pass rate: {passed_tests / total_tests:.2%}")
    print(f"Exact match rate: {exact_match_count / total_tests:.2%}")
    print(f"Leak-free rate: {leak_free_count / total_tests:.2%}")
    print(f"Duplicate-free rate: {duplicate_free_count / total_tests:.2%}")
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
    print_family_summary(results)
    print_difficulty_summary(results)


if __name__ == "__main__":
    asyncio.run(main())