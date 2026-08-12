"""
Enhanced API Gateway for Kailash Middleware

Provides a comprehensive API gateway that integrates agent-UI middleware,
real-time communication, and dynamic workflow management with full
frontend support capabilities.
"""

import asyncio
import logging
import os
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Union

# `fastapi` is an OPTIONAL dependency under the `server` extra. Per
# `rules/dependencies.md` § "Declared = Imported": optional-extra imports
# MUST raise loudly with an actionable error naming the extra.
try:
    from fastapi import Depends, FastAPI, HTTPException, Request, WebSocket
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import JSONResponse
except ImportError as exc:  # pragma: no cover — covered by structural invariant test
    raise ImportError(
        "kailash.middleware.communication.api_gateway requires server "
        "dependencies (fastapi). Install with: pip install 'kailash[server]'"
    ) from exc

from pydantic import BaseModel, Field

from ...nodes.base import NodeRegistry
from ...nodes.security import CredentialManagerNode
from ...nodes.transform import DataTransformer
from ...utils.http_errors import new_error_reference, safe_http_detail
from ...utils.lifespan import (
    drive_router_lifespan_shutdown,
    drive_router_lifespan_startup,
)
from ...utils.secure_logging import sanitize_log_value
from ...utils.server_auth import install_server_auth_middleware, resolve_server_auth
from ...workflow import Workflow
from ...workflow.builder import WorkflowBuilder
from ..core.agent_ui import AgentUIMiddleware
from ..core.schema import DynamicSchemaRegistry
from .events import EventFilter, EventType
from .realtime import RealtimeMiddleware

logger = logging.getLogger(__name__)

# Auth manager will be injected via dependency injection
# This avoids circular imports and allows for flexible auth implementations


# Pydantic Models
class SessionCreateRequest(BaseModel):
    """Request model for creating a new session."""

    user_id: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class SessionResponse(BaseModel):
    """Response model for session operations."""

    session_id: str
    user_id: Optional[str] = None
    created_at: datetime
    active: bool = True


class WorkflowCreateRequest(BaseModel):
    """Request model for creating a workflow."""

    name: str
    description: Optional[str] = None
    nodes: List[Dict[str, Any]] = Field(default_factory=list)
    connections: List[Dict[str, Any]] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class WorkflowExecuteRequest(BaseModel):
    """Request model for executing a workflow."""

    workflow_id: str
    inputs: Dict[str, Any] = Field(default_factory=dict)
    config_overrides: Dict[str, Any] = Field(default_factory=dict)


class ExecutionResponse(BaseModel):
    """Response model for workflow execution."""

    execution_id: str
    workflow_id: str
    status: str
    created_at: datetime
    progress: float = 0.0


class NodeSchemaRequest(BaseModel):
    """Request model for getting node schemas."""

    node_types: Optional[List[str]] = None
    include_examples: bool = False


class WebhookRegisterRequest(BaseModel):
    """Request model for registering webhooks."""

    url: str
    secret: Optional[str] = None
    event_types: List[str] = Field(default_factory=list)
    headers: Dict[str, str] = Field(default_factory=dict)


