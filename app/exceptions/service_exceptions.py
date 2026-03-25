class ServiceError(Exception):
    def __init__(self, detail: str, status_code: int) -> None:
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code


class BadRequestServiceError(ServiceError):
    pass


class UnauthorizedServiceError(ServiceError):
    pass


class ForbiddenServiceError(ServiceError):
    pass


class ConflictServiceError(ServiceError):
    pass


class UpstreamServiceError(ServiceError):
    pass

