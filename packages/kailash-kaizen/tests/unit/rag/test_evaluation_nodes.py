"""Tier 1 unit coverage — ``kaizen.nodes.rag.evaluation``.

F8 shard B9b. The 3 classes under test (RAGEvaluationNode,
RAGBenchmarkNode, TestDatasetGeneratorNode) are the documented
evaluation / benchmarking / test-data-generation surface.

Tier 1 scope:

- Construction with default + custom kwargs across all 3 classes.
- ``get_parameters()`` contracts for the 2 ``Node``-subclass classes.
- The inner workflow GRAPH SHAPE produced by
  ``RAGEvaluationNode._create_workflow``.
- The deterministic ``run()`` paths on RAGBenchmarkNode +
  TestDatasetGeneratorNode (seeded-RNG reproducibility, dataset shape,
  benchmark aggregate shape).
- Metric-correctness floor: the context-precision codegen template
  produces deterministic P@k, MRR, and diversity values when fed a
  fixed retrieval fixture.

The value-anchor per the F8 plan §B B9b row is **metric correctness +
real storage read-back** — this file lifts the metric-correctness half;
``tests/integration/rag/test_conversational_nodes.py`` lifts the real-
storage-read-back half via real aiosqlite.
"""

from __future__ import annotations

import pytest
from kailash.workflow.graph import Workflow

from kaizen.nodes.rag.evaluation import (
    RAGBenchmarkNode,
    RAGEvaluationNode,
    TestDatasetGeneratorNode,
)

pytestmark = pytest.mark.unit


def _build(node: RAGEvaluationNode) -> Workflow:
    """Call ``node._create_workflow()`` past the ``@register_node`` Node-type erasure.

    Mirrors the B7/B8/B9a ``_build`` precedent: ``@register_node()`` erases
    the concrete subclass to ``Node`` for static checkers, so
    ``_create_workflow`` becomes invisible to pyright. The single
    suppression lets every call site stay clean.
    """
    return node._create_workflow()  # type: ignore[attr-defined]


# ==========================================================================
# Construction floor — all three classes
# ==========================================================================


class TestAllThreeConstruct:
    def test_rag_evaluation_constructs_default(self):
        node = RAGEvaluationNode()
        assert node is not None
        assert node.metadata.name == "rag_evaluation"
        # @register_node erases RAGEvaluationNode→Node for static checkers.
        assert node.metrics == [  # type: ignore[attr-defined]
            "faithfulness",
            "relevance",
            "context_precision",
            "answer_quality",
        ]
        assert node.use_reference_answers is True  # type: ignore[attr-defined]
        # F9 #1126: default is now env-loaded (`OPENAI_PROD_MODEL` /
        # `DEFAULT_LLM_MODEL`); resolves to None when neither is set.
        import os as _os

        expected = _os.environ.get(
            "OPENAI_PROD_MODEL", _os.environ.get("DEFAULT_LLM_MODEL")
        )
        assert node.llm_judge_model == expected  # type: ignore[attr-defined]

    def test_rag_evaluation_constructs_with_custom_kwargs(self):
        node = RAGEvaluationNode(
            name="custom_eval",
            metrics=["faithfulness"],
            use_reference_answers=False,
            llm_judge_model="claude-test",
        )
        assert node.metadata.name == "custom_eval"
        assert node.metrics == ["faithfulness"]  # type: ignore[attr-defined]
        assert node.use_reference_answers is False  # type: ignore[attr-defined]
        assert node.llm_judge_model == "claude-test"  # type: ignore[attr-defined]

    def test_rag_benchmark_constructs_default(self):
        node = RAGBenchmarkNode()
        assert node is not None
        assert node.metadata.name == "rag_benchmark"
        assert node.workload_sizes == [10, 100, 1000]  # type: ignore[attr-defined]
        assert node.concurrent_users == [1, 5, 10]  # type: ignore[attr-defined]

    def test_rag_benchmark_constructs_with_custom_kwargs(self):
        node = RAGBenchmarkNode(
            name="bench_custom",
            workload_sizes=[5],
            concurrent_users=[2],
        )
        assert node.metadata.name == "bench_custom"
        assert node.workload_sizes == [5]  # type: ignore[attr-defined]
        assert node.concurrent_users == [2]  # type: ignore[attr-defined]

    def test_test_dataset_generator_constructs_default(self):
        node = TestDatasetGeneratorNode()
        assert node is not None
        assert node.metadata.name == "test_dataset_generator"
        assert node.categories == ["factual", "analytical", "comparative"]  # type: ignore[attr-defined]
        assert node.include_adversarial is True  # type: ignore[attr-defined]

    def test_test_dataset_generator_constructs_with_custom_kwargs(self):
        node = TestDatasetGeneratorNode(
            name="gen_custom",
            categories=["factual"],
            include_adversarial=False,
        )
        assert node.metadata.name == "gen_custom"
        assert node.categories == ["factual"]  # type: ignore[attr-defined]
        assert node.include_adversarial is False  # type: ignore[attr-defined]


