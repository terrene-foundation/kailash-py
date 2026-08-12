"""Gateway creation utilities with enterprise defaults.

This module provides the main create_gateway function that creates
production-ready servers with enterprise features enabled by default.
"""

import logging
from typing import Any, Awaitable, Callable, List, Optional

from ..gateway.security import SecretManager
from ..resources.registry import ResourceRegistry
from .durable_workflow_server import DurableWorkflowServer
from .enterprise_workflow_server import EnterpriseWorkflowServer
from .workflow_server import WorkflowServer

logger = logging.getLogger(__name__)


def create_gateway(
    title: str = "Kailash Enterprise Gateway",
    description: str = "Production-ready workflow server with enterprise features",
    version: str = "1.0.0",
    # Server type selection
    server_type: str = "enterprise",  # "enterprise", "durable", "basic"
    # Basic configuration
    max_workers: int = 20,
    cors_origins: Optional[List[str]] = None,
    # Server-wide authentication (#2072) -- NAMED, never **kwargs. Threading
    # these through **kwargs is what let `enable_auth=True` be documented and
    # silently discarded (zero-tolerance.md Rule 3c); a named parameter makes
    # a typo a TypeError instead of an open server.
    require_auth: bool = True,
    auth_config: Any = None,
    external_auth_reason: Optional[str] = None,
    auth_exempt_paths: Optional[List[str]] = None,
    # Enterprise features (enabled by default)
    enable_durability: bool = True,
    enable_resource_management: bool = True,
    enable_async_execution: bool = True,
    enable_health_checks: bool = True,
    # Enterprise components
    resource_registry: Optional[ResourceRegistry] = None,
    secret_manager: Optional[SecretManager] = None,
    # Lifespan hooks (run inside FastAPI lifespan / uvicorn loop)
    startup_hook: Optional[Callable[[], Awaitable[None]]] = None,
    shutdown_hook: Optional[Callable[[], Awaitable[None]]] = None,
    startup_hook_timeout: Optional[float] = None,
    # Backward compatibility
    **kwargs,
) -> WorkflowServer:
    """Create a production-ready workflow server.

    By default, creates an EnterpriseWorkflowServer with all enterprise
    features enabled. This is the recommended configuration for production
    deployments.

    Args:
        title: Server title for documentation
        description: Server description
        version: Server version
        server_type: Type of server to create ("enterprise", "durable", "basic")
        max_workers: Maximum thread pool workers (default: 20 for enterprise)
        cors_origins: Allowed CORS origins
        require_auth: Whether every request must be authenticated.
            **Defaults to ``True`` (fail-closed). This is a BREAKING change**:
            a ``create_gateway()`` with no credential source now raises
            :class:`~kailash.utils.server_auth.ServerAuthNotConfiguredError`
            at construction instead of serving anonymous workflow execution
            on ``POST /workflows/{name}/execute`` (issue #2072). Configure
            ``KAILASH_JWT_SECRET`` / ``KAILASH_API_KEY_<NAME>``, pass
            ``auth_config=``, or opt out explicitly with
            ``require_auth=False``.
        auth_config: Explicit ``JWTConfig`` (or field ``dict``) to
            authenticate with, bypassing environment lookup.
        external_auth_reason: Non-empty string declaring that an ASGI
            middleware outside this server authenticates every request, so
            this server installs none.
        auth_exempt_paths: Extra paths exempt from authentication.
        enable_durability: Enable request durability features
        enable_resource_management: Enable resource registry
        enable_async_execution: Enable async workflow execution
        enable_health_checks: Enable comprehensive health checks
        resource_registry: Optional ResourceRegistry instance
        secret_manager: Optional SecretManager instance
        startup_hook: Optional async callback awaited inside uvicorn's event
            loop during FastAPI lifespan startup. Runs after ``router.startup()``
            fires but BEFORE the server accepts requests. Background tasks
            created here survive for the server's lifetime.
        shutdown_hook: Optional async callback awaited inside uvicorn's event
            loop during FastAPI lifespan shutdown. Runs AFTER the server stops
            accepting requests but BEFORE ``router.shutdown()`` and the
            ShutdownCoordinator. Exceptions are logged at WARN and never
            prevent router/coordinator cleanup.
        startup_hook_timeout: Optional seconds to wait for ``startup_hook``
            before timing out. ``None`` (default) waits indefinitely. A finite
            value defends against a hung plugin pinning uvicorn's lifespan
            and preventing it from accepting connections.
        **kwargs: Additional arguments passed to server constructor

    Returns:
        Configured workflow server instance

    Examples:
        >>> # Enterprise server with all features (recommended)
        >>> gateway = create_gateway()

        >>> # Enterprise server with custom configuration
        >>> gateway = create_gateway(
        ...     title="My Application",
        ...     cors_origins=["http://localhost:3000"],
        ...     max_workers=50
        ... )

        >>> # Durable server without full enterprise features
        >>> gateway = create_gateway(
        ...     server_type="durable",
        ...     enable_resource_management=False
        ... )

        >>> # Basic server for development
        >>> gateway = create_gateway(
        ...     server_type="basic",
        ...     enable_durability=False
        ... )
    """
    # Log server creation
    logger.info(f"Creating {server_type} workflow server: {title}")

    # Common configuration
    common_config = {
        "title": title,
        "description": description,
        "version": version,
        "max_workers": max_workers,
        "cors_origins": cors_origins,
        "require_auth": require_auth,
        "auth_config": auth_config,
        "external_auth_reason": external_auth_reason,
        "auth_exempt_paths": auth_exempt_paths,
        "startup_hook": startup_hook,
        "shutdown_hook": shutdown_hook,
        "startup_hook_timeout": startup_hook_timeout,
        **kwargs,
    }

    # Create server based on type
    if server_type == "enterprise":
        server = EnterpriseWorkflowServer(
            enable_durability=enable_durability,
            enable_resource_management=enable_resource_management,
            enable_async_execution=enable_async_execution,
            enable_health_checks=enable_health_checks,
            resource_registry=resource_registry,
            secret_manager=secret_manager,
            **common_config,
        )

    elif server_type == "durable":
        server = DurableWorkflowServer(
            enable_durability=enable_durability, **common_config
        )

    elif server_type == "basic":
        server = WorkflowServer(**common_config)

    else:
        raise ValueError(f"Unknown server type: {server_type}")

    logger.info(
        f"Created {type(server).__name__} with features: durability={enable_durability}, "
        f"resources={enable_resource_management}, async={enable_async_execution}"
    )

    return server


def create_enterprise_gateway(**kwargs) -> EnterpriseWorkflowServer:
    """Create enterprise workflow server (explicit enterprise features).

    This is an alias for create_gateway(server_type="enterprise") that makes
    it explicit that enterprise features are desired.
    """
    server = create_gateway(server_type="enterprise", **kwargs)
    assert isinstance(server, EnterpriseWorkflowServer)
    return server


def create_durable_gateway(**kwargs) -> DurableWorkflowServer:
    """Create durable workflow server without full enterprise features.

    This creates a server with durability features but without resource
    management and other enterprise capabilities.
    """
    server = create_gateway(server_type="durable", **kwargs)
    assert isinstance(server, DurableWorkflowServer)
    return server


def create_basic_gateway(**kwargs) -> WorkflowServer:
    """Create basic workflow server for development/testing.

    This creates a minimal server without durability or enterprise features.
    Suitable for development and testing scenarios.
    """
    return create_gateway(server_type="basic", **kwargs)
