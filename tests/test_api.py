import asyncio
import json
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

import app as api
from tplink_modern import ArcherAX12
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
# Field names and values copied from a live read of these forms on firmware 1.10.2.
GUEST_2G = {
    "success": True,
    "data": {
        "enable": "off", "ssid": "TP-Link", "encryption": "psk_sae",
        "psk_cipher": "", "psk_key": "", "psk_version": "", "hidden": "off",
    },
}
GUEST_5G = {
    "success": True,
    "data": {
        "enable": "off", "ssid": "GuestExample", "encryption": "psk_sae",
        "psk_cipher": "", "psk_key": "", "psk_version": "", "hidden": "off",
    },
}
GUEST_PERMISSIONS = {"success": True, "data": {"access": "off", "isolate": "off"}}

# Device rows copied from a live load of admin/access_control?form=black_devices.
ACCESS_BLACK_DEVICES = [
    {
        "conn_type": "wireless", "guest": "NON_GUEST", "host": "NON_HOST",
        "ipaddr": "192.168.0.118", "mac": "AA-BB-CC-DD-EE-06", "name": "Lava",
        "raw_conn_type": "2.4G", "type": "Mobile",
    },
    {
        "conn_type": "wireless", "guest": "GUEST", "host": "NON_HOST",
        "ipaddr": "192.168.0.43", "mac": "AA-BB-CC-DD-EE-05", "name": "Tab-A7",
        "raw_conn_type": "5G", "type": "Mobile",
    },
]
ACCESS_WHITE_DEVICES = list(ACCESS_BLACK_DEVICES)
ACCESS_ENABLE = {"success": True, "data": {"enable": "off", "host_mac": "AA-BB-CC-DD-EE-04"}}
ACCESS_MODE = {"success": True, "data": {"access_mode": "black"}}
# The router reports saved wake targets plus its own limit in an `others` sibling.
WOL_LOAD = {
    "success": True,
    "data": [{"key": "dev1", "name": "server", "mac": "AA-BB-CC-DD-EE-07"}],
    "others": {"max_rules": 8},
}
DMZ_READ = {"success": True, "data": {"enable": "off", "ipaddr": ""}}
# This unit has no rules configured, so a row shape with an unrecognised field stands in for it.
VS_RULES = [{"key": "rule1", "name": "ssh", "enable": "on", "protocol": "tcp", "eport": "2222"}]
# Copied from a live read of admin/wireless?form=region on this unit.
REGION_CAPABILITY = {
    "success": True,
    "data": {
        "country": "US",
        "region_list": {},
        "support_smart_connect": "yes",
        "support_wireless_schedule": "yes",
        "capability": {
            "channel_2g": [str(n) for n in range(1, 12)],
            "channel_5g": ["36", "40", "44", "48", "149", "153", "157", "161", "165"],
            "channel_6g": {},
            "hwmode_2g": ["n", "gn", "bgn"],
            "hwmode_5g": ["anac_5", "anacax_5"],
            "htmode_2g": ["20", "40"],
            "htmode_5g": ["20", "40", "80"],
        },
    },
}
ACCESS_TABLES = {
    "black_devices": ACCESS_BLACK_DEVICES,
    "white_devices": ACCESS_WHITE_DEVICES,
    # An empty list comes back as {} on this firmware; one entry as a list.
    "black_list": [{"mac": "AA-BB-CC-DD-EE-01", "name": "laptop"}],
    "white_list": [],
}
FIRMWARE = {"success": True, "data": {"update_number": "1"}}


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
    if "admin/wol?form=device" in url:
        return WOL_LOAD if data.get("operation") == "load" else OK
    if "admin/nat?form=dmz" in url:
        return DMZ_READ if data.get("operation") == "read" else OK
    if "admin/nat?form=vs" in url or "admin/nat?form=pt" in url:
        return {"success": True, "data": VS_RULES} if data.get("operation") == "load" else OK
    if "admin/access_control" in url:
        form = url.split("?form=")[1]
        operation = data.get("operation")
        if operation == "read":
            return ACCESS_ENABLE if form == "enable" else ACCESS_MODE
        if operation == "load":
            return {"success": True, "data": ACCESS_TABLES.get(form, [])}
        return OK
    if "admin/wireless?form=region" in url:
        return REGION_CAPABILITY
    if "admin/wireless?form=statistics" in url:
        return WIFI_STATS
    if "admin/wireless" in url and "?form=guest" in url:
        form = url.split("?form=")[1]
        if data.get("operation") == "read":
            return {"guest_2g": GUEST_2G, "guest_5g": GUEST_5G, "guest": GUEST_PERMISSIONS}.get(form)
        return OK
    if "admin/wireless?form=wireless_2g" in url:
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


