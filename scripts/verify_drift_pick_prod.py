"""Prod verification for drift pick v1 (run after Railway deploys df132a00).

1. Sign in as the screenshot test account (password grant, anon key).
2. GET /intentions/drift?pick=true  -> expect a pick (threshold_days=0 fallback
   if the account has no >=14d-quiet intentions).
3. Repeat the call -> expect the SAME pick id (48h stickiness).
4. Service-role read of the picked row -> surfaced_at stamped just now.
Prints PASS/FAIL per step; never prints secrets.
"""
import json
import os
import sys
import urllib.request
from datetime import datetime, timezone

ROOT = r"C:\projects\Mindgraph - Frictionless AI journal app"
API = "https://mindgraph-production.up.railway.app"


def load_env(path):
    vals = {}
    with open(path, "r", encoding="utf-8-sig") as f:  # utf-8-sig strips the BOM
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                vals[k.strip()] = v.strip().strip('"').strip("'")
    return vals


def post_json(url, payload, headers):
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode(), headers=headers, method="POST"
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def get_json(url, headers):
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


backend_env = load_env(os.path.join(ROOT, ".env"))
frontend_env = load_env(os.path.join(ROOT, "mindgraph-frontend", ".env"))

supa_url = frontend_env.get("REACT_APP_SUPABASE_URL") or backend_env.get("SUPABASE_URL")
anon = frontend_env["REACT_APP_SUPABASE_ANON_KEY"]
service = backend_env["SUPABASE_SERVICE_ROLE_KEY"]
email = backend_env["SCREENSHOT_EMAIL"]
password = backend_env["SCREENSHOT_PASSWORD"]

# 1. Password-grant sign-in
tok = post_json(
    f"{supa_url}/auth/v1/token?grant_type=password",
    {"email": email, "password": password},
    {"apikey": anon, "Content-Type": "application/json"},
)
jwt = tok["access_token"]
user_id = tok["user"]["id"]
print(f"PASS sign-in as test account (user {user_id[:8]}…)")

auth_headers = {"Authorization": f"Bearer {jwt}", "Content-Type": "application/json"}

# 2. Pick call (threshold_days=0 fallback so a fresh test account still yields a pick)
before = datetime.now(timezone.utc)
out = get_json(f"{API}/intentions/drift?pick=true", auth_headers)
used_fallback = False
if out.get("pick") is None:
    out = get_json(f"{API}/intentions/drift?pick=true&threshold_days=0", auth_headers)
    used_fallback = True
pick = out.get("pick")
if pick is None:
    print("INCONCLUSIVE: test account has no eligible intentions even at threshold 0")
    sys.exit(1)
print(
    f"PASS pick returned{' (threshold_days=0 fallback)' if used_fallback else ''}: "
    f"id={pick['id'][:8]}… days={pick['drift_days']} refs={pick['reference_count']} score={pick['score']}"
)
print(f"      text (guard-passed): {pick['text']!r}")

# 3. Stickiness: same pick on the next call
out2 = get_json(
    f"{API}/intentions/drift?pick=true" + ("&threshold_days=0" if used_fallback else ""),
    auth_headers,
)
pick2 = out2.get("pick")
same = pick2 and pick2["id"] == pick["id"]
print(f"{'PASS' if same else 'FAIL'} sticky re-serve returned the same pick")

# 4. surfaced_at stamped (service-role read)
# Two valid outcomes:
#  - FRESH pick: stamped within the last few minutes.
#  - STICKY re-serve: an existing stamp inside the 48h window, deliberately
#    NOT refreshed (restamping would defeat rotation) -- also a PASS.
rows = get_json(
    f"{supa_url}/rest/v1/intentions?id=eq.{pick['id']}&select=id,surfaced_at",
    {"apikey": service, "Authorization": f"Bearer {service}"},
)
stamp = rows[0]["surfaced_at"] if rows else None
if stamp:
    stamped_at = datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
    age_s = (before - stamped_at).total_seconds()
    if abs(age_s) < 300:
        print(f"PASS surfaced_at freshly stamped: {stamp}")
    elif 0 <= age_s < 48 * 3600:
        print(
            f"PASS surfaced_at unchanged inside the 48h sticky window "
            f"(stamped {age_s/3600:.1f}h ago) -- sticky serve, no restamp by design"
        )
    else:
        print(f"FAIL surfaced_at stale beyond the sticky window: {stamp}")
else:
    print("FAIL surfaced_at not stamped")
