"""The router reports its refusal under four different field spellings.

The web UI normalizes all of them (`errorCode`, `error`, `error_code`, `errorcode`); a client that
watches only one treats a session loss arriving under another spelling as ordinary data.
"""

from unittest.mock import patch

import pytest
from test_features import (
    MOCK_AUTH_RESPONSE,
    MOCK_KEYS_RESPONSE,
    MOCK_LOGIN_RESPONSE,
    make_mock_response,
)

from tplink_modern import ArcherAX12
from tplink_modern.exceptions import FeatureUnavailableError
from tplink_modern.session import error_field

VALID_STATUS = {"success": True, "data": {"lan_macaddr": "AA-BB-CC-DD-EE-FF"}}


def test_error_field_reads_every_spelling() -> None:
    assert error_field({"errorcode": "timeout"}) == "timeout"
    assert error_field({"errorCode": "permission denied"}) == "permission denied"
    assert error_field({"error_code": "no such callback"}) == "no such callback"
    assert error_field({"error": "invalid args"}) == "invalid args"


def test_error_field_follows_the_ui_precedence() -> None:
    # Mirrors the bundle: errorCode || error || error_code || errorcode.
    mixed = {"errorcode": "a", "error_code": "b", "error": "c", "errorCode": "d"}
    assert error_field(mixed) == "d"
    assert error_field({"errorcode": "a", "error_code": "b", "error": "c"}) == "c"
    assert error_field({"errorcode": "a", "error_code": "b"}) == "b"
    assert error_field({"success": True, "errorCode": ""}) is None


def _router() -> ArcherAX12:
    return ArcherAX12(host="192.168.0.1", password="secret")


@pytest.mark.asyncio
async def test_expiry_under_a_second_spelling_still_re_authenticates() -> None:
    """`error_code: timeout` must trigger the single re-auth, not be returned as a successful read."""
    router = _router()
    expired = {"success": False, "error_code": "timeout"}
    calls = {"login": 0, "status": 0}

    async def respond(url, *args, **kwargs):
        link = str(url)
        if "form=keys" in link:
            calls["login"] += 1
            return make_mock_response(MOCK_KEYS_RESPONSE)
        if "form=auth" in link:
            return make_mock_response(MOCK_AUTH_RESPONSE)
        if "form=login" in link:
            return make_mock_response(MOCK_LOGIN_RESPONSE)
        calls["status"] += 1
        # First status sees a stolen stok, the retry after re-login succeeds.
        return make_mock_response(expired if calls["status"] == 1 else VALID_STATUS)

    with patch("httpx.AsyncClient.post", side_effect=respond):
        await router.login()
        status = await router.get_status()

    assert status.lan.macaddr == "AA-BB-CC-DD-EE-FF"
    assert calls["login"] == 2


@pytest.mark.asyncio
async def test_refusal_under_error_raises_feature_unavailable() -> None:
    router = _router()

    async def respond(url, *args, **kwargs):
        link = str(url)
        if "form=keys" in link:
            return make_mock_response(MOCK_KEYS_RESPONSE)
        if "form=auth" in link:
            return make_mock_response(MOCK_AUTH_RESPONSE)
        if "form=login" in link:
            return make_mock_response(MOCK_LOGIN_RESPONSE)
        if "admin/status?form=all" in link:
            return make_mock_response(VALID_STATUS)
        return make_mock_response({"success": False, "error": "no such callback"})

    with patch("httpx.AsyncClient.post", side_effect=respond):
        await router.login()
        with pytest.raises(FeatureUnavailableError):
            await router.read("admin/wireless", "wireless")