# ==========================================================================
# get_parameters() contracts — RAGBenchmarkNode + TestDatasetGeneratorNode
# ==========================================================================


class TestRAGBenchmarkParameters:
    def test_required_parameters(self):
        params = RAGBenchmarkNode().get_parameters()
        assert params["rag_systems"].required is True
        assert params["rag_systems"].type is dict
        assert params["test_queries"].required is True
        assert params["test_queries"].type is list

    def test_optional_parameters_with_defaults(self):
        params = RAGBenchmarkNode().get_parameters()
        assert params["name"].required is False
        assert params["workload_sizes"].required is False
        assert params["concurrent_users"].required is False
        assert params["duration"].required is False
        assert params["duration"].default == 60

    def test_get_parameters_returns_all_documented_keys(self):
        params = RAGBenchmarkNode().get_parameters()
        assert set(params.keys()) == {
            "name",
            "workload_sizes",
            "concurrent_users",
            "rag_systems",
            "test_queries",
            "duration",
        }


class TestTestDatasetGeneratorParameters:
    def test_required_parameters(self):
        params = TestDatasetGeneratorNode().get_parameters()
        assert params["num_samples"].required is True
        assert params["num_samples"].type is int

    def test_optional_parameters_with_defaults(self):
        params = TestDatasetGeneratorNode().get_parameters()
        assert params["name"].required is False
        assert params["categories"].required is False
        assert params["include_adversarial"].required is False
        assert params["include_adversarial"].default is True
        assert params["domain"].required is False
        assert params["domain"].default == "general"
        assert params["seed"].required is False


# ==========================================================================
# RAGEvaluationNode inner workflow — graph shape
# ==========================================================================


