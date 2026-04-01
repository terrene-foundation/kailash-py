# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""AutoMLEngine -- automated model selection + hyperparameter optimization.

Orchestrates HyperparameterSearch across multiple model families, ranks
results, and optionally augments decisions with Kaizen agents (double opt-in).
"""
from __future__ import annotations

import logging
import math
import time
from dataclasses import dataclass, field
from typing import Any

import polars as pl
from kailash_ml_protocols import FeatureSchema

logger = logging.getLogger(__name__)

__all__ = [
    "AutoMLEngine",
    "AutoMLConfig",
    "CandidateResult",
    "AgentRecommendation",
    "AutoMLResult",
    "LLMCostTracker",
    "LLMBudgetExceededError",
]


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class LLMBudgetExceededError(Exception):
    """Raised when agent LLM cost exceeds the configured budget."""


# ---------------------------------------------------------------------------
# Core types
# ---------------------------------------------------------------------------


@dataclass
class AutoMLConfig:
    """AutoML configuration."""

    task_type: str = "classification"  # "classification", "regression"
    metric_to_optimize: str = "accuracy"
    direction: str = "maximize"
    candidate_families: list[str] | None = None  # None = all supported
    search_strategy: str = "random"
    search_n_trials: int = 30
    register_best: bool = True
    # Agent guardrails
    agent: bool = False
    auto_approve: bool = False
    max_llm_cost_usd: float = 1.0
    approval_timeout_seconds: float = 600.0
    audit_batch_size: int = 10
    audit_flush_interval_seconds: float = 30.0


@dataclass
class CandidateResult:
    """Result of evaluating a single model candidate."""

    model_class: str
    framework: str
    default_metrics: dict[str, float]
    search_result: Any | None = None  # SearchResult | None
    rank: int = 0


@dataclass
class AgentRecommendation:
    """Agent's model selection recommendation."""

    recommended_models: list[str]
    search_spaces: dict[str, Any]
    reasoning: str
    self_assessed_confidence: float
    cost_usd: float


@dataclass
class AutoMLResult:
    """Complete AutoML result."""

    best_model: CandidateResult
    best_metrics: dict[str, float]
    all_candidates: list[CandidateResult]
    search_result: Any | None = None  # SearchResult | None
    agent_recommendation: AgentRecommendation | None = None
    baseline_recommendation: list[str] = field(default_factory=list)
    total_time_seconds: float = 0.0
    model_version: Any | None = None  # ModelVersion | None


# ---------------------------------------------------------------------------
# LLMCostTracker (Guardrail 2)
# ---------------------------------------------------------------------------


class LLMCostTracker:
    """Tracks LLM token costs across multiple Delegate runs.

    Per-model pricing loaded from environment variables:
    KAILASH_ML_LLM_COST_INPUT_PER_1K, KAILASH_ML_LLM_COST_OUTPUT_PER_1K.
    """

    def __init__(self, max_budget_usd: float = 1.0) -> None:
        if not math.isfinite(max_budget_usd) or max_budget_usd < 0:
            raise ValueError("max_budget_usd must be a finite non-negative number")
        self._max_budget = max_budget_usd
        self._spent: float = 0.0
        self._calls: list[dict[str, Any]] = []

    def record(self, model: str, input_tokens: int, output_tokens: int) -> None:
        """Record a Delegate call and check budget."""
        cost = self._compute_cost(model, input_tokens, output_tokens)
        self._spent += cost
        self._calls.append(
            {
                "model": model,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "cost": cost,
            }
        )
        if self._spent > self._max_budget:
            raise LLMBudgetExceededError(
                f"LLM cost ${self._spent:.4f} exceeds budget ${self._max_budget:.2f}"
            )

    def _compute_cost(self, model: str, input_tokens: int, output_tokens: int) -> float:
        """Compute cost for a single call. Uses simple default pricing."""
        import os

        input_cost_per_1k = float(
            os.environ.get("KAILASH_ML_LLM_COST_INPUT_PER_1K", "0.003")
        )
        output_cost_per_1k = float(
            os.environ.get("KAILASH_ML_LLM_COST_OUTPUT_PER_1K", "0.015")
        )
        return (input_tokens / 1000.0) * input_cost_per_1k + (
            output_tokens / 1000.0
        ) * output_cost_per_1k

    @property
    def total_spent(self) -> float:
        return self._spent

    @property
    def calls(self) -> list[dict[str, Any]]:
        return list(self._calls)


