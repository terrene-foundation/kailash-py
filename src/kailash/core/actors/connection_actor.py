"""Actor-based connection management for Kailash SDK.

This module implements an actor-based approach to database connections,
providing better isolation, fault tolerance, and concurrent handling
compared to traditional thread-based models.
"""

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any, Callable, Dict, Optional, Union

logger = logging.getLogger(__name__)


class ConnectionState(Enum):
    """Connection lifecycle states."""

    INITIALIZING = "initializing"
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    RECYCLING = "recycling"
    FAILED = "failed"
    TERMINATED = "terminated"


class MessageType(Enum):
    """Actor message types."""

    QUERY = "query"
    HEALTH_CHECK = "health_check"
    RECYCLE = "recycle"
    TERMINATE = "terminate"
    GET_STATS = "get_stats"
    PING = "ping"


@dataclass
class Message:
    """Message for actor communication."""

    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    type: MessageType = MessageType.QUERY
    payload: Any = None
    reply_to: Optional[asyncio.Queue] = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class QueryResult:
    """Result of a database query."""

    success: bool
    data: Optional[Any] = None
    error: Optional[str] = None
    execution_time: float = 0.0
    connection_id: Optional[str] = None


@dataclass
class ConnectionStats:
    """Statistics for a connection."""

    queries_executed: int = 0
    errors_encountered: int = 0
    total_execution_time: float = 0.0
    health_checks_passed: int = 0
    health_checks_failed: int = 0
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    last_used_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    health_score: float = 100.0


