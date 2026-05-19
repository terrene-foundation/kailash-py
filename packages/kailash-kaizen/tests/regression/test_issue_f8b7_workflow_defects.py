"""Regression: latent ``kaizen.nodes.rag.workflows`` + ``strategies`` defects.

F8 shard B7 owns the A3-triage-gated fixes for ``workflows.py`` +
``strategies.py`` (the documented Quick Start RAG pipelines):

R3-L2 — chunker node-types unregistered (lazy module cache).
  ``strategies.py`` references ``SemanticChunkerNode`` /
  ``StatisticalChunkerNode`` / ``HierarchicalChunkerNode`` by string in
  ``add_node(...)``. The ``@register_node()`` decorators fire only when
  ``kailash.nodes.transform.chunkers`` is imported; kailash's lazy module
  cache means ``import kailash.nodes`` alone does NOT populate them. Fix: a
  registering import in ``strategies.py``. Verified: the 3 chunker strings
  resolve in ``NodeRegistry`` after importing ``kaizen.nodes.rag.strategies``.

R3-L3 — stale ``add_connection(from, to, route=...)`` form.
  ``workflows.py`` mixed the canonical 4-positional
  ``WorkflowBuilder.add_connection(from_node, from_output, to_node,
  to_input)`` form with a pre-monorepo 3-arg ``route=`` keyword form that the
  current strict signature rejects with ``TypeError``. 9 sites across the 3
  multi-strategy workflows (advanced / adaptive / configurable). Fix: rewrote
  all 9 to the 4-arg form. The ``SwitchNode`` routers also carried an invalid
  ``routes`` dict config key; corrected to ``cases`` (multi-case mode) so the
  per-case ``case_<value>`` output ports exist for the rewritten connections.

Defect — content:None / non-dict crash class in 4 codegen templates.
  ``doc.get("content", "")`` returns ``None`` for a present-but-None
  ``content`` key (the ``""`` default fires ONLY for a MISSING key); a
  following ``.lower()`` / ``len()`` then raised ``TypeError``. A non-dict
  element (``documents`` is arbitrary upstream input) raised ``AttributeError``
  on ``.get``. The defect spans 4 ``code=`` PythonCodeNode templates:
  ``quality_analyzer`` + ``document_preprocessor`` (workflows.py) and
  ``keyword_extractor`` + ``level_processor`` (strategies.py). Fix: nested
  ``_content`` helper with ``or ""`` + ``isinstance(doc, dict)`` filtering.

These tests fail against pre-B7 ``workflows.py`` / ``strategies.py`` and pass
against the fix. Assertions are behavioral: import / construct / execute the
PythonCodeNode, assert it returns and does not raise — never source-grep.
"""

from __future__ import annotations

import inspect

import pytest
from kailash.nodes.base import Node, NodeRegistry
from kailash.nodes.logic.workflow import WorkflowNode
from kailash.workflow.builder import WorkflowBuilder
from kailash.workflow.graph import Workflow

from kaizen.nodes.rag.strategies import (
    RAGConfig,
    create_hierarchical_rag_workflow,
    create_statistical_rag_workflow,
)
from kaizen.nodes.rag.workflows import AdaptiveRAGWorkflowNode, AdvancedRAGWorkflowNode

pytestmark = pytest.mark.regression


def _wf(node: WorkflowNode) -> Workflow:
    """Narrow ``WorkflowNode.workflow`` (``Workflow | None``) to ``Workflow``."""
    wf = node.workflow  # type: ignore[attr-defined]
    assert wf is not None
    return wf


def _node(workflow: Workflow, node_id: str) -> Node:
    """Narrow ``Workflow.get_node`` (``Node | None``) to ``Node``."""
    found = workflow.get_node(node_id)
    assert found is not None, node_id
    return found


# A present-but-None content key, a non-dict element, a missing-content dict,
# and one well-formed doc — the four-way malformed-input fixture.
_MALFORMED = [
    {"content": None},
    "not-a-dict-element",
    {"no_content_key": 1},
    {"content": "real document text about code and functions"},
]


# ==========================================================================
# R3-L2 — chunker node-types register via the strategies.py importing import
# ==========================================================================


class TestR3L2ChunkerRegistration:
    """Importing kaizen.nodes.rag.strategies must populate the chunker types."""

    @pytest.mark.parametrize(
        "node_type",
        ["SemanticChunkerNode", "StatisticalChunkerNode", "HierarchicalChunkerNode"],
    )
    def test_chunker_type_resolves_in_registry(self, node_type):
        """The 3 chunker strings referenced by strategies.py builders resolve.

        Pre-B7: strategies.py imported only Node/WorkflowNode; the chunker
        decorators never fired, so add_node('SemanticChunkerNode', ...) raised
        a node-not-registered error inside every _create_*_workflow().
        """
        # Importing the module at the top of this file is the registering act.
        import kaizen.nodes.rag.strategies  # noqa: F401

        assert node_type in NodeRegistry._nodes

    def test_strategies_module_carries_registering_import(self):
        """The chunkers module is imported by strategies.py (the L2 fix)."""
        import kaizen.nodes.rag.strategies as strat

        # The registering import binds the module object; it must be present.
        assert hasattr(strat, "_chunkers")


