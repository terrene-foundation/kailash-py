# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""PACT governance middleware for Nexus — authorization enforcement at the request boundary.

``PACTMiddleware`` is the missing Nexus→PACT integration identified in the
SPEC-06 audit. It delegates every non-exempt request to
``kailash.trust.pact.GovernanceEngine.verify_action()`` and fails closed on
any error.

The middleware sits BETWEEN Nexus authentication (which establishes identity:
user_id, tenant_id, role_address on ``scope["state"]``) and the business
handlers. Nexus owns authN, PACT owns authZ — see ``rules/framework-first.md``.

Pipeline position (LIFO ASGI add order → outermost-to-innermost):

    client -> [security headers] -> [CSRF] -> [auth] -> [PACTMiddleware] -> handler

So PACTMiddleware MUST be added AFTER any authentication middleware in the
add_middleware() call sequence, because Nexus applies add_middleware in LIFO
order (last added = runs first on request). In practice the NexusEngine
builder pins the ordering via ``.governance(engine)`` in the build step.

Usage::

    from kailash.trust.pact.engine import GovernanceEngine
    from nexus import Nexus
    from nexus.middleware.governance import PACTMiddleware

    engine = GovernanceEngine(my_compiled_org, ...)

    app = Nexus()
    app.add_middleware(PACTMiddleware, governance_engine=engine)

Or via the NexusEngine builder::

    from nexus import NexusEngine
    engine = (
        NexusEngine.builder()
        .governance(my_governance_engine)
        .build()
    )

Envelope resolution is **structural** — the request's role_address is taken
from ``scope["state"]["pact_role_address"]`` (populated by the auth chain)
or from the ``X-PACT-Role-Address`` header. Path-to-action mapping uses the
HTTP method + first path segment only. No keyword/regex matching on the
request body, no content analysis. See ``rules/agent-reasoning.md`` for the
no-semantic-routing rule that motivates this constraint.

On deny, a structured JSON 403 is returned and a structured WARN log is
emitted with correlation_id, role_address, action, and the governance
verdict level + reason. On allow, the request proceeds to the next middleware
and an INFO log records the allow decision + latency.

