
from tplink_modern.exceptions import NotFoundError
from tplink_modern.models import DmzSettings, ForwardRule
from tplink_modern.resources.base import BaseResource

PATH = "admin/nat"


def _rows(data) -> list[dict]:
    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)]
    if isinstance(data, dict):
        return [row for row in data.values() if isinstance(row, dict)]
    return []


class NatResource(BaseResource):
    """Port forwarding: virtual servers, port triggering and the DMZ host."""

    async def get_dmz(self) -> DmzSettings:
        """Current DMZ host."""
        data = (await self.client.read(PATH, "dmz")).get("data", {})
        return DmzSettings(enable=data.get("enable") == "on", ipaddr=data.get("ipaddr", ""))

    async def set_dmz(self, enable: bool, ipaddr: str = "") -> bool:
        """Point the DMZ at a single internal host, or take it off."""
        await self.client.write(PATH, "dmz", enable="on" if enable else "off", ipaddr=ipaddr)
        return True

    async def virtual_servers(self) -> list[ForwardRule]:
        """Port forwarding rules."""
        return await self._rules("vs")

    async def port_triggers(self) -> list[ForwardRule]:
        """Port triggering rules."""
        return await self._rules("pt")

    async def _rules(self, form: str) -> list[ForwardRule]:
        resp = await self.client.api(PATH, form, "load")
        return [ForwardRule.from_router(row, i) for i, row in enumerate(_rows(resp.get("data")))]

    async def delete_virtual_server(self, key: str) -> bool:
        """Remove a port forwarding rule by its router-assigned key."""
        return await self._delete("vs", key)

    async def delete_port_trigger(self, key: str) -> bool:
        """Remove a port triggering rule by its router-assigned key."""
        return await self._delete("pt", key)

    async def _delete(self, form: str, key: str) -> bool:
        rules = await self._rules(form)
        match = next((rule for rule in rules if rule.key == key), None)
        if match is None:
            raise NotFoundError(f"no {form} rule with key {key!r}")
        await self.client.api(PATH, form, "remove", key=match.key, index=match.raw_index)
        return True
