"""Tier-2a integration coverage for ``kaizen.nodes.rag.agentic``.

F8 shard B3. The 3 agentic RAG nodes are exercised here with NO mocking
(``@patch`` / ``MagicMock`` / ``unittest.mock`` are BLOCKED in Tier 2 per the
3-tier testing rule). The agentic path is the most defect-prone RAG path per
the plan, so the integration tests assert end-to-end structural behavior.

Real infrastructure used:

- ``ToolAugmentedRAGNode``'s deterministic ``run()`` path needs no external
  infra — tool detection is keyword-based and synthesis is rule-based. Its
  default path makes NO network call, so the deterministic path is tested
  directly.
- One test stands up a real loopback HTTP server (``pytest_httpserver`` —
  real ``http.server`` on ``127.0.0.1``, real infra, NOT a mock) and registers
  a tool callable that performs a genuine REST call against it, proving the
  ``tool_registry`` contract end-to-end with real network IO.
- The ``AgenticRAGNode`` / ``ReasoningRAGNode`` ``WorkflowNode``s build real
  sub-workflows via the real ``WorkflowBuilder``; their ``code=``
  ``PythonCodeNode`` templates are executed directly against real input.

Assertions are structural: output keys, score ranges, list lengths, real
graph node counts, typed outputs.
"""

from __future__ import annotations

import json
import logging
import urllib.request
import warnings

import pytest

from kaizen.nodes.rag.agentic import (
    AgenticRAGNode,
    ReasoningRAGNode,
    ToolAugmentedRAGNode,
)

pytestmark = pytest.mark.integration


_DOCS = [
    {"id": "p1", "content": "the transformer model uses self-attention", "title": "T"},
    {"id": "p2", "content": "recurrent networks process sequences in order"},
]


