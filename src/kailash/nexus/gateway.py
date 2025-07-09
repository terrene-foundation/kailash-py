"""Nexus Gateway - Main orchestration hub for multi-channel communication."""

import asyncio
import logging
import signal
import sys
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Union

from ..channels.api_channel import APIChannel
from ..channels.base import Channel, ChannelConfig, ChannelStatus, ChannelType
from ..channels.cli_channel import CLIChannel
from ..channels.event_router import EventRoute, EventRouter, RoutingRule
from ..channels.mcp_channel import MCPChannel
from ..channels.session import SessionManager
from ..workflow import Workflow

logger = logging.getLogger(__name__)


@dataclass
class NexusConfig:
    """Configuration for Nexus Gateway."""

    # Basic settings
    name: str = "kailash-nexus"
    description: str = "Multi-channel workflow orchestration gateway"
    version: str = "1.0.0"

    # Channel configuration
    enable_api: bool = True
    enable_cli: bool = True
    enable_mcp: bool = True

    # API channel settings
    api_host: str = "localhost"
    api_port: int = 8000
    api_cors_origins: List[str] = field(default_factory=lambda: ["*"])

    # CLI channel settings
    cli_interactive: bool = False
    cli_prompt_template: str = "nexus> "

    # MCP channel settings
    mcp_host: str = "localhost"
    mcp_port: int = 3001
    mcp_server_name: str = "kailash-nexus-mcp"

    # Session management
    session_timeout: int = 3600  # 1 hour
    session_cleanup_interval: int = 300  # 5 minutes

    # Event routing
    enable_event_routing: bool = True
    event_queue_size: int = 10000

    # Advanced settings
    enable_health_monitoring: bool = True
    health_check_interval: int = 30
    graceful_shutdown_timeout: int = 30


