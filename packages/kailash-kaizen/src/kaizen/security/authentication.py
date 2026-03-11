"""
Authentication providers for Kaizen Security Framework.

Supports multiple authentication methods:
- JWT (JSON Web Tokens) with HS256/RS256 and external user validation
- OAuth2 authorization code flow
- API Key authentication
- Multi-factor authentication (MFA)
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, Protocol

import jwt


class AuthenticationError(Exception):
    """Raised when authentication fails."""

    pass


class UserValidator(Protocol):
    """Protocol for user credential validation.

    Implementations must use secure password hashing (e.g., bcrypt).
    NEVER store or compare passwords in plaintext.
    """

    def validate_credentials(self, username: str, password: str) -> bool:
        """
        Validate user credentials.

        Args:
            username: Username to validate
            password: Password to validate (will be hashed internally by implementation)

        Returns:
            True if credentials are valid, False otherwise
        """
        ...


class AuthenticationProvider:
    """
    JWT-based authentication provider with external user validation.

    Provides token generation and validation using JWT (JSON Web Tokens).
    Requires external user validator for secure credential validation.
    NO hardcoded credentials allowed in production.

    Example:
        import bcrypt

        class MyUserValidator:
            def __init__(self):
                # Store hashed password (NOT plaintext!)
                self.users = {
                    "user": bcrypt.hashpw("pass".encode(), bcrypt.gensalt())
                }

            def validate_credentials(self, username: str, password: str) -> bool:
                if username not in self.users:
                    return False
                return bcrypt.checkpw(password.encode(), self.users[username])

        validator = MyUserValidator()
        auth = AuthenticationProvider(
            secret_key="your-secret-key-min-32-chars",
            user_validator=validator
        )
        token = auth.authenticate({"username": "user", "password": "pass"})
        decoded = auth.verify_token(token)
    """

    def __init__(
        self,
        secret_key: str,
        user_validator: Optional[UserValidator] = None,
        algorithm: str = "HS256",
    ):
        """
        Initialize authentication provider.

        Args:
            secret_key: Secret key for JWT signing (minimum 32 characters)
            user_validator: External user credential validator (REQUIRED - no default)
            algorithm: JWT algorithm (HS256 or RS256)

        Raises:
            ValueError: If secret_key is too short or user_validator is missing/invalid
        """
        # Validate secret key length (256 bits minimum)
        if len(secret_key) < 32:
            raise ValueError("Secret key must be at least 32 characters (256 bits)")

        # Validate user_validator is provided
        if user_validator is None:
            raise ValueError(
                "user_validator is required - hardcoded users not allowed in production"
            )

        # Validate user_validator has required method
        if not hasattr(user_validator, "validate_credentials"):
            raise ValueError("user_validator must have validate_credentials method")

        self.secret_key = secret_key
        self.algorithm = algorithm
        self.user_validator = user_validator

    def authenticate(self, credentials: Dict[str, str]) -> str:
        """
        Authenticate user and return JWT token.

        Validates credentials using external validator (NO plaintext comparison).

        Args:
            credentials: Dictionary with username and password

        Returns:
            JWT token string

        Raises:
            AuthenticationError: If credentials are invalid
        """
        username = credentials.get("username")
        password = credentials.get("password")

        if not username:
            raise AuthenticationError("Username is required")

        # Validate credentials using external validator (NO plaintext comparison!)
        if not self.user_validator.validate_credentials(username, password):
            raise AuthenticationError("Invalid credentials")

        # Create JWT payload
        payload = {
            "username": username,
            "exp": datetime.now(timezone.utc)
            + timedelta(hours=1),  # Token expires in 1 hour
            "iat": datetime.now(timezone.utc),  # Issued at timestamp
        }

        # Generate JWT token
        token = jwt.encode(payload, self.secret_key, algorithm=self.algorithm)
        return token

    def verify_token(self, token: str) -> Dict[str, Any]:
        """
        Verify JWT token and return decoded payload.

        Args:
            token: JWT token string

        Returns:
            Decoded token payload

        Raises:
            AuthenticationError: If token is invalid or expired
        """
        try:
            decoded = jwt.decode(token, self.secret_key, algorithms=[self.algorithm])
            return decoded
        except jwt.ExpiredSignatureError:
            raise AuthenticationError("Token has expired")
        except jwt.InvalidTokenError:
            raise AuthenticationError("Invalid token")
