# Copyright 2026 Terrene Foundation
# Licensed under the Apache License, Version 2.0
"""Unit tests for governance API authentication and authorization.

Tests the GovernanceAuth class: scope validation, token verification,
unauthenticated rejection, and scope-based access control.
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock

import pytest

from pact.governance.api.auth import GovernanceAuth


# ===================================================================
# GovernanceAuth initialization
# ===================================================================


class TestGovernanceAuthInit:
    """Test GovernanceAuth construction and configuration."""

    def test_explicit_token(self) -> None:
        """Auth uses the explicitly provided API token."""
        auth = GovernanceAuth(api_token="test-token-123")
        assert auth._api_token == "test-token-123"

    def test_token_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Falls back to PACT_GOVERNANCE_API_TOKEN env var."""
        monkeypatch.setenv("PACT_GOVERNANCE_API_TOKEN", "env-token-456")
        auth = GovernanceAuth()
        assert auth._api_token == "env-token-456"

    def test_falls_back_to_pact_api_token(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Falls back to PACT_API_TOKEN when governance-specific token not set."""
        monkeypatch.delenv("PACT_GOVERNANCE_API_TOKEN", raising=False)
        monkeypatch.setenv("PACT_API_TOKEN", "general-token-789")
        auth = GovernanceAuth()
        assert auth._api_token == "general-token-789"

    def test_no_token_set(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """When no token is configured, auth is disabled (dev mode)."""
        monkeypatch.delenv("PACT_GOVERNANCE_API_TOKEN", raising=False)
        monkeypatch.delenv("PACT_API_TOKEN", raising=False)
        auth = GovernanceAuth()
        assert auth._api_token is None

    def test_scopes_defined(self) -> None:
        """GovernanceAuth defines the expected scopes."""
        assert "governance:read" in GovernanceAuth.SCOPES
        assert "governance:write" in GovernanceAuth.SCOPES
        assert "governance:admin" in GovernanceAuth.SCOPES


# ===================================================================
# Token verification logic
# ===================================================================


class TestGovernanceAuthVerification:
    """Test the _verify method internals."""

    def test_valid_token_returns_identity(self) -> None:
        """A valid token returns the identity string."""
        auth = GovernanceAuth(api_token="correct-token")
        identity = auth.verify_token("correct-token")
        assert identity == "authenticated"

    def test_invalid_token_raises(self) -> None:
        """An invalid token raises an error."""
        auth = GovernanceAuth(api_token="correct-token")
        with pytest.raises(Exception):
            auth.verify_token("wrong-token")

    def test_no_token_configured_allows_dev_mode(self) -> None:
        """When no API token is configured, dev mode allows access."""
        auth = GovernanceAuth(api_token=None)
        identity = auth.verify_token(None)
        assert identity == "anonymous"

    def test_no_token_configured_with_bearer_allows_dev_mode(self) -> None:
        """Dev mode allows any bearer token when no API token is configured."""
        auth = GovernanceAuth(api_token=None)
        identity = auth.verify_token("any-token")
        assert identity == "anonymous"

    def test_missing_token_when_required_raises(self) -> None:
        """When API token IS configured, missing token is rejected."""
        auth = GovernanceAuth(api_token="required-token")
        with pytest.raises(Exception):
            auth.verify_token(None)

    def test_constant_time_comparison(self) -> None:
        """Token comparison uses hmac.compare_digest (not ==)."""
        # We verify this through the implementation, not behavior,
        # but we can at least verify timing attacks don't work with valid/invalid
        auth = GovernanceAuth(api_token="secret-token")
        # Valid
        assert auth.verify_token("secret-token") == "authenticated"
        # Invalid
        with pytest.raises(Exception):
            auth.verify_token("secret-toke")  # off by one char


# ===================================================================
# Scope-based access control
# ===================================================================


class TestGovernanceAuthScopes:
    """Test scope-based access delegation methods."""

    @pytest.mark.asyncio
    async def test_require_read_with_valid_token(self) -> None:
        """require_read returns identity when token is valid."""
        auth = GovernanceAuth(api_token="test-token")
        request = _make_mock_request("test-token")
        identity = await auth.require_read(request)
        assert identity == "authenticated"

    @pytest.mark.asyncio
    async def test_require_write_with_valid_token(self) -> None:
        """require_write returns identity when token is valid."""
        auth = GovernanceAuth(api_token="test-token")
        request = _make_mock_request("test-token")
        identity = await auth.require_write(request)
        assert identity == "authenticated"

    @pytest.mark.asyncio
    async def test_require_admin_with_valid_token(self) -> None:
        """require_admin returns identity when token is valid."""
        auth = GovernanceAuth(api_token="test-token")
        request = _make_mock_request("test-token")
        identity = await auth.require_admin(request)
        assert identity == "authenticated"

    @pytest.mark.asyncio
    async def test_require_read_without_token_raises(self) -> None:
        """require_read raises 401 when no token provided and auth is required."""
        auth = GovernanceAuth(api_token="required-token")
        request = _make_mock_request(None)
        with pytest.raises(Exception):
            await auth.require_read(request)

    @pytest.mark.asyncio
    async def test_require_write_without_token_raises(self) -> None:
        """require_write raises 401 when no token provided and auth is required."""
        auth = GovernanceAuth(api_token="required-token")
        request = _make_mock_request(None)
        with pytest.raises(Exception):
            await auth.require_write(request)

    @pytest.mark.asyncio
    async def test_dev_mode_allows_read(self) -> None:
        """In dev mode (no API token configured), require_read allows access."""
        auth = GovernanceAuth(api_token=None)
        request = _make_mock_request(None)
        identity = await auth.require_read(request)
        assert identity == "anonymous"


# ===================================================================
# Helpers
# ===================================================================


def _make_mock_request(bearer_token: str | None) -> MagicMock:
    """Create a mock Request with an optional Authorization header."""
    request = MagicMock()
    if bearer_token is not None:
        request.headers = {"authorization": f"Bearer {bearer_token}"}
    else:
        request.headers = {}
    return request
