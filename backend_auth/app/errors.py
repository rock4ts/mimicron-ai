class AuthError(Exception):
    """Base application error."""


class WrongCredentialsError(AuthError):
    def __init__(self, detail: str = "Incorrect email or password") -> None:
        super().__init__(detail)


class RefreshTokenError(AuthError):
    def __init__(self, detail: str = "Invalid refresh token") -> None:
        super().__init__(detail)


class RefreshTokenMissingError(AuthError):
    def __init__(self, detail: str = "Refresh token is required") -> None:
        super().__init__(detail)


class InvalidTokenError(AuthError):
    def __init__(self, detail: str = "Invalid token") -> None:
        super().__init__(detail)


class UserNotFoundError(AuthError):
    def __init__(self, detail: str = "User not found") -> None:
        super().__init__(detail)


class UserAlreadyExistsError(AuthError):
    def __init__(self, detail: str = "User already exists") -> None:
        super().__init__(detail)


class EmailAlreadyExistsError(AuthError):
    def __init__(self, detail: str = "Email already exists") -> None:
        super().__init__(detail)


class WrongPasswordError(AuthError):
    def __init__(self, detail: str = "Wrong password") -> None:
        super().__init__(detail)


class RateLimitExceededError(AuthError):
    def __init__(self, retry_after_seconds: int, detail: str = "Too many requests") -> None:
        super().__init__(detail)
        self.retry_after_seconds = retry_after_seconds


class RateLimitStorageError(AuthError):
    def __init__(self, detail: str = "Rate limiter is temporarily unavailable") -> None:
        super().__init__(detail)


class YandexIdStateError(AuthError):
    def __init__(self, detail: str = "OAuth state is invalid or expired") -> None:
        super().__init__(detail)


class YandexIdTokenError(AuthError):
    def __init__(self, detail: str = "Error during token exchange with provider") -> None:
        super().__init__(detail)


class YandexIdProviderError(AuthError):
    def __init__(self, detail: str = "OAuth provider is temporarily unavailable") -> None:
        super().__init__(detail)


class YandexIdUserInfoError(AuthError):
    def __init__(self, detail: str = "Error during user profile fetch from provider") -> None:
        super().__init__(detail)


class YandexIdAccountConflictError(AuthError):
    def __init__(self, detail: str = "Yandex account link conflict") -> None:
        super().__init__(detail)
