import asyncio
import app.nodes.deadline as deadline_module
from app.nodes.deadline import extract_deadlines

base_state = {
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
    "trigger_check": False,
    "duplicate_of": None,
    "dedup_check_result": None,
}

TEST_CASES = [
    {
        "name": "absolute_single_deadline",
        "state": {
            **base_state,
            "raw_text": "submit visa docs on 2026-04-10",
            "cleaned_text": "Submit visa documents on 2026-04-10.",
        },
        "expected": [
            ("submit visa documents", "2026-04-10", "2026-04-10"),
        ],
    },
    {
        "name": "absolute_multiple_deadlines",
        "state": {
            **base_state,
            "raw_text": "pay rent on 2026-04-05 and call mom on 2026-04-06",
            "cleaned_text": "Pay rent on 2026-04-05 and call mom on 2026-04-06.",
        },
        "expected": [
            ("pay rent", "2026-04-05", "2026-04-05"),
            ("call mom", "2026-04-06", "2026-04-06"),
        ],
    },
    {
        "name": "mixed_case_real_plus_emotion",
        "state": {
            **base_state,
            "raw_text": "I feel anxious but need to pay rent on 2026-04-05",
            "cleaned_text": "I feel anxious but need to pay rent on 2026-04-05.",
        },
        "expected": [
            ("pay rent", "2026-04-05", "2026-04-05"),
        ],
    },
    {
        "name": "false_positive_hope",
        "state": {
            **base_state,
            "raw_text": "I hope for a better day tomorrow",
            "cleaned_text": "I hope for a better day tomorrow.",
        },
        "expected": [],
    },
    {
        "name": "false_positive_possibilities",
        "state": {
            **base_state,
            "raw_text": "I want new possibilities this month",
            "cleaned_text": "I want new possibilities this month.",
        },
        "expected": [],
    },
    {
        "name": "false_positive_metadata",
        "state": {
            **base_state,
            "raw_text": "Entry date: 2026-04-01",
            "cleaned_text": "Entry date: 2026-04-01.",
        },
        "expected": [],
    },
    {
        "name": "false_positive_progress",
        "state": {
            **base_state,
            "raw_text": "Project progress is slow this week",
            "cleaned_text": "Project progress is slow this week.",
        },
        "expected": [],
    },
    {
        "name": "wish_with_time_word",
        "state": {
            **base_state,
            "raw_text": "I hope tomorrow feels better",
            "cleaned_text": "I hope tomorrow feels better.",
        },
        "expected": [],
    },
    {
        "name": "aspiration_with_week",
        "state": {
            **base_state,
            "raw_text": "Need to feel more productive next week",
            "cleaned_text": "Need to feel more productive next week.",
        },
        "expected": [],
    },
    {
        "name": "vague_future_goal",
        "state": {
            **base_state,
            "raw_text": "Someday I want to move cities",
            "cleaned_text": "Someday I want to move cities.",
        },
        "expected": [],
    },
    {
        "name": "status_not_deadline",
        "state": {
            **base_state,
            "raw_text": "Need better progress by next month emotionally",
            "cleaned_text": "Need better progress by next month emotionally.",
        },
        "expected": [],
    },
    {
        "name": "reflection_with_date_not_commitment",
        "state": {
            **base_state,
            "raw_text": "On 2026-04-03 I felt more hopeful about life",
            "cleaned_text": "On 2026-04-03 I felt more hopeful about life.",
        },
        "expected": [],
    },
    {
        "name": "real_payment_deadline",
        "state": {
            **base_state,
            "raw_text": "Pay electricity bill by 2026-04-12",
            "cleaned_text": "Pay electricity bill by 2026-04-12.",
        },
        "expected": [
            ("pay electricity bill", "2026-04-12", "2026-04-12"),
        ],
    },
    {
        "name": "real_submission_deadline",
        "state": {
            **base_state,
            "raw_text": "Need to submit assignment on 2026-04-14",
            "cleaned_text": "Need to submit assignment on 2026-04-14.",
        },
        "expected": [
            ("submit assignment", "2026-04-14", "2026-04-14"),
        ],
    },
    {
        "name": "real_appointment_absolute",
        "state": {
            **base_state,
            "raw_text": "Doctor appointment on 2026-04-18 at 5pm",
            "cleaned_text": "Doctor appointment on 2026-04-18 at 5pm.",
        },
        "expected": [
            ("doctor appointment", "2026-04-18", "2026-04-18"),
        ],
    },
    {
        "name": "real_meeting_relative",
        "state": {
            **base_state,
            "raw_text": "Project review next Friday with Arun",
            "cleaned_text": "Project review next Friday with Arun.",
        },
        "expected": [
            ("project review with arun", "2026-04-10", "next Friday"),
        ],
    },
    {
        "name": "two_real_deadlines_with_noise",
        "state": {
            **base_state,
            "raw_text": "Life feels messy, but pay credit card on 2026-04-09 and meet Rahul on 2026-04-11",
            "cleaned_text": "Life feels messy, but pay credit card on 2026-04-09 and meet Rahul on 2026-04-11.",
        },
        "expected": [
            ("pay credit card", "2026-04-09", "2026-04-09"),
            ("meet rahul", "2026-04-11", "2026-04-11"),
        ],
    },
    {
        "name": "journal_metadata_plus_real_deadline",
        "state": {
            **base_state,
            "raw_text": "Entry date: 2026-04-01. Need to renew passport on 2026-04-20.",
            "cleaned_text": "Entry date: 2026-04-01. Need to renew passport on 2026-04-20.",
        },
        "expected": [
            ("renew passport", "2026-04-20", "2026-04-20"),
        ],
    },
    {
        "name": "emotional_plan_not_commitment",
        "state": {
            **base_state,
            "raw_text": "Tomorrow I just want peace and a better mood",
            "cleaned_text": "Tomorrow I just want peace and a better mood.",
        },
        "expected": [],
    },
    {
        "name": "future_intention_but_no_date",
        "state": {
            **base_state,
            "raw_text": "I need to change my life soon",
            "cleaned_text": "I need to change my life soon.",
        },
        "expected": [],
    },
    {
        "name": "real_task_with_slang_raw_and_normalized_clean",
        "state": {
            **base_state,
            "raw_text": "gonna meet rahul tmrw abt projectx",
            "cleaned_text": "I am going to meet Rahul tomorrow about ProjectX.",
        },
        "expected": [
            ("meet rahul about projectx", "2026-04-02", "tomorrow"),
        ],
    },
    {
        "name": "status_phrase_with_real_deadline_wording",
        "state": {
            **base_state,
            "raw_text": "Need project progress update by 2026-04-08",
            "cleaned_text": "Need project progress update by 2026-04-08.",
        },
        "expected": [
            ("project progress update", "2026-04-08", "2026-04-08"),
        ],
    },
    {
        "name": "non_deadline_event_memory",
        "state": {
            **base_state,
            "raw_text": "Last Friday was terrible and I cried a lot",
            "cleaned_text": "Last Friday was terrible and I cried a lot.",
        },
        "expected": [],
    },
]

