import asyncio

import app.nodes.store as store_module


class FakeResponse:
    def __init__(self, data):
        self.data = data


class FakeTable:
    def __init__(self, storage: dict, table_name: str):
        self.storage = storage
        self.table_name = table_name
        self.pending_data = None
        self.pending_conflict = None

    def upsert(self, data, on_conflict=None):
        self.pending_data = data
        self.pending_conflict = on_conflict
        return self

    def execute(self):
        if self.table_name != "entity_relations":
            return FakeResponse([])

        if self.pending_conflict != "user_id,source_entity_id,target_entity_id,relation_type":
            raise AssertionError(f"Unexpected on_conflict value: {self.pending_conflict}")

        key = (
            self.pending_data["user_id"],
            self.pending_data["source_entity_id"],
            self.pending_data["target_entity_id"],
            self.pending_data["relation_type"],
        )
        self.storage[key] = dict(self.pending_data)
        return FakeResponse([self.pending_data])


class FakeSupabase:
    def __init__(self):
        self.rows = {}

    def table(self, table_name: str):
        return FakeTable(self.rows, table_name)


async def run_tests() -> None:
    original_supabase = store_module.supabase
    fake_supabase = FakeSupabase()
    store_module.supabase = fake_supabase

    try:
        lookup = {
            "mindgraph|project": "project-1",
            "claude|tool": "tool-1",
            "rahul|person": "person-2",
            "priya|person": "person-1",
        }

        result_insert = await store_module.store_relations(
            [
                {
                    "source": "MindGraph",
                    "source_type": "project",
                    "target": "Claude",
                    "target_type": "tool",
                    "relation": "built_with",
                }
            ],
            "user-1",
            "entry-1",
            lookup,
        )

        relation_key = ("user-1", "project-1", "tool-1", "built_with")
        insert_pass = relation_key in fake_supabase.rows and result_insert["stored"] == 1

        result_repeat = await store_module.store_relations(
            [
                {
                    "source": "MindGraph",
                    "source_type": "project",
                    "target": "Claude",
                    "target_type": "tool",
                    "relation": "built_with",
                }
            ],
            "user-1",
            "entry-2",
            lookup,
        )

        repeat_pass = (
            len(fake_supabase.rows) == 1
            and fake_supabase.rows[relation_key]["source_entry_id"] == "entry-2"
            and result_repeat["stored"] == 1
        )

        result_missing = await store_module.store_relations(
            [
                {
                    "source": "Unknown",
                    "source_type": "project",
                    "target": "Claude",
                    "target_type": "tool",
                    "relation": "built_with",
                }
            ],
            "user-1",
            "entry-3",
            lookup,
        )

        missing_pass = len(fake_supabase.rows) == 1 and result_missing["skipped"] == 1

        result_symmetric = await store_module.store_relations(
            [
                {
                    "source": "Rahul",
                    "source_type": "person",
                    "target": "Priya",
                    "target_type": "person",
                    "relation": "works_with",
                }
            ],
            "user-1",
            "entry-4",
            lookup,
        )

        symmetric_key = ("user-1", "person-1", "person-2", "works_with")
        symmetric_pass = (
            symmetric_key in fake_supabase.rows
            and result_symmetric["stored"] == 1
        )

        checks = {
            "successful_relation_insert": insert_pass,
            "repeated_relation_upserts_not_duplicates": repeat_pass,
            "unresolved_lookup_is_skipped": missing_pass,
            "works_with_is_stored_once_with_sorted_ids": symmetric_pass,
        }

        print("=" * 100)
        print("STORE RELATIONS TESTS")
        for label, passed in checks.items():
            print(f"{label}: {'PASS' if passed else 'FAIL'}")

        if not all(checks.values()):
            raise SystemExit(1)
    finally:
        store_module.supabase = original_supabase


if __name__ == "__main__":
    asyncio.run(run_tests())
