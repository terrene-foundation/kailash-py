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
    "JWTWebSocketAuthMiddleware",
]

#: Sent on every 401 so a compliant client knows which scheme to retry with.
_WWW_AUTHENTICATE = 'Bearer realm="api"'

#: Maps a configured algorithm name to the label this module logs for it.
#:
#: A MAPPING, not a set, and the keys and values are deliberately equal strings:
#: the config value is used only as a lookup KEY, so what reaches the log record
#: is always a literal defined here. That is what actually breaks the dataflow
#: from the secret-bearing ``JWTConfig`` to the log sink -- a set-membership test
#: leaves ``config.algorithm`` itself flowing out on the matching branch.
#: Anything unrecognized logs as ``"other"``.
#:
#: NOT an enforcement allowlist: which algorithms are ACCEPTED is
#: ``JWTValidator``'s decision (it bans ``none`` and rejects confusion), and
#: duplicating that policy here would create a second list to drift.
_ALGORITHM_LABELS = {
    "HS256": "HS256",
    "HS384": "HS384",
    "HS512": "HS512",
    "RS256": "RS256",
    "RS384": "RS384",
    "RS512": "RS512",
    "ES256": "ES256",
    "ES384": "ES384",
    "ES512": "ES512",
    "PS256": "PS256",
    "PS384": "PS384",
    "PS512": "PS512",
    "EdDSA": "EdDSA",
}


