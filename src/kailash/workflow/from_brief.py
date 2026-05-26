# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""``Workflow.from_brief()`` — the workflow surface of the family.

Closes issue #1125 AC 1 + AC 6: the documented call
``kailash.Workflow.from_brief(brief)`` raised ``AttributeError`` today;
this module promotes the documented contract to executable behavior.

The pipeline composes the foundation laid by :mod:`kailash._from_brief`::

    brief (prose)
      → scrub_brief()                # credential scrub (S1)
      → WorkflowPlanSignature        # LLM emits typed plan
      → coerce_plan / validate_plan  # typed + confidence + allowlist (S1)
      → WorkflowBuilder loop         # deterministic structural plumbing
      → WorkflowBuilder (returned)

Per ``rules/agent-reasoning.md`` MUST Rule 1, the LLM does ALL reasoning
about which nodes to add, how to configure them, and how to connect
them. The realizer is permitted deterministic logic (per the rule's
§ "Permitted Deterministic Logic" exception 6 — tool result parsing /
structural plumbing) — it does NOT decide what the agent should think,
only how a validated plan maps to the framework's API.

Per ``rules/env-models.md``, the LLM model is read from
``DEFAULT_LLM_MODEL`` in the environment; the helper raises
:class:`~kailash._from_brief.signatures.MissingDefaultLLMModelError`
when unset.

Per ``rules/orphan-detection.md`` MUST Rule 1, this module is the
production call site for the S1 ``_from_brief`` primitives: every
S1 gate (scrub, validate, allowlist, confidence, realize) is invoked
from :func:`workflow_from_brief` on the hot path.

**Import-time circularity note.** All Kaizen imports are LAZY (deferred
to call-time inside the helpers below) because ``kaizen.__init__`` chains
into ``kailash.trust.posture`` which reads ``kailash.__version__``;
``kailash.__init__`` imports ``kailash.workflow`` BEFORE ``__version__``
is bound on line 98, so any top-level kaizen import in this module would
trigger a circular-import ``ImportError`` at package load time. The
``WorkflowPlanSignature`` class is therefore also lazy — accessed via
:func:`_signature_cls`, NOT defined at module scope.

Architecture context: ``workspaces/from-brief-1125/02-plans/01-architecture.md``
§ 3.1 names this surface as Sg-Workflow. Sibling shards land
Sg-Pipeline (S3, kailash-dataflow) and Sg-Agent (S4, kaizen).

Origin: issue #1125 — the brief asserts (AC 1) that
``wf.build().execute()`` runs end-to-end on the synthesized graph;
this is the executable surface that converts that claim from
"aspirational" to "shipped". User-anchored value source (a):
the issue body.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Set

if TYPE_CHECKING:
    from kailash._from_brief.branching import ConnectionSpec  # noqa: F401
    from kailash._from_brief.validator import BriefPlan  # noqa: F401
    from kailash.workflow.builder import WorkflowBuilder

__all__ = [
    "WorkflowPlan",
    "WorkflowPlanSignature",
    "workflow_from_brief",
]

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Plan model (Pydantic — typed validation gate, S1 foundation)                #
# --------------------------------------------------------------------------- #
#
# WorkflowPlan extends `BriefPlan` from `kailash._from_brief.validator`.
# Importing the validator submodule triggers `kailash._from_brief.__init__`
# which eagerly loads `signatures.py` → `kaizen.signatures` → `kaizen.core`
# → `kailash.trust.posture` → `kailash.__version__` (BOOM: circular at
# package-load time before kailash/__init__.py:98 binds __version__).
#
# The class is therefore built LAZILY via `_workflow_plan_cls()` and exposed
# at module scope through `__getattr__` (PEP 562). Same fence pattern as
# the signature class below — see module docstring for the full failure
# mode rationale.


_WORKFLOW_PLAN_CLS_CACHE: Optional[type] = None


