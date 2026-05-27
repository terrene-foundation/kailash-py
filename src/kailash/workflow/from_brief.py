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
      → coerce_plan / validate_plan  # schema + confidence + allowlist (S1)
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


# --------------------------------------------------------------------------- #
# Node-type security model — DEFAULT-DENY positive allowlist (issue #1125 R2)  #
# --------------------------------------------------------------------------- #
#
# The brief is UNTRUSTED input. `from_brief` realizes whatever node types the
# LLM emits, so the node-type surface IS a code-execution boundary. The prior
# model — "all registered nodes MINUS a denylist of code-exec nodes" — was
# proven unsound (R2 2026-05-27): the dangerous set cannot be reliably
# enumerated (e.g. PythonCodeNode execs via the CodeExecutor helper, invisible
# to a class-scope scan; DataTransformer/Convergence nodes exec/eval config),
# and every new code-running node added to the SDK would silently re-open the
# bypass.
#
# `_SAFE_NODE_TYPES` inverts to DEFAULT-DENY (positive allowlist per
# `rules/cc-artifacts.md` Rule 10): `from_brief` realizes ONLY these explicitly
# vetted node types — data I/O, declarative transform/filter/sort, flow
# control, DB/vector/streaming connectors — every one verified to take
# DECLARATIVE config (field/operator/path), never config-supplied code or
# expressions. A new SDK node is NOT brief-reachable until a human adds it here
# AFTER review. The `tests/.../test_from_brief_safe_allowlist.py` inverse-
# completeness test asserts no member is code-exec-capable, so a future
# mis-curation is caught mechanically.
#
# Excluded by design (code execution or composition bypass): PythonCodeNode,
# AsyncPythonCodeNode (exec), DataTransformer (exec config transformations),
# ConvergenceCheckerNode, MultiCriteriaConvergenceNode (eval config
# expression), WorkflowNode (nests an arbitrary sub-workflow that could embed
# any of the above).
_SAFE_NODE_TYPES: frozenset[str] = frozenset(
    {
        # Data readers / sources
        "CSVReaderNode",
        "JSONReaderNode",
        "TextReaderNode",
        "DocumentProcessorNode",
        "DocumentSourceNode",
        "DirectoryReaderNode",
        "FileDiscoveryNode",
        "QuerySourceNode",
        # Data writers
        "CSVWriterNode",
        "JSONWriterNode",
        "TextWriterNode",
        # Declarative transforms (no config-code; field/operator/path config)
        "FilterNode",
        "Map",
        "Sort",
        "ChunkTextExtractorNode",
        "ContextFormatterNode",
        "ContextualCompressorNode",
        "QueryTextWrapperNode",
        "HierarchicalChunkerNode",
        "SemanticChunkerNode",
        "StatisticalChunkerNode",
        "TextSplitterNode",
        # Flow control
        "MergeNode",
        "AsyncMergeNode",
        "SwitchNode",
        "AsyncSwitchNode",
        "SignalWaitNode",
        # Database / cache / routing
        "SQLDatabaseNode",
        "AsyncSQLDatabaseNode",
        "RedisNode",
        "QueryRouterNode",
        "OptimisticLockingNode",
        "WorkflowConnectionPool",
        # Vector / retrieval
        "EmbeddingNode",
        "VectorDatabaseNode",
        "AsyncPostgreSQLVectorNode",
        "HybridRetrieverNode",
        "RelevanceScorerNode",
        # Streaming / events
        "EventGeneratorNode",
        "EventStreamNode",
        "KafkaConsumerNode",
        "StreamPublisherNode",
        "WebSocketNode",
        # NOTE: SharePoint connectors (SharePointGraphReader/Writer) are
        # EXCLUDED — `SharePointGraphReader` routes a config `device_code_callback`
        # string to `importlib.import_module(...) + getattr + call` (a dynamic-
        # import code-exec vector, #1125 R4 MEDIUM); the Writer shares that
        # device-code-flow auth module. Both are denylisted below.
    }
)


