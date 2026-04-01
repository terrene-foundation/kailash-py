# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tests for AlignmentConfig and sub-configs."""
from __future__ import annotations

import math

import pytest

from kailash_align.config import (
    AdapterSignature,
    AlignmentConfig,
    DPOConfig,
    LoRAConfig,
    SFTConfig,
    _validate_finite,
    _validate_positive,
)


# --- Validation Utilities ---


class TestValidateFinite:
    def test_finite_passes(self):
        _validate_finite(1.0, "test")
        _validate_finite(0.0, "test")
        _validate_finite(-1.0, "test")

    def test_nan_raises(self):
        with pytest.raises(ValueError, match="must be finite"):
            _validate_finite(float("nan"), "test")

    def test_inf_raises(self):
        with pytest.raises(ValueError, match="must be finite"):
            _validate_finite(float("inf"), "test")

    def test_negative_inf_raises(self):
        with pytest.raises(ValueError, match="must be finite"):
            _validate_finite(float("-inf"), "test")

    def test_none_passes(self):
        _validate_finite(None, "test")  # None is acceptable (optional field)


class TestValidatePositive:
    def test_positive_passes(self):
        _validate_positive(1.0, "test")
        _validate_positive(0.001, "test")

    def test_zero_raises(self):
        with pytest.raises(ValueError, match="must be positive"):
            _validate_positive(0.0, "test")

    def test_negative_raises(self):
        with pytest.raises(ValueError, match="must be positive"):
            _validate_positive(-1.0, "test")

    def test_nan_raises(self):
        with pytest.raises(ValueError, match="must be finite"):
            _validate_positive(float("nan"), "test")


# --- LoRAConfig ---


class TestLoRAConfig:
    def test_defaults(self):
        cfg = LoRAConfig()
        assert cfg.rank == 16
        assert cfg.alpha == 32
        assert cfg.target_modules == ("q_proj", "v_proj", "k_proj", "o_proj")
        assert cfg.dropout == 0.05
        assert cfg.bias == "none"
        assert cfg.task_type == "CAUSAL_LM"

    def test_frozen(self):
        cfg = LoRAConfig()
        with pytest.raises(AttributeError):
            cfg.rank = 8  # type: ignore[misc]

    def test_invalid_rank_zero(self):
        with pytest.raises(ValueError, match="rank must be >= 1"):
            LoRAConfig(rank=0)

    def test_invalid_rank_negative(self):
        with pytest.raises(ValueError, match="rank must be >= 1"):
            LoRAConfig(rank=-1)

    def test_invalid_alpha_zero(self):
        with pytest.raises(ValueError, match="alpha must be >= 1"):
            LoRAConfig(alpha=0)

    def test_invalid_dropout_nan(self):
        with pytest.raises(ValueError, match="must be finite"):
            LoRAConfig(dropout=float("nan"))

    def test_invalid_dropout_out_of_range(self):
        with pytest.raises(ValueError, match="dropout must be in"):
            LoRAConfig(dropout=1.0)

    def test_invalid_dropout_negative(self):
        with pytest.raises(ValueError, match="dropout must be in"):
            LoRAConfig(dropout=-0.1)

    def test_empty_target_modules(self):
        with pytest.raises(ValueError, match="target_modules must not be empty"):
            LoRAConfig(target_modules=())

    def test_invalid_bias(self):
        with pytest.raises(ValueError, match="bias must be"):
            LoRAConfig(bias="invalid")

    def test_custom_values(self):
        cfg = LoRAConfig(
            rank=8,
            alpha=16,
            target_modules=("q_proj",),
            dropout=0.1,
            bias="all",
        )
        assert cfg.rank == 8
        assert cfg.alpha == 16
        assert cfg.target_modules == ("q_proj",)
        assert cfg.dropout == 0.1
        assert cfg.bias == "all"


# --- SFTConfig ---


class TestSFTConfig:
    def test_defaults(self):
        cfg = SFTConfig()
        assert cfg.num_train_epochs == 3
        assert cfg.learning_rate == 2e-4
        assert cfg.bf16 is True
        assert cfg.fp16 is False

    def test_frozen(self):
        cfg = SFTConfig()
        with pytest.raises(AttributeError):
            cfg.learning_rate = 1e-3  # type: ignore[misc]

    def test_nan_learning_rate(self):
        with pytest.raises(ValueError, match="must be finite"):
            SFTConfig(learning_rate=float("nan"))

    def test_inf_learning_rate(self):
        with pytest.raises(ValueError, match="must be finite"):
            SFTConfig(learning_rate=float("inf"))

    def test_negative_learning_rate(self):
        with pytest.raises(ValueError, match="must be positive"):
            SFTConfig(learning_rate=-1e-4)

    def test_zero_learning_rate(self):
        with pytest.raises(ValueError, match="must be positive"):
            SFTConfig(learning_rate=0.0)

    def test_nan_warmup_ratio(self):
        with pytest.raises(ValueError, match="must be finite"):
            SFTConfig(warmup_ratio=float("nan"))

    def test_bf16_fp16_mutual_exclusion(self):
        with pytest.raises(ValueError, match="Cannot enable both bf16 and fp16"):
            SFTConfig(bf16=True, fp16=True)

    def test_warmup_ratio_out_of_range(self):
        with pytest.raises(ValueError, match="warmup_ratio must be in"):
            SFTConfig(warmup_ratio=1.0)


