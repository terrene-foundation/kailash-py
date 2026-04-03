# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""
OAuth2TokenManager — client credentials flow with auto-refresh.

Manages the full OAuth2 client-credentials token lifecycle:

1. Acquires tokens by POSTing to the token URL with client credentials.
2. Caches the token in-memory only (NEVER Redis, NEVER disk — doc
   01-redteam H5).
3. Re-reads credentials from environment variables at each refresh
   (supports secret rotation without restart — doc 04, Resolution 8).
4. Validates the token URL with ``validate_url_safe()`` for SSRF
   protection (doc 01-redteam H4).
5. Auto-refreshes when the token is within 60 seconds of expiry.

Usage::

    from dataflow.fabric.auth import OAuth2TokenManager
    from dataflow.fabric.config import OAuth2Auth

    config = OAuth2Auth(
        client_id_env="CRM_CLIENT_ID",
        client_secret_env="CRM_CLIENT_SECRET",
        token_url="https://auth.example.com/oauth/token",
        scopes=("read", "write"),
    )
    manager = OAuth2TokenManager(config)
    token = await manager.get_access_token()
    # Use token in Authorization header

Design reference: TODO-36 in M5-M6 milestones.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

from dataflow.fabric.config import OAuth2Auth
from dataflow.fabric.ssrf import validate_url_safe

logger = logging.getLogger(__name__)

__all__ = [
    "OAuth2TokenManager",
]

# Refresh buffer: request a new token this many seconds before expiry
_REFRESH_BUFFER_SECONDS = 60


class OAuth2TokenManager:
    """OAuth2 client credentials flow with auto-refresh.

    Tokens are stored in-memory only. Credentials are re-read from
    environment variables at each refresh to support runtime secret
    rotation.

    Args:
        config: The ``OAuth2Auth`` configuration specifying env var names
            for client credentials, the token URL, and optional scopes.
    """

    def __init__(self, config: OAuth2Auth) -> None:
        self._config = config
        self._token: Optional[str] = None
        self._expires_at: Optional[datetime] = None

        # Validate token URL at construction time (fail-fast)
        validate_url_safe(config.token_url)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def get_access_token(self) -> str:
        """Return a valid access token, refreshing if needed.

        If the current token exists and will not expire within the next
        60 seconds, it is returned immediately. Otherwise, a new token
        is acquired from the token endpoint.

        Returns:
            The OAuth2 access token string.

        Raises:
            ValueError: If required environment variables are missing.
            RuntimeError: If the token endpoint returns an error.
            httpx.HTTPStatusError: On non-2xx responses from the token URL.
        """
        if self._token is not None and self._expires_at is not None:
            now = datetime.now(timezone.utc)
            buffer = timedelta(seconds=_REFRESH_BUFFER_SECONDS)
            if now + buffer < self._expires_at:
                return self._token

        return await self._refresh()

    @property
    def is_token_valid(self) -> bool:
        """Whether the current token exists and is not expiring soon."""
        if self._token is None or self._expires_at is None:
            return False
        now = datetime.now(timezone.utc)
        buffer = timedelta(seconds=_REFRESH_BUFFER_SECONDS)
        return now + buffer < self._expires_at

    def invalidate(self) -> None:
        """Force-expire the current token.

        The next call to ``get_access_token()`` will acquire a fresh
        token. Useful when a 401 is received from a downstream API.
        """
        self._token = None
        self._expires_at = None
        logger.debug("OAuth2TokenManager: token invalidated")

    # ------------------------------------------------------------------
    # Token refresh
    # ------------------------------------------------------------------

    async def _refresh(self) -> str:
        """Acquire a new access token from the token endpoint.

        Credentials are read from environment variables at call time
        (not cached from construction). This supports runtime secret
        rotation without restarting the process.

        Returns:
            The new access token string.

        Raises:
            ValueError: If credentials env vars are not set.
            RuntimeError: If the response does not contain an access_token.
            httpx.HTTPStatusError: On non-2xx responses.
        """
        try:
            import httpx
        except ImportError as exc:
            raise ImportError(
                "httpx is required for OAuth2 token management. "
                "Install with: pip install httpx"
            ) from exc

        # Re-read credentials from env at refresh time (doc 04, Resolution 8)
        client_id = os.environ.get(self._config.client_id_env)
        if not client_id:
            raise ValueError(
                f"OAuth2 client_id environment variable "
                f"'{self._config.client_id_env}' is not set or empty"
            )

        client_secret = os.environ.get(self._config.client_secret_env)
        if not client_secret:
            raise ValueError(
                f"OAuth2 client_secret environment variable "
                f"'{self._config.client_secret_env}' is not set or empty"
            )

        # Re-validate token URL at refresh time (SSRF protection)
        validate_url_safe(self._config.token_url)

        # Build the token request payload
        payload = {
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
        }
        if self._config.scopes:
            payload["scope"] = " ".join(self._config.scopes)

        logger.debug(
            "OAuth2TokenManager: refreshing token from %s",
            self._config.token_url,
        )

        async with httpx.AsyncClient() as http_client:
            response = await http_client.post(
                self._config.token_url,
                data=payload,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            response.raise_for_status()

        token_data = response.json()

        access_token = token_data.get("access_token")
        if not access_token:
            raise RuntimeError(
                "OAuth2 token response did not contain 'access_token'. "
                f"Response keys: {sorted(token_data.keys())}"
            )

        # Parse expiry: use expires_in if present, default to 3600s
        expires_in = token_data.get("expires_in", 3600)
        try:
            expires_in_seconds = int(expires_in)
        except (TypeError, ValueError):
            logger.warning(
                "OAuth2TokenManager: invalid expires_in value %r; "
                "defaulting to 3600s",
                expires_in,
            )
            expires_in_seconds = 3600

        # Validate expires_in is finite and positive
        if expires_in_seconds <= 0:
            logger.warning(
                "OAuth2TokenManager: expires_in=%d is non-positive; "
                "defaulting to 3600s",
                expires_in_seconds,
            )
            expires_in_seconds = 3600

        # Store token in-memory only (NEVER Redis, NEVER disk — H5)
        self._token = access_token
        self._expires_at = datetime.now(timezone.utc) + timedelta(
            seconds=expires_in_seconds
        )

        logger.debug(
            "OAuth2TokenManager: acquired token (expires_in=%ds, expires_at=%s)",
            expires_in_seconds,
            self._expires_at.isoformat(),
        )

        return access_token
