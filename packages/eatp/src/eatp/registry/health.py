# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""
Agent Health Monitoring - Background health checks for registered agents.

This module provides the AgentHealthMonitor for tracking agent health
and automatically suspending stale agents that stop responding.

Key Components:
- HealthStatus: Enum for agent health states
- AgentHealthMonitor: Background task for health monitoring
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Optional

from eatp.registry.agent_registry import AgentRegistry
from eatp.registry.models import AgentStatus

logger = logging.getLogger(__name__)


class HealthStatus(Enum):
    """
    Enumeration of agent health states.

    Health status is determined by the agent's activity and registry
    status. It provides a more granular view than AgentStatus alone.

    Values:
        HEALTHY: Agent is active and has sent heartbeats recently.
            This is the normal state for functioning agents.

        STALE: Agent is marked active but hasn't sent heartbeats
            within the expected interval. May indicate network issues
            or agent problems.

        SUSPENDED: Agent has been suspended due to extended inactivity.
            Auto-suspension happens after the stale timeout expires.

        UNKNOWN: Agent health cannot be determined. May occur if
            the agent is not in the registry or there's an error
            checking status.
    """

    HEALTHY = "HEALTHY"
    STALE = "STALE"
    SUSPENDED = "SUSPENDED"
    UNKNOWN = "UNKNOWN"


