# cleanup_test_store_data.py
import os
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()

supabase = create_client(
    os.getenv("SUPABASE_URL"),
    os.getenv("SUPABASE_KEY")
)

USER_ID = "e5e611e2-7618-43e2-be84-bf1fc3296382"

# IDs from your output
ENTRY_IDS = [
    "543e09e2-489d-4e32-86b9-2b6f574379a7",  # store_entry test
    "99ef589e-ee9f-45b1-b1eb-9b23fcd2e9e8",  # store_node test
]

ENTITY_IDS = [
    # helper test entity IDs
    "afea8d28-e256-47e7-828f-121a18c39eaa",
    "7a13f5ba-5ca9-4b95-9ef7-3eed7d048fdf",
    "c5860441-7d70-4453-92e5-e8a390573cc5",
    "599d5f20-3b85-41a5-9c55-ddaba37ddf46",
    "c070a170-0ad4-48d4-a4ec-100802605d37",
    "683afedb-5b90-432e-9b8c-98f6874dc7b5",
    "ea4ecc2f-4de1-464a-ab00-c235aeef3801",
    "669bb5c4-cc51-4579-9d77-64fe9d7a35b2",
    "5abd523d-7a82-4297-8124-f09607805dfd",
    "2d8919a6-a431-41fa-b214-166630be1807",

    # store_node entity IDs
    "4eb45cba-4414-4d27-8444-86f81765f777",
    "103e5fa2-daa5-47e7-9325-4da6f1828f13",
    "904ed115-f0b8-49a8-af7f-6416bfae8ada",
    "80355fbf-f9dc-48e0-9610-ce2358d4152a",
    "53e7e1d0-e1e2-4184-adbd-039a0b52c4ee",
    "13aaa040-efe1-4cd1-a039-cd44ab184a8e",
    "cbbe1ef5-43de-436c-b754-63f5faef69b7",
    "f51e128a-b77d-4d2d-b0bf-cf08393e3eb8",
    "c5b83634-84ba-4e0d-9d06-26cd5a36476a",
    "49cb2871-2448-4683-a052-d3f270dd3bc0",
]

def delete_in(table: str, column: str, values: list[str]):
    if not values:
        print(f"Skipping {table} (no values)")
        return
    result = supabase.table(table).delete().in_(column, values).execute()
    print(f"Deleted from {table}: {len(result.data) if result.data else 0}")

def main():
    print("Starting cleanup...")

    # 1) Child tables linked to entries/entities
    delete_in("entry_entities", "entry_id", ENTRY_IDS)
    delete_in("entry_entities", "entity_id", ENTITY_IDS)  # extra safety

    delete_in("entry_tags", "entry_id", ENTRY_IDS)
    delete_in("deadlines", "source_entry_id", ENTRY_IDS)

    # 2) Parent table: entries
    delete_in("entries", "id", ENTRY_IDS)

    # 3) Parent table: entities (created in tests)
    delete_in("entities", "id", ENTITY_IDS)

    print("Cleanup complete ✅ (users table untouched)")

if __name__ == "__main__":
    main()