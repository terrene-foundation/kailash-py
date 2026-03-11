# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Trust metrics collection for posture and constraint monitoring.

Provides metrics collection for trust postures, transitions,
circuit breaker events, and constraint evaluations.

Part of CARE-030 implementation.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from threading import Lock
from typing import Any, Deque, Dict, List, Optional

from eatp.postures import TrustPosture

# Autonomy level mapping for average calculation
POSTURE_LEVEL_MAP: Dict[TrustPosture, int] = {
    TrustPosture.FULL_AUTONOMY: 5,
    TrustPosture.ASSISTED: 4,
    TrustPosture.SUPERVISED: 3,
    TrustPosture.HUMAN_DECIDES: 2,
    TrustPosture.BLOCKED: 1,
}


@dataclass
class PostureMetrics:
    """Metrics for posture distribution and transitions.

    Attributes:
        posture_distribution: Count of agents at each posture level
        transitions_by_type: Count of transitions by type
        circuit_breaker_opens: Number of circuit breaker open events
        emergency_downgrades: Number of emergency downgrade events
        average_posture_level: Average posture level across all agents
        timestamp: When these metrics were collected
    """

    posture_distribution: Dict[str, int] = field(default_factory=dict)
    transitions_by_type: Dict[str, int] = field(default_factory=dict)
    circuit_breaker_opens: int = 0
    emergency_downgrades: int = 0
    average_posture_level: float = 0.0
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "posture_distribution": self.posture_distribution,
            "transitions_by_type": self.transitions_by_type,
            "circuit_breaker_opens": self.circuit_breaker_opens,
            "emergency_downgrades": self.emergency_downgrades,
            "average_posture_level": self.average_posture_level,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class ConstraintMetrics:
    """Metrics for constraint evaluation.

    Attributes:
        evaluations_total: Total number of constraint evaluations
        evaluations_passed: Number of evaluations that passed
        evaluations_failed: Number of evaluations that failed
        dimension_failures: Count of failures by dimension (e.g., 'rate_limit')
        anti_gaming_flags: Count of anti-gaming flags by type
        average_evaluation_time_ms: Average time to evaluate constraints
    """

    evaluations_total: int = 0
    evaluations_passed: int = 0
    evaluations_failed: int = 0
    dimension_failures: Dict[str, int] = field(default_factory=dict)
    anti_gaming_flags: Dict[str, int] = field(default_factory=dict)
    average_evaluation_time_ms: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "evaluations_total": self.evaluations_total,
            "evaluations_passed": self.evaluations_passed,
            "evaluations_failed": self.evaluations_failed,
            "dimension_failures": self.dimension_failures,
            "anti_gaming_flags": self.anti_gaming_flags,
            "average_evaluation_time_ms": self.average_evaluation_time_ms,
        }


