# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Cost tracking utilities for provider token usage.

Provides per-model pricing data and a lightweight accumulator so that
callers can track spend without depending on external billing services.
"""

from __future__ import annotations

import logging
import threading
from collections import deque
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ModelPricing:
    """Per-token pricing for a single model (in USD).

    Attributes:
        prompt_cost_per_1k: Cost per 1 000 prompt tokens.
        completion_cost_per_1k: Cost per 1 000 completion tokens.
    """

    prompt_cost_per_1k: float = 0.0
    completion_cost_per_1k: float = 0.0


@dataclass
class CostConfig:
    """Global cost-tracking configuration.

    Attributes:
        enabled: Whether to accumulate costs at all.
        pricing: Mapping of model name to ``ModelPricing``.
    """

    enabled: bool = True
    pricing: dict[str, ModelPricing] = field(default_factory=dict)


class CostTracker:
    """Thread-safe accumulator for LLM token costs.

    Usage::

        tracker = CostTracker(config=CostConfig(pricing={...}))
        tracker.record("gpt-4o", prompt_tokens=500, completion_tokens=100)
        print(tracker.total_cost_usd)
    """

    def __init__(self, config: CostConfig | None = None) -> None:
        self._config = config or CostConfig()
        self._lock = threading.Lock()
        self._total_prompt_tokens = 0
        self._total_completion_tokens = 0
        self._total_cost_usd = 0.0
        self._records: deque[dict[str, Any]] = deque(maxlen=10000)

    def record(
        self,
        model: str,
        *,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
    ) -> float:
        """Record token usage and return the incremental cost in USD."""
        if not self._config.enabled:
            return 0.0

        pricing = self._config.pricing.get(model, ModelPricing())
        cost = (
            prompt_tokens * pricing.prompt_cost_per_1k / 1000.0
            + completion_tokens * pricing.completion_cost_per_1k / 1000.0
        )

        with self._lock:
            self._total_prompt_tokens += prompt_tokens
            self._total_completion_tokens += completion_tokens
            self._total_cost_usd += cost
            self._records.append(
                {
                    "model": model,
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "cost_usd": cost,
                }
            )

        return cost

    @property
    def total_cost_usd(self) -> float:
        with self._lock:
            return self._total_cost_usd

    @property
    def total_prompt_tokens(self) -> int:
        with self._lock:
            return self._total_prompt_tokens

    @property
    def total_completion_tokens(self) -> int:
        with self._lock:
            return self._total_completion_tokens

    @property
    def records(self) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._records)

    def reset(self) -> None:
        """Reset all accumulated costs."""
        with self._lock:
            self._total_prompt_tokens = 0
            self._total_completion_tokens = 0
            self._total_cost_usd = 0.0
            self._records.clear()
