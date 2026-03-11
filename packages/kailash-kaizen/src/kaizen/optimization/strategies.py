"""
Optimization strategies implementation for Kaizen auto-optimization system.

This module implements various optimization strategies including:
- Bayesian optimization
- Genetic algorithm optimization
- Gradient-based optimization
- Random search optimization
"""

import logging
import time
from typing import Dict, List, Optional, Tuple

import numpy as np
from scipy.optimize import minimize
from scipy.stats import norm

from .core import (
    OptimizationEngineInterface,
    OptimizationResult,
    OptimizationStrategy,
    PerformancePattern,
)

logger = logging.getLogger(__name__)

# Conditional imports for machine learning dependencies
try:
    from sklearn.gaussian_process import GaussianProcessRegressor
    from sklearn.gaussian_process.kernels import RBF, ConstantKernel, Matern

    SKLEARN_AVAILABLE = True
except ImportError:
    logger.warning(
        "scikit-learn not available. Bayesian optimization will use simplified implementation."
    )
    SKLEARN_AVAILABLE = False


class BayesianOptimizationStrategy(OptimizationEngineInterface):
    """Bayesian optimization strategy using Gaussian Process."""

    def __init__(self, config: Optional[Dict] = None):
        self.config = config or {}
        self.X_observed = []
        self.y_observed = []
        self.gp = None
        self.parameter_bounds = {}
        self.optimization_history = []

        if SKLEARN_AVAILABLE:
            self._init_gaussian_process()
        else:
            logger.warning(
                "Using simplified Bayesian optimization without scikit-learn"
            )

    def _init_gaussian_process(self):
        """Initialize Gaussian Process Regressor."""
        if SKLEARN_AVAILABLE:
            # RBF kernel with constant kernel for smooth optimization landscape
            kernel = ConstantKernel(1.0) * RBF(length_scale=1.0)
            self.gp = GaussianProcessRegressor(
                kernel=kernel,
                alpha=1e-6,
                normalize_y=True,
                n_restarts_optimizer=10,
                random_state=42,
            )

    async def optimize(
        self,
        current_params: Dict,
        history: List[Dict],
        target_metric: str = "quality_score",
    ) -> OptimizationResult:
        """Perform Bayesian optimization."""
        start_time = time.time()

        if len(history) < 2:
            # Not enough data for Bayesian optimization, use random search
            optimized_params = await self._random_suggestion(current_params)
            return OptimizationResult(
                optimized_params=optimized_params,
                expected_improvement=0.1,
                confidence=0.3,
                strategy_used=OptimizationStrategy.BAYESIAN,
                optimization_time=time.time() - start_time,
                metadata={"reason": "insufficient_data", "fallback": "random_search"},
            )

        # Extract features and targets from history
        X, y = self._extract_training_data(history, target_metric)

        if len(X) < 2 or not SKLEARN_AVAILABLE:
            # Fall back to simplified optimization
            optimized_params = await self._simplified_bayesian_optimization(
                current_params, history, target_metric
            )
        else:
            # Use full Gaussian Process optimization
            optimized_params = await self._gaussian_process_optimization(
                current_params, X, y
            )

        # Calculate expected improvement
        expected_improvement = await self._calculate_expected_improvement(
            optimized_params, current_params, history, target_metric
        )

        # Calculate confidence based on data quality and amount
        confidence = self._calculate_optimization_confidence(X, y)

        optimization_time = time.time() - start_time

        result = OptimizationResult(
            optimized_params=optimized_params,
            expected_improvement=expected_improvement,
            confidence=confidence,
            strategy_used=OptimizationStrategy.BAYESIAN,
            optimization_time=optimization_time,
            metadata={
                "training_samples": len(X),
                "target_metric": target_metric,
                "sklearn_available": SKLEARN_AVAILABLE,
            },
        )

        # Store for future optimization
        self.optimization_history.append(
            {"timestamp": time.time(), "params": current_params, "result": result}
        )

        return result

    def _extract_training_data(
        self, history: List[Dict], target_metric: str
    ) -> Tuple[np.ndarray, np.ndarray]:
        """Extract training data from execution history."""
        X = []
        y = []

        for entry in history:
            if "params" in entry and target_metric in entry:
                # Extract parameter features
                feature_vector = self._params_to_vector(entry["params"])
                if feature_vector is not None:
                    X.append(feature_vector)
                    y.append(float(entry[target_metric]))

        return np.array(X), np.array(y)

    def _params_to_vector(self, params: Dict) -> Optional[List[float]]:
        """Convert parameter dictionary to feature vector."""
        try:
            # Define parameter ordering for consistent feature vectors
            param_order = [
                "temperature",
                "max_tokens",
                "top_p",
                "frequency_penalty",
                "presence_penalty",
                "batch_size",
                "timeout",
                "retry_count",
            ]

            vector = []
            for param_name in param_order:
                if param_name in params:
                    value = params[param_name]
                    # Convert to float if possible
                    try:
                        vector.append(float(value))
                    except (ValueError, TypeError):
                        # Use default value for non-numeric parameters
                        vector.append(0.0)
                else:
                    # Use default value if parameter not present
                    defaults = {
                        "temperature": 0.7,
                        "max_tokens": 100,
                        "top_p": 1.0,
                        "frequency_penalty": 0.0,
                        "presence_penalty": 0.0,
                        "batch_size": 1,
                        "timeout": 30,
                        "retry_count": 3,
                    }
                    vector.append(defaults.get(param_name, 0.0))

            return vector if vector else None

        except Exception as e:
            logger.warning(f"Error converting params to vector: {e}")
            return None

    def _vector_to_params(self, vector: np.ndarray, reference_params: Dict) -> Dict:
        """Convert feature vector back to parameter dictionary."""
        param_order = [
            "temperature",
            "max_tokens",
            "top_p",
            "frequency_penalty",
            "presence_penalty",
            "batch_size",
            "timeout",
            "retry_count",
        ]

        params = reference_params.copy()

        for i, param_name in enumerate(param_order):
            if i < len(vector) and param_name in reference_params:
                value = vector[i]

                # Apply parameter-specific constraints and types
                if param_name in ["max_tokens", "batch_size", "retry_count"]:
                    params[param_name] = max(1, int(round(value)))
                elif param_name == "timeout":
                    params[param_name] = max(1, int(round(value)))
                elif param_name in [
                    "temperature",
                    "top_p",
                    "frequency_penalty",
                    "presence_penalty",
                ]:
                    # Apply bounds
                    bounds = self._get_parameter_bounds(param_name)
                    if bounds:
                        min_val, max_val = bounds
                        params[param_name] = max(min_val, min(max_val, float(value)))
                    else:
                        params[param_name] = float(value)

        return params

    def _get_parameter_bounds(self, param_name: str) -> Optional[Tuple[float, float]]:
        """Get bounds for specific parameters."""
        bounds_map = {
            "temperature": (0.0, 2.0),
            "top_p": (0.0, 1.0),
            "frequency_penalty": (-2.0, 2.0),
            "presence_penalty": (-2.0, 2.0),
            "max_tokens": (1, 4096),
            "batch_size": (1, 100),
            "timeout": (1, 300),
            "retry_count": (0, 10),
        }
        return bounds_map.get(param_name)

    async def _gaussian_process_optimization(
        self, current_params: Dict, X: np.ndarray, y: np.ndarray
    ) -> Dict:
        """Perform optimization using Gaussian Process."""
        if not SKLEARN_AVAILABLE or len(X) < 2:
            return current_params.copy()

        try:
            # Fit Gaussian Process
            self.gp.fit(X, y)

            # Find optimal parameters using acquisition function
            current_vector = self._params_to_vector(current_params)
            if current_vector is None:
                return current_params.copy()

            optimal_vector = await self._optimize_acquisition_function(
                np.array(current_vector), X, y
            )

            optimal_params = self._vector_to_params(optimal_vector, current_params)
            return optimal_params

        except Exception as e:
            logger.error(f"Error in Gaussian Process optimization: {e}")
            return await self._simplified_bayesian_optimization(
                current_params, [], "quality_score"
            )

    async def _optimize_acquisition_function(
        self, current_vector: np.ndarray, X: np.ndarray, y: np.ndarray
    ) -> np.ndarray:
        """Optimize acquisition function to find next best parameters."""
        best_y = np.max(y) if len(y) > 0 else 0

        def expected_improvement(x):
            """Expected Improvement acquisition function."""
            if len(x.shape) == 1:
                x = x.reshape(1, -1)

            mu, sigma = self.gp.predict(x, return_std=True)
            improvement = mu - best_y - 0.01  # Small exploration factor

            with np.errstate(divide="warn"):
                Z = improvement / sigma
                ei = improvement * norm.cdf(Z) + sigma * norm.pdf(Z)
                ei[sigma == 0.0] = 0.0

            return -ei  # Minimize negative EI

        # Define bounds for optimization
        bounds = []
        for i in range(len(current_vector)):
            param_names = [
                "temperature",
                "max_tokens",
                "top_p",
                "frequency_penalty",
                "presence_penalty",
                "batch_size",
                "timeout",
                "retry_count",
            ]
            if i < len(param_names):
                param_bounds = self._get_parameter_bounds(param_names[i])
                if param_bounds:
                    bounds.append(param_bounds)
                else:
                    # Default bounds
                    bounds.append((current_vector[i] * 0.5, current_vector[i] * 2.0))
            else:
                bounds.append((current_vector[i] * 0.5, current_vector[i] * 2.0))

        try:
            # Optimize acquisition function
            result = minimize(
                expected_improvement,
                x0=current_vector,
                bounds=bounds,
                method="L-BFGS-B",
                options={"maxiter": 100},
            )

            if result.success:
                return result.x
            else:
                logger.warning(f"Acquisition optimization failed: {result.message}")
                return current_vector

        except Exception as e:
            logger.error(f"Error optimizing acquisition function: {e}")
            return current_vector

    async def _simplified_bayesian_optimization(
        self, current_params: Dict, history: List[Dict], target_metric: str
    ) -> Dict:
        """Simplified Bayesian optimization without scikit-learn."""
        if not history:
            return await self._random_suggestion(current_params)

        # Find best performing parameters in history
        best_entry = max(history, key=lambda x: x.get(target_metric, 0))
        best_params = best_entry.get("params", {})

        # Create hybrid of current and best parameters
        optimized_params = current_params.copy()

        for param_name, best_value in best_params.items():
            if param_name in current_params:
                current_value = current_params[param_name]

                try:
                    # Weighted average towards best performing value
                    current_float = float(current_value)
                    best_float = float(best_value)

                    # 70% towards best, 30% current (with some randomness)
                    weight = 0.7 + np.random.normal(0, 0.1)
                    weight = np.clip(weight, 0.5, 0.9)

                    new_value = weight * best_float + (1 - weight) * current_float

                    # Apply bounds
                    bounds = self._get_parameter_bounds(param_name)
                    if bounds:
                        min_val, max_val = bounds
                        new_value = np.clip(new_value, min_val, max_val)

                    # Convert back to original type
                    if isinstance(current_value, int):
                        optimized_params[param_name] = int(round(new_value))
                    else:
                        optimized_params[param_name] = new_value

                except (ValueError, TypeError):
                    # Keep original value if conversion fails
                    pass

        return optimized_params

    async def _random_suggestion(self, current_params: Dict) -> Dict:
        """Generate random parameter suggestion."""
        suggested_params = current_params.copy()

        for param_name, current_value in current_params.items():
            try:
                current_float = float(current_value)
                bounds = self._get_parameter_bounds(param_name)

                if bounds:
                    min_val, max_val = bounds
                    # Random value within bounds
                    new_value = np.random.uniform(min_val, max_val)
                else:
                    # Random perturbation around current value
                    perturbation = np.random.normal(0, 0.1) * current_float
                    new_value = current_float + perturbation

                # Convert back to original type
                if isinstance(current_value, int):
                    suggested_params[param_name] = int(round(new_value))
                else:
                    suggested_params[param_name] = new_value

            except (ValueError, TypeError):
                # Keep original value if conversion fails
                pass

        return suggested_params

    async def _calculate_expected_improvement(
        self,
        optimized_params: Dict,
        current_params: Dict,
        history: List[Dict],
        target_metric: str,
    ) -> float:
        """Calculate expected improvement from optimization."""
        if not history:
            return 0.1  # Small expected improvement without data

        # Calculate average performance improvement in history
        recent_history = history[-20:]  # Recent 20 executions
        if len(recent_history) < 2:
            return 0.1

        performance_values = [entry.get(target_metric, 0) for entry in recent_history]
        baseline_performance = np.mean(performance_values)

        # Estimate improvement based on parameter changes
        total_change = 0.0
        changed_params = 0

        for param_name in current_params:
            if param_name in optimized_params:
                try:
                    current_val = float(current_params[param_name])
                    optimized_val = float(optimized_params[param_name])
                    relative_change = abs(optimized_val - current_val) / max(
                        abs(current_val), 1e-6
                    )
                    total_change += relative_change
                    changed_params += 1
                except (ValueError, TypeError):
                    pass

        if changed_params > 0:
            avg_change = total_change / changed_params
            # Estimate improvement as 10-50% of average parameter change
            expected_improvement = min(0.5, 0.1 + avg_change * 0.4)
        else:
            expected_improvement = 0.1

        return expected_improvement

    def _calculate_optimization_confidence(self, X: np.ndarray, y: np.ndarray) -> float:
        """Calculate confidence in optimization based on data quality."""
        if len(X) < 2:
            return 0.3  # Low confidence with insufficient data

        # Base confidence from sample size
        sample_size_factor = min(1.0, len(X) / 50.0)

        # Confidence from target value variance (more variance = more opportunity)
        if len(y) > 1:
            y_std = np.std(y)
            y_mean = np.mean(y)
            cv = y_std / max(abs(y_mean), 1e-6)  # Coefficient of variation
            variance_factor = min(
                1.0, cv
            )  # More variance suggests more optimization potential
        else:
            variance_factor = 0.5

        # Overall confidence
        confidence = 0.4 + 0.4 * sample_size_factor + 0.2 * variance_factor

        return min(confidence, 0.9)  # Cap at 90% confidence

    async def analyze_patterns(self, history: List[Dict]) -> List[PerformancePattern]:
        """Analyze patterns specific to Bayesian optimization."""
        patterns = []

        if len(history) < 10:
            return patterns

        # Analyze convergence patterns
        convergence_pattern = await self._analyze_convergence_pattern(history)
        if convergence_pattern:
            patterns.append(convergence_pattern)

        # Analyze parameter sensitivity
        sensitivity_patterns = await self._analyze_parameter_sensitivity(history)
        patterns.extend(sensitivity_patterns)

        return patterns

    async def _analyze_convergence_pattern(
        self, history: List[Dict]
    ) -> Optional[PerformancePattern]:
        """Analyze if optimization is converging."""
        if len(history) < 20:
            return None

        # Look at quality scores over time
        quality_scores = []
        for entry in history:
            if "quality_score" in entry:
                quality_scores.append(entry["quality_score"])

        if len(quality_scores) < 20:
            return None

        # Check if recent performance is better than early performance
        early_performance = np.mean(quality_scores[:10])
        recent_performance = np.mean(quality_scores[-10:])

        improvement = (recent_performance - early_performance) / max(
            abs(early_performance), 1e-6
        )

        if improvement > 0.1:  # 10% improvement
            return PerformancePattern(
                pattern_type="convergence_improvement",
                parameters=["optimization_progress"],
                correlation_strength=improvement,
                improvement_potential=min(0.3, improvement * 2),  # Future potential
                confidence=0.8,
                examples=[
                    {
                        "early_performance": early_performance,
                        "recent_performance": recent_performance,
                        "improvement": improvement,
                    }
                ],
            )

        return None

    async def _analyze_parameter_sensitivity(
        self, history: List[Dict]
    ) -> List[PerformancePattern]:
        """Analyze parameter sensitivity for Bayesian optimization."""
        patterns = []

        # Group by parameter values and analyze performance
        param_performance = {}

        for entry in history:
            if "params" not in entry or "quality_score" not in entry:
                continue

            for param_name, param_value in entry["params"].items():
                try:
                    float_value = float(param_value)
                    if param_name not in param_performance:
                        param_performance[param_name] = []

                    param_performance[param_name].append(
                        {"value": float_value, "quality": entry["quality_score"]}
                    )

                except (ValueError, TypeError):
                    continue

        # Analyze each parameter
        for param_name, data_points in param_performance.items():
            if len(data_points) >= 10:
                pattern = await self._analyze_single_parameter_sensitivity(
                    param_name, data_points
                )
                if pattern:
                    patterns.append(pattern)

        return patterns

    async def _analyze_single_parameter_sensitivity(
        self, param_name: str, data_points: List[Dict]
    ) -> Optional[PerformancePattern]:
        """Analyze sensitivity of a single parameter."""
        values = [dp["value"] for dp in data_points]
        qualities = [dp["quality"] for dp in data_points]

        # Calculate correlation
        correlation = np.corrcoef(values, qualities)[0, 1]

        if np.isnan(correlation) or abs(correlation) < 0.3:
            return None

        return PerformancePattern(
            pattern_type="parameter_sensitivity",
            parameters=[param_name],
            correlation_strength=abs(correlation),
            improvement_potential=min(0.4, abs(correlation) * 0.5),
            confidence=min(0.9, len(data_points) / 50.0),
            examples=[
                {
                    "param_name": param_name,
                    "correlation": correlation,
                    "sample_size": len(data_points),
                    "value_range": (min(values), max(values)),
                    "quality_range": (min(qualities), max(qualities)),
                }
            ],
        )

    def update_strategy(self, feedback: Dict) -> None:
        """Update Bayesian optimization strategy based on feedback."""
        if "performance" in feedback:
            performance = feedback["performance"]

            # Adjust exploration vs exploitation based on performance
            if performance < 0.5:  # Poor performance, increase exploration
                if SKLEARN_AVAILABLE and self.gp:
                    # Increase noise parameter for more exploration
                    self.gp.alpha = min(1e-3, self.gp.alpha * 1.1)

            elif performance > 0.8:  # Good performance, reduce exploration
                if SKLEARN_AVAILABLE and self.gp:
                    # Decrease noise parameter for more exploitation
                    self.gp.alpha = max(1e-8, self.gp.alpha * 0.9)

        logger.debug(
            f"Updated Bayesian optimization strategy based on feedback: {feedback}"
        )