# Defense-in-depth FLOOR (secondary to the positive allowlist above). With the
# default-deny allowlist, anything not in `_SAFE_NODE_TYPES` is already
# rejected; this denylist is an UNCONDITIONAL floor at the realizer + the
# caller-override path (`workflow_from_brief(allowed_node_types=...)`), so a
# caller that supplies a custom allowlist still cannot re-admit a known
# code-execution node. Enumerates the confirmed config-code-exec registered
# nodes across all submodules (not only those `from_brief` warms), because the
# NodeRegistry is process-global and these may be registered by other imports.
_DANGEROUS_NODE_TYPES: frozenset[str] = frozenset(
    {
        "PythonCodeNode",
        "AsyncPythonCodeNode",
        "DataTransformer",
        "ConvergenceCheckerNode",
        "MultiCriteriaConvergenceNode",
        "BatchProcessorNode",
        "CodeValidationNode",
        "WorkflowValidationNode",
        "ValidationTestSuiteExecutorNode",
        "WorkflowNode",
        # SharePoint connectors — dynamic-import code-exec vector via the
        # config `device_code_callback` → `importlib.import_module` path
        # (#1125 R4 MEDIUM); both share the device-code-flow auth module.
        "SharePointGraphReader",
        "SharePointGraphWriter",
    }
)

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

    from kailash._from_brief.signatures import BriefPlanSignature
    from kaizen.signatures import OutputField  # type: ignore[import-not-found]

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
                "name, e.g. 'CSVReaderNode', 'MergeNode', "
                "'FilterNode'); 'node_id' (str — a unique identifier "
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


def _safe_node_types() -> Set[str]:
    """Return the DEFAULT-DENY safe node-type allowlist for `from_brief`.

    Returns ``_SAFE_NODE_TYPES`` intersected with the nodes actually
    registered in :class:`kailash.nodes.base.NodeRegistry` at call time —
    so the allowlist never advertises a vetted node type whose submodule
    is not installed, and never admits a node type that is not on the
    explicit positive allowlist. This is the surface
    :func:`workflow_from_brief` passes to the realizer per
    ``rules/agent-reasoning.md`` Rule 1 (the LLM freely proposes node
    types; this allowlist is the structural gate that rejects both
    hallucinations AND any node type not vetted as safe).

    DEFAULT-DENY (issue #1125 R2): a node type the LLM emits is realized
    ONLY if it is BOTH registered AND in ``_SAFE_NODE_TYPES``. A new SDK
    node is excluded until a human adds it to ``_SAFE_NODE_TYPES`` after
    confirming it takes no config-supplied code (see the module-level
    rationale + the inverse-completeness test).

    Returns:
        The safe node-type names that are registered in this process.
    """
    # Warm the common node-type submodules so the registry is populated
    # against the canonical Kailash node surface (data, logic, transform,
    # code). These are core `pip install kailash` submodules — a genuine
    # ImportError here is a real breakage, NOT an expected-absent optional
    # dep, so it is surfaced at WARN (per `rules/observability.md` Rule 5 +
    # `rules/zero-tolerance.md` Rule 3) rather than silently swallowed. The
    # guard is retained (a missing submodule must not crash the allowlist
    # build) but the failure is now loud.
    # (`kailash.nodes.ai` is intentionally absent — that submodule does not
    # exist in the current SDK layout; warming it would raise a
    # static-analyzer reportMissingImports.)
    import importlib

    for _submodule in (
        "kailash.nodes.data",
        "kailash.nodes.transform",
        "kailash.nodes.logic",
        "kailash.nodes.code",
    ):
        try:
            importlib.import_module(_submodule)
        except ImportError as exc:
            logger.warning(
                "workflow_from_brief.registry_warm_failed",
                extra={"submodule": _submodule, "error": str(exc)},
            )

    from kailash.nodes.base import NodeRegistry

    # DEFAULT-DENY: intersect the vetted positive allowlist with what is
    # actually registered. Anything not in `_SAFE_NODE_TYPES` (including
    # every code-execution node and any new/unvetted SDK node) is excluded
    # by construction — there is no "all registered minus denylist" path
    # that a newly-added dangerous node could slip through.
    return set(_SAFE_NODE_TYPES) & set(NodeRegistry.list_nodes().keys())


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


