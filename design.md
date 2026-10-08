# Design Specification: TP-Link Archer AX12 API & Management UI (`tplink-modern`)

> **Source of Truth**: Repository codebase, [`README.md`](README.md), [`pyproject.toml`](pyproject.toml), [`docs/router-api-inventory.md`](docs/router-api-inventory.md), [`2026-06-26_sdk-tplink-router-report.md`](2026-06-26_sdk-tplink-router-report.md), and resource schemas in `tplink_modern/`.  
> **Target Device**: TP-Link Archer AX12 v1 (Firmware: **`AX12v1_1.10.2`** at default gateway `192.168.0.1`).

---

## 1. Product Identity, Purpose & Goals

### 1.1 Product Name & Tagline
- **Package Name**: `tplink-modern` (Version `0.1.0`)
- **Product Title**: **TP-Link Archer AX12 API & Dashboard**
- **Tagline**:  
  *"Async Python SDK, FastAPI REST layer, and Management Console for the TP-Link Archer AX12 v1 router — built from the router's own web UI, endpoint by endpoint, and verified against a live device."*

### 1.2 Core Pillars (Verbatim from Codebase)
1. **"Nothing guessed."** Every form name, verb, and payload shape was recovered from the JavaScript the router ships, then re-checked against the physical device.
2. **"A real inventory."** [226 endpoints surveyed across 50 modules, 179 confirmed answering](docs/router-api-inventory.md), each labelled with what this firmware actually did.
3. **"Typed and checked."** Pydantic models, mypy and ruff clean, 76 mocked unit tests that require no physical router to run.

### 1.3 Goals of the Management UI
- **Unified Operations**: Provide a responsive, high-performance web dashboard to monitor router vitals, manage connected devices, adjust Wi-Fi radios, and enforce network policies without logging into the clunky vendor interface.
- **Complete 226-Endpoint Surface Access**: Move beyond the ~24 curated REST endpoints by providing an interactive **API Explorer / Console** capable of querying, testing, and managing all 226 discovered router forms.
- **Hardware Protocol Integrity**: Visually handle router quirks in real time—specifically the **single-admin-session lock** (`stok` timeout recovery), secret redaction protections, and granular error code mapping.
- **Zero-Accident Safety Gates**: Prevent accidental network lockouts (`white` mode access control), credential corruption, or unintended reboots through two-stage confirmation dialogs.

---

## 2. Frontend Tech Stack & Deployment Architecture

In compliance with project directives (modern TypeScript, Bun, and high performance):

### 2.1 Tech Stack
- **Runtime & Package Manager**: **Bun** (`bun install`, `bun run build`, `bun test`)
- **Framework & Bundler**: **Vite + React** with **TypeScript** (Strict Mode enabled: `noImplicitAny: true`, `strictNullChecks: true`)
- **Styling**: **Tailwind CSS** configured with the TP-Link chassis design token palette
- **Icons**: **Lucide React** (`lucide-react`)
- **State & Data Fetching**: **TanStack Query (React Query v5)** for robust caching, background polling, and automatic retry control
- **Code & JSON Viewer**: `@monaco-editor/react` or lightweight syntax-highlighted tree viewer for JSON inspection

### 2.2 Delivery & Deployment Model
The UI will live in a `ui/` directory within the repository and support two deployment modes:
1. **Embedded Single-Port Service (Production)**:
   - The compiled static SPA bundle (`ui/dist`) is mounted directly onto the FastAPI server in [`app.py`](app.py) via `fastapi.staticfiles.StaticFiles`:
     ```python
     app.mount("/", StaticFiles(directory="ui/dist", html=True), name="ui")
     ```
   - Running `uvicorn app:app --host 127.0.0.1 --port 8000` serves both the REST API and the management UI seamlessly from one process.
2. **Standalone Development Mode (Vite Dev Server)**:
   - Fast hot-module reloading powered by Bun: `cd ui && bun run dev` (running on `http://localhost:5173`).
   - Vite proxy configured in `vite.config.ts` forwarding `/status`, `/clients`, `/network`, `/wifi`, `/access-control`, `/nat`, `/vpn`, `/wol`, and `/api/*` directly to `http://127.0.0.1:8000`.

---

## 3. Backend REST Extensions Required (`app.py`)

To empower the UI to manage **all 226 endpoints** (not just the 24 pre-built REST routes), [`app.py`](app.py) must be extended with three dedicated endpoints:

