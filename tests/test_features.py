from unittest.mock import AsyncMock, patch
import pytest
from tplink_modern import ArcherAX12
from tplink_modern.models import OpenVpnConfig, PptpVpnConfig


def make_mock_response(json_data, status_code=200):
    mock_resp = AsyncMock()
    mock_resp.json = lambda: json_data
    mock_resp.status_code = status_code
    mock_resp.raise_for_status = lambda: None
    return mock_resp


# Common encryption params for valid mock keys
VALID_MODULUS = "D1E79FF135D14E342D76185C23024E6DEAD4D6EC2C317A526C811E83538EA4E5ED8E1B0EEE5CE26E3C1B6A5F1FE11FA804F28B7E8821CA90AFA5B2F300DF99FDA27C9D2131E031EA11463C47944C05005EF4C1CE932D7F4A87C7563581D9F27F0C305023FCE94997EC7D790696E784357ED803A610EBB71B12A8BE5936429BFD"
MOCK_KEYS_RESPONSE = {"success": True, "data": {"password": [VALID_MODULUS, "010001"]}}
MOCK_AUTH_RESPONSE = {"success": True, "data": {"key": [VALID_MODULUS[:128], "010001"], "seq": 1}}
MOCK_LOGIN_RESPONSE = {"success": True, "data": {"stok": "token"}}


@pytest.mark.asyncio
async def test_dhcp_reservations():
    mock_status_response = {"success": True, "data": {"lan_macaddr": "AA-BB-CC-DD-EE-FF"}}
    
    mock_load_reservations = {
        "success": True,
        "data": [
            {
                "mac": "AA-BB-CC-DD-EE-01",
                "comment": "laptop",
                "hostname": "laptop",
                "enable": "on",
                "ip": "192.168.0.56"
            }
        ]
    }
    
    mock_insert_reservation = {"success": True, "data": {}}
    mock_remove_reservation = {"success": True, "data": []}

    with patch("httpx.AsyncClient.post") as mock_post:
        def post_side_effect(url, *args, **kwargs):
            url_str = str(url)
            if "form=keys" in url_str:
                return make_mock_response(MOCK_KEYS_RESPONSE)
            elif "form=auth" in url_str:
                return make_mock_response(MOCK_AUTH_RESPONSE)
            elif "form=login" in url_str:
                return make_mock_response(MOCK_LOGIN_RESPONSE)
            elif "admin/status?form=all" in url_str:
                return make_mock_response(mock_status_response)
            elif "admin/dhcps?form=reservation" in url_str:
                data_param = kwargs.get("data", {})
                op = data_param.get("operation")
                if op == "load":
                    return make_mock_response(mock_load_reservations)
                elif op == "insert":
                    return make_mock_response(mock_insert_reservation)
                elif op == "remove":
                    return make_mock_response(mock_remove_reservation)
            elif "admin/system?form=logout" in url_str:
                return make_mock_response({"success": True})
            raise ValueError(f"Unexpected request: {url_str}")

        mock_post.side_effect = post_side_effect

        async with ArcherAX12(host="192.168.0.1", password="test_password") as router:
            await router.login()
            
            # test get
            reservations = await router.network.get_dhcp_reservations()
            assert len(reservations) == 1
            assert reservations[0].macaddr == "AA-BB-CC-DD-EE-01"
            assert reservations[0].ipaddr == "192.168.0.56"
            assert reservations[0].enable is True
            assert reservations[0].name == "laptop"

            # test add
            success_add = await router.network.add_dhcp_reservation(
                macaddr="00:11:22:33:44:55",
                ipaddr="192.168.0.99",
                name="NewDevice",
                enable=True
            )
            assert success_add is True

            # test delete
            success_del = await router.network.delete_dhcp_reservation("AA-BB-CC-DD-EE-01")
            assert success_del is True


@pytest.mark.asyncio
async def test_wifi_band_config():
    mock_status_response = {
        "success": True,
        "data": {
            "wireless_2g_ssid": "Goloka",
            "wireless_2g_enable": "on",
            "wireless_2g_macaddr": "AA-BB-CC-DD-EE-02",
            "wireless_2g_channel": "auto",
            "wireless_2g_encryption": "psk",
            "wireless_2g_psk_key": "password123",
            "wireless_2g_psk_cipher": "aes",
            "wireless_2g_htmode": "auto"
        }
    }
    
    mock_write_wifi = {"success": True}

    with patch("httpx.AsyncClient.post") as mock_post:
        def post_side_effect(url, *args, **kwargs):
            url_str = str(url)
            if "form=keys" in url_str:
                return make_mock_response(MOCK_KEYS_RESPONSE)
            elif "form=auth" in url_str:
                return make_mock_response(MOCK_AUTH_RESPONSE)
            elif "form=login" in url_str:
                return make_mock_response(MOCK_LOGIN_RESPONSE)
            elif "admin/status?form=all" in url_str:
                return make_mock_response(mock_status_response)
            elif "admin/wireless" in url_str:
                return make_mock_response(mock_write_wifi)
            elif "admin/system?form=logout" in url_str:
                return make_mock_response({"success": True})
            raise ValueError(f"Unexpected request: {url_str}")

        mock_post.side_effect = post_side_effect

        async with ArcherAX12(host="192.168.0.1", password="test_password") as router:
            await router.login()
            
            # test get 2g
            wifi_2g = await router.wifi.get_2g()
            assert wifi_2g.ssid == "Goloka"
            assert wifi_2g.enable is True

            # test set wireless band
            success_set = await router.wifi.set_wireless_band(
                band="2g",
                ssid="Goloka_New",
                password="newpassword123"
            )
            assert success_set is True


