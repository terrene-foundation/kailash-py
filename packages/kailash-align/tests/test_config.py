# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tests for AlignmentConfig and sub-configs."""
from __future__ import annotations

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


# --- trl 1.x compatibility (issue #1426) ---
#
# Behavioral tests: call to_trl_config() against the INSTALLED trl and assert
# the result constructs without TypeError. The old field names (max_seq_length,
# max_prompt_length) and the removed classes (ORPOConfig, OnlineDPOConfig) broke
# every one of these against trl >=1.0. Config construction only -- no GPU.


@pytest.mark.unit
class TestTrl1xCompat:
    """Guards that to_trl_config() forwards trl 1.x kwarg names, not 0.x."""

    def test_sft_to_trl_config_trl1x_compat(self):
        from kailash_align.config import SFTConfig as KASFTConfig

        pytest.importorskip("trl")
        # Must construct without TypeError. trl 1.x has max_length (not
        # max_seq_length); the dataclass field stays max_seq_length.
        trl_cfg = KASFTConfig(max_seq_length=512).to_trl_config("/tmp/x")
        assert trl_cfg.max_length == 512

    def test_dpo_to_trl_config_trl1x_compat(self):
        from kailash_align.config import DPOConfig as KADPOConfig

        pytest.importorskip("trl")
        # trl 1.x DPOConfig has max_length, NOT max_prompt_length.
        trl_cfg = KADPOConfig(max_length=1024).to_trl_config("/tmp/x")
        assert trl_cfg.max_length == 1024

    def test_kto_to_trl_config_trl1x_compat(self):
        from kailash_align.config import KTOConfig as KAKTOConfig

        pytest.importorskip("trl")
        # trl 1.x KTOConfig has max_length, NOT max_prompt_length.
        trl_cfg = KAKTOConfig(max_length=768).to_trl_config("/tmp/x")
        assert trl_cfg.max_length == 768

    def test_grpo_to_trl_config_trl1x_compat(self):
        from kailash_align.config import GRPOConfig as KAGRPOConfig

        pytest.importorskip("trl")
        # trl 1.x renamed kl_coef -> beta. Default path (use_vllm=False).
        trl_cfg = KAGRPOConfig(max_completion_length=256, kl_coef=0.02).to_trl_config(
            "/tmp/x"
        )
        assert trl_cfg.max_completion_length == 256
        assert trl_cfg.beta == 0.02

    def test_grpo_to_trl_config_trl1x_compat_vllm(self):
        from kailash_align.config import GRPOConfig as KAGRPOConfig

        pytest.importorskip("trl")
        # trl 1.x renamed vllm_gpu_utilization -> vllm_gpu_memory_utilization.
        trl_cfg = KAGRPOConfig(use_vllm=True, vllm_gpu_utilization=0.4).to_trl_config(
            "/tmp/x"
        )
        assert trl_cfg.use_vllm is True
        assert trl_cfg.vllm_gpu_memory_utilization == 0.4

    def test_rloo_to_trl_config_trl1x_compat(self):
        from kailash_align.config import RLOOConfig as KARLOOConfig

        pytest.importorskip("trl")
        # trl 1.x renamed kl_coef -> beta. Default path (use_vllm=False).
        trl_cfg = KARLOOConfig(max_completion_length=256, kl_coef=0.02).to_trl_config(
            "/tmp/x"
        )
        assert trl_cfg.max_completion_length == 256
        assert trl_cfg.beta == 0.02

    def test_rloo_to_trl_config_trl1x_compat_vllm(self):
        from kailash_align.config import RLOOConfig as KARLOOConfig

        pytest.importorskip("trl")
        # trl 1.x renamed vllm_gpu_utilization -> vllm_gpu_memory_utilization.
        trl_cfg = KARLOOConfig(use_vllm=True, vllm_gpu_utilization=0.4).to_trl_config(
            "/tmp/x"
        )
        assert trl_cfg.use_vllm is True
        assert trl_cfg.vllm_gpu_memory_utilization == 0.4

    def test_orpo_to_trl_config_trl1x_compat_raises(self):
        from kailash_align.config import ORPOConfig as KAORPOConfig
        from kailash_align.exceptions import TrainingError

        # ORPOConfig/ORPOTrainer were removed in trl >=1.0. Calling
        # to_trl_config() must raise an informative error pointing at DPO/GRPO.
        with pytest.raises(TrainingError, match="trl >=1.0 removed"):
            KAORPOConfig().to_trl_config("/tmp/x")

    def test_online_dpo_to_trl_config_trl1x_compat_raises(self):
        from kailash_align.config import OnlineDPOConfig as KAOnlineDPOConfig
        from kailash_align.exceptions import TrainingError

        # OnlineDPOConfig/OnlineDPOTrainer were removed in trl >=1.0.
        with pytest.raises(TrainingError, match="trl >=1.0 removed"):
            KAOnlineDPOConfig().to_trl_config("/tmp/x")
