"""Regression: analytics.track must speak the INSTALLED posthog client's
capture() signature.

The drift-pick suite (test_drift_pick.py) mocks track() itself, so a
posthog-python signature break passes every unit test while prod drops 100%
of events: posthog >= 6 moved distinct_id out of the positional args
(capture(event, **kwargs)), the old 3-positional call raises TypeError, and
BOTH the library's internal exception guard and track()'s by-design swallow
hide it. Exactly this happened with the unpinned `posthog` requirement.

Hermetic: the client is real, but before_send appends each event to a list
and returns None, which drops it before the network queue — nothing is ever
sent anywhere.
"""
import os

os.environ.setdefault("SUPABASE_URL", "http://localhost")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-key")

import pytest
from posthog import Posthog

import app.services.analytics as analytics


@pytest.fixture
def captured(monkeypatch):
    events = []
    client = Posthog(
        "phc_test-not-a-real-key",
        host="http://127.0.0.1:9",  # unroutable on purpose; nothing is sent anyway
        before_send=lambda e: events.append(e) or None,  # None -> event dropped pre-queue
    )
    monkeypatch.setattr(analytics, "_client", client)
    yield events
    client.shutdown()


@pytest.mark.parametrize(
    "event", ["drift_card_served", "intention_resolved", "intention_dismissed"]
)
def test_track_reaches_real_posthog_client(captured, event):
    analytics.track("user-1", event, {"intention_id": "i-1", "days_since": 30})

    assert len(captured) == 1, (
        "track() produced no capture on the real client — signature mismatch "
        "with the installed posthog version"
    )
    assert captured[0]["event"] == event
    assert captured[0]["distinct_id"] == "user-1"
    assert captured[0]["properties"]["intention_id"] == "i-1"
    assert captured[0]["properties"]["days_since"] == 30


def test_track_without_properties(captured):
    analytics.track("user-1", "entry_submitted")
    assert len(captured) == 1
    assert captured[0]["event"] == "entry_submitted"


def test_track_noops_without_api_key(monkeypatch):
    # Documents the prod flag: no POSTHOG_API_KEY -> get_posthog() is None ->
    # every event silently no-ops. Railway MUST carry POSTHOG_API_KEY.
    monkeypatch.setattr(analytics, "_client", None)
    monkeypatch.delenv("POSTHOG_API_KEY", raising=False)
    analytics.track("user-1", "drift_card_served", {})  # must not raise
    assert analytics.get_posthog() is None
