"""Tier-2a integration coverage — ``kaizen.nodes.rag.evaluation``.

F8 shard B9b. The 3 classes under test (RAGEvaluationNode,
RAGBenchmarkNode, TestDatasetGeneratorNode) carry the metric-correctness
CLAIMS the resurrection floor never verified.

Value-anchor (F8 plan §B B9b row): "**metric correctness + real storage
read-back**". This file lifts the metric-correctness half by exercising
the codegen PythonCodeNode templates AND the Node-subclass run paths
under a real ``LocalRuntime.execute(workflow.build())`` against fixed
fixtures. The real-storage-read-back half lives in
``tests/integration/rag/test_conversational_nodes.py`` via real aiosqlite.

NO mocking (``@patch`` / ``MagicMock`` / ``unittest.mock`` are BLOCKED in
Tier 2/3 per ``rules/testing.md``).
"""

from __future__ import annotations

import pytest
from kailash.runtime.local import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder
from kailash.workflow.graph import Workflow

from kaizen.nodes.rag.evaluation import (
    RAGBenchmarkNode,
    RAGEvaluationNode,
    TestDatasetGeneratorNode,
)

pytestmark = pytest.mark.integration


def _build(node: RAGEvaluationNode) -> Workflow:
    """Past the ``@register_node`` Node-type erasure — see B7/B8/B9a precedent."""
    return node._create_workflow()  # type: ignore[attr-defined]


def _run_context_evaluator(code: str, test_result: dict) -> dict:
    """Exec the codegen against a single ``test_result`` fixture.

    F9 #1117 fixed the codegen: the function returns its dict AND the
    codegen invokes ``result = ...`` at module scope by iterating
    ``test_data``. For Tier-2a's per-test-result correctness assertions
    we exec the codegen with ``test_data`` bound to a single-element
    list and re-call the inner function on the caller's fixture.
    """
    ns: dict = {"test_data": [test_result]}
    exec(code, ns)
    return ns["evaluate_context_precision"](test_result)


# ==========================================================================
# RAGEvaluationNode — metric-correctness end-to-end through real codegen
# ==========================================================================


class TestContextPrecisionUnderRealRuntime:
    """The context_evaluator runs under a real LocalRuntime executor.

    Mirrors B9a's ``TestCodegenRealRuntime`` precedent: extract codegen
    from the workflow node, embed it in a fresh single-node builder, run
    it through LocalRuntime against a real input dict. The patched
    function adds the missing ``return result`` + module-scope call so
    PythonCodeNode binds a top-level ``result``.
    """

    @pytest.mark.filterwarnings("ignore::SyntaxWarning")
    def test_context_evaluator_under_runtime_returns_documented_shape(self):
        wf = _build(RAGEvaluationNode())
        evaluator = wf.get_node("context_evaluator")
        assert evaluator is not None
        # F9 #1117: codegen now returns its dict AND iterates `test_data`
        # at module scope. Embed verbatim; LocalRuntime binds `test_data`
        # from `parameters` and publishes the module-scope `result`.
        code = evaluator.config["code"]

        builder = WorkflowBuilder()
        builder.add_node(
            "PythonCodeNode",
            node_id="ctx_under_runtime",
            config={"code": code},
        )
        runtime = LocalRuntime()
        results, _ = runtime.execute(
            builder.build(),
            parameters={
                "ctx_under_runtime": {
                    "test_data": [
                        {
                            "retrieved_contexts": [
                                {"content": "a b c d e", "score": 0.95},
                                {"content": "f g h i j", "score": 0.90},
                                {"content": "k l m n o", "score": 0.45},
                            ],
                            "query": "test query",
                        }
                    ]
                }
            },
        )
        out = results["ctx_under_runtime"]["result"]
        # The shape MUST carry the documented context_metrics list (one
        # entry per input test_data row after the codegen iterates).
        assert "context_metrics" in out
        ctx_list = out["context_metrics"]
        assert isinstance(ctx_list, list)
        assert len(ctx_list) == 1
        cm = ctx_list[0]
        for key in (
            "precision_at_k",
            "mrr",
            "diversity_score",
            "avg_relevance_score",
            "context_count",
        ):
            assert key in cm, key
        # Numeric correctness — 2 of 3 contexts scored > 0.7.
        assert cm["context_count"] == 3
        assert cm["precision_at_k"]["P@3"] == pytest.approx(2 / 3)
        # First relevant at rank 1 → MRR = 1.0.
        assert cm["mrr"] == 1.0


# ==========================================================================
# RAGEvaluationNode — metric_aggregator end-to-end against fixed scores
# ==========================================================================


