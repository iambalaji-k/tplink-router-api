from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any


class ClientDevice(BaseModel):
    """Represents a device connected to the router."""
    hostname: str = ""
    ipaddr: str = ""
    macaddr: str = ""
    wire_type: str = Field(default="wired", description="Connection type: 'wired', '2.4G', or '5G'")


class DhcpReservation(BaseModel):
    """Represents a DHCP static address reservation entry."""
    macaddr: str
    ipaddr: str
    enable: bool = True
    name: Optional[str] = None


class OpenVpnConfig(BaseModel):
    """Configuration settings for the OpenVPN server."""
    enable: bool
    proto: str = "udp"
    port: int = 1194
    serverip: str = "10.8.0.0"
    mask: str = "255.255.255.0"


class PptpVpnConfig(BaseModel):
    """Configuration settings for the PPTP VPN server."""
    enable: bool
    remoteip: str = "10.0.0.11-20"


class VpnConnection(BaseModel):
    """Represents an active incoming VPN connection."""
    username: str
    ipaddr: str
    macaddr: Optional[str] = None
    uptime: Optional[str] = None
    vpntype: str  # 'openvpn' or 'pptp'


class WirelessClientStats(BaseModel):
    """Wireless statistics for a specific connected client."""
    macaddr: str
    band: str  # '2.4GHz' or '5GHz'
    encryption: str
    rx_packets: int
    tx_packets: int





REDACTED_PSK = "***redacted***"


def redact_secrets(model: BaseModel) -> BaseModel:
    """Return a copy of `model` with every pre-shared key replaced by a placeholder.

    Recurses through nested models, so `***` never leaks back into a router write:
    the SDK keeps operating on the unredacted object and only this copy is exposed.
    """
    clone = model.model_copy(deep=True)
    for name in type(clone).model_fields:
        value = getattr(clone, name)
        if isinstance(value, BaseModel):
            setattr(clone, name, redact_secrets(value))
        elif name.endswith("psk_key") and value:
            setattr(clone, name, REDACTED_PSK)
    return clone


class AccessControlSettings(BaseModel):
    """Parental-control / access-control list state."""
    enable: bool = False
    mode: str = Field(default="black", description="'black' blocks listed devices, 'white' allows only listed ones")
    host_mac: str = Field(default="", description="MAC the router never blocks (usually the one it is configured from)")


class ManagedDevice(BaseModel):
    """A device the router offers to put on an access-control list."""
    macaddr: str
    name: str = ""
    ipaddr: str = ""
    conn_type: str = ""
    band: str = Field(default="", description="Raw band, e.g. '2.4G' or '5G'")
    device_type: str = Field(default="", description="Router's own guess, e.g. 'Mobile'")
    is_guest: bool = False

    @classmethod
    def from_router(cls, raw: Dict[str, Any]) -> "ManagedDevice":
        return cls(
            macaddr=raw.get("mac", ""),
            name=raw.get("name", ""),
            ipaddr=raw.get("ipaddr", ""),
            conn_type=raw.get("conn_type", ""),
            band=raw.get("raw_conn_type", ""),
            device_type=raw.get("type", ""),
            is_guest=raw.get("guest") == "GUEST",
        )


class SystemResource(BaseModel):
    """System utilization metrics."""
    cpu_usage: float = Field(default=0.0, description="CPU usage ratio (0.0 to 1.0)")
    mem_usage: float = Field(default=0.0, description="Memory usage ratio (0.0 to 1.0)")
    cpu1_usage: Optional[float] = Field(default=None, description="Secondary CPU core usage if available")


class WirelessBandConfig(BaseModel):
    """Wireless network configuration for a specific frequency band."""
    ssid: str = ""
    enable: bool = False
    macaddr: str = ""
    channel: str = Field(default="auto", description="Configured channel setting (e.g. 'auto' or channel number)")
    current_channel: Optional[str] = Field(default=None, description="Actual operating channel")
    encryption: str = "none"
    psk_key: Optional[str] = Field(default=None, description="WPA/WPA2 pre-shared key (password)")
    psk_cipher: Optional[str] = Field(default=None, description="Cipher used (e.g. 'aes', 'tkip')")
    htmode: Optional[str] = Field(default=None, description="Channel width configuration (e.g. '20', '40', '80')")
    hwmode: Optional[str] = Field(default=None, description="IEEE 802.11 mode (e.g. 'bgn', 'anacax')")


class LanSettings(BaseModel):
    """Local Area Network settings of the router."""
    ipaddr: str = ""
    netmask: str = ""
    macaddr: str = ""
    dhcp_enable: bool = False
    ipv6_ipaddr: Optional[str] = None
    ipv6_link_local: Optional[str] = None


class WanSettings(BaseModel):
    """Wide Area Network (Internet) interface settings."""
    ipaddr: str = ""
    netmask: str = ""
    gateway: str = ""
    macaddr: str = ""
    conntype: str = Field(default="dhcp", description="Connection type (e.g. 'dhcp', 'static', 'pppoe')")
    pridns: str = Field(default="", description="Primary DNS server")
    snddns: Optional[str] = Field(default=None, description="Secondary DNS server")
    uptime: int = Field(default=0, description="WAN connection uptime in seconds")


class GuestNetworkConfig(BaseModel):
    """Guest network settings."""
    isolate: bool = Field(default=False, description="Whether guest clients are isolated from the main LAN")
    guest_access: bool = Field(default=False, description="Whether guest clients can access the router's settings")
    
    # 2.4G Guest network
    guest_2g_ssid: str = ""
    guest_2g_enable: bool = False
    guest_2g_psk_key: Optional[str] = None
    
    # 5G Guest network
    guest_5g_ssid: str = ""
    guest_5g_enable: bool = False
    guest_5g_psk_key: Optional[str] = None


