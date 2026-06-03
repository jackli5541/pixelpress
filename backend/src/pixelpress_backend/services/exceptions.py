class PixelPressError(Exception):
    """Base application exception."""


class ConflictError(PixelPressError):
    """Raised on idempotency or optimistic lock conflicts."""


class NotFoundError(PixelPressError):
    """Raised when a requested resource does not exist."""


class InvalidStateError(PixelPressError):
    """Raised when a state transition is not allowed."""