class ActorConnection:
    """
    Actor-based database connection with isolated state and message passing.

    This class represents a single database connection as an independent actor
    with its own mailbox, state, and lifecycle management.
    """

    def __init__(
        self,
        connection_id: str,
        db_config: Dict[str, Any],
        health_check_query: str = "SELECT 1",
        health_check_interval: float = 30.0,
        max_lifetime: float = 3600.0,
        max_idle_time: float = 600.0,
    ):
        """
        Initialize an actor connection.

        Args:
            connection_id: Unique identifier for this connection
            db_config: Database configuration parameters
            health_check_query: Query to run for health checks
            health_check_interval: Seconds between health checks
            max_lifetime: Maximum connection lifetime in seconds
            max_idle_time: Maximum idle time before recycling
        """
        self.id = connection_id
        self.db_config = db_config
        self.health_check_query = health_check_query
        self.health_check_interval = health_check_interval
        self.max_lifetime = max_lifetime
        self.max_idle_time = max_idle_time

        # Actor state
        self.state = ConnectionState.INITIALIZING
        self.mailbox = asyncio.Queue(maxsize=100)
        self.stats = ConnectionStats()
        self.supervisor = None

        # Physical connection (set during connect)
        self._connection = None
        self._adapter = None

        # Background tasks
        self._message_handler_task = None
        self._health_monitor_task = None

        # Lifecycle tracking
        self._created_at = time.time()
        self._last_activity = time.time()

    async def start(self):
        """Start the actor and its background tasks."""
        try:
            # Establish connection
            await self._connect()

            # Start message handler
            self._message_handler_task = asyncio.create_task(self._handle_messages())

            # Start health monitor
            self._health_monitor_task = asyncio.create_task(self._monitor_health())

            self.state = ConnectionState.HEALTHY
            logger.info(f"Connection actor {self.id} started successfully")

        except Exception as e:
            self.state = ConnectionState.FAILED
            logger.error(f"Failed to start connection actor {self.id}: {e}")
            raise

    async def stop(self):
        """Stop the actor gracefully."""
        self.state = ConnectionState.TERMINATED

        # Cancel background tasks
        if self._message_handler_task:
            self._message_handler_task.cancel()
            try:
                await self._message_handler_task
            except asyncio.CancelledError:
                pass

        if self._health_monitor_task:
            self._health_monitor_task.cancel()
            try:
                await self._health_monitor_task
            except asyncio.CancelledError:
                pass

        # Close connection
        await self._disconnect()

        logger.info(f"Connection actor {self.id} stopped")

    async def send_message(self, message: Message) -> Any:
        """
        Send a message to the actor and wait for response.

        Args:
            message: Message to send

        Returns:
            Response from the actor
        """
        if self.state == ConnectionState.TERMINATED:
            raise RuntimeError(f"Actor {self.id} is terminated")

        # Create reply queue if not provided
        if not message.reply_to:
            message.reply_to = asyncio.Queue(maxsize=1)

        # Send message
        await self.mailbox.put(message)

        # Wait for reply
        response = await message.reply_to.get()
        return response

    async def _handle_messages(self):
        """Main message handling loop."""
        message = None
        while self.state != ConnectionState.TERMINATED:
            try:
                # Check if event loop is still running
                try:
                    asyncio.get_running_loop()
                except RuntimeError:
                    # Event loop closed, terminate gracefully
                    break

                # Wait for message with timeout
                message = await asyncio.wait_for(self.mailbox.get(), timeout=1.0)

                # Update activity timestamp
                self._last_activity = time.time()

                # Process message based on type
                if message.type == MessageType.QUERY:
                    response = await self._handle_query(message.payload)
                elif message.type == MessageType.HEALTH_CHECK:
                    response = await self._handle_health_check()
                elif message.type == MessageType.RECYCLE:
                    response = await self._handle_recycle()
                elif message.type == MessageType.GET_STATS:
                    response = self._get_stats()
                elif message.type == MessageType.PING:
                    response = {"status": "pong", "state": self.state.value}
                else:
                    response = {"error": f"Unknown message type: {message.type}"}

                # Send reply if requested (check if we can still send replies)
                if message and message.reply_to:
                    try:
                        await message.reply_to.put(response)
                    except RuntimeError:
                        # Queue is bound to different event loop, skip reply
                        pass

                # Clear message reference
                message = None

            except asyncio.TimeoutError:
                # Check if connection should be recycled
                if self._should_recycle():
                    await self._initiate_recycle()
            except (asyncio.CancelledError, GeneratorExit):
                # Handle graceful shutdown
                break
            except Exception as e:
                logger.error(f"Error handling message in actor {self.id}: {e}")
                if message and message.reply_to:
                    try:
                        await message.reply_to.put({"error": str(e)})
                    except RuntimeError:
                        # Queue is bound to different event loop, skip reply
                        pass
                message = None

    async def _handle_query(self, query_params: Dict[str, Any]) -> QueryResult:
        """Execute a database query."""
        start_time = time.time()

        try:
            if self.state != ConnectionState.HEALTHY:
                return QueryResult(
                    success=False,
                    error=f"Connection in {self.state.value} state",
                    connection_id=self.id,
                )

            # Import FetchMode enum
            from kailash.nodes.data.async_sql import FetchMode

            # Execute query using adapter
            fetch_mode_str = query_params.get("fetch_mode", "all")
            fetch_mode = FetchMode(fetch_mode_str.lower())

            result = await self._adapter.execute(
                query=query_params.get("query"),
                params=query_params.get("params"),
                fetch_mode=fetch_mode,
            )

            execution_time = time.time() - start_time

            # Update stats
            self.stats.queries_executed += 1
            self.stats.total_execution_time += execution_time
            self.stats.last_used_at = datetime.now(UTC)

            return QueryResult(
                success=True,
                data=result,
                execution_time=execution_time,
                connection_id=self.id,
            )

        except Exception as e:
            execution_time = time.time() - start_time
            self.stats.errors_encountered += 1

            # Degrade connection on errors
            self._update_health_score(-10)

            return QueryResult(
                success=False,
                error=str(e),
                execution_time=execution_time,
                connection_id=self.id,
            )

    async def _handle_health_check(self) -> Dict[str, Any]:
        """Perform a health check."""
        try:
            start_time = time.time()

            # Import FetchMode enum
            from kailash.nodes.data.async_sql import FetchMode

            # Run health check query
            await self._adapter.execute(
                query=self.health_check_query, params=None, fetch_mode=FetchMode.ONE
            )

            check_time = time.time() - start_time

            # Update stats
            self.stats.health_checks_passed += 1
            self._update_health_score(5)  # Boost score on success

            return {
                "healthy": True,
                "check_time": check_time,
                "health_score": self.stats.health_score,
            }

        except Exception as e:
            self.stats.health_checks_failed += 1
            self._update_health_score(-20)  # Significant penalty on failure

            return {
                "healthy": False,
                "error": str(e),
                "health_score": self.stats.health_score,
            }

    async def _handle_recycle(self) -> Dict[str, Any]:
        """Handle connection recycling request."""
        if self.state == ConnectionState.RECYCLING:
            return {"status": "already_recycling"}

        self.state = ConnectionState.RECYCLING

        # Notify supervisor if present
        if self.supervisor:
            await self.supervisor.notify_recycling(self.id)

        return {"status": "recycling_initiated"}

    def _get_stats(self) -> Dict[str, Any]:
        """Get connection statistics."""
        uptime = time.time() - self._created_at
        idle_time = time.time() - self._last_activity

        return {
            "connection_id": self.id,
            "state": self.state.value,
            "stats": {
                "queries_executed": self.stats.queries_executed,
                "errors_encountered": self.stats.errors_encountered,
                "avg_execution_time": (
                    self.stats.total_execution_time / self.stats.queries_executed
                    if self.stats.queries_executed > 0
                    else 0
                ),
                "health_checks_passed": self.stats.health_checks_passed,
                "health_checks_failed": self.stats.health_checks_failed,
                "health_score": self.stats.health_score,
                "uptime_seconds": uptime,
                "idle_seconds": idle_time,
            },
        }

    async def _monitor_health(self):
        """Background health monitoring task."""
        while self.state not in [ConnectionState.TERMINATED, ConnectionState.RECYCLING]:
            try:
                await asyncio.sleep(self.health_check_interval)

                # Send health check message to self
                health_result = await self.send_message(
                    Message(type=MessageType.HEALTH_CHECK)
                )

                # Update state based on health
                if not health_result.get("healthy"):
                    if self.stats.health_score < 30:
                        self.state = ConnectionState.FAILED
                        if self.supervisor:
                            await self.supervisor.notify_failure(self.id)
                    elif self.stats.health_score < 50:
                        self.state = ConnectionState.DEGRADED
                else:
                    if (
                        self.state == ConnectionState.DEGRADED
                        and self.stats.health_score > 70
                    ):
                        self.state = ConnectionState.HEALTHY

            except Exception as e:
                logger.error(f"Health monitor error in actor {self.id}: {e}")

    def _should_recycle(self) -> bool:
        """Check if connection should be recycled."""
        # Check lifetime
        if time.time() - self._created_at > self.max_lifetime:
            return True

        # Check idle time
        if time.time() - self._last_activity > self.max_idle_time:
            return True

        # Check health score
        if self.stats.health_score < 20:
            return True

        return False

    async def _initiate_recycle(self):
        """Initiate connection recycling."""
        await self.send_message(Message(type=MessageType.RECYCLE))

    def _update_health_score(self, delta: float):
        """Update health score with bounds checking."""
        self.stats.health_score = max(0, min(100, self.stats.health_score + delta))

        # Update state based on score
        if self.stats.health_score < 30:
            self.state = ConnectionState.DEGRADED
        elif self.stats.health_score > 70 and self.state == ConnectionState.DEGRADED:
            self.state = ConnectionState.HEALTHY

    async def _connect(self):
        """Establish physical database connection."""
        # Import here to avoid circular dependencies
        from kailash.nodes.data.async_sql import (
            DatabaseConfig,
            DatabaseType,
            MySQLAdapter,
            PostgreSQLAdapter,
            SQLiteAdapter,
        )

        # Determine database type
        db_type = DatabaseType(self.db_config["type"].lower())

        # Create configuration
        config = DatabaseConfig(
            type=db_type,
            host=self.db_config.get("host"),
            port=self.db_config.get("port"),
            database=self.db_config.get("database"),
            user=self.db_config.get("user"),
            password=self.db_config.get("password"),
            connection_string=self.db_config.get("connection_string"),
            pool_size=1,  # Single connection per actor
            max_pool_size=1,
        )

        # Create adapter
        if db_type == DatabaseType.POSTGRESQL:
            self._adapter = PostgreSQLAdapter(config)
        elif db_type == DatabaseType.MYSQL:
            self._adapter = MySQLAdapter(config)
        elif db_type == DatabaseType.SQLITE:
            self._adapter = SQLiteAdapter(config)
        else:
            raise ValueError(f"Unsupported database type: {db_type}")

        # Connect
        await self._adapter.connect()
        logger.info(f"Connection actor {self.id} connected to {db_type.value}")

    async def _disconnect(self):
        """Close physical database connection."""
        if self._adapter:
            await self._adapter.disconnect()
            self._adapter = None
            logger.info(f"Connection actor {self.id} disconnected")


