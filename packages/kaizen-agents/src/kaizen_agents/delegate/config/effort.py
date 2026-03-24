"""Effort level presets for kz CLI.

Three effort levels control model selection, token budgets, temperature,
and reasoning depth. Users pick an effort level; the system maps it to
concrete LLM parameters.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass


class EffortLevel(enum.Enum):
    """Effort levels available to the user."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass(frozen=True)
class EffortPreset:
    """Concrete LLM parameters for a given effort level."""

    level: EffortLevel
    model: str
    temperature: float
    max_tokens: int
    reasoning_effort: str  # "low", "medium", "high" — passed to provider if supported


# Default presets — can be overridden by config.
def _default_presets() -> dict[EffortLevel, EffortPreset]:
    """Build presets using .env model names when available."""
    import os

    default_model = os.environ.get("DEFAULT_LLM_MODEL", "gpt-4o")
    dev_model = os.environ.get("OPENAI_DEV_MODEL", "gpt-4o-mini")
    prod_model = os.environ.get("OPENAI_PROD_MODEL", default_model)

    return {
        EffortLevel.LOW: EffortPreset(
            level=EffortLevel.LOW,
            model=dev_model,
            temperature=0.2,
            max_tokens=4096,
            reasoning_effort="low",
        ),
        EffortLevel.MEDIUM: EffortPreset(
            level=EffortLevel.MEDIUM,
            model=default_model,
            temperature=0.4,
            max_tokens=16384,
            reasoning_effort="medium",
        ),
        EffortLevel.HIGH: EffortPreset(
            level=EffortLevel.HIGH,
            model=prod_model,
            temperature=1.0,
            max_tokens=65536,
            reasoning_effort="high",
        ),
    }


_PRESETS: dict[EffortLevel, EffortPreset] | None = None


def get_effort_preset(
    level: EffortLevel | str,
    *,
    model_override: str | None = None,
    temperature_override: float | None = None,
    max_tokens_override: int | None = None,
) -> EffortPreset:
    """Return the preset for a given effort level, with optional overrides.

    Parameters
    ----------
    level:
        The effort level (enum member or string name).
    model_override:
        If provided, replaces the preset's model.
    temperature_override:
        If provided, replaces the preset's temperature.
    max_tokens_override:
        If provided, replaces the preset's max_tokens.

    Returns
    -------
    EffortPreset with the resolved values.
    """
    if isinstance(level, str):
        level = EffortLevel(level.lower())

    global _PRESETS
    if _PRESETS is None:
        _PRESETS = _default_presets()

    base = _PRESETS[level]

    return EffortPreset(
        level=base.level,
        model=model_override if model_override is not None else base.model,
        temperature=temperature_override if temperature_override is not None else base.temperature,
        max_tokens=max_tokens_override if max_tokens_override is not None else base.max_tokens,
        reasoning_effort=base.reasoning_effort,
    )
