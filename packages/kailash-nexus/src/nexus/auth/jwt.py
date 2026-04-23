"""JWT Middleware for Nexus Authentication.

SPEC-06 Migration: Core JWT validation logic extracted to kailash.trust.auth.jwt.
This module retains the Starlette/FastAPI JWTMiddleware that delegates to
JWTValidator for the actual crypto work.

Provides:
    - JWTMiddleware (Starlette BaseHTTPMiddleware)
    - JWTConfig (re-exported from kailash.trust.auth.jwt)
"""

from __future__ import annotations

import inspect
import logging
from typing import Any, Callable, Dict, List, Optional, Union

from kailash.trust.auth.exceptions import ExpiredTokenError, InvalidTokenError
from kailash.trust.auth.jwt import JWTConfig, JWTValidator
from kailash.trust.auth.models import AuthenticatedUser
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

# Cross-engine propagation surface per specs/nexus-ml-integration.md §§2–3.
# JWT middleware sets these on every validated request so kailash-ml,
# kailash-dataflow, and kailash-kaizen engines read the ambient tenant/actor
# without the caller extracting claims manually.
from nexus.context import _current_actor_id, _current_tenant_id

logger = logging.getLogger(__name__)

# Re-export JWTConfig for backward compatibility
__all__ = [
    "JWTConfig",
    "JWTMiddleware",
]


