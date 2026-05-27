# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Typed plan validator for LLM-emitted ``from_brief()`` outputs.

Every ``from_brief()`` primitive funnels its Signature output through
:func:`validate_plan` before deterministic realization. The validator
composes three independent gates:

1. Structural gate — :class:`BriefPlan` (Pydantic v2 BaseModel) carries
   the floor contract (``interpretation_confidence: float``); subclasses
   add their primitive-specific fields. Pydantic raises
   :class:`pydantic.ValidationError` on malformed input.
2. Confidence gate — :func:`kailash._from_brief.confidence.check_confidence`
   raises :class:`BriefInterpretationError(low_confidence=True)` when
   the LLM's self-rated confidence is below the threshold.
3. Allowlist gate — when ``allowed_node_types`` / ``allowed_field_types``
   / ``allowed_config_values`` are provided AND the plan exposes
   ``node_types`` / ``field_types`` / ``config_values`` attributes
   (typical for plan subclasses), each LLM-emitted identifier is
   checked against the caller-provided allowlist.

A typed exception is raised at the first failure so the caller can
branch on the discriminator (``low_confidence`` / ``unknown_value`` /
``malformed``) without parsing exception messages.

Origin: issue #1125 — the documented "natural language to running
workflow" pipeline cannot complete without a typed validation gate; an
``AttributeError`` raised five frames into the realizer is unactionable.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, Optional, Set

from pydantic import BaseModel, ConfigDict, ValidationError

from kailash._from_brief.allowlist import (
    validate_config_value,
    validate_field_type,
    validate_node_type,
)
from kailash._from_brief.confidence import (
    DEFAULT_CONFIDENCE_THRESHOLD,
    check_confidence,
)
from kailash._from_brief.exceptions import BriefInterpretationError

__all__ = ["BriefPlan", "validate_plan"]


class BriefPlan(BaseModel):
    """Base class for every LLM-emitted plan in the ``from_brief()`` pipeline.

    Every Signature output Pydantic-models from this class so the
    confidence-gate field is uniform across primitives. Plan
    subclasses add their own typed fields (e.g. a node plan adds
    ``node_type: str`` and ``config: dict``).

    Pydantic's ``extra="forbid"`` config means an LLM emitting a stray
    field raises at model construction — converting "the LLM
    hallucinated a field" into a loud, debuggable error rather than a
    silently-ignored extra.
    """

    # ``allow_inf_nan=False`` rejects NaN/±inf at Pydantic construction —
    # defense-in-depth for the confidence gate (the LLM cannot smuggle a
    # NaN confidence past the float field). ``check_confidence`` enforces
    # the same floor with ``math.isfinite`` at the gate.
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    interpretation_confidence: float
    """The LLM's self-rated 0.0-1.0 confidence in the plan."""


def _iter_str_values(value: Any) -> Iterable[str]:
    """Yield every string the LLM might have emitted as a name.

    Plan subclasses may expose node-type / field-type identifiers as
    either a single string (``node_type: str``), a list of strings
    (``node_types: list[str]``), or a dict whose keys are identifiers
    (``fields: dict[str, str]``). This helper normalizes those shapes
    so the allowlist gate can iterate without knowing the plan's
    concrete schema.
    """
    if value is None:
        return
    if isinstance(value, str):
        yield value
        return
    if isinstance(value, dict):
        for key in value.keys():
            if isinstance(key, str):
                yield key
        return
    if isinstance(value, (list, tuple, set, frozenset)):
        for item in value:
            if isinstance(item, str):
                yield item


