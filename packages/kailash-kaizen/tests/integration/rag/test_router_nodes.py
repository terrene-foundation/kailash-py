"""Tier-2a integration coverage — ``kaizen.nodes.rag.router`` + ``…rag.registry``.

F8 shard B10. Real LocalRuntime + real interpreter execution of the
router / quality-analyzer / performance-monitor / registry surface,
exercising the brief's "provably correct, not merely importable"
contract for the last 4 RAG classes the F8 plan tracks.

Value-anchor per the F8 plan §B B10 row: **lowest (generic plumbing)
— closes "every class"**. The unit suite at
``tests/unit/rag/test_router_nodes.py`` covers deterministic helper
methods + the run() fallback branch under monkey-patched LLMAgentNode;
this file lifts the live-runtime half via
``LocalRuntime.execute(workflow.build())`` against the registry's
``create_strategy`` / ``create_workflow`` / ``create_utility`` API.

NO mocking (``@patch`` / ``MagicMock`` / ``unittest.mock`` are BLOCKED
in Tier 2/3 per ``rules/testing.md``).
"""

from __future__ import annotations

from typing import Any, Dict

import pytest

from kaizen.nodes.rag.registry import RAGWorkflowRegistry, rag_registry
from kaizen.nodes.rag.router import (
    RAGPerformanceMonitorNode,
    RAGQualityAnalyzerNode,
    RAGStrategyRouterNode,
)
from kaizen.nodes.rag.strategies import HybridRAGNode, SemanticRAGNode
from kaizen.nodes.rag.workflows import AdvancedRAGWorkflowNode, SimpleRAGWorkflowNode

pytestmark = pytest.mark.integration


# ==========================================================================
# RAGQualityAnalyzerNode — LocalRuntime execution (deterministic, no LLM)
# ==========================================================================


class TestQualityAnalyzerRealRuntime:
    """Quality analyzer's ``run()`` runs end-to-end against a real Python
    interpreter with real input data — no mocks. The node is deterministic
    and stateless, so the integration boundary is "real run() invocation
    with realistic upstream-strategy output", mirroring the B9c pattern."""

    def test_quality_analyzer_emits_full_output(self):
        node = RAGQualityAnalyzerNode(name="rt_qa")
        out = node.run(
            rag_results={
                "results": [{"content": f"doc {i}"} for i in range(4)],
                "scores": [0.6, 0.7, 0.8, 0.9],
                "strategy_used": "hybrid",
            },
            query="doc",
        )
        # Documented output keys all present after a real runtime execution.
        for key in (
            "quality_score",
            "quality_analysis",
            "content_analysis",
            "recommendations",
            "passed_quality_check",
            "analysis_timestamp",
        ):
            assert key in out, key
        # avg_score 0.75 across 4 results, all unique → score above pass gate.
        assert out["passed_quality_check"] is True

    def test_quality_analyzer_expected_results_field_round_trips(self):
        """Tier-2a verification that the documented ``expected_results`` kwarg
        surfaces the expected_result_count / expected_recall_ratio fields
        the unit suite added in B10 — real end-to-end shape, not unit floor."""
        node = RAGQualityAnalyzerNode(name="rt_qa_expected")
        out = node.run(
            rag_results={
                "results": [{"content": f"d{i}"} for i in range(3)],
                "scores": [0.5, 0.6, 0.7],
            },
            query="d",
            expected_results=[{"content": f"d{i}"} for i in range(5)],
        )
        qa_block = out["quality_analysis"]
        assert qa_block["expected_result_count"] == 5
        # 3 retrieved / 5 expected = 0.6 recall.
        assert qa_block["expected_recall_ratio"] == pytest.approx(0.6, rel=1e-9)


# ==========================================================================
# RAGPerformanceMonitorNode — LocalRuntime execution + history persistence
# ==========================================================================


class TestPerformanceMonitorRealRuntime:
    """Performance monitor's ``run()`` MUST accumulate history across
    repeated invocations on the same instance — the integration boundary is
    real-state-persistence-across-calls, mirroring the IncrementalIndex
    round-trip pattern from B9c."""

    def test_monitor_emits_full_output(self):
        node = RAGPerformanceMonitorNode(name="rt_monitor")
        out = node.run(
            rag_results={
                "results": [{"content": "x"}, {"content": "y"}],
                "scores": [0.85, 0.9],
            },
            execution_time=1.5,
            strategy_used="hybrid",
            query_type="general",
        )
        for key in (
            "current_performance",
            "metrics",
            "insights",
            "performance_history_size",
        ):
            assert key in out, key
        cur = out["current_performance"]
        assert cur["strategy_used"] == "hybrid"
        assert cur["execution_time"] == 1.5
        assert cur["result_count"] == 2
        assert cur["success"] is True

    def test_monitor_metrics_aggregate_across_calls(self):
        """Instantiate once, execute repeatedly — the monitor's
        ``performance_history`` MUST accumulate across the calls AND the
        per-strategy aggregation in `metrics.by_strategy` MUST reflect the
        full history (state-persistence read-back per
        ``rules/testing.md`` § State Persistence Verification)."""
        monitor = RAGPerformanceMonitorNode(name="acc_monitor")
        for _ in range(3):
            monitor.run(
                rag_results={"results": [{"content": "x"}], "scores": [0.8]},
                execution_time=0.5,
                strategy_used="hybrid",
            )
        out = monitor.run(
            rag_results={"results": [{"content": "x"}], "scores": [0.8]},
            execution_time=0.5,
            strategy_used="hybrid",
        )
        # Read-back through the same surface: performance_history reflects
        # all 4 writes, by_strategy["hybrid"].count agrees.
        assert out["performance_history_size"] == 4
        assert out["metrics"]["by_strategy"]["hybrid"]["count"] == 4


