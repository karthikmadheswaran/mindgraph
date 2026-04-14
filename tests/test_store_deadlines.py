import asyncio
from datetime import datetime

import app.nodes.store as store_module


class FakeResponse:
    def __init__(self, data):
        self.data = data


class FakeTable:
    def __init__(self, storage: dict, table_name: str):
        self.storage = storage
        self.table_name = table_name
        self.pending_data = None

    def insert(self, data):
        self.pending_data = data
        return self

    def execute(self):
        if self.table_name != "deadlines":
            return FakeResponse([])

        row = dict(self.pending_data)
        key = (
            row["source_entry_id"],
            row["description"].strip().lower(),
            row["due_date"],
        )
        if key in self.storage:
            raise Exception("23505 duplicate key value violates unique constraint")

        self.storage[key] = row
        return FakeResponse([row])


class FakeSupabase:
    def __init__(self):
        self.rows = {}

    def table(self, table_name: str):
        return FakeTable(self.rows, table_name)


def make_deadline(description: str, due_at: datetime, raw_text: str) -> dict:
    return {
        "description": description,
        "due_at": due_at,
        "raw_text": raw_text,
    }


async def run_tests() -> None:
    original_supabase = store_module.supabase
    fake_supabase = FakeSupabase()
    store_module.supabase = fake_supabase

    try:
        entry_id = "entry-1"
        user_id = "user-1"
        due_date = datetime(2026, 4, 9)

        duplicate_deadlines = [
            make_deadline("meeting with Manuel", due_date, "meeting tomorrow"),
            make_deadline("meeting with Manuel", due_date, "scheduled for tomorrow at 19:30"),
        ]
        first_result = await store_module.store_entry_deadlines(entry_id, duplicate_deadlines, user_id)

        distinct_same_day = [
            make_deadline("meeting with Manuel", due_date, "meeting tomorrow"),
            make_deadline("submit the report", due_date, "submit the report tomorrow"),
        ]
        second_result = await store_module.store_entry_deadlines("entry-2", distinct_same_day, user_id)

        duplicate_retry = [
            make_deadline("meeting with Manuel", due_date, "meeting tomorrow"),
        ]
        retry_result = await store_module.store_entry_deadlines(entry_id, duplicate_retry, user_id)

        checks = {
            "store_dedups_duplicate_rows_before_insert": (
                first_result["success"]
                and first_result["stored"] == 1
                and first_result["skipped_duplicates"] == 1
            ),
            "store_preserves_same_day_distinct_deadlines": (
                second_result["success"]
                and second_result["stored"] == 2
                and second_result["skipped_duplicates"] == 0
            ),
            "store_ignores_duplicate_constraint_errors_from_db": (
                retry_result["success"]
                and retry_result["stored"] == 0
                and retry_result["skipped_duplicates"] == 1
            ),
            "fake_db_contains_only_three_unique_rows": len(fake_supabase.rows) == 3,
        }

        print("=" * 100)
        print("STORE DEADLINE TESTS")
        for label, passed in checks.items():
            print(f"{label}: {'PASS' if passed else 'FAIL'}")

        if not all(checks.values()):
            raise SystemExit(1)
    finally:
        store_module.supabase = original_supabase


if __name__ == "__main__":
    asyncio.run(run_tests())
