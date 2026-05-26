# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Typed exceptions for the ``_from_brief`` LLM-mediation pipeline.

The ``from_brief()`` primitives accept natural-language input and emit a
typed plan via an LLM Signature. Three distinct failure modes can occur
while validating that plan against the framework primitive being
realized: the LLM rated its own confidence too low, the LLM emitted a
node-type / field-type / config-value the framework does not expose, or
the plan was structurally malformed.

A single typed exception with discriminator fields lets every caller
react precisely without parsing exception messages. Per
``rules/zero-tolerance.md`` Rule 3a, raising a typed exception at the
validation gate turns an opaque ``AttributeError`` (from later code
trying to use a missing plan field) into a one-line fix instruction.

Origin: issue #1125 — the documented "natural language to running
workflow" pipeline cannot complete unless plan-validation failures
surface as typed errors with structured discriminators.
"""

from __future__ import annotations

from typing import Optional


class BriefInterpretationError(ValueError):
    """Raised when an LLM-emitted plan cannot be realized into a primitive.

    The exception carries three discriminator fields so callers can
    branch on the failure mode without string-matching the message:

    - ``low_confidence``: the LLM's self-rated
      ``interpretation_confidence`` fell below the gate threshold.
    - ``unknown_value``: the LLM emitted a node-type / field-type /
      config-value that is not in the caller-provided allowlist. The
      offending name is the value of this field.
    - ``malformed``: the plan was structurally invalid (missing field,
      wrong type, schema violation).

    Subclassing :class:`ValueError` preserves the principle that the
    plan came from user-supplied input; the call site already catches
    ``ValueError`` for input validation, and the typed shape extends
    rather than replaces that contract.

    Example:
        try:
            validate_plan(plan, ...)
        except BriefInterpretationError as exc:
            if exc.low_confidence:
                # ask the user to rephrase the brief
                ...
            elif exc.unknown_value is not None:
                # the brief mentioned a primitive that does not exist
                ...
            elif exc.malformed:
                # the LLM produced an off-schema plan; retry or bail
                ...

    Args:
        message: Human-readable description of the failure.
        low_confidence: True when the failure is a confidence-gate miss.
        unknown_value: The unknown node/field/config name, when the
            failure is an allowlist miss; ``None`` otherwise.
        malformed: True when the plan was structurally invalid.
    """

    def __init__(
        self,
        message: str,
        *,
        low_confidence: bool = False,
        unknown_value: Optional[str] = None,
        malformed: bool = False,
    ) -> None:
        super().__init__(message)
        self.low_confidence = low_confidence
        self.unknown_value = unknown_value
        self.malformed = malformed
