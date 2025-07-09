"""Factory functions for creating Nexus Gateway instances."""

import logging
from typing import Any, Dict, List, Optional, Union

from ..workflow import Workflow
from .gateway import NexusConfig, NexusGateway

logger = logging.getLogger(__name__)


def create_nexus(
    name: Optional[str] = None,
    description: Optional[str] = None,
    # Channel configuration
    enable_api: bool = True,
    enable_cli: bool = True,
    enable_mcp: bool = True,
    # API settings
    api_host: str = "localhost",
    api_port: int = 8000,
    api_cors_origins: Optional[List[str]] = None,
    # CLI settings
    cli_interactive: bool = False,
    cli_prompt: str = "nexus> ",
    # MCP settings
    mcp_host: str = "localhost",
    mcp_port: int = 3001,
    mcp_server_name: Optional[str] = None,
    # Session management
    session_timeout: int = 3600,
    session_cleanup_interval: int = 300,
    # Event routing
    enable_event_routing: bool = True,
    event_queue_size: int = 10000,
    # Advanced settings
    enable_health_monitoring: bool = True,
    health_check_interval: int = 30,
    graceful_shutdown_timeout: int = 30,
    # Initial workflows
    workflows: Optional[Dict[str, Workflow]] = None,
    # Custom configuration
    **kwargs,
) -> NexusGateway:
    """Create a Nexus Gateway with the specified configuration.

    This is the main entry point for creating a Nexus Gateway instance
    with sensible defaults for different use cases.

    Args:
        name: Gateway name (defaults to "kailash-nexus")
        description: Gateway description

        # Channel Configuration
        enable_api: Enable HTTP API channel
        enable_cli: Enable CLI channel
        enable_mcp: Enable MCP channel

        # API Channel Settings
        api_host: API server host
        api_port: API server port
        api_cors_origins: CORS origins for API

        # CLI Channel Settings
        cli_interactive: Enable interactive CLI mode
        cli_prompt: CLI prompt template

        # MCP Channel Settings
        mcp_host: MCP server host
        mcp_port: MCP server port
        mcp_server_name: MCP server name

        # Session Management
        session_timeout: Session timeout in seconds
        session_cleanup_interval: Session cleanup interval in seconds

        # Event Routing
        enable_event_routing: Enable cross-channel event routing
        event_queue_size: Event queue size

        # Advanced Settings
        enable_health_monitoring: Enable background health monitoring
        health_check_interval: Health check interval in seconds
        graceful_shutdown_timeout: Graceful shutdown timeout in seconds

        # Initial Workflows
        workflows: Dictionary of workflows to register initially

        # Custom Configuration
        **kwargs: Additional configuration options

    Returns:
        Configured NexusGateway instance

    Examples:
        Create a basic Nexus with all channels:
        >>> nexus = create_nexus()

        Create API-only Nexus:
        >>> nexus = create_nexus(
        ...     enable_cli=False,
        ...     enable_mcp=False,
        ...     api_port=9000
        ... )

        Create Nexus with custom configuration:
        >>> nexus = create_nexus(
        ...     name="my-nexus",
        ...     description="Custom multi-channel gateway",
        ...     api_port=8080,
        ...     mcp_port=3002,
        ...     session_timeout=7200,  # 2 hours
        ...     workflows={"my_workflow": my_workflow_instance}
        ... )
    """

    # Build configuration
    config = NexusConfig(
        name=name or "kailash-nexus",
        description=description or "Multi-channel workflow orchestration gateway",
        # Channel configuration
        enable_api=enable_api,
        enable_cli=enable_cli,
        enable_mcp=enable_mcp,
        # API settings
        api_host=api_host,
        api_port=api_port,
        api_cors_origins=api_cors_origins or ["*"],
        # CLI settings
        cli_interactive=cli_interactive,
        cli_prompt_template=cli_prompt,
        # MCP settings
        mcp_host=mcp_host,
        mcp_port=mcp_port,
        mcp_server_name=mcp_server_name or f"{name or 'kailash'}-nexus-mcp",
        # Session management
        session_timeout=session_timeout,
        session_cleanup_interval=session_cleanup_interval,
        # Event routing
        enable_event_routing=enable_event_routing,
        event_queue_size=event_queue_size,
        # Advanced settings
        enable_health_monitoring=enable_health_monitoring,
        health_check_interval=health_check_interval,
        graceful_shutdown_timeout=graceful_shutdown_timeout,
    )

    # Apply any additional kwargs to config
    for key, value in kwargs.items():
        if hasattr(config, key):
            setattr(config, key, value)
        else:
            logger.warning(f"Unknown configuration option: {key}")

    # Create gateway
    nexus = NexusGateway(config)

    # Register initial workflows if provided
    if workflows:
        for workflow_name, workflow in workflows.items():
            nexus.register_workflow(workflow_name, workflow)
            logger.info(f"Registered initial workflow: {workflow_name}")

    logger.info(f"Created Nexus Gateway: {config.name}")
    logger.info(
        f"Enabled channels: API={enable_api}, CLI={enable_cli}, MCP={enable_mcp}"
    )

    return nexus


