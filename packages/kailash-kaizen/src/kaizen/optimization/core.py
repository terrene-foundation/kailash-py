"""
Core optimization engine for Kaizen auto-optimization system.

This module implements the core optimization algorithms including:
- OptimizationEngine interface
- Performance pattern analyzer
- Parameter adjustment algorithms
- Optimization strategy registry
"""

import logging
import time
from abc import ABC, abstractmethod
from collections import defaultdict, deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)


class OptimizationStrategy(Enum):
    """Available optimization strategies."""

    BAYESIAN = "bayesian"
    GENETIC = "genetic"
    GRADIENT = "gradient"
    RANDOM_SEARCH = "random_search"
    GRID_SEARCH = "grid_search"


@dataclass
class PerformanceMetrics:
    """Performance metrics for optimization tracking."""

    execution_time: float
    memory_usage: float
    accuracy: float
    quality_score: float
    resource_efficiency: float = 1.0
    timestamp: float = field(default_factory=time.time)
    success_rate: float = 1.0

    def __post_init__(self):
        """Validate metrics are within expected ranges."""
        if not 0 <= self.accuracy <= 1:
            raise ValueError(f"Accuracy must be 0-1, got {self.accuracy}")
        if not 0 <= self.quality_score <= 1:
            raise ValueError(f"Quality score must be 0-1, got {self.quality_score}")
        if not 0 <= self.resource_efficiency <= 1:
            raise ValueError(
                f"Resource efficiency must be 0-1, got {self.resource_efficiency}"
            )
        if not 0 <= self.success_rate <= 1:
            raise ValueError(f"Success rate must be 0-1, got {self.success_rate}")

    def to_dict(self) -> Dict[str, float]:
        """Convert metrics to dictionary."""
        return {
            "execution_time": self.execution_time,
            "memory_usage": self.memory_usage,
            "accuracy": self.accuracy,
            "quality_score": self.quality_score,
            "resource_efficiency": self.resource_efficiency,
            "timestamp": self.timestamp,
            "success_rate": self.success_rate,
        }


@dataclass
class OptimizationResult:
    """Result of an optimization operation."""

    optimized_params: Dict[str, Any]
    expected_improvement: float
    confidence: float
    strategy_used: OptimizationStrategy
    optimization_time: float
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ImprovementResult:
    """Result of improvement calculation between baseline and optimized metrics."""

    execution_time_improvement: float
    memory_improvement: float
    quality_improvement: float
    accuracy_improvement: float
    success_rate_improvement: float
    overall_improvement: float


@dataclass
class PerformancePattern:
    """Identified performance pattern."""

    pattern_type: str
    parameters: List[str]
    correlation_strength: float
    improvement_potential: float
    confidence: float
    examples: List[Dict] = field(default_factory=list)


class OptimizationEngineInterface(ABC):
    """Abstract interface for optimization engines."""

    @abstractmethod
    async def optimize(
        self,
        current_params: Dict,
        history: List[Dict],
        target_metric: str = "quality_score",
    ) -> OptimizationResult:
        """Optimize parameters based on history."""
        pass

    @abstractmethod
    async def analyze_patterns(self, history: List[Dict]) -> List[PerformancePattern]:
        """Analyze performance patterns in execution history."""
        pass

    @abstractmethod
    def update_strategy(self, feedback: Dict) -> None:
        """Update optimization strategy based on feedback."""
        pass