def _workflow_plan_cls() -> type:
    """Return the :class:`WorkflowPlan` class, constructed lazily.

    Defers the ``kailash._from_brief.__init__`` chain to call time so
    the kailash package can finish initialising (binding ``__version__``)
    before the kaizen transitive dependency lands.

    Returns:
        The lazily-constructed :class:`WorkflowPlan` subclass, cached
        after first invocation.
    """
    global _WORKFLOW_PLAN_CLS_CACHE
    if _WORKFLOW_PLAN_CLS_CACHE is not None:
        return _WORKFLOW_PLAN_CLS_CACHE

    from kailash._from_brief.validator import BriefPlan

    class WorkflowPlan(BriefPlan):
        """The LLM-emitted workflow plan.

        Extends :class:`~kailash._from_brief.validator.BriefPlan` with
        the two workflow-specific fields :func:`workflow_from_brief`
        consumes:

        - ``nodes`` — an ordered list of node specs. Each spec is a
          dict with ``node_type`` (str — MUST be a registered node
          type), ``node_id`` (str — unique identifier within the plan),
          and ``config`` (dict — node parameters; may be empty).
        - ``connections`` — a list of edges between nodes. Each spec is
          a dict with ``source_node``, ``target_node``, and optional
          ``source_output`` (defaults to ``"result"``) and
          ``target_input`` (defaults to ``"input"``). Branching is
          expressed as multiple connection entries sharing
          ``source_node``.

        Pydantic's ``extra="forbid"`` (inherited from
        :class:`BriefPlan`) rejects any field the LLM hallucinates
        outside this schema. The allowlist gate downstream of
        construction additionally rejects any ``node_type`` not
        registered in :class:`kailash.nodes.base.NodeRegistry`.
        """

        nodes: List[Dict[str, Any]]
        connections: List[Dict[str, Any]]

    _WORKFLOW_PLAN_CLS_CACHE = WorkflowPlan
    return WorkflowPlan


# --------------------------------------------------------------------------- #
# Lazy Signature class (defers kaizen import past kailash.__version__ bind)   #
# --------------------------------------------------------------------------- #


_SIGNATURE_CLS_CACHE: Optional[type] = None


def _signature_cls() -> type:
    """Return the WorkflowPlanSignature class, constructed lazily.

    The class is built on first access (NOT at module import) because
    ``kaizen.signatures`` triggers ``kaizen.__init__`` which imports
    ``kailash.trust.posture`` which reads ``kailash.__version__`` —
    creating a circular import if invoked during ``kailash.workflow``
    package load (kailash's ``__init__.py`` imports workflow BEFORE
    binding ``__version__``). The lazy access pattern defers kaizen
    import to call-time, when ``kailash`` is fully initialized.

    Returns:
        The :class:`WorkflowPlanSignature` class, cached after first
        construction.
    """
    global _SIGNATURE_CLS_CACHE
    if _SIGNATURE_CLS_CACHE is not None:
        return _SIGNATURE_CLS_CACHE

    from kaizen.signatures import OutputField  # type: ignore[import-not-found]

    from kailash._from_brief.signatures import BriefPlanSignature

    class WorkflowPlanSignature(BriefPlanSignature):
        """Kaizen Signature for Sg-Workflow plan emission.

        Inherits the floor contract from :class:`BriefPlanSignature`
        (``brief: str`` input + ``interpretation_confidence: float``
        output). Adds the two workflow-specific OutputFields the LLM
        is asked to emit:

        - ``nodes`` — ordered list of node specs (see
          :class:`WorkflowPlan`).
        - ``connections`` — list of edge specs (see
          :class:`WorkflowPlan`).

        Per ``rules/agent-reasoning.md`` MUST Rule 3, the Signature
        DESCRIBES the reasoning the LLM is to perform; Python does
        not pre-classify the brief or filter its content.
        """

        # Pyright suppressions cite the Kaizen-wide ``reportAssignmentType``
        # pattern documented at ``_from_brief/signatures.py:110-138``.
        nodes: list = OutputField(  # pyright: ignore[reportAssignmentType]
            description=(
                "Ordered list of node specs that realize the user's "
                "intent. Each entry MUST be a dict with these keys: "
                "'node_type' (str — the registered Kailash node type "
                "name, e.g. 'CSVReaderNode', 'PythonCodeNode', "
                "'MergeNode'); 'node_id' (str — a unique identifier "
                "within this plan, e.g. 'reader', 'transform_1'); "
                "'config' (dict — parameters for the node, may be "
                "empty {}). Use ONLY node types from the allowed list "
                "provided in the brief context. If unsure, lower "
                "interpretation_confidence."
            )
        )
        connections: list = OutputField(  # pyright: ignore[reportAssignmentType]
            description=(
                "List of edges between nodes describing data flow. "
                "Each entry MUST be a dict with these keys: "
                "'source_node' (str — node_id of the source); "
                "'target_node' (str — node_id of the target); and "
                "OPTIONALLY 'source_output' (str, defaults to "
                "'result') and 'target_input' (str, defaults to "
                "'input'). For branching (one node fans out to many), "
                "emit multiple entries sharing the same source_node. "
                "May be an empty list [] if the plan has only one node."
            )
        )

    _SIGNATURE_CLS_CACHE = WorkflowPlanSignature
    return WorkflowPlanSignature


