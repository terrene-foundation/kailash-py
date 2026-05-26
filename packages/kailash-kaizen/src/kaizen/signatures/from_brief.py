# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""``Kaizen.signature_from_brief`` — runtime Signature subclass from a brief.

Closes issue #1125 acceptance criterion 3:

    ``kailash.Kaizen.signature_from_brief(brief)`` returns a ``Signature``
    subclass with typed input + output fields, usable as the ``signature=``
    arg to any Kaizen agent constructor.

This module is the **Kaizen** surface of the ``from_brief()`` family.
The result of the call is a ``Signature`` SUBCLASS (a Python class
object, not an instance) — the user instantiates it themselves and
passes it as ``signature=MyNewSig()`` to ``BaseAgent`` (or any Kaizen
agent constructor). The naming reflects that distinction: the verb is
``signature_from_brief``, not ``from_brief``, because the return value
is a Signature, not a Kaizen instance.

## Pipeline

::

    brief (prose)
      → scrub_brief()                              # credential scrub
      → SignaturePlanSignature (meta-Signature)    # LLM emits typed plan
      → validate_plan() (confidence + allowlist)   # gate
      → SignatureMeta-mediated class construction  (type(name, bases, ns))
      → Signature subclass                         # AC 3 return shape

The pipeline composes the S1 foundation modules
(:mod:`kailash._from_brief`) so the LLM-mediation discipline
(scrubbing, confidence gating, field-type allowlisting, typed
exceptions) is identical across every ``from_brief()`` surface.

## Field-type allowlist

Per the architecture plan §3.3 and S1 invariant 2, every LLM-emitted
field type is validated against a closed allowlist BEFORE the realizer
constructs the class. The allowlist below covers the Python types
Kaizen Signatures actually use today (per a grep over
``packages/kailash-kaizen/src/kaizen/signatures/`` showing exclusively
``str``, ``int``, ``float``, ``bool``, ``list``, ``dict``,
``Optional[X]``, and ``List[Y]`` annotations on InputField/OutputField
declarations). Extending the allowlist requires an explicit code
change so the realizer cannot silently accept a hallucinated type.

## LLM-first reasoning (rules/agent-reasoning.md)

The Signature description tells the LLM what to emit; the realizer is
DETERMINISTIC structural plumbing — no ``if``/``elif`` on brief
content, no keyword routing, no regex classification. The LLM IS the
classifier and extractor.

Origin: issue #1125 AC 3 + AC 8; architecture plan §3.3.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Set, Tuple, Type

from kailash._from_brief import (
    BriefInterpretationError,
    BriefPlanSignature,
    coerce_plan,
    get_default_llm_model,
    scrub_brief,
    validate_field_type,
)
from kailash._from_brief.confidence import (
    DEFAULT_CONFIDENCE_THRESHOLD,
    check_confidence,
)
from kailash._from_brief.validator import BriefPlan

from .core import InputField, OutputField, Signature

__all__ = [
    "ALLOWED_FIELD_TYPES",
    "FIELD_TYPE_MAP",
    "SignaturePlanSignature",
    "SignaturePlan",
    "signature_from_brief",
]


logger = logging.getLogger(__name__)


# =========================================================================
# Field-type allowlist
# =========================================================================
#
# The strings below are the ONLY type identifiers the LLM may emit for
# input/output field types. The mapping resolves each string to the
# runtime Python type the realizer uses when constructing the
# Signature subclass via ``type(name, (Signature,), namespace)``.
#
# Extending this set requires an explicit code change so a
# hallucinated type ("Tensor", "Path", "DataFrame") fails loudly at
# the validation gate rather than silently constructing a broken
# Signature.
#
# Scope (per architecture plan §3.3): cover what existing Kaizen
# Signatures use today. The grep over
# ``packages/kailash-kaizen/src/kaizen/signatures/`` shows
# exclusively ``str``, ``int``, ``float``, ``bool``, ``list``,
# ``dict`` annotations on InputField/OutputField; the
# ``Optional[X]`` and ``List[Y]`` parametrized variants are exposed
# but documented as advanced — not part of the v1 ``from_brief()``
# surface.

