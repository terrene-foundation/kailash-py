"""
Feedback system for Kaizen auto-optimization.

This module implements the feedback loop system including:
- Execution result analysis
- Quality scoring system
- Learning algorithms
- Feedback integration
- Anomaly detection and correction
"""

import asyncio
import logging
import statistics
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

import numpy as np

logger = logging.getLogger(__name__)


class FeedbackType(Enum):
    """Types of feedback that can be collected."""

    EXECUTION_RESULT = "execution_result"
    USER_FEEDBACK = "user_feedback"
    PERFORMANCE_METRIC = "performance_metric"
    QUALITY_SCORE = "quality_score"
    ANOMALY_DETECTION = "anomaly_detection"


class QualityMetric(Enum):
    """Quality metrics for evaluation."""

    ACCURACY = "accuracy"
    RELEVANCE = "relevance"
    COMPLETENESS = "completeness"
    COHERENCE = "coherence"
    EFFICIENCY = "efficiency"
    RELIABILITY = "reliability"


@dataclass
class FeedbackEntry:
    """Individual feedback entry."""

    execution_id: str
    timestamp: float = field(default_factory=time.time)
    feedback_id: str = ""
    feedback_type: FeedbackType = FeedbackType.EXECUTION_RESULT
    content: Dict[str, Any] = field(default_factory=dict)
    quality_score: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    # Additional fields for test compatibility
    signature_id: str = ""
    parameters: Dict[str, Any] = field(default_factory=dict)
    performance_metrics: Any = None
    result_quality: float = 0.0

    def __post_init__(self):
        """Validate and process feedback entry."""
        # Auto-generate feedback_id if not provided
        if not self.feedback_id:
            self.feedback_id = f"feedback_{self.execution_id}_{int(self.timestamp)}"

        # Set quality_score from result_quality if provided
        if self.result_quality > 0:
            self.quality_score = self.result_quality

        # Process performance_metrics into content if provided
        if self.performance_metrics:
            if hasattr(self.performance_metrics, "to_dict"):
                metrics_dict = self.performance_metrics.to_dict()
            else:
                metrics_dict = self.performance_metrics

            self.content = {
                "parameters": self.parameters,
                "metrics": metrics_dict,
                "context": {"signature_id": self.signature_id},
            }

        # Validate quality score
        if not 0 <= self.quality_score <= 1:
            raise ValueError(f"Quality score must be 0-1, got {self.quality_score}")


@dataclass
class AnomalyReport:
    """Anomaly detection report."""

    anomaly_id: str
    execution_id: str
    timestamp: float
    anomaly_type: str
    severity: str  # low, medium, high, critical
    description: str
    detected_values: Dict[str, Any]
    suggested_corrections: Dict[str, Any]
    confidence: float
    metrics_affected: List[str] = field(default_factory=list)


@dataclass
class LearningUpdate:
    """Learning algorithm update."""

    update_id: str
    timestamp: float
    algorithm_type: str
    parameters_updated: Dict[str, Any]
    performance_improvement: float
    confidence: float
    metadata: Dict[str, Any] = field(default_factory=dict)