def __getattr__(name: str) -> Any:
    """PEP 562 module-level ``__getattr__`` for lazy class resolution.

    Per `rules/orphan-detection.md` § 6b, lazy-loaded symbols MUST stay
    discoverable through the module's public surface. This hook resolves
    ``from kailash.workflow.from_brief import WorkflowPlanSignature``
    and ``WorkflowPlan`` at call-time (the symbols are in ``__all__``,
    have lazy resolvers, and have ``TYPE_CHECKING`` entries below).
    """
    if name == "WorkflowPlanSignature":
        return _signature_cls()
    if name == "WorkflowPlan":
        return _workflow_plan_cls()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


if TYPE_CHECKING:
    # Surface lazy classes to static analyzers (CodeQL py/undefined-export,
    # pyright, mypy) per `rules/orphan-detection.md` § 6b. Runtime bodies
    # live inside `_signature_cls` / `_workflow_plan_cls`.
    class WorkflowPlanSignature:  # type: ignore[no-redef]
        """Static-analyzer stub; runtime body in :func:`_signature_cls`."""

        nodes: list
        connections: list

    class WorkflowPlan:  # type: ignore[no-redef]
        """Static-analyzer stub; runtime body in :func:`_workflow_plan_cls`."""

        nodes: List[Dict[str, Any]]
        connections: List[Dict[str, Any]]
        interpretation_confidence: float


# --------------------------------------------------------------------------- #
# Allowlist derivation                                                        #
# --------------------------------------------------------------------------- #


def _registered_node_types() -> Set[str]:
    """Return the set of registered Kailash node type names.

    Reads :meth:`kailash.nodes.base.NodeRegistry.list_nodes` at call
    time so newly-registered node types are visible without a process
    restart. This is the allowlist :func:`workflow_from_brief` passes
    to :func:`validate_plan` per ``rules/agent-reasoning.md`` Rule 1
    (the LLM may freely propose node types; the allowlist gate is the
    structural check that rejects hallucinations).

    Returns:
        A set of node type names registered at import time.
    """
    # Warm the common node-type submodules so the registry is populated
    # against the canonical Kailash node surface (data, logic, transform,
    # code, AI). Wrapped in try/except per `rules/dependencies.md` —
    # except branch is bounded to ImportError so non-import errors
    # propagate loudly (NOT the silent-fallback anti-pattern).
    try:
        import kailash.nodes.data  # noqa: F401
    except ImportError:
        pass
    try:
        import kailash.nodes.transform  # noqa: F401
    except ImportError:
        pass
    try:
        import kailash.nodes.logic  # noqa: F401
    except ImportError:
        pass
    try:
        import kailash.nodes.code  # noqa: F401
    except ImportError:
        pass
    # Note: `kailash.nodes.ai` is intentionally NOT warmed here — that
    # submodule does not exist in the current SDK layout (verified via
    # `ls src/kailash/nodes/ai`). Adding the import would create a static
    # analyzer warning (pyright reportMissingImports). The allowlist still
    # picks up any AI nodes registered through other warmed submodules.

    from kailash.nodes.base import NodeRegistry

    return set(NodeRegistry.list_nodes().keys())


