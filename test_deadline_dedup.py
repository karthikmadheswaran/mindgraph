import asyncio
from datetime import datetime

import app.nodes.deadline as deadline_module
from app.nodes.deadline import build_deadline_prompt, dedup_deadlines, extract_deadlines


class FakeResponse:
    def __init__(self, content: str):
        self.content = content


class FakeModel:
    def __init__(self, content: str):
        self.content = content

    async def ainvoke(self, prompt: str):
        return FakeResponse(self.content)


def make_deadline(description: str, due_at: datetime, raw_text: str) -> dict:
    return {
        "description": description,
        "due_at": due_at,
        "raw_text": raw_text,
    }


async def run_tests() -> None:
    due_date = datetime(2026, 4, 9)

    exact_dupes = [
        make_deadline("meeting with Manuel", due_date, "tomorrow"),
        make_deadline("meeting with Manuel", due_date, "scheduled for tomorrow at 19:30"),
    ]
    exact_result = dedup_deadlines(exact_dupes)

    near_dupes = [
        make_deadline("meeting with Manuel at 19:30", due_date, "scheduled for tomorrow at 19:30"),
        make_deadline("meeting with Manuel", due_date, "meeting tomorrow"),
    ]
    near_result = dedup_deadlines(near_dupes)

    same_day_distinct = [
        make_deadline("meeting with Manuel", due_date, "meeting tomorrow"),
        make_deadline("submit the report", due_date, "submit the report tomorrow"),
    ]
    same_day_result = dedup_deadlines(same_day_distinct)

    original_model = deadline_module.model
    deadline_module.model = FakeModel(
        """
        [
          {"description": "meeting with Manuel", "due_at": "2026-04-09", "raw_text": "meeting tomorrow"},
          {"description": "meeting with Manuel", "due_at": "2026-04-09", "raw_text": "scheduled for tomorrow at 19:30"}
        ]
        """.strip()
    )

    try:
        state = {
            "raw_text": "Meeting tomorrow. It is scheduled for tomorrow at 19:30.",
            "cleaned_text": "Meeting on 2026-04-09. It is scheduled for 2026-04-09 at 19:30.",
            "user_id": "test-user",
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
            "entry_id": None,
        }
        extraction_result = await extract_deadlines(state)
    finally:
        deadline_module.model = original_model

    prompt = build_deadline_prompt("Meeting on 2026-04-09.", "Meeting tomorrow.")

    checks = {
        "exact_duplicates_collapsed_to_one": len(exact_result) == 1,
        "exact_duplicate_keeps_more_specific_raw_text": (
            len(exact_result) == 1
            and exact_result[0]["raw_text"] == "scheduled for tomorrow at 19:30"
        ),
        "same_date_substring_duplicates_collapse_to_shorter_description": (
            len(near_result) == 1
            and near_result[0]["description"] == "meeting with Manuel"
        ),
        "same_date_distinct_descriptions_are_preserved": len(same_day_result) == 2,
        "extract_deadlines_dedups_model_output_before_state": (
            len(extraction_result["deadline"]) == 1
            and extraction_result["deadline"][0]["description"] == "meeting with Manuel"
        ),
        "prompt_explicitly_instructs_model_not_to_duplicate_events": "extract it only once" in prompt.lower(),
    }

    print("=" * 100)
    print("DEADLINE DEDUP TESTS")
    for label, passed in checks.items():
        print(f"{label}: {'PASS' if passed else 'FAIL'}")

    if not all(checks.values()):
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(run_tests())
