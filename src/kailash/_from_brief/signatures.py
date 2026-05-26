# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Kaizen Signature base class for the ``from_brief()`` pipeline.

Every ``from_brief()`` primitive composes a Kaizen Signature that
emits a typed plan from a natural-language brief. The base class here
declares the two fields every primitive's Signature MUST share:

- ``brief: str`` — the user's natural-language intent (already
  credential-scrubbed by :func:`kailash._from_brief.scrubber.scrub_brief`
  BEFORE this Signature is invoked).
- ``interpretation_confidence: float`` — the LLM's self-rated 0.0-1.0
  confidence in the plan. The downstream
  :func:`kailash._from_brief.validator.validate_plan` gate consumes
  this field.

Each primitive's concrete Signature subclasses :class:`BriefPlanSignature`
and adds plan-specific OutputFields. Per
``rules/agent-reasoning.md`` MUST Rule 3 ("Signatures describe, code
doesn't decide"), the subclass MUST describe the reasoning the LLM is
to perform — not pre-filter the brief in Python before the LLM sees it.

Origin: issue #1125 — every primitive (Sg-Workflow, Sg-Signature,
Sg-Agent, Sg-Pipeline, Sg-Coordination) needs the same Signature
shell; centralizing the floor contract makes the LLM-mediation surface
auditable and uniform.
"""

from __future__ import annotations

import os

from kaizen.signatures import InputField, OutputField, Signature

__all__ = [
    "BriefPlanSignature",
    "get_default_llm_model",
    "MissingDefaultLLMModelError",
]


class MissingDefaultLLMModelError(RuntimeError):
    """Raised when ``DEFAULT_LLM_MODEL`` is not set in the environment.

    Per ``rules/env-models.md``, model names MUST come from ``.env`` —
    NEVER hardcoded. This exception surfaces the missing-env state as
    a loud, typed failure at the helper boundary rather than a deep
    ``KeyError`` inside the Signature dispatch.
    """


def get_default_llm_model() -> str:
    """Return the default LLM model name from the environment.

    Reads ``DEFAULT_LLM_MODEL`` from :func:`os.environ`. The root
    ``conftest.py`` auto-loads ``.env`` for pytest, so this helper
    works in both test and production contexts.

    Per ``rules/env-models.md`` § "NEVER Hardcode Model Names", a
    missing model name is a configuration error — NOT a default the
    helper should silently invent. This function raises
    :class:`MissingDefaultLLMModelError` rather than returning a
    fallback string.

    Returns:
        The model name string from the environment.

    Raises:
        MissingDefaultLLMModelError: When ``DEFAULT_LLM_MODEL`` is
            unset or empty.
    """
    model = os.environ.get("DEFAULT_LLM_MODEL", "").strip()
    if not model:
        raise MissingDefaultLLMModelError(
            "DEFAULT_LLM_MODEL is unset; per rules/env-models.md the "
            "model name MUST come from .env. Add a DEFAULT_LLM_MODEL "
            "entry (e.g. via the OPENAI_PROD_MODEL setting) before "
            "invoking a from_brief() primitive."
        )
    return model


class BriefPlanSignature(Signature):
    """Base Signature for ``from_brief()`` plan emission.

    Every concrete primitive (Sg-Workflow, Sg-Signature, Sg-Agent,
    Sg-Pipeline, Sg-Coordination) subclasses this Signature to add
    its plan-specific OutputFields. The two floor fields below are
    inherited unchanged so the validation pipeline can rely on them.

    Example subclass shape::

        class WorkflowPlanSignature(BriefPlanSignature):
            \"\"\"Parse a natural-language brief into a workflow plan.\"\"\"

            nodes: list = OutputField(
                description="List of node specs (each with node_type, "
                "node_id, config)."
            )
            connections: list = OutputField(
                description="List of connection specs (each with "
                "source_node, target_node, source_output, target_input)."
            )

    The ``brief`` InputField is what the orchestrator passes into the
    Signature; ``interpretation_confidence`` is what the LLM emits
    alongside the plan-specific fields the subclass adds.
    """

    brief: str = InputField(
        description=(
            "Natural-language intent describing the primitive to "
            "realize. Already credential-scrubbed."
        )
    )
    interpretation_confidence: float = OutputField(
        description=(
            "Your self-rated 0.0-1.0 confidence that the emitted plan "
            "faithfully captures the user's intent. 1.0 means the "
            "plan is a precise translation; below 0.6 the realizer "
            "will refuse to proceed. Calibrate honestly."
        )
    )