# --------------------------------------------------------------------------- #
# Agent factory                                                               #
# --------------------------------------------------------------------------- #


def _build_agent(model: str, signature: Any) -> Any:
    """Construct the Kaizen BaseAgent that emits the workflow plan.

    Per ``rules/framework-first.md`` § Kaizen, agents are Kaizen
    primitives (BaseAgent + Signature). The agent is constructed with
    a structured-output ``response_format`` derived from the signature
    so the LLM returns schema-conformant JSON the validator can coerce
    without regex post-processing (per
    ``rules/probe-driven-verification.md`` MUST Rule 2 — every probe
    has an expected-answer schema; the validator IS that schema).

    Args:
        model: The LLM model name from ``DEFAULT_LLM_MODEL`` per
            ``rules/env-models.md``.
        signature: The signature instance the agent runs against.

    Returns:
        A constructed :class:`~kaizen.core.base_agent.BaseAgent`.
    """
    from kaizen.core.base_agent import BaseAgent  # type: ignore[import-not-found]
    from kaizen.core.config import BaseAgentConfig  # type: ignore[import-not-found]
    from kaizen.core.structured_output import (  # type: ignore[import-not-found]
        create_structured_output_config,
    )

    # Provider inference from the model string prefix (structural plumbing,
    # NOT a decision on user input content — `rules/agent-reasoning.md`
    # § "Permitted Deterministic Logic" exception 6).
    provider = "openai"
    lower = model.lower()
    if lower.startswith("claude"):
        provider = "anthropic"
    elif lower.startswith("gemini"):
        provider = "google"
    elif lower.startswith("deepseek"):
        provider = "deepseek"
    elif lower.startswith(("mistral", "mixtral")):
        provider = "mistral"

    response_format = create_structured_output_config(signature, strict=False)
    config = BaseAgentConfig(
        llm_provider=provider,
        model=model,
        temperature=0.1,
        response_format=response_format,
        structured_output_mode="explicit",
    )
    return BaseAgent(config=config, signature=signature)


# --------------------------------------------------------------------------- #
# Realizer (deterministic plumbing — permitted per agent-reasoning § 6)        #
# --------------------------------------------------------------------------- #


