"""Regression: `kaizen.nodes.rag` is importable + collision-free.

The 17-module `kaizen.nodes.rag` package was dead-on-arrival from the
2026-03-11 monorepo move (`b553104c`) — every module's relative imports
pointed at a non-existent `kaizen.nodes.{base,code,data,logic,security}` /
`kaizen.runtime` / `kaizen.workflow` tree (the symbols live in `kailash.*`).
The package was un-importable for ~2 months; nothing referenced it.

This resurrection repoints every broken import to `kailash.*` and renames the
one intra-package duplicate-registered node (`rag.realtime.StreamingRAGNode`
→ `RealtimeStreamingRAGNode`) so the package imports clean under the
kailash 2.23.0 cross-module collision guard (issue #891).

This test is the structural floor: Python executes every class body + every
`@register_node` decorator (including its constructor validation) at import,
so a clean import of all 16 submodules under the live guard proves imports
resolve AND no cross-module registry collision remains. Deep per-node
behavioral coverage of the ~53 RAG node classes is a separate follow-up.
"""

from __future__ import annotations

import importlib

import pytest

RAG_MODULES = [
    "advanced",
    "agentic",
    "conversational",
    "evaluation",
    "federated",
    "graph",
    "multimodal",
    "optimized",
    "privacy",
    "query_processing",
    "realtime",
    "registry",
    "router",
    "similarity",
    "strategies",
    "workflows",
]


@pytest.mark.regression
def test_rag_package_imports_clean_under_collision_guard():
    """`import kaizen.nodes.rag` must not raise (incl. no #891 guard error)."""
    import kaizen.nodes.rag  # noqa: F401


@pytest.mark.regression
@pytest.mark.parametrize("mod", RAG_MODULES)
def test_each_rag_module_imports_clean(mod):
    """Every rag submodule imports — its relative imports resolve to kailash.*."""
    importlib.import_module(f"kaizen.nodes.rag.{mod}")


@pytest.mark.regression
def test_streamingrag_collision_resolved():
    """realtime → RealtimeStreamingRAGNode; optimized keeps StreamingRAGNode.

    Both register distinctly; the bare-name collision that the kailash 2.23.0
    guard would raise on is gone.
    """
    from kailash.nodes.base import NodeRegistry

    import kaizen.nodes.rag.optimized  # noqa: F401
    import kaizen.nodes.rag.realtime  # noqa: F401

    reg = NodeRegistry._nodes
    assert "RealtimeStreamingRAGNode" in reg, "realtime rename did not register"
    assert "StreamingRAGNode" in reg, "optimized StreamingRAGNode missing"
    assert reg["RealtimeStreamingRAGNode"].__module__.endswith("rag.realtime"), reg[
        "RealtimeStreamingRAGNode"
    ].__module__
    assert reg["StreamingRAGNode"].__module__.endswith("rag.optimized"), reg[
        "StreamingRAGNode"
    ].__module__


@pytest.mark.regression
def test_representative_rag_nodes_register():
    """A spread of the ~53 RAG node classes are reachable in the registry."""
    from kailash.nodes.base import NodeRegistry

    import kaizen.nodes.rag  # noqa: F401

    reg = NodeRegistry._nodes
    for name in (
        "GraphRAGNode",
        "AgenticRAGNode",
        "HyDENode",
        "FederatedRAGNode",
        "MultimodalRAGNode",
        "PrivacyPreservingRAGNode",
        "ColBERTRetrievalNode",
        "RAGEvaluationNode",
    ):
        assert name in reg, f"{name} not registered after rag import"


@pytest.mark.regression
def test_rag_coexists_with_broader_kaizen_node_surface():
    """No rag class name collides cross-module with the wider kaizen registry.

    The kailash 2.23.0 cross-module guard raises NodeConfigurationError at
    import on ANY two distinct modules registering the same name. Importing
    the broader kaizen node surface AND kaizen.nodes.rag in one process is the
    definitive check that no rag node name collides with a non-rag node — the
    gap the rag-only smoke test cannot see.
    """
    import kaizen.nodes.ai  # noqa: F401  — large non-rag kaizen node package
    import kaizen.nodes.rag  # noqa: F401  — must not raise under the guard


