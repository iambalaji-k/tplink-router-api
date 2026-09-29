from unittest.mock import AsyncMock, patch

import pytest

from tplink_modern import ArcherAX12
from tplink_modern.exceptions import AuthenticationError


@pytest.mark.asyncio
async def test_login_success():
    # Setup mock responses from the router
    mock_keys_response = {
        "success": True,
        "data": {
            "password": [
                "D1E79FF135D14E342D76185C23024E6DEAD4D6EC2C317A526C811E83538EA4E5ED8E1B0EEE5CE26E3C1B6A5F1FE11FA804F28B7E8821CA90AFA5B2F300DF99FDA27C9D2131E031EA11463C47944C05005EF4C1CE932D7F4A87C7563581D9F27F0C305023FCE94997EC7D790696E784357ED803A610EBB71B12A8BE5936429BFD",
                "010001"
            ]
        }
    }
    
    mock_auth_response = {
        "success": True,
        "data": {
            "key": [
                "C6452EF381D74E2B24EBCE2E6EECCD73070E3042FAA18E720B88A8FE5CDC214836FE464615031948E727A5C62775F364C7C93A922F067F049ADBFA03592F1137",
                "010001"
            ],
            "seq": 123456
        }
    }
    
    mock_login_response = {
        "success": True,
        "data": {
            "stok": "mocked_stok_token_value_1234"
        }
    }
    
    mock_status_response = {
        "success": True,
        "data": {
            "lan_macaddr": "AA-BB-CC-DD-EE-FF"
        }
    }

    def make_mock_response(json_data):
        mock_resp = AsyncMock()
        mock_resp.json = lambda: json_data
        mock_resp.status_code = 200
        mock_resp.raise_for_status = lambda: None
        return mock_resp

    with patch("httpx.AsyncClient.post") as mock_post:
        def post_side_effect(url, *args, **kwargs):
            url_str = str(url)
            if "form=keys" in url_str:
                return make_mock_response(mock_keys_response)
            elif "form=auth" in url_str:
                return make_mock_response(mock_auth_response)
            elif "form=login" in url_str:
                return make_mock_response(mock_login_response)
            elif "admin/status" in url_str:
                return make_mock_response(mock_status_response)
            elif "admin/system?form=logout" in url_str:
                return make_mock_response({"success": True})
            raise ValueError(f"Unexpected mocked request to URL: {url_str}")

        mock_post.side_effect = post_side_effect

        async with ArcherAX12(host="192.168.0.1", password="test_password") as router:
            await router.login()
            assert router.session.stok == "mocked_stok_token_value_1234"
            
            status = await router.get_status()
            assert status.lan.macaddr == "AA-BB-CC-DD-EE-FF"
            
            # 5 calls made before closing (keys, auth, login, status_verify, status_test)
            assert mock_post.call_count == 5

        # 6 calls after exiting (including logout)
        assert mock_post.call_count == 6


@pytest.mark.asyncio
async def test_login_failure():
    mock_keys_response = {
        "success": True,
        "data": {
            "password": [
                "D1E79FF135D14E342D76185C23024E6DEAD4D6EC2C317A526C811E83538EA4E5ED8E1B0EEE5CE26E3C1B6A5F1FE11FA804F28B7E8821CA90AFA5B2F300DF99FDA27C9D2131E031EA11463C47944C05005EF4C1CE932D7F4A87C7563581D9F27F0C305023FCE94997EC7D790696E784357ED803A610EBB71B12A8BE5936429BFD",
                "010001"
            ]
        }
    }
    
    mock_auth_response = {
        "success": True,
        "data": {
            "key": [
                "C6452EF381D74E2B24EBCE2E6EECCD73070E3042FAA18E720B88A8FE5CDC214836FE464615031948E727A5C62775F364C7C93A922F067F049ADBFA03592F1137",
                "010001"
            ],
            "seq": 123456
        }
    }
    
    mock_login_failure_response = {
        "success": False,
        "errorcode": "incorrect password"
    }

    def make_mock_response(json_data):
        mock_resp = AsyncMock()
        mock_resp.json = lambda: json_data
        mock_resp.status_code = 200
        mock_resp.raise_for_status = lambda: None
        return mock_resp

    with patch("httpx.AsyncClient.post") as mock_post:
        def post_side_effect(url, *args, **kwargs):
            url_str = str(url)
            if "form=keys" in url_str:
                return make_mock_response(mock_keys_response)
            elif "form=auth" in url_str:
                return make_mock_response(mock_auth_response)
            elif "form=login" in url_str:
                return make_mock_response(mock_login_failure_response)
            raise ValueError(f"Unexpected mocked request to URL: {url_str}")

        mock_post.side_effect = post_side_effect

        with pytest.raises(AuthenticationError) as excinfo:
            async with ArcherAX12(host="192.168.0.1", password="wrong_password") as router:
                await router.login()
        
        assert "Authentication failed" in str(excinfo.value)
        assert mock_post.call_count == 3


