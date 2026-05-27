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

from typing import TYPE_CHECKING, Any

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
from kailash._from_brief.validator import BriefPlan, coerce_plan, validate_plan

# ---------------------------------------------------------------------------
# Lazy signatures exports — kaizen is a downstream package (kailash-kaizen).
#
# ``signatures.py:33`` does ``from kaizen.signatures import ...`` at module
# scope, so eager-importing the three signatures exports below into THIS
# package's __init__ would make ``import kailash._from_brief`` require kaizen
# to be installed. kaizen is a SEPARATE package that depends on kailash core;
# core MUST NOT import it at module scope (``rules/dependencies.md`` § "Declared
# = Imported"; ``rules/framework-first.md`` layering). In CI only the package
# under test has its deps installed, so kaizen is absent in Base / DataFlow /
# kailash-ml jobs, and an eager chain into ``signatures.py`` breaks collection.
#
# The kaizen-free helpers above (exceptions, scrubber, validator, allowlist,
# confidence, branching) stay EAGER — they carry no kaizen dependency, and a
# caller doing ``from kailash._from_brief import BriefInterpretationError``
# (the DataFlow conftest path) MUST keep working without kaizen.
#
# The three kaizen-tainted exports (BriefPlanSignature, get_default_llm_model,
# MissingDefaultLLMModelError) are lazy-loaded via PEP 562 ``__getattr__``
# below. A caller asking for any of the three IS in a from_brief execution
# path where kaizen is present, so resolving ``signatures.py`` (and thus
# kaizen) at attribute-access time is acceptable. The KEY win is that mere
# IMPORT of ``kailash._from_brief`` no longer triggers the kaizen import.
#
# The TYPE_CHECKING block keeps the three symbols resolvable for static
# analyzers (pyright / mypy --strict / CodeQL py/undefined-export) even though
# they have no module-scope runtime binding, per ``rules/orphan-detection.md``
# § 6b (same reconciliation pattern as the lazy WorkflowPlanSignature in
# ``kailash/workflow/from_brief.py``).
# ---------------------------------------------------------------------------

if TYPE_CHECKING:
    from kailash._from_brief.signatures import (  # noqa: F401
        BriefPlanSignature,
        MissingDefaultLLMModelError,
        get_default_llm_model,
    )

_LAZY_SIGNATURE_EXPORTS = frozenset(
    {"BriefPlanSignature", "MissingDefaultLLMModelError", "get_default_llm_model"}
)


def __getattr__(name: str) -> Any:
    """PEP 562 lazy resolver for the kaizen-dependent signatures exports.

    Defers the ``kailash._from_brief.signatures`` import (which pulls in
    ``kaizen.signatures`` at its module scope) to first attribute access, so
    ``import kailash._from_brief`` succeeds without kaizen installed. The three
    names in :data:`_LAZY_SIGNATURE_EXPORTS` are the kaizen-tainted surface;
    everything else raises ``AttributeError`` per the standard PEP 562 contract.
    """
    if name in _LAZY_SIGNATURE_EXPORTS:
        from kailash._from_brief import signatures

        return getattr(signatures, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


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
