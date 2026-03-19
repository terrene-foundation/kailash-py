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
    TrustPosture.DELEGATED: 5,
    TrustPosture.CONTINUOUS_INSIGHT: 4,
    TrustPosture.SHARED_PLANNING: 3,
    TrustPosture.SUPERVISED: 2,
    TrustPosture.PSEUDO_AGENT: 1,
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
        >>> collector.record_posture("agent-001", TrustPosture.DELEGATED)
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

    def __init__(self, max_agents: int = 10_000) -> None:
        """Initialize the metrics collector.

        Args:
            max_agents: Maximum number of entries in per-agent/per-key dicts.
                When exceeded, oldest 10% of entries are trimmed. Default 10,000.
                Applies to _agent_postures, _transitions, _dimension_failures,
                and _anti_gaming_flags.
        """
        self._lock = Lock()
        self._max_agents = max_agents

        # Posture tracking per agent (bounded by _max_agents)
        self._agent_postures: Dict[str, TrustPosture] = {}

        # Transition counts by type (bounded by _max_agents)
        self._transitions: Dict[str, int] = {}

        # Circuit breaker and emergency downgrade counts
        self._circuit_breaker_opens: int = 0
        self._emergency_downgrades: int = 0

        # Constraint evaluation metrics
        self._evaluations_total: int = 0
        self._evaluations_passed: int = 0
        self._evaluations_failed: int = 0
        self._dimension_failures: Dict[str, int] = {}  # bounded by _max_agents
        self._anti_gaming_flags: Dict[str, int] = {}  # bounded by _max_agents

        # Rolling window for evaluation times
        self._evaluation_times: Deque[float] = deque(maxlen=self.MAX_EVALUATION_TIMES)

    def _trim_bounded_dict(self, d: Dict, name: str) -> None:
        """Trim oldest 10% of entries if dict exceeds _max_agents.

        Args:
            d: The dict to potentially trim.
            name: Name of the dict for logging.
        """
        if len(d) > self._max_agents:
            trim_count = self._max_agents // 10
            keys_to_remove = list(d.keys())[:trim_count]
            for key in keys_to_remove:
                del d[key]

    def record_posture(self, agent_id: str, posture: TrustPosture) -> None:
        """Record the current posture for an agent.

        Args:
            agent_id: The agent identifier
            posture: The agent's current posture
        """
        with self._lock:
            self._agent_postures[agent_id] = posture
            self._trim_bounded_dict(self._agent_postures, "_agent_postures")

    def record_transition(self, transition_type: str) -> None:
        """Record a posture transition.

        Args:
            transition_type: Type of transition (e.g., 'upgrade', 'downgrade')
        """
        with self._lock:
            self._transitions[transition_type] = self._transitions.get(transition_type, 0) + 1
            self._trim_bounded_dict(self._transitions, "_transitions")

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
                self._dimension_failures[dimension] = self._dimension_failures.get(dimension, 0) + 1
            self._trim_bounded_dict(self._dimension_failures, "_dimension_failures")

            # Track anti-gaming flags
            for flag in gaming_flags:
                self._anti_gaming_flags[flag] = self._anti_gaming_flags.get(flag, 0) + 1
            self._trim_bounded_dict(self._anti_gaming_flags, "_anti_gaming_flags")

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


# ============================================================================
# Prometheus Text Format Exporter
# ============================================================================


def export_prometheus(collector: TrustMetricsCollector) -> str:
    """Export metrics in Prometheus text exposition format.

    Generates a multi-line string conforming to the Prometheus text format
    specification (https://prometheus.io/docs/instrumenting/exposition_formats/).

    No external dependencies are required -- this is pure string formatting.

    Metrics exported:
        - eatp_trust_score{agent_id="..."} -- posture autonomy level per agent (gauge)
        - eatp_verification_total -- total constraint evaluations (counter)
        - eatp_posture_distribution{posture="..."} -- agent count per posture (gauge)
        - eatp_constraint_utilization -- constraint pass rate 0.0-1.0 (gauge)
        - eatp_circuit_breaker_opens_total -- circuit breaker open events (counter)

    Args:
        collector: A TrustMetricsCollector instance to read metrics from.

    Returns:
        Multi-line string in Prometheus text exposition format.
    """
    lines: list[str] = []

    posture_metrics = collector.get_posture_metrics()
    constraint_metrics = collector.get_constraint_metrics()

    # --- eatp_trust_score (gauge): per-agent posture autonomy level ---
    lines.append("# HELP eatp_trust_score Trust posture autonomy level per agent (1-5)")
    lines.append("# TYPE eatp_trust_score gauge")
    # Access collector internals under lock for per-agent data
    with collector._lock:
        for agent_id, posture in collector._agent_postures.items():
            level = POSTURE_LEVEL_MAP.get(posture, 0)
            lines.append(f'eatp_trust_score{{agent_id="{agent_id}"}} {level}')

    # --- eatp_verification_total (counter): total constraint evaluations ---
    lines.append("# HELP eatp_verification_total Total constraint evaluations performed")
    lines.append("# TYPE eatp_verification_total counter")
    lines.append(f"eatp_verification_total {constraint_metrics.evaluations_total}")

    # --- eatp_posture_distribution (gauge): agent count per posture ---
    lines.append("# HELP eatp_posture_distribution Number of agents at each trust posture level")
    lines.append("# TYPE eatp_posture_distribution gauge")
    for posture_name, count in posture_metrics.posture_distribution.items():
        lines.append(f'eatp_posture_distribution{{posture="{posture_name}"}} {count}')

    # --- eatp_constraint_utilization (gauge): pass rate ---
    lines.append("# HELP eatp_constraint_utilization Constraint evaluation pass rate (0.0-1.0)")
    lines.append("# TYPE eatp_constraint_utilization gauge")
    if constraint_metrics.evaluations_total > 0:
        utilization = constraint_metrics.evaluations_passed / constraint_metrics.evaluations_total
    else:
        utilization = 0.0
    lines.append(f"eatp_constraint_utilization {utilization:.6f}")

    # --- eatp_circuit_breaker_opens_total (counter) ---
    lines.append("# HELP eatp_circuit_breaker_opens_total Total circuit breaker open events")
    lines.append("# TYPE eatp_circuit_breaker_opens_total counter")
    lines.append(f"eatp_circuit_breaker_opens_total {posture_metrics.circuit_breaker_opens}")

    return "\n".join(lines) + "\n"