def _coerce_node_spec(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize one LLM-emitted node spec.

    Pydantic validated the plan's outer shape; this helper checks the
    per-entry fields the realizer relies on. Missing required fields
    raise :class:`~kailash._from_brief.exceptions.BriefInterpretationError`
    with ``malformed=True`` per S1's typed exception contract.

    Args:
        raw: A single node spec from ``plan.nodes``.

    Returns:
        A dict with keys ``node_type`` (str), ``node_id`` (str),
        and ``config`` (dict — may be empty).

    Raises:
        BriefInterpretationError: When required fields are missing
            or have the wrong type.
    """
    from kailash._from_brief.exceptions import BriefInterpretationError

    if not isinstance(raw, dict):
        raise BriefInterpretationError(
            f"node spec must be a dict, got {type(raw).__name__}",
            malformed=True,
        )
    node_type = raw.get("node_type")
    node_id = raw.get("node_id")
    config = raw.get("config", {})
    if not isinstance(node_type, str) or not node_type:
        raise BriefInterpretationError(
            f"node spec missing 'node_type' string: {raw!r}",
            malformed=True,
        )
    if not isinstance(node_id, str) or not node_id:
        raise BriefInterpretationError(
            f"node spec missing 'node_id' string: {raw!r}",
            malformed=True,
        )
    if not isinstance(config, dict):
        raise BriefInterpretationError(
            f"node spec 'config' must be a dict, got "
            f"{type(config).__name__}: {raw!r}",
            malformed=True,
        )
    return {"node_type": node_type, "node_id": node_id, "config": config}


def _coerce_connection_spec(raw: Dict[str, Any]) -> "ConnectionSpec":
    """Normalize one LLM-emitted connection spec into a ConnectionSpec.

    Mirrors :func:`_coerce_node_spec` but produces a
    :class:`~kailash._from_brief.branching.ConnectionSpec` the S1
    realizer consumes. Defaults match the framework's most common port
    names (``result`` → ``input``).

    Args:
        raw: A single connection spec from ``plan.connections``.

    Returns:
        A :class:`ConnectionSpec` instance.

    Raises:
        BriefInterpretationError: When required fields are missing
            or have the wrong type.
    """
    from kailash._from_brief.branching import ConnectionSpec
    from kailash._from_brief.exceptions import BriefInterpretationError

    if not isinstance(raw, dict):
        raise BriefInterpretationError(
            f"connection spec must be a dict, got {type(raw).__name__}",
            malformed=True,
        )
    source_node = raw.get("source_node")
    target_node = raw.get("target_node")
    if not isinstance(source_node, str) or not source_node:
        raise BriefInterpretationError(
            f"connection spec missing 'source_node' string: {raw!r}",
            malformed=True,
        )
    if not isinstance(target_node, str) or not target_node:
        raise BriefInterpretationError(
            f"connection spec missing 'target_node' string: {raw!r}",
            malformed=True,
        )
    source_output = raw.get("source_output", "result")
    target_input = raw.get("target_input", "input")
    if not isinstance(source_output, str):
        source_output = "result"
    if not isinstance(target_input, str):
        target_input = "input"
    return ConnectionSpec(
        source_node=source_node,
        target_node=target_node,
        source_output=source_output,
        target_input=target_input,
    )


def _realize(plan: Any) -> "WorkflowBuilder":
    """Realize a validated workflow plan into a WorkflowBuilder.

    Pure structural plumbing per ``rules/agent-reasoning.md`` §
    "Permitted Deterministic Logic" (exception 6, tool-result parsing).
    The function does NOT inspect brief CONTENT — it only iterates the
    LLM-validated plan and calls the framework's builder API.

    Args:
        plan: A :class:`WorkflowPlan` already validated by
            :func:`validate_plan` (typed + confidence + allowlist).

    Returns:
        A :class:`~kailash.workflow.builder.WorkflowBuilder` populated
        with the plan's nodes and connections.

    Raises:
        BriefInterpretationError: When a node spec or connection spec
            is structurally malformed.
    """
    from kailash._from_brief.branching import realize_connections
    from kailash._from_brief.exceptions import BriefInterpretationError
    from kailash.workflow.builder import WorkflowBuilder

    builder = WorkflowBuilder()
    seen_ids: Set[str] = set()
    for raw_node in plan.nodes:
        spec = _coerce_node_spec(raw_node)
        if spec["node_id"] in seen_ids:
            raise BriefInterpretationError(
                f"plan contains duplicate node_id: {spec['node_id']!r}",
                malformed=True,
            )
        seen_ids.add(spec["node_id"])
        builder.add_node(spec["node_type"], spec["node_id"], spec["config"])

    conn_specs = [_coerce_connection_spec(c) for c in plan.connections]
    realize_connections(builder, conn_specs)
    return builder


# --------------------------------------------------------------------------- #
# Public entrypoint                                                           #
# --------------------------------------------------------------------------- #


def workflow_from_brief(
    brief: str,
    *,
    model: Optional[str] = None,
    confidence_threshold: float = 0.6,
    allowed_node_types: Optional[Set[str]] = None,
) -> "WorkflowBuilder":
    """Realize a natural-language brief into a :class:`WorkflowBuilder`.

    This function is the workflow surface of the ``from_brief()``
    family (issue #1125 AC 1). It composes the full S1 pipeline:

    1. **Credential scrub** — :func:`scrub_brief` strips embedded
       credentials before the LLM sees the brief.
    2. **LLM plan emission** — a Kaizen agent runs
       :class:`WorkflowPlanSignature` against the configured model.
    3. **Typed validation** — :func:`coerce_plan` enforces the
       :class:`WorkflowPlan` shape; :func:`validate_plan` enforces
       the confidence floor and the node-type allowlist.
    4. **Realization** — :func:`_realize` iterates the validated plan
       and builds the :class:`WorkflowBuilder`.

    Args:
        brief: A natural-language description of the workflow.
            Credentials in the brief are scrubbed before any logging
            or LLM call.
        model: Optional LLM model name override. When ``None``,
            reads ``DEFAULT_LLM_MODEL`` from the environment per
            ``rules/env-models.md``.
        confidence_threshold: Minimum
            ``interpretation_confidence`` the LLM must emit. Defaults
            to 0.6 per S1's :data:`DEFAULT_CONFIDENCE_THRESHOLD`.
        allowed_node_types: Optional override of the node-type
            allowlist. When ``None``, derived from
            :meth:`NodeRegistry.list_nodes` so only registered Kailash
            nodes pass the allowlist gate.

    Returns:
        A :class:`~kailash.workflow.builder.WorkflowBuilder` whose
        ``.build()`` produces a :class:`Workflow` ready for
        ``runtime.execute(workflow.build())``.

    Raises:
        MissingDefaultLLMModelError: When ``DEFAULT_LLM_MODEL`` is
            unset and no ``model`` override was provided.
        BriefInterpretationError: When the LLM emits a plan with
            ``interpretation_confidence`` below the threshold
            (``low_confidence=True``), with a node type not in the
            allowlist (``unknown_value="<name>"``), or with a
            structurally malformed plan (``malformed=True``).
    """
    # Lazy imports — all `_from_brief` submodules load via
    # `kailash._from_brief.__init__` which transitively imports kaizen
    # (see module docstring). Deferring to call-time fences the circular
    # load against the kailash package-init order.
    from kailash._from_brief.scrubber import scrub_brief
    from kailash._from_brief.signatures import get_default_llm_model
    from kailash._from_brief.validator import coerce_plan, validate_plan

    # Step 1 — credential scrub (pre-LLM, pre-logging).
    scrubbed = scrub_brief(brief)
    logger.info(
        "workflow_from_brief.start",
        extra={"brief_length": len(scrubbed)},
    )

    # Step 2 — derive model + allowlist.
    resolved_model = model if model is not None else get_default_llm_model()
    if allowed_node_types is None:
        allowed_node_types = _registered_node_types()

    # Step 3 — augment the brief with the allowlist so the LLM has the
    # full vocabulary inline. The agent runs against a structured-output
    # response_format derived from the signature, so the LLM is forced
    # to emit JSON matching WorkflowPlanSignature's shape. Listing the
    # allowed node types in the brief lowers the rate of
    # unknown_value-class refusals downstream.
    allowed_list = ", ".join(sorted(allowed_node_types))
    augmented_brief = (
        f"{scrubbed}\n\n"
        f"AVAILABLE NODE TYPES (use ONLY these):\n{allowed_list}\n\n"
        f"If you cannot map the user's intent to these node types, "
        f"emit an empty nodes list and set interpretation_confidence "
        f"below {confidence_threshold}."
    )

    # Step 4 — LLM plan emission.
    signature = _signature_cls()()
    agent = _build_agent(resolved_model, signature)
    raw = agent.run(brief=augmented_brief)
    logger.info(
        "workflow_from_brief.llm_returned",
        extra={"raw_keys": sorted(raw.keys()) if isinstance(raw, dict) else []},
    )

    # Step 5 — typed validation. coerce_plan wraps pydantic.ValidationError
    # in BriefInterpretationError(malformed=True). The runtime type is the
    # lazy WorkflowPlan subclass (extra fields `nodes` + `connections`);
    # pyright sees the BriefPlan static return. The Any cast below tells
    # pyright the dynamic shape is intentional — `_realize` accepts Any
    # for the same reason and consumes the extra fields safely.
    plan: Any = coerce_plan(raw, _workflow_plan_cls())
    validate_plan(
        plan,
        allowed_node_types=allowed_node_types,
        confidence_threshold=confidence_threshold,
    )

    # Step 6 — realize into a WorkflowBuilder.
    builder = _realize(plan)
    logger.info(
        "workflow_from_brief.ok",
        extra={
            "node_count": len(plan.nodes),
            "connection_count": len(plan.connections),
            "confidence": plan.interpretation_confidence,
        },
    )
    return builder
