from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

import app as api
from tplink_modern.exceptions import SessionExpiredError
from tplink_modern.models import REDACTED_PSK, OpenVpnConfig, PptpVpnConfig

MODULUS = "D1E79FF135D14E342D76185C23024E6DEAD4D6EC2C317A526C811E83538EA4E5ED8E1B0EEE5CE26E3C1B6A5F1FE11FA804F28B7E8821CA90AFA5B2F300DF99FDA27C9D2131E031EA11463C47944C05005EF4C1CE932D7F4A87C7563581D9F27F0C305023FCE94997EC7D790696E784357ED803A610EBB71B12A8BE5936429BFD"

KEYS_OK = {"success": True, "data": {"password": [MODULUS, "010001"]}}
AUTH_OK = {"success": True, "data": {"key": [MODULUS[:128], "010001"], "seq": 1}}
LOGIN_OK = {"success": True, "data": {"stok": "mocked_stok"}}

STATUS_OK = {
    "success": True,
    "data": {
        "cpu_usage": 0.12,
        "mem_usage": 0.4,
        "lan_ipv4_ipaddr": "192.168.0.1",
        "lan_ipv4_netmask": "255.255.255.0",
        "lan_macaddr": "AA-BB-CC-DD-EE-02",
        "lan_ipv4_dhcp_enable": "on",
        "wan_ipv4_ipaddr": "103.21.1.5",
        "wan_ipv4_netmask": "255.255.255.248",
        "wan_ipv4_gateway": "103.21.1.1",
        "wan_macaddr": "AA-BB-CC-DD-EE-03",
        "wan_ipv4_conntype": "dhcp",
        "wan_ipv4_pridns": "1.1.1.1",
        "wan_ipv4_uptime": "123456",
        "wireless_2g_ssid": "Goloka",
        "wireless_2g_enable": "on",
        "wireless_2g_macaddr": "AA-BB-CC-DD-EE-02",
        "wireless_2g_channel": "auto",
        "wireless_2g_current_channel": "6",
        "wireless_2g_encryption": "psk",
        "wireless_2g_psk_key": "password123",
        "wireless_2g_psk_cipher": "aes",
        "wireless_2g_htmode": "40",
        "wireless_5g_ssid": "Goloka-5G",
        "wireless_5g_enable": "on",
        "wireless_5g_channel": "auto",
        "wireless_5g_encryption": "psk",
        "wireless_5g_psk_key": "password123",
        "guest_isolate": "off",
        "guest_2g_enable": "off",
        "guest_2g_psk_key": "guestsecret",
        "guest_5g_enable": "off",
        "guest_5g_psk_key": "guestsecret",
        "access_devices_wired": [
            {"hostname": "nas", "ipaddr": "192.168.0.30", "macaddr": "00-11-22-33-44-55"}
        ],
        "access_devices_wireless_host": [
            {"hostname": "phone", "ipaddr": "192.168.0.41", "macaddr": "AA-BB-CC-DD-EE-01", "wire_type": "2.4G"}
        ],
    },
}

DHCP_LOAD = {
    "success": True,
    "data": [
        {"mac": "AA-BB-CC-DD-EE-01", "ip": "192.168.0.56", "enable": "on", "comment": "phone"}
    ],
}
OK = {"success": True, "data": {}}
WIFI_STATS = {
    "success": True,
    "data": [
        {"mac": "AA-BB-CC-DD-EE-01", "type": "2.4GHz", "encryption": "wpa2-psk", "rxpkts": 774, "txpkts": 1207}
    ],
}
OPENVPN_READ = {
    "success": True,
    "data": {"enabled": "on", "proto": "udp", "port": "1194", "serverip": "10.8.0.0", "mask": "255.255.255.0"},
}
PPTP_READ = {"success": True, "data": {"enabled": "off", "remoteip": "10.0.0.11-20"}}
VPN_CONNS = {
    "openvpn": {"success": True, "data": [{"username": "client1", "ipaddr": "10.8.0.6", "uptime": "00:05:23"}]},
    "pptp": {"success": True, "data": []},
}
FIRMWARE = {"success": True, "data": {"new_version": "", "hardware_version": "V1", "software_version": "1.0.0"}}


_MISSING = object()


