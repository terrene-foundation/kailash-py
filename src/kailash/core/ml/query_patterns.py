"""Query pattern learning and prediction for intelligent routing optimization.

This module implements pattern tracking and prediction to optimize query routing
and connection pre-warming based on historical execution patterns.
"""

import asyncio
import logging
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Set, Tuple

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class QueryExecution:
    """Record of a single query execution."""

    fingerprint: str
    timestamp: datetime
    execution_time_ms: float
    connection_id: str
    parameters: Dict[str, Any]
    success: bool
    result_size: int


@dataclass
class QueryPattern:
    """Identified pattern in query execution."""

    fingerprint: str
    frequency: float  # Queries per minute
    avg_execution_time: float
    temporal_pattern: Optional[str]  # e.g., "hourly", "daily", "weekly"
    common_parameters: Dict[str, List[Any]]
    typical_result_size: int
    follows_queries: List[str]  # Queries that often precede this one
    followed_by_queries: List[str]  # Queries that often follow this one


@dataclass
class PredictedQuery:
    """Prediction of a future query."""

    fingerprint: str
    probability: float
    expected_time: datetime
    confidence: float
    reason: str  # Why this was predicted


class QueryPatternTracker:
    """Tracks and analyzes query execution patterns."""

    def __init__(
        self, retention_hours: int = 168, min_pattern_frequency: int = 5  # 7 days
    ):
        self.retention_hours = retention_hours
        self.min_pattern_frequency = min_pattern_frequency

        # Storage
        self.executions: deque = deque()  # All executions in time order
        self.execution_by_fingerprint: Dict[str, List[QueryExecution]] = defaultdict(
            list
        )
        self.sequence_patterns: Dict[str, Dict[str, int]] = defaultdict(
            lambda: defaultdict(int)
        )

        # Analysis cache
        self.pattern_cache: Dict[str, QueryPattern] = {}
        self.last_analysis_time = datetime.now()
        self.analysis_interval = timedelta(minutes=5)

    def record_execution(
        self,
        fingerprint: str,
        execution_time_ms: float,
        connection_id: str,
        parameters: Optional[Dict[str, Any]] = None,
        success: bool = True,
        result_size: int = 0,
    ):
        """Record a query execution for pattern analysis."""
        execution = QueryExecution(
            fingerprint=fingerprint,
            timestamp=datetime.now(),
            execution_time_ms=execution_time_ms,
            connection_id=connection_id,
            parameters=parameters or {},
            success=success,
            result_size=result_size,
        )

        # Add to storage
        self.executions.append(execution)
        self.execution_by_fingerprint[fingerprint].append(execution)

        # Update sequence patterns
        if len(self.executions) > 1:
            prev_execution = self.executions[-2]
            self.sequence_patterns[prev_execution.fingerprint][fingerprint] += 1

        # Clean old data
        self._clean_old_data()

        # Trigger analysis if needed
        if datetime.now() - self.last_analysis_time > self.analysis_interval:
            self._analyze_patterns()

    def get_pattern(self, fingerprint: str) -> Optional[QueryPattern]:
        """Get analyzed pattern for a query fingerprint."""
        if fingerprint in self.pattern_cache:
            return self.pattern_cache[fingerprint]

        # Try to analyze just this fingerprint
        pattern = self._analyze_single_pattern(fingerprint)
        if pattern:
            self.pattern_cache[fingerprint] = pattern

        return pattern

    def predict_next_queries(
        self, current_fingerprint: str, time_window_minutes: int = 5
    ) -> List[PredictedQuery]:
        """Predict queries likely to follow the current one."""
        predictions = []

        # Get sequence patterns
        if current_fingerprint in self.sequence_patterns:
            followers = self.sequence_patterns[current_fingerprint]
            total_occurrences = sum(followers.values())

            for next_fingerprint, count in followers.items():
                if count >= 2:  # Minimum threshold
                    probability = count / total_occurrences

                    # Get timing information
                    avg_delay = self._calculate_average_delay(
                        current_fingerprint, next_fingerprint
                    )

                    predictions.append(
                        PredictedQuery(
                            fingerprint=next_fingerprint,
                            probability=probability,
                            expected_time=datetime.now() + avg_delay,
                            confidence=min(0.9, probability * 2),  # Scale confidence
                            reason=f"Follows {current_fingerprint} in {count}/{total_occurrences} cases",
                        )
                    )

        # Add temporal predictions
        temporal_predictions = self._predict_temporal_queries(time_window_minutes)
        predictions.extend(temporal_predictions)

        # Sort by probability
        predictions.sort(key=lambda p: p.probability, reverse=True)

        return predictions[:10]  # Top 10 predictions

    def get_workload_forecast(self, horizon_minutes: int = 60) -> Dict[str, Any]:
        """Forecast workload for the specified time horizon."""
        now = datetime.now()
        forecast_end = now + timedelta(minutes=horizon_minutes)

        # Analyze historical patterns for this time period
        historical_load = self._analyze_historical_load(
            now.time(), forecast_end.time(), now.weekday()
        )

        # Calculate expected queries
        expected_queries = []
        for pattern in self.pattern_cache.values():
            if pattern.temporal_pattern:
                expected_count = self._estimate_query_count(pattern, horizon_minutes)
                if expected_count > 0:
                    expected_queries.append(
                        {
                            "fingerprint": pattern.fingerprint,
                            "expected_count": expected_count,
                            "avg_execution_time": pattern.avg_execution_time,
                        }
                    )

        return {
            "horizon_minutes": horizon_minutes,
            "historical_qps": historical_load.get("avg_qps", 0),
            "expected_total_queries": sum(
                q["expected_count"] for q in expected_queries
            ),
            "expected_queries": expected_queries,
            "peak_load_probability": historical_load.get("peak_probability", 0),
            "recommended_pool_size": self._calculate_recommended_pool_size(
                expected_queries, historical_load
            ),
        }

    def _clean_old_data(self):
        """Remove data older than retention period."""
        cutoff_time = datetime.now() - timedelta(hours=self.retention_hours)

        # Clean executions deque
        while self.executions and self.executions[0].timestamp < cutoff_time:
            old_execution = self.executions.popleft()

            # Remove from fingerprint index
            fingerprint_list = self.execution_by_fingerprint[old_execution.fingerprint]
            fingerprint_list.remove(old_execution)
            if not fingerprint_list:
                del self.execution_by_fingerprint[old_execution.fingerprint]

    def _analyze_patterns(self):
        """Analyze all patterns in the data."""
        self.pattern_cache.clear()

        for fingerprint, executions in self.execution_by_fingerprint.items():
            if len(executions) >= self.min_pattern_frequency:
                pattern = self._analyze_single_pattern(fingerprint)
                if pattern:
                    self.pattern_cache[fingerprint] = pattern

        self.last_analysis_time = datetime.now()

    def _analyze_single_pattern(self, fingerprint: str) -> Optional[QueryPattern]:
        """Analyze pattern for a single query fingerprint."""
        executions = self.execution_by_fingerprint.get(fingerprint, [])

        if len(executions) < self.min_pattern_frequency:
            return None

        # Calculate basic statistics
        execution_times = [e.execution_time_ms for e in executions if e.success]
        if not execution_times:
            return None

        avg_execution_time = np.mean(execution_times)

        # Calculate frequency (queries per minute)
        time_span = (
            executions[-1].timestamp - executions[0].timestamp
        ).total_seconds() / 60
        frequency = len(executions) / time_span if time_span > 0 else 0

        # Analyze temporal patterns
        temporal_pattern = self._detect_temporal_pattern(executions)

        # Analyze parameters
        common_parameters = self._analyze_parameters(executions)

        # Calculate typical result size
        result_sizes = [e.result_size for e in executions if e.result_size > 0]
        typical_result_size = int(np.median(result_sizes)) if result_sizes else 0

        # Find sequence patterns
        follows_queries = []
        followed_by_queries = []

        for other_fingerprint, followers in self.sequence_patterns.items():
            if fingerprint in followers and followers[fingerprint] >= 2:
                follows_queries.append(other_fingerprint)

        if fingerprint in self.sequence_patterns:
            for follower, count in self.sequence_patterns[fingerprint].items():
                if count >= 2:
                    followed_by_queries.append(follower)

        return QueryPattern(
            fingerprint=fingerprint,
            frequency=frequency,
            avg_execution_time=avg_execution_time,
            temporal_pattern=temporal_pattern,
            common_parameters=common_parameters,
            typical_result_size=typical_result_size,
            follows_queries=follows_queries,
            followed_by_queries=followed_by_queries,
        )

    def _detect_temporal_pattern(
        self, executions: List[QueryExecution]
    ) -> Optional[str]:
        """Detect temporal patterns in query execution."""
        if len(executions) < 10:
            return None

        # Extract hour of day for each execution
        hours = [e.timestamp.hour for e in executions]
        hour_counts = defaultdict(int)
        for hour in hours:
            hour_counts[hour] += 1

        # Check for hourly pattern (concentrated in specific hours)
        max_hour_count = max(hour_counts.values())
        if max_hour_count > len(executions) * 0.3:  # 30% in one hour
            peak_hours = [
                h for h, c in hour_counts.items() if c > len(executions) * 0.2
            ]
            if len(peak_hours) <= 3:
                return "hourly"

        # Check for daily pattern (regular daily execution)
        dates = [e.timestamp.date() for e in executions]
        unique_dates = len(set(dates))
        date_span = (dates[-1] - dates[0]).days + 1

        if unique_dates > 5 and unique_dates / date_span > 0.7:
            return "daily"

        # Check for weekly pattern
        weekdays = [e.timestamp.weekday() for e in executions]
        weekday_counts = defaultdict(int)
        for wd in weekdays:
            weekday_counts[wd] += 1

        # Business days pattern
        business_days = sum(weekday_counts[i] for i in range(5))  # Mon-Fri
        if business_days > len(executions) * 0.8:
            return "business_days"

        return None

    def _analyze_parameters(
        self, executions: List[QueryExecution]
    ) -> Dict[str, List[Any]]:
        """Analyze common parameter values."""
        param_values = defaultdict(list)

        for execution in executions:
            for param_name, param_value in execution.parameters.items():
                param_values[param_name].append(param_value)

        # Find most common values
        common_parameters = {}
        for param_name, values in param_values.items():
            # Get unique values and their counts
            unique_values = list(set(values))
            if len(unique_values) <= 10:  # Only track if limited variety
                common_parameters[param_name] = unique_values[:5]  # Top 5

        return common_parameters

    def _calculate_average_delay(
        self, from_fingerprint: str, to_fingerprint: str
    ) -> timedelta:
        """Calculate average delay between two queries in sequence."""
        delays = []

        for i in range(1, len(self.executions)):
            if (
                self.executions[i - 1].fingerprint == from_fingerprint
                and self.executions[i].fingerprint == to_fingerprint
            ):
                delay = self.executions[i].timestamp - self.executions[i - 1].timestamp
                delays.append(delay.total_seconds())

        if delays:
            avg_delay_seconds = np.mean(delays)
            return timedelta(seconds=avg_delay_seconds)
        else:
            return timedelta(seconds=30)  # Default 30 seconds

    def _predict_temporal_queries(
        self, time_window_minutes: int
    ) -> List[PredictedQuery]:
        """Predict queries based on temporal patterns."""
        predictions = []
        now = datetime.now()

        for fingerprint, pattern in self.pattern_cache.items():
            if pattern.temporal_pattern == "hourly":
                # Check if we're in a typical execution hour
                current_hour = now.hour
                executions = self.execution_by_fingerprint[fingerprint]
                hour_counts = defaultdict(int)
                for e in executions:
                    hour_counts[e.timestamp.hour] += 1

                if hour_counts[current_hour] > len(executions) * 0.2:
                    predictions.append(
                        PredictedQuery(
                            fingerprint=fingerprint,
                            probability=0.7,
                            expected_time=now
                            + timedelta(minutes=time_window_minutes / 2),
                            confidence=0.6,
                            reason=f"Hourly pattern at {current_hour}:00",
                        )
                    )

            elif pattern.temporal_pattern == "daily":
                # Check if query typically runs around this time
                executions = self.execution_by_fingerprint[fingerprint]
                time_of_day = now.time()

                # Find executions within 30 minutes of current time
                matching_executions = [
                    e
                    for e in executions
                    if abs(
                        (e.timestamp.time().hour * 60 + e.timestamp.time().minute)
                        - (time_of_day.hour * 60 + time_of_day.minute)
                    )
                    <= 30
                ]

                if len(matching_executions) > len(executions) * 0.3:
                    predictions.append(
                        PredictedQuery(
                            fingerprint=fingerprint,
                            probability=0.6,
                            expected_time=now
                            + timedelta(minutes=time_window_minutes / 2),
                            confidence=0.5,
                            reason="Daily pattern at this time",
                        )
                    )

        return predictions

    def _analyze_historical_load(
        self, start_time: datetime.time, end_time: datetime.time, weekday: int
    ) -> Dict[str, Any]:
        """Analyze historical load for a time period."""
        matching_executions = []

        for execution in self.executions:
            exec_time = execution.timestamp.time()
            exec_weekday = execution.timestamp.weekday()

            # Check if execution falls within time window
            if start_time <= exec_time <= end_time:
                # Check weekday match (or adjacent days for more data)
                if abs(exec_weekday - weekday) <= 1:
                    matching_executions.append(execution)

        if not matching_executions:
            return {"avg_qps": 0, "peak_probability": 0}

        # Calculate QPS
        time_span_minutes = (
            datetime.combine(datetime.today(), end_time)
            - datetime.combine(datetime.today(), start_time)
        ).total_seconds() / 60

        avg_qps = len(matching_executions) / time_span_minutes / 60

        # Detect if this is typically a peak period
        total_daily_queries = len(
            [e for e in self.executions if e.timestamp.weekday() == weekday]
        )

        period_percentage = len(matching_executions) / max(total_daily_queries, 1)
        peak_probability = min(1.0, period_percentage * 3)  # Scale up

        return {
            "avg_qps": avg_qps,
            "peak_probability": peak_probability,
            "query_count": len(matching_executions),
        }

    def _estimate_query_count(self, pattern: QueryPattern, horizon_minutes: int) -> int:
        """Estimate number of queries for a pattern in the time horizon."""
        # Simple estimation based on frequency
        return int(pattern.frequency * horizon_minutes)

    def _calculate_recommended_pool_size(
        self, expected_queries: List[Dict[str, Any]], historical_load: Dict[str, Any]
    ) -> int:
        """Calculate recommended connection pool size based on forecast."""
        if not expected_queries:
            return 5  # Default minimum

        # Calculate expected concurrent load
        total_execution_time = sum(
            q["expected_count"] * q["avg_execution_time"] for q in expected_queries
        )

        # Convert to concurrent connections needed
        avg_concurrent = total_execution_time / (60 * 1000)  # Convert to minutes

        # Add buffer for peak loads
        peak_factor = 1 + historical_load.get("peak_probability", 0.5)
        recommended = int(avg_concurrent * peak_factor) + 2  # +2 for safety

        # Apply bounds
        return max(5, min(50, recommended))


