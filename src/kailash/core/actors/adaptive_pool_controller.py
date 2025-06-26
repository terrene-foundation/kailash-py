"""Adaptive pool sizing controller for dynamic connection management.

This module implements intelligent pool size adjustment based on workload
patterns and resource constraints.
"""

import asyncio
import logging
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import psutil

logger = logging.getLogger(__name__)


@dataclass
class PoolMetrics:
    """Metrics for pool sizing decisions."""

    current_size: int
    active_connections: int
    idle_connections: int
    queue_depth: int
    avg_wait_time_ms: float
    avg_query_time_ms: float
    queries_per_second: float
    utilization_rate: float  # 0-1
    health_score: float  # 0-100


@dataclass
class ResourceConstraints:
    """System resource constraints."""

    max_database_connections: int
    available_memory_mb: float
    memory_per_connection_mb: float
    cpu_usage_percent: float
    network_bandwidth_mbps: float


@dataclass
class ScalingDecision:
    """Result of scaling decision."""

    action: str  # "scale_up", "scale_down", "no_change"
    current_size: int
    target_size: int
    reason: str
    confidence: float  # 0-1


class PoolSizeCalculator:
    """Calculates optimal pool size using queueing theory and heuristics."""

    def __init__(
        self, target_utilization: float = 0.75, max_wait_time_ms: float = 100.0
    ):
        self.target_utilization = target_utilization
        self.max_wait_time_ms = max_wait_time_ms

    def calculate_optimal_size(
        self,
        metrics: PoolMetrics,
        constraints: ResourceConstraints,
        workload_forecast: Optional[Dict[str, Any]] = None,
    ) -> int:
        """Calculate optimal pool size based on multiple factors."""

        # Method 1: Little's Law
        littles_law_size = self._calculate_by_littles_law(metrics)

        # Method 2: Utilization-based
        utilization_size = self._calculate_by_utilization(metrics)

        # Method 3: Queue depth based
        queue_size = self._calculate_by_queue_depth(metrics)

        # Method 4: Response time based
        response_time_size = self._calculate_by_response_time(metrics)

        # Method 5: Forecast-based (if available)
        forecast_size = metrics.current_size
        if workload_forecast:
            forecast_size = self._calculate_by_forecast(workload_forecast)

        # Combine methods with weights
        weighted_size = (
            littles_law_size * 0.25
            + utilization_size * 0.25
            + queue_size * 0.2
            + response_time_size * 0.2
            + forecast_size * 0.1
        )

        # Apply constraints
        optimal_size = self._apply_constraints(
            int(weighted_size), metrics.current_size, constraints
        )

        logger.debug(
            f"Pool size calculation: Little's={littles_law_size}, "
            f"Utilization={utilization_size}, Queue={queue_size}, "
            f"Response={response_time_size}, Forecast={forecast_size}, "
            f"Final={optimal_size}"
        )

        return optimal_size

    def _calculate_by_littles_law(self, metrics: PoolMetrics) -> int:
        """Use Little's Law: L = λW (connections = arrival_rate * service_time)."""
        if metrics.queries_per_second == 0 or metrics.avg_query_time_ms == 0:
            return metrics.current_size

        arrival_rate = metrics.queries_per_second
        service_time_seconds = metrics.avg_query_time_ms / 1000

        # Add buffer for variability
        required_connections = arrival_rate * service_time_seconds * 1.2

        return max(2, int(required_connections))

    def _calculate_by_utilization(self, metrics: PoolMetrics) -> int:
        """Calculate based on target utilization."""
        if metrics.utilization_rate == 0:
            return metrics.current_size

        # If utilization is too high, scale up
        if metrics.utilization_rate > self.target_utilization + 0.1:
            scale_factor = metrics.utilization_rate / self.target_utilization
            return int(metrics.current_size * scale_factor)

        # If utilization is too low, scale down
        elif metrics.utilization_rate < self.target_utilization - 0.2:
            scale_factor = metrics.utilization_rate / self.target_utilization
            return max(2, int(metrics.current_size * scale_factor))

        return metrics.current_size

    def _calculate_by_queue_depth(self, metrics: PoolMetrics) -> int:
        """Calculate based on queue depth."""
        if metrics.queue_depth == 0:
            return metrics.current_size

        # If queue is building up, we need more connections
        if metrics.queue_depth > metrics.current_size * 0.5:
            # Add connections proportional to queue depth
            additional_needed = int(metrics.queue_depth / 2)
            return metrics.current_size + additional_needed

        # If no queue and low utilization, we might have too many
        elif metrics.queue_depth == 0 and metrics.utilization_rate < 0.5:
            return max(2, int(metrics.current_size * 0.8))

        return metrics.current_size

    def _calculate_by_response_time(self, metrics: PoolMetrics) -> int:
        """Calculate based on response time targets."""
        if metrics.avg_wait_time_ms <= self.max_wait_time_ms:
            # Meeting targets, check if we can reduce
            if metrics.avg_wait_time_ms < self.max_wait_time_ms * 0.5:
                return max(2, int(metrics.current_size * 0.9))
            return metrics.current_size
        else:
            # Not meeting targets, scale up
            scale_factor = metrics.avg_wait_time_ms / self.max_wait_time_ms
            return int(metrics.current_size * scale_factor)

    def _calculate_by_forecast(self, forecast: Dict[str, Any]) -> int:
        """Calculate based on workload forecast."""
        return forecast.get("recommended_pool_size", 10)

    def _apply_constraints(
        self, calculated_size: int, current_size: int, constraints: ResourceConstraints
    ) -> int:
        """Apply resource constraints to calculated size."""
        # Database connection limit (use 80% to leave room for other apps)
        max_by_db = int(constraints.max_database_connections * 0.8)

        # Memory limit
        max_by_memory = int(
            constraints.available_memory_mb / constraints.memory_per_connection_mb
        )

        # CPU constraint (don't scale up if CPU is high)
        if constraints.cpu_usage_percent > 80 and calculated_size > current_size:
            calculated_size = current_size

        # Apply all constraints
        final_size = min(calculated_size, max_by_db, max_by_memory)

        # Ensure minimum size
        return max(2, final_size)