# ============================================================================
# OpenTelemetry Adapter (Optional Dependency)
# ============================================================================


class OTelMetricsAdapter:
    """OpenTelemetry metrics adapter for EATP trust health metrics.

    Optional: requires ``opentelemetry-api``. Raises ``ImportError`` at
    instantiation time if the package is not installed.

    Uses EATP OTel naming convention with dotted metric names:
        - eatp.trust_score
        - eatp.verification.count
        - eatp.posture

    Example::

        adapter = OTelMetricsAdapter(meter_name="eatp")
        adapter.record_trust_score("agent-001", 5)
        adapter.record_verification("agent-001", "passed")
        adapter.record_posture("agent-001", "delegated")

    Args:
        meter_name: Name of the OTel meter. Defaults to ``"eatp"``.

    Raises:
        ImportError: If ``opentelemetry-api`` is not installed.
    """

    def __init__(self, meter_name: str = "eatp") -> None:
        """Initialize the OpenTelemetry adapter.

        Args:
            meter_name: Name of the OTel meter. Defaults to ``"eatp"``.

        Raises:
            ImportError: If ``opentelemetry-api`` is not installed.
        """
        try:
            from opentelemetry import metrics as otel_metrics
        except ImportError:
            raise ImportError(
                "opentelemetry-api is required for OTelMetricsAdapter. Install with: pip install opentelemetry-api"
            )

        self._meter_name = meter_name
        self._meter = otel_metrics.get_meter(meter_name)

        # Create instruments
        self._trust_score_gauge = self._meter.create_gauge(
            name="eatp.trust_score",
            description="Trust posture autonomy level per agent (1-5)",
            unit="level",
        )
        self._verification_counter = self._meter.create_counter(
            name="eatp.verification.count",
            description="Total verification/constraint evaluations",
            unit="1",
        )
        self._posture_gauge = self._meter.create_gauge(
            name="eatp.posture",
            description="Current trust posture for an agent",
            unit="1",
        )

    def record_trust_score(self, agent_id: str, score: int) -> None:
        """Record a trust score for an agent.

        Args:
            agent_id: The agent identifier.
            score: The trust score value (typically 1-5 for posture levels).
        """
        self._trust_score_gauge.set(score, attributes={"agent_id": agent_id})

    def record_verification(self, agent_id: str, result: str) -> None:
        """Record a verification event.

        Args:
            agent_id: The agent identifier.
            result: The verification result (e.g., "passed", "failed").
        """
        self._verification_counter.add(1, attributes={"agent_id": agent_id, "result": result})

    def record_posture(self, agent_id: str, posture: str) -> None:
        """Record the current posture for an agent.

        Args:
            agent_id: The agent identifier.
            posture: The posture name (e.g., "delegated", "supervised").
        """
        # Map posture name to numeric level for gauge
        posture_levels = {
            "delegated": 5,
            "continuous_insight": 4,
            "shared_planning": 3,
            "supervised": 2,
            "pseudo_agent": 1,
        }
        level = posture_levels.get(posture)
        if level is None:
            raise ValueError(f"Unknown posture '{posture}'. Valid postures: {list(posture_levels.keys())}")
        self._posture_gauge.set(level, attributes={"agent_id": agent_id, "posture": posture})


__all__ = [
    "TrustMetricsCollector",
    "PostureMetrics",
    "ConstraintMetrics",
    "POSTURE_LEVEL_MAP",
    "export_prometheus",
    "OTelMetricsAdapter",
]
