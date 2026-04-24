# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Nexus ↔ kailash-ml integration surface.

Per `specs/nexus-ml-integration.md` §§1.1, 4, 5, this module exposes:

1. ``MLDashboard(auth="nexus")`` — a validator adapter that reuses Nexus's
   JWT public-key registry so the dashboard HTTP/SSE/WebSocket surface
   authenticates against the same token store as the Nexus instance it
   runs alongside.
2. ``mount_ml_endpoints(nexus, serve_handle)`` — mounts REST + MCP + WebSocket
   routes for a kailash-ml ``ServeHandle`` behind Nexus. Ambient tenant/actor
   ContextVars (set by ``JWTMiddleware``) propagate into every ``predict()``
   call.
3. ``dashboard_embed(port)`` — iframe integration helper returning the HTML
   snippet a parent page uses to embed the dashboard behind Nexus auth.

kailash-ml is NOT a hard dependency. When a caller invokes a function that
requires a kailash-ml object (``MLDashboard``, ``ServeHandle``) Nexus imports
the ml package lazily; if the ``[ml]`` extra is absent the error names the
missing extra (per `rules/dependencies.md` § "Exception: Optional Extras with
Loud Failure").
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any, List, Optional, Tuple

from nexus.context import get_current_actor_id, get_current_tenant_id

logger = logging.getLogger(__name__)

__all__ = [
    "DashboardPrincipal",
    "MLDashboard",
    "mount_ml_endpoints",
    "dashboard_embed",
]


# ---------------------------------------------------------------------------
# Dashboard principal dataclass — frozen per spec §4.3.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DashboardPrincipal:
    """Immutable principal returned by ``MLDashboard`` auth validation.

    Frozen (``@dataclass(frozen=True)``) per PACT MUST Rule 1 discipline.
    The ``scopes`` field is a ``tuple`` — also immutable — so downstream
    code cannot mutate the authorisation decision after validation.
    """

    actor_id: str
    tenant_id: Optional[str]
    scopes: Tuple[str, ...]


# ---------------------------------------------------------------------------
# MLDashboard(auth="nexus") adapter — spec §4.
# ---------------------------------------------------------------------------


class MLDashboard:
    """Nexus-auth adapter for ``kailash_ml.dashboard.MLDashboard(auth="nexus")``.

    Instantiated via :meth:`from_nexus`. The dashboard calls
    :meth:`authenticate` with a bearer token; this adapter verifies it
    against Nexus's ``JWTValidator`` (which shares the server's issuer,
    audience, JWKS URL, and public-key registry) and returns a
    :class:`DashboardPrincipal`.

    Usage:

        dash_auth = MLDashboard.from_nexus(nexus)
        principal = await dash_auth.authenticate(bearer_token)

    The ``auth="nexus"`` string in ``kailash_ml.dashboard.MLDashboard`` is
    resolved by the ml package to call ``MLDashboard.from_nexus(nexus)``.
    See spec §4.1.
    """

    def __init__(
        self,
        *,
        issuer: Optional[str] = None,
        audience: Optional[Any] = None,
        jwks_url: Optional[str] = None,
        public_key: Optional[str] = None,
        secret: Optional[str] = None,
        algorithm: Optional[str] = None,
    ) -> None:
        from kailash.trust.auth.jwt import JWTConfig, JWTValidator

        kwargs: dict = {}
        if issuer is not None:
            kwargs["issuer"] = issuer
        if audience is not None:
            kwargs["audience"] = audience
        if jwks_url is not None:
            kwargs["jwks_url"] = jwks_url
        if public_key is not None:
            kwargs["public_key"] = public_key
        if secret is not None:
            kwargs["secret"] = secret
        if algorithm is not None:
            kwargs["algorithm"] = algorithm
        self._config = JWTConfig(**kwargs)
        self._validator = JWTValidator(self._config)
        logger.info(
            "ml_dashboard.auth.initialized",
            extra={"algorithm": self._config.algorithm, "issuer": issuer},
        )

    @classmethod
    def from_nexus(cls, nexus: Any) -> "MLDashboard":
        """Construct an ``MLDashboard`` auth adapter from a live Nexus instance.

        Reuses the Nexus instance's JWT config (issuer / audience / JWKS URL /
        public key) so the dashboard does NOT store key material independently
        — see spec §4.2 invariant.
        """
        cfg = cls._extract_jwt_config(nexus)
        return cls(**cfg)

    @staticmethod
    def _extract_jwt_config(nexus: Any) -> dict:
        """Extract JWT config fields from a Nexus instance's auth middleware.

        Traverses the Nexus ASGI middleware stack looking for a
        ``JWTMiddleware`` and returns its config dict. Raises
        ``RuntimeError`` when no JWT middleware is registered — dashboard
        auth requires a source of truth for the key material.
        """
        from nexus.auth.jwt import JWTMiddleware

        fastapi_app = getattr(nexus, "fastapi_app", None)
        if fastapi_app is None:
            raise RuntimeError(
                "MLDashboard.from_nexus: Nexus instance has no fastapi_app; "
                "start the server or pass an already-constructed app"
            )
        # Walk user_middleware stack to find JWTMiddleware config
        for mw in getattr(fastapi_app, "user_middleware", []):
            cls = getattr(mw, "cls", None)
            if cls is JWTMiddleware:
                options = (
                    getattr(mw, "kwargs", None) or getattr(mw, "options", {}) or {}
                )
                if "config" in options and options["config"] is not None:
                    cfg = options["config"]
                    return {
                        "issuer": cfg.issuer,
                        "audience": cfg.audience,
                        "jwks_url": cfg.jwks_url,
                        "public_key": cfg.public_key,
                        "secret": cfg.secret,
                        "algorithm": cfg.algorithm,
                    }
                return {
                    k: v
                    for k, v in options.items()
                    if k
                    in {
                        "issuer",
                        "audience",
                        "jwks_url",
                        "public_key",
                        "secret",
                        "algorithm",
                    }
                }
        raise RuntimeError(
            "MLDashboard.from_nexus: no JWTMiddleware found on the Nexus "
            "instance; add_middleware(JWTMiddleware, config=...) first"
        )

    async def authenticate(self, token: str) -> DashboardPrincipal:
        """Verify ``token`` and return the derived principal.

        Raises ``InvalidTokenError`` / ``ExpiredTokenError`` from
        ``kailash.trust.auth.exceptions`` on verification failure. The
        dashboard's HTTP/SSE/WebSocket layer is responsible for mapping
        these to the correct HTTP status (401) per
        `rules/nexus-http-status-convention.md`.
        """
        payload = self._validator.verify_token(token)
        scopes_raw = payload.get("scopes", [])
        if isinstance(scopes_raw, str):
            scopes = (scopes_raw,)
        else:
            scopes = tuple(scopes_raw)
        return DashboardPrincipal(
            actor_id=payload["sub"],
            tenant_id=payload.get("tenant_id"),
            scopes=scopes,
        )


# ---------------------------------------------------------------------------
# mount_ml_endpoints — spec §5 + §1.1 item 4 (tenant propagation).
# ---------------------------------------------------------------------------


def _require_ml_extra(symbol: str) -> Any:
    """Import a kailash-ml symbol, raising a descriptive error when absent."""
    try:
        import kailash_ml  # noqa: F401
    except ImportError as exc:  # pragma: no cover — exercised only when extra absent
        raise ImportError(
            "kailash-nexus ml-bridge requires the [ml] extra: "
            "pip install kailash-nexus[ml] (or pip install kailash-ml)"
        ) from exc
    return symbol


def mount_ml_endpoints(nexus: Any, serve_handle: Any, *, prefix: str = "/ml") -> None:
    """Mount REST + MCP + WebSocket routes for a kailash-ml ``ServeHandle``.

    Every registered endpoint propagates the ambient tenant/actor into the
    predictor's ``predict()`` call via
    :func:`nexus.context.get_current_tenant_id` and
    :func:`nexus.context.get_current_actor_id`. The JWT middleware owns the
    ContextVar setup; this mount function reads the values at the handler
    boundary so a ``ServeHandle`` implementation that does not import nexus
    still sees the propagated tenant.

    Args:
        nexus: a :class:`nexus.Nexus` instance (or test TestClient host).
        serve_handle: a ``kailash_ml.ServeHandle`` or any object exposing
            ``predict(inputs, *, tenant_id, actor_id) -> dict`` and an
            optional ``describe() -> dict`` metadata method.
        prefix: URL prefix for the mounted routes (default ``"/ml"``).

    Routes registered:
        - ``POST {prefix}/predict`` — REST prediction endpoint.
        - ``GET  {prefix}/describe`` — model metadata (signature, version).
        - ``GET  {prefix}/healthz`` — liveness probe.
        - ``POST {prefix}/mcp/predict`` — MCP-compatible prediction endpoint.
        - WebSocket ``{prefix}/ws`` — streaming predictions.

    Raises:
        RuntimeError: if the Nexus HTTP transport is not initialised.
    """
    _require_ml_extra("mount_ml_endpoints")

    rest_path = f"{prefix}/predict"
    describe_path = f"{prefix}/describe"
    health_path = f"{prefix}/healthz"
    mcp_path = f"{prefix}/mcp/predict"
    ws_path = f"{prefix}/ws"

    async def _predict_handler(request_body: dict) -> dict:
        """REST predict handler; propagates tenant/actor into the predictor."""
        tenant_id = get_current_tenant_id()
        actor_id = get_current_actor_id()
        t0 = time.monotonic()
        logger.info(
            "nexus.ml.predict.start",
            extra={
                "path": rest_path,
                "tenant_id": tenant_id,
                "actor_id": actor_id,
            },
        )
        try:
            result = await _invoke_predict(
                serve_handle, request_body, tenant_id=tenant_id, actor_id=actor_id
            )
            logger.info(
                "nexus.ml.predict.ok",
                extra={
                    "path": rest_path,
                    "latency_ms": (time.monotonic() - t0) * 1000,
                },
            )
            return result
        except Exception:
            logger.exception(
                "nexus.ml.predict.error",
                extra={"path": rest_path},
            )
            raise

    async def _describe_handler() -> dict:
        describe = getattr(serve_handle, "describe", None)
        if describe is None:
            return {"prefix": prefix}
        if callable(describe):
            val = describe()
            if hasattr(val, "__await__"):
                val = await val
            return val
        return {"prefix": prefix}

    async def _health_handler() -> dict:
        return {"status": "ok", "prefix": prefix}

    async def _mcp_predict_handler(request_body: dict) -> dict:
        """MCP-style predict handler. MCP wraps inputs in a tool-call envelope
        ``{"tool": "predict", "arguments": {...}}``; unwrap to the raw inputs
        before forwarding to the predictor."""
        inputs = request_body.get("arguments", request_body)
        tenant_id = get_current_tenant_id()
        actor_id = get_current_actor_id()
        logger.info(
            "nexus.ml.mcp.predict.start",
            extra={"path": mcp_path, "tenant_id": tenant_id, "actor_id": actor_id},
        )
        result = await _invoke_predict(
            serve_handle, inputs, tenant_id=tenant_id, actor_id=actor_id
        )
        return {"tool": "predict", "result": result}

    nexus.register_endpoint(rest_path, ["POST"], _predict_handler)
    nexus.register_endpoint(describe_path, ["GET"], _describe_handler)
    nexus.register_endpoint(health_path, ["GET"], _health_handler)
    nexus.register_endpoint(mcp_path, ["POST"], _mcp_predict_handler)

    # WebSocket streaming prediction — optional, registers only when the
    # underlying Nexus supports `register_websocket`. The class-based handler
    # pattern per `skills/03-nexus/nexus-multi-channel.md`.
    if hasattr(nexus, "register_websocket"):
        _register_ml_websocket(nexus, ws_path, serve_handle)

    logger.info(
        "nexus.ml.endpoints.mounted",
        extra={
            "prefix": prefix,
            "rest": rest_path,
            "mcp": mcp_path,
            "ws": ws_path,
        },
    )


async def _invoke_predict(
    serve_handle: Any,
    inputs: Any,
    *,
    tenant_id: Optional[str],
    actor_id: Optional[str],
) -> Any:
    """Call ``serve_handle.predict`` propagating tenant/actor when supported.

    If the predictor's signature accepts ``tenant_id`` / ``actor_id`` kwargs,
    pass them. Otherwise call with just the inputs — the predictor may still
    read ``get_current_tenant_id()`` itself via the compat layer.
    """
    predict = getattr(serve_handle, "predict", None)
    if predict is None:
        raise RuntimeError(
            "serve_handle does not expose .predict(); cannot mount ml endpoints"
        )
    import inspect as _inspect

    sig = _inspect.signature(predict)
    kwargs: dict = {}
    if "tenant_id" in sig.parameters:
        kwargs["tenant_id"] = tenant_id
    if "actor_id" in sig.parameters:
        kwargs["actor_id"] = actor_id
    result = predict(inputs, **kwargs)
    if hasattr(result, "__await__"):
        result = await result
    return result


def _register_ml_websocket(nexus: Any, path: str, serve_handle: Any) -> None:
    """Register a class-based WebSocket handler that streams predictions.

    Each inbound message is a JSON dict of inputs; the handler invokes
    ``predict()`` with ambient tenant/actor ContextVars and sends back a
    ``{"result": ...}`` JSON response. Errors send ``{"error": "..."}``
    without leaking exception details (per
    `rules/security.md` § generic error messages).
    """
    from nexus.websocket_handlers import Connection, MessageHandler

    class _MLPredictStream(MessageHandler):  # type: ignore[misc]
        async def on_message(self, conn: Connection, msg: dict) -> None:  # type: ignore[override]
            tenant_id = get_current_tenant_id()
            actor_id = get_current_actor_id()
            try:
                result = await _invoke_predict(
                    serve_handle,
                    msg,
                    tenant_id=tenant_id,
                    actor_id=actor_id,
                )
                await conn.send_json({"result": result})
            except Exception:
                logger.exception(
                    "nexus.ml.ws.predict.error",
                    extra={"path": path, "tenant_id": tenant_id},
                )
                await conn.send_json({"error": "prediction failed"})

    nexus.register_websocket(path, _MLPredictStream)


# ---------------------------------------------------------------------------
# dashboard_embed — spec §1.1 "iframe integration helper"
# ---------------------------------------------------------------------------


def dashboard_embed(
    port: int,
    *,
    host: str = "localhost",
    width: str = "100%",
    height: str = "800px",
    title: str = "Kailash ML Dashboard",
) -> str:
    """Return an HTML iframe snippet that embeds ``kailash-ml-dashboard``.

    The dashboard runs on ``host:port`` (started via
    ``kailash_ml.km.dashboard()``); this helper returns the snippet a parent
    HTML page uses to embed it. The iframe's ``src`` assumes the dashboard
    shares the Nexus server's auth cookie / bearer context — pair this with
    ``MLDashboard(auth="nexus")`` on the dashboard side (spec §4).

    Args:
        port: port the dashboard is listening on.
        host: hostname (default ``"localhost"``).
        width: iframe width (CSS units, default ``"100%"``).
        height: iframe height (CSS units, default ``"800px"``).
        title: accessibility title for the iframe.

    Returns:
        HTML snippet as a string.
    """
    if not isinstance(port, int) or port <= 0 or port > 65535:
        raise ValueError(f"port must be an integer in 1..65535 (got {port!r})")
    src = f"http://{host}:{port}/"
    # Allow same-origin + fullscreen for interactive plots; no external scripts.
    return (
        f'<iframe src="{src}" '
        f'title="{title}" '
        f'width="{width}" height="{height}" '
        f'sandbox="allow-same-origin allow-scripts allow-forms allow-popups" '
        f'style="border: none;"></iframe>'
    )