FIELD_TYPE_MAP: Dict[str, type] = {
    "str": str,
    "int": int,
    "float": float,
    "bool": bool,
    "list": list,
    "dict": dict,
}
"""Mapping from LLM-emitted type identifier to runtime Python type."""

ALLOWED_FIELD_TYPES: Set[str] = set(FIELD_TYPE_MAP.keys())
"""The closed set of type identifiers the LLM may emit."""


# =========================================================================
# Meta-Signature (Kaizen Signature that emits a Signature spec)
# =========================================================================


class SignaturePlanSignature(BriefPlanSignature):
    """Meta-Signature: parse a brief into a Kaizen Signature spec.

    Per the architecture plan §3.3, this Signature is the
    LLM-mediation surface for ``Kaizen.signature_from_brief``. The
    realizer feeds the LLM's emitted plan to a single
    :class:`SignatureMeta` invocation that constructs the new
    Signature subclass at runtime.

    Plan-emitted fields:

    - ``class_name``: PascalCase identifier for the synthesized
      Signature class (e.g. ``"CustomerSupportSignature"``). The
      realizer uses this as the first argument to ``type(...)``.
    - ``input_fields``: list of ``(name, type, description)`` triples
      describing each :class:`InputField` declaration. The realizer
      validates every ``type`` string against
      :data:`ALLOWED_FIELD_TYPES`.
    - ``output_fields``: list of ``(name, type, description)`` triples
      describing each :class:`OutputField` declaration. Same
      allowlist gate as inputs.
    - ``instructions``: the docstring/instructions block the
      synthesized Signature carries (advisory text the LLM downstream
      consumes when the Signature is invoked).

    The LLM is instructed in the descriptions below to:

    1. Pick a PascalCase name reflecting the brief's intent.
    2. Identify the prose's input variables → InputField list.
    3. Identify the prose's expected outputs → OutputField list.
    4. Distill the brief's reasoning instructions into a docstring.
    5. Self-rate the interpretation confidence (inherited from
       :class:`BriefPlanSignature`).

    See :class:`BriefPlanSignature` for the inherited ``brief`` +
    ``interpretation_confidence`` floor contract; this subclass
    layers four plan-specific OutputFields on top.
    """

    # The pyright suppressions cite the same Kaizen-wide
    # reportAssignmentType pattern as the S1 BriefPlanSignature base
    # class — see ``src/kailash/_from_brief/signatures.py:110-138``
    # for the full rationale + #73 citation. Runtime safety:
    # ``SignatureMeta`` rebinds these class attributes at class
    # creation; they never hold the raw ``OutputField`` instance at
    # runtime. The shape ``: <type> = OutputField(...)`` is canonical
    # across every existing Kaizen Signature subclass.
    class_name: str = OutputField(  # pyright: ignore[reportAssignmentType]
        description=(
            "A PascalCase identifier for the synthesized Signature "
            "class (e.g. 'CustomerSupportSignature', "
            "'OrderClassifierSignature'). Choose a name that "
            "reflects the brief's intent; the name appears in error "
            "messages and logs."
        )
    )
    input_fields: list = OutputField(  # pyright: ignore[reportAssignmentType]
        description=(
            "List of [name, type, description] triples describing "
            "each InputField the synthesized Signature exposes. "
            "Each triple is a 3-element list. `name` is the snake_case "
            "Python attribute name. `type` MUST be one of: 'str', "
            "'int', 'float', 'bool', 'list', 'dict'. `description` is "
            "a one-sentence human-readable description of the field. "
            "Example: [['question', 'str', 'The user question to "
            "answer'], ['context', 'str', 'Optional supporting "
            "context']]."
        )
    )
    output_fields: list = OutputField(  # pyright: ignore[reportAssignmentType]
        description=(
            "List of [name, type, description] triples describing "
            "each OutputField the synthesized Signature exposes. "
            "Same shape and type allowlist as input_fields. Example: "
            "[['answer', 'str', 'A clear, accurate answer'], "
            "['confidence', 'float', 'A 0.0-1.0 self-rated confidence "
            "score']]."
        )
    )
    instructions: str = OutputField(  # pyright: ignore[reportAssignmentType]
        description=(
            "The docstring/instructions block for the synthesized "
            "Signature class. This text becomes the Signature's "
            "__doc__ attribute and is the prose the LLM downstream "
            "consumes when the Signature is invoked. Phrase as "
            "imperative instructions describing the reasoning the "
            "LLM should perform when fulfilling the Signature."
        )
    )