class TestRAGEvaluationGraphShape:
    """The _create_workflow graph holds the documented pipeline shape."""

    def test_default_graph_has_all_nodes_including_messages_composers(self):
        """With default use_reference_answers=True, all 12 nodes are wired: the 6
        pipeline nodes PLUS the 3 L3 messages-composers (one per LLM judge) that
        render the real evaluation data into each judge's ``messages`` port PLUS
        the 3 OUTPUT-side response-parsers (one per LLM judge) that read each
        judge's ``response`` -> ``.content`` -> ``json.loads`` into the per-test
        score list the aggregator indexes (the parse-gap fix)."""
        wf = _build(RAGEvaluationNode())
        assert set(wf.nodes.keys()) == {
            "test_executor",
            "faithfulness_evaluator",
            "faithfulness_messages_composer",
            "faithfulness_response_parser",
            "relevance_evaluator",
            "relevance_messages_composer",
            "relevance_response_parser",
            "context_evaluator",
            "answer_quality_evaluator",
            "answer_quality_messages_composer",
            "answer_quality_response_parser",
            "metric_aggregator",
        }

    def test_use_reference_answers_false_omits_answer_quality(self):
        """With use_reference_answers=False, the answer-quality node is skipped."""
        wf = _build(RAGEvaluationNode(use_reference_answers=False))
        assert "answer_quality_evaluator" not in wf.nodes
        # The other 5 nodes are still wired.
        assert {
            "test_executor",
            "faithfulness_evaluator",
            "relevance_evaluator",
            "context_evaluator",
            "metric_aggregator",
        }.issubset(set(wf.nodes.keys()))

    def test_use_reference_answers_false_drops_answer_quality_edges(self):
        wf = _build(RAGEvaluationNode(use_reference_answers=False))
        aq_edges = [
            c
            for c in wf.connections
            if c.target_node == "answer_quality_evaluator"
            or c.source_node == "answer_quality_evaluator"
        ]
        assert aq_edges == []

    def test_test_executor_fans_out_to_composers_context_and_aggregator(self):
        """test_executor feeds the 2 LLM-judge messages-composers (L3 fix), the
        context_evaluator (a PythonCodeNode, fed directly), and the aggregator.

        The LLM judges (faithfulness / relevance) are NO LONGER fed directly by
        test_executor — their context now flows test_executor → composer →
        judge.messages (the VALID LLMAgentNode context port). The composers are
        the new fan-out targets; the judges are downstream of them.
        """
        wf = _build(RAGEvaluationNode(use_reference_answers=False))
        targets = {
            c.target_node for c in wf.connections if c.source_node == "test_executor"
        }
        assert {
            "faithfulness_messages_composer",
            "relevance_messages_composer",
            "context_evaluator",
            "metric_aggregator",
        }.issubset(targets)
        # The LLM judges are fed by their composers, NOT directly by test_executor.
        assert "faithfulness_evaluator" not in targets
        assert "relevance_evaluator" not in targets

    def test_metric_aggregator_is_final_sink(self):
        """metric_aggregator has no outbound edges."""
        wf = _build(RAGEvaluationNode())
        outbound = [c for c in wf.connections if c.source_node == "metric_aggregator"]
        assert outbound == []
        # It has multiple inbound edges from upstream evaluators.
        inbound = [c for c in wf.connections if c.target_node == "metric_aggregator"]
        # test_executor + faithfulness + relevance + context + answer_quality = 5
        assert len(inbound) == 5

    def test_metric_aggregator_carries_configured_metrics(self):
        """The metrics list is baked into the aggregator's code template."""
        wf = _build(RAGEvaluationNode(metrics=["faithfulness", "relevance"]))
        aggregator = wf.get_node("metric_aggregator")
        assert aggregator is not None
        code = aggregator.config.get("code", "")
        # The metrics list is interpolated into the source via {self.metrics}.
        assert "['faithfulness', 'relevance']" in code

    def test_llm_judge_model_baked_into_evaluator_configs(self):
        """The llm_judge_model kwarg flows into the LLM-judge node configs."""
        wf = _build(RAGEvaluationNode(llm_judge_model="custom-judge"))
        faithfulness = wf.get_node("faithfulness_evaluator")
        relevance = wf.get_node("relevance_evaluator")
        assert faithfulness is not None
        assert relevance is not None
        assert faithfulness.config.get("model") == "custom-judge"
        assert relevance.config.get("model") == "custom-judge"


# ==========================================================================
# RAGEvaluationNode — metric-correctness floor (codegen template execution)
# ==========================================================================


