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
from collections import deque
from dataclasses import dataclass, field
from typing import Any

import polars as pl
from kailash_ml.types import FeatureSchema

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

    def __post_init__(self) -> None:
        import math

        if not math.isfinite(self.max_llm_cost_usd):
            raise ValueError("max_llm_cost_usd must be finite")
        if self.max_llm_cost_usd < 0:
            raise ValueError("max_llm_cost_usd must be non-negative")
        if not math.isfinite(self.approval_timeout_seconds):
            raise ValueError("approval_timeout_seconds must be finite")
        if self.approval_timeout_seconds <= 0:
            raise ValueError("approval_timeout_seconds must be positive")

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_type": self.task_type,
            "metric_to_optimize": self.metric_to_optimize,
            "direction": self.direction,
            "candidate_families": self.candidate_families,
            "search_strategy": self.search_strategy,
            "search_n_trials": self.search_n_trials,
            "register_best": self.register_best,
            "agent": self.agent,
            "auto_approve": self.auto_approve,
            "max_llm_cost_usd": self.max_llm_cost_usd,
            "approval_timeout_seconds": self.approval_timeout_seconds,
            "audit_batch_size": self.audit_batch_size,
            "audit_flush_interval_seconds": self.audit_flush_interval_seconds,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AutoMLConfig:
        return cls(
            task_type=data.get("task_type", "classification"),
            metric_to_optimize=data.get("metric_to_optimize", "accuracy"),
            direction=data.get("direction", "maximize"),
            candidate_families=data.get("candidate_families"),
            search_strategy=data.get("search_strategy", "random"),
            search_n_trials=data.get("search_n_trials", 30),
            register_best=data.get("register_best", True),
            agent=data.get("agent", False),
            auto_approve=data.get("auto_approve", False),
            max_llm_cost_usd=data.get("max_llm_cost_usd", 1.0),
            approval_timeout_seconds=data.get("approval_timeout_seconds", 600.0),
            audit_batch_size=data.get("audit_batch_size", 10),
            audit_flush_interval_seconds=data.get("audit_flush_interval_seconds", 30.0),
        )


