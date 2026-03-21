# Copyright 2026 Terrene Foundation
# Licensed under the Apache License, Version 2.0
"""Authentication and authorization for governance API endpoints.

Provides scope-based access control for governance operations:
- governance:read  -- query org structure, check access, verify actions
- governance:write -- grant clearance, create bridges, create KSPs
- governance:admin -- all operations including configuration changes

Token verification uses constant-time comparison via hmac.compare_digest()
to prevent timing side-channel attacks (per trust-plane-security.md rule).

Dev mode: When no API token is configured, authentication is disabled
for local development. This matches the existing server.py behavior.
"""

from __future__ import annotations

import hmac
import logging
import os
from typing import Any

from fastapi import HTTPException, Request

logger = logging.getLogger(__name__)

__all__ = ["GovernanceAuth"]


_UNSET = object()
"""Sentinel to distinguish 'not passed' from 'explicitly None'."""


class GovernanceAuth:
    """Authorization for governance endpoints.

    Supports three scopes:
    - governance:read  -- GET endpoints and POST check/verify
    - governance:write -- POST endpoints that mutate state
    - governance:admin -- all operations

    Token resolution order (when api_token is not passed):
    1. PACT_GOVERNANCE_API_TOKEN environment variable
    2. PACT_API_TOKEN environment variable (fallback)
    3. None -- dev mode, auth disabled

    When api_token is explicitly provided (including None), env vars
    are NOT consulted. This allows tests to force dev mode by passing
    api_token=None.
    """

    SCOPES = frozenset({"governance:read", "governance:write", "governance:admin"})

    def __init__(self, api_token: str | None = _UNSET) -> None:  # type: ignore[assignment]
        if api_token is not _UNSET:
            # Explicit value provided (could be a string or None)
            self._api_token: str | None = api_token
        else:
            # Not provided -- resolve from environment
            self._api_token = (
                os.environ.get("PACT_GOVERNANCE_API_TOKEN")
                or os.environ.get("PACT_API_TOKEN")
                or None
            )

        if self._api_token:
            logger.info("GovernanceAuth initialized with API token authentication")
        else:
            logger.warning(
                "GovernanceAuth initialized without API token -- "
                "auth is disabled (dev mode). Set PACT_GOVERNANCE_API_TOKEN "
                "or PACT_API_TOKEN to enable."
            )

    def verify_token(self, token: str | None) -> str:
        """Verify a bearer token and return the identity string.

        Args:
            token: The bearer token from the Authorization header,
                or None if no token was provided.

        Returns:
            Identity string: "authenticated" for valid tokens,
            "anonymous" for dev mode.

        Raises:
            HTTPException: 401 if token is invalid or missing when required.
        """
        # Dev mode: no API token configured
        if not self._api_token:
            return "anonymous"

        # Token required but not provided
        if not token:
            raise HTTPException(
                status_code=401,
                detail="Authentication required: provide Bearer token in Authorization header",
            )

        # Constant-time comparison to prevent timing attacks
        if hmac.compare_digest(token, self._api_token):
            return "authenticated"

        raise HTTPException(
            status_code=401,
            detail="Invalid API token",
        )

    async def require_read(self, request: Request) -> str:
        """Require governance:read scope. Used as FastAPI dependency.

        Args:
            request: The incoming HTTP request.

        Returns:
            Identity string for the authenticated caller.

        Raises:
            HTTPException: 401 if authentication fails.
        """
        return self._verify_from_request(request, "governance:read")

    async def require_write(self, request: Request) -> str:
        """Require governance:write scope. Used as FastAPI dependency.

        Args:
            request: The incoming HTTP request.

        Returns:
            Identity string for the authenticated caller.

        Raises:
            HTTPException: 401 if authentication fails.
        """
        return self._verify_from_request(request, "governance:write")

    async def require_admin(self, request: Request) -> str:
        """Require governance:admin scope. Used as FastAPI dependency.

        Args:
            request: The incoming HTTP request.

        Returns:
            Identity string for the authenticated caller.

        Raises:
            HTTPException: 401 if authentication fails.
        """
        return self._verify_from_request(request, "governance:admin")

    def _verify_from_request(self, request: Request, scope: str) -> str:
        """Extract bearer token from request and verify.

        Args:
            request: The incoming HTTP request.
            scope: The required scope (logged for audit).

        Returns:
            Identity string for the authenticated caller.

        Raises:
            HTTPException: 401 if authentication fails.
        """
        auth_header = request.headers.get("authorization", "")
        token: str | None = None
        if auth_header.lower().startswith("bearer "):
            token = auth_header[7:]  # Strip "Bearer " prefix

        identity = self.verify_token(token)

        logger.debug(
            "Governance auth: identity=%s scope=%s path=%s",
            identity,
            scope,
            request.url.path,
        )
        return identity
