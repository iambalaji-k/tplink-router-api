from tplink_modern.resources.base import BaseResource


class SystemResource(BaseResource):
    """Resource for administrative system operations."""

    async def reboot(self) -> bool:
        """Trigger a router reboot."""
        await self.client.write("admin/system", "reboot")
        return True