class TestContextPrecisionMetricCorrectness:
    """The context_evaluator codegen template implements P@k, MRR, diversity.

    Value-anchor per F8 plan §B B9b row: "metric correctness + real storage
    read-back" — this class exercises the metric-correctness half by
    extracting the codegen function from the workflow node, executing it
    against a known-fixture retrieval result, and asserting deterministic
    metric values match the documented formulas.

    The codegen DEFINES ``evaluate_context_precision`` but never CALLS it at
    module scope. We extract the function and call it directly, mirroring
    the B9a integration-test ``_run_pii_detector`` helper precedent.
    """

    @staticmethod
    def _run_context_evaluator(code: str, test_result: dict) -> dict:
        """Exec the codegen against a single ``test_result`` fixture.

        F9 #1117 fixed the codegen: the function returns its dict, the
        codegen invokes ``result = ...`` at module scope iterating
        ``test_data``, then `del`s the helper so PythonCodeNode's output
        gate sees only `result`. For unit tests we strip the `del` line
        so the inner function survives exec, then call it directly on the
        caller's fixture for per-test-result assertions.
        """
        # Strip the F9 #1117 cleanup line so the helper survives exec.
        code_no_del = "\n".join(
            line
            for line in code.splitlines()
            if not line.startswith("del evaluate_context_precision")
        )
        ns: dict = {"test_data": [test_result]}
        exec(code_no_del, ns)
        return ns["evaluate_context_precision"](test_result)

    def test_empty_contexts_returns_zero_precision(self):
        wf = _build(RAGEvaluationNode())
        evaluator = wf.get_node("context_evaluator")
        assert evaluator is not None
        out = self._run_context_evaluator(
            evaluator.config["code"], {"retrieved_contexts": [], "query": "x"}
        )
        # The early-exit branch returns precision=recall=ranking_quality=0.
        assert out["context_precision"] == 0.0
        assert out["context_recall"] == 0.0
        assert out["context_ranking_quality"] == 0.0

    def test_p_at_k_with_all_relevant_contexts(self):
        """3 contexts all scoring > 0.7 → P@1=P@3=1.0."""
        wf = _build(RAGEvaluationNode())
        evaluator = wf.get_node("context_evaluator")
        assert evaluator is not None
        ctxs = [
            {"content": "a b c d e", "score": 0.95},
            {"content": "f g h i j", "score": 0.90},
            {"content": "k l m n o", "score": 0.80},
        ]
        out = self._run_context_evaluator(
            evaluator.config["code"],
            {"retrieved_contexts": ctxs, "query": "test"},
        )
        ctx_metrics = out["context_metrics"]
        assert ctx_metrics["precision_at_k"]["P@1"] == 1.0
        assert ctx_metrics["precision_at_k"]["P@3"] == 1.0
        # MRR — first relevant at rank 1 → 1.0.
        assert ctx_metrics["mrr"] == 1.0
        assert ctx_metrics["context_count"] == 3

    def test_p_at_k_with_mixed_relevance(self):
        """First two contexts < 0.7 → P@1 = 0, MRR = 1/3."""
        wf = _build(RAGEvaluationNode())
        evaluator = wf.get_node("context_evaluator")
        assert evaluator is not None
        ctxs = [
            {"content": "a", "score": 0.5},
            {"content": "b", "score": 0.6},
            {"content": "c", "score": 0.9},
        ]
        out = self._run_context_evaluator(
            evaluator.config["code"],
            {"retrieved_contexts": ctxs, "query": "test"},
        )
        ctx_metrics = out["context_metrics"]
        assert ctx_metrics["precision_at_k"]["P@1"] == 0.0
        # 1 relevant in top-3 → P@3 = 1/3.
        assert ctx_metrics["precision_at_k"]["P@3"] == pytest.approx(1 / 3)
        # First relevant at rank 3 → MRR = 1/3.
        assert ctx_metrics["mrr"] == pytest.approx(1 / 3)

    def test_mrr_zero_when_no_relevant_contexts(self):
        wf = _build(RAGEvaluationNode())
        evaluator = wf.get_node("context_evaluator")
        assert evaluator is not None
        ctxs = [{"content": "x", "score": 0.1}, {"content": "y", "score": 0.2}]
        out = self._run_context_evaluator(
            evaluator.config["code"],
            {"retrieved_contexts": ctxs, "query": "q"},
        )
        ctx_metrics = out["context_metrics"]
        assert ctx_metrics["mrr"] == 0.0

    def test_avg_relevance_is_arithmetic_mean(self):
        """avg_relevance_score = sum(scores) / len(scores)."""
        wf = _build(RAGEvaluationNode())
        evaluator = wf.get_node("context_evaluator")
        assert evaluator is not None
        ctxs = [
            {"content": "a", "score": 0.8},
            {"content": "b", "score": 0.6},
            {"content": "c", "score": 0.4},
        ]
        out = self._run_context_evaluator(
            evaluator.config["code"],
            {"retrieved_contexts": ctxs, "query": "q"},
        )
        # (0.8 + 0.6 + 0.4) / 3 = 0.6.
        assert out["context_metrics"]["avg_relevance_score"] == pytest.approx(0.6)


