import httpx
from typing import Any, Dict, Optional
from tplink_modern.exceptions import SessionExpiredError

# The AX12 keeps a single admin session and answers HTTP 200 with these error codes once
# another login has replaced our stok.
EXPIRED_ERROR_CODES = frozenset({"permission denied", "timeout"})


class RouterSession:
    def __init__(self, host: str):
        # Normalize host format
        host_clean = host.rstrip("/")
        if not host_clean.startswith(("http://", "https://")):
            self.base_url = f"http://{host_clean}"
        else:
            self.base_url = host_clean

        self.client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=10,
            follow_redirects=True,
            verify=False,
        )
        self.stok: Optional[str] = None
        self.generation = 0

    async def post(self, path: str, data: Dict[str, Any], use_login_stok: bool = False) -> Dict[str, Any]:
        """Send a POST request to the router's Luci CGI endpoint.
        
        Args:
            path: The endpoint path (e.g. 'admin/status?form=all' or 'login?form=auth')
            data: Form-urlencoded request body dict.
            use_login_stok: Force use of '/login' instead of session token (for login phase).
        """
        stok_val = "/login" if (self.stok is None or use_login_stok) else self.stok
        
        # Clean path and format URL
        clean_path = path.lstrip("/")
        url = f"/cgi-bin/luci/;stok={stok_val}/{clean_path}"
        
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Referer": f"{self.base_url}/webpages/index.html",
        }
        
        response = await self.client.post(url, data=data, headers=headers)
        
        # Check HTTP authentication failure
        if response.status_code in (401, 403):
            raise SessionExpiredError("Session expired or permission denied")
            
        response.raise_for_status()
        res_json = response.json()

        # Check for TP-Link specific session expiration indicators
        err_code = res_json.get("errorcode") or res_json.get("errorCode")
        if err_code in EXPIRED_ERROR_CODES:
            raise SessionExpiredError(f"Session no longer accepted by router: {err_code}")

        return res_json

    async def close(self):
        await self.client.aclose()