class QualityMetrics:
    """Quality metrics calculation and management."""

    def __init__(self):
        self.metric_weights = {
            QualityMetric.ACCURACY: 0.25,
            QualityMetric.RELEVANCE: 0.20,
            QualityMetric.COMPLETENESS: 0.15,
            QualityMetric.COHERENCE: 0.15,
            QualityMetric.EFFICIENCY: 0.15,
            QualityMetric.RELIABILITY: 0.10,
        }
        self.metric_calculators = {
            QualityMetric.ACCURACY: self._calculate_accuracy,
            QualityMetric.RELEVANCE: self._calculate_relevance,
            QualityMetric.COMPLETENESS: self._calculate_completeness,
            QualityMetric.COHERENCE: self._calculate_coherence,
            QualityMetric.EFFICIENCY: self._calculate_efficiency,
            QualityMetric.RELIABILITY: self._calculate_reliability,
        }

    async def calculate_quality_score(self, result: Any, context: Dict) -> float:
        """Calculate overall quality score for a result."""
        metric_scores = {}

        for metric, calculator in self.metric_calculators.items():
            try:
                score = await calculator(result, context)
                metric_scores[metric] = score
            except Exception as e:
                logger.warning(f"Error calculating {metric}: {e}")
                metric_scores[metric] = 0.5  # Default neutral score

        # Calculate weighted average
        total_score = 0.0
        total_weight = 0.0

        for metric, score in metric_scores.items():
            weight = self.metric_weights.get(metric, 0.1)
            total_score += score * weight
            total_weight += weight

        if total_weight > 0:
            overall_score = total_score / total_weight
        else:
            overall_score = 0.5

        return min(max(overall_score, 0.0), 1.0)

    async def _calculate_accuracy(self, result: Any, context: Dict) -> float:
        """Calculate accuracy metric."""
        # Check for explicit accuracy in context
        if "accuracy" in context:
            return float(context["accuracy"])

        # Check for ground truth comparison
        if "ground_truth" in context and result is not None:
            ground_truth = context["ground_truth"]
            try:
                # Simple string similarity for text results
                if isinstance(result, str) and isinstance(ground_truth, str):
                    return self._calculate_text_similarity(result, ground_truth)

                # Exact match for other types
                if result == ground_truth:
                    return 1.0
                else:
                    return 0.0

            except Exception as e:
                logger.warning(f"Error comparing result to ground truth: {e}")

        # Default heuristic based on result properties
        if result is None or result == "":
            return 0.0

        # For string results, check for completeness and coherence
        if isinstance(result, str):
            if len(result) < 10:
                return 0.3  # Very short results are likely incomplete
            elif len(result) > 10000:
                return 0.6  # Very long results might be verbose
            else:
                return 0.7  # Reasonable length

        return 0.6  # Default for other types

    async def _calculate_relevance(self, result: Any, context: Dict) -> float:
        """Calculate relevance metric."""
        if "query" in context and isinstance(result, str):
            query = str(context["query"]).lower()
            result_text = str(result).lower()

            # Simple keyword overlap
            query_words = set(query.split())
            result_words = set(result_text.split())

            if len(query_words) == 0:
                return 0.5

            overlap = len(query_words & result_words)
            relevance = overlap / len(query_words)

            return min(relevance * 1.5, 1.0)  # Boost relevance score

        # Check for topic/domain relevance
        if "expected_topics" in context and isinstance(result, str):
            topics = context["expected_topics"]
            result_text = str(result).lower()

            topic_matches = 0
            for topic in topics:
                if str(topic).lower() in result_text:
                    topic_matches += 1

            if len(topics) > 0:
                return topic_matches / len(topics)

        return 0.6  # Default relevance

    async def _calculate_completeness(self, result: Any, context: Dict) -> float:
        """Calculate completeness metric."""
        if result is None:
            return 0.0

        # Check for required elements
        if "required_elements" in context:
            required = context["required_elements"]
            result_text = str(result).lower()

            found_elements = 0
            for element in required:
                if str(element).lower() in result_text:
                    found_elements += 1

            return found_elements / len(required) if required else 1.0

        # Check minimum length requirements
        if "min_length" in context and isinstance(result, str):
            min_length = context["min_length"]
            if len(result) >= min_length:
                return 1.0
            else:
                return len(result) / min_length

        # Default completeness based on result size
        if isinstance(result, str):
            if len(result) < 50:
                return 0.4  # Likely incomplete
            elif len(result) > 200:
                return 0.9  # Likely complete
            else:
                return 0.7  # Reasonable completeness

        return 0.7  # Default

    async def _calculate_coherence(self, result: Any, context: Dict) -> float:
        """Calculate coherence metric."""
        if not isinstance(result, str):
            return 0.6  # Default for non-text

        result_text = result.strip()

        if len(result_text) == 0:
            return 0.0

        # Check for basic sentence structure
        sentences = result_text.split(".")
        if len(sentences) < 2:
            return 0.5  # Single sentence

        # Check for repeated patterns (might indicate incoherence)
        words = result_text.lower().split()
        if len(words) > 0:
            unique_words = len(set(words))
            repetition_ratio = unique_words / len(words)

            if repetition_ratio < 0.3:
                return 0.3  # High repetition
            elif repetition_ratio > 0.8:
                return 0.9  # Good variety
            else:
                return 0.6 + (repetition_ratio - 0.3) * 0.6  # Scaled

        return 0.6  # Default

    async def _calculate_efficiency(self, result: Any, context: Dict) -> float:
        """Calculate efficiency metric."""
        # Check execution time
        if "execution_time" in context:
            exec_time = context["execution_time"]

            # Define efficiency thresholds
            if exec_time < 1.0:
                return 1.0  # Very fast
            elif exec_time < 5.0:
                return 0.9  # Fast
            elif exec_time < 15.0:
                return 0.7  # Acceptable
            elif exec_time < 30.0:
                return 0.5  # Slow
            else:
                return 0.3  # Very slow

        # Check memory usage
        if "memory_usage" in context:
            memory_mb = context["memory_usage"] / (1024 * 1024)

            if memory_mb < 50:
                return 1.0  # Very efficient
            elif memory_mb < 200:
                return 0.8  # Efficient
            elif memory_mb < 500:
                return 0.6  # Acceptable
            else:
                return 0.4  # Inefficient

        return 0.7  # Default efficiency

    async def _calculate_reliability(self, result: Any, context: Dict) -> float:
        """Calculate reliability metric."""
        # Check for errors or exceptions
        if "error_count" in context:
            error_count = context["error_count"]
            if error_count == 0:
                return 1.0
            elif error_count <= 2:
                return 0.7
            else:
                return 0.3

        # Check for consistency with previous results
        if "previous_results" in context and len(context["previous_results"]) > 0:
            previous = context["previous_results"]
            if result in previous:
                return 0.9  # Consistent
            else:
                # Calculate similarity to previous results
                similarities = []
                for prev_result in previous[-5:]:  # Check last 5
                    if isinstance(result, str) and isinstance(prev_result, str):
                        sim = self._calculate_text_similarity(result, prev_result)
                        similarities.append(sim)

                if similarities:
                    avg_similarity = statistics.mean(similarities)
                    return 0.5 + avg_similarity * 0.4  # Scale to 0.5-0.9 range

        return 0.8  # Default reliability

    def _calculate_text_similarity(self, text1: str, text2: str) -> float:
        """Calculate similarity between two text strings."""
        if not text1 or not text2:
            return 0.0

        # Simple word-based similarity
        words1 = set(text1.lower().split())
        words2 = set(text2.lower().split())

        if len(words1) == 0 and len(words2) == 0:
            return 1.0

        intersection = len(words1 & words2)
        union = len(words1 | words2)

        if union == 0:
            return 0.0

        return intersection / union

    def update_metric_weights(self, new_weights: Dict[QualityMetric, float]) -> None:
        """Update metric weights for quality calculation."""
        # Normalize weights to sum to 1.0
        total_weight = sum(new_weights.values())
        if total_weight > 0:
            for metric, weight in new_weights.items():
                self.metric_weights[metric] = weight / total_weight

        logger.info(f"Updated quality metric weights: {self.metric_weights}")


