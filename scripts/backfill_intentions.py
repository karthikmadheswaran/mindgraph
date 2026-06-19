"""ONE-TIME backfill: replay intention extraction + resolution over a user's
EXISTING entries, so launch-day drift is REAL (an intention stated in an April
entry reads as ~10 weeks stale on June 30) instead of an empty feature.

It replays the live path exactly: for each entry oldest -> newest, run the P1
extraction node (app/nodes/intentions.extract_intentions) then the P2 resolver
(app/intention_resolver.resolve_and_persist_intentions). first_stated_at /
last_referenced_at come from each entry's real created_at (the resolver already
reads it), so a goal stated in April and restated in May ends with
last_referenced_at = May, reference_count = 2 — correct ONLY because we process
chronologically.

Idempotent: re-running is safe — the P2 origin-reprocess no-op + the partial
unique index (user_id, source_entry_id, lower(text)) WHERE deleted_at IS NULL
prevent double-inserts.

DRY RUN by default: extraction + resolution run in memory against a fake store,
NOTHING is written to the DB; it prints what WOULD be inserted for review. Only
--apply writes. Reads private journal data — commit NO output (this script takes
the user at runtime and prints to stdout only).

  python -m scripts.backfill_intentions --email krithikb4u@gmail.com            # dry run
  python -m scripts.backfill_intentions --email krithikb4u@gmail.com --limit 3  # quick sample
  USE_VERTEX=1 python -m scripts.backfill_intentions --user-id <uuid> --apply   # write (after review)
"""
import argparse
import asyncio
import os
import random
from datetime import datetime, timezone

from dotenv import load_dotenv

load_dotenv(encoding="utf-8-sig")

from supabase import create_client

import app.intention_resolver as resolver
from app.nodes.intentions import extract_intentions

DRIFT_DAYS = int(os.getenv("DRIFT_THRESHOLD_DAYS", "14"))
_PACE_S = float(os.getenv("BACKFILL_PACE", "6"))


# --- robust paced calls (generation + embedding both have shallow Vertex QPM) --

def _is_rate(exc) -> bool:
    m = str(exc).lower()
    return "429" in m or "resource exhausted" in m or "exhausted" in m or "quota" in m


async def _with_backoff(coro_factory, label, max_attempts=8):
    for attempt in range(max_attempts):
        try:
            return await coro_factory()
        except Exception as exc:
            if not _is_rate(exc) or attempt == max_attempts - 1:
                raise
            backoff = _PACE_S * (2 ** attempt) + random.uniform(0, 1.0)
            print(f"   [429] {label} backoff {backoff:.1f}s ({attempt + 1}/{max_attempts})")
            await asyncio.sleep(backoff)


# --- in-memory store for the dry run (real resolver code path, zero DB writes) -

class _Resp:
    def __init__(self, data):
        self.data = data


class _Query:
    def __init__(self, store, table):
        self.store, self.table = store, table
        self.filters, self.mode, self.payload = [], "select", None
        self._n = store["_seq"]

    def select(self, *a, **k):
        self.mode = "select"; return self

    def insert(self, data):
        self.mode, self.payload = "insert", data; return self

    def update(self, data, returning=None):
        self.mode, self.payload = "update", data; return self

    def eq(self, c, v): self.filters.append(("eq", c, v)); return self
    def in_(self, c, v): self.filters.append(("in", c, list(v))); return self
    def is_(self, c, v): self.filters.append(("is", c, None if v == "null" else v)); return self
    def order(self, *a, **k): return self
    def limit(self, n): return self

    def _match(self, r):
        for op, c, v in self.filters:
            cur = r.get(c)
            if op == "eq" and cur != v: return False
            if op == "in" and cur not in v: return False
            if op == "is" and cur != v: return False
        return True

    def execute(self):
        rows = self.store.setdefault(self.table, [])
        if self.mode == "select":
            return _Resp([dict(r) for r in rows if self._match(r)])
        if self.mode == "insert":
            row = dict(self.payload)
            if self.table == "intentions":
                key = (row.get("user_id"), row.get("source_entry_id"), (row.get("text") or "").lower())
                for o in rows:
                    if o.get("deleted_at") is None and (
                        o.get("user_id"), o.get("source_entry_id"), (o.get("text") or "").lower()) == key:
                        raise Exception('23505 duplicate key value violates unique constraint')
            self.store["_seq"][0] += 1
            row.setdefault("id", f"dry-{self.store['_seq'][0]}")
            row.setdefault("deleted_at", None)
            rows.append(row)
            return _Resp([dict(row)])
        if self.mode == "update":
            matched = [r for r in rows if self._match(r)]
            for r in matched:
                r.update(self.payload)
            return _Resp([dict(r) for r in matched])
        return _Resp([])


