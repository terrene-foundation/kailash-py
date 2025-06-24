"""
Authentication Models for Kailash Middleware

Provides data models for JWT authentication without any circular dependencies.
These models can be imported anywhere in the codebase safely.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import List, Optional


@dataclass
class JWTConfig:
    """Configuration for JWT authentication supporting both HS256 and RSA algorithms."""

    # Signing configuration
    algorithm: str = "HS256"  # Default to HS256 for simplicity
    secret_key: Optional[str] = None  # For HS256
    use_rsa: bool = False  # Enable RSA mode
    private_key: Optional[str] = None  # For RSA (PEM format)
    public_key: Optional[str] = None  # For RSA (PEM format)

    # Token expiration
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7

    # Security settings
    issuer: str = "kailash-middleware"
    audience: str = "kailash-api"

    # Key management
    auto_generate_keys: bool = True
    key_rotation_days: int = 30  # Only applies to RSA mode

    # Token settings
    include_user_claims: bool = True
    include_permissions: bool = True
    max_refresh_count: int = 10

    # Security features
    enable_blacklist: bool = True
    enable_token_cleanup: bool = True
    cleanup_interval_minutes: int = 60


@dataclass
class TokenPayload:
    """JWT token payload structure."""

    # Standard claims
    sub: str  # Subject (user ID)
    iss: str  # Issuer
    aud: str  # Audience
    exp: int  # Expiration time
    iat: int  # Issued at
    jti: str  # JWT ID

    # Custom claims
    tenant_id: Optional[str] = None
    session_id: Optional[str] = None
    user_type: str = "user"
    permissions: List[str] = None
    roles: List[str] = None

    # Token metadata
    token_type: str = "access"  # access, refresh
    refresh_count: int = 0

    def __post_init__(self):
        if self.permissions is None:
            self.permissions = []
        if self.roles is None:
            self.roles = []


@dataclass
class TokenPair:
    """Access and refresh token pair."""

    access_token: str
    refresh_token: str
    token_type: str = "Bearer"
    expires_in: int = 0
    expires_at: Optional[datetime] = None
    scope: Optional[str] = None


@dataclass
class RefreshTokenData:
    """Metadata for tracking refresh tokens."""

    jti: str  # Token ID
    user_id: str
    tenant_id: Optional[str] = None
    session_id: Optional[str] = None
    created_at: datetime = None
    last_used: Optional[datetime] = None
    refresh_count: int = 0
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now(UTC)


@dataclass
class UserClaims:
    """User claims for JWT tokens."""

    user_id: str
    tenant_id: Optional[str] = None
    email: Optional[str] = None
    username: Optional[str] = None
    roles: List[str] = None
    permissions: List[str] = None
    metadata: dict = None

    def __post_init__(self):
        if self.roles is None:
            self.roles = []
        if self.permissions is None:
            self.permissions = []
        if self.metadata is None:
            self.metadata = {}


@dataclass
class AuthenticationResult:
    """Result of authentication attempt."""

    success: bool
    token_pair: Optional[TokenPair] = None
    user_claims: Optional[UserClaims] = None
    error: Optional[str] = None
    error_code: Optional[str] = None
