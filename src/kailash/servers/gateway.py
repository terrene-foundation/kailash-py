"""Gateway creation utilities with enterprise defaults.

This module provides the main create_gateway function that creates
production-ready servers with enterprise features enabled by default.
"""

import logging
from typing import Any, List, Optional

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
    # Enterprise features (enabled by default)
    enable_durability: bool = True,
    enable_resource_management: bool = True,
    enable_async_execution: bool = True,
    enable_health_checks: bool = True,
    # Enterprise components
    resource_registry: Optional[ResourceRegistry] = None,
    secret_manager: Optional[SecretManager] = None,
    # Backward compatibility
    **kwargs,
) -> EnterpriseWorkflowServer:
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
        enable_durability: Enable request durability features
        enable_resource_management: Enable resource registry
        enable_async_execution: Enable async workflow execution
        enable_health_checks: Enable comprehensive health checks
        resource_registry: Optional ResourceRegistry instance
        secret_manager: Optional SecretManager instance
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
    return create_gateway(server_type="enterprise", **kwargs)


def create_durable_gateway(**kwargs) -> DurableWorkflowServer:
    """Create durable workflow server without full enterprise features.

    This creates a server with durability features but without resource
    management and other enterprise capabilities.
    """
    return create_gateway(server_type="durable", **kwargs)


def create_basic_gateway(**kwargs) -> WorkflowServer:
    """Create basic workflow server for development/testing.

    This creates a minimal server without durability or enterprise features.
    Suitable for development and testing scenarios.
    """
    return create_gateway(server_type="basic", **kwargs)


# Backward compatibility - maintain the existing create_gateway signature
# but issue deprecation warning for old usage patterns
def create_gateway_legacy(agent_ui_middleware=None, auth_manager=None, **kwargs):
    """Legacy create_gateway function for backward compatibility.

    This function maintains compatibility with the old APIGateway-based
    create_gateway function. New code should use the new create_gateway()
    function which creates EnterpriseWorkflowServer by default.
    """
    import warnings

    warnings.warn(
        "Legacy create_gateway usage detected. Consider migrating to the new "
        "create_gateway() function which creates EnterpriseWorkflowServer by default. "
        "See migration guide for details.",
        DeprecationWarning,
        stacklevel=2,
    )

    # For now, delegate to the old APIGateway implementation
    from ..middleware.communication.api_gateway import (
        create_gateway as old_create_gateway,
    )

    return old_create_gateway(
        agent_ui_middleware=agent_ui_middleware, auth_manager=auth_manager, **kwargs
    )