class JWTMiddleware(BaseHTTPMiddleware):
    """JWT authentication middleware for Starlette/FastAPI.

    Extracts JWT tokens from requests, verifies them via JWTValidator,
    and populates request.state.user with an AuthenticatedUser instance.

    Usage:
        config = JWTConfig(
            secret="your-secret-key",
            algorithm="HS256",
            exempt_paths=["/health", "/public/*"],
        )
        app.add_middleware(JWTMiddleware, config=config)
    """

    def __init__(
        self,
        app: Any,
        config: Optional[JWTConfig] = None,
        *,
        secret: Optional[str] = None,
        algorithm: Optional[str] = None,
        public_key: Optional[str] = None,
        private_key: Optional[str] = None,
        issuer: Optional[str] = None,
        audience: Optional[Union[str, List[str]]] = None,
        token_header: Optional[str] = None,
        token_cookie: Optional[str] = None,
        token_query_param: Optional[str] = None,
        exempt_paths: Optional[List[str]] = None,
        jwks_url: Optional[str] = None,
    ):
        """Initialize JWT middleware.

        Args:
            app: ASGI application
            config: JWTConfig instance (preferred)
            secret: Override config.secret
            algorithm: Override config.algorithm
            public_key: Override config.public_key
            private_key: Override config.private_key
            issuer: Override config.issuer
            audience: Override config.audience
            token_header: Override config.token_header
            token_cookie: Override config.token_cookie
            token_query_param: Override config.token_query_param
            exempt_paths: Override config.exempt_paths
            jwks_url: Override config.jwks_url
        """
        super().__init__(app)

        # Start with config or build from parameters
        if config:
            self.config = config
        else:
            # Build config from individual parameters
            kwargs: Dict[str, Any] = {}
            if secret is not None:
                kwargs["secret"] = secret
            if algorithm is not None:
                kwargs["algorithm"] = algorithm
            if public_key is not None:
                kwargs["public_key"] = public_key
            if private_key is not None:
                kwargs["private_key"] = private_key
            if issuer is not None:
                kwargs["issuer"] = issuer
            if audience is not None:
                kwargs["audience"] = audience
            if token_header is not None:
                kwargs["token_header"] = token_header
            if token_cookie is not None:
                kwargs["token_cookie"] = token_cookie
            if token_query_param is not None:
                kwargs["token_query_param"] = token_query_param
            if exempt_paths is not None:
                kwargs["exempt_paths"] = exempt_paths
            if jwks_url is not None:
                kwargs["jwks_url"] = jwks_url
            self.config = JWTConfig(**kwargs)

        # Delegate to JWTValidator for crypto operations
        self._validator = JWTValidator(self.config)

        logger.info(
            "JWTMiddleware initialized with algorithm=%s", self.config.algorithm
        )

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Any],
    ) -> Response:
        """Process request and verify JWT token."""
        # Check if path is exempt
        if self._validator.is_path_exempt(request.url.path):
            return await call_next(request)

        # Extract token
        token = self._extract_token(request)
        if not token:
            return JSONResponse(
                status_code=401,
                content={"detail": "Not authenticated", "error": "missing_token"},
                headers={"WWW-Authenticate": 'Bearer realm="api"'},
            )

        # Handle API key authentication
        if token.startswith("__apikey__") and self.config.api_key_enabled:
            api_key = token[len("__apikey__") :]
            if self.config.api_key_validator:
                try:
                    result = self.config.api_key_validator(api_key)
                    if inspect.isawaitable(result):
                        result = await result
                    if not result:
                        return JSONResponse(
                            status_code=401,
                            content={
                                "detail": "Invalid API key",
                                "error": "invalid_api_key",
                            },
                        )
                    # api_key_validator can return a user dict or True
                    if isinstance(result, dict):
                        user = self._validator.create_user_from_payload(result)
                        ak_tenant_id = result.get("tenant_id")
                        ak_actor_id = result.get("sub") or result.get("user_id")
                    else:
                        user = AuthenticatedUser(user_id="apikey", roles=["api"])
                        ak_tenant_id = None
                        ak_actor_id = "apikey"
                    request.state.user = user
                    request.state.token = api_key
                    request.state.token_payload = {"type": "api_key"}
                    # Cross-engine propagation mirrors the JWT-validated path; see
                    # specs/nexus-ml-integration.md §2.2 for the reset-in-finally invariant.
                    tenant_token = _current_tenant_id.set(ak_tenant_id)
                    actor_token = _current_actor_id.set(ak_actor_id)
                    try:
                        return await call_next(request)
                    finally:
                        _current_actor_id.reset(actor_token)
                        _current_tenant_id.reset(tenant_token)
                except Exception as e:
                    logger.warning("API key validation failed: %s", e)
                    return JSONResponse(
                        status_code=401,
                        content={
                            "detail": "API key validation error",
                            "error": "api_key_error",
                        },
                    )
            else:
                return JSONResponse(
                    status_code=500,
                    content={
                        "detail": "API key auth enabled but no validator configured"
                    },
                )

        # Verify JWT token
        try:
            payload = self._validator.verify_token(token)

            # Absolute token age check
            age_error = self._validator.check_token_age(payload)
            if age_error:
                return JSONResponse(
                    status_code=401,
                    content={"detail": age_error, "error": "invalid_token"},
                )

            user = self._validator.create_user_from_payload(payload)

            # Store user in request state
            request.state.user = user
            request.state.token = token
            request.state.token_payload = payload

            # Post-validation hook
            if self.config.on_token_validated:
                try:
                    result = self.config.on_token_validated(payload)
                    if inspect.isawaitable(result):
                        await result
                except Exception:
                    logger.exception("on_token_validated hook failed")

            # Cross-engine tenant/actor propagation per specs/nexus-ml-integration.md §2.2.
            # Reset in `finally:` — a raise inside call_next must NOT leak into the next
            # request on the same worker, or the next tenant sees prior-tenant data.
            tenant_token = _current_tenant_id.set(payload.get("tenant_id"))
            actor_token = _current_actor_id.set(payload.get("sub"))
            try:
                return await call_next(request)
            finally:
                _current_actor_id.reset(actor_token)
                _current_tenant_id.reset(tenant_token)

        except ExpiredTokenError:
            return JSONResponse(
                status_code=401,
                content={"detail": "Token has expired", "error": "token_expired"},
                headers={
                    "WWW-Authenticate": 'Bearer realm="api", error="invalid_token"'
                },
            )
        except InvalidTokenError as e:
            logger.warning("Invalid token: %s", e)
            return JSONResponse(
                status_code=401,
                content={"detail": "Invalid token", "error": "invalid_token"},
                headers={
                    "WWW-Authenticate": 'Bearer realm="api", error="invalid_token"'
                },
            )
        except Exception as e:
            logger.error("JWT verification failed: %s", e)
            return JSONResponse(
                status_code=401,
                content={"detail": "Authentication failed", "error": "auth_error"},
                headers={"WWW-Authenticate": 'Bearer realm="api"'},
            )

    def _extract_token(self, request: Request) -> Optional[str]:
        """Extract JWT token or API key from request.

        Extraction priority:
        1. API key header (if api_key_enabled)
        2. Authorization header (Bearer token)
        3. Cookie (if configured)
        4. Query parameter (if configured)
        """
        # 0. API key
        if self.config.api_key_enabled:
            api_key = request.headers.get(self.config.api_key_header, "")
            if api_key:
                request.state._fabric_api_key = api_key
                return f"__apikey__{api_key}"

        # 1. Authorization header
        auth_header = request.headers.get(self.config.token_header, "")
        if auth_header.startswith("Bearer "):
            return auth_header[7:]
        elif auth_header.startswith("bearer "):
            return auth_header[7:]

        # 2. Cookie (for browser-based apps)
        if self.config.token_cookie:
            token = request.cookies.get(self.config.token_cookie)
            if token:
                return token

        # 3. Query parameter (for WebSocket connections)
        if self.config.token_query_param:
            token = request.query_params.get(self.config.token_query_param)
            if token:
                return token

        return None

    # --- Delegate token operations to validator ---
    #
    # SPEC-06 extracted the crypto path from the middleware into
    # JWTValidator. These thin delegates preserve the pre-migration
    # API so external consumers (and the unit test suite) that call
    # mw.create_access_token / mw._verify_token / mw._create_user_from_payload
    # continue to work unchanged during the deprecation window.
    #
    # Each delegate guards against a bypassed ``__init__`` (e.g., a
    # caller using ``__new__`` to construct the middleware without
    # ``self._validator`` being set). The guard converts what would
    # otherwise be an uninformative ``AttributeError`` on ``None`` into
    # a typed ``RuntimeError`` that names the root cause. The hot path
    # is unaffected because ``__init__`` always assigns
    # ``self._validator = JWTValidator(self.config)``.

    def _require_validator(self) -> "JWTValidator":
        """Return ``self._validator`` or raise if it was never assigned.

        Red-team R1 C.2 follow-up: if a caller constructs the
        middleware via ``__new__`` (the test suite does this) and
        forgets to assign ``_validator``, every delegate would raise
        a raw ``AttributeError`` on ``None``. The typed error here
        identifies the root cause unambiguously.
        """
        validator = getattr(self, "_validator", None)
        if validator is None:
            raise RuntimeError(
                "JWTMiddleware._validator is not set. This usually means "
                "the middleware was constructed via __new__ without "
                "calling __init__ — assign mw._validator = "
                "JWTValidator(mw.config) before calling any delegate."
            )
        return validator

    def create_access_token(self, **kwargs: Any) -> str:
        """Create a new access token. Delegates to JWTValidator."""
        return self._require_validator().create_access_token(**kwargs)

    def create_refresh_token(self, **kwargs: Any) -> str:
        """Create a refresh token. Delegates to JWTValidator."""
        return self._require_validator().create_refresh_token(**kwargs)

    def _verify_token(self, token: str) -> Dict[str, Any]:
        """Verify a JWT token. Delegates to JWTValidator.verify_token.

        Kept on the middleware for backward compatibility with callers
        from before the SPEC-06 crypto extraction.
        """
        return self._require_validator().verify_token(token)

    def _create_user_from_payload(self, payload: Dict[str, Any]) -> AuthenticatedUser:
        """Build an AuthenticatedUser from a verified JWT payload.

        Delegates to JWTValidator.create_user_from_payload — kept on
        the middleware for backward compatibility with callers from
        before the SPEC-06 crypto extraction.
        """
        return self._require_validator().create_user_from_payload(payload)

    def _is_path_exempt(self, path: str) -> bool:
        """Check whether a request path bypasses JWT validation.

        Delegates to JWTValidator.is_path_exempt — kept on the
        middleware for backward compatibility with callers from
        before the SPEC-06 crypto extraction.
        """
        return self._require_validator().is_path_exempt(path)