def create_api_nexus(
    name: Optional[str] = None,
    port: int = 8000,
    host: str = "localhost",
    cors_origins: Optional[List[str]] = None,
    workflows: Optional[Dict[str, Workflow]] = None,
    **kwargs,
) -> NexusGateway:
    """Create an API-only Nexus Gateway.

    This is a convenience function for creating a Nexus Gateway
    that only exposes the HTTP API channel.

    Args:
        name: Gateway name
        port: API server port
        host: API server host
        cors_origins: CORS origins
        workflows: Initial workflows to register
        **kwargs: Additional configuration options

    Returns:
        Configured NexusGateway with only API channel enabled

    Example:
        >>> nexus = create_api_nexus(
        ...     name="api-only-nexus",
        ...     port=9000,
        ...     workflows={"my_workflow": workflow}
        ... )
    """
    return create_nexus(
        name=name or "kailash-api-nexus",
        description="API-only workflow gateway",
        enable_api=True,
        enable_cli=False,
        enable_mcp=False,
        api_host=host,
        api_port=port,
        api_cors_origins=cors_origins,
        workflows=workflows,
        **kwargs,
    )


def create_cli_nexus(
    name: Optional[str] = None,
    interactive: bool = True,
    prompt: str = "nexus-cli> ",
    workflows: Optional[Dict[str, Workflow]] = None,
    **kwargs,
) -> NexusGateway:
    """Create a CLI-only Nexus Gateway.

    This is a convenience function for creating a Nexus Gateway
    that only exposes the CLI channel.

    Args:
        name: Gateway name
        interactive: Enable interactive CLI mode
        prompt: CLI prompt template
        workflows: Initial workflows to register
        **kwargs: Additional configuration options

    Returns:
        Configured NexusGateway with only CLI channel enabled

    Example:
        >>> nexus = create_cli_nexus(
        ...     name="cli-nexus",
        ...     interactive=True,
        ...     workflows={"help": help_workflow}
        ... )
    """
    return create_nexus(
        name=name or "kailash-cli-nexus",
        description="CLI-only workflow gateway",
        enable_api=False,
        enable_cli=True,
        enable_mcp=False,
        cli_interactive=interactive,
        cli_prompt=prompt,
        workflows=workflows,
        **kwargs,
    )


