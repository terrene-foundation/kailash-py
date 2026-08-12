"""Base channel abstractions for the Nexus framework."""

import asyncio
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, NamedTuple, Optional, Union

from kailash.utils.secure_logging import safe_exception_frames, safe_type_name

logger = logging.getLogger(__name__)

# How long ``_cleanup`` waits to CONFIRM that the task it just cancelled has
# actually stopped. The cancel itself is synchronous and unconditional, so this
# bounds only the observation. Deliberately short: ``_cleanup`` runs from
# ``stop()``'s ``finally`` while a caller-aimed cancellation is propagating,
# often under a shutdown deadline, so a long join here compounds the very
# teardown it is trying not to obstruct. Long enough for a cooperative task to
# unwind, short enough that a task which ignores cancellation cannot hold the
# caller.
_CLEANUP_JOIN_TIMEOUT = 1.0


class CleanupOutcome(NamedTuple):
    """What ``Channel._cleanup`` established, beyond a single bool.

    ``complete=False`` used to denote TWO conditions that a caller must act on
    DIFFERENTLY, and collapsing them onto one ``STOPPING`` told the caller to
    do the wrong thing in one of the two (issue #2018/#2021):

    * ``event_task_live`` -- the event task IGNORED its cancellation and is
      still running. ``STOPPING`` is exactly right: stop again, and keep
      stopping until it dies.
    * ``event_task_failed`` -- the event task DIED OF A REAL ERROR. The task is
      gone, so a retry finds nothing left to cancel and clears straight to
      ``STOPPED`` -- laundering a failed teardown into a clean stop one call
      later. ``STOPPING``'s documented meaning ("still running, stop it again")
      is false here and the advice it carries is actively wrong.

    ``__bool__`` returns ``complete``, so the pre-existing ``if cleaned:``
    reading is preserved exactly for any caller that only asks the old
    question.
    """

    #: Nothing live was left behind and no task failed.
    complete: bool
    #: The event task outlived its cancellation and the bounded join.
    event_task_live: bool = False
    #: The event task terminated with an exception rather than a cancellation.
    event_task_failed: bool = False

    def __bool__(self) -> bool:
        return self.complete


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
    #
    # TRI-STATE, and deliberately so (#2072). ``APIChannel`` builds an
    # ``EnterpriseWorkflowServer``, whose ``POST /workflows/{name}/execute``
    # runs arbitrary registered workflows; that server now fails CLOSED. This
    # field decides whether the channel keeps that gate or takes it away, so
    # "the operator never said" and "the operator said no" cannot be the same
    # value:
    #
    # * ``None``  -- unstated. The channel INHERITS the server's fail-closed
    #   default, so a caller who never considered authentication gets it
    #   rather than silently serving anonymous workflow execution.
    # * ``True``  -- install the gate; ``auth_config`` supplies the credential.
    # * ``False`` -- an EXPLICIT opt-out. Honoured, and never silent: the
    #   server logs a WARN naming the exposure (``security.md``
    #   § Secure-Default).
    #
    # A plain ``bool`` default of ``False`` could not express the first case,
    # which is why the previous default made every ``APIChannel`` an open
    # server. Channels that do NOT enforce this (CLI, MCP) must report it as
    # ``bool(...)`` -- reporting an unstated ``None`` as enabled would be a
    # false assurance, which is the defect class this whole change closes.
    enable_auth: Optional[bool] = None
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
        #: Latched by ``_cleanup`` when the event task died of a real error.
        #: See :meth:`_status_after_cleanup` for why it must survive a retry.
        self._cleanup_failed: bool = False

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
        """Set up the event queue for this channel.

        Also the start-time reset for the ``_cleanup_failed`` latch. All three
        channels call this from ``start()``, so a channel that is genuinely
        restarted gets a clean slate while a channel that merely had ``stop()``
        called twice does not -- which is the whole point of latching.
        """
        self._cleanup_failed = False
        if self.config.enable_event_routing:
            self._event_queue = asyncio.Queue(maxsize=self.config.event_buffer_size)

    def _status_after_cleanup(
        self,
        outcome: Union[CleanupOutcome, bool],
        *,
        other_resource_live: bool = False,
    ) -> ChannelStatus:
        """Map a cleanup outcome onto the status an orchestrator acts on.

        THREE outcomes, not two, because ``STOPPING`` carries advice ("stop it
        again") that is only true for one of the two ways cleanup fails -- see
        :class:`CleanupOutcome`.

        ``other_resource_live`` is for a channel that owns a teardown resource
        ``_cleanup`` does not cover; ``MCPChannel``'s dedicated server thread is
        the only one today, and reporting ``STOPPED`` over it was issue #2018.

        A FAILED teardown takes precedence over a live one. Both demand a
        different action, and ``ERROR`` is the one that stops an orchestrator
        from retrying its way to a clean-looking ``STOPPED``; a caller that
        retries an ``ERROR`` channel still finds the live resource and is told
        so again, so precedence loses no information in that direction.

        The failure is STICKY (``_cleanup_failed``) precisely because the failed
        task is gone by the second call: without the latch, retrying reports
        ``STOPPED`` and the failure vanishes from the record. ``start()``
        clears it via :meth:`_setup_event_queue` -- a restarted channel is
        entitled to a clean slate; a stopped one is not.
        """
        if isinstance(outcome, bool):
            # Compatibility with a subclass that overrides ``_cleanup`` against
            # its former ``-> bool`` signature. It degrades to the old two-state
            # behaviour, which is the most such an override can express -- NOT a
            # fallback that invents a distinction the caller did not report.
            outcome = CleanupOutcome(complete=outcome, event_task_live=not outcome)
        if self._cleanup_failed or outcome.event_task_failed:
            return ChannelStatus.ERROR
        if outcome.complete and not other_resource_live:
            return ChannelStatus.STOPPED
        return ChannelStatus.STOPPING

    async def _cleanup(self) -> CleanupOutcome:
        """Clean up channel resources. Reports WHAT cleanup established.

        The return value is load-bearing: a caller that promotes an incomplete
        cleanup to ``STOPPED`` reports a clean stop over a live task, which is
        the false-success family this channel work exists to close.

        It returns a :class:`CleanupOutcome` rather than a bare bool because
        ``complete=False`` denoted TWO conditions a retrying caller must handle
        DIFFERENTLY -- a live event task versus one that died of an error. The
        WARN text distinguished them; the bool did not, and the status derived
        from it therefore could not either (issue #2021). ``CleanupOutcome``
        remains truthy exactly when cleanup completed, so ``if cleaned:`` is
        unchanged for a caller asking only the old question.

        THE JOIN IS BOUNDED AND DOES NOT RE-RAISE, for two reasons that both
        surfaced when ``stop()`` began running this from a ``finally`` while a
        caller-aimed ``CancelledError`` was propagating.

        ``await self._running_task`` STRANDS the caller when that task ignores
        cancellation -- the join never completes, so the ``finally`` never
        completes, and the caller who asked to be cancelled never regains
        control. That is a worse failure than the swallowed cancellation the
        channel work set out to fix, and it re-opens one task over the exact
        property ``test_stop_does_not_strand_a_caller_behind_an_unstoppable_task``
        already pins for ``_server_task``.

        ``await`` also RE-RAISES whatever the task died of. A real exception
        escaping here replaces the in-flight ``CancelledError`` and demotes it
        to ``__context__``, silently losing the cancellation -- the same defect
        one layer down.

        ``asyncio.wait`` fixes both: it observes completion without re-raising,
        and it takes a timeout. ``cancel()`` above is SYNCHRONOUS and has
        already landed, so the task is cancelled regardless of what the join
        observes; only the CONFIRMATION is bounded, which is the right
        semantics for a task that may never honour it.
        """
        complete = True
        event_task_live = False
        event_task_failed = False
        if self._running_task and not self._running_task.done():
            self._running_task.cancel()
            done, pending = await asyncio.wait(
                {self._running_task}, timeout=_CLEANUP_JOIN_TIMEOUT
            )
            # THE TASK'S OWN ERROR STILL HAS TO SURFACE. `asyncio.wait` does not
            # re-raise -- which is why it replaced the `await` that displaced
            # the caller's CancelledError -- but discarding `done` trades that
            # defect for the opposite one: a `_running_task` that died of a real
            # error is now silently swallowed, and Python additionally emits an
            # unstructured "Task exception was never retrieved" at GC. Retrieve
            # it and log it. Cancellation is the EXPECTED outcome here and is
            # not an error, so it is excluded.
            for task in done:
                if task.cancelled():
                    continue
                task_error = task.exception()
                if task_error is not None:
                    complete = False
                    event_task_failed = True
                    # LATCHED, not merely returned. The task is gone by the
                    # next call, so an unlatched failure evaporates on the
                    # first retry and the channel reports a clean STOPPED over
                    # a teardown that failed.
                    self._cleanup_failed = True
                    logger.warning(
                        "Channel %s: event task failed during cleanup: %s at %s",
                        self.name,
                        safe_type_name(task_error),
                        safe_exception_frames(task_error, limit=3),
                    )
            if pending:
                # BOUNDING THE JOIN WITHOUT READING ITS RESULT WOULD TRADE A
                # HANG FOR A LIE. `asyncio.wait` returns (done, pending) and
                # nothing else distinguishes "the task stopped" from "the
                # timeout elapsed and it is still running" -- so discarding the
                # result lets cleanup log success and the caller record STOPPED
                # over a live task. That is the false-success family this branch
                # exists to close, and the sibling bounded join in
                # `visualization/api.py` already shows the right shape: surface
                # the timeout, refuse to claim success.
                complete = False
                event_task_live = True
                logger.warning(
                    "Channel %s: event task did not stop within %ss; cleanup is "
                    "INCOMPLETE and the task is still live",
                    self.name,
                    _CLEANUP_JOIN_TIMEOUT,
                )

        if self._event_queue:
            # Clear any remaining events
            while not self._event_queue.empty():
                try:
                    self._event_queue.get_nowait()
                except asyncio.QueueEmpty:
                    break

        if complete:
            logger.info(f"Cleaned up channel {self.name}")
        return CleanupOutcome(
            complete=complete,
            event_task_live=event_task_live,
            event_task_failed=event_task_failed,
        )
