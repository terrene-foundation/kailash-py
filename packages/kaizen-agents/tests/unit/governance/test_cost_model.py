# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tests for CostModel — LLM token cost computation for budget tracking."""

from __future__ import annotations

import math

import pytest

from kaizen_agents.governance.cost_model import CostModel


# =========================================================================
# Construction and validation
# =========================================================================


class TestCostModelConstruction:
    """Verify that CostModel validates rates at construction time."""

    def test_default_construction(self) -> None:
        """CostModel can be created with no arguments."""
        model = CostModel()
        assert model is not None

    def test_rejects_nan_rate_in_defaults(self) -> None:
        """NaN rates in custom_costs must be rejected per PACT NaN/Inf rule."""
        with pytest.raises(ValueError, match="finite and non-negative"):
            CostModel(custom_costs={"bad-model": {"prompt": float("nan"), "completion": 10.0}})

    def test_rejects_inf_rate(self) -> None:
        """Inf rates must be rejected."""
        with pytest.raises(ValueError, match="finite and non-negative"):
            CostModel(custom_costs={"bad-model": {"prompt": float("inf"), "completion": 10.0}})

    def test_rejects_negative_inf_rate(self) -> None:
        """Negative infinity rates must be rejected."""
        with pytest.raises(ValueError, match="finite and non-negative"):
            CostModel(custom_costs={"bad-model": {"prompt": float("-inf"), "completion": 10.0}})

    def test_rejects_negative_rate(self) -> None:
        """Negative rates must be rejected."""
        with pytest.raises(ValueError, match="finite and non-negative"):
            CostModel(custom_costs={"bad-model": {"prompt": -1.0, "completion": 10.0}})

    def test_rejects_nan_default_prompt_rate(self) -> None:
        """NaN in default_prompt_rate must be rejected."""
        with pytest.raises(ValueError, match="default_prompt_rate must be finite and non-negative"):
            CostModel(default_prompt_rate=float("nan"))

    def test_rejects_negative_default_completion_rate(self) -> None:
        """Negative default_completion_rate must be rejected."""
        with pytest.raises(
            ValueError, match="default_completion_rate must be finite and non-negative"
        ):
            CostModel(default_completion_rate=-5.0)

    def test_custom_costs_override_defaults(self) -> None:
        """Custom costs take precedence over DEFAULT_COSTS."""
        custom = {"gpt-4o": {"prompt": 99.0, "completion": 199.0}}
        model = CostModel(custom_costs=custom)
        rates = model.get_rate("gpt-4o")
        assert rates["prompt"] == 99.0
        assert rates["completion"] == 199.0

    def test_custom_costs_additive(self) -> None:
        """Custom costs add new models without removing defaults."""
        custom = {"my-private-model": {"prompt": 1.0, "completion": 2.0}}
        model = CostModel(custom_costs=custom)
        # Default model still accessible
        rates_default = model.get_rate("claude-sonnet-4-6")
        assert rates_default["prompt"] == 3.0
        # Custom model also accessible
        rates_custom = model.get_rate("my-private-model")
        assert rates_custom["prompt"] == 1.0


# =========================================================================
# Cost computation — known models
# =========================================================================


class TestCostModelCompute:
    """Verify compute() returns correct USD costs for known models."""

    def test_compute_known_model_claude_sonnet(self) -> None:
        """Claude Sonnet 4.6: $3.00/1M prompt, $15.00/1M completion."""
        model = CostModel()
        # 1000 prompt tokens, 500 completion tokens
        cost = model.compute("claude-sonnet-4-6", 1000, 500)
        expected = (1000 * 3.0 + 500 * 15.0) / 1_000_000
        assert cost == pytest.approx(expected)

    def test_compute_known_model_gpt4o(self) -> None:
        """GPT-4o: $2.50/1M prompt, $10.00/1M completion."""
        model = CostModel()
        cost = model.compute("gpt-4o", 2000, 1000)
        expected = (2000 * 2.5 + 1000 * 10.0) / 1_000_000
        assert cost == pytest.approx(expected)

    def test_compute_zero_tokens_returns_zero(self) -> None:
        """Zero tokens must return zero cost."""
        model = CostModel()
        cost = model.compute("claude-sonnet-4-6", 0, 0)
        assert cost == 0.0

    def test_compute_returns_finite(self) -> None:
        """Computed cost must always be a finite float."""
        model = CostModel()
        cost = model.compute("gpt-4o", 100_000, 50_000)
        assert math.isfinite(cost)

    def test_compute_large_token_counts(self) -> None:
        """Large token counts must still produce finite results."""
        model = CostModel()
        cost = model.compute("o3", 10_000_000, 5_000_000)
        # o3: $10.00/1M prompt, $40.00/1M completion
        expected = (10_000_000 * 10.0 + 5_000_000 * 40.0) / 1_000_000
        assert cost == pytest.approx(expected)
        assert math.isfinite(cost)


