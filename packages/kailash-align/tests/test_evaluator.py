# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tests for AlignmentEvaluator (ALN-300)."""
from __future__ import annotations

import sys
from types import ModuleType
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from kailash_align.config import EvalConfig, QUICK_TASKS, STANDARD_TASKS
from kailash_align.evaluator import (
    AlignmentEvaluator,
    EvalResult,
    TaskResult,
    _resolve_tasks,
)
from kailash_align.exceptions import EvaluationError


# --- TaskResult tests ---


class TestTaskResult:
    def test_to_dict(self):
        tr = TaskResult(
            task_name="arc_easy",
            metrics={"acc,none": 0.72, "acc_stderr,none": 0.01},
            num_samples=100,
            task_version="1",
        )
        d = tr.to_dict()
        assert d["task_name"] == "arc_easy"
        assert d["metrics"]["acc,none"] == 0.72
        assert d["num_samples"] == 100
        assert d["task_version"] == "1"

    def test_from_dict(self):
        data = {
            "task_name": "hellaswag",
            "metrics": {"acc,none": 0.85},
            "num_samples": 50,
            "task_version": "2",
        }
        tr = TaskResult.from_dict(data)
        assert tr.task_name == "hellaswag"
        assert tr.metrics["acc,none"] == 0.85
        assert tr.num_samples == 50

    def test_to_dict_none_version(self):
        tr = TaskResult(task_name="test", metrics={"acc": 0.5}, num_samples=10)
        d = tr.to_dict()
        assert d["task_version"] is None


# --- EvalResult tests ---


class TestEvalResult:
    def test_to_dict(self):
        result = EvalResult(
            adapter_name="my-adapter",
            adapter_version="1",
            task_results=[
                TaskResult(
                    task_name="arc_easy",
                    metrics={"acc,none": 0.72},
                    num_samples=100,
                ),
            ],
            eval_config={"tasks": ["arc_easy"], "limit": 100},
            total_duration_seconds=120.5,
        )
        d = result.to_dict()
        assert d["adapter_name"] == "my-adapter"
        assert d["adapter_version"] == "1"
        assert len(d["task_results"]) == 1
        assert d["total_duration_seconds"] == 120.5

    def test_from_dict(self):
        data = {
            "adapter_name": "test",
            "adapter_version": "2",
            "task_results": [
                {
                    "task_name": "hellaswag",
                    "metrics": {"acc,none": 0.85},
                    "num_samples": 50,
                }
            ],
            "eval_config": {"tasks": ["hellaswag"]},
            "total_duration_seconds": 60.0,
        }
        result = EvalResult.from_dict(data)
        assert result.adapter_name == "test"
        assert len(result.task_results) == 1
        assert result.task_results[0].task_name == "hellaswag"

    def test_summary_property(self):
        result = EvalResult(
            adapter_name="test",
            adapter_version="1",
            task_results=[
                TaskResult(
                    task_name="arc_easy",
                    metrics={"acc,none": 0.72, "acc_stderr,none": 0.01},
                    num_samples=100,
                ),
                TaskResult(
                    task_name="hellaswag",
                    metrics={"acc,none": 0.85},
                    num_samples=100,
                ),
                TaskResult(
                    task_name="custom_task",
                    metrics={"f1": 0.90},  # No "acc" metric
                    num_samples=100,
                ),
            ],
            eval_config={},
            total_duration_seconds=60.0,
        )
        summary = result.summary
        assert summary["arc_easy"] == 0.72
        assert summary["hellaswag"] == 0.85
        assert "custom_task" not in summary  # No acc metric

    def test_summary_empty_tasks(self):
        result = EvalResult(
            adapter_name="test",
            adapter_version="1",
            task_results=[],
            eval_config={},
            total_duration_seconds=0.0,
        )
        assert result.summary == {}


# --- EvalConfig tests ---


class TestEvalConfig:
    def test_defaults(self):
        config = EvalConfig()
        assert config.tasks == ("arc_easy", "hellaswag", "truthfulqa_mc1")
        assert config.limit == 100
        assert config.batch_size == "auto"
        assert config.num_fewshot is None
        assert config.device is None
        assert config.local_files_only is False
        assert config.use_adapter is True

    def test_limit_validation(self):
        with pytest.raises(ValueError, match="limit must be >= 1"):
            EvalConfig(limit=0)
        with pytest.raises(ValueError, match="limit must be >= 1"):
            EvalConfig(limit=-1)

    def test_valid_limit(self):
        config = EvalConfig(limit=1)
        assert config.limit == 1
        config = EvalConfig(limit=1000)
        assert config.limit == 1000

    def test_custom_tasks(self):
        config = EvalConfig(tasks=("mmlu", "winogrande"))
        assert config.tasks == ("mmlu", "winogrande")


# --- Task resolution tests ---


class TestResolveTask:
    def test_quick_preset(self):
        assert _resolve_tasks(("quick",)) == list(QUICK_TASKS)
        assert _resolve_tasks(["quick"]) == list(QUICK_TASKS)

    def test_standard_preset(self):
        assert _resolve_tasks(("standard",)) == list(STANDARD_TASKS)

    def test_explicit_tasks_passthrough(self):
        tasks = ("mmlu", "winogrande")
        assert _resolve_tasks(tasks) == ["mmlu", "winogrande"]

    def test_quick_preset_contents(self):
        resolved = _resolve_tasks(["quick"])
        assert "arc_easy" in resolved
        assert "hellaswag" in resolved
        assert "truthfulqa_mc1" in resolved
        assert len(resolved) == 3


