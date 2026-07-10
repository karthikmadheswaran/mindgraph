"""
Invite-only allowlist unit tests (migration 021 + app/services/allowlist.py
+ the get_current_user gate in app/auth.py).

All Supabase calls are mocked — no real DB connection is needed.
"""
import time
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from app.services import allowlist


@pytest.fixture(autouse=True)
def fresh_cache():
    allowlist.invalidate_cache()
    yield
    allowlist.invalidate_cache()


def _select_result(rows):
    result = MagicMock()
    result.data = rows
    chain = MagicMock()
    chain.select.return_value = chain
    chain.execute.return_value = result
    return chain


# ---------------------------------------------------------------------------
# Membership
# ---------------------------------------------------------------------------


def test_allowed_email_passes():
    with patch.object(allowlist, "supabase") as mock_sb:
        mock_sb.table.return_value = _select_result([{"email": "invited@example.com"}])
        assert allowlist.is_email_allowed("invited@example.com") is True


def test_unknown_email_rejected():
    with patch.object(allowlist, "supabase") as mock_sb:
        mock_sb.table.return_value = _select_result([{"email": "invited@example.com"}])
        assert allowlist.is_email_allowed("stranger@example.com") is False


def test_missing_email_rejected_without_db_hit():
    with patch.object(allowlist, "supabase") as mock_sb:
        assert allowlist.is_email_allowed(None) is False
        assert allowlist.is_email_allowed("") is False
        mock_sb.table.assert_not_called()


def test_case_insensitive_both_sides():
    with patch.object(allowlist, "supabase") as mock_sb:
        mock_sb.table.return_value = _select_result([{"email": "Invited@Example.COM"}])
        assert allowlist.is_email_allowed("iNviTed@exaMple.com") is True


# ---------------------------------------------------------------------------
# Cache TTL
# ---------------------------------------------------------------------------


def test_cache_serves_within_ttl_without_refetch():
    with patch.object(allowlist, "supabase") as mock_sb:
        mock_sb.table.return_value = _select_result([{"email": "invited@example.com"}])
        allowlist.is_email_allowed("invited@example.com")
        allowlist.is_email_allowed("someone-else@example.com")
        assert mock_sb.table.call_count == 1


def test_cache_refetches_after_ttl_expiry():
    with patch.object(allowlist, "supabase") as mock_sb:
        mock_sb.table.return_value = _select_result([{"email": "invited@example.com"}])
        allowlist.is_email_allowed("invited@example.com")
        # Age the cache past the TTL, then check that a new invite is picked up.
        allowlist._cache["fetched_at"] = (
            time.monotonic() - allowlist.CACHE_TTL_SECONDS - 1
        )
        mock_sb.table.return_value = _select_result(
            [{"email": "invited@example.com"}, {"email": "new@example.com"}]
        )
        assert allowlist.is_email_allowed("new@example.com") is True
        assert mock_sb.table.call_count == 2


def test_fetch_failure_serves_stale_cache():
    with patch.object(allowlist, "supabase") as mock_sb:
        mock_sb.table.return_value = _select_result([{"email": "invited@example.com"}])
        allowlist.is_email_allowed("invited@example.com")
        allowlist._cache["fetched_at"] = (
            time.monotonic() - allowlist.CACHE_TTL_SECONDS - 1
        )
        mock_sb.table.side_effect = Exception("db down")
        assert allowlist.is_email_allowed("invited@example.com") is True
        assert allowlist.is_email_allowed("stranger@example.com") is False


def test_fetch_failure_with_no_cache_fails_open():
    # Table not migrated yet / DB error on cold start: gate must not lock
    # everyone (founder included) out — it opens and logs loudly instead.
    with patch.object(allowlist, "supabase") as mock_sb:
        mock_sb.table.side_effect = Exception("relation allowed_emails does not exist")
        assert allowlist.is_email_allowed("anyone@example.com") is True


# ---------------------------------------------------------------------------
# get_current_user gate (choke point in app/auth.py)
# ---------------------------------------------------------------------------


def _fake_credentials():
    creds = MagicMock()
    creds.credentials = "fake-jwt"
    return creds


@pytest.mark.anyio
async def test_get_current_user_rejects_unlisted_email_with_invite_only():
    from app import auth

    payload = {"sub": "user-123", "email": "stranger@example.com"}
    with patch.object(auth, "jwks_client") as mock_jwks, patch.object(
        auth.jwt, "decode", return_value=payload
    ), patch.object(auth, "is_email_allowed", return_value=False):
        mock_jwks.get_signing_key_from_jwt.return_value = MagicMock()
        with pytest.raises(HTTPException) as exc_info:
            await auth.get_current_user(credentials=_fake_credentials())
    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "invite_only"


@pytest.mark.anyio
async def test_get_current_user_passes_allowed_email():
    from app import auth

    payload = {"sub": "user-123", "email": "invited@example.com"}
    with patch.object(auth, "jwks_client") as mock_jwks, patch.object(
        auth.jwt, "decode", return_value=payload
    ), patch.object(auth, "is_email_allowed", return_value=True) as mock_gate:
        mock_jwks.get_signing_key_from_jwt.return_value = MagicMock()
        user_id = await auth.get_current_user(credentials=_fake_credentials())
    assert user_id == "user-123"
    mock_gate.assert_called_once_with("invited@example.com")