# =========================================================================
# Pydantic plan (for typed validation between Signature and realizer)
# =========================================================================


class SignaturePlan(BriefPlan):
    """Typed plan model for ``signature_from_brief()`` outputs.

    Pydantic v2 model that mirrors :class:`SignaturePlanSignature`'s
    OutputFields. The S1 :func:`coerce_plan` helper converts the
    LLM's raw dict output into an instance of this model, raising
    :class:`BriefInterpretationError(malformed=True)` on schema
    violations.

    The ``field_types`` property is the attribute the S1
    :func:`validate_plan` allowlist gate inspects — it surfaces the
    union of input + output type strings so a single allowlist sweep
    covers both lists.
    """

    class_name: str
    input_fields: List[List[Any]]
    output_fields: List[List[Any]]
    instructions: str

    @property
    def field_types(self) -> List[str]:
        """Return every type string the plan emits (inputs + outputs).

        Used by the realizer to validate against
        :data:`ALLOWED_FIELD_TYPES`. Inspects the second element of
        each triple; non-string entries surface as part of the
        ``unknown_value`` allowlist failure (the validator will reject
        a non-string type identifier).
        """
        types: List[str] = []
        for triple in self.input_fields:
            if len(triple) >= 2 and isinstance(triple[1], str):
                types.append(triple[1])
        for triple in self.output_fields:
            if len(triple) >= 2 and isinstance(triple[1], str):
                types.append(triple[1])
        return types


# =========================================================================
# Validation helpers
# =========================================================================


def _validate_class_name(name: str) -> None:
    """Raise if ``name`` is not a valid Python class identifier.

    A LLM-emitted class name is used as the first argument to
    ``type(name, bases, ns)``; Python silently accepts an invalid
    identifier here (the class is constructed but cannot be referenced
    by that name). Guard the realizer's input so a malformed name
    fails loudly at the validation gate.
    """
    if not name:
        raise BriefInterpretationError(
            "class_name is empty; the LLM did not emit a Signature " "class name",
            malformed=True,
        )
    if not name.isidentifier():
        raise BriefInterpretationError(
            f"class_name={name!r} is not a valid Python identifier; "
            f"the LLM emitted a malformed class name",
            malformed=True,
        )


