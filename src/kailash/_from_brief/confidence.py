# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Confidence-gate helper for LLM-emitted plans.

Every Signature in the ``_from_brief`` pipeline emits a float field
``interpretation_confidence`` (range 0.0-1.0) representing the LLM's
own assessment of how confident it is in the plan. A plan below the
threshold is BLOCKED rather than silently realized — per
``rules/zero-tolerance.md`` Rule 3, no silent fallback at the gate.

Origin: issue #1125 — the documented "natural language to running
workflow" pipeline cannot complete unless low-confidence plans fail
loudly. The threshold default of 0.6 mirrors common LLM-judge
calibration baselines and is overridable per call.
"""

from __future__ import annotations

from kailash._from_brief.exceptions import BriefInterpretationError

__all__ = ["DEFAULT_CONFIDENCE_THRESHOLD", "check_confidence"]


# Module-level default. Callers MAY override per call; the central
# constant ensures every primitive sees the same baseline so a brief
# that fails the gate at one surface fails at every surface.
DEFAULT_CONFIDENCE_THRESHOLD: float = 0.6


def check_confidence(
    value: float,
    *,
    threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
) -> None:
    """Raise :class:`BriefInterpretationError` when confidence is below threshold.

    Args:
        value: The LLM's self-rated ``interpretation_confidence`` from
            the plan Signature output. Expected range is 0.0-1.0; values
            outside this range are treated as malformed (an LLM emitting
            ``-1.0`` or ``2.0`` failed the structured-output contract).
        threshold: The minimum confidence required to proceed. Defaults
            to :data:`DEFAULT_CONFIDENCE_THRESHOLD` (0.6).

    Raises:
        BriefInterpretationError: With ``low_confidence=True`` when
            ``value < threshold``. With ``malformed=True`` when ``value``
            is outside the 0.0-1.0 range.

    Returns:
        ``None`` when the value is at or above the threshold.
    """
    if value < 0.0 or value > 1.0:
        raise BriefInterpretationError(
            f"interpretation_confidence={value!r} is outside the 0.0-1.0 "
            f"range; the LLM emitted a malformed confidence score",
            malformed=True,
        )
    if value < threshold:
        raise BriefInterpretationError(
            f"interpretation_confidence={value:.3f} is below the gate "
            f"threshold {threshold:.3f}; rephrase the brief or raise the "
            f"threshold explicitly to override",
            low_confidence=True,
        )
