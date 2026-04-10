# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Circuit breaker for automatic posture downgrade on agent failures.

Implements the circuit breaker pattern to automatically downgrade agent
postures when failures exceed thresholds, protecting the system from
cascading failures.

Concurrency Model:
    This module uses ``asyncio.Lock`` for coroutine-safe access, NOT
    ``threading.Lock``. This means:

    - Safe: Multiple coroutines in a single-threaded asyncio event loop
    - NOT safe: Multiple OS threads calling these methods concurrently
    - NOT safe: Multiple processes (use file locking for cross-process)

    If thread-safety is required, callers must provide external
    synchronization. A ``threading_mode`` parameter is reserved as a
    future extension point for native thread-safe operation.

    The same ``asyncio.Lock`` pattern is used across 10+ modules in the
    EATP SDK including cache.py, rotation.py, security.py,
    replay_protection.py, channel.py, esa/api.py, and
    revocation/broadcaster.py. All share this concurrency model.

Part of CARE-028: PostureCircuitBreaker implementation.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from kailash.trust.posture.postures import (
    PostureStateMachine,
    PostureTransitionRequest,
    TrustPosture,
)

logger = logging.getLogger(__name__)


class CircuitState(str, Enum):
    """State of the circuit breaker.

    - CLOSED: Normal operation, failures are counted
    - HALF_OPEN: Testing recovery, limited calls allowed
    - OPEN: Failures blocked, posture downgraded
    """

    CLOSED = "closed"
    HALF_OPEN = "half_open"
    OPEN = "open"


@dataclass
class FailureEvent:
    """Record of a failure event.

    Attributes:
        timestamp: When the failure occurred
        error_type: Type/class of the error
        error_message: Error message
        action: The action that failed
        severity: Severity level (low, medium, high, critical)
    """

    timestamp: datetime
    error_type: str
    error_message: str
    action: str
    severity: str = "medium"

    def __post_init__(self):
        """Validate severity."""
        valid_severities = {"low", "medium", "high", "critical"}
        if self.severity not in valid_severities:
            raise ValueError(
                f"Invalid severity '{self.severity}'. Must be one of: {valid_severities}"
            )


@dataclass
class CircuitBreakerConfig:
    """Configuration for the circuit breaker.

    Attributes:
        failure_threshold: Number of weighted failures to open circuit
        recovery_timeout: Seconds to wait before transitioning to half-open
        half_open_max_calls: Max calls allowed in half-open state
        failure_window_seconds: Window for counting failures
        severity_weights: Weights for different severity levels
        downgrade_on_open: Posture to downgrade to when circuit opens
    """

    failure_threshold: int = 5
    recovery_timeout: int = 60
    half_open_max_calls: int = 3
    failure_window_seconds: int = 300
    severity_weights: Dict[str, float] = field(
        default_factory=lambda: {
            "low": 0.5,
            "medium": 1.0,
            "high": 2.0,
            "critical": 5.0,
        }
    )
    downgrade_on_open: str = "supervised"

    def __post_init__(self):
        """Validate configuration."""
        if self.failure_threshold < 1:
            raise ValueError("failure_threshold must be at least 1")
        if self.recovery_timeout < 0:
            raise ValueError("recovery_timeout must be non-negative")
        if self.half_open_max_calls < 1:
            raise ValueError("half_open_max_calls must be at least 1")
        if self.failure_window_seconds < 1:
            raise ValueError("failure_window_seconds must be at least 1")

        # Validate downgrade_on_open is a valid posture
        valid_postures = {p.value for p in TrustPosture}
        if self.downgrade_on_open not in valid_postures:
            raise ValueError(
                f"Invalid downgrade_on_open '{self.downgrade_on_open}'. Must be one of: {valid_postures}"
            )


