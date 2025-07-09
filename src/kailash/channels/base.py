"""Base channel abstractions for the Nexus framework."""

import asyncio
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Union

logger = logging.getLogger(__name__)


class ChannelType(Enum):
    """Supported channel types."""

    API = "api"
    CLI = "cli"
    MCP = "mcp"


class ChannelStatus(Enum):
    """Channel status states."""

    INITIALIZED = "initialized"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"
    ERROR = "error"


@dataclass
class ChannelConfig:
    """Configuration for a channel."""

    name: str
    channel_type: ChannelType
    enabled: bool = True
    host: str = "localhost"
    port: Optional[int] = None

    # Security settings
    enable_auth: bool = False
    auth_config: Dict[str, Any] = field(default_factory=dict)

    # Session management
    enable_sessions: bool = True
    session_timeout: int = 3600  # 1 hour default

    # Event handling
    enable_event_routing: bool = True
    event_buffer_size: int = 1000

    # Channel-specific configuration
    extra_config: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ChannelEvent:
    """Represents an event in a channel."""

    event_id: str
    channel_name: str
    channel_type: ChannelType
    event_type: str
    payload: Dict[str, Any]
    session_id: Optional[str] = None
    timestamp: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ChannelResponse:
    """Response from a channel operation."""

    success: bool
    data: Any = None
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class Channel(ABC):
    """Abstract base class for all channel implementations.

    Channels provide a unified interface for different communication protocols
    (HTTP API, CLI, MCP) in the Nexus framework.
    """

    def __init__(self, config: ChannelConfig):
        """Initialize the channel.

        Args:
            config: Channel configuration
        """
        self.config = config
        self.status = ChannelStatus.INITIALIZED
        self._event_handlers: Dict[str, List[Callable]] = {}
        self._event_queue: Optional[asyncio.Queue] = None
        self._running_task: Optional[asyncio.Task] = None

        logger.info(f"Initialized {config.channel_type.value} channel: {config.name}")

    @property
    def name(self) -> str:
        """Get channel name."""
        return self.config.name

    @property
    def channel_type(self) -> ChannelType:
        """Get channel type."""
        return self.config.channel_type

    @property
    def is_running(self) -> bool:
        """Check if channel is running."""
        return self.status == ChannelStatus.RUNNING

    @abstractmethod
    async def start(self) -> None:
        """Start the channel.

        This method should:
        1. Initialize channel-specific resources
        2. Start listening for requests
        3. Set status to RUNNING
        """
        pass

    @abstractmethod
    async def stop(self) -> None:
        """Stop the channel.

        This method should:
        1. Stop accepting new requests
        2. Clean up resources
        3. Set status to STOPPED
        """
        pass

    @abstractmethod
    async def handle_request(self, request: Dict[str, Any]) -> ChannelResponse:
        """Handle a request from this channel.

        Args:
            request: Channel-specific request data

        Returns:
            ChannelResponse with the result
        """
        pass

    async def emit_event(self, event: ChannelEvent) -> None:
        """Emit an event from this channel.

        Args:
            event: Event to emit
        """
        if not self.config.enable_event_routing:
            return

        # Add to event queue for routing
        if self._event_queue:
            try:
                await self._event_queue.put(event)
                logger.debug(f"Emitted event {event.event_id} from channel {self.name}")
            except asyncio.QueueFull:
                logger.warning(f"Event queue full, dropping event {event.event_id}")

    def add_event_handler(
        self, event_type: str, handler: Callable[[ChannelEvent], None]
    ) -> None:
        """Add an event handler for specific event types.

        Args:
            event_type: Type of event to handle
            handler: Callable to handle the event
        """
        if event_type not in self._event_handlers:
            self._event_handlers[event_type] = []
        self._event_handlers[event_type].append(handler)
        logger.debug(f"Added event handler for {event_type} on channel {self.name}")

    async def handle_event(self, event: ChannelEvent) -> None:
        """Handle an incoming event.

        Args:
            event: Event to handle
        """
        handlers = self._event_handlers.get(event.event_type, [])
        for handler in handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(event)
                else:
                    handler(event)
            except Exception as e:
                logger.error(f"Error in event handler for {event.event_type}: {e}")

    async def get_status(self) -> Dict[str, Any]:
        """Get channel status information.

        Returns:
            Dictionary with channel status details
        """
        return {
            "name": self.name,
            "type": self.channel_type.value,
            "status": self.status.value,
            "enabled": self.config.enabled,
            "host": self.config.host,
            "port": self.config.port,
            "event_handlers": len(self._event_handlers),
            "queue_size": self._event_queue.qsize() if self._event_queue else 0,
        }

    async def health_check(self) -> Dict[str, Any]:
        """Perform a health check on the channel.

        Returns:
            Health check results
        """
        try:
            # Base health check - can be overridden by subclasses
            is_healthy = self.status in [
                ChannelStatus.RUNNING,
                ChannelStatus.INITIALIZED,
            ]

            return {
                "healthy": is_healthy,
                "status": self.status.value,
                "message": (
                    "OK" if is_healthy else f"Channel status: {self.status.value}"
                ),
                "checks": {
                    "status": is_healthy,
                    "event_queue": self._event_queue is not None,
                    "enabled": self.config.enabled,
                },
            }
        except Exception as e:
            return {
                "healthy": False,
                "status": "error",
                "message": str(e),
                "checks": {},
            }

    def _setup_event_queue(self) -> None:
        """Set up the event queue for this channel."""
        if self.config.enable_event_routing:
            self._event_queue = asyncio.Queue(maxsize=self.config.event_buffer_size)

    async def _cleanup(self) -> None:
        """Clean up channel resources."""
        if self._running_task and not self._running_task.done():
            self._running_task.cancel()
            try:
                await self._running_task
            except asyncio.CancelledError:
                pass

        if self._event_queue:
            # Clear any remaining events
            while not self._event_queue.empty():
                try:
                    self._event_queue.get_nowait()
                except asyncio.QueueEmpty:
                    break

        logger.info(f"Cleaned up channel {self.name}")