class AnomalyDetector:
    """Detects anomalies in execution results and performance."""

    def __init__(self, config: Optional[Dict] = None):
        self.config = config or {}
        self.baseline_metrics = {}
        self.anomaly_thresholds = {
            "execution_time": 3.0,  # 3x normal time
            "memory_usage": 2.5,  # 2.5x normal memory
            "quality_score": 0.3,  # Drop of 0.3 points
            "error_rate": 0.1,  # Error rate > 10%
        }
        self.detection_history = deque(maxlen=1000)

    async def detect_anomalies(
        self, execution_id: str, result: Any, metrics: Dict, context: Dict
    ) -> List[AnomalyReport]:
        """Detect anomalies in execution results and metrics."""
        anomalies = []

        # Update baselines
        await self._update_baselines(metrics)

        # Performance anomalies
        perf_anomalies = await self._detect_performance_anomalies(execution_id, metrics)
        anomalies.extend(perf_anomalies)

        # Quality anomalies
        quality_anomalies = await self._detect_quality_anomalies(
            execution_id, result, metrics, context
        )
        anomalies.extend(quality_anomalies)

        # Pattern anomalies
        pattern_anomalies = await self._detect_pattern_anomalies(
            execution_id, result, metrics
        )
        anomalies.extend(pattern_anomalies)

        # Store detection results
        self.detection_history.append(
            {
                "timestamp": time.time(),
                "execution_id": execution_id,
                "anomalies_detected": len(anomalies),
                "anomaly_types": [a.anomaly_type for a in anomalies],
            }
        )

        return anomalies

    async def _update_baselines(self, metrics: Dict) -> None:
        """Update baseline metrics for anomaly detection."""
        for metric_name, value in metrics.items():
            if isinstance(value, (int, float)):
                if metric_name not in self.baseline_metrics:
                    self.baseline_metrics[metric_name] = []

                # Keep rolling window of recent values
                self.baseline_metrics[metric_name].append(value)
                if len(self.baseline_metrics[metric_name]) > 100:
                    self.baseline_metrics[metric_name] = self.baseline_metrics[
                        metric_name
                    ][-100:]

    async def _detect_performance_anomalies(
        self, execution_id: str, metrics: Dict
    ) -> List[AnomalyReport]:
        """Detect performance-related anomalies."""
        anomalies = []

        for metric_name, threshold in self.anomaly_thresholds.items():
            if metric_name in metrics and metric_name in self.baseline_metrics:
                current_value = metrics[metric_name]
                baseline_values = self.baseline_metrics[metric_name]

                if len(baseline_values) >= 10:  # Need enough data
                    baseline_mean = statistics.mean(baseline_values)
                    baseline_std = statistics.stdev(baseline_values)

                    # Z-score based anomaly detection
                    if baseline_std > 0:
                        z_score = abs(current_value - baseline_mean) / baseline_std

                        if z_score > threshold:
                            severity = self._calculate_anomaly_severity(
                                z_score, threshold
                            )

                            anomaly = AnomalyReport(
                                anomaly_id=f"perf_{execution_id}_{metric_name}_{int(time.time())}",
                                execution_id=execution_id,
                                timestamp=time.time(),
                                anomaly_type=f"performance_{metric_name}",
                                severity=severity,
                                description=f"{metric_name} is {z_score:.1f} standard deviations from baseline",
                                detected_values={
                                    metric_name: current_value,
                                    "z_score": z_score,
                                    "baseline_mean": baseline_mean,
                                    "baseline_std": baseline_std,
                                },
                                suggested_corrections=await self._suggest_performance_corrections(
                                    metric_name, current_value, baseline_mean
                                ),
                                confidence=min(0.9, z_score / (threshold * 2)),
                            )
                            anomalies.append(anomaly)

        return anomalies

    async def _detect_quality_anomalies(
        self, execution_id: str, result: Any, metrics: Dict, context: Dict
    ) -> List[AnomalyReport]:
        """Detect quality-related anomalies."""
        anomalies = []

        # Check for sudden quality drops
        if "quality_score" in metrics:
            current_quality = metrics["quality_score"]

            # Compare with recent quality scores
            if "quality_score" in self.baseline_metrics:
                recent_scores = self.baseline_metrics["quality_score"][
                    -20:
                ]  # Recent 20
                if len(recent_scores) >= 5:
                    recent_mean = statistics.mean(recent_scores)

                    quality_drop = recent_mean - current_quality

                    if quality_drop > self.anomaly_thresholds["quality_score"]:
                        anomaly = AnomalyReport(
                            anomaly_id=f"quality_{execution_id}_{int(time.time())}",
                            execution_id=execution_id,
                            timestamp=time.time(),
                            anomaly_type="quality_degradation",
                            severity=self._calculate_quality_severity(quality_drop),
                            description=f"Quality score dropped by {quality_drop:.2f} from recent average",
                            detected_values={
                                "current_quality": current_quality,
                                "recent_average": recent_mean,
                                "quality_drop": quality_drop,
                            },
                            suggested_corrections=await self._suggest_quality_corrections(
                                current_quality, recent_mean, context
                            ),
                            confidence=min(0.8, quality_drop * 2),
                        )
                        anomalies.append(anomaly)

        # Check for result format anomalies
        if result is not None:
            format_anomaly = await self._detect_format_anomaly(execution_id, result)
            if format_anomaly:
                anomalies.append(format_anomaly)

        return anomalies

    async def _detect_pattern_anomalies(
        self, execution_id: str, result: Any, metrics: Dict
    ) -> List[AnomalyReport]:
        """Detect pattern-based anomalies."""
        anomalies = []

        # Detect repeating failures
        recent_history = list(self.detection_history)[-20:]  # Recent 20 executions
        if len(recent_history) >= 10:
            # Check for high anomaly rate
            anomaly_counts = [h["anomalies_detected"] for h in recent_history]
            avg_anomalies = statistics.mean(anomaly_counts)

            if avg_anomalies > 2.0:  # More than 2 anomalies per execution on average
                anomaly = AnomalyReport(
                    anomaly_id=f"pattern_{execution_id}_{int(time.time())}",
                    execution_id=execution_id,
                    timestamp=time.time(),
                    anomaly_type="high_anomaly_rate",
                    severity="high",
                    description=f"High anomaly rate detected: {avg_anomalies:.1f} per execution",
                    detected_values={
                        "average_anomalies": avg_anomalies,
                        "recent_executions": len(recent_history),
                    },
                    suggested_corrections={
                        "action": "system_review",
                        "recommendations": [
                            "Review system configuration",
                            "Check for external factors",
                            "Consider resetting optimization parameters",
                        ],
                    },
                    confidence=0.7,
                )
                anomalies.append(anomaly)

        return anomalies

    async def _detect_format_anomaly(
        self, execution_id: str, result: Any
    ) -> Optional[AnomalyReport]:
        """Detect anomalies in result format or content."""
        if isinstance(result, str):
            # Check for suspicious patterns
            if result.count("\n") > 1000:  # Too many line breaks
                return AnomalyReport(
                    anomaly_id=f"format_{execution_id}_{int(time.time())}",
                    execution_id=execution_id,
                    timestamp=time.time(),
                    anomaly_type="format_anomaly",
                    severity="medium",
                    description="Result contains excessive line breaks",
                    detected_values={"line_breaks": result.count("\n")},
                    suggested_corrections={"action": "content_filtering"},
                    confidence=0.6,
                )

            # Check for repetitive content
            words = result.split()
            if len(words) > 10:
                unique_words = len(set(words))
                repetition_ratio = unique_words / len(words)

                if repetition_ratio < 0.2:  # High repetition
                    return AnomalyReport(
                        anomaly_id=f"repetition_{execution_id}_{int(time.time())}",
                        execution_id=execution_id,
                        timestamp=time.time(),
                        anomaly_type="content_repetition",
                        severity="medium",
                        description="Result contains highly repetitive content",
                        detected_values={"repetition_ratio": repetition_ratio},
                        suggested_corrections={"action": "parameter_adjustment"},
                        confidence=0.7,
                    )

        return None

    def _calculate_anomaly_severity(self, z_score: float, threshold: float) -> str:
        """Calculate severity based on z-score and threshold."""
        if z_score > threshold * 3:
            return "critical"
        elif z_score > threshold * 2:
            return "high"
        elif z_score > threshold * 1.5:
            return "medium"
        else:
            return "low"

    def _calculate_quality_severity(self, quality_drop: float) -> str:
        """Calculate severity based on quality drop."""
        if quality_drop > 0.5:
            return "critical"
        elif quality_drop > 0.4:
            return "high"
        elif quality_drop > 0.3:
            return "medium"
        else:
            return "low"

    async def _suggest_performance_corrections(
        self, metric_name: str, current_value: float, baseline: float
    ) -> Dict[str, Any]:
        """Suggest corrections for performance anomalies."""
        corrections = {
            "metric": metric_name,
            "current_value": current_value,
            "baseline": baseline,
        }

        if metric_name == "execution_time":
            if current_value > baseline * 2:
                corrections["recommendations"] = [
                    "Reduce model complexity",
                    "Optimize input preprocessing",
                    "Check for resource contention",
                    "Consider timeout adjustments",
                ]
        elif metric_name == "memory_usage":
            if current_value > baseline * 2:
                corrections["recommendations"] = [
                    "Reduce batch size",
                    "Implement memory optimization",
                    "Check for memory leaks",
                    "Consider streaming processing",
                ]

        return corrections

    async def _suggest_quality_corrections(
        self, current_quality: float, recent_average: float, context: Dict
    ) -> Dict[str, Any]:
        """Suggest corrections for quality anomalies."""
        return {
            "current_quality": current_quality,
            "recent_average": recent_average,
            "recommendations": [
                "Review input parameters",
                "Check for data quality issues",
                "Consider model retraining",
                "Validate optimization settings",
            ],
        }