class NexusGateway:
    """Main orchestration hub for the Kailash Nexus framework.

    The Nexus Gateway provides a unified interface for managing multiple
    communication channels (API, CLI, MCP) with shared session management
    and cross-channel event routing.
    """

    def __init__(self, config: Optional[NexusConfig] = None):
        """Initialize Nexus Gateway.

        Args:
            config: Optional configuration, uses defaults if not provided
        """
        self.config = config or NexusConfig()

        # Core components
        self.session_manager = SessionManager(
            default_timeout=self.config.session_timeout,
            cleanup_interval=self.config.session_cleanup_interval,
        )
        self.event_router = EventRouter(session_manager=self.session_manager)

        # Channels
        self._channels: Dict[str, Channel] = {}
        self._workflows: Dict[str, Workflow] = {}

        # Runtime state
        self._running = False
        self._startup_tasks: List[asyncio.Task] = []
        self._health_task: Optional[asyncio.Task] = None
        self._shutdown_event = asyncio.Event()

        # Initialize channels based on configuration
        self._initialize_channels()

        logger.info(f"Nexus Gateway initialized: {self.config.name}")

    def _initialize_channels(self) -> None:
        """Initialize channels based on configuration."""

        # API Channel
        if self.config.enable_api:
            api_config = ChannelConfig(
                name="api",
                channel_type=ChannelType.API,
                host=self.config.api_host,
                port=self.config.api_port,
                enable_event_routing=self.config.enable_event_routing,
                extra_config={
                    "title": f"{self.config.name} API",
                    "description": f"API interface for {self.config.description}",
                    "cors_origins": self.config.api_cors_origins,
                    "enable_durability": True,
                    "enable_resource_management": True,
                    "enable_async_execution": True,
                    "enable_health_checks": True,
                },
            )
            self._channels["api"] = APIChannel(api_config)

        # CLI Channel
        if self.config.enable_cli:
            cli_config = ChannelConfig(
                name="cli",
                channel_type=ChannelType.CLI,
                host=self.config.api_host,  # CLI doesn't use network host
                enable_event_routing=self.config.enable_event_routing,
                extra_config={
                    "interactive_mode": self.config.cli_interactive,
                    "prompt_template": self.config.cli_prompt_template,
                },
            )
            self._channels["cli"] = CLIChannel(cli_config)

        # MCP Channel
        if self.config.enable_mcp:
            mcp_config = ChannelConfig(
                name="mcp",
                channel_type=ChannelType.MCP,
                host=self.config.mcp_host,
                port=self.config.mcp_port,
                enable_event_routing=self.config.enable_event_routing,
                extra_config={
                    "server_name": self.config.mcp_server_name,
                    "description": f"MCP interface for {self.config.description}",
                },
            )
            self._channels["mcp"] = MCPChannel(mcp_config)

    async def start(self) -> None:
        """Start the Nexus Gateway and all enabled channels."""
        if self._running:
            logger.warning("Nexus Gateway is already running")
            return

        try:
            logger.info(f"Starting Nexus Gateway: {self.config.name}")

            # Start session manager
            await self.session_manager.start()

            # Start event router
            await self.event_router.start()

            # Register channels with event router
            for channel in self._channels.values():
                self.event_router.register_channel(channel)

            # Start all channels
            channel_tasks = []
            for channel_name, channel in self._channels.items():
                logger.info(f"Starting {channel_name} channel...")
                task = asyncio.create_task(channel.start())
                task.set_name(f"start_{channel_name}")
                channel_tasks.append(task)

            # Wait for all channels to start
            await asyncio.gather(*channel_tasks, return_exceptions=True)

            # Verify channel startup
            failed_channels = []
            for channel_name, channel in self._channels.items():
                if channel.status != ChannelStatus.RUNNING:
                    failed_channels.append(channel_name)
                    logger.error(
                        f"Failed to start {channel_name} channel: {channel.status}"
                    )

            if failed_channels:
                raise RuntimeError(f"Failed to start channels: {failed_channels}")

            # Start health monitoring if enabled
            if self.config.enable_health_monitoring:
                self._health_task = asyncio.create_task(self._health_monitoring_loop())

            # Setup signal handlers for graceful shutdown
            self._setup_signal_handlers()

            self._running = True

            logger.info(
                f"Nexus Gateway started successfully with {len(self._channels)} channels"
            )

            # Register shared workflows with all channels
            await self._register_workflows()

        except Exception as e:
            logger.error(f"Failed to start Nexus Gateway: {e}")
            await self.stop()  # Cleanup on failure
            raise

    async def stop(self) -> None:
        """Stop the Nexus Gateway and all channels."""
        if not self._running:
            return

        try:
            logger.info("Stopping Nexus Gateway...")
            self._running = False
            self._shutdown_event.set()

            # Stop health monitoring
            if self._health_task and not self._health_task.done():
                self._health_task.cancel()
                try:
                    await self._health_task
                except asyncio.CancelledError:
                    pass

            # Stop all channels
            channel_tasks = []
            for channel_name, channel in self._channels.items():
                logger.info(f"Stopping {channel_name} channel...")
                task = asyncio.create_task(channel.stop())
                task.set_name(f"stop_{channel_name}")
                channel_tasks.append(task)

            # Wait for channels to stop (with timeout)
            try:
                await asyncio.wait_for(
                    asyncio.gather(*channel_tasks, return_exceptions=True),
                    timeout=self.config.graceful_shutdown_timeout,
                )
            except asyncio.TimeoutError:
                logger.warning("Channel shutdown timed out")

            # Stop event router
            await self.event_router.stop()

            # Stop session manager
            await self.session_manager.stop()

            logger.info("Nexus Gateway stopped")

        except Exception as e:
            logger.error(f"Error stopping Nexus Gateway: {e}")

    def register_workflow(
        self, name: str, workflow: Workflow, channels: Optional[List[str]] = None
    ) -> None:
        """Register a workflow with specified channels.

        Args:
            name: Workflow name
            workflow: Workflow instance
            channels: List of channel names to register with (all channels if None)
        """
        self._workflows[name] = workflow

        # Register with specified channels (or all channels if none specified)
        target_channels = channels or list(self._channels.keys())

        for channel_name in target_channels:
            if channel_name in self._channels:
                channel = self._channels[channel_name]

                # Register based on channel type
                if isinstance(channel, APIChannel):
                    channel.register_workflow(name, workflow)
                elif isinstance(channel, MCPChannel):
                    channel.register_workflow(name, workflow)
                # CLI channel uses workflows through routing

                logger.info(f"Registered workflow '{name}' with {channel_name} channel")

    def proxy_workflow(
        self,
        name: str,
        proxy_url: str,
        channels: Optional[List[str]] = None,
        health_check: Optional[str] = None,
    ) -> None:
        """Register a proxied workflow with specified channels.

        Args:
            name: Workflow name
            proxy_url: URL to proxy requests to
            channels: List of channel names to register with
            health_check: Optional health check endpoint
        """
        target_channels = channels or [
            "api"
        ]  # Default to API only for proxied workflows

        for channel_name in target_channels:
            if channel_name in self._channels and isinstance(
                self._channels[channel_name], APIChannel
            ):
                channel = self._channels[channel_name]
                channel.proxy_workflow(name, proxy_url, health_check)
                logger.info(
                    f"Registered proxied workflow '{name}' with {channel_name} channel"
                )

    async def _register_workflows(self) -> None:
        """Register all stored workflows with appropriate channels."""
        for name, workflow in self._workflows.items():
            self.register_workflow(name, workflow)

    def get_channel(self, name: str) -> Optional[Channel]:
        """Get a channel by name.

        Args:
            name: Channel name

        Returns:
            Channel instance or None if not found
        """
        return self._channels.get(name)

    def list_channels(self) -> Dict[str, Dict[str, Any]]:
        """List all channels and their status.

        Returns:
            Dictionary of channel information
        """
        channels_info = {}

        for name, channel in self._channels.items():
            channels_info[name] = {
                "name": name,
                "type": channel.channel_type.value,
                "status": channel.status.value,
                "config": {
                    "host": channel.config.host,
                    "port": channel.config.port,
                    "enabled": channel.config.enabled,
                },
            }

        return channels_info

    def list_workflows(self) -> Dict[str, Dict[str, Any]]:
        """List all registered workflows.

        Returns:
            Dictionary of workflow information
        """
        workflows_info = {}

        for name, workflow in self._workflows.items():
            workflows_info[name] = {"name": name, "available_on": []}

            # Check which channels have this workflow
            for channel_name, channel in self._channels.items():
                if (
                    isinstance(channel, APIChannel)
                    and name in channel.workflow_server.workflows
                ):
                    workflows_info[name]["available_on"].append(channel_name)
                elif (
                    isinstance(channel, MCPChannel)
                    and name in channel._workflow_registry
                ):
                    workflows_info[name]["available_on"].append(channel_name)

        return workflows_info

    async def health_check(self) -> Dict[str, Any]:
        """Perform comprehensive health check.

        Returns:
            Health check results
        """
        overall_healthy = True
        checks = {}

        # Check session manager
        try:
            session_stats = self.session_manager.get_stats()
            checks["session_manager"] = {
                "healthy": True,
                "total_sessions": session_stats["total_sessions"],
                "active_sessions": session_stats["active_sessions"],
            }
        except Exception as e:
            checks["session_manager"] = {"healthy": False, "error": str(e)}
            overall_healthy = False

        # Check event router
        try:
            router_health = await self.event_router.health_check()
            checks["event_router"] = router_health
            if not router_health["healthy"]:
                overall_healthy = False
        except Exception as e:
            checks["event_router"] = {"healthy": False, "error": str(e)}
            overall_healthy = False

        # Check all channels
        channel_checks = {}
        for name, channel in self._channels.items():
            try:
                channel_health = await channel.health_check()
                channel_checks[name] = channel_health
                if not channel_health["healthy"]:
                    overall_healthy = False
            except Exception as e:
                channel_checks[name] = {"healthy": False, "error": str(e)}
                overall_healthy = False

        checks["channels"] = channel_checks

        return {
            "healthy": overall_healthy,
            "nexus_running": self._running,
            "channels_count": len(self._channels),
            "workflows_count": len(self._workflows),
            "checks": checks,
            "channels": list(self._channels.keys()),
            "config": {
                "name": self.config.name,
                "version": self.config.version,
                "enable_api": self.config.enable_api,
                "enable_cli": self.config.enable_cli,
                "enable_mcp": self.config.enable_mcp,
            },
        }

    async def get_stats(self) -> Dict[str, Any]:
        """Get comprehensive Nexus Gateway statistics.

        Returns:
            Statistics dictionary
        """
        stats = {
            "nexus": {
                "name": self.config.name,
                "version": self.config.version,
                "running": self._running,
                "channels_enabled": len(self._channels),
                "workflows_registered": len(self._workflows),
            },
            "session_manager": self.session_manager.get_stats(),
            "event_router": self.event_router.get_stats(),
            "channels": {},
        }

        # Get channel-specific stats
        for name, channel in self._channels.items():
            try:
                channel_status = await channel.get_status()
                stats["channels"][name] = channel_status
            except Exception as e:
                stats["channels"][name] = {"error": str(e)}

        return stats

    async def _health_monitoring_loop(self) -> None:
        """Background health monitoring loop."""
        while self._running:
            try:
                await asyncio.sleep(self.config.health_check_interval)

                if not self._running:
                    break

                # Perform health check
                health = await self.health_check()

                if not health["healthy"]:
                    logger.warning("Nexus Gateway health check failed")
                    logger.debug(f"Health check details: {health}")

                # Check for unhealthy channels
                for channel_name, channel_health in health["checks"][
                    "channels"
                ].items():
                    if not channel_health.get("healthy", False):
                        logger.warning(
                            f"Channel {channel_name} is unhealthy: {channel_health}"
                        )

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in health monitoring: {e}")

    def _setup_signal_handlers(self) -> None:
        """Setup signal handlers for graceful shutdown."""
        if sys.platform != "win32":
            # Unix-style signal handling
            loop = asyncio.get_event_loop()

            def signal_handler():
                logger.info("Received shutdown signal")
                asyncio.create_task(self.stop())

            loop.add_signal_handler(signal.SIGINT, signal_handler)
            loop.add_signal_handler(signal.SIGTERM, signal_handler)

    async def run_forever(self) -> None:
        """Run the Nexus Gateway until shutdown signal."""
        if not self._running:
            await self.start()

        try:
            logger.info("Nexus Gateway is running. Press Ctrl+C to stop.")
            await self._shutdown_event.wait()
        except KeyboardInterrupt:
            logger.info("Received keyboard interrupt")
        finally:
            await self.stop()

    def __enter__(self):
        """Context manager entry."""
        return self

    async def __aenter__(self):
        """Async context manager entry."""
        await self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        # Note: This is synchronous, for async context use __aexit__
        pass

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.stop()
