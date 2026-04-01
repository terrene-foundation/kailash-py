# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Reward function protocol and registry for online RL methods.

Security-critical: reward functions are arbitrary Python callables. They MUST
be registered programmatically (NO pickle, NO dynamic import, NO eval).
See ALN-220 and red team C2 for security rationale.
"""
from __future__ import annotations

import math
import logging
from typing import Any, Protocol, runtime_checkable

from kailash_align.exceptions import AlignmentError

logger = logging.getLogger(__name__)

__all__ = [
    "RewardFunction",
    "RewardRegistry",
    "reward_registry",
    "validate_rewards",
]


class RewardValidationError(AlignmentError):
    """Raised when reward function output fails validation."""

    pass


@runtime_checkable
class RewardFunction(Protocol):
    """Protocol for reward functions used by online RL methods (GRPO, RLOO).

    Reward functions score model completions. They receive a batch of completions
    and their corresponding prompts, and return one float score per completion.

    Security: reward functions are Python objects passed programmatically.
    NO serialization (pickle), NO string-based dynamic import, NO eval().
    """

    def __call__(
        self,
        completions: list[str],
        prompts: list[str],
        **kwargs: Any,
    ) -> list[float]:
        """Score completions. Returns one float per completion.

        Args:
            completions: List of model-generated completions to score.
            prompts: List of prompts that generated the completions.
            **kwargs: Additional context (e.g., expected answers).

        Returns:
            List of float scores, one per completion. Higher = better.
        """
        ...


def validate_rewards(
    rewards: list[float],
    num_completions: int,
) -> None:
    """Validate reward function output.

    Checks:
    1. rewards is a list of floats
    2. Length matches num_completions
    3. All values are finite (no NaN, no Inf)

    Args:
        rewards: Output from a reward function.
        num_completions: Expected number of scores.

    Raises:
        RewardValidationError: If validation fails.
    """
    if not isinstance(rewards, list):
        raise RewardValidationError(
            f"Reward function must return list[float], got {type(rewards).__name__}"
        )
    if len(rewards) != num_completions:
        raise RewardValidationError(
            f"Reward function returned {len(rewards)} scores "
            f"for {num_completions} completions"
        )
    for i, r in enumerate(rewards):
        if not isinstance(r, (int, float)):
            raise RewardValidationError(
                f"Reward score at index {i} must be numeric, "
                f"got {type(r).__name__}: {r!r}"
            )
        if not math.isfinite(r):
            raise RewardValidationError(
                f"Reward score at index {i} must be finite, got {r}"
            )


class RewardRegistry:
    """Named reward function registry. Functions registered programmatically only.

    Security constraints (red team C2):
    - NO pickle serialization of reward functions
    - NO importlib.import_module() from user-provided strings for rewards
    - NO eval() or exec() on reward function definitions
    - Config files reference reward functions by NAME only
    - RewardRegistry is in-process only (not distributed)
    """

    def __init__(self) -> None:
        self._registry: dict[str, RewardFunction] = {}

    def register(self, name: str):
        """Decorator to register a reward function by name.

        Usage:
            @reward_registry.register("my_reward")
            def my_reward(completions, prompts, **kwargs):
                return [1.0 for _ in completions]
        """

        def decorator(func: Any) -> Any:
            if not callable(func):
                raise TypeError(
                    f"Reward function must be callable, got {type(func).__name__}"
                )
            self._registry[name] = func
            logger.debug("Registered reward function: %s", name)
            return func

        return decorator

    def register_function(self, name: str, func: Any) -> None:
        """Register a reward function by name (non-decorator form).

        Args:
            name: Name for the reward function.
            func: Callable matching RewardFunction protocol.
        """
        if not callable(func):
            raise TypeError(
                f"Reward function must be callable, got {type(func).__name__}"
            )
        self._registry[name] = func
        logger.debug("Registered reward function: %s", name)

    def get(self, name: str) -> RewardFunction:
        """Get a registered reward function by name.

        Args:
            name: Registered function name.

        Returns:
            The reward function.

        Raises:
            KeyError: If name is not registered.
        """
        if name not in self._registry:
            available = sorted(self._registry.keys())
            raise KeyError(
                f"Reward function '{name}' not registered. "
                f"Available: {available}"
            )
        return self._registry[name]

    def list_names(self) -> list[str]:
        """List all registered reward function names."""
        return sorted(self._registry.keys())

    def __contains__(self, name: str) -> bool:
        return name in self._registry

    def __len__(self) -> int:
        return len(self._registry)


# Module-level singleton
reward_registry = RewardRegistry()


# --- Built-in reward functions ---


@reward_registry.register("exact_match")
def exact_match_reward(
    completions: list[str],
    prompts: list[str],
    *,
    expected: list[str] | None = None,
    **kwargs: Any,
) -> list[float]:
    """1.0 if completion matches expected answer exactly, 0.0 otherwise.

    Args:
        completions: Model completions to score.
        prompts: Original prompts (unused).
        expected: Expected answers. Must be same length as completions.
    """
    if expected is None:
        raise RewardValidationError(
            "exact_match_reward requires 'expected' keyword argument"
        )
    if len(expected) != len(completions):
        raise RewardValidationError(
            f"expected has {len(expected)} items but got {len(completions)} completions"
        )
    return [1.0 if c.strip() == e.strip() else 0.0 for c, e in zip(completions, expected)]


@reward_registry.register("contains_answer")
def contains_answer_reward(
    completions: list[str],
    prompts: list[str],
    *,
    expected: list[str] | None = None,
    **kwargs: Any,
) -> list[float]:
    """1.0 if expected answer appears anywhere in completion, 0.0 otherwise.

    Args:
        completions: Model completions to score.
        prompts: Original prompts (unused).
        expected: Expected answers to search for in completions.
    """
    if expected is None:
        raise RewardValidationError(
            "contains_answer_reward requires 'expected' keyword argument"
        )
    if len(expected) != len(completions):
        raise RewardValidationError(
            f"expected has {len(expected)} items but got {len(completions)} completions"
        )
    return [1.0 if e.strip() in c else 0.0 for c, e in zip(completions, expected)]


@reward_registry.register("length_penalty")
def length_penalty_reward(
    completions: list[str],
    prompts: list[str],
    *,
    max_length: int = 1024,
    **kwargs: Any,
) -> list[float]:
    """Penalize completions exceeding max_length. Score is 1.0 for short, decays for long.

    Score = max(0.0, 1.0 - (len(completion) - max_length) / max_length) for long completions.
    Score = 1.0 for completions within max_length.

    Args:
        completions: Model completions to score.
        prompts: Original prompts (unused).
        max_length: Maximum desired completion length in characters.
    """
    scores: list[float] = []
    for c in completions:
        if len(c) <= max_length:
            scores.append(1.0)
        else:
            penalty = (len(c) - max_length) / max_length
            scores.append(max(0.0, 1.0 - penalty))
    return scores
