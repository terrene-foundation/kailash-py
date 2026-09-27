# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier-1 unit tests — algorithm adapter dispatch + error hierarchy.

Covers W29 invariants #7 (RLError) and #8 (8-algorithm dispatch,
unknown -> RLError not RuntimeError/ValueError).
"""
from __future__ import annotations

import pytest

from kailash_ml.errors import FeatureNotYetSupportedError, RLError
from kailash_ml.rl.algorithms import (
    A2CAdapter,
    AlgorithmAdapter,
    DDPGAdapter,
    DecisionTransformerAdapter,
    DQNAdapter,
    MaskablePPOAdapter,
    PPOAdapter,
    SACAdapter,
    TD3Adapter,
    load_adapter_class,
    register_algorithm,
    supported_algorithm_names,
)


class TestAdapterDispatch:
    """W29 invariant #8 — 8 algorithms registered, unknown raises RLError."""

    def test_all_8_algorithms_registered(self) -> None:
        names = supported_algorithm_names()
        for required in (
            "ppo",
            "sac",
            "dqn",
            "a2c",
            "td3",
            "ddpg",
            "maskable-ppo",
            "decision-transformer",
        ):
            assert required in names, f"missing algorithm: {required}"

    def test_lowercase_canonical(self) -> None:
        assert load_adapter_class("ppo") is PPOAdapter
        assert load_adapter_class("sac") is SACAdapter
        assert load_adapter_class("dqn") is DQNAdapter
        assert load_adapter_class("a2c") is A2CAdapter
        assert load_adapter_class("td3") is TD3Adapter
        assert load_adapter_class("ddpg") is DDPGAdapter
        assert load_adapter_class("maskable-ppo") is MaskablePPOAdapter
        assert load_adapter_class("decision-transformer") is DecisionTransformerAdapter

    def test_uppercase_alias(self) -> None:
        """Legacy uppercase names resolve to the same adapter class."""
        assert load_adapter_class("PPO") is PPOAdapter
        assert load_adapter_class("SAC") is SACAdapter
        assert load_adapter_class("MaskablePPO") is MaskablePPOAdapter
        assert load_adapter_class("DecisionTransformer") is DecisionTransformerAdapter

    def test_unknown_algorithm_raises_rl_error(self) -> None:
        """Unknown algo -> RLError, not RuntimeError/ValueError."""
        with pytest.raises(RLError) as exc:
            load_adapter_class("bogus-algo")
        assert exc.value.reason == "unknown_algorithm"
        assert exc.value.context["algorithm"] == "bogus-algo"

    def test_case_insensitive_lowercase_fallback(self) -> None:
        """Mixed-case user input resolves via the lowercase path."""
        assert load_adapter_class("Ppo") is PPOAdapter


class TestDefaultHyperparameters:
    """Per spec §3.4 — adapters inject their own GAE / policy defaults."""

    def test_ppo_defaults(self) -> None:
        assert PPOAdapter.default_hyperparameters["gae_lambda"] == 0.95
        assert PPOAdapter.default_hyperparameters["gamma"] == 0.99
        assert PPOAdapter.default_hyperparameters["clip_range"] == 0.2

    def test_a2c_defaults_differ_from_ppo(self) -> None:
        # A2C literature uses gae_lambda=1.0 (MC-style returns); the adapter
        # MUST NOT inherit PPO's 0.95 default.
        assert A2CAdapter.default_hyperparameters["gae_lambda"] == 1.0

    def test_dqn_uses_replay_buffer(self) -> None:
        assert DQNAdapter.buffer_kind == "replay"
        assert DQNAdapter.paradigm == "off-policy"


class TestDecisionTransformerDeferred:
    """W29 trap — DT is deferred (post-1.0 RA-03); constructor refuses."""

    def test_construction_raises_feature_not_yet_supported(self) -> None:
        with pytest.raises(FeatureNotYetSupportedError) as exc:
            DecisionTransformerAdapter(env=object(), hyperparameters={})
        assert exc.value.reason == "decision_transformer_deferred_to_1_2"

    def test_load_raises_feature_not_yet_supported(self) -> None:
        with pytest.raises(FeatureNotYetSupportedError):
            DecisionTransformerAdapter.load("/tmp/fake")


class TestRegisterAlgorithm:
    """User-registration path for custom adapters."""

    def test_idempotent_reregistration(self) -> None:
        class _MyAdapter(AlgorithmAdapter):
            name = "user-algo-test"
            _sb3_class_path = "stable_baselines3:PPO"

        register_algorithm("user-algo-test-idempotent", _MyAdapter)
        # Re-registering the same class is allowed (no error).
        register_algorithm("user-algo-test-idempotent", _MyAdapter)
        assert load_adapter_class("user-algo-test-idempotent") is _MyAdapter

    def test_name_collision_raises(self) -> None:
        class _A(AlgorithmAdapter):
            _sb3_class_path = "stable_baselines3:PPO"

        class _B(AlgorithmAdapter):
            _sb3_class_path = "stable_baselines3:PPO"

        register_algorithm("user-algo-collision", _A)
        with pytest.raises(RLError, match="algorithm_name_occupied"):
            register_algorithm("user-algo-collision", _B)

    def test_non_subclass_rejected(self) -> None:
        class _Bogus:
            pass

        with pytest.raises(RLError, match="adapter_not_subclass"):
            register_algorithm("not-an-adapter", _Bogus)  # type: ignore[arg-type]
