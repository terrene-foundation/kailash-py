# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""W13 Tier-1 unit tests — query primitives (spec ``ml-tracking.md`` §5).

Covers:

- Filter DSL tokenisation + parsing (MLflow-compatible grammar).
- ``build_search_sql`` emits parameterised SQL (no identifier
  interpolation from user input).
- ``list_runs`` / ``search_runs`` polars returns — column shape +
  ordering.
- ``list_experiments`` summary shape (run_count / finished_count / …).
- ``list_metrics`` / ``list_artifacts`` tenant-scoped access.
- ``get_run`` returns a typed :class:`RunRecord`; cross-tenant access
  raises :class:`RunNotFoundError`.
- ``diff_runs`` returns a :class:`RunDiff` with typed
  ``reproducibility_risk`` boolean.

Uses the in-memory SQLite alias so tests run without filesystem state.
"""
from __future__ import annotations

from pathlib import Path

import polars as pl
import pytest
from kailash_ml.errors import RunNotFoundError
from kailash_ml.tracking import ExperimentTracker
from kailash_ml.tracking.query import (
    FilterParseError,
    ParamDelta,
    RunDiff,
    RunRecord,
    build_search_sql,
    compute_run_diff,
    run_record_from_row,
)


# ---------------------------------------------------------------------------
# Filter DSL — pure parser unit tests (no backend)
# ---------------------------------------------------------------------------


class TestFilterParser:
    def test_metric_equals_number(self) -> None:
        sql, params = build_search_sql(
            "metrics.loss = 0.5", tenant_id=None, order_by=None, limit=10
        )
        assert "EXISTS" in sql
        assert "experiment_metrics" in sql
        assert "m.value = ?" in sql
        # params: [key, key, value, limit] — two key bindings for the
        # correlated sub-select that picks MAX(id).
        assert params == ["loss", "loss", 0.5, 10]

    def test_param_string_literal(self) -> None:
        sql, params = build_search_sql(
            "params.family = 'lightgbm'",
            tenant_id=None,
            order_by=None,
            limit=5,
        )
        assert "json_extract(r.params, ?)" in sql
        assert params == ['$."family"', "lightgbm", 5]

    def test_tag_contains_like(self) -> None:
        sql, params = build_search_sql(
            "tags.golden LIKE 'prod-%'",
            tenant_id=None,
            order_by=None,
            limit=100,
        )
        assert "experiment_tags" in sql
        assert "t.value LIKE ?" in sql
        assert params == ["golden", "prod-%", 100]

    def test_attributes_column_allowlisted(self) -> None:
        sql, params = build_search_sql(
            "attributes.status = 'FINISHED'",
            tenant_id=None,
            order_by=None,
            limit=10,
        )
        assert "r.status = ?" in sql
        assert params == ["FINISHED", 10]

    def test_attributes_column_rejects_non_allowlisted(self) -> None:
        # run_id is not in the allowlist — must reject.
        with pytest.raises(FilterParseError, match="not in allowlist"):
            build_search_sql(
                "attributes.run_id = 'abc'",
                tenant_id=None,
                order_by=None,
                limit=10,
            )

    def test_in_clause_mixed_values(self) -> None:
        sql, params = build_search_sql(
            "attributes.status IN ('FINISHED', 'FAILED')",
            tenant_id=None,
            order_by=None,
            limit=10,
        )
        assert "r.status IN (?, ?)" in sql
        assert params == ["FINISHED", "FAILED", 10]

    def test_and_or_glue_preserves_order(self) -> None:
        sql, _ = build_search_sql(
            "metrics.loss < 0.5 AND params.family = 'lightgbm'",
            tenant_id=None,
            order_by=None,
            limit=10,
        )
        assert " AND " in sql

    def test_tenant_scope_applied_as_additional_clause(self) -> None:
        sql, params = build_search_sql(
            "metrics.loss < 0.5",
            tenant_id="tenant-1",
            order_by=None,
            limit=10,
        )
        assert "r.tenant_id = ?" in sql
        # Tenant binding comes FIRST (clauses assembled in order).
        assert params[0] == "tenant-1"

    def test_empty_filter_raises(self) -> None:
        with pytest.raises(FilterParseError, match="empty"):
            build_search_sql("  ", tenant_id=None, order_by=None, limit=10)

    def test_unknown_prefix_raises(self) -> None:
        with pytest.raises(FilterParseError, match="unknown prefix"):
            build_search_sql("stuff.x = 1", tenant_id=None, order_by=None, limit=10)

    def test_unterminated_string_raises(self) -> None:
        with pytest.raises(FilterParseError, match="unterminated"):
            build_search_sql(
                "params.k = 'oops", tenant_id=None, order_by=None, limit=10
            )

    def test_injection_payload_rejected_by_ident_regex(self) -> None:
        # SQL injection in the name position is blocked by the regex.
        with pytest.raises(FilterParseError):
            build_search_sql(
                'metrics.foo"; DROP = 1',
                tenant_id=None,
                order_by=None,
                limit=10,
            )

    def test_order_by_allowlisted_column(self) -> None:
        sql, params = build_search_sql(
            None,
            tenant_id=None,
            order_by="duration_seconds DESC",
            limit=5,
        )
        assert "ORDER BY r.duration_seconds DESC" in sql
        assert params == [5]

    def test_order_by_rejects_non_allowlisted(self) -> None:
        with pytest.raises(FilterParseError, match="not in allowlist"):
            build_search_sql(
                None,
                tenant_id=None,
                order_by="run_id ASC",
                limit=5,
            )

    def test_no_filter_no_tenant_defaults_to_wall_clock_end(self) -> None:
        sql, params = build_search_sql(None, tenant_id=None, order_by=None, limit=10)
        # Default ordering is wall_clock_end DESC per spec §5 invariant 5.
        assert "ORDER BY r.wall_clock_end DESC" in sql
        assert params == [10]


# ---------------------------------------------------------------------------
# RunRecord + diff helpers — pure functions
# ---------------------------------------------------------------------------


class TestRunRecordFromRow:
    def test_params_decoded_from_dict_passthrough(self) -> None:
        record = run_record_from_row(
            {
                "run_id": "r1",
                "experiment": "exp",
                "status": "FINISHED",
                "tenant_id": "t1",
                "parent_run_id": None,
                "wall_clock_start": "2026-01-01T00:00:00+00:00",
                "wall_clock_end": "2026-01-01T00:01:00+00:00",
                "duration_seconds": 60.0,
                "params": {"lr": 0.1},
                "git_sha": "abc",
                "cuda_version": "12.4",
                "error_type": None,
                "error_message": None,
            }
        )
        assert record.params == {"lr": 0.1}
        assert record.environment["git_sha"] == "abc"
        assert record.environment["cuda_version"] == "12.4"

    def test_params_decoded_from_json_string(self) -> None:
        record = run_record_from_row(
            {
                "run_id": "r1",
                "experiment": "exp",
                "status": "RUNNING",
                "params": '{"lr": 0.01, "batch": 32}',
            }
        )
        assert record.params == {"lr": 0.01, "batch": 32}

    def test_as_dict_is_plain_dict(self) -> None:
        record = run_record_from_row(
            {"run_id": "r1", "experiment": "exp", "status": "RUNNING"}
        )
        d = record.as_dict()
        assert d["run_id"] == "r1"
        assert isinstance(d["params"], dict)


class TestComputeRunDiff:
    def _mk_record(
        self,
        run_id: str,
        *,
        params: dict,
        git_sha: str,
        cuda_version: str,
    ) -> RunRecord:
        return RunRecord(
            run_id=run_id,
            experiment="exp",
            status="FINISHED",
            tenant_id=None,
            parent_run_id=None,
            wall_clock_start=None,
            wall_clock_end=None,
            duration_seconds=None,
            params=params,
            environment={
                "git_sha": git_sha,
                "cuda_version": cuda_version,
                "python_version": "3.13",
                "kailash_ml_version": "1.0.0",
                "lightning_version": None,
                "torch_version": None,
                "git_branch": "main",
                "host": "alice",
                "accelerator": "cpu",
                "precision": "fp32",
            },
            error_type=None,
            error_message=None,
        )

    def test_param_deltas_flagged(self) -> None:
        a = self._mk_record("A", params={"lr": 0.1}, git_sha="abc", cuda_version="12.4")
        b = self._mk_record(
            "B", params={"lr": 0.01}, git_sha="abc", cuda_version="12.4"
        )
        diff = compute_run_diff(a, b, [], [])
        assert diff.params["lr"].changed is True
        assert diff.params["lr"].value_a == 0.1
        assert diff.params["lr"].value_b == 0.01

    def test_reproducibility_risk_requires_all_three_conditions(self) -> None:
        # Git different, CUDA different, BUT no metric pct_change above 5%
        a = self._mk_record("A", params={}, git_sha="abc", cuda_version="12.4")
        b = self._mk_record("B", params={}, git_sha="def", cuda_version="13.0")
        diff = compute_run_diff(
            a,
            b,
            [{"key": "loss", "step": 0, "value": 0.10, "timestamp": "t"}],
            [{"key": "loss", "step": 0, "value": 0.103, "timestamp": "t"}],
        )
        # pct_change = 3% < 5% → reproducibility_risk False.
        assert diff.reproducibility_risk is False

    def test_reproducibility_risk_true_when_metric_shifts(self) -> None:
        a = self._mk_record("A", params={}, git_sha="abc", cuda_version="12.4")
        b = self._mk_record("B", params={}, git_sha="def", cuda_version="13.0")
        diff = compute_run_diff(
            a,
            b,
            [{"key": "loss", "step": 0, "value": 0.1, "timestamp": "t"}],
            [{"key": "loss", "step": 0, "value": 0.2, "timestamp": "t"}],
        )
        # pct_change = 100% → triggers reproducibility_risk.
        assert diff.reproducibility_risk is True
        assert diff.metrics["loss"].pct_change == 100.0

    def test_per_step_frame_built_when_both_have_steps(self) -> None:
        a = self._mk_record("A", params={}, git_sha="abc", cuda_version="12.4")
        b = self._mk_record("B", params={}, git_sha="abc", cuda_version="12.4")
        diff = compute_run_diff(
            a,
            b,
            [
                {"key": "loss", "step": 0, "value": 1.0, "timestamp": "t"},
                {"key": "loss", "step": 1, "value": 0.5, "timestamp": "t"},
            ],
            [
                {"key": "loss", "step": 0, "value": 1.1, "timestamp": "t"},
                {"key": "loss", "step": 1, "value": 0.4, "timestamp": "t"},
            ],
        )
        frame = diff.metrics["loss"].per_step
        assert frame is not None
        assert frame.columns == ["step", "value_a", "value_b"]
        assert frame.height == 2


# ---------------------------------------------------------------------------
# Tracker integration — backend-exercising T1 tests (:memory: SQLite)
# ---------------------------------------------------------------------------


pytestmark_async = pytest.mark.asyncio


@pytest.fixture
async def tracker(tmp_path: Path) -> ExperimentTracker:
    db = tmp_path / "w13.db"
    t = await ExperimentTracker.create(f"sqlite:///{db}")
    yield t
    await t.close()


class TestTrackerQueries:
    pytestmark = pytest.mark.asyncio

    async def test_get_run_returns_run_record(self, tracker: ExperimentTracker) -> None:
        async with tracker.track("exp-1", lr=0.1) as run:
            run_id = run.run_id
        record = await tracker.get_run(run_id)
        assert isinstance(record, RunRecord)
        assert record.run_id == run_id
        assert record.experiment == "exp-1"
        assert record.status == "FINISHED"
        assert record.params.get("lr") == 0.1

    async def test_get_run_missing_raises(self, tracker: ExperimentTracker) -> None:
        with pytest.raises(RunNotFoundError):
            await tracker.get_run("does-not-exist")

    async def test_get_run_cross_tenant_is_hidden(
        self, tracker: ExperimentTracker
    ) -> None:
        async with tracker.track("exp-1", tenant_id="tenant-a") as run:
            run_id = run.run_id
        # Tenant-b cannot see tenant-a's run.
        with pytest.raises(RunNotFoundError):
            await tracker.get_run(run_id, tenant_id="tenant-b")
        # Tenant-a can.
        record = await tracker.get_run(run_id, tenant_id="tenant-a")
        assert record.tenant_id == "tenant-a"

    async def test_list_runs_returns_polars_dataframe(
        self, tracker: ExperimentTracker
    ) -> None:
        async with tracker.track("exp-A") as r1:
            await r1.log_metric("loss", 0.5)
        async with tracker.track("exp-A") as r2:
            await r2.log_metric("loss", 0.3)
        df = await tracker.list_runs(experiment="exp-A", limit=10)
        assert isinstance(df, pl.DataFrame)
        assert df.height == 2
        assert "run_id" in df.columns
        assert "status" in df.columns

    async def test_list_runs_status_filter(self, tracker: ExperimentTracker) -> None:
        async with tracker.track("exp-B") as _run:
            pass
        df = await tracker.list_runs(status="FINISHED")
        assert df.height >= 1
        assert set(df["status"].to_list()) == {"FINISHED"}
        empty = await tracker.list_runs(status="KILLED")
        assert empty.height == 0

    async def test_search_runs_metric_filter(self, tracker: ExperimentTracker) -> None:
        async with tracker.track("exp-A") as r1:
            await r1.log_metric("val_loss", 0.9)
        async with tracker.track("exp-A") as r2:
            await r2.log_metric("val_loss", 0.1)
        df = await tracker.search_runs(filter="metrics.val_loss < 0.5")
        ids = df["run_id"].to_list()
        assert r2.run_id in ids
        assert r1.run_id not in ids

    async def test_search_runs_param_filter(self, tracker: ExperimentTracker) -> None:
        async with tracker.track("exp-A", family="lightgbm") as r1:
            pass
        async with tracker.track("exp-A", family="xgboost") as r2:
            pass
        df = await tracker.search_runs(filter="params.family = 'lightgbm'")
        assert r1.run_id in df["run_id"].to_list()
        assert r2.run_id not in df["run_id"].to_list()

    async def test_search_runs_tenant_auto_scoped(
        self, tracker: ExperimentTracker
    ) -> None:
        async with tracker.track("exp-X", tenant_id="tenant-a") as _r1:
            pass
        async with tracker.track("exp-X", tenant_id="tenant-b") as _r2:
            pass
        df_a = await tracker.search_runs(
            filter="attributes.experiment = 'exp-X'",
            tenant_id="tenant-a",
        )
        assert df_a.height == 1
        assert df_a["tenant_id"].to_list() == ["tenant-a"]

    async def test_search_runs_invalid_filter_raises(
        self, tracker: ExperimentTracker
    ) -> None:
        with pytest.raises(ValueError, match="invalid filter"):
            await tracker.search_runs(filter="metrics.loss @@ 0.5")

    async def test_list_experiments_summary(self, tracker: ExperimentTracker) -> None:
        async with tracker.track("exp-A") as _r1:
            pass
        async with tracker.track("exp-A") as _r2:
            pass
        async with tracker.track("exp-B") as _r3:
            pass
        df = await tracker.list_experiments()
        assert set(df["experiment"].to_list()) == {"exp-A", "exp-B"}
        # exp-A should have 2 runs.
        row_a = df.filter(pl.col("experiment") == "exp-A").row(0, named=True)
        assert row_a["run_count"] == 2
        assert row_a["finished_count"] == 2

    async def test_list_metrics_tenant_scoped(self, tracker: ExperimentTracker) -> None:
        async with tracker.track("exp-A", tenant_id="t-a") as run:
            await run.log_metric("loss", 0.5, step=0)
            await run.log_metric("loss", 0.3, step=1)
        df = await tracker.list_metrics(run.run_id, tenant_id="t-a")
        assert df.height == 2
        assert df.columns == ["key", "step", "value", "timestamp"]
        # Cross-tenant access is blocked.
        with pytest.raises(RunNotFoundError):
            await tracker.list_metrics(run.run_id, tenant_id="t-b")

    async def test_list_artifacts_tenant_scoped(
        self, tracker: ExperimentTracker
    ) -> None:
        async with tracker.track("exp-A", tenant_id="t-a") as run:
            await run.log_artifact(b"hello", "hello.txt")
        df = await tracker.list_artifacts(run.run_id, tenant_id="t-a")
        assert df.height == 1
        # Cross-tenant blocked.
        with pytest.raises(RunNotFoundError):
            await tracker.list_artifacts(run.run_id, tenant_id="t-b")

    async def test_diff_runs_returns_run_diff(self, tracker: ExperimentTracker) -> None:
        async with tracker.track("exp-A", lr=0.1) as r1:
            await r1.log_metric("acc", 0.80)
        async with tracker.track("exp-A", lr=0.01) as r2:
            await r2.log_metric("acc", 0.82)
        diff = await tracker.diff_runs(r1.run_id, r2.run_id)
        assert isinstance(diff, RunDiff)
        assert diff.run_id_a == r1.run_id
        assert diff.run_id_b == r2.run_id
        assert isinstance(diff.params.get("lr"), ParamDelta)
        assert diff.params["lr"].changed is True
        # Both runs share env (same process) → reproducibility_risk False.
        assert diff.reproducibility_risk is False
        assert "metrics" in diff.summary.lower() or "params" in diff.summary.lower()