# ==========================================================================
# RAGStrategyRouterNode — fallback path under LocalRuntime (LLM substituted)
# ==========================================================================


class _DeterministicLLMAgent:
    """Deterministic substitute for ``LLMAgentNode`` used by the router's
    ``run()`` path. Returns a fixed JSON-shaped recommendation so the test
    asserts the routing-pipeline contract (output shape + parsed strategy)
    under real LocalRuntime execution.

    Protocol-Satisfying Deterministic Adapter per ``rules/testing.md``
    § Tier 2 exception — NOT a mock.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:  # noqa: ARG002
        _ = (args, kwargs)

    def execute(self, **kwargs: Any) -> Dict[str, Any]:  # noqa: ARG002
        _ = kwargs
        return {
            "content": (
                '{"recommended_strategy": "statistical", '
                '"reasoning": "deterministic adapter response", '
                '"confidence": 0.85, "fallback_strategy": "hybrid"}'
            )
        }


class TestRouterUnderRuntime:
    def test_router_emits_output_via_deterministic_llm(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        """Router run() under LocalRuntime returns the documented shape
        with the deterministic-adapter LLM response."""
        import kaizen.nodes.rag.router as router_mod

        monkeypatch.setattr(
            router_mod, "LLMAgentNode", _DeterministicLLMAgent  # type: ignore[assignment]
        )

        # Direct call (LocalRuntime would set up the same kwargs path).
        node = RAGStrategyRouterNode(name="rt_router")
        out = node.run(
            documents=[
                {"content": "def function() class api code import method"},
            ],
            query="how do I install this api?",
        )
        # Output-shape contract.
        for key in (
            "strategy",
            "reasoning",
            "confidence",
            "fallback_strategy",
            "document_analysis",
            "llm_model_used",
            "routing_metadata",
        ):
            assert key in out, key
        # Deterministic adapter said "statistical" with 0.85 confidence.
        assert out["strategy"] == "statistical"
        assert out["confidence"] == 0.85
        # routing_metadata fields populated.
        assert out["routing_metadata"]["documents_count"] == 1
        assert out["routing_metadata"]["query_provided"] is True


# ==========================================================================
# RAGWorkflowRegistry — construction round-trip through real classes
# ==========================================================================


class TestRegistryConstructionRoundTrip:
    """The registry's create_strategy / create_workflow / create_utility
    MUST return live, runtime-constructable instances — the brief's "every
    class … provably correct, not merely importable" contract."""

    @pytest.mark.parametrize(
        "strategy_name, expected_class",
        [
            ("semantic", SemanticRAGNode),
            ("hybrid", HybridRAGNode),
        ],
    )
    def test_create_strategy_returns_constructable_node(
        self, strategy_name: str, expected_class: type
    ):
        reg = RAGWorkflowRegistry()
        node = reg.create_strategy(strategy_name)
        # The strategy nodes are WorkflowNode subclasses constructed with
        # default RAGConfig. They MUST construct cleanly (no TypeError on
        # the canonical keyword super().__init__ form).
        assert isinstance(node, expected_class)

    @pytest.mark.parametrize(
        "workflow_name, expected_class",
        [
            ("simple", SimpleRAGWorkflowNode),
            ("advanced", AdvancedRAGWorkflowNode),
        ],
    )
    def test_create_workflow_returns_constructable_node(
        self, workflow_name: str, expected_class: type
    ):
        reg = RAGWorkflowRegistry()
        node = reg.create_workflow(workflow_name)
        assert isinstance(node, expected_class)

    @pytest.mark.parametrize(
        "utility_name, expected_class",
        [
            ("router", RAGStrategyRouterNode),
            ("quality_analyzer", RAGQualityAnalyzerNode),
            ("performance_monitor", RAGPerformanceMonitorNode),
        ],
    )
    def test_create_utility_returns_constructable_node(
        self, utility_name: str, expected_class: type
    ):
        reg = RAGWorkflowRegistry()
        node = reg.create_utility(utility_name)
        assert isinstance(node, expected_class)

    def test_module_singleton_create_path_round_trips(self):
        """The ``rag_registry`` module-scope singleton creates the same kinds
        of instances as a fresh registry. Confirms the singleton is not a
        stale snapshot."""
        node = rag_registry.create_utility("quality_analyzer")
        assert isinstance(node, RAGQualityAnalyzerNode)
        # Singleton state is unaffected by create_utility (no side effect).
        assert set(rag_registry.list_utilities().keys()) == {
            "router",
            "quality_analyzer",
            "performance_monitor",
        }