class ConnectionActor:
    """
    High-level interface for interacting with actor connections.

    This class provides a convenient API for sending messages to
    connection actors without dealing with low-level message passing.
    """

    def __init__(self, actor: ActorConnection):
        """
        Initialize connection actor interface.

        Args:
            actor: The underlying actor connection
        """
        self.actor = actor

    async def execute(
        self,
        query: str,
        params: Optional[Union[tuple, dict]] = None,
        fetch_mode: str = "all",
    ) -> QueryResult:
        """
        Execute a database query.

        Args:
            query: SQL query to execute
            params: Query parameters
            fetch_mode: How to fetch results (one, all, many)

        Returns:
            Query result with data or error
        """
        return await self.actor.send_message(
            Message(
                type=MessageType.QUERY,
                payload={"query": query, "params": params, "fetch_mode": fetch_mode},
            )
        )

    async def health_check(self) -> Dict[str, Any]:
        """Perform a health check on the connection."""
        return await self.actor.send_message(Message(type=MessageType.HEALTH_CHECK))

    async def get_stats(self) -> Dict[str, Any]:
        """Get connection statistics."""
        return await self.actor.send_message(Message(type=MessageType.GET_STATS))

    async def recycle(self) -> Dict[str, Any]:
        """Request connection recycling."""
        return await self.actor.send_message(Message(type=MessageType.RECYCLE))

    async def ping(self) -> Dict[str, Any]:
        """Ping the connection actor."""
        return await self.actor.send_message(Message(type=MessageType.PING))

    @property
    def id(self) -> str:
        """Get connection ID."""
        return self.actor.id

    @property
    def state(self) -> ConnectionState:
        """Get current connection state."""
        return self.actor.state

    @property
    def health_score(self) -> float:
        """Get current health score."""
        return self.actor.stats.health_score

    async def stop(self):
        """Stop the underlying actor connection."""
        await self.actor.stop()
