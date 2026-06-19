"""Hermetic tests for intention resolution + persistence (drift P2).

resolve_and_persist_intentions decides, per candidate, NEW vs RE-REFERENCE and
winds the drift clock. These run against a tiny in-memory fake of the supabase
PostgREST chain that honours .in_/.is_ filters AND the partial-unique constraint
(user_id, source_entry_id, lower(text)) WHERE deleted_at IS NULL, plus a
deterministic fake embedder (orthogonal concept vectors -> cosine 1.0 for a
restatement, 0.0 for a distinct intention) so the assertions are independent of
the exact calibrated threshold.

Covers: insert-new (entry.created_at dates, NOT now()); re-reference bump;
dormant re-activate; distinct -> insert; reprocess of the origin entry is a
no-op; the unique-constraint insert collision is swallowed; soft-deleted rows are
not matched; one bad candidate never sinks the entry.
"""
import os

os.environ.setdefault("SUPABASE_URL", "http://localhost")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-key")

import asyncio
import itertools

import pytest

import app.intention_resolver as resolver

USER = "user-1"
APRIL = "2026-04-01T00:00:00+00:00"
JUNE = "2026-06-01T00:00:00+00:00"

# Orthogonal concept vectors: a restatement maps to the SAME vector (cosine 1.0),
# a distinct intention to a different one (cosine 0.0).
CONCEPTS = {"gym": [1.0, 0.0, 0.0], "spanish": [0.0, 1.0, 0.0], "guitar": [0.0, 0.0, 1.0]}


async def fake_embed(text, task_type="RETRIEVAL_DOCUMENT"):
    t = (text or "").lower()
    for key, vec in CONCEPTS.items():
        if key in t:
            return list(vec)
    return [0.0, 0.0, 0.0]


class FakeResponse:
    def __init__(self, data):
        self.data = data


class FakeQuery:
    def __init__(self, store, table):
        self.store = store
        self.table = table
        self.filters = []
        self._mode = "select"
        self._payload = None
        self._limit = None
        self._ids = itertools.count(1)

    def select(self, *a, **k):
        self._mode = "select"
        return self

    def insert(self, data):
        self._mode = "insert"
        self._payload = data
        return self

    def update(self, data, returning=None):
        self._mode = "update"
        self._payload = data
        return self

    def eq(self, col, val):
        self.filters.append(("eq", col, val))
        return self

    def in_(self, col, vals):
        self.filters.append(("in", col, list(vals)))
        return self

    def is_(self, col, val):
        self.filters.append(("is", col, None if val == "null" else val))
        return self

    def order(self, *a, **k):
        return self

    def limit(self, n):
        self._limit = n
        return self

    def _match(self, row):
        for op, col, val in self.filters:
            cur = row.get(col)
            if op == "eq" and cur != val:
                return False
            if op == "in" and cur not in val:
                return False
            if op == "is" and cur != val:
                return False
        return True

    def execute(self):
        rows = self.store.setdefault(self.table, [])

        if self._mode == "select":
            matched = [dict(r) for r in rows if self._match(r)]
            if self._limit is not None:
                matched = matched[: self._limit]
            return FakeResponse(matched)

        if self._mode == "insert":
            row = dict(self._payload)
            # Partial unique: (user_id, source_entry_id, lower(text)) WHERE deleted_at IS NULL
            if self.table == "intentions":
                key = (row.get("user_id"), row.get("source_entry_id"),
                       (row.get("text") or "").lower())
                for other in rows:
                    if other.get("deleted_at") is not None:
                        continue
                    other_key = (other.get("user_id"), other.get("source_entry_id"),
                                 (other.get("text") or "").lower())
                    if other_key == key:
                        raise Exception(
                            '23505 duplicate key value violates unique constraint '
                            '"idx_intentions_user_entry_text"'
                        )
            row.setdefault("id", f"int-{next(self._ids)}")
            row.setdefault("deleted_at", None)
            rows.append(row)
            return FakeResponse([dict(row)])

        if self._mode == "update":
            matched = [r for r in rows if self._match(r)]
            for r in matched:
                r.update(self._payload)
            return FakeResponse([dict(r) for r in matched])

        return FakeResponse([])


class FakeSupabase:
    def __init__(self, store):
        self.store = store

    def table(self, name):
        return FakeQuery(self.store, name)


def make_intention(iid, *, text="get back to the gym", concept="gym", status="active",
                   source_entry_id="entry-old", reference_count=1,
                   last_referenced_at=APRIL, deleted_at=None):
    return {
        "id": iid, "user_id": USER, "text": text, "embedding": list(CONCEPTS[concept]),
        "status": status, "source_entry_id": source_entry_id,
        "first_stated_at": APRIL, "last_referenced_at": last_referenced_at,
        "reference_count": reference_count, "deleted_at": deleted_at,
    }


def install(monkeypatch, intentions=None, entries=None):
    store = {
        "intentions": [dict(i) for i in (intentions or [])],
        "entries": entries if entries is not None else [
            {"id": "entry-1", "user_id": USER, "created_at": APRIL},
            {"id": "entry-2", "user_id": USER, "created_at": JUNE},
        ],
    }
    monkeypatch.setattr(resolver, "supabase", FakeSupabase(store))
    monkeypatch.setattr(resolver, "get_embedding", fake_embed)
    return store