# ---------------------------------------------------------------------------
# Constructor-floor coverage (F8 A1 / A2).
#
# The import-smoke tests above execute every class body + every @register_node
# decorator at import — but a @register_node decorator does NOT call __init__.
# A node whose __init__ calls super().__init__(name) positionally against the
# kailash.nodes.base.Node keyword config-bag imports clean yet raises TypeError
# on EVERY construction. That is the resurrection false-floor: "imports clean"
# is necessary but not sufficient — the package was advertised as usable while
# every node was un-constructable.
#
# Each entry below names one representative class per code module AND the
# constructor kwargs to build it. `Node`-subclass entries are A1 scope (fixed:
# canonical super().__init__(name=name, **config) keyword form) and asserted
# live.
#
# A2 corrected the 13 `WorkflowNode`-subclass constructor *forms*: positional
# super().__init__(name, self._create_workflow()) — which landed `name` in the
# `workflow` slot of WorkflowNode.__init__(workflow, **kwargs) and left the
# real workflow with no positional slot, a TypeError on EVERY construction —
# became canonical keyword super().__init__(workflow=self._create_workflow(),
# name=name). The constructor form is now correct for all 17 WorkflowNode
# subclasses, but 6 still cannot fully construct because their
# _create_workflow() bodies reference unregistered node types or hit a
# NameError — that is A3-triage scope, not A2. A3 dispositioned all 6 (see
# `workspaces/kaizen-rag-node-coverage/01-analysis/04-A3-triage.md`): the
# rag-side `_create_workflow()` fixes are routed to the owning B-coverage
# shards, and the owning B-shard un-marks its xfail when it lands the fix.
# `workflows.py`'s 4 classes were already constructor-canonical (never A2
# scope) but are A3-blocked on the unregistered 'SemanticChunkerNode' all
# the same.
# ---------------------------------------------------------------------------

# (module, class_name, ctor_kwargs) — representative Node-subclass per module.
RAG_NODE_REPRESENTATIVES = [
    ("advanced", "SelfCorrectingRAGNode", {"name": "smoke_self_correcting"}),
    ("agentic", "ToolAugmentedRAGNode", {"name": "smoke_tool_augmented"}),
    ("conversational", "ConversationMemoryNode", {"name": "smoke_conv_memory"}),
    ("evaluation", "RAGBenchmarkNode", {"name": "smoke_rag_benchmark"}),
    ("federated", "EdgeRAGNode", {"name": "smoke_edge_rag"}),
    ("graph", "GraphBuilderNode", {"name": "smoke_graph_builder"}),
    ("multimodal", "VisualQuestionAnsweringNode", {"name": "smoke_vqa"}),
    ("privacy", "SecureMultiPartyRAGNode", {"name": "smoke_secure_mpc"}),
    ("query_processing", "QueryExpansionNode", {"name": "smoke_query_expansion"}),
    ("realtime", "RealtimeStreamingRAGNode", {"name": "smoke_realtime_streaming"}),
    ("registry", "RAGWorkflowRegistry", {}),
    ("router", "RAGStrategyRouterNode", {"name": "smoke_rag_router"}),
    ("similarity", "DenseRetrievalNode", {"name": "smoke_dense_retrieval"}),
    ("strategies", "SemanticRAGNode", {"name": "smoke_semantic_rag"}),
]

# (module, class_name, ctor_kwargs) — every WorkflowNode subclass in the rag
# package. A2 corrected the 13 fixed classes' constructor *form*: positional
# super().__init__(name, self._create_workflow()) — which landed `name` in the
# `workflow` slot of WorkflowNode.__init__(workflow, **kwargs) and left the real
# workflow with no positional slot, a TypeError on EVERY construction — became
# canonical keyword super().__init__(workflow=self._create_workflow(), name=name).
#
# The constructor *form* is now correct for all 17, but 6 classes still cannot
# FULLY construct because their _create_workflow() bodies reference unregistered
# node types or hit a NameError — that is A3-triage scope, not A2. Those 6 are
# marked xfail(strict=True): the moment the owning B-coverage shard fixes the
# _create_workflow() body they XPASS, the strict marker turns the unexpected
# pass into a FAILURE, and that B-shard is forced to remove the mark. The
# marker IS the cross-shard tracking hook (A3 dispositions, the B-shard fixes
# + un-marks — see 04-A3-triage.md) — skip would be silent, dropping the
# param would hide the gap.
#
# The 4 workflows.py classes were already constructor-canonical (multi-line
# keyword super().__init__(workflow=, name=, description=)) and were never A2
# scope — but they are A3-blocked on the unregistered 'SemanticChunkerNode' all
# the same, so they carry the same xfail marker. Each class takes a defaulted
# `name` plus defaulted config.
_A3_CACHE_NODE = (
    "A3 (R3): _create_workflow references unregistered node type 'CacheNode'"
)
_A3_PII_NAMEERROR = (
    "A3 (R4 LEAK, A0-tabled): privacy.py _create_workflow raises NameError 'pii_type'"
)

