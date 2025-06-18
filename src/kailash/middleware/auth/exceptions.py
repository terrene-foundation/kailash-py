"""
Authentication Exceptions for Kailash Middleware

Provides exception classes for authentication errors without circular dependencies.
"""


class AuthenticationError(Exception):
    """Base exception for authentication errors."""

    def __init__(self, message: str, error_code: str = None):
        super().__init__(message)
        self.error_code = error_code


class TokenExpiredError(AuthenticationError):
    """Raised when a JWT token has expired."""

    def __init__(self, message: str = "Token has expired"):
        super().__init__(message, "TOKEN_EXPIRED")


class InvalidTokenError(AuthenticationError):
    """Raised when a JWT token is invalid."""

    def __init__(self, message: str = "Invalid token"):
        super().__init__(message, "INVALID_TOKEN")


class TokenBlacklistedError(AuthenticationError):
    """Raised when a JWT token has been blacklisted/revoked."""

    def __init__(self, message: str = "Token has been revoked"):
        super().__init__(message, "TOKEN_BLACKLISTED")


class KeyRotationError(AuthenticationError):
    """Raised when key rotation fails."""

    def __init__(self, message: str = "Key rotation failed"):
        super().__init__(message, "KEY_ROTATION_ERROR")


class RefreshTokenError(AuthenticationError):
    """Raised when refresh token operations fail."""

    def __init__(self, message: str = "Refresh token error"):
        super().__init__(message, "REFRESH_TOKEN_ERROR")


class PermissionDeniedError(AuthenticationError):
    """Raised when user lacks required permissions."""

    def __init__(
        self, message: str = "Permission denied", required_permission: str = None
    ):
        super().__init__(message, "PERMISSION_DENIED")
        self.required_permission = required_permission


class RateLimitError(AuthenticationError):
    """Raised when authentication rate limit is exceeded."""

    def __init__(self, message: str = "Rate limit exceeded", retry_after: int = None):
        super().__init__(message, "RATE_LIMIT_EXCEEDED")
        self.retry_after = retry_after


class InvalidCredentialsError(AuthenticationError):
    """Raised when login credentials are invalid."""

    def __init__(self, message: str = "Invalid credentials"):
        super().__init__(message, "INVALID_CREDENTIALS")


class SessionExpiredError(AuthenticationError):
    """Raised when a session has expired."""

    def __init__(self, message: str = "Session has expired"):
        super().__init__(message, "SESSION_EXPIRED")