def normalize_text(value: str) -> str:
    return " ".join(value.strip().lower().split())

def normalize_predicted_strict(deadlines):
    normalized = set()
    for d in deadlines:
        description = normalize_text(d["description"])
        due_at = d["due_at"].strftime("%Y-%m-%d")
        raw_text = normalize_text(d["raw_text"])
        normalized.add((description, due_at, raw_text))
    return normalized

def normalize_expected_strict(expected):
    return set(
        (normalize_text(desc), due.strip(), normalize_text(raw))
        for desc, due, raw in expected
    )

def normalize_predicted_relaxed(deadlines):
    normalized = set()
    for d in deadlines:
        due_at = d["due_at"].strftime("%Y-%m-%d")
        raw_text = normalize_text(d["raw_text"])
        normalized.add((due_at, raw_text))
    return normalized

def normalize_expected_relaxed(expected):
    return set(
        (due.strip(), normalize_text(raw))
        for _, due, raw in expected
    )

async def run_case(case):
    result = await extract_deadlines(case["state"])

    predicted_strict = normalize_predicted_strict(result["deadline"])
    expected_strict = normalize_expected_strict(case["expected"])

    predicted_relaxed = normalize_predicted_relaxed(result["deadline"])
    expected_relaxed = normalize_expected_relaxed(case["expected"])

    tp_strict = len(predicted_strict & expected_strict)
    fp_strict = len(predicted_strict - expected_strict)
    fn_strict = len(expected_strict - predicted_strict)

    tp_relaxed = len(predicted_relaxed & expected_relaxed)
    fp_relaxed = len(predicted_relaxed - expected_relaxed)
    fn_relaxed = len(expected_relaxed - predicted_relaxed)

    return {
        "name": case["name"],
        "predicted_strict": predicted_strict,
        "expected_strict": expected_strict,
        "predicted_relaxed": predicted_relaxed,
        "expected_relaxed": expected_relaxed,
        "tp_strict": tp_strict,
        "fp_strict": fp_strict,
        "fn_strict": fn_strict,
        "tp_relaxed": tp_relaxed,
        "fp_relaxed": fp_relaxed,
        "fn_relaxed": fn_relaxed,
        "exact_match_strict": predicted_strict == expected_strict,
        "exact_match_relaxed": predicted_relaxed == expected_relaxed,
    }