def run(entry_id, intentions, user_id=USER):
    return asyncio.run(resolver.resolve_and_persist_intentions(entry_id, intentions, user_id))


# ---- insert new ----------------------------------------------------------

def test_new_intention_inserts_with_entry_dates(monkeypatch):
    store = install(monkeypatch)
    res = run("entry-1", [{"text": "get back to the gym"}])
    assert res == {"inserted": 1, "rereferenced": 0, "skipped": 0}
    rows = store["intentions"]
    assert len(rows) == 1
    row = rows[0]
    assert row["text"] == "get back to the gym"
    assert row["source_entry_id"] == "entry-1"
    assert row["status"] == "active"
    assert row["reference_count"] == 1
    # dates come from the ENTRY (April), not now() — what makes backfill real
    assert row["first_stated_at"] == APRIL
    assert row["last_referenced_at"] == APRIL


# ---- re-reference --------------------------------------------------------

def test_rereference_bumps_clock_no_insert(monkeypatch):
    store = install(monkeypatch, intentions=[make_intention("int-gym")])
    res = run("entry-2", [{"text": "really want to hit the gym again"}])
    assert res == {"inserted": 0, "rereferenced": 1, "skipped": 0}
    assert len(store["intentions"]) == 1          # no new row
    row = store["intentions"][0]
    assert row["reference_count"] == 2            # bumped
    assert row["last_referenced_at"] == JUNE      # clock wound to entry-2's date
    assert row["source_entry_id"] == "entry-old"  # origin unchanged


def test_dormant_match_reactivates(monkeypatch):
    store = install(monkeypatch, intentions=[make_intention("int-gym", status="dormant")])
    res = run("entry-2", [{"text": "get back to the gym"}])
    assert res["rereferenced"] == 1
    assert store["intentions"][0]["status"] == "active"
    assert store["intentions"][0]["reference_count"] == 2


def test_distinct_intention_inserts_new(monkeypatch):
    store = install(monkeypatch, intentions=[make_intention("int-gym")])
    res = run("entry-2", [{"text": "learn spanish"}])
    assert res["inserted"] == 1 and res["rereferenced"] == 0
    assert len(store["intentions"]) == 2
    assert {r["text"] for r in store["intentions"]} == {"get back to the gym", "learn spanish"}


# ---- reprocess / idempotency --------------------------------------------

def test_reprocess_origin_entry_is_noop(monkeypatch):
    # The existing intention was first stated by entry-1; reprocessing entry-1
    # must not bump or insert.
    store = install(monkeypatch, intentions=[
        make_intention("int-gym", source_entry_id="entry-1", reference_count=1),
    ])
    res = run("entry-1", [{"text": "get back to the gym"}])
    assert res == {"inserted": 0, "rereferenced": 0, "skipped": 1}
    assert len(store["intentions"]) == 1
    assert store["intentions"][0]["reference_count"] == 1  # not inflated


def test_insert_unique_collision_is_swallowed(monkeypatch):
    # A live row already has (user, entry-1, "get back to the gym") but a
    # different embedding (spanish vec) so the cosine path does NOT match -> the
    # insert path fires and hits the partial-unique index. Must be a clean skip.
    store = install(monkeypatch, intentions=[
        make_intention("int-x", text="get back to the gym", concept="spanish",
                       source_entry_id="entry-1"),
    ])
    res = run("entry-1", [{"text": "get back to the gym"}])  # embeds to gym vec, no match
    assert res == {"inserted": 0, "rereferenced": 0, "skipped": 1}
    assert len(store["intentions"]) == 1  # no duplicate row created


# ---- soft-delete aware ---------------------------------------------------

def test_soft_deleted_not_matched(monkeypatch):
    # A soft-deleted gym intention must be invisible to resolution -> a new gym
    # candidate inserts fresh rather than reviving the deleted row.
    store = install(monkeypatch, intentions=[
        make_intention("int-del", deleted_at="2026-05-01T00:00:00+00:00"),
    ])
    res = run("entry-2", [{"text": "get back to the gym"}])
    assert res["inserted"] == 1
    live = [r for r in store["intentions"] if r["deleted_at"] is None]
    assert len(live) == 1 and live[0]["source_entry_id"] == "entry-2"


# ---- fail-safe -----------------------------------------------------------

def test_one_bad_candidate_does_not_sink_the_entry(monkeypatch):
    store = install(monkeypatch)

    async def flaky_embed(text, task_type="RETRIEVAL_DOCUMENT"):
        if "boom" in text:
            raise RuntimeError("embedding service exploded")
        return await fake_embed(text)

    monkeypatch.setattr(resolver, "get_embedding", flaky_embed)
    res = run("entry-1", [{"text": "boom bad candidate"}, {"text": "learn spanish"}])
    assert res["skipped"] == 1          # the bad one
    assert res["inserted"] == 1         # the good one still persisted
    assert [r["text"] for r in store["intentions"]] == ["learn spanish"]


def test_empty_intentions_is_noop(monkeypatch):
    store = install(monkeypatch)
    res = run("entry-1", [])
    assert res == {"inserted": 0, "rereferenced": 0, "skipped": 0}
    assert store["intentions"] == []