def request_payload(calls, path_fragment, form=None, **fields):
    """The first recorded request body for a URL, optionally requiring an exact form."""
    return next(
        data
        for url, data in calls
        if path_fragment in url
        and (form is None or url.endswith(f"?form={form}"))
        and all(data.get(k) == v for k, v in fields.items())
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

    assert client.get("/firmware").json()["update_number"] == 1
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


def test_delete_unknown_reservation_returns_404(client):
    response = client.delete("/network/dhcp/reservations/99-99-99-99-99-99")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"]


def test_form_the_firmware_lacks_reports_501(client, monkeypatch):
    """'no such callback' means this firmware has no such feature - not a transient failure."""

    async def refuse(path, data, **kwargs):
        return {"success": False, "errorcode": "no such callback"}

    monkeypatch.setattr(api.router.session, "post", refuse)
    response = client.get("/wifi/statistics")
    assert response.status_code == 501
    assert response.json()["errorcode"] == "no such callback"


def test_router_refusal_reports_502_with_the_router_reason(client, monkeypatch):
    async def refuse(path, data, **kwargs):
        return {"success": False, "errorcode": "permission error"}

    monkeypatch.setattr(api.router.session, "post", refuse)
    response = client.post("/reboot")
    assert response.status_code == 502
    assert "admin/system?form=reboot" in response.json()["detail"]
    assert response.json()["errorcode"] == "permission error"


def test_write_failure_is_not_reported_as_success(client, monkeypatch):
    """A refused write used to return {"success": false}; it must never look like a success."""

    async def refuse(path, data, **kwargs):
        return {"success": False, "errorcode": "parameter value invalid"}

    monkeypatch.setattr(api.router.session, "post", refuse)
    response = client.post("/wifi/guest", json={"enable": True})
    assert response.status_code == 502
    assert "success" not in response.json()


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


def test_guest_toggle_writes_each_band_form(client, router_requests):
    response = client.post("/wifi/guest", json={"enable": True, "isolate": True})
    assert response.status_code == 200 and response.json() == {"success": True}

    band = request_payload(router_requests, "admin/wireless?form=guest_2g", operation="write")
    assert band["enable"] == "on"
    # Untouched fields are echoed back from the router rather than dropped.
    assert band["ssid"] == "TP-Link"
    assert band["psk_key"] == ""
    assert band["encryption"] == "psk_sae"
    assert request_payload(router_requests, "admin/wireless?form=guest_5g", operation="write")["ssid"] == "GuestExample"

    # Isolation lives on its own form on this firmware, alongside the guest-access flag.
    perms = request_payload(router_requests, "admin/wireless", form="guest", operation="write")
    assert perms["isolate"] == "on" and perms["access"] == "off"
    assert not any("guest_2g5g" in url for url, _ in router_requests)


def test_guest_ssid_and_password_apply_to_both_bands(client, router_requests):
    response = client.post("/wifi/guest", json={"ssid": "Guests", "password": "guestpass1"})
    assert response.status_code == 200

    for form in ("guest_2g", "guest_5g"):
        write = request_payload(router_requests, f"admin/wireless?form={form}", operation="write")
        assert write["ssid"] == "Guests"
        assert write["psk_key"] == "guestpass1"
        assert write["enable"] == "off", "setting a key must not switch the network on"

    assert not [data for url, data in router_requests
                if url.endswith("?form=guest") and data.get("operation") == "write"]


def test_guest_isolate_alone_leaves_the_bands_alone(client, router_requests):
    response = client.post("/wifi/guest", json={"isolate": False})
    assert response.status_code == 200
    assert not any("guest_2g" in url and data.get("operation") == "write" for url, data in router_requests)
    perms = request_payload(router_requests, "admin/wireless", form="guest", operation="write")
    assert perms == {"operation": "write", "isolate": "off", "access": "off"}


def test_guest_requires_at_least_one_change(client):
    response = client.post("/wifi/guest", json={})
    assert response.status_code == 400
    assert "at least one" in response.json()["detail"]


def test_guest_rejects_a_redaction_placeholder(client):
    """Writing the placeholder back would really set the guest key to '***redacted***'."""
    response = client.post("/wifi/guest", json={"password": REDACTED_PSK})
    assert response.status_code == 400
    assert "placeholder" in response.json()["detail"]


def test_access_control_state(client):
    body = client.get("/access-control").json()
    assert body == {"enable": False, "mode": "black", "host_mac": "AA-BB-CC-DD-EE-04"}


def test_access_control_devices_are_parsed(client):
    devices = client.get("/access-control/devices").json()
    assert [d["macaddr"] for d in devices] == ["AA-BB-CC-DD-EE-06", "AA-BB-CC-DD-EE-05"]
    assert devices[0]["band"] == "2.4G"
    assert devices[0]["device_type"] == "Mobile"
    assert devices[0]["is_guest"] is False
    assert devices[1]["is_guest"] is True


def test_blocked_and_allowed_macs(client):
    assert client.get("/access-control/blocked").json() == ["AA-BB-CC-DD-EE-01"]
    assert client.get("/access-control/allowed").json() == []


def test_block_sends_the_routers_own_device_row(client, router_requests):
    response = client.post("/access-control/block", json={"macaddr": "aa:bb:cc:dd:ee:06"})
    assert response.status_code == 200 and response.json() == {"success": True}

    payload = request_payload(router_requests, "admin/access_control", form="black_devices", operation="block")
    assert payload["index"] == 0, "the router needs the row's position in its own list"
    row = json.loads(payload["data"])
    assert row["mac"] == "AA-BB-CC-DD-EE-06"
    assert row["name"] == "Lava"


def test_block_requires_a_device_the_router_has_seen(client):
    response = client.post("/access-control/block", json={"macaddr": "99-99-99-99-99-99"})
    assert response.status_code == 404
    assert "not on the router's black_devices list" in response.json()["detail"]


def test_unblock_removes_by_mac_and_index(client, router_requests):
    response = client.delete("/access-control/block/AA-BB-CC-DD-EE-01")
    assert response.status_code == 200 and response.json() == {"success": True}

    payload = request_payload(router_requests, "admin/access_control", form="black_list", operation="remove")
    assert payload["key"] == "AA-BB-CC-DD-EE-01" and payload["index"] == 0


def test_unblock_absent_mac_returns_404(client):
    response = client.delete("/access-control/allow/99-99-99-99-99-99")
    assert response.status_code == 404


def test_access_control_mode_change(client, router_requests):
    response = client.post("/access-control", json={"enable": True, "mode": "white"})
    assert response.status_code == 200 and response.json() == {"success": True}

    enable = request_payload(router_requests, "admin/access_control", form="enable", operation="write")
    assert enable["enable"] == "on"
    assert enable["host_mac"] == "AA-BB-CC-DD-EE-04", "the protected host MAC must be preserved"
    assert request_payload(router_requests, "admin/access_control", form="mode", operation="write")["access_mode"] == "white"


def test_access_control_rejects_unknown_mode(client):
    response = client.post("/access-control", json={"mode": "grey"})
    assert response.status_code == 400


def test_access_control_requires_a_change(client):
    response = client.post("/access-control", json={})
    assert response.status_code == 400


def test_vpn_config_round_trip(client, router_requests):

    response = client.post("/vpn/openvpn", json=OpenVpnConfig(enable=False, proto="tcp", port=1195).model_dump())
    assert response.status_code == 200 and response.json() == {"success": True}

    write = request_payload(router_requests, "admin/openvpn?form=config", operation="write")
    assert write["enabled"] == "off" and write["proto"] == "tcp" and write["port"] == "1195"

    response = client.post("/vpn/pptp", json=PptpVpnConfig(enable=True, remoteip="10.0.0.50-60").model_dump())
    assert response.status_code == 200 and response.json() == {"success": True}

    write = request_payload(router_requests, "admin/pptpd?form=config", operation="write")
    assert write["enabled"] == "on" and write["remoteip"] == "10.0.0.50-60"


def test_wol_devices_are_parsed(client):
    devices = client.get("/wol/devices").json()
    assert devices == [
        {
            "key": "dev1", "name": "server", "macaddr": "AA-BB-CC-DD-EE-07",
            "index": 0, "raw": {"key": "dev1", "name": "server", "mac": "AA-BB-CC-DD-EE-07"},
        }
    ]


def test_wake_replays_the_routers_own_row(client, router_requests):
    response = client.post("/wol/wake", json={"macaddr": "aa:bb:cc:dd:ee:07"})
    assert response.status_code == 200 and response.json() == {"success": True}

    payload = request_payload(router_requests, "admin/wol", form="device", operation="wakeup")
    assert json.loads(payload["data"])["mac"] == "AA-BB-CC-DD-EE-07"


def test_wake_needs_a_saved_device(client):
    response = client.post("/wol/wake", json={"macaddr": "99-99-99-99-99-99"})
    assert response.status_code == 404
    assert "not a saved Wake-on-LAN device" in response.json()["detail"]


def test_wake_needs_a_target(client):
    response = client.post("/wol/wake", json={})
    assert response.status_code == 400


def test_add_wol_device_normalizes_the_mac(client, router_requests):
    response = client.post("/wol/devices", json={"macaddr": "aa:bb:cc:dd:ee:ff", "name": "laptop"})
    assert response.status_code == 200

    payload = request_payload(router_requests, "admin/wol", form="device", operation="insert")
    assert payload["mac"] == "AA-BB-CC-DD-EE-FF"
    assert payload["name"] == "laptop"
    assert payload["key"], "the firmware expects the caller to generate the row key"


def test_remove_wol_device_uses_key_and_index(client, router_requests):
    response = client.delete("/wol/devices/AA-BB-CC-DD-EE-07")
    assert response.status_code == 200

    payload = request_payload(router_requests, "admin/wol", form="device", operation="remove")
    assert payload["key"] == "dev1" and payload["index"] == 0


def test_dmz_round_trip(client, router_requests):
    assert client.get("/nat/dmz").json() == {"enable": False, "ipaddr": ""}

    response = client.post("/nat/dmz", json={"enable": True, "ipaddr": "192.168.0.50"})
    assert response.status_code == 200
    write = request_payload(router_requests, "admin/nat", form="dmz", operation="write")
    assert write["enable"] == "on" and write["ipaddr"] == "192.168.0.50"


def test_forwarding_rules_keep_unrecognised_fields(client):
    """Rule schemas were never observed on a populated router, so extras must survive."""
    rules = client.get("/nat/virtual-servers").json()
    assert rules[0]["key"] == "rule1"
    assert rules[0]["name"] == "ssh"
    assert rules[0]["enable"] is True
    assert rules[0]["eport"] == "2222"


def test_delete_forwarding_rule_by_key(client, router_requests):
    response = client.delete("/nat/virtual-servers/rule1")
    assert response.status_code == 200
    payload = request_payload(router_requests, "admin/nat?form=vs", operation="remove")
    assert payload == {"operation": "remove", "key": "rule1", "index": 0}


def test_delete_unknown_forwarding_rule_returns_404(client):
    assert client.delete("/nat/port-triggers/nope").status_code == 404


def test_wifi_capabilities_come_from_the_router(client):
    caps = client.get("/wifi/capabilities").json()
    assert caps["country"] == "US"
    assert caps["channels_2g"] == [str(n) for n in range(1, 12)]
    assert "165" in caps["channels_5g"]
    assert caps["htmodes_5g"] == ["20", "40", "80"]
    assert caps["hwmodes_2g"] == ["n", "gn", "bgn"]
    assert caps["support_smart_connect"] is True
    # An empty 6G list arrives as {} rather than [], and no region list means the
    # country cannot be changed.
    assert caps["channels_6g"] == []
    assert caps["region_selectable"] is False


def test_reboot(client, router_requests):
    response = client.post("/reboot")
    assert response.status_code == 200 and response.json() == {"success": True}
    assert any("admin/system?form=reboot" in url for url, _ in router_requests)


def test_endpoints_answer_503_without_a_router_client(client, monkeypatch):
    monkeypatch.setattr(api, "router", None)
    response = client.get("/status")
    assert response.status_code == 503
    assert "not initialized" in response.json()["detail"]


def test_concurrent_requests_share_one_reauth():
    """This firmware keeps one admin session, so parallel re-logins would kill each other.

    Simulates it: only the most recently issued stok is accepted, and a rejected request
    answers HTTP 200 with errorcode "timeout" the way the AX12 really does.
    """
    calls = []
    state = {"active": None, "logins": 0}

    async def fake_post(self, url, *args, **kwargs):
        await asyncio.sleep(0)  # yield, so the gathered requests really interleave
        payload = kwargs.get("data") or {}
        url_str = str(url)
        calls.append((url_str, payload))

        if "login?form=keys" in url_str:
            return mock_response(KEYS_OK)
        if "login?form=auth" in url_str:
            return mock_response(AUTH_OK)
        if "login?form=login" in url_str:
            state["logins"] += 1
            state["active"] = f"stok{state['logins']}"
            return mock_response({"success": True, "data": {"stok": state["active"]}})

        used = url_str.split(";stok=")[1].split("/")[0]
        if used != state["active"]:
            return mock_response({"success": False, "errorcode": "timeout"})
        if "admin/system?form=logout" in url_str:
            return mock_response(OK)
        return mock_response(STATUS_OK)

    async def run():
        async with ArcherAX12(host="192.168.0.1", password="test_password") as router:
            await router.login()
            assert state["logins"] == 1
            # Somebody else logs in (the web UI, another process) and takes the session over.
            state["active"] = "stok-hijacked"
            first, second = await asyncio.gather(router.get_status(), router.get_status())
            return first, second

    with patch("httpx.AsyncClient.post", fake_post):
        first, second = asyncio.run(run())

    assert first.lan.ipaddr == "192.168.0.1"
    assert second.lan.ipaddr == "192.168.0.1"
    # One of the two lost the race and re-authenticated; the other must reuse that login
    # rather than logging in again and invalidating it.
    assert state["logins"] == 2, f"expected one re-auth, saw {state['logins']} extra logins"
    assert sum(1 for url, _ in calls if "login?form=keys" in url) == 2


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
        "/access-control",
        "/access-control/devices",
        "/access-control/blocked",
        "/access-control/allowed",
        "/access-control/block",
        "/access-control/block/{macaddr}",
        "/access-control/allow",
        "/access-control/allow/{macaddr}",
        "/wol/devices",
        "/wol/devices/{macaddr}",
        "/wol/wake",
        "/nat/dmz",
        "/nat/virtual-servers",
        "/nat/virtual-servers/{key}",
        "/nat/port-triggers",
        "/nat/port-triggers/{key}",
        "/wifi/config",
        "/wifi/guest",
        "/wifi/statistics",
        "/wifi/capabilities",
        "/vpn/openvpn",
        "/vpn/pptp",
        "/vpn/connections",
        "/reboot",
        "/api/inventory/endpoints",
        "/api/inventory/modules",
        "/api/raw",
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


def test_inventory_endpoints(client):
    res = client.get("/api/inventory/endpoints")
    assert res.status_code == 200
    endpoints = res.json()
    assert len(endpoints) == 226
    urls = {ep["url"] for ep in endpoints}
    assert "admin/wireless?form=wireless_2g" in urls


def test_inventory_modules(client):
    res = client.get("/api/inventory/modules")
    assert res.status_code == 200
    modules = res.json()
    assert len(modules) == 50
    assert "admin/wireless" in modules


def test_raw_api_dispatch(client, router_requests):
    res = client.post("/api/raw", json={"module": "admin/wireless", "form": "wireless_2g", "operation": "read"})
    assert res.status_code == 200
    assert any("admin/wireless?form=wireless_2g" in url for url, _ in router_requests)