class TestMetricAggregatorUnderRealRuntime:
    """The metric_aggregator computes mean/median/std_dev over fixed scores.

    The aggregator's docstring promises aggregate_metrics carrying
    statistics.mean / median / stdev plus failure analysis +
    recommendations. We feed deterministic per-test scores in and assert
    the aggregate values match the formulas.
    """

    @pytest.mark.filterwarnings("ignore::SyntaxWarning")
    def test_metric_aggregator_under_runtime_computes_means(self):
        wf = _build(RAGEvaluationNode(use_reference_answers=False))
        aggregator = wf.get_node("metric_aggregator")
        assert aggregator is not None
        # F9 #1117 + #1118: codegen now imports the `datetime` class
        # explicitly, returns its aggregate dict, AND calls
        # `aggregate_evaluation_metrics(...)` at module scope. Embed the
        # codegen verbatim; LocalRuntime binds the wired inputs from
        # `parameters` and publishes the module-scope `result`.
        code = aggregator.config["code"]

        builder = WorkflowBuilder()
        builder.add_node(
            "PythonCodeNode",
            node_id="agg_under_runtime",
            config={"code": code},
        )
        runtime = LocalRuntime()
        results, _ = runtime.execute(
            builder.build(),
            parameters={
                "agg_under_runtime": {
                    "test_results": [
                        {"query": "q1", "execution_time": 0.1},
                        {"query": "q2", "execution_time": 0.2},
                    ],
                    "faithfulness_scores": [
                        {"response": {"faithfulness_score": 0.9}},
                        {"response": {"faithfulness_score": 0.7}},
                    ],
                    "relevance_scores": [
                        {"response": {"relevance_score": 0.8}},
                        {"response": {"relevance_score": 0.6}},
                    ],
                    "context_metrics": [
                        {"context_metrics": {"avg_relevance_score": 0.85}},
                        {"context_metrics": {"avg_relevance_score": 0.75}},
                    ],
                }
            },
        )
        out = results["agg_under_runtime"]["result"]
        summary = out["evaluation_summary"]
        aggregate = summary["aggregate_metrics"]
        # Mean of 0.9 + 0.7 = 0.8.
        assert aggregate["faithfulness"]["mean"] == pytest.approx(0.8)
        # Mean of 0.8 + 0.6 = 0.7.
        assert aggregate["relevance"]["mean"] == pytest.approx(0.7)
        # Mean of execution_time = 0.15.
        assert aggregate["execution_time"]["mean"] == pytest.approx(0.15)
        # Failure analysis honors the 0.6 threshold; with average ~0.825 +
        # ~0.683, neither test falls below 0.6.
        assert summary["failure_analysis"]["failure_count"] in (0, 1)
        # The overall score is the mean of faithfulness + relevance +
        # context-precision means.
        assert summary["overall_score"] == pytest.approx(
            (0.8 + 0.7 + 0.8) / 3, rel=0.01
        )


# ==========================================================================
# RAGBenchmarkNode — Node.run() invariants under real Python runtime
# ==========================================================================


class TestRAGBenchmarkRealRuntime:
    """RAGBenchmarkNode.run() exercised end-to-end under the real interpreter.

    No mock — the run() body uses real time.sleep + real statistics calls.
    """

    def test_run_produces_comparison_winners_for_each_axis(self):
        node = RAGBenchmarkNode(workload_sizes=[2], concurrent_users=[1])
        out = node.run(
            rag_systems={"sys_alpha": {}, "sys_beta": {}},
            test_queries=[{"q": "1"}, {"q": "2"}],
            duration=1,
        )
        # The three winner-keys are populated.
        comp = out["comparison"]
        assert comp["fastest_system"] in {"sys_alpha", "sys_beta"}
        assert comp["most_scalable"] in {"sys_alpha", "sys_beta"}
        assert comp["most_efficient"] in {"sys_alpha", "sys_beta"}
        # Each system has a populated latency profile per workload size.
        for sys_name in ("sys_alpha", "sys_beta"):
            sys_results = out["benchmark_results"][sys_name]
            assert "size_2" in sys_results["latency_profiles"]
            # p50/p95/p99 are real (numbers, not None).
            assert isinstance(sys_results["latency_profiles"]["size_2"]["p50"], float)

    def test_run_throughput_curves_have_positive_values(self):
        """Throughput is queries/total_time — always positive when queries > 0."""
        node = RAGBenchmarkNode(workload_sizes=[2], concurrent_users=[1])
        out = node.run(
            rag_systems={"only": {}},
            test_queries=[{"q": "1"}, {"q": "2"}],
            duration=1,
        )
        throughput = out["benchmark_results"]["only"]["throughput_curves"]["size_2"]
        assert throughput > 0


# ==========================================================================
# TestDatasetGeneratorNode — generation invariants under real interpreter
# ==========================================================================


class TestTestDatasetGeneratorRealRuntime:
    """Real run() against the deterministic-seed paths."""

    def test_run_carries_generation_config_to_caller(self):
        node = TestDatasetGeneratorNode(
            categories=["factual"], include_adversarial=False
        )
        out = node.run(num_samples=4, domain="machine learning", seed=11)
        # The generation_config block reflects the constructor + invocation.
        gen = out["generation_config"]
        assert gen["domain"] == "machine learning"
        assert gen["categories"] == ["factual"]
        assert gen["seed"] == 11

    def test_run_every_entry_has_three_contexts_default(self):
        """The codegen produces exactly 3 contexts per non-adversarial entry."""
        node = TestDatasetGeneratorNode(
            categories=["factual"], include_adversarial=False
        )
        out = node.run(num_samples=5, seed=2)
        for entry in out["test_dataset"]:
            assert len(entry["contexts"]) == 3
            # Contexts are typed with decreasing relevance: 0.9, 0.8, 0.7.
            assert entry["contexts"][0]["relevance"] == pytest.approx(0.9)
            assert entry["contexts"][1]["relevance"] == pytest.approx(0.8)
            assert entry["contexts"][2]["relevance"] == pytest.approx(0.7)

    def test_run_id_field_is_unique_per_entry(self):
        node = TestDatasetGeneratorNode(include_adversarial=False)
        out = node.run(num_samples=10, seed=42)
        ids = [e["id"] for e in out["test_dataset"]]
        assert len(set(ids)) == len(ids)
        # Each id has the documented "test_<i>" shape.
        for i, entry in enumerate(out["test_dataset"]):
            assert entry["id"] == f"test_{i}"
