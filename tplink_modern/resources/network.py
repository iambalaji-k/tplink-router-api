from typing import List
import json
from tplink_modern.resources.base import BaseResource
from tplink_modern.models import LanSettings, WanSettings, DhcpReservation
from tplink_modern.exceptions import NotFoundError


class NetworkResource(BaseResource):
    """Resource to inspect router local and wide area network details."""

    async def get_lan(self) -> LanSettings:
        """Get current LAN details."""
        status = await self.client.get_status()
        return status.lan

    async def get_wan(self) -> WanSettings:
        """Get current WAN details."""
        status = await self.client.get_status()
        return status.wan

    async def get_dhcp_reservations(self) -> List[DhcpReservation]:
        """Get all DHCP static address reservations."""
        res = await self.client.api("admin/dhcps", "reservation", "load")

        reservations = []
        for item in res.get("data", []):
            reservations.append(DhcpReservation(
                macaddr=item.get("mac", ""),
                ipaddr=item.get("ip", ""),
                enable=item.get("enable") == "on",
                name=item.get("comment") or item.get("hostname")
            ))
        return reservations

    async def add_dhcp_reservation(self, macaddr: str, ipaddr: str, name: str = "", enable: bool = True) -> bool:
        """Add a DHCP static address reservation."""
        # Normalize MAC address format (usually uppercase with hyphens in TP-Link)
        mac_norm = macaddr.replace(":", "-").upper()
        
        new_entry = {
            "mac": mac_norm,
            "ip": ipaddr,
            "enable": "on" if enable else "off",
            "comment": name
        }
        
        await self.client.api(
            "admin/dhcps", "reservation", "insert",
            new=json.dumps(new_entry),
            index=0
        )
        return True

    async def delete_dhcp_reservation(self, macaddr: str) -> bool:
        """Delete a DHCP static address reservation by MAC address."""
        mac_norm = macaddr.replace(":", "-").upper()
        
        # We must load the list to find the correct index of the reservation rule
        reservations = await self.get_dhcp_reservations()
        
        target_idx = None
        for idx, res in enumerate(reservations):
            if res.macaddr.upper() == mac_norm:
                target_idx = idx
                break
                
        if target_idx is None:
            raise NotFoundError(f"Reservation with MAC address {macaddr} not found")

        await self.client.api(
            "admin/dhcps", "reservation", "remove",
            key=mac_norm,
            index=target_idx
        )
        return True

