# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Tests for #459 — missing Nexus binding symbols for per-handler auth + typed errors.

Verifies cross-SDK alignment with kailash-rs#389: NexusAuthPlugin, AuthGuard,
typed errors, and guard= on @app.handler() are all importable and functional
from the nexus top-level package.
"""

import pytest


class TestNexusReExports:
    """Verify all four gap symbols are importable from nexus."""

    def test_nexus_auth_plugin_importable(self):
        """Gap 1: NexusAuthPlugin.saas_app() is importable from nexus."""
        from nexus import NexusAuthPlugin

        assert hasattr(NexusAuthPlugin, "saas_app")
        assert callable(NexusAuthPlugin.saas_app)

    def test_auth_guard_importable(self):
        """Gap 3: AuthGuard is importable from nexus."""
        from nexus import AuthGuard

        assert hasattr(AuthGuard, "RequireRole")
        assert hasattr(AuthGuard, "RequirePermission")
        assert hasattr(AuthGuard, "All")
        assert hasattr(AuthGuard, "Any")

    def test_typed_errors_importable(self):
        """Gap 4: All typed error classes importable from nexus."""
        from nexus import (
            BadGatewayError,
            ConflictError,
            NexusError,
            NexusPermissionError,
            NexusTimeoutError,
            NotFoundError,
            RateLimitError,
            ServiceUnavailableError,
            UnauthorizedError,
            ValidationError,
        )

        # All are subclasses of NexusError
        for cls in [
            ValidationError,
            NotFoundError,
            ConflictError,
            UnauthorizedError,
            NexusPermissionError,
            RateLimitError,
            ServiceUnavailableError,
            BadGatewayError,
            NexusTimeoutError,
        ]:
            assert issubclass(
                cls, NexusError
            ), f"{cls.__name__} not subclass of NexusError"

    def test_nexus_error_has_status_code(self):
        """Typed errors carry HTTP status codes for cross-channel translation."""
        from nexus import NotFoundError, ValidationError

        err = NotFoundError("not found")
        assert hasattr(err, "status_code")
        assert err.status_code == 404

        err2 = ValidationError("bad input")
        assert err2.status_code == 400


class TestJWTConfigKwarg:
    """Gap 2: JWTConfig accepts secret= kwarg."""

    def test_jwt_config_secret_kwarg(self):
        """JWTConfig(secret=...) matches cross-SDK spec."""
        from kailash.trust.auth.jwt import JWTConfig

        config = JWTConfig(secret="test-secret-at-least-32-chars-long!")
        assert config.secret == "test-secret-at-least-32-chars-long!"


class TestHandlerGuardParameter:
    """Gap 3: @app.handler(guard=...) accepts and stores guards."""

    def test_handler_def_has_guard_field(self):
        """HandlerDef dataclass has guard field."""
        from nexus.registry import HandlerDef

        hd = HandlerDef(name="test")
        assert hasattr(hd, "guard")
        assert hd.guard is None

    def test_handler_def_stores_guard(self):
        """HandlerDef stores a guard when provided."""
        from nexus import AuthGuard
        from nexus.registry import HandlerDef

        guard = AuthGuard.RequireRole("admin")
        hd = HandlerDef(name="test", guard=guard)
        assert hd.guard is guard

    def test_handler_registry_passes_guard(self):
        """HandlerRegistry.register_handler stores guard on HandlerDef."""
        from nexus import AuthGuard
        from nexus.registry import HandlerRegistry

        registry = HandlerRegistry()
        guard = AuthGuard.RequirePermission("items:delete")

        async def my_handler(name: str) -> dict:
            return {"name": name}

        hd = registry.register_handler("test.handler", my_handler, guard=guard)
        assert hd.guard is guard

    def test_guard_check_passes(self):
        """AuthGuard.RequireRole passes for a user with the role."""
        from nexus import AuthGuard

        guard = AuthGuard.RequireRole("admin")

        class FakeUser:
            roles = ["admin", "viewer"]

        passed, reason = guard.check(FakeUser())
        assert passed is True

    def test_guard_check_fails(self):
        """AuthGuard.RequireRole fails for a user without the role."""
        from nexus import AuthGuard

        guard = AuthGuard.RequireRole("admin")

        class FakeUser:
            roles = ["viewer"]

        passed, reason = guard.check(FakeUser())
        assert passed is False
        assert "admin" in reason

    def test_guard_check_fails_no_user(self):
        """Guards fail when no user is provided."""
        from nexus import AuthGuard

        guard = AuthGuard.RequirePermission("items:delete")
        passed, reason = guard.check(None)
        assert passed is False


class TestGuardEnforcement:
    """Guard enforcement at function-wrapping level (cross-transport)."""

    @pytest.mark.asyncio
    async def test_guarded_async_handler_raises_on_no_user(self):
        """Wrapped async handler raises NexusPermissionError when guard fails."""
        from nexus import AuthGuard, NexusPermissionError
        from nexus.core import _wrap_with_guard

        guard = AuthGuard.RequireRole("admin")

        async def my_handler(name: str) -> dict:
            return {"name": name}

        wrapped = _wrap_with_guard(my_handler, guard, "test.handler")

        with pytest.raises(NexusPermissionError):
            await wrapped(name="alice")

    def test_guarded_sync_handler_raises_on_no_user(self):
        """Wrapped sync handler raises NexusPermissionError when guard fails."""
        from nexus import AuthGuard, NexusPermissionError
        from nexus.core import _wrap_with_guard

        guard = AuthGuard.RequireRole("admin")

        def my_handler(name: str) -> dict:
            return {"name": name}

        wrapped = _wrap_with_guard(my_handler, guard, "test.handler")

        with pytest.raises(NexusPermissionError):
            wrapped(name="alice")

    def test_guarded_handler_passes_with_valid_user(self):
        """Wrapped handler passes when guard check succeeds."""
        from nexus import AuthGuard
        from nexus.core import _wrap_with_guard

        guard = AuthGuard.RequireRole("admin")

        class FakeRequest:
            class state:
                class user:
                    roles = ["admin"]

        def my_handler(request: object, name: str) -> dict:
            return {"name": name}

        wrapped = _wrap_with_guard(my_handler, guard, "test.handler")
        result = wrapped(request=FakeRequest(), name="alice")
        assert result == {"name": "alice"}

    def test_wrapped_preserves_function_name(self):
        """functools.wraps preserves the original function's metadata."""
        from nexus import AuthGuard
        from nexus.core import _wrap_with_guard

        guard = AuthGuard.RequireRole("admin")

        async def create_agent(name: str) -> dict:
            """Create an agent."""
            return {"name": name}

        wrapped = _wrap_with_guard(create_agent, guard, "agent.create")
        assert wrapped.__name__ == "create_agent"
        assert wrapped.__doc__ == "Create an agent."
