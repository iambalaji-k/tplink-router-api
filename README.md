# tplink-modern

A modern, production-quality Python SDK and FastAPI REST API wrapper for the TP-Link Archer AX12 v1 Router API.

## Project Structure
```text
tplink-router-api/
│
├── app.py                  # FastAPI REST Server
├── pyproject.toml          # Package configuration & dependencies
├── README.md               # Documentation
├── .gitignore
├── .env                    # Environment credentials
│
├── docs/
│   └── router-api-inventory.md   # Full surveyed router API (41 modules / 181 endpoints)
│
├── examples/               # SDK Usage Examples (live router)
│   ├── login.py
│   ├── devices.py
│   ├── status.py
│   └── reboot.py
│
├── tests/                  # Mock-based unit tests (no router required)
│   ├── test_login.py       # Login handshake, failure and auto-re-auth
│   └── test_features.py    # DHCP, Wi-Fi, VPN and wireless statistics
│
└── tplink_modern/          # Python SDK package
    ├── __init__.py         # Package entry point
    ├── client.py           # ArcherAX12 high-level client
    ├── auth.py             # RSA-based login handshake logic
    ├── crypto.py           # RSA PKCS#1 v1.5 utilities
    ├── session.py          # Session management & re-auth HTTP client
    ├── exceptions.py       # Custom RouterError definitions
    ├── models.py           # Pydantic schemas for type safety
    ├── endpoints.py        # Placeholder module (currently unused)
    └── resources/          # API resources
        ├── base.py         # Base Resource class
        ├── clients.py      # Connected client device queries
        ├── firmware.py     # Upgrade check actions
        ├── network.py      # LAN / WAN settings and DHCP reservations
        ├── status.py       # General router status
        ├── system.py       # Reboot and system commands
        ├── vpn.py          # OpenVPN / PPTP servers and connections
        └── wifi.py         # Guest and main Wi-Fi configurations
```

## Features
- **Robust Authentication**: Handles standard 1024-bit RSA PKCS#1 v1.5 key-exchange and encryption.
- **Session Resilience**: Automatic session check, keep-alive, and transparent re-authentication on token expiration.
- **Strong Typing**: Strongly typed Pydantic models for responses and settings (LAN, WAN, Wifi, Connected Clients, etc.).
- **Sub-Resource Client**: Modular layout where router components are accessed intuitively via `router.status`, `router.wifi`, `router.clients`, etc.
- **REST Wrapper**: Full-featured FastAPI server with lifespan state management and auto-generated OpenAPI documentation.
- **Surveyed API surface**: [`docs/router-api-inventory.md`](docs/router-api-inventory.md) maps all 181 router endpoints discovered on firmware 1.10.2, of which this SDK models 16.

---

## Installation & Setup

Requires Python 3.11+. The router is reachable over plain HTTP on the LAN, so run this only from a trusted network segment.

1. **Clone the Repository** and navigate to the project directory:
   ```bash
   cd tplink-router-api
   ```

2. **Initialize a Virtual Environment** and activate it:
   ```bash
   python -m venv venv
   # On Windows:
   .\venv\Scripts\activate
   # On macOS/Linux:
   source venv/bin/activate
   ```

3. **Install the SDK and its runtime dependencies**:
   ```bash
   pip install -e .
   ```

4. **Install the development tools** (not declared in `pyproject.toml`):
   ```bash
   pip install pytest pytest-asyncio mypy ruff
   ```

5. **Configure Environment variables**:
   Create a `.env` file in the root of the project:
   ```env
   TPLINK_HOST=192.168.0.1
   TPLINK_PASSWORD=your_router_admin_password
   ```

---

## SDK Usage Examples

Runnable versions of these snippets live in [`examples/`](examples) and read credentials from `.env`.

### 1. Connecting and Checking Status
```python
import asyncio
from tplink_modern import ArcherAX12

async def main():
    # Use context manager for automatic cleanup (logout + close)
    async with ArcherAX12(host="192.168.0.1", password="YOUR_PASSWORD") as router:
        await router.login()

        status = await router.status.get()
        print(f"LAN IP: {status.lan.ipaddr}")
        print(f"WAN IP: {status.wan.ipaddr}")
        print(f"CPU Load: {status.system.cpu_usage * 100:.1f}%")
        print(f"Memory Load: {status.system.mem_usage * 100:.1f}%")

        # login() already verifies the session, and get_status() doubles as the probe
        print(f"Session alive: {await router.keep_alive()}")

if __name__ == "__main__":
    asyncio.run(main())
```

