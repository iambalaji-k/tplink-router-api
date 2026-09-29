from typing import Any, Dict, List, Optional
from tplink_modern.resources.base import BaseResource
from tplink_modern.models import (
    REDACTED_PSK,
    GuestNetworkConfig,
    WirelessBandConfig,
    WirelessCapabilities,
    WirelessClientStats,
)

GUEST_BANDS = ("2g", "5g")


def _guest_band(band: str) -> str:
    band = band.lower().strip()
    if band not in ("2g", "5g", "6g"):
        raise ValueError("Band must be one of '2g', '5g' or '6g'")
    return band


def _on_off(value: bool) -> str:
    return "on" if value else "off"


def _reject_placeholder(value: Optional[str], field: str) -> None:
    """A redacted key echoed back by a caller would overwrite the real one."""
    if value == REDACTED_PSK:
        raise ValueError(f"{field} is a redaction placeholder; read the real value first")


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

    async def get_capabilities(self) -> WirelessCapabilities:
        """Channels and widths this unit accepts per band, straight from the router.

        The region form reports what the driver supports in the current country, so a caller
        can validate a channel or htmode before writing it instead of guessing per firmware.
        """
        resp = await self.client.read("admin/wireless", "region")
        return WirelessCapabilities.from_router(resp.get("data", {}))

    async def get_guest_band(self, band: str) -> Dict[str, Any]:
        """Read one guest band's configuration straight from its own form.

        The per-band guest forms report the field names they accept, so writes echo
        these values back rather than guessing at them.
        """
        resp = await self.client.read("admin/wireless", f"guest_{_guest_band(band)}")
        return resp.get("data", {})

    async def set_guest(
        self,
        enable: Optional[bool] = None,
        isolate: Optional[bool] = None,
        ssid: Optional[str] = None,
        password: Optional[str] = None,
        bands: Optional[List[str]] = None,
    ) -> bool:
        """Configure the guest network.

        Args:
            enable: Turn the guest network on or off. Omit to leave it as-is.
            isolate: Isolate guests from the main LAN (its own form on this firmware).
            ssid: Guest network name applied to every band listed.
            password: Guest WPA key applied to every band listed.
            bands: Which guest bands to write, defaults to 2g and 5g.

        Omitted values keep whatever the router currently reports, so calling this with
        only ``enable`` cannot blank an SSID or a key.
        """
        if enable is None and isolate is None and ssid is None and password is None:
            raise ValueError("set_guest needs at least one of enable, isolate, ssid or password")

        _reject_placeholder(password, "password")
        targets = [_guest_band(b) for b in bands] if bands else list(GUEST_BANDS)

        if enable is not None or ssid is not None or password is not None:
            for band in targets:
                current = await self.get_guest_band(band)
                await self.client.write(
                    "admin/wireless",
                    f"guest_{band}",
                    enable=_on_off(enable) if enable is not None else current.get("enable", "off"),
                    ssid=ssid if ssid is not None else current.get("ssid", ""),
                    psk_key=password if password is not None else (current.get("psk_key") or ""),
                    encryption=current.get("encryption") or "psk",
                    psk_cipher=current.get("psk_cipher") or "aes",
                    psk_version=current.get("psk_version") or "",
                    hidden=current.get("hidden") or "off",
                )

        if isolate is not None:
            permissions = await self.client.read("admin/wireless", "guest")
            current = permissions.get("data", {})
            await self.client.write(
                "admin/wireless",
                "guest",
                isolate=_on_off(isolate),
                access=current.get("access", "off"),
            )

        return True

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
        _reject_placeholder(password, "password")

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
        
        await self.client.write("admin/wireless", form, **payload)
        return True

    async def get_statistics(self) -> List[WirelessClientStats]:
        """Get active wireless transmission statistics for each connected client device."""
        res = await self.client.api("admin/wireless", "statistics", "load")

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


