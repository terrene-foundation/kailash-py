"""EATP Trust Verification Middleware for Kailash Nexus.

This module provides ASGI middleware for verifying EATP (Extensible Agent Trust Protocol)
trust context on incoming HTTP requests. It integrates with the EATPHeaderExtractor to
extract trust headers and optionally with TrustOperations to verify agent trust.

Modes of Operation:
    - disabled: No trust verification, all requests pass through
    - permissive: Trust verification performed but failures are logged, not blocked
    - enforcing: Trust verification required, failures result in 401/403 responses

Usage:
    from nexus.trust.middleware import TrustMiddleware, TrustMiddlewareConfig
    from starlette.applications import Starlette

    config = TrustMiddlewareConfig(
        mode="enforcing",
        exempt_paths=["/health", "/metrics"],
        require_human_origin=True,
    )

    app = Starlette(routes=routes)
    app.add_middleware(TrustMiddleware, config=config, trust_operations=trust_ops)
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, List, Optional, Protocol, runtime_checkable

from nexus.trust.headers import EATPHeaderExtractor, ExtractedEATPContext
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

logger = logging.getLogger(__name__)


@runtime_checkable
class TrustOperationsProtocol(Protocol):
    """Protocol for TrustOperations to avoid hard Kaizen dependency."""

    async def verify(
        self,
        agent_id: str,
        action: str,
        resource: Optional[str] = None,
        **kwargs: Any,
    ) -> Any:
        """Verify agent trust for an action."""
        ...


@dataclass
class TrustMiddlewareConfig:
    """Configuration for the TrustMiddleware.

    Attributes:
        enabled: Whether the middleware is active. If False, all requests pass through.
        mode: Operating mode - 'disabled', 'permissive', or 'enforcing'.
            - disabled: No verification, requests pass through
            - permissive: Verify but log failures, don't block
            - enforcing: Verify and block on failures (401/403)
        exempt_paths: List of URL paths that bypass trust verification entirely.
        require_human_origin: If True, requests must have human origin in EATP context.
        audit_all_requests: If True, audit all requests (future feature).
        reject_expired_sessions: If True, reject requests with expired session_id.
    """

    enabled: bool = True
    mode: str = "permissive"
    exempt_paths: List[str] = field(
        default_factory=lambda: [
            "/health",
            "/metrics",
            "/openapi.json",
            "/docs",
            "/redoc",
        ]
    )
    require_human_origin: bool = False
    audit_all_requests: bool = True
    reject_expired_sessions: bool = True


class TrustMiddleware(BaseHTTPMiddleware):
    """ASGI middleware for EATP trust verification.

    This middleware intercepts incoming HTTP requests and:
    1. Checks if the path is exempt from verification
    2. Extracts EATP headers using EATPHeaderExtractor
    3. Stores the extracted context in request.state.eatp_context
    4. Optionally verifies trust using TrustOperations
    5. Returns appropriate HTTP responses based on verification results

    The middleware can operate in three modes:
    - disabled: No verification, all requests pass through
    - permissive: Log verification failures but allow requests
    - enforcing: Block requests that fail verification

    Example:
        >>> from starlette.applications import Starlette
        >>> from nexus.trust.middleware import TrustMiddleware, TrustMiddlewareConfig
        >>>
        >>> config = TrustMiddlewareConfig(mode="enforcing")
        >>> app = Starlette(routes=routes)
        >>> app.add_middleware(TrustMiddleware, config=config)
    """

    def __init__(
        self,
        app: Any,
        trust_operations: Optional[TrustOperationsProtocol] = None,
        config: Optional[TrustMiddlewareConfig] = None,
        header_extractor: Optional[EATPHeaderExtractor] = None,
    ) -> None:
        """Initialize the TrustMiddleware.

        Args:
            app: The ASGI application to wrap.
            trust_operations: Optional TrustOperations instance for verification.
                If not provided, only header-level validation is performed.
            config: Configuration for the middleware. Defaults to TrustMiddlewareConfig().
            header_extractor: Optional custom EATPHeaderExtractor. Defaults to
                EATPHeaderExtractor().
        """
        super().__init__(app)
        self.trust_operations = trust_operations
        self.config = config or TrustMiddlewareConfig()
        self.header_extractor = header_extractor or EATPHeaderExtractor()

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Any],
    ) -> Response:
        """Process the request and perform trust verification.

        This method implements the main middleware logic:
        1. Check if middleware is enabled
        2. Check if path is exempt
        3. Extract EATP headers
        4. Store context in request.state
        5. Perform verification based on mode
        6. Return appropriate response

        Args:
            request: The incoming Starlette request.
            call_next: The next middleware or route handler.

        Returns:
            Response: Either the downstream response or an error response.
        """
        # Step 1: Check if middleware is enabled
        if not self.config.enabled:
            return await call_next(request)

        # Step 2: Check if path is exempt
        if self._is_path_exempt(request.url.path):
            return await call_next(request)

        # Step 3: Extract EATP headers
        headers_dict = dict(request.headers)
        eatp_context = self.header_extractor.extract(headers_dict)

        # Step 4: Store context in request.state (always, even if invalid)
        request.state.eatp_context = eatp_context

        # Step 5: Check mode and perform appropriate verification
        if self.config.mode == "disabled":
            return await call_next(request)

        # Perform verification
        verification_result = await self._verify_trust(request, eatp_context)

        if verification_result.allowed:
            return await call_next(request)

        # Handle verification failure based on mode
        if self.config.mode == "permissive":
            # Log warning but allow request through
            logger.warning(
                f"EATP trust verification failed (permissive mode): "
                f"{verification_result.reason}. "
                f"Path: {request.url.path}, "
                f"Agent: {eatp_context.agent_id or 'unknown'}"
            )
            return await call_next(request)

        # enforcing mode - return error response
        return verification_result.error_response

    def _is_path_exempt(self, path: str) -> bool:
        """Check if a path is exempt from trust verification.

        CARE-052: Security fix for path exemption matching.
        Supports both exact matching and prefix matching for paths ending with `/*`.

        Security rationale:
        - Exact matching (e.g., "/health") ensures only the specific path is exempt
        - Prefix matching (e.g., "/health/*") allows exemption of path hierarchies
          like "/health/ready", "/health/detailed", etc.
        - The `/*` suffix is explicit to prevent accidental over-matching
        - Without this, operators must list every subpath individually, which is
          error-prone and can lead to security misconfigurations

        Args:
            path: The URL path to check.

        Returns:
            True if the path matches an exempt path (exact or prefix match).
        """
        for exempt_path in self.config.exempt_paths:
            # CARE-052: Check for prefix pattern (ends with /*)
            if exempt_path.endswith("/*"):
                # Extract the prefix (remove /*)
                prefix = exempt_path[
                    :-1
                ]  # Keep trailing slash: "/health/*" -> "/health/"
                # Match if path starts with prefix or equals the base path (without trailing slash)
                base_path = exempt_path[:-2]  # "/health/*" -> "/health"
                if path == base_path or path.startswith(prefix):
                    return True
            else:
                # Exact match for paths without /* suffix
                if path == exempt_path:
                    return True
        return False

    async def _verify_trust(
        self,
        request: Request,
        context: ExtractedEATPContext,
    ) -> "VerificationOutcome":
        """Perform trust verification on the request.

        This method checks:
        1. Whether EATP context is valid (has trace_id and agent_id)
        2. Whether human origin is present (if required)
        3. Whether TrustOperations verification passes (if configured)

        Args:
            request: The incoming request.
            context: The extracted EATP context.

        Returns:
            VerificationOutcome with allowed status and optional error response.
        """
        # Check 1: Valid EATP context (has required headers)
        if not context.is_valid():
            return VerificationOutcome(
                allowed=False,
                reason="Missing required EATP headers (trace_id and/or agent_id)",
                error_response=JSONResponse(
                    status_code=401,
                    content={
                        "error": "Missing required EATP headers. "
                        "Both X-EATP-Trace-ID and X-EATP-Agent-ID are required."
                    },
                ),
            )

        # Check 2: Human origin requirement
        if self.config.require_human_origin and not context.has_human_origin():
            return VerificationOutcome(
                allowed=False,
                reason="Missing required human origin in EATP context",
                error_response=JSONResponse(
                    status_code=403,
                    content={
                        "error": "Human origin required. "
                        "X-EATP-Human-Origin header must be present and valid."
                    },
                ),
            )

        # Check 3: TrustOperations verification (if configured)
        if self.trust_operations is not None:
            try:
                # Derive action from request method and path
                action = f"{request.method.lower()}:{request.url.path}"
                resource = request.url.path

                result = await self.trust_operations.verify(
                    agent_id=context.agent_id,
                    action=action,
                    resource=resource,
                )

                if not result.valid:
                    return VerificationOutcome(
                        allowed=False,
                        reason=result.reason or "Trust verification failed",
                        error_response=JSONResponse(
                            status_code=403,
                            content={
                                "error": "Trust verification failed. "
                                f"Agent '{context.agent_id}' is not authorized for this action."
                            },
                        ),
                    )
            except Exception as e:
                # Handle TrustOperations exceptions
                logger.error(
                    f"Trust verification error: {e}. "
                    f"Agent: {context.agent_id}, Path: {request.url.path}"
                )
                return VerificationOutcome(
                    allowed=False,
                    reason=f"Trust service error: {e}",
                    error_response=JSONResponse(
                        status_code=503,
                        content={
                            "error": "Trust verification service unavailable. "
                            "Please try again later."
                        },
                    ),
                )
        else:
            # No TrustOperations configured - log warning but allow if headers valid
            if self.config.mode == "enforcing":
                logger.warning(
                    "No TrustOperations configured. "
                    "Performing header-only validation in enforcing mode."
                )

        # All checks passed
        return VerificationOutcome(allowed=True)


@dataclass
class VerificationOutcome:
    """Result of trust verification.

    Attributes:
        allowed: Whether the request should be allowed.
        reason: Human-readable reason for the outcome.
        error_response: Response to return if not allowed (for enforcing mode).
    """

    allowed: bool
    reason: Optional[str] = None
    error_response: Optional[Response] = None