# --- DPOConfig ---


class TestDPOConfig:
    def test_defaults(self):
        cfg = DPOConfig()
        assert cfg.num_train_epochs == 1
        assert cfg.learning_rate == 5e-5
        assert cfg.beta == 0.1

    def test_frozen(self):
        cfg = DPOConfig()
        with pytest.raises(AttributeError):
            cfg.beta = 0.5  # type: ignore[misc]

    def test_nan_beta(self):
        with pytest.raises(ValueError, match="must be finite"):
            DPOConfig(beta=float("nan"))

    def test_inf_beta(self):
        with pytest.raises(ValueError, match="must be finite"):
            DPOConfig(beta=float("inf"))

    def test_negative_beta(self):
        with pytest.raises(ValueError, match="must be positive"):
            DPOConfig(beta=-0.1)

    def test_zero_beta(self):
        with pytest.raises(ValueError, match="must be positive"):
            DPOConfig(beta=0.0)

    def test_nan_learning_rate(self):
        with pytest.raises(ValueError, match="must be finite"):
            DPOConfig(learning_rate=float("nan"))

    def test_bf16_fp16_mutual_exclusion(self):
        with pytest.raises(ValueError, match="Cannot enable both bf16 and fp16"):
            DPOConfig(bf16=True, fp16=True)


# --- AdapterSignature ---


class TestAdapterSignature:
    def test_defaults(self):
        sig = AdapterSignature(base_model_id="test/model")
        assert sig.adapter_type == "lora"
        assert sig.rank == 16
        assert sig.alpha == 32
        assert sig.target_modules == ("q_proj", "v_proj")
        assert sig.task_type == "CAUSAL_LM"
        assert sig.training_method == "sft"

    def test_frozen(self):
        sig = AdapterSignature(base_model_id="test/model")
        with pytest.raises(AttributeError):
            sig.rank = 8  # type: ignore[misc]

    def test_empty_base_model_id(self):
        with pytest.raises(ValueError, match="base_model_id is required"):
            AdapterSignature(base_model_id="")

    def test_invalid_rank(self):
        with pytest.raises(ValueError, match="rank must be >= 1"):
            AdapterSignature(base_model_id="test/model", rank=0)

    def test_invalid_alpha(self):
        with pytest.raises(ValueError, match="alpha must be >= 1"):
            AdapterSignature(base_model_id="test/model", alpha=0)

    def test_empty_target_modules(self):
        with pytest.raises(ValueError, match="target_modules must not be empty"):
            AdapterSignature(base_model_id="test/model", target_modules=())

    def test_invalid_adapter_type(self):
        with pytest.raises(ValueError, match="adapter_type must be"):
            AdapterSignature(base_model_id="test/model", adapter_type="prefix")

    def test_invalid_training_method(self):
        with pytest.raises(ValueError, match="Unknown training method"):
            AdapterSignature(base_model_id="test/model", training_method="nonexistent")

    def test_valid_qlora(self):
        sig = AdapterSignature(base_model_id="test/model", adapter_type="qlora")
        assert sig.adapter_type == "qlora"

    def test_valid_dpo_method(self):
        sig = AdapterSignature(base_model_id="test/model", training_method="dpo")
        assert sig.training_method == "dpo"

    def test_valid_sft_then_dpo_method(self):
        sig = AdapterSignature(
            base_model_id="test/model", training_method="sft_then_dpo"
        )
        assert sig.training_method == "sft_then_dpo"


# --- AlignmentConfig ---


class TestAlignmentConfig:
    def test_defaults_require_base_model(self):
        with pytest.raises(ValueError, match="base_model_id is required"):
            AlignmentConfig()

    def test_valid_construction(self):
        cfg = AlignmentConfig(base_model_id="test/model")
        assert cfg.method == "sft_then_dpo"
        assert cfg.base_model_id == "test/model"
        assert isinstance(cfg.lora, LoRAConfig)
        assert isinstance(cfg.sft, SFTConfig)
        assert isinstance(cfg.dpo, DPOConfig)

    def test_invalid_method(self):
        with pytest.raises(ValueError, match="Unknown training method"):
            AlignmentConfig(base_model_id="test/model", method="nonexistent")

    def test_sft_method(self):
        cfg = AlignmentConfig(base_model_id="test/model", method="sft")
        assert cfg.method == "sft"

    def test_dpo_method(self):
        cfg = AlignmentConfig(base_model_id="test/model", method="dpo")
        assert cfg.method == "dpo"

    def test_validate_no_warnings(self):
        cfg = AlignmentConfig(base_model_id="test/model")
        warnings = cfg.validate()
        assert warnings == []

    def test_mutable(self):
        cfg = AlignmentConfig(base_model_id="test/model")
        cfg.method = "sft"  # AlignmentConfig is mutable (not frozen)
        assert cfg.method == "sft"

    def test_qlora_without_bitsandbytes(self):
        # This test validates the import check fires.
        # In test environments bitsandbytes may or may not be available.
        # We just verify the config is constructible if bitsandbytes is found,
        # or raises ImportError if not.
        try:
            import bitsandbytes  # noqa: F401

            cfg = AlignmentConfig(base_model_id="test/model", use_qlora=True)
            assert cfg.use_qlora is True
        except ImportError:
            with pytest.raises(ImportError, match="bitsandbytes"):
                AlignmentConfig(base_model_id="test/model", use_qlora=True)
