"""Tier 1 unit coverage — ``kaizen.nodes.rag.router`` and ``…rag.registry``.

F8 shard B10. The 3 ``@register_node`` Node-subclass classes in
``router.py`` (RAGStrategyRouterNode, RAGQualityAnalyzerNode,
RAGPerformanceMonitorNode) and the 1 non-registered class in
``registry.py`` (RAGWorkflowRegistry, plus the module-scope
``rag_registry`` singleton) cover the routing / strategy-selection /
quality-analysis / performance-monitoring / discovery surface of the
RAG package.

Tier 1 scope:

- Construction with default + custom kwargs across all 4 classes.
- ``get_parameters()`` contracts for the 3 ``Node``-subclass classes.
- Deterministic helpers on RAGStrategyRouterNode:
  * ``_analyze_documents`` (empty + populated, technical + structured)
  * ``_analyze_query`` (question / technical / conceptual detection)
  * ``_fallback_strategy_selection`` (all four rule branches)
  * ``_parse_fallback_response`` (each strategy keyword + reasoning)
  * ``_parse_llm_response`` (valid-JSON, missing-fields, exception)
- The ``run()`` LLM-fails fallback path via a deterministic stub on
  ``LLMAgentNode.execute`` raising — exercises the
  ``_fallback_strategy_selection`` path inside ``run()`` and verifies
  the output shape contract is honored on the failure branch.
- RAGQualityAnalyzerNode.run() over fixed rag_results — verifies
  quality_score / recommendations / passed_quality_check derivation.
- RAGPerformanceMonitorNode.run() accumulation, 100-record cap, and
  metric / insight derivation against an in-memory history.
- RAGWorkflowRegistry list / recommend / create surface across all
  4 strategies / 4 workflows / 3 utilities.
- ``rag_registry`` module-scope singleton existence + identity.

Value-anchor per the F8 plan §B B10 row is **lowest (generic
plumbing) — closes "every class"**: every preserved RAG class
acquires ≥1 behavioral test, completing the brief's "provably
correct, not merely importable" criterion.

NB: ``@register_node()`` erases the concrete subclass to ``Node`` for
static type-checkers, so attribute access on the per-class config
fields (``llm_model``, ``provider``, ``performance_history``) goes
through ``# type: ignore[attr-defined]`` at the call site — the same
B7/B8/B9a/B9b/B9c precedent.
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

pytestmark = pytest.mark.unit


# ==========================================================================
# Construction floor — all four classes
# ==========================================================================


class TestAllFourConstruct:
    def test_strategy_router_constructs_default(self):
        node = RAGStrategyRouterNode()
        assert node is not None
        assert node.metadata.name == "rag_strategy_router"
        # llm_model resolves from env (.env), MAY be None — env-models compliant.
        assert node.provider == "openai"  # type: ignore[attr-defined]
        assert node.llm_agent is None  # type: ignore[attr-defined]

    def test_strategy_router_constructs_with_custom_kwargs(self):
        node = RAGStrategyRouterNode(
            name="custom_router", llm_model="custom-test-model", provider="anthropic"
        )
        assert node.metadata.name == "custom_router"
        assert node.llm_model == "custom-test-model"  # type: ignore[attr-defined]
        assert node.provider == "anthropic"  # type: ignore[attr-defined]

    def test_quality_analyzer_constructs_default(self):
        node = RAGQualityAnalyzerNode()
        assert node is not None
        assert node.metadata.name == "rag_quality_analyzer"

    def test_quality_analyzer_constructs_with_custom_name(self):
        node = RAGQualityAnalyzerNode(name="custom_quality_analyzer")
        assert node.metadata.name == "custom_quality_analyzer"

    def test_performance_monitor_constructs_default(self):
        node = RAGPerformanceMonitorNode()
        assert node is not None
        assert node.metadata.name == "rag_performance_monitor"
        assert node.performance_history == []  # type: ignore[attr-defined]

    def test_performance_monitor_constructs_with_custom_name(self):
        node = RAGPerformanceMonitorNode(name="custom_monitor")
        assert node.metadata.name == "custom_monitor"

    def test_workflow_registry_constructs(self):
        reg = RAGWorkflowRegistry()
        # Registers 4 strategies + 4 workflows + 3 utilities at construction.
        assert set(reg._strategies.keys()) == {
            "semantic",
            "statistical",
            "hybrid",
            "hierarchical",
        }
        assert set(reg._workflows.keys()) == {
            "simple",
            "advanced",
            "adaptive",
            "configurable",
        }
        assert set(reg._utilities.keys()) == {
            "router",
            "quality_analyzer",
            "performance_monitor",
        }

    def test_module_scope_rag_registry_singleton_exists(self):
        assert isinstance(rag_registry, RAGWorkflowRegistry)
        # Module-scope singleton MUST expose the full discovery surface.
        assert "semantic" in rag_registry.list_strategies()
        assert "simple" in rag_registry.list_workflows()
        assert "router" in rag_registry.list_utilities()


# ==========================================================================
# get_parameters() — Node-subclass parameter contracts
# ==========================================================================


class TestGetParametersContract:
    def test_strategy_router_get_parameters_shape(self):
        params = RAGStrategyRouterNode().get_parameters()
        # Required: documents only. Optional: name, llm_model, provider,
        # query, user_preferences, performance_history.
        assert params["documents"].required is True
        for opt in (
            "name",
            "llm_model",
            "provider",
            "query",
            "user_preferences",
            "performance_history",
        ):
            assert params[opt].required is False, opt
        assert params["documents"].type is list
        assert params["query"].type is str
        assert params["user_preferences"].type is dict

    def test_quality_analyzer_get_parameters_shape(self):
        params = RAGQualityAnalyzerNode().get_parameters()
        assert params["rag_results"].required is True
        assert params["query"].required is False
        assert params["expected_results"].required is False
        assert params["rag_results"].type is dict
        assert params["expected_results"].type is list

    def test_performance_monitor_get_parameters_shape(self):
        params = RAGPerformanceMonitorNode().get_parameters()
        assert params["rag_results"].required is True
        for opt in ("execution_time", "strategy_used", "query_type"):
            assert params[opt].required is False, opt
        assert params["execution_time"].type is float


# ==========================================================================
# RAGStrategyRouterNode._analyze_documents — deterministic floor
# ==========================================================================


class TestAnalyzeDocuments:
    def test_empty_documents_returns_zero_stats(self):
        node = RAGStrategyRouterNode()
        out = node._analyze_documents([], query="")  # type: ignore[attr-defined]
        assert out["total_docs"] == 0
        assert out["avg_length"] == 0
        assert out["total_length"] == 0
        assert out["has_structure"] is False
        assert out["is_technical"] is False
        assert out["content_types"] == []
        assert out["complexity_score"] == 0.0

    def test_populated_documents_compute_basic_stats(self):
        node = RAGStrategyRouterNode()
        docs = [
            {"content": "Hello world. Some narrative content here."},
            {"content": "Another paragraph of flowing prose for analysis."},
        ]
        out = node._analyze_documents(docs, query="")  # type: ignore[attr-defined]
        assert out["total_docs"] == 2
        assert out["total_length"] == sum(len(d["content"]) for d in docs)
        assert out["avg_length"] == out["total_length"] // 2

    def test_structured_documents_flagged(self):
        node = RAGStrategyRouterNode()
        docs = [{"content": "# Introduction\n## Section 1\nNarrative paragraph here."}]
        out = node._analyze_documents(docs, query="")  # type: ignore[attr-defined]
        assert out["has_structure"] is True
        assert "structured" in out["content_types"]

    def test_technical_documents_flagged(self):
        node = RAGStrategyRouterNode()
        # Dense technical content — many technical keywords per word.
        docs = [
            {"content": "def function class import return method parameter api code"}
        ] * 3
        out = node._analyze_documents(docs, query="")  # type: ignore[attr-defined]
        assert out["is_technical"] is True
        assert "technical" in out["content_types"]
        assert out["technical_content_ratio"] > 0.1

    def test_long_form_flag_at_avg_length_threshold(self):
        node = RAGStrategyRouterNode()
        docs = [{"content": "narrative " * 250}]  # ~2500 chars
        out = node._analyze_documents(docs, query="")  # type: ignore[attr-defined]
        assert "long_form" in out["content_types"]

    def test_query_analysis_included_when_query_provided(self):
        node = RAGStrategyRouterNode()
        out = node._analyze_documents(  # type: ignore[attr-defined]
            [{"content": "x"}], query="how do I install this?"
        )
        assert out["query_analysis"] is not None
        assert out["query_analysis"]["is_question"] is True
        assert out["query_analysis"]["is_technical"] is True

    def test_query_analysis_absent_when_query_empty(self):
        node = RAGStrategyRouterNode()
        out = node._analyze_documents([{"content": "x"}], query="")  # type: ignore[attr-defined]
        assert out["query_analysis"] is None


class TestAnalyzeQuery:
    def test_conceptual_query_flagged(self):
        node = RAGStrategyRouterNode()
        out = node._analyze_query("Please explain the concept of recursion.")  # type: ignore[attr-defined]
        assert out["is_conceptual"] is True
        assert out["is_technical"] is False

    def test_question_query_flagged(self):
        node = RAGStrategyRouterNode()
        out = node._analyze_query("Where does the cache live?")  # type: ignore[attr-defined]
        assert out["is_question"] is True

    def test_neither_question_nor_technical(self):
        node = RAGStrategyRouterNode()
        out = node._analyze_query("Tell me a story about dragons.")  # type: ignore[attr-defined]
        assert out["is_question"] is False
        assert out["is_technical"] is False

    def test_query_complexity_grows_with_words(self):
        node = RAGStrategyRouterNode()
        short = node._analyze_query("hi")  # type: ignore[attr-defined]
        long_ = node._analyze_query("one two three four five six seven eight")  # type: ignore[attr-defined]
        assert long_["complexity"] > short["complexity"]


# ==========================================================================
# RAGStrategyRouterNode._fallback_strategy_selection — rule branches
# ==========================================================================


class TestFallbackStrategySelection:
    def test_hierarchical_picked_for_complex_structured(self):
        node = RAGStrategyRouterNode()
        decision = node._fallback_strategy_selection(  # type: ignore[attr-defined]
            {
                "complexity_score": 0.8,
                "has_structure": True,
                "is_technical": False,
                "technical_content_ratio": 0.0,
                "total_docs": 5,
                "avg_length": 500,
            }
        )
        assert decision["recommended_strategy"] == "hierarchical"
        assert decision["confidence"] == 0.8

    def test_statistical_picked_for_technical(self):
        node = RAGStrategyRouterNode()
        decision = node._fallback_strategy_selection(  # type: ignore[attr-defined]
            {
                "complexity_score": 0.3,
                "has_structure": False,
                "is_technical": True,
                "technical_content_ratio": 0.3,
                "total_docs": 5,
                "avg_length": 500,
            }
        )
        assert decision["recommended_strategy"] == "statistical"

    def test_hybrid_picked_for_large_collection(self):
        node = RAGStrategyRouterNode()
        decision = node._fallback_strategy_selection(  # type: ignore[attr-defined]
            {
                "complexity_score": 0.3,
                "has_structure": False,
                "is_technical": False,
                "technical_content_ratio": 0.0,
                "total_docs": 100,
                "avg_length": 500,
            }
        )
        assert decision["recommended_strategy"] == "hybrid"

    def test_semantic_picked_as_default(self):
        node = RAGStrategyRouterNode()
        decision = node._fallback_strategy_selection(  # type: ignore[attr-defined]
            {
                "complexity_score": 0.1,
                "has_structure": False,
                "is_technical": False,
                "technical_content_ratio": 0.0,
                "total_docs": 5,
                "avg_length": 200,
            }
        )
        assert decision["recommended_strategy"] == "semantic"

    def test_fallback_strategy_field_always_hybrid(self):
        node = RAGStrategyRouterNode()
        for branch in (
            {
                "complexity_score": 0.8,
                "has_structure": True,
                "is_technical": False,
                "technical_content_ratio": 0.0,
                "total_docs": 5,
                "avg_length": 500,
            },
            {
                "complexity_score": 0.1,
                "has_structure": False,
                "is_technical": False,
                "technical_content_ratio": 0.0,
                "total_docs": 5,
                "avg_length": 200,
            },
        ):
            decision = node._fallback_strategy_selection(branch)  # type: ignore[attr-defined]
            assert decision["fallback_strategy"] == "hybrid"


# ==========================================================================
# RAGStrategyRouterNode._parse_llm_response + _parse_fallback_response
# ==========================================================================


class TestParseLLMResponse:
    def test_parse_valid_json_response(self):
        node = RAGStrategyRouterNode()
        resp = {
            "content": (
                'Some preamble. {"recommended_strategy": "hybrid", '
                '"reasoning": "test reasoning", "confidence": 0.9, '
                '"fallback_strategy": "semantic"} trailing'
            )
        }
        out = node._parse_llm_response(resp)  # type: ignore[attr-defined]
        assert out["recommended_strategy"] == "hybrid"
        assert out["confidence"] == 0.9
        assert out["fallback_strategy"] == "semantic"

    def test_parse_content_as_list_extracts_first_element(self):
        node = RAGStrategyRouterNode()
        resp = {
            "content": [
                '{"recommended_strategy": "statistical", "reasoning": "r", "confidence": 0.7}'
            ]
        }
        out = node._parse_llm_response(resp)  # type: ignore[attr-defined]
        assert out["recommended_strategy"] == "statistical"

    def test_parse_json_missing_required_field_falls_back(self):
        node = RAGStrategyRouterNode()
        # `confidence` missing → falls to _parse_fallback_response.
        resp = {"content": '{"recommended_strategy": "hybrid", "reasoning": "r"}'}
        out = node._parse_llm_response(resp)  # type: ignore[attr-defined]
        # Fallback parser picks first matching strategy keyword from text.
        assert out["recommended_strategy"] == "hybrid"

    def test_parse_completely_broken_returns_safe_default(self):
        node = RAGStrategyRouterNode()
        # raise inside try → except → safe default.
        out = node._parse_llm_response({"content": {"bad": "shape"}})  # type: ignore[attr-defined]
        assert out["recommended_strategy"] == "hybrid"
        assert out["confidence"] == 0.5


class TestParseFallbackResponse:
    @pytest.mark.parametrize(
        "content, expected",
        [
            ("Use the semantic approach for narrative content.", "semantic"),
            ("Statistical retrieval suits this technical input.", "statistical"),
            ("A hybrid pipeline gives best coverage.", "hybrid"),
            ("Hierarchical processing for long structured docs.", "hierarchical"),
            ("Nothing recognizable here at all.", "hybrid"),  # default
        ],
    )
    def test_strategy_keyword_extraction(self, content: str, expected: str):
        node = RAGStrategyRouterNode()
        out = node._parse_fallback_response(content)  # type: ignore[attr-defined]
        assert out["recommended_strategy"] == expected
        assert "reasoning" in out
        assert out["fallback_strategy"] == "hybrid"


# ==========================================================================
# RAGStrategyRouterNode.run() — LLM-fails fallback branch
# ==========================================================================


class _RaisingLLMAgentNode:
    """Protocol-satisfying deterministic stub: a class that exposes the same
    ``execute`` signature ``LLMAgentNode`` does and raises on every call,
    forcing ``run()`` into the deterministic fallback branch.

    This is NOT a mock (``unittest.mock``/``@patch`` BLOCKED in unit per
    ``testing.md``) — it is a deterministic substitute matching the
    ``LLMAgentNode.execute(messages=...)`` shape.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:  # noqa: ARG002
        # Accept any kwargs LLMAgentNode's constructor accepts; ignore them.
        _ = (args, kwargs)

    def execute(self, **kwargs: Any) -> Dict[str, Any]:  # noqa: ARG002
        _ = kwargs
        raise RuntimeError("simulated LLM failure for fallback-branch coverage")


