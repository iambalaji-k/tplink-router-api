from tplink_modern.resources.base import BaseResource
from tplink_modern.models import RouterStatus


class StatusResource(BaseResource):
    """Resource to fetch complete status details from the router."""
    
    async def get(self) -> RouterStatus:
        """Fetch the current status of the router."""
        return await self.client.get_status()
