# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""
External Agent Cost Estimator.

Estimates execution costs for external agents (Copilot Studio, custom REST APIs,
third-party AI systems) with platform-specific cost tables and complexity multipliers.

Extends Kaizen's BudgetEnforcer pattern for external agent contexts.
"""

import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class CostEstimate:
    """
    Cost estimation result.

    Attributes:
        base_cost: Base platform cost (USD)
        complexity_multiplier: Complexity adjustment factor (0.5-2.0)
        token_cost: Additional token-based cost for LLM agents (USD)
        buffer_cost: Conservative 20% buffer (USD)
        total_cost: Final estimated cost with buffer (USD)
    """

    base_cost: float
    complexity_multiplier: float
    token_cost: float
    buffer_cost: float
    total_cost: float


class ExternalAgentCostEstimator:
    """
    Cost estimation for external agent executions.

    Provides conservative cost estimates based on:
    - Platform type (Copilot Studio, custom REST API, third-party agents)
    - Complexity level (simple, standard, complex)
    - Token usage (for LLM-based agents)
    - Conservative 20% buffer for unknowns

    Cost tables are based on:
    - Microsoft Copilot Studio pricing (last updated: 2025-12-20)
    - Conservative defaults for custom/third-party agents
    - OpenAI GPT-4 pricing for token estimates

    Examples:
        >>> estimator = ExternalAgentCostEstimator()
        >>> # Standard invocation
        >>> cost = estimator.estimate_cost("copilot_studio", "ms_teams")
        >>> print(f"${cost:.4f}")
        $0.0600

        >>> # Complex invocation with tokens
        >>> cost = estimator.estimate_cost(
        ...     "copilot_studio",
        ...     "ms_teams",
        ...     complexity="complex",
        ...     input_tokens=1000
        ... )
        >>> print(f"${cost:.4f}")
        $0.1560
    """

    # Platform base costs (USD per invocation)
    # Last updated: 2025-12-20
    # Sources:
    # - Microsoft Copilot Studio: https://www.microsoft.com/en-us/microsoft-copilot/copilot-studio-pricing
    # - Custom REST API: Conservative estimate based on typical API costs
    # - Third-party agents: Conservative default for unknown platforms
    EXTERNAL_AGENT_COSTS = {
        "copilot_studio": 0.05,  # $0.05 per invocation (Microsoft pricing)
        "custom_rest_api": 0.01,  # $0.01 per API call (conservative)
        "third_party_agent": 0.03,  # $0.03 per invocation (conservative)
        "power_automate": 0.02,  # $0.02 per flow execution
        "azure_openai": 0.04,  # $0.04 base cost (tokens additional)
    }

    # Complexity multipliers
    # Simple: Basic operations, minimal processing (0.5x)
    # Standard: Normal operations (1.0x)
    # Complex: Heavy processing, multi-step workflows (2.0x)
    COMPLEXITY_MULTIPLIERS = {
        "simple": 0.5,
        "standard": 1.0,
        "complex": 2.0,
    }

    # LLM token costs (USD per 1000 tokens)
    # Based on OpenAI GPT-4 pricing as conservative estimate
    TOKEN_COSTS = {
        "gpt-4": 0.03,  # $0.03 per 1K input tokens
        "gpt-4-turbo": 0.01,  # $0.01 per 1K input tokens
        "gpt-3.5-turbo": 0.001,  # $0.001 per 1K input tokens
        "default": 0.03,  # Conservative default
    }

    # Conservative buffer (20%) for unknown factors
    COST_BUFFER = 1.20

    def __init__(self, custom_costs: dict[str, float] | None = None):
        """
        Initialize cost estimator.

        Args:
            custom_costs: Optional custom cost overrides for specific platforms
                         (e.g., {"custom_agent": 0.025})
        """
        self.custom_costs = custom_costs or {}

    def estimate_cost(
        self,
        platform_type: str,
        agent_name: str,
        complexity: str = "standard",
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        model_name: str | None = None,
    ) -> float:
        """
        Estimate cost for external agent execution.

        Uses conservative estimates with 20% buffer.

        Args:
            platform_type: Type of external agent platform
                          (copilot_studio, custom_rest_api, third_party_agent, etc.)
            agent_name: Name of specific agent (for logging/audit)
            complexity: Execution complexity (simple, standard, complex)
            input_tokens: Optional input token count for LLM-based agents
            output_tokens: Optional output token count for LLM-based agents
            model_name: Optional LLM model name for token pricing

        Returns:
            Estimated cost in USD with 20% buffer

        Raises:
            ValueError: If complexity is not recognized

        Examples:
            >>> estimator = ExternalAgentCostEstimator()
            >>> estimator.estimate_cost("copilot_studio", "hr_assistant")
            0.06
            >>> estimator.estimate_cost("copilot_studio", "hr_assistant", complexity="complex")
            0.12
            >>> estimator.estimate_cost(
            ...     "azure_openai",
            ...     "code_reviewer",
            ...     input_tokens=1000,
            ...     model_name="gpt-4"
            ... )
            0.084
        """
        # Validate complexity
        if complexity not in self.COMPLEXITY_MULTIPLIERS:
            raise ValueError(
                f"Unknown complexity: {complexity}. Must be one of: {list(self.COMPLEXITY_MULTIPLIERS.keys())}"
            )

        # Get base cost
        base_cost = self._get_base_cost(platform_type)

        # Apply complexity multiplier
        complexity_multiplier = self.COMPLEXITY_MULTIPLIERS[complexity]
        adjusted_cost = base_cost * complexity_multiplier

        # Add token costs if provided
        token_cost = 0.0
        if input_tokens or output_tokens:
            token_cost = self._estimate_token_cost(input_tokens or 0, output_tokens or 0, model_name)

        # Calculate total with buffer
        subtotal = adjusted_cost + token_cost
        total_cost = subtotal * self.COST_BUFFER

        # Log estimation details
        logger.debug(
            f"Cost estimate for {agent_name} on {platform_type}: "
            f"base=${base_cost:.4f}, "
            f"complexity={complexity} ({complexity_multiplier}x), "
            f"tokens=${token_cost:.4f}, "
            f"total=${total_cost:.4f} (with 20% buffer)"
        )

        return total_cost

    def estimate_cost_detailed(
        self,
        platform_type: str,
        agent_name: str,
        complexity: str = "standard",
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        model_name: str | None = None,
    ) -> CostEstimate:
        """
        Get detailed cost estimation breakdown.

        Args:
            platform_type: Type of external agent platform
            agent_name: Name of specific agent
            complexity: Execution complexity (simple, standard, complex)
            input_tokens: Optional input token count
            output_tokens: Optional output token count
            model_name: Optional LLM model name

        Returns:
            CostEstimate with detailed breakdown

        Examples:
            >>> estimator = ExternalAgentCostEstimator()
            >>> estimate = estimator.estimate_cost_detailed(
            ...     "copilot_studio",
            ...     "hr_assistant",
            ...     complexity="complex",
            ...     input_tokens=1000
            ... )
            >>> print(f"Base: ${estimate.base_cost:.4f}")
            Base: $0.0500
            >>> print(f"Total: ${estimate.total_cost:.4f}")
            Total: $0.1560
        """
        # Get base cost
        base_cost = self._get_base_cost(platform_type)

        # Get complexity multiplier
        complexity_multiplier = self.COMPLEXITY_MULTIPLIERS.get(complexity, 1.0)

        # Calculate token cost
        token_cost = 0.0
        if input_tokens or output_tokens:
            token_cost = self._estimate_token_cost(input_tokens or 0, output_tokens or 0, model_name)

        # Calculate subtotal and buffer
        subtotal = (base_cost * complexity_multiplier) + token_cost
        buffer_cost = subtotal * (self.COST_BUFFER - 1.0)  # 20% of subtotal
        total_cost = subtotal + buffer_cost

        return CostEstimate(
            base_cost=base_cost,
            complexity_multiplier=complexity_multiplier,
            token_cost=token_cost,
            buffer_cost=buffer_cost,
            total_cost=total_cost,
        )

    def _get_base_cost(self, platform_type: str) -> float:
        """
        Get base cost for platform type.

        Checks custom costs first, then falls back to default table.

        Args:
            platform_type: Type of external agent platform

        Returns:
            Base cost in USD

        Examples:
            >>> estimator = ExternalAgentCostEstimator()
            >>> estimator._get_base_cost("copilot_studio")
            0.05
            >>> estimator = ExternalAgentCostEstimator({"custom": 0.025})
            >>> estimator._get_base_cost("custom")
            0.025
        """
        # Check custom costs first
        if platform_type in self.custom_costs:
            return self.custom_costs[platform_type]

        # Fall back to default table
        if platform_type in self.EXTERNAL_AGENT_COSTS:
            return self.EXTERNAL_AGENT_COSTS[platform_type]

        # Unknown platform - use conservative default
        logger.warning(
            f"Unknown platform type: {platform_type}. "
            f"Using conservative default: ${self.EXTERNAL_AGENT_COSTS['third_party_agent']:.4f}"
        )
        return self.EXTERNAL_AGENT_COSTS["third_party_agent"]

    def _estimate_token_cost(self, input_tokens: int, output_tokens: int, model_name: str | None) -> float:
        """
        Estimate cost based on token usage.

        Args:
            input_tokens: Number of input tokens
            output_tokens: Number of output tokens
            model_name: Optional model name for pricing

        Returns:
            Estimated token cost in USD

        Examples:
            >>> estimator = ExternalAgentCostEstimator()
            >>> estimator._estimate_token_cost(1000, 500, "gpt-4")
            0.045
            >>> estimator._estimate_token_cost(1000, 500, None)
            0.045
        """
        # Get cost per 1K tokens
        if model_name and model_name in self.TOKEN_COSTS:
            cost_per_1k = self.TOKEN_COSTS[model_name]
        else:
            cost_per_1k = self.TOKEN_COSTS["default"]

        # Calculate input and output costs
        # Note: Output tokens typically cost 2x input tokens for GPT-4
        input_cost = (input_tokens / 1000.0) * cost_per_1k
        output_cost = (output_tokens / 1000.0) * cost_per_1k * 2.0  # 2x for output

        total_token_cost = input_cost + output_cost

        logger.debug(
            f"Token cost: {input_tokens} input + {output_tokens} output = "
            f"${total_token_cost:.4f} (model: {model_name or 'default'})"
        )

        return total_token_cost

    def get_platform_costs(self) -> dict[str, float]:
        """
        Get all platform costs (default + custom).

        Returns:
            Dictionary mapping platform types to costs

        Examples:
            >>> estimator = ExternalAgentCostEstimator({"custom": 0.025})
            >>> costs = estimator.get_platform_costs()
            >>> costs["copilot_studio"]
            0.05
            >>> costs["custom"]
            0.025
        """
        # Merge default and custom costs
        all_costs = dict(self.EXTERNAL_AGENT_COSTS)
        all_costs.update(self.custom_costs)
        return all_costs


# Export all public types
__all__ = [
    "ExternalAgentCostEstimator",
    "CostEstimate",
]