`cpu_usage` / `mem_usage` are ratios in `0.0–1.0`, and every `bool` field on `RouterStatus`
is derived from the router's raw `"on"` / `"off"` strings.

### 2. Querying Connected Clients
```python
import asyncio
from tplink_modern import ArcherAX12

async def main():
    async with ArcherAX12(host="192.168.0.1", password="YOUR_PASSWORD") as router:
        await router.login()
        clients = await router.clients.get_all()
        for device in clients:
            # wire_type is one of 'wired', '2.4G' or '5G'
            name = device.hostname or "<unknown>"
            print(f"[{device.wire_type}] {name} - IP: {device.ipaddr} (MAC: {device.macaddr})")

if __name__ == "__main__":
    asyncio.run(main())
```

### 3. Reading and Changing Wi-Fi Settings
```python
import asyncio
from tplink_modern import ArcherAX12

async def main():
    async with ArcherAX12(host="192.168.0.1", password="YOUR_PASSWORD") as router:
        await router.login()

        wifi_2g = await router.wifi.get_2g()
        print(f"Current 2.4G SSID: {wifi_2g.ssid}, channel: {wifi_2g.channel}")

        # set_wireless_band performs a read-modify-write: omitted arguments
        # keep their current value, so this only changes the SSID.
        await router.wifi.set_wireless_band(band="2g", ssid="MyNetwork")

        # Enable the guest network with client isolation
        success = await router.wifi.set_guest(enable=True, isolate=True)
        print(f"Guest Wifi Configured: {success}")

if __name__ == "__main__":
    asyncio.run(main())
```

### 4. DHCP Reservations and VPN Status
```python
import asyncio
from tplink_modern import ArcherAX12
from tplink_modern.models import OpenVpnConfig

async def main():
    async with ArcherAX12(host="192.168.0.1", password="YOUR_PASSWORD") as router:
        await router.login()

        # MAC addresses are normalized to the router's uppercase hyphenated form
        await router.network.add_dhcp_reservation(
            macaddr="00:11:22:33:44:55", ipaddr="192.168.0.99", name="NAS"
        )
        for res in await router.network.get_dhcp_reservations():
            print(f"{res.macaddr} -> {res.ipaddr} ({res.name})")

        await router.network.delete_dhcp_reservation("00:11:22:33:44:55")

        # Turning the OpenVPN server off
        await router.vpn.set_openvpn(OpenVpnConfig(enable=False))
        print(f"Active VPN connections: {len(await router.vpn.get_connections())}")

if __name__ == "__main__":
    asyncio.run(main())
```

> **Caution:** `system.reboot()` restarts the router and drops the session. See `examples/reboot.py`, which asks for confirmation first.

---

## Low-Level Access

Every endpoint in the SDK is a thin wrapper over three primitives on `ArcherAX12`, useful for
calling router forms the SDK does not model yet:

| Method | Resulting request |
| --- | --- |
| `await router.read(path, form, **kw)` | `POST /cgi-bin/luci/;stok=<stok>/{path}?form={form}` with `operation=read` |
| `await router.write(path, form, **kw)` | same, with `operation=write` |
| `await router.api(path, form, operation, **kw)` | same, with any operation (`load`, `insert`, `remove`, `list`, …) |

Responses are the router's raw JSON dict (`{"success": bool, "data": ..., "errorcode": ...}`);
`data` is unwrapped by the higher-level resources.

---

## Running the FastAPI REST Server

You can expose the SDK as a high-performance REST service. The server initializes a shared `ArcherAX12` client and coordinates the connection lifespan automatically.

Start the FastAPI application:
```bash
uvicorn app:app --host 0.0.0.0 --port 8000 --reload
```

On startup the server logs in once. A failed startup login is logged as a warning rather than fatal: the client re-authenticates transparently on the first request. Until then, endpoints answer `503`.