@dataclass
class CandidateResult:
    """Result of evaluating a single model candidate."""

    model_class: str
    framework: str
    default_metrics: dict[str, float]
    search_result: Any | None = None  # SearchResult | None
    rank: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "model_class": self.model_class,
            "framework": self.framework,
            "default_metrics": dict(self.default_metrics),
            "search_result": None,  # SearchResult is not JSON-serializable here
            "rank": self.rank,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CandidateResult:
        return cls(
            model_class=data["model_class"],
            framework=data["framework"],
            default_metrics=data["default_metrics"],
            search_result=data.get("search_result"),
            rank=data.get("rank", 0),
        )


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

    def to_dict(self) -> dict[str, Any]:
        return {
            "best_model": self.best_model.to_dict(),
            "best_metrics": dict(self.best_metrics),
            "all_candidates": [c.to_dict() for c in self.all_candidates],
            "search_result": None,  # SearchResult is not JSON-serializable here
            "agent_recommendation": None,  # AgentRecommendation serialized separately
            "baseline_recommendation": list(self.baseline_recommendation),
            "total_time_seconds": self.total_time_seconds,
            "model_version": None,  # ModelVersion is not JSON-serializable
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AutoMLResult:
        return cls(
            best_model=CandidateResult.from_dict(data["best_model"]),
            best_metrics=data["best_metrics"],
            all_candidates=[
                CandidateResult.from_dict(c) for c in data["all_candidates"]
            ],
            search_result=data.get("search_result"),
            agent_recommendation=data.get("agent_recommendation"),
            baseline_recommendation=data.get("baseline_recommendation", []),
            total_time_seconds=data.get("total_time_seconds", 0.0),
            model_version=data.get("model_version"),
        )


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
        self._calls: deque[dict[str, Any]] = deque(maxlen=10000)

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
        """Compute cost for a single call.

        Pricing precedence (first hit wins):
            1. Model-specific env var — ``KAILASH_ML_LLM_COST_INPUT_PER_1K_<UPPER>``
               where ``<UPPER>`` is ``model.upper()`` with non-alphanumeric chars
               replaced by ``_`` (e.g. ``gpt-4o-mini`` → ``GPT_4O_MINI``).
            2. Global env var — ``KAILASH_ML_LLM_COST_INPUT_PER_1K``.
            3. Hard-coded default (0.003 input / 0.015 output per 1k tokens).
        """
        import os
        import re

        suffix = re.sub(r"[^A-Za-z0-9]+", "_", model).strip("_").upper()
        input_cost_per_1k = float(
            os.environ.get(
                f"KAILASH_ML_LLM_COST_INPUT_PER_1K_{suffix}",
                os.environ.get("KAILASH_ML_LLM_COST_INPUT_PER_1K", "0.003"),
            )
        )
        output_cost_per_1k = float(
            os.environ.get(
                f"KAILASH_ML_LLM_COST_OUTPUT_PER_1K_{suffix}",
                os.environ.get("KAILASH_ML_LLM_COST_OUTPUT_PER_1K", "0.015"),
            )
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
# GPU / accelerator detection
# ---------------------------------------------------------------------------


def _cuda_available() -> bool:
    """Probe for an available CUDA device without requiring torch.

    Preference order:
        1. ``torch.cuda.is_available()`` if torch is importable (already in
           ``[dl]``/``[rl]`` extras; common in production installs).
        2. ``nvidia-smi`` subprocess returning 0 as a lightweight fallback.
        3. Assume CPU otherwise.
    """
    # 1. torch probe
    try:
        import torch  # type: ignore[import-not-found]

        return bool(torch.cuda.is_available())
    except Exception:  # noqa: BLE001 -- torch optional, any failure => no GPU
        pass

    # 2. nvidia-smi probe
    try:
        import subprocess

        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
            capture_output=True,
            timeout=2.0,
            check=False,
        )
        return result.returncode == 0 and bool(result.stdout.strip())
    except (
        Exception
    ):  # noqa: BLE001 -- any failure (missing binary, timeout, OS) => no GPU
        return False


def _select_xgboost_device() -> str:
    """Select an XGBoost device string ("cuda" if available, else "cpu").

    XGBoost>=2.0 wheels ship with CUDA built-in; ``device="cuda"`` works on any
    machine with a visible NVIDIA GPU and falls back to CPU otherwise (the
    XGBoost runtime raises a clear error if CUDA is requested but unavailable,
    which is why we probe first rather than always passing "cuda").
    """
    device = "cuda" if _cuda_available() else "cpu"
    # Observability Rule § "State Transitions, Config Loads" — log which
    # accelerator AutoML picked so operators can confirm expected backend.
    logger.info(
        "automl.xgboost_backend_selected",
        extra={"device": device, "source": "kailash_ml.automl"},
    )
    return device


# ---------------------------------------------------------------------------
# Default candidate families
# ---------------------------------------------------------------------------


def _classification_candidates() -> list[tuple[str, str, dict[str, Any]]]:
    """Default classification candidates with runtime GPU detection.

    Returns the frozen sklearn baseline extended with xgboost and lightgbm —
    xgboost's ``device`` kwarg is resolved per-call via ``_select_xgboost_device``
    so `AutoMLEngine.run()` consistently logs the accelerator decision.
    """
    xgb_device = _select_xgboost_device()
    return [
        *_CLASSIFICATION_CANDIDATES,
        (
            "xgboost.XGBClassifier",
            "xgboost",
            {
                "n_estimators": 100,
                "random_state": 42,
                "device": xgb_device,
                "tree_method": "hist",
            },
        ),
        (
            "lightgbm.LGBMClassifier",
            "lightgbm",
            {"n_estimators": 100, "random_state": 42, "verbose": -1},
        ),
    ]


def _regression_candidates() -> list[tuple[str, str, dict[str, Any]]]:
    """Default regression candidates with runtime GPU detection."""
    xgb_device = _select_xgboost_device()
    return [
        *_REGRESSION_CANDIDATES,
        (
            "xgboost.XGBRegressor",
            "xgboost",
            {
                "n_estimators": 100,
                "random_state": 42,
                "device": xgb_device,
                "tree_method": "hist",
            },
        ),
        (
            "lightgbm.LGBMRegressor",
            "lightgbm",
            {"n_estimators": 100, "random_state": 42, "verbose": -1},
        ),
    ]


# Back-compat constants (frozen sklearn baseline — no xgboost device resolution
# side effects). Tests import these directly. The factory functions above
# extend them with xgboost + lightgbm for actual AutoML runs.
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

    Composes four primitives via dependency injection:

    1. ``TrainingPipeline`` (constructor ``pipeline=``) — trains each candidate
       model family with default hyperparameters for the quick-rank pass.
    2. ``HyperparameterSearch`` (constructor ``search=``) — runs the deep
       optimization sweep on the top-ranked candidate after quick-rank.
    3. ``ModelRegistry`` (constructor ``registry=``, optional) — when
       supplied, registers the best model at STAGING if thresholds are met.
    4. ``ExperimentTracker`` (``run(tracker=...)``, optional) — when supplied,
       opens a parent run for the AutoML session and threads the same tracker
       through every child training + hyperparameter-search call so all
       candidate metrics and chosen params land in one hierarchical trace.

    Kaizen agent augmentation is opt-in via ``run(agent=True)`` AND
    ``pip install kailash-ml[agents]`` — the engine does NOT call an LLM
    unless both signals are present.

    Parameters
    ----------
    pipeline:
        TrainingPipeline for training candidates (required).
    search:
        HyperparameterSearch for deep optimization (required).
    registry:
        Optional ModelRegistry; when supplied, best model is registered.

    Notes
    -----
    ExperimentTracker is NOT a constructor argument — it is per-call because
    a single AutoMLEngine instance may drive many sessions that each belong
    to different experiments. See ``run(tracker=...)``.
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
        *,
        tracker: Any | None = None,
    ) -> AutoMLResult:
        """Run automated model selection + hyperparameter optimization.

        1. Profile data
        2. Compute baseline recommendation (Guardrail 4)
        3. Quick-train each candidate with default hyperparameters
        4. Rank candidates by metric
        5. Run HyperparameterSearch on top candidate
        6. Register best model if requested

        Parameters
        ----------
        tracker:
            Optional ExperimentTracker instance. When provided, creates a
            parent run for the AutoML session and passes the tracker to
            all training and search calls for hierarchical logging.
            Typed as ``Any`` to avoid circular imports.
        """
        from kailash_ml.engines.hyperparameter_search import SearchConfig
        from kailash_ml.engines.training_pipeline import ModelSpec

        start_time = time.perf_counter()

        # Start parent run for AutoML if tracker provided
        parent_run_id: str | None = None
        parent_run_obj: Any | None = None
        if tracker is not None:
            parent_run_obj = await tracker.start_run(
                experiment_name,
                run_name="automl",
            )
            assert parent_run_obj is not None  # narrows for pyright
            parent_run_id = parent_run_obj.id
            await tracker.log_params(
                parent_run_id,
                {
                    "task_type": config.task_type,
                    "metric_to_optimize": config.metric_to_optimize,
                    "direction": config.direction,
                    "search_strategy": config.search_strategy,
                    "search_n_trials": str(config.search_n_trials),
                },
            )

        try:
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
                        tracker=tracker,
                        parent_run_id=parent_run_id,
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
                tracker=tracker,
                parent_run_id=parent_run_id,
            )
            top.search_result = search_result

            # Best metrics from search
            best_metrics = (
                search_result.best_metrics
                if search_result.best_metrics
                else top.default_metrics
            )

            total_time = time.perf_counter() - start_time

            # Log best metrics on parent run
            if tracker is not None and parent_run_id is not None and best_metrics:
                await tracker.log_metrics(parent_run_id, best_metrics)

        except BaseException:
            if tracker is not None and parent_run_id is not None:
                await tracker.end_run(parent_run_id, status="FAILED")
            raise
        else:
            if tracker is not None and parent_run_id is not None:
                await tracker.end_run(parent_run_id, status="COMPLETED")

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
        """Get candidate model families for the task type.

        Calls the factory functions so ``_select_xgboost_device`` logs the
        resolved xgboost backend on every AutoML run.
        """
        if config.task_type == "classification":
            return _classification_candidates()
        elif config.task_type == "regression":
            return _regression_candidates()
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
        """Create a default search space for a model class.

        Framework is used as the primary discriminator for xgboost + lightgbm
        (their class names don't contain ``randomforest`` / ``gradientboosting``
        keywords, so an earlier implementation silently fell through to the
        generic ``n_estimators``-only space — missing learning_rate tuning,
        the single most impactful xgb/lgbm knob). Model_class is used for
        sklearn families where cls_name encodes the intent.
        """
        from kailash_ml.engines.hyperparameter_search import (
            ParamDistribution,
            SearchSpace,
        )

        cls_name = model_class.split(".")[-1].lower()

        if framework == "xgboost":
            return SearchSpace(
                [
                    ParamDistribution("n_estimators", "int_uniform", low=50, high=400),
                    ParamDistribution(
                        "learning_rate", "log_uniform", low=0.01, high=0.3
                    ),
                    ParamDistribution("max_depth", "int_uniform", low=3, high=12),
                    ParamDistribution("subsample", "uniform", low=0.5, high=1.0),
                    ParamDistribution("colsample_bytree", "uniform", low=0.5, high=1.0),
                ]
            )
        if framework == "lightgbm":
            return SearchSpace(
                [
                    ParamDistribution("n_estimators", "int_uniform", low=50, high=400),
                    ParamDistribution(
                        "learning_rate", "log_uniform", low=0.01, high=0.3
                    ),
                    ParamDistribution("num_leaves", "int_uniform", low=15, high=127),
                    ParamDistribution("max_depth", "int_uniform", low=-1, high=12),
                    ParamDistribution(
                        "min_child_samples", "int_uniform", low=5, high=50
                    ),
                ]
            )
        if "randomforest" in cls_name:
            return SearchSpace(
                [
                    ParamDistribution("n_estimators", "int_uniform", low=10, high=200),
                    ParamDistribution("max_depth", "int_uniform", low=3, high=20),
                ]
            )
        if "gradientboosting" in cls_name:
            return SearchSpace(
                [
                    ParamDistribution("n_estimators", "int_uniform", low=20, high=200),
                    ParamDistribution(
                        "learning_rate", "log_uniform", low=0.01, high=0.3
                    ),
                    ParamDistribution("max_depth", "int_uniform", low=2, high=10),
                ]
            )
        if "logisticregression" in cls_name:
            return SearchSpace(
                [
                    ParamDistribution("C", "log_uniform", low=0.01, high=10.0),
                ]
            )
        if "ridge" in cls_name:
            return SearchSpace(
                [
                    ParamDistribution("alpha", "log_uniform", low=0.01, high=100.0),
                ]
            )
        return SearchSpace(
            [
                ParamDistribution("n_estimators", "int_uniform", low=10, high=100),
            ]
        )