class AgentHealthMonitor:
    """
    Background health monitor for registered agents.

    The AgentHealthMonitor runs a background task that periodically
    checks for stale agents and optionally suspends them. This helps
    maintain registry accuracy and prevents discovery of unresponsive
    agents.

    Features:
    - Periodic health checks
    - Automatic stale detection
    - Optional auto-suspension
    - Individual agent health queries
    - Graceful start/stop

    Example:
        >>> monitor = AgentHealthMonitor(
        ...     registry=registry,
        ...     check_interval=60,    # Check every 60 seconds
        ...     stale_timeout=300,    # 5 minutes to become stale
        ...     auto_suspend_stale=True
        ... )
        >>>
        >>> await monitor.start()
        >>> # Monitor runs in background
        >>> health = await monitor.check_agent("agent-001")
        >>> assert health == HealthStatus.HEALTHY
        >>> await monitor.stop()
    """

    def __init__(
        self,
        registry: AgentRegistry,
        check_interval: int = 60,
        stale_timeout: int = 300,
        auto_suspend_stale: bool = True,
    ):
        """
        Initialize the AgentHealthMonitor.

        Args:
            registry: The AgentRegistry to monitor.

            check_interval: Seconds between health check cycles.
                Default is 60 seconds. Lower values provide faster
                stale detection but use more resources.

            stale_timeout: Seconds without heartbeat to consider an
                agent stale. Default is 300 seconds (5 minutes).
                Should be several times the expected heartbeat interval.

            auto_suspend_stale: Whether to automatically suspend stale
                agents. Default is True. If False, stale agents are
                only logged, not suspended.
        """
        self._registry = registry
        self._check_interval = check_interval
        self._stale_timeout = stale_timeout
        self._auto_suspend_stale = auto_suspend_stale

        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._last_check: Optional[datetime] = None

    async def start(self) -> None:
        """
        Start the health monitoring background task.

        This method returns immediately after starting the background
        task. Use stop() to stop the monitoring.

        Raises:
            RuntimeError: If monitor is already running.
        """
        if self._running:
            raise RuntimeError("Health monitor is already running")

        self._running = True
        self._task = asyncio.create_task(self._monitoring_loop())

        logger.info(
            f"AgentHealthMonitor started: check_interval={self._check_interval}s, "
            f"stale_timeout={self._stale_timeout}s, auto_suspend={self._auto_suspend_stale}"
        )

    async def stop(self) -> None:
        """
        Stop the health monitoring background task.

        Waits for the current check cycle to complete before returning.
        """
        if not self._running:
            return

        self._running = False

        if self._task:
            # Cancel the task
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

        logger.info("AgentHealthMonitor stopped")

    async def check_agent(self, agent_id: str) -> HealthStatus:
        """
        Check a specific agent's health status.

        This method does not modify agent status, only reports it.

        Args:
            agent_id: ID of the agent to check.

        Returns:
            HealthStatus indicating the agent's current health.
        """
        try:
            metadata = await self._registry.get(agent_id)

            if not metadata:
                return HealthStatus.UNKNOWN

            if metadata.status == AgentStatus.SUSPENDED:
                return HealthStatus.SUSPENDED

            if metadata.status != AgentStatus.ACTIVE:
                return HealthStatus.UNKNOWN

            # Check if stale
            cutoff = datetime.now(timezone.utc) - timedelta(seconds=self._stale_timeout)
            if metadata.last_seen < cutoff:
                return HealthStatus.STALE

            return HealthStatus.HEALTHY

        except Exception as e:
            logger.error(f"Error checking health for {agent_id}: {e}")
            return HealthStatus.UNKNOWN

    @property
    def is_running(self) -> bool:
        """Check if the monitor is currently running."""
        return self._running

    @property
    def last_check(self) -> Optional[datetime]:
        """Get the timestamp of the last health check cycle."""
        return self._last_check

    async def _monitoring_loop(self) -> None:
        """
        Main monitoring loop that runs in the background.

        Checks for stale agents at regular intervals and optionally
        suspends them.
        """
        while self._running:
            try:
                await self._check_health()
                self._last_check = datetime.now(timezone.utc)

            except Exception as e:
                logger.error(f"Health monitoring error: {e}")
                # Continue monitoring despite errors

            # Wait for next check interval
            try:
                await asyncio.sleep(self._check_interval)
            except asyncio.CancelledError:
                break

    async def _check_health(self) -> None:
        """
        Perform a single health check cycle.

        Gets all stale agents and optionally suspends them.
        """
        try:
            # Get stale agents
            stale_agents = await self._registry.get_stale_agents(timeout=self._stale_timeout)

            if not stale_agents:
                logger.debug("Health check: no stale agents found")
                return

            logger.info(f"Health check: found {len(stale_agents)} stale agent(s)")

            # Auto-suspend if configured
            if self._auto_suspend_stale:
                for agent in stale_agents:
                    try:
                        await self._registry.update_status(
                            agent.agent_id,
                            AgentStatus.SUSPENDED,
                            reason=f"No heartbeat for {self._stale_timeout}s",
                        )
                        logger.warning(f"Auto-suspended stale agent: {agent.agent_id} (last seen: {agent.last_seen})")

                    except Exception as e:
                        logger.error(f"Failed to suspend stale agent {agent.agent_id}: {e}")
            else:
                # Just log the stale agents
                for agent in stale_agents:
                    logger.warning(f"Stale agent detected: {agent.agent_id} (last seen: {agent.last_seen})")

        except Exception as e:
            logger.error(f"Error during health check: {e}")
            raise

    async def run_immediate_check(self) -> int:
        """
        Run an immediate health check outside the regular cycle.

        Returns:
            Number of stale agents found (and optionally suspended).
        """
        stale_agents = await self._registry.get_stale_agents(timeout=self._stale_timeout)

        if self._auto_suspend_stale:
            for agent in stale_agents:
                try:
                    await self._registry.update_status(
                        agent.agent_id,
                        AgentStatus.SUSPENDED,
                        reason=f"No heartbeat for {self._stale_timeout}s",
                    )
                except Exception as e:
                    logger.error(f"Failed to suspend {agent.agent_id}: {e}")

        return len(stale_agents)

    async def reactivate_agent(self, agent_id: str) -> bool:
        """
        Reactivate a suspended agent.

        This sets the agent's status back to ACTIVE and updates
        its last_seen timestamp.

        Args:
            agent_id: ID of the agent to reactivate.

        Returns:
            True if reactivation succeeded, False otherwise.
        """
        try:
            metadata = await self._registry.get(agent_id)

            if not metadata:
                logger.warning(f"Cannot reactivate {agent_id}: not found")
                return False

            if metadata.status != AgentStatus.SUSPENDED:
                logger.warning(f"Cannot reactivate {agent_id}: status is {metadata.status.value}")
                return False

            await self._registry.update_status(
                agent_id,
                AgentStatus.ACTIVE,
                reason="Reactivated by health monitor",
            )

            await self._registry.heartbeat(agent_id)

            logger.info(f"Reactivated agent: {agent_id}")
            return True

        except Exception as e:
            logger.error(f"Error reactivating {agent_id}: {e}")
            return False
