# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Configurable LLM token cost model for budget tracking.

Maps (model_name, prompt_tokens, completion_tokens) to a cost in USD.
Used by GovernedSupervisor to compute LLM completion costs from token
counts, replacing the flat per-call cost assumption.

Prices are USD per 1M tokens (the industry-standard denomination).
"""

from __future__ import annotations

import logging
import math
from typing import Any

logger = logging.getLogger(__name__)

__all__ = ["CostModel"]


class CostModel:
    """Maps (model_name, prompt_tokens, completion_tokens) to cost in USD.

    Default table covers major 2026 models. Override via constructor for
    custom/private models. Prices are USD per 1M tokens.

    Usage::

        model = CostModel()
        cost = model.compute("claude-sonnet-4-6", prompt_tokens=5000, completion_tokens=1500)
        # cost is in USD

    Custom models::

        model = CostModel(custom_costs={"my-model": {"prompt": 1.0, "completion": 3.0}})
    """

    DEFAULT_COSTS: dict[str, dict[str, float]] = {
        # OpenAI GPT-5 family
        "gpt-5": {"prompt": 3.00, "completion": 15.00},
        "gpt-5-mini": {"prompt": 0.30, "completion": 1.25},
        "gpt-5-nano": {"prompt": 0.10, "completion": 0.40},
        # OpenAI GPT-4 family
        "gpt-4o": {"prompt": 2.50, "completion": 10.00},
        "gpt-4o-mini": {"prompt": 0.15, "completion": 0.60},
        "gpt-4.1": {"prompt": 2.00, "completion": 8.00},
        "gpt-4.1-mini": {"prompt": 0.40, "completion": 1.60},
        "gpt-4.1-nano": {"prompt": 0.10, "completion": 0.40},
        # OpenAI reasoning models
        "o3": {"prompt": 10.00, "completion": 40.00},
        "o4-mini": {"prompt": 1.10, "completion": 4.40},
        # Anthropic Claude family
        "claude-sonnet-4-6": {"prompt": 3.00, "completion": 15.00},
        "claude-opus-4-6": {"prompt": 15.00, "completion": 75.00},
        "claude-haiku-4-5": {"prompt": 0.80, "completion": 4.00},
    }

    def __init__(
        self,
        custom_costs: dict[str, dict[str, float]] | None = None,
        default_prompt_rate: float = 5.0,
        default_completion_rate: float = 15.0,
    ) -> None:
        """Initialize with optional custom cost overrides.

        Args:
            custom_costs: Model-specific rate overrides. Keys are model names,
                values are dicts with "prompt" and "completion" rates per 1M tokens.
            default_prompt_rate: Fallback prompt rate (USD/1M tokens) for unknown models.
            default_completion_rate: Fallback completion rate (USD/1M tokens) for unknown models.

        Raises:
            ValueError: If any rate is NaN, Inf, or negative.
        """
        # Validate default rates before anything else
        if not math.isfinite(default_prompt_rate) or default_prompt_rate < 0:
            raise ValueError(
                f"default_prompt_rate must be finite and non-negative, got {default_prompt_rate}"
            )
        if not math.isfinite(default_completion_rate) or default_completion_rate < 0:
            raise ValueError(
                f"default_completion_rate must be finite and non-negative, "
                f"got {default_completion_rate}"
            )

        self._costs: dict[str, dict[str, float]] = {
            **self.DEFAULT_COSTS,
            **(custom_costs or {}),
        }
        self._default_prompt = default_prompt_rate
        self._default_completion = default_completion_rate

        # Validate all rates are finite and non-negative
        for model, rates in self._costs.items():
            for key, val in rates.items():
                if not math.isfinite(val) or val < 0:
                    raise ValueError(
                        f"Rate for {model}.{key} must be finite and non-negative, got {val}"
                    )

    def compute(self, model: str, prompt_tokens: int, completion_tokens: int) -> float:
        """Compute cost in USD for a given model and token counts.

        Args:
            model: Model identifier string (e.g., "claude-sonnet-4-6").
            prompt_tokens: Number of prompt/input tokens.
            completion_tokens: Number of completion/output tokens.

        Returns:
            Cost in USD (always finite and non-negative).

        Raises:
            ValueError: If the computed cost is not finite (should not happen
                with validated rates, but defense-in-depth).
        """
        rates = self._resolve_rates(model)
        cost = (
            prompt_tokens * rates["prompt"] + completion_tokens * rates["completion"]
        ) / 1_000_000
        if not math.isfinite(cost):
            raise ValueError(f"Computed cost is not finite: {cost}")
        return cost

    def get_rate(self, model: str) -> dict[str, float]:
        """Get the resolved rate table for a model.

        Returns a copy so callers cannot mutate internal state.

        Args:
            model: Model identifier string.

        Returns:
            Dict with "prompt" and "completion" rates (USD per 1M tokens).
        """
        return dict(self._resolve_rates(model))

    def _resolve_rates(self, model: str) -> dict[str, float]:
        """Resolve rates for a model name, with fuzzy matching.

        Resolution order:
        1. Exact match in the cost table.
        2. Fuzzy match: any known model name is a substring of the query,
           or the query is a substring of a known model name.
        3. Default rates.

        Args:
            model: Model identifier string.

        Returns:
            Dict with "prompt" and "completion" rates.
        """
        # 1. Exact match
        if model in self._costs:
            return self._costs[model]

        # 2. Fuzzy: prefer longest matching key (most specific match wins)
        matches = []
        for key, rates in self._costs.items():
            if key in model or model in key:
                matches.append((len(key), key, rates))
        if matches:
            matches.sort(reverse=True)  # longest key first
            return matches[0][2]

        # 3. Default rates
        logger.debug(
            "No cost model match for %r, using default rates: prompt=$%.2f/1M, completion=$%.2f/1M",
            model,
            self._default_prompt,
            self._default_completion,
        )
        return {"prompt": self._default_prompt, "completion": self._default_completion}
