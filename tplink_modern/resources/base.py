class BaseResource:
    """Base class for all TP-Link Router API resources."""
    def __init__(self, client):
        self.client = client