class APIGateway:
    """
    Enhanced API Gateway for Kailash Middleware.

    Now uses SDK components for:
    - Authentication and authorization with SDKAuthManager
    - Data transformation with DataTransformer nodes
    - Audit logging with AuditLogNode
    - Security event tracking with SecurityEventNode

    Provides:
    - Session management for frontend clients
    - Real-time workflow execution and monitoring
    - Dynamic workflow creation and modification
    - Node discovery and schema generation
    - Multi-transport real-time communication (WebSocket, SSE, Webhooks)
    - AI chat integration for workflow assistance
    - Comprehensive monitoring and statistics
    """

    def __init__(
        self,
        title: str = "Kailash Middleware Gateway",
        description: str = "Enhanced API gateway for agent-frontend communication",
        version: str = "1.0.0",
        cors_origins: Optional[List[str]] = None,
        enable_docs: bool = True,
        max_sessions: int = 1000,
        enable_auth: bool = True,
        auth_manager=None,  # Dependency injection for auth
        database_url: Optional[str] = None,
        require_auth: Optional[bool] = None,
        auth_config: Any = None,
        external_auth_reason: Optional[str] = None,
        auth_exempt_paths: Optional[List[str]] = None,
    ):
        """
        Initialize API Gateway with dependency injection support.

        ``enable_auth`` and ``require_auth`` are DIFFERENT knobs and both are
        needed, because this gateway both ISSUES and ACCEPTS credentials:

        * ``enable_auth`` -- whether the gateway holds a token-ISSUING
          :class:`~kailash.middleware.auth.jwt_auth.JWTAuthManager` (issue #636
          behaviour, unchanged).
        * ``require_auth`` -- whether every request must PRESENT a credential.

        ``require_auth`` is TRI-STATE (``Optional[bool]``, default ``None``) for
        the same reason ``ChannelConfig.enable_auth`` is: a plain ``bool``
        cannot distinguish "the operator never said" from "the operator said
        no". ``None`` means unstated and inherits fail-closed -- EXCEPT when
        ``enable_auth=False``, which was the only auth control this class had
        before #2072 and is therefore an EXPLICIT opt-out, not silence. Reading
        it as silence would raise on callers who already said what they wanted,
        in the words that were available to them (issue #636's contract).
        ``require_auth=True`` alongside ``enable_auth=False`` still gates: the
        newer, more specific statement wins.

        Before issue #2072 only the first existed, and it gated nothing: with
        ``enable_auth=True`` a ``JWTAuthManager`` was constructed that **no
        route ever consulted**. Measured on a real socket against a default
        ``create_gateway()`` with ``KAILASH_API_GATEWAY_SECRET`` set, every
        request UNCREDENTIALED::

            enable_auth: True   auth_manager: JWTAuthManager
            GET    /                          -> 200
            GET    /api/workflows             -> 200
            POST   /api/executions?session_id -> 500   (handler RAN)
            DELETE /api/executions/e          -> 500   (handler RAN)
            GET    /api/stats                 -> 200
            GET    /openapi.json              -> 200

        Not one 401. The 500s are the application failing on a missing session
        AFTER routing, which is what proves the request reached the handler --
        an anonymous caller holding any live ``session_id`` executed workflows.

        This is the SIXTH surface of #2072 and it was the most dangerous,
        because ``kailash.middleware`` re-exports ``create_gateway`` under the
        SAME NAME as the fixed ``kailash.servers.gateway.create_gateway``. The
        two callables had opposite security postures, and this module's own
        docstring demonstrates the unsafe one. It now routes through the same
        :func:`~kailash.utils.server_auth.resolve_server_auth` as the other
        five, so there is one gate and one policy.

        Credential resolution for the gate, in order: ``auth_config`` if given;
        else the ``auth_manager``'s own key/issuer/audience -- so the credential
        this gateway ISSUES is the one it ACCEPTS, and an existing
        ``KAILASH_API_GATEWAY_SECRET`` deployment keeps working with the tokens
        it already mints; else the environment
        (``KAILASH_JWT_SECRET`` / ``KAILASH_API_KEY_*``), which fails closed.

        Args:
            title: API title
            description: API description
            version: API version
            cors_origins: Allowed CORS origins
            enable_docs: Enable OpenAPI documentation
            max_sessions: Maximum concurrent sessions
            enable_auth: Hold a token-issuing auth manager
            auth_manager: Optional auth manager instance (creates default if None and auth enabled)
            database_url: Optional database URL for persistence
            require_auth: Reject unauthenticated requests. ``None`` (default)
                inherits fail-closed unless ``enable_auth=False`` explicitly
                opted out; ``True`` gates and RAISES when no credential source
                is configured; ``False`` serves openly and logs a loud WARN.
            auth_config: Explicit ``kailash.trust.auth.jwt.JWTConfig`` (or a
                dict of its fields) for the request gate.
            external_auth_reason: Non-empty when an ASGI middleware outside
                this gateway already authenticates every request.
            auth_exempt_paths: Extra paths exempt from the gate, on top of
                ``kailash.utils.server_auth.DEFAULT_EXEMPT_PATHS``.

        Raises:
            ServerAuthNotConfiguredError: The gate is required and no credential
                source could be resolved -- including the case where an
                ``auth_manager`` was supplied but carries no derivable key, in
                which case it cannot verify anything and installing nothing
                would be the #2013 silent-no-op shape. Pass ``require_auth=
                False`` to run open.
        """
        self.title = title
        self.version = version
        self.enable_docs = enable_docs
        self.enable_auth = enable_auth

        # Initialize SDK nodes for gateway operations
        self._init_sdk_nodes(database_url)

        # Initialize core middleware components
        self.agent_ui = AgentUIMiddleware(max_sessions=max_sessions)
        self.realtime = RealtimeMiddleware(self.agent_ui)
        self.schema_registry = DynamicSchemaRegistry()
        self.node_registry = NodeRegistry()

        # Initialize auth manager if enabled
        if enable_auth:
            if auth_manager is None:
                secret_key = os.environ.get("KAILASH_API_GATEWAY_SECRET")
                if not secret_key:
                    raise RuntimeError(
                        "APIGateway(enable_auth=True) without auth_manager requires "
                        "KAILASH_API_GATEWAY_SECRET environment variable (>=32 bytes). "
                        "Either set the env var, pass auth_manager=JWTAuthManager(...), "
                        "or set enable_auth=False. See issue #636."
                    )
                if len(secret_key.encode("utf-8")) < 32:
                    raise ValueError(
                        "KAILASH_API_GATEWAY_SECRET must be at least 32 bytes "
                        f"(got {len(secret_key.encode('utf-8'))}). See RFC 7518 §3.2 "
                        "and kailash.trust.auth.jwt.JWTConfig.MIN_SECRET_LENGTH. "
                        "(The middleware JWTConfig carries no such constant; "
                        "naming it there sent readers looking for an attribute "
                        "that does not exist.)"
                    )
                from ..auth import JWTAuthManager

                self.auth_manager = JWTAuthManager(
                    secret_key=secret_key,
                    algorithm="HS256",
                    issuer="kailash-gateway",
                    audience="kailash-api",
                )
            else:
                self.auth_manager = auth_manager
        else:
            self.auth_manager = None

        # Create FastAPI app with lifespan management
        @asynccontextmanager
        async def lifespan(app: FastAPI):
            # Startup
            logger.info(f"Starting {title} v{version}")
            # S2 (#712): drive router.on_startup hooks (e.g. consumer
            # @app.on_event("startup")). Without this iteration, the custom
            # lifespan above replaces Starlette's _DefaultLifespan and
            # silently drops every router-registered hook (the #500 bug class).
            await drive_router_lifespan_startup(app)
            await self._log_startup()
            yield
            # Shutdown
            logger.info("Shutting down gateway")
            await drive_router_lifespan_shutdown(app)
            await self._cleanup()

        self.app = FastAPI(
            title=title,
            description=description,
            version=version,
            docs_url="/docs" if enable_docs else None,
            redoc_url="/redoc" if enable_docs else None,
            lifespan=lifespan,
        )

        # Install the request gate BEFORE CORS. Starlette's `add_middleware`
        # PREPENDS, so the layer added LAST is the OUTERMOST one; auth added
        # after CORS ends up inside it and answers cross-origin preflight
        # OPTIONS with 401 before CORS can. PR #2054 hit exactly this ordering
        # bug on the Nexus surface.
        # Tri-state resolution. `None` is "unstated", and the only thing that
        # turns unstated into an opt-out is `enable_auth=False` -- the sole auth
        # control this class had before #2072, so a caller who set it DID say
        # what they wanted. An explicit `require_auth` always wins over it.
        resolved_require_auth = (
            bool(enable_auth) if require_auth is None else bool(require_auth)
        )
        self._auth_config = resolve_server_auth(
            require_auth=resolved_require_auth,
            auth_config=(
                auth_config
                if auth_config is not None
                else self._auth_config_from_manager()
            ),
            external_auth_reason=external_auth_reason,
            extra_exempt_paths=auth_exempt_paths,
            server_label=title,
        )
        if self._auth_config is not None:
            install_server_auth_middleware(self.app, self._auth_config)

        # Add CORS middleware
        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=cors_origins or [],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

        # Setup routes
        self._setup_routes()

        # Performance tracking
        self.start_time = time.time()
        self.requests_processed = 0

    def _auth_config_from_manager(self) -> Optional[Any]:
        """Derive the request gate's config from this gateway's token ISSUER.

        The gateway mints tokens with ``JWTAuthManager`` and now also verifies
        them. If the two used different keys, every token this gateway issued
        would be rejected by its own gate -- so the verifier is built from the
        issuer's own key, algorithm, issuer and audience rather than from a
        second, independently-configured source.

        ``issuer``/``audience`` are NOT optional here. ``JWTAuthManager`` stamps
        both into every token, and PyJWT raises ``InvalidAudienceError`` when a
        token carries an ``aud`` claim the verifier was not told to expect. A
        verifier built without them would 401 every legitimately-issued token.

        Returns ``None`` when there is no manager to derive from (``enable_auth=
        False``), which lets :func:`resolve_server_auth` fall through to the
        environment and fail closed there.
        """
        manager = getattr(self, "auth_manager", None)
        if manager is None:
            return None
        config = getattr(manager, "config", None)
        if config is None:
            # A manager with no config carries no key, so no verifier can be
            # built from it. Loud, because the caller supplied a manager and
            # would otherwise read the downstream "no credential source"
            # message as though they had supplied nothing.
            logger.warning(
                "api_gateway.auth_manager_yields_no_verifier",
                extra={
                    "manager_type": type(manager).__name__,
                    "reason": "no .config, so no key material to verify against",
                },
            )
            return None

        algorithm = getattr(config, "algorithm", "HS256") or "HS256"
        # RSA/EC verification needs the PUBLIC key; the private half must never
        # reach a verifier config. `JWTAuthManager` exposes the PEM it loaded or
        # generated via `get_public_key()`.
        public_key = None
        secret = None
        if algorithm.startswith(("RS", "ES", "PS")):
            # Two shapes. A caller-SUPPLIED key pair leaves the PEM on
            # `config.public_key`. An AUTO-GENERATED pair does not write the PEM
            # back to the config -- it lives only as a key object on the
            # manager's private `_public_key` -- so it has to be serialized.
            public_key = getattr(config, "public_key", None)
            if not public_key:
                key_object = getattr(manager, "_public_key", None)
                if key_object is not None:
                    try:
                        from cryptography.hazmat.primitives import serialization

                        public_key = key_object.public_bytes(
                            encoding=serialization.Encoding.PEM,
                            format=serialization.PublicFormat.SubjectPublicKeyInfo,
                        ).decode("utf-8")
                    except Exception:
                        # Not swallowed: reported with a stack trace, and the
                        # return below leaves `resolve_server_auth` to fall
                        # through to the environment and FAIL CLOSED rather than
                        # install a gate that cannot verify. Degrading to "no
                        # gate" here would be the #2013 shape this whole change
                        # exists to remove.
                        logger.exception(
                            "api_gateway.auth_public_key_unavailable",
                            extra={"algorithm": algorithm},
                        )
                        return None
            if not public_key:
                return None
        else:
            secret = getattr(config, "secret_key", None)
            if not secret:
                return None

        from ...trust.auth.jwt import JWTConfig as TrustJWTConfig

        return TrustJWTConfig(
            secret=secret,
            public_key=public_key,
            algorithm=algorithm,
            issuer=getattr(config, "issuer", None),
            audience=getattr(config, "audience", None),
        )

    def _init_sdk_nodes(self, database_url: Optional[str] = None):
        """Initialize SDK nodes for gateway operations."""

        # Data transformer for request/response formatting
        self.data_transformer = DataTransformer(
            name="gateway_transformer",
            # Transformations will be provided at runtime
            transformations=[],
        )

        # Credential manager for gateway security
        self.credential_manager = CredentialManagerNode(
            name="gateway_credentials",
            credential_name="gateway_secrets",
            credential_type="custom",
        )

    async def _log_startup(self):
        """Log gateway startup."""
        logger.info(
            f"API Gateway started: {self.title} v{self.version}, Auth: {self.enable_auth}"
        )

    async def _cleanup(self):
        """Cleanup resources on shutdown."""
        try:
            # Close all sessions
            for session_id in list(self.agent_ui.sessions.keys()):
                await self.agent_ui.close_session(session_id)
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")

    def _setup_routes(self):
        """Setup all API routes."""
        self._setup_core_routes()
        self._setup_session_routes()
        self._setup_workflow_routes()
        self._setup_execution_routes()
        self._setup_schema_routes()
        self._setup_realtime_routes()
        self._setup_monitoring_routes()

    def _setup_core_routes(self):
        """Setup core gateway routes."""

        @self.app.get("/")
        async def root():
            """Gateway information and status."""
            return {
                "name": self.title,
                "version": self.version,
                "status": "healthy",
                "uptime_seconds": time.time() - self.start_time,
                "features": {
                    "sessions": True,
                    "real_time": True,
                    "dynamic_workflows": True,
                    "webhooks": True,
                },
                "endpoints": {
                    "sessions": "/api/sessions",
                    "workflows": "/api/workflows",
                    "schemas": "/api/schemas",
                    "websocket": "/ws",
                    "sse": "/events",
                    "docs": "/docs" if self.enable_docs else None,
                },
            }

        @self.app.get("/health")
        async def health_check():
            """Detailed health check."""
            try:
                agent_ui_stats = self.agent_ui.get_stats()
                realtime_stats = self.realtime.get_stats()
                schema_stats = self.schema_registry.get_stats()

                return {
                    "status": "healthy",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "uptime_seconds": time.time() - self.start_time,
                    "requests_processed": self.requests_processed,
                    "components": {
                        "agent_ui": {
                            "status": "healthy",
                            "active_sessions": agent_ui_stats["active_sessions"],
                            "workflows_executed": agent_ui_stats["workflows_executed"],
                        },
                        "realtime": {
                            "status": "healthy",
                            "events_processed": realtime_stats["events_processed"],
                            "websocket_connections": realtime_stats.get(
                                "websocket_stats", {}
                            ).get("total_connections", 0),
                        },
                        "schema_registry": {
                            "status": "healthy",
                            "schemas_generated": schema_stats["schemas_generated"],
                            "cache_hit_rate": schema_stats["cache_hit_rate"],
                        },
                    },
                }
            except Exception as e:
                return JSONResponse(
                    status_code=503,
                    content={
                        "status": "unhealthy",
                        "error": safe_http_detail(
                            e, logger=logger, context="health check", status_code=503
                        ),
                    },
                )

    def _setup_session_routes(self):
        """Setup session management routes."""

        # Create auth dependency
        async def get_optional_current_user(request: Request):
            """Resolve the authenticated principal, or None when there is none.

            This returned None unconditionally -- "For now, return None to
            avoid complex auth setup" -- on EVERY path, including with auth
            enabled and a valid bearer token presented. `enable_auth` defaults
            to True, so on the default path the session identity was always
            the caller-supplied `request.user_id` body field and the
            server-derived principal never won (`zero-tolerance.md` Rule 2;
            same bug class as #2047 at the HTTP surface). The auth manager's
            `verify_token` / `verify_api_key` existed the whole time and were
            simply not called.

            Deliberately still OPTIONAL: a request with no credential resolves
            to None rather than 401, which preserves this route's contract.
            Whether an auth-enabled gateway should REFUSE a session create
            that carries no credential is a separate, breaking decision and is
            tracked as its own issue rather than smuggled in here.
            """
            if not (self.enable_auth and self.auth_manager):
                return None

            scheme, _, token = (request.headers.get("Authorization") or "").partition(
                " "
            )
            if scheme.lower() == "bearer" and token:
                try:
                    payload = await self.auth_manager.verify_token(token)
                except HTTPException:
                    # An invalid/expired token is a REJECTED credential, not
                    # an absent one. Logged rather than swallowed silently
                    # (`zero-tolerance.md` Rule 3); the request continues
                    # unauthenticated, which this route already permits.
                    logger.warning("Session-route bearer token was rejected")
                    return None
                except Exception as exc:
                    logger.warning(
                        "Session-route token verification failed: %s",
                        type(exc).__name__,
                    )
                    return None
                return {
                    "user_id": payload.get("user_id"),
                    "permissions": payload.get("permissions", []),
                    "metadata": payload.get("metadata", {}),
                }

            # NO `X-API-Key` BRANCH HERE, deliberately.
            #
            # A first draft of this added one, calling
            # `auth_manager.verify_api_key`. That method CANNOT SUCCEED, which
            # was measured rather than assumed: it calls
            # `credential_manager.execute(operation=..., credential_name=...)`,
            # but `CredentialManagerNode.run()` takes `**inputs` and ignores
            # BOTH -- it reads `self.credential_name`, fixed at construction --
            # and its return dict has no `"success"` key at all. So
            # `result.get("success", False)` is always False and the call
            # always raises 401. An auth path that can only ever reject is a
            # non-functional feature presented as a working one
            # (`zero-tolerance.md` Rule 2), so it is not shipped. The
            # underlying `verify_api_key` defect is pre-existing and tracked
            # separately.
            return None

        @self.app.post("/api/sessions", response_model=SessionResponse)
        async def create_session(
            request: SessionCreateRequest,
            current_user: Dict[str, Any] = Depends(get_optional_current_user),
        ):
            """Create a new session for a frontend client."""
            try:
                # A resolved principal WINS -- and an UNUSABLE one REFUSES.
                #
                # `.get("user_id", user_id)` fell back to the body value only
                # when the key was ABSENT, so a principal resolving to a None
                # user_id silently produced a session with no owner. The first
                # fix for that skipped the assignment instead, which is just
                # as wrong in the other direction: it reverted to the
                # caller-supplied body field. A credential that verified but
                # carries no usable subject is a BROKEN credential, not an
                # absent one, and falling back to the caller's claim there is
                # fail-open at an identity-resolution site.
                user_id = request.user_id
                if self.enable_auth and current_user:
                    principal = current_user.get("user_id")
                    if not isinstance(principal, str) or not principal:
                        raise HTTPException(
                            status_code=401,
                            detail=(
                                "Authenticated credential carries no usable " "subject"
                            ),
                        )
                    user_id = principal

                session_id = await self.agent_ui.create_session(
                    user_id=user_id or "", metadata=request.metadata
                )

                session = await self.agent_ui.get_session(session_id)
                self.requests_processed += 1

                # Log session creation. ``user_id`` is caller-controlled: it
                # comes from the POST body and is only overridden when auth is
                # enabled AND a principal resolved, so on the default path it
                # is the raw request value. Interpolated, an embedded newline
                # forges a second well-formed log record (issue #2040).
                logger.info(
                    "Session created: %s for user %s",
                    sanitize_log_value(session_id, 128),
                    sanitize_log_value(user_id, 128),
                )

                # Transform response using SDK node
                response_data = {
                    "session_id": session_id,
                    "user_id": session.user_id if session else None,
                    "created_at": session.created_at.isoformat() if session else None,
                    "active": session.active if session else False,
                }

                transformed = self.data_transformer.execute(
                    data=response_data,
                    transformations=[f"{{**data, 'api_version': '{self.version}'}}"],
                )

                return SessionResponse(**transformed["result"])
            except HTTPException:
                # A deliberate status -- the 401 raised above for a credential
                # with no usable subject -- must reach the client as itself.
                # The `except Exception` below would otherwise relabel every
                # auth refusal on this route as a 500, hiding the refusal and
                # reporting a server fault for a client error.
                raise
            except Exception as e:
                # The security event and the client response share one
                # reference id, so the failed-session record can be tied to
                # the caller report without the exception text -- which on
                # this path reaches a session/credential backend -- landing
                # in either sink raw.
                reference = new_error_reference()
                detail = safe_http_detail(
                    e, logger=logger, context="create session", reference=reference
                )

                # Log security event for failed session creation. `user_id` is
                # the raw POST body value here -- a site the first #2040 sweep
                # missed even though it sits nine lines below one it fixed,
                # which is the drift argument in #2088 happening inside this
                # very change.
                logger.warning(
                    "Session creation failed for user %s [reference=%s]",
                    sanitize_log_value(request.user_id, 128),
                    reference,
                )

                raise HTTPException(status_code=500, detail=detail) from e

        @self.app.get("/api/sessions/{session_id}")
        async def get_session(session_id: str):
            """Get session information."""
            session = await self.agent_ui.get_session(session_id)
            if not session:
                raise HTTPException(status_code=404, detail="Session not found")

            return {
                "session_id": session_id,
                "user_id": session.user_id,
                "created_at": session.created_at.isoformat(),
                "active": session.active,
                "workflows": list(session.workflows.keys()),
                "active_executions": len(
                    [
                        exec_id
                        for exec_id, exec_data in session.executions.items()
                        if exec_data["status"] in ["started", "running"]
                    ]
                ),
            }

        @self.app.delete("/api/sessions/{session_id}")
        async def close_session(session_id: str):
            """Close a session."""
            await self.agent_ui.close_session(session_id)
            return {"message": "Session closed"}

        @self.app.get("/api/sessions")
        async def list_sessions():
            """List all active sessions."""
            sessions = []
            for session_id, session in self.agent_ui.sessions.items():
                if session.active:
                    sessions.append(
                        {
                            "session_id": session_id,
                            "user_id": session.user_id,
                            "created_at": session.created_at.isoformat(),
                            "workflow_count": len(session.workflows),
                            "execution_count": len(session.executions),
                        }
                    )
            return {"sessions": sessions, "total": len(sessions)}

    def _setup_workflow_routes(self):
        """Setup workflow management routes."""

        @self.app.post("/api/workflows")
        async def create_workflow(request: WorkflowCreateRequest, session_id: str):
            """Create a new workflow dynamically."""
            try:
                workflow_config = {
                    "name": request.name,
                    "description": request.description,
                    "nodes": request.nodes,
                    "connections": request.connections,
                    "metadata": request.metadata,
                }

                workflow_id = await self.agent_ui.create_dynamic_workflow(
                    session_id=session_id, workflow_config=workflow_config
                )

                return {
                    "workflow_id": workflow_id,
                    "name": request.name,
                    "session_id": session_id,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }
            except Exception as e:
                raise HTTPException(
                    status_code=500,
                    detail=safe_http_detail(
                        e, logger=logger, context="create workflow"
                    ),
                ) from e

        @self.app.get("/api/workflows/{workflow_id}")
        async def get_workflow(workflow_id: str, session_id: str):
            """Get workflow information and schema."""
            session = await self.agent_ui.get_session(session_id)
            if not session:
                raise HTTPException(status_code=404, detail="Session not found")

            workflow = None
            if workflow_id in session.workflows:
                workflow = session.workflows[workflow_id]
            elif workflow_id in self.agent_ui.shared_workflows:
                workflow = self.agent_ui.shared_workflows[workflow_id]
            else:
                raise HTTPException(status_code=404, detail="Workflow not found")

            # Generate schema
            schema = self.schema_registry.get_workflow_schema(workflow)

            return {
                "workflow_id": workflow_id,
                "schema": schema,
                "is_shared": workflow_id in self.agent_ui.shared_workflows,
            }

        @self.app.get("/api/workflows")
        async def list_workflows(session_id: Optional[str] = None):
            """List available workflows."""
            workflows = []

            # Add shared workflows
            for workflow_id, workflow in self.agent_ui.shared_workflows.items():
                workflows.append(
                    {
                        "workflow_id": workflow_id,
                        "name": workflow.name,
                        "description": workflow.description,
                        "is_shared": True,
                        "node_count": len(workflow.nodes),
                    }
                )

            # Add session workflows if session_id provided
            if session_id:
                session = await self.agent_ui.get_session(session_id)
                if session:
                    for workflow_id, workflow in session.workflows.items():
                        workflows.append(
                            {
                                "workflow_id": workflow_id,
                                "name": workflow.name,
                                "description": workflow.description,
                                "is_shared": False,
                                "node_count": len(workflow.nodes),
                            }
                        )

            return {"workflows": workflows, "total": len(workflows)}

    def _setup_execution_routes(self):
        """Setup workflow execution routes."""

        @self.app.post("/api/executions", response_model=ExecutionResponse)
        async def execute_workflow(request: WorkflowExecuteRequest, session_id: str):
            """Execute a workflow."""
            try:
                execution_id = await self.agent_ui.execute(
                    session_id=session_id,
                    workflow_id=request.workflow_id,
                    inputs=request.inputs,
                    config_overrides=request.config_overrides,
                )

                return ExecutionResponse(
                    execution_id=execution_id,
                    workflow_id=request.workflow_id,
                    status="started",
                    created_at=datetime.now(timezone.utc),
                )
            except Exception as e:
                raise HTTPException(
                    status_code=500,
                    detail=safe_http_detail(
                        e, logger=logger, context="execute workflow"
                    ),
                ) from e

        @self.app.get("/api/executions/{execution_id}")
        async def get_execution_status(execution_id: str, session_id: str):
            """Get execution status."""
            status = await self.agent_ui.get_execution_status(execution_id, session_id)
            if not status:
                raise HTTPException(status_code=404, detail="Execution not found")

            return {
                "execution_id": execution_id,
                "status": status["status"],
                "progress": status.get("progress", 0.0),
                "created_at": status["created_at"].isoformat(),
                "outputs": status.get("outputs", {}),
                "error": status.get("error"),
            }

        @self.app.delete("/api/executions/{execution_id}")
        async def cancel_execution(execution_id: str, session_id: str):
            """Cancel a running execution."""
            await self.agent_ui.cancel_execution(execution_id, session_id)
            return {"message": "Execution cancelled"}

        @self.app.get("/api/executions")
        async def list_executions(session_id: str):
            """List executions for a session."""
            session = await self.agent_ui.get_session(session_id)
            if not session:
                raise HTTPException(status_code=404, detail="Session not found")

            executions = []
            for execution_id, execution in session.executions.items():
                executions.append(
                    {
                        "execution_id": execution_id,
                        "workflow_id": execution["workflow_id"],
                        "status": execution["status"],
                        "progress": execution.get("progress", 0.0),
                        "created_at": execution["created_at"].isoformat(),
                    }
                )

            return {"executions": executions, "total": len(executions)}

    def _setup_schema_routes(self):
        """Setup schema and node discovery routes."""

        @self.app.get("/api/schemas/nodes")
        async def get_node_schemas(request: NodeSchemaRequest = Depends()):
            """Get schemas for available node types."""
            try:
                # Get all registered nodes
                # NodeRegistry doesn't have get_all_nodes, need to use _nodes directly
                available_nodes = {}
                if hasattr(self.node_registry, "_nodes"):
                    available_nodes = self.node_registry._nodes.copy()
                else:
                    # Fallback - return empty dict
                    available_nodes = {}

                # Filter by requested types if specified
                if request.node_types:
                    available_nodes = {
                        name: node_class
                        for name, node_class in available_nodes.items()
                        if name in request.node_types
                    }

                # Generate schemas
                schemas = {}
                for node_name, node_class in available_nodes.items():
                    schema = self.schema_registry.get_node_schema(node_class)
                    schemas[node_name] = schema

                return {
                    "schemas": schemas,
                    "total": len(schemas),
                    "categories": self._get_node_categories(schemas),
                }
            except Exception as e:
                raise HTTPException(
                    status_code=500,
                    detail=safe_http_detail(
                        e, logger=logger, context="get node schemas"
                    ),
                ) from e

        @self.app.get("/api/schemas/nodes/{node_type}")
        async def get_node_schema(node_type: str):
            """Get schema for a specific node type."""
            node_class = self.node_registry.get(node_type)
            if not node_class:
                raise HTTPException(status_code=404, detail="Node type not found")

            schema = self.schema_registry.get_node_schema(node_class)
            return {"node_type": node_type, "schema": schema}

        @self.app.get("/api/schemas/workflows/{workflow_id}")
        async def get_workflow_schema(workflow_id: str, session_id: str):
            """Get schema for a specific workflow."""
            session = await self.agent_ui.get_session(session_id)
            if not session:
                raise HTTPException(status_code=404, detail="Session not found")

            workflow = None
            if workflow_id in session.workflows:
                workflow = session.workflows[workflow_id]
            elif workflow_id in self.agent_ui.shared_workflows:
                workflow = self.agent_ui.shared_workflows[workflow_id]
            else:
                raise HTTPException(status_code=404, detail="Workflow not found")

            schema = self.schema_registry.get_workflow_schema(workflow)
            return {"workflow_id": workflow_id, "schema": schema}

    def _get_node_categories(self, schemas: Dict[str, Any]) -> Dict[str, List[str]]:
        """Group nodes by category."""
        categories = {}
        for node_name, schema in schemas.items():
            category = schema.get("category", "general")
            if category not in categories:
                categories[category] = []
            categories[category].append(node_name)
        return categories

    def _setup_realtime_routes(self):
        """Setup real-time communication routes."""

        @self.app.websocket("/ws")
        async def websocket_endpoint(
            websocket: WebSocket,
            session_id: Optional[str] = None,
            user_id: Optional[str] = None,
            event_types: Optional[str] = None,
        ):
            """WebSocket endpoint for real-time communication."""
            # Parse event types from query parameter
            event_type_list = event_types.split(",") if event_types else None

            await self.realtime.handle_websocket(
                websocket, session_id, user_id, event_type_list
            )

        @self.app.get("/events")
        async def sse_endpoint(
            request: Request,
            session_id: Optional[str] = None,
            user_id: Optional[str] = None,
            event_types: Optional[str] = None,
        ):
            """Server-Sent Events endpoint."""
            event_type_list = event_types.split(",") if event_types else None

            return self.realtime.create_sse_stream(
                request, session_id, user_id, event_type_list
            )

        @self.app.post("/api/webhooks")
        async def register_webhook(request: WebhookRegisterRequest):
            """Register a webhook endpoint."""
            webhook_id = str(uuid.uuid4())

            self.realtime.register_webhook(
                webhook_id=webhook_id,
                url=request.url,
                secret=request.secret,
                event_types=request.event_types,
                headers=request.headers,
            )

            return {
                "webhook_id": webhook_id,
                "url": request.url,
                "event_types": request.event_types,
            }

        @self.app.delete("/api/webhooks/{webhook_id}")
        async def unregister_webhook(webhook_id: str):
            """Unregister a webhook endpoint."""
            self.realtime.unregister_webhook(webhook_id)
            return {"message": "Webhook unregistered"}

    def _setup_monitoring_routes(self):
        """Setup monitoring and statistics routes."""

        @self.app.get("/api/stats")
        async def get_stats():
            """Get comprehensive system statistics."""
            try:
                return {
                    "gateway": {
                        "uptime_seconds": time.time() - self.start_time,
                        "requests_processed": self.requests_processed,
                        "title": self.title,
                        "version": self.version,
                    },
                    "agent_ui": self.agent_ui.get_stats(),
                    "realtime": self.realtime.get_stats(),
                    "schema_registry": self.schema_registry.get_stats(),
                }
            except Exception as e:
                raise HTTPException(
                    status_code=500,
                    detail=safe_http_detail(e, logger=logger, context="get stats"),
                ) from e

        @self.app.get("/api/events/recent")
        async def get_recent_events(
            count: int = 100,
            event_types: Optional[str] = None,
            session_id: Optional[str] = None,
        ):
            """Get recent events with filtering."""
            try:
                # Parse event types
                event_type_list = None
                if event_types:
                    event_type_list = [
                        EventType(t.strip()) for t in event_types.split(",")
                    ]

                # Create filter
                event_filter = EventFilter(
                    event_types=event_type_list, session_id=session_id
                )

                # Get events
                events = await self.agent_ui.event_stream.get_recent_events(
                    count=count, event_filter=event_filter
                )

                return {
                    "events": [event.to_dict() for event in events],
                    "total": len(events),
                    "filters": {
                        "event_types": event_types,
                        "session_id": session_id,
                        "count": count,
                    },
                }
            except Exception as e:
                raise HTTPException(
                    status_code=500,
                    detail=safe_http_detail(
                        e, logger=logger, context="get recent events"
                    ),
                ) from e

    # Public API methods
    def run(
        self, host: str = "127.0.0.1", port: int = 8000, reload: bool = False, **kwargs
    ):
        """Run the API gateway server."""
        import uvicorn

        logger.info(f"Starting {self.title} on {host}:{port}")
        uvicorn.run(self.app, host=host, port=port, reload=reload, **kwargs)

    def mount_existing_app(self, path: str, app: FastAPI):
        """Mount an existing FastAPI app at a specific path."""
        self.app.mount(path, app)
        logger.info(f"Mounted existing app at {path}")

    def register_shared_workflow(
        self, workflow_id: str, workflow: Union[Workflow, WorkflowBuilder]
    ):
        """Register a workflow as shared across all sessions."""
        asyncio.create_task(
            self.agent_ui.register_workflow(
                workflow_id=workflow_id, workflow=workflow, make_shared=True
            )
        )
        logger.info(f"Registered shared workflow: {workflow_id}")


