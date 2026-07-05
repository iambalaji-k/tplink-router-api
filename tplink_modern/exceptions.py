class RouterError(Exception):
    """Base exception for all TP-Link Router SDK errors."""
    pass


class AuthenticationError(RouterError):
    """Raised when authentication fails."""
    pass


class SessionExpiredError(AuthenticationError):
    """Raised when the router session has expired or is invalid."""
    pass


class APIError(RouterError):
    """Raised when the router API returns an error or invalid response."""
    pass