class PostureCircuitBreaker:
    """Circuit breaker for automatic posture downgrade on agent failures.

    Tracks failures per agent and automatically downgrades postures when
    failures exceed thresholds. Implements the three-state circuit breaker
    pattern: CLOSED -> OPEN -> HALF_OPEN -> CLOSED.

    Example:
        >>> from kailash.trust.posture.postures import PostureStateMachine, TrustPosture
        >>> from kailash.trust.circuit_breaker import PostureCircuitBreaker
        >>>
        >>> machine = PostureStateMachine()
        >>> machine.set_posture("agent-001", TrustPosture.AUTONOMOUS)
        >>> breaker = PostureCircuitBreaker(machine)
        >>>
        >>> # Record failures
        >>> await breaker.record_failure(
        ...     "agent-001", "ConnectionError", "Failed to connect", "api_call"
        ... )
        >>>
        >>> # Check if agent can proceed
        >>> can_proceed = await breaker.can_proceed("agent-001")
    """

    def __init__(
        self,
        posture_machine: PostureStateMachine,
        config: Optional[CircuitBreakerConfig] = None,
        max_failures_per_agent: int = 10_000,
    ):
        """Initialize the circuit breaker.

        Args:
            posture_machine: The PostureStateMachine to use for transitions
            config: Configuration for the circuit breaker
            max_failures_per_agent: Maximum failure events stored per agent.
                When exceeded, oldest 10% are trimmed. Default 10,000.
        """
        self._posture_machine = posture_machine
        self._config = config or CircuitBreakerConfig()
        self._max_failures_per_agent = max_failures_per_agent

        # Per-agent state tracking (bounded by _max_failures_per_agent)
        self._states: Dict[str, CircuitState] = {}
        self._failures: Dict[str, List[FailureEvent]] = {}
        self._last_failure: Dict[str, datetime] = {}
        self._half_open_calls: Dict[str, int] = {}
        self._half_open_successes: Dict[str, int] = {}
        self._original_postures: Dict[str, TrustPosture] = {}
        self._open_time: Dict[str, datetime] = {}

        # Lock for thread-safe operations
        self._lock = asyncio.Lock()

    def get_state(self, agent_id: str) -> CircuitState:
        """Get the current circuit state for an agent.

        Args:
            agent_id: The agent ID

        Returns:
            The current CircuitState (defaults to CLOSED)
        """
        return self._states.get(agent_id, CircuitState.CLOSED)

    async def record_failure(
        self,
        agent_id: str,
        error_type: str,
        error_message: str,
        action: str,
        severity: str = "medium",
    ) -> None:
        """Record a failure event for an agent.

        This may trigger circuit opening if the weighted failure count
        exceeds the threshold.

        Args:
            agent_id: The agent ID
            error_type: Type/class of the error
            error_message: Error message
            action: The action that failed
            severity: Severity level (low, medium, high, critical)
        """
        async with self._lock:
            event = FailureEvent(
                timestamp=datetime.now(timezone.utc),
                error_type=error_type,
                error_message=error_message,
                action=action,
                severity=severity,
            )

            # Initialize failure list if needed
            if agent_id not in self._failures:
                self._failures[agent_id] = []

            # Clean old failures before adding new one
            self._clean_old_failures(agent_id)

            # Add the failure
            self._failures[agent_id].append(event)
            self._last_failure[agent_id] = event.timestamp

            # Enforce bounded collection: trim oldest 10% when capacity exceeded
            if len(self._failures[agent_id]) > self._max_failures_per_agent:
                trim_count = self._max_failures_per_agent // 10
                self._failures[agent_id] = self._failures[agent_id][trim_count:]
                logger.debug(
                    f"Trimmed {trim_count} oldest failures for agent {agent_id} "
                    f"(capacity {self._max_failures_per_agent} exceeded)"
                )

            current_state = self.get_state(agent_id)

            if current_state == CircuitState.HALF_OPEN:
                # Any failure in half-open reopens the circuit
                await self._open_circuit(
                    agent_id, f"Failure during half-open test: {error_message}"
                )
            elif current_state == CircuitState.CLOSED:
                # Check if we should open the circuit
                weighted_failures = self._calculate_weighted_failures(agent_id)
                if weighted_failures >= self._config.failure_threshold:
                    await self._open_circuit(
                        agent_id,
                        f"Weighted failure count ({weighted_failures:.1f}) "
                        f"exceeded threshold ({self._config.failure_threshold})",
                    )

            logger.debug(
                f"Recorded failure for agent {agent_id}: {error_type} - {error_message} (severity: {severity})"
            )

    async def record_success(self, agent_id: str) -> None:
        """Record a successful action for an agent.

        In half-open state, this counts toward closing the circuit.
        In closed state, this is a no-op.

        Args:
            agent_id: The agent ID
        """
        async with self._lock:
            current_state = self.get_state(agent_id)

            if current_state == CircuitState.HALF_OPEN:
                self._half_open_successes[agent_id] = (
                    self._half_open_successes.get(agent_id, 0) + 1
                )

                # If we've had enough successes, close the circuit
                if (
                    self._half_open_successes[agent_id]
                    >= self._config.half_open_max_calls
                ):
                    await self._close_circuit(agent_id)

            logger.debug(f"Recorded success for agent {agent_id}")

    async def can_proceed(self, agent_id: str) -> bool:
        """Check if an agent can proceed with actions.

        Also handles automatic transition from OPEN to HALF_OPEN after
        the recovery timeout.

        Args:
            agent_id: The agent ID

        Returns:
            True if the agent can proceed, False if blocked
        """
        async with self._lock:
            current_state = self.get_state(agent_id)

            if current_state == CircuitState.CLOSED:
                return True

            if current_state == CircuitState.OPEN:
                # Check if recovery timeout has passed
                open_time = self._open_time.get(agent_id)
                if open_time:
                    elapsed = (datetime.now(timezone.utc) - open_time).total_seconds()
                    if elapsed >= self._config.recovery_timeout:
                        await self._transition_to_half_open(agent_id)
                        # Count this call against the half-open limit
                        self._half_open_calls[agent_id] = 1
                        return True
                return False

            if current_state == CircuitState.HALF_OPEN:
                # Allow limited calls in half-open state
                calls = self._half_open_calls.get(agent_id, 0)
                if calls < self._config.half_open_max_calls:
                    self._half_open_calls[agent_id] = calls + 1
                    return True
                return False

            return False

    async def _open_circuit(self, agent_id: str, reason: str) -> None:
        """Open the circuit for an agent.

        Stores the original posture and downgrades via PostureStateMachine.

        Args:
            agent_id: The agent ID
            reason: Reason for opening the circuit
        """
        # Store original posture if not already stored
        if agent_id not in self._original_postures:
            self._original_postures[agent_id] = self._posture_machine.get_posture(
                agent_id
            )

        # Transition state
        self._states[agent_id] = CircuitState.OPEN
        self._open_time[agent_id] = datetime.now(timezone.utc)
        self._half_open_calls[agent_id] = 0
        self._half_open_successes[agent_id] = 0

        # Downgrade posture
        current_posture = self._posture_machine.get_posture(agent_id)
        target_posture = TrustPosture(self._config.downgrade_on_open)

        # Only downgrade if current posture is higher
        if current_posture > target_posture:
            request = PostureTransitionRequest(
                agent_id=agent_id,
                from_posture=current_posture,
                to_posture=target_posture,
                reason=f"Circuit breaker opened: {reason}",
                requester_id="circuit_breaker",
            )
            result = self._posture_machine.transition(request)

            if result.success:
                logger.warning(
                    f"Circuit opened for agent {agent_id}: {reason}. "
                    f"Posture downgraded from {current_posture.value} "
                    f"to {target_posture.value}"
                )
            else:
                # If transition fails due to guards, force set the posture
                self._posture_machine.set_posture(agent_id, target_posture)
                logger.warning(
                    f"Circuit opened for agent {agent_id}: {reason}. Posture force-set to {target_posture.value}"
                )
        else:
            logger.warning(
                f"Circuit opened for agent {agent_id}: {reason}. Posture already at or below {target_posture.value}"
            )

    async def _transition_to_half_open(self, agent_id: str) -> None:
        """Transition circuit to half-open state.

        Allows limited test calls to verify recovery.

        Args:
            agent_id: The agent ID
        """
        self._states[agent_id] = CircuitState.HALF_OPEN
        self._half_open_calls[agent_id] = 0
        self._half_open_successes[agent_id] = 0

        logger.info(
            f"Circuit transitioned to half-open for agent {agent_id}. "
            f"Testing recovery with up to {self._config.half_open_max_calls} calls."
        )

    async def _close_circuit(self, agent_id: str) -> None:
        """Close the circuit for an agent.

        Clears failures and logs suggestion to restore posture.

        Args:
            agent_id: The agent ID
        """
        self._states[agent_id] = CircuitState.CLOSED
        self._failures[agent_id] = []
        self._half_open_calls[agent_id] = 0
        self._half_open_successes[agent_id] = 0

        if agent_id in self._open_time:
            del self._open_time[agent_id]

        # Log suggestion to restore posture
        if agent_id in self._original_postures:
            original = self._original_postures[agent_id]
            current = self._posture_machine.get_posture(agent_id)

            if current < original:
                logger.info(
                    f"Circuit closed for agent {agent_id}. "
                    f"Consider restoring posture from {current.value} "
                    f"to {original.value}."
                )
            else:
                logger.info(f"Circuit closed for agent {agent_id}.")

            # Clear stored original posture
            del self._original_postures[agent_id]
        else:
            logger.info(f"Circuit closed for agent {agent_id}.")

    def _clean_old_failures(self, agent_id: str) -> None:
        """Remove failures outside the failure window.

        Args:
            agent_id: The agent ID
        """
        if agent_id not in self._failures:
            return

        cutoff = datetime.now(timezone.utc) - timedelta(
            seconds=self._config.failure_window_seconds
        )

        self._failures[agent_id] = [
            f for f in self._failures[agent_id] if f.timestamp >= cutoff
        ]

    def _calculate_weighted_failures(self, agent_id: str) -> float:
        """Calculate the weighted failure count for an agent.

        Applies severity weights to each failure.

        Args:
            agent_id: The agent ID

        Returns:
            The weighted failure count
        """
        if agent_id not in self._failures:
            return 0.0

        weights = self._config.severity_weights
        total = 0.0

        for failure in self._failures[agent_id]:
            weight = weights.get(failure.severity, 1.0)
            total += weight

        return total

    def get_metrics(self, agent_id: str) -> Dict[str, Any]:
        """Get metrics for an agent's circuit breaker state.

        Args:
            agent_id: The agent ID

        Returns:
            Dictionary containing circuit breaker metrics
        """
        state = self.get_state(agent_id)
        failures = self._failures.get(agent_id, [])
        self._clean_old_failures(agent_id)  # Clean before reporting

        metrics = {
            "agent_id": agent_id,
            "state": state.value,
            "failure_count": len(failures),
            "weighted_failures": self._calculate_weighted_failures(agent_id),
            "failure_threshold": self._config.failure_threshold,
            "recovery_timeout_seconds": self._config.recovery_timeout,
            "failure_window_seconds": self._config.failure_window_seconds,
        }

        if state == CircuitState.OPEN:
            open_time = self._open_time.get(agent_id)
            if open_time:
                elapsed = (datetime.now(timezone.utc) - open_time).total_seconds()
                metrics["time_in_open_state"] = elapsed
                metrics["time_until_half_open"] = max(
                    0, self._config.recovery_timeout - elapsed
                )

        if state == CircuitState.HALF_OPEN:
            metrics["half_open_calls"] = self._half_open_calls.get(agent_id, 0)
            metrics["half_open_successes"] = self._half_open_successes.get(agent_id, 0)
            metrics["half_open_max_calls"] = self._config.half_open_max_calls

        if agent_id in self._original_postures:
            metrics["original_posture"] = self._original_postures[agent_id].value

        metrics["current_posture"] = self._posture_machine.get_posture(agent_id).value

        # Add failure breakdown by severity
        severity_counts: Dict[str, int] = {}
        for failure in failures:
            severity_counts[failure.severity] = (
                severity_counts.get(failure.severity, 0) + 1
            )
        metrics["failures_by_severity"] = severity_counts

        return metrics


