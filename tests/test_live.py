"""Live checks against a real Archer AX12.

Skipped unless TPLINK_LIVE=1, because they need the router and credentials from .env. They only
issue reads and logins -- nothing here changes router configuration, and reboot is never called.

    TPLINK_LIVE=1 pytest -m live
"""
import asyncio
import os

import httpx
import pytest
from fastapi.testclient import TestClient

import app as api
from tplink_modern import ArcherAX12
from tplink_modern.models import (
    ClientDevice,
    DhcpReservation,
    LanSettings,
    OpenVpnConfig,
    PptpVpnConfig,
    REDACTED_PSK,
    RouterStatus,
    VpnConnection,
    WanSettings,
    WirelessCapabilities,
    WirelessClientStats,
)

pytestmark = pytest.mark.live

RUN_LIVE = os.environ.get("TPLINK_LIVE") == "1"
skip_reason = "set TPLINK_LIVE=1 to run checks against the real router"

READ_ROUTES = [
    ("/status", RouterStatus),
    ("/clients", ClientDevice),
    ("/network/lan", LanSettings),
    ("/network/wan", WanSettings),
    ("/network/dhcp/reservations", DhcpReservation),
    ("/wifi/statistics", WirelessClientStats),
    ("/wifi/capabilities", WirelessCapabilities),
    ("/vpn/openvpn", OpenVpnConfig),
    ("/vpn/pptp", PptpVpnConfig),
    ("/vpn/connections", VpnConnection),
]

if not RUN_LIVE:
    pytest.skip(skip_reason, allow_module_level=True)


@pytest.fixture(scope="module")
def live_client():
    with TestClient(api.app) as client:
        yield client


@pytest.mark.parametrize("route, model", READ_ROUTES)
def test_read_route_matches_its_model(live_client, route, model):
    """Every documented read route must answer 200 with data the declared model accepts."""
    response = live_client.get(route)
    assert response.status_code == 200, f"{route} -> {response.status_code} {response.text[:200]}"

    body = response.json()
    rows = body if isinstance(body, list) else [body]
    for row in rows:
        model.model_validate(row)


def test_status_hides_the_wifi_keys(live_client):
    body = live_client.get("/status").json()
    assert body["wireless_2g"]["psk_key"] == REDACTED_PSK
    assert body["wireless_5g"]["psk_key"] == REDACTED_PSK
    assert REDACTED_PSK not in live_client.get("/status").text.replace('"***redacted***"', "")


def test_status_can_still_show_them(live_client):
    body = live_client.get("/status", params={"include_secrets": True}).json()
    assert body["wireless_2g"]["psk_key"] != REDACTED_PSK


def test_session_survives_being_hijacked(live_client):
    """Proves the single-flight re-auth on real hardware.

    Logging in elsewhere evicts the server's stok -- the same thing the web UI does when an
    operator opens the admin page. Two concurrent requests must then share one re-login and
    both succeed, rather than each logging in and knocking the other's token out.
    """

    async def scenario():
        squatter = ArcherAX12(host=api.TPLINK_HOST, password=api.TPLINK_PASSWORD)
        await squatter.login()  # evicts the stok the server is holding
        await squatter.session.client.aclose()  # close without logout, so we do not evict again

        transport = httpx.ASGITransport(app=api.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            results = await asyncio.gather(client.get("/status"), client.get("/clients"))
        return results

    first, second = asyncio.run(scenario())
    assert first.status_code == 200, first.text[:200]
    assert second.status_code == 200, second.text[:200]


def test_firmware_check_reports_a_count(live_client):
    body = live_client.get("/firmware").json()
    assert isinstance(body["update_number"], int)


def test_capabilities_describe_this_unit(live_client):
    caps = live_client.get("/wifi/capabilities").json()
    assert caps["country"]
    assert caps["channels_2g"], "the router must report usable 2.4G channels"
    assert all(channel.isdigit() for channel in caps["channels_2g"])
