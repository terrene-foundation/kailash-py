"""Cross-channel event router for Nexus framework."""

import asyncio
import fnmatch
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set, Union

from .base import Channel, ChannelEvent
from .session import CrossChannelSession, SessionManager

logger = logging.getLogger(__name__)


class RoutingRule(Enum):
    """Event routing rule types."""

    BROADCAST = "broadcast"  # Send to all channels
    UNICAST = "unicast"  # Send to specific channel
    MULTICAST = "multicast"  # Send to selected channels
    SESSION = "session"  # Route based on session
    PATTERN = "pattern"  # Route based on pattern matching


@dataclass
class EventRoute:
    """Defines an event routing rule."""

    rule_type: RoutingRule
    source_patterns: List[str] = field(default_factory=list)
    target_channels: List[str] = field(default_factory=list)
    event_type_patterns: List[str] = field(default_factory=list)
    session_filter: Optional[Callable[[CrossChannelSession], bool]] = None
    condition: Optional[Callable[[ChannelEvent], bool]] = None
    transform: Optional[Callable[[ChannelEvent], ChannelEvent]] = None
    priority: int = 100  # Lower number = higher priority
    enabled: bool = True


@dataclass
class RoutingStats:
    """Event routing statistics."""

    total_events: int = 0
    routed_events: int = 0
    dropped_events: int = 0
    failed_events: int = 0
    routes_matched: Dict[str, int] = field(default_factory=dict)
    channel_stats: Dict[str, Dict[str, int]] = field(default_factory=dict)


