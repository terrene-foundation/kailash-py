"""Actor supervision for fault tolerance.

This module implements supervision strategies for managing actor lifecycles
and handling failures gracefully.
"""

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from .connection_actor import ActorConnection, ConnectionState

logger = logging.getLogger(__name__)


class SupervisionStrategy(Enum):
    """Supervision strategies for handling actor failures."""

    ONE_FOR_ONE = "one_for_one"  # Restart only the failed actor
    ONE_FOR_ALL = "one_for_all"  # Restart all actors on any failure
    REST_FOR_ONE = "rest_for_one"  # Restart failed actor and all after it


class RestartDecision(Enum):
    """Decision on whether to restart a failed actor."""

    RESTART = "restart"
    STOP = "stop"
    ESCALATE = "escalate"


class ActorSupervisor:
    """
    Supervises a group of actors, handling failures and restarts.

    Inspired by Erlang/OTP supervision trees, this class manages
    actor lifecycles and implements various restart strategies.
    """

    def __init__(
        self,
        name: str,
        strategy: SupervisionStrategy = SupervisionStrategy.ONE_FOR_ONE,
        max_restarts: int = 3,
        restart_window: float = 60.0,
        restart_delay: float = 1.0,
    ):
        """
        Initialize actor supervisor.

        Args:
            name: Supervisor name
            strategy: Supervision strategy to use
            max_restarts: Maximum restarts within window
            restart_window: Time window for restart counting (seconds)
            restart_delay: Delay between restarts (seconds)
        """
        self.name = name
        self.strategy = strategy
        self.max_restarts = max_restarts
        self.restart_window = restart_window
        self.restart_delay = restart_delay

        # Supervised actors
        self.actors: Dict[str, ActorConnection] = {}
        self.actor_order: List[str] = []  # For REST_FOR_ONE strategy

        # Restart tracking
        self.restart_counts: Dict[str, List[datetime]] = {}

        # Callbacks
        self.on_actor_failure: Optional[Callable[[str, Exception], None]] = None
        self.on_actor_restart: Optional[Callable[[str, int], None]] = None
        self.on_supervisor_failure: Optional[Callable[[Exception], None]] = None

        # Supervisor state
        self._running = False
        self._monitor_task = None

    async def start(self):
        """Start the supervisor and all actors."""
        self._running = True

        # Start all actors
        for actor_id in self.actor_order:
            actor = self.actors[actor_id]
            actor.supervisor = self
            await self._start_actor(actor)

        # Start monitoring
        self._monitor_task = asyncio.create_task(self._monitor_actors())

        logger.info(f"Supervisor {self.name} started with {len(self.actors)} actors")

    async def stop(self):
        """Stop the supervisor and all actors."""
        self._running = False

        # Cancel monitoring
        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass

        # Stop all actors
        for actor in self.actors.values():
            await actor.stop()

        logger.info(f"Supervisor {self.name} stopped")

    def add_actor(self, actor: ActorConnection):
        """
        Add an actor to supervision.

        Args:
            actor: Actor to supervise
        """
        self.actors[actor.id] = actor
        self.actor_order.append(actor.id)
        self.restart_counts[actor.id] = []
        actor.supervisor = self

        # Start actor if supervisor is running
        if self._running:
            asyncio.create_task(self._start_actor(actor))

    def remove_actor(self, actor_id: str):
        """
        Remove an actor from supervision.

        Args:
            actor_id: ID of actor to remove
        """
        if actor_id in self.actors:
            actor = self.actors[actor_id]
            asyncio.create_task(actor.stop())

            del self.actors[actor_id]
            self.actor_order.remove(actor_id)
            del self.restart_counts[actor_id]

    async def notify_failure(self, actor_id: str, error: Optional[Exception] = None):
        """
        Notify supervisor of actor failure.

        Args:
            actor_id: ID of failed actor
            error: Exception that caused failure
        """
        logger.warning(f"Actor {actor_id} failed: {error}")

        # Callback
        if self.on_actor_failure:
            self.on_actor_failure(actor_id, error)

        # Decide on restart
        decision = self._decide_restart(actor_id)

        if decision == RestartDecision.RESTART:
            await self._handle_restart(actor_id)
        elif decision == RestartDecision.STOP:
            self.remove_actor(actor_id)
        elif decision == RestartDecision.ESCALATE:
            await self._escalate_failure(error)

    async def notify_recycling(self, actor_id: str):
        """
        Notify supervisor that actor is recycling.

        Args:
            actor_id: ID of recycling actor
        """
        logger.info(f"Actor {actor_id} is recycling")

        # Create replacement actor
        if actor_id in self.actors:
            old_actor = self.actors[actor_id]

            # Create new actor with same config
            new_actor = ActorConnection(
                connection_id=f"{actor_id}_new",
                db_config=old_actor.db_config,
                health_check_query=old_actor.health_check_query,
                health_check_interval=old_actor.health_check_interval,
                max_lifetime=old_actor.max_lifetime,
                max_idle_time=old_actor.max_idle_time,
            )

            # Start new actor
            await self._start_actor(new_actor)

            # Swap actors
            await self._swap_actors(actor_id, new_actor)

    async def _monitor_actors(self):
        """Monitor actor health periodically."""
        while self._running:
            try:
                await asyncio.sleep(0.1)  # Fast health checks for tests

                for actor_id, actor in list(self.actors.items()):
                    if actor.state == ConnectionState.FAILED:
                        await self.notify_failure(actor_id)
                    elif actor.state == ConnectionState.TERMINATED:
                        # Actor stopped unexpectedly
                        await self.notify_failure(
                            actor_id, RuntimeError("Actor terminated unexpectedly")
                        )

            except Exception as e:
                logger.error(f"Monitor error in supervisor {self.name}: {e}")

    async def _start_actor(self, actor: ActorConnection):
        """Start an actor with error handling."""
        try:
            await actor.start()
        except Exception as e:
            logger.error(f"Failed to start actor {actor.id}: {e}")
            await self.notify_failure(actor.id, e)

    def _decide_restart(self, actor_id: str) -> RestartDecision:
        """Decide whether to restart a failed actor."""
        # Check restart count within window
        now = datetime.now(UTC)
        window_start = now - timedelta(seconds=self.restart_window)

        # Filter restarts within window
        recent_restarts = [
            ts for ts in self.restart_counts[actor_id] if ts > window_start
        ]

        if len(recent_restarts) >= self.max_restarts:
            logger.error(
                f"Actor {actor_id} exceeded max restarts "
                f"({self.max_restarts} in {self.restart_window}s)"
            )
            return RestartDecision.ESCALATE

        return RestartDecision.RESTART

    async def _handle_restart(self, actor_id: str):
        """Handle actor restart based on strategy."""
        # Record restart
        self.restart_counts[actor_id].append(datetime.now(UTC))

        # Delay before restart
        await asyncio.sleep(self.restart_delay)

        if self.strategy == SupervisionStrategy.ONE_FOR_ONE:
            await self._restart_one(actor_id)
        elif self.strategy == SupervisionStrategy.ONE_FOR_ALL:
            await self._restart_all()
        elif self.strategy == SupervisionStrategy.REST_FOR_ONE:
            await self._restart_rest(actor_id)

        # Callback
        if self.on_actor_restart:
            restart_count = len(self.restart_counts[actor_id])
            self.on_actor_restart(actor_id, restart_count)

    async def _restart_one(self, actor_id: str):
        """Restart a single actor."""
        if actor_id not in self.actors:
            return

        actor = self.actors[actor_id]

        # Stop the failed actor
        await actor.stop()

        # Create new actor with same config
        new_actor = ActorConnection(
            connection_id=actor_id,
            db_config=actor.db_config,
            health_check_query=actor.health_check_query,
            health_check_interval=actor.health_check_interval,
            max_lifetime=actor.max_lifetime,
            max_idle_time=actor.max_idle_time,
        )

        # Replace and start
        self.actors[actor_id] = new_actor
        new_actor.supervisor = self
        await self._start_actor(new_actor)

    async def _restart_all(self):
        """Restart all actors."""
        # Stop all actors
        for actor in self.actors.values():
            await actor.stop()

        # Restart all
        for actor_id in self.actor_order:
            await self._restart_one(actor_id)

    async def _restart_rest(self, failed_actor_id: str):
        """Restart failed actor and all actors after it."""
        if failed_actor_id not in self.actor_order:
            return

        failed_index = self.actor_order.index(failed_actor_id)

        # Restart from failed actor onwards
        for i in range(failed_index, len(self.actor_order)):
            actor_id = self.actor_order[i]
            await self._restart_one(actor_id)

    async def _swap_actors(self, old_id: str, new_actor: ActorConnection):
        """Atomically swap an old actor with a new one."""
        if old_id not in self.actors:
            return

        old_actor = self.actors[old_id]

        # Wait for old actor to drain
        drain_timeout = 30.0
        start_time = asyncio.get_event_loop().time()

        while old_actor.state != ConnectionState.TERMINATED:
            if asyncio.get_event_loop().time() - start_time > drain_timeout:
                logger.warning(f"Timeout draining actor {old_id}, forcing stop")
                break
            await asyncio.sleep(0.1)

        # Stop old actor
        await old_actor.stop()

        # Replace with new actor
        self.actors[old_id] = new_actor
        new_actor.supervisor = self

        logger.info(f"Swapped actor {old_id} with new instance")

    async def _escalate_failure(self, error: Optional[Exception]):
        """Escalate failure to higher level."""
        logger.critical(f"Supervisor {self.name} escalating failure: {error}")

        if self.on_supervisor_failure:
            self.on_supervisor_failure(error)
        else:
            # Default behavior: stop supervisor
            await self.stop()

    def get_stats(self) -> Dict[str, Any]:
        """Get supervisor statistics."""
        stats = {
            "name": self.name,
            "strategy": self.strategy.value,
            "running": self._running,
            "actors": {},
        }

        for actor_id, actor in self.actors.items():
            stats["actors"][actor_id] = {
                "state": actor.state.value,
                "health_score": actor.stats.health_score,
                "restart_count": len(self.restart_counts.get(actor_id, [])),
            }

        return stats