class _FakeSupabase:
    def __init__(self, entries):
        self.store = {"entries": [dict(e) for e in entries], "intentions": [], "_seq": [0]}

    def table(self, name):
        return _Query(self.store, name)


# --- run -------------------------------------------------------------------

def resolve_user_id(sb, args) -> str:
    if args.user_id:
        return args.user_id
    for page in range(1, 9):
        users = sb.auth.admin.list_users(page=page, per_page=50)
        if not users:
            break
        for u in users:
            if (getattr(u, "email", "") or "").lower() == (args.email or "").lower():
                return u.id
        if len(users) < 50:
            break
    raise SystemExit(f"Could not resolve user for email {args.email!r}")


async def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--user-id")
    ap.add_argument("--email")
    ap.add_argument("--apply", action="store_true", help="WRITE to the DB (default: dry run)")
    ap.add_argument("--limit", type=int, default=None, help="process only the first N entries (sampling)")
    args = ap.parse_args()
    if not args.user_id and not args.email:
        raise SystemExit("Pass --user-id or --email")

    sb = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_SERVICE_ROLE_KEY"))
    user_id = resolve_user_id(sb, args)

    entries = (
        sb.table("entries")
        .select("id, created_at, raw_text, cleaned_text")
        .eq("user_id", user_id)
        .eq("status", "completed")
        .is_("deleted_at", "null")
        .order("created_at", desc=False)   # CHRONOLOGICAL — clock correctness
        .execute()
    ).data or []
    if args.limit:
        entries = entries[: args.limit]

    mode = "APPLY (writing to DB)" if args.apply else "DRY RUN (no DB writes)"
    print(f"\n=== backfill intentions — {mode} ===")
    print(f"user={user_id[:8]}...  entries={len(entries)}  "
          f"span={entries[0]['created_at'][:10] if entries else '-'}..{entries[-1]['created_at'][:10] if entries else '-'}\n")

    # Robust embeddings everywhere (retry 429s instead of the resolver's per-candidate skip).
    real_embed = resolver.get_embedding
    resolver.get_embedding = lambda text, **k: _with_backoff(lambda: real_embed(text, **k), "embed")

    if not args.apply:
        resolver.supabase = _FakeSupabase(entries)  # in-memory; zero DB writes

    entries_with_intent = 0
    totals = {"inserted": 0, "rereferenced": 0, "skipped": 0}
    for i, e in enumerate(entries):
        state = {
            "raw_text": e.get("raw_text") or "",
            "cleaned_text": e.get("cleaned_text") or e.get("raw_text") or "",
            "user_id": user_id, "user_timezone": "Asia/Kolkata",
        }
        out = await _with_backoff(lambda: extract_intentions(state), "extract")
        cands = out.get("intentions", [])
        if cands:
            entries_with_intent += 1
        res = await resolver.resolve_and_persist_intentions(e["id"], cands, user_id)
        for k in totals:
            totals[k] += res[k]
        if cands:
            print(f"[{e['created_at'][:10]}] {len(cands)} cand -> "
                  f"+{res['inserted']} new / {res['rereferenced']} reref  "
                  f":: {[c['text'] for c in cands]}")
        if i + 1 < len(entries):
            await asyncio.sleep(_PACE_S)

    # Report final intention set.
    if args.apply:
        rows = (sb.table("intentions").select("text, first_stated_at, last_referenced_at, reference_count, status")
                .eq("user_id", user_id).is_("deleted_at", "null").order("first_stated_at", desc=False).execute()).data or []
    else:
        rows = sorted(resolver.supabase.store["intentions"], key=lambda r: r["first_stated_at"])

    now = datetime.now(timezone.utc)
    def days_since(ts):
        d = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        if d.tzinfo is None:
            d = d.replace(tzinfo=timezone.utc)
        return (now - d).days

    print(f"\n=== {'WOULD CREATE' if not args.apply else 'CREATED'} {len(rows)} intentions ===")
    print(f"{'first_stated':12} {'last_ref':12} {'refs':>4} {'drift_d':>7}  text")
    drifting = 0
    for r in rows:
        dd = days_since(r["last_referenced_at"])
        if dd >= DRIFT_DAYS:
            drifting += 1
        print(f"{str(r['first_stated_at'])[:10]:12} {str(r['last_referenced_at'])[:10]:12} "
              f"{r.get('reference_count', 1):>4} {dd:>7}  {r['text']}")

    print(f"\nentries with >=1 extracted intention: {entries_with_intent}/{len(entries)}")
    print(f"resolution: {totals}")
    print(f"DRIFTING as of today (last_referenced >= {DRIFT_DAYS}d ago): {drifting}/{len(rows)}")
    if not args.apply:
        print("\nDRY RUN — nothing written. Re-run with --apply to persist (after review).")


if __name__ == "__main__":
    asyncio.run(main())