class EventRouter:
    """Cross-channel event router for the Nexus framework.

    This router handles event distribution between different channels,
    enabling unified communication across API, CLI, and MCP interfaces.
    """

    def __init__(self, session_manager: Optional[SessionManager] = None):
        """Initialize event router.

        Args:
            session_manager: Optional session manager for session-based routing
        """
        self.session_manager = session_manager
        self._channels: Dict[str, Channel] = {}
        self._routes: List[EventRoute] = []
        self._event_queue: Optional[asyncio.Queue] = None
        self._router_task: Optional[asyncio.Task] = None
        self._running = False
        self._stats = RoutingStats()

        # Setup default routes
        self._setup_default_routes()

        logger.info("Event router initialized")

    def _setup_default_routes(self) -> None:
        """Set up default routing rules."""

        # Route channel lifecycle events to all other channels
        self.add_route(
            EventRoute(
                rule_type=RoutingRule.BROADCAST,
                event_type_patterns=[
                    "channel_started",
                    "channel_stopped",
                    "channel_error",
                ],
                priority=50,
            )
        )

        # Route session events to channels in the same session
        self.add_route(
            EventRoute(
                rule_type=RoutingRule.SESSION,
                event_type_patterns=["session_*"],
                priority=60,
            )
        )

        # Route workflow events based on session
        self.add_route(
            EventRoute(
                rule_type=RoutingRule.SESSION,
                event_type_patterns=["workflow_*", "mcp_*", "command_*"],
                priority=70,
            )
        )

    async def start(self) -> None:
        """Start the event router."""
        if self._running:
            logger.warning("Event router is already running")
            return

        self._running = True
        self._event_queue = asyncio.Queue(maxsize=10000)
        self._router_task = asyncio.create_task(self._routing_loop())

        logger.info("Event router started")

    async def stop(self) -> None:
        """Stop the event router."""
        if not self._running:
            return

        self._running = False

        if self._router_task and not self._router_task.done():
            self._router_task.cancel()
            try:
                await self._router_task
            except asyncio.CancelledError:
                pass

        # Clear remaining events
        if self._event_queue:
            while not self._event_queue.empty():
                try:
                    self._event_queue.get_nowait()
                except asyncio.QueueEmpty:
                    break

        logger.info("Event router stopped")

    def register_channel(self, channel: Channel) -> None:
        """Register a channel with the router.

        Args:
            channel: Channel to register
        """
        self._channels[channel.name] = channel

        # Initialize channel stats
        if channel.name not in self._stats.channel_stats:
            self._stats.channel_stats[channel.name] = {
                "events_sent": 0,
                "events_received": 0,
                "events_failed": 0,
            }

        logger.info(f"Registered channel '{channel.name}' with event router")

    def unregister_channel(self, channel_name: str) -> None:
        """Unregister a channel from the router.

        Args:
            channel_name: Name of channel to unregister
        """
        if channel_name in self._channels:
            del self._channels[channel_name]
            logger.info(f"Unregistered channel '{channel_name}' from event router")

    def add_route(self, route: EventRoute) -> None:
        """Add a routing rule.

        Args:
            route: Routing rule to add
        """
        self._routes.append(route)
        # Sort by priority (lower number = higher priority)
        self._routes.sort(key=lambda r: r.priority)
        logger.debug(f"Added routing rule: {route.rule_type.value}")

    def remove_route(self, route: EventRoute) -> None:
        """Remove a routing rule.

        Args:
            route: Routing rule to remove
        """
        if route in self._routes:
            self._routes.remove(route)
            logger.debug(f"Removed routing rule: {route.rule_type.value}")

    async def route_event(self, event: ChannelEvent) -> None:
        """Route an event to appropriate channels.

        Args:
            event: Event to route
        """
        if not self._running or not self._event_queue:
            logger.warning("Event router not running, dropping event")
            return

        try:
            await self._event_queue.put(event)
            self._stats.total_events += 1
        except asyncio.QueueFull:
            logger.warning("Event queue full, dropping event")
            self._stats.dropped_events += 1

    async def _routing_loop(self) -> None:
        """Main event routing loop."""
        while self._running:
            try:
                if not self._event_queue:
                    break

                # Get event with timeout
                try:
                    event = await asyncio.wait_for(self._event_queue.get(), timeout=1.0)
                except asyncio.TimeoutError:
                    continue

                await self._process_event(event)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in routing loop: {e}")

    async def _process_event(self, event: ChannelEvent) -> None:
        """Process a single event through routing rules.

        Args:
            event: Event to process
        """
        try:
            # Update stats
            source_channel = event.channel_name
            if source_channel in self._stats.channel_stats:
                self._stats.channel_stats[source_channel]["events_sent"] += 1

            # Find matching routes
            matching_routes = self._find_matching_routes(event)

            if not matching_routes:
                logger.debug(f"No routes found for event {event.event_id}")
                self._stats.dropped_events += 1
                return

            # Apply routes in priority order
            for route in matching_routes:
                try:
                    await self._apply_route(event, route)
                    self._stats.routed_events += 1

                    # Update route stats
                    route_key = f"{route.rule_type.value}_{id(route)}"
                    self._stats.routes_matched[route_key] = (
                        self._stats.routes_matched.get(route_key, 0) + 1
                    )

                except Exception as e:
                    logger.error(f"Error applying route {route.rule_type.value}: {e}")
                    self._stats.failed_events += 1

        except Exception as e:
            logger.error(f"Error processing event {event.event_id}: {e}")
            self._stats.failed_events += 1

    def _find_matching_routes(self, event: ChannelEvent) -> List[EventRoute]:
        """Find routes that match the given event.

        Args:
            event: Event to match

        Returns:
            List of matching routes in priority order
        """
        matching_routes = []

        for route in self._routes:
            if not route.enabled:
                continue

            # Check source pattern
            if route.source_patterns and not self._match_patterns(
                event.channel_name, route.source_patterns
            ):
                continue

            # Check event type pattern
            if route.event_type_patterns and not self._match_patterns(
                event.event_type, route.event_type_patterns
            ):
                continue

            # Check custom condition
            if route.condition and not route.condition(event):
                continue

            matching_routes.append(route)

        return matching_routes

    def _match_patterns(self, value: str, patterns: List[str]) -> bool:
        """Check if value matches any of the patterns.

        Args:
            value: Value to match
            patterns: List of patterns (supports wildcards)

        Returns:
            True if value matches any pattern
        """
        for pattern in patterns:
            if fnmatch.fnmatch(value, pattern):
                return True
        return False

    async def _apply_route(self, event: ChannelEvent, route: EventRoute) -> None:
        """Apply a routing rule to an event.

        Args:
            event: Event to route
            route: Route to apply
        """
        # Transform event if needed
        if route.transform:
            event = route.transform(event)

        # Determine target channels based on route type
        if route.rule_type == RoutingRule.BROADCAST:
            targets = [
                name for name in self._channels.keys() if name != event.channel_name
            ]
        elif route.rule_type == RoutingRule.UNICAST:
            targets = route.target_channels[:1] if route.target_channels else []
        elif route.rule_type == RoutingRule.MULTICAST:
            targets = route.target_channels
        elif route.rule_type == RoutingRule.SESSION:
            targets = await self._find_session_targets(event, route)
        elif route.rule_type == RoutingRule.PATTERN:
            targets = self._find_pattern_targets(event, route)
        else:
            targets = []

        # Send event to target channels
        for target_name in targets:
            if target_name in self._channels:
                try:
                    target_channel = self._channels[target_name]
                    await target_channel.handle_event(event)

                    # Update target channel stats
                    if target_name in self._stats.channel_stats:
                        self._stats.channel_stats[target_name]["events_received"] += 1

                except Exception as e:
                    logger.error(f"Error sending event to channel {target_name}: {e}")
                    if target_name in self._stats.channel_stats:
                        self._stats.channel_stats[target_name]["events_failed"] += 1

    async def _find_session_targets(
        self, event: ChannelEvent, route: EventRoute
    ) -> List[str]:
        """Find target channels based on session routing.

        Args:
            event: Event to route
            route: Route configuration

        Returns:
            List of target channel names
        """
        if not self.session_manager or not event.session_id:
            return []

        session = self.session_manager.get_session(event.session_id)
        if not session:
            return []

        # Apply session filter if provided
        if route.session_filter and not route.session_filter(session):
            return []

        # Return channels active in the session (excluding source)
        return [
            ch
            for ch in session.active_channels
            if ch != event.channel_name and ch in self._channels
        ]

    def _find_pattern_targets(
        self, event: ChannelEvent, route: EventRoute
    ) -> List[str]:
        """Find target channels based on pattern matching.

        Args:
            event: Event to route
            route: Route configuration

        Returns:
            List of target channel names
        """
        targets = []

        for channel_name in self._channels.keys():
            if channel_name == event.channel_name:
                continue  # Don't send back to source

            # Check if channel matches target patterns
            if route.target_channels:
                if any(
                    self._match_patterns(channel_name, [pattern])
                    for pattern in route.target_channels
                ):
                    targets.append(channel_name)

        return targets

    def get_stats(self) -> Dict[str, Any]:
        """Get event routing statistics.

        Returns:
            Dictionary with routing statistics
        """
        return {
            "total_events": self._stats.total_events,
            "routed_events": self._stats.routed_events,
            "dropped_events": self._stats.dropped_events,
            "failed_events": self._stats.failed_events,
            "success_rate": (
                self._stats.routed_events / max(1, self._stats.total_events)
            )
            * 100,
            "routes_count": len(self._routes),
            "channels_count": len(self._channels),
            "queue_size": self._event_queue.qsize() if self._event_queue else 0,
            "route_matches": dict(self._stats.routes_matched),
            "channel_stats": dict(self._stats.channel_stats),
            "channels_registered": list(self._channels.keys()),
        }

    def reset_stats(self) -> None:
        """Reset routing statistics."""
        self._stats = RoutingStats()
        logger.info("Event router statistics reset")

    async def health_check(self) -> Dict[str, Any]:
        """Perform health check on the event router.

        Returns:
            Health check results
        """
        try:
            is_healthy = (
                self._running
                and self._event_queue is not None
                and self._router_task is not None
                and not self._router_task.done()
            )

            queue_health = True
            if self._event_queue:
                queue_size = self._event_queue.qsize()
                queue_health = queue_size < 8000  # Warning if queue getting full

            return {
                "healthy": is_healthy and queue_health,
                "running": self._running,
                "queue_size": self._event_queue.qsize() if self._event_queue else 0,
                "channels_registered": len(self._channels),
                "routes_configured": len(self._routes),
                "total_events_processed": self._stats.total_events,
                "success_rate": (
                    self._stats.routed_events / max(1, self._stats.total_events)
                )
                * 100,
                "checks": {
                    "router_running": self._running,
                    "queue_available": self._event_queue is not None,
                    "task_active": self._router_task is not None
                    and not self._router_task.done(),
                    "queue_healthy": queue_health,
                    "channels_available": len(self._channels) > 0,
                },
            }

        except Exception as e:
            return {"healthy": False, "error": str(e), "checks": {}}