def response_for(url: str, data: dict):
    """Return the router's canned JSON reply for a mocked CGI request."""
    if "login?form=keys" in url:
        return KEYS_OK
    if "login?form=auth" in url:
        return AUTH_OK
    if "login?form=login" in url:
        return LOGIN_OK
    if "admin/status?form=all" in url:
        return STATUS_OK
    if "admin/status?form=internet" in url:
        return OK
    if "admin/cloud_account?form=check_upgrade" in url:
        return FIRMWARE
    if "admin/dhcps?form=reservation" in url:
        return {"load": DHCP_LOAD, "insert": OK, "remove": OK}[data["operation"]]
    if "admin/wireless?form=statistics" in url:
        return WIFI_STATS
    if "admin/wireless?form=guest_2g5g" in url or "admin/wireless?form=wireless_2g" in url:
        return OK
    if "admin/openvpn?form=config" in url:
        return OK if data["operation"] == "write" else OPENVPN_READ
    if "admin/pptpd?form=config" in url:
        return OK if data["operation"] == "write" else PPTP_READ
    if "admin/vpnconn?form=config" in url:
        # The router answers one VPN type per request.
        vpntype = data.get("vpntype") or ""
        return VPN_CONNS.get(vpntype, {"success": True, "data": []})
    if "admin/system?form=reboot" in url:
        return OK
    if "admin/system?form=logout" in url:
        return OK
    raise AssertionError(f"unexpected router request: {url}")


def mock_response(payload):
    resp = AsyncMock()
    resp.json = lambda: payload
    resp.status_code = 200
    resp.raise_for_status = lambda: None
    return resp


def request_payload(calls, path_fragment, **fields):
    """The first recorded request body for a URL fragment matching the given fields."""
    return next(
        data
        for url, data in calls
        if path_fragment in url and all(data.get(k) == v for k, v in fields.items())
    )


@pytest.fixture
def router_requests():
    """Patch the HTTP layer and record every (url, form-data) pair the SDK sends."""
    calls = []

    async def fake_post(self, url, *args, **kwargs):
        payload = kwargs.get("data") or {}
        calls.append((str(url), payload))
        return mock_response(response_for(str(url), payload))

    with patch("httpx.AsyncClient.post", fake_post):
        yield calls


@pytest.fixture
def client(router_requests):
    with TestClient(api.app) as test_client:
        yield test_client


def test_server_logs_in_on_startup(client, router_requests):
    assert api.router is not None and api.router.session.stok == "mocked_stok"
    urls = [url for url, _ in router_requests]
    assert any("login?form=keys" in u for u in urls)
    assert any("login?form=login" in u for u in urls)
    assert any("admin/status?form=all" in u for u in urls)


def test_read_only_endpoints(client):
    status = client.get("/status")
    assert status.status_code == 200
    body = status.json()
    assert body["system"]["cpu_usage"] == 0.12
    assert body["lan"]["dhcp_enable"] is True
    assert body["wan"]["uptime"] == 123456
    assert body["wireless_2g"]["ssid"] == "Goloka"
    assert {c["macaddr"] for c in body["clients"]} == {"00-11-22-33-44-55", "AA-BB-CC-DD-EE-01"}

    clients = client.get("/clients").json()
    assert [c["wire_type"] for c in clients] == ["wired", "2.4G"]

    assert client.get("/firmware").json()["data"]["hardware_version"] == "V1"
    assert client.get("/network/lan").json()["ipaddr"] == "192.168.0.1"
    assert client.get("/network/wan").json()["gateway"] == "103.21.1.1"

    stats = client.get("/wifi/statistics").json()
    assert stats[0]["rx_packets"] == 774 and stats[0]["tx_packets"] == 1207

    assert client.get("/vpn/openvpn").json() == OpenVpnConfig(enable=True).model_dump()
    assert client.get("/vpn/pptp").json() == PptpVpnConfig(enable=False).model_dump()
    assert [c["username"] for c in client.get("/vpn/connections").json()] == ["client1"]


def test_status_redacts_wireless_keys_by_default(client):
    body = client.get("/status").json()
    assert body["wireless_2g"]["psk_key"] == REDACTED_PSK
    assert body["wireless_5g"]["psk_key"] == REDACTED_PSK
    assert body["guest"]["guest_2g_psk_key"] == REDACTED_PSK
    assert body["guest"]["guest_5g_psk_key"] == REDACTED_PSK
    assert "password123" not in client.get("/status").text
    # Non-secret wireless details stay useful.
    assert body["wireless_2g"]["ssid"] == "Goloka"
    assert body["wireless_2g"]["encryption"] == "psk"


def test_status_returns_keys_only_when_opted_in(client):
    body = client.get("/status", params={"include_secrets": True}).json()
    assert body["wireless_2g"]["psk_key"] == "password123"
    assert body["guest"]["guest_2g_psk_key"] == "guestsecret"


def test_redaction_does_not_leak_into_wifi_writes(client, router_requests):
    """Redacting a response must not poison the read-modify-write path with the placeholder."""
    assert client.get("/status").json()["wireless_2g"]["psk_key"] == REDACTED_PSK

    response = client.post("/wifi/config", json={"band": "2g", "ssid": "Goloka_New"})
    assert response.status_code == 200

    write = request_payload(router_requests, "admin/wireless?form=wireless_2g", operation="write")
    assert write["psk_key"] == "password123"


