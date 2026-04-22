# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""W12 Tier-1 unit tests — logging primitives (spec ``ml-tracking.md`` §4).

Covers:

- ``log_metric`` / ``log_metrics`` finite-check + append-only rows.
- ``log_param`` / ``log_params`` finite-check + key regex.
- ``log_artifact`` SHA-256 content-addressing + dedupe.
- ``log_figure`` plotly JSON + matplotlib PNG dispatch (mocked figure).
- ``log_model`` mandatory signature kwarg + run-scoped snapshot row.
- ``add_tag`` / ``add_tags`` / ``set_tags`` — key regex + upsert.
- Rank-0 guard — every primitive is a no-op when the DDP rank probe
  reports a non-zero rank.
- ``attach_training_result_async`` flattens metrics + hyperparameters
  per spec §4.6 MUST-flatten.

Uses the in-memory SQLite alias so tests run without filesystem state.
"""
from __future__ import annotations

import math
from pathlib import Path

import pytest
from kailash_ml._device_report import DeviceReport
from kailash_ml._result import TrainingResult
from kailash_ml.errors import (
    MetricValueError,
    ModelSignatureRequiredError,
    ParamValueError,
    TrackingError,
)
from kailash_ml.tracking import ExperimentTracker
from kailash_ml.tracking.runner import (
    ArtifactHandle,
    ModelVersionInfo,
    _coerce_tag_value,
    _is_rank_zero,
    _serialise_figure,
    _validate_key,
    _validate_metric_value,
    _validate_param_value,
    _validate_tag_key,
)

# Module-wide asyncio marker applied selectively per class via decorators
# below so pure-helper tests (TestValidators / TestFigureSerialisation)
# stay sync.


# ---------------------------------------------------------------------------
# Helper-level unit tests (pure functions — no backend)
# ---------------------------------------------------------------------------


class TestValidators:
    def test_key_regex_accepts_spec_shapes(self) -> None:
        _validate_key("metric", "loss")
        _validate_key("metric", "train.loss")
        _validate_key("metric", "val-acc")
        _validate_key("metric", "_internal")
        _validate_key("param", "learning_rate.0")

    @pytest.mark.parametrize(
        "bad", ["", "1starts_digit", "has space", "has/slash", "has$"]
    )
    def test_key_regex_rejects_bad(self, bad: str) -> None:
        with pytest.raises(TrackingError):
            _validate_key("metric", bad)

    def test_tag_key_regex_is_stricter_than_param_key(self) -> None:
        # Param / metric keys allow uppercase + dot + hyphen.
        _validate_key("param", "LearningRate")
        # Tag keys do NOT.
        with pytest.raises(TrackingError):
            _validate_tag_key("LearningRate")
        with pytest.raises(TrackingError):
            _validate_tag_key("has.dot")
        with pytest.raises(TrackingError):
            _validate_tag_key("has-hyphen")
        # Tag keys accept lowercase + underscore + digits.
        _validate_tag_key("env")
        _validate_tag_key("cost_center")
        _validate_tag_key("_internal_9")

    def test_metric_value_rejects_nan_inf_bool_str(self) -> None:
        assert _validate_metric_value("loss", 0.5) == 0.5
        assert _validate_metric_value("step", 7) == 7.0
        with pytest.raises(MetricValueError):
            _validate_metric_value("loss", float("nan"))
        with pytest.raises(MetricValueError):
            _validate_metric_value("loss", float("inf"))
        with pytest.raises(MetricValueError):
            _validate_metric_value("loss", -math.inf)
        with pytest.raises(MetricValueError):
            _validate_metric_value("ok", True)  # bool is NOT numeric
        with pytest.raises(MetricValueError):
            _validate_metric_value("ok", "0.5")

    def test_param_value_rejects_nan_inf_but_accepts_strings_bools(self) -> None:
        assert _validate_param_value("model", "resnet50") == "resnet50"
        assert _validate_param_value("use_amp", True) is True
        assert _validate_param_value("lr", 3e-4) == 3e-4
        with pytest.raises(ParamValueError):
            _validate_param_value("lr", float("nan"))
        with pytest.raises(ParamValueError):
            _validate_param_value("lr", float("inf"))

    def test_coerce_tag_value(self) -> None:
        assert _coerce_tag_value("prod") == "prod"
        assert _coerce_tag_value(3) == "3"
        assert _coerce_tag_value(True) == "True"

    def test_rank_zero_defaults_true_without_torch_dist(self) -> None:
        # In CI torch may or may not be importable; when dist is not
        # initialised the helper returns True (single-process).
        assert _is_rank_zero() is True


class _FakePlotlyFig:
    """Duck-typed plotly figure for the figure-sink test."""

    def to_json(self) -> str:
        return '{"data": [], "layout": {}}'


class _FakeMatplotlibFig:
    """Duck-typed matplotlib figure that writes PNG magic bytes."""

    def savefig(self, buf, *, format: str) -> None:  # noqa: ANN001
        assert format == "png"
        # PNG magic number + minimal padding — enough for shape tests.
        buf.write(b"\x89PNG\r\n\x1a\n" + b"\x00" * 32)


class TestFigureSerialisation:
    def test_plotly_path(self) -> None:
        payload, ct = _serialise_figure(_FakePlotlyFig())
        assert ct == "application/vnd.plotly.v1+json"
        assert payload.startswith(b"{")

    def test_matplotlib_path(self) -> None:
        payload, ct = _serialise_figure(_FakeMatplotlibFig())
        assert ct == "image/png"
        assert payload.startswith(b"\x89PNG")

    def test_unsupported_figure_raises(self) -> None:
        with pytest.raises(TrackingError):
            _serialise_figure(object())


# ---------------------------------------------------------------------------
# ExperimentRun integration with real SQLite backend (Tier-1 — :memory:)
# ---------------------------------------------------------------------------


async def _mk_tracker() -> ExperimentTracker:
    return await ExperimentTracker.create("sqlite+memory")


@pytest.mark.asyncio
class TestLogMetric:
    async def test_single_metric_appends_row(self) -> None:
        tracker = await _mk_tracker()
        try:
            async with tracker.track("e") as run:
                await run.log_metric("loss", 0.5, step=0)
                await run.log_metric("loss", 0.3, step=1)
                await run.log_metric("loss", 0.1, step=2)
            rows = await tracker._backend.list_metrics(run.run_id)
            assert [r["value"] for r in rows] == [0.5, 0.3, 0.1]
            assert [r["step"] for r in rows] == [0, 1, 2]
        finally:
            await tracker.close()

    async def test_nan_inf_raise_metric_value_error(self) -> None:
        tracker = await _mk_tracker()
        try:
            async with tracker.track("e") as run:
                with pytest.raises(MetricValueError):
                    await run.log_metric("loss", float("nan"))
                with pytest.raises(MetricValueError):
                    await run.log_metric("loss", float("inf"))
        finally:
            await tracker.close()

    async def test_log_metrics_batch_is_atomic(self) -> None:
        tracker = await _mk_tracker()
        try:
            async with tracker.track("e") as run:
                await run.log_metrics({"loss": 0.5, "acc": 0.9, "f1": 0.8}, step=0)
            rows = await tracker._backend.list_metrics(run.run_id)
            keys = sorted({r["key"] for r in rows})
            assert keys == ["acc", "f1", "loss"]
            assert all(r["step"] == 0 for r in rows)
        finally:
            await tracker.close()

    async def test_log_metrics_batch_rejects_nan_without_partial_write(self) -> None:
        tracker = await _mk_tracker()
        try:
            async with tracker.track("e") as run:
                with pytest.raises(MetricValueError):
                    await run.log_metrics({"loss": 0.5, "bad": float("nan")})
            # Neither "loss" nor "bad" persisted — validation happens
            # before the INSERT batch.
            rows = await tracker._backend.list_metrics(run.run_id)
            assert rows == []
        finally:
            await tracker.close()


@pytest.mark.asyncio
class TestLogParam:
    async def test_numeric_nan_raises_param_value_error(self) -> None:
        tracker = await _mk_tracker()
        try:
            async with tracker.track("e") as run:
                with pytest.raises(ParamValueError):
                    await run.log_param("learning_rate", float("nan"))
        finally:
            await tracker.close()

    async def test_string_params_pass_through(self) -> None:
        tracker = await _mk_tracker()
        try:
            async with tracker.track("e") as run:
                await run.log_param("model", "resnet50")
                await run.log_params(
                    {"optimizer": "adam", "batch_size": 64, "use_amp": True}
                )
            fetched = await tracker._backend.get_run(run.run_id)
            assert fetched is not None
            params = fetched["params"]
            assert params["model"] == "resnet50"
            assert params["optimizer"] == "adam"
            assert params["batch_size"] == 64
            assert params["use_amp"] is True
        finally:
            await tracker.close()


@pytest.mark.asyncio
class TestLogArtifact:
    async def test_sha256_dedupe_returns_same_handle(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        # Override artifact root so dedupe is tested against tmp_path.
        from kailash_ml.tracking import runner as _runner

        monkeypatch.setattr(
            _runner,
            "_artifact_storage_root",
            lambda _db: tmp_path / "artifacts",
        )
        tracker = await _mk_tracker()
        try:
            async with tracker.track("e") as run:
                h1 = await run.log_artifact(b"hello world", "greeting.txt")
                h2 = await run.log_artifact(b"hello world", "greeting.txt")
            assert h1.sha256 == h2.sha256
            assert h1.storage_uri == h2.storage_uri
            # Still only one row on disk — PK (run_id, name, sha256)
            # dedupes the second INSERT.
            rows = await tracker._backend.list_artifacts(run.run_id)
            assert len(rows) == 1
            assert rows[0]["size_bytes"] == len(b"hello world")
        finally:
            await tracker.close()

    async def test_rejects_missing_file(self, tmp_path: Path) -> None:
        tracker = await _mk_tracker()
        try:
            async with tracker.track("e") as run:
                with pytest.raises(FileNotFoundError):
                    await run.log_artifact(
                        tmp_path / "does-not-exist.bin", "missing.bin"
                    )
        finally:
            await tracker.close()

    async def test_accepts_filesystem_path(self, tmp_path: Path, monkeypatch) -> None:
        from kailash_ml.tracking import runner as _runner

        monkeypatch.setattr(
            _runner,
            "_artifact_storage_root",
            lambda _db: tmp_path / "artifacts",
        )
        path = tmp_path / "weights.bin"
        path.write_bytes(b"\x00\x01\x02\x03")
        tracker = await _mk_tracker()
        try:
            async with tracker.track("e") as run:
                handle = await run.log_artifact(path, "weights.bin")
            assert handle.size_bytes == 4
            assert Path(handle.storage_uri).exists()
        finally:
            await tracker.close()


@pytest.mark.asyncio
class TestLogFigure:
    async def test_plotly_is_logged_as_plotly_json(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        from kailash_ml.tracking import runner as _runner

        monkeypatch.setattr(
            _runner,
            "_artifact_storage_root",
            lambda _db: tmp_path / "artifacts",
        )
        tracker = await _mk_tracker()
        try:
            async with tracker.track("e") as run:
                handle = await run.log_figure(_FakePlotlyFig(), "loss_curve")
            assert handle.content_type == "application/vnd.plotly.v1+json"
            rows = await tracker._backend.list_artifacts(run.run_id)
            assert rows[0]["content_type"] == "application/vnd.plotly.v1+json"
        finally:
            await tracker.close()

    async def test_matplotlib_is_logged_as_png(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        from kailash_ml.tracking import runner as _runner

        monkeypatch.setattr(
            _runner,
            "_artifact_storage_root",
            lambda _db: tmp_path / "artifacts",
        )
        tracker = await _mk_tracker()
        try:
            async with tracker.track("e") as run:
                handle = await run.log_figure(_FakeMatplotlibFig(), "roc")
            assert handle.content_type == "image/png"
        finally:
            await tracker.close()


@pytest.mark.asyncio
class TestLogModel:
    async def test_signature_is_mandatory(self, tmp_path, monkeypatch) -> None:
        from kailash_ml.tracking import runner as _runner

        monkeypatch.setattr(
            _runner,
            "_artifact_storage_root",
            lambda _db: tmp_path / "artifacts",
        )
        tracker = await _mk_tracker()
        try:
            async with tracker.track("e") as run:
                with pytest.raises(ModelSignatureRequiredError):
                    await run.log_model(b"\x00", "my_model", signature=None)
        finally:
            await tracker.close()

    async def test_snapshot_row_written(self, tmp_path, monkeypatch) -> None:
        from kailash_ml.tracking import runner as _runner

        monkeypatch.setattr(
            _runner,
            "_artifact_storage_root",
            lambda _db: tmp_path / "artifacts",
        )
        tracker = await _mk_tracker()
        try:
            async with tracker.track("e") as run:
                info = await run.log_model(
                    b"fake-onnx-bytes",
                    "fraud-detector",
                    format="onnx",
                    signature={"input": "float32[1,10]", "output": "float32[1]"},
                    lineage={"dataset_hash": "sha256:beef"},
                )
            assert isinstance(info, ModelVersionInfo)
            assert info.name == "fraud-detector"
            assert info.format == "onnx"
            assert info.run_id == run.run_id
            rows = await tracker._backend.list_model_versions(run.run_id)
            assert len(rows) == 1
            assert rows[0]["name"] == "fraud-detector"
            assert rows[0]["format"] == "onnx"
            assert rows[0]["artifact_sha"] == info.artifact_sha
        finally:
            await tracker.close()


@pytest.mark.asyncio
class TestTags:
    async def test_add_tag_rejects_non_lowercase(self) -> None:
        tracker = await _mk_tracker()
        try:
            async with tracker.track("e") as run:
                with pytest.raises(TrackingError):
                    await run.add_tag("Env", "prod")  # uppercase rejected
        finally:
            await tracker.close()

    async def test_add_tags_upserts_many(self) -> None:
        tracker = await _mk_tracker()
        try:
            async with tracker.track("e") as run:
                await run.add_tags({"env": "prod", "cost_center": "research"})
                # Upsert: second call overrides.
                await run.add_tag("env", "staging")
            tags = await tracker._backend.list_tags(run.run_id)
            assert tags == {"env": "staging", "cost_center": "research"}
        finally:
            await tracker.close()

    async def test_set_tags_kwargs_form(self) -> None:
        tracker = await _mk_tracker()
        try:
            async with tracker.track("e") as run:
                await run.set_tags(env="prod", release="1.0")
            tags = await tracker._backend.list_tags(run.run_id)
            assert tags == {"env": "prod", "release": "1.0"}
        finally:
            await tracker.close()

    async def test_non_string_value_coerced(self) -> None:
        tracker = await _mk_tracker()
        try:
            async with tracker.track("e") as run:
                await run.add_tag("num", 42)
            tags = await tracker._backend.list_tags(run.run_id)
            assert tags == {"num": "42"}
        finally:
            await tracker.close()


@pytest.mark.asyncio
class TestRankZeroGuard:
    async def test_non_rank_zero_is_noop(self, monkeypatch) -> None:
        from kailash_ml.tracking import runner as _runner

        monkeypatch.setattr(_runner, "_is_rank_zero", lambda: False)
        tracker = await _mk_tracker()
        try:
            async with tracker.track("e") as run:
                await run.log_metric("loss", 0.5)
                await run.log_metrics({"acc": 0.9})
                await run.log_param("lr", 1e-4)
                await run.log_params({"batch": 64})
                await run.add_tag("env", "prod")
                await run.add_tags({"stage": "beta"})
                await run.set_tags(role="trainer")
                handle = await run.log_artifact(b"x", "x.bin")
                fig_handle = await run.log_figure(_FakePlotlyFig(), "x")
                info = await run.log_model(
                    b"x", "m", signature={"x": 1}, lineage={"y": 2}
                )
            # Nothing persisted: rank-0 guard is structural.
            metrics = await tracker._backend.list_metrics(run.run_id)
            artifacts = await tracker._backend.list_artifacts(run.run_id)
            tags = await tracker._backend.list_tags(run.run_id)
            versions = await tracker._backend.list_model_versions(run.run_id)
            assert metrics == []
            assert artifacts == []
            assert tags == {}
            assert versions == []
            # Sentinel shapes still valid (downstream unpacking is safe).
            assert isinstance(handle, ArtifactHandle)
            assert handle.storage_uri == ""
            assert isinstance(fig_handle, ArtifactHandle)
            assert fig_handle.storage_uri == ""
            assert isinstance(info, ModelVersionInfo)
            assert info.artifact_sha == ""
        finally:
            await tracker.close()


@pytest.mark.asyncio
class TestAttachTrainingResultAsync:
    async def test_flattens_metrics_and_hyperparameters(
        self, tmp_path, monkeypatch
    ) -> None:
        from kailash_ml.tracking import runner as _runner

        monkeypatch.setattr(
            _runner,
            "_artifact_storage_root",
            lambda _db: tmp_path / "artifacts",
        )
        device = DeviceReport(
            family="cpu",
            backend="cpu",
            device_string="cpu",
            precision="float32",
            array_api=True,
            fallback_reason=None,
        )
        result = TrainingResult(
            model_uri="models://attach_test/v1",
            metrics={"final_loss": 0.12, "final_acc": 0.97},
            device_used="cpu",
            accelerator="cpu",
            precision="float32",
            elapsed_seconds=1.0,
            tracker_run_id=None,
            tenant_id=None,
            artifact_uris={},
            lightning_trainer_config={},
            family="cpu",
            hyperparameters={"lr": 3e-4, "batch_size": 64, "optimizer": "adam"},
            device=device,
        )
        tracker = await _mk_tracker()
        try:
            async with tracker.track("e") as run:
                await run.attach_training_result_async(result)
            metrics = await tracker._backend.list_metrics(run.run_id)
            keys = sorted({r["key"] for r in metrics})
            assert keys == ["final_acc", "final_loss"]
            fetched = await tracker._backend.get_run(run.run_id)
            assert fetched is not None
            # Numeric + string hyperparameters both flatten — string
            # "optimizer" passes through because log_param validates but
            # does not reject non-numeric values.
            assert fetched["params"]["lr"] == 3e-4
            assert fetched["params"]["batch_size"] == 64
            assert fetched["params"]["optimizer"] == "adam"
            # Device envelope carried through.
            assert fetched["device_used"] == "cpu"
            assert fetched["device_family"] == "cpu"
        finally:
            await tracker.close()
