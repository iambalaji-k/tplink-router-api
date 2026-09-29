class RouterError(Exception):
    """Base exception for all TP-Link Router SDK errors."""


class AuthenticationError(RouterError):
    """Raised when authentication fails."""


class SessionExpiredError(AuthenticationError):
    """Raised when the router session has expired or is invalid."""


class APIError(RouterError):
    """The router refused a request or answered with something unusable.

    `errorcode` carries the router's own reason (e.g. "timeout", "no such callback")
    so callers can tell a firmware gap from a transient failure.
    """

    def __init__(self, message: str, errorcode: object = None):
        super().__init__(message)
        self.errorcode = errorcode


class FeatureUnavailableError(APIError):
    """This firmware does not implement the requested form or operation."""


class NotFoundError(RouterError):
    """A local lookup found nothing to act on."""
