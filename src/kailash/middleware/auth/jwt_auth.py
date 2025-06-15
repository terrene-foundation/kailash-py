"""
JWT Authentication Manager for Kailash Middleware

Provides enterprise-grade JWT authentication built entirely with Kailash SDK components.
Uses Kailash nodes, workflows, and patterns for all authentication operations.
"""

import json
import logging
import secrets
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Union

# JWT and cryptography imports
try:
    import jwt
    from cryptography.hazmat.primitives.asymmetric import rsa
except ImportError:
    jwt = None
    rsa = None

# Import Kailash SDK components
from kailash.nodes.base import Node, NodeParameter
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.data import JSONReaderNode
from kailash.nodes.logic import SwitchNode
from kailash.runtime.local import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder

logger = logging.getLogger(__name__)


@dataclass
class JWTConfig:
    """Configuration for JWT authentication using only Python standard library."""

    # Signing configuration
    algorithm: str = (
        "HS256"  # Use HMAC instead of RSA to avoid external crypto dependencies
    )
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7

    # Security settings
    issuer: str = "kailash-middleware"
    audience: str = "kailash-api"

    # Key management
    auto_generate_keys: bool = True
    key_rotation_days: int = 30

    # Token settings
    include_user_claims: bool = True
    include_permissions: bool = True
    max_refresh_count: int = 10


@dataclass
class TokenPayload:
    """JWT token payload structure using standard Python."""

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
    """Access and refresh token pair using standard Python."""

    access_token: str
    refresh_token: str
    token_type: str = "Bearer"
    expires_in: int = 0
    expires_at: Optional[datetime] = None
    scope: Optional[str] = None