# ==========================================================================
# RAGEvaluationNode test_executor — honest pass-through (no fabrication)
# ==========================================================================


class TestTestExecutorPassThrough:
    """The test_executor codegen judges caller-provided results, not invented ones.

    Provably-correct remediation: the inner ``collect_rag_results`` MUST pass
    the caller's real ``generated_answer`` + ``retrieved_contexts`` through
    (no ``f"Generated answer for: {query}"`` fabrication, no hardcoded
    contexts) and MUST raise when those fields are absent.
    """

    @staticmethod
    def _exec_collector(code: str, test_queries: list) -> dict:
        """Exec the codegen with the helper preserved; return module `result`."""
        # Strip the F9 cleanup `del` so we can also assert on the namespace.
        code_no_del = "\n".join(
            line
            for line in code.splitlines()
            if not line.startswith("del collect_rag_results")
        )
        ns: dict = {"test_queries": test_queries}
        exec(code_no_del, ns)
        return ns["result"]

    def test_codegen_no_longer_fabricates_answers(self):
        """The fabrication template MUST be gone from the source."""
        wf = _build(RAGEvaluationNode())
        executor = wf.get_node("test_executor")
        assert executor is not None
        code = executor.config["code"]
        assert 'f"Generated answer for: {query}"' not in code
        assert "Context 1 about transformers" not in code

    def test_passes_through_caller_provided_results(self):
        wf = _build(RAGEvaluationNode())
        executor = wf.get_node("test_executor")
        assert executor is not None
        out = self._exec_collector(
            executor.config["code"],
            [
                {
                    "query": "What is BERT?",
                    "reference": "BERT is bidirectional...",
                    "generated_answer": "BERT is a transformer encoder.",
                    "retrieved_contexts": [
                        {"content": "BERT paper excerpt", "score": 0.92}
                    ],
                }
            ],
        )
        assert out["total_tests"] == 1
        tr = out["test_results"][0]
        # The caller's REAL answer + contexts survive verbatim.
        assert tr["generated_answer"] == "BERT is a transformer encoder."
        assert tr["retrieved_contexts"] == [
            {"content": "BERT paper excerpt", "score": 0.92}
        ]
        assert tr["query"] == "What is BERT?"
        assert tr["reference_answer"] == "BERT is bidirectional..."

    def test_missing_generated_answer_raises(self):
        wf = _build(RAGEvaluationNode())
        executor = wf.get_node("test_executor")
        assert executor is not None
        with pytest.raises(ValueError, match="generated_answer"):
            self._exec_collector(
                executor.config["code"],
                [{"query": "q", "retrieved_contexts": []}],
            )

    def test_missing_retrieved_contexts_raises(self):
        wf = _build(RAGEvaluationNode())
        executor = wf.get_node("test_executor")
        assert executor is not None
        with pytest.raises(ValueError, match="retrieved_contexts"):
            self._exec_collector(
                executor.config["code"],
                [{"query": "q", "generated_answer": "a"}],
            )


# ==========================================================================
# RAGBenchmarkNode.run() — REAL execution of a deterministic system
# ==========================================================================


