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
├── examples/               # SDK Usage Examples
│   ├── login.py
│   ├── devices.py
│   ├── status.py
│   └── reboot.py
│
├── tests/                  # Unit and Integration Tests
│   └── test_login.py
│
└── tplink_modern/          # Python SDK package
    ├── __init__.py         # Package entry point
    ├── client.py           # ArcherAX12 high-level client
    ├── auth.py             # RSA-based login handshake logic
    ├── crypto.py           # RSA PKCS#1 v1.5 utilities
    ├── session.py          # Session management & auto-reauth HTTP client
    ├── endpoints.py        # Router API JSON request paths
    ├── exceptions.py       # Custom RouterException definitions
    ├── models.py           # Pydantic schemas for type safety
    └── resources/          # API resources
        ├── __init__.py
        ├── base.py         # Base Resource class
        ├── clients.py      # Connected client device queries
        ├── firmware.py     # Upgrade check actions
        ├── network.py      # LAN / WAN settings
        ├── status.py       # General router status
        ├── system.py       # Reboot and system commands
        └── wifi.py         # Guest and main Wi-Fi configurations
```

## Features
- **Robust Authentication**: Handles standard 1024-bit RSA PKCS#1 v1.5 key-exchange and encryption.
- **Session Resilience**: Automatic session check, keep-alive, and transparent re-authentication on token expiration.
- **Strong Typing**: Strongly typed Pydantic models for responses and settings (LAN, WAN, Wifi, Connected Clients, etc.).
- **Sub-Resource Client**: Modular layout where router components are accessed intuitively via `router.status`, `router.wifi`, `router.clients`, etc.
- **REST Wrapper**: Full-featured FastAPI server with lifespan state management and auto-generated OpenAPI documentation.

---

## Installation & Setup

Requires Python 3.11+.

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

3. **Install Dependencies** (package and dev/prod tools):
   ```bash
   pip install -e .
   ```

4. **Configure Environment variables**:
   Create a `.env` file in the root of the project:
   ```env
   TPLINK_HOST=192.168.0.1
   TPLINK_PASSWORD=your_router_admin_password
   ```

---

## SDK Usage Examples

### 1. Connecting and Checking Status
```python
import asyncio
from tplink_modern import ArcherAX12

async def main():
    # Use context manager for automatic cleanup
    async with ArcherAX12(host="192.168.0.1", password="YOUR_PASSWORD") as router:
        await router.login()
        status = await router.status.get()
        print(f"Device: {status.device_info.model}")
        print(f"CPU Load: {status.cpu_usage}%")
        print(f"Memory Load: {status.mem_usage}%")

if __name__ == "__main__":
    asyncio.run(main())
```

### 2. Querying Connected Clients
```python
import asyncio
from tplink_modern import ArcherAX12

async def main():
    async with ArcherAX12(host="192.168.0.1", password="YOUR_PASSWORD") as router:
        await router.login()
        clients = await router.clients.get_all()
        for device in clients:
            print(f"[{device.connection_type}] {device.name} - IP: {device.ip_address} (MAC: {device.mac_address})")

if __name__ == "__main__":
    asyncio.run(main())
```

### 3. Configuring Guest Wi-Fi
```python
import asyncio
from tplink_modern import ArcherAX12

async def main():
    async with ArcherAX12(host="192.168.0.1", password="YOUR_PASSWORD") as router:
        await router.login()
        # Enable guest network with client isolation
        success = await router.wifi.set_guest(enable=True, isolate=True)
        print(f"Guest Wifi Configured: {success}")

if __name__ == "__main__":
    asyncio.run(main())
```

---

## Running the FastAPI REST Server

You can expose the SDK as a high-performance REST service. The server initializes a shared `ArcherAX12` client and coordinates the connection lifespan automatically.

Start the FastAPI application:
```bash
uvicorn app:app --host 0.0.0.0 --port 8000 --reload
```

### API Endpoints
- `GET /status` - Complete system resource usage, CPU, RAM, LAN, and Wi-Fi band configurations.
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

### OpenAPI Documentation
Once the server is running, navigate to:
- **Swagger UI**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **ReDoc**: [http://localhost:8000/redoc](http://localhost:8000/redoc)

---

## Running Tests & Type Checks

Ensure code quality using static analysis and mock tests:

```bash
# Type checking
mypy .

# Linter
ruff check .

# Unit Tests (Mocking HTTP endpoints)
pytest
```