@pytest.mark.asyncio
async def test_vpn_resources():
    mock_status_response = {"success": True, "data": {"lan_macaddr": "AA-BB-CC-DD-EE-FF"}}
    
    mock_vpn_config = {
        "success": True,
        "data": {
            "enabled": "on",
            "proto": "udp",
            "port": "1194",
            "serverip": "10.8.0.0",
            "mask": "255.255.255.0"
        }
    }
    
    mock_pptp_config = {
        "success": True,
        "data": {
            "enabled": "off",
            "remoteip": "10.0.0.11-20"
        }
    }
    
    mock_vpn_connections = {
        "success": True,
        "data": [
            {
                "username": "client1",
                "ipaddr": "10.8.0.6",
                "macaddr": "00:11:22:33:44:55",
                "uptime": "00:05:23"
            }
        ]
    }

    with patch("httpx.AsyncClient.post") as mock_post:
        def post_side_effect(url, *args, **kwargs):
            url_str = str(url)
            if "form=keys" in url_str:
                return make_mock_response(MOCK_KEYS_RESPONSE)
            elif "form=auth" in url_str:
                return make_mock_response(MOCK_AUTH_RESPONSE)
            elif "form=login" in url_str:
                return make_mock_response(MOCK_LOGIN_RESPONSE)
            elif "admin/status?form=all" in url_str:
                return make_mock_response(mock_status_response)
            elif "admin/openvpn?form=config" in url_str:
                return make_mock_response(mock_vpn_config)
            elif "admin/pptpd?form=config" in url_str:
                return make_mock_response(mock_pptp_config)
            elif "admin/vpnconn?form=config" in url_str:
                return make_mock_response(mock_vpn_connections)
            elif "admin/system?form=logout" in url_str:
                return make_mock_response({"success": True})
            raise ValueError(f"Unexpected request: {url_str}")

        mock_post.side_effect = post_side_effect

        async with ArcherAX12(host="192.168.0.1", password="test_password") as router:
            await router.login()
            
            # test openvpn config get
            ovpn = await router.vpn.get_openvpn()
            assert ovpn.enable is True
            assert ovpn.port == 1194
            
            # test openvpn config set
            new_ovpn = OpenVpnConfig(enable=False, proto="tcp", port=1195)
            assert await router.vpn.set_openvpn(new_ovpn) is True
            
            # test pptp config get
            pptp = await router.vpn.get_pptp()
            assert pptp.enable is False
            assert pptp.remoteip == "10.0.0.11-20"
            
            # test pptp config set
            new_pptp = PptpVpnConfig(enable=True, remoteip="10.0.0.50-60")
            assert await router.vpn.set_pptp(new_pptp) is True
            
            # test connections
            conns = await router.vpn.get_connections()
            assert len(conns) == 2  # 1 from openvpn, 1 from pptp (both mock vpn_connections list)
            assert conns[0].username == "client1"
            assert conns[0].ipaddr == "10.8.0.6"


@pytest.mark.asyncio
async def test_wireless_statistics():
    mock_status_response = {"success": True, "data": {"lan_macaddr": "AA-BB-CC-DD-EE-FF"}}
    
    mock_wifi_stats = {
        "success": True,
        "data": [
            {
                "mac": "AA-BB-CC-DD-EE-01",
                "type": "2.4GHz",
                "encryption": "wpa2-psk",
                "rxpkts": 774,
                "txpkts": 1207
            }
        ]
    }

    with patch("httpx.AsyncClient.post") as mock_post:
        def post_side_effect(url, *args, **kwargs):
            url_str = str(url)
            if "form=keys" in url_str:
                return make_mock_response(MOCK_KEYS_RESPONSE)
            elif "form=auth" in url_str:
                return make_mock_response(MOCK_AUTH_RESPONSE)
            elif "form=login" in url_str:
                return make_mock_response(MOCK_LOGIN_RESPONSE)
            elif "admin/status?form=all" in url_str:
                return make_mock_response(mock_status_response)
            elif "admin/wireless?form=statistics" in url_str:
                return make_mock_response(mock_wifi_stats)
            elif "admin/system?form=logout" in url_str:
                return make_mock_response({"success": True})
            raise ValueError(f"Unexpected request: {url_str}")

        mock_post.side_effect = post_side_effect

        async with ArcherAX12(host="192.168.0.1", password="test_password") as router:
            await router.login()
            
            stats = await router.wifi.get_statistics()
            assert len(stats) == 1
            assert stats[0].macaddr == "AA-BB-CC-DD-EE-01"
            assert stats[0].band == "2.4GHz"
            assert stats[0].rx_packets == 774
            assert stats[0].tx_packets == 1207

