# test_dedup.py
# Guards the entry-dedup similarity gate against false positives that silently
# swallow unique entries (a real entry was dropped this way at the old 0.85
# cutoff, leaving an empty cleaned_text/title/no-entities row).
#
# Hermetic: the node test stubs get_embedding + supabase, so no embedding API or
# DB is touched. Run directly (`python tests/test_dedup.py`) or via pytest.
import asyncio

import app.nodes.dedup as dedup_module
from app.nodes.dedup import dedup, is_duplicate_similarity

# ── Real calibration data (evals/dedup_threshold_calibration.py) ──────────────
# Cosine of a real unique entry vs an unrelated earlier entry that it was wrongly
# flagged as a duplicate of at the old 0.85 cutoff.
FALSE_POSITIVE_SIM = 0.8596
# Max cosine among 59 genuinely-distinct entries for one user (p99 = 0.8523).
# The threshold MUST sit above this or same-voice journal prose false-positives.
DISTINCT_PAIR_MAX = 0.8904
# A true accidental re-submit of the same text embeds ~identically.
TRUE_RESUBMIT_SIM = 0.985


# ── Hermetic stubs for the node-level test ───────────────────────────────────
class _FakeResp:
    def __init__(self, data):
        self.data = data


class _FakeTableQuery:
    """Swallows the duplicate-branch UPDATE chain: .update().eq().execute()."""
    def update(self, *args, **kwargs):
        return self

    def eq(self, *args, **kwargs):
        return self

    def execute(self):
        return _FakeResp([{"id": "stub"}])


class _FakeRPC:
    def __init__(self, match):
        self._match = match

    def execute(self):
        return _FakeResp([self._match] if self._match else [])


class _FakeSupabase:
    def __init__(self, match):
        self._match = match

    def rpc(self, name, params):
        return _FakeRPC(self._match)

    def table(self, name):
        return _FakeTableQuery()


async def _run_node(similarity: float) -> dict:
    """Run the real dedup node with a single mocked nearest-match at `similarity`."""
    match = {"id": "match-id-123", "auto_title": "An earlier entry", "similarity": similarity}
    original_embed = dedup_module.get_embedding
    original_supabase = dedup_module.supabase
    dedup_module.get_embedding = lambda *a, **k: _async_value([0.0] * 1536)
    dedup_module.supabase = _FakeSupabase(match)
    try:
        return await dedup({
            "raw_text": "a unique journal entry about today",
            "cleaned_text": "a unique journal entry about today",
            "user_id": "test-user",
            "entry_id": "entry-under-test",
            "dedup_check_result": None,
            "duplicate_of": None,
        })
    finally:
        dedup_module.get_embedding = original_embed
        dedup_module.supabase = original_supabase


def _async_value(value):
    async def _coro(*args, **kwargs):
        return value
    return _coro(value)


# ── Pure-function checks (sync, pytest-collectable) ───────────────────────────
def test_threshold_rejects_real_false_positive():
    assert not is_duplicate_similarity(FALSE_POSITIVE_SIM)
    assert not is_duplicate_similarity(DISTINCT_PAIR_MAX)


def test_threshold_still_catches_true_resubmit():
    assert is_duplicate_similarity(TRUE_RESUBMIT_SIM)
    assert is_duplicate_similarity(0.93)


# ── Node-level checks (exercise the real decision path, hermetically) ─────────
def test_dedup_node_passes_false_positive_through():
    result = asyncio.run(_run_node(FALSE_POSITIVE_SIM))
    assert result["dedup_check_result"] == "not_duplicate"


def test_dedup_node_flags_true_duplicate():
    result = asyncio.run(_run_node(TRUE_RESUBMIT_SIM))
    assert result["dedup_check_result"] == "duplicate"
    assert result["duplicate_of"] == "match-id-123"


# ── Script-style runner (repo convention: PASS/FAIL + SystemExit) ─────────────
def run_tests() -> None:
    checks = {
        "false_positive_0.86_not_flagged_duplicate (pure)": not is_duplicate_similarity(FALSE_POSITIVE_SIM),
        "distinct_pair_max_0.89_not_flagged_duplicate (pure)": not is_duplicate_similarity(DISTINCT_PAIR_MAX),
        "true_resubmit_0.985_flagged_duplicate (pure)": is_duplicate_similarity(TRUE_RESUBMIT_SIM),
        "node_passes_false_positive_through": (
            asyncio.run(_run_node(FALSE_POSITIVE_SIM))["dedup_check_result"] == "not_duplicate"
        ),
        "node_flags_true_duplicate": (
            asyncio.run(_run_node(TRUE_RESUBMIT_SIM))["dedup_check_result"] == "duplicate"
        ),
    }

    print("=" * 100)
    print("DEDUP THRESHOLD TESTS")
    for label, passed in checks.items():
        print(f"{label}: {'PASS' if passed else 'FAIL'}")

    if not all(checks.values()):
        raise SystemExit(1)


if __name__ == "__main__":
    run_tests()
