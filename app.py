import os
import sys
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from tplink_modern import ArcherAX12
from tplink_modern.exceptions import (
    APIError,
    AuthenticationError,
    FeatureUnavailableError,
    NotFoundError,
    RouterError,
)
from tplink_modern.models import (
    AccessControlSettings,
    ClientDevice,
    DhcpReservation,
    DmzSettings,
    ForwardRule,
    LanSettings,
    ManagedDevice,
    OpenVpnConfig,
    PptpVpnConfig,
    RouterStatus,
    VpnConnection,
    WanSettings,
    WolDevice,
    WirelessClientStats,
    redact_secrets,
)


def load_env_file() -> None:
    """Load credentials from .env into environment variables."""
    env_path = os.path.abspath(os.path.join(os.path.dirname(__file__), ".env"))
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    key, val = line.split("=", 1)
                    os.environ[key.strip()] = val.strip().strip('"').strip("'")


# Load variables from .env
load_env_file()

TPLINK_HOST: str = os.environ.get("TPLINK_HOST", "192.168.0.1")
tplink_password_val: Optional[str] = os.environ.get("TPLINK_PASSWORD")

if not tplink_password_val:
    print("CRITICAL ERROR: TPLINK_PASSWORD is not set in .env file.", file=sys.stderr)
    sys.exit(1)

TPLINK_PASSWORD: str = tplink_password_val


# Global router client reference
router: Optional[ArcherAX12] = None


def get_router() -> ArcherAX12:
    """Get the active router client or raise a 503 error if not initialized."""
    if router is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Router client is not initialized or failed to start up."
        )
    return router


# Router failures are the router's fault, not ours, so they default to 502. Anything the
# firmware simply does not implement gets 501 so callers can tell the two apart.
HTTP_BY_ERROR: Dict[Any, int] = {
    NotFoundError: status.HTTP_404_NOT_FOUND,
    FeatureUnavailableError: status.HTTP_501_NOT_IMPLEMENTED,
    ValueError: status.HTTP_400_BAD_REQUEST,
    APIError: status.HTTP_502_BAD_GATEWAY,
    AuthenticationError: status.HTTP_502_BAD_GATEWAY,
    RouterError: status.HTTP_502_BAD_GATEWAY,
}


