# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for ExperimentTracker engine.

Uses a real SQLite database via ConnectionManager (in-memory).
"""
from __future__ import annotations

import asyncio
import math
import os
import tempfile
from pathlib import Path

import pytest

from kailash.db.connection import ConnectionManager
from kailash_ml.engines.experiment_tracker import (
    Experiment,
    ExperimentNotFoundError,
    ExperimentTracker,
    MetricEntry,
    Run,
    RunComparison,
    RunContext,
    RunNotFoundError,
    _validate_artifact_path,
    _validate_metric_value,
    _validate_status,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def conn():
    """Real SQLite ConnectionManager for unit tests."""
    cm = ConnectionManager("sqlite://:memory:")
    await cm.initialize()
    yield cm
    await cm.close()


@pytest.fixture
async def tracker(conn: ConnectionManager, tmp_path: Path) -> ExperimentTracker:
    """ExperimentTracker backed by real SQLite + tmp_path artifacts."""
    return ExperimentTracker(conn, artifact_root=str(tmp_path / "mlartifacts"))


@pytest.fixture
def sample_file(tmp_path: Path) -> Path:
    """Create a sample file for artifact logging."""
    p = tmp_path / "model.pkl"
    p.write_bytes(b"fake-model-bytes-12345")
    return p


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------


class TestValidationHelpers:
    """Tests for standalone validation functions."""

    def test_validate_status_valid(self) -> None:
        for status in ("RUNNING", "COMPLETED", "FAILED", "KILLED"):
            _validate_status(status)  # Should not raise

    def test_validate_status_invalid(self) -> None:
        with pytest.raises(ValueError, match="Invalid status"):
            _validate_status("PAUSED")

    def test_validate_status_lowercase_rejected(self) -> None:
        with pytest.raises(ValueError, match="Invalid status"):
            _validate_status("completed")

    def test_validate_metric_value_finite(self) -> None:
        _validate_metric_value(0.0)
        _validate_metric_value(1.5)
        _validate_metric_value(-100.0)

    def test_validate_metric_value_nan_rejected(self) -> None:
        with pytest.raises(ValueError, match="finite"):
            _validate_metric_value(float("nan"))

    def test_validate_metric_value_inf_rejected(self) -> None:
        with pytest.raises(ValueError, match="finite"):
            _validate_metric_value(float("inf"))

    def test_validate_metric_value_neg_inf_rejected(self) -> None:
        with pytest.raises(ValueError, match="finite"):
            _validate_metric_value(float("-inf"))

    def test_validate_artifact_path_valid(self) -> None:
        _validate_artifact_path("model.pkl")
        _validate_artifact_path("subdir/model.pkl")
        _validate_artifact_path("a.txt")

    def test_validate_artifact_path_traversal(self) -> None:
        with pytest.raises(ValueError, match="must not contain"):
            _validate_artifact_path("../../etc/passwd")

    def test_validate_artifact_path_absolute(self) -> None:
        with pytest.raises(ValueError, match="must not"):
            _validate_artifact_path("/etc/passwd")

    def test_validate_artifact_path_null_byte(self) -> None:
        with pytest.raises(ValueError, match="null bytes"):
            _validate_artifact_path("model\x00.pkl")


# ---------------------------------------------------------------------------
# Experiment management
# ---------------------------------------------------------------------------


class TestExperimentManagement:
    """Tests for create/get/list experiments."""

    @pytest.mark.asyncio
    async def test_create_experiment(self, tracker: ExperimentTracker) -> None:
        exp_id = await tracker.create_experiment("test-exp", description="A test")
        assert isinstance(exp_id, str)
        assert len(exp_id) > 0

    @pytest.mark.asyncio
    async def test_create_experiment_idempotent(
        self, tracker: ExperimentTracker
    ) -> None:
        id1 = await tracker.create_experiment("idempotent-exp")
        id2 = await tracker.create_experiment("idempotent-exp")
        assert id1 == id2

    @pytest.mark.asyncio
    async def test_create_experiment_with_tags(
        self, tracker: ExperimentTracker
    ) -> None:
        exp_id = await tracker.create_experiment(
            "tagged-exp", tags={"env": "dev", "team": "ml"}
        )
        exp = await tracker.get_experiment("tagged-exp")
        assert exp.tags == {"env": "dev", "team": "ml"}

    @pytest.mark.asyncio
    async def test_get_experiment(self, tracker: ExperimentTracker) -> None:
        await tracker.create_experiment("get-me", description="hello")
        exp = await tracker.get_experiment("get-me")
        assert isinstance(exp, Experiment)
        assert exp.name == "get-me"
        assert exp.description == "hello"
        assert exp.created_at != ""

    @pytest.mark.asyncio
    async def test_get_experiment_not_found(self, tracker: ExperimentTracker) -> None:
        with pytest.raises(ExperimentNotFoundError, match="not found"):
            await tracker.get_experiment("nonexistent")

    @pytest.mark.asyncio
    async def test_list_experiments(self, tracker: ExperimentTracker) -> None:
        await tracker.create_experiment("exp-a")
        await tracker.create_experiment("exp-b")
        exps = await tracker.list_experiments()
        assert len(exps) == 2
        names = [e.name for e in exps]
        assert "exp-a" in names
        assert "exp-b" in names

    @pytest.mark.asyncio
    async def test_list_experiments_empty(self, tracker: ExperimentTracker) -> None:
        exps = await tracker.list_experiments()
        assert exps == []


# ---------------------------------------------------------------------------
# Run management
# ---------------------------------------------------------------------------


class TestRunManagement:
    """Tests for start/end/get/list runs."""

    @pytest.mark.asyncio
    async def test_start_run(self, tracker: ExperimentTracker) -> None:
        run = await tracker.start_run("my-exp", run_name="trial-1")
        assert isinstance(run, Run)
        assert run.status == "RUNNING"
        assert run.name == "trial-1"
        assert run.end_time is None
        assert run.params == {}
        assert run.metrics == {}
        assert run.artifacts == []

    @pytest.mark.asyncio
    async def test_start_run_auto_creates_experiment(
        self, tracker: ExperimentTracker
    ) -> None:
        run = await tracker.start_run("auto-created-exp")
        exp = await tracker.get_experiment("auto-created-exp")
        assert run.experiment_id == exp.id

    @pytest.mark.asyncio
    async def test_start_run_with_tags(self, tracker: ExperimentTracker) -> None:
        run = await tracker.start_run(
            "tag-exp", run_name="tagged", tags={"gpu": "A100"}
        )
        assert run.tags == {"gpu": "A100"}

    @pytest.mark.asyncio
    async def test_end_run_completed(self, tracker: ExperimentTracker) -> None:
        run = await tracker.start_run("end-exp")
        await tracker.end_run(run.id, status="COMPLETED")
        updated = await tracker.get_run(run.id)
        assert updated.status == "COMPLETED"
        assert updated.end_time is not None

    @pytest.mark.asyncio
    async def test_end_run_failed(self, tracker: ExperimentTracker) -> None:
        run = await tracker.start_run("fail-exp")
        await tracker.end_run(run.id, status="FAILED")
        updated = await tracker.get_run(run.id)
        assert updated.status == "FAILED"

    @pytest.mark.asyncio
    async def test_end_run_killed(self, tracker: ExperimentTracker) -> None:
        run = await tracker.start_run("kill-exp")
        await tracker.end_run(run.id, status="KILLED")
        updated = await tracker.get_run(run.id)
        assert updated.status == "KILLED"

    @pytest.mark.asyncio
    async def test_end_run_invalid_status(self, tracker: ExperimentTracker) -> None:
        run = await tracker.start_run("bad-status-exp")
        with pytest.raises(ValueError, match="Invalid status"):
            await tracker.end_run(run.id, status="PAUSED")

    @pytest.mark.asyncio
    async def test_end_run_not_found(self, tracker: ExperimentTracker) -> None:
        with pytest.raises(RunNotFoundError, match="not found"):
            await tracker.end_run("nonexistent-run-id")

    @pytest.mark.asyncio
    async def test_get_run(self, tracker: ExperimentTracker) -> None:
        run = await tracker.start_run("get-run-exp", run_name="r1")
        fetched = await tracker.get_run(run.id)
        assert fetched.id == run.id
        assert fetched.name == "r1"
        assert fetched.status == "RUNNING"

    @pytest.mark.asyncio
    async def test_get_run_not_found(self, tracker: ExperimentTracker) -> None:
        with pytest.raises(RunNotFoundError, match="not found"):
            await tracker.get_run("nonexistent")

    @pytest.mark.asyncio
    async def test_list_runs(self, tracker: ExperimentTracker) -> None:
        await tracker.start_run("list-exp", run_name="r1")
        await tracker.start_run("list-exp", run_name="r2")
        runs = await tracker.list_runs("list-exp")
        assert len(runs) == 2

    @pytest.mark.asyncio
    async def test_list_runs_filter_by_status(self, tracker: ExperimentTracker) -> None:
        r1 = await tracker.start_run("filter-exp", run_name="r1")
        r2 = await tracker.start_run("filter-exp", run_name="r2")
        await tracker.end_run(r1.id, status="COMPLETED")

        running = await tracker.list_runs("filter-exp", status="RUNNING")
        assert len(running) == 1
        assert running[0].id == r2.id

        completed = await tracker.list_runs("filter-exp", status="COMPLETED")
        assert len(completed) == 1
        assert completed[0].id == r1.id


# ---------------------------------------------------------------------------
# Parameter logging
# ---------------------------------------------------------------------------


class TestParamLogging:
    """Tests for log_param and log_params."""

    @pytest.mark.asyncio
    async def test_log_param_single(self, tracker: ExperimentTracker) -> None:
        run = await tracker.start_run("param-exp")
        await tracker.log_param(run.id, "learning_rate", "0.01")
        fetched = await tracker.get_run(run.id)
        assert fetched.params["learning_rate"] == "0.01"

    @pytest.mark.asyncio
    async def test_log_params_batch(self, tracker: ExperimentTracker) -> None:
        run = await tracker.start_run("batch-param-exp")
        await tracker.log_params(
            run.id, {"lr": "0.01", "epochs": "10", "batch_size": "32"}
        )
        fetched = await tracker.get_run(run.id)
        assert fetched.params == {"lr": "0.01", "epochs": "10", "batch_size": "32"}

    @pytest.mark.asyncio
    async def test_log_param_idempotent_upsert(
        self, tracker: ExperimentTracker
    ) -> None:
        run = await tracker.start_run("upsert-param-exp")
        await tracker.log_param(run.id, "lr", "0.01")
        await tracker.log_param(run.id, "lr", "0.001")  # Update
        fetched = await tracker.get_run(run.id)
        assert fetched.params["lr"] == "0.001"

    @pytest.mark.asyncio
    async def test_log_param_run_not_found(self, tracker: ExperimentTracker) -> None:
        with pytest.raises(RunNotFoundError, match="not found"):
            await tracker.log_param("nonexistent", "key", "val")

    @pytest.mark.asyncio
    async def test_log_params_converts_to_string(
        self, tracker: ExperimentTracker
    ) -> None:
        run = await tracker.start_run("convert-exp")
        await tracker.log_params(run.id, {"epochs": 10, "lr": 0.01})
        fetched = await tracker.get_run(run.id)
        assert fetched.params["epochs"] == "10"
        assert fetched.params["lr"] == "0.01"


# ---------------------------------------------------------------------------
# Metric logging
# ---------------------------------------------------------------------------


class TestMetricLogging:
    """Tests for log_metric and log_metrics."""

    @pytest.mark.asyncio
    async def test_log_metric_single(self, tracker: ExperimentTracker) -> None:
        run = await tracker.start_run("metric-exp")
        await tracker.log_metric(run.id, "accuracy", 0.95)
        fetched = await tracker.get_run(run.id)
        assert fetched.metrics["accuracy"] == 0.95

    @pytest.mark.asyncio
    async def test_log_metrics_batch(self, tracker: ExperimentTracker) -> None:
        run = await tracker.start_run("batch-metric-exp")
        await tracker.log_metrics(run.id, {"accuracy": 0.95, "loss": 0.05})
        fetched = await tracker.get_run(run.id)
        assert fetched.metrics["accuracy"] == 0.95
        assert fetched.metrics["loss"] == 0.05

    @pytest.mark.asyncio
    async def test_log_metric_step_based(self, tracker: ExperimentTracker) -> None:
        run = await tracker.start_run("step-metric-exp")
        await tracker.log_metric(run.id, "loss", 1.0, step=0)
        await tracker.log_metric(run.id, "loss", 0.5, step=1)
        await tracker.log_metric(run.id, "loss", 0.1, step=2)

        # get_run returns latest metric (highest step)
        fetched = await tracker.get_run(run.id)
        assert fetched.metrics["loss"] == 0.1

        # Full history available
        history = await tracker.get_metric_history(run.id, "loss")
        assert len(history) == 3
        assert history[0].value == 1.0
        assert history[0].step == 0
        assert history[2].value == 0.1
        assert history[2].step == 2

    @pytest.mark.asyncio
    async def test_log_metric_auto_step(self, tracker: ExperimentTracker) -> None:
        run = await tracker.start_run("auto-step-exp")
        await tracker.log_metric(run.id, "loss", 1.0)  # step=0
        await tracker.log_metric(run.id, "loss", 0.5)  # step=1
        await tracker.log_metric(run.id, "loss", 0.1)  # step=2

        history = await tracker.get_metric_history(run.id, "loss")
        assert len(history) == 3
        assert [h.step for h in history] == [0, 1, 2]

    @pytest.mark.asyncio
    async def test_log_metric_nan_rejected(self, tracker: ExperimentTracker) -> None:
        run = await tracker.start_run("nan-exp")
        with pytest.raises(ValueError, match="finite"):
            await tracker.log_metric(run.id, "loss", float("nan"))

    @pytest.mark.asyncio
    async def test_log_metric_inf_rejected(self, tracker: ExperimentTracker) -> None:
        run = await tracker.start_run("inf-exp")
        with pytest.raises(ValueError, match="finite"):
            await tracker.log_metric(run.id, "loss", float("inf"))

    @pytest.mark.asyncio
    async def test_log_metric_neg_inf_rejected(
        self, tracker: ExperimentTracker
    ) -> None:
        run = await tracker.start_run("neg-inf-exp")
        with pytest.raises(ValueError, match="finite"):
            await tracker.log_metric(run.id, "loss", float("-inf"))

    @pytest.mark.asyncio
    async def test_log_metric_run_not_found(self, tracker: ExperimentTracker) -> None:
        with pytest.raises(RunNotFoundError, match="not found"):
            await tracker.log_metric("nonexistent", "loss", 0.5)

    @pytest.mark.asyncio
    async def test_log_metrics_with_step(self, tracker: ExperimentTracker) -> None:
        run = await tracker.start_run("batch-step-exp")
        await tracker.log_metrics(run.id, {"loss": 0.5, "acc": 0.8}, step=5)
        history_loss = await tracker.get_metric_history(run.id, "loss")
        history_acc = await tracker.get_metric_history(run.id, "acc")
        assert history_loss[0].step == 5
        assert history_acc[0].step == 5


# ---------------------------------------------------------------------------
# Artifact logging
# ---------------------------------------------------------------------------


class TestArtifactLogging:
    """Tests for log_artifact."""

    @pytest.mark.asyncio
    async def test_log_artifact(
        self, tracker: ExperimentTracker, sample_file: Path
    ) -> None:
        run = await tracker.start_run("artifact-exp")
        await tracker.log_artifact(run.id, str(sample_file))
        fetched = await tracker.get_run(run.id)
        assert "model.pkl" in fetched.artifacts

    @pytest.mark.asyncio
    async def test_log_artifact_custom_path(
        self, tracker: ExperimentTracker, sample_file: Path
    ) -> None:
        run = await tracker.start_run("custom-path-exp")
        await tracker.log_artifact(
            run.id, str(sample_file), artifact_path="models/best.pkl"
        )
        fetched = await tracker.get_run(run.id)
        assert "models/best.pkl" in fetched.artifacts

    @pytest.mark.asyncio
    async def test_log_artifact_file_copied(
        self, tracker: ExperimentTracker, sample_file: Path, tmp_path: Path
    ) -> None:
        run = await tracker.start_run("copy-exp")
        await tracker.log_artifact(run.id, str(sample_file))
        # Verify file was actually copied
        dest = tmp_path / "mlartifacts" / run.id / "model.pkl"
        assert dest.exists()
        assert dest.read_bytes() == b"fake-model-bytes-12345"

    @pytest.mark.asyncio
    async def test_log_artifact_not_found(self, tracker: ExperimentTracker) -> None:
        run = await tracker.start_run("missing-file-exp")
        with pytest.raises(FileNotFoundError, match="not found"):
            await tracker.log_artifact(run.id, "/nonexistent/file.pkl")

    @pytest.mark.asyncio
    async def test_log_artifact_path_traversal(
        self, tracker: ExperimentTracker, sample_file: Path
    ) -> None:
        run = await tracker.start_run("traversal-exp")
        with pytest.raises(ValueError, match="must not contain"):
            await tracker.log_artifact(
                run.id, str(sample_file), artifact_path="../../etc/passwd"
            )

    @pytest.mark.asyncio
    async def test_log_artifact_run_not_found(
        self, tracker: ExperimentTracker, sample_file: Path
    ) -> None:
        with pytest.raises(RunNotFoundError, match="not found"):
            await tracker.log_artifact("nonexistent", str(sample_file))


# ---------------------------------------------------------------------------
# Tags
# ---------------------------------------------------------------------------


class TestTags:
    """Tests for set_tag."""

    @pytest.mark.asyncio
    async def test_set_tag(self, tracker: ExperimentTracker) -> None:
        run = await tracker.start_run("tag-exp")
        await tracker.set_tag(run.id, "model_type", "random_forest")
        fetched = await tracker.get_run(run.id)
        assert fetched.tags["model_type"] == "random_forest"

    @pytest.mark.asyncio
    async def test_set_tag_overwrites(self, tracker: ExperimentTracker) -> None:
        run = await tracker.start_run("overwrite-tag-exp")
        await tracker.set_tag(run.id, "stage", "dev")
        await tracker.set_tag(run.id, "stage", "prod")
        fetched = await tracker.get_run(run.id)
        assert fetched.tags["stage"] == "prod"

    @pytest.mark.asyncio
    async def test_set_tag_multiple(self, tracker: ExperimentTracker) -> None:
        run = await tracker.start_run("multi-tag-exp")
        await tracker.set_tag(run.id, "a", "1")
        await tracker.set_tag(run.id, "b", "2")
        fetched = await tracker.get_run(run.id)
        assert fetched.tags["a"] == "1"
        assert fetched.tags["b"] == "2"

    @pytest.mark.asyncio
    async def test_set_tag_run_not_found(self, tracker: ExperimentTracker) -> None:
        with pytest.raises(RunNotFoundError, match="not found"):
            await tracker.set_tag("nonexistent", "key", "val")


# ---------------------------------------------------------------------------
# Search runs
# ---------------------------------------------------------------------------


class TestSearchRuns:
    """Tests for search_runs."""

    @pytest.mark.asyncio
    async def test_search_runs_no_filter(self, tracker: ExperimentTracker) -> None:
        await tracker.start_run("search-exp", run_name="r1")
        await tracker.start_run("search-exp", run_name="r2")
        results = await tracker.search_runs("search-exp")
        assert len(results) == 2

    @pytest.mark.asyncio
    async def test_search_runs_by_param(self, tracker: ExperimentTracker) -> None:
        r1 = await tracker.start_run("search-param-exp", run_name="r1")
        r2 = await tracker.start_run("search-param-exp", run_name="r2")
        await tracker.log_param(r1.id, "model", "rf")
        await tracker.log_param(r2.id, "model", "xgb")

        results = await tracker.search_runs(
            "search-param-exp", filter_params={"model": "rf"}
        )
        assert len(results) == 1
        assert results[0].id == r1.id

    @pytest.mark.asyncio
    async def test_search_runs_by_multiple_params(
        self, tracker: ExperimentTracker
    ) -> None:
        r1 = await tracker.start_run("multi-param-exp", run_name="r1")
        r2 = await tracker.start_run("multi-param-exp", run_name="r2")
        await tracker.log_params(r1.id, {"model": "rf", "lr": "0.01"})
        await tracker.log_params(r2.id, {"model": "rf", "lr": "0.1"})

        results = await tracker.search_runs(
            "multi-param-exp", filter_params={"model": "rf", "lr": "0.01"}
        )
        assert len(results) == 1
        assert results[0].id == r1.id

    @pytest.mark.asyncio
    async def test_search_runs_max_results(self, tracker: ExperimentTracker) -> None:
        for i in range(5):
            await tracker.start_run("max-results-exp", run_name=f"r{i}")
        results = await tracker.search_runs("max-results-exp", max_results=3)
        assert len(results) == 3

    @pytest.mark.asyncio
    async def test_search_runs_order_by_metric_desc(
        self, tracker: ExperimentTracker
    ) -> None:
        r1 = await tracker.start_run("order-exp", run_name="r1")
        r2 = await tracker.start_run("order-exp", run_name="r2")
        r3 = await tracker.start_run("order-exp", run_name="r3")
        await tracker.log_metric(r1.id, "accuracy", 0.7)
        await tracker.log_metric(r2.id, "accuracy", 0.9)
        await tracker.log_metric(r3.id, "accuracy", 0.8)

        results = await tracker.search_runs(
            "order-exp", order_by="metric.accuracy DESC"
        )
        assert results[0].metrics["accuracy"] == 0.9
        assert results[1].metrics["accuracy"] == 0.8
        assert results[2].metrics["accuracy"] == 0.7

    @pytest.mark.asyncio
    async def test_search_runs_order_by_metric_asc(
        self, tracker: ExperimentTracker
    ) -> None:
        r1 = await tracker.start_run("order-asc-exp", run_name="r1")
        r2 = await tracker.start_run("order-asc-exp", run_name="r2")
        await tracker.log_metric(r1.id, "loss", 0.5)
        await tracker.log_metric(r2.id, "loss", 0.1)

        results = await tracker.search_runs("order-asc-exp", order_by="metric.loss ASC")
        assert results[0].metrics["loss"] == 0.1
        assert results[1].metrics["loss"] == 0.5


# ---------------------------------------------------------------------------
# Compare runs
# ---------------------------------------------------------------------------


class TestCompareRuns:
    """Tests for compare_runs."""

    @pytest.mark.asyncio
    async def test_compare_runs(self, tracker: ExperimentTracker) -> None:
        r1 = await tracker.start_run("compare-exp", run_name="baseline")
        r2 = await tracker.start_run("compare-exp", run_name="improved")

        await tracker.log_params(r1.id, {"model": "rf", "lr": "0.01"})
        await tracker.log_params(r2.id, {"model": "xgb", "lr": "0.1"})
        await tracker.log_metric(r1.id, "accuracy", 0.85)
        await tracker.log_metric(r2.id, "accuracy", 0.92)
        await tracker.log_metric(r1.id, "loss", 0.15)

        comparison = await tracker.compare_runs([r1.id, r2.id])

        assert isinstance(comparison, RunComparison)
        assert comparison.run_ids == [r1.id, r2.id]
        assert comparison.run_names == ["baseline", "improved"]
        assert comparison.params["model"] == ["rf", "xgb"]
        assert comparison.params["lr"] == ["0.01", "0.1"]
        assert comparison.metrics["accuracy"] == [0.85, 0.92]
        # loss only in r1
        assert comparison.metrics["loss"] == [0.15, None]

    @pytest.mark.asyncio
    async def test_compare_runs_single(self, tracker: ExperimentTracker) -> None:
        r1 = await tracker.start_run("single-compare-exp")
        await tracker.log_metric(r1.id, "f1", 0.9)
        comparison = await tracker.compare_runs([r1.id])
        assert comparison.metrics["f1"] == [0.9]


# ---------------------------------------------------------------------------
# Metric history
# ---------------------------------------------------------------------------


class TestMetricHistory:
    """Tests for get_metric_history."""

    @pytest.mark.asyncio
    async def test_get_metric_history(self, tracker: ExperimentTracker) -> None:
        run = await tracker.start_run("history-exp")
        for epoch in range(5):
            await tracker.log_metric(run.id, "loss", 1.0 / (epoch + 1), step=epoch)

        history = await tracker.get_metric_history(run.id, "loss")
        assert len(history) == 5
        assert all(isinstance(h, MetricEntry) for h in history)
        assert history[0].step == 0
        assert history[0].value == 1.0
        assert history[4].step == 4
        assert history[4].value == 0.2

    @pytest.mark.asyncio
    async def test_get_metric_history_empty(self, tracker: ExperimentTracker) -> None:
        run = await tracker.start_run("empty-history-exp")
        history = await tracker.get_metric_history(run.id, "nonexistent")
        assert history == []

    @pytest.mark.asyncio
    async def test_get_metric_history_run_not_found(
        self, tracker: ExperimentTracker
    ) -> None:
        with pytest.raises(RunNotFoundError, match="not found"):
            await tracker.get_metric_history("nonexistent", "loss")

    @pytest.mark.asyncio
    async def test_metric_history_ordered_by_step(
        self, tracker: ExperimentTracker
    ) -> None:
        run = await tracker.start_run("ordered-history-exp")
        # Log out of order
        await tracker.log_metric(run.id, "lr", 0.1, step=2)
        await tracker.log_metric(run.id, "lr", 0.01, step=0)
        await tracker.log_metric(run.id, "lr", 0.05, step=1)

        history = await tracker.get_metric_history(run.id, "lr")
        assert [h.step for h in history] == [0, 1, 2]
        assert [h.value for h in history] == [0.01, 0.05, 0.1]


# ---------------------------------------------------------------------------
# Context manager
# ---------------------------------------------------------------------------


class TestRunContext:
    """Tests for the async context manager run lifecycle."""

    @pytest.mark.asyncio
    async def test_context_manager_success(self, tracker: ExperimentTracker) -> None:
        async with tracker.run("ctx-exp", run_name="success-run") as ctx:
            assert isinstance(ctx, RunContext)
            assert ctx.run_id is not None
            await ctx.log_params({"lr": "0.01"})
            await ctx.log_metric("loss", 0.5, step=0)

        # Run should be COMPLETED
        fetched = await tracker.get_run(ctx.run_id)
        assert fetched.status == "COMPLETED"
        assert fetched.end_time is not None
        assert fetched.params["lr"] == "0.01"
        assert fetched.metrics["loss"] == 0.5

    @pytest.mark.asyncio
    async def test_context_manager_failure(self, tracker: ExperimentTracker) -> None:
        run_id = None
        with pytest.raises(ValueError, match="intentional"):
            async with tracker.run("ctx-fail-exp", run_name="fail-run") as ctx:
                run_id = ctx.run_id
                await ctx.log_metric("loss", 1.0)
                raise ValueError("intentional failure")

        assert run_id is not None
        fetched = await tracker.get_run(run_id)
        assert fetched.status == "FAILED"
        assert fetched.end_time is not None

    @pytest.mark.asyncio
    async def test_context_manager_log_artifact(
        self, tracker: ExperimentTracker, sample_file: Path
    ) -> None:
        async with tracker.run("ctx-artifact-exp") as ctx:
            await ctx.log_artifact(str(sample_file))
            await ctx.set_tag("version", "1.0")

        fetched = await tracker.get_run(ctx.run_id)
        assert "model.pkl" in fetched.artifacts
        assert fetched.tags["version"] == "1.0"

    @pytest.mark.asyncio
    async def test_context_manager_provides_run(
        self, tracker: ExperimentTracker
    ) -> None:
        async with tracker.run("ctx-run-exp", run_name="named") as ctx:
            assert ctx.run.name == "named"
            assert ctx.run.status == "RUNNING"


# ---------------------------------------------------------------------------
# Delete operations
# ---------------------------------------------------------------------------


class TestDeleteOperations:
    """Tests for delete_run and delete_experiment."""

    @pytest.mark.asyncio
    async def test_delete_run(self, tracker: ExperimentTracker) -> None:
        run = await tracker.start_run("delete-run-exp")
        await tracker.log_param(run.id, "key", "val")
        await tracker.log_metric(run.id, "loss", 0.5)
        await tracker.delete_run(run.id)

        with pytest.raises(RunNotFoundError, match="not found"):
            await tracker.get_run(run.id)

    @pytest.mark.asyncio
    async def test_delete_run_cascades_params(
        self, tracker: ExperimentTracker, conn: ConnectionManager
    ) -> None:
        run = await tracker.start_run("cascade-exp")
        await tracker.log_params(run.id, {"a": "1", "b": "2"})
        await tracker.delete_run(run.id)

        # Verify params are gone
        rows = await conn.fetch(
            "SELECT * FROM kailash_run_params WHERE run_id = ?", run.id
        )
        assert len(rows) == 0

    @pytest.mark.asyncio
    async def test_delete_run_cascades_metrics(
        self, tracker: ExperimentTracker, conn: ConnectionManager
    ) -> None:
        run = await tracker.start_run("cascade-metric-exp")
        await tracker.log_metric(run.id, "loss", 0.5)
        await tracker.log_metric(run.id, "loss", 0.3, step=1)
        await tracker.delete_run(run.id)

        rows = await conn.fetch(
            "SELECT * FROM kailash_run_metrics WHERE run_id = ?", run.id
        )
        assert len(rows) == 0

    @pytest.mark.asyncio
    async def test_delete_run_cascades_artifacts(
        self,
        tracker: ExperimentTracker,
        conn: ConnectionManager,
        sample_file: Path,
        tmp_path: Path,
    ) -> None:
        run = await tracker.start_run("cascade-artifact-exp")
        await tracker.log_artifact(run.id, str(sample_file))
        await tracker.delete_run(run.id)

        rows = await conn.fetch(
            "SELECT * FROM kailash_run_artifacts WHERE run_id = ?", run.id
        )
        assert len(rows) == 0

        # Artifact directory should be cleaned up
        artifact_dir = tmp_path / "mlartifacts" / run.id
        assert not artifact_dir.exists()

    @pytest.mark.asyncio
    async def test_delete_run_not_found(self, tracker: ExperimentTracker) -> None:
        with pytest.raises(RunNotFoundError, match="not found"):
            await tracker.delete_run("nonexistent")

    @pytest.mark.asyncio
    async def test_delete_experiment(self, tracker: ExperimentTracker) -> None:
        r1 = await tracker.start_run("delete-exp-exp", run_name="r1")
        r2 = await tracker.start_run("delete-exp-exp", run_name="r2")
        await tracker.log_metric(r1.id, "acc", 0.9)
        await tracker.log_metric(r2.id, "acc", 0.8)

        await tracker.delete_experiment("delete-exp-exp")

        with pytest.raises(ExperimentNotFoundError, match="not found"):
            await tracker.get_experiment("delete-exp-exp")

        # Runs should also be deleted
        with pytest.raises(RunNotFoundError, match="not found"):
            await tracker.get_run(r1.id)
        with pytest.raises(RunNotFoundError, match="not found"):
            await tracker.get_run(r2.id)

    @pytest.mark.asyncio
    async def test_delete_experiment_not_found(
        self, tracker: ExperimentTracker
    ) -> None:
        with pytest.raises(ExperimentNotFoundError, match="not found"):
            await tracker.delete_experiment("nonexistent")


# ---------------------------------------------------------------------------
# Concurrent experiment creation (idempotency)
# ---------------------------------------------------------------------------


class TestConcurrency:
    """Tests for concurrent operations."""

    @pytest.mark.asyncio
    async def test_concurrent_experiment_creation(
        self, tracker: ExperimentTracker
    ) -> None:
        """Multiple concurrent create_experiment calls for the same name
        should return the same ID."""
        tasks = [tracker.create_experiment(f"concurrent-exp") for _ in range(10)]
        results = await asyncio.gather(*tasks)
        # All should return the same experiment ID
        assert len(set(results)) == 1


# ---------------------------------------------------------------------------
# Dataclass serialization
# ---------------------------------------------------------------------------


class TestDataclassSerialization:
    """Tests for to_dict/from_dict on dataclasses."""

    def test_experiment_round_trip(self) -> None:
        exp = Experiment(
            id="abc",
            name="test",
            description="desc",
            created_at="2026-01-01T00:00:00",
            tags={"env": "dev"},
        )
        d = exp.to_dict()
        restored = Experiment.from_dict(d)
        assert restored == exp

    def test_run_round_trip(self) -> None:
        run = Run(
            id="run1",
            experiment_id="exp1",
            name="trial",
            status="COMPLETED",
            start_time="2026-01-01T00:00:00",
            end_time="2026-01-01T01:00:00",
            tags={"gpu": "A100"},
            params={"lr": "0.01"},
            metrics={"accuracy": 0.95},
            artifacts=["model.pkl"],
        )
        d = run.to_dict()
        restored = Run.from_dict(d)
        assert restored == run

    def test_metric_entry_round_trip(self) -> None:
        entry = MetricEntry(
            key="loss", value=0.5, step=10, timestamp="2026-01-01T00:00:00"
        )
        d = entry.to_dict()
        restored = MetricEntry.from_dict(d)
        assert restored == entry

    def test_run_comparison_to_dict(self) -> None:
        comp = RunComparison(
            run_ids=["r1", "r2"],
            run_names=["a", "b"],
            params={"lr": ["0.01", "0.1"]},
            metrics={"acc": [0.9, 0.95]},
        )
        d = comp.to_dict()
        assert d["run_ids"] == ["r1", "r2"]
        assert d["params"]["lr"] == ["0.01", "0.1"]
        assert d["metrics"]["acc"] == [0.9, 0.95]


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    @pytest.mark.asyncio
    async def test_run_with_no_name(self, tracker: ExperimentTracker) -> None:
        run = await tracker.start_run("no-name-exp")
        assert run.name == ""

    @pytest.mark.asyncio
    async def test_experiment_with_empty_description(
        self, tracker: ExperimentTracker
    ) -> None:
        await tracker.create_experiment("empty-desc-exp")
        exp = await tracker.get_experiment("empty-desc-exp")
        assert exp.description == ""

    @pytest.mark.asyncio
    async def test_get_run_with_all_data(
        self, tracker: ExperimentTracker, sample_file: Path
    ) -> None:
        """Verify get_run hydrates all child data correctly."""
        run = await tracker.start_run(
            "full-data-exp", run_name="full", tags={"env": "test"}
        )
        await tracker.log_params(run.id, {"lr": "0.01", "epochs": "10"})
        await tracker.log_metric(run.id, "loss", 1.0, step=0)
        await tracker.log_metric(run.id, "loss", 0.5, step=1)
        await tracker.log_metric(run.id, "acc", 0.9)
        await tracker.log_artifact(run.id, str(sample_file))
        await tracker.set_tag(run.id, "model_type", "rf")
        await tracker.end_run(run.id)

        fetched = await tracker.get_run(run.id)
        assert fetched.status == "COMPLETED"
        assert fetched.params == {"lr": "0.01", "epochs": "10"}
        assert fetched.metrics["loss"] == 0.5  # Latest step
        assert fetched.metrics["acc"] == 0.9
        assert "model.pkl" in fetched.artifacts
        assert fetched.tags["env"] == "test"
        assert fetched.tags["model_type"] == "rf"

    @pytest.mark.asyncio
    async def test_zero_metric_value(self, tracker: ExperimentTracker) -> None:
        run = await tracker.start_run("zero-metric-exp")
        await tracker.log_metric(run.id, "loss", 0.0)
        fetched = await tracker.get_run(run.id)
        assert fetched.metrics["loss"] == 0.0

    @pytest.mark.asyncio
    async def test_negative_metric_value(self, tracker: ExperimentTracker) -> None:
        run = await tracker.start_run("neg-metric-exp")
        await tracker.log_metric(run.id, "log_likelihood", -100.5)
        fetched = await tracker.get_run(run.id)
        assert fetched.metrics["log_likelihood"] == -100.5

    @pytest.mark.asyncio
    async def test_multiple_experiments_isolation(
        self, tracker: ExperimentTracker
    ) -> None:
        """Runs in different experiments don't mix."""
        r1 = await tracker.start_run("exp-a", run_name="r1")
        r2 = await tracker.start_run("exp-b", run_name="r2")

        runs_a = await tracker.list_runs("exp-a")
        runs_b = await tracker.list_runs("exp-b")

        assert len(runs_a) == 1
        assert runs_a[0].id == r1.id
        assert len(runs_b) == 1
        assert runs_b[0].id == r2.id


