# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tests for AlignmentPipeline (unit tests -- no GPU, no model loading)."""
from __future__ import annotations

from pathlib import Path

import pytest

from kailash_align.config import AlignmentConfig
from kailash_align.exceptions import TrainingError
from kailash_align.pipeline import AlignmentPipeline, AlignmentResult


class TestAlignmentPipelineInit:
    def test_init_with_config(self):
        cfg = AlignmentConfig(base_model_id="test/model", method="sft")
        pipeline = AlignmentPipeline(config=cfg)
        assert pipeline._config is cfg
        assert pipeline._registry is None

    def test_init_with_registry(self):
        cfg = AlignmentConfig(base_model_id="test/model", method="sft")
        fake_registry = object()
        pipeline = AlignmentPipeline(config=cfg, adapter_registry=fake_registry)
        assert pipeline._registry is fake_registry


class TestAlignmentPipelineTrainDispatch:
    @pytest.mark.asyncio
    async def test_dpo_requires_preference_dataset(self):
        cfg = AlignmentConfig(base_model_id="test/model", method="dpo")
        pipeline = AlignmentPipeline(config=cfg)
        with pytest.raises(TrainingError, match="dpo requires preference_dataset"):
            await pipeline.train(dataset=None, adapter_name="test")

    @pytest.mark.asyncio
    async def test_sft_then_dpo_requires_preference_dataset(self):
        cfg = AlignmentConfig(base_model_id="test/model", method="sft_then_dpo")
        pipeline = AlignmentPipeline(config=cfg)
        with pytest.raises(
            TrainingError, match="sft_then_dpo requires preference_dataset"
        ):
            await pipeline.train(dataset=None, adapter_name="test")


class TestDatasetValidation:
    """Tests for dataset validators used by MethodRegistry."""

    def test_preference_missing_columns(self):
        """Dataset with wrong columns raises TrainingError."""
        from kailash_align.method_registry import _validate_preference_columns

        class FakeDataset:
            column_names = ["text", "label"]

            def __len__(self):
                return 1

        with pytest.raises(TrainingError, match="missing"):
            _validate_preference_columns(FakeDataset())

    def test_preference_empty_dataset(self):
        """Empty dataset raises TrainingError."""
        from kailash_align.method_registry import _validate_preference_columns

        class FakeDataset:
            column_names = ["prompt", "chosen", "rejected"]

            def __len__(self):
                return 0

        with pytest.raises(TrainingError, match="empty"):
            _validate_preference_columns(FakeDataset())

    def test_preference_valid_passes(self):
        """Valid preference dataset passes validation."""
        from kailash_align.method_registry import _validate_preference_columns

        class FakeDataset:
            column_names = ["prompt", "chosen", "rejected"]

            def __len__(self):
                return 2

        # Should not raise
        _validate_preference_columns(FakeDataset())

    def test_unpaired_missing_columns(self):
        """Unpaired dataset with wrong columns raises TrainingError."""
        from kailash_align.method_registry import _validate_unpaired_columns

        class FakeDataset:
            column_names = ["text"]

            def __len__(self):
                return 1

        with pytest.raises(TrainingError, match="missing"):
            _validate_unpaired_columns(FakeDataset())

    def test_unpaired_valid_passes(self):
        """Valid unpaired dataset passes."""
        from kailash_align.method_registry import _validate_unpaired_columns

        class FakeDataset:
            column_names = ["prompt", "completion", "label"]

            def __len__(self):
                return 2

        _validate_unpaired_columns(FakeDataset())

    def test_prompt_only_missing_column(self):
        """Prompt-only dataset without prompt column raises."""
        from kailash_align.method_registry import _validate_prompt_only

        class FakeDataset:
            column_names = ["text"]

            def __len__(self):
                return 1

        with pytest.raises(TrainingError, match="prompt"):
            _validate_prompt_only(FakeDataset())

    def test_prompt_only_valid_passes(self):
        """Valid prompt-only dataset passes."""
        from kailash_align.method_registry import _validate_prompt_only

        class FakeDataset:
            column_names = ["prompt"]

            def __len__(self):
                return 2

        _validate_prompt_only(FakeDataset())

    def test_sft_empty_raises(self):
        """Empty SFT dataset raises."""
        from kailash_align.method_registry import _validate_sft_columns

        class FakeDataset:
            column_names = ["text"]

            def __len__(self):
                return 0

        with pytest.raises(TrainingError, match="empty"):
            _validate_sft_columns(FakeDataset())


class TestCheckpointDetection:
    def test_no_checkpoints(self, tmp_path: Path):
        cfg = AlignmentConfig(base_model_id="test/model", method="sft")
        pipeline = AlignmentPipeline(config=cfg)
        assert pipeline._find_checkpoint(tmp_path) is None

    def test_finds_latest_checkpoint(self, tmp_path: Path):
        cfg = AlignmentConfig(base_model_id="test/model", method="sft")
        pipeline = AlignmentPipeline(config=cfg)

        # Create checkpoint directories
        (tmp_path / "checkpoint-100").mkdir()
        (tmp_path / "checkpoint-200").mkdir()
        (tmp_path / "checkpoint-50").mkdir()

        result = pipeline._find_checkpoint(tmp_path)
        assert result is not None
        assert "checkpoint-200" in result


class TestAlignmentResult:
    def test_dataclass_fields(self):
        result = AlignmentResult(
            adapter_name="test",
            adapter_path="/path",
            adapter_version=None,
            training_metrics={"loss": 0.5},
            experiment_dir="/exp",
            method="sft",
        )
        assert result.adapter_name == "test"
        assert result.adapter_path == "/path"
        assert result.adapter_version is None
        assert result.training_metrics == {"loss": 0.5}
        assert result.experiment_dir == "/exp"
        assert result.method == "sft"