class ScalingDecisionEngine:
    """Makes scaling decisions with hysteresis and dampening."""

    def __init__(
        self,
        scale_up_threshold: float = 0.15,
        scale_down_threshold: float = 0.20,
        max_adjustment_step: int = 2,
        cooldown_seconds: int = 60,
    ):
        self.scale_up_threshold = scale_up_threshold
        self.scale_down_threshold = scale_down_threshold
        self.max_adjustment_step = max_adjustment_step
        self.cooldown_seconds = cooldown_seconds

        # History tracking
        self.decision_history: deque = deque(maxlen=100)
        self.last_scaling_time = datetime.min
        self.size_history: deque = deque(maxlen=20)

    def should_scale(
        self,
        current_size: int,
        optimal_size: int,
        metrics: PoolMetrics,
        emergency: bool = False,
    ) -> ScalingDecision:
        """Decide whether to scale with hysteresis."""

        # Check cooldown period
        if not emergency and not self._cooldown_expired():
            return ScalingDecision(
                action="no_change",
                current_size=current_size,
                target_size=current_size,
                reason="In cooldown period",
                confidence=1.0,
            )

        # Calculate size difference
        size_diff = optimal_size - current_size
        size_diff_ratio = abs(size_diff) / current_size if current_size > 0 else 1.0

        # Check for flapping
        if self._is_flapping():
            return ScalingDecision(
                action="no_change",
                current_size=current_size,
                target_size=current_size,
                reason="Flapping detected - stabilizing",
                confidence=0.9,
            )

        # Emergency scaling (bypass normal thresholds)
        if emergency:
            if metrics.queue_depth > current_size:
                target = min(current_size + self.max_adjustment_step * 2, optimal_size)
                return self._create_scaling_decision(
                    "scale_up",
                    current_size,
                    target,
                    "Emergency: High queue depth",
                    0.95,
                )

        # Normal scaling logic
        if size_diff > 0 and size_diff_ratio > self.scale_up_threshold:
            # Scale up
            target = self._calculate_gradual_target(current_size, optimal_size, "up")
            reason = self._get_scale_up_reason(metrics)
            confidence = self._calculate_confidence(metrics, size_diff_ratio)

            return self._create_scaling_decision(
                "scale_up", current_size, target, reason, confidence
            )

        elif size_diff < 0 and size_diff_ratio > self.scale_down_threshold:
            # Scale down
            target = self._calculate_gradual_target(current_size, optimal_size, "down")
            reason = self._get_scale_down_reason(metrics)
            confidence = self._calculate_confidence(metrics, size_diff_ratio)

            return self._create_scaling_decision(
                "scale_down", current_size, target, reason, confidence
            )

        else:
            # No change needed
            return ScalingDecision(
                action="no_change",
                current_size=current_size,
                target_size=current_size,
                reason="Within acceptable thresholds",
                confidence=0.8,
            )

    def _cooldown_expired(self) -> bool:
        """Check if cooldown period has expired."""
        return (
            datetime.now() - self.last_scaling_time
        ).total_seconds() > self.cooldown_seconds

    def _is_flapping(self) -> bool:
        """Detect if pool size is flapping."""
        if len(self.decision_history) < 4:
            return False

        # Check if we've been alternating between scale up/down
        recent_actions = [d.action for d in list(self.decision_history)[-4:]]
        alternating = all(
            recent_actions[i] != recent_actions[i + 1]
            for i in range(len(recent_actions) - 1)
            if recent_actions[i] != "no_change"
        )

        return alternating

    def _calculate_gradual_target(
        self, current: int, optimal: int, direction: str
    ) -> int:
        """Calculate gradual scaling target."""
        if direction == "up":
            # Don't scale up more than max_adjustment_step at once
            max_target = current + self.max_adjustment_step
            return min(optimal, max_target)
        else:
            # Don't scale down more than max_adjustment_step at once
            min_target = current - self.max_adjustment_step
            return max(optimal, min_target, 2)  # Never go below 2

    def _get_scale_up_reason(self, metrics: PoolMetrics) -> str:
        """Generate reason for scaling up."""
        reasons = []

        if metrics.utilization_rate > 0.85:
            reasons.append(f"High utilization ({metrics.utilization_rate:.1%})")
        if metrics.queue_depth > 0:
            reasons.append(f"Queue depth: {metrics.queue_depth}")
        if metrics.avg_wait_time_ms > 50:
            reasons.append(f"Wait time: {metrics.avg_wait_time_ms:.0f}ms")

        return " | ".join(reasons) if reasons else "Optimal size increased"

    def _get_scale_down_reason(self, metrics: PoolMetrics) -> str:
        """Generate reason for scaling down."""
        reasons = []

        if metrics.utilization_rate < 0.5:
            reasons.append(f"Low utilization ({metrics.utilization_rate:.1%})")
        if metrics.idle_connections > metrics.active_connections:
            reasons.append(f"Idle connections: {metrics.idle_connections}")

        return " | ".join(reasons) if reasons else "Optimal size decreased"

    def _calculate_confidence(
        self, metrics: PoolMetrics, size_diff_ratio: float
    ) -> float:
        """Calculate confidence in scaling decision."""
        confidence = 0.5

        # Higher confidence for extreme situations
        if metrics.utilization_rate > 0.9 or metrics.utilization_rate < 0.3:
            confidence += 0.2

        if metrics.queue_depth > 5:
            confidence += 0.15

        if size_diff_ratio > 0.3:
            confidence += 0.15

        # Lower confidence if health score is low
        if metrics.health_score < 70:
            confidence *= 0.8

        return min(confidence, 0.95)

    def _create_scaling_decision(
        self,
        action: str,
        current_size: int,
        target_size: int,
        reason: str,
        confidence: float,
    ) -> ScalingDecision:
        """Create and record scaling decision."""
        decision = ScalingDecision(
            action=action,
            current_size=current_size,
            target_size=target_size,
            reason=reason,
            confidence=confidence,
        )

        # Record decision
        self.decision_history.append(decision)
        self.size_history.append(target_size)

        if action != "no_change":
            self.last_scaling_time = datetime.now()

        return decision


class ResourceMonitor:
    """Monitors system resources for constraint enforcement."""

    def __init__(self):
        self.process = psutil.Process()
        self.last_check_time = datetime.min
        self.check_interval = timedelta(seconds=10)
        self.cached_constraints: Optional[ResourceConstraints] = None

    async def get_resource_constraints(
        self, db_connection_info: Dict[str, Any]
    ) -> ResourceConstraints:
        """Get current resource constraints."""
        # Use cache if recent
        if (
            self.cached_constraints
            and datetime.now() - self.last_check_time < self.check_interval
        ):
            return self.cached_constraints

        # Get system memory
        memory = psutil.virtual_memory()
        available_memory_mb = memory.available / (1024 * 1024)

        # Get CPU usage
        cpu_percent = psutil.cpu_percent(interval=0.1)

        # Estimate network bandwidth (simplified)
        network_bandwidth_mbps = 100.0  # Default 100 Mbps

        # Get database connection limit
        max_db_connections = await self._get_database_limit(db_connection_info)

        # Estimate memory per connection
        memory_per_connection = self._estimate_connection_memory()

        constraints = ResourceConstraints(
            max_database_connections=max_db_connections,
            available_memory_mb=available_memory_mb,
            memory_per_connection_mb=memory_per_connection,
            cpu_usage_percent=cpu_percent,
            network_bandwidth_mbps=network_bandwidth_mbps,
        )

        self.cached_constraints = constraints
        self.last_check_time = datetime.now()

        return constraints

    async def _get_database_limit(self, db_info: Dict[str, Any]) -> int:
        """Get database connection limit."""
        # This would query the database for max_connections
        # For now, use reasonable defaults
        db_type = db_info.get("type", "postgresql")

        defaults = {"postgresql": 100, "mysql": 150, "sqlite": 10}

        return defaults.get(db_type, 50)

    def _estimate_connection_memory(self) -> float:
        """Estimate memory usage per connection in MB."""
        # This is a rough estimate
        # Real implementation would measure actual usage
        return 10.0  # 10 MB per connection


class AdaptivePoolController:
    """Main controller for adaptive pool sizing."""

    def __init__(
        self,
        min_size: int = 2,
        max_size: int = 50,
        target_utilization: float = 0.75,
        adjustment_interval_seconds: int = 30,
    ):
        self.min_size = min_size
        self.max_size = max_size
        self.target_utilization = target_utilization
        self.adjustment_interval_seconds = adjustment_interval_seconds

        # Components
        self.calculator = PoolSizeCalculator(target_utilization=target_utilization)
        self.decision_engine = ScalingDecisionEngine()
        self.resource_monitor = ResourceMonitor()

        # State
        self.running = False
        self.adjustment_task: Optional[asyncio.Task] = None
        self.metrics_history: deque = deque(maxlen=60)  # 30 minutes of history

    async def start(self, pool_ref: Any, pattern_tracker: Optional[Any] = None):
        """Start the adaptive controller."""
        self.pool_ref = pool_ref
        self.pattern_tracker = pattern_tracker
        self.running = True

        # Start adjustment loop
        self.adjustment_task = asyncio.create_task(self._adjustment_loop())

        logger.info("Adaptive pool controller started")

    async def stop(self):
        """Stop the adaptive controller."""
        self.running = False

        if self.adjustment_task:
            self.adjustment_task.cancel()
            try:
                await self.adjustment_task
            except asyncio.CancelledError:
                pass

        logger.info("Adaptive pool controller stopped")

    async def _adjustment_loop(self):
        """Main loop for pool size adjustments."""
        while self.running:
            try:
                # Collect metrics
                metrics = await self._collect_metrics()
                self.metrics_history.append((datetime.now(), metrics))

                # Get resource constraints
                constraints = await self.resource_monitor.get_resource_constraints(
                    self.pool_ref.db_config
                )

                # Get workload forecast if available
                forecast = None
                if self.pattern_tracker:
                    forecast = self.pattern_tracker.get_workload_forecast(
                        horizon_minutes=self.adjustment_interval_seconds // 60 + 5
                    )

                # Calculate optimal size
                optimal_size = self.calculator.calculate_optimal_size(
                    metrics, constraints, forecast
                )

                # Make scaling decision
                decision = self.decision_engine.should_scale(
                    metrics.current_size,
                    optimal_size,
                    metrics,
                    emergency=self._is_emergency(metrics),
                )

                # Execute scaling if needed
                if decision.action != "no_change":
                    await self._execute_scaling(decision)

                # Log metrics
                if decision.action != "no_change" or metrics.current_size % 10 == 0:
                    logger.info(
                        f"Pool metrics: size={metrics.current_size}, "
                        f"utilization={metrics.utilization_rate:.1%}, "
                        f"queue={metrics.queue_depth}, "
                        f"action={decision.action}, "
                        f"target={decision.target_size}"
                    )

            except Exception as e:
                logger.error(f"Error in adaptive pool adjustment: {e}")

            # Wait for next adjustment
            await asyncio.sleep(self.adjustment_interval_seconds)

    async def _collect_metrics(self) -> PoolMetrics:
        """Collect current pool metrics."""
        pool_stats = await self.pool_ref.get_pool_statistics()

        return PoolMetrics(
            current_size=pool_stats["total_connections"],
            active_connections=pool_stats["active_connections"],
            idle_connections=pool_stats["idle_connections"],
            queue_depth=pool_stats.get("queue_depth", 0),
            avg_wait_time_ms=pool_stats.get("avg_acquisition_time_ms", 0),
            avg_query_time_ms=pool_stats.get("avg_query_time_ms", 0),
            queries_per_second=pool_stats.get("queries_per_second", 0),
            utilization_rate=pool_stats.get("utilization_rate", 0),
            health_score=pool_stats.get("avg_health_score", 100),
        )

    def _is_emergency(self, metrics: PoolMetrics) -> bool:
        """Check if emergency scaling is needed."""
        return (
            metrics.queue_depth > metrics.current_size * 2
            or metrics.avg_wait_time_ms > 1000
            or metrics.utilization_rate > 0.95
        )

    async def _execute_scaling(self, decision: ScalingDecision):
        """Execute the scaling decision."""
        logger.info(
            f"Executing pool scaling: {decision.action} from "
            f"{decision.current_size} to {decision.target_size} - {decision.reason}"
        )

        try:
            # Apply bounds
            target_size = max(self.min_size, min(self.max_size, decision.target_size))

            # Call pool's adjustment method
            success = await self.pool_ref.adjust_pool_size(target_size)

            if success:
                logger.info(f"Pool size adjusted to {target_size}")
            else:
                logger.warning(f"Failed to adjust pool size to {target_size}")

        except Exception as e:
            logger.error(f"Error executing pool scaling: {e}")

    def get_adjustment_history(self) -> List[Dict[str, Any]]:
        """Get recent adjustment history."""
        return [
            {
                "timestamp": self.decision_engine.last_scaling_time.isoformat(),
                "action": decision.action,
                "from_size": decision.current_size,
                "to_size": decision.target_size,
                "reason": decision.reason,
                "confidence": decision.confidence,
            }
            for decision in self.decision_engine.decision_history
            if decision.action != "no_change"
        ]