# ==========================================================================
# R3-L3 — workflows.py uses the canonical 4-arg add_connection form
# ==========================================================================


class TestR3L3CanonicalAddConnection:
    """All 3 multi-strategy WorkflowNodes construct (no route= TypeError)."""

    def test_add_connection_signature_is_strict_four_positional(self):
        """The fix targets this exact signature: no `route` keyword exists."""
        sig = inspect.signature(WorkflowBuilder.add_connection)
        params = [p for p in sig.parameters if p != "self"]
        assert params == ["from_node", "from_output", "to_node", "to_input"]

    def test_advanced_workflow_constructs(self):
        """Pre-B7: add_connection(router, target, route=...) → TypeError."""
        node = AdvancedRAGWorkflowNode()
        assert node.workflow is not None  # type: ignore[attr-defined]

    def test_adaptive_workflow_constructs(self):
        node = AdaptiveRAGWorkflowNode()
        assert node.workflow is not None  # type: ignore[attr-defined]

    def test_advanced_router_emits_per_case_ports(self):
        """The SwitchNode router is configured for multi-case (cases=[...]).

        The R3-L3 rewrite connects from `case_<strategy>` output ports; those
        ports exist only when the router runs in multi-case mode. The wiring
        would be structurally impossible against the old invalid `routes`
        config (SwitchNode has no `routes` parameter).
        """
        wf = _wf(AdvancedRAGWorkflowNode())
        router = _node(wf, "strategy_router")
        assert router.config.get("cases") == [
            "semantic",
            "statistical",
            "hybrid",
            "hierarchical",
        ]

    def test_advanced_workflow_connections_reference_case_ports(self):
        """The router→pipeline edges use case_<value> source-output ports.

        ``Workflow.connections`` holds ``Connection`` pydantic models whose
        source-output field is ``source_output``.
        """
        wf = _wf(AdvancedRAGWorkflowNode())
        router_edges = [c for c in wf.connections if c.source_node == "strategy_router"]
        source_outputs = {c.source_output for c in router_edges}
        assert source_outputs == {
            "case_semantic",
            "case_statistical",
            "case_hybrid",
            "case_hierarchical",
        }


# ==========================================================================
# Defect — content:None / non-dict crash class across 4 codegen templates
# ==========================================================================


class TestNoneContentCrashClass:
    """Malformed documents must not crash any RAG codegen PythonCodeNode."""

    def test_advanced_quality_analyzer_survives_malformed_corpus(self):
        """quality_analyzer: doc.get('content','').lower() crashed on None."""
        node = _node(_wf(AdvancedRAGWorkflowNode()), "quality_analyzer")
        out = node.execute(documents=_MALFORMED)
        analysis = out["result"]["analysis"]
        # one well-formed doc survives the isinstance filter
        assert analysis["total_docs"] == 3
        assert analysis["recommended_strategy"] in {
            "semantic",
            "statistical",
            "hybrid",
            "hierarchical",
        }

    def test_advanced_quality_analyzer_survives_empty(self):
        node = _node(_wf(AdvancedRAGWorkflowNode()), "quality_analyzer")
        out = node.execute(documents=[])
        assert out["result"]["analysis"]["total_docs"] == 0

    def test_advanced_quality_analyzer_detects_technical_content(self):
        """The well-formed doc mentions 'code'+'functions' → is_technical true.

        Proves the _content helper still reads real content (not a no-op
        guard that swallows every doc).
        """
        node = _node(_wf(AdvancedRAGWorkflowNode()), "quality_analyzer")
        out = node.execute(documents=_MALFORMED)
        assert out["result"]["analysis"]["is_technical"] is True

    def test_adaptive_document_preprocessor_survives_malformed_corpus(self):
        """document_preprocessor: total_length sum() crashed on None content."""
        node = _node(_wf(AdaptiveRAGWorkflowNode()), "document_preprocessor")
        out = node.execute(documents=_MALFORMED, query="optimize")
        assert out["result"]["document_count"] == 3

    def test_adaptive_document_preprocessor_survives_unicode(self):
        node = _node(_wf(AdaptiveRAGWorkflowNode()), "document_preprocessor")
        out = node.execute(
            documents=[{"content": "naïve café — 日本語 código"}],
            query="q",
        )
        assert out["result"]["document_count"] == 1

    def test_statistical_keyword_extractor_survives_malformed_chunks(self):
        """keyword_extractor: chunk['content'] KeyError / None.lower() crash."""
        node = _node(
            _wf(create_statistical_rag_workflow(RAGConfig())), "keyword_extractor"
        )
        out = node.execute(chunks=_MALFORMED)
        # 3 dict chunks survive the isinstance filter
        assert len(out["result"]["keywords"]) == 3

    def test_hierarchical_level_processor_survives_malformed_chunks(self):
        """level_processor: chunk.get on a non-dict element raised."""
        node = _node(
            _wf(create_hierarchical_rag_workflow(RAGConfig())), "level_processor"
        )
        out = node.execute(chunks=_MALFORMED)
        assert set(out["result"]["level_chunks"].keys()) == {
            "document",
            "section",
            "paragraph",
        }
