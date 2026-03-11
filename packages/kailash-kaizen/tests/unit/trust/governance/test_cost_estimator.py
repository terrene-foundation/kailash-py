"""
Tier 1 Unit Tests: ExternalAgentCostEstimator

Tests cost estimation accuracy in isolation without external dependencies.

Intent: Verify cost calculations are accurate, conservative, and handle all platforms.
"""

import pytest
from kaizen.trust.governance import CostEstimate, ExternalAgentCostEstimator


class TestExternalAgentCostEstimator:
    """Test suite for cost estimation logic."""

    def test_estimate_cost_copilot_studio_standard(self):
        """
        Intent: Verify base cost calculation for Copilot Studio with standard complexity.

        Expected: $0.05 base * 1.0 multiplier * 1.20 buffer = $0.06
        """
        estimator = ExternalAgentCostEstimator()
        cost = estimator.estimate_cost(
            "copilot_studio", "hr_assistant", complexity="standard"
        )

        # Expected: 0.05 * 1.0 * 1.20 = 0.06
        assert cost == pytest.approx(0.06, rel=0.01)

    def test_estimate_cost_copilot_studio_simple(self):
        """
        Intent: Verify simple complexity multiplier (0.5x) reduces cost.

        Expected: $0.05 base * 0.5 multiplier * 1.20 buffer = $0.03
        """
        estimator = ExternalAgentCostEstimator()
        cost = estimator.estimate_cost(
            "copilot_studio", "hr_assistant", complexity="simple"
        )

        # Expected: 0.05 * 0.5 * 1.20 = 0.03
        assert cost == pytest.approx(0.03, rel=0.01)

    def test_estimate_cost_copilot_studio_complex(self):
        """
        Intent: Verify complex complexity multiplier (2.0x) increases cost.

        Expected: $0.05 base * 2.0 multiplier * 1.20 buffer = $0.12
        """
        estimator = ExternalAgentCostEstimator()
        cost = estimator.estimate_cost(
            "copilot_studio", "hr_assistant", complexity="complex"
        )

        # Expected: 0.05 * 2.0 * 1.20 = 0.12
        assert cost == pytest.approx(0.12, rel=0.01)

    def test_estimate_cost_with_input_tokens(self):
        """
        Intent: Verify LLM token costs are added to base cost.

        Expected:
        - Base: $0.05 * 1.0 * 1.20 = $0.06
        - Tokens: 1000 input * $0.03/1K = $0.03
        - Total: ($0.05 + $0.03) * 1.20 = $0.096
        """
        estimator = ExternalAgentCostEstimator()
        cost = estimator.estimate_cost(
            "copilot_studio",
            "hr_assistant",
            complexity="standard",
            input_tokens=1000,
            model_name="gpt-4",
        )

        # Expected: (0.05 + 0.03) * 1.20 = 0.096
        assert cost == pytest.approx(0.096, rel=0.01)

    def test_estimate_cost_with_input_and_output_tokens(self):
        """
        Intent: Verify output tokens cost 2x input tokens (GPT-4 pricing).

        Expected:
        - Base: $0.05 * 1.0 = $0.05
        - Input tokens: 1000 * $0.03/1K = $0.03
        - Output tokens: 500 * $0.03/1K * 2.0 = $0.03
        - Subtotal: $0.05 + $0.03 + $0.03 = $0.11
        - Total: $0.11 * 1.20 = $0.132
        """
        estimator = ExternalAgentCostEstimator()
        cost = estimator.estimate_cost(
            "azure_openai",
            "code_reviewer",
            complexity="standard",
            input_tokens=1000,
            output_tokens=500,
            model_name="gpt-4",
        )

        # Expected: (0.04 + 0.03 + 0.03) * 1.20 = 0.12
        assert cost == pytest.approx(0.12, rel=0.01)

    def test_estimate_cost_custom_rest_api(self):
        """
        Intent: Verify custom REST API platform uses correct base cost.

        Expected: $0.01 base * 1.0 multiplier * 1.20 buffer = $0.012
        """
        estimator = ExternalAgentCostEstimator()
        cost = estimator.estimate_cost(
            "custom_rest_api", "inventory_sync", complexity="standard"
        )

        # Expected: 0.01 * 1.0 * 1.20 = 0.012
        assert cost == pytest.approx(0.012, rel=0.01)

    def test_estimate_cost_third_party_agent(self):
        """
        Intent: Verify third-party agent platform uses correct base cost.

        Expected: $0.03 base * 1.0 multiplier * 1.20 buffer = $0.036
        """
        estimator = ExternalAgentCostEstimator()
        cost = estimator.estimate_cost(
            "third_party_agent", "sentiment_analysis", complexity="standard"
        )

        # Expected: 0.03 * 1.0 * 1.20 = 0.036
        assert cost == pytest.approx(0.036, rel=0.01)

    def test_estimate_cost_unknown_platform_uses_conservative_default(self):
        """
        Intent: Verify unknown platforms fall back to conservative default ($0.03).

        Expected: $0.03 default * 1.0 multiplier * 1.20 buffer = $0.036
        """
        estimator = ExternalAgentCostEstimator()
        cost = estimator.estimate_cost(
            "unknown_platform", "test_agent", complexity="standard"
        )

        # Expected: 0.03 (third_party default) * 1.0 * 1.20 = 0.036
        assert cost == pytest.approx(0.036, rel=0.01)

    def test_estimate_cost_invalid_complexity_raises_error(self):
        """
        Intent: Verify invalid complexity levels are rejected.

        Expected: ValueError raised with helpful message.
        """
        estimator = ExternalAgentCostEstimator()

        with pytest.raises(ValueError) as exc_info:
            estimator.estimate_cost(
                "copilot_studio", "test", complexity="ultra_mega_complex"
            )

        assert "Unknown complexity" in str(exc_info.value)
        assert "simple" in str(exc_info.value)
        assert "standard" in str(exc_info.value)
        assert "complex" in str(exc_info.value)

    def test_estimate_cost_custom_platform_costs(self):
        """
        Intent: Verify custom cost overrides work correctly.

        Expected: Custom cost ($0.025) * 1.0 * 1.20 = $0.03
        """
        custom_costs = {"my_custom_agent": 0.025}
        estimator = ExternalAgentCostEstimator(custom_costs=custom_costs)
        cost = estimator.estimate_cost("my_custom_agent", "test", complexity="standard")

        # Expected: 0.025 * 1.0 * 1.20 = 0.03
        assert cost == pytest.approx(0.03, rel=0.01)

    def test_estimate_cost_detailed_breakdown(self):
        """
        Intent: Verify detailed cost estimate provides all components.

        Expected: CostEstimate with base_cost, multiplier, token_cost, buffer, total.
        """
        estimator = ExternalAgentCostEstimator()
        estimate = estimator.estimate_cost_detailed(
            "copilot_studio",
            "hr_assistant",
            complexity="complex",
            input_tokens=1000,
            model_name="gpt-4",
        )

        assert isinstance(estimate, CostEstimate)
        assert estimate.base_cost == 0.05
        assert estimate.complexity_multiplier == 2.0
        assert estimate.token_cost == pytest.approx(0.03, rel=0.01)
        # Subtotal: (0.05 * 2.0) + 0.03 = 0.13
        # Buffer: 0.13 * 0.20 = 0.026
        assert estimate.buffer_cost == pytest.approx(0.026, rel=0.01)
        # Total: 0.13 + 0.026 = 0.156
        assert estimate.total_cost == pytest.approx(0.156, rel=0.01)

    def test_estimate_cost_gpt_3_5_turbo_lower_cost(self):
        """
        Intent: Verify GPT-3.5-turbo has lower token costs than GPT-4.

        Expected: GPT-3.5-turbo cost < GPT-4 cost for same token count.
        """
        estimator = ExternalAgentCostEstimator()

        gpt4_cost = estimator.estimate_cost(
            "azure_openai", "test", input_tokens=1000, model_name="gpt-4"
        )

        gpt35_cost = estimator.estimate_cost(
            "azure_openai", "test", input_tokens=1000, model_name="gpt-3.5-turbo"
        )

        assert gpt35_cost < gpt4_cost

    def test_get_platform_costs_includes_defaults_and_custom(self):
        """
        Intent: Verify get_platform_costs merges default and custom costs.

        Expected: Dictionary contains both default platforms and custom overrides.
        """
        custom_costs = {"my_platform": 0.02}
        estimator = ExternalAgentCostEstimator(custom_costs=custom_costs)

        all_costs = estimator.get_platform_costs()

        # Check defaults are present
        assert "copilot_studio" in all_costs
        assert all_costs["copilot_studio"] == 0.05

        # Check custom cost is present
        assert "my_platform" in all_costs
        assert all_costs["my_platform"] == 0.02

    def test_conservative_buffer_always_applied(self):
        """
        Intent: Verify 20% buffer is always applied for conservative estimates.

        Expected: All estimates are 1.20x the base calculation.
        """
        estimator = ExternalAgentCostEstimator()

        # Test multiple platforms
        platforms = ["copilot_studio", "custom_rest_api", "third_party_agent"]

        for platform in platforms:
            cost = estimator.estimate_cost(platform, "test", complexity="standard")
            base = estimator._get_base_cost(platform)

            # Cost should be base * 1.0 (standard) * 1.20 (buffer)
            expected = base * 1.0 * 1.20
            assert cost == pytest.approx(expected, rel=0.01)

    def test_zero_tokens_no_token_cost(self):
        """
        Intent: Verify no token cost when tokens not provided.

        Expected: Cost equals base cost with buffer only.
        """
        estimator = ExternalAgentCostEstimator()

        # Without tokens
        cost_no_tokens = estimator.estimate_cost(
            "copilot_studio", "test", complexity="standard"
        )

        # With zero tokens
        cost_zero_tokens = estimator.estimate_cost(
            "copilot_studio",
            "test",
            complexity="standard",
            input_tokens=0,
            output_tokens=0,
        )

        # Should be identical
        assert cost_no_tokens == cost_zero_tokens

    def test_estimate_cost_power_automate_platform(self):
        """
        Intent: Verify Power Automate platform cost calculation.

        Expected: $0.02 base * 1.0 * 1.20 = $0.024
        """
        estimator = ExternalAgentCostEstimator()
        cost = estimator.estimate_cost(
            "power_automate", "flow_executor", complexity="standard"
        )

        # Expected: 0.02 * 1.0 * 1.20 = 0.024
        assert cost == pytest.approx(0.024, rel=0.01)

    def test_estimate_cost_azure_openai_platform(self):
        """
        Intent: Verify Azure OpenAI platform base cost.

        Expected: $0.04 base * 1.0 * 1.20 = $0.048
        """
        estimator = ExternalAgentCostEstimator()
        cost = estimator.estimate_cost(
            "azure_openai", "chat_completion", complexity="standard"
        )

        # Expected: 0.04 * 1.0 * 1.20 = 0.048
        assert cost == pytest.approx(0.048, rel=0.01)


class TestCostEstimateDataclass:
    """Test CostEstimate dataclass."""

    def test_cost_estimate_creation(self):
        """
        Intent: Verify CostEstimate can be created with all fields.

        Expected: All fields accessible and correct types.
        """
        estimate = CostEstimate(
            base_cost=0.05,
            complexity_multiplier=2.0,
            token_cost=0.03,
            buffer_cost=0.016,
            total_cost=0.096,
        )

        assert estimate.base_cost == 0.05
        assert estimate.complexity_multiplier == 2.0
        assert estimate.token_cost == 0.03
        assert estimate.buffer_cost == 0.016
        assert estimate.total_cost == 0.096


# Run tests with pytest -xvs tests/unit/trust/governance/test_cost_estimator.py
