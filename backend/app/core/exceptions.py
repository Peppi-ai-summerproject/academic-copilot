class AppException(Exception):
    """Base exception for expected application errors."""

    def __init__(
        self,
        message: str,
        status_code: int = 400,
        error_code: str = "APPLICATION_ERROR",
    ) -> None:
        self.message = message
        self.status_code = status_code
        self.error_code = error_code
        super().__init__(message)


class ResourceNotFoundException(AppException):
    def __init__(self, resource: str, resource_id: str | int) -> None:
        super().__init__(
            message=f"{resource} with id '{resource_id}' was not found.",
            status_code=404,
            error_code="RESOURCE_NOT_FOUND",
        )