class PatternLearningOptimizer:
    """Optimizer that learns from patterns to improve routing decisions."""

    def __init__(self, pattern_tracker: QueryPatternTracker):
        self.pattern_tracker = pattern_tracker
        self.optimization_rules: Dict[str, Dict[str, Any]] = {}

    def optimize_routing(
        self, fingerprint: str, current_decision: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Optimize routing decision based on learned patterns."""
        pattern = self.pattern_tracker.get_pattern(fingerprint)

        if not pattern:
            return current_decision

        optimized = current_decision.copy()

        # Apply pattern-based optimizations
        if pattern.frequency > 10:  # High-frequency query
            optimized["connection_affinity"] = True
            optimized["cache_priority"] = "high"

        if pattern.temporal_pattern == "hourly":
            optimized["pre_warm_connections"] = True

        if pattern.avg_execution_time > 1000:  # Slow query
            optimized["dedicated_connection"] = True
            optimized["timeout_extension"] = 2.0

        if pattern.typical_result_size > 10000:  # Large results
            optimized["streaming_enabled"] = True

        return optimized

    def suggest_pre_warming(self, current_time: datetime) -> List[str]:
        """Suggest queries to pre-warm based on predictions."""
        predictions = []

        # Get predictions for next 5 minutes
        for pattern in self.pattern_tracker.pattern_cache.values():
            next_queries = self.pattern_tracker.predict_next_queries(
                pattern.fingerprint, time_window_minutes=5
            )

            for prediction in next_queries:
                if prediction.probability > 0.5 and prediction.confidence > 0.6:
                    predictions.append(prediction.fingerprint)

        return list(set(predictions))[:10]  # Top 10 unique queries