# --- AlignmentEvaluator tests ---


class TestAlignmentEvaluator:
    @pytest.mark.asyncio
    async def test_evaluate_raises_import_error_without_lm_eval(self):
        """lm-eval is optional; ImportError with install instructions if missing."""
        evaluator = AlignmentEvaluator()
        with pytest.raises(ImportError, match="pip install kailash-align\\[eval\\]"):
            await evaluator.evaluate("test-adapter")

    @pytest.mark.asyncio
    async def test_evaluate_with_mocked_lm_eval(
        self, adapter_registry, sample_signature
    ):
        """Test evaluate() with mocked lm-eval simple_evaluate."""
        # Register an adapter first
        await adapter_registry.register_adapter(
            name="test-adapter",
            adapter_path="/path/to/adapter",
            signature=sample_signature,
        )

        # Create a mock lm_eval module
        mock_lm_eval = ModuleType("lm_eval")
        mock_simple_evaluate = MagicMock(
            return_value={
                "results": {
                    "arc_easy": {
                        "acc,none": 0.72,
                        "acc_stderr,none": 0.01,
                        "alias": "arc_easy",
                    },
                    "hellaswag": {
                        "acc,none": 0.65,
                        "acc_stderr,none": 0.02,
                        "alias": "hellaswag",
                    },
                },
                "versions": {
                    "arc_easy": "1",
                    "hellaswag": "1",
                },
            }
        )
        mock_lm_eval.simple_evaluate = mock_simple_evaluate

        with patch.dict(sys.modules, {"lm_eval": mock_lm_eval}):
            evaluator = AlignmentEvaluator(adapter_registry=adapter_registry)
            config = EvalConfig(
                tasks=("arc_easy", "hellaswag"),
                limit=10,
            )
            result = await evaluator.evaluate("test-adapter", config=config)

        assert isinstance(result, EvalResult)
        assert result.adapter_name == "test-adapter"
        assert result.adapter_version == "1"
        assert len(result.task_results) == 2
        assert result.total_duration_seconds >= 0

        # Verify task results
        task_names = {tr.task_name for tr in result.task_results}
        assert "arc_easy" in task_names
        assert "hellaswag" in task_names

        # Verify summary
        summary = result.summary
        assert summary["arc_easy"] == 0.72
        assert summary["hellaswag"] == 0.65

    @pytest.mark.asyncio
    async def test_evaluate_stores_results_in_registry(
        self, adapter_registry, sample_signature
    ):
        """Test that evaluate() stores results back in AdapterRegistry."""
        await adapter_registry.register_adapter(
            name="test-store",
            adapter_path="/path/to/adapter",
            signature=sample_signature,
        )

        mock_lm_eval = ModuleType("lm_eval")
        mock_lm_eval.simple_evaluate = MagicMock(
            return_value={
                "results": {
                    "arc_easy": {"acc,none": 0.72},
                },
                "versions": {},
            }
        )

        with patch.dict(sys.modules, {"lm_eval": mock_lm_eval}):
            evaluator = AlignmentEvaluator(adapter_registry=adapter_registry)
            await evaluator.evaluate("test-store")

        # Verify results were stored in registry
        adapter = await adapter_registry.get_adapter("test-store")
        assert adapter.eval_results is not None
        assert "task_results" in adapter.eval_results

    def test_build_comparison(self):
        evaluator = AlignmentEvaluator()
        a = EvalResult(
            adapter_name="adapter-a",
            adapter_version="1",
            task_results=[
                TaskResult("arc_easy", {"acc,none": 0.72}, 100),
                TaskResult("hellaswag", {"acc,none": 0.65}, 100),
            ],
            eval_config={},
            total_duration_seconds=60.0,
        )
        b = EvalResult(
            adapter_name="adapter-b",
            adapter_version="2",
            task_results=[
                TaskResult("arc_easy", {"acc,none": 0.80}, 100),
                TaskResult("hellaswag", {"acc,none": 0.70}, 100),
            ],
            eval_config={},
            total_duration_seconds=60.0,
        )
        comparison = evaluator._build_comparison(a, b)
        assert comparison["adapter_a"]["name"] == "adapter-a"
        assert comparison["adapter_b"]["name"] == "adapter-b"
        assert comparison["per_task"]["arc_easy"]["delta"] == pytest.approx(0.08)
        assert comparison["per_task"]["hellaswag"]["delta"] == pytest.approx(0.05)
        assert comparison["average_delta"] == pytest.approx(0.065)

    def test_build_comparison_missing_task(self):
        evaluator = AlignmentEvaluator()
        a = EvalResult(
            adapter_name="a",
            adapter_version="1",
            task_results=[TaskResult("arc_easy", {"acc,none": 0.72}, 100)],
            eval_config={},
            total_duration_seconds=0,
        )
        b = EvalResult(
            adapter_name="b",
            adapter_version="1",
            task_results=[TaskResult("hellaswag", {"acc,none": 0.85}, 100)],
            eval_config={},
            total_duration_seconds=0,
        )
        comparison = evaluator._build_comparison(a, b)
        # Tasks not in common have None delta
        assert comparison["per_task"]["arc_easy"]["delta"] is None
        assert comparison["per_task"]["hellaswag"]["delta"] is None
        assert comparison["average_delta"] is None