# =========================================================================
# Cost computation — unknown models (fallback to defaults)
# =========================================================================


class TestCostModelUnknownModel:
    """Verify fallback behavior for unrecognized model names."""

    def test_compute_unknown_model_uses_defaults(self) -> None:
        """Unknown models use default_prompt_rate and default_completion_rate."""
        model = CostModel(default_prompt_rate=5.0, default_completion_rate=15.0)
        cost = model.compute("my-private-model", 1000, 500)
        expected = (1000 * 5.0 + 500 * 15.0) / 1_000_000
        assert cost == pytest.approx(expected)

    def test_compute_unknown_model_custom_defaults(self) -> None:
        """Custom default rates are honored for unknown models."""
        model = CostModel(default_prompt_rate=1.0, default_completion_rate=2.0)
        cost = model.compute("totally-unknown-model", 1_000_000, 1_000_000)
        expected = (1_000_000 * 1.0 + 1_000_000 * 2.0) / 1_000_000
        assert cost == pytest.approx(expected)

    def test_get_rate_unknown_returns_defaults(self) -> None:
        """get_rate() for unknown model returns defaults."""
        model = CostModel(default_prompt_rate=7.0, default_completion_rate=21.0)
        rates = model.get_rate("never-heard-of-this")
        assert rates["prompt"] == 7.0
        assert rates["completion"] == 21.0


# =========================================================================
# Fuzzy matching
# =========================================================================


class TestCostModelFuzzyMatch:
    """Verify fuzzy model name resolution (substring matching)."""

    def test_fuzzy_match_versioned_suffix(self) -> None:
        """A versioned model name like 'claude-sonnet-4-6-20260101' should match."""
        model = CostModel()
        cost = model.compute("claude-sonnet-4-6-20260101", 1000, 500)
        expected = (1000 * 3.0 + 500 * 15.0) / 1_000_000
        assert cost == pytest.approx(expected)

    def test_fuzzy_match_provider_prefix(self) -> None:
        """A provider-prefixed name like 'openai/gpt-4o' should match."""
        model = CostModel()
        cost = model.compute("openai/gpt-4o", 1000, 500)
        expected = (1000 * 2.5 + 500 * 10.0) / 1_000_000
        assert cost == pytest.approx(expected)

    def test_get_rate_fuzzy_returns_matched(self) -> None:
        """get_rate() with fuzzy match returns resolved rates, not defaults."""
        model = CostModel()
        rates = model.get_rate("claude-opus-4-6-latest")
        assert rates["prompt"] == 15.0
        assert rates["completion"] == 75.0

    def test_get_rate_returns_copy(self) -> None:
        """get_rate() must return a copy, not internal state."""
        model = CostModel()
        rates = model.get_rate("gpt-4o")
        rates["prompt"] = 999.0
        # Internal state should be unchanged
        rates2 = model.get_rate("gpt-4o")
        assert rates2["prompt"] == 2.5


# =========================================================================
# Default cost table coverage
# =========================================================================


class TestCostModelDefaultTable:
    """Verify all default models are present and produce valid costs."""

    @pytest.mark.parametrize(
        "model_name",
        [
            "gpt-4o",
            "gpt-4o-mini",
            "gpt-4.1",
            "gpt-4.1-mini",
            "gpt-4.1-nano",
            "o3",
            "o4-mini",
            "claude-sonnet-4-6",
            "claude-opus-4-6",
            "claude-haiku-4-5",
        ],
    )
    def test_default_model_produces_finite_cost(self, model_name: str) -> None:
        """Every default model must produce a finite, non-negative cost."""
        model = CostModel()
        cost = model.compute(model_name, 1000, 500)
        assert math.isfinite(cost)
        assert cost >= 0.0

    @pytest.mark.parametrize(
        "model_name",
        [
            "gpt-4o",
            "gpt-4o-mini",
            "gpt-4.1",
            "gpt-4.1-mini",
            "gpt-4.1-nano",
            "o3",
            "o4-mini",
            "claude-sonnet-4-6",
            "claude-opus-4-6",
            "claude-haiku-4-5",
        ],
    )
    def test_default_model_has_both_rates(self, model_name: str) -> None:
        """Every default model must have both prompt and completion rates."""
        model = CostModel()
        rates = model.get_rate(model_name)
        assert "prompt" in rates
        assert "completion" in rates
        assert rates["prompt"] >= 0.0
        assert rates["completion"] >= 0.0