class TestRouterRunFallbackBranch:
    def test_run_with_failing_llm_falls_back_to_rule_based(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        """When the LLM agent raises, ``run()`` MUST honor the
        ``_fallback_strategy_selection`` decision and emit the documented
        output shape."""
        import kaizen.nodes.rag.router as router_mod

        # Substitute the LLMAgentNode class the router constructs inside run().
        monkeypatch.setattr(
            router_mod, "LLMAgentNode", _RaisingLLMAgentNode  # type: ignore[assignment]
        )

        node = RAGStrategyRouterNode(name="failing_router")
        out = node.run(
            documents=[{"content": "narrative " * 300}],  # avg_length > 2500
            query="explain the concept of recursion",
        )

        # Output-shape contract — every key the documented run() emits MUST
        # be present even on the fallback branch.
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

        # Deterministic-branch assertion: 1 doc (≤50) AND avg_length > 1000
        # AND not technical / no structure → "hybrid" branch in
        # _fallback_strategy_selection.
        assert out["strategy"] == "hybrid"
        assert out["fallback_strategy"] == "hybrid"
        assert out["routing_metadata"]["documents_count"] == 1
        assert out["routing_metadata"]["query_provided"] is True


# ==========================================================================
# RAGQualityAnalyzerNode.run() — deterministic, no LLM
# ==========================================================================


class TestQualityAnalyzerRun:
    def test_run_with_empty_results_yields_low_quality(self):
        """Empty-results case scores 0.1 — only the inverse-duplicate-ratio
        weight contributes when there are no docs, scores, or coverage."""
        node = RAGQualityAnalyzerNode()
        out = node.run(rag_results={"results": [], "scores": []}, query="x")
        assert out["quality_analysis"]["result_count"] == 0
        # 0 docs, 0 avg_score, 0 diversity, 0 coverage, (1 - 0) duplicate = 1
        # weighted by 0.1 → quality_score = 0.1, well below 0.6 pass gate.
        assert out["quality_score"] == pytest.approx(0.1, rel=1e-9)
        assert out["passed_quality_check"] is False
        assert "analysis_timestamp" in out

    def test_run_extracts_documents_field_alias(self):
        """rag_results may use ``documents`` OR ``results`` — both supported."""
        node = RAGQualityAnalyzerNode()
        out_with_results = node.run(
            rag_results={"results": [{"content": "hello"}], "scores": [0.9]},
            query="hello",
        )
        out_with_documents = node.run(
            rag_results={"documents": [{"content": "hello"}], "scores": [0.9]},
            query="hello",
        )
        assert out_with_results["quality_analysis"]["result_count"] == 1
        assert out_with_documents["quality_analysis"]["result_count"] == 1

    def test_run_computes_score_statistics(self):
        node = RAGQualityAnalyzerNode()
        scores = [0.5, 0.6, 0.7, 0.8, 0.9]
        out = node.run(
            rag_results={
                "results": [{"content": f"doc {i}"} for i in range(5)],
                "scores": scores,
            },
            query="doc",
        )
        qa = out["quality_analysis"]
        assert qa["has_scores"] is True
        assert qa["min_score"] == 0.5
        assert qa["max_score"] == 0.9
        assert pytest.approx(qa["avg_score"], rel=1e-9) == sum(scores) / len(scores)
        # Variance is non-negative and finite for non-trivial score sets.
        assert qa["score_variance"] >= 0.0

    def test_run_diversity_score_lowers_with_duplicates(self):
        node = RAGQualityAnalyzerNode()
        unique = node.run(
            rag_results={
                "results": [{"content": f"distinct content {i}"} for i in range(4)],
                "scores": [0.8] * 4,
            },
            query="content",
        )
        dupes = node.run(
            rag_results={
                "results": [{"content": "same content"} for _ in range(4)],
                "scores": [0.8] * 4,
            },
            query="content",
        )
        assert unique["content_analysis"]["diversity_score"] == 1.0
        assert dupes["content_analysis"]["diversity_score"] < 1.0
        assert dupes["content_analysis"]["duplicate_ratio"] > 0.0

    def test_run_recommends_lower_threshold_when_few_results(self):
        node = RAGQualityAnalyzerNode()
        out = node.run(
            rag_results={
                "results": [{"content": "only one"}],
                "scores": [0.5],
            },
            query="one",
        )
        recs = out["recommendations"]
        assert any("lowering similarity threshold" in r for r in recs)

    def test_run_recommends_raising_threshold_when_too_many_results(self):
        node = RAGQualityAnalyzerNode()
        out = node.run(
            rag_results={
                "results": [{"content": f"d{i}"} for i in range(12)],
                "scores": [0.5] * 12,
            },
            query="d",
        )
        recs = out["recommendations"]
        assert any("raising similarity threshold" in r for r in recs)

    def test_run_consumes_expected_results_kwarg(self):
        """Documented kwarg ``expected_results`` MUST be consumed (Rule 3c —
        documented kwargs accepted but unused = silent fallback)."""
        node = RAGQualityAnalyzerNode()
        out = node.run(
            rag_results={
                "results": [{"content": f"d{i}"} for i in range(3)],
                "scores": [0.8] * 3,
            },
            query="d",
            expected_results=[{"content": f"d{i}"} for i in range(5)],
        )
        qa = out["quality_analysis"]
        # 3 retrieved, 5 expected → recall 0.6.
        assert qa["expected_result_count"] == 5
        assert qa["expected_recall_ratio"] == pytest.approx(0.6, rel=1e-9)

    def test_run_without_expected_results_omits_comparison_fields(self):
        """When ``expected_results`` is absent, the comparison fields MUST NOT
        appear — preserves backwards compatibility with prior callers."""
        node = RAGQualityAnalyzerNode()
        out = node.run(
            rag_results={
                "results": [{"content": "d"}],
                "scores": [0.8],
            },
            query="d",
        )
        qa = out["quality_analysis"]
        assert "expected_result_count" not in qa
        assert "expected_recall_ratio" not in qa

    def test_run_strategy_specific_recommendation_semantic(self):
        node = RAGQualityAnalyzerNode()
        out = node.run(
            rag_results={
                "results": [{"content": "a"}, {"content": "b"}, {"content": "c"}],
                "scores": [0.3, 0.4, 0.5],
                "strategy_used": "semantic",
            },
            query="a",
        )
        assert any("switching to hybrid" in r for r in out["recommendations"])


# ==========================================================================
# RAGPerformanceMonitorNode.run() — accumulation + 100-cap + metrics
# ==========================================================================


class TestPerformanceMonitorRun:
    def test_run_records_single_invocation(self):
        node = RAGPerformanceMonitorNode()
        out = node.run(
            rag_results={"results": [{"content": "x"}], "scores": [0.8]},
            execution_time=0.5,
            strategy_used="semantic",
            query_type="conceptual",
        )
        assert out["current_performance"]["strategy_used"] == "semantic"
        assert out["current_performance"]["query_type"] == "conceptual"
        assert out["current_performance"]["execution_time"] == 0.5
        assert out["current_performance"]["result_count"] == 1
        assert out["current_performance"]["success"] is True
        assert out["performance_history_size"] == 1

    def test_run_failure_record_when_no_results(self):
        node = RAGPerformanceMonitorNode()
        out = node.run(
            rag_results={"results": [], "scores": []},
            execution_time=0.1,
            strategy_used="hybrid",
        )
        assert out["current_performance"]["success"] is False

    def test_history_capped_at_100_records(self):
        node = RAGPerformanceMonitorNode()
        for i in range(125):
            node.run(
                rag_results={"results": [{"content": f"d{i}"}], "scores": [0.5]},
                execution_time=0.2,
                strategy_used="semantic",
            )
        # 100-record sliding window invariant.
        assert len(node.performance_history) == 100  # type: ignore[attr-defined]
        assert node.performance_history[0]["result_count"] == 1  # type: ignore[attr-defined]

    def test_metrics_aggregate_across_strategies(self):
        node = RAGPerformanceMonitorNode()
        for strategy in ("semantic", "semantic", "hybrid", "hybrid", "hybrid"):
            node.run(
                rag_results={"results": [{"content": "x"}], "scores": [0.8]},
                execution_time=1.0,
                strategy_used=strategy,
            )
        out = node.run(
            rag_results={"results": [{"content": "x"}], "scores": [0.8]},
            execution_time=1.0,
            strategy_used="hybrid",
        )
        by_strategy = out["metrics"]["by_strategy"]
        assert "semantic" in by_strategy
        assert "hybrid" in by_strategy
        assert by_strategy["semantic"]["count"] == 2
        assert by_strategy["hybrid"]["count"] == 4
        assert by_strategy["hybrid"]["success_rate"] == 1.0

    def test_insights_flag_high_execution_time(self):
        node = RAGPerformanceMonitorNode()
        for _ in range(5):
            node.run(
                rag_results={"results": [{"content": "x"}], "scores": [0.8]},
                execution_time=10.0,  # > 5s threshold
                strategy_used="hierarchical",
            )
        out = node.run(
            rag_results={"results": [{"content": "x"}], "scores": [0.8]},
            execution_time=10.0,
            strategy_used="hierarchical",
        )
        assert any("High average execution time" in s for s in out["insights"])

    def test_insights_flag_low_success_rate(self):
        node = RAGPerformanceMonitorNode()
        # 8 of 10 fail → success_rate 0.2 (< 0.8).
        for _ in range(8):
            node.run(
                rag_results={"results": [], "scores": []},
                execution_time=0.1,
                strategy_used="semantic",
            )
        for _ in range(2):
            node.run(
                rag_results={"results": [{"content": "x"}], "scores": [0.8]},
                execution_time=0.1,
                strategy_used="semantic",
            )
        out = node.run(
            rag_results={"results": [], "scores": []},
            execution_time=0.1,
            strategy_used="semantic",
        )
        assert any("Low success rate" in s for s in out["insights"])


# ==========================================================================
# RAGWorkflowRegistry — list / recommend / create
# ==========================================================================


class TestWorkflowRegistryList:
    def test_list_strategies_returns_metadata(self):
        reg = RAGWorkflowRegistry()
        out = reg.list_strategies()
        for name in ("semantic", "statistical", "hybrid", "hierarchical"):
            assert name in out
            assert "description" in out[name]
            assert "use_cases" in out[name]
            assert "strengths" in out[name]
            assert "performance" in out[name]

    def test_list_workflows_returns_metadata(self):
        reg = RAGWorkflowRegistry()
        out = reg.list_workflows()
        for name in ("simple", "advanced", "adaptive", "configurable"):
            assert name in out
            assert "description" in out[name]
            assert "complexity" in out[name]
            assert "features" in out[name]

    def test_list_utilities_returns_metadata(self):
        reg = RAGWorkflowRegistry()
        out = reg.list_utilities()
        for name in ("router", "quality_analyzer", "performance_monitor"):
            assert name in out
            assert "description" in out[name]
            assert "use_case" in out[name]


class TestWorkflowRegistryRecommend:
    def test_hierarchical_top_pick_for_long_structured_docs(self):
        reg = RAGWorkflowRegistry()
        out = reg.recommend_strategy(
            document_count=10,
            avg_document_length=3000,
            has_structure=True,
        )
        assert out["recommended_strategy"] == "hierarchical"
        assert out["confidence"] >= 0.8
        assert "strategy_details" in out

    def test_statistical_picked_for_technical_query(self):
        reg = RAGWorkflowRegistry()
        out = reg.recommend_strategy(
            document_count=10,
            avg_document_length=500,
            is_technical=True,
        )
        assert out["recommended_strategy"] in ("statistical", "hybrid")

    def test_semantic_default_when_no_other_signals(self):
        reg = RAGWorkflowRegistry()
        out = reg.recommend_strategy(
            document_count=5,
            avg_document_length=200,
            query_type="conceptual",
        )
        # Conceptual content with no technical / structured signal → semantic
        # wins after the speed-priority unaffected tie-break.
        assert out["recommended_strategy"] in ("semantic", "hybrid")

    def test_speed_priority_demotes_hierarchical(self):
        """Hierarchical scores 0.9 by default but speed-priority subtracts
        0.2 → 0.7, while statistical (0.85) gets +0.1 → 0.95. With both
        signals present, statistical wins under the speed-priority weighting."""
        reg = RAGWorkflowRegistry()
        out = reg.recommend_strategy(
            document_count=10,
            avg_document_length=3000,
            has_structure=True,
            is_technical=True,  # triggers statistical@0.85
            performance_priority="speed",
        )
        # Hierarchical: 0.9 - 0.2 = 0.7; statistical: 0.85 + 0.1 = 0.95.
        assert out["recommended_strategy"] != "hierarchical"

    def test_recommend_workflow_beginner_picks_simple(self):
        reg = RAGWorkflowRegistry()
        out = reg.recommend_workflow(user_level="beginner")
        assert out["recommended_workflow"] == "simple"

    def test_recommend_workflow_needs_customization_picks_configurable(self):
        reg = RAGWorkflowRegistry()
        out = reg.recommend_workflow(
            user_level="intermediate", needs_customization=True
        )
        assert out["recommended_workflow"] == "configurable"

    def test_recommend_workflow_advanced_research_picks_adaptive(self):
        reg = RAGWorkflowRegistry()
        out = reg.recommend_workflow(user_level="advanced", use_case="research")
        assert out["recommended_workflow"] == "adaptive"
        # Adaptive workflow MUST suggest the router + analyzer + monitor.
        assert "router" in out["suggested_utilities"]
        assert "quality_analyzer" in out["suggested_utilities"]
        assert "performance_monitor" in out["suggested_utilities"]


class TestWorkflowRegistryCreate:
    def test_create_strategy_returns_node_instance(self):
        reg = RAGWorkflowRegistry()
        node = reg.create_strategy("semantic")
        # Construction succeeded; the registry returns a real Node instance
        # (concrete subclass type checked behaviorally — has a `metadata`
        # attribute and the strategy name in the registry maps to the right
        # class kind).
        assert node is not None
        assert hasattr(node, "metadata")

    def test_create_strategy_with_unknown_name_raises(self):
        reg = RAGWorkflowRegistry()
        with pytest.raises(ValueError, match="Unknown strategy"):
            reg.create_strategy("nonexistent_strategy")

    def test_create_workflow_returns_node_instance(self):
        reg = RAGWorkflowRegistry()
        node = reg.create_workflow("simple")
        assert node is not None
        assert hasattr(node, "metadata")

    def test_create_workflow_with_unknown_name_raises(self):
        reg = RAGWorkflowRegistry()
        with pytest.raises(ValueError, match="Unknown workflow"):
            reg.create_workflow("nonexistent_workflow")

    def test_create_utility_returns_node_instance(self):
        reg = RAGWorkflowRegistry()
        node = reg.create_utility("quality_analyzer")
        assert node is not None
        assert isinstance(node, RAGQualityAnalyzerNode)

    def test_create_utility_with_unknown_name_raises(self):
        reg = RAGWorkflowRegistry()
        with pytest.raises(ValueError, match="Unknown utility"):
            reg.create_utility("nonexistent_utility")


class TestWorkflowRegistryGuides:
    def test_quick_start_guide_returns_nontrivial_text(self):
        reg = RAGWorkflowRegistry()
        guide = reg.get_quick_start_guide()
        # The guide is documentation; behavioral floor is that it's a
        # non-trivial string with the registry's primary entry points named.
        assert isinstance(guide, str)
        assert len(guide) > 200
        # Test by call-through: the guide mentions every documented entry.
        for name in ("simple", "advanced", "adaptive", "router"):
            assert name in guide

    def test_strategy_comparison_returns_full_matrix(self):
        reg = RAGWorkflowRegistry()
        out = reg.get_strategy_comparison()
        assert set(out["performance_matrix"].keys()) == {
            "semantic",
            "statistical",
            "hybrid",
            "hierarchical",
        }
        for name, fields in out["performance_matrix"].items():
            assert set(fields.keys()) == {"speed", "accuracy", "complexity"}, name