class _DeterministicRagSystem:
    """A deterministic, runnable RAG system for benchmarking offline.

    NOT a mock: it satisfies the runtime runner contract (a callable accepting
    ``query=...`` returning a result dict) with deterministic output and a
    tiny real CPU cost, so RAGBenchmarkNode's REAL execution path is exercised
    without a network/LLM. Per ``rules/testing.md`` Tier-2 exception, a
    Protocol-satisfying deterministic adapter is NOT a mock.
    """

    def __init__(self, work: int = 200):
        self._work = work
        self.calls = 0

    def __call__(self, query=None, **kwargs):
        self.calls += 1
        # A small, real arithmetic loop so latency is measured (not synthetic).
        acc = 0
        for i in range(self._work):
            acc += i * i
        return {
            "answer": f"answer::{query}::{acc}",
            "retrieved_contexts": [{"content": "ctx", "score": 0.9}],
        }


class _NodeStyleRagSystem:
    """Deterministic runnable exposing ``.execute(**query)`` like a Core SDK Node."""

    def __init__(self, work: int = 200):
        self._inner = _DeterministicRagSystem(work=work)

    def execute(self, query=None, **kwargs):
        return self._inner(query=query, **kwargs)


class TestRAGBenchmarkRun:
    """Benchmark run() executes a REAL deterministic system end-to-end."""

    def test_run_single_system_returns_documented_shape(self):
        # Keep workload + users tiny so the per-test budget stays sub-second.
        node = RAGBenchmarkNode(workload_sizes=[2], concurrent_users=[1])
        system = _DeterministicRagSystem()
        out = node.run(
            rag_systems={"system_a": system},
            test_queries=[{"q": "1"}, {"q": "2"}, {"q": "3"}],
            duration=1,
        )
        assert "benchmark_results" in out
        assert "comparison" in out
        assert "test_configuration" in out
        sys_results = out["benchmark_results"]["system_a"]
        assert "latency_profiles" in sys_results
        assert "throughput_curves" in sys_results
        assert "resource_usage" in sys_results
        assert "scalability_analysis" in sys_results
        # The workload-size-2 latency profile reports p50/p95/p99/mean/std_dev.
        size_2 = sys_results["latency_profiles"]["size_2"]
        assert {"p50", "p95", "p99", "mean", "std_dev"}.issubset(set(size_2.keys()))
        # The system was REALLY executed: workload-2 + concurrency workload.
        assert system.calls > 0
        # resource_usage now carries a real measured memory_mb (tracemalloc).
        assert "memory_mb" in sys_results["resource_usage"]
        assert isinstance(sys_results["resource_usage"]["memory_mb"], float)

    def test_run_node_style_system_via_execute(self):
        """A system exposing ``.execute(**query)`` is run through that path."""
        node = RAGBenchmarkNode(workload_sizes=[2], concurrent_users=[1])
        system = _NodeStyleRagSystem()
        out = node.run(
            rag_systems={"node_sys": system},
            test_queries=[{"query": "a"}, {"query": "b"}],
            duration=1,
        )
        assert system._inner.calls > 0
        assert "node_sys" in out["benchmark_results"]

    def test_run_non_runnable_system_raises_typed_error(self):
        """A non-runnable 'system' (e.g. {}) raises — NO fabrication fallback."""
        node = RAGBenchmarkNode(workload_sizes=[2], concurrent_users=[1])
        with pytest.raises(TypeError, match="cannot execute system"):
            node.run(
                rag_systems={"bad": {}},
                test_queries=[{"q": "1"}, {"q": "2"}],
                duration=1,
            )

    def test_run_multi_system_picks_comparison_keys(self):
        node = RAGBenchmarkNode(workload_sizes=[2], concurrent_users=[1])
        out = node.run(
            rag_systems={
                "system_a": _DeterministicRagSystem(work=50),
                "system_b": _DeterministicRagSystem(work=400),
            },
            test_queries=[{"q": "1"}, {"q": "2"}, {"q": "3"}],
            duration=1,
        )
        comparison = out["comparison"]
        # All three winner-keys are populated (no None when ≥1 system).
        assert comparison["fastest_system"] in {"system_a", "system_b"}
        assert comparison["most_scalable"] in {"system_a", "system_b"}
        assert comparison["most_efficient"] in {"system_a", "system_b"}
        # Recommendations enumerate the three winners.
        assert len(comparison["recommendations"]) == 3

    def test_run_empty_systems_returns_null_winner_shape(self):
        """Zero systems → null-winner comparison, no crash on empty mapping."""
        node = RAGBenchmarkNode(workload_sizes=[2], concurrent_users=[1])
        out = node.run(rag_systems={}, test_queries=[{"q": "1"}], duration=1)
        assert out["benchmark_results"] == {}
        assert out["comparison"]["fastest_system"] is None
        assert out["comparison"]["most_scalable"] is None
        assert out["comparison"]["most_efficient"] is None

    def test_run_test_configuration_carries_constructor_state(self):
        node = RAGBenchmarkNode(workload_sizes=[2], concurrent_users=[1])
        out = node.run(
            rag_systems={"system_a": _DeterministicRagSystem()},
            test_queries=[{"q": "1"}, {"q": "2"}],
            duration=5,
        )
        cfg = out["test_configuration"]
        assert cfg["workload_sizes"] == [2]
        assert cfg["concurrent_users"] == [1]
        assert cfg["duration"] == 5
        assert cfg["num_queries"] == 2

    def test_run_test_configuration_carries_duration_exceeded_flag(self):
        """A fast run reports duration_exceeded=False (the budget held)."""
        node = RAGBenchmarkNode(workload_sizes=[2], concurrent_users=[1])
        out = node.run(
            rag_systems={"system_a": _DeterministicRagSystem()},
            test_queries=[{"q": "1"}, {"q": "2"}],
            duration=30,
        )
        assert out["test_configuration"]["duration_exceeded"] is False


