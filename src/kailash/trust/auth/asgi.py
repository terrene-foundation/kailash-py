# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Starlette ASGI authentication middleware -- the core-side auth primitive.

Issue #2072. ``kailash.servers`` needed a gate that reaches routes registered
by ``app.mount(...)``, and core had none: ``grep -rn 'BaseHTTPMiddleware'
src/kailash/`` returned zero matches before this module existed.

**Why middleware and not a route dependency.** ``WorkflowServer.register_workflow``
and ``register_mcp_server`` both mount a sub-application. A ``Depends`` declared
on the parent app -- even ``FastAPI(dependencies=[...])`` -- does NOT run for a
request routed into a mounted sub-app, because the mount hands the raw ASGI
scope to a *different* application whose own dependency stack is empty. ASGI
middleware wraps the outermost app, so it sees the request before routing
decides which sub-app owns it. Measured on this codebase, with a credentialed
third row as the discrimination control::

    A app-level Depends  -> /direct        : 401
    A app-level Depends  -> mounted execute: 200      <-- OPEN
    B middleware         -> /direct        : 401
    B middleware         -> mounted execute: 401      <-- closed
    B middleware + creds -> mounted execute: 200      <-- control

Without the third row the 401 on B could equally have been a broken route.

All crypto is delegated to :class:`kailash.trust.auth.jwt.JWTValidator`, which
already implements algorithm-confusion rejection, the ``none``-algorithm ban,
JWKS, and the RFC 7518 §3.2 32-byte minimum for HS*. This module contributes
only the HTTP binding.

