"""
FallbackStrategy - Try strategies in sequence until one succeeds.

Use Cases:
- Primary LLM fails, fallback to secondary
- Try expensive strategy first, cheap strategy if it fails
- Progressive degradation (GPT-4 → GPT-3.5 → local model)
- Redundancy for critical operations
"""

from typing import Any, Dict, List, Tuple


class FallbackStrategy:
    """
    Strategy that tries multiple strategies in sequence until one succeeds.

    Use Cases:
    - Primary LLM fails, fallback to secondary
    - Try expensive strategy first, cheap strategy if it fails
    - Progressive degradation (GPT-4 → GPT-3.5 → local model)
    - Redundancy for critical operations
    """

    def __init__(self, strategies: List[Any]):
        """
        Initialize fallback strategy.

        Args:
            strategies: List of strategies to try in order

        Raises:
            ValueError: If strategies list is empty
        """
        if not strategies:
            raise ValueError("FallbackStrategy requires at least one strategy")

        self.strategies = strategies
        self.last_errors: List[Tuple[Any, Exception]] = []

    async def execute(self, agent, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """
        Try strategies in sequence until one succeeds.

        Args:
            agent: Agent instance
            inputs: Input dictionary

        Returns:
            Result from first successful strategy

        Raises:
            RuntimeError: If all strategies fail
        """
        self.last_errors = []

        for i, strategy in enumerate(self.strategies):
            try:
                # Try this strategy
                result = await strategy.execute(agent, inputs)

                # Success! Add metadata about which strategy succeeded
                result["_fallback_strategy_used"] = i
                result["_fallback_attempts"] = i + 1

                return result

            except Exception as e:
                # Failed - track error and try next
                self.last_errors.append((strategy, e))
                continue

        # All strategies failed — truncate error messages to avoid leaking internals
        error_msg = f"All {len(self.strategies)} strategies failed:\n"
        for i, (strategy, error) in enumerate(self.last_errors):
            strategy_name = strategy.__class__.__name__
            truncated = str(error)[:200]
            error_msg += f"  {i+1}. {strategy_name}: {truncated}\n"

        raise RuntimeError(error_msg)

    def get_error_summary(self) -> List[Dict[str, Any]]:
        """
        Get summary of errors from failed strategies.

        Returns:
            List of error summaries with strategy name, error message, and error type
        """
        return [
            {
                "strategy": strategy.__class__.__name__,
                "error": str(error)[:200],
                "error_type": error.__class__.__name__,
            }
            for strategy, error in self.last_errors
        ]
