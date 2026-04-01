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
        with pytest.raises(TrainingError, match="DPO requires preference_dataset"):
            await pipeline.train(dataset=None, adapter_name="test")

    @pytest.mark.asyncio
    async def test_sft_then_dpo_requires_preference_dataset(self):
        cfg = AlignmentConfig(base_model_id="test/model", method="sft_then_dpo")
        pipeline = AlignmentPipeline(config=cfg)
        with pytest.raises(
            TrainingError, match="sft_then_dpo requires preference_dataset"
        ):
            await pipeline.train(dataset=None, adapter_name="test")


class TestPreferenceDatasetValidation:
    def _make_pipeline(self) -> AlignmentPipeline:
        cfg = AlignmentConfig(base_model_id="test/model", method="dpo")
        return AlignmentPipeline(config=cfg)

    def test_missing_columns(self):
        """Dataset with wrong columns raises TrainingError."""
        pipeline = self._make_pipeline()

        class FakeDataset:
            column_names = ["text", "label"]

            def __len__(self):
                return 1

        with pytest.raises(TrainingError, match="missing required columns"):
            pipeline._validate_preference_dataset(FakeDataset())

    def test_empty_dataset(self):
        """Empty dataset raises TrainingError."""
        pipeline = self._make_pipeline()

        class FakeDataset:
            column_names = ["prompt", "chosen", "rejected"]

            def __len__(self):
                return 0

        with pytest.raises(TrainingError, match="empty"):
            pipeline._validate_preference_dataset(FakeDataset())

    def test_empty_string_in_column(self):
        """Non-empty string check on first row."""
        pipeline = self._make_pipeline()

        class FakeDataset:
            column_names = ["prompt", "chosen", "rejected"]

            def __len__(self):
                return 1

            def __getitem__(self, idx):
                return {"prompt": "test", "chosen": "", "rejected": "bad response"}

        with pytest.raises(TrainingError, match="non-empty strings"):
            pipeline._validate_preference_dataset(FakeDataset())

    def test_valid_dataset_passes(self):
        """Valid preference dataset passes validation."""
        pipeline = self._make_pipeline()

        class FakeDataset:
            column_names = ["prompt", "chosen", "rejected"]

            def __len__(self):
                return 2

            def __getitem__(self, idx):
                return {
                    "prompt": "What is 2+2?",
                    "chosen": "4",
                    "rejected": "5",
                }

        # Should not raise
        pipeline._validate_preference_dataset(FakeDataset())


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
