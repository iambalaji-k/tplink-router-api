
from tplink_modern.models import ClientDevice
from tplink_modern.resources.base import BaseResource


class ClientsResource(BaseResource):
    """Resource to query and manage connected client devices."""

    async def get_all(self) -> list[ClientDevice]:
        """Retrieve the list of all connected devices (wired and wireless)."""
        status = await self.client.get_status()
        return status.clients