**The router allows only one admin session.** Logging in from the web UI (or a second process) invalidates this server's `stok`, and vice versa — the API answers `200` with `errorcode: "timeout"` for the discarded token. The client detects that and re-authenticates, and a lock makes concurrent requests share a single re-login instead of stampeding, since parallel logins would otherwise knock each other out. Don't run two copies of this server against the same router.

### API Endpoints

All endpoints live on one shared router client. Read-only endpoints are `GET`; configuration
changes are `POST`/`DELETE`. Write handlers return `{"success": true}` and map any `RouterError`
to `500`.

- `GET /status` - Complete system resource usage, CPU, RAM, LAN, and Wi-Fi band configurations. Wi-Fi keys are redacted unless you pass `?include_secrets=true`.
- `GET /clients` - Returns list of all connected wired and wireless devices.
- `GET /firmware` - Checks for available firmware upgrades.
- `GET /network/lan` - Get current local area network settings.
- `GET /network/wan` - Get current wide area network settings.
- `GET /network/dhcp/reservations` - List static DHCP IP-MAC address reservations.
- `POST /network/dhcp/reservations` - Create a new static DHCP address reservation.
- `DELETE /network/dhcp/reservations/{macaddr}` - Delete a static DHCP address reservation by MAC.
- `POST /wifi/config` - Update SSID, password, channel, HT mode for 2.4G or 5G bands.
- `POST /wifi/guest` - Update Guest Wi-Fi state (enable/disable, isolate).
- `GET /wifi/statistics` - Query packets sent/received statistics for all connected wireless client devices.
- `GET /vpn/openvpn` - Retrieve current OpenVPN server configuration.
- `POST /vpn/openvpn` - Configure and toggle the OpenVPN server.
- `GET /vpn/pptp` - Retrieve current PPTP VPN server configuration.
- `POST /vpn/pptp` - Configure and toggle the PPTP VPN server.
- `GET /vpn/connections` - List active incoming OpenVPN and PPTP connections.
- `POST /reboot` - Triggers a router restart.

### Security Notes

Read these before exposing the server beyond `127.0.0.1`:

- **The REST API is unauthenticated.** Anyone who can reach the port holds router admin rights, including `POST /reboot` and Wi-Fi/VPN changes. Bind to localhost, or put your own auth in front of it.
- **Wi-Fi keys are redacted from `GET /status` by default** (they come back as `"***redacted***"`), because the router returns them in its own status payload. Pass `?include_secrets=true` to see them. The SDK deliberately still hands back real keys — `wifi.set_wireless_band()` re-sends the current PSK on every write, so masking at that layer would let a redacted placeholder overwrite your password. `tplink_modern.redact_secrets()` is exported if you serialize `RouterStatus` yourself.
- **The SDK connects to the router over `http://`** and does not verify TLS if you pass an `https://` host (`verify=False` in `session.py`).

### OpenAPI Documentation
Once the server is running, navigate to:
- **Swagger UI**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **ReDoc**: [http://localhost:8000/redoc](http://localhost:8000/redoc)

---

## Running Tests & Type Checks

The suite mocks the router's HTTP layer, so no router needs to be reachable:

```bash
pytest -q          # 22 tests
mypy .             # clean across 26 source files
ruff check .
```

| File | Covers |
| --- | --- |
| `tests/conftest.py` | Supplies dummy `TPLINK_*` env vars so `app.py` imports without a real `.env` |
| `tests/test_login.py` | RSA login handshake, wrong-password failure, transparent re-auth on `permission denied` |
| `tests/test_features.py` | SDK-level DHCP reservations, Wi-Fi band writes, VPN config, wireless statistics |
| `tests/test_api.py` | Every REST endpoint of `app.py`, including status codes, request bodies sent to the router, PSK redaction, `400`/`500`/`503` handling, and OpenAPI route coverage |

`ruff check .` currently reports style findings in the SDK and server (PEP 604/585 annotations,
import ordering, and broad `except Exception: pass` blocks). None of them change runtime behaviour,
and they are not treated as failures here.

> Note: `examples/` scripts are live tools, not tests — they talk to the real router in `.env`,
> and `reboot.py` restarts it after an interactive confirmation.

