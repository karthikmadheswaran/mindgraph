"""Tests for the invite-access request flow (migration 023 + POST /access-requests
+ app/services/access_request_service.py).

Covers: happy-path insert, email validation, note length cap, rate limiting
(3/hour/IP), duplicate idempotency, and the table-absent fail-safe. RLS
(anon cannot READ the table) is asserted at the SQL layer in migration 023 and
verified live at deploy time — see the report; it can't be exercised against a
mocked supabase here, so this suite locks the app-layer contract.

All Supabase calls are mocked; no real DB connection needed.
"""
import os

os.environ.setdefault("SUPABASE_URL", "http://localhost")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-key")

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services import access_request_service


def _allow_rl(allow=True):
    """try_rate_limit rpc side-effect for the access-request IP key."""
    def side_effect(name, params=None, *a, **k):
        r = MagicMock()
        r.data = allow
        chain = MagicMock()
        chain.execute.return_value = r
        return chain
    return side_effect


@pytest.fixture
def client():
    return TestClient(app)


# ---------------------------------------------------------------------------
# Route: happy path
# ---------------------------------------------------------------------------


def test_insert_path_returns_received(client):
    with patch("app.dependencies.rate_limit.supabase") as rl_sb, patch.object(
        access_request_service, "supabase"
    ) as svc_sb:
        rl_sb.rpc.side_effect = _allow_rl(True)
        insert_chain = MagicMock()
        svc_sb.table.return_value.insert.return_value = insert_chain

        resp = client.post(
            "/access-requests",
            json={"email": "New.Person@Example.com", "note": "curious about journaling"},
        )

    assert resp.status_code == 200
    assert resp.json() == {"status": "received"}
    # Email normalized to lowercase before insert.
    payload = svc_sb.table.return_value.insert.call_args[0][0]
    assert payload["email"] == "new.person@example.com"
    assert payload["note"] == "curious about journaling"


def test_invalid_email_rejected_422(client):
    with patch("app.dependencies.rate_limit.supabase") as rl_sb:
        rl_sb.rpc.side_effect = _allow_rl(True)
        resp = client.post("/access-requests", json={"email": "not-an-email"})
    assert resp.status_code == 422


def test_note_over_280_rejected_422(client):
    with patch("app.dependencies.rate_limit.supabase") as rl_sb:
        rl_sb.rpc.side_effect = _allow_rl(True)
        resp = client.post(
            "/access-requests",
            json={"email": "x@example.com", "note": "z" * 281},
        )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Rate limit (3/hour/IP)
# ---------------------------------------------------------------------------


def test_rate_limited_returns_429(client):
    with patch("app.dependencies.rate_limit.supabase") as rl_sb:
        rl_sb.rpc.side_effect = _allow_rl(False)  # limit exhausted
        resp = client.post("/access-requests", json={"email": "x@example.com"})
    assert resp.status_code == 429


def test_rate_limit_keys_on_access_request_bucket(client):
    seen = {}

    def side_effect(name, params=None, *a, **k):
        seen["key"] = (params or {}).get("p_key")
        seen["limit"] = (params or {}).get("p_limit")
        r = MagicMock()
        r.data = True
        chain = MagicMock()
        chain.execute.return_value = r
        return chain

    with patch("app.dependencies.rate_limit.supabase") as rl_sb, patch.object(
        access_request_service, "supabase"
    ) as svc_sb:
        rl_sb.rpc.side_effect = side_effect
        svc_sb.table.return_value.insert.return_value = MagicMock()
        client.post("/access-requests", json={"email": "x@example.com"})

    assert seen["key"].endswith(":access_request")
    assert seen["limit"] == 3


# ---------------------------------------------------------------------------
# Service layer: idempotency + fail-safe
# ---------------------------------------------------------------------------


def test_duplicate_email_is_idempotent_no_raise():
    with patch.object(access_request_service, "supabase") as svc_sb, patch.object(
        access_request_service, "sentry_sdk"
    ) as sentry:
        svc_sb.table.return_value.insert.return_value.execute.side_effect = Exception(
            'duplicate key value violates unique constraint '
            '"idx_access_requests_email_lower"'
        )
        # Must not raise, and must NOT report a duplicate as an error.
        access_request_service.submit_access_request("dupe@example.com", None)
        sentry.capture_exception.assert_not_called()


def test_table_absent_fails_safe_and_reports_to_sentry():
    with patch.object(access_request_service, "supabase") as svc_sb, patch.object(
        access_request_service, "sentry_sdk"
    ) as sentry:
        svc_sb.table.return_value.insert.return_value.execute.side_effect = Exception(
            "relation \"access_requests\" does not exist"
        )
        # No raise (user still sees "received"), but the error is captured.
        access_request_service.submit_access_request("x@example.com", None)
        sentry.capture_exception.assert_called_once()


def test_client_ip_prefers_forwarded_for():
    from unittest.mock import MagicMock

    from app.dependencies.rate_limit import _client_ip

    # Railway populates X-Forwarded-For with "client, proxy…"; take the client.
    req = MagicMock()
    req.headers = {"x-forwarded-for": "203.0.113.7, 10.0.0.1"}
    req.client.host = "10.0.0.1"  # proxy peer — must NOT be used
    assert _client_ip(req) == "203.0.113.7"

    # No header (local/dev): fall back to the peer address.
    req2 = MagicMock()
    req2.headers = {}
    req2.client.host = "127.0.0.1"
    assert _client_ip(req2) == "127.0.0.1"


def test_note_truncated_to_280_at_service_layer():
    with patch.object(access_request_service, "supabase") as svc_sb:
        insert_chain = MagicMock()
        svc_sb.table.return_value.insert.return_value = insert_chain
        access_request_service.submit_access_request("x@example.com", "z" * 500)
        payload = svc_sb.table.return_value.insert.call_args[0][0]
        assert len(payload["note"]) == 280