# ---------------------------------------------------------------------------
# Factory create (#317)
# ---------------------------------------------------------------------------


class TestFactoryCreate:
    """Tests for ExperimentTracker.create() factory (#317)."""

    @pytest.mark.asyncio
    async def test_create_factory(self, tmp_path: Path) -> None:
        """Factory creates a working tracker."""
        db_path = tmp_path / "test.db"
        tracker = await ExperimentTracker.create(
            f"sqlite:///{db_path}",
            artifact_root=str(tmp_path / "artifacts"),
        )
        try:
            assert tracker._owns_conn is True
            exp_name = await tracker.create_experiment("test-exp")
            assert exp_name is not None
        finally:
            await tracker.close()

    @pytest.mark.asyncio
    async def test_create_context_manager(self, tmp_path: Path) -> None:
        """Factory tracker works as async context manager."""
        db_path = tmp_path / "test.db"
        async with await ExperimentTracker.create(
            f"sqlite:///{db_path}",
            artifact_root=str(tmp_path / "artifacts"),
        ) as tracker:
            assert tracker._owns_conn is True
            exp_name = await tracker.create_experiment("ctx-exp")
            assert exp_name is not None

    @pytest.mark.asyncio
    async def test_external_conn_not_closed(self, tmp_path: Path) -> None:
        """Tracker with external conn does not close it."""
        db_path = tmp_path / "test.db"
        conn = ConnectionManager(f"sqlite:///{db_path}")
        await conn.initialize()
        try:
            tracker = ExperimentTracker(conn, artifact_root=str(tmp_path / "artifacts"))
            assert tracker._owns_conn is False
            await tracker.close()
            # Connection should still be usable
            assert conn is not None
        finally:
            await conn.close()