### 3.1 `GET /api/inventory/endpoints`
- **Purpose**: Feeds the UI with the complete 226-endpoint dictionary directly from [`tplink_modern/endpoints.py`](tplink_modern/endpoints.py).
- **Response Schema**:
  ```typescript
  interface InventoryEndpoint {
    module: string;            // e.g., "admin/wireless"
    form: string;              // e.g., "wireless_2g"
    url: string;               // e.g., "admin/wireless?form=wireless_2g"
    status: "answered" | "not-implemented" | "exists-needs-parameters" | 
            "refused-stated-reason" | "refused-without-reason" | 
            "non-json-or-server-error" | "not-served-404" | "not-probed";
    ui_operations: string[];   // e.g., ["read", "write"]
    read_verbs: string[];      // e.g., ["read"]
    others_key: string | null; // e.g., "others" (capacity limits)
    row_fields: string[];      // Field names for table entries
    in_bundles: boolean;
  }
  ```

### 3.2 `GET /api/inventory/modules`
- **Purpose**: Groups the 226 forms into their 50 distinct functional modules (e.g., `admin/status`, `admin/network`, `admin/wireless`, `admin/nat`, `admin/parentctrl`) for navigation filtering.

### 3.3 `POST /api/raw`
- **Purpose**: Dispatches dynamic, low-level calls against any router form using `ArcherAX12.api(path, form, operation, **kwargs)`.
- **Request Body**:
  ```json
  {
    "module": "admin/wireless",
    "form": "wireless_2g",
    "operation": "read",
    "params": {}
  }
  ```
- **Safety Gate**: Rejects destructive system forms (`form="reboot"`, `form="factory_reset"`, `form="firmware_upgrade"`) unless an explicit header `X-Allow-Destructive: true` is passed.
- **Response**: The raw router envelope `{ "success": boolean, "data": Any, "errorcode": Any }`.

---

## 4. UI Architecture & Screen Specifications

The UI organizes into **5 primary views** accessible via a persistent sidebar:

```
┌─────────────────┬──────────────────────────────────────────────────────────────────┐
│  TP-LINK AX12   │  [Live Status: Connected]  [stok: ab12cd...]  [Pause Polling]    │
├─────────────────┼──────────────────────────────────────────────────────────────────┤
│ 📊 Overview     │                                                                  │
│ 💻 Clients (14) │                  MAIN VIEWPORT CONTENT AREA                      │
│ 📡 Wireless     │                                                                  │
│ 🛡️ Security & IP│                                                                  │
│ 🧪 API Explorer │                                                                  │
├─────────────────┴──────────────────────────────────────────────────────────────────┤
│ Host: 192.168.0.1 │ FW: AX12v1_1.10.2 │ [!] Admin Session Exclusive               │
└────────────────────────────────────────────────────────────────────────────────────┘
```

---

### View 1: Telemetry & System Overview (Dominant Feature)
Reflects the lead content of the README.

- **Hero Telemetry Cards**:
  - **CPU Utilization**: Circular Gauge showing percentage (`status.system.cpu_usage * 100`).
  - **Memory Utilization**: Circular Gauge showing percentage (`status.system.mem_usage * 100`).
  - **WAN Gateway**: IP Address, Subnet Mask, Gateway, DNS Servers, and Uptime duration.
  - **LAN Gateway**: IP Address (`192.168.0.1`), Netmask, MAC Address, DHCP Server status.
- **Radio Quick-Cards**:
  - 2.4 GHz Radio: SSID, State (ON/OFF), Channel, HT Mode (`20M` / `40M`).
  - 5.0 GHz Radio: SSID, State (ON/OFF), Channel, HT Mode (`20M` / `40M` / `80M`).
  - Guest Wi-Fi badge: Status and client isolation flag.
- **Session Health & Power Controls**:
  - Session Pill: Green when verified, Amber with spinner when re-authenticating.
  - **Reboot Button**: Red danger button triggering the two-step Confirmation Modal.

---

### View 2: Client Topology & Bandwidth Monitor
Visualizes connected devices using data from `GET /clients` and `GET /wifi/statistics`.

- **Summary Filters**: Total Devices, Wired Devices (`wired`), 2.4G Devices (`2.4G`), 5G Devices (`5G`), and Guest Devices.
- **Interactive Search**: Filter by Hostname, IP address, or MAC address.
- **Client Device Grid / Table**:
  - **Device Identifier**: Hostname (fallback to `<unknown>` if empty), Vendor icon (Mobile, PC, IoT).
  - **Network Coordinates**: Monospace IP (`192.168.0.x`) and normalized MAC (`AA-BB-CC-DD-EE-FF`).
  - **Connection Medium**: Color-coded pill (`Ethernet` in Indigo, `2.4 GHz` in Amber, `5.0 GHz` in Emerald).
  - **Traffic Telemetry**: Transmitted packets (`tx_packets`) & Received packets (`rx_packets`).
  - **Actions**: One-click "Add to DHCP Reservation" and "Block Device" (Access Control).