class GeneticOptimizationStrategy(OptimizationEngineInterface):
    """Genetic algorithm optimization strategy."""

    def __init__(self, config: Optional[Dict] = None):
        self.config = config or {}
        self.population_size = self.config.get("population_size", 20)
        self.mutation_rate = self.config.get("mutation_rate", 0.1)
        self.crossover_rate = self.config.get("crossover_rate", 0.8)
        self.generations = self.config.get("generations", 10)

    async def optimize(
        self,
        current_params: Dict,
        history: List[Dict],
        target_metric: str = "quality_score",
    ) -> OptimizationResult:
        """Perform genetic algorithm optimization."""
        start_time = time.time()

        if len(history) < 5:
            # Not enough data for genetic algorithm
            optimized_params = self._mutate_parameters(current_params)
            return OptimizationResult(
                optimized_params=optimized_params,
                expected_improvement=0.15,
                confidence=0.4,
                strategy_used=OptimizationStrategy.GENETIC,
                optimization_time=time.time() - start_time,
                metadata={"reason": "insufficient_data", "fallback": "mutation"},
            )

        # Extract top performers from history
        top_performers = self._select_top_performers(history, target_metric)

        # Run genetic algorithm
        optimized_params = await self._run_genetic_algorithm(
            current_params, top_performers, target_metric
        )

        # Calculate expected improvement
        expected_improvement = self._estimate_genetic_improvement(
            optimized_params, current_params, history
        )

        optimization_time = time.time() - start_time

        return OptimizationResult(
            optimized_params=optimized_params,
            expected_improvement=expected_improvement,
            confidence=0.7,
            strategy_used=OptimizationStrategy.GENETIC,
            optimization_time=optimization_time,
            metadata={
                "population_size": self.population_size,
                "generations": self.generations,
                "top_performers": len(top_performers),
            },
        )

    def _select_top_performers(
        self, history: List[Dict], target_metric: str
    ) -> List[Dict]:
        """Select top performing parameter sets from history."""
        # Sort by target metric and take top 20%
        valid_entries = [
            entry for entry in history if target_metric in entry and "params" in entry
        ]
        valid_entries.sort(key=lambda x: x[target_metric], reverse=True)

        top_count = max(2, len(valid_entries) // 5)  # Top 20%
        return valid_entries[:top_count]

    async def _run_genetic_algorithm(
        self, current_params: Dict, top_performers: List[Dict], target_metric: str
    ) -> Dict:
        """Run genetic algorithm to find optimal parameters."""
        # Initialize population with top performers and current params
        population = []

        # Add current parameters
        population.append(current_params)

        # Add top performers
        for performer in top_performers[: self.population_size - 1]:
            if "params" in performer:
                population.append(performer["params"])

        # Fill remaining population with mutations
        while len(population) < self.population_size:
            parent = np.random.choice(population)
            mutated = self._mutate_parameters(parent)
            population.append(mutated)

        # Run evolution for specified generations
        for generation in range(self.generations):
            # Select parents for crossover
            new_population = []

            # Keep best individuals (elitism)
            elite_count = max(1, self.population_size // 10)
            new_population.extend(population[:elite_count])

            # Generate offspring
            while len(new_population) < self.population_size:
                if np.random.random() < self.crossover_rate and len(population) >= 2:
                    # Crossover
                    parent1, parent2 = np.random.choice(population, 2, replace=False)
                    offspring = self._crossover_parameters(parent1, parent2)
                else:
                    # Mutation
                    parent = np.random.choice(population)
                    offspring = self._mutate_parameters(parent)

                new_population.append(offspring)

            population = new_population

        # Return best individual (first one after sorting)
        return population[0]

    def _mutate_parameters(self, params: Dict) -> Dict:
        """Mutate parameters for genetic algorithm."""
        mutated = params.copy()

        for param_name, value in params.items():
            if np.random.random() < self.mutation_rate:
                try:
                    current_float = float(value)

                    # Apply Gaussian mutation
                    mutation_strength = 0.1  # 10% of current value
                    mutation = np.random.normal(
                        0, mutation_strength * abs(current_float)
                    )
                    new_value = current_float + mutation

                    # Apply bounds
                    bounds = self._get_parameter_bounds(param_name)
                    if bounds:
                        min_val, max_val = bounds
                        new_value = np.clip(new_value, min_val, max_val)

                    # Convert back to original type
                    if isinstance(value, int):
                        mutated[param_name] = int(round(new_value))
                    else:
                        mutated[param_name] = new_value

                except (ValueError, TypeError):
                    # Can't mutate non-numeric parameter
                    pass

        return mutated

    def _crossover_parameters(self, parent1: Dict, parent2: Dict) -> Dict:
        """Crossover two parameter sets."""
        offspring = {}

        all_params = set(parent1.keys()) | set(parent2.keys())

        for param_name in all_params:
            # Random choice between parents
            if param_name in parent1 and param_name in parent2:
                if np.random.random() < 0.5:
                    offspring[param_name] = parent1[param_name]
                else:
                    offspring[param_name] = parent2[param_name]
            elif param_name in parent1:
                offspring[param_name] = parent1[param_name]
            else:
                offspring[param_name] = parent2[param_name]

        return offspring

    def _get_parameter_bounds(self, param_name: str) -> Optional[Tuple[float, float]]:
        """Get bounds for parameters (same as Bayesian)."""
        bounds_map = {
            "temperature": (0.0, 2.0),
            "top_p": (0.0, 1.0),
            "frequency_penalty": (-2.0, 2.0),
            "presence_penalty": (-2.0, 2.0),
            "max_tokens": (1, 4096),
            "batch_size": (1, 100),
            "timeout": (1, 300),
            "retry_count": (0, 10),
        }
        return bounds_map.get(param_name)

    def _estimate_genetic_improvement(
        self, optimized_params: Dict, current_params: Dict, history: List[Dict]
    ) -> float:
        """Estimate improvement from genetic optimization."""
        # Similar to Bayesian but with higher expected improvement due to population diversity
        total_change = 0.0
        changed_params = 0

        for param_name in current_params:
            if param_name in optimized_params:
                try:
                    current_val = float(current_params[param_name])
                    optimized_val = float(optimized_params[param_name])
                    relative_change = abs(optimized_val - current_val) / max(
                        abs(current_val), 1e-6
                    )
                    total_change += relative_change
                    changed_params += 1
                except (ValueError, TypeError):
                    pass

        if changed_params > 0:
            avg_change = total_change / changed_params
            # Genetic algorithms often find better solutions
            expected_improvement = min(0.6, 0.15 + avg_change * 0.5)
        else:
            expected_improvement = 0.15

        return expected_improvement

    async def analyze_patterns(self, history: List[Dict]) -> List[PerformancePattern]:
        """Analyze patterns for genetic optimization."""
        # Genetic algorithms are good at finding patterns in parameter combinations
        patterns = []

        if len(history) < 20:
            return patterns

        # Analyze parameter combinations that work well together
        combination_pattern = await self._analyze_parameter_combinations(history)
        if combination_pattern:
            patterns.append(combination_pattern)

        return patterns

    async def _analyze_parameter_combinations(
        self, history: List[Dict]
    ) -> Optional[PerformancePattern]:
        """Analyze which parameter combinations work well together."""
        # This is a simplified analysis - in practice, you'd use more sophisticated methods
        top_performers = self._select_top_performers(history, "quality_score")

        if len(top_performers) < 5:
            return None

        # Look for common parameter ranges in top performers
        param_stats = {}

        for performer in top_performers:
            params = performer.get("params", {})
            for param_name, value in params.items():
                try:
                    float_value = float(value)
                    if param_name not in param_stats:
                        param_stats[param_name] = []
                    param_stats[param_name].append(float_value)
                except (ValueError, TypeError):
                    continue

        # Find parameters with low variance in top performers (indicating good combinations)
        stable_params = []
        for param_name, values in param_stats.items():
            if len(values) >= 3:
                cv = np.std(values) / max(abs(np.mean(values)), 1e-6)
                if cv < 0.2:  # Low coefficient of variation
                    stable_params.append(param_name)

        if len(stable_params) >= 2:
            return PerformancePattern(
                pattern_type="parameter_combination",
                parameters=stable_params,
                correlation_strength=0.6,
                improvement_potential=0.3,
                confidence=0.7,
                examples=[
                    {
                        "stable_parameters": stable_params,
                        "top_performers_count": len(top_performers),
                    }
                ],
            )

        return None

    def update_strategy(self, feedback: Dict) -> None:
        """Update genetic algorithm parameters based on feedback."""
        performance = feedback.get("performance", 0.5)

        if performance < 0.4:
            # Poor performance, increase mutation for more exploration
            self.mutation_rate = min(0.3, self.mutation_rate * 1.2)
            self.population_size = min(50, int(self.population_size * 1.1))
        elif performance > 0.8:
            # Good performance, reduce mutation for more exploitation
            self.mutation_rate = max(0.05, self.mutation_rate * 0.9)

        logger.debug(
            f"Updated genetic algorithm parameters: mutation_rate={self.mutation_rate}, "
            f"population_size={self.population_size}"
        )


class RandomSearchStrategy(OptimizationEngineInterface):
    """Random search optimization strategy."""

    def __init__(self, config: Optional[Dict] = None):
        self.config = config or {}
        self.num_samples = self.config.get("num_samples", 10)

    async def optimize(
        self,
        current_params: Dict,
        history: List[Dict],
        target_metric: str = "quality_score",
    ) -> OptimizationResult:
        """Perform random search optimization."""
        start_time = time.time()

        best_params = current_params.copy()
        best_score = 0.0

        # Get baseline from history if available
        if history:
            recent_scores = [entry.get(target_metric, 0) for entry in history[-10:]]
            baseline = np.mean(recent_scores) if recent_scores else 0.0
        else:
            baseline = 0.0

        # Generate random parameter combinations
        for _ in range(self.num_samples):
            random_params = self._generate_random_parameters(current_params)

            # Estimate score for these parameters (simplified heuristic)
            estimated_score = self._estimate_parameter_score(
                random_params, history, target_metric
            )

            if estimated_score > best_score:
                best_score = estimated_score
                best_params = random_params

        # Calculate expected improvement
        expected_improvement = max(
            0.05, (best_score - baseline) if baseline > 0 else 0.1
        )

        optimization_time = time.time() - start_time

        return OptimizationResult(
            optimized_params=best_params,
            expected_improvement=expected_improvement,
            confidence=0.5,  # Medium confidence for random search
            strategy_used=OptimizationStrategy.RANDOM_SEARCH,
            optimization_time=optimization_time,
            metadata={
                "samples_generated": self.num_samples,
                "best_estimated_score": best_score,
                "baseline_score": baseline,
            },
        )

    def _generate_random_parameters(self, base_params: Dict) -> Dict:
        """Generate random parameter values within bounds."""
        random_params = base_params.copy()

        for param_name, value in base_params.items():
            bounds = self._get_parameter_bounds(param_name)

            if bounds:
                min_val, max_val = bounds
                random_value = np.random.uniform(min_val, max_val)

                # Convert to appropriate type
                if isinstance(value, int):
                    random_params[param_name] = int(round(random_value))
                else:
                    random_params[param_name] = random_value
            else:
                # For unbounded parameters, use normal distribution around current value
                try:
                    current_float = float(value)
                    std = abs(current_float) * 0.2  # 20% standard deviation
                    random_value = np.random.normal(current_float, std)

                    if isinstance(value, int):
                        random_params[param_name] = int(round(random_value))
                    else:
                        random_params[param_name] = random_value

                except (ValueError, TypeError):
                    # Keep original value for non-numeric parameters
                    pass

        return random_params

    def _estimate_parameter_score(
        self, params: Dict, history: List[Dict], target_metric: str
    ) -> float:
        """Estimate score for parameter combination based on history."""
        if not history:
            return np.random.uniform(0.3, 0.7)  # Random baseline

        # Find similar parameter combinations in history
        similarities = []

        for entry in history:
            if "params" not in entry or target_metric not in entry:
                continue

            similarity = self._calculate_parameter_similarity(params, entry["params"])
            score = entry[target_metric]

            similarities.append((similarity, score))

        if not similarities:
            return np.random.uniform(0.3, 0.7)

        # Weight scores by similarity
        weighted_score = 0.0
        total_weight = 0.0

        for similarity, score in similarities:
            weight = similarity
            weighted_score += weight * score
            total_weight += weight

        if total_weight > 0:
            return weighted_score / total_weight
        else:
            return np.random.uniform(0.3, 0.7)

    def _calculate_parameter_similarity(self, params1: Dict, params2: Dict) -> float:
        """Calculate similarity between two parameter sets."""
        common_params = set(params1.keys()) & set(params2.keys())

        if not common_params:
            return 0.0

        similarity_sum = 0.0

        for param_name in common_params:
            try:
                val1 = float(params1[param_name])
                val2 = float(params2[param_name])

                # Normalized difference
                max_val = max(abs(val1), abs(val2), 1e-6)
                diff = abs(val1 - val2) / max_val
                similarity = 1.0 - min(diff, 1.0)

                similarity_sum += similarity

            except (ValueError, TypeError):
                # For non-numeric parameters, exact match
                if params1[param_name] == params2[param_name]:
                    similarity_sum += 1.0

        return similarity_sum / len(common_params)

    def _get_parameter_bounds(self, param_name: str) -> Optional[Tuple[float, float]]:
        """Get bounds for parameters."""
        bounds_map = {
            "temperature": (0.0, 2.0),
            "top_p": (0.0, 1.0),
            "frequency_penalty": (-2.0, 2.0),
            "presence_penalty": (-2.0, 2.0),
            "max_tokens": (1, 4096),
            "batch_size": (1, 100),
            "timeout": (1, 300),
            "retry_count": (0, 10),
        }
        return bounds_map.get(param_name)

    async def analyze_patterns(self, history: List[Dict]) -> List[PerformancePattern]:
        """Random search doesn't identify complex patterns."""
        return []  # Random search is pattern-agnostic

    def update_strategy(self, feedback: Dict) -> None:
        """Update random search parameters."""
        performance = feedback.get("performance", 0.5)

        if performance < 0.3:
            # Poor performance, increase sample count
            self.num_samples = min(50, int(self.num_samples * 1.5))
        elif performance > 0.8:
            # Good performance, maintain or slightly reduce samples
            self.num_samples = max(5, int(self.num_samples * 0.95))

        logger.debug(
            f"Updated random search parameters: num_samples={self.num_samples}"
        )