``nexus.auth.jwt.JWTMiddleware`` is the sibling binding for the Nexus surface.
It is NOT imported here and must not be: Nexus depends on ``kailash``, never the
reverse, so core cannot reach it. It additionally propagates Nexus-specific
tenant/actor contextvars, which is why :meth:`JWTAuthMiddleware.request_context`
exists as an override point rather than being inlined.
"""

from __future__ import annotations

import inspect
import logging
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Callable, Dict, Optional

# `starlette` is an OPTIONAL dependency under the `server` extra. Per
# `rules/dependencies.md` § "Declared = Imported", raise loudly naming the extra.
try:
    from starlette.middleware.base import BaseHTTPMiddleware
    from starlette.requests import Request
    from starlette.responses import JSONResponse, Response
except ImportError as exc:  # pragma: no cover -- covered by structural test
    raise ImportError(
        "kailash.trust.auth.asgi requires Starlette. "
        "Install with: pip install 'kailash[server]'"
    ) from exc

from kailash.trust.auth.exceptions import ExpiredTokenError, InvalidTokenError
from kailash.trust.auth.jwt import JWTConfig, JWTValidator
from kailash.trust.auth.models import AuthenticatedUser

logger = logging.getLogger(__name__)

__all__ = [
    "JWTAuthMiddleware",
]

#: Sent on every 401 so a compliant client knows which scheme to retry with.
_WWW_AUTHENTICATE = 'Bearer realm="api"'


class JWTAuthMiddleware(BaseHTTPMiddleware):
    """Reject unauthenticated requests with 401 before they reach any route.

    Args:
        app: The ASGI application to wrap.
        config: JWT configuration. Required -- there is deliberately no
            default, because a middleware that constructed its own config
            would be able to come up with a usable one from nothing and
            silently authenticate against a key the operator never chose.

    Example:
        >>> from kailash.trust.auth.asgi import JWTAuthMiddleware
        >>> from kailash.trust.auth.jwt import JWTConfig
        >>> config = JWTConfig(secret="a" * 32, exempt_paths=["/health"])
        >>> app.add_middleware(JWTAuthMiddleware, config=config)  # doctest: +SKIP

    Note:
        Starlette's ``add_middleware`` **prepends**, so the layer added LAST is
        the OUTERMOST one. Add this BEFORE ``CORSMiddleware`` or a cross-origin
        preflight ``OPTIONS`` is rejected with 401 by auth before CORS can
        answer it. PR #2054 hit exactly that ordering bug on the Nexus surface.
    """

    def __init__(self, app: Any, config: JWTConfig) -> None:
        super().__init__(app)
        if config is None:
            raise ValueError(
                "JWTAuthMiddleware requires a JWTConfig. Passing None would "
                "install a middleware with no credential to verify against, "
                "which authenticates nothing while appearing to (#2072)."
            )
        self.config = config
        self._validator = JWTValidator(config)
        logger.info(
            "jwt_auth_middleware.installed",
            extra={
                "algorithm": config.algorithm,
                "exempt_path_count": len(config.exempt_paths),
                "api_key_enabled": config.api_key_enabled,
            },
        )

    # ------------------------------------------------------------------
    # Override point
    # ------------------------------------------------------------------
    @asynccontextmanager
    async def request_context(
        self, claims: Dict[str, Any]
    ) -> AsyncIterator[None]:  # pragma: no cover -- trivial default
        """Ambient context held for the duration of the downstream call.

        The default is a no-op. Bindings that propagate request-scoped state
        (Nexus sets tenant/actor contextvars) override this. Implementations
        MUST reset their state in a ``finally:`` -- a raise inside the
        downstream call must not leak the previous request's tenant into the
        next request served by the same worker.
        """
        yield

    # ------------------------------------------------------------------
    # Dispatch
    # ------------------------------------------------------------------
    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Any]
    ) -> Response:
        """Authenticate the request or return 401."""
        if self._validator.is_path_exempt(request.url.path):
            return await call_next(request)

        token = self._extract_token(request)
        if not token:
            return self._unauthorized("missing_token")

        if token.startswith("__apikey__") and self.config.api_key_enabled:
            return await self._dispatch_api_key(
                request, call_next, token[len("__apikey__") :]
            )

        return await self._dispatch_bearer(request, call_next, token)

    async def _dispatch_bearer(
        self, request: Request, call_next: Callable[[Request], Any], token: str
    ) -> Response:
        try:
            payload = self._validator.verify_token(token)
            age_error = self._validator.check_token_age(payload)
            if age_error:
                # `age_error` is generated by the validator from configuration,
                # never from the token, so it carries no attacker-controlled
                # bytes back to the caller.
                logger.warning(
                    "jwt_auth_middleware.token_age_rejected",
                    extra={"path": request.url.path},
                )
                return self._unauthorized("invalid_token")

            user = self._validator.create_user_from_payload(payload)
        except ExpiredTokenError:
            return self._unauthorized("token_expired")
        except InvalidTokenError as exc:
            # The exception text is logged, never returned: it can name the
            # configured algorithm and issuer, which is a fingerprinting aid
            # for an unauthenticated caller.
            logger.warning(
                "jwt_auth_middleware.invalid_token",
                extra={"path": request.url.path, "reason": str(exc)},
            )
            return self._unauthorized("invalid_token")
        except Exception:
            # Not `except: pass` -- this logs with a stack trace and still
            # fails CLOSED with 401. An unexpected verification error must
            # never fall through into the protected route.
            logger.exception(
                "jwt_auth_middleware.verification_failed",
                extra={"path": request.url.path},
            )
            return self._unauthorized("auth_error")

        request.state.user = user
        request.state.token_payload = payload

        if self.config.on_token_validated:
            try:
                result = self.config.on_token_validated(payload)
                if inspect.isawaitable(result):
                    await result
            except Exception:
                # An audit/stale-detection hook is advisory. It is logged with
                # a stack trace and never allowed to convert a valid token
                # into a 500, but neither is it allowed to pass silently.
                logger.exception("jwt_auth_middleware.on_token_validated_failed")

        async with self.request_context(payload):
            return await call_next(request)

    async def _dispatch_api_key(
        self, request: Request, call_next: Callable[[Request], Any], api_key: str
    ) -> Response:
        validator = self.config.api_key_validator
        if validator is None:
            # api_key_enabled without a validator cannot authenticate anyone.
            # Fail closed with 401 rather than 500: the caller is still
            # unauthenticated, and a 500 would advertise a server misconfig to
            # an anonymous prober. The operator gets the detail in the log.
            logger.error(
                "jwt_auth_middleware.api_key_enabled_without_validator",
                extra={"path": request.url.path},
            )
            return self._unauthorized("invalid_api_key")

        try:
            result = validator(api_key)
            if inspect.isawaitable(result):
                result = await result
        except Exception:
            logger.exception("jwt_auth_middleware.api_key_validator_failed")
            return self._unauthorized("invalid_api_key")

        if not result:
            return self._unauthorized("invalid_api_key")

        if isinstance(result, dict):
            claims = result
            user = self._validator.create_user_from_payload(result)
        else:
            claims = {"type": "api_key"}
            user = AuthenticatedUser(user_id="apikey", roles=["api"])

        request.state.user = user
        request.state.token_payload = {"type": "api_key"}

        async with self.request_context(claims):
            return await call_next(request)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _unauthorized(self, error: str) -> JSONResponse:
        """Build the 401 response.

        The body carries a stable machine-readable ``error`` code and a fixed
        human string. It never echoes the token, the exception text, or any
        configuration value -- an unauthenticated caller learns only that it
        is unauthenticated.
        """
        return JSONResponse(
            status_code=401,
            content={"detail": "Not authenticated", "error": error},
            headers={"WWW-Authenticate": _WWW_AUTHENTICATE},
        )

    def _extract_token(self, request: Request) -> Optional[str]:
        """Extract an API key or bearer token, in priority order.

        1. API-key header (only when ``api_key_enabled``)
        2. ``Authorization: Bearer <token>``
        3. Cookie (only when ``token_cookie`` is configured)
        4. Query parameter (only when ``token_query_param`` is configured)

        Returns ``None`` when no credential is present, which the caller turns
        into a 401.
        """
        if self.config.api_key_enabled:
            api_key = request.headers.get(self.config.api_key_header, "")
            if api_key:
                return f"__apikey__{api_key}"

        auth_header = request.headers.get(self.config.token_header, "")
        # Scheme names are case-insensitive per RFC 7235 §2.1.
        if auth_header[:7].lower() == "bearer ":
            return auth_header[7:].strip() or None

        if self.config.token_cookie:
            token = request.cookies.get(self.config.token_cookie)
            if token:
                return token

        if self.config.token_query_param:
            token = request.query_params.get(self.config.token_query_param)
            if token:
                return token

        return None