RAG_WORKFLOWNODE_SUBCLASSES = [
    # 13 A2-fixed classes (positional super().__init__ → keyword form).
    pytest.param("realtime", "RealtimeRAGNode", {"name": "smoke_realtime_rag"}),
    pytest.param("agentic", "AgenticRAGNode", {"name": "smoke_agentic_rag"}),
    pytest.param("agentic", "ReasoningRAGNode", {"name": "smoke_reasoning_rag"}),
    pytest.param("evaluation", "RAGEvaluationNode", {"name": "smoke_rag_evaluation"}),
    pytest.param("graph", "GraphRAGNode", {"name": "smoke_graph_rag"}),
    pytest.param("multimodal", "MultimodalRAGNode", {"name": "smoke_multimodal_rag"}),
    pytest.param("federated", "FederatedRAGNode", {"name": "smoke_federated_rag"}),
    pytest.param(
        "conversational",
        "ConversationalRAGNode",
        {"name": "smoke_conversational_rag"},
    ),
    pytest.param(
        "optimized",
        "CacheOptimizedRAGNode",
        {"name": "smoke_cache_optimized_rag"},
        marks=pytest.mark.xfail(strict=True, reason=_A3_CACHE_NODE),
    ),
    pytest.param(
        "optimized", "AsyncParallelRAGNode", {"name": "smoke_async_parallel_rag"}
    ),
    pytest.param("optimized", "StreamingRAGNode", {"name": "smoke_streaming_rag"}),
    pytest.param(
        "optimized", "BatchOptimizedRAGNode", {"name": "smoke_batch_optimized_rag"}
    ),
    pytest.param(
        "privacy",
        "PrivacyPreservingRAGNode",
        {"name": "smoke_privacy_rag"},
        marks=pytest.mark.xfail(strict=True, reason=_A3_PII_NAMEERROR),
    ),
    # 4 workflows.py classes — already constructor-canonical, never A2 scope.
    # B7 applied the A3-triage R3-L2 fix (chunker registering import in
    # strategies.py) + R3-L3 fix (rewrote the stale `add_connection(route=)`
    # calls to the canonical 4-arg form), so all 4 now construct fully — the
    # xfail markers were removed by B7, the owning shard.
    pytest.param(
        "workflows",
        "SimpleRAGWorkflowNode",
        {"name": "smoke_simple_rag_workflow"},
    ),
    pytest.param(
        "workflows",
        "AdvancedRAGWorkflowNode",
        {"name": "smoke_advanced_rag_workflow"},
    ),
    pytest.param(
        "workflows",
        "AdaptiveRAGWorkflowNode",
        {"name": "smoke_adaptive_rag_workflow"},
    ),
    pytest.param(
        "workflows",
        "RAGPipelineWorkflowNode",
        {"name": "smoke_rag_pipeline_workflow"},
    ),
]

# Stable test ids: (module.class_name) per param, mirroring RAG_NODE_REPRESENTATIVES.
_RAG_WORKFLOWNODE_IDS = [
    f"{p.values[0]}.{p.values[1]}" for p in RAG_WORKFLOWNODE_SUBCLASSES
]


@pytest.mark.regression
@pytest.mark.parametrize(
    "mod, cls_name, ctor_kwargs",
    RAG_NODE_REPRESENTATIVES,
    ids=[f"{m}.{c}" for m, c, _ in RAG_NODE_REPRESENTATIVES],
)
def test_representative_rag_node_constructs(mod, cls_name, ctor_kwargs):
    """One representative Node-subclass per module MUST construct, no TypeError.

    This is the line-per-module that catches the resurrection false-floor: a
    @register_node decorator runs the class body at import but never calls
    __init__. Only an actual construction exercises super().__init__ — a
    positional super().__init__(name) against the keyword config-bag raises
    TypeError here while the import-smoke tests above stay green.
    """
    module = importlib.import_module(f"kaizen.nodes.rag.{mod}")
    cls = getattr(module, cls_name)
    instance = cls(**ctor_kwargs)
    assert instance is not None


@pytest.mark.regression
@pytest.mark.parametrize(
    "mod, cls_name, ctor_kwargs",
    RAG_WORKFLOWNODE_SUBCLASSES,
    ids=_RAG_WORKFLOWNODE_IDS,
)
def test_workflownode_subclass_constructs(mod, cls_name, ctor_kwargs):
    """Every WorkflowNode subclass in the rag package MUST construct.

    A2 corrected the 13 fixed classes' constructor form: positional
    super().__init__(name, self._create_workflow()) — `name` landed in the
    `workflow` slot of WorkflowNode.__init__(workflow, **kwargs), the real
    workflow had no positional slot, TypeError on EVERY construction — became
    canonical super().__init__(workflow=self._create_workflow(), name=name).

    Constructor form is now correct for all 17, but 6 classes still cannot
    fully construct: their _create_workflow() bodies reference unregistered
    node types ('CacheNode', 'SemanticChunkerNode') or raise a NameError
    ('pii_type'). A3-triage dispositioned all 6 (04-A3-triage.md) and routed
    the rag-side fixes to the owning B-coverage shards; each carries
    xfail(strict=True) — when the owning B-shard fixes the _create_workflow()
    body the param XPASSes, the strict marker fails the test, and that
    B-shard is forced to remove the mark.

    Same false-floor logic as the Node-subclass test above: a @register_node
    decorator runs the class body at import but never calls __init__, so only
    an actual construction exercises super().__init__.
    """
    module = importlib.import_module(f"kaizen.nodes.rag.{mod}")
    cls = getattr(module, cls_name)
    instance = cls(**ctor_kwargs)
    assert instance is not None
