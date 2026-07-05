from typing import Any, Dict
from tplink_modern.resources.base import BaseResource


class FirmwareResource(BaseResource):
    """Resource to check and manage firmware upgrades."""

    async def check_upgrade(self) -> Dict[str, Any]:
        """Check if there is a newer firmware version available."""
        return await self.client.read("admin/cloud_account", "check_upgrade")