def create_mcp_nexus(
    name: Optional[str] = None,
    port: int = 3001,
    host: str = "localhost",
    server_name: Optional[str] = None,
    workflows: Optional[Dict[str, Workflow]] = None,
    **kwargs,
) -> NexusGateway:
    """Create an MCP-only Nexus Gateway.

    This is a convenience function for creating a Nexus Gateway
    that only exposes the MCP channel.

    Args:
        name: Gateway name
        port: MCP server port
        host: MCP server host
        server_name: MCP server name
        workflows: Initial workflows to register
        **kwargs: Additional configuration options

    Returns:
        Configured NexusGateway with only MCP channel enabled

    Example:
        >>> nexus = create_mcp_nexus(
        ...     name="mcp-nexus",
        ...     port=3002,
        ...     workflows={"ai_tool": ai_workflow}
        ... )
    """
    return create_nexus(
        name=name or "kailash-mcp-nexus",
        description="MCP-only workflow gateway",
        enable_api=False,
        enable_cli=False,
        enable_mcp=True,
        mcp_host=host,
        mcp_port=port,
        mcp_server_name=server_name,
        workflows=workflows,
        **kwargs,
    )


def create_development_nexus(
    name: Optional[str] = None,
    api_port: int = 8000,
    mcp_port: int = 3001,
    workflows: Optional[Dict[str, Workflow]] = None,
    **kwargs,
) -> NexusGateway:
    """Create a development-focused Nexus Gateway.

    This configuration is optimized for development with:
    - All channels enabled
    - Interactive CLI
    - Health monitoring
    - Verbose logging
    - Short timeouts for faster iteration

    Args:
        name: Gateway name
        api_port: API server port
        mcp_port: MCP server port
        workflows: Initial workflows to register
        **kwargs: Additional configuration options

    Returns:
        Configured NexusGateway optimized for development

    Example:
        >>> nexus = create_development_nexus(
        ...     name="dev-nexus",
        ...     workflows={"test": test_workflow}
        ... )
    """
    return create_nexus(
        name=name or "kailash-dev-nexus",
        description="Development multi-channel gateway",
        # Enable all channels
        enable_api=True,
        enable_cli=True,
        enable_mcp=True,
        # Development-friendly settings
        api_port=api_port,
        mcp_port=mcp_port,
        cli_interactive=True,
        cli_prompt="dev-nexus> ",
        # Faster cleanup for development
        session_timeout=1800,  # 30 minutes
        session_cleanup_interval=60,  # 1 minute
        health_check_interval=10,  # 10 seconds
        graceful_shutdown_timeout=10,  # 10 seconds
        # Enhanced monitoring
        enable_health_monitoring=True,
        enable_event_routing=True,
        workflows=workflows,
        **kwargs,
    )


def create_production_nexus(
    name: Optional[str] = None,
    api_port: int = 80,
    mcp_port: int = 3001,
    workflows: Optional[Dict[str, Workflow]] = None,
    **kwargs,
) -> NexusGateway:
    """Create a production-optimized Nexus Gateway.

    This configuration is optimized for production with:
    - Conservative timeouts
    - Enhanced monitoring
    - Larger queue sizes
    - Robust error handling

    Args:
        name: Gateway name
        api_port: API server port (defaults to 80 for production)
        mcp_port: MCP server port
        workflows: Initial workflows to register
        **kwargs: Additional configuration options

    Returns:
        Configured NexusGateway optimized for production

    Example:
        >>> nexus = create_production_nexus(
        ...     name="prod-nexus",
        ...     api_port=8080,
        ...     workflows=production_workflows
        ... )
    """
    return create_nexus(
        name=name or "kailash-prod-nexus",
        description="Production multi-channel gateway",
        # Production ports
        api_port=api_port,
        mcp_port=mcp_port,
        # Conservative timeouts
        session_timeout=7200,  # 2 hours
        session_cleanup_interval=300,  # 5 minutes
        health_check_interval=60,  # 1 minute
        graceful_shutdown_timeout=60,  # 1 minute
        # Larger queues for production load
        event_queue_size=50000,
        # Enhanced monitoring
        enable_health_monitoring=True,
        enable_event_routing=True,
        # CLI disabled by default in production
        enable_cli=False,
        workflows=workflows,
        **kwargs,
    )
