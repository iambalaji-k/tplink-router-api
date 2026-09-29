import json
from typing import Any, Dict, List

from tplink_modern.exceptions import NotFoundError
from tplink_modern.models import AccessControlSettings, ManagedDevice
from tplink_modern.resources.base import BaseResource

PATH = "admin/access_control"


def _mac_key(macaddr: str) -> str:
    return macaddr.replace(":", "-").upper()


def _as_rows(data: Any) -> List[Dict[str, Any]]:
    """The router answers these forms as a list when populated and a dict when empty."""
    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)]
    if isinstance(data, dict):
        return [row for row in data.values() if isinstance(row, dict)]
    return []


class AccessControlResource(BaseResource):
    """Parental-control / access-control list: let the router block or allow a device."""

    async def get_settings(self) -> AccessControlSettings:
        """Current enable flag, list mode and the host MAC the router excludes."""
        enable = (await self.client.read(PATH, "enable")).get("data", {})
        mode = (await self.client.read(PATH, "mode")).get("data", {})
        return AccessControlSettings(
            enable=enable.get("enable") == "on",
            mode=mode.get("access_mode", "black"),
            host_mac=enable.get("host_mac", ""),
        )

    async def set_enabled(self, enable: bool) -> bool:
        """Turn access control on or off. The router keeps the current host MAC."""
        current = await self.client.read(PATH, "enable")
        data = current.get("data", {})
        await self.client.write(
            PATH, "enable",
            enable="on" if enable else "off",
            host_mac=data.get("host_mac", ""),
        )
        return True

    async def set_mode(self, mode: str) -> bool:
        """Switch between 'black' (block listed) and 'white' (allow listed)."""
        mode = mode.lower().strip()
        if mode not in ("black", "white"):
            raise ValueError("mode must be 'black' or 'white'")
        await self.client.write(PATH, "mode", access_mode=mode)
        return True

    async def devices(self, list_type: str = "black") -> List[ManagedDevice]:
        """Devices the router offers to put on the given list."""
        if list_type not in ("black", "white"):
            raise ValueError("list_type must be 'black' or 'white'")
        resp = await self.client.api(PATH, f"{list_type}_devices", "load")
        return [ManagedDevice.from_router(row) for row in _as_rows(resp.get("data"))]

    async def blocked(self) -> List[str]:
        """MACs currently on the block list."""
        return self._macs(await self.client.api(PATH, "black_list", "load"))

    async def allowed(self) -> List[str]:
        """MACs currently on the allow list."""
        return self._macs(await self.client.api(PATH, "white_list", "load"))

    @staticmethod
    def _macs(resp: Dict[str, Any]) -> List[str]:
        macs = []
        for row in _as_rows(resp.get("data")):
            mac = row.get("mac") or row.get("macaddr")
            if mac:
                macs.append(_mac_key(mac))
        return macs

    async def block(self, macaddr: str) -> bool:
        """Add a device to the block list. It must currently be known to the router."""
        return await self._mutate(macaddr, "black", "block")

    async def allow(self, macaddr: str) -> bool:
        """Add a device to the allow list (only effective while mode is 'white')."""
        return await self._mutate(macaddr, "white", "access")

    async def _mutate(self, macaddr: str, list_type: str, operation: str) -> bool:
        target = _mac_key(macaddr)
        rows = _as_rows((await self.client.api(PATH, f"{list_type}_devices", "load")).get("data"))
        index = next(
            (i for i, row in enumerate(rows) if _mac_key(row.get("mac", "")) == target), None
        )
        if index is None:
            raise NotFoundError(
                f"{target} is not on the router's {list_type}_devices list; "
                "access control can only list a device it has seen"
            )

        await self.client.api(
            PATH,
            f"{list_type}_devices",
            operation,
            data=json.dumps(rows[index]),
            index=index,
        )
        return True

    async def unblock(self, macaddr: str) -> bool:
        """Remove a MAC from the block list."""
        return await self._remove(macaddr, "black")

    async def unallow(self, macaddr: str) -> bool:
        """Remove a MAC from the allow list."""
        return await self._remove(macaddr, "white")

    async def _remove(self, macaddr: str, list_type: str) -> bool:
        target = _mac_key(macaddr)
        entries = _as_rows((await self.client.api(PATH, f"{list_type}_list", "load")).get("data"))
        index = next(
            (i for i, row in enumerate(entries) if _mac_key(row.get("mac", row.get("macaddr", ""))) == target),
            None,
        )
        if index is None:
            raise NotFoundError(f"{target} is not on the {list_type} list")

        await self.client.api(
            PATH,
            f"{list_type}_list",
            "remove",
            key=target,
            index=index,
        )
        return True
