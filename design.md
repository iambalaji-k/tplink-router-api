# Design Specification: TP-Link Archer AX12 API (`tplink-modern`)

> **Source of Truth**: Repository codebase, [`README.md`](README.md), [`pyproject.toml`](pyproject.toml), [`docs/router-api-inventory.md`](docs/router-api-inventory.md), [`2026-06-26_sdk-tplink-router-report.md`](2026-06-26_sdk-tplink-router-report.md), and resource schemas in `tplink_modern/`.  
> **Status**: Verified against hardware target firmware **`AX12v1_1.10.2`** at default gateway `192.168.0.1`.

---

## 1. Product Identity, Purpose & Goals

### 1.1 Product Name & Tagline
- **Package Name**: `tplink-modern` (Version `0.1.0`)
- **Product Title**: **TP-Link Archer AX12 API**
- **Tagline**:  
  *"Async Python SDK and FastAPI REST layer for the TP-Link Archer AX12 v1 router — built from the router's own web UI, endpoint by endpoint, and verified against a live device."*

### 1.2 Core Pillars (Verbatim from README)
1. **"Nothing guessed."** Every form name, verb, and payload shape was recovered from the JavaScript the router ships, then re-checked against the device.
2. **"A real inventory."** [226 endpoints surveyed across 50 modules, 179 confirmed answering](docs/router-api-inventory.md), each labelled with what this firmware actually did.
3. **"Typed and checked."** Pydantic models, mypy and ruff clean, 76 mocked unit tests that require no physical router to run.

### 1.3 Primary Purpose & Goals
- **Purpose**: Provide a production-grade, asynchronous Python SDK and FastAPI REST service to inspect, monitor, configure, and automate the TP-Link Archer AX12 v1 Wi-Fi 6 router.
- **Core Goals**:
  - **Empirical Rigor**: Zero reliance on third-party guesses or generic LuCI assumptions. Extract endpoints directly from vendor Vue bundles and verify them live with non-destructive read operations.
  - **Protocol Reliability**: Handle the router's strict **single-admin-session** constraint, transparently re-authenticating on session timeout or external eviction without stampeding concurrent requests.
  - **Operational Safety**: Redact cleartext Wi-Fi pre-shared keys (`***redacted***`) by default, prevent unintended credential overwrites, and isolate privileged actions (`POST /reboot`, Wi-Fi reconfiguration, Access Control blocks).
  - **Developer Ergonomics**: Modern Python 3.11+ async interfaces with strict typing (`mypy`), linting (`ruff`), Pydantic validation, and interactive OpenAPI documentation (`/docs` Swagger, `/redoc`).

---

## 2. Critical Files & Architecture

```
tplink-router-api/
├── app.py                  # FastAPI REST server exposing SDK over HTTP
├── pyproject.toml          # Project configuration, dependencies, and test/lint rules
├── README.md               # Product documentation, API surface, and usage guides
├── docs/
│   └── router-api-inventory.md   # Complete surveyed catalog (50 modules / 226 endpoints)
├── tplink_modern/          # Core SDK library
│   ├── client.py           # High-level ArcherAX12 async client facade
│   ├── auth.py             # 3-phase RSA handshake authenticator
│   ├── crypto.py           # RSA PKCS#1 v1.5 encryption (1024-bit modulus -> 256-hex)
│   ├── session.py          # Session manager, URL stok handler, concurrency lock & auto-reauth
│   ├── models.py           # Pydantic schemas for router status, clients, network, and policies
│   ├── endpoints.py        # Machine-readable endpoint constants & status classification
│   ├── exceptions.py       # Hierarchical typed exceptions (RouterError, APIError, etc.)
│   └── resources/          # Domain resource managers
│       ├── status.py       # Hardware telemetry (CPU, RAM, WAN, LAN, Wi-Fi summary)
│       ├── clients.py      # Connected device enumeration (wired, 2.4G, 5G)
│       ├── wifi.py         # 2.4G & 5G radio config, guest networks, transmit statistics
│       ├── network.py      # LAN, WAN, and DHCP static address reservations
│       ├── access.py       # Access control (black/white lists, host MAC preservation)
│       ├── nat.py          # DMZ hosting, virtual servers, port triggering
│       ├── vpn.py          # OpenVPN & PPTP server configs and active tunnel monitoring
│       ├── wol.py          # Wake-on-LAN device inventory and packet triggering
│       ├── system.py       # Device reboot and hardware commands
│       └── firmware.py     # Upgrade check polling
└── tools/inventory/        # Static AST extraction & live hardware probing suite
```