def validate_plan(
    plan: BriefPlan,
    *,
    allowed_node_types: Optional[Set[str]] = None,
    allowed_field_types: Optional[Set[str]] = None,
    allowed_config_values: Optional[Dict[str, Set[str]]] = None,
    confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
) -> None:
    """Validate an LLM-emitted plan against three independent gates.

    Args:
        plan: The plan to validate. Already Pydantic-validated by
            construction; this function adds the confidence + allowlist
            gates on top of the structural gate Pydantic enforces.
        allowed_node_types: When provided, every identifier surfaced
            by the plan's ``node_type`` or ``node_types`` attribute MUST
            be a member of this set. ``None`` skips the node-type gate.
        allowed_field_types: When provided, every identifier surfaced
            by the plan's ``field_type`` / ``field_types`` / ``fields``
            attribute MUST be a member of this set. ``None`` skips the
            field-type gate.
        allowed_config_values: When provided, for every field listed
            in the plan's ``config`` / ``config_values`` attribute,
            the corresponding value MUST be a member of
            ``allowed_config_values[field]``. ``None`` skips the
            config-value gate.
        confidence_threshold: The minimum
            ``interpretation_confidence`` required to pass. Defaults
            to :data:`DEFAULT_CONFIDENCE_THRESHOLD` (0.6).

    Raises:
        BriefInterpretationError: With ``low_confidence=True`` when the
            confidence gate fails. With ``unknown_value=<name>`` when
            an allowlist gate fails. With ``malformed=True`` when the
            confidence value is outside the 0.0-1.0 range OR the plan
            shape violates an invariant.

    Returns:
        ``None`` when every gate passes.
    """
    # Confidence gate — raises on out-of-range AND on below-threshold.
    check_confidence(plan.interpretation_confidence, threshold=confidence_threshold)

    # Allowlist gate — node types.
    if allowed_node_types is not None:
        for attr in ("node_type", "node_types"):
            value = getattr(plan, attr, None)
            for name in _iter_str_values(value):
                validate_node_type(name, allowed_node_types)

    # Allowlist gate — field types.
    if allowed_field_types is not None:
        for attr in ("field_type", "field_types", "fields"):
            value = getattr(plan, attr, None)
            # For dict-of-name-to-type, the type strings are the
            # values, not the keys. Inspect dict values too.
            if isinstance(value, dict):
                for inner in value.values():
                    if isinstance(inner, str):
                        validate_field_type(inner, allowed_field_types)
            else:
                for name in _iter_str_values(value):
                    validate_field_type(name, allowed_field_types)

    # Allowlist gate — config values.
    if allowed_config_values is not None:
        config = getattr(plan, "config", None) or getattr(plan, "config_values", None)
        if isinstance(config, dict):
            for field, value in config.items():
                if not isinstance(field, str) or not isinstance(value, str):
                    # Non-string keys/values fall outside the
                    # allowlist contract; they were structurally
                    # accepted by Pydantic. Skip silently here — the
                    # gate covers enum-shaped string fields only.
                    continue
                validate_config_value(field, value, allowed_config_values)


def coerce_plan(
    raw: Dict[str, Any],
    plan_cls: type[BriefPlan],
) -> BriefPlan:
    """Construct ``plan_cls`` from a raw dict, translating Pydantic errors.

    Convenience helper for call sites that receive an LLM's raw
    Signature output as a dict (e.g. via the autonomous-tool-calling
    path that does not pre-validate). Wraps :class:`pydantic.ValidationError`
    in :class:`BriefInterpretationError(malformed=True)` so callers see
    a uniform exception surface.

    Args:
        raw: The LLM's emitted plan as a dictionary.
        plan_cls: The concrete :class:`BriefPlan` subclass to construct.

    Raises:
        BriefInterpretationError: With ``malformed=True`` when Pydantic
            validation fails. The original ``ValidationError`` is
            attached as ``__cause__`` for diagnostic traceback.

    Returns:
        A validated instance of ``plan_cls``.
    """
    try:
        return plan_cls.model_validate(raw)
    except ValidationError as exc:
        raise BriefInterpretationError(
            f"the LLM emitted a plan that does not conform to "
            f"{plan_cls.__name__}: {exc.errors()!r}",
            malformed=True,
        ) from exc
