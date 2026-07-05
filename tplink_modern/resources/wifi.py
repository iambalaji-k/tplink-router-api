from typing import List, Optional
from tplink_modern.resources.base import BaseResource
from tplink_modern.models import WirelessBandConfig, GuestNetworkConfig, WirelessClientStats
from tplink_modern.exceptions import RouterError


class WifiResource(BaseResource):
    """Resource to check and configure wireless settings."""

    async def get_2g(self) -> WirelessBandConfig:
        """Get current 2.4GHz Wi-Fi configuration."""
        status = await self.client.get_status()
        return status.wireless_2g

    async def get_5g(self) -> WirelessBandConfig:
        """Get current 5GHz Wi-Fi configuration."""
        status = await self.client.get_status()
        return status.wireless_5g

    async def get_guest(self) -> GuestNetworkConfig:
        """Get current Guest Network configuration."""
        status = await self.client.get_status()
        return status.guest

    async def set_guest(self, enable: bool, isolate: bool = False) -> bool:
        """Turn guest networks on or off.
        
        Args:
            enable: True to enable, False to disable.
            isolate: True to isolate guests from the main LAN.
        """
        enable_str = "on" if enable else "off"
        isolate_str = "on" if isolate else "off"
        
        # In AX12, setting guest wifi usually targets guest_2g5g form on wireless endpoint
        payload = {
            "enable": enable_str,
            "isolate": isolate_str,
        }
        resp = await self.client.write("admin/wireless", "guest_2g5g", **payload)
        return resp.get("success", False)

    async def set_wireless_band(
        self,
        band: str,
        ssid: Optional[str] = None,
        password: Optional[str] = None,
        enable: Optional[bool] = None,
        channel: Optional[str] = None,
        htmode: Optional[str] = None,
    ) -> bool:
        """Update Wi-Fi band configuration (2.4GHz or 5GHz).
        
        Args:
            band: '2g' or '5g'.
            ssid: Wireless Network Name (SSID).
            password: WPA/WPA2 pre-shared key password.
            enable: True to turn on, False to turn off.
            channel: Wi-Fi channel setting (e.g. 'auto' or channel number).
            htmode: Channel width setting (e.g. '20', '40', '80', 'auto').
        """
        band_clean = band.lower().strip()
        if band_clean not in ("2g", "5g"):
            raise ValueError("Band must be either '2g' or '5g'")
            
        if band_clean == "2g":
            current = await self.get_2g()
            form = "wireless_2g"
        else:
            current = await self.get_5g()
            form = "wireless_5g"
            
        # Build payload overriding only provided parameters
        payload = {
            "ssid": ssid if ssid is not None else current.ssid,
            "psk_key": password if password is not None else (current.psk_key or ""),
            "enable": ("on" if enable else "off") if enable is not None else ("on" if current.enable else "off"),
            "encryption": current.encryption or "psk",
            "psk_cipher": current.psk_cipher or "aes",
            "channel": channel if channel is not None else (current.channel or "auto"),
            "htmode": htmode if htmode is not None else (current.htmode or "auto"),
        }
        
        resp = await self.client.write("admin/wireless", form, **payload)
        return resp.get("success", False)

    async def get_statistics(self) -> List[WirelessClientStats]:
        """Get active wireless transmission statistics for each connected client device."""
        res = await self.client.api("admin/wireless", "statistics", "load")
        if not res.get("success"):
            raise RouterError("Failed to fetch wireless statistics")
            
        stats = []
        for item in res.get("data", []):
            stats.append(WirelessClientStats(
                macaddr=item.get("mac", ""),
                band=item.get("type", "2.4GHz"),
                encryption=item.get("encryption", ""),
                rx_packets=int(item.get("rxpkts", 0)),
                tx_packets=int(item.get("txpkts", 0))
            ))
        return stats