def compute_metrics(tp, fp, fn):
    precision = tp / (tp + fp) if (tp + fp) else 0
    recall = tp / (tp + fn) if (tp + fn) else 0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0
    return precision, recall, f1

async def run_suite(use_validator: bool):
    deadline_module.USE_SEMANTIC_VALIDATOR = use_validator

    print("\n" + "=" * 80)
    print(f"RUNNING TEST SUITE | USE_SEMANTIC_VALIDATOR = {use_validator}")
    print("=" * 80)

    results = []

    total_tp_strict = total_fp_strict = total_fn_strict = 0
    total_tp_relaxed = total_fp_relaxed = total_fn_relaxed = 0
    exact_matches_strict = 0
    exact_matches_relaxed = 0

    for case in TEST_CASES:
        r = await run_case(case)
        results.append(r)

        total_tp_strict += r["tp_strict"]
        total_fp_strict += r["fp_strict"]
        total_fn_strict += r["fn_strict"]

        total_tp_relaxed += r["tp_relaxed"]
        total_fp_relaxed += r["fp_relaxed"]
        total_fn_relaxed += r["fn_relaxed"]

        if r["exact_match_strict"]:
            exact_matches_strict += 1
        if r["exact_match_relaxed"]:
            exact_matches_relaxed += 1

        print(f"\nCASE: {r['name']}")
        print("STRICT EXPECTED :", r["expected_strict"])
        print("STRICT PREDICTED:", r["predicted_strict"])
        print(
            f"STRICT -> TP={r['tp_strict']} FP={r['fp_strict']} "
            f"FN={r['fn_strict']} EXACT={r['exact_match_strict']}"
        )

        print("RELAXED EXPECTED :", r["expected_relaxed"])
        print("RELAXED PREDICTED:", r["predicted_relaxed"])
        print(
            f"RELAXED -> TP={r['tp_relaxed']} FP={r['fp_relaxed']} "
            f"FN={r['fn_relaxed']} EXACT={r['exact_match_relaxed']}"
        )

    precision_strict, recall_strict, f1_strict = compute_metrics(
        total_tp_strict, total_fp_strict, total_fn_strict
    )
    precision_relaxed, recall_relaxed, f1_relaxed = compute_metrics(
        total_tp_relaxed, total_fp_relaxed, total_fn_relaxed
    )

    exact_match_rate_strict = exact_matches_strict / len(results) if results else 0
    exact_match_rate_relaxed = exact_matches_relaxed / len(results) if results else 0

    print("\n" + "-" * 80)
    print("STRICT METRICS")
    print(f"Precision        : {precision_strict:.2f}")
    print(f"Recall           : {recall_strict:.2f}")
    print(f"F1 Score         : {f1_strict:.2f}")
    print(f"Exact Match Rate : {exact_match_rate_strict:.2f}")

    print("\nRELAXED METRICS")
    print(f"Precision        : {precision_relaxed:.2f}")
    print(f"Recall           : {recall_relaxed:.2f}")
    print(f"F1 Score         : {f1_relaxed:.2f}")
    print(f"Exact Match Rate : {exact_match_rate_relaxed:.2f}")
    print("-" * 80)

    return {
        "use_validator": use_validator,
        "strict": {
            "precision": precision_strict,
            "recall": recall_strict,
            "f1": f1_strict,
            "exact_match_rate": exact_match_rate_strict,
        },
        "relaxed": {
            "precision": precision_relaxed,
            "recall": recall_relaxed,
            "f1": f1_relaxed,
            "exact_match_rate": exact_match_rate_relaxed,
        },
    }

async def main():
    with_validator = await run_suite(True)
    without_validator = await run_suite(False)

    print("\n" + "=" * 80)
    print("A/B COMPARISON SUMMARY")
    print("=" * 80)

    print("\nWITH VALIDATOR")
    print(with_validator)

    print("\nWITHOUT VALIDATOR")
    print(without_validator)

asyncio.run(main())