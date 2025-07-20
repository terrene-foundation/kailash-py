"""Predictive scaler for intelligent edge resource scaling.

This module provides ML-based demand prediction and preemptive scaling
decisions for edge computing resources.
"""

import asyncio
import json
import logging
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from scipy import stats

# For time series forecasting
try:
    from statsmodels.tsa.arima.model import ARIMA
    from statsmodels.tsa.holtwinters import ExponentialSmoothing

    STATSMODELS_AVAILABLE = True
except ImportError:
    STATSMODELS_AVAILABLE = False


class ScalingStrategy(Enum):
    """Strategies for predictive scaling."""

    REACTIVE = "reactive"  # Scale based on current metrics
    PREDICTIVE = "predictive"  # Scale based on predictions
    SCHEDULED = "scheduled"  # Scale based on time patterns
    HYBRID = "hybrid"  # Combine multiple strategies
    AGGRESSIVE = "aggressive"  # Scale early and generously
    CONSERVATIVE = "conservative"  # Scale cautiously


class PredictionHorizon(Enum):
    """Time horizons for predictions."""

    IMMEDIATE = 300  # 5 minutes
    SHORT_TERM = 900  # 15 minutes
    MEDIUM_TERM = 3600  # 1 hour
    LONG_TERM = 86400  # 24 hours


@dataclass
class ScalingPrediction:
    """Prediction for resource scaling needs."""

    timestamp: datetime
    horizon: PredictionHorizon
    resource_type: str
    edge_node: str
    current_usage: float
    predicted_usage: float
    confidence: float
    recommended_capacity: float
    scaling_action: str  # scale_up, scale_down, maintain
    urgency: str  # immediate, soon, planned
    reasoning: List[str] = field(default_factory=list)

    @property
    def scaling_factor(self) -> float:
        """Calculate scaling factor."""
        if self.current_usage > 0:
            return self.predicted_usage / self.current_usage
        return 1.0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "horizon": self.horizon.value,
            "resource_type": self.resource_type,
            "edge_node": self.edge_node,
            "current_usage": self.current_usage,
            "predicted_usage": self.predicted_usage,
            "confidence": self.confidence,
            "recommended_capacity": self.recommended_capacity,
            "scaling_action": self.scaling_action,
            "scaling_factor": self.scaling_factor,
            "urgency": self.urgency,
            "reasoning": self.reasoning,
        }


@dataclass
class ScalingDecision:
    """Scaling decision with execution plan."""

    decision_id: str
    predictions: List[ScalingPrediction]
    strategy: ScalingStrategy
    action_plan: Dict[str, Any]
    estimated_cost: float
    risk_assessment: Dict[str, Any]
    approval_required: bool

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "decision_id": self.decision_id,
            "predictions": [p.to_dict() for p in self.predictions],
            "strategy": self.strategy.value,
            "action_plan": self.action_plan,
            "estimated_cost": self.estimated_cost,
            "risk_assessment": self.risk_assessment,
            "approval_required": self.approval_required,
        }


class PredictiveScaler:
    """ML-based predictive scaler for edge resources."""

    def __init__(
        self,
        prediction_window: int = 3600,  # 1 hour of history for predictions
        update_interval: int = 60,  # Update predictions every minute
        confidence_threshold: float = 0.7,
        scale_up_threshold: float = 0.8,  # 80% utilization triggers scale up
        scale_down_threshold: float = 0.3,  # 30% utilization triggers scale down
        min_data_points: int = 30,
    ):
        """Initialize predictive scaler.

        Args:
            prediction_window: Historical data window for predictions
            update_interval: How often to update predictions
            confidence_threshold: Minimum confidence for actions
            scale_up_threshold: Utilization threshold for scaling up
            scale_down_threshold: Utilization threshold for scaling down
            min_data_points: Minimum data points for predictions
        """
        self.prediction_window = prediction_window
        self.update_interval = update_interval
        self.confidence_threshold = confidence_threshold
        self.scale_up_threshold = scale_up_threshold
        self.scale_down_threshold = scale_down_threshold
        self.min_data_points = min_data_points

        # Historical data storage
        self.usage_history: Dict[str, deque] = defaultdict(lambda: deque(maxlen=1000))

        # Prediction models cache
        self.models: Dict[str, Any] = {}
        self.last_model_update: Dict[str, datetime] = {}

        # Scaling history for learning
        self.scaling_history: List[Dict[str, Any]] = []

        # Background task
        self._prediction_task: Optional[asyncio.Task] = None

        self.logger = logging.getLogger(__name__)

    async def start(self):
        """Start background prediction updates."""
        if not self._prediction_task:
            self._prediction_task = asyncio.create_task(self._prediction_loop())
            self.logger.info("Predictive scaler started")

    async def stop(self):
        """Stop background prediction updates."""
        if self._prediction_task:
            self._prediction_task.cancel()
            try:
                await self._prediction_task
            except asyncio.CancelledError:
                pass
            self._prediction_task = None
            self.logger.info("Predictive scaler stopped")

    async def record_usage(
        self,
        edge_node: str,
        resource_type: str,
        usage: float,
        capacity: float,
        timestamp: Optional[datetime] = None,
    ):
        """Record resource usage data point.

        Args:
            edge_node: Edge node identifier
            resource_type: Type of resource
            usage: Current usage amount
            capacity: Total capacity
            timestamp: Usage timestamp
        """
        if timestamp is None:
            timestamp = datetime.now()

        key = f"{edge_node}:{resource_type}"

        # Store normalized utilization (0-100%)
        utilization = (usage / capacity * 100) if capacity > 0 else 0

        self.usage_history[key].append(
            {
                "timestamp": timestamp,
                "usage": usage,
                "capacity": capacity,
                "utilization": utilization,
            }
        )

    async def predict_scaling_needs(
        self,
        strategy: ScalingStrategy = ScalingStrategy.HYBRID,
        horizons: Optional[List[PredictionHorizon]] = None,
    ) -> List[ScalingDecision]:
        """Predict scaling needs across all resources.

        Args:
            strategy: Scaling strategy to use
            horizons: Prediction horizons to consider

        Returns:
            List of scaling decisions
        """
        if horizons is None:
            horizons = [PredictionHorizon.IMMEDIATE, PredictionHorizon.SHORT_TERM]

        decisions = []

        # Group predictions by edge node
        predictions_by_node: Dict[str, List[ScalingPrediction]] = defaultdict(list)

        for key, history in self.usage_history.items():
            if len(history) < self.min_data_points:
                continue

            edge_node, resource_type = key.split(":")

            # Generate predictions for each horizon
            for horizon in horizons:
                prediction = await self._predict_for_resource(
                    edge_node, resource_type, history, horizon
                )

                if prediction and prediction.confidence >= self.confidence_threshold:
                    predictions_by_node[edge_node].append(prediction)

        # Create scaling decisions
        for edge_node, predictions in predictions_by_node.items():
            if not predictions:
                continue

            decision = await self._create_scaling_decision(
                edge_node, predictions, strategy
            )

            if decision:
                decisions.append(decision)

        return decisions

    async def get_resource_forecast(
        self, edge_node: str, resource_type: str, forecast_minutes: int = 60
    ) -> Dict[str, Any]:
        """Get detailed forecast for a specific resource.

        Args:
            edge_node: Edge node identifier
            resource_type: Type of resource
            forecast_minutes: Minutes to forecast

        Returns:
            Forecast details
        """
        key = f"{edge_node}:{resource_type}"
        history = self.usage_history.get(key, [])

        if len(history) < self.min_data_points:
            return {
                "error": "Insufficient data for forecast",
                "data_points": len(history),
                "required": self.min_data_points,
            }

        # Prepare time series data
        timestamps = [h["timestamp"] for h in history]
        utilizations = [h["utilization"] for h in history]

        # Generate forecast
        forecast = await self._generate_forecast(
            timestamps, utilizations, forecast_minutes
        )

        return {
            "edge_node": edge_node,
            "resource_type": resource_type,
            "current_utilization": utilizations[-1] if utilizations else 0,
            "forecast": forecast,
            "confidence_intervals": self._calculate_confidence_intervals(forecast),
        }

    async def evaluate_scaling_decision(
        self,
        decision_id: str,
        actual_usage: Dict[str, float],
        feedback: Optional[str] = None,
    ):
        """Evaluate a past scaling decision for learning.

        Args:
            decision_id: Decision to evaluate
            actual_usage: Actual usage that occurred
            feedback: Optional human feedback
        """
        # Find the decision in history
        decision_record = None
        for record in self.scaling_history:
            if record.get("decision_id") == decision_id:
                decision_record = record
                break

        if not decision_record:
            self.logger.warning(f"Decision {decision_id} not found in history")
            return

        # Calculate prediction accuracy
        predictions = decision_record.get("predictions", [])
        accuracy_scores = []

        for pred in predictions:
            key = f"{pred['edge_node']}:{pred['resource_type']}"
            if key in actual_usage:
                predicted = pred["predicted_usage"]
                actual = actual_usage[key]

                # Calculate error percentage
                error = abs(predicted - actual) / actual if actual > 0 else 0
                accuracy = max(0, 1 - error)
                accuracy_scores.append(accuracy)

        # Update decision record
        decision_record["evaluation"] = {
            "actual_usage": actual_usage,
            "accuracy_scores": accuracy_scores,
            "average_accuracy": np.mean(accuracy_scores) if accuracy_scores else 0,
            "feedback": feedback,
            "evaluated_at": datetime.now().isoformat(),
        }

        # Learn from the evaluation
        await self._update_models_from_feedback(decision_record)

    async def _prediction_loop(self):
        """Background loop for updating predictions."""
        while True:
            try:
                await asyncio.sleep(self.update_interval)

                # Update models if needed
                await self._update_prediction_models()

                # Clean old history
                await self._cleanup_old_history()

            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Prediction loop error: {e}")

    async def _predict_for_resource(
        self,
        edge_node: str,
        resource_type: str,
        history: deque,
        horizon: PredictionHorizon,
    ) -> Optional[ScalingPrediction]:
        """Generate prediction for a specific resource.

        Args:
            edge_node: Edge node identifier
            resource_type: Type of resource
            history: Usage history
            horizon: Prediction horizon

        Returns:
            Scaling prediction or None
        """
        # Extract time series
        utilizations = [h["utilization"] for h in history]
        timestamps = [h["timestamp"] for h in history]

        if not utilizations:
            return None

        current_usage = utilizations[-1]
        current_capacity = history[-1]["capacity"]

        # Predict future usage
        predicted_usage, confidence = await self._predict_usage(
            utilizations, timestamps, horizon.value
        )

        # Determine scaling action
        if predicted_usage > self.scale_up_threshold * 100:
            scaling_action = "scale_up"
            urgency = "immediate" if horizon == PredictionHorizon.IMMEDIATE else "soon"
        elif predicted_usage < self.scale_down_threshold * 100:
            scaling_action = "scale_down"
            urgency = "planned"
        else:
            scaling_action = "maintain"
            urgency = "none"

        # Calculate recommended capacity
        if scaling_action == "scale_up":
            # Add 20% buffer above predicted usage
            recommended_capacity = current_capacity * (predicted_usage / 100) * 1.2
        elif scaling_action == "scale_down":
            # Keep 50% buffer above predicted usage
            recommended_capacity = current_capacity * (predicted_usage / 100) * 1.5
        else:
            recommended_capacity = current_capacity

        # Build reasoning
        reasoning = []
        if scaling_action == "scale_up":
            reasoning.append(
                f"Predicted utilization ({predicted_usage:.1f}%) exceeds threshold ({self.scale_up_threshold * 100}%)"
            )
        elif scaling_action == "scale_down":
            reasoning.append(
                f"Predicted utilization ({predicted_usage:.1f}%) below threshold ({self.scale_down_threshold * 100}%)"
            )

        # Add trend analysis
        trend = self._analyze_trend(utilizations)
        if trend > 0.1:
            reasoning.append(f"Upward trend detected ({trend:.2f}% per interval)")
        elif trend < -0.1:
            reasoning.append(f"Downward trend detected ({trend:.2f}% per interval)")

        return ScalingPrediction(
            timestamp=datetime.now(),
            horizon=horizon,
            resource_type=resource_type,
            edge_node=edge_node,
            current_usage=current_usage,
            predicted_usage=predicted_usage,
            confidence=confidence,
            recommended_capacity=recommended_capacity,
            scaling_action=scaling_action,
            urgency=urgency,
            reasoning=reasoning,
        )

    async def _predict_usage(
        self,
        utilizations: List[float],
        timestamps: List[datetime],
        horizon_seconds: int,
    ) -> Tuple[float, float]:
        """Predict future usage using time series models.

        Args:
            utilizations: Historical utilization values
            timestamps: Timestamps for utilization values
            horizon_seconds: Prediction horizon in seconds

        Returns:
            Tuple of (predicted_usage, confidence)
        """
        if not STATSMODELS_AVAILABLE:
            # Fallback to simple linear regression
            return self._simple_prediction(utilizations, timestamps, horizon_seconds)

        try:
            # Use ARIMA for time series prediction
            model = ARIMA(utilizations, order=(1, 1, 1))
            model_fit = model.fit()

            # Calculate steps ahead
            interval_seconds = (
                (timestamps[-1] - timestamps[-2]).total_seconds()
                if len(timestamps) > 1
                else 60
            )
            steps_ahead = int(horizon_seconds / interval_seconds)

            # Make prediction
            forecast = model_fit.forecast(steps=steps_ahead)
            predicted_usage = float(forecast[-1])

            # Calculate confidence based on model metrics
            confidence = 0.8  # Base confidence for ARIMA

            # Adjust confidence based on data quality
            if len(utilizations) > 100:
                confidence += 0.1
            if np.std(utilizations) < 10:  # Low variance
                confidence += 0.05

            return max(0, min(100, predicted_usage)), min(1.0, confidence)

        except Exception as e:
            self.logger.warning(
                f"ARIMA prediction failed: {e}, falling back to simple prediction"
            )
            return self._simple_prediction(utilizations, timestamps, horizon_seconds)

    def _simple_prediction(
        self,
        utilizations: List[float],
        timestamps: List[datetime],
        horizon_seconds: int,
    ) -> Tuple[float, float]:
        """Simple prediction using linear regression.

        Args:
            utilizations: Historical utilization values
            timestamps: Timestamps for utilization values
            horizon_seconds: Prediction horizon in seconds

        Returns:
            Tuple of (predicted_usage, confidence)
        """
        if len(utilizations) < 2:
            return utilizations[-1] if utilizations else 0, 0.5

        # Convert timestamps to seconds from first timestamp
        time_values = [(t - timestamps[0]).total_seconds() for t in timestamps]

        # Linear regression
        slope, intercept, r_value, _, _ = stats.linregress(time_values, utilizations)

        # Predict future value
        future_time = time_values[-1] + horizon_seconds
        predicted_usage = intercept + slope * future_time

        # Confidence based on R-squared
        confidence = abs(r_value) ** 2

        # Add exponential smoothing for better short-term predictions
        if len(utilizations) > 5:
            alpha = 0.3  # Smoothing factor
            smoothed = utilizations[-1]
            for i in range(len(utilizations) - 2, -1, -1):
                smoothed = alpha * utilizations[i] + (1 - alpha) * smoothed

            # Blend linear prediction with smoothed value
            predicted_usage = 0.7 * predicted_usage + 0.3 * smoothed
            confidence = (
                confidence * 0.9
            )  # Slightly reduce confidence for blended prediction

        return max(0, min(100, predicted_usage)), confidence

    def _analyze_trend(self, utilizations: List[float]) -> float:
        """Analyze trend in utilization data.

        Args:
            utilizations: Utilization values

        Returns:
            Trend slope (percentage per interval)
        """
        if len(utilizations) < 3:
            return 0.0

        # Use recent data for trend
        recent = utilizations[-10:] if len(utilizations) > 10 else utilizations

        # Linear regression for trend
        x = list(range(len(recent)))
        slope, _, _, _, _ = stats.linregress(x, recent)

        return slope

    async def _create_scaling_decision(
        self,
        edge_node: str,
        predictions: List[ScalingPrediction],
        strategy: ScalingStrategy,
    ) -> Optional[ScalingDecision]:
        """Create scaling decision from predictions.

        Args:
            edge_node: Edge node identifier
            predictions: List of predictions
            strategy: Scaling strategy

        Returns:
            Scaling decision or None
        """
        # Filter predictions by strategy
        relevant_predictions = []

        if strategy == ScalingStrategy.REACTIVE:
            # Only immediate predictions
            relevant_predictions = [
                p for p in predictions if p.horizon == PredictionHorizon.IMMEDIATE
            ]
        elif strategy == ScalingStrategy.PREDICTIVE:
            # All predictions
            relevant_predictions = predictions
        elif strategy == ScalingStrategy.SCHEDULED:
            # Focus on longer-term predictions
            relevant_predictions = [
                p
                for p in predictions
                if p.horizon
                in [PredictionHorizon.MEDIUM_TERM, PredictionHorizon.LONG_TERM]
            ]
        elif strategy == ScalingStrategy.HYBRID:
            # Use all predictions with weighting
            relevant_predictions = predictions

        if not relevant_predictions:
            return None

        # Check if any action needed
        actions_needed = [
            p for p in relevant_predictions if p.scaling_action != "maintain"
        ]

        if not actions_needed:
            return None

        # Create action plan
        action_plan = await self._create_action_plan(
            edge_node, actions_needed, strategy
        )

        # Estimate cost
        estimated_cost = self._estimate_scaling_cost(action_plan)

        # Risk assessment
        risk_assessment = self._assess_scaling_risk(actions_needed)

        # Determine if approval needed
        approval_required = (
            estimated_cost > 100  # Cost threshold
            or risk_assessment.get("risk_level", "low") == "high"
            or strategy == ScalingStrategy.AGGRESSIVE
        )

        decision = ScalingDecision(
            decision_id=f"{edge_node}_{datetime.now().timestamp()}",
            predictions=actions_needed,
            strategy=strategy,
            action_plan=action_plan,
            estimated_cost=estimated_cost,
            risk_assessment=risk_assessment,
            approval_required=approval_required,
        )

        # Store in history
        self.scaling_history.append(decision.to_dict())

        return decision

    async def _create_action_plan(
        self,
        edge_node: str,
        predictions: List[ScalingPrediction],
        strategy: ScalingStrategy,
    ) -> Dict[str, Any]:
        """Create detailed action plan.

        Args:
            edge_node: Edge node identifier
            predictions: Predictions requiring action
            strategy: Scaling strategy

        Returns:
            Action plan
        """
        actions = []

        # Group by resource type
        by_resource = defaultdict(list)
        for pred in predictions:
            by_resource[pred.resource_type].append(pred)

        for resource_type, preds in by_resource.items():
            # Find most urgent prediction
            most_urgent = min(preds, key=lambda p: p.horizon.value)

            if most_urgent.scaling_action == "scale_up":
                actions.append(
                    {
                        "action": "increase_capacity",
                        "resource_type": resource_type,
                        "current_capacity": most_urgent.current_usage
                        / (most_urgent.predicted_usage / 100),
                        "target_capacity": most_urgent.recommended_capacity,
                        "urgency": most_urgent.urgency,
                        "execute_at": (
                            datetime.now() + timedelta(seconds=60)
                            if most_urgent.urgency == "immediate"
                            else datetime.now()
                            + timedelta(seconds=most_urgent.horizon.value / 2)
                        ).isoformat(),
                    }
                )
            elif most_urgent.scaling_action == "scale_down":
                actions.append(
                    {
                        "action": "decrease_capacity",
                        "resource_type": resource_type,
                        "current_capacity": most_urgent.current_usage
                        / (most_urgent.predicted_usage / 100),
                        "target_capacity": most_urgent.recommended_capacity,
                        "urgency": most_urgent.urgency,
                        "execute_at": (
                            datetime.now()
                            + timedelta(seconds=most_urgent.horizon.value)
                        ).isoformat(),
                    }
                )

        return {
            "edge_node": edge_node,
            "actions": actions,
            "strategy": strategy.value,
            "created_at": datetime.now().isoformat(),
        }

    def _estimate_scaling_cost(self, action_plan: Dict[str, Any]) -> float:
        """Estimate cost of scaling actions.

        Args:
            action_plan: Action plan

        Returns:
            Estimated cost
        """
        total_cost = 0.0

        # Simple cost model
        resource_costs = {
            "cpu": 0.1,  # Per core per hour
            "memory": 0.01,  # Per GB per hour
            "gpu": 1.0,  # Per GPU per hour
            "storage": 0.05,  # Per GB per month
            "network": 0.02,  # Per Mbps
        }

        for action in action_plan.get("actions", []):
            resource_type = action["resource_type"]

            if action["action"] == "increase_capacity":
                capacity_increase = (
                    action["target_capacity"] - action["current_capacity"]
                )
                cost_per_unit = resource_costs.get(resource_type, 0.05)

                # Estimate hours until scale down (assume 4 hours)
                hours = 4
                total_cost += capacity_increase * cost_per_unit * hours

        return round(total_cost, 2)

    def _assess_scaling_risk(
        self, predictions: List[ScalingPrediction]
    ) -> Dict[str, Any]:
        """Assess risk of scaling actions.

        Args:
            predictions: Scaling predictions

        Returns:
            Risk assessment
        """
        risks = []

        # Check for conflicting predictions
        scale_up_count = sum(1 for p in predictions if p.scaling_action == "scale_up")
        scale_down_count = sum(
            1 for p in predictions if p.scaling_action == "scale_down"
        )

        if scale_up_count > 0 and scale_down_count > 0:
            risks.append(
                {
                    "type": "conflicting_predictions",
                    "severity": "medium",
                    "description": "Both scale up and scale down predicted",
                }
            )

        # Check confidence levels
        low_confidence = [p for p in predictions if p.confidence < 0.6]
        if low_confidence:
            risks.append(
                {
                    "type": "low_confidence",
                    "severity": "low",
                    "description": f"{len(low_confidence)} predictions with low confidence",
                }
            )

        # Check for aggressive scaling
        high_scale_factors = [p for p in predictions if p.scaling_factor > 2.0]
        if high_scale_factors:
            risks.append(
                {
                    "type": "aggressive_scaling",
                    "severity": "high",
                    "description": f"{len(high_scale_factors)} predictions require >2x scaling",
                }
            )

        # Determine overall risk level
        if any(r["severity"] == "high" for r in risks):
            risk_level = "high"
        elif any(r["severity"] == "medium" for r in risks):
            risk_level = "medium"
        else:
            risk_level = "low"

        return {
            "risk_level": risk_level,
            "risks": risks,
            "mitigation_suggestions": self._get_mitigation_suggestions(risks),
        }

    def _get_mitigation_suggestions(self, risks: List[Dict[str, Any]]) -> List[str]:
        """Get risk mitigation suggestions.

        Args:
            risks: Identified risks

        Returns:
            Mitigation suggestions
        """
        suggestions = []

        for risk in risks:
            if risk["type"] == "conflicting_predictions":
                suggestions.append(
                    "Review resource allocation patterns and consider phased scaling"
                )
            elif risk["type"] == "low_confidence":
                suggestions.append(
                    "Collect more historical data before aggressive scaling"
                )
            elif risk["type"] == "aggressive_scaling":
                suggestions.append(
                    "Consider gradual scaling with monitoring checkpoints"
                )

        return suggestions

    async def _update_prediction_models(self):
        """Update prediction models based on new data."""
        for key in self.usage_history:
            # Check if model needs update
            last_update = self.last_model_update.get(key)
            if last_update and (datetime.now() - last_update).total_seconds() < 3600:
                continue  # Update models hourly

            # Update model for this resource
            # In production, this would retrain ML models
            self.models[key] = {"updated": datetime.now().isoformat()}
            self.last_model_update[key] = datetime.now()

    async def _cleanup_old_history(self):
        """Clean up old historical data."""
        cutoff = datetime.now() - timedelta(seconds=self.prediction_window * 2)

        for key, history in self.usage_history.items():
            # Remove old entries
            while history and history[0]["timestamp"] < cutoff:
                history.popleft()

    async def _update_models_from_feedback(self, decision_record: Dict[str, Any]):
        """Update models based on decision evaluation.

        Args:
            decision_record: Evaluated decision record
        """
        evaluation = decision_record.get("evaluation", {})
        accuracy = evaluation.get("average_accuracy", 0)

        # Simple learning: adjust thresholds based on accuracy
        if accuracy < 0.7:  # Poor prediction
            # Make predictions more conservative
            self.confidence_threshold = min(0.9, self.confidence_threshold + 0.05)
            self.logger.info(
                f"Adjusted confidence threshold to {self.confidence_threshold}"
            )
        elif accuracy > 0.9:  # Good prediction
            # Can be slightly less conservative
            self.confidence_threshold = max(0.6, self.confidence_threshold - 0.02)

    def _calculate_confidence_intervals(
        self, forecast: List[float]
    ) -> Dict[str, List[float]]:
        """Calculate confidence intervals for forecast.

        Args:
            forecast: Forecast values

        Returns:
            Confidence intervals
        """
        # Simple confidence intervals based on historical variance
        std_dev = np.std(forecast) if len(forecast) > 1 else 5.0

        return {
            "lower_95": [max(0, v - 1.96 * std_dev) for v in forecast],
            "upper_95": [min(100, v + 1.96 * std_dev) for v in forecast],
            "lower_68": [max(0, v - std_dev) for v in forecast],
            "upper_68": [min(100, v + std_dev) for v in forecast],
        }

    async def _generate_forecast(
        self, timestamps: List[datetime], values: List[float], forecast_minutes: int
    ) -> List[Dict[str, Any]]:
        """Generate detailed forecast.

        Args:
            timestamps: Historical timestamps
            values: Historical values
            forecast_minutes: Minutes to forecast

        Returns:
            Forecast points
        """
        if not timestamps or not values:
            return []

        # Calculate interval
        interval_seconds = (
            (timestamps[-1] - timestamps[-2]).total_seconds()
            if len(timestamps) > 1
            else 60
        )
        points_to_forecast = int(forecast_minutes * 60 / interval_seconds)

        forecast_points = []

        for i in range(1, points_to_forecast + 1):
            future_time = timestamps[-1] + timedelta(seconds=interval_seconds * i)

            # Predict value
            predicted_value, confidence = await self._predict_usage(
                values, timestamps, interval_seconds * i
            )

            forecast_points.append(
                {
                    "timestamp": future_time.isoformat(),
                    "value": predicted_value,
                    "confidence": confidence,
                    "minutes_ahead": i * interval_seconds / 60,
                }
            )

        return forecast_points
