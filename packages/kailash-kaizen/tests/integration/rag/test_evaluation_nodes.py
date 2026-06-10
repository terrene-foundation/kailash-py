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

import threading
import time
import tracemalloc

import pytest
from kailash.nodes.base import Node
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
        #
        # OUTPUT-side fix: the aggregator now receives PARSED per-test score
        # LISTS (the response-parser nodes already did `response -> .content ->
        # json.loads`). So `faithfulness_scores` is a bare list of per-test score
        # dicts `[{"faithfulness_score": 0.9}, ...]` — NO `{"response": {...}}`
        # wrapper (that wrapper was the parse-gap the parser nodes now strip).
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
                        {"faithfulness_score": 0.9},
                        {"faithfulness_score": 0.7},
                    ],
                    "relevance_scores": [
                        {"relevance_score": 0.8},
                        {"relevance_score": 0.6},
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
# RAGBenchmarkNode — REAL system execution under the real Python runtime
# ==========================================================================


class _DeterministicRagNode(Node):
    """A real, runnable Core SDK Node used as the deterministic system-under-test.

    Per ``rules/testing.md`` Tier-2 exception: a Protocol-satisfying
    deterministic adapter (a real ``Node`` with deterministic output and a
    tiny real CPU cost) is NOT a mock. RAGBenchmarkNode executes it through
    the genuine ``Node.execute(**query)`` path, so the benchmark measures
    REAL latency / throughput / memory — no ``@patch`` / ``MagicMock``.
    """

    def __init__(self, name: str = "det_rag", work: int = 500):
        super().__init__(name=name)
        self._work = work
        self.calls = 0

    def get_parameters(self):
        from kailash.nodes.base import NodeParameter

        return {
            "query": NodeParameter(
                name="query",
                type=str,
                required=False,
                default="",
                description="Query to answer",
            ),
        }

    def run(self, **kwargs):
        self.calls += 1
        query = kwargs.get("query", "")
        acc = 0
        for i in range(self._work):
            acc += i * i
        return {
            "answer": f"answer::{query}::{acc}",
            "retrieved_contexts": [{"content": "ctx", "score": 0.9}],
        }


class TestRAGBenchmarkRealRuntime:
    """RAGBenchmarkNode.run() executes a REAL Node and measures real metrics.

    No mock — the run() body executes the deterministic Node via the genuine
    Core SDK ``Node.execute`` path and measures latency via
    ``time.perf_counter()``, throughput, and memory via ``tracemalloc``.
    """

    def test_run_produces_comparison_winners_for_each_axis(self):
        node = RAGBenchmarkNode(workload_sizes=[2], concurrent_users=[1])
        out = node.run(
            rag_systems={
                "sys_alpha": _DeterministicRagNode(name="alpha", work=100),
                "sys_beta": _DeterministicRagNode(name="beta", work=800),
            },
            test_queries=[{"query": "1"}, {"query": "2"}],
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

    def test_run_measures_real_latency_and_throughput(self):
        """Real measured latency > 0 and real throughput > 0 (no synthetic data)."""
        system = _DeterministicRagNode(name="only", work=1000)
        node = RAGBenchmarkNode(workload_sizes=[3], concurrent_users=[2])
        out = node.run(
            rag_systems={"only": system},
            test_queries=[{"query": "1"}, {"query": "2"}, {"query": "3"}],
            duration=1,
        )
        sys_results = out["benchmark_results"]["only"]
        size_3 = sys_results["latency_profiles"]["size_3"]
        # Real measured latency: a real CPU loop took nonzero wall-clock.
        assert size_3["mean"] > 0
        assert size_3["p50"] > 0
        # Real throughput: queries / real elapsed > 0.
        assert sys_results["throughput_curves"]["size_3"] > 0
        # Real concurrency exercised the system via the thread pool.
        assert "users_2" in sys_results["scalability_analysis"]
        assert sys_results["scalability_analysis"]["users_2"]["avg_latency"] > 0
        # Real peak memory measured by tracemalloc.
        assert sys_results["resource_usage"]["memory_mb"] >= 0
        # The system was REALLY executed (workload-3 + concurrency workload).
        assert system.calls >= 3

    def test_run_non_runnable_system_raises_no_fabrication(self):
        """A non-runnable system raises — there is NO synthetic-metric fallback."""
        node = RAGBenchmarkNode(workload_sizes=[2], concurrent_users=[1])
        with pytest.raises(TypeError, match="cannot execute system"):
            node.run(
                rag_systems={"bad": object()},
                test_queries=[{"query": "1"}, {"query": "2"}],
                duration=1,
            )

    def test_run_io_bound_system_measures_real_parallel_speedup(self):
        """An IO-bound system under real concurrency shows speedup > 1.

        Proves `parallel_speedup` measures genuine concurrency (higher = better):
        `time.sleep` releases the GIL, so N concurrent queries overlap and the
        amortized wall-clock per query drops well below the per-query latency.
        """
        node = RAGBenchmarkNode(workload_sizes=[4], concurrent_users=[4])
        out = node.run(
            rag_systems={"io": _IOBoundRagNode(name="io", sleep_s=0.05)},
            test_queries=[{"query": str(i)} for i in range(4)],
            duration=30,
        )
        speedup = out["benchmark_results"]["io"]["scalability_analysis"]["users_4"][
            "parallel_speedup"
        ]
        # 4 overlapping 0.05s sleeps → amortized wall-clock per query ≈ 0.0125s
        # vs ~0.05s measured latency → speedup ≈ 4. Assert a robust floor.
        assert speedup > 1.5


class _RaisingRagNode(Node):
    """A real Node whose run() raises — exercises the tracemalloc try/finally."""

    def get_parameters(self):
        from kailash.nodes.base import NodeParameter

        return {
            "query": NodeParameter(
                name="query", type=str, required=False, default="", description="q"
            )
        }

    def run(self, **kwargs):
        raise RuntimeError("system boom")


class _IOBoundRagNode(Node):
    """A real IO-bound Node (sleeps, releasing the GIL) for concurrency tests."""

    def __init__(self, name: str = "io_rag", sleep_s: float = 0.05):
        super().__init__(name=name)
        self._sleep_s = sleep_s

    def get_parameters(self):
        from kailash.nodes.base import NodeParameter

        return {
            "query": NodeParameter(
                name="query", type=str, required=False, default="", description="q"
            )
        }

    def run(self, **kwargs):
        time.sleep(self._sleep_s)
        return {"answer": "io", "retrieved_contexts": []}


class _ReleasableSlowRagNode(Node):
    """A real Node that blocks until released — models a wedged system whose
    worker thread the test can drain WITHIN its window (so no orphan thread
    survives to log against a closed capture stream). The internal
    ``wait(timeout)`` is a hard safety cap so a forgotten release cannot hang."""

    def __init__(self, name: str = "wedged_rag"):
        super().__init__(name=name)
        self.release = threading.Event()

    def get_parameters(self):
        from kailash.nodes.base import NodeParameter

        return {
            "query": NodeParameter(
                name="query", type=str, required=False, default="", description="q"
            )
        }

    def run(self, **kwargs):
        # Blocks past any sane benchmark budget; released explicitly by the test.
        self.release.wait(timeout=10.0)
        return {"answer": "wedged", "retrieved_contexts": []}


class TestRAGBenchmarkResourceSafety:
    """Resource-safety of the real-execution path (security-review R1 fixes)."""

    def test_raising_system_does_not_leak_tracemalloc(self):
        """A system that raises mid-benchmark propagates AND leaves tracemalloc
        in its prior state — the per-system try/finally stops tracing on the
        exception path (no process-global leak).

        The exact exception type the Core SDK ``Node.execute`` surfaces (raw
        ``RuntimeError`` vs wrapped ``NodeExecutionError``) is SDK behavior; the
        invariant under test is PROPAGATION (no swallow) + tracemalloc cleanup.
        """
        was_tracing = tracemalloc.is_tracing()
        node = RAGBenchmarkNode(workload_sizes=[1], concurrent_users=[1])
        raised = None
        try:
            node.run(
                rag_systems={"boom": _RaisingRagNode(name="boom")},
                test_queries=[{"query": "1"}],
                duration=5,
            )
        except Exception as exc:  # noqa: BLE001 — assert the failure propagated
            raised = exc
        assert raised is not None, "the raising system must propagate, not swallow"
        chained = f"{raised}|{raised.__cause__}|{raised.__context__}"
        assert "system boom" in chained
        # The per-system try/finally stopped tracing despite the exception.
        assert tracemalloc.is_tracing() == was_tracing

    def test_duration_budget_caps_wedged_system(self):
        """A wedged system must NOT hang run() — the `duration` wall-clock cap
        bounds the sequential path via a bounded future, and `duration_exceeded`
        is reported honestly. The wedged worker is released + drained INSIDE the
        test window so no orphan thread logs against a closed capture stream."""
        wedged = _ReleasableSlowRagNode(name="slow")
        node = RAGBenchmarkNode(workload_sizes=[1], concurrent_users=[1])
        try:
            start = time.perf_counter()
            out = node.run(
                rag_systems={"slow": wedged},
                test_queries=[{"query": "1"}],
                duration=1,
            )
            elapsed = time.perf_counter() - start
            # Bounded near the 1s budget, NOT the (≤10s) the wedged system blocks.
            assert elapsed < 1.4
            assert out["test_configuration"]["duration_exceeded"] is True
            # tracemalloc not left tracing after the timeout path.
            assert tracemalloc.is_tracing() is False
        finally:
            # Release the wedged worker and let it drain (run() returns + the SDK
            # success-log flushes) while this test's capture stream is still open.
            wedged.release.set()
            time.sleep(0.2)


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


# ==========================================================================
# RAGEvaluationNode — L3 fix: every LLM judge MUST consume the real evaluation
# data (query / retrieved contexts / generated answer / reference answer) via
# the VALID `messages` port — NOT score from `system_prompt` alone.
# ==========================================================================


class TestEvaluationContextReachesLLM:
    """L3 contract: each of the 3 LLM judges (faithfulness / relevance /
    answer-quality) MUST receive the REAL evaluation data via a well-formed
    ``messages`` list.

    Pre-fix every judge consumed context ONLY via the phantom ``test_data``
    port (``LLMAgentNode.run`` reads context EXCLUSIVELY through
    ``kwargs["messages"]``), so the query / retrieved contexts / generated
    answer / reference answer were silently dropped and each judge scored from
    its ``system_prompt`` alone — the ``metric_aggregator`` then computed
    statistics over fabricated scores. The fix inserts a
    ``PythonCodeNode.from_function`` messages-composer upstream of each judge
    that renders the real fields into an OpenAI-format ``messages`` list wired
    to the VALID ``messages`` port.

    This suite proves, under the real ``LocalRuntime``, that each composer
    publishes a ``messages`` list embedding the real evaluation data and feeds
    the judge's ``messages`` input — structural + behavioral probes, no LLM
    judgment, no graph surgery, no ``unittest.mock``.

    ── OUTPUT-SIDE FIX (this shard) — parse-gap + batch-vs-per-test closed ────
    The judge publishes its answer on the ``response`` port as a dict shaped
    ``{"content": "<JSON string>", ...}``; ``LLMAgentNode`` does NOT parse that
    JSON into top-level ports. The OUTPUT-side fix inserts a ``from_function``
    response-parser downstream of EACH judge that reads ``response`` ->
    ``.content`` -> ``json.loads`` -> a per-test list of score dicts (the judge
    now returns a JSON ARRAY, one element per numbered test). The aggregator
    indexes the REAL parsed ``faithfulness_score`` / ``relevance_score`` /
    ``overall_quality`` per test — closing BOTH (1) the parse-gap (the prior
    aggregator read ``.get("response", {}).get("faithfulness_score", 0)`` and
    defaulted every score to a fabricated 0) AND (2) the batch-vs-per-test
    single-``response``->list-indexed mismatch. Malformed / non-JSON judge
    output is FLAGGED by the parser, not silently zeroed (zero-tolerance Rule 2).
    ``TestEvaluationScoresFlowEndToEnd`` below proves the real parsed score
    reaches the aggregator's mean (the parse-gap closure) AND that per-test
    scores flow for a multi-test batch (the batch-vs-per-test closure).
    """

    # Grep-able sentinels distinct from system-prompt text and each other.
    CTX_SENTINEL = "SENTINEL_CTX_71"
    QUERY = "How does the TRANSFORMER_QUERY_SENTINEL attention mechanism work?"
    ANSWER = "Transformers use ANSWER_SENTINEL self-attention mechanisms."
    REFERENCE = "Self-attention is the REFERENCE_SENTINEL core of transformers."

    def _test_queries(self):
        return [
            {
                "query": self.QUERY,
                "reference": self.REFERENCE,
                "generated_answer": self.ANSWER,
                "retrieved_contexts": [
                    {
                        "content": f"{self.CTX_SENTINEL} attention is all you need",
                        "score": 0.95,
                    },
                    {"content": "BERT is a bidirectional encoder.", "score": 0.40},
                ],
            }
        ]

    def _run(self, node):
        """Exercise the PRODUCTION delivery path.

        ``test_queries`` is supplied as a TOP-LEVEL workflow input so the
        parameter-injector auto-distributes it to ``test_executor`` (whose
        ``get_parameters()`` advertises ``test_queries``) — the same path a real
        ``WorkflowNode`` caller uses. The judges receive ONLY operational config
        (``provider`` / ``model``) node-keyed; the load-bearing evaluation DATA
        flows test_queries → test_executor → composer → judge.messages, NOT via
        node-keyed injection of the content (the Wave-1 MED-2 false-green trap).
        """
        wf = node._create_workflow()  # type: ignore[attr-defined]
        params = {
            "test_queries": self._test_queries(),
            "faithfulness_evaluator": {"provider": "mock", "model": "mock-model"},
            "relevance_evaluator": {"provider": "mock", "model": "mock-model"},
        }
        if node.use_reference_answers:  # type: ignore[attr-defined]
            params["answer_quality_evaluator"] = {
                "provider": "mock",
                "model": "mock-model",
            }
        with LocalRuntime() as rt:
            results, _ = rt.execute(wf, parameters=params)
        return results

    @staticmethod
    def _composer_blob(results, composer_id):
        comp = results.get(composer_id)
        assert isinstance(comp, dict), (
            f"{composer_id} node missing — judge context still wired to the "
            f"phantom `test_data` port (L3 defect). keys={list(results)}"
        )
        messages = comp["result"]["messages"]
        assert isinstance(messages, list) and messages, f"empty messages: {comp}"
        for m in messages:
            assert (
                isinstance(m, dict) and "role" in m and "content" in m
            ), f"malformed message (not OpenAI {{role,content}} shape): {m!r}"
        return "\n".join(str(m.get("content", "")) for m in messages)

    # ── Checklist item 1: EVERY one of the 3 judges receives context via
    # `messages`, not just faithfulness. ──────────────────────────────────────

    def test_faithfulness_judge_messages_embed_contexts_and_answer(self):
        """The faithfulness judge MUST see the retrieved contexts + generated
        answer (it scores grounding). RED pre-fix: no composer; judge fed
        phantom ``test_data``. GREEN post-fix: composer embeds the real data.
        """
        results = self._run(RAGEvaluationNode(use_reference_answers=False))
        blob = self._composer_blob(results, "faithfulness_messages_composer")
        assert (
            self.CTX_SENTINEL in blob
        ), f"retrieved context did NOT reach the faithfulness judge: {blob!r}"
        assert (
            "ANSWER_SENTINEL" in blob
        ), f"generated answer did NOT reach the faithfulness judge: {blob!r}"
        # The judge actually ran (received the messages, not unbound).
        assert results.get("faithfulness_evaluator", {}).get("response") is not None

    def test_relevance_judge_messages_embed_query_and_answer(self):
        """The relevance judge MUST see the query + generated answer (it scores
        answer-to-query relevance)."""
        results = self._run(RAGEvaluationNode(use_reference_answers=False))
        blob = self._composer_blob(results, "relevance_messages_composer")
        assert (
            "TRANSFORMER_QUERY_SENTINEL" in blob
        ), f"query did NOT reach the relevance judge: {blob!r}"
        assert (
            "ANSWER_SENTINEL" in blob
        ), f"generated answer did NOT reach the relevance judge: {blob!r}"
        assert results.get("relevance_evaluator", {}).get("response") is not None

    def test_answer_quality_judge_messages_embed_generated_and_reference(self):
        """The answer-quality judge (use_reference_answers=True) MUST see BOTH
        the generated answer AND the reference answer (it compares them)."""
        results = self._run(RAGEvaluationNode(use_reference_answers=True))
        blob = self._composer_blob(results, "answer_quality_messages_composer")
        assert (
            "ANSWER_SENTINEL" in blob
        ), f"generated answer did NOT reach the answer-quality judge: {blob!r}"
        assert (
            "REFERENCE_SENTINEL" in blob
        ), f"reference answer did NOT reach the answer-quality judge: {blob!r}"
        assert results.get("answer_quality_evaluator", {}).get("response") is not None

    # ── Structural guards: each judge fed the VALID `messages` port, NOT the
    # phantom `test_data` port. These regress to RED if the composer→messages
    # edge is stripped (the load-bearing production wiring). ───────────────────

    @pytest.mark.parametrize(
        "use_ref,judge_id,composer_id",
        [
            (False, "faithfulness_evaluator", "faithfulness_messages_composer"),
            (False, "relevance_evaluator", "relevance_messages_composer"),
            (True, "answer_quality_evaluator", "answer_quality_messages_composer"),
        ],
    )
    def test_judge_wired_to_messages_not_phantom_test_data(
        self, use_ref, judge_id, composer_id
    ):
        wf = _build(RAGEvaluationNode(use_reference_answers=use_ref))
        feeders = [c for c in wf.connections if c.target_node == judge_id]
        assert feeders, f"{judge_id} has no inbound connections"
        # No judge may be fed the phantom `test_data` port (silently dropped).
        bad = [c for c in feeders if c.target_input == "test_data"]
        assert not bad, (
            f"{judge_id} still fed via phantom `test_data` — LLMAgentNode reads "
            f"context only via `messages`, so `test_data` is silently dropped."
        )
        # The composer MUST feed the valid `messages` port.
        msg_feeders = [
            c
            for c in feeders
            if c.target_input == "messages" and c.source_node == composer_id
        ]
        assert msg_feeders, (
            f"{composer_id} is not wired to {judge_id}'s `messages` port. "
            f"feeders={[(c.source_node, c.target_input) for c in feeders]}"
        )

    # ── OUTPUT-side fix: the aggregator now reaches a real evaluation_summary
    # because the response-parser nodes feed it parsed per-test score lists.
    # (Replaces the retired `test_aggregator_list_shape_limitation_is_surfaced`
    #  xfail — orphan-detection Rule 4a: implementing the deferred limitation
    #  sweeps the deferral test in the same change.) ────────────────────────────

    def test_aggregator_reaches_evaluation_summary_under_mock_judges(self):
        """End-to-end under the real ``LocalRuntime`` with the production mock
        provider, ``metric_aggregator`` now PRODUCES an ``evaluation_summary``
        dict — the prior single-``response``->list-indexed ``KeyError: 0`` is
        gone because each judge's ``response`` flows through a response-parser
        that yields the per-test list shape the aggregator indexes.

        The mock provider does NOT return judge JSON, so the parser FLAGS the
        non-JSON content (``parse_gaps`` populated) — the honest behavior: the
        summary is produced, the means are computed only over real scores (here
        none, since the mock judge emits prose), and the gap is surfaced rather
        than counted as fabricated zeros. The scored-content assertion lives in
        ``TestEvaluationScoresFlowEndToEnd`` with a deterministic JSON judge."""
        results = self._run(RAGEvaluationNode(use_reference_answers=False))
        agg = results.get("metric_aggregator", {})
        summary = agg.get("result", {}).get("evaluation_summary")
        assert summary is not None, (
            "metric_aggregator did not produce evaluation_summary — the "
            "response-parser per-test list wiring should make it indexable."
        )
        # Honest gap surface: the mock judge emitted prose, not JSON, so the
        # faithfulness/relevance scores were FLAGGED (not fabricated zeros).
        assert "parse_gaps" in summary
        assert summary["parse_gaps"].get("faithfulness")
        assert summary["parse_gaps"].get("relevance")


# ==========================================================================
# OUTPUT-side fix — REAL parsed scores flow judge -> parser -> aggregator.
#
# Protocol-Satisfying Deterministic Adapter (legal Tier-2 exception per
# `rules/testing.md` § 3-Tier Testing): a real ``Node`` subclass that publishes
# the production ``response`` port shape (``{"content": "<JSON string>", ...}``)
# with a KNOWN judge JSON array. This is NOT a mock — the runtime, the workflow,
# the wiring, the response-parser, and the aggregator are all REAL; only the
# judge's text content is made deterministic so the per-test score is known.
# ==========================================================================


class _DeterministicJsonJudge(Node):
    """Real ``LLMAgentNode`` substitute whose ``response.content`` is a KNOWN
    JSON ARRAY of per-test scores, keyed by the graph node_id.

    Publishes the EXACT production ``response`` port shape
    (``{"content": "<json string>", ...}``) so the real response-parser node
    exercises its real ``response -> .content -> json.loads`` path. Per
    ``rules/testing.md`` § Tier 2 Protocol-Satisfying Deterministic Adapter
    exception, this IS NOT a mock — it inherits the real ``Node`` base and
    satisfies the full runtime contract with deterministic output.

    Dispatch is keyed on ``self.id`` (the graph node_id WorkflowBuilder
    assigns), so each judge (faithfulness / relevance / answer_quality) routes
    to its own known per-test JSON array. The number of array elements aligns
    1:1 with the number of numbered tests in the batch (set by the test).
    """

    # Per-judge known scores, one object per test. The test sets how many
    # tests; these arrays are sized to the multi-test batch the test feeds.
    _SCORES = {
        "faithfulness_evaluator": [
            {"faithfulness_score": 0.8},
            {"faithfulness_score": 0.6},
        ],
        "relevance_evaluator": [
            {"relevance_score": 0.7},
            {"relevance_score": 0.5},
        ],
        "answer_quality_evaluator": [
            {"overall_quality": 0.9},
            {"overall_quality": 0.4},
        ],
    }

    def __init__(self, *args, **kwargs):
        for k in ("system_prompt", "model", "provider", "temperature"):
            kwargs.pop(k, None)
        super().__init__(*args, **kwargs)

    def get_parameters(self):
        from kailash.nodes.base import NodeParameter

        return {
            "messages": NodeParameter(
                name="messages",
                type=list,
                required=False,
                default=[],
                description="LLM chat messages (deterministic substitute ignores)",
            ),
        }

    def run(self, **_kwargs):
        import json

        scores = self._SCORES.get(self.id, [])
        # Publish the production `response` port shape: the judge's text lives
        # in `content` as a JSON STRING (NOT a pre-parsed structure) — exactly
        # what LLMAgentNode emits — so the real parser must json.loads it.
        return {"response": {"content": json.dumps(scores), "role": "assistant"}}


class _GarbageFaithfulnessJudge(_DeterministicJsonJudge):
    """Same deterministic judge, but the faithfulness judge returns NON-JSON
    prose (an honest "I cannot evaluate" refusal) so faithfulness is FULLY
    parse-gapped while relevance + context_precision remain real. Used to prove
    the overall_score roll-up EXCLUDES the gapped metric rather than averaging
    in a fabricated 0 (the MED-1 honesty invariant)."""

    def run(self, **_kwargs):
        import json

        if self.id == "faithfulness_evaluator":
            return {
                "response": {
                    "content": "I cannot evaluate this — no JSON here.",
                    "role": "assistant",
                }
            }
        scores = self._SCORES.get(self.id, [])
        return {"response": {"content": json.dumps(scores), "role": "assistant"}}


class TestEvaluationScoresFlowEndToEnd:
    """The parse-gap is closed: REAL parsed judge scores reach the aggregator's
    mean, AND per-test scores flow for a multi-test batch.

    RED pre-fix proof: the prior aggregator read
    ``faithfulness_scores[i].get("response", {}).get("faithfulness_score", 0)``
    against the raw ``response`` dict, where ``faithfulness_score`` lives INSIDE
    ``response["content"]``'s JSON string — so the ``.get`` always missed and
    every mean defaulted to 0. The OUTPUT-side fix routes the judge's
    ``response`` through a parser (``response -> .content -> json.loads -> list``)
    and the aggregator indexes the real per-test scores. This suite asserts the
    mean equals the KNOWN deterministic value (≈ 0.8 faithfulness for test 0),
    NOT 0 — the load-bearing proof the parse-gap is closed.
    """

    def _two_test_queries(self):
        return [
            {
                "query": "What is attention?",
                "reference": "Attention weights inputs.",
                "generated_answer": "Attention weights the inputs by relevance.",
                "retrieved_contexts": [
                    {"content": "Attention is all you need.", "score": 0.95},
                ],
            },
            {
                "query": "What is BERT?",
                "reference": "BERT is a bidirectional encoder.",
                "generated_answer": "BERT is a transformer encoder.",
                "retrieved_contexts": [
                    {"content": "BERT paper excerpt.", "score": 0.88},
                ],
            },
        ]

    @pytest.fixture
    def deterministic_judges(self, monkeypatch):
        """Register the deterministic JSON judge under the ``"LLMAgentNode"``
        NodeRegistry key the inner workflow's ``add_node("LLMAgentNode", ...)``
        resolves through. Restores the prior binding on teardown."""
        from kailash.nodes.base import NodeRegistry

        nodes_dict = NodeRegistry._nodes  # type: ignore[attr-defined]
        prior = nodes_dict.get("LLMAgentNode")
        nodes_dict["LLMAgentNode"] = _DeterministicJsonJudge
        try:
            yield _DeterministicJsonJudge
        finally:
            if prior is None:
                nodes_dict.pop("LLMAgentNode", None)
            else:
                nodes_dict["LLMAgentNode"] = prior

    def _run(self, use_reference_answers: bool):
        node = RAGEvaluationNode(use_reference_answers=use_reference_answers)
        wf = node._create_workflow()  # type: ignore[attr-defined]
        with LocalRuntime() as rt:
            results, _ = rt.execute(
                wf, parameters={"test_queries": self._two_test_queries()}
            )
        return results

    def test_real_faithfulness_mean_is_parsed_not_zero(self, deterministic_judges):
        """The aggregator's mean faithfulness ≈ (0.8 + 0.6)/2 = 0.7 — the REAL
        parsed scores, NOT the fabricated 0 the parse-gap produced."""
        results = self._run(use_reference_answers=False)
        summary = results["metric_aggregator"]["result"]["evaluation_summary"]
        agg = summary["aggregate_metrics"]
        # Load-bearing: a REAL parsed mean, NOT 0.
        assert agg["faithfulness"]["mean"] == pytest.approx(0.7)
        assert agg["faithfulness"]["mean"] != 0
        # Relevance: (0.7 + 0.5)/2 = 0.6.
        assert agg["relevance"]["mean"] == pytest.approx(0.6)
        # No parse gaps — the deterministic judge returned valid JSON arrays.
        assert summary["parse_gaps"].get("faithfulness") is None
        assert summary["parse_gaps"].get("relevance") is None

    def test_per_test_scores_flow_for_multi_test_batch(self, deterministic_judges):
        """The batch-vs-per-test fix: BOTH per-test scores reach the aggregator,
        so the stored per-test score list has one entry per test (not one
        batched value duplicated or a KeyError)."""
        results = self._run(use_reference_answers=False)
        summary = results["metric_aggregator"]["result"]["evaluation_summary"]
        faith_scores = summary["aggregate_metrics"]["faithfulness"]["scores"]
        # Exactly the two known per-test scores flowed through, in order.
        assert faith_scores == [pytest.approx(0.8), pytest.approx(0.6)]
        rel_scores = summary["aggregate_metrics"]["relevance"]["scores"]
        assert rel_scores == [pytest.approx(0.7), pytest.approx(0.5)]

    def test_answer_quality_real_mean_with_reference(self, deterministic_judges):
        """With use_reference_answers=True the answer-quality judge's parsed
        per-test ``overall_quality`` reaches the aggregator mean (0.9+0.4)/2."""
        results = self._run(use_reference_answers=True)
        summary = results["metric_aggregator"]["result"]["evaluation_summary"]
        aq = summary["aggregate_metrics"]["answer_quality"]
        assert aq["mean"] == pytest.approx(0.65)
        assert aq["scores"] == [pytest.approx(0.9), pytest.approx(0.4)]

    @pytest.fixture
    def garbage_faithfulness_judges(self, monkeypatch):
        """Register the judge whose faithfulness response is non-JSON prose
        (fully parse-gapped) while relevance + context stay real."""
        from kailash.nodes.base import NodeRegistry

        nodes_dict = NodeRegistry._nodes  # type: ignore[attr-defined]
        prior = nodes_dict.get("LLMAgentNode")
        nodes_dict["LLMAgentNode"] = _GarbageFaithfulnessJudge
        try:
            yield _GarbageFaithfulnessJudge
        finally:
            if prior is None:
                nodes_dict.pop("LLMAgentNode", None)
            else:
                nodes_dict["LLMAgentNode"] = prior

    def test_overall_score_excludes_parse_gapped_metric_not_fabricated_zero(
        self, garbage_faithfulness_judges
    ):
        """MED-1 honesty: when faithfulness is FULLY parse-gapped, overall_score
        rolls up only the metrics with a REAL mean (relevance +
        context_precision) — it MUST NOT average in a fabricated 0 for the
        gapped faithfulness metric (the failure mode the prior
        ``.get("mean", 0)`` roll-up produced)."""
        results = self._run(use_reference_answers=False)
        summary = results["metric_aggregator"]["result"]["evaluation_summary"]
        agg = summary["aggregate_metrics"]
        # faithfulness fully parse-gapped: absent from aggregate_metrics AND
        # surfaced honestly in parse_gaps (not silently zero).
        assert agg.get("faithfulness", {}).get("mean") is None
        assert summary["parse_gaps"].get("faithfulness")
        # relevance + context_precision produced real means.
        present = [
            agg[m]["mean"]
            for m in ("relevance", "context_precision")
            if m in agg and agg[m].get("mean") is not None
        ]
        assert present, "relevance + context_precision must still have real means"
        expected_present_only = sum(present) / len(present)
        # overall_score rolls up ONLY the present means...
        assert summary["overall_score"] == pytest.approx(expected_present_only)
        # ...and is STRICTLY HIGHER than the pre-fix fabricated value, which
        # divided the present sum by 3 (averaging in faithfulness=0).
        fabricated_with_zero = sum(present) / 3
        assert summary["overall_score"] != pytest.approx(fabricated_with_zero)
        assert summary["overall_score"] > fabricated_with_zero
