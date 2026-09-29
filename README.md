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
        ├── access.py       # Access control: block / allow devices
        ├── clients.py      # Connected client device queries
        ├── firmware.py     # Upgrade check actions
        ├── nat.py          # DMZ, virtual servers, port triggering
        ├── network.py      # LAN / WAN settings and DHCP reservations
        ├── status.py       # General router status
        ├── system.py       # Reboot and system commands
        ├── vpn.py          # OpenVPN / PPTP servers and connections
        ├── wifi.py         # Guest and main Wi-Fi configurations
        └── wol.py          # Saved Wake-on-LAN targets and magic packets
```

## Features
- **Robust Authentication**: Handles standard 1024-bit RSA PKCS#1 v1.5 key-exchange and encryption.
- **Session Resilience**: Automatic session check, keep-alive, and transparent re-authentication on token expiration.
- **Strong Typing**: Strongly typed Pydantic models for responses and settings (LAN, WAN, Wifi, Connected Clients, etc.).
- **Sub-Resource Client**: Modular layout where router components are accessed intuitively via `router.status`, `router.wifi`, `router.clients`, etc.
- **REST Wrapper**: Full-featured FastAPI server with lifespan state management and auto-generated OpenAPI documentation.
- **Surveyed API surface**: [`docs/router-api-inventory.md`](docs/router-api-inventory.md) maps all 181 router endpoints discovered on firmware 1.10.2; the SDK and REST layer model roughly two dozen of them, including device block/allow and guest credentials.

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

        # Both setters are read-modify-write: omitted arguments keep their current
        # value, so this only changes the SSID.
        await router.wifi.set_wireless_band(band="2g", ssid="MyNetwork")

        # Guest networks are per-band on this firmware, and isolation is a separate form.
        await router.wifi.set_guest(enable=True, ssid="Guests", password="guest-pass-1", isolate=True)

        print(await router.wifi.get_guest_band("2g"))

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

### 5. Blocking and Allowing Devices
```python
import asyncio
from tplink_modern import ArcherAX12

async def main():
    async with ArcherAX12(host="192.168.0.1", password="YOUR_PASSWORD") as router:
        await router.login()

        for device in await router.access.devices("black"):
            print(f"{device.name:<12} {device.macaddr} {device.band} guest={device.is_guest}")

        # Only devices the router has already seen can be listed; it needs the row
        # it reported, which is why block() looks the MAC up first.
        await router.access.block("AA-BB-CC-DD-EE-01")
        await router.access.set_enabled(True)     # access control is off until you turn it on
        print(await router.access.blocked())

        await router.access.set_mode("white")     # allow-list mode
        await router.access.allow("AA-BB-CC-DD-EE-06")
        await router.access.unblock("AA-BB-CC-DD-EE-01")
        await router.access.set_enabled(False)

if __name__ == "__main__":
    asyncio.run(main())
