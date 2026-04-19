"""Kailash Nexus - Zero-Config Multi-Channel Workflow Platform.

Deploy Kailash workflows across API, CLI, and MCP channels with built-in
middleware, CORS, plugins, and preset configurations.

Usage:
    from nexus import Nexus

    # Simple case with CORS
    app = Nexus(cors_origins=["http://localhost:3000"])
    app.register("my_workflow", workflow.build())
    app.start()

    # With preset (one-line middleware stack)
    app = Nexus(preset="lightweight", cors_origins=["http://localhost:3000"])
    app.start()

    # Enterprise features
    app = Nexus(
        preset="saas",
        cors_origins=["https://app.example.com"],
        enable_auth=True,
        enable_monitoring=True,
    )
    app.start()
"""

# Auth symbols — importable from nexus without triggering the nexus.auth
# deprecation warning (SPEC-06 consolidation moves auth to kailash.trust.auth,
# but these re-exports keep the cross-SDK API surface stable).
import warnings as _warnings

from .background import BackgroundService
from .core import (
    MiddlewareInfo,
    MountInfo,
    Nexus,
    NexusPluginProtocol,
    RouterInfo,
    create_nexus,
)
from .engine import EnterpriseMiddlewareConfig, NexusEngine, Preset
from .events import EventBus, NexusEvent, NexusEventType
from .files import NexusFile
from .metrics import register_metrics_endpoint
from .openapi import OpenApiGenerator, OpenApiInfo
from .presets import PRESETS, NexusConfig, PresetConfig, apply_preset, get_preset
from .probes import ProbeManager, ProbeResponse, ProbeState
from .registry import HandlerDef, HandlerParam, HandlerRegistry
from .sse import register_sse_endpoint
from .transports import (
    HTTPTransport,
    MCPTransport,
    Transport,
    WebhookTransport,
    WebSocketTransport,
)
from .websocket_handlers import Connection, MessageHandler, MessageHandlerRegistry

with _warnings.catch_warnings():
    _warnings.simplefilter("ignore", DeprecationWarning)
    from .auth.guards import AuthGuard
    from .auth.plugin import NexusAuthPlugin

# Re-export Starlette types so Nexus consumers can `from nexus import Request, ...`
# instead of importing directly from starlette or fastapi. This allows the
# enforce-framework-first hook to block raw starlette/fastapi imports in
# application code while still providing the types Nexus endpoint handlers need.
from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import JSONResponse, Response, StreamingResponse
from starlette.websockets import WebSocket, WebSocketDisconnect

from .errors import (
    BadGatewayError,
    ConflictError,
    ForbiddenError,
    NexusError,
    NotFoundError,
)
from .errors import PermissionError as NexusPermissionError  # deprecated alias
from .errors import RateLimitError, ServiceUnavailableError
from .errors import TimeoutError as NexusTimeoutError
from .errors import UnauthorizedError, ValidationError
from .http_client import (
    HttpClient,
    HttpClientConfig,
    HttpClientError,
    HttpResponse,
    InvalidEndpointError,
)
from .outbound import post_webhook, probe_remote_health
from .service_client import (
    ServiceClient,
    ServiceClientDeserializeError,
    ServiceClientError,
    ServiceClientHttpError,
    ServiceClientHttpStatusError,
    ServiceClientInvalidHeaderError,
    ServiceClientInvalidPathError,
    ServiceClientSerializeError,
)
from .typed_service_client import Decoder, TypedServiceClient

__version__ = "2.1.1"
__all__ = [
    # Core
    "Nexus",
    "create_nexus",
    # Transport Layer
    "Transport",
    "HTTPTransport",
    "MCPTransport",
    "WebhookTransport",
    "WebSocketTransport",
    # Handler Registry
    "HandlerDef",
    "HandlerParam",
    "HandlerRegistry",
    # Event System
    "EventBus",
    "NexusEvent",
    "NexusEventType",
    # Background Services
    "BackgroundService",
    # Files
    "NexusFile",
    # Engine (cross-SDK parity with kailash-rs)
    "NexusEngine",
    "Preset",
    "EnterpriseMiddlewareConfig",
    # Middleware API
    "MiddlewareInfo",
    "RouterInfo",
    "NexusPluginProtocol",
    # Preset System
    "NexusConfig",
    "PresetConfig",
    "PRESETS",
    "get_preset",
    "apply_preset",
    # Kubernetes Probes
    "ProbeManager",
    "ProbeState",
    "ProbeResponse",
    # OpenAPI
    "OpenApiGenerator",
    "OpenApiInfo",
    # Metrics & SSE
    "register_metrics_endpoint",
    "register_sse_endpoint",
    # Class-based WebSocket message handlers (issue #448)
    "Connection",
    "MessageHandler",
    "MessageHandlerRegistry",
    # Auth (cross-SDK: kailash-rs#389)
    "NexusAuthPlugin",
    "AuthGuard",
    # Typed Errors (cross-SDK: kailash-rs#389)
    "NexusError",
    "ValidationError",
    "NotFoundError",
    "ConflictError",
    "UnauthorizedError",
    "ForbiddenError",  # canonical name for 403
    "NexusPermissionError",  # deprecated alias for ForbiddenError
    "RateLimitError",
    "ServiceUnavailableError",
    "BadGatewayError",
    "NexusTimeoutError",
    # Starlette type re-exports for endpoint handlers
    "HTTPException",
    "Request",
    "Response",
    "JSONResponse",
    "StreamingResponse",
    "WebSocket",
    "WebSocketDisconnect",
    # Outbound HTTP primitive (issue #464 + cross-SDK kailash-rs#399)
    "HttpClient",
    "HttpClientConfig",
    "HttpClientError",
    "HttpResponse",
    "InvalidEndpointError",
    # Typed service-to-service client (issue #473 + cross-SDK kailash-rs#400)
    "ServiceClient",
    "ServiceClientError",
    "ServiceClientHttpError",
    "ServiceClientHttpStatusError",
    "ServiceClientSerializeError",
    "ServiceClientDeserializeError",
    "ServiceClientInvalidPathError",
    "ServiceClientInvalidHeaderError",
    # Typed-model service client (issue #465 + cross-SDK kailash-rs#400)
    "TypedServiceClient",
    "Decoder",
    # Outbound helpers (internal + user-facing producers of HttpClient /
    # ServiceClient call sites — see nexus/outbound.py)
    "post_webhook",
    "probe_remote_health",
]