class TestMostScalableRankingDirection:
    """Direction-pin for the `most_scalable` ranking (deterministic, no timing).

    `parallel_speedup` is HIGHER = better (≈ achieved concurrency). The
    ranking MUST select the system with the GREATEST mean speedup. A prior
    cut ranked with `min`, silently crowning the LEAST-scalable system; this
    test crafts `_compare_systems` input directly so the assertion locks the
    direction without depending on thread-scheduling timing.
    """

    @staticmethod
    def _system_block(speedups: list[float]) -> dict:
        return {
            "latency_profiles": {"size_2": {"mean": 0.01}},
            "throughput_curves": {"size_2": 100.0},
            "resource_usage": {"memory_mb": 1.0},
            "scalability_analysis": {
                f"users_{i}": {
                    "avg_latency": 0.01,
                    "concurrent_throughput": 50.0,
                    "parallel_speedup": s,
                    "timed_out": False,
                }
                for i, s in enumerate(speedups, start=1)
            },
        }

    def test_most_scalable_is_the_highest_mean_speedup(self):
        node = RAGBenchmarkNode()
        results = {
            "scalable": self._system_block([7.8, 8.2]),  # mean 8.0 — best
            "serial": self._system_block([1.1, 1.0]),  # mean ~1.05 — worst
        }
        comparison = node._compare_systems(results)  # type: ignore[attr-defined]
        assert comparison["most_scalable"] == "scalable"

    def test_no_scalability_data_defaults_to_zero_not_winner(self):
        """A system with no concurrency data (speedup default 0.0) cannot win."""
        node = RAGBenchmarkNode()
        results = {
            "has_data": self._system_block([3.0]),
            "no_data": {
                "latency_profiles": {"size_2": {"mean": 0.01}},
                "throughput_curves": {"size_2": 100.0},
                "resource_usage": {"memory_mb": 1.0},
                "scalability_analysis": {},  # no concurrency measured
            },
        }
        comparison = node._compare_systems(results)  # type: ignore[attr-defined]
        assert comparison["most_scalable"] == "has_data"