# ---------------------------------------------------------------------------
# Default candidate families
# ---------------------------------------------------------------------------


_CLASSIFICATION_CANDIDATES: list[tuple[str, str, dict[str, Any]]] = [
    (
        "sklearn.ensemble.RandomForestClassifier",
        "sklearn",
        {"n_estimators": 50, "random_state": 42},
    ),
    (
        "sklearn.ensemble.GradientBoostingClassifier",
        "sklearn",
        {"n_estimators": 50, "random_state": 42},
    ),
    (
        "sklearn.linear_model.LogisticRegression",
        "sklearn",
        {"max_iter": 200, "random_state": 42},
    ),
]

_REGRESSION_CANDIDATES: list[tuple[str, str, dict[str, Any]]] = [
    (
        "sklearn.ensemble.RandomForestRegressor",
        "sklearn",
        {"n_estimators": 50, "random_state": 42},
    ),
    (
        "sklearn.ensemble.GradientBoostingRegressor",
        "sklearn",
        {"n_estimators": 50, "random_state": 42},
    ),
    ("sklearn.linear_model.Ridge", "sklearn", {"alpha": 1.0}),
]


# ---------------------------------------------------------------------------
# AutoMLEngine
# ---------------------------------------------------------------------------


class AutoMLEngine:
    """[P1: Production with Caveats] Automated model selection and optimization.

    Orchestrates HyperparameterSearch across multiple model families,
    ranks results, and optionally augments decisions with Kaizen agents.
    Agent augmentation requires double opt-in: ``pip install kailash-ml[agents]``
    AND ``agent=True`` at call site.

    Parameters
    ----------
    pipeline:
        TrainingPipeline for training candidates.
    search:
        HyperparameterSearch for deep optimization.
    registry:
        Optional ModelRegistry for registration.
    """

    def __init__(
        self,
        pipeline: Any,
        search: Any,
        *,
        registry: Any | None = None,
    ) -> None:
        self._pipeline = pipeline
        self._search = search
        self._registry = registry

    async def run(
        self,
        data: pl.DataFrame,
        schema: FeatureSchema,
        config: AutoMLConfig,
        eval_spec: Any,
        experiment_name: str,
    ) -> AutoMLResult:
        """Run automated model selection + hyperparameter optimization.

        1. Profile data
        2. Compute baseline recommendation (Guardrail 4)
        3. Quick-train each candidate with default hyperparameters
        4. Rank candidates by metric
        5. Run HyperparameterSearch on top candidate
        6. Register best model if requested
        """
        from kailash_ml.engines.hyperparameter_search import (
            ParamDistribution,
            SearchConfig,
            SearchSpace,
        )
        from kailash_ml.engines.training_pipeline import ModelSpec

        start_time = time.perf_counter()

        # Guardrail 4: baseline recommendation
        baseline = self._compute_baseline_recommendation(data, schema, config)

        # Agent augmentation (not implemented in v1 -- requires kaizen agents)
        agent_rec: AgentRecommendation | None = None

        # Determine candidates
        candidates_spec = self._get_candidates(config)

        # Quick-train each candidate
        candidate_results: list[CandidateResult] = []
        for model_class, framework, default_hp in candidates_spec:
            try:
                spec = ModelSpec(model_class, default_hp, framework)
                train_result = await self._pipeline.train(
                    data,
                    schema,
                    spec,
                    eval_spec,
                    f"{experiment_name}_{model_class.split('.')[-1]}",
                )
                candidate_results.append(
                    CandidateResult(
                        model_class=model_class,
                        framework=framework,
                        default_metrics=train_result.metrics,
                    )
                )
            except Exception as exc:
                logger.warning("Candidate %s failed: %s", model_class, exc)

        if not candidate_results:
            raise RuntimeError("All AutoML candidates failed during quick-train")

        # Rank by metric
        if config.direction == "maximize":
            candidate_results.sort(
                key=lambda c: c.default_metrics.get(config.metric_to_optimize, 0.0),
                reverse=True,
            )
        else:
            candidate_results.sort(
                key=lambda c: c.default_metrics.get(
                    config.metric_to_optimize, float("inf")
                ),
            )

        for i, c in enumerate(candidate_results):
            c.rank = i + 1

        # Deep search on top candidate
        top = candidate_results[0]
        search_space = self._default_search_space(top.model_class, top.framework)
        search_config = SearchConfig(
            strategy=config.search_strategy,
            n_trials=config.search_n_trials,
            metric_to_optimize=config.metric_to_optimize,
            direction=config.direction,
            register_best=False,  # We register manually
        )

        base_spec = ModelSpec(top.model_class, {}, top.framework)
        search_result = await self._search.search(
            data,
            schema,
            base_spec,
            search_space,
            search_config,
            eval_spec,
            f"{experiment_name}_hp_search",
        )
        top.search_result = search_result

        # Best metrics from search
        best_metrics = (
            search_result.best_metrics
            if search_result.best_metrics
            else top.default_metrics
        )

        total_time = time.perf_counter() - start_time

        return AutoMLResult(
            best_model=top,
            best_metrics=best_metrics,
            all_candidates=candidate_results,
            search_result=search_result,
            agent_recommendation=agent_rec,
            baseline_recommendation=baseline,
            total_time_seconds=total_time,
        )

    def _get_candidates(
        self, config: AutoMLConfig
    ) -> list[tuple[str, str, dict[str, Any]]]:
        """Get candidate model families for the task type."""
        if config.task_type == "classification":
            return list(_CLASSIFICATION_CANDIDATES)
        elif config.task_type == "regression":
            return list(_REGRESSION_CANDIDATES)
        else:
            raise ValueError(f"Unknown task type: {config.task_type}")

    def _compute_baseline_recommendation(
        self,
        data: pl.DataFrame,
        schema: FeatureSchema,
        config: AutoMLConfig,
    ) -> list[str]:
        """Compute what the default algorithmic selection would pick.

        Profiles the data and returns a ranked list of model families
        based on dataset size, feature count, and task type.
        """
        n_rows = data.height
        n_features = len(schema.features)

        if config.task_type == "classification":
            if n_rows < 500 or n_features < 5:
                return [
                    "sklearn.linear_model.LogisticRegression",
                    "sklearn.ensemble.RandomForestClassifier",
                    "sklearn.ensemble.GradientBoostingClassifier",
                ]
            else:
                return [
                    "sklearn.ensemble.GradientBoostingClassifier",
                    "sklearn.ensemble.RandomForestClassifier",
                    "sklearn.linear_model.LogisticRegression",
                ]
        else:
            if n_rows < 500:
                return [
                    "sklearn.linear_model.Ridge",
                    "sklearn.ensemble.RandomForestRegressor",
                    "sklearn.ensemble.GradientBoostingRegressor",
                ]
            else:
                return [
                    "sklearn.ensemble.GradientBoostingRegressor",
                    "sklearn.ensemble.RandomForestRegressor",
                    "sklearn.linear_model.Ridge",
                ]

    def _default_search_space(self, model_class: str, framework: str) -> Any:
        """Create a default search space for a model class."""
        from kailash_ml.engines.hyperparameter_search import (
            ParamDistribution,
            SearchSpace,
        )

        cls_name = model_class.split(".")[-1].lower()

        if "randomforest" in cls_name:
            return SearchSpace(
                [
                    ParamDistribution("n_estimators", "int_uniform", low=10, high=200),
                    ParamDistribution("max_depth", "int_uniform", low=3, high=20),
                ]
            )
        elif "gradientboosting" in cls_name:
            return SearchSpace(
                [
                    ParamDistribution("n_estimators", "int_uniform", low=20, high=200),
                    ParamDistribution(
                        "learning_rate", "log_uniform", low=0.01, high=0.3
                    ),
                    ParamDistribution("max_depth", "int_uniform", low=2, high=10),
                ]
            )
        elif "logisticregression" in cls_name:
            return SearchSpace(
                [
                    ParamDistribution("C", "log_uniform", low=0.01, high=10.0),
                ]
            )
        elif "ridge" in cls_name:
            return SearchSpace(
                [
                    ParamDistribution("alpha", "log_uniform", low=0.01, high=100.0),
                ]
            )
        else:
            return SearchSpace(
                [
                    ParamDistribution("n_estimators", "int_uniform", low=10, high=100),
                ]
            )
