# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""AlignmentEvaluator: benchmark evaluation for fine-tuned models.

Wraps lm-eval-harness for standardized benchmarks and supports custom
evaluation via transformers.pipeline. Results stored in AdapterRegistry.
lm-eval is an OPTIONAL dependency ([eval] extra).
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from kailash_align.config import QUICK_TASKS, STANDARD_TASKS, EvalConfig
from kailash_align.exceptions import EvaluationError

logger = logging.getLogger(__name__)

__all__ = ["AlignmentEvaluator", "EvalResult", "TaskResult"]


@dataclass
class TaskResult:
    """Result for a single evaluation task."""

    task_name: str
    metrics: dict[str, float]
    num_samples: int
    task_version: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_name": self.task_name,
            "metrics": self.metrics,
            "num_samples": self.num_samples,
            "task_version": self.task_version,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TaskResult:
        return cls(
            task_name=data["task_name"],
            metrics=data["metrics"],
            num_samples=data["num_samples"],
            task_version=data.get("task_version"),
        )


@dataclass
class EvalResult:
    """Complete evaluation result across all tasks."""

    adapter_name: str
    adapter_version: Optional[str]
    task_results: list[TaskResult]
    eval_config: dict[str, Any]
    total_duration_seconds: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "adapter_name": self.adapter_name,
            "adapter_version": self.adapter_version,
            "task_results": [t.to_dict() for t in self.task_results],
            "eval_config": self.eval_config,
            "total_duration_seconds": self.total_duration_seconds,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EvalResult:
        return cls(
            adapter_name=data["adapter_name"],
            adapter_version=data.get("adapter_version"),
            task_results=[TaskResult.from_dict(t) for t in data["task_results"]],
            eval_config=data["eval_config"],
            total_duration_seconds=data["total_duration_seconds"],
        )

    @property
    def summary(self) -> dict[str, float]:
        """Quick summary: task_name -> primary metric value.

        Uses the first metric containing 'acc' as the primary metric for each task.
        """
        result: dict[str, float] = {}
        for tr in self.task_results:
            for key, value in tr.metrics.items():
                if "acc" in key:
                    result[tr.task_name] = value
                    break
        return result


def _resolve_tasks(tasks: tuple[str, ...] | list[str]) -> list[str]:
    """Resolve task presets ('quick', 'standard') to actual task lists."""
    task_list = list(tasks)
    if task_list == ["quick"]:
        return list(QUICK_TASKS)
    if task_list == ["standard"]:
        return list(STANDARD_TASKS)
    return task_list