Fail-closed: any exception inside the middleware is caught and converted
into a 403 BLOCKED response. Missing ``governance_engine`` at construction
time raises ``TypeError`` at import time — there is no silent no-op fallback.
"""

from __future__ import annotations

import json
import logging
import math
import time
import uuid
from typing import Any, Dict, Iterable, Optional

logger = logging.getLogger(__name__)

__all__ = [
    "PACTMiddleware",
    "PACTGovernanceError",
]


class PACTGovernanceError(Exception):
    """Raised when PACTMiddleware cannot be constructed or configured safely.

    Construction-time errors (missing governance engine, invalid exempt
    paths, etc.). Runtime denials do NOT raise this — they return a 403
    JSON response so the ASGI pipeline completes cleanly.
    """


# Exempt paths: health/metrics/docs endpoints bypass governance entirely.
# These MUST be structural (exact path match), not a regex / prefix pattern,
# so that a bug in the pattern cannot accidentally exempt a sensitive route.
_DEFAULT_EXEMPT_PATHS = frozenset(
    {
        "/health",
        "/healthz",
        "/ready",
        "/readyz",
        "/live",
        "/livez",
        "/metrics",
        "/docs",
        "/redoc",
        "/openapi.json",
    }
)

# Role-address header fallback for when the auth middleware hasn't populated
# scope["state"]. Used only as a secondary source.
_ROLE_ADDRESS_HEADER = b"x-pact-role-address"

# Correlation header for request tracing.
_CORRELATION_HEADER = b"x-request-id"


def _decode_header(
    headers: Iterable[tuple[bytes, bytes]], name: bytes
) -> Optional[str]:
    """Extract a single header value as a string, or None if absent.

    Args:
        headers: ASGI headers list (list of (bytes, bytes) tuples).
        name: Lowercase header name (bytes).

    Returns:
        The decoded header value, or None if the header is missing.
    """
    lower = name.lower()
    for k, v in headers:
        if k.lower() == lower:
            try:
                return v.decode("latin-1", errors="replace")
            except Exception:
                return None
    return None


def _derive_action(method: str, path: str) -> str:
    """Derive a structural action identifier from method + first path segment.

    This is purely structural: no keyword/regex matching on request content.
    ``POST /api/workflows/deploy`` -> ``"post:api"``. The GovernanceEngine
    uses the role's operating envelope to decide whether ``post:api`` is an
    allowed action, so the action label just needs to be deterministic.

    Args:
        method: HTTP method (already uppercased).
        path: URL path from scope.

    Returns:
        A deterministic ``"<method>:<first_segment>"`` string.
    """
    segments = [s for s in path.split("/") if s]
    first = segments[0] if segments else ""
    # Normalize method for consistency with the envelope's allowed_actions.
    return f"{method.lower()}:{first}" if first else method.lower()


class PACTMiddleware:
    """ASGI middleware that enforces PACT governance at the request boundary.

    For every non-exempt request:

    1. Generate or propagate a ``request_id`` correlation token.
    2. Extract the role_address from ``scope["state"]`` or the
       ``X-PACT-Role-Address`` header.
    3. Derive a structural action identifier from method + first path segment.
    4. Call ``GovernanceEngine.verify_action(role_address, action, context)``.
    5. If ``verdict.allowed`` -> pass to next middleware.
    6. Otherwise -> return a 403 JSON response with the verdict reason.

    Fail-closed: any exception during resolution or verification returns 403.
    """

    def __init__(
        self,
        app: Any,
        *,
        governance_engine: Any,
        exempt_paths: Optional[Iterable[str]] = None,
        role_address_state_key: str = "pact_role_address",
        require_role_address: bool = True,
    ) -> None:
        """Initialize the middleware.

        Args:
            app: The ASGI application to wrap.
            governance_engine: A ``kailash.trust.pact.GovernanceEngine``
                instance. MUST NOT be None — there is no silent no-op mode.
            exempt_paths: Paths that bypass governance entirely (exact match).
                Defaults to the health/metrics/docs exact-match set.
            role_address_state_key: Attribute name to read from
                ``scope["state"]`` for the role_address. Defaults to
                ``"pact_role_address"``.
            require_role_address: If True (default), requests without a
                role_address are DENIED (fail-closed). If False, they pass
                through to the next middleware without governance. The
                non-strict mode is intended for bring-up / migration.

        Raises:
            PACTGovernanceError: If ``governance_engine`` is None.
        """
        if governance_engine is None:
            raise PACTGovernanceError(
                "PACTMiddleware requires a governance_engine. "
                "Pass a kailash.trust.pact.GovernanceEngine instance; "
                "there is no silent no-op fallback."
            )

        # Duck-type the engine contract — we only call .verify_action().
        if not callable(getattr(governance_engine, "verify_action", None)):
            raise PACTGovernanceError(
                "governance_engine must implement verify_action(role_address, "
                "action, context). Got %r." % (type(governance_engine).__name__,)
            )

        self.app = app
        self._engine = governance_engine
        self._exempt_paths = (
            frozenset(exempt_paths) if exempt_paths else _DEFAULT_EXEMPT_PATHS
        )
        self._state_key = role_address_state_key
        self._require_role_address = bool(require_role_address)

        logger.info(
            "pact_middleware.initialized",
            extra={
                "component": "nexus.middleware.governance",
                "exempt_path_count": len(self._exempt_paths),
                "require_role_address": self._require_role_address,
                "state_key": self._state_key,
            },
        )

    async def __call__(self, scope: Dict[str, Any], receive: Any, send: Any) -> None:
        """ASGI interface. Only http scopes are filtered; websocket/lifespan pass through.

        WebSocket and lifespan scopes pass through unmodified because the
        HTTP authentication chain does not run for them — governance for
        WebSocket channels is enforced at channel-handshake time inside
        the Nexus websocket layer (see SPEC-06 § 2, future work).
        """
        scope_type = scope.get("type", "")
        if scope_type != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")

        # Exempt paths bypass governance entirely.
        if path in self._exempt_paths:
            await self.app(scope, receive, send)
            return

        # Generate or propagate correlation id. Nexus's observability rule
        # (rules/observability.md) requires a correlation id on every log
        # line in a request scope — bind it to a logger adapter.
        headers = scope.get("headers", [])
        request_id = _decode_header(headers, _CORRELATION_HEADER) or uuid.uuid4().hex
        method = scope.get("method", "GET").upper()
        t0 = time.monotonic()

        log_base: Dict[str, Any] = {
            "request_id": request_id,
            "path": path,
            "method": method,
            "component": "nexus.middleware.governance",
        }

        logger.info("pact_middleware.request.start", extra=dict(log_base))

        # -------------------------------------------------------------
        # Extract role_address (structural, not semantic).
        # Priority: scope["state"][state_key] > header fallback.
        # -------------------------------------------------------------
        role_address: Optional[str] = None
        state_obj = scope.get("state")
        if isinstance(state_obj, dict):
            candidate = state_obj.get(self._state_key)
            if isinstance(candidate, str) and candidate:
                role_address = candidate
        if role_address is None:
            hdr = _decode_header(headers, _ROLE_ADDRESS_HEADER)
            if hdr:
                role_address = hdr

        if role_address is None:
            if self._require_role_address:
                # Fail-closed: no identity -> no action. Rule: pact-governance.md
                # MUST Rule 4 (Fail-Closed Decisions).
                logger.warning(
                    "pact_middleware.request.denied",
                    extra={
                        **log_base,
                        "reason": "missing_role_address",
                        "level": "blocked",
                        "latency_ms": (time.monotonic() - t0) * 1000.0,
                    },
                )
                await self._send_denied(
                    send,
                    status_code=403,
                    level="blocked",
                    reason="missing_role_address",
                    request_id=request_id,
                )
                return
            # Permissive migration mode: pass through without governance.
            logger.info(
                "pact_middleware.request.bypass_no_identity",
                extra={**log_base, "mode": "non_strict"},
            )
            await self.app(scope, receive, send)
            return

        action = _derive_action(method, path)

        logger.info(
            "pact_middleware.envelope.resolved",
            extra={
                **log_base,
                "role_address": role_address,
                "action": action,
            },
        )

        # -------------------------------------------------------------
        # Verify against the operating envelope.
        # Fail-closed on ANY exception — return 403.
        # -------------------------------------------------------------
        context: Dict[str, Any] = {}
        # Scope state may carry a pre-computed cost (e.g. from rate-limiting).
        # Validate with math.isfinite to defeat the NaN/Inf bypass rule
        # (rules/pact-governance.md Rule 6, rules/trust-plane-security.md Rule 3).
        if isinstance(state_obj, dict):
            raw_cost = state_obj.get("pact_cost_usd")
            if raw_cost is not None:
                try:
                    cost = float(raw_cost)
                    if math.isfinite(cost) and cost >= 0:
                        context["cost"] = cost
                except (TypeError, ValueError):
                    # Silently drop malformed cost — engine will evaluate
                    # without a cost context, which is the safe default.
                    logger.warning(
                        "pact_middleware.context.invalid_cost",
                        extra={**log_base, "raw_cost_type": type(raw_cost).__name__},
                    )

        try:
            verdict = self._engine.verify_action(
                role_address=role_address,
                action=action,
                context=context,
            )
        except Exception as exc:
            logger.exception(
                "pact_middleware.engine.error",
                extra={
                    **log_base,
                    "role_address": role_address,
                    "action": action,
                    "error": str(exc),
                    "latency_ms": (time.monotonic() - t0) * 1000.0,
                },
            )
            await self._send_denied(
                send,
                status_code=403,
                level="blocked",
                reason="internal_governance_error",
                request_id=request_id,
            )
            return

        level = getattr(verdict, "level", "blocked")
        allowed = bool(getattr(verdict, "allowed", False))
        reason = getattr(verdict, "reason", "no_reason")

        if not allowed:
            # BLOCKED or HELD both deny the request at the HTTP layer;
            # HELD maps to 429 (the request could proceed after approval).
            status = 429 if level == "held" else 403
            logger.warning(
                "pact_middleware.request.denied",
                extra={
                    **log_base,
                    "role_address": role_address,
                    "action": action,
                    "level": level,
                    "reason": reason,
                    "latency_ms": (time.monotonic() - t0) * 1000.0,
                },
            )
            await self._send_denied(
                send,
                status_code=status,
                level=level,
                reason=reason,
                request_id=request_id,
            )
            return

        # Record the allow decision (FLAGGED actions are allowed but logged
        # for review per PACT verification gradient).
        if level == "flagged":
            logger.warning(
                "pact_middleware.request.flagged",
                extra={
                    **log_base,
                    "role_address": role_address,
                    "action": action,
                    "reason": reason,
                },
            )
        else:
            logger.info(
                "pact_middleware.request.allowed",
                extra={
                    **log_base,
                    "role_address": role_address,
                    "action": action,
                    "level": level,
                },
            )

        # Pass to next middleware / handler.
        await self.app(scope, receive, send)

        logger.info(
            "pact_middleware.request.complete",
            extra={
                **log_base,
                "role_address": role_address,
                "action": action,
                "level": level,
                "latency_ms": (time.monotonic() - t0) * 1000.0,
            },
        )

    # --------------------------------------------------------------
    # Response helpers
    # --------------------------------------------------------------

    async def _send_denied(
        self,
        send: Any,
        *,
        status_code: int,
        level: str,
        reason: str,
        request_id: str,
    ) -> None:
        """Emit a structured JSON denial response.

        Args:
            send: ASGI send callable.
            status_code: HTTP status (403 for BLOCKED, 429 for HELD).
            level: Verdict level string for the JSON body.
            reason: Human-readable reason for the denial.
            request_id: Correlation id to echo in the response headers.
        """
        body = json.dumps(
            {
                "error": "governance_denied",
                "level": level,
                "reason": reason,
                "request_id": request_id,
            }
        ).encode("utf-8")
        await send(
            {
                "type": "http.response.start",
                "status": status_code,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode("ascii")),
                    (b"x-request-id", request_id.encode("ascii")),
                    (b"x-pact-verdict-level", level.encode("ascii")),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body, "more_body": False})
