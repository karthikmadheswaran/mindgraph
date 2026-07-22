"""Tests for the server-side signup gate (POST /auth/signup).

Signup is proxied through the backend so the allowlist check runs BEFORE any
GoTrue call: a non-invited email must never create an auth user or send a
confirmation email. Covers: the not_invited rejection, allowlisted
passthrough, the 5/hour/IP rate-limit bucket, GoTrue error passthrough,
missing-anon-key 503, and the loud fail-open path when the allowlist is
unreachable.

All Supabase/GoTrue calls are mocked; no real DB or network needed.
"""
import os

os.environ.setdefault("SUPABASE_URL", "http://localhost")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-key")
os.environ.setdefault("SUPABASE_ANON_KEY", "test-anon-key")

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

import app.main as main
from app.main import app
from app.services import allowlist


@pytest.fixture(autouse=True)
def fresh_allowlist_cache():
    allowlist.invalidate_cache()
    yield
    allowlist.invalidate_cache()


@pytest.fixture(autouse=True)
def anon_key_configured():
    # app.main may have been imported by another test module before this one
    # set the env var, so patch the module global rather than the environment.
    # Tests that need it absent (the 503 path) re-patch it to None inline.
    with patch.object(main, "SUPABASE_ANON_KEY", "test-anon-key"):
        yield


@pytest.fixture
def client():
    return TestClient(app)


def _allow_rl(allow=True):
    """try_rate_limit rpc side-effect for the signup IP key."""
    def side_effect(name, params=None, *a, **k):
        r = MagicMock()
        r.data = allow
        chain = MagicMock()
        chain.execute.return_value = r
        return chain
    return side_effect


def _allowlist_rows(rows):
    result = MagicMock()
    result.data = rows
    chain = MagicMock()
    chain.select.return_value = chain
    chain.execute.return_value = result
    return chain


INVITED = [{"email": "invited@example.com"}]


# ---------------------------------------------------------------------------
# Gate: allowlist checked BEFORE any GoTrue call
# ---------------------------------------------------------------------------


def test_non_allowlisted_email_rejected_not_invited(client):
    with patch("app.dependencies.rate_limit.supabase") as rl_sb, patch.object(
        allowlist, "supabase"
    ) as al_sb, patch.object(
        main, "_forward_signup_to_gotrue", new_callable=AsyncMock
    ) as forward:
        rl_sb.rpc.side_effect = _allow_rl(True)
        al_sb.table.return_value = _allowlist_rows(INVITED)

        resp = client.post(
            "/auth/signup",
            json={"email": "stranger@example.com", "password": "hunter22"},
        )

    assert resp.status_code == 403
    assert resp.json()["detail"] == "not_invited"
    # The whole point: GoTrue must never be reached → no auth user, no email.
    forward.assert_not_called()


def test_allowlisted_email_forwards_to_gotrue(client):
    with patch("app.dependencies.rate_limit.supabase") as rl_sb, patch.object(
        allowlist, "supabase"
    ) as al_sb, patch.object(
        main, "_forward_signup_to_gotrue", new_callable=AsyncMock
    ) as forward:
        rl_sb.rpc.side_effect = _allow_rl(True)
        al_sb.table.return_value = _allowlist_rows(INVITED)
        forward.return_value = (200, None)

        resp = client.post(
            "/auth/signup",
            json={"email": "Invited@Example.com", "password": "hunter22"},
        )

    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
    forward.assert_awaited_once_with("Invited@Example.com", "hunter22")


def test_invalid_email_rejected_422(client):
    with patch("app.dependencies.rate_limit.supabase") as rl_sb:
        rl_sb.rpc.side_effect = _allow_rl(True)
        resp = client.post(
            "/auth/signup", json={"email": "not-an-email", "password": "hunter22"}
        )
    assert resp.status_code == 422


def test_short_password_rejected_422(client):
    with patch("app.dependencies.rate_limit.supabase") as rl_sb:
        rl_sb.rpc.side_effect = _allow_rl(True)
        resp = client.post(
            "/auth/signup", json={"email": "x@example.com", "password": "abc"}
        )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Rate limit (5/hour/IP, own bucket)
# ---------------------------------------------------------------------------


def test_rate_limited_returns_429(client):
    with patch("app.dependencies.rate_limit.supabase") as rl_sb:
        rl_sb.rpc.side_effect = _allow_rl(False)  # limit exhausted
        resp = client.post(
            "/auth/signup", json={"email": "x@example.com", "password": "hunter22"}
        )
    assert resp.status_code == 429