---

### View 3: Wireless & Radio Configuration
Manages 2.4G & 5G radios via `POST /wifi/config`, `POST /wifi/guest`, and `GET /wifi/capabilities`.

- **Band Configuration Panels** (Split 2.4 GHz / 5 GHz tabs):
  - **SSID Name**: Editable input field.
  - **Channel Selector**: Dynamic dropdown populated *only* with channels accepted by the router according to `/wifi/capabilities` (e.g. 1–13 for 2.4G, 36–161 for 5G).
  - **Bandwidth (HT Mode)**: Dropdown (`20M`, `40M`, `80M`).
  - **Password (PSK)**:
    - Default masked display (`***redacted***`).
    - Eye toggle button to reveal or replace password.
    - Prominent banner: *"Saving Wi-Fi settings will momentarily disconnect wireless clients."*
- **Guest Network Section**:
  - Master Toggle (`enable`).
  - Guest SSID & Password fields.
  - **Client Isolation Switch** (`isolate`): Prevents guests from communicating with LAN devices.

---

### View 4: Security, Access Control & Network Services
Covers DHCP, Access Control, NAT/DMZ, and Wake-on-LAN.

- **Access Control Matrix**:
  - Master Toggle (`POST /access-control`).
  - Mode Switcher: **Blacklist** (`black`) vs. **Whitelist** (`white`).
  - **Protected Host Badge**: Displays the router's immune `host_mac` with a padlock icon, preventing administrative lockouts.
  - Blocked / Allowed Devices Table: Add MAC manually or select from active clients.
- **DHCP Static Reservations**:
  - Table of MAC address -> Fixed IP mappings with names.
  - Modal form to Add / Edit / Delete static bindings (`POST / DELETE /network/dhcp/reservations`).
- **NAT / Forwarding & DMZ**:
  - DMZ Host toggle with internal IP destination input (`POST /nat/dmz`).
  - Port forwarding virtual servers list (`GET /nat/virtual-servers`) with deletion actions.
- **Wake-on-LAN (WoL)**:
  - Saved targets list with target name, MAC, and instant "Wake Device" magic packet trigger button.

---

### View 5: The 226-Endpoint Full-Surface Explorer & Playground
**The centerpiece for managing all API endpoints.**

```
┌─────────────────────────┬─────────────────────────────────────────────────────────┐
│ SEARCH & MODULES        │ admin/wireless?form=wireless_2g                         │
├─────────────────────────┼─────────────────────────────────────────────────────────┤
│ Filter: [All Outcomes ▾]│ Status: [ANSWERED]   Module: admin/wireless             │
│ [Search forms...]       │ Row Form: Yes        Row Fields: name, ssid, channel... │
│                         ├─────────────────────────────────────────────────────────┤
│ ▼ admin/wireless (9)    │ Operation: [read   ▾]   [Send Request ▶]                │
│   ● wireless_2g         ├─────────────────────────────────────────────────────────┤
│   ● wireless_5g         │ Parameters (Form Payload):                              │
│   ● guest_2g            │ {                                                       │
│   ○ wps (not-impl)      │   "operation": "read"                                   │
│ ▶ admin/network (12)    │ }                                                       │
│ ▶ admin/nat (7)         ├─────────────────────────────────────────────────────────┤
│ ▶ admin/parentctrl (6)  │ Response (200 OK - 42ms):                               │
│ ▶ admin/status (5)      │ {                                                       │
│                         │   "success": true,                                      │
│                         │   "data": { "enable": "on", "ssid": "MyNet_2G" }        │
│                         │ }                                                       │
└─────────────────────────┴─────────────────────────────────────────────────────────┘
```

- **Module Tree & Endpoint Selector (Left Pane)**:
  - List of 50 router modules collapsible into folders.
  - Search filter by form name or module path.
  - Status Filter Pills: Filter by `answered` (179), `not-implemented` (18), `needs-parameters` (4), `not-probed` (13), etc.
- **Execution Console (Center/Top Pane)**:
  - Form Header: Displays module name, form name, known row fields, and `others` limit key.
  - **Operation Dropdown**: Autocompletes with the verbs recovered from JS bundles (`read`, `load`, `list`, `write`, `insert`, `update`, `remove`).
  - **Parameter Editor**: Interactive JSON/Key-Value builder for request arguments.
  - **Send Request Button**: Dispatches the query through `POST /api/raw`.
