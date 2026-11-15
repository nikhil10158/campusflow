class ServiceError(Exception):
    status_code = 400

    def __init__(self, message: str, data: dict | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.data = data or {}


class BadRequest(ServiceError):
    status_code = 422


class Forbidden(ServiceError):
    status_code = 403


class NotFound(ServiceError):
    status_code = 404


class Conflict(ServiceError):
    status_code = 409