class TrustMetricsCollector:
    """Collector for trust-related metrics.

    Thread-safe metrics collection for postures, transitions,
    circuit breaker events, and constraint evaluations.

    Example:
        >>> collector = TrustMetricsCollector()
        >>> collector.record_posture("agent-001", TrustPosture.FULL_AUTONOMY)
        >>> collector.record_transition("upgrade")
        >>> collector.record_constraint_evaluation(
        ...     passed=True,
        ...     failed_dimensions=[],
        ...     gaming_flags=[],
        ...     duration_ms=5.2,
        ... )
        >>> metrics = collector.get_posture_metrics()
        >>> print(metrics.average_posture_level)
    """

    # Maximum number of evaluation times to keep for rolling average
    MAX_EVALUATION_TIMES = 1000

    def __init__(self) -> None:
        """Initialize the metrics collector."""
        self._lock = Lock()

        # Posture tracking per agent
        self._agent_postures: Dict[str, TrustPosture] = {}

        # Transition counts by type
        self._transitions: Dict[str, int] = {}

        # Circuit breaker and emergency downgrade counts
        self._circuit_breaker_opens: int = 0
        self._emergency_downgrades: int = 0

        # Constraint evaluation metrics
        self._evaluations_total: int = 0
        self._evaluations_passed: int = 0
        self._evaluations_failed: int = 0
        self._dimension_failures: Dict[str, int] = {}
        self._anti_gaming_flags: Dict[str, int] = {}

        # Rolling window for evaluation times
        self._evaluation_times: Deque[float] = deque(maxlen=self.MAX_EVALUATION_TIMES)

    def record_posture(self, agent_id: str, posture: TrustPosture) -> None:
        """Record the current posture for an agent.

        Args:
            agent_id: The agent identifier
            posture: The agent's current posture
        """
        with self._lock:
            self._agent_postures[agent_id] = posture

    def record_transition(self, transition_type: str) -> None:
        """Record a posture transition.

        Args:
            transition_type: Type of transition (e.g., 'upgrade', 'downgrade')
        """
        with self._lock:
            self._transitions[transition_type] = (
                self._transitions.get(transition_type, 0) + 1
            )

    def record_circuit_breaker_open(self) -> None:
        """Record a circuit breaker open event."""
        with self._lock:
            self._circuit_breaker_opens += 1

    def record_emergency_downgrade(self) -> None:
        """Record an emergency downgrade event."""
        with self._lock:
            self._emergency_downgrades += 1

    def record_constraint_evaluation(
        self,
        passed: bool,
        failed_dimensions: Optional[List[str]] = None,
        gaming_flags: Optional[List[str]] = None,
        duration_ms: float = 0.0,
    ) -> None:
        """Record a constraint evaluation result.

        Args:
            passed: Whether the evaluation passed
            failed_dimensions: List of dimensions that failed (if any)
            gaming_flags: List of anti-gaming flags triggered (if any)
            duration_ms: Time taken to evaluate in milliseconds
        """
        failed_dimensions = failed_dimensions or []
        gaming_flags = gaming_flags or []

        with self._lock:
            self._evaluations_total += 1

            if passed:
                self._evaluations_passed += 1
            else:
                self._evaluations_failed += 1

            # Track dimension failures
            for dimension in failed_dimensions:
                self._dimension_failures[dimension] = (
                    self._dimension_failures.get(dimension, 0) + 1
                )

            # Track anti-gaming flags
            for flag in gaming_flags:
                self._anti_gaming_flags[flag] = self._anti_gaming_flags.get(flag, 0) + 1

            # Add to rolling window
            self._evaluation_times.append(duration_ms)

    def get_posture_metrics(self) -> PostureMetrics:
        """Get current posture metrics.

        Returns:
            PostureMetrics with current distribution and statistics
        """
        with self._lock:
            # Calculate posture distribution
            distribution: Dict[str, int] = {}
            for posture in TrustPosture:
                distribution[posture.value] = 0

            for posture in self._agent_postures.values():
                distribution[posture.value] = distribution.get(posture.value, 0) + 1

            # Calculate average posture level
            average_level = self._calculate_average_posture_level()

            return PostureMetrics(
                posture_distribution=distribution,
                transitions_by_type=dict(self._transitions),
                circuit_breaker_opens=self._circuit_breaker_opens,
                emergency_downgrades=self._emergency_downgrades,
                average_posture_level=average_level,
                timestamp=datetime.now(timezone.utc),
            )

    def get_constraint_metrics(self) -> ConstraintMetrics:
        """Get current constraint evaluation metrics.

        Returns:
            ConstraintMetrics with evaluation statistics
        """
        with self._lock:
            # Calculate average evaluation time
            if self._evaluation_times:
                avg_time = sum(self._evaluation_times) / len(self._evaluation_times)
            else:
                avg_time = 0.0

            return ConstraintMetrics(
                evaluations_total=self._evaluations_total,
                evaluations_passed=self._evaluations_passed,
                evaluations_failed=self._evaluations_failed,
                dimension_failures=dict(self._dimension_failures),
                anti_gaming_flags=dict(self._anti_gaming_flags),
                average_evaluation_time_ms=avg_time,
            )

    def _calculate_average_posture_level(self) -> float:
        """Calculate the average posture level across all agents.

        Formula: sum(count * level_map[posture]) / total_agents

        Returns:
            Average posture level (0.0 if no agents)
        """
        if not self._agent_postures:
            return 0.0

        total_level = 0
        for posture in self._agent_postures.values():
            total_level += POSTURE_LEVEL_MAP.get(posture, 0)

        return total_level / len(self._agent_postures)

    def reset(self) -> None:
        """Reset all metrics to initial state."""
        with self._lock:
            self._agent_postures.clear()
            self._transitions.clear()
            self._circuit_breaker_opens = 0
            self._emergency_downgrades = 0
            self._evaluations_total = 0
            self._evaluations_passed = 0
            self._evaluations_failed = 0
            self._dimension_failures.clear()
            self._anti_gaming_flags.clear()
            self._evaluation_times.clear()


__all__ = [
    "TrustMetricsCollector",
    "PostureMetrics",
    "ConstraintMetrics",
    "POSTURE_LEVEL_MAP",
]