class AlignmentEvaluator:
    """Evaluates fine-tuned models using lm-eval-harness and custom evaluations.

    lm-eval-harness is an OPTIONAL dependency ([eval] extra). Standard benchmarks
    require it. Custom evaluation via transformers.pipeline does NOT require lm-eval.

    Args:
        adapter_registry: AdapterRegistry for looking up adapter metadata.
    """

    def __init__(
        self,
        adapter_registry: Any = None,
        onprem_config: Any = None,
    ) -> None:
        self._registry = adapter_registry
        self._onprem = onprem_config

    async def evaluate(
        self,
        adapter_name: str,
        version: Optional[str] = None,
        config: Optional[EvalConfig] = None,
    ) -> EvalResult:
        """Run standard benchmarks on an adapter via lm-eval-harness.

        Requires lm-eval to be installed (pip install kailash-align[eval]).

        Uses simple_evaluate() from lm-eval which handles model loading,
        task selection, batch evaluation, and result aggregation.

        Args:
            adapter_name: Name of adapter in registry.
            version: Specific version (None = latest).
            config: EvalConfig (defaults to quick preset with limit=100).

        Returns:
            EvalResult with per-task metrics.

        Raises:
            ImportError: If lm-eval is not installed.
            EvaluationError: If evaluation fails.
        """
        try:
            from lm_eval import simple_evaluate  # noqa: F401
        except ImportError as exc:
            raise ImportError(
                "lm-eval-harness is required for standard benchmarks. "
                "Install with: pip install kailash-align[eval]"
            ) from exc

        config = config or EvalConfig()
        tasks = _resolve_tasks(config.tasks)

        # Get adapter info from registry
        adapter_version_str: Optional[str] = None
        model_args: dict[str, str] = {}
        if self._registry is not None:
            av = await self._registry.get_adapter(adapter_name, version)
            adapter_version_str = av.version
            model_args["pretrained"] = av.base_model_id
            if config.use_adapter and av.merge_status == "separate":
                model_args["peft"] = av.adapter_path
            elif av.merge_status == "merged" and av.merged_model_path:
                model_args["pretrained"] = av.merged_model_path

        start = time.monotonic()

        try:
            results = simple_evaluate(
                model="hf",
                model_args=model_args,
                tasks=tasks,
                limit=config.limit,
                batch_size=config.batch_size,
                num_fewshot=config.num_fewshot,
                device=config.device,
            )
        except Exception as exc:
            raise EvaluationError(f"Evaluation failed: {exc}") from exc

        duration = time.monotonic() - start

        # Parse results
        task_results: list[TaskResult] = []
        for task_name, task_metrics in results.get("results", {}).items():
            task_results.append(
                TaskResult(
                    task_name=task_name,
                    metrics={
                        k: v
                        for k, v in task_metrics.items()
                        if isinstance(v, (int, float))
                    },
                    num_samples=config.limit or 0,
                    task_version=results.get("versions", {}).get(task_name),
                )
            )

        eval_result = EvalResult(
            adapter_name=adapter_name,
            adapter_version=adapter_version_str,
            task_results=task_results,
            eval_config={
                "tasks": tasks,
                "limit": config.limit,
                "batch_size": config.batch_size,
            },
            total_duration_seconds=duration,
        )

        # Update AdapterRegistry with eval results
        if self._registry is not None and adapter_version_str is not None:
            await self._registry.update_eval_results(
                adapter_name,
                adapter_version_str,
                eval_result.to_dict(),
            )

        logger.info(
            "Evaluation complete for %s v%s: %d tasks in %.1fs",
            adapter_name,
            adapter_version_str,
            len(task_results),
            duration,
        )
        return eval_result

    async def evaluate_custom(
        self,
        adapter_name: str,
        dataset: Any,
        scoring_fn: Callable[..., dict[str, float]],
        version: Optional[str] = None,
        batch_size: int = 8,
    ) -> EvalResult:
        """Run custom evaluation using transformers.pipeline (not lm-eval).

        Does NOT require lm-eval to be installed.

        Args:
            adapter_name: Name of adapter in registry.
            dataset: HuggingFace Dataset with input column.
            scoring_fn: Callable(predictions, references) -> dict of metrics.
            version: Specific version (None = latest).
            batch_size: Inference batch size.

        Returns:
            EvalResult with custom task metrics.

        Raises:
            EvaluationError: If evaluation fails.
        """
        from transformers import pipeline as hf_pipeline

        # Get adapter info from registry
        adapter_version_str: Optional[str] = None
        model_path: Optional[str] = None
        if self._registry is not None:
            av = await self._registry.get_adapter(adapter_name, version)
            adapter_version_str = av.version
            if av.merge_status == "merged" and av.merged_model_path:
                model_path = av.merged_model_path
            else:
                model_path = av.adapter_path
        else:
            model_path = adapter_name

        start = time.monotonic()

        try:
            pipe = hf_pipeline(
                "text-generation",
                model=model_path,
                batch_size=batch_size,
                trust_remote_code=False,
            )

            # Extract input texts from dataset
            text_column = None
            for col in ("text", "input", "prompt", "question"):
                if col in dataset.column_names:
                    text_column = col
                    break
            if text_column is None:
                text_column = dataset.column_names[0]

            inputs = dataset[text_column]
            predictions = []
            for i in range(0, len(inputs), batch_size):
                batch = inputs[i : i + batch_size]
                outputs = pipe(batch, max_new_tokens=128, do_sample=False)
                for output in outputs:
                    predictions.append(output[0]["generated_text"])

            # Score using provided scoring function
            references_col = None
            for col in ("label", "answer", "reference", "target"):
                if col in dataset.column_names:
                    references_col = col
                    break

            references = dataset[references_col] if references_col else None
            metrics = scoring_fn(predictions, references)

        except Exception as exc:
            raise EvaluationError(f"Custom evaluation failed: {exc}") from exc

        duration = time.monotonic() - start

        task_results = [
            TaskResult(
                task_name="custom",
                metrics=metrics,
                num_samples=len(dataset),
            )
        ]

        eval_result = EvalResult(
            adapter_name=adapter_name,
            adapter_version=adapter_version_str,
            task_results=task_results,
            eval_config={
                "tasks": ["custom"],
                "batch_size": batch_size,
                "scoring_fn": scoring_fn.__name__,
            },
            total_duration_seconds=duration,
        )

        if self._registry is not None and adapter_version_str is not None:
            await self._registry.update_eval_results(
                adapter_name,
                adapter_version_str,
                eval_result.to_dict(),
            )

        logger.info(
            "Custom evaluation complete for %s v%s in %.1fs",
            adapter_name,
            adapter_version_str,
            duration,
        )
        return eval_result

    async def compare(
        self,
        adapter_a: str,
        adapter_b: str,
        version_a: Optional[str] = None,
        version_b: Optional[str] = None,
        config: Optional[EvalConfig] = None,
    ) -> dict[str, Any]:
        """Compare two adapter versions on the same benchmarks.

        Returns dict with per-task comparison and overall delta.
        """
        result_a = await self.evaluate(adapter_a, version_a, config)
        result_b = await self.evaluate(adapter_b, version_b, config)
        return self._build_comparison(result_a, result_b)

    def _build_comparison(self, a: EvalResult, b: EvalResult) -> dict[str, Any]:
        """Build per-task comparison between two eval results."""
        summary_a = a.summary
        summary_b = b.summary

        all_tasks = set(summary_a.keys()) | set(summary_b.keys())
        per_task: dict[str, dict[str, Any]] = {}
        total_delta = 0.0
        count = 0

        for task in sorted(all_tasks):
            val_a = summary_a.get(task)
            val_b = summary_b.get(task)
            delta = None
            if val_a is not None and val_b is not None:
                delta = val_b - val_a
                total_delta += delta
                count += 1
            per_task[task] = {
                f"{a.adapter_name}": val_a,
                f"{b.adapter_name}": val_b,
                "delta": delta,
            }

        return {
            "adapter_a": {
                "name": a.adapter_name,
                "version": a.adapter_version,
            },
            "adapter_b": {
                "name": b.adapter_name,
                "version": b.adapter_version,
            },
            "per_task": per_task,
            "average_delta": total_delta / count if count > 0 else None,
        }