class LearningEngine:
    """Learning engine that adapts based on feedback."""

    def __init__(self, config: Optional[Dict] = None):
        self.config = config or {}
        self.learning_rate = self.config.get("learning_rate", 0.1)
        self.adaptation_threshold = self.config.get("adaptation_threshold", 0.05)
        self.learning_history = deque(maxlen=1000)
        self.parameter_adjustments = defaultdict(list)

    async def learn_from_feedback(
        self, feedback_entries: List[FeedbackEntry]
    ) -> List[LearningUpdate]:
        """Learn from feedback and generate parameter updates."""
        if not feedback_entries:
            return []

        updates = []

        # Analyze feedback patterns
        patterns = await self._analyze_feedback_patterns(feedback_entries)

        # Generate parameter updates based on patterns
        for pattern in patterns:
            update = await self._generate_parameter_update(pattern)
            if update:
                updates.append(update)

        # Apply learning updates
        for update in updates:
            await self._apply_learning_update(update)

        return updates

    async def _analyze_feedback_patterns(
        self, feedback_entries: List[FeedbackEntry]
    ) -> List[Dict]:
        """Analyze patterns in feedback entries."""
        patterns = []

        # Group feedback by type
        feedback_by_type = defaultdict(list)
        for entry in feedback_entries:
            feedback_by_type[entry.feedback_type].append(entry)

        # Analyze quality score trends
        quality_scores = [entry.quality_score for entry in feedback_entries]
        if len(quality_scores) >= 5:
            trend = await self._analyze_quality_trend(quality_scores)
            if trend:
                patterns.append(trend)

        # Analyze parameter correlations
        param_patterns = await self._analyze_parameter_feedback_correlations(
            feedback_entries
        )
        patterns.extend(param_patterns)

        # Analyze temporal patterns
        temporal_patterns = await self._analyze_temporal_feedback_patterns(
            feedback_entries
        )
        patterns.extend(temporal_patterns)

        return patterns

    async def _analyze_quality_trend(
        self, quality_scores: List[float]
    ) -> Optional[Dict]:
        """Analyze quality score trends."""
        if len(quality_scores) < 5:
            return None

        # Simple linear trend analysis
        x = list(range(len(quality_scores)))
        slope = np.polyfit(x, quality_scores, 1)[0]

        if abs(slope) > self.adaptation_threshold:
            return {
                "pattern_type": "quality_trend",
                "trend_slope": slope,
                "trend_direction": "improving" if slope > 0 else "declining",
                "magnitude": abs(slope),
                "sample_size": len(quality_scores),
                "adaptation_needed": True,
            }

        return None

    async def _analyze_parameter_feedback_correlations(
        self, feedback_entries: List[FeedbackEntry]
    ) -> List[Dict]:
        """Analyze correlations between parameters and feedback quality."""
        patterns = []

        # Extract parameter-quality pairs
        param_quality_pairs = defaultdict(list)

        for entry in feedback_entries:
            if "parameters" in entry.content:
                params = entry.content["parameters"]
                for param_name, param_value in params.items():
                    try:
                        float_value = float(param_value)
                        param_quality_pairs[param_name].append(
                            {
                                "value": float_value,
                                "quality": entry.quality_score,
                                "timestamp": entry.timestamp,
                            }
                        )
                    except (ValueError, TypeError):
                        continue

        # Analyze correlations
        for param_name, pairs in param_quality_pairs.items():
            if len(pairs) >= 10:
                correlation = await self._calculate_parameter_correlation(pairs)
                if correlation and abs(correlation["strength"]) > 0.3:
                    patterns.append(
                        {
                            "pattern_type": "parameter_correlation",
                            "parameter_name": param_name,
                            "correlation_strength": correlation["strength"],
                            "sample_size": len(pairs),
                            "adaptation_needed": True,
                            "suggested_direction": (
                                "increase"
                                if correlation["strength"] > 0
                                else "decrease"
                            ),
                        }
                    )

        return patterns

    async def _calculate_parameter_correlation(
        self, pairs: List[Dict]
    ) -> Optional[Dict]:
        """Calculate correlation between parameter values and quality scores."""
        values = [pair["value"] for pair in pairs]
        qualities = [pair["quality"] for pair in pairs]

        try:
            correlation = np.corrcoef(values, qualities)[0, 1]
            if not np.isnan(correlation):
                return {
                    "strength": correlation,
                    "value_range": (min(values), max(values)),
                    "quality_range": (min(qualities), max(qualities)),
                }
        except Exception as e:
            logger.warning(f"Error calculating correlation: {e}")

        return None

    async def _analyze_temporal_feedback_patterns(
        self, feedback_entries: List[FeedbackEntry]
    ) -> List[Dict]:
        """Analyze temporal patterns in feedback."""
        patterns = []

        # Sort by timestamp
        sorted_entries = sorted(feedback_entries, key=lambda x: x.timestamp)

        # Analyze quality evolution over time windows
        window_size = max(5, len(sorted_entries) // 5)
        if window_size >= 5 and len(sorted_entries) >= window_size * 2:
            windows = []
            for i in range(0, len(sorted_entries) - window_size + 1, window_size // 2):
                window = sorted_entries[i : i + window_size]
                avg_quality = statistics.mean([entry.quality_score for entry in window])
                windows.append(avg_quality)

            if len(windows) >= 3:
                # Check for trend
                trend_slope = np.polyfit(range(len(windows)), windows, 1)[0]

                if abs(trend_slope) > self.adaptation_threshold:
                    patterns.append(
                        {
                            "pattern_type": "temporal_trend",
                            "trend_slope": trend_slope,
                            "window_count": len(windows),
                            "adaptation_needed": True,
                            "urgency": "high" if abs(trend_slope) > 0.1 else "medium",
                        }
                    )

        return patterns

    async def _generate_parameter_update(
        self, pattern: Dict
    ) -> Optional[LearningUpdate]:
        """Generate parameter update based on identified pattern."""
        if not pattern.get("adaptation_needed", False):
            return None

        update_id = f"learn_{int(time.time())}_{pattern['pattern_type']}"

        if pattern["pattern_type"] == "quality_trend":
            return await self._generate_trend_update(update_id, pattern)
        elif pattern["pattern_type"] == "parameter_correlation":
            return await self._generate_correlation_update(update_id, pattern)
        elif pattern["pattern_type"] == "temporal_trend":
            return await self._generate_temporal_update(update_id, pattern)

        return None

    async def _generate_trend_update(
        self, update_id: str, pattern: Dict
    ) -> LearningUpdate:
        """Generate update based on quality trend."""
        trend_direction = pattern["trend_direction"]
        magnitude = pattern["magnitude"]

        # Adjust learning parameters based on trend
        if trend_direction == "declining":
            # Increase exploration to find better parameters
            parameters_updated = {
                "exploration_rate": min(0.3, 0.1 + magnitude),
                "learning_rate": min(0.2, self.learning_rate * 1.2),
                "adaptation_threshold": max(0.01, self.adaptation_threshold * 0.8),
            }
            performance_improvement = magnitude * 0.5  # Potential improvement
        else:
            # Reduce exploration to maintain good performance
            parameters_updated = {
                "exploration_rate": max(0.05, 0.1 - magnitude * 0.5),
                "learning_rate": max(0.01, self.learning_rate * 0.9),
                "adaptation_threshold": min(0.1, self.adaptation_threshold * 1.1),
            }
            performance_improvement = magnitude * 0.3  # Smaller improvement expected

        return LearningUpdate(
            update_id=update_id,
            timestamp=time.time(),
            algorithm_type="trend_adaptation",
            parameters_updated=parameters_updated,
            performance_improvement=performance_improvement,
            confidence=min(0.8, pattern["sample_size"] / 20.0),
            metadata=pattern,
        )

    async def _generate_correlation_update(
        self, update_id: str, pattern: Dict
    ) -> LearningUpdate:
        """Generate update based on parameter correlation."""
        param_name = pattern["parameter_name"]
        correlation_strength = pattern["correlation_strength"]
        suggested_direction = pattern["suggested_direction"]

        # Calculate adjustment magnitude
        adjustment_magnitude = (
            abs(correlation_strength) * 0.1
        )  # 10% of correlation strength

        parameters_updated = {
            f"{param_name}_adjustment_direction": suggested_direction,
            f"{param_name}_adjustment_magnitude": adjustment_magnitude,
            f"{param_name}_correlation_strength": correlation_strength,
        }

        performance_improvement = abs(correlation_strength) * 0.4

        return LearningUpdate(
            update_id=update_id,
            timestamp=time.time(),
            algorithm_type="correlation_adaptation",
            parameters_updated=parameters_updated,
            performance_improvement=performance_improvement,
            confidence=min(0.9, pattern["sample_size"] / 30.0),
            metadata=pattern,
        )

    async def _generate_temporal_update(
        self, update_id: str, pattern: Dict
    ) -> LearningUpdate:
        """Generate update based on temporal patterns."""
        trend_slope = pattern["trend_slope"]
        urgency = pattern.get("urgency", "medium")

        # Adjust adaptation speed based on urgency
        if urgency == "high":
            adaptation_speed = 1.5
        elif urgency == "medium":
            adaptation_speed = 1.0
        else:
            adaptation_speed = 0.7

        parameters_updated = {
            "adaptation_speed": adaptation_speed,
            "temporal_trend_slope": trend_slope,
            "monitoring_frequency": "increased" if abs(trend_slope) > 0.1 else "normal",
        }

        performance_improvement = abs(trend_slope) * 0.6

        return LearningUpdate(
            update_id=update_id,
            timestamp=time.time(),
            algorithm_type="temporal_adaptation",
            parameters_updated=parameters_updated,
            performance_improvement=performance_improvement,
            confidence=0.7,
            metadata=pattern,
        )

    async def _apply_learning_update(self, update: LearningUpdate) -> None:
        """Apply learning update to the system."""
        # Store learning update
        self.learning_history.append(
            {
                "timestamp": update.timestamp,
                "update_id": update.update_id,
                "algorithm_type": update.algorithm_type,
                "performance_improvement": update.performance_improvement,
                "confidence": update.confidence,
            }
        )

        # Update internal parameters
        for param_name, param_value in update.parameters_updated.items():
            if param_name == "learning_rate":
                self.learning_rate = param_value
            elif param_name == "adaptation_threshold":
                self.adaptation_threshold = param_value

        # Record parameter adjustments
        self.parameter_adjustments[update.algorithm_type].append(update)

        logger.info(
            f"Applied learning update {update.update_id}: "
            f"{update.algorithm_type} with {update.confidence:.2f} confidence"
        )


class FeedbackSystem:
    """Main feedback system coordinating all feedback components."""

    def __init__(self, memory_system=None, config: Optional[Dict] = None):
        self.memory = memory_system
        self.config = config or {}
        self.quality_metrics = QualityMetrics()
        self.anomaly_detector = AnomalyDetector(
            self.config.get("anomaly_detection", {})
        )
        self.learning_engine = LearningEngine(self.config.get("learning", {}))
        self.feedback_buffer = deque(maxlen=10000)
        self.processing_queue = asyncio.Queue()

    async def collect_feedback(
        self,
        execution_id: str,
        result: Any,
        metrics: Dict,
        context: Optional[Dict] = None,
    ) -> FeedbackEntry:
        """Collect feedback from execution."""
        context = context or {}

        # Calculate quality score
        quality_score = await self.quality_metrics.calculate_quality_score(
            result, context
        )

        # Create feedback entry
        feedback_entry = FeedbackEntry(
            feedback_id=f"feedback_{execution_id}_{int(time.time())}",
            execution_id=execution_id,
            timestamp=time.time(),
            feedback_type=FeedbackType.EXECUTION_RESULT,
            content={
                "result": result,
                "metrics": metrics,
                "context": context,
                "parameters": context.get("parameters", {}),
            },
            quality_score=quality_score,
            metadata={
                "result_type": type(result).__name__,
                "metrics_count": len(metrics),
                "context_keys": list(context.keys()),
            },
        )

        # Store feedback
        self.feedback_buffer.append(feedback_entry)

        # Store in memory system if available
        if self.memory:
            await self.memory.put(
                f"feedback:{feedback_entry.feedback_id}",
                {
                    "feedback_entry": feedback_entry,
                    "timestamp": feedback_entry.timestamp,
                },
                tier_hint="warm",
            )

        # Queue for processing
        await self.processing_queue.put(feedback_entry)

        return feedback_entry

    async def process_feedback_batch(self, batch_size: int = 10) -> Dict[str, Any]:
        """Process a batch of feedback entries."""
        batch = []

        # Collect batch
        for _ in range(batch_size):
            try:
                feedback_entry = await asyncio.wait_for(
                    self.processing_queue.get(), timeout=0.1
                )
                batch.append(feedback_entry)
            except asyncio.TimeoutError:
                break

        if not batch:
            return {"processed": 0}

        # Process batch
        results = {
            "processed": len(batch),
            "anomalies": [],
            "learning_updates": [],
            "quality_stats": {},
        }

        # Detect anomalies for each entry
        for entry in batch:
            anomalies = await self.anomaly_detector.detect_anomalies(
                entry.execution_id,
                entry.content["result"],
                entry.content["metrics"],
                entry.content["context"],
            )
            results["anomalies"].extend(anomalies)

        # Learning from batch
        learning_updates = await self.learning_engine.learn_from_feedback(batch)
        results["learning_updates"] = learning_updates

        # Calculate quality statistics
        quality_scores = [entry.quality_score for entry in batch]
        results["quality_stats"] = {
            "mean": statistics.mean(quality_scores),
            "median": statistics.median(quality_scores),
            "std": statistics.stdev(quality_scores) if len(quality_scores) > 1 else 0,
            "min": min(quality_scores),
            "max": max(quality_scores),
        }

        return results

    async def get_feedback_analytics(self, window_hours: int = 24) -> Dict[str, Any]:
        """Get analytics on recent feedback."""
        cutoff_time = time.time() - (window_hours * 3600)

        # Filter recent feedback
        recent_feedback = [
            entry for entry in self.feedback_buffer if entry.timestamp >= cutoff_time
        ]

        if not recent_feedback:
            return {"message": "No recent feedback available"}

        # Calculate analytics
        quality_scores = [entry.quality_score for entry in recent_feedback]
        analytics = {
            "feedback_count": len(recent_feedback),
            "time_window_hours": window_hours,
            "quality_analytics": {
                "mean": statistics.mean(quality_scores),
                "median": statistics.median(quality_scores),
                "std": (
                    statistics.stdev(quality_scores) if len(quality_scores) > 1 else 0
                ),
                "percentiles": {
                    "25th": np.percentile(quality_scores, 25),
                    "75th": np.percentile(quality_scores, 75),
                    "95th": np.percentile(quality_scores, 95),
                },
            },
            "feedback_types": {},
            "execution_analytics": {},
        }

        # Feedback type distribution
        type_counts = defaultdict(int)
        for entry in recent_feedback:
            type_counts[entry.feedback_type.value] += 1
        analytics["feedback_types"] = dict(type_counts)

        # Recent anomalies
        recent_anomaly_count = len(
            [
                entry
                for history_entry in self.anomaly_detector.detection_history
                if history_entry["timestamp"] >= cutoff_time
            ]
        )
        analytics["anomaly_count"] = recent_anomaly_count

        # Learning progress
        recent_learning_updates = len(
            [
                update
                for update in self.learning_engine.learning_history
                if update["timestamp"] >= cutoff_time
            ]
        )
        analytics["learning_updates_count"] = recent_learning_updates

        return analytics

    async def get_recommendations(self) -> List[Dict[str, Any]]:
        """Get optimization recommendations based on feedback analysis."""
        recommendations = []

        # Analyze recent feedback
        recent_feedback = list(self.feedback_buffer)[-100:]  # Recent 100

        if len(recent_feedback) < 10:
            return [
                {
                    "type": "insufficient_data",
                    "description": "Insufficient feedback data for recommendations",
                    "action": "collect_more_data",
                }
            ]

        # Quality-based recommendations
        quality_scores = [entry.quality_score for entry in recent_feedback]
        avg_quality = statistics.mean(quality_scores)

        if avg_quality < 0.6:
            recommendations.append(
                {
                    "type": "quality_improvement",
                    "description": f"Average quality score is low: {avg_quality:.2f}",
                    "priority": "high",
                    "suggested_actions": [
                        "Review parameter settings",
                        "Analyze low-scoring executions",
                        "Consider model retraining",
                    ],
                }
            )

        # Anomaly-based recommendations
        recent_anomalies = len(
            [
                h
                for h in self.anomaly_detector.detection_history
                if h["timestamp"] > time.time() - 3600  # Last hour
            ]
        )

        if recent_anomalies > 5:
            recommendations.append(
                {
                    "type": "anomaly_investigation",
                    "description": f"High anomaly rate: {recent_anomalies} in last hour",
                    "priority": "high",
                    "suggested_actions": [
                        "Investigate system stability",
                        "Check for external factors",
                        "Review recent configuration changes",
                    ],
                }
            )

        # Learning-based recommendations
        if len(self.learning_engine.learning_history) > 0:
            recent_improvements = [
                update["performance_improvement"]
                for update in list(self.learning_engine.learning_history)[-10:]
            ]
            avg_improvement = statistics.mean(recent_improvements)

            if avg_improvement < 0.1:
                recommendations.append(
                    {
                        "type": "learning_optimization",
                        "description": f"Low learning improvement rate: {avg_improvement:.3f}",
                        "priority": "medium",
                        "suggested_actions": [
                            "Increase exploration rate",
                            "Expand parameter search space",
                            "Consider alternative optimization strategies",
                        ],
                    }
                )

        return recommendations