@pytest.mark.asyncio
async def test_auto_reauth_success():
    mock_keys_response = {
        "success": True,
        "data": {
            "password": [
                "D1E79FF135D14E342D76185C23024E6DEAD4D6EC2C317A526C811E83538EA4E5ED8E1B0EEE5CE26E3C1B6A5F1FE11FA804F28B7E8821CA90AFA5B2F300DF99FDA27C9D2131E031EA11463C47944C05005EF4C1CE932D7F4A87C7563581D9F27F0C305023FCE94997EC7D790696E784357ED803A610EBB71B12A8BE5936429BFD",
                "010001"
            ]
        }
    }
    
    mock_auth_response = {
        "success": True,
        "data": {
            "key": [
                "C6452EF381D74E2B24EBCE2E6EECCD73070E3042FAA18E720B88A8FE5CDC214836FE464615031948E727A5C62775F364C7C93A922F067F049ADBFA03592F1137",
                "010001"
            ],
            "seq": 123456
        }
    }
    
    mock_login_response = {
        "success": True,
        "data": {
            "stok": "mocked_stok_token_value_1234"
        }
    }
    
    mock_status_expired_response = {
        "success": False,
        "errorcode": "permission denied"
    }
    
    mock_status_ok_response = {
        "success": True,
        "data": {
            "lan_macaddr": "AA-BB-CC-DD-EE-FF"
        }
    }

    def make_mock_response(json_data):
        mock_resp = AsyncMock()
        mock_resp.json = lambda: json_data
        mock_resp.status_code = 200
        mock_resp.raise_for_status = lambda: None
        return mock_resp

    with patch("httpx.AsyncClient.post") as mock_post:
        status_calls = 0

        def post_side_effect(url, *args, **kwargs):
            nonlocal status_calls
            url_str = str(url)
            if "form=keys" in url_str:
                return make_mock_response(mock_keys_response)
            elif "form=auth" in url_str:
                return make_mock_response(mock_auth_response)
            elif "form=login" in url_str:
                return make_mock_response(mock_login_response)
            elif "admin/status" in url_str:
                status_calls += 1
                if status_calls == 1:
                    # Initial login verification succeeds
                    return make_mock_response(mock_status_ok_response)
                elif status_calls == 2:
                    # Subsequent request fails (session expired)
                    return make_mock_response(mock_status_expired_response)
                else:
                    # Retry request succeeds after auto-reauth
                    return make_mock_response(mock_status_ok_response)
            elif "admin/system?form=logout" in url_str:
                return make_mock_response({"success": True})
            raise ValueError(f"Unexpected mocked request to URL: {url_str}")

        mock_post.side_effect = post_side_effect

        async with ArcherAX12(host="192.168.0.1", password="test_password") as router:
            # Performs: keys (1), auth (2), login (3), get_status (4) [status_calls=1]
            await router.login()
            assert router.session.stok == "mocked_stok_token_value_1234"
            
            # Performs:
            # - get_status [status_calls=2] -> fails (5)
            # - auto-reauth: keys (6), auth (7), login (8)
            # - get_status retry [status_calls=3] -> succeeds (9)
            status = await router.get_status()
            assert status.lan.macaddr == "AA-BB-CC-DD-EE-FF"
            
            assert mock_post.call_count == 9

        # Performs: logout (10)
        assert mock_post.call_count == 10