# ==========================================================================
# TestDatasetGeneratorNode.run() deterministic paths
# ==========================================================================


class TestTestDatasetGeneratorRun:
    """Seeded-RNG paths produce reproducible test fixtures."""

    def test_run_with_seed_reproducible(self):
        """Same seed → same generated dataset."""
        node_a = TestDatasetGeneratorNode(include_adversarial=False)
        node_b = TestDatasetGeneratorNode(include_adversarial=False)
        out_a = node_a.run(num_samples=5, seed=42)
        out_b = node_b.run(num_samples=5, seed=42)
        # The deterministic seed makes the queries identical.
        queries_a = [t["query"] for t in out_a["test_dataset"]]
        queries_b = [t["query"] for t in out_b["test_dataset"]]
        assert queries_a == queries_b

    def test_run_returns_documented_shape(self):
        node = TestDatasetGeneratorNode(include_adversarial=False)
        out = node.run(num_samples=3, seed=7)
        assert "test_dataset" in out
        assert "statistics" in out
        assert "generation_config" in out
        assert out["statistics"]["total_samples"] == 3
        # Every entry has the documented fields.
        for entry in out["test_dataset"]:
            assert "id" in entry
            assert "query" in entry
            assert "reference_answer" in entry
            assert "contexts" in entry
            assert "metadata" in entry
            assert entry["metadata"]["category"] in {
                "factual",
                "analytical",
                "comparative",
            }

    def test_run_with_machine_learning_domain_uses_ml_concepts(self):
        """Domain 'machine learning' picks from the ML concept list."""
        node = TestDatasetGeneratorNode(
            categories=["factual"], include_adversarial=False
        )
        out = node.run(num_samples=10, domain="machine learning", seed=1)
        # Every "What is X?" question's X MUST be from the ML concept list.
        ml_concepts = {
            "neural networks",
            "transformers",
            "BERT",
            "attention mechanism",
            "backpropagation",
        }
        what_is_queries = [
            q["query"] for q in out["test_dataset"] if q["query"].startswith("What is ")
        ]
        # At least one query was generated against the ML concept set.
        assert len(what_is_queries) >= 1
        for q in what_is_queries:
            # Extract the X in "What is X?" — strip leading "What is " and trailing "?".
            extracted = q[len("What is ") :].rstrip("?")
            assert (
                extracted in ml_concepts
            ), f"query '{q}' did not pick an ML concept (extracted: '{extracted}')"

    def test_run_include_adversarial_false_emits_no_adversarial_entries(self):
        node = TestDatasetGeneratorNode(include_adversarial=False)
        out = node.run(num_samples=20, seed=99)
        # With adversarial off, zero entries carry the adversarial_type tag.
        assert out["statistics"]["adversarial_count"] == 0
        for entry in out["test_dataset"]:
            assert "adversarial_type" not in entry["metadata"]

    def test_run_category_distribution_matches_constructor_categories(self):
        node = TestDatasetGeneratorNode(
            categories=["factual"], include_adversarial=False
        )
        out = node.run(num_samples=10, seed=3)
        # Only "factual" entries when categories=["factual"].
        dist = out["statistics"]["category_distribution"]
        assert dist["factual"] == 10
        # No analytical / comparative entries — the category dict only has the
        # configured key.
        assert set(dist.keys()) == {"factual"}


# ==========================================================================
# Module-level __all__ contract
# ==========================================================================


def test_module_all_exports_three_classes():
    """The module exports exactly the 3 documented classes."""
    from kaizen.nodes.rag import evaluation

    assert set(evaluation.__all__) == {
        "RAGEvaluationNode",
        "RAGBenchmarkNode",
        "TestDatasetGeneratorNode",
    }