def status_code_for(exc: BaseException) -> int:
    for cls in type(exc).__mro__:
        if cls in HTTP_BY_ERROR:
            return HTTP_BY_ERROR[cls]
    return status.HTTP_502_BAD_GATEWAY


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager that handles startup login and shutdown logout."""
    global router
    print(f"[*] Initializing connection and logging in to router at {TPLINK_HOST} ...")
    router = ArcherAX12(host=TPLINK_HOST, password=TPLINK_PASSWORD)
    try:
        await router.login()
        print("[+] Router connection established and session verified.")
    except Exception as e:
        print(f"[-] WARNING: Failed to login to router on startup: {e}. Auto-reauth will retry on request.")

    yield

    if router is not None:
        print("[*] Terminating router session and closing client...")
        try:
            await router.close()
            print("[+] Router connection closed.")
        except Exception as e:
            print(f"[-] Error closing router session: {e}")


app = FastAPI(
    title="TP-Link Modern Router API REST Wrapper",
    description="A FastAPI REST API wrapper for the tplink-modern router SDK.",
    version="0.1.0",
    lifespan=lifespan
)


@app.exception_handler(RouterError)
async def router_error_handler(request: Request, exc: RouterError) -> JSONResponse:
    """Map router SDK failures onto meaningful HTTP codes."""
    body: Dict[str, Any] = {"detail": str(exc)}
    errorcode = getattr(exc, "errorcode", None)
    if errorcode is not None:
        body["errorcode"] = errorcode
    return JSONResponse(status_code=status_code_for(exc), content=body)


@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError) -> JSONResponse:
    """Bad arguments are the caller's mistake, not the router's."""
    return JSONResponse(status_code=status.HTTP_400_BAD_REQUEST, content={"detail": str(exc)})


@app.get("/status", response_model=RouterStatus, summary="Get complete router status")
async def get_status(include_secrets: bool = False):
    """Retrieve system resource usage, LAN, WAN, and Wi-Fi band configurations.

    Wi-Fi pre-shared keys are redacted unless `include_secrets=true` is passed.
    """
    client = get_router()
    router_status = await client.status.get()
    if include_secrets:
        return router_status
    return redact_secrets(router_status)


@app.get("/clients", response_model=List[ClientDevice], summary="Get connected client devices")
async def get_clients():
    """Retrieve details (hostnames, IP, MAC addresses) of all connected wired and wireless devices."""
    client = get_router()
    return await client.clients.get_all()


@app.get("/firmware", response_model=Dict[str, Any], summary="Check for firmware upgrades")
async def check_firmware():
    """Check if there is an upgrade package available for the router."""
    client = get_router()
    return await client.firmware.check_upgrade()


@app.get("/network/lan", response_model=LanSettings, summary="Get LAN configuration")
async def get_lan():
    """Get the local area network configuration, including IP, netmask, MAC, and DHCP status."""
    client = get_router()
    return await client.network.get_lan()


@app.get("/network/wan", response_model=WanSettings, summary="Get WAN configuration")
async def get_wan():
    """Get the wide area network configuration, including public IP, gateway, DNS, and uptime."""
    client = get_router()
    return await client.network.get_wan()


# --- Stage 1: DHCP Reservations ---

@app.get("/network/dhcp/reservations", response_model=List[DhcpReservation], summary="Get DHCP address reservations")
async def get_dhcp_reservations():
    """Retrieve all static address reservations mapping specific MAC addresses to fixed IPs."""
    client = get_router()
    return await client.network.get_dhcp_reservations()


@app.post("/network/dhcp/reservations", summary="Add DHCP address reservation")
async def add_dhcp_reservation(req: DhcpReservation):
    """Add a new static DHCP address reservation mapping a MAC address to a fixed IP."""
    client = get_router()
    success = await client.network.add_dhcp_reservation(
        macaddr=req.macaddr,
        ipaddr=req.ipaddr,
        name=req.name or "",
        enable=req.enable
    )
    return {"success": success}


@app.delete("/network/dhcp/reservations/{macaddr}", summary="Delete DHCP address reservation")
async def delete_dhcp_reservation(macaddr: str):
    """Remove an existing static DHCP address reservation by MAC address."""
    client = get_router()
    success = await client.network.delete_dhcp_reservation(macaddr=macaddr)
    return {"success": success}


# --- Access control: block or allow a device ---

class AccessControlUpdate(BaseModel):
    enable: Optional[bool] = None
    mode: Optional[str] = None


class DeviceMACRequest(BaseModel):
    macaddr: str


@app.get("/access-control", response_model=AccessControlSettings, summary="Get access-control state")
async def get_access_control():
    """Whether access control is on, which list mode it uses, and the protected host MAC."""
    client = get_router()
    return await client.access.get_settings()


@app.post("/access-control", summary="Enable access control or switch its list mode")
async def update_access_control(req: AccessControlUpdate):
    """Turn access control on/off, or choose 'black' (block listed) / 'white' (allow only listed)."""
    client = get_router()
    if req.enable is None and req.mode is None:
        raise ValueError("provide 'enable' and/or 'mode'")
    if req.enable is not None:
        await client.access.set_enabled(req.enable)
    if req.mode is not None:
        await client.access.set_mode(req.mode)
    return {"success": True}


@app.get("/access-control/devices", response_model=List[ManagedDevice], summary="List devices that can be listed")
async def get_access_control_devices(list_type: str = "black"):
    """Devices the router offers for the block ('black') or allow ('white') list."""
    client = get_router()
    return await client.access.devices(list_type)


@app.get("/access-control/blocked", response_model=List[str], summary="List blocked MAC addresses")
async def get_blocked_devices():
    """MACs currently on the block list."""
    client = get_router()
    return await client.access.blocked()


@app.get("/access-control/allowed", response_model=List[str], summary="List allowed MAC addresses")
async def get_allowed_devices():
    """MACs currently on the allow list."""
    client = get_router()
    return await client.access.allowed()


@app.post("/access-control/block", summary="Block a device by MAC address")
async def block_device(req: DeviceMACRequest):
    """Add a device to the block list. It must be a device the router has already seen."""
    client = get_router()
    return {"success": await client.access.block(req.macaddr)}


@app.delete("/access-control/block/{macaddr}", summary="Unblock a device")
async def unblock_device(macaddr: str):
    """Remove a MAC from the block list."""
    client = get_router()
    return {"success": await client.access.unblock(macaddr)}


@app.post("/access-control/allow", summary="Allow a device by MAC address")
async def allow_device(req: DeviceMACRequest):
    """Add a device to the allow list (only takes effect while mode is 'white')."""
    client = get_router()
    return {"success": await client.access.allow(req.macaddr)}


@app.delete("/access-control/allow/{macaddr}", summary="Remove a device from the allow list")
async def undisallow_device(macaddr: str):
    """Remove a MAC from the allow list."""
    client = get_router()
    return {"success": await client.access.unallow(macaddr)}


# --- Stage 2 & 4: Wireless Settings & Stats ---

class WifiConfigRequest(BaseModel):
    band: str
    ssid: Optional[str] = None
    password: Optional[str] = None
    enable: Optional[bool] = None
    channel: Optional[str] = None
    htmode: Optional[str] = None


@app.post("/wifi/config", summary="Configure advanced Wi-Fi network settings")
async def configure_wifi(req: WifiConfigRequest):
    """Update wireless band configuration (SSID, password, status, channel, HT mode) for 2.4GHz or 5GHz."""
    client = get_router()
    success = await client.wifi.set_wireless_band(
        band=req.band,
        ssid=req.ssid,
        password=req.password,
        enable=req.enable,
        channel=req.channel,
        htmode=req.htmode
    )
    return {"success": success}


class GuestWifiRequest(BaseModel):
    enable: Optional[bool] = None
    isolate: Optional[bool] = None
    ssid: Optional[str] = None
    password: Optional[str] = None
    bands: Optional[List[str]] = None


@app.post("/wifi/guest", summary="Update guest Wi-Fi network settings")
async def update_guest_wifi(req: GuestWifiRequest):
    """Toggle guest Wi-Fi and isolation, or rename it and set its password.

    Omitted fields keep their current values, so enabling the network cannot blank the
    SSID or key. At least one field is required.
    """
    client = get_router()
    success = await client.wifi.set_guest(
        enable=req.enable,
        isolate=req.isolate,
        ssid=req.ssid,
        password=req.password,
        bands=req.bands,
    )
    return {"success": success}


@app.get("/wifi/statistics", response_model=List[WirelessClientStats], summary="Get wireless client statistics")
async def get_wifi_statistics():
    """Retrieve detailed packets sent/received statistics for all connected wireless client devices."""
    client = get_router()
    return await client.wifi.get_statistics()


# --- Stage 3: VPN Servers & Connections ---

@app.get("/vpn/openvpn", response_model=OpenVpnConfig, summary="Get OpenVPN configuration")
async def get_openvpn_config():
    """Retrieve current OpenVPN server configuration details."""
    client = get_router()
    return await client.vpn.get_openvpn()


@app.post("/vpn/openvpn", summary="Update OpenVPN server configuration")
async def update_openvpn_config(req: OpenVpnConfig):
    """Update OpenVPN server configurations."""
    client = get_router()
    success = await client.vpn.set_openvpn(req)
    return {"success": success}


@app.get("/vpn/pptp", response_model=PptpVpnConfig, summary="Get PPTP VPN configuration")
async def get_pptp_config():
    """Retrieve current PPTP VPN server configuration details."""
    client = get_router()
    return await client.vpn.get_pptp()


@app.post("/vpn/pptp", summary="Update PPTP VPN server configuration")
async def update_pptp_config(req: PptpVpnConfig):
    """Update PPTP VPN server configurations."""
    client = get_router()
    success = await client.vpn.set_pptp(req)
    return {"success": success}


@app.get("/vpn/connections", response_model=List[VpnConnection], summary="Get active VPN connections")
async def get_vpn_connections():
    """List all active incoming OpenVPN and PPTP connections to the router."""
    client = get_router()
    return await client.vpn.get_connections()


# --- Wake on LAN and port forwarding ---

class WakeRequest(BaseModel):
    macaddr: Optional[str] = None
    name: Optional[str] = None


class WolDeviceRequest(BaseModel):
    macaddr: str
    name: str = ""


class DmzRequest(BaseModel):
    enable: bool
    ipaddr: str = ""


@app.get("/wol/devices", response_model=List[WolDevice], summary="List saved Wake-on-LAN targets")
async def get_wol_devices():
    """Devices the router has stored for waking. It does not infer them from the client list."""
    client = get_router()
    return await client.wol.devices()


@app.post("/wol/devices", summary="Save a Wake-on-LAN target")
async def add_wol_device(req: WolDeviceRequest):
    """Add a MAC (and optional name) the router may send a magic packet to."""
    client = get_router()
    return {"success": await client.wol.add(req.macaddr, req.name)}


@app.delete("/wol/devices/{macaddr}", summary="Delete a Wake-on-LAN target")
async def remove_wol_device(macaddr: str):
    """Remove a saved wake target by MAC."""
    client = get_router()
    return {"success": await client.wol.remove(macaddr)}


@app.post("/wol/wake", summary="Send a magic packet to a saved device")
async def wake_device(req: WakeRequest):
    """Wake a device the router has saved, by MAC or name."""
    client = get_router()
    return {"success": await client.wol.wake(macaddr=req.macaddr, name=req.name)}


@app.get("/nat/dmz", response_model=DmzSettings, summary="Get DMZ settings")
async def get_dmz():
    """Whether a DMZ host is configured and which internal address it points at."""
    client = get_router()
    return await client.nat.get_dmz()


@app.post("/nat/dmz", summary="Configure the DMZ host")
async def set_dmz(req: DmzRequest):
    """Expose one internal host to the internet, or remove it from the DMZ."""
    client = get_router()
    return {"success": await client.nat.set_dmz(req.enable, req.ipaddr)}


@app.get("/nat/virtual-servers", response_model=List[ForwardRule], summary="List port forwarding rules")
async def get_virtual_servers():
    """Port forwarding rules as the router reports them."""
    client = get_router()
    return await client.nat.virtual_servers()


@app.delete("/nat/virtual-servers/{key}", summary="Delete a port forwarding rule")
async def delete_virtual_server(key: str):
    """Remove a virtual server rule by the key the router assigned it."""
    client = get_router()
    return {"success": await client.nat.delete_virtual_server(key)}


@app.get("/nat/port-triggers", response_model=List[ForwardRule], summary="List port triggering rules")
async def get_port_triggers():
    """Port triggering rules as the router reports them."""
    client = get_router()
    return await client.nat.port_triggers()


@app.delete("/nat/port-triggers/{key}", summary="Delete a port triggering rule")
async def delete_port_trigger(key: str):
    """Remove a port trigger rule by the key the router assigned it."""
    client = get_router()
    return {"success": await client.nat.delete_port_trigger(key)}


# --- System Controls ---

@app.post("/reboot", summary="Trigger a router reboot")
async def reboot():
    """Request the router to perform a system restart."""
    client = get_router()
    success = await client.system.reboot()
    return {"success": success}
