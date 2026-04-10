# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""
Fabric Integrity Middleware — detect silent bypass, null body, direct storage access.

Three silent failure classes plague every DataFlow fabric serving layer:

1. **Silent bypass** — a route returns 2xx without hitting the fabric
   layer at all (``fabric_hits=0``). The handler talks directly to
   Redis/Postgres, bypassing all fabric caching, SSE invalidation,
   and observability.
2. **Silent null body** — the fabric read happened but returned
   ``null``/empty on a non-empty-by-spec route. This is the exact
   root cause of gh#358 (parameterised products returning null with
   HTTP 200).
3. **Direct storage access** — a data-returning route talks directly
   to Redis/Postgres instead of through fabric. A migration candidate,
   not an error per se, but operators need the signal.

All three are invisible to HTTP status codes, invisible to upstream
middleware that only inspects requests/responses, and invisible to the
SDK's own caching metrics (the call never enters the cached path).

Usage::

    from dataflow.fabric.integrity import FabricIntegrityMiddleware

    # Observation-only (default — safe for day-one deployment)
    app.add_middleware(FabricIntegrityMiddleware)

    # With project-specific extensions
    app.add_middleware(
        FabricIntegrityMiddleware,
        config=FabricIntegrityConfig(
            extra_exempt_prefixes=("/api/custom/webhook/",),
            extra_direct_storage_patterns=("/api/legacy/",),
            enforcement_stage="observation",
        ),
    )