### Critical File Responsibilities
- **[`app.py`](app.py)**: Coordinates FastAPI lifespan (logging in on startup, logging out on shutdown), exposes REST endpoints for all major resources, maps router errors to HTTP status codes (`400`, `404`, `501`, `502`, `503`), and redacts secrets from status payloads unless explicitly requested (`?include_secrets=true`).
- **[`tplink_modern/client.py`](tplink_modern/client.py)**: The developer entrypoint (`ArcherAX12(host, password)`). Provides context management (`async with`), low-level operations (`read`, `write`, `api`), and delegates domain logic to modular resource handlers.
- **[`tplink_modern/session.py`](tplink_modern/session.py)**: Maintains the HTTP transport (`httpx.AsyncClient`), embeds the dynamic `stok` token into URL paths (`/cgi-bin/luci/;stok=<stok>/...`), and employs an `asyncio.Lock` to guarantee exactly one re-login runs if a `timeout` or `permission denied` occurs.
- **[`tplink_modern/auth.py`](tplink_modern/auth.py)** & **[`tplink_modern/crypto.py`](tplink_modern/crypto.py)**: Implement the router's proprietary authentication protocol:
  1. `form=keys`: Fetches the 1024-bit RSA public key modulus `key[0]` and exponent `key[1]`.
  2. `form=auth`: Validates authentication availability.
  3. `form=login`: Encrypts the password with PKCS#1 v1.5 padding into a 256-character hexadecimal string and retrieves the `stok`.
- **[`tplink_modern/models.py`](tplink_modern/models.py)**: Defines the data models and contracts (`RouterStatus`, `ClientDevice`, `DhcpReservation`, `AccessControlSettings`, `ManagedDevice`, `WolDevice`, `OpenVpnConfig`, etc.), enforcing field types and sanitizing boolean values (`"on"`/`"off"` strings -> `bool`).
- **[`tplink_modern/endpoints.py`](tplink_modern/endpoints.py)**: Auto-generated repository of 226 surveyed endpoints across 50 modules, tracking supported verbs, row schemas, and empirical outcomes on firmware `AX12v1_1.10.2`.

---

## 3. Product Native Shape: What Dominates the Architecture

The product is not an abstract SaaS dashboard or a linear timeline. Its native shape is a **Dual-Plane Hardware Gateway & Topology Hub**:

```
+-----------------------------------------------------------------------------------+
|                        PLANE 1: LIVE HARDWARE & TOPOLOGY                          |
|                                                                                   |
|  [Hardware Core]                                                                  |
|   - Archer AX12 v1 (Firmware AX12v1_1.10.2)                                      |
|   - CPU Usage & Memory Usage Ratios                                               |
|   - WAN IP / Gateway / DNS & LAN Gateway (192.168.0.1)                           |
|   - Single Admin Session Token (`stok`) Health                                    |
|                                                                                   |
|  [Network Radios & Client Graph]                                                  |
|   - 2.4 GHz Band (SSID, Channel, HT Mode, PSK)                                    |
|   - 5.0 GHz Band (SSID, Channel, HT Mode, PSK)                                    |
|   - Connected Clients (Wired Ethernet, 2.4G Wireless, 5G Wireless)                |
|   - Guest Networks & Client Isolation                                             |
|                                                                                   |
|  [Control & Security Matrix]                                                      |
|   - Access Control: Blacklist / Whitelist (Protected Host MAC)                    |
|   - DHCP Static Leases: MAC -> Fixed IP                                           |
|   - NAT / Port Forwarding / DMZ Host                                              |
|   - Wake-on-LAN Targets & VPN Connections                                         |
+-----------------------------------------------------------------------------------+
                                         │
                                         ▼
+-----------------------------------------------------------------------------------+
|                     PLANE 2: THE 226-ENDPOINT CATALOG & AUDIT                     |
|                                                                                   |
|  50 Modules | 226 Forms | 179 Answering Endpoints                                 |
|  Outcomes: Answered (179), Not Implemented (18), Needs Params (4),                |
|            Refused with Reason (3), Refused No Reason (1), Non-JSON (4),          |
|            Not Served 404 (4), Action Forms Not Probed (13)                       |
+-----------------------------------------------------------------------------------+
```

### Lead Feature Dominance
The **README leads with the Live Router Status, Resource Telemetry, and Topology Inspection**.  
When designing a visual representation or interface for this product:
1. **The Device Status & System Telemetry must dominate**: CPU and Memory load dials, WAN/LAN network state, and session connectivity state take primary visual weight.
2. **The Connected Client Topology is secondary**: Grouped by physical connection medium (`wired`, `2.4G`, `5G`), with hostname, IP, MAC, and live packet statistics (`rx_packets`, `tx_packets`).
3. **The Configuration Surfaces form modular controls**: Wi-Fi radios, DHCP reservations, Access Control block/allow lists, and NAT/DMZ settings.
4. **The Empirical API Inventory acts as an inspection panel**: An explorer displaying the 226 endpoints, their module classification, and their verified firmware state.

---

## 4. Real Terminology, Tokens & Data Dict (Zero Invented)

### 4.1 Identifiers & Connection Types
- **Gateway Address**: `192.168.0.1` (configurable via `TPLINK_HOST`)
- **Session Token**: `stok` (e.g. `ab12cd34ef56gh78...`)
- **Connection Types (`wire_type`)**:
  - `wired`
  - `2.4G`
  - `5G`
- **Access Control Modes (`mode`)**:
  - `black` (blacklist: blocks listed devices)
  - `white` (whitelist: allows only listed devices)