def _realize(plan: Any, allowed_node_types: Set[str]) -> "WorkflowBuilder":
    """Realize a validated workflow plan into a WorkflowBuilder.

    Structural plumbing per ``rules/agent-reasoning.md`` § "Permitted
    Deterministic Logic" (exception 6, tool-result parsing) — it does NOT
    reason about brief CONTENT. It DOES enforce the node-type allowlist
    and the SEC-1 code-execution denylist at the realization choke point:
    ``validate_plan``'s top-level ``node_type`` gate is a structural no-op
    for :class:`WorkflowPlan` because the per-node types live inside
    ``plan.nodes[i]["node_type"]``, not at a top-level attribute. This
    loop is therefore the boundary where an LLM-emitted ``node_type``
    reaches ``builder.add_node``, so the allowlist + denylist MUST be
    enforced here. The denylist is re-applied UNCONDITIONALLY (independent
    of ``allowed_node_types``) so a caller-supplied allowlist cannot
    re-admit a code-execution node.

    Args:
        plan: A :class:`WorkflowPlan` already validated by
            :func:`validate_plan` (typed + confidence).
        allowed_node_types: The registered-node allowlist (with the SEC-1
            denylist already subtracted). Every realized ``node_type``
            MUST be a member; ``_DANGEROUS_NODE_TYPES`` is additionally
            enforced as an absolute floor regardless of this set.

    Returns:
        A :class:`~kailash.workflow.builder.WorkflowBuilder` populated
        with the plan's nodes and connections.

    Raises:
        BriefInterpretationError: When a node spec or connection spec is
            structurally malformed (``malformed=True``), or when a node
            type is denylisted / not in the allowlist (``unknown_value``).
    """
    from kailash._from_brief.allowlist import validate_node_type
    from kailash._from_brief.branching import realize_connections
    from kailash._from_brief.exceptions import BriefInterpretationError
    from kailash.workflow.builder import WorkflowBuilder

    builder = WorkflowBuilder()
    seen_ids: Set[str] = set()
    for raw_node in plan.nodes:
        spec = _coerce_node_spec(raw_node)
        # SEC-1 denylist floor — enforced FIRST and unconditionally, so a
        # custom allowed_node_types cannot re-admit a code-execution node
        # (MEDIUM-2). PythonCodeNode/AsyncPythonCodeNode call exec() on
        # LLM-emitted strings.
        if spec["node_type"] in _DANGEROUS_NODE_TYPES:
            raise BriefInterpretationError(
                f"node_type={spec['node_type']!r} is denylisted because it "
                f"executes arbitrary code (exec); a natural-language brief "
                f"cannot realize it regardless of the allowlist",
                unknown_value=spec["node_type"],
            )
        # Allowlist gate at the realization choke point — validate_plan's
        # top-level node_type gate does not reach plan.nodes[i]["node_type"]
        # (CRITICAL-1). Rejects hallucinated / prompt-injected node types.
        validate_node_type(spec["node_type"], allowed_node_types)
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
        allowed_node_types = _safe_node_types()
    else:
        # SEC-1: the denylist is a FLOOR, not a default. Subtract it even
        # from a caller-supplied allowlist so a custom set cannot re-admit
        # a code-execution node (MEDIUM-2). The realizer re-checks the
        # denylist unconditionally too (defense in depth).
        allowed_node_types = set(allowed_node_types) - _DANGEROUS_NODE_TYPES

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
    # SEC-6: per rules/observability.md Rule 8, schema-revealing field
    # names (the keys of the LLM-emitted plan dict) stay at DEBUG with
    # a count-only surface so future Signature fields cannot leak via
    # raw_keys to log aggregators. The operational signal — "LLM
    # returned a dict" — survives via field_count.
    logger.debug(
        "workflow_from_brief.llm_returned",
        extra={"field_count": len(raw) if isinstance(raw, dict) else 0},
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

    # Step 6 — realize into a WorkflowBuilder. The realizer enforces the
    # node-type allowlist + SEC-1 denylist at the add_node choke point
    # (validate_plan's top-level node_type gate does not reach plan.nodes).
    builder = _realize(plan, allowed_node_types)
    logger.info(
        "workflow_from_brief.ok",
        extra={
            "node_count": len(plan.nodes),
            "connection_count": len(plan.connections),
            "confidence": plan.interpretation_confidence,
        },
    )
    return builder