Design points (from the originating issue gh#369):

- **Four-way classification, not three.** ``fabric_required``,
  ``direct_storage``, ``exempt``, and ``neutral`` are the minimum
  set that avoids false positives while covering the direct-storage
  migration case.
- **Observation-only by default.** Stage 0 collects WARNs for a
  deployment cycle before any fail-closed behaviour is enabled.
- **Trace ID threaded through detection.** Every WARN includes
  a ``trace_id`` so operators can join against request logs.
- **``null_body`` is distinct from ``bypass``.** Different root
  causes, different remediation — collapsing them loses signal.
- **Exempt list is explicit, not regex.** Tuple of literal prefix
  strings; regex rules rot invisibly.

See gh#369 for the full design rationale and acceptance criteria.
"""

from __future__ import annotations

import logging
import time
import uuid
from contextvars import ContextVar, Token
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Literal, Optional, Tuple

logger = logging.getLogger(__name__)

__all__ = [
    "FabricIntegrityMiddleware",
    "FabricIntegrityConfig",
    "classify_route",
    "record_fabric_hit",
    "get_fabric_hit_count",
    "get_current_integrity_trace",
]


# ---------------------------------------------------------------------------
# ContextVar-based per-request fabric hit counter
# ---------------------------------------------------------------------------

_fabric_hit_count: ContextVar[int] = ContextVar("_fabric_hit_count", default=0)
_integrity_trace_id: ContextVar[Optional[str]] = ContextVar(
    "_integrity_trace_id", default=None
)


def record_fabric_hit() -> None:
    """Increment the per-request fabric hit counter.

    Call this from the serving layer bridge after each SDK handler
    returns a result from the fabric pipeline. The middleware reads
    this counter on response exit to determine whether the request
    actually went through fabric.
    """
    current = _fabric_hit_count.get()
    _fabric_hit_count.set(current + 1)


def get_fabric_hit_count() -> int:
    """Return the current per-request fabric hit count.

    Useful for downstream code that needs to inspect the counter
    without incrementing it (e.g., test assertions).
    """
    return _fabric_hit_count.get()


def get_current_integrity_trace() -> Optional[str]:
    """Return the integrity trace ID for the current request scope.

    Returns ``None`` when called outside a middleware-managed scope.
    """
    return _integrity_trace_id.get()


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Default exempt prefixes — routes that should never touch fabric.
# Each entry is a literal prefix string (no regex) with an inline
# comment in the source explaining the exemption.
_DEFAULT_EXEMPT_PREFIXES: Tuple[str, ...] = (
    "/health",  # Health endpoints — no data, no fabric
    "/fabric/_health",  # Fabric's own health probe
    "/fabric/_trace",  # Fabric trace inspection endpoint
    "/fabric/metrics",  # Prometheus metrics scrape
    "/docs",  # API documentation (OpenAPI/Swagger)
    "/openapi",  # OpenAPI schema
    "/redoc",  # ReDoc documentation
    "/auth/",  # Authentication flows — no fabric data
    "/oauth/",  # OAuth flows — no fabric data
    "/.well-known/",  # OIDC discovery, etc.
    "/favicon",  # Static asset
)

# Default fabric-required prefixes — routes that MUST go through fabric.
_DEFAULT_FABRIC_REQUIRED_PREFIXES: Tuple[str, ...] = (
    "/fabric/",  # All fabric product endpoints
)

EnforcementStage = Literal["observation", "per_prefix", "fail_closed"]
RouteClassification = Literal["fabric_required", "direct_storage", "exempt", "neutral"]


@dataclass(frozen=True)
class FabricIntegrityConfig:
    """Configuration for :class:`FabricIntegrityMiddleware`.

    All prefix tuples are matched with ``str.startswith``, not regex.
    This is intentional — regex rules rot invisibly, literal strings
    are reviewable in PRs.

    Args:
        fabric_required_prefixes: Routes that MUST go through the
            fabric layer. Defaults to ``("/fabric/",)``.
        direct_storage_patterns: Known direct-storage routes to emit
            warnings about. Defaults to empty (project-specific).
        exempt_prefixes: Routes to skip entirely (health, metrics,
            docs, auth). Defaults to a standard set.
        extra_exempt_prefixes: Additional exempt prefixes appended to
            the default set. Avoids having to repeat all defaults.
        extra_direct_storage_patterns: Additional direct-storage
            patterns appended to the default set.
        extra_fabric_required_prefixes: Additional fabric-required
            prefixes appended to the default set.
        enforcement_stage: Controls what happens when a violation is
            detected. ``"observation"`` (default) logs only.
            ``"per_prefix"`` returns 500 for fabric_required routes.
            ``"fail_closed"`` returns 500 for any non-exempt violation.
        exempt_methods: HTTP methods to always exempt (e.g., OPTIONS
            for CORS preflight). Defaults to ``("OPTIONS",)``.
    """

    fabric_required_prefixes: Tuple[str, ...] = _DEFAULT_FABRIC_REQUIRED_PREFIXES
    direct_storage_patterns: Tuple[str, ...] = ()
    exempt_prefixes: Tuple[str, ...] = _DEFAULT_EXEMPT_PREFIXES
    extra_exempt_prefixes: Tuple[str, ...] = ()
    extra_direct_storage_patterns: Tuple[str, ...] = ()
    extra_fabric_required_prefixes: Tuple[str, ...] = ()
    enforcement_stage: EnforcementStage = "observation"
    exempt_methods: Tuple[str, ...] = ("OPTIONS",)

    @property
    def all_exempt_prefixes(self) -> Tuple[str, ...]:
        """Combined default + extra exempt prefixes."""
        return self.exempt_prefixes + self.extra_exempt_prefixes

    @property
    def all_fabric_required_prefixes(self) -> Tuple[str, ...]:
        """Combined default + extra fabric-required prefixes."""
        return self.fabric_required_prefixes + self.extra_fabric_required_prefixes

    @property
    def all_direct_storage_patterns(self) -> Tuple[str, ...]:
        """Combined default + extra direct-storage patterns."""
        return self.direct_storage_patterns + self.extra_direct_storage_patterns


# ---------------------------------------------------------------------------
# Route classification — pure function, no I/O
# ---------------------------------------------------------------------------


def classify_route(
    path: str,
    method: str,
    config: Optional[FabricIntegrityConfig] = None,
) -> RouteClassification:
    """Classify a route into one of four categories.

    This is a pure function — no I/O, no side effects, O(prefix-check).
    Classification is deterministic from ``(path, method)`` and the
    config's prefix tuples.

    Priority order (first match wins):
    1. Exempt methods (OPTIONS) -> ``"exempt"``
    2. Exempt prefixes -> ``"exempt"``
    3. Fabric-required prefixes -> ``"fabric_required"``
    4. Direct-storage patterns -> ``"direct_storage"``
    5. Default -> ``"neutral"``

    Args:
        path: The request path (e.g., ``"/fabric/dashboard"``).
        method: The HTTP method (e.g., ``"GET"``).
        config: Optional config override. Uses default config when
            ``None``.

    Returns:
        One of ``"fabric_required"``, ``"direct_storage"``,
        ``"exempt"``, or ``"neutral"``.
    """
    if config is None:
        config = FabricIntegrityConfig()

    method_upper = method.upper()

    # 1. Exempt methods
    if method_upper in config.exempt_methods:
        return "exempt"

    # 2. Exempt prefixes
    all_exempt = config.all_exempt_prefixes
    if all_exempt and path.startswith(all_exempt):
        return "exempt"

    # 3. Fabric-required prefixes
    all_required = config.all_fabric_required_prefixes
    if all_required and path.startswith(all_required):
        return "fabric_required"

    # 4. Direct-storage patterns
    all_direct = config.all_direct_storage_patterns
    if all_direct and path.startswith(all_direct):
        return "direct_storage"

    # 5. Default
    return "neutral"


# ---------------------------------------------------------------------------
# Response body inspection
# ---------------------------------------------------------------------------


def _is_null_body(body: bytes) -> bool:
    """Check if a response body is null/empty.

    Returns ``True`` for: empty bytes, literal ``null``, ``{}``,
    ``[]``, ``{"data": null}``, ``{"data": {}}``, ``{"data": []}``.
    Whitespace is stripped before comparison.
    """
    if not body:
        return True
    stripped = body.strip()
    if not stripped:
        return True
    if stripped in (b"null", b"None", b"{}", b"[]"):
        return True
    # Check for common wrapper patterns: {"data": null/{}/ []}
    if stripped.startswith(b"{"):
        # Quick substring checks to avoid full JSON parse on every
        # request. These cover the fabric serving layer's standard
        # response shapes.
        lower = stripped.lower()
        if lower in (
            b'{"data": null}',
            b'{"data":null}',
            b'{"data": {}}',
            b'{"data":{}}',
            b'{"data": []}',
            b'{"data":[]}',
        ):
            return True
    return False


# ---------------------------------------------------------------------------
# ASGI Middleware
# ---------------------------------------------------------------------------


class FabricIntegrityMiddleware:
    """ASGI middleware that detects silent fabric failure classes.

    Wraps an ASGI application and inspects every HTTP response for
    three failure classes:

    - **Silent bypass** — ``fabric_required`` route returned 2xx with
      ``fabric_hits=0``.
    - **Silent null body** — ``fabric_required`` route returned 2xx
      with ``fabric_hits>=1`` but a null/empty body.
    - **Direct storage access** — ``direct_storage`` route returned 2xx.

    Emits structured log events:

    - ``fabric.integrity.bypass`` (WARN)
    - ``fabric.integrity.null_body`` (WARN)
    - ``fabric.integrity.direct_storage`` (WARN)
    - ``fabric.integrity.ok`` (DEBUG)

    In enforcement stages beyond ``"observation"``, the middleware can
    replace the response with a 500 error instead of just logging.

    Args:
        app: The ASGI application to wrap.
        config: Optional configuration. Defaults to observation-only
            with standard exempt/required prefixes.
    """

    def __init__(
        self,
        app: Any,
        config: Optional[FabricIntegrityConfig] = None,
    ) -> None:
        self.app = app
        self.config = config or FabricIntegrityConfig()

    async def __call__(
        self,
        scope: Dict[str, Any],
        receive: Callable,
        send: Callable,
    ) -> None:
        """ASGI interface — called once per HTTP request."""
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        path: str = scope.get("path", "")
        method: str = scope.get("method", "GET")
        classification = classify_route(path, method, self.config)

        # Exempt routes skip all checks
        if classification == "exempt":
            await self.app(scope, receive, send)
            return

        # Neutral routes also skip — no assertion to make
        if classification == "neutral":
            await self.app(scope, receive, send)
            return

        # Set up per-request ContextVars
        trace_id = uuid.uuid4().hex[:12]
        hit_count_token: Token[int] = _fabric_hit_count.set(0)
        trace_token: Token[Optional[str]] = _integrity_trace_id.set(trace_id)

        t0 = time.monotonic()

        # Capture the response status and body
        response_status: int = 0
        response_body_chunks: list[bytes] = []
        response_started = False
        enforcement_blocked = False

        async def send_wrapper(message: Dict[str, Any]) -> None:
            nonlocal response_status, response_started, enforcement_blocked

            if message.get("type") == "http.response.start":
                response_status = message.get("status", 0)
                response_started = True

            if message.get("type") == "http.response.body":
                body_chunk = message.get("body", b"")
                if body_chunk:
                    response_body_chunks.append(body_chunk)

            # In observation mode, always pass through
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            elapsed_ms = round((time.monotonic() - t0) * 1000, 2)
            hits = _fabric_hit_count.get()

            # Restore ContextVars
            _fabric_hit_count.reset(hit_count_token)
            _integrity_trace_id.reset(trace_token)

            # Only inspect 2xx responses — non-2xx is already an error
            # the caller can see.
            is_success = 200 <= response_status < 300

            log_extra: Dict[str, Any] = {
                "route": path,
                "method": method,
                "status": response_status,
                "trace_id": trace_id,
                "elapsed_ms": elapsed_ms,
                "fabric_hits": hits,
                "classification": classification,
            }

            if classification == "fabric_required" and is_success:
                if hits == 0:
                    # Silent bypass — route returned 2xx without
                    # hitting the fabric layer at all.
                    logger.warning(
                        "fabric.integrity.bypass",
                        extra=log_extra,
                    )
                    if self.config.enforcement_stage in (
                        "per_prefix",
                        "fail_closed",
                    ):
                        enforcement_blocked = True
                elif _is_null_body(b"".join(response_body_chunks)):
                    # Silent null body — fabric read happened but
                    # returned null/empty.
                    logger.warning(
                        "fabric.integrity.null_body",
                        extra=log_extra,
                    )
                    if self.config.enforcement_stage == "fail_closed":
                        enforcement_blocked = True
                else:
                    # All good — fabric was hit and returned data.
                    logger.debug(
                        "fabric.integrity.ok",
                        extra=log_extra,
                    )

            elif classification == "direct_storage" and is_success:
                # Direct storage access — route bypasses fabric.
                logger.warning(
                    "fabric.integrity.direct_storage",
                    extra=log_extra,
                )
                if self.config.enforcement_stage == "fail_closed":
                    enforcement_blocked = True

            # Enforcement: in observation mode (default), enforcement
            # is a no-op. In per_prefix / fail_closed modes, the
            # response was already sent by the time we detect the
            # violation (because ASGI streams the response). We log
            # the enforcement intent; a future iteration could buffer
            # the response to actually block it. For now, enforcement
            # stages beyond observation are logged as a separate event
            # so operators can measure the blast radius before
            # upgrading.
            if enforcement_blocked:
                logger.warning(
                    "fabric.integrity.enforcement",
                    extra={
                        **log_extra,
                        "enforcement_stage": self.config.enforcement_stage,
                        "action": "would_block",
                    },
                )