- **Response Inspector (Center/Bottom Pane)**:
  - Response Status Badge (`200 OK`, `501 Not Implemented`, `502 Bad Gateway`).
  - Latency Tracker (`48ms`).
  - Syntax-highlighted JSON viewer with expandable nodes and one-click "Copy JSON".
  - Refusal Field Callout: If the router rejects the operation, automatically highlights the detected refusal key (`errorcode`, `errorCode`, `error`, `error_code`) and error string.

---

## 5. Real-Time State Management & Single-Session Safeguards

### 5.1 Polling Intervals
To prevent saturating the router's embedded MIPS/ARM CPU while keeping UI data fresh:
- **Telemetry & Vitals (`/status`)**: Poll every **5 seconds**.
- **Connected Clients (`/clients`)**: Poll every **15 seconds**.
- **Wireless Statistics (`/wifi/statistics`)**: Poll every **10 seconds** only when the Wireless view is active.
- **Global Pause Button**: A prominent toggle on the header to freeze all background polling during active debugging or configuration.

### 5.2 Session Conflict Handling (Single Admin Session)
The TP-Link Archer AX12 firmware permits **strictly one admin session at any time**:
1. When an external client (e.g. official web UI) logs in, the router disposes the API's token, answering future requests with HTTP 200 and `errorcode: "timeout"`.
2. When this happens, [`app.py`](app.py) handles re-authentication under an asynchronous mutex lock.
3. **UI Behavior**:
   - The UI intercepts `502` or transient re-auth delays and displays a non-blocking toast banner:  
     `⚠️ Router session invalidated by external login. Re-authenticating...`
   - Polling temporarily backs off for 3 seconds to avoid knocking out the new session, then resumes transparently once the client lock resolves.

---

## 6. Destructive Action Safety Modals

Certain hardware commands can cause loss of management connectivity or disrupt network traffic. The UI enforces modal confirmation barriers before execution:

1. **Router Reboot Modal**:
   - Triggered by `POST /reboot`.
   - Displays warning: *"Rebooting will terminate all active internet connections and drop this session for approximately 60 seconds."*
   - Requires user to click "Confirm Reboot" with an active 5-second countdown lock.
2. **Access Control Mode Change Modal**:
   - Triggered when switching to `white` (allow-list) mode.
   - Displays warning: *"Enabling Whitelist mode will immediately disconnect all devices not currently listed in the allowed table. Your protected host MAC is: AA-BB-CC-DD-EE-FF."*
3. **Wi-Fi Credential Modification**:
   - Compares previous SSID/PSK with new values.
   - Alerts user that modifying pre-shared keys will disconnect existing wireless sessions.

---

## 7. Concrete File Structure for UI Implementation

The planned directory layout under the repository root:

```
tplink-router-api/
├── app.py                      # Extended with /api/inventory and /api/raw + StaticFiles mount
├── design.md                   # This master design specification
├── pyproject.toml
├── ui/                         # React + Bun + Vite frontend
│   ├── index.html
│   ├── package.json            # Scripts: dev, build, lint
│   ├── tsconfig.json           # Strict mode TypeScript config
│   ├── vite.config.ts          # Proxy configuration to FastAPI port 8000
│   ├── tailwind.config.js      # TP-Link Dark Slate & Cyan theme tokens
│   └── src/
│       ├── main.tsx            # App bootstrap & TanStack Query provider
│       ├── App.tsx             # Root layout with sidebar & view switcher
│       ├── types/              # TypeScript definitions generated from Pydantic schemas
│       │   ├── router.ts       # Status, ClientDevice, DhcpReservation, etc.
│       │   └── inventory.ts    # 226 Endpoint & module schemas
│       ├── api/                # API client layer (typed fetch wrappers)
│       │   ├── client.ts       # Base HTTP client with re-auth handling
│       │   ├── endpoints.ts    # REST endpoints (/status, /clients, /wifi, etc.)
│       │   └── raw.ts          # /api/raw dispatcher
│       ├── components/         # Reusable UI primitives
│       │   ├── Header.tsx      # Vitals, connection pill, pause polling toggle
│       │   ├── Sidebar.tsx     # Navigation between 5 views
│       │   ├── Gauge.tsx       # CPU & RAM metric dials
│       │   ├── SafetyModal.tsx # Confirmation barriers for reboot & white mode
│       │   └── JsonViewer.tsx  # Syntax-highlighted response inspector
│       └── views/              # View implementations
│           ├── OverviewView.tsx     # Telemetry, gauges, WAN/LAN pills
│           ├── ClientsView.tsx      # Client device grid & search
│           ├── WirelessView.tsx     # 2.4G & 5G radio cards & capabilities
│           ├── SecurityView.tsx     # Access control, DHCP, NAT, WoL
│           └── ApiExplorerView.tsx  # 226-endpoint interactive catalog & console
```