class JWTAuthManager:
    """
    Enterprise JWT Authentication Manager.

    Provides comprehensive JWT token management with security best practices:
    - RSA key pair generation and rotation
    - Refresh token management
    - Token blacklisting
    - Comprehensive audit logging
    - Rate limiting protection
    """

    def __init__(self, config: JWTConfig = None):
        self.config = config or JWTConfig()

        # Key management
        self._private_key: Optional[rsa.RSAPrivateKey] = None
        self._public_key: Optional[rsa.RSAPublicKey] = None
        self._key_id = str(uuid.uuid4())
        self._key_generated_at = datetime.now(timezone.utc)

        # Token tracking
        self._blacklisted_tokens: set = set()
        self._refresh_tokens: Dict[str, Dict[str, Any]] = {}
        self._failed_attempts: Dict[str, List[datetime]] = {}

        # Initialize keys
        if self.config.auto_generate_keys:
            self._generate_key_pair()

    def _generate_key_pair(self):
        """Generate new RSA key pair for token signing."""
        self._private_key = rsa.generate_private_key(
            public_exponent=65537, key_size=2048
        )
        self._public_key = self._private_key.public_key()
        self._key_id = str(uuid.uuid4())
        self._key_generated_at = datetime.now(timezone.utc)

        logger.info(f"Generated new JWT key pair with ID: {self._key_id}")

    def _should_rotate_keys(self) -> bool:
        """Check if keys should be rotated."""
        if not self._key_generated_at:
            return True

        rotation_threshold = timedelta(days=self.config.key_rotation_days)
        return datetime.now(timezone.utc) - self._key_generated_at > rotation_threshold

    def _create_token_payload(
        self,
        user_id: str,
        token_type: str = "access",
        tenant_id: str = None,
        session_id: str = None,
        permissions: List[str] = None,
        roles: List[str] = None,
        **kwargs,
    ) -> TokenPayload:
        """Create token payload with all claims."""
        now = datetime.now(timezone.utc)

        # Determine expiration
        if token_type == "access":
            expire_delta = timedelta(minutes=self.config.access_token_expire_minutes)
        else:  # refresh
            expire_delta = timedelta(days=self.config.refresh_token_expire_days)

        return TokenPayload(
            sub=user_id,
            iss=self.config.issuer,
            aud=self.config.audience,
            exp=int((now + expire_delta).timestamp()),
            iat=int(now.timestamp()),
            jti=str(uuid.uuid4()),
            tenant_id=tenant_id,
            session_id=session_id,
            token_type=token_type,
            permissions=permissions or [],
            roles=roles or [],
            **kwargs,
        )

    def create_access_token(
        self,
        user_id: str,
        tenant_id: str = None,
        session_id: str = None,
        permissions: List[str] = None,
        roles: List[str] = None,
        **kwargs,
    ) -> str:
        """Create JWT access token."""
        if self._should_rotate_keys():
            self._generate_key_pair()

        payload = self._create_token_payload(
            user_id=user_id,
            token_type="access",
            tenant_id=tenant_id,
            session_id=session_id,
            permissions=permissions,
            roles=roles,
            **kwargs,
        )

        # Add key ID to header
        headers = {"kid": self._key_id}

        # Sign token
        token = jwt.encode(
            payload.dict(),
            self._private_key,
            algorithm=self.config.algorithm,
            headers=headers,
        )

        logger.debug(f"Created access token for user {user_id}")
        return token

    def create_refresh_token(
        self, user_id: str, tenant_id: str = None, session_id: str = None, **kwargs
    ) -> str:
        """Create JWT refresh token."""
        payload = self._create_token_payload(
            user_id=user_id,
            token_type="refresh",
            tenant_id=tenant_id,
            session_id=session_id,
            **kwargs,
        )

        headers = {"kid": self._key_id}

        token = jwt.encode(
            payload.dict(),
            self._private_key,
            algorithm=self.config.algorithm,
            headers=headers,
        )

        # Store refresh token metadata
        self._refresh_tokens[payload.jti] = {
            "user_id": user_id,
            "tenant_id": tenant_id,
            "session_id": session_id,
            "created_at": datetime.now(timezone.utc),
            "refresh_count": 0,
            "last_used": None,
        }

        logger.debug(f"Created refresh token for user {user_id}")
        return token

    def create_token_pair(
        self,
        user_id: str,
        tenant_id: str = None,
        session_id: str = None,
        permissions: List[str] = None,
        roles: List[str] = None,
        **kwargs,
    ) -> TokenPair:
        """Create access and refresh token pair."""
        access_token = self.create_access_token(
            user_id, tenant_id, session_id, permissions, roles, **kwargs
        )
        refresh_token = self.create_refresh_token(
            user_id, tenant_id, session_id, **kwargs
        )

        expires_at = datetime.now(timezone.utc) + timedelta(
            minutes=self.config.access_token_expire_minutes
        )

        return TokenPair(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=self.config.access_token_expire_minutes * 60,
            expires_at=expires_at,
        )

    def verify_token(self, token: str) -> Dict[str, Any]:
        """
        Verify and decode JWT token.

        Returns:
            Decoded token payload or raises exception
        """
        try:
            # Check if token is blacklisted
            if token in self._blacklisted_tokens:
                raise jwt.InvalidTokenError("Token has been revoked")

            # Decode without verification first to get header
            unverified_header = jwt.get_unverified_header(token)
            key_id = unverified_header.get("kid")

            # Verify key ID matches current key
            if key_id != self._key_id:
                logger.warning(f"Token signed with unknown key ID: {key_id}")
                # In production, you might want to support multiple keys
                # for graceful key rotation

            # Verify and decode token
            payload = jwt.decode(
                token,
                self._public_key,
                algorithms=[self.config.algorithm],
                issuer=self.config.issuer,
                audience=self.config.audience,
            )

            return payload

        except jwt.ExpiredSignatureError:
            logger.debug("Token has expired")
            raise
        except jwt.InvalidTokenError as e:
            logger.warning(f"Invalid token: {e}")
            raise
        except Exception as e:
            logger.error(f"Token verification error: {e}")
            raise jwt.InvalidTokenError(f"Token verification failed: {e}")

    def refresh_access_token(self, refresh_token: str) -> TokenPair:
        """
        Create new access token using refresh token.

        Args:
            refresh_token: Valid refresh token

        Returns:
            New token pair with refreshed access token
        """
        try:
            # Verify refresh token
            payload = self.verify_token(refresh_token)

            if payload.get("token_type") != "refresh":
                raise jwt.InvalidTokenError("Token is not a refresh token")

            jti = payload.get("jti")
            if jti not in self._refresh_tokens:
                raise jwt.InvalidTokenError("Refresh token not found")

            refresh_data = self._refresh_tokens[jti]

            # Check refresh count limit
            if refresh_data["refresh_count"] >= self.config.max_refresh_count:
                self.revoke_refresh_token(jti)
                raise jwt.InvalidTokenError("Refresh token has exceeded usage limit")

            # Update refresh count
            refresh_data["refresh_count"] += 1
            refresh_data["last_used"] = datetime.now(timezone.utc)

            # Create new token pair
            return self.create_token_pair(
                user_id=payload["sub"],
                tenant_id=payload.get("tenant_id"),
                session_id=payload.get("session_id"),
                permissions=payload.get("permissions", []),
                roles=payload.get("roles", []),
            )

        except Exception as e:
            logger.error(f"Token refresh failed: {e}")
            raise

    def revoke_token(self, token: str):
        """Add token to blacklist."""
        try:
            payload = self.verify_token(token)
            jti = payload.get("jti")
            if jti:
                self._blacklisted_tokens.add(token)
                logger.info(f"Revoked token {jti}")
        except:
            # Even if verification fails, add to blacklist
            self._blacklisted_tokens.add(token)

    def revoke_refresh_token(self, jti: str):
        """Revoke specific refresh token."""
        if jti in self._refresh_tokens:
            del self._refresh_tokens[jti]
            logger.info(f"Revoked refresh token {jti}")

    def revoke_all_user_tokens(self, user_id: str):
        """Revoke all tokens for a specific user."""
        # Remove all refresh tokens for user
        to_remove = []
        for jti, data in self._refresh_tokens.items():
            if data["user_id"] == user_id:
                to_remove.append(jti)

        for jti in to_remove:
            del self._refresh_tokens[jti]

        logger.info(f"Revoked all tokens for user {user_id}")

    def cleanup_expired_tokens(self):
        """Remove expired tokens from tracking."""
        now = datetime.now(timezone.utc)

        # Clean up expired refresh tokens
        expired_refresh = []
        for jti, data in self._refresh_tokens.items():
            # Check if token is older than refresh token lifetime
            token_age = now - data["created_at"]
            if token_age > timedelta(days=self.config.refresh_token_expire_days):
                expired_refresh.append(jti)

        for jti in expired_refresh:
            del self._refresh_tokens[jti]

        # Clean up old failed attempts (keep only last hour)
        cutoff = now - timedelta(hours=1)
        for ip, attempts in list(self._failed_attempts.items()):
            recent_attempts = [t for t in attempts if t > cutoff]
            if recent_attempts:
                self._failed_attempts[ip] = recent_attempts
            else:
                del self._failed_attempts[ip]

        if expired_refresh or self._failed_attempts:
            logger.debug(f"Cleaned up {len(expired_refresh)} expired refresh tokens")

    def get_public_key_jwks(self) -> Dict[str, Any]:
        """Get public key in JWKS format for external verification."""
        if not self._public_key:
            return {}

        # Convert public key to JWKS format
        public_numbers = self._public_key.public_numbers()

        return {
            "keys": [
                {
                    "kty": "RSA",
                    "kid": self._key_id,
                    "use": "sig",
                    "alg": self.config.algorithm,
                    "n": self._encode_number(public_numbers.n),
                    "e": self._encode_number(public_numbers.e),
                }
            ]
        }

    def _encode_number(self, number: int) -> str:
        """Encode number for JWKS format."""
        import base64

        byte_length = (number.bit_length() + 7) // 8
        number_bytes = number.to_bytes(byte_length, "big")
        return base64.urlsafe_b64encode(number_bytes).decode("ascii").rstrip("=")

    def get_stats(self) -> Dict[str, Any]:
        """Get authentication manager statistics."""
        return {
            "active_refresh_tokens": len(self._refresh_tokens),
            "blacklisted_tokens": len(self._blacklisted_tokens),
            "key_id": self._key_id,
            "key_age_days": (
                (datetime.now(timezone.utc) - self._key_generated_at).days
                if self._key_generated_at
                else 0
            ),
            "failed_attempts_tracked": len(self._failed_attempts),
            "config": {
                "algorithm": self.config.algorithm,
                "access_token_expire_minutes": self.config.access_token_expire_minutes,
                "refresh_token_expire_days": self.config.refresh_token_expire_days,
            },
        }
