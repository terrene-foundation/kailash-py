"""Predictive edge warming service for anticipating and pre-warming edge nodes.

This service analyzes usage patterns, predicts future needs, and pre-warms
edge nodes to reduce cold start latency.
"""

import asyncio
import json
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple

import numpy as np
from sklearn.linear_model import LinearRegression
from sklearn.preprocessing import StandardScaler


class PredictionStrategy(Enum):
    """Prediction strategies for edge warming."""

    TIME_SERIES = "time_series"  # Historical time-based patterns
    GEOGRAPHIC = "geographic"  # Location-based predictions
    USER_BEHAVIOR = "user_behavior"  # User-specific patterns
    WORKLOAD = "workload"  # Workload type patterns
    HYBRID = "hybrid"  # Combination of strategies


@dataclass
class UsagePattern:
    """Represents a usage pattern for prediction."""

    timestamp: datetime
    edge_node: str
    user_id: Optional[str]
    location: Optional[Tuple[float, float]]  # lat, lon
    workload_type: str
    response_time: float
    resource_usage: Dict[str, float]  # cpu, memory, etc.

    def to_features(self) -> List[float]:
        """Convert pattern to feature vector for ML."""
        features = [
            self.timestamp.hour,
            self.timestamp.weekday(),
            self.response_time,
            self.resource_usage.get("cpu", 0),
            self.resource_usage.get("memory", 0),
        ]

        if self.location:
            features.extend(self.location)

        return features


@dataclass
class WarmingDecision:
    """Represents a decision to warm an edge node."""

    edge_node: str
    confidence: float
    predicted_time: datetime
    resources_needed: Dict[str, float]
    strategy_used: PredictionStrategy
    reasoning: str


class PredictiveWarmer:
    """Predictive edge warming service.

    Analyzes usage patterns and pre-warms edge nodes to reduce latency.
    """

    def __init__(
        self,
        history_window: int = 7 * 24 * 60 * 60,  # 7 days in seconds
        prediction_horizon: int = 300,  # 5 minutes ahead
        confidence_threshold: float = 0.7,
        max_prewarmed_nodes: int = 10,
    ):
        """Initialize predictive warmer.

        Args:
            history_window: Time window for historical analysis
            prediction_horizon: How far ahead to predict (seconds)
            confidence_threshold: Minimum confidence for warming
            max_prewarmed_nodes: Maximum nodes to keep warm
        """
        self.history_window = history_window
        self.prediction_horizon = prediction_horizon
        self.confidence_threshold = confidence_threshold
        self.max_prewarmed_nodes = max_prewarmed_nodes

        # Pattern storage
        self.usage_history: deque = deque(maxlen=10000)
        self.pattern_cache: Dict[str, List[UsagePattern]] = defaultdict(list)

        # ML models for prediction
        self.time_series_model = LinearRegression()
        self.scaler = StandardScaler()
        self.model_trained = False

        # Current state
        self.warmed_nodes: Set[str] = set()
        self.warming_decisions: List[WarmingDecision] = []

        # Metrics
        self.predictions_made = 0
        self.successful_predictions = 0
        self.false_positives = 0
        self.missed_predictions = 0

        self._running = False
        self._prediction_task = None

    async def start(self):
        """Start the predictive warming service."""
        self._running = True
        self._prediction_task = asyncio.create_task(self._prediction_loop())

    async def stop(self):
        """Stop the predictive warming service."""
        self._running = False
        if self._prediction_task:
            self._prediction_task.cancel()
            try:
                await self._prediction_task
            except asyncio.CancelledError:
                pass

    async def record_usage(self, pattern: UsagePattern):
        """Record a usage pattern for analysis.

        Args:
            pattern: Usage pattern to record
        """
        self.usage_history.append(pattern)

        # Cache by different dimensions
        self.pattern_cache[pattern.edge_node].append(pattern)
        if pattern.user_id:
            self.pattern_cache[f"user_{pattern.user_id}"].append(pattern)
        self.pattern_cache[pattern.workload_type].append(pattern)

        # Retrain model periodically
        if len(self.usage_history) % 100 == 0:
            await self._train_models()

    async def predict_warming_needs(
        self, strategy: PredictionStrategy = PredictionStrategy.HYBRID
    ) -> List[WarmingDecision]:
        """Predict which edge nodes need warming.

        Args:
            strategy: Prediction strategy to use

        Returns:
            List of warming decisions
        """
        decisions = []

        if strategy == PredictionStrategy.TIME_SERIES:
            decisions.extend(await self._predict_time_series())
        elif strategy == PredictionStrategy.GEOGRAPHIC:
            decisions.extend(await self._predict_geographic())
        elif strategy == PredictionStrategy.USER_BEHAVIOR:
            decisions.extend(await self._predict_user_behavior())
        elif strategy == PredictionStrategy.WORKLOAD:
            decisions.extend(await self._predict_workload())
        elif strategy == PredictionStrategy.HYBRID:
            # Combine all strategies
            all_decisions = []
            all_decisions.extend(await self._predict_time_series())
            all_decisions.extend(await self._predict_geographic())
            all_decisions.extend(await self._predict_user_behavior())
            all_decisions.extend(await self._predict_workload())

            # Aggregate and rank decisions
            decisions = self._aggregate_decisions(all_decisions)

        # Filter by confidence and limit
        decisions = [d for d in decisions if d.confidence >= self.confidence_threshold]
        decisions.sort(key=lambda d: d.confidence, reverse=True)

        return decisions[: self.max_prewarmed_nodes]

    async def _prediction_loop(self):
        """Main prediction loop."""
        while self._running:
            try:
                # Make predictions
                decisions = await self.predict_warming_needs()
                self.warming_decisions = decisions

                # Execute warming decisions
                for decision in decisions:
                    await self._execute_warming(decision)

                # Wait before next prediction
                await asyncio.sleep(0.1)  # Fast prediction for tests

            except Exception as e:
                print(f"Prediction error: {e}")
                await asyncio.sleep(0.1)  # Fast retry for tests

    async def _train_models(self):
        """Train ML models on historical data."""
        if len(self.usage_history) < 100:
            return  # Not enough data

        # Prepare training data
        X = []
        y = []

        for i in range(len(self.usage_history) - 1):
            pattern = self.usage_history[i]
            next_pattern = self.usage_history[i + 1]

            # Features from current pattern
            features = pattern.to_features()
            X.append(features)

            # Target: will this edge be used in next time window?
            time_diff = (next_pattern.timestamp - pattern.timestamp).total_seconds()
            y.append(1 if time_diff < self.prediction_horizon else 0)

        if X and y:
            # Normalize features
            X_scaled = self.scaler.fit_transform(X)

            # Train model
            self.time_series_model.fit(X_scaled, y)
            self.model_trained = True

    async def _predict_time_series(self) -> List[WarmingDecision]:
        """Predict based on time series patterns."""
        decisions = []

        if not self.model_trained or len(self.usage_history) < 10:
            return decisions

        # Analyze patterns for each edge node
        edge_patterns = defaultdict(list)
        for pattern in self.usage_history:
            edge_patterns[pattern.edge_node].append(pattern)

        current_time = datetime.now()

        for edge_node, patterns in edge_patterns.items():
            if len(patterns) < 5:
                continue

            # Extract time-based features
            hourly_usage = defaultdict(int)
            daily_usage = defaultdict(int)

            for pattern in patterns[-100:]:  # Last 100 patterns
                hourly_usage[pattern.timestamp.hour] += 1
                daily_usage[pattern.timestamp.weekday()] += 1

            # Predict if node will be needed
            current_hour = current_time.hour
            current_day = current_time.weekday()

            # Simple heuristic: high usage in current hour/day
            hour_score = (
                hourly_usage[current_hour] / max(hourly_usage.values())
                if hourly_usage
                else 0
            )
            day_score = (
                daily_usage[current_day] / max(daily_usage.values())
                if daily_usage
                else 0
            )

            confidence = (hour_score + day_score) / 2

            if confidence > self.confidence_threshold:
                decisions.append(
                    WarmingDecision(
                        edge_node=edge_node,
                        confidence=confidence,
                        predicted_time=current_time
                        + timedelta(seconds=self.prediction_horizon),
                        resources_needed=self._estimate_resources(patterns),
                        strategy_used=PredictionStrategy.TIME_SERIES,
                        reasoning=f"High usage at hour {current_hour} (score: {hour_score:.2f})",
                    )
                )

        return decisions

    async def _predict_geographic(self) -> List[WarmingDecision]:
        """Predict based on geographic patterns."""
        decisions = []

        # Group patterns by location proximity
        location_patterns = defaultdict(list)

        for pattern in self.usage_history:
            if pattern.location:
                # Simple grid-based grouping
                lat_grid = int(pattern.location[0] * 10) / 10
                lon_grid = int(pattern.location[1] * 10) / 10
                location_patterns[(lat_grid, lon_grid)].append(pattern)

        # Find active locations
        current_time = datetime.now()
        active_locations = []

        for location, patterns in location_patterns.items():
            recent_patterns = [
                p
                for p in patterns
                if (current_time - p.timestamp).total_seconds() < 3600  # Last hour
            ]

            if len(recent_patterns) > 5:
                active_locations.append(location)

        # Predict edge nodes for active locations
        for location in active_locations:
            patterns = location_patterns[location]

            # Find most used edge node for this location
            edge_usage = defaultdict(int)
            for pattern in patterns:
                edge_usage[pattern.edge_node] += 1

            if edge_usage:
                best_edge = max(edge_usage, key=edge_usage.get)
                confidence = edge_usage[best_edge] / len(patterns)

                decisions.append(
                    WarmingDecision(
                        edge_node=best_edge,
                        confidence=confidence,
                        predicted_time=current_time
                        + timedelta(seconds=self.prediction_horizon),
                        resources_needed=self._estimate_resources(patterns),
                        strategy_used=PredictionStrategy.GEOGRAPHIC,
                        reasoning=f"Active location {location} typically uses {best_edge}",
                    )
                )

        return decisions

    async def _predict_user_behavior(self) -> List[WarmingDecision]:
        """Predict based on user behavior patterns."""
        decisions = []

        # Analyze per-user patterns
        user_patterns = defaultdict(list)

        for pattern in self.usage_history:
            if pattern.user_id:
                user_patterns[pattern.user_id].append(pattern)

        current_time = datetime.now()

        for user_id, patterns in user_patterns.items():
            if len(patterns) < 10:
                continue

            # Find user's typical usage times
            usage_times = [p.timestamp.hour for p in patterns]
            avg_hour = sum(usage_times) / len(usage_times)

            # Check if current time matches user's pattern
            if abs(current_time.hour - avg_hour) < 2:
                # Find user's preferred edge nodes
                edge_usage = defaultdict(int)
                for pattern in patterns:
                    edge_usage[pattern.edge_node] += 1

                if edge_usage:
                    best_edge = max(edge_usage, key=edge_usage.get)
                    confidence = edge_usage[best_edge] / len(patterns)

                    decisions.append(
                        WarmingDecision(
                            edge_node=best_edge,
                            confidence=confidence
                            * 0.8,  # Slightly lower confidence for user-based
                            predicted_time=current_time
                            + timedelta(seconds=self.prediction_horizon),
                            resources_needed=self._estimate_resources(patterns),
                            strategy_used=PredictionStrategy.USER_BEHAVIOR,
                            reasoning=f"User {user_id} typically active at this time",
                        )
                    )

        return decisions

    async def _predict_workload(self) -> List[WarmingDecision]:
        """Predict based on workload patterns."""
        decisions = []

        # Analyze workload type patterns
        workload_patterns = defaultdict(list)

        for pattern in self.usage_history:
            workload_patterns[pattern.workload_type].append(pattern)

        current_time = datetime.now()

        for workload_type, patterns in workload_patterns.items():
            # Find recent surge in this workload type
            recent_patterns = [
                p
                for p in patterns
                if (current_time - p.timestamp).total_seconds() < 600  # Last 10 minutes
            ]

            if len(recent_patterns) > 5:
                # Increasing trend suggests more coming
                edge_usage = defaultdict(int)
                for pattern in recent_patterns:
                    edge_usage[pattern.edge_node] += 1

                for edge_node, count in edge_usage.items():
                    confidence = count / len(recent_patterns)

                    decisions.append(
                        WarmingDecision(
                            edge_node=edge_node,
                            confidence=confidence,
                            predicted_time=current_time
                            + timedelta(seconds=self.prediction_horizon),
                            resources_needed=self._estimate_resources(patterns),
                            strategy_used=PredictionStrategy.WORKLOAD,
                            reasoning=f"Surge in {workload_type} workload detected",
                        )
                    )

        return decisions

    def _aggregate_decisions(
        self, decisions: List[WarmingDecision]
    ) -> List[WarmingDecision]:
        """Aggregate decisions from multiple strategies."""
        # Group by edge node
        node_decisions = defaultdict(list)
        for decision in decisions:
            node_decisions[decision.edge_node].append(decision)

        # Combine confidences
        aggregated = []
        for edge_node, node_decisions_list in node_decisions.items():
            # Weight different strategies
            weights = {
                PredictionStrategy.TIME_SERIES: 0.3,
                PredictionStrategy.GEOGRAPHIC: 0.25,
                PredictionStrategy.USER_BEHAVIOR: 0.25,
                PredictionStrategy.WORKLOAD: 0.2,
            }

            total_confidence = 0
            total_weight = 0
            resources = {}
            reasons = []

            for decision in node_decisions_list:
                weight = weights.get(decision.strategy_used, 0.25)
                total_confidence += decision.confidence * weight
                total_weight += weight

                # Merge resource estimates
                for resource, value in decision.resources_needed.items():
                    resources[resource] = max(resources.get(resource, 0), value)

                reasons.append(f"{decision.strategy_used.value}: {decision.reasoning}")

            if total_weight > 0:
                aggregated.append(
                    WarmingDecision(
                        edge_node=edge_node,
                        confidence=total_confidence / total_weight,
                        predicted_time=datetime.now()
                        + timedelta(seconds=self.prediction_horizon),
                        resources_needed=resources,
                        strategy_used=PredictionStrategy.HYBRID,
                        reasoning="; ".join(reasons),
                    )
                )

        return aggregated

    def _estimate_resources(self, patterns: List[UsagePattern]) -> Dict[str, float]:
        """Estimate resource needs based on patterns."""
        if not patterns:
            return {"cpu": 0.1, "memory": 128}

        # Average resource usage
        cpu_usage = []
        memory_usage = []

        for pattern in patterns[-20:]:  # Last 20 patterns
            cpu_usage.append(pattern.resource_usage.get("cpu", 0))
            memory_usage.append(pattern.resource_usage.get("memory", 0))

        return {
            "cpu": np.percentile(cpu_usage, 75) if cpu_usage else 0.1,
            "memory": np.percentile(memory_usage, 75) if memory_usage else 128,
        }

    async def _execute_warming(self, decision: WarmingDecision):
        """Execute a warming decision."""
        if decision.edge_node not in self.warmed_nodes:
            # Simulate warming the edge node
            print(
                f"Warming edge node {decision.edge_node} "
                f"(confidence: {decision.confidence:.2f}, "
                f"reason: {decision.reasoning})"
            )

            self.warmed_nodes.add(decision.edge_node)
            self.predictions_made += 1

            # TODO: Actual edge node warming implementation
            # This would involve:
            # 1. Pre-allocating resources
            # 2. Loading necessary data
            # 3. Establishing connections
            # 4. Running health checks

    def evaluate_prediction(self, edge_node: str, was_used: bool):
        """Evaluate a prediction after the fact.

        Args:
            edge_node: Edge node that was predicted
            was_used: Whether the node was actually used
        """
        if edge_node in self.warmed_nodes:
            if was_used:
                self.successful_predictions += 1
            else:
                self.false_positives += 1
        elif was_used:
            self.missed_predictions += 1

    def get_metrics(self) -> Dict[str, Any]:
        """Get prediction metrics."""
        total_evaluated = (
            self.successful_predictions + self.false_positives + self.missed_predictions
        )

        if total_evaluated == 0:
            precision = recall = f1_score = 0
        else:
            precision = (
                self.successful_predictions
                / (self.successful_predictions + self.false_positives)
                if (self.successful_predictions + self.false_positives) > 0
                else 0
            )
            recall = (
                self.successful_predictions
                / (self.successful_predictions + self.missed_predictions)
                if (self.successful_predictions + self.missed_predictions) > 0
                else 0
            )
            f1_score = (
                2 * precision * recall / (precision + recall)
                if (precision + recall) > 0
                else 0
            )

        return {
            "predictions_made": self.predictions_made,
            "successful_predictions": self.successful_predictions,
            "false_positives": self.false_positives,
            "missed_predictions": self.missed_predictions,
            "precision": precision,
            "recall": recall,
            "f1_score": f1_score,
            "warmed_nodes": list(self.warmed_nodes),
            "current_decisions": [
                {
                    "edge_node": d.edge_node,
                    "confidence": d.confidence,
                    "strategy": d.strategy_used.value,
                    "reasoning": d.reasoning,
                }
                for d in self.warming_decisions
            ],
        }