def test_dhcp_reservation_lifecycle(client, router_requests):
    assert [r["macaddr"] for r in client.get("/network/dhcp/reservations").json()] == ["AA-BB-CC-DD-EE-01"]

    add = client.post(
        "/network/dhcp/reservations",
        json={"macaddr": "00:11:22:33:44:55", "ipaddr": "192.168.0.99", "name": "nas", "enable": True},
    )
    assert add.status_code == 200 and add.json() == {"success": True}

    insert = request_payload(router_requests, "admin/dhcps", operation="insert")
    assert '"mac": "00-11-22-33-44-55"' in insert["new"], "MAC must be normalized for the router"

    delete = client.delete("/network/dhcp/reservations/AA-BB-CC-DD-EE-01")
    assert delete.status_code == 200 and delete.json() == {"success": True}

    # The router has no delete-by-MAC call, so the SDK resolves the list index first.
    remove = request_payload(router_requests, "admin/dhcps", operation="remove")
    assert remove["key"] == "AA-BB-CC-DD-EE-01" and remove["index"] == 0


def test_delete_unknown_reservation_returns_500(client):
    response = client.delete("/network/dhcp/reservations/99-99-99-99-99-99")
    assert response.status_code == 500
    assert "not found" in response.json()["detail"]


def test_wifi_config_is_read_modify_write(client, router_requests):
    response = client.post("/wifi/config", json={"band": "2g", "ssid": "Goloka_New"})
    assert response.status_code == 200 and response.json() == {"success": True}

    write = request_payload(router_requests, "admin/wireless?form=wireless_2g", operation="write")
    assert write["ssid"] == "Goloka_New"
    # Untouched fields are re-sent from the router's current values, not blanked out.
    assert write["psk_key"] == "password123"
    assert write["encryption"] == "psk"
    assert write["enable"] == "on"
    assert write["channel"] == "auto"
    assert write["htmode"] == "40"


def test_wifi_config_rejects_unknown_band(client):
    response = client.post("/wifi/config", json={"band": "6g"})
    assert response.status_code == 400
    assert "2g" in response.json()["detail"]


def test_guest_wifi_toggle(client, router_requests):
    response = client.post("/wifi/guest", json={"enable": True, "isolate": True})
    assert response.status_code == 200 and response.json() == {"success": True}

    write = request_payload(router_requests, "admin/wireless?form=guest_2g5g", operation="write")
    assert write == {"operation": "write", "enable": "on", "isolate": "on"}


def test_vpn_config_round_trip(client, router_requests):
    response = client.post("/vpn/openvpn", json=OpenVpnConfig(enable=False, proto="tcp", port=1195).model_dump())
    assert response.status_code == 200 and response.json() == {"success": True}

    write = request_payload(router_requests, "admin/openvpn?form=config", operation="write")
    assert write["enabled"] == "off" and write["proto"] == "tcp" and write["port"] == "1195"

    response = client.post("/vpn/pptp", json=PptpVpnConfig(enable=True, remoteip="10.0.0.50-60").model_dump())
    assert response.status_code == 200 and response.json() == {"success": True}

    write = request_payload(router_requests, "admin/pptpd?form=config", operation="write")
    assert write["enabled"] == "on" and write["remoteip"] == "10.0.0.50-60"


def test_reboot(client, router_requests):
    response = client.post("/reboot")
    assert response.status_code == 200 and response.json() == {"success": True}
    assert any("admin/system?form=reboot" in url for url, _ in router_requests)


def test_endpoints_answer_503_without_a_router_client(client, monkeypatch):
    monkeypatch.setattr(api, "router", None)
    response = client.get("/status")
    assert response.status_code == 503
    assert "not initialized" in response.json()["detail"]


def test_openapi_documents_every_route(client):
    paths = client.get("/openapi.json").json()["paths"]
    assert set(paths) == {
        "/status",
        "/clients",
        "/firmware",
        "/network/lan",
        "/network/wan",
        "/network/dhcp/reservations",
        "/network/dhcp/reservations/{macaddr}",
        "/wifi/config",
        "/wifi/guest",
        "/wifi/statistics",
        "/vpn/openvpn",
        "/vpn/pptp",
        "/vpn/connections",
        "/reboot",
    }


def test_session_expires_mid_request(client, router_requests):
    """A stale stok must trigger one re-login and a retried request, not an error."""
    session = api.router.session
    original = session.post
    stale = 1

    async def flaky_post(path, data, **kwargs):
        nonlocal stale
        if stale:
            stale -= 1
            raise SessionExpiredError("Session expired or permission denied")
        return await original(path, data, **kwargs)

    session.post = flaky_post
    before = len(router_requests)
    response = client.get("/status")
    assert response.status_code == 200
    assert response.json()["lan"]["ipaddr"] == "192.168.0.1"
    assert stale == 0

    # The retry re-authenticates from scratch, then replays the original request.
    reauth = [url for url, _ in router_requests[before:]]
    assert any("login?form=keys" in u for u in reauth)
    assert any("login?form=login" in u for u in reauth)
    assert reauth[-1] == "/cgi-bin/luci/;stok=mocked_stok/admin/status?form=all"
