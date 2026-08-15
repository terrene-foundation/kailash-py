"""
Enhanced API Gateway for Kailash Middleware

Provides a comprehensive API gateway that integrates agent-UI middleware,
real-time communication, and dynamic workflow management with full
frontend support capabilities.
"""

import asyncio
import inspect
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
        # Kept, because it is also the IDENTITY policy and not only the gate
        # policy: a deployment that authenticates its requests must never take
        # a principal from a request field (issue #2102). Read by
        # `_resolve_identity`.
        self._require_auth = resolved_require_auth
        if not resolved_require_auth:
            self._warn_session_ownership_unenforced()
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

    async def _authenticated_user_id(self, connection: Any) -> Optional[str]:
        """The SERVER-DERIVED principal for one HTTP request or WS handshake.

        THE single place this gateway answers "who is calling". Every route
        that has an identity to establish calls it -- ``POST /api/sessions``,
        ``/ws`` and ``/events`` -- so there is one derivation and one policy
        rather than three (``security.md`` § Credential Decode Helpers).

        Two sources, in order, and NEITHER of them is a request field:

        1. **The installed gate's answer.** When ``require_auth`` resolves True
           this gateway installs
           :class:`~kailash.trust.auth.asgi.JWTAuthMiddleware` (HTTP) and
           :class:`~kailash.trust.auth.asgi.JWTWebSocketAuthMiddleware`
           (websocket), each of which verifies the credential and leaves an
           :class:`~kailash.trust.auth.models.AuthenticatedUser` on
           ``scope["state"]["user"]``. Re-verifying it here would be a second
           implementation of a decision already made.
        2. **A direct verification**, for the deployments where NO gate is
           installed -- ``require_auth=False``, or ``external_auth_reason``
           naming an outside ASGI layer, or a path the operator exempted. A
           presented bearer token is verified with this gateway's own auth
           manager, which is the issuer of the tokens it accepts.

        ``verify_token`` is called and its result awaited ONLY IF awaitable.
        The two managers in this SDK disagree: ``JWTAuthManager.verify_token``
        is SYNC and ``MiddlewareAuthManager.verify_token`` is ASYNC. The
        previous revision awaited unconditionally, so with the manager this
        class constructs by DEFAULT every verification raised
        ``TypeError: object dict can't be used in 'await' expression``, was
        caught by the handler below, and resolved to "no principal" -- which
        is how a valid bearer token lost to a POST body field (issue #2102).

        Returns:
            The principal's id, or ``None`` when no credential could be
            resolved. Never raises: the REFUSAL decision belongs to
            :meth:`_resolve_identity`, which knows whether this deployment
            authenticates at all.
        """
        state = getattr(connection, "state", None)
        user = getattr(state, "user", None) if state is not None else None
        if user is not None:
            user_id = getattr(user, "user_id", None)
            if isinstance(user_id, str) and user_id:
                return user_id
            # A gate-verified principal with no usable subject cannot happen
            # through `create_user_from_payload` (it raises first), so this is
            # a foreign middleware's object. Loud, and it falls through to the
            # direct verification rather than being treated as an identity.
            logger.warning(
                "api_gateway.authenticated_user_without_subject",
                extra={"user_type": type(user).__name__},
            )

        manager = getattr(self, "auth_manager", None)
        if manager is None:
            return None

        scheme, _, token = (
            (connection.headers.get("Authorization") or "").partition(" ")
            if getattr(connection, "headers", None) is not None
            else ("", "", "")
        )
        if scheme.lower() != "bearer" or not token:
            return None

        try:
            payload = manager.verify_token(token)
            if inspect.isawaitable(payload):
                payload = await payload
        except HTTPException:
            # A REJECTED credential, not an absent one. Logged rather than
            # swallowed silently (`zero-tolerance.md` Rule 3); the caller is
            # then unauthenticated, and `_resolve_identity` decides what that
            # means for this deployment.
            logger.warning("api_gateway.presented_token_rejected")
            return None
        except Exception as exc:
            logger.warning(
                "api_gateway.token_verification_failed",
                extra={"error_type": type(exc).__name__},
            )
            return None

        if not isinstance(payload, dict):
            logger.warning(
                "api_gateway.verify_token_returned_non_mapping",
                extra={"payload_type": type(payload).__name__},
            )
            return None

        # A REFRESH token is NOT an access credential, and this path is the
        # only place in the gateway that could have treated it as one.
        # `JWTValidator.verify_token` — the gate's verifier — already refuses
        # it (`trust/auth/jwt.py`, "Refresh tokens cannot be used for API
        # authentication"), but NEITHER middleware manager does:
        # `auth_manager.py` never mentions `token_type`, and `jwt_auth.py`
        # only reads it in `refresh_access_token`, checking the OPPOSITE
        # direction. So the two verification surfaces disagreed, and this one
        # was the permissive half (`security.md` § Enforcement-Surface Parity).
        #
        # Reachable ONLY where this direct path IS the identity source — a
        # deployment with no gate installed here (`external_auth_reason=`, an
        # exempted path, `require_auth=False`). Measured before this fix:
        #
        #     DEFAULT (gate installed)      -> 401  (the gate refused it)
        #     external_auth_reason          -> 200  as the refresh token's subject
        #     require_auth=False            -> 200  as the refresh token's subject
        #
        # A refresh token lives for `refresh_token_expire_days` (7 by default)
        # and is the credential most likely to sit in cookie storage or a
        # client log, so accepting it here turns a long-lived exchange token
        # into a session-opening one on exactly the deployments that cannot
        # fall back on the gate.
        if payload.get("token_type") == "refresh":
            logger.warning("api_gateway.refresh_token_presented_as_access")
            return None

        from ...trust.auth.jwt import subject_from_claims

        return subject_from_claims(payload)

    async def _resolve_identity(
        self, connection: Any, caller_supplied: Optional[str]
    ) -> Optional[str]:
        """Decide whose identity a request acts under, fail-closed.

        The rule, one line: **a deployment that authenticates its requests
        never takes a principal from a request field.**

        * A server-derived principal ALWAYS wins, including over a body or
          query value that disagrees with it.
        * With no principal and ``require_auth`` resolved True, this RAISES
          401. It does not fall back. Falling back is the whole defect: it let
          an unauthenticated caller open a session under any name it chose
          (issue #2102, the same class as #2047).

          SCOPED CLAIM, deliberately. This closes identity DERIVATION — who a
          request acts AS, at the routes that MINT or FILTER by an identity.
          It does NOT close what an authenticated principal may act ON: every
          route taking a caller-supplied ``session_id`` still acts on it
          without checking who owns that session, so an authenticated caller
          can still act as somebody else THERE. That is horizontal
          authorization, a different class with a different fix, tracked as
          issue #2145 — do not read this docstring as closing it.
        * With no principal and authentication explicitly opted OUT
          (``require_auth=False``, or ``enable_auth=False`` which is the older
          spelling of the same statement), the caller-supplied value stands.
          That is this route's documented contract for an open deployment, and
          `resolve_server_auth` has already logged that exposure loudly at
          construction.

        Raises:
            HTTPException: 401, when this deployment authenticates requests and
                no principal could be derived for this one.
        """
        principal = await self._authenticated_user_id(connection)
        if principal:
            return principal

        if self._require_auth:
            raise HTTPException(
                status_code=401,
                detail=(
                    "Authentication required: this gateway authenticates "
                    "requests, so the identity for this operation must come "
                    "from a verified credential and cannot be read from the "
                    "request. Present a bearer token, or construct the "
                    "gateway with require_auth=False to serve openly."
                ),
            )

        return caller_supplied

    async def _require_session_owner(
        self, connection: Any, session_id: str
    ) -> Optional[str]:
        """Fail closed unless the caller OWNS ``session_id``.

        THE single ownership predicate for this gateway. Every session-scoped
        route calls it, so there is one rule rather than twelve inline
        comparisons that drift (issue #2145; the same consolidation argument
        as `_resolve_identity` and `subject_from_claims`).

        #2102 answered "who is calling". This answers the adjacent question it
        does NOT answer: **what may that caller act on**. Every route here
        takes a caller-supplied ``session_id`` and acted on it without ever
        comparing the session's owner against the caller, even though
        ``WorkflowSession.user_id`` has always carried that owner. Measured
        before the fix, both parties holding valid tokens this gateway
        itself minted::

            POST /api/workflows?session_id=<alice>   as bob -> 200
            POST /api/executions?session_id=<alice>  as bob -> 200

        which is authenticated arbitrary code execution inside another user's
        session, since the workflow body is caller-authored `PythonCodeNode`
        source.

        The four outcomes, in order:

        1. **Open deployment** (``require_auth`` resolved False -- i.e.
           ``require_auth=False`` or ``enable_auth=False``). The check is
           SKIPPED, deliberately and as an explicit branch rather than as a
           side effect of there being no principal to compare. Such a
           deployment has no identities at all, so there is nothing an
           ownership rule could mean; the exposure is announced once at
           construction by ``_warn_session_ownership_unenforced``.
        2. **No principal** on a gated deployment -> 401, via
           :meth:`_resolve_identity`, which owns that decision.
        3. **Unclaimed session** -- the owner is empty or ``None`` -> 403.
           This is legacy state: since #2102 every session created carries a
           server-derived owner, so an ownerless one predates that fix.
           Treating an empty owner as a wildcard that matches every caller
           would be the silent-fallback shape (`zero-tolerance.md` Rule 3) and
           would quietly re-open exactly what this closes.
        4. **Someone else's session** -> 404, NOT 403, and the difference is
           deliberate. 403 would confirm that a session id exists, turning
           every route here into a membership oracle over session ids. The
           unclaimed case above answers 403 because it is an operator-facing
           condition about the server's own legacy state, and reaching it
           requires already holding a valid session id -- it tells an attacker
           nothing it did not already know.

        Args:
            connection: The HTTP request or WebSocket handshake.
            session_id: The caller-supplied session identifier.

        Returns:
            The principal that owns the session, or ``None`` on an open
            deployment where no ownership rule applies.

        Raises:
            HTTPException: 401 (no principal), 403 (unclaimed session), or 404
                (unknown session, or one owned by somebody else).
        """
        if not self._require_auth:
            return None

        principal = await self._resolve_identity(connection, None)

        session = await self.agent_ui.get_session(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

        owner = getattr(session, "user_id", None)
        if not isinstance(owner, str) or not owner:
            logger.warning(
                "api_gateway.session_without_owner",
                extra={"session_id": sanitize_log_value(session_id, 128)},
            )
            raise HTTPException(
                status_code=403,
                detail=(
                    "This session has no recorded owner and cannot be acted "
                    "on while the gateway authenticates requests. Sessions "
                    "created before server-derived identity landed carry no "
                    "owner; create a new session, or run the gateway with "
                    "require_auth=False if it is meant to serve openly."
                ),
            )

        if owner != principal:
            # Logged with BOTH ids so an operator can see the attempt; the
            # CLIENT is told only that there is no such session.
            logger.warning(
                "api_gateway.session_ownership_denied",
                extra={
                    "session_id": sanitize_log_value(session_id, 128),
                    "principal": sanitize_log_value(principal, 128),
                },
            )
            raise HTTPException(status_code=404, detail="Session not found")

        return principal

    def _warn_session_ownership_unenforced(self) -> None:
        """Announce, once per gateway, that session ownership is not enforced.

        Separate from `resolve_server_auth`'s own `server_auth.disabled` WARN
        because it names a DIFFERENT protection. That one says requests are
        not authenticated; this one says any caller may drive any session --
        including executing workflows in it -- which is the consequence an
        operator actually needs to weigh (`security.md` § Secure-Default:
        a control that is off must say so loudly and name its wiring).
        """
        logger.warning(
            "api_gateway.session_ownership_unenforced",
            extra={
                "reason": (
                    "require_auth resolved False, so no principal exists to "
                    "own a session"
                ),
                "exposure": (
                    "any caller may read, drive and close any session, "
                    "including POST /api/executions which runs workflows in it"
                ),
                "wiring": "construct with require_auth=True to enforce ownership",
            },
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

        # NO `X-API-Key` BRANCH ON THIS ROUTE, deliberately.
        #
        # A first draft added one, calling `auth_manager.verify_api_key`. That
        # method CANNOT SUCCEED, which was measured rather than assumed: it
        # calls `credential_manager.execute(operation=..., credential_name=...)`,
        # but `CredentialManagerNode.run()` takes `**inputs` and ignores BOTH --
        # it reads `self.credential_name`, fixed at construction -- and its
        # return dict has no `"success"` key at all. So
        # `result.get("success", False)` is always False and the call always
        # raises 401. An auth path that can only ever reject is a non-functional
        # feature presented as a working one (`zero-tolerance.md` Rule 2), so it
        # is not shipped. API keys DO work on this gateway, through the
        # installed gate's own `api_key_validator`, which is a real
        # implementation; the `verify_api_key` defect is pre-existing and
        # tracked separately.

        @self.app.post("/api/sessions", response_model=SessionResponse)
        async def create_session(
            request: SessionCreateRequest,
            http_request: Request,
        ):
            """Create a new session for a frontend client."""
            try:
                # The identity is SERVER-DERIVED or the request is REFUSED.
                # `request.user_id` is a POST body field and survives only on a
                # deployment that explicitly opted out of authentication.
                user_id = await self._resolve_identity(http_request, request.user_id)

                session_id = await self.agent_ui.create_session(
                    user_id=user_id or "", metadata=request.metadata
                )

                session = await self.agent_ui.get_session(session_id)
                self.requests_processed += 1

                # Log session creation. ``user_id`` is caller-controlled on an
                # open deployment: `_resolve_identity` returns the POST body
                # value verbatim when authentication was explicitly opted out.
                # Interpolated, an embedded newline forges a second well-formed
                # log record (issue #2040).
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
                # A deliberate status -- the 401 `_resolve_identity` raises
                # when no principal could be derived -- must reach the client
                # as itself. The `except Exception` below would otherwise
                # relabel every auth refusal on this route as a 500, hiding the
                # refusal and reporting a server fault for a client error.
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
        async def get_session(session_id: str, http_request: Request):
            """Get session information."""
            await self._require_session_owner(http_request, session_id)

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
        async def close_session(session_id: str, http_request: Request):
            """Close a session."""
            await self._require_session_owner(http_request, session_id)

            await self.agent_ui.close_session(session_id)
            return {"message": "Session closed"}

        @self.app.get("/api/sessions")
        async def list_sessions(http_request: Request):
            """List the caller's active sessions.

            SCOPED to the caller, where it used to enumerate every session on
            the gateway with its owner's `user_id`. That listing was not merely
            an information leak in its own right -- it was the TARGET DIRECTORY
            for the rest of #2145: the other eleven routes need a `session_id`
            they do not otherwise possess, and this handed out every one of
            them, already labelled with whose it was.

            On an open deployment (`require_auth` resolved False) there are no
            identities, so the unscoped listing remains -- that is the same
            explicit branch every other route here takes, not an oversight.
            """
            principal = (
                await self._resolve_identity(http_request, None)
                if self._require_auth
                else None
            )

            sessions = []
            for session_id, session in self.agent_ui.sessions.items():
                if not session.active:
                    continue
                # `principal is None` ONLY on an open deployment: on a gated
                # one `_resolve_identity` raised 401 rather than returning it.
                if principal is not None and session.user_id != principal:
                    continue
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
        async def create_workflow(
            request: WorkflowCreateRequest, session_id: str, http_request: Request
        ):
            """Create a new workflow dynamically."""
            # BEFORE the try: an ownership refusal is a deliberate status and
            # must not be relabelled a 500 by the handler below.
            await self._require_session_owner(http_request, session_id)
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
        async def get_workflow(
            workflow_id: str, session_id: str, http_request: Request
        ):
            """Get workflow information and schema."""
            await self._require_session_owner(http_request, session_id)

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
        async def list_workflows(
            http_request: Request, session_id: Optional[str] = None
        ):
            """List available workflows.

            `session_id` is OPTIONAL here, so the ownership check is too --
            but only in the sense that there is nothing to own when it is
            absent. Supplying another user's id is refused exactly as it is on
            the routes where it is required; without one, the caller sees only
            the SHARED workflows, which are shared by construction.
            """
            if session_id:
                await self._require_session_owner(http_request, session_id)

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
        async def execute_workflow(
            request: WorkflowExecuteRequest, session_id: str, http_request: Request
        ):
            """Execute a workflow."""
            # THE site the #2145 attack trace ends at: the workflow body is
            # caller-authored `PythonCodeNode` source, so an unowned execution
            # here is arbitrary code execution in someone else's session.
            # Outside the try, so the refusal is not relabelled a 500.
            await self._require_session_owner(http_request, session_id)
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
        async def get_execution_status(
            execution_id: str, session_id: str, http_request: Request
        ):
            """Get execution status."""
            await self._require_session_owner(http_request, session_id)

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
        async def cancel_execution(
            execution_id: str, session_id: str, http_request: Request
        ):
            """Cancel a running execution."""
            await self._require_session_owner(http_request, session_id)

            await self.agent_ui.cancel_execution(execution_id, session_id)
            return {"message": "Execution cancelled"}

        @self.app.get("/api/executions")
        async def list_executions(session_id: str, http_request: Request):
            """List executions for a session."""
            await self._require_session_owner(http_request, session_id)

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
        async def get_workflow_schema(
            workflow_id: str, session_id: str, http_request: Request
        ):
            """Get schema for a specific workflow."""
            await self._require_session_owner(http_request, session_id)

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
            """WebSocket endpoint for real-time communication.

            ``user_id`` is a SUBSCRIPTION FILTER, not a label: it is handed to
            ``EventFilter`` and decides which users' events this socket
            receives. Taken from the query string it let any caller subscribe
            to another user's event stream, so it is resolved the same way the
            session route resolves its identity (issue #2102 sibling sweep).
            """
            # Parse event types from query parameter
            event_type_list = event_types.split(",") if event_types else None

            try:
                resolved_user_id = await self._resolve_identity(websocket, user_id)
                # `session_id` is the OTHER caller-supplied selector on this
                # route, and #2139's `user_id` pin does not cover it:
                # `ConnectionManager.send_to_session` walks
                # `session_connections[session_id]` and calls
                # `send_to_connection` DIRECTLY, never evaluating the
                # `EventFilter`. So subscribing with another user's session id
                # delivered that session's traffic regardless of the pinned
                # user. Measured before this fix -- alice, authenticated as
                # alice, on `?session_id=<bob's session>`::
                #
                #     send_to_session(bob) delivered to 1 connection(s)
                #     ALICE'S SOCKET RECEIVED: {"body": "bob-session-only payload"}
                if session_id:
                    await self._require_session_owner(websocket, session_id)
            except HTTPException:
                # A websocket cannot carry a 401. 1008 is POLICY VIOLATION,
                # sent WITHOUT `accept()` so the handshake is refused outright
                # rather than accepted and then torn down.
                #
                # The `receive()` mirrors `JWTWebSocketAuthMiddleware._deny`
                # and is not decoration: the ASGI spec has the server send
                # `websocket.connect` before the application may reply, and
                # while uvicorn tolerates a close without it, hypercorn,
                # daphne and the wsproto implementation are stricter -- a
                # refusal that only fails closed on one server is not a
                # refusal. Wrapped because the peer can vanish between the
                # server queuing `connect` and this read; the close below is
                # then a no-op and turning that into a 500 would convert a
                # disconnect into a server fault.
                logger.warning("api_gateway.websocket_identity_unresolved")
                try:
                    await websocket.receive()
                except Exception:
                    logger.debug(
                        "api_gateway.websocket_connect_event_unavailable",
                        exc_info=True,
                    )
                await websocket.close(code=1008)
                return

            await self.realtime.handle_websocket(
                websocket, session_id, resolved_user_id, event_type_list
            )

        @self.app.get("/events")
        async def sse_endpoint(
            request: Request,
            session_id: Optional[str] = None,
            user_id: Optional[str] = None,
            event_types: Optional[str] = None,
        ):
            """Server-Sent Events endpoint.

            ``user_id`` is the same subscription filter as on ``/ws`` and is
            resolved the same way: from the verified credential, never from the
            query string (issue #2102 sibling sweep).
            """
            event_type_list = event_types.split(",") if event_types else None
            resolved_user_id = await self._resolve_identity(request, user_id)
            # Same second selector as `/ws`, same reason: the SSE manager
            # tracks streams by `session_id` independently of the filter.
            if session_id:
                await self._require_session_owner(request, session_id)

            return self.realtime.create_sse_stream(
                request, session_id, resolved_user_id, event_type_list
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
            http_request: Request,
            count: int = 100,
            event_types: Optional[str] = None,
            session_id: Optional[str] = None,
        ):
            """Get recent events with filtering.

            Two changes, and the second is the one that matters. With a
            `session_id` the ownership check applies as everywhere else.
            WITHOUT one this returned every user's recent events to any
            authenticated caller -- the #2151 confidentiality defect at the
            REST surface rather than the websocket one -- so the filter is now
            pinned to the caller's own `user_id`.

            That filter also excludes events carrying NO `user_id`, and that
            is the intended direction: an event this gateway cannot attribute
            to the caller is not one to hand them (`EventFilter.matches`
            rejects on `event.user_id != self.user_id`).
            """
            # Outside the try: an ownership refusal is a deliberate status and
            # must reach the client rather than becoming a 500 below.
            principal = None
            if self._require_auth:
                principal = (
                    await self._require_session_owner(http_request, session_id)
                    if session_id
                    else await self._resolve_identity(http_request, None)
                )
            try:
                # Parse event types
                event_type_list = None
                if event_types:
                    event_type_list = [
                        EventType(t.strip()) for t in event_types.split(",")
                    ]

                # Create filter
                event_filter = EventFilter(
                    event_types=event_type_list,
                    session_id=session_id,
                    user_id=principal,
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
