# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""
A2A Authentication Module.

JWT-based authentication for A2A protocol using Ed25519 signatures
with trust chain verification.
"""

import base64
import json
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, Tuple

from kailash.trust.a2a.exceptions import (
    AuthenticationError,
    InvalidTokenError,
    TokenExpiredError,
    TrustVerificationError,
)
from kailash.trust.a2a.models import A2AToken
from kailash.trust.signing.crypto import sign, verify_signature
from kailash.trust.operations import TrustOperations

logger = logging.getLogger(__name__)


class A2AAuthenticator:
    """
    JWT-based authenticator for A2A protocol.

    Creates and validates JWT tokens signed with Ed25519 keys,
    with trust chain verification to ensure the signing agent
    is trusted.

    Token Format:
    - Header: {"alg": "EdDSA", "typ": "JWT"}
    - Payload: Standard JWT claims + EATP claims
    - Signature: Ed25519 signature over header.payload

    Example:
        >>> auth = A2AAuthenticator(trust_ops, "agent-001", private_key)
        >>> token = await auth.create_token(
        ...     audience="agent-002",
        ...     capabilities=["invoke"],
        ...     ttl_seconds=3600,
        ... )
        >>> claims = await auth.verify_token(token)
    """

    # Default token TTL: 1 hour
    DEFAULT_TTL_SECONDS = 3600

    def __init__(
        self,
        trust_operations: TrustOperations,
        agent_id: str,
        private_key: str,
    ):
        """
        Initialize the authenticator.

        Args:
            trust_operations: TrustOperations for trust verification.
            agent_id: This agent's identifier.
            private_key: Base64-encoded Ed25519 private key for signing.
        """
        self._trust_ops = trust_operations
        self._agent_id = agent_id
        self._private_key = private_key

    async def create_token(
        self,
        audience: str,
        capabilities: Optional[list[str]] = None,
        constraints: Optional[Dict[str, Any]] = None,
        ttl_seconds: int = DEFAULT_TTL_SECONDS,
    ) -> str:
        """
        Create a JWT token for A2A authentication.

        Args:
            audience: Target agent ID (aud claim).
            capabilities: Capabilities to include in token.
            constraints: Constraints to include in token.
            ttl_seconds: Token time-to-live in seconds.

        Returns:
            Base64url-encoded JWT token string.

        Raises:
            AuthenticationError: If token creation fails.
        """
        try:
            # Get trust chain for this agent
            chain = await self._trust_ops.get_chain(self._agent_id)
            if not chain:
                raise AuthenticationError(
                    f"No trust chain found for agent: {self._agent_id}"
                )

            now = datetime.now(timezone.utc)
            token_data = A2AToken(
                sub=self._agent_id,
                iss=self._agent_id,
                aud=audience,
                exp=now + timedelta(seconds=ttl_seconds),
                iat=now,
                jti=str(uuid.uuid4()),
                authority_id=chain.genesis.authority_id,
                trust_chain_hash=chain.hash(),  # TrustLineageChain uses hash() not compute_hash()
                capabilities=capabilities or [],
                constraints=constraints,
            )

            return self._encode_token(token_data)

        except AuthenticationError:
            raise
        except Exception as e:
            logger.exception(f"Failed to create token: {e}")
            raise AuthenticationError(f"Token creation failed: {e}")

    async def verify_token(
        self,
        token: str,
        expected_audience: Optional[str] = None,
        verify_trust: bool = True,
    ) -> A2AToken:
        """
        Verify a JWT token and return claims.

        Args:
            token: JWT token string.
            expected_audience: Expected audience (if provided, validates aud).
            verify_trust: Whether to verify the issuer's trust chain.

        Returns:
            Parsed A2AToken with claims.

        Raises:
            InvalidTokenError: If token is malformed.
            TokenExpiredError: If token has expired.
            TrustVerificationError: If issuer's trust chain is invalid.
        """
        try:
            # Decode and parse token
            header, payload, signature = self._decode_token(token)

            # Parse claims
            claims = A2AToken.from_claims(payload)

            # Check expiration
            if datetime.now(timezone.utc) > claims.exp:
                raise TokenExpiredError()

            # Check audience if provided
            if expected_audience and claims.aud != expected_audience:
                raise InvalidTokenError(
                    f"Token audience mismatch: expected {expected_audience}, got {claims.aud}"
                )

            # Verify signature
            if not await self._verify_signature(
                token, claims.iss, claims.trust_chain_hash
            ):
                raise InvalidTokenError("Invalid token signature")

            # Verify trust chain if requested
            if verify_trust:
                result = await self._trust_ops.verify(claims.iss, "token_verification")
                if not result.valid:
                    raise TrustVerificationError(
                        claims.iss,
                        f"Trust verification failed: {result.errors}",
                    )

                # Verify trust chain hash matches
                chain = await self._trust_ops.get_chain(claims.iss)
                if chain and chain.hash() != claims.trust_chain_hash:
                    raise TrustVerificationError(
                        claims.iss,
                        "Trust chain hash mismatch - chain may have changed",
                    )

            return claims

        except (TokenExpiredError, InvalidTokenError, TrustVerificationError):
            raise
        except Exception as e:
            logger.exception(f"Token verification failed: {e}")
            raise InvalidTokenError(f"Token verification failed: {e}")

    def _encode_token(self, token: A2AToken) -> str:
        """Encode token to JWT string."""
        # Header
        header = {"alg": "EdDSA", "typ": "JWT"}
        header_b64 = self._base64url_encode(json.dumps(header).encode())

        # Payload
        payload = token.to_claims()
        payload_b64 = self._base64url_encode(json.dumps(payload).encode())

        # Sign header.payload
        message = f"{header_b64}.{payload_b64}".encode()
        signature = sign(message, self._private_key)

        # Return complete JWT
        return f"{header_b64}.{payload_b64}.{signature}"

    def _decode_token(self, token: str) -> Tuple[Dict, Dict, str]:
        """Decode JWT token into components."""
        parts = token.split(".")
        if len(parts) != 3:
            raise InvalidTokenError("Invalid token format: expected 3 parts")

        try:
            header = json.loads(self._base64url_decode(parts[0]))
            payload = json.loads(self._base64url_decode(parts[1]))
            signature = parts[2]

            # Validate header
            if header.get("alg") != "EdDSA":
                raise InvalidTokenError(f"Unsupported algorithm: {header.get('alg')}")

            return header, payload, signature

        except json.JSONDecodeError as e:
            raise InvalidTokenError(f"Invalid token encoding: {e}")

    async def _verify_signature(
        self,
        token: str,
        issuer_id: str,
        trust_chain_hash: str,
    ) -> bool:
        """Verify token signature against issuer's public key."""
        try:
            # Get issuer's public key from registry or trust chain
            chain = await self._trust_ops.get_chain(issuer_id)
            if not chain:
                logger.warning(f"No trust chain for issuer: {issuer_id}")
                return False

            # Get public key from genesis or key manager
            public_key = await self._trust_ops.get_public_key(issuer_id)
            if not public_key:
                logger.warning(f"No public key for issuer: {issuer_id}")
                return False

            # Extract message and signature from token
            parts = token.rsplit(".", 1)
            message = parts[0].encode()
            signature = parts[1]

            return verify_signature(message, signature, public_key)

        except Exception as e:
            logger.exception(f"Signature verification failed: {e}")
            return False

    @staticmethod
    def _base64url_encode(data: bytes) -> str:
        """Base64url encode without padding."""
        return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")

    @staticmethod
    def _base64url_decode(data: str) -> bytes:
        """Base64url decode with padding restoration."""
        # Add padding if needed
        padding = 4 - len(data) % 4
        if padding != 4:
            data += "=" * padding
        return base64.urlsafe_b64decode(data)


def extract_token_from_header(authorization: Optional[str]) -> Optional[str]:
    """
    Extract JWT token from Authorization header.

    Args:
        authorization: Authorization header value.

    Returns:
        Token string or None if not found.
    """
    if not authorization:
        return None

    parts = authorization.split()
    if len(parts) != 2:
        return None

    scheme, token = parts
    if scheme.lower() != "bearer":
        return None

    return token
