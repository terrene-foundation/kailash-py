# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Private LLM-mediation primitives for ``from_brief()`` surfaces.

This module is **private** by convention (leading underscore) — its
helpers are consumed exclusively by the public ``from_brief()``
methods on framework primitives (Sg-Workflow, Sg-Signature, Sg-Agent,
Sg-Pipeline, Sg-Coordination). External callers MUST NOT depend on
these symbols; they are an implementation surface, not a public API.

The pipeline every ``from_brief()`` primitive composes::

    brief (prose)
      → scrub_brief()                       # credential scrub
      → BriefPlanSignature subclass         # LLM emits typed plan
      → validate_plan()                     # confidence + allowlist gates
      → deterministic realization           # permitted structural plumbing
      → framework primitive

Origin: issue #1125 — the documented "natural-language to running
workflow" pipeline cannot complete unless every primitive routes
through the same validation discipline. This module IS that
discipline.
"""

from __future__ import annotations

from kailash._from_brief.allowlist import (
    validate_config_value,
    validate_field_type,
    validate_node_type,
)
from kailash._from_brief.branching import (
    ConnectionSpec,
    realize_connection,
    realize_connections,
)
from kailash._from_brief.confidence import (
    DEFAULT_CONFIDENCE_THRESHOLD,
    check_confidence,
)
from kailash._from_brief.exceptions import BriefInterpretationError
from kailash._from_brief.scrubber import scrub_brief
from kailash._from_brief.signatures import (
    BriefPlanSignature,
    MissingDefaultLLMModelError,
    get_default_llm_model,
)
from kailash._from_brief.validator import BriefPlan, coerce_plan, validate_plan

__all__ = [
    # Exceptions
    "BriefInterpretationError",
    "MissingDefaultLLMModelError",
    # Scrubbing
    "scrub_brief",
    # Validation
    "BriefPlan",
    "validate_plan",
    "coerce_plan",
    # Allowlists
    "validate_node_type",
    "validate_field_type",
    "validate_config_value",
    # Confidence
    "DEFAULT_CONFIDENCE_THRESHOLD",
    "check_confidence",
    # Realization
    "ConnectionSpec",
    "realize_connection",
    "realize_connections",
    # Signature base
    "BriefPlanSignature",
    "get_default_llm_model",
]
