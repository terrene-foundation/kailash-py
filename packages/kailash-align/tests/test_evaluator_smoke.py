# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Smoke tests for AlignmentEvaluator -- supplements test_evaluator.py.

Focuses on: quick preset task list contents, ImportError handling when
lm-eval missing, config validation edge cases.
Runs without torch/transformers/lm_eval installed.
"""
from __future__ import annotations

import sys
from types import ModuleType
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from kailash_align.config import QUICK_TASKS, STANDARD_TASKS, EvalConfig
from kailash_align.evaluator import (
    AlignmentEvaluator,
    EvalResult,
    TaskResult,
    _resolve_tasks,
)
from kailash_align.exceptions import EvaluationError


class TestQuickPresetContents:
    """Verify the quick preset contains exactly the expected tasks."""

    def test_quick_tasks_is_three(self):
        assert len(QUICK_TASKS) == 3

    def test_quick_tasks_contains_arc_easy(self):
        assert "arc_easy" in QUICK_TASKS

    def test_quick_tasks_contains_hellaswag(self):
        assert "hellaswag" in QUICK_TASKS

    def test_quick_tasks_contains_truthfulqa(self):
        assert "truthfulqa_mc1" in QUICK_TASKS

    def test_standard_is_superset_of_quick(self):
        """Every quick task should also be in the standard preset."""
        for task in QUICK_TASKS:
            assert task in STANDARD_TASKS

    def test_standard_has_mmlu(self):
        assert "mmlu" in STANDARD_TASKS


class TestImportErrorHandling:
    """Test that lm-eval missing produces a clear ImportError."""

    @pytest.mark.asyncio
    async def test_evaluate_without_lm_eval_gives_install_hint(self):
        """When lm-eval is not installed, ImportError includes pip install command."""
        evaluator = AlignmentEvaluator()
        with pytest.raises(ImportError) as exc_info:
            await evaluator.evaluate("any-adapter")
        assert "kailash-align[eval]" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_evaluate_without_lm_eval_preserves_cause(self):
        """ImportError should chain from the original ModuleNotFoundError."""
        evaluator = AlignmentEvaluator()
        with pytest.raises(ImportError) as exc_info:
            await evaluator.evaluate("test")
        assert exc_info.value.__cause__ is not None


class TestEvalConfigValidation:
    """Test edge cases in EvalConfig."""

    def test_limit_zero_raises(self):
        with pytest.raises(ValueError, match="limit must be >= 1"):
            EvalConfig(limit=0)

    def test_limit_negative_raises(self):
        with pytest.raises(ValueError, match="limit must be >= 1"):
            EvalConfig(limit=-5)

    def test_limit_one_is_valid(self):
        config = EvalConfig(limit=1)
        assert config.limit == 1

    def test_default_tasks_match_quick(self):
        """Default tasks in EvalConfig should match QUICK_TASKS."""
        config = EvalConfig()
        assert list(config.tasks) == list(QUICK_TASKS)


class TestResolveTasksEdgeCases:
    """Edge cases in _resolve_tasks beyond basic preset resolution."""

    def test_single_custom_task(self):
        result = _resolve_tasks(["mmlu"])
        assert result == ["mmlu"]

    def test_multiple_custom_tasks(self):
        result = _resolve_tasks(["mmlu", "winogrande", "arc_challenge"])
        assert result == ["mmlu", "winogrande", "arc_challenge"]

    def test_quick_as_tuple(self):
        result = _resolve_tasks(("quick",))
        assert result == list(QUICK_TASKS)

    def test_standard_as_list(self):
        result = _resolve_tasks(["standard"])
        assert result == list(STANDARD_TASKS)


class TestBuildComparison:
    """Test _build_comparison with additional edge cases."""

    def test_comparison_both_empty(self):
        evaluator = AlignmentEvaluator()
        a = EvalResult(
            adapter_name="a",
            adapter_version="1",
            task_results=[],
            eval_config={},
            total_duration_seconds=0,
        )
        b = EvalResult(
            adapter_name="b",
            adapter_version="1",
            task_results=[],
            eval_config={},
            total_duration_seconds=0,
        )
        comparison = evaluator._build_comparison(a, b)
        assert comparison["per_task"] == {}
        assert comparison["average_delta"] is None

    def test_comparison_identical_results(self):
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
            task_results=[TaskResult("arc_easy", {"acc,none": 0.72}, 100)],
            eval_config={},
            total_duration_seconds=0,
        )
        comparison = evaluator._build_comparison(a, b)
        assert comparison["average_delta"] == pytest.approx(0.0)
