# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Fail-closed JWT authentication for **aiohttp** server surfaces.

The aiohttp sibling of :mod:`kailash.trust.auth.asgi`. It exists because the
eighth un-gated HTTP server found by the #2112 parity sweep --
:class:`~kailash.nodes.monitoring.connection_dashboard.ConnectionDashboardNode`
-- is an ``aiohttp.web.Application``, not an ASGI app, so
:func:`kailash.utils.server_auth.install_server_auth_middleware` (which calls
Starlette's ``add_middleware``) cannot reach it.

**The DECISION half is shared, only the INSTALLATION half is new.** Whether to
authenticate, with which credential, and which paths are exempt is decided by
:func:`kailash.utils.server_auth.resolve_server_auth` exactly as it is for the
seven ASGI surfaces, and the token is verified by the same
:class:`kailash.trust.auth.jwt.JWTValidator`. Per ``rules/security.md``
§ Enforcement-Surface Parity, a second POLICY implementation is what this
module deliberately avoids; the transport adapter below is all that differs.

One structural advantage over ASGI: aiohttp's WebSocket upgrade happens INSIDE
a normal request handler (``web.WebSocketResponse().prepare(request)``), so a
single middleware sees the handshake as an ordinary HTTP request. There is no
websocket blind spot to close separately here -- the split that
``install_server_auth_middleware`` is forced into by ``BaseHTTPMiddleware``
does not arise. A test pins that the ``/ws`` handshake is actually gated,
because "it should follow from the architecture" is not a measurement.
"""

from __future__ import annotations

import importlib
import inspect
import logging
from typing import TYPE_CHECKING, Any, Callable, Optional

if TYPE_CHECKING:  # pragma: no cover -- typing only
    from kailash.trust.auth.jwt import JWTConfig

logger = logging.getLogger(__name__)

__all__ = ["build_jwt_auth_middleware", "install_aiohttp_auth_middleware"]

#: Matches :data:`kailash.trust.auth.asgi._WWW_AUTHENTICATE` in spirit: a
#: bearer challenge naming no realm, issuer or algorithm. An unauthenticated
#: caller learns that it is unauthenticated and nothing about the server.
_WWW_AUTHENTICATE = "Bearer"


def _unauthorized(error: str):
    """Build the 401 response.

    The body carries a stable machine-readable ``error`` code and a fixed
    human string, and never echoes the token, the exception text, or any
    configuration value -- byte-identical in shape to the ASGI middleware's
    401 so a client can treat the two surfaces the same way.
    """
    from aiohttp import web

    return web.json_response(
        {"detail": "Not authenticated", "error": error},
        status=401,
        headers={"WWW-Authenticate": _WWW_AUTHENTICATE},
    )


def _extract_token(request: Any, config: "JWTConfig") -> Optional[str]:
    """Extract an API key or bearer token, in the ASGI middleware's order.

    1. API-key header (only when ``api_key_enabled``)
    2. ``Authorization: Bearer <token>``
    3. Cookie (only when ``token_cookie`` is configured)
    4. Query parameter (only when ``token_query_param`` is configured)

    Deliberately the SAME priority order as
    :meth:`kailash.trust.auth.asgi.JWTAuthMiddleware._extract_token`. A
    surface that accepted a credential source the ASGI surfaces reject (or
    vice versa) would be an enforcement-parity gap of its own.

    Returns ``None`` when no credential is present, which the caller turns
    into a 401. It never invents a source the config did not enable.
    """
    if config.api_key_enabled:
        api_key = request.headers.get(config.api_key_header, "")
        if api_key:
            return f"__apikey__{api_key}"

    auth_header = request.headers.get(config.token_header, "")
    # Scheme names are case-insensitive per RFC 7235 §2.1.
    if auth_header[:7].lower() == "bearer ":
        return auth_header[7:].strip() or None

    if config.token_cookie:
        token = request.cookies.get(config.token_cookie)
        if token:
            return token

    if config.token_query_param:
        token = request.query.get(config.token_query_param)
        if token:
            return token

    return None


def _cors_preflight_function() -> Optional[Any]:
    """The underlying function of ``aiohttp_cors``'s preflight handler, if any.

    Resolved ONCE at import. Returns ``None`` when ``aiohttp_cors`` is absent
    or has renamed the symbol -- in which case there is no preflight handler
    to exempt and :func:`_is_cors_preflight` denies every OPTIONS request,
    which is the fail-CLOSED direction.
    """
    # `aiohttp_cors.preflight_handler` is the DEFINING module; `cors_config`
    # re-exports the same object (verified: `A is B` and
    # `A._preflight_handler is B._preflight_handler`). The defining module is
    # tried first because importing the re-export is what pyright reports as
    # `reportPrivateImportUsage`. The name is private either way, which is why
    # every step here is guarded and an unresolvable symbol fails CLOSED.
    handler = None
    for module_name in (
        "aiohttp_cors.preflight_handler",
        "aiohttp_cors.cors_config",
    ):
        try:
            module = importlib.import_module(module_name)
        except Exception:
            continue
        preflight_cls = getattr(module, "_PreflightHandler", None)
        handler = getattr(preflight_cls, "_preflight_handler", None)
        if handler is not None:
            break
    # On a class the attribute is already a plain function; `__func__` covers
    # the bound-method form defensively.
    return getattr(handler, "__func__", handler)


_CORS_PREFLIGHT_FUNC = _cors_preflight_function()

if _CORS_PREFLIGHT_FUNC is None:  # pragma: no cover -- depends on installed extras
    logger.warning(
        "aiohttp_jwt_auth.preflight_handler_unresolved",
        extra={
            "effect": (
                "CORS preflight OPTIONS requests will be authenticated like any "
                "other request and will therefore be rejected with 401"
            ),
            "wiring": (
                "install aiohttp-cors, or add the preflight path to "
                "auth_exempt_paths"
            ),
        },
    )


def _is_cors_preflight(request: Any) -> bool:
    """True only when this request RESOLVED to ``aiohttp_cors``'s own handler.

    The OPTIONS exemption must be decided by WHAT WILL RUN, never by what the
    caller claims. An earlier revision gated on ``request.method == "OPTIONS"``
    plus the presence of the ``Origin`` and ``Access-Control-Request-Method``
    headers -- three properties an attacker sets freely -- and never checked
    that ``handler`` was the preflight handler at all. On an application whose
    routes are all method-specific that is unreachable, because OPTIONS
    resolves only to the preflight route. But this module is EXPORTED, and a
    consumer with ``router.add_route("*", ...)``, a ``web.View`` implementing
    ``options()``, or an explicit ``add_options(...)`` made it an
    unauthenticated invocation of their own handler::

        curl -X OPTIONS -H 'Origin: x' -H 'Access-Control-Request-Method: GET' \\
             https://host/api/thing

    Measured on aiohttp 3.13.3 / aiohttp_cors 0.8.1, the resolved handler
    discriminates the two cases exactly::

        OPTIONS /g     -> _PreflightHandler._preflight_handler   (real preflight)
        OPTIONS /star  -> star_h                                 (consumer handler)

    ``request.match_info`` is populated by ``UrlDispatcher.resolve()`` BEFORE
    the middleware chain runs, so the resolved handler is available here --
    also measured, not assumed.

    Fails CLOSED: an unresolvable preflight symbol returns ``None`` above and
    every OPTIONS request is then authenticated normally.
    """
    if _CORS_PREFLIGHT_FUNC is None:
        return False
    handler = getattr(getattr(request, "match_info", None), "handler", None)
    if handler is None:
        return False
    return getattr(handler, "__func__", None) is _CORS_PREFLIGHT_FUNC


def build_jwt_auth_middleware(config: "JWTConfig") -> Callable:
    """Build an ``aiohttp`` middleware that authenticates every request.

    Args:
        config: JWT configuration. Required -- there is deliberately no
            default, for the same reason
            :class:`~kailash.trust.auth.asgi.JWTAuthMiddleware` requires one:
            a middleware able to construct its own config could come up with a
            usable one from nothing and silently authenticate against a key the
            operator never chose.

    Returns:
        An ``@web.middleware``-decorated coroutine ready for
        ``web.Application(middlewares=[...])``.

    Raises:
        ValueError: ``config`` is ``None``.
    """
    from aiohttp import web

    from kailash.trust.auth.jwt import (
        AuthenticatedUser,
        ExpiredTokenError,
        InvalidTokenError,
        JWTValidator,
    )

    if config is None:
        raise ValueError(
            "build_jwt_auth_middleware requires a JWTConfig. Passing None "
            "would install a middleware with no credential to verify against, "
            "which authenticates nothing while appearing to (#2072)."
        )

    validator = JWTValidator(config)

    async def _api_key_ok(api_key: str):
        """Return the validator's result, or False on any failure.

        Fails CLOSED in every branch: a missing validator, a raising
        validator, and a falsy result all deny. ``api_key_enabled`` without a
        validator cannot authenticate anyone, and is denied with 401 rather
        than 500 -- the caller IS still unauthenticated, and a 500 would
        advertise a server misconfiguration to an anonymous prober. The
        operator gets the detail from the log.
        """
        key_validator = config.api_key_validator
        if key_validator is None:
            logger.error("aiohttp_jwt_auth.api_key_enabled_without_validator")
            return False
        try:
            result = key_validator(api_key)
            if inspect.isawaitable(result):
                result = await result
        except Exception:
            # Not a swallow: logged with a stack trace and still failing
            # CLOSED. An unexpected validator error must never fall through
            # into the protected handler.
            logger.exception("aiohttp_jwt_auth.api_key_validator_failed")
            return False
        return result

    @web.middleware
    async def jwt_auth_middleware(request, handler):
        """Authenticate the request or return 401.

        Covers the WebSocket handshake too, without a second middleware: an
        aiohttp websocket upgrade is performed by an ordinary request handler,
        so the handshake reaches this middleware as a normal HTTP request and
        is refused before the handler can call ``prepare()``. This is the one
        place aiohttp is structurally simpler than ASGI, where
        ``BaseHTTPMiddleware`` returns early for a non-"http" scope and forces
        a separate websocket layer (see #2100).
        """
        path = request.path

        # CORS preflight is exempt, and has to be. MEASURED on aiohttp 3.13.3:
        # `aiohttp_cors` answers a preflight from a ROUTE handler, and that
        # request still traverses the whole middleware chain --
        #
        #     preflight OPTIONS -> ['m1-in', 'm2-in', 'm2-out', 'm1-out']
        #
        # -- so without this branch auth 401s the preflight before CORS can
        # answer, and every cross-origin browser client breaks. This is the
        # aiohttp form of the ordering constraint the ASGI installer states as
        # "MUST be called BEFORE CORSMiddleware" (#2054).
        #
        # The exemption is decided by the RESOLVED HANDLER, never by the
        # request's own headers -- see `_is_cors_preflight`, which documents
        # the header-gated version this replaced and why it was unsafe to
        # export. Exempting the real preflight handler is safe: it reads no
        # application state, its response carries only CORS policy headers,
        # and the ACTUAL request that follows is a separate trip through this
        # middleware with no exemption. The test asserting the real
        # cross-origin GET is still 401'd is what stops this branch from being
        # widened into a hole.
        if request.method == "OPTIONS" and _is_cors_preflight(request):
            return await handler(request)

        if validator.is_path_exempt(path):
            return await handler(request)

        token = _extract_token(request, config)
        if not token:
            return _unauthorized("missing_token")

        if token.startswith("__apikey__") and config.api_key_enabled:
            result = await _api_key_ok(token[len("__apikey__") :])
            if not result:
                return _unauthorized("invalid_api_key")
            if isinstance(result, dict):
                request["user"] = validator.create_user_from_payload(result)
                request["token_payload"] = result
            else:
                request["user"] = AuthenticatedUser(user_id="apikey", roles=["api"])
                request["token_payload"] = {"type": "api_key"}
            return await handler(request)

        try:
            payload = validator.verify_token(token)
            if validator.check_token_age(payload):
                # `check_token_age` derives its error from CONFIGURATION, never
                # from the token, so nothing attacker-controlled is at stake --
                # but the caller still learns only "invalid_token".
                logger.warning(
                    "aiohttp_jwt_auth.token_age_rejected", extra={"path": path}
                )
                return _unauthorized("invalid_token")
            user = validator.create_user_from_payload(payload)
        except ExpiredTokenError:
            return _unauthorized("token_expired")
        except InvalidTokenError as exc:
            # The exception text is logged, never returned: it can name the
            # configured algorithm and issuer, which fingerprints the server
            # for an unauthenticated caller.
            logger.warning(
                "aiohttp_jwt_auth.invalid_token",
                extra={"path": path, "reason": str(exc)},
            )
            return _unauthorized("invalid_token")
        except Exception:
            # Not `except: pass` -- logged with a stack trace and still failing
            # CLOSED with 401.
            logger.exception(
                "aiohttp_jwt_auth.verification_failed", extra={"path": path}
            )
            return _unauthorized("auth_error")

        # aiohttp's request is a MutableMapping; this is the idiomatic place a
        # handler reads who connected, and mirrors `request.state.user` on the
        # ASGI side.
        request["user"] = user
        request["token_payload"] = payload

        if config.on_token_validated:
            try:
                result = config.on_token_validated(payload)
                if inspect.isawaitable(result):
                    await result
            except Exception:
                # An audit/stale-detection hook is advisory: logged with a
                # stack trace, never allowed to convert a valid token into a
                # 500, and never allowed to pass silently.
                logger.exception("aiohttp_jwt_auth.on_token_validated_failed")

        return await handler(request)

    logger.info(
        "aiohttp_jwt_auth.installed",
        extra={"exempt_paths": len(config.exempt_paths)},
    )
    return jwt_auth_middleware


def install_aiohttp_auth_middleware(app: Any, config: "JWTConfig") -> None:
    """Install the authentication middleware onto an ``aiohttp`` application.

    The aiohttp counterpart of
    :func:`kailash.utils.server_auth.install_server_auth_middleware`.

    Args:
        app: The ``aiohttp.web.Application`` to protect.
        config: The resolved JWT configuration.

    Raises:
        RuntimeError: The application has already been frozen (started), so
            aiohttp will not accept another middleware and the auth layer
            would never run.

    Note:
        aiohttp applies middlewares OUTERMOST-FIRST in list order, which is the
        OPPOSITE of Starlette's prepending ``add_middleware``. Appending here
        therefore places auth INSIDE any middleware already registered -- which
        is what is wanted when CORS is registered first, for the same reason
        the ASGI installer must be called BEFORE ``CORSMiddleware``: a
        cross-origin preflight ``OPTIONS`` must be answered by CORS rather than
        401'd by auth.
    """
    if getattr(app, "frozen", False):
        # Swallowing this would hand back an app that reports auth as enabled
        # while serving every route unauthenticated -- the exact #2013 shape.
        raise RuntimeError(
            "Cannot install authentication: the aiohttp application is already "
            "frozen, so the middleware would never run. Install the gate "
            "before the application starts."
        )
    app.middlewares.append(build_jwt_auth_middleware(config))
    logger.info(
        "aiohttp_jwt_auth.middleware_installed",
        extra={"exempt_paths": len(config.exempt_paths)},
    )
