class AppError(Exception):
    """An actionable domain error exposed through a consistent API envelope."""

    def __init__(self, message: str, status: int = 422, details: dict | None = None):
        self.message = message
        self.status = status
        self.details = details or {}
        super().__init__(message)