def _validate_triples(
    triples: List[List[Any]],
    *,
    field_kind: str,
) -> List[Tuple[str, str, str]]:
    """Coerce + validate a list of LLM-emitted field triples.

    Each triple MUST be a 3-element list of strings:
    ``[name, type, description]``. Returns the validated triples as
    tuples for use by the realizer; raises
    :class:`BriefInterpretationError(malformed=True)` on any shape
    violation.

    The per-element type-string allowlist gate runs separately via
    :func:`validate_field_type` — this helper only enforces the
    structural triple shape.

    Args:
        triples: The LLM-emitted list of triples.
        field_kind: ``"input"`` or ``"output"`` for error messages.

    Returns:
        List of ``(name, type, description)`` tuples.
    """
    validated: List[Tuple[str, str, str]] = []
    for index, triple in enumerate(triples):
        if not isinstance(triple, list) or len(triple) != 3:
            raise BriefInterpretationError(
                f"{field_kind}_fields[{index}]={triple!r} is not a "
                f"3-element list; expected [name, type, description]",
                malformed=True,
            )
        name, type_str, description = triple
        if not isinstance(name, str) or not name.isidentifier():
            raise BriefInterpretationError(
                f"{field_kind}_fields[{index}].name={name!r} is not a "
                f"valid Python identifier",
                malformed=True,
            )
        if not isinstance(type_str, str):
            raise BriefInterpretationError(
                f"{field_kind}_fields[{index}].type={type_str!r} is " f"not a string",
                malformed=True,
            )
        if not isinstance(description, str):
            raise BriefInterpretationError(
                f"{field_kind}_fields[{index}].description="
                f"{description!r} is not a string",
                malformed=True,
            )
        validated.append((name, type_str, description))
    return validated


# =========================================================================
# Realizer (deterministic Signature subclass construction)
# =========================================================================


def _realize_signature(plan: SignaturePlan) -> Type[Signature]:
    """Construct a :class:`Signature` subclass from a validated plan.

    This is the deterministic structural-plumbing step: it does NOT
    reason about the brief — the LLM already did. It takes the typed
    plan and feeds the plan-derived ``(name, bases, namespace)``
    triple to ``type(...)``. The :class:`SignatureMeta` metaclass on
    :class:`Signature` then processes the namespace and registers the
    ``_signature_inputs`` / ``_signature_outputs`` dictionaries the
    rest of Kaizen depends on.

    Per the architecture plan §3.3, the realizer is a single
    ``type(class_name, (Signature,), namespace_dict)`` call — no
    ad-hoc class-attribute setting; the metaclass governs the
    canonical Signature shape (invariant 6).

    Args:
        plan: A validated :class:`SignaturePlan` whose ``class_name``,
            ``input_fields``, and ``output_fields`` have already
            passed :func:`_validate_class_name`, the triple-shape
            check, and the :data:`ALLOWED_FIELD_TYPES` allowlist.

    Returns:
        A new :class:`Signature` subclass.
    """
    input_triples = _validate_triples(plan.input_fields, field_kind="input")
    output_triples = _validate_triples(plan.output_fields, field_kind="output")

    # Build the class namespace the metaclass consumes. The shape
    # mirrors a hand-authored Signature subclass:
    #
    #   class MySignature(Signature):
    #       """<instructions>"""
    #       field_a: str = InputField(description=...)
    #       field_b: int = OutputField(description=...)
    #
    # The metaclass reads ``__annotations__`` to find the field
    # annotation types and pairs each one with its InputField/OutputField
    # default.
    namespace: Dict[str, Any] = {
        "__doc__": plan.instructions,
        "__annotations__": {},
    }
    for name, type_str, description in input_triples:
        runtime_type = FIELD_TYPE_MAP[type_str]
        namespace["__annotations__"][name] = runtime_type
        namespace[name] = InputField(description=description)
    for name, type_str, description in output_triples:
        runtime_type = FIELD_TYPE_MAP[type_str]
        namespace["__annotations__"][name] = runtime_type
        namespace[name] = OutputField(description=description)

    # ``type(name, bases, namespace)`` invokes ``SignatureMeta.__new__``
    # because ``Signature``'s metaclass is ``SignatureMeta``. The
    # metaclass processes the annotations + InputField/OutputField
    # defaults, registers ``_signature_inputs`` / ``_signature_outputs``,
    # and returns the new class. This IS the documented runtime
    # construction pattern for Signature subclasses.
    new_class = type(plan.class_name, (Signature,), namespace)
    return new_class


# =========================================================================
# Public entry point — bound onto Kaizen as a classmethod via __init__.py
# =========================================================================