def _build(node):
    """Build a WorkflowNode's sub-workflow, silencing cosmetic
    PythonCodeNode line-count UserWarnings."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return node._create_workflow()


# ===========================================================================
# ToolAugmentedRAGNode — deterministic run() path, real (no-infra) execution
# ===========================================================================
class TestToolAugmentedRAGIntegration:
    def test_end_to_end_run_returns_structural_output(self):
        """A full ``run()`` over a real document set returns the documented
        output shape with sane value ranges."""
        result = ToolAugmentedRAGNode().run(
            query="calculate the average length", documents=_DOCS
        )
        assert set(result.keys()) == {
            "answer",
            "tools_invoked",
            "tool_outputs",
            "confidence",
        }
        assert isinstance(result["answer"], str) and result["answer"]
        assert "calculator" in result["tools_invoked"]
        assert 0.0 <= result["confidence"] <= 1.0
        # The synthesized answer reports the real document count.
        assert "2 documents" in result["answer"]

    def test_registered_tool_output_flows_into_answer(self):
        """A registered tool's real output is woven into the synthesized
        answer and lifts confidence to 0.9."""

        def calculator(query, context):
            return {"tool": "calculator", "result": 168}

        result = ToolAugmentedRAGNode(tool_registry={"calculator": calculator}).run(
            query="calculate the total", documents=_DOCS
        )
        assert result["tool_outputs"]["calculator"]["result"] == 168
        assert result["confidence"] == 0.9
        assert "calculator" in result["answer"]

    def test_genuine_rest_tool_against_loopback_server(self, httpserver):
        """A tool callable that makes a REAL REST call to a loopback HTTP
        server resolves end-to-end. The server is real ``http.server`` on
        127.0.0.1 — real infrastructure, not a mock.

        This proves the ``tool_registry`` contract: tools are arbitrary
        callables, including ones that perform genuine network IO."""
        httpserver.expect_request("/units").respond_with_json(
            {"converted": 42.0, "unit": "kg"}
        )
        endpoint = httpserver.url_for("/units")

        def unit_converter(query, context):
            # Genuine outbound HTTP GET to the loopback server.
            with urllib.request.urlopen(endpoint, timeout=3) as resp:
                return json.loads(resp.read().decode())

        result = ToolAugmentedRAGNode(
            tool_registry={"unit_converter": unit_converter}
        ).run(query="convert these units", documents=_DOCS)

        assert "unit_converter" in result["tools_invoked"]
        assert result["tool_outputs"]["unit_converter"]["converted"] == 42.0
        assert result["confidence"] == 0.9

    def test_failing_rest_tool_is_captured_not_propagated(self, httpserver):
        """When a REST tool hits a real 500 from the loopback server, the
        node captures the failure as an error entry rather than crashing."""
        httpserver.expect_request("/broken").respond_with_data("boom", status=500)
        endpoint = httpserver.url_for("/broken")

        def unit_converter(query, context):
            with urllib.request.urlopen(endpoint, timeout=3) as resp:
                return json.loads(resp.read().decode())

        result = ToolAugmentedRAGNode(
            tool_registry={"unit_converter": unit_converter}
        ).run(query="convert the units", documents=[])
        assert "error" in result["tool_outputs"]["unit_converter"]
        # The node still produces a usable answer despite the tool failure.
        assert isinstance(result["answer"], str) and result["answer"]


# ===========================================================================
# AgenticRAGNode — real WorkflowBuilder graph + real code= template execution
# ===========================================================================
class TestAgenticRAGIntegration:
    def test_real_workflow_built_with_six_nodes(self):
        """``_create_workflow()`` builds a real Workflow with six nodes when
        verification is enabled."""
        wf = _build(AgenticRAGNode(verification_enabled=True))
        assert len(wf.nodes) == 6
        # The workflow carries real connections between the nodes.
        assert len(wf.connections) > 0

    def test_tool_executor_template_runs_real_search(self):
        """The tool_executor ``code=`` template executes a real keyword
        search and ranks documents by overlap score."""
        wf = _build(AgenticRAGNode())
        code = wf.nodes["tool_executor"].config["code"]
        ns = {
            "reasoning_state": {"current_action": 'search("transformer attention")'},
            "documents": [
                {"id": "hit", "content": "the transformer uses attention heavily"},
                {"id": "miss", "content": "completely unrelated text"},
            ],
        }
        exec(code, ns)
        tr = ns["result"]["tool_result"]
        assert tr["tool"] == "search"
        assert tr["count"] == 1
        # The matching document scored above zero and ranks first.
        assert tr["results"][0]["id"] == "hit"
        assert tr["results"][0]["score"] > 0

    def test_tool_executor_template_calculate_real_arithmetic(self):
        """The tool_executor ``calculate`` action evaluates real arithmetic
        via the AST-walked safe evaluator."""
        wf = _build(AgenticRAGNode())
        code = wf.nodes["tool_executor"].config["code"]
        ns = {
            "reasoning_state": {"current_action": "calculate((100 - 80) / 80 * 100)"},
            "documents": [],
        }
        exec(code, ns)
        assert ns["result"]["tool_result"]["result"] == pytest.approx(25.0)

    def test_result_synthesizer_template_interpolates_real_config(self):
        """The result_synthesizer template runs and the constructor config
        is interpolated into the real metadata block."""
        wf = _build(
            AgenticRAGNode(planning_strategy="tree-of-thought", max_reasoning_steps=9)
        )
        code = wf.nodes["result_synthesizer"].config["code"]
        ns = {
            "reasoning_state": {
                "steps": [
                    {
                        "step_number": 1,
                        "thought": "t",
                        "action": "search(x)",
                        "observation": {"tool": "search"},
                    }
                ],
                "final_answer": "the answer",
                "completed": True,
            },
            "query": "compare revenue",
        }
        exec(code, ns)
        out = ns["result"]["agentic_rag_result"]
        assert out["answer"] == "the answer"
        assert out["tools_used"] == ["search"]
        assert out["metadata"]["planning_strategy"] == "tree-of-thought"
        assert out["metadata"]["max_steps"] == 9
        assert out["total_steps"] == 1


# ===========================================================================
# ReasoningRAGNode — real WorkflowBuilder graph
# ===========================================================================
class TestReasoningRAGIntegration:
    def test_real_workflow_built_with_three_nodes(self):
        """``_create_workflow()`` builds a real Workflow with three nodes and
        real connections."""
        wf = _build(ReasoningRAGNode())
        assert set(wf.nodes) == {
            "problem_decomposer",
            "step_reasoner",
            "logic_verifier",
        }
        assert len(wf.connections) > 0

    def test_constructor_config_flows_into_real_prompt(self):
        """The constructor strategy + depth land in the real decomposer
        system prompt of the built workflow."""
        wf = _build(ReasoningRAGNode(reasoning_depth=6, strategy="tree_of_thought"))
        prompt = wf.nodes["problem_decomposer"].config["system_prompt"]
        assert "Strategy: tree_of_thought" in prompt
        assert "Max depth: 6" in prompt


# ===========================================================================
# Observability — fallback / error log assertions
# ===========================================================================
class TestAgenticObservability:
    def test_failing_tool_emits_error_log(self, caplog):
        """A registered tool that raises is logged at ERROR with the tool
        name — the observable contract for a tool failure
        (rules/observability.md Mandatory Log Points)."""

        def boom(query, context):
            raise RuntimeError("network down")

        with caplog.at_level(logging.ERROR, logger="kaizen.nodes.rag.agentic"):
            result = ToolAugmentedRAGNode(tool_registry={"calculator": boom}).run(
                query="calculate the sum", documents=[]
            )
        assert "error" in result["tool_outputs"]["calculator"]
        assert any(
            "calculator" in r.message and r.levelno == logging.ERROR
            for r in caplog.records
        )
