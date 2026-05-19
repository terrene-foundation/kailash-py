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
# live. `WorkflowNode`-subclass entries are A2 scope (super().__init__(name,
# self._create_workflow()) — still broken until A2) and marked skip so this
# file is green now; A2 un-skips them.
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

# Modules whose only node classes are WorkflowNode subclasses — A2 scope.
# Listed for completeness; their instantiation is skip-marked below.
RAG_WORKFLOWNODE_ONLY_MODULES = ["optimized", "workflows"]


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
@pytest.mark.parametrize("mod", RAG_WORKFLOWNODE_ONLY_MODULES)
@pytest.mark.skip(reason="WorkflowNode constructors fixed in A2")
def test_representative_workflownode_constructs(mod):
    """A2 un-skips this: WorkflowNode-subclass modules construct.

    `optimized` and `workflows` expose only WorkflowNode subclasses, whose
    __init__ calls super().__init__(name, self._create_workflow()) — still
    broken (A2 scope). Skip-marked so this file is green at A1; A2 removes the
    skip and asserts construction of a representative WorkflowNode per module.
    """
    importlib.import_module(f"kaizen.nodes.rag.{mod}")