class RouterStatus(BaseModel):
    """Root model representing the complete status of the router."""
    system: SystemResource = SystemResource()
    lan: LanSettings = LanSettings()
    wan: WanSettings = WanSettings()
    wireless_2g: WirelessBandConfig = WirelessBandConfig()
    wireless_5g: WirelessBandConfig = WirelessBandConfig()
    guest: GuestNetworkConfig = GuestNetworkConfig()
    clients: List[ClientDevice] = Field(default_factory=list)

    @classmethod
    def from_raw(cls, raw_data: Dict[str, Any]) -> "RouterStatus":
        """Factory method to parse and map raw router status API JSON into RouterStatus."""
        
        def to_bool(val: Any) -> bool:
            if isinstance(val, bool):
                return val
            if isinstance(val, str):
                return val.lower() in ("on", "true", "yes", "1")
            return bool(val)

        # 1. Parse connected client devices
        clients = []
        for dev in raw_data.get("access_devices_wired", []):
            clients.append(ClientDevice(
                hostname=dev.get("hostname", ""),
                ipaddr=dev.get("ipaddr", ""),
                macaddr=dev.get("macaddr", ""),
                wire_type="wired"
            ))
        for dev in raw_data.get("access_devices_wireless_host", []):
            clients.append(ClientDevice(
                hostname=dev.get("hostname", ""),
                ipaddr=dev.get("ipaddr", ""),
                macaddr=dev.get("macaddr", ""),
                wire_type=dev.get("wire_type", "wireless")
            ))

        # 2. Parse system utilization
        system = SystemResource(
            cpu_usage=raw_data.get("cpu_usage", 0.0),
            mem_usage=raw_data.get("mem_usage", 0.0),
            cpu1_usage=raw_data.get("cpu1_usage")
        )

        # 3. Parse LAN configuration
        lan = LanSettings(
            ipaddr=raw_data.get("lan_ipv4_ipaddr", ""),
            netmask=raw_data.get("lan_ipv4_netmask", ""),
            macaddr=raw_data.get("lan_macaddr", ""),
            dhcp_enable=to_bool(raw_data.get("lan_ipv4_dhcp_enable")),
            ipv6_ipaddr=raw_data.get("lan_ipv6_ipaddr"),
            ipv6_link_local=raw_data.get("lan_ipv6_link_local_addr")
        )

        # 4. Parse WAN configuration
        wan = WanSettings(
            ipaddr=raw_data.get("wan_ipv4_ipaddr", ""),
            netmask=raw_data.get("wan_ipv4_netmask", ""),
            gateway=raw_data.get("wan_ipv4_gateway", ""),
            macaddr=raw_data.get("wan_macaddr", ""),
            conntype=raw_data.get("wan_ipv4_conntype", ""),
            pridns=raw_data.get("wan_ipv4_pridns", ""),
            snddns=raw_data.get("wan_ipv4_snddns"),
            uptime=int(raw_data.get("wan_ipv4_uptime", 0))
        )

        # 5. Parse 2.4GHz Wireless configuration
        wireless_2g = WirelessBandConfig(
            ssid=raw_data.get("wireless_2g_ssid", ""),
            enable=to_bool(raw_data.get("wireless_2g_enable")),
            macaddr=raw_data.get("wireless_2g_macaddr", ""),
            channel=raw_data.get("wireless_2g_channel", ""),
            current_channel=raw_data.get("wireless_2g_current_channel"),
            encryption=raw_data.get("wireless_2g_encryption", ""),
            psk_key=raw_data.get("wireless_2g_psk_key"),
            psk_cipher=raw_data.get("wireless_2g_psk_cipher"),
            htmode=raw_data.get("wireless_2g_htmode"),
            hwmode=raw_data.get("wireless_2g_hwmode")
        )

        # 6. Parse 5GHz Wireless configuration
        wireless_5g = WirelessBandConfig(
            ssid=raw_data.get("wireless_5g_ssid", ""),
            enable=to_bool(raw_data.get("wireless_5g_enable")),
            macaddr=raw_data.get("wireless_5g_macaddr", ""),
            channel=raw_data.get("wireless_5g_channel", ""),
            current_channel=raw_data.get("wireless_5g_current_channel"),
            encryption=raw_data.get("wireless_5g_encryption", ""),
            psk_key=raw_data.get("wireless_5g_psk_key"),
            psk_cipher=raw_data.get("wireless_5g_psk_cipher"),
            htmode=raw_data.get("wireless_5g_htmode"),
            hwmode=raw_data.get("wireless_5g_hwmode")
        )

        # 7. Parse Guest Network configuration
        guest = GuestNetworkConfig(
            isolate=to_bool(raw_data.get("guest_isolate")),
            guest_access=to_bool(raw_data.get("guest_access")),
            guest_2g_ssid=raw_data.get("guest_2g_ssid", ""),
            guest_2g_enable=to_bool(raw_data.get("guest_2g_enable")),
            guest_2g_psk_key=raw_data.get("guest_2g_psk_key"),
            guest_5g_ssid=raw_data.get("guest_5g_ssid", ""),
            guest_5g_enable=to_bool(raw_data.get("guest_5g_enable")),
            guest_5g_psk_key=raw_data.get("guest_5g_psk_key")
        )

        return cls(
            system=system,
            lan=lan,
            wan=wan,
            wireless_2g=wireless_2g,
            wireless_5g=wireless_5g,
            guest=guest,
            clients=clients
        )
