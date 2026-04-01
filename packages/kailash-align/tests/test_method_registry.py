# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tests for MethodRegistry, new config classes, AlignmentConfig updates, and AdapterSignature.

Tier 1 unit tests -- no torch, TRL, or GPU dependencies required.
"""
from __future__ import annotations

import math
import warnings

import pytest

from kailash_align.config import (
    AdapterSignature,
    AlignmentConfig,
    GRPOConfig,
    KTOConfig,
    OnlineDPOConfig,
    ORPOConfig,
    RLOOConfig,
)
from kailash_align.exceptions import AlignmentError
from kailash_align.method_registry import (
    METHOD_REGISTRY,
    MethodConfig,
    _lazy_import,
    get_method,
    register_method,
    validate_method_name,
)


# =============================================================================
# Section 1: Method Registry
# =============================================================================


class TestMethodRegistryCompleteness:
    """All expected methods are registered with correct metadata."""

    EXPECTED_METHODS = {
        "sft",
        "dpo",
        "kto",
        "orpo",
        "grpo",
        "rloo",
        "online_dpo",
        "xpo",
        "nash_md",
        "cpo",
        "bco",
        "ppo",
    }

    def test_all_methods_registered(self):
        """All 12 built-in methods are present in the registry."""
        assert self.EXPECTED_METHODS == set(METHOD_REGISTRY.keys())

    def test_registry_count(self):
        """Exactly 12 methods are registered (no accidental extras)."""
        assert len(METHOD_REGISTRY) == 12


class TestGetMethod:
    """get_method() returns correct MethodConfig or raises on unknown."""

    @pytest.mark.parametrize(
        "name",
        [
            "sft",
            "dpo",
            "kto",
            "orpo",
            "grpo",
            "rloo",
            "online_dpo",
            "xpo",
            "nash_md",
            "cpo",
            "bco",
        ],
    )
    def test_returns_method_config(self, name: str):
        config = get_method(name)
        assert isinstance(config, MethodConfig)
        assert config.name == name

    def test_unknown_method_raises_alignment_error(self):
        with pytest.raises(
            AlignmentError, match="Unknown training method 'nonexistent'"
        ):
            get_method("nonexistent")

    def test_error_message_lists_available_methods(self):
        with pytest.raises(AlignmentError, match="Available methods:"):
            get_method("invalid_method")


class TestValidateMethodName:
    """validate_method_name() accepts registered methods + 'sft_then_dpo'."""

    @pytest.mark.parametrize(
        "name",
        [
            "sft",
            "dpo",
            "kto",
            "orpo",
            "grpo",
            "rloo",
            "online_dpo",
            "xpo",
            "nash_md",
            "cpo",
            "bco",
        ],
    )
    def test_valid_registered_methods(self, name: str):
        validate_method_name(name)  # Should not raise

    def test_sft_then_dpo_is_valid(self):
        validate_method_name("sft_then_dpo")  # Special combo method

    def test_unknown_method_raises_value_error(self):
        with pytest.raises(ValueError, match="Unknown training method"):
            validate_method_name("totally_fake_method")

    def test_error_includes_sft_then_dpo_in_available(self):
        with pytest.raises(ValueError, match="sft_then_dpo"):
            validate_method_name("invalid")


class TestRegisterMethod:
    """register_method() adds custom methods to the global registry."""

    def test_register_custom_method(self):
        custom = MethodConfig(
            name="test_custom_method",
            trainer_module="test_module",
            trainer_class_name="TestTrainer",
            config_module="test_module",
            config_class_name="TestConfig",
            dataset_validator=lambda ds: None,
            category="custom",
        )
        register_method(custom)
        assert "test_custom_method" in METHOD_REGISTRY
        assert get_method("test_custom_method") is custom

        # Cleanup to avoid polluting other tests
        del METHOD_REGISTRY["test_custom_method"]

    def test_register_overwrites_existing(self):
        original = get_method("sft")
        custom = MethodConfig(
            name="sft",
            trainer_module="custom",
            trainer_class_name="CustomSFT",
            config_module="custom",
            config_class_name="CustomSFTConfig",
            dataset_validator=lambda ds: None,
        )
        register_method(custom)
        assert get_method("sft").trainer_module == "custom"

        # Restore original
        register_method(original)
        assert get_method("sft").trainer_module == "trl"


class TestCategoryClassification:
    """Methods are classified into correct categories."""

    OFFLINE_METHODS = {"sft", "dpo", "cpo"}
    UNPAIRED_METHODS = {"kto", "bco"}
    MONOLITHIC_METHODS = {"orpo"}
    ONLINE_METHODS = {"grpo", "rloo", "online_dpo", "xpo", "nash_md", "ppo"}

    @pytest.mark.parametrize("name", OFFLINE_METHODS)
    def test_offline_category(self, name: str):
        assert get_method(name).category == "offline"

    @pytest.mark.parametrize("name", UNPAIRED_METHODS)
    def test_unpaired_category(self, name: str):
        assert get_method(name).category == "unpaired"

    @pytest.mark.parametrize("name", MONOLITHIC_METHODS)
    def test_monolithic_category(self, name: str):
        assert get_method(name).category == "monolithic"

    @pytest.mark.parametrize("name", ONLINE_METHODS)
    def test_online_category(self, name: str):
        assert get_method(name).category == "online"


class TestMethodFlags:
    """Method boolean flags are set correctly."""

    REWARD_FUNC_METHODS = {"grpo", "rloo", "xpo", "nash_md", "ppo"}
    GENERATION_BACKEND_METHODS = {"grpo", "rloo", "online_dpo", "xpo", "nash_md", "ppo"}
    PREFERENCE_DATA_METHODS = {"dpo", "orpo", "cpo"}
    SUPPORTS_LOSS_TYPE_METHODS = {"dpo"}

    @pytest.mark.parametrize("name", REWARD_FUNC_METHODS)
    def test_requires_reward_func_true(self, name: str):
        assert get_method(name).requires_reward_func is True

    @pytest.mark.parametrize(
        "name",
        ["sft", "dpo", "kto", "orpo", "online_dpo", "cpo", "bco"],
    )
    def test_requires_reward_func_false(self, name: str):
        assert get_method(name).requires_reward_func is False

    @pytest.mark.parametrize("name", GENERATION_BACKEND_METHODS)
    def test_requires_generation_backend_true(self, name: str):
        assert get_method(name).requires_generation_backend is True

    @pytest.mark.parametrize(
        "name",
        ["sft", "dpo", "kto", "orpo", "cpo", "bco"],
    )
    def test_requires_generation_backend_false(self, name: str):
        assert get_method(name).requires_generation_backend is False

    @pytest.mark.parametrize("name", PREFERENCE_DATA_METHODS)
    def test_requires_preference_data_true(self, name: str):
        assert get_method(name).requires_preference_data is True

    @pytest.mark.parametrize(
        "name",
        ["sft", "kto", "grpo", "rloo", "online_dpo", "xpo", "nash_md", "bco"],
    )
    def test_requires_preference_data_false(self, name: str):
        assert get_method(name).requires_preference_data is False

    def test_supports_loss_type_only_dpo(self):
        for name, config in METHOD_REGISTRY.items():
            if name == "dpo":
                assert (
                    config.supports_loss_type is True
                ), f"{name} should support loss_type"
            else:
                assert (
                    config.supports_loss_type is False
                ), f"{name} should not support loss_type"


class TestLazyImport:
    """_lazy_import handles missing modules and attributes gracefully."""

    def test_import_nonexistent_module_raises(self):
        with pytest.raises(ImportError, match="Cannot import"):
            _lazy_import("nonexistent_module_xyz_12345", "SomeClass")

    def test_import_nonexistent_class_raises(self):
        with pytest.raises(ImportError, match="does not have attribute"):
            _lazy_import("os", "NonExistentClass_xyz_12345")

    def test_import_existing_module_and_class(self):
        # Use a stdlib class to verify the mechanism works
        result = _lazy_import("os.path", "join")
        import os.path

        assert result is os.path.join

    def test_error_message_suggests_pip_install(self):
        with pytest.raises(ImportError, match="pip install kailash-align"):
            _lazy_import("totally_missing_package_xyz", "Trainer")


class TestMethodConfigDataclass:
    """MethodConfig is frozen and has correct defaults."""

    def test_frozen(self):
        config = get_method("sft")
        with pytest.raises(AttributeError):
            config.name = "changed"  # type: ignore[misc]

    def test_defaults(self):
        config = MethodConfig(
            name="test",
            trainer_module="mod",
            trainer_class_name="Cls",
            config_module="mod",
            config_class_name="CfgCls",
            dataset_validator=lambda ds: None,
        )
        assert config.requires_preference_data is False
        assert config.requires_reward_func is False
        assert config.requires_generation_backend is False
        assert config.supports_loss_type is False
        assert config.category == "offline"
        assert config.dataset_required_columns == frozenset()

    def test_trainer_references_are_strings(self):
        """All registered methods use string-based lazy references, not actual classes."""
        for name, config in METHOD_REGISTRY.items():
            assert isinstance(
                config.trainer_module, str
            ), f"{name} trainer_module not string"
            assert isinstance(
                config.trainer_class_name, str
            ), f"{name} trainer_class_name not string"
            assert isinstance(
                config.config_module, str
            ), f"{name} config_module not string"
            assert isinstance(
                config.config_class_name, str
            ), f"{name} config_class_name not string"


# =============================================================================
# Section 2: New Config Classes
# =============================================================================


class TestKTOConfig:
    """KTOConfig defaults, validation, and construction."""

    def test_defaults(self):
        config = KTOConfig()
        assert config.learning_rate == 5e-7
        assert config.beta == 0.1
        assert config.desirable_weight == 1.0
        assert config.undesirable_weight == 1.0
        assert config.max_length == 1024
        assert config.max_prompt_length == 512
        assert config.bf16 is True
        assert config.fp16 is False
        assert config.num_train_epochs == 1

    def test_nan_beta_raises(self):
        with pytest.raises(ValueError, match="must be finite"):
            KTOConfig(beta=float("nan"))

    def test_negative_desirable_weight_raises(self):
        with pytest.raises(ValueError, match="must be positive"):
            KTOConfig(desirable_weight=-1.0)

    def test_negative_undesirable_weight_raises(self):
        with pytest.raises(ValueError, match="must be positive"):
            KTOConfig(undesirable_weight=-0.5)

    def test_bf16_and_fp16_raises(self):
        with pytest.raises(ValueError, match="Cannot enable both bf16 and fp16"):
            KTOConfig(bf16=True, fp16=True)

    def test_zero_beta_raises(self):
        with pytest.raises(ValueError, match="must be positive"):
            KTOConfig(beta=0.0)

    def test_inf_learning_rate_raises(self):
        with pytest.raises(ValueError, match="must be finite"):
            KTOConfig(learning_rate=float("inf"))

    def test_frozen(self):
        config = KTOConfig()
        with pytest.raises(AttributeError):
            config.beta = 0.5  # type: ignore[misc]

    def test_custom_values(self):
        config = KTOConfig(
            learning_rate=1e-6,
            beta=0.2,
            desirable_weight=1.5,
            undesirable_weight=0.5,
        )
        assert config.learning_rate == 1e-6
        assert config.beta == 0.2
        assert config.desirable_weight == 1.5
        assert config.undesirable_weight == 0.5


class TestORPOConfig:
    """ORPOConfig defaults and validation."""

    def test_defaults(self):
        config = ORPOConfig()
        assert config.learning_rate == 8e-6
        assert config.beta == 0.1
        assert config.max_length == 1024
        assert config.max_prompt_length == 512
        assert config.bf16 is True
        assert config.num_train_epochs == 1

    def test_learning_rate_default_is_8e_6(self):
        """ORPO paper recommends 8e-6 as the default learning rate."""
        config = ORPOConfig()
        assert config.learning_rate == 8e-6

    def test_nan_beta_raises(self):
        with pytest.raises(ValueError, match="must be finite"):
            ORPOConfig(beta=float("nan"))

    def test_bf16_and_fp16_raises(self):
        with pytest.raises(ValueError, match="Cannot enable both bf16 and fp16"):
            ORPOConfig(bf16=True, fp16=True)

    def test_negative_learning_rate_raises(self):
        with pytest.raises(ValueError, match="must be positive"):
            ORPOConfig(learning_rate=-1e-5)

    def test_zero_beta_raises(self):
        with pytest.raises(ValueError, match="must be positive"):
            ORPOConfig(beta=0.0)

    def test_warmup_ratio_out_of_range_raises(self):
        with pytest.raises(ValueError, match="warmup_ratio must be in"):
            ORPOConfig(warmup_ratio=1.0)

    def test_frozen(self):
        config = ORPOConfig()
        with pytest.raises(AttributeError):
            config.learning_rate = 1e-4  # type: ignore[misc]


class TestGRPOConfig:
    """GRPOConfig defaults and validation (online RL)."""

    def test_defaults(self):
        config = GRPOConfig()
        assert config.num_generations == 4
        assert config.temperature == 0.7
        assert config.max_completion_length == 2048
        assert config.learning_rate == 1e-5
        assert config.kl_coef == 0.001
        assert config.use_vllm is False
        assert config.vllm_gpu_utilization == 0.5
        assert config.bf16 is True

    def test_default_num_generations_is_4(self):
        """4 fits single GPU; DeepSeek used 16."""
        config = GRPOConfig()
        assert config.num_generations == 4

    def test_negative_kl_coef_raises(self):
        with pytest.raises(ValueError, match="kl_coef must be >= 0"):
            GRPOConfig(kl_coef=-0.01)

    def test_nan_kl_coef_raises(self):
        with pytest.raises(ValueError, match="must be finite"):
            GRPOConfig(kl_coef=float("nan"))

    def test_zero_temperature_raises(self):
        with pytest.raises(ValueError, match="temperature must be > 0"):
            GRPOConfig(temperature=0.0)

    def test_negative_temperature_raises(self):
        with pytest.raises(ValueError, match="temperature must be > 0"):
            GRPOConfig(temperature=-0.5)

    def test_nan_temperature_raises(self):
        with pytest.raises(ValueError, match="must be finite"):
            GRPOConfig(temperature=float("nan"))

    def test_invalid_vllm_gpu_utilization_zero(self):
        with pytest.raises(ValueError, match="vllm_gpu_utilization must be in"):
            GRPOConfig(vllm_gpu_utilization=0.0)

    def test_invalid_vllm_gpu_utilization_above_one(self):
        with pytest.raises(ValueError, match="vllm_gpu_utilization must be in"):
            GRPOConfig(vllm_gpu_utilization=1.5)

    def test_num_generations_less_than_1_raises(self):
        with pytest.raises(ValueError, match="num_generations must be >= 1"):
            GRPOConfig(num_generations=0)

    def test_negative_num_generations_raises(self):
        with pytest.raises(ValueError, match="num_generations must be >= 1"):
            GRPOConfig(num_generations=-2)

    def test_bf16_and_fp16_raises(self):
        with pytest.raises(ValueError, match="Cannot enable both bf16 and fp16"):
            GRPOConfig(bf16=True, fp16=True)

    def test_zero_kl_coef_allowed(self):
        """kl_coef=0 is valid (no KL penalty)."""
        config = GRPOConfig(kl_coef=0.0)
        assert config.kl_coef == 0.0

    def test_vllm_gpu_utilization_one_allowed(self):
        """100% GPU utilization is valid (boundary)."""
        config = GRPOConfig(vllm_gpu_utilization=1.0)
        assert config.vllm_gpu_utilization == 1.0

    def test_frozen(self):
        config = GRPOConfig()
        with pytest.raises(AttributeError):
            config.num_generations = 8  # type: ignore[misc]


class TestRLOOConfig:
    """RLOOConfig defaults and validation (mirrors GRPO structure)."""

    def test_defaults(self):
        config = RLOOConfig()
        assert config.num_generations == 4
        assert config.temperature == 0.7
        assert config.kl_coef == 0.001
        assert config.learning_rate == 1e-5
        assert config.use_vllm is False

    def test_negative_kl_coef_raises(self):
        with pytest.raises(ValueError, match="kl_coef must be >= 0"):
            RLOOConfig(kl_coef=-0.01)

    def test_zero_temperature_raises(self):
        with pytest.raises(ValueError, match="temperature must be > 0"):
            RLOOConfig(temperature=0.0)

    def test_invalid_vllm_gpu_utilization(self):
        with pytest.raises(ValueError, match="vllm_gpu_utilization must be in"):
            RLOOConfig(vllm_gpu_utilization=0.0)

    def test_num_generations_less_than_1_raises(self):
        with pytest.raises(ValueError, match="num_generations must be >= 1"):
            RLOOConfig(num_generations=0)

    def test_bf16_and_fp16_raises(self):
        with pytest.raises(ValueError, match="Cannot enable both bf16 and fp16"):
            RLOOConfig(bf16=True, fp16=True)

    def test_nan_temperature_raises(self):
        with pytest.raises(ValueError, match="must be finite"):
            RLOOConfig(temperature=float("nan"))

    def test_frozen(self):
        config = RLOOConfig()
        with pytest.raises(AttributeError):
            config.kl_coef = 0.1  # type: ignore[misc]


class TestOnlineDPOConfig:
    """OnlineDPOConfig defaults and validation."""

    def test_defaults(self):
        config = OnlineDPOConfig()
        assert config.learning_rate == 5e-5
        assert config.beta == 0.1
        assert config.max_length == 2048
        assert config.max_prompt_length == 512
        assert config.max_completion_length == 512
        assert config.use_vllm is False
        assert config.vllm_gpu_utilization == 0.5
        assert config.bf16 is True

    def test_negative_beta_raises(self):
        with pytest.raises(ValueError, match="must be positive"):
            OnlineDPOConfig(beta=-0.1)

    def test_nan_beta_raises(self):
        with pytest.raises(ValueError, match="must be finite"):
            OnlineDPOConfig(beta=float("nan"))

    def test_bf16_and_fp16_raises(self):
        with pytest.raises(ValueError, match="Cannot enable both bf16 and fp16"):
            OnlineDPOConfig(bf16=True, fp16=True)

    def test_invalid_vllm_gpu_utilization(self):
        with pytest.raises(ValueError, match="vllm_gpu_utilization must be in"):
            OnlineDPOConfig(vllm_gpu_utilization=0.0)

    def test_warmup_ratio_out_of_range(self):
        with pytest.raises(ValueError, match="warmup_ratio must be in"):
            OnlineDPOConfig(warmup_ratio=1.5)

    def test_negative_warmup_ratio(self):
        with pytest.raises(ValueError, match="warmup_ratio must be in"):
            OnlineDPOConfig(warmup_ratio=-0.1)

    def test_frozen(self):
        config = OnlineDPOConfig()
        with pytest.raises(AttributeError):
            config.beta = 0.5  # type: ignore[misc]


# =============================================================================
# Section 3: AlignmentConfig updates
# =============================================================================


class TestAlignmentConfigAutoCreate:
    """AlignmentConfig auto-creates method-specific configs when method is set."""

    def test_kto_auto_creates_config(self):
        config = AlignmentConfig(method="kto", base_model_id="test/model")
        assert config.kto is not None
        assert isinstance(config.kto, KTOConfig)

    def test_grpo_auto_creates_config(self):
        config = AlignmentConfig(method="grpo", base_model_id="test/model")
        assert config.grpo is not None
        assert isinstance(config.grpo, GRPOConfig)

    def test_rloo_auto_creates_config(self):
        config = AlignmentConfig(method="rloo", base_model_id="test/model")
        assert config.rloo is not None
        assert isinstance(config.rloo, RLOOConfig)

    def test_orpo_auto_creates_config(self):
        config = AlignmentConfig(method="orpo", base_model_id="test/model")
        assert config.orpo is not None
        assert isinstance(config.orpo, ORPOConfig)

    def test_online_dpo_auto_creates_config(self):
        config = AlignmentConfig(method="online_dpo", base_model_id="test/model")
        assert config.online_dpo is not None
        assert isinstance(config.online_dpo, OnlineDPOConfig)

    def test_cpo_works_without_dedicated_config(self):
        """CPO is an experimental method with no dedicated config class."""
        config = AlignmentConfig(method="cpo", base_model_id="test/model")
        # CPO has no dedicated config field; get_method_config falls back to sft
        method_config = config.get_method_config("cpo")
        assert method_config is config.sft

    def test_bco_works_without_dedicated_config(self):
        """BCO is an experimental method with no dedicated config class."""
        config = AlignmentConfig(method="bco", base_model_id="test/model")
        method_config = config.get_method_config("bco")
        assert method_config is config.sft

    def test_custom_kto_config_preserved(self):
        """User-provided KTO config is not overwritten by auto-create."""
        custom_kto = KTOConfig(beta=0.5, learning_rate=1e-6)
        config = AlignmentConfig(
            method="kto", base_model_id="test/model", kto=custom_kto
        )
        assert config.kto is custom_kto
        assert config.kto.beta == 0.5


class TestAlignmentConfigFields:
    """AlignmentConfig loss_type, reward_funcs, and validation."""

    def test_loss_type_passthrough(self):
        config = AlignmentConfig(
            method="dpo", base_model_id="test/model", loss_type="ipo"
        )
        assert config.loss_type == "ipo"

    def test_loss_type_default_is_none(self):
        config = AlignmentConfig(method="dpo", base_model_id="test/model")
        assert config.loss_type is None

    def test_reward_funcs_stores_list(self):
        config = AlignmentConfig(
            method="grpo",
            base_model_id="test/model",
            reward_funcs=["accuracy", "format_check"],
        )
        assert config.reward_funcs == ["accuracy", "format_check"]

    def test_reward_funcs_default_is_empty(self):
        config = AlignmentConfig(method="grpo", base_model_id="test/model")
        assert config.reward_funcs == []

    def test_validate_warns_online_method_no_reward_funcs(self):
        """Online methods requiring reward_funcs generate a warning from validate()."""
        config = AlignmentConfig(method="grpo", base_model_id="test/model")
        warnings_list = config.validate()
        assert any("reward_funcs" in w for w in warnings_list)

    def test_validate_no_warning_when_reward_funcs_provided(self):
        config = AlignmentConfig(
            method="grpo",
            base_model_id="test/model",
            reward_funcs=["accuracy"],
        )
        warnings_list = config.validate()
        assert not any("reward_funcs" in w for w in warnings_list)

    def test_validate_rloo_warns_no_reward_funcs(self):
        config = AlignmentConfig(method="rloo", base_model_id="test/model")
        warnings_list = config.validate()
        assert any("reward_funcs" in w for w in warnings_list)

    def test_validate_xpo_warns_no_reward_funcs(self):
        config = AlignmentConfig(method="xpo", base_model_id="test/model")
        warnings_list = config.validate()
        assert any("reward_funcs" in w for w in warnings_list)

    def test_validate_nash_md_warns_no_reward_funcs(self):
        config = AlignmentConfig(method="nash_md", base_model_id="test/model")
        warnings_list = config.validate()
        assert any("reward_funcs" in w for w in warnings_list)

    def test_validate_sft_no_reward_func_warning(self):
        """SFT does not require reward_funcs -- no warning expected."""
        config = AlignmentConfig(method="sft", base_model_id="test/model")
        warnings_list = config.validate()
        assert not any("reward_funcs" in w for w in warnings_list)

    def test_base_model_id_required(self):
        with pytest.raises(ValueError, match="base_model_id is required"):
            AlignmentConfig(method="sft", base_model_id="")

    def test_unknown_method_raises(self):
        with pytest.raises(ValueError, match="Unknown training method"):
            AlignmentConfig(method="totally_invalid", base_model_id="test/model")


class TestAlignmentConfigGetMethodConfig:
    """get_method_config() returns correct config for each method."""

    def test_sft_returns_sft_config(self):
        config = AlignmentConfig(method="sft", base_model_id="test/model")
        assert config.get_method_config("sft") is config.sft

    def test_dpo_returns_dpo_config(self):
        config = AlignmentConfig(method="dpo", base_model_id="test/model")
        assert config.get_method_config("dpo") is config.dpo

    def test_kto_returns_kto_config(self):
        config = AlignmentConfig(method="kto", base_model_id="test/model")
        assert config.get_method_config("kto") is config.kto

    def test_grpo_returns_grpo_config(self):
        config = AlignmentConfig(method="grpo", base_model_id="test/model")
        assert config.get_method_config("grpo") is config.grpo

    def test_experimental_falls_back_to_sft(self):
        """xpo, nash_md, cpo, bco have no dedicated config -- fall back to sft."""
        config = AlignmentConfig(method="xpo", base_model_id="test/model")
        assert config.get_method_config("xpo") is config.sft


# =============================================================================
# Section 4: AdapterSignature updates
# =============================================================================


class TestAdapterSignatureTrainingMethods:
    """AdapterSignature accepts all registered methods as training_method."""

    @pytest.mark.parametrize(
        "method",
        [
            "sft",
            "dpo",
            "kto",
            "grpo",
            "rloo",
            "orpo",
            "online_dpo",
            "xpo",
            "nash_md",
            "cpo",
            "bco",
        ],
    )
    def test_registered_methods_valid(self, method: str):
        sig = AdapterSignature(base_model_id="test/model", training_method=method)
        assert sig.training_method == method

    def test_sft_then_dpo_still_valid(self):
        sig = AdapterSignature(
            base_model_id="test/model", training_method="sft_then_dpo"
        )
        assert sig.training_method == "sft_then_dpo"

    def test_unknown_method_raises(self):
        with pytest.raises(ValueError, match="Unknown training method"):
            AdapterSignature(base_model_id="test/model", training_method="fake_method")

    def test_empty_base_model_id_raises(self):
        with pytest.raises(ValueError, match="base_model_id is required"):
            AdapterSignature(base_model_id="", training_method="sft")

    def test_default_training_method_is_sft(self):
        sig = AdapterSignature(base_model_id="test/model")
        assert sig.training_method == "sft"

    def test_adapter_type_validation(self):
        with pytest.raises(ValueError, match="adapter_type must be"):
            AdapterSignature(base_model_id="test/model", adapter_type="invalid")

    def test_frozen(self):
        sig = AdapterSignature(base_model_id="test/model")
        with pytest.raises(AttributeError):
            sig.training_method = "dpo"  # type: ignore[misc]
