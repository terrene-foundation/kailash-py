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
