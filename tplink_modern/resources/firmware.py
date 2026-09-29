
from tplink_modern.models import FirmwareUpgradeCheck
from tplink_modern.resources.base import BaseResource


class FirmwareResource(BaseResource):
    """Resource to check and manage firmware upgrades."""

    async def check_upgrade(self) -> FirmwareUpgradeCheck:
        """Ask the router whether it thinks an upgrade is pending.

        The firmware only reports a count, not a version, so `raw` keeps whatever else it
        chose to send.
        """
        resp = await self.client.read("admin/cloud_account", "check_upgrade")
        return FirmwareUpgradeCheck.from_router(resp.get("data", {}))