- **Protected MAC (`host_mac`)**: The device administering the router, protected by firmware from accidental self-lockout.
- **Secret Redaction Token**: `"***redacted***"` (replaces `wpa2_psk_key`, `wpa3_psk_key`, etc.)

### 4.2 Endpoint Outcome Taxonomy (`tplink_modern/endpoints.py`)
- `answered`: Read, load, or list succeeded (179 forms).
- `not-implemented`: Returned `no such callback` for all approved verbs (18 forms).
- `exists-needs-parameters`: Handler exists but rejected parameterless read (4 forms).
- `refused-stated-reason`: Handler named a specific blocking state, e.g. `err_download`, `recovery enable is off` (3 forms).
- `refused-without-reason`: Declined with `{"success": false}` with no reason code (1 form).
- `non-json-or-server-error`: Returned non-JSON data, file download, or HTTP 500 (4 forms).
- `not-served-404`: Module referenced in JS bundle but not hosted by firmware (4 forms).
- `not-probed`: Deliberately skipped because the form name is an active command (13 forms).

### 4.3 Refusal Spellings & Router Errors
The hardware firmware normalizes refusals under four distinct JSON keys:
1. `errorCode`
2. `error`
3. `error_code`
4. `errorcode`

Known firmware error strings:
- `"timeout"` (Signals discarded `stok` due to session takeover by another login)
- `"permission denied"` (Expired session or unauthorized operation)
- `"no such callback"` (Unimplemented CGI form)
- `"invalid proto_name"`
- `"invalid parameter vpntype"`

### 4.4 HTTP Status Mapping (`app.py`)
| HTTP Code | Error Condition |
|:---|:---|
| `200 OK` | Successful read or write (`{"success": true}`) |
| `400 Bad Request` | Invalid arguments (`ValueError`, bad band, malformed body) |
| `404 Not Found` | Target not found (`NotFoundError`, unknown MAC or reservation) |
| `501 Not Implemented` | Firmware lacks callback (`FeatureUnavailableError`) |
| `502 Bad Gateway` | Router refused request (`APIError`, `RouterError`, carries `errorcode`) |
| `503 Service Unavailable`| Router client uninitialized or startup login pending |

---

## 5. Visual Identity & Design System Tokens

Derived from repository badges, terminal logging styles, and router hardware branding:

### 5.1 Color Palette
- **Primary / Accent (TP-Link Cyan)**: `#00A7E1` (Interactive buttons, active states, Wi-Fi 6 branding)
- **Deep Slate / Hardware Chassis**:
  - Background (Dark): `#0B0F19`
  - Surface Card: `#131B2E`
  - Border / Separator: `#1E293B`
  - Text Primary: `#F8FAFC`
  - Text Muted: `#94A3B8`
- **Telemetry & Status Accents**:
  - Connected / Answering / Verified (`green`): `#10B981` (Badge: `#2EA44F`)
  - Firmware Version / Warning (`orange`): `#F59E0B` (Badge: `#F38020`)
  - Protocol / Python / System (`blue`): `#0284C7` (Badge: `#007ACC`)
  - Error / Refused / Reboot (`red`): `#EF4444`
  - Not Implemented / Inactive (`violet`): `#8B5CF6`
  - Redaction / Masking Indicator (`amber`): `#D97706`

### 5.2 Typography & Notation
- **Body & Headings**: Inter or system modern sans-serif (`-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif`).
- **Telemetry & Network Primitives**: Monospace (`JetBrains Mono`, `Fira Code`, `Consolas`, monospace).
  - MAC Addresses: Always normalized to uppercase hyphenated (`AA-BB-CC-DD-EE-01`).
  - IP Addresses: Monospace IPv4 notation (`192.168.0.1`, `10.8.0.0/24`).
  - CPU & RAM Usage: Ratios formatted as percentages (`0.142` -> `14.2%`).
  - Endpoints: Route paths formatted as `module?form=form_name`.

### 5.3 Component Patterns
1. **Device Metric Gauge**: Circular or bar gauges displaying `cpu_usage` and `mem_usage` ratios (0.0 to 1.0).
2. **Network Interface Pill**: WAN status badge displaying public IP, subnet mask, and gateway; LAN status badge displaying `192.168.0.1` and DHCP server toggle.
3. **Band Radio Card**: Split 2.4 GHz vs 5.0 GHz cards indicating SSID, channel number, channel width (`htmode`), and secure PSK indicator (`***redacted***` toggleable to cleartext).
4. **Client Device Table**: Grouped by `wire_type` (`wired`, `2.4G`, `5G`), displaying hostname (or `<unknown>`), assigned IP, MAC, and live packet counts (`rx_packets`, `tx_packets`).
5. **Access Policy Switch**: Segmented control between `black` (Blocklist) and `white` (Allowlist), highlighting the protected `host_mac`.
6. **Inventory Matrix**: Searchable 50-module / 226-endpoint data table with status pill indicators (`answered`, `not-implemented`, etc.) matching [`docs/router-api-inventory.md`](docs/router-api-inventory.md).
