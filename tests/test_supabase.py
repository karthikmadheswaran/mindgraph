# test_supabase.py
import os
from dotenv import load_dotenv
from supabase import create_client
from datetime import datetime, timezone
from supabase_auth import datetime

load_dotenv()

supabase = create_client(
    os.getenv("SUPABASE_URL"),
    os.getenv("SUPABASE_KEY")
)

# Try inserting a test user
'''result = supabase.table("users").insert({
    "email": "test@example.com"
}).execute()

print("USER CREATED:", result.data)

# Check if it's there
users = supabase.table("users").select("*").execute()
print("ALL USERS:", users.data)'''

'''
user_id: e5e611e2-7618-43e2-be84-bf1fc3296382
project_id: 035842a8-c613-488e-85eb-f5128e94e3c0

CREATE TABLE projects (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id),
    name VARCHAR(200),
    status VARCHAR(20) DEFAULT 'active',     -- active, stale, completed, abandoned
    first_mentioned_at TIMESTAMPTZ,
    last_mentioned_at TIMESTAMPTZ,
    mention_count INT DEFAULT 1,
    running_summary TEXT,                    -- updated by summary engine
    detected_deadline TIMESTAMPTZ,
    related_entities JSONB
);

'''
USER_ID = "e5e611e2-7618-43e2-be84-bf1fc3296382"

# Example project row for testing
project_payload = {
    "user_id": USER_ID,
    "name": "ProjectX",
    "status": "active",
    "first_mentioned_at": datetime.now(timezone.utc).isoformat(),
    "last_mentioned_at": datetime.now(timezone.utc).isoformat(),
    "mention_count": 1,
    "running_summary": "Initial test insert for ProjectX from journal pipeline.",
    "detected_deadline": "2026-02-27T00:00:00+00:00",  # optional; can also be None
    "related_entities": [
        {"name": "ProjectX", "type": "project"},
        {"name": "API documentation", "type": "task"},
        {"name": "PR", "type": "task"},
        {"name": "Rahul", "type": "person"},
    ],
}

result = supabase.table("projects").insert(project_payload).execute()

print("PROJECT INSERTED:", result.data)

# Verify
projects = (
    supabase.table("projects")
    .select("*")
    .eq("user_id", USER_ID)
    .execute()
)

print("PROJECTS FOR USER:", projects.data)