class JWTAuthMiddleware(BaseHTTPMiddleware):
    """Reject unauthenticated **HTTP** requests with 401 before any route.

    HTTP ONLY, and the word is load-bearing. This extends
    ``BaseHTTPMiddleware``, whose ``__call__`` begins::

        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

    so :meth:`dispatch` never runs for a ``websocket`` scope and every
    ``@app.websocket(...)`` route is served straight through. An earlier
    revision of this line said "before they reach any route", which was false
    for websocket routes and inherited by
    ``install_server_auth_middleware``'s own docstring.

    :class:`JWTWebSocketAuthMiddleware` is the sibling that covers the
    ``websocket`` scope. :func:`kailash.utils.server_auth.install_server_auth_middleware`
    installs BOTH; install this one alone and websocket routes stay open.

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
        # Counts and booleans only, and the algorithm resolved to a LITERAL
        # from a fixed set rather than echoed from the config.
        #
        # `config` is constructed from the signing secret, so every attribute
        # read off it is taint-carrying to a dataflow analyzer -- CodeQL
        # reported `py/clear-text-logging-sensitive-data` here for exactly that
        # reason. `config.algorithm` is not itself the secret, but proving that
        # to a scanner is not possible and asserting it is not worth doing on
        # an auth path.
        #
        # A membership test (`x if x in SET else "other"`) is NOT enough, and
        # was measured not to be: CodeQL still reported the finding, because on
        # the true branch the value flowing out is still `config.algorithm`.
        # A MAPPING lookup is the real fix rather than a scanner-pleasing one --
        # every value it can return is a literal owned by this module, so the
        # config string is used only as a KEY and never reaches the record.
        #
        # The exempt-path count and the api-key flag are NOT logged here, and
        # dropping them is a deduplication rather than a loss:
        # `server_auth.build_server_auth_config` already emits both on its own
        # `server_auth.configured` record, from the same values, one call
        # earlier. Reading them off `config` a second time re-derived
        # secret-adjacent state at a second sink for information already on the
        # record.
        logger.info(
            "jwt_auth_middleware.installed",
            extra={"algorithm": _ALGORITHM_LABELS.get(config.algorithm, "other")},
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


class JWTWebSocketAuthMiddleware:
    """Authenticate the WebSocket HANDSHAKE, or refuse to open the connection.

    The sibling of :class:`JWTAuthMiddleware` for the one scope that class
    cannot see. ``BaseHTTPMiddleware.__call__`` returns early for any scope
    whose type is not ``"http"``, so an ``@app.websocket("/ws")`` route was
    reachable with no credential on a server constructed with
    ``require_auth=True`` (issue #2072). Measured on ``WorkflowServer`` before
    this class existed: the handshake completed and the echo loop ran.

    Written as a PURE ASGI callable rather than a ``BaseHTTPMiddleware``
    subclass for exactly the reason above -- inheriting from that base is what
    causes the blind spot.

    **Rejection happens at the handshake, before ``accept``.** Accepting and
    then closing would still have allocated the connection and run the route's
    ``accept()`` path. Sending ``websocket.close`` while the handshake is still
    pending makes the server refuse it outright (uvicorn answers HTTP 403), so
    an unauthenticated caller never reaches the route's loop.

    **What this closes on the core echo route.** The in-tree handler is an echo,
    so immediate data exposure is low -- but ``await websocket.accept()``
    followed by ``while True`` is unauthenticated resource consumption per
    connection, the handler's own docstring invites subclasses to override it
    with something stateful, and ``register_mcp_server`` mounts third-party MCP
    applications that are told not to install their own gate.

    **Credential sources differ from HTTP by necessity.** A browser cannot set
    ``Authorization`` on a WebSocket handshake, so this also reads the cookie
    and query-parameter sources when the config enables them. It never invents
    a source the config did not enable.

    Args:
        app: The ASGI application to wrap.
        config: JWT configuration. Required, for the same reason
            :class:`JWTAuthMiddleware` requires one.
    """

    def __init__(self, app: Any, config: JWTConfig) -> None:
        if config is None:
            raise ValueError(
                "JWTWebSocketAuthMiddleware requires a JWTConfig. Passing None "
                "would install a middleware with no credential to verify "
                "against, which authenticates nothing while appearing to "
                "(#2072)."
            )
        self.app = app
        self.config = config
        self._validator = JWTValidator(config)

    async def __call__(self, scope: Dict[str, Any], receive: Any, send: Any) -> None:
        if scope.get("type") != "websocket":
            await self.app(scope, receive, send)
            return

        if self._validator.is_path_exempt(scope.get("path", "")):
            await self.app(scope, receive, send)
            return

        token = self._extract_token_from_scope(scope)
        if not token:
            await self._deny(scope, receive, send, "missing_token")
            return

        if token.startswith("__apikey__") and self.config.api_key_enabled:
            api_key_result = await self._api_key_ok(token[len("__apikey__") :])
            if not api_key_result:
                await self._deny(scope, receive, send, "invalid_api_key")
                return
            # Populate the principal, exactly as the HTTP sibling does at
            # `_dispatch_api_key`. This branch previously accepted the
            # handshake and passed it through with NO `scope["state"]["user"]`,
            # so a route that reads the authenticated principal saw nothing on
            # a credential the gate had just ACCEPTED -- and a fail-closed
            # route then refused it (close 1008). Not a bypass, but a
            # reachability regression for a valid credential, and the exact
            # surface-parity gap `security.md` names: two independent paths
            # authenticating the same key, only one recording who it was.
            scope.setdefault("state", {})
            try:
                if isinstance(api_key_result, dict):
                    scope["state"]["user"] = self._validator.create_user_from_payload(
                        api_key_result
                    )
                else:
                    scope["state"]["user"] = AuthenticatedUser(
                        user_id="apikey", roles=["api"]
                    )
                scope["state"]["token_payload"] = {"type": "api_key"}
            except Exception:
                logger.exception(
                    "jwt_ws_auth_middleware.api_key_user_construction_failed",
                    extra={"path": scope.get("path", "")},
                )
                await self._deny(scope, receive, send, "auth_error")
                return
            await self.app(scope, receive, send)
            return

        try:
            payload = self._validator.verify_token(token)
            if self._validator.check_token_age(payload):
                await self._deny(scope, receive, send, "invalid_token")
                return
        except (ExpiredTokenError, InvalidTokenError) as exc:
            # Logged, never sent: the validator's text can name the configured
            # algorithm and issuer, which fingerprints the server for an
            # unauthenticated caller.
            logger.warning(
                "jwt_ws_auth_middleware.invalid_token",
                extra={"path": scope.get("path", ""), "reason": str(exc)},
            )
            await self._deny(scope, receive, send, "invalid_token")
            return
        except Exception:
            # Not a swallow -- logged with a stack trace and still failing
            # CLOSED. An unexpected verification error must never fall through
            # into an open socket.
            logger.exception(
                "jwt_ws_auth_middleware.verification_failed",
                extra={"path": scope.get("path", "")},
            )
            await self._deny(scope, receive, send, "auth_error")
            return

        # Starlette exposes `scope["state"]` to the endpoint as
        # `websocket.state`, which is how a route reads who connected.
        scope.setdefault("state", {})
        try:
            scope["state"]["user"] = self._validator.create_user_from_payload(payload)
            scope["state"]["token_payload"] = payload
        except Exception:
            logger.exception(
                "jwt_ws_auth_middleware.user_construction_failed",
                extra={"path": scope.get("path", "")},
            )
            await self._deny(scope, receive, send, "auth_error")
            return

        await self.app(scope, receive, send)

    async def _api_key_ok(self, api_key: str) -> Any:
        """Authenticate an API key, RETURNING the validator's own result.

        Returns the validator's value rather than a bare bool so the caller
        can build the same principal the HTTP path builds: a dict result
        carries claims (name, roles, tenant) that `create_user_from_payload`
        normalizes, and collapsing it to `True` discarded exactly the
        information needed to say WHO connected. Falsy (reject) and the
        error paths return a falsy value, so `if not result` still reads as
        the rejection test.
        """
        validator = self.config.api_key_validator
        if validator is None:
            logger.error(
                "jwt_ws_auth_middleware.api_key_enabled_without_validator",
            )
            return None
        try:
            result = validator(api_key)
            if inspect.isawaitable(result):
                result = await result
        except Exception:
            # Logged with a stack trace and failing CLOSED (the caller denies
            # on a falsy return) -- not a swallow.
            logger.exception("jwt_ws_auth_middleware.api_key_validator_failed")
            return None
        return result

    async def _deny(
        self, scope: Dict[str, Any], receive: Any, send: Any, error: str
    ) -> None:
        """Refuse the handshake without ever calling ``accept``.

        The ``websocket.connect`` event is consumed first because the ASGI spec
        has the server send it before the application may reply. Uvicorn
        tolerates a ``close`` sent without it; other servers (hypercorn, daphne,
        the wsproto implementation) are stricter, and a gate that only fails
        closed on one server is not a gate.

        The close carries 1008 (POLICY VIOLATION) and no reason text, matching
        :meth:`JWTAuthMiddleware._unauthorized`: an unauthenticated caller
        learns only that it was refused.
        """
        logger.warning(
            "jwt_ws_auth_middleware.rejected",
            extra={"path": scope.get("path", ""), "error": error},
        )
        try:
            await receive()
        except Exception:
            # The peer can vanish between the server queuing `connect` and this
            # read. Reported at debug rather than raised: the connection is
            # already gone, and the close below is then a no-op. Failing here
            # would turn a disconnect into a 500 on the server's error path.
            logger.debug(
                "jwt_ws_auth_middleware.connect_event_unavailable", exc_info=True
            )
        await send({"type": "websocket.close", "code": 1008})

    def _extract_token_from_scope(self, scope: Dict[str, Any]) -> Optional[str]:
        """Extract an API key or bearer token from a raw websocket scope.

        Same priority order as :meth:`JWTAuthMiddleware._extract_token`, read
        from ``scope`` directly because there is no ``Request`` for a websocket
        handshake. Header names are compared lowercased: HTTP/2 requires
        lowercase and ASGI does not normalize case for the application.
        """
        headers = {
            key.decode("latin-1").lower(): value.decode("latin-1")
            for key, value in scope.get("headers", [])
        }

        if self.config.api_key_enabled:
            api_key = headers.get(self.config.api_key_header.lower(), "")
            if api_key:
                return f"__apikey__{api_key}"

        auth_header = headers.get(self.config.token_header.lower(), "")
        # Scheme names are case-insensitive per RFC 7235 §2.1.
        if auth_header[:7].lower() == "bearer ":
            return auth_header[7:].strip() or None

        if self.config.token_cookie:
            from http.cookies import SimpleCookie

            try:
                jar = SimpleCookie()
                jar.load(headers.get("cookie", ""))
                morsel = jar.get(self.config.token_cookie)
            except Exception:
                # A malformed Cookie header is attacker-supplied input, not a
                # server fault. Reported at debug and treated as "no cookie",
                # which falls through to the query param and ultimately to a
                # denial -- never to an open socket.
                logger.debug(
                    "jwt_ws_auth_middleware.cookie_parse_failed", exc_info=True
                )
                morsel = None
            if morsel is not None and morsel.value:
                return morsel.value

        if self.config.token_query_param:
            from urllib.parse import parse_qs

            query = parse_qs(scope.get("query_string", b"").decode("latin-1"))
            values = query.get(self.config.token_query_param) or []
            if values and values[0]:
                return values[0]

        return None