# Convenience function for quick setup
def create_gateway(
    agent_ui_middleware: Optional[AgentUIMiddleware] = None,
    auth_manager=None,
    *,
    require_auth: Optional[bool] = None,
    auth_config: Any = None,
    external_auth_reason: Optional[str] = None,
    auth_exempt_paths: Optional[List[str]] = None,
    **kwargs,
) -> APIGateway:
    """
    Create a configured API gateway instance with dependency injection.

    .. warning::

        This is NOT the same callable as
        :func:`kailash.servers.gateway.create_gateway`, which
        ``from kailash import create_gateway`` resolves to. Both are exported
        under the name ``create_gateway`` -- this one from
        ``kailash.middleware``. They build different gateways with different
        route sets. Prefer the ``kailash.servers`` one unless you specifically
        need the agent-UI middleware surface.

    Every security parameter is NAMED rather than left to ``**kwargs``. When
    ``require_auth`` rode in ``**kwargs`` it could be silently absorbed by a
    typo (``require_authentication=False`` would be accepted and ignored by
    ``APIGateway``), which on a fail-closed gate is the one mistake that must
    not pass quietly.

    Args:
        agent_ui_middleware: Optional existing AgentUIMiddleware instance
        auth_manager: Optional auth manager instance (e.g., JWTAuthManager)
        require_auth: Reject unauthenticated requests. ``None`` (default)
            inherits fail-closed unless ``enable_auth=False`` explicitly opted
            out; ``True`` gates and RAISES when no credential source is
            configured; ``False`` serves openly with a loud WARN (#2072).
        auth_config: Explicit ``kailash.trust.auth.jwt.JWTConfig`` (or dict) for
            the request gate.
        external_auth_reason: Non-empty when an ASGI middleware outside this
            gateway already authenticates every request.
        auth_exempt_paths: Extra paths exempt from the gate.
        **kwargs: Additional arguments for APIGateway initialization

    Returns:
        Configured APIGateway instance

    Example:
        >>> from kailash.middleware.auth import JWTAuthManager
        >>>
        >>> # Create with custom auth. The gate verifies the tokens this
        >>> # manager issues, using the manager's own key.
        >>> auth = JWTAuthManager(use_rsa=True)
        >>> gateway = create_gateway(
        ...     title="My App Gateway",
        ...     cors_origins=["http://localhost:3000"],
        ...     auth_manager=auth
        ... )
        >>>
        >>> # Or use default auth (needs KAILASH_API_GATEWAY_SECRET)
        >>> gateway = create_gateway(title="My App")
        >>>
        >>> gateway.execute(port=8000)
    """
    # Pass auth_manager to APIGateway
    if auth_manager is not None:
        kwargs["auth_manager"] = auth_manager

    gateway = APIGateway(
        require_auth=require_auth,
        auth_config=auth_config,
        external_auth_reason=external_auth_reason,
        auth_exempt_paths=auth_exempt_paths,
        **kwargs,
    )

    if agent_ui_middleware:
        gateway.agent_ui = agent_ui_middleware
        gateway.realtime = RealtimeMiddleware(agent_ui_middleware)

    return gateway
