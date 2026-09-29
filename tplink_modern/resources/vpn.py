from tplink_modern.exceptions import FeatureUnavailableError
from tplink_modern.models import OpenVpnConfig, PptpVpnConfig, VpnConnection
from tplink_modern.resources.base import BaseResource

# The router omits the address for connections that have not negotiated one yet.
UNKNOWN_PEER_IP = "0.0.0.0"  # noqa: S104


class VpnResource(BaseResource):
    """Resource to query and configure VPN Server settings on the router."""

    async def get_openvpn(self) -> OpenVpnConfig:
        """Get current OpenVPN server configuration."""
        res = await self.client.api("admin/openvpn", "config", "read")

        data = res.get("data", {})
        return OpenVpnConfig(
            enable=data.get("enabled") == "on",
            proto=data.get("proto", "udp"),
            port=int(data.get("port", "1194")),
            serverip=data.get("serverip", "10.8.0.0"),
            mask=data.get("mask", "255.255.255.0")
        )

    async def set_openvpn(self, config: OpenVpnConfig) -> bool:
        """Update OpenVPN server configuration."""
        payload = {
            "enabled": "on" if config.enable else "off",
            "proto": config.proto,
            "port": str(config.port),
            "serverip": config.serverip,
            "mask": config.mask,
            "interface_type": "tun",
            "access": "home"
        }
        await self.client.write("admin/openvpn", "config", **payload)
        return True

    async def get_pptp(self) -> PptpVpnConfig:
        """Get current PPTP VPN server configuration."""
        res = await self.client.api("admin/pptpd", "config", "read")

        data = res.get("data", {})
        return PptpVpnConfig(
            enable=data.get("enabled") == "on",
            remoteip=data.get("remoteip", "10.0.0.11-20")
        )

    async def set_pptp(self, config: PptpVpnConfig) -> bool:
        """Update PPTP VPN server configuration."""
        payload = {
            "enabled": "on" if config.enable else "off",
            "remoteip": config.remoteip,
            "unencrypted_access": "on",
            "samba_access": "on",
            "netbios_pass": "on"
        }
        await self.client.write("admin/pptpd", "config", **payload)
        return True

    async def get_connections(self) -> list[VpnConnection]:
        """Get all active incoming OpenVPN and PPTP connections."""
        return [*(await self._connections("openvpn")), *(await self._connections("pptp"))]

    async def _connections(self, vpntype: str) -> list[VpnConnection]:
        """Connections for one VPN type.

        Only "this firmware has no such server" is treated as empty. Anything else --
        a refused session, a malformed answer -- propagates, because the previous
        version swallowed every error and reported "nobody connected".
        """
        try:
            resp = await self.client.api("admin/vpnconn", "config", "list", vpntype=vpntype)
        except FeatureUnavailableError:
            return []

        rows = resp.get("data")
        if isinstance(rows, dict):
            rows = list(rows.values())

        return [
            VpnConnection(
                username=row.get("username") or row.get("name", "unknown"),
                ipaddr=row.get("ipaddr") or row.get("ip", UNKNOWN_PEER_IP),
                macaddr=row.get("macaddr") or row.get("mac"),
                uptime=row.get("uptime"),
                vpntype=vpntype,
            )
            for row in rows or []
            if isinstance(row, dict)
        ]