class PerformancePatternAnalyzer:
    """Analyzes execution patterns to identify optimization opportunities."""

    def __init__(self, window_size: int = 100, min_correlation: float = 0.3):
        self.window_size = window_size
        self.min_correlation = min_correlation
        self.pattern_cache = {}

    async def analyze_execution_patterns(
        self, history: List[Dict]
    ) -> List[PerformancePattern]:
        """Analyze execution history for performance patterns."""
        if len(history) < 10:
            logger.warning(
                f"Insufficient history for pattern analysis: {len(history)} entries"
            )
            return []

        patterns = []

        # Analyze parameter correlations
        param_patterns = await self._analyze_parameter_correlations(history)
        patterns.extend(param_patterns)

        # Analyze temporal patterns
        temporal_patterns = await self._analyze_temporal_patterns(history)
        patterns.extend(temporal_patterns)

        # Analyze resource usage patterns
        resource_patterns = await self._analyze_resource_patterns(history)
        patterns.extend(resource_patterns)

        return patterns

    async def _analyze_parameter_correlations(
        self, history: List[Dict]
    ) -> List[PerformancePattern]:
        """Analyze correlations between parameters and performance."""
        patterns = []

        # Extract parameter values and metrics
        param_names = set()
        for entry in history:
            if "params" in entry:
                param_names.update(entry["params"].keys())

        for param_name in param_names:
            correlation = await self._calculate_parameter_correlation(
                history, param_name
            )

            if abs(correlation["strength"]) >= self.min_correlation:
                pattern = PerformancePattern(
                    pattern_type="parameter_correlation",
                    parameters=[param_name],
                    correlation_strength=abs(correlation["strength"]),
                    improvement_potential=self._estimate_improvement_potential(
                        correlation
                    ),
                    confidence=self._calculate_confidence(correlation, len(history)),
                    examples=correlation["examples"][:5],  # Top 5 examples
                )
                patterns.append(pattern)

        return patterns

    async def _calculate_parameter_correlation(
        self, history: List[Dict], param_name: str
    ) -> Dict:
        """Calculate correlation between parameter and performance metrics."""
        param_values = []
        quality_scores = []
        examples = []

        for entry in history:
            if (
                "params" in entry
                and param_name in entry["params"]
                and "quality_score" in entry
            ):
                param_value = entry["params"][param_name]
                quality_score = entry["quality_score"]

                # Convert to numeric if possible
                try:
                    param_value = float(param_value)
                    param_values.append(param_value)
                    quality_scores.append(quality_score)
                    examples.append(
                        {
                            "param_value": param_value,
                            "quality_score": quality_score,
                            "timestamp": entry.get("timestamp", 0),
                        }
                    )
                except (ValueError, TypeError):
                    continue

        if len(param_values) < 5:
            return {"strength": 0, "examples": []}

        # Calculate correlation coefficient
        correlation = np.corrcoef(param_values, quality_scores)[0, 1]
        if np.isnan(correlation):
            correlation = 0

        # Sort examples by quality score for analysis
        examples.sort(key=lambda x: x["quality_score"], reverse=True)

        return {
            "strength": correlation,
            "examples": examples,
            "param_range": (min(param_values), max(param_values)),
            "quality_range": (min(quality_scores), max(quality_scores)),
        }

    async def _analyze_temporal_patterns(
        self, history: List[Dict]
    ) -> List[PerformancePattern]:
        """Analyze temporal patterns in performance."""
        patterns = []

        # Sort history by timestamp
        sorted_history = sorted(history, key=lambda x: x.get("timestamp", 0))

        # Analyze trends over time
        window_size = min(20, len(sorted_history) // 5)
        if window_size < 5:
            return patterns

        quality_trends = []
        for i in range(0, len(sorted_history) - window_size + 1, window_size // 2):
            window = sorted_history[i : i + window_size]
            avg_quality = np.mean([entry.get("quality_score", 0) for entry in window])
            quality_trends.append(avg_quality)

        if len(quality_trends) >= 3:
            # Check for declining trend
            trend_slope = np.polyfit(range(len(quality_trends)), quality_trends, 1)[0]

            if trend_slope < -0.05:  # Significant decline
                pattern = PerformancePattern(
                    pattern_type="declining_performance",
                    parameters=["temporal"],
                    correlation_strength=abs(trend_slope),
                    improvement_potential=0.3,  # Estimate 30% improvement potential
                    confidence=0.7,
                    examples=[
                        {"trend_slope": trend_slope, "quality_trends": quality_trends}
                    ],
                )
                patterns.append(pattern)

        return patterns

    async def _analyze_resource_patterns(
        self, history: List[Dict]
    ) -> List[PerformancePattern]:
        """Analyze resource usage patterns."""
        patterns = []

        # Analyze memory usage vs quality
        memory_usage = []
        quality_scores = []

        for entry in history:
            if "memory_usage" in entry and "quality_score" in entry:
                memory_usage.append(entry["memory_usage"])
                quality_scores.append(entry["quality_score"])

        if len(memory_usage) >= 10:
            correlation = np.corrcoef(memory_usage, quality_scores)[0, 1]
            if not np.isnan(correlation) and abs(correlation) >= self.min_correlation:
                pattern = PerformancePattern(
                    pattern_type="memory_efficiency",
                    parameters=["memory_usage"],
                    correlation_strength=abs(correlation),
                    improvement_potential=0.2,
                    confidence=0.6,
                    examples=[
                        {
                            "correlation": correlation,
                            "avg_memory": np.mean(memory_usage),
                            "avg_quality": np.mean(quality_scores),
                        }
                    ],
                )
                patterns.append(pattern)

        return patterns

    def _estimate_improvement_potential(self, correlation: Dict) -> float:
        """Estimate improvement potential based on correlation analysis."""
        strength = abs(correlation["strength"])

        # Higher correlation suggests more improvement potential
        if strength > 0.7:
            return 0.4  # Up to 40% improvement
        elif strength > 0.5:
            return 0.3  # Up to 30% improvement
        elif strength > 0.3:
            return 0.2  # Up to 20% improvement
        else:
            return 0.1  # Up to 10% improvement

    def _calculate_confidence(self, correlation: Dict, sample_size: int) -> float:
        """Calculate confidence in correlation based on strength and sample size."""
        strength = abs(correlation["strength"])

        # Base confidence from correlation strength
        base_confidence = min(strength, 0.8)

        # Adjust for sample size
        if sample_size >= 100:
            size_factor = 1.0
        elif sample_size >= 50:
            size_factor = 0.9
        elif sample_size >= 20:
            size_factor = 0.8
        else:
            size_factor = 0.6

        return base_confidence * size_factor


class ParameterAdjustmentEngine:
    """Engine for adjusting parameters based on optimization strategies."""

    def __init__(self):
        self.adjustment_history = deque(maxlen=1000)

    async def adjust_parameters(
        self,
        current_params: Dict,
        patterns: List[PerformancePattern],
        strategy: OptimizationStrategy = OptimizationStrategy.BAYESIAN,
    ) -> Dict:
        """Adjust parameters based on identified patterns."""

        if not patterns:
            logger.warning("No patterns provided for parameter adjustment")
            return current_params.copy()

        adjusted_params = current_params.copy()

        for pattern in patterns:
            if pattern.pattern_type == "parameter_correlation":
                adjusted_params = await self._adjust_correlated_parameters(
                    adjusted_params, pattern, strategy
                )
            elif pattern.pattern_type == "memory_efficiency":
                adjusted_params = await self._adjust_memory_parameters(
                    adjusted_params, pattern
                )

        # Record adjustment
        self.adjustment_history.append(
            {
                "timestamp": time.time(),
                "original_params": current_params,
                "adjusted_params": adjusted_params,
                "patterns_used": [p.pattern_type for p in patterns],
                "strategy": strategy,
            }
        )

        return adjusted_params

    async def _adjust_correlated_parameters(
        self, params: Dict, pattern: PerformancePattern, strategy: OptimizationStrategy
    ) -> Dict:
        """Adjust parameters based on correlation patterns."""
        if not pattern.parameters:
            return params

        param_name = pattern.parameters[0]
        if param_name not in params:
            return params

        current_value = params[param_name]

        # Determine adjustment based on correlation and strategy
        if strategy == OptimizationStrategy.BAYESIAN:
            adjustment = await self._bayesian_adjustment(current_value, pattern)
        elif strategy == OptimizationStrategy.GRADIENT:
            adjustment = await self._gradient_adjustment(current_value, pattern)
        else:
            adjustment = await self._random_adjustment(current_value, pattern)

        # Apply adjustment with bounds checking
        new_value = self._apply_bounds_checking(param_name, current_value, adjustment)
        params[param_name] = new_value

        return params

    async def _bayesian_adjustment(
        self, current_value: Any, pattern: PerformancePattern
    ) -> float:
        """Calculate Bayesian optimization adjustment."""
        # Simplified Bayesian adjustment based on correlation strength
        correlation_strength = pattern.correlation_strength
        improvement_potential = pattern.improvement_potential

        # Adjust based on correlation direction and strength
        if pattern.examples:
            best_example = max(pattern.examples, key=lambda x: x["quality_score"])
            best_value = best_example["param_value"]

            # Move towards best observed value
            try:
                current_float = float(current_value)
                best_float = float(best_value)

                # Calculate adjustment magnitude based on confidence
                adjustment_magnitude = correlation_strength * improvement_potential
                direction = 1 if best_float > current_float else -1

                return (
                    direction
                    * adjustment_magnitude
                    * abs(best_float - current_float)
                    * 0.1
                )
            except (ValueError, TypeError):
                return 0

        return 0

    async def _gradient_adjustment(
        self, current_value: Any, pattern: PerformancePattern
    ) -> float:
        """Calculate gradient-based adjustment."""
        # Simplified gradient calculation
        if not pattern.examples or len(pattern.examples) < 2:
            return 0

        try:
            # Calculate approximate gradient from examples
            examples = sorted(pattern.examples, key=lambda x: x["param_value"])
            if len(examples) >= 2:
                x_diff = examples[-1]["param_value"] - examples[0]["param_value"]
                y_diff = examples[-1]["quality_score"] - examples[0]["quality_score"]

                if x_diff != 0:
                    gradient = y_diff / x_diff
                    # Move in direction of positive gradient
                    return gradient * pattern.improvement_potential * 0.1

        except (ValueError, TypeError, KeyError):
            pass

        return 0

    async def _random_adjustment(
        self, current_value: Any, pattern: PerformancePattern
    ) -> float:
        """Calculate random search adjustment."""
        # Random adjustment within improvement potential range
        try:
            current_float = float(current_value)
            max_change = abs(current_float) * pattern.improvement_potential * 0.2
            return np.random.uniform(-max_change, max_change)
        except (ValueError, TypeError):
            return 0

    async def _adjust_memory_parameters(
        self, params: Dict, pattern: PerformancePattern
    ) -> Dict:
        """Adjust memory-related parameters."""
        # Identify memory-related parameters and adjust them
        memory_params = ["batch_size", "buffer_size", "cache_size", "memory_limit"]

        for param_name in memory_params:
            if param_name in params:
                current_value = params[param_name]
                try:
                    current_float = float(current_value)
                    # Reduce memory usage if correlation is negative
                    if pattern.correlation_strength < 0:
                        # Reduce by up to 20%
                        reduction = current_float * 0.2 * pattern.improvement_potential
                        params[param_name] = max(1, current_float - reduction)
                    break
                except (ValueError, TypeError):
                    continue

        return params

    def _apply_bounds_checking(
        self, param_name: str, current_value: Any, adjustment: float
    ) -> Any:
        """Apply bounds checking to parameter adjustments."""
        try:
            current_float = float(current_value)
            new_value = current_float + adjustment

            # Apply parameter-specific bounds
            bounds = self._get_parameter_bounds(param_name)
            if bounds:
                min_val, max_val = bounds
                new_value = max(min_val, min(max_val, new_value))

            # Return in original type if possible
            if isinstance(current_value, int):
                return int(round(new_value))
            else:
                return new_value

        except (ValueError, TypeError):
            return current_value

    def _get_parameter_bounds(self, param_name: str) -> Optional[Tuple[float, float]]:
        """Get bounds for specific parameters."""
        bounds_map = {
            "temperature": (0.0, 2.0),
            "top_p": (0.0, 1.0),
            "max_tokens": (1, 4096),
            "batch_size": (1, 1000),
            "learning_rate": (1e-6, 1e-1),
            "timeout": (1, 300),
            "retry_count": (0, 10),
        }

        return bounds_map.get(param_name)


class OptimizationStrategyRegistry:
    """Registry for optimization strategies."""

    def __init__(self):
        self.strategies = {}
        self.strategy_performance = defaultdict(list)

    def register_strategy(
        self, strategy: OptimizationStrategy, optimizer: OptimizationEngineInterface
    ) -> None:
        """Register an optimization strategy."""
        self.strategies[strategy] = optimizer
        logger.info(f"Registered optimization strategy: {strategy}")

    def get_strategy(
        self, strategy: OptimizationStrategy
    ) -> Optional[OptimizationEngineInterface]:
        """Get optimization strategy by name."""
        return self.strategies.get(strategy)

    def get_best_strategy(self, context: Dict) -> OptimizationStrategy:
        """Get the best strategy based on historical performance."""
        if not self.strategy_performance:
            return OptimizationStrategy.BAYESIAN  # Default

        # Calculate average performance for each strategy
        strategy_scores = {}
        for strategy, performances in self.strategy_performance.items():
            if performances:
                strategy_scores[strategy] = np.mean(performances)

        if strategy_scores:
            best_strategy = max(
                strategy_scores.keys(), key=lambda k: strategy_scores[k]
            )
            return best_strategy
        else:
            return OptimizationStrategy.BAYESIAN

    def record_strategy_performance(
        self, strategy: OptimizationStrategy, performance: float
    ) -> None:
        """Record performance of a strategy."""
        self.strategy_performance[strategy].append(performance)

        # Keep only recent performances
        if len(self.strategy_performance[strategy]) > 100:
            self.strategy_performance[strategy] = self.strategy_performance[strategy][
                -100:
            ]

    def list_strategies(self) -> List[OptimizationStrategy]:
        """List all registered strategies."""
        return list(self.strategies.keys())


class OptimizationEngine:
    """Main optimization engine coordinating all optimization components."""

    def __init__(self, config: Optional[Dict] = None):
        self.config = config or {}
        self.pattern_analyzer = PerformancePatternAnalyzer(
            window_size=self.config.get("analysis_window_size", 100),
            min_correlation=self.config.get("min_correlation", 0.3),
        )
        self.parameter_adjuster = ParameterAdjustmentEngine()
        self.strategy_registry = OptimizationStrategyRegistry()
        self.optimization_history = deque(maxlen=1000)

    async def optimize_parameters(
        self,
        current_params: Dict,
        execution_history: List[Dict],
        target_metric: str = "quality_score",
        strategy: Optional[OptimizationStrategy] = None,
    ) -> OptimizationResult:
        """Main optimization entry point."""
        start_time = time.time()

        # Choose strategy if not specified
        if strategy is None:
            strategy = self.strategy_registry.get_best_strategy(
                {"history_size": len(execution_history)}
            )

        # Analyze patterns
        patterns = await self.pattern_analyzer.analyze_execution_patterns(
            execution_history
        )

        # Adjust parameters based on patterns
        optimized_params = await self.parameter_adjuster.adjust_parameters(
            current_params, patterns, strategy
        )

        # Calculate expected improvement
        expected_improvement = self._calculate_expected_improvement(patterns)

        # Calculate confidence
        confidence = self._calculate_optimization_confidence(
            patterns, execution_history
        )

        optimization_time = time.time() - start_time

        result = OptimizationResult(
            optimized_params=optimized_params,
            expected_improvement=expected_improvement,
            confidence=confidence,
            strategy_used=strategy,
            optimization_time=optimization_time,
            metadata={
                "patterns_found": len(patterns),
                "history_size": len(execution_history),
                "target_metric": target_metric,
            },
        )

        # Record optimization
        self.optimization_history.append(
            {
                "timestamp": time.time(),
                "original_params": current_params,
                "result": result,
                "patterns": patterns,
            }
        )

        return result

    def _calculate_expected_improvement(
        self, patterns: List[PerformancePattern]
    ) -> float:
        """Calculate expected improvement from optimization."""
        if not patterns:
            return 0.0

        # Combine improvement potentials from all patterns
        total_improvement = 0.0
        for pattern in patterns:
            weighted_improvement = pattern.improvement_potential * pattern.confidence
            total_improvement += weighted_improvement

        # Cap at 1.0 (100% improvement)
        return min(total_improvement, 1.0)

    def _calculate_optimization_confidence(
        self, patterns: List[PerformancePattern], history: List[Dict]
    ) -> float:
        """Calculate confidence in optimization results."""
        if not patterns:
            return 0.1  # Low confidence with no patterns

        # Base confidence from pattern analysis
        pattern_confidence = np.mean([p.confidence for p in patterns])

        # Adjust for history size
        history_size = len(history)
        if history_size >= 100:
            history_factor = 1.0
        elif history_size >= 50:
            history_factor = 0.9
        elif history_size >= 20:
            history_factor = 0.8
        else:
            history_factor = 0.6

        return pattern_confidence * history_factor

    async def get_optimization_recommendations(
        self, execution_history: List[Dict]
    ) -> List[Dict]:
        """Get optimization recommendations based on analysis."""
        patterns = await self.pattern_analyzer.analyze_execution_patterns(
            execution_history
        )

        recommendations = []

        for pattern in patterns:
            if pattern.improvement_potential > 0.2:  # Significant improvement potential
                recommendation = {
                    "type": "parameter_optimization",
                    "pattern_type": pattern.pattern_type,
                    "parameters": pattern.parameters,
                    "expected_improvement": pattern.improvement_potential,
                    "confidence": pattern.confidence,
                    "description": self._generate_recommendation_description(pattern),
                    "priority": self._calculate_recommendation_priority(pattern),
                }
                recommendations.append(recommendation)

        # Sort by priority
        recommendations.sort(key=lambda x: x["priority"], reverse=True)

        return recommendations

    def _generate_recommendation_description(self, pattern: PerformancePattern) -> str:
        """Generate human-readable recommendation description."""
        if pattern.pattern_type == "parameter_correlation":
            param = pattern.parameters[0] if pattern.parameters else "parameter"
            return f"Adjust {param} to improve performance (correlation strength: {pattern.correlation_strength:.2f})"
        elif pattern.pattern_type == "declining_performance":
            return "Address declining performance trend over time"
        elif pattern.pattern_type == "memory_efficiency":
            return "Optimize memory usage for better performance"
        else:
            return f"Optimize based on {pattern.pattern_type} pattern"

    def _calculate_recommendation_priority(self, pattern: PerformancePattern) -> float:
        """Calculate priority score for recommendation."""
        # Combine improvement potential and confidence
        return pattern.improvement_potential * pattern.confidence

    def get_optimization_statistics(self) -> Dict:
        """Get optimization statistics."""
        if not self.optimization_history:
            return {"total_optimizations": 0}

        recent_optimizations = list(self.optimization_history)[-50:]  # Recent 50

        improvements = [
            opt["result"].expected_improvement for opt in recent_optimizations
        ]
        confidences = [opt["result"].confidence for opt in recent_optimizations]
        times = [opt["result"].optimization_time for opt in recent_optimizations]

        return {
            "total_optimizations": len(self.optimization_history),
            "recent_optimizations": len(recent_optimizations),
            "avg_expected_improvement": np.mean(improvements) if improvements else 0,
            "avg_confidence": np.mean(confidences) if confidences else 0,
            "avg_optimization_time": np.mean(times) if times else 0,
            "max_improvement": max(improvements) if improvements else 0,
            "strategies_used": list(
                set(opt["result"].strategy_used for opt in recent_optimizations)
            ),
        }