def test_rate_limit_keys_on_signup_bucket(client):
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
        allowlist, "supabase"
    ) as al_sb, patch.object(
        main, "_forward_signup_to_gotrue", new_callable=AsyncMock
    ) as forward:
        rl_sb.rpc.side_effect = side_effect
        al_sb.table.return_value = _allowlist_rows(INVITED)
        forward.return_value = (200, None)
        client.post(
            "/auth/signup",
            json={"email": "invited@example.com", "password": "hunter22"},
        )

    assert seen["key"].endswith(":signup")
    assert seen["limit"] == 5


# ---------------------------------------------------------------------------
# GoTrue passthrough + config guard
# ---------------------------------------------------------------------------


def test_gotrue_error_passthrough(client):
    with patch("app.dependencies.rate_limit.supabase") as rl_sb, patch.object(
        allowlist, "supabase"
    ) as al_sb, patch.object(
        main, "_forward_signup_to_gotrue", new_callable=AsyncMock
    ) as forward:
        rl_sb.rpc.side_effect = _allow_rl(True)
        al_sb.table.return_value = _allowlist_rows(INVITED)
        forward.return_value = (429, "over_email_send_rate_limit")

        resp = client.post(
            "/auth/signup",
            json={"email": "invited@example.com", "password": "hunter22"},
        )

    assert resp.status_code == 429
    assert resp.json()["detail"] == "over_email_send_rate_limit"


def test_missing_anon_key_returns_503(client):
    # Real _forward_signup_to_gotrue, but no anon key configured: the route
    # must fail closed with a distinct code instead of forwarding.
    with patch("app.dependencies.rate_limit.supabase") as rl_sb, patch.object(
        allowlist, "supabase"
    ) as al_sb, patch.object(main, "SUPABASE_ANON_KEY", None):
        rl_sb.rpc.side_effect = _allow_rl(True)
        al_sb.table.return_value = _allowlist_rows(INVITED)

        resp = client.post(
            "/auth/signup",
            json={"email": "invited@example.com", "password": "hunter22"},
        )

    assert resp.status_code == 503
    assert resp.json()["detail"] == "signup_unavailable"


@pytest.mark.anyio
async def test_forward_uses_anon_key_and_gotrue_signup_url():
    captured = {}

    class _FakeResp:
        status_code = 200

        @staticmethod
        def json():
            return {"id": "new-user"}

    class _FakeClient:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def post(self, url, headers=None, json=None):
            captured["url"] = url
            captured["headers"] = headers
            captured["json"] = json
            return _FakeResp()

    with patch.object(main, "SUPABASE_ANON_KEY", "anon-test-key"), patch.object(
        main.httpx, "AsyncClient", _FakeClient
    ):
        status_code, error_code = await main._forward_signup_to_gotrue(
            "invited@example.com", "hunter22"
        )

    assert status_code == 200
    assert error_code is None
    assert captured["url"].endswith("/auth/v1/signup")
    # Anon key, NOT the service-role key: forwarded signup must be
    # byte-for-byte what the browser used to send.
    assert captured["headers"]["apikey"] == "anon-test-key"
    assert captured["json"] == {"email": "invited@example.com", "password": "hunter22"}


# ---------------------------------------------------------------------------
# Fail-open (allowlist unreachable) — loud by requirement
# ---------------------------------------------------------------------------


def test_signup_gate_fails_open_when_allowlist_unreachable(client, caplog):
    with patch("app.dependencies.rate_limit.supabase") as rl_sb, patch.object(
        allowlist, "supabase"
    ) as al_sb, patch.object(
        main, "_forward_signup_to_gotrue", new_callable=AsyncMock
    ) as forward:
        rl_sb.rpc.side_effect = _allow_rl(True)
        al_sb.table.side_effect = Exception("relation allowed_emails does not exist")
        forward.return_value = (200, None)

        with caplog.at_level("ERROR", logger="app.main"):
            resp = client.post(
                "/auth/signup",
                json={"email": "anyone@example.com", "password": "hunter22"},
            )

    # Fail-open: signup proceeds (founder must never be locked out by a DB
    # blip), but the gate being open MUST be loud in the logs.
    assert resp.status_code == 200
    forward.assert_awaited_once()
    assert any("FAILING OPEN" in rec.getMessage() for rec in caplog.records)