```

> **Caution:** enabling access control in `black` mode cuts the listed device off the network,
> and in `white` mode anything not on the allow list loses connectivity. Test with a device you
> can reach over cable, and note the router protects one MAC (`host_mac`) — usually the machine
> that configured it.

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

All endpoints share one router client. Read-only endpoints are `GET`; configuration changes are
`POST`/`DELETE`. A write answers `{"success": true}`, and a refused write never looks like a
success — the router's own `errorcode` comes back in the body:

| HTTP | Meaning |
| --- | --- |
| `400` | Bad arguments (unknown band, malformed body) |
| `404` | Nothing to act on (e.g. deleting an unknown DHCP reservation) |
| `501` | This firmware does not implement the form (`errorcode: "no such callback"`) |
| `502` | The router refused or failed the request; body carries `errorcode` |
| `503` | Router client not initialized (startup login still pending, or the server is shutting down) |

- `GET /status` - Complete system resource usage, CPU, RAM, LAN, and Wi-Fi band configurations. Wi-Fi keys are redacted unless you pass `?include_secrets=true`.
- `GET /clients` - Returns list of all connected wired and wireless devices.
- `GET /firmware` - Whether the router thinks an upgrade is pending (a count, not a version).
- `GET /network/lan` - Get current local area network settings.
- `GET /network/wan` - Get current wide area network settings.
- `GET /network/dhcp/reservations` - List static DHCP IP-MAC address reservations.
- `POST /network/dhcp/reservations` - Create a new static DHCP address reservation.
- `DELETE /network/dhcp/reservations/{macaddr}` - Delete a static DHCP address reservation by MAC.
- `GET /access-control` - Whether access control is enabled, its list mode, and the protected host MAC.
- `POST /access-control` - Enable/disable access control or switch mode (`black`/`white`).
- `GET /access-control/devices` - Devices the router offers for the block or allow list.
- `GET /access-control/blocked` / `GET /access-control/allowed` - MACs on each list.
- `POST /access-control/block` - Block a device by MAC (body `{"macaddr": "..."}`).
- `DELETE /access-control/block/{macaddr}` - Unblock a device.
- `POST /access-control/allow` - Add a device to the allow list.
- `DELETE /access-control/allow/{macaddr}` - Remove a device from the allow list.
- `GET /wol/devices` - Wake-on-LAN targets saved on the router.
- `POST /wol/devices` - Save a wake target (body `{"macaddr": "...", "name": "..."}`).
- `DELETE /wol/devices/{macaddr}` - Delete a saved wake target.
- `POST /wol/wake` - Send a magic packet to a saved device by MAC or name.
- `GET /nat/dmz` / `POST /nat/dmz` - Read or set the DMZ host.
- `GET /nat/virtual-servers` - Port forwarding rules.
- `DELETE /nat/virtual-servers/{key}` - Delete a port forwarding rule.
- `GET /nat/port-triggers` / `DELETE /nat/port-triggers/{key}` - Port triggering rules.
- `POST /wifi/config` - Update SSID, password, channel, HT mode for 2.4G or 5G bands.
- `POST /wifi/guest` - Toggle guest Wi-Fi, set its SSID and password, or change client isolation. Omitted fields keep their current values.
- `GET /wifi/statistics` - Query packets sent/received statistics for all connected wireless client devices.
- `GET /wifi/capabilities` - Channels, band widths and modes this unit supports in its current country — validate a `/wifi/config` write against this.
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
- **The SDK talks plain HTTP to the router.** If you pass an `https://` host, certificates are verified by default; `ArcherAX12(host, password, timeout=10.0, verify=True)` exposes both, so turn `verify` off deliberately for a self-signed device rather than silently trusting a bad certificate.

### OpenAPI Documentation
Once the server is running, navigate to:
- **Swagger UI**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **ReDoc**: [http://localhost:8000/redoc](http://localhost:8000/redoc)

---

## Running Tests & Type Checks

The suite mocks the router's HTTP layer, so no router needs to be reachable:

```bash
pytest -q          # 51 mocked tests, live module skipped
mypy .             # clean across 30 source files
ruff check .       # clean
```

`.github/workflows/ci.yml` runs all three on Python 3.11 and 3.13. The rule set CI enforces is
pinned in `pyproject.toml`, so a ruff upgrade cannot quietly move the bar.

| File | Covers |
| --- | --- |
| `tests/conftest.py` | Supplies dummy `TPLINK_*` env vars so `app.py` imports without a real `.env` |
| `tests/test_login.py` | RSA login handshake, wrong-password failure, transparent re-auth on `permission denied` |
| `tests/test_features.py` | SDK-level DHCP reservations, Wi-Fi band writes, VPN config, wireless statistics |
| `tests/test_api.py` | Every REST endpoint of `app.py` against a mocked router: status codes, request bodies sent to the device, PSK redaction, concurrent re-auth, `400`/`404`/`501`/`502`/`503` handling, OpenAPI route coverage |
| `tests/test_live.py` | Opt-in checks against a real Archer AX12 |

### Live tests

`tests/test_live.py` talks to the router in your `.env` — it issues reads and logins only, and
never calls a write or reboot endpoint. It is skipped unless you ask for it:

```bash
TPLINK_LIVE=1 pytest -m live
```

Each read route's response is validated against its declared Pydantic model, so a firmware change
that alters a payload shows up as a failure rather than a wrong value downstream. One test also
logs in from a second client to evict the server's `stok` — the same thing the web admin page does
— and asserts that two concurrent requests both recover. **Running it will log out any router web
session you have open.**

The lint cleanup was mostly mechanical, except where broad `except Exception` handlers were
converting real failures into empty results: `vpn.get_connections()` swallowed every error and
reported "nobody connected", so it now tolerates only `FeatureUnavailableError` (a unit without
that VPN server) and lets anything else propagate. `keep_alive()`, `logout()`, and the server's
startup/shutdown handlers narrow to router and transport errors for the same reason.

> Note: `examples/` scripts are live tools, not tests — they talk to the real router in `.env`,
> and `reboot.py` restarts it after an interactive confirmation.

