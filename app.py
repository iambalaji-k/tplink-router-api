import os
import sys
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional
from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel

from tplink_modern import ArcherAX12
from tplink_modern.exceptions import RouterError
from tplink_modern.models import (
    RouterStatus,
    ClientDevice,
    LanSettings,
    WanSettings,
    DhcpReservation,
    OpenVpnConfig,
    PptpVpnConfig,
    VpnConnection,
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


@app.get("/status", response_model=RouterStatus, summary="Get complete router status")
async def get_status(include_secrets: bool = False):
    """Retrieve system resource usage, LAN, WAN, and Wi-Fi band configurations.

    Wi-Fi pre-shared keys are redacted unless `include_secrets=true` is passed.
    """
    client = get_router()
    try:
        router_status = await client.status.get()
    except RouterError as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

    if include_secrets:
        return router_status
    return redact_secrets(router_status)


@app.get("/clients", response_model=List[ClientDevice], summary="Get connected client devices")
async def get_clients():
    """Retrieve details (hostnames, IP, MAC addresses) of all connected wired and wireless devices."""
    client = get_router()
    try:
        return await client.clients.get_all()
    except RouterError as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@app.get("/firmware", response_model=Dict[str, Any], summary="Check for firmware upgrades")
async def check_firmware():
    """Check if there is an upgrade package available for the router."""
    client = get_router()
    try:
        return await client.firmware.check_upgrade()
    except RouterError as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@app.get("/network/lan", response_model=LanSettings, summary="Get LAN configuration")
async def get_lan():
    """Get the local area network configuration, including IP, netmask, MAC, and DHCP status."""
    client = get_router()
    try:
        return await client.network.get_lan()
    except RouterError as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@app.get("/network/wan", response_model=WanSettings, summary="Get WAN configuration")
async def get_wan():
    """Get the wide area network configuration, including public IP, gateway, DNS, and uptime."""
    client = get_router()
    try:
        return await client.network.get_wan()
    except RouterError as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


# --- Stage 1: DHCP Reservations ---

@app.get("/network/dhcp/reservations", response_model=List[DhcpReservation], summary="Get DHCP address reservations")
async def get_dhcp_reservations():
    """Retrieve all static address reservations mapping specific MAC addresses to fixed IPs."""
    client = get_router()
    try:
        return await client.network.get_dhcp_reservations()
    except RouterError as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@app.post("/network/dhcp/reservations", summary="Add DHCP address reservation")
async def add_dhcp_reservation(req: DhcpReservation):
    """Add a new static DHCP address reservation mapping a MAC address to a fixed IP."""
    client = get_router()
    try:
        success = await client.network.add_dhcp_reservation(
            macaddr=req.macaddr,
            ipaddr=req.ipaddr,
            name=req.name or "",
            enable=req.enable
        )
        return {"success": success}
    except RouterError as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@app.delete("/network/dhcp/reservations/{macaddr}", summary="Delete DHCP address reservation")
async def delete_dhcp_reservation(macaddr: str):
    """Remove an existing static DHCP address reservation by MAC address."""
    client = get_router()
    try:
        success = await client.network.delete_dhcp_reservation(macaddr=macaddr)
        return {"success": success}
    except RouterError as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


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
    try:
        success = await client.wifi.set_wireless_band(
            band=req.band,
            ssid=req.ssid,
            password=req.password,
            enable=req.enable,
            channel=req.channel,
            htmode=req.htmode
        )
        return {"success": success}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except RouterError as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


class GuestWifiRequest(BaseModel):
    enable: bool
    isolate: bool = False


@app.post("/wifi/guest", summary="Update guest Wi-Fi network settings")
async def update_guest_wifi(req: GuestWifiRequest):
    """Enable/disable guest Wi-Fi and configure client isolation."""
    client = get_router()
    try:
        success = await client.wifi.set_guest(enable=req.enable, isolate=req.isolate)
        return {"success": success}
    except RouterError as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@app.get("/wifi/statistics", response_model=List[WirelessClientStats], summary="Get wireless client statistics")
async def get_wifi_statistics():
    """Retrieve detailed packets sent/received statistics for all wireless client devices."""
    client = get_router()
    try:
        return await client.wifi.get_statistics()
    except RouterError as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


# --- Stage 3: VPN Servers & Connections ---

@app.get("/vpn/openvpn", response_model=OpenVpnConfig, summary="Get OpenVPN configuration")
async def get_openvpn_config():
    """Retrieve current OpenVPN server configuration details."""
    client = get_router()
    try:
        return await client.vpn.get_openvpn()
    except RouterError as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@app.post("/vpn/openvpn", summary="Update OpenVPN server configuration")
async def update_openvpn_config(req: OpenVpnConfig):
    """Update OpenVPN server configurations."""
    client = get_router()
    try:
        success = await client.vpn.set_openvpn(req)
        return {"success": success}
    except RouterError as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@app.get("/vpn/pptp", response_model=PptpVpnConfig, summary="Get PPTP VPN configuration")
async def get_pptp_config():
    """Retrieve current PPTP VPN server configuration details."""
    client = get_router()
    try:
        return await client.vpn.get_pptp()
    except RouterError as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@app.post("/vpn/pptp", summary="Update PPTP VPN server configuration")
async def update_pptp_config(req: PptpVpnConfig):
    """Update PPTP VPN server configurations."""
    client = get_router()
    try:
        success = await client.vpn.set_pptp(req)
        return {"success": success}
    except RouterError as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@app.get("/vpn/connections", response_model=List[VpnConnection], summary="Get active VPN connections")
async def get_vpn_connections():
    """List all active incoming OpenVPN and PPTP connections to the router."""
    client = get_router()
    try:
        return await client.vpn.get_connections()
    except RouterError as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


# --- System Controls ---

@app.post("/reboot", summary="Trigger a router reboot")
async def reboot():
    """Request the router to perform a system restart."""
    client = get_router()
    try:
        success = await client.system.reboot()
        return {"success": success}
    except RouterError as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


