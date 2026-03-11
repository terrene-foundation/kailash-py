"""
Cost tracking and budget enforcement for E2E tests.

Provides:
- Cost tracking per test and per suite
- Budget enforcement with abort on exceeded threshold
- Detailed cost reports per provider (Ollama free, OpenAI paid)
"""

from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional


@dataclass
class CostEntry:
    """Single cost entry for a test or operation."""

    test_name: str
    provider: str  # "ollama" or "openai"
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    timestamp: datetime = field(default_factory=datetime.now)

    def __repr__(self) -> str:
        return (
            f"CostEntry(test={self.test_name}, provider={self.provider}, "
            f"model={self.model}, tokens={self.input_tokens + self.output_tokens}, "
            f"cost=${self.cost_usd:.4f})"
        )


class CostTracker:
    """Track and enforce budget limits for E2E tests."""

    # Pricing per 1M tokens (as of 2024-10)
    PRICING = {
        "gpt-4o-mini": {"input": 0.15, "output": 0.60},  # per 1M tokens
        "gpt-4": {"input": 30.00, "output": 60.00},
        "gpt-3.5-turbo": {"input": 0.50, "output": 1.50},
        "llama3.1:8b-instruct-q8_0": {"input": 0.0, "output": 0.0},  # Ollama free
        "llama3.2:3b": {"input": 0.0, "output": 0.0},
    }

    def __init__(self, budget_usd: float = 20.0):
        """Initialize cost tracker with budget limit.

        Args:
            budget_usd: Maximum budget in USD (default: $20 for full E2E suite)
        """
        self.budget_usd = budget_usd
        self.entries: List[CostEntry] = []
        self._current_test: Optional[str] = None

    def track_usage(
        self,
        test_name: str,
        provider: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
    ) -> CostEntry:
        """Track token usage for a test.

        Args:
            test_name: Name of the test
            provider: "ollama" or "openai"
            model: Model name
            input_tokens: Input token count
            output_tokens: Output token count

        Returns:
            CostEntry with calculated cost

        Raises:
            ValueError: If budget exceeded
        """
        cost_usd = self._calculate_cost(model, input_tokens, output_tokens)
        entry = CostEntry(
            test_name=test_name,
            provider=provider,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost_usd,
        )
        self.entries.append(entry)

        # Check budget
        total_cost = self.get_total_cost()
        if total_cost > self.budget_usd:
            raise ValueError(
                f"Budget exceeded! Total: ${total_cost:.2f} > ${self.budget_usd:.2f}"
            )

        return entry

    def _calculate_cost(
        self, model: str, input_tokens: int, output_tokens: int
    ) -> float:
        """Calculate cost in USD for token usage.

        Args:
            model: Model name
            input_tokens: Input token count
            output_tokens: Output token count

        Returns:
            Cost in USD
        """
        if model not in self.PRICING:
            print(f"Warning: Unknown model '{model}', assuming free (Ollama)")
            return 0.0

        pricing = self.PRICING[model]
        input_cost = (input_tokens / 1_000_000) * pricing["input"]
        output_cost = (output_tokens / 1_000_000) * pricing["output"]
        return input_cost + output_cost

    def get_total_cost(self) -> float:
        """Get total cost across all tracked entries."""
        return sum(entry.cost_usd for entry in self.entries)

    def get_cost_by_provider(self) -> Dict[str, float]:
        """Get cost breakdown by provider."""
        costs = {}
        for entry in self.entries:
            costs[entry.provider] = costs.get(entry.provider, 0.0) + entry.cost_usd
        return costs

    def get_cost_by_test(self) -> Dict[str, float]:
        """Get cost breakdown by test."""
        costs = {}
        for entry in self.entries:
            costs[entry.test_name] = costs.get(entry.test_name, 0.0) + entry.cost_usd
        return costs

    def print_report(self):
        """Print detailed cost report."""
        print("\n" + "=" * 80)
        print("COST TRACKING REPORT")
        print("=" * 80)

        total = self.get_total_cost()
        remaining = self.budget_usd - total
        pct_used = (total / self.budget_usd) * 100

        print(f"\nBudget: ${self.budget_usd:.2f}")
        print(f"Total Cost: ${total:.4f} ({pct_used:.1f}%)")
        print(f"Remaining: ${remaining:.4f}")

        print("\n--- By Provider ---")
        for provider, cost in self.get_cost_by_provider().items():
            print(f"  {provider}: ${cost:.4f}")

        print("\n--- Top 10 Most Expensive Tests ---")
        by_test = self.get_cost_by_test()
        top_tests = sorted(by_test.items(), key=lambda x: x[1], reverse=True)[:10]
        for test_name, cost in top_tests:
            print(f"  {test_name}: ${cost:.4f}")

        print("\n--- All Entries ---")
        for entry in self.entries:
            print(f"  {entry}")

        print("=" * 80 + "\n")

    @contextmanager
    def track_test(self, test_name: str):
        """Context manager to track a single test.

        Usage:
            with cost_tracker.track_test("test_my_feature"):
                # Run test that calls track_usage()
                pass
        """
        self._current_test = test_name
        try:
            yield self
        finally:
            self._current_test = None


# Global tracker for pytest
_global_tracker: Optional[CostTracker] = None


def get_global_tracker(budget_usd: float = 20.0) -> CostTracker:
    """Get or create global cost tracker."""
    global _global_tracker
    if _global_tracker is None:
        _global_tracker = CostTracker(budget_usd=budget_usd)
    return _global_tracker


def reset_global_tracker():
    """Reset global tracker (for testing)."""
    global _global_tracker
    _global_tracker = None