class CircuitBreakerRegistry:
    """Registry for per-agent circuit breakers.

    Provides lazy creation, bulk status queries, and lifecycle management
    for PostureCircuitBreaker instances.

    Boundary note:
        Circuit breaker is an orchestration concern retained in the EATP SDK
        for ``pip install`` ergonomics. The canonical placement for circuit
        breaker orchestration is ``kailash-kaizen`` (D2 decision). This module
        provides the primitive; kaizen provides the orchestration.

    Example:
        >>> from kailash.trust.circuit_breaker import CircuitBreakerRegistry
        >>> from kailash.trust.posture.postures import PostureStateMachine
        >>>
        >>> machine = PostureStateMachine()
        >>> registry = CircuitBreakerRegistry(posture_machine=machine)
        >>> breaker = registry.get_or_create("agent-001")
        >>> await breaker.record_failure("agent-001", "Error", "msg", "act")
    """

    def __init__(
        self,
        posture_machine: PostureStateMachine,
        default_config: Optional[CircuitBreakerConfig] = None,
        max_breakers: int = 10_000,
    ):
        """Initialize the circuit breaker registry.

        Args:
            posture_machine: Shared PostureStateMachine for all breakers.
            default_config: Default config for newly created breakers.
                Uses CircuitBreakerConfig() defaults if not provided.
            max_breakers: Maximum number of breakers to track. When exceeded,
                oldest 10% are removed. Default 10,000.
        """
        self._posture_machine = posture_machine
        self._default_config = default_config or CircuitBreakerConfig()
        self._max_breakers = max_breakers
        self._breakers: Dict[str, PostureCircuitBreaker] = {}
        self._lock = asyncio.Lock()

    def get_or_create(
        self,
        agent_id: str,
        config: Optional[CircuitBreakerConfig] = None,
    ) -> PostureCircuitBreaker:
        """Get or lazily create a circuit breaker for an agent.

        Args:
            agent_id: The agent ID.
            config: Optional per-agent config override. If not provided,
                uses the registry's default config.

        Returns:
            The PostureCircuitBreaker for this agent.
        """
        if agent_id not in self._breakers:
            # Enforce bounded collection: trim oldest 10% when capacity exceeded
            if len(self._breakers) >= self._max_breakers:
                trim_count = self._max_breakers // 10
                keys_to_remove = list(self._breakers.keys())[:trim_count]
                for key in keys_to_remove:
                    del self._breakers[key]
                logger.debug(
                    f"Trimmed {trim_count} oldest breakers (capacity {self._max_breakers} exceeded)"
                )

            effective_config = config or self._default_config
            self._breakers[agent_id] = PostureCircuitBreaker(
                posture_machine=self._posture_machine,
                config=effective_config,
            )
            logger.debug(f"Created circuit breaker for agent {agent_id}")
        elif config is not None:
            logger.warning(
                f"Circuit breaker for agent {agent_id} already exists; "
                f"ignoring provided config override. Use reset_agent() first "
                f"to apply a new config."
            )
        return self._breakers[agent_id]

    def has(self, agent_id: str) -> bool:
        """Check if a breaker exists for an agent.

        Args:
            agent_id: The agent ID.

        Returns:
            True if a breaker has been created for this agent.
        """
        return agent_id in self._breakers

    def get_all_open(self) -> Dict[str, PostureCircuitBreaker]:
        """Get all breakers in OPEN state.

        Returns:
            Dict mapping agent IDs to their breakers for agents in OPEN state.
        """
        return {
            agent_id: breaker
            for agent_id, breaker in self._breakers.items()
            if breaker.get_state(agent_id) == CircuitState.OPEN
        }

    def get_all_half_open(self) -> Dict[str, PostureCircuitBreaker]:
        """Get all breakers in HALF_OPEN state.

        Returns:
            Dict mapping agent IDs to their breakers for agents in HALF_OPEN state.
        """
        return {
            agent_id: breaker
            for agent_id, breaker in self._breakers.items()
            if breaker.get_state(agent_id) == CircuitState.HALF_OPEN
        }

    def get_status_summary(self) -> Dict[str, int]:
        """Get a summary of circuit breaker states across all agents.

        Returns:
            Dict with keys: "closed", "open", "half_open", "total".
        """
        counts = {"closed": 0, "open": 0, "half_open": 0, "total": 0}
        for agent_id, breaker in self._breakers.items():
            state = breaker.get_state(agent_id)
            counts[state.value] += 1
            counts["total"] += 1
        return counts

    def remove_agent(self, agent_id: str) -> None:
        """Remove a breaker for an agent.

        No-op if the agent has no breaker.

        Args:
            agent_id: The agent ID to remove.
        """
        if agent_id in self._breakers:
            del self._breakers[agent_id]
            logger.debug(f"Removed circuit breaker for agent {agent_id}")

    def reset_agent(self, agent_id: str) -> None:
        """Reset a breaker for an agent by removing and re-creating.

        Creates a fresh breaker with the default config on next access.

        Args:
            agent_id: The agent ID to reset.
        """
        self.remove_agent(agent_id)
        logger.debug(f"Reset circuit breaker for agent {agent_id}")


__all__ = [
    "CircuitState",
    "FailureEvent",
    "CircuitBreakerConfig",
    "PostureCircuitBreaker",
    "CircuitBreakerRegistry",
]
