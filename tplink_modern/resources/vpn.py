from typing import List
from tplink_modern.resources.base import BaseResource
from tplink_modern.models import OpenVpnConfig, PptpVpnConfig, VpnConnection
from tplink_modern.exceptions import RouterError


class VpnResource(BaseResource):
    """Resource to query and configure VPN Server settings on the router."""

    async def get_openvpn(self) -> OpenVpnConfig:
        """Get current OpenVPN server configuration."""
        res = await self.client.api("admin/openvpn", "config", "read")
        if not res.get("success"):
            raise RouterError("Failed to fetch OpenVPN configuration")
            
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
        res = await self.client.write("admin/openvpn", "config", **payload)
        return bool(res.get("success"))

    async def get_pptp(self) -> PptpVpnConfig:
        """Get current PPTP VPN server configuration."""
        res = await self.client.api("admin/pptpd", "config", "read")
        if not res.get("success"):
            raise RouterError("Failed to fetch PPTP VPN configuration")
            
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
        res = await self.client.write("admin/pptpd", "config", **payload)
        return bool(res.get("success"))

    async def get_connections(self) -> List[VpnConnection]:
        """Get all active incoming OpenVPN and PPTP connections."""
        connections = []

        # 1. Fetch OpenVPN connections
        try:
            res_ovpn = await self.client.api("admin/vpnconn", "config", "list", vpntype="openvpn")
            if res_ovpn.get("success"):
                ovpn_data = res_ovpn.get("data")
                if isinstance(ovpn_data, list):
                    for item in ovpn_data:
                        connections.append(VpnConnection(
                            username=item.get("username") or item.get("name", "unknown"),
                            ipaddr=item.get("ipaddr") or item.get("ip", "0.0.0.0"),
                            macaddr=item.get("macaddr") or item.get("mac"),
                            uptime=item.get("uptime"),
                            vpntype="openvpn"
                        ))
                elif isinstance(ovpn_data, dict):
                    for item in ovpn_data.values():
                        if isinstance(item, dict):
                            connections.append(VpnConnection(
                                username=item.get("username") or item.get("name", "unknown"),
                                ipaddr=item.get("ipaddr") or item.get("ip", "0.0.0.0"),
                                macaddr=item.get("macaddr") or item.get("mac"),
                                uptime=item.get("uptime"),
                                vpntype="openvpn"
                            ))
        except Exception:
            pass

        # 2. Fetch PPTP connections
        try:
            res_pptp = await self.client.api("admin/vpnconn", "config", "list", vpntype="pptp")
            if res_pptp.get("success"):
                pptp_data = res_pptp.get("data")
                if isinstance(pptp_data, list):
                    for item in pptp_data:
                        connections.append(VpnConnection(
                            username=item.get("username") or item.get("name", "unknown"),
                            ipaddr=item.get("ipaddr") or item.get("ip", "0.0.0.0"),
                            macaddr=item.get("macaddr") or item.get("mac"),
                            uptime=item.get("uptime"),
                            vpntype="pptp"
                        ))
                elif isinstance(pptp_data, dict):
                    for item in pptp_data.values():
                        if isinstance(item, dict):
                            connections.append(VpnConnection(
                                username=item.get("username") or item.get("name", "unknown"),
                                ipaddr=item.get("ipaddr") or item.get("ip", "0.0.0.0"),
                                macaddr=item.get("macaddr") or item.get("mac"),
                                uptime=item.get("uptime"),
                                vpntype="pptp"
                            ))
        except Exception:
            pass

        return connections