def signature_from_brief(
    brief: str,
    *,
    model: Optional[str] = None,
    confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
) -> Type[Signature]:
    """Build a :class:`Signature` subclass from a natural-language brief.

    Closes issue #1125 acceptance criterion 3. The result is a
    Signature SUBCLASS (a Python class object) — instantiate it and
    pass it as ``signature=MySig()`` to any Kaizen agent constructor.

    Pipeline (composes :mod:`kailash._from_brief`):

    1. :func:`scrub_brief` masks credentials in the brief BEFORE
       logging or LLM call.
    2. :class:`SignaturePlanSignature` emits a typed plan (class
       name, input fields, output fields, instructions, confidence).
    3. :func:`check_confidence` raises
       :class:`BriefInterpretationError(low_confidence=True)` when the
       LLM rates its plan below ``confidence_threshold``.
    4. :func:`validate_field_type` raises
       :class:`BriefInterpretationError(unknown_value=<type>)` when
       the LLM emits a type outside :data:`ALLOWED_FIELD_TYPES`.
    5. :func:`_realize_signature` constructs the Signature subclass
       via :class:`SignatureMeta`.

    Args:
        brief: The user's natural-language description of the
            Signature to synthesize. Credentials are scrubbed at
            intake; the raw brief is never logged.
        model: Optional LLM model identifier. Defaults to the value
            of ``DEFAULT_LLM_MODEL`` in the environment (per
            ``rules/env-models.md``); raises
            :class:`MissingDefaultLLMModelError` when neither is set.
        confidence_threshold: Minimum interpretation confidence
            required to realize the plan (default 0.6).

    Returns:
        A :class:`Signature` subclass usable as ``signature=MySig()``
        to any Kaizen agent constructor.

    Raises:
        BriefInterpretationError: When the LLM's plan fails the
            confidence gate, the field-type allowlist gate, or the
            structural shape check.
        MissingDefaultLLMModelError: When ``model`` is None AND
            ``DEFAULT_LLM_MODEL`` is unset.
    """
    # Step 1 — credential scrub. Done at intake so no log path sees
    # the raw brief (per rules/security.md § "No secrets in logs").
    scrubbed = scrub_brief(brief)

    # Step 2 — LLM model resolution. Resolve ONCE before agent
    # construction so the error path surfaces a typed missing-env
    # failure rather than a deep RuntimeError inside BaseAgent.
    resolved_model = model if model is not None else get_default_llm_model()

    logger.debug(
        "signature_from_brief: invoking LLM (model=%s, brief_len=%d)",
        resolved_model,
        len(scrubbed),
    )

    # Step 3 — invoke the meta-Signature. The lazy import of
    # BaseAgent avoids a circular import on package load (BaseAgent
    # imports from kaizen.signatures, and this module IS
    # kaizen.signatures.from_brief).
    from kaizen.core.base_agent import BaseAgent

    agent = BaseAgent(
        config={"model": resolved_model, "temperature": 0},
        signature=SignaturePlanSignature(),
    )
    raw_output = agent.run(brief=scrubbed)

    # Step 4 — typed plan coercion. Translates Pydantic
    # ValidationError into BriefInterpretationError(malformed=True).
    plan = coerce_plan(raw_output, SignaturePlan)

    # Step 5 — confidence gate (raises on miss).
    check_confidence(plan.interpretation_confidence, threshold=confidence_threshold)

    # Step 6 — structural + identifier validation.
    _validate_class_name(plan.class_name)

    # Step 7 — field-type allowlist gate. Run per-type so the
    # unknown_value discriminator on the raised exception names the
    # offending type string.
    for type_str in plan.field_types:
        validate_field_type(type_str, ALLOWED_FIELD_TYPES)

    # Step 8 — realize. The metaclass-mediated construction is the
    # ONLY place the synthesized class comes into existence; the
    # validator gates above ensure the realizer cannot fail.
    return _realize_signature(plan)
