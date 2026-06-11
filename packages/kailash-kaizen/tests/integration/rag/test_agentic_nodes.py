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
from typing import Any, Dict

import pytest
from kailash.nodes.base import Node, NodeParameter
from kailash.nodes.code.python import PythonCodeNode
from kailash.runtime.local import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder

from kaizen.nodes.rag.agentic import (
    AgenticRAGNode,
    ReasoningRAGNode,
    ToolAugmentedRAGNode,
    _make_result_synthesizer,
    _make_state_manager,
    execute_tool_action,
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

        def calculator(_query, _context):
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

        def unit_converter(_query, _context):
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

        def unit_converter(_query, _context):
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
    def test_real_workflow_built_with_twelve_nodes(self):
        """``_create_workflow()`` builds a real Workflow with twelve nodes when
        verification is enabled: the 6 original nodes, the 3 L3
        messages-composers (planner / react / verifier) that render real context
        into each LLM stage's ``messages`` port, AND the 3 O5 output-side
        response parsers (plan / reasoning / verification) that unwrap each LLM
        stage's ``response.content`` before its consumer."""
        wf = _build(AgenticRAGNode(verification_enabled=True))
        assert len(wf.nodes) == 12
        # The workflow carries real connections between the nodes.
        assert len(wf.connections) > 0

    def test_tool_executor_fn_runs_real_search(self):
        """The lifted ``execute_tool_action`` executes a real keyword search and
        ranks documents by overlap score (post-S6b from_function migration)."""
        out = execute_tool_action(
            reasoning_state={"current_action": 'search("transformer attention")'},
            documents=[
                {"id": "hit", "content": "the transformer uses attention heavily"},
                {"id": "miss", "content": "completely unrelated text"},
            ],
        )
        tr = out["tool_result"]
        assert tr["tool"] == "search"
        assert tr["count"] == 1
        # The matching document scored above zero and ranks first.
        assert tr["results"][0]["id"] == "hit"
        assert tr["results"][0]["score"] > 0

    def test_tool_executor_fn_calculate_real_arithmetic(self):
        """The lifted ``execute_tool_action`` ``calculate`` action evaluates real
        arithmetic via the AST-walked safe evaluator."""
        out = execute_tool_action(
            reasoning_state={"current_action": "calculate((100 - 80) / 80 * 100)"},
            documents=[],
        )
        assert out["tool_result"]["result"] == pytest.approx(25.0)

    def test_result_synthesizer_fn_binds_real_config(self):
        """The lifted ``_make_result_synthesizer`` closure binds the constructor
        config into the real metadata block and computes the trace."""
        synth = _make_result_synthesizer("tree-of-thought", 9)
        out = synth(
            reasoning_state={
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
            query="compare revenue",
        )["agentic_rag_result"]
        assert out["answer"] == "the answer"
        assert out["tools_used"] == ["search"]
        assert out["metadata"]["planning_strategy"] == "tree-of-thought"
        assert out["metadata"]["max_steps"] == 9
        assert out["total_steps"] == 1


# ===========================================================================
# ReasoningRAGNode — real WorkflowBuilder graph
# ===========================================================================
class TestReasoningRAGIntegration:
    def test_real_workflow_built_with_eight_nodes(self):
        """``_create_workflow()`` builds a real Workflow with eight nodes and
        real connections: the 3 LLM stages, the 3 L3 messages-composers (one per
        LLM stage) that render real context into each ``messages`` port, AND the
        2 O5 output-side response parsers (decomposition / reasoning-chain) that
        unwrap the decomposer's and step_reasoner's ``response.content`` before
        the downstream composer."""
        wf = _build(ReasoningRAGNode())
        assert set(wf.nodes) == {
            "problem_decomposer",
            "step_reasoner",
            "logic_verifier",
            "decomposer_messages_composer",
            "step_reasoner_messages_composer",
            "logic_verifier_messages_composer",
            "decomposition_parser",
            "reasoning_chain_parser",
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

        def boom(_query, _context):
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


# ===========================================================================
# L3 messages-wiring proof — the REAL context reaches every LLM stage via the
# `messages` port (Wave 2 Shard 3).
#
# LLMAgentNode consumes context EXCLUSIVELY through `messages` (its `run` reads
# `kwargs["messages"]`); ANY other wired port is silently dropped. Pre-shard the
# 6 agentic LLM stages received NO real input — they answered from their
# `system_prompt` alone (the planner never saw the query, the ReAct agent never
# saw the observations, the verifier never saw the answer, the reasoning chain
# never reached the step-reasoner or logic-verifier). This shard added a
# `*_messages_composer` (PythonCodeNode.from_function) per LLM stage that renders
# the REAL context (query and/or genuine upstream output) into the `messages`
# port.
#
# Two complementary proofs, BOTH under the real ``LocalRuntime`` (no mocking):
#
#   1. ``ReasoningRAGNode`` is ACYCLIC, so its FULL inner workflow runs
#      end-to-end via the production delivery path: the query is delivered as a
#      TOP-LEVEL workflow input (``parameters={"query": ...}``) and the runtime's
#      parameter injector auto-distributes it to every node declaring a ``query``
#      param — including each composer. A ``_MessageCapturingLLMAgent`` records
#      the ``messages`` each LLM stage actually receives, proving the composer →
#      ``messages`` wiring AND the parameter-injector delivery. This is NOT
#      node-keyed injection into the LLM stage (the false-green trap that would
#      bypass the composer entirely).
#
#   2. ``AgenticRAGNode``'s ReAct loop is a GENUINE pre-existing cycle
#      (``react_agent`` ↔ ``state_manager`` ↔ ``tool_executor``), so its full
#      graph cannot run under a plain unmarked ``LocalRuntime`` — this predates
#      the L3 fix (the original integration tests only exec'd individual
#      ``code=`` templates, never the full graph). HONEST DISPOSITION: the
#      agentic composers are proven by (a) a STRUCTURAL wiring assertion that
#      each composer's ``result.messages`` connects to its LLM stage's
#      ``messages`` port (load-bearing — the wiring is the production guard), AND
#      (b) a production-delivery probe that runs each composer STANDALONE under a
#      real ``LocalRuntime`` with the real top-level + upstream inputs the graph
#      feeds it, asserting the rendered ``result.messages`` embed the real
#      context.
# ===========================================================================


# Module-level sink the capturing substitute writes into. Keyed by the LLM
# stage's graph node_id → the `messages` list it received. Reset per test.
_CAPTURED_MESSAGES: Dict[str, Any] = {}


class _MessageCapturingLLMAgent(Node):
    """Protocol-Satisfying Deterministic Adapter (legal Tier-2 surface per
    ``rules/testing.md`` § 3-Tier Testing) that records the ``messages`` each
    LLM stage receives into ``_CAPTURED_MESSAGES`` AND returns deterministic
    output so the rest of each workflow runs to completion.

    This is NOT a mock: it inherits the real ``kailash.nodes.base.Node`` base
    and implements the full runtime contract (``get_parameters`` + ``run``).
    Dispatch is keyed on ``self.id`` (the graph node_id) so each LLM stage
    routes to its specific payload.

    O5 PRODUCTION-SHAPE FIX: ``run`` returns the EXACT wire shape the real
    ``LLMAgentNode`` publishes — ``{"response": {"content": "<text-or-JSON>"}}``
    (``llm_agent.py::_mock_llm_response`` returns a dict whose ``content`` is a
    string; the JSON-output stages carry a ``json.dumps(...)`` string). The
    runtime delivers the inner ``{"content": ...}`` for a wired ``response``
    port, which the O5 ``parse_*_response`` parsers unwrap (``.content`` ->
    ``json.loads``). The PRIOR shape put the structured fields at the TOP LEVEL
    of ``response`` (no ``content`` key) — a FALSE-GREEN that matched the
    pre-O5 consumer bug and never exercised the real parsed path.
    """

    # Each value is the JSON/prose payload the stage's ``content`` carries —
    # exactly what the real provider would emit. JSON-output stages
    # (problem_decomposer, logic_verifier) carry a JSON object; the prose stage
    # (step_reasoner) carries free text. ``run`` wraps each as
    # ``{"content": <str>}`` mirroring the production wire shape.
    _CONTENT_PAYLOADS: Dict[str, Any] = {
        # ReasoningRAGNode.problem_decomposer → decomposition_parser unwraps
        # `.content` -> json.loads -> the step_reasoner composer's reasoning_plan.
        "problem_decomposer": {
            "steps": [
                {
                    "step": 1,
                    "goal": "Define the growth rates",
                    "approach": "arithmetic",
                },
                {"step": 2, "goal": "Solve for the crossover", "approach": "algebra"},
            ],
            "assumptions": ["compound annual growth"],
            "complexity": "medium",
        },
        # ReasoningRAGNode.step_reasoner is a PROSE stage → reasoning_chain_parser
        # unwraps `.content` (a plain string) -> the logic_verifier composer's
        # reasoning_to_verify.
        "step_reasoner": "A compounds at 20%, B at 15% from a 50% larger base; "
        "A overtakes B after several years",
        "logic_verifier": {"verified": True, "confidence": 0.9, "issues": []},
    }

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        for k in ("system_prompt", "model", "provider", "temperature"):
            kwargs.pop(k, None)
        super().__init__(*args, **kwargs)

    def get_parameters(self) -> Dict[str, NodeParameter]:
        return {
            "messages": NodeParameter(
                name="messages",
                type=list,
                required=False,
                default=[],
                description="LLM chat messages (deterministic substitute records)",
            ),
        }

    def run(self, **kwargs: Any) -> Dict[str, Any]:
        _CAPTURED_MESSAGES[self.id] = kwargs.get("messages")
        payload = self._CONTENT_PAYLOADS.get(self.id, "")
        # PRODUCTION wire shape: the real LLMAgentNode publishes
        # `response = {"content": "<str>"}`; JSON-output stages carry a
        # json.dumps(...) string in `content`, prose stages a plain string.
        content = payload if isinstance(payload, str) else json.dumps(payload)
        return {"response": {"content": content}}


@pytest.fixture
def capturing_llm(monkeypatch: pytest.MonkeyPatch):
    """Substitute the ``LLMAgentNode`` registry binding with the
    message-capturing adapter (the string-keyed registry
    ``WorkflowBuilder.add_node("LLMAgentNode", ...)`` resolves through), and
    clear the capture sink per test. Teardown restores the prior binding."""
    from kailash.nodes.base import NodeRegistry

    _CAPTURED_MESSAGES.clear()
    nodes_dict = NodeRegistry._nodes  # type: ignore[attr-defined]
    prior = nodes_dict.get("LLMAgentNode")
    nodes_dict["LLMAgentNode"] = _MessageCapturingLLMAgent
    try:
        yield _MessageCapturingLLMAgent
    finally:
        if prior is None:
            nodes_dict.pop("LLMAgentNode", None)
        else:
            nodes_dict["LLMAgentNode"] = prior


def _flatten_message_text(messages: Any) -> str:
    """Concatenate the `content` of every message in an OpenAI-format list."""
    assert isinstance(messages, list), f"messages must be a list, got {messages!r}"
    return "\n".join(str(m.get("content", "")) for m in messages if isinstance(m, dict))


def _run_composer(node_instance, **inputs: Any) -> Any:
    """Run a single ``from_function`` composer node STANDALONE under a real
    ``LocalRuntime`` and return its published ``result.messages``.

    This exercises the production delivery path for an agentic composer: the
    inputs are delivered as top-level workflow inputs (the parameter injector
    auto-distributes them to the composer's declared function params), exactly
    as the full graph delivers `query` (top-level) + the upstream port values
    to the composer. Used for the cyclic AgenticRAG graph whose full ReAct loop
    cannot run under a plain unmarked ``LocalRuntime``."""
    builder = WorkflowBuilder()
    builder.add_node_instance(node_instance, node_id="probe_composer", _internal=True)
    wf = builder.build(name="composer_probe")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        with LocalRuntime() as rt:
            results, _run_id = rt.execute(wf, parameters=inputs)
    return results["probe_composer"]["result"]["messages"]


class TestAgenticContextReachesLLM:
    """Every LLM stage in the agentic module receives its REAL context through
    the VALID ``messages`` port — delivered via the production top-level-input
    path (parameter injector), NOT node-keyed injection into the LLM stage."""

    _QUERY = "when will company A revenue exceed company B if A grows faster"

    # -- ReasoningRAGNode: full acyclic graph runs end-to-end -----------------

    def test_reasoning_decomposer_receives_problem(self, capturing_llm):
        """problem_decomposer (stage 1) receives the REAL problem (query)."""
        wf = _build(ReasoningRAGNode(name="ctx_rr1"))
        with LocalRuntime() as rt:
            rt.execute(wf, parameters={"query": self._QUERY})
        text = _flatten_message_text(_CAPTURED_MESSAGES.get("problem_decomposer"))
        assert self._QUERY in text, (
            "problem_decomposer MUST receive the real query via `messages`; "
            f"got: {text!r}"
        )

    def test_reasoning_step_reasoner_receives_query_and_decomposition(
        self, capturing_llm
    ):
        """step_reasoner (stage 2) receives the REAL query AND the upstream
        problem_decomposer output (the decomposition steps)."""
        wf = _build(ReasoningRAGNode(name="ctx_rr2"))
        with LocalRuntime() as rt:
            rt.execute(wf, parameters={"query": self._QUERY})
        text = _flatten_message_text(_CAPTURED_MESSAGES.get("step_reasoner"))
        assert (
            self._QUERY in text
        ), "step_reasoner MUST receive the real query via `messages`"
        # The deterministic decomposer returned a step with goal
        # "Define the growth rates"; the composer renders it into the reasoner's
        # messages — proving the REAL upstream output reached the stage.
        assert "Define the growth rates" in text, (
            "step_reasoner MUST receive the upstream decomposition via `messages`; "
            f"got: {text!r}"
        )

    def test_reasoning_logic_verifier_receives_reasoning_chain(self, capturing_llm):
        """logic_verifier (stage 3) receives the REAL step_reasoner reasoning
        chain to verify (not its system_prompt alone)."""
        wf = _build(ReasoningRAGNode(name="ctx_rr3"))
        with LocalRuntime() as rt:
            rt.execute(wf, parameters={"query": self._QUERY})
        text = _flatten_message_text(_CAPTURED_MESSAGES.get("logic_verifier"))
        # The deterministic step_reasoner returned a `reasoning` field; the
        # composer renders the real chain into the verifier's messages.
        assert "compounds at 20%" in text, (
            "logic_verifier MUST receive the real step_reasoner reasoning chain "
            f"via `messages`; got: {text!r}"
        )

    # -- AgenticRAGNode: cyclic graph → standalone composer probes ------------

    def test_agentic_planner_composer_embeds_query(self):
        """The planner composer renders the REAL query into the planner's
        ``messages`` (production top-level-input delivery)."""
        from kaizen.nodes.rag.agentic import compose_planner_messages

        messages = _run_composer(
            PythonCodeNode.from_function(  # type: ignore[attr-defined]
                compose_planner_messages, name="planner_messages_composer"
            ),
            query=self._QUERY,
        )
        assert self._QUERY in _flatten_message_text(messages)

    def test_agentic_react_composer_embeds_query_and_observations(self):
        """The react composer renders the REAL query AND the real
        state_manager observations transcript into the react agent's
        ``messages`` (in-graph: `context_for_agent` is the genuine
        Thought/Action/Observation transcript)."""
        from kaizen.nodes.rag.agentic import compose_react_messages

        messages = _run_composer(
            PythonCodeNode.from_function(  # type: ignore[attr-defined]
                compose_react_messages, name="react_messages_composer"
            ),
            query=self._QUERY,
            context_for_agent=(
                "Thought: search financials\n"
                "Action: search(revenue)\n"
                "Observation: A grew 20%, B grew 15%"
            ),
        )
        text = _flatten_message_text(messages)
        assert self._QUERY in text
        assert "A grew 20%" in text, (
            "react composer MUST render the real observations transcript; "
            f"got: {text!r}"
        )

    def test_agentic_verifier_composer_embeds_answer_and_evidence(self):
        """The verifier composer renders the generated answer AND its
        supporting evidence (the observations across the reasoning steps,
        carried in `reasoning_state`) into the verifier's ``messages``."""
        from kaizen.nodes.rag.agentic import compose_verifier_messages

        messages = _run_composer(
            PythonCodeNode.from_function(  # type: ignore[attr-defined]
                compose_verifier_messages, name="verifier_messages_composer"
            ),
            reasoning_state={
                "steps": [
                    {
                        "thought": "compare growth",
                        "action": "search(revenue)",
                        "observation": "A grew 20%, B grew 15%",
                    }
                ],
                "final_answer": "A overtakes B in 4 years",
            },
        )
        text = _flatten_message_text(messages)
        # Both the answer AND the supporting evidence (observation) are present.
        assert "A overtakes B in 4 years" in text, "verifier MUST receive the answer"
        assert "A grew 20%" in text, (
            "verifier MUST receive the supporting evidence (observations); "
            f"got: {text!r}"
        )

    # -- Structural wiring guards (load-bearing — the production edge) --------

    def test_agentic_composers_wired_to_llm_messages_ports(self):
        """STRUCTURAL: each agentic LLM stage's ``messages`` port is fed by its
        composer's ``result.messages`` — and NO phantom inbound context port
        (`additional_context` / `answer_to_verify`) remains. Removing a
        composer→messages edge (the production wiring) breaks this test."""
        wf = _build(AgenticRAGNode(verification_enabled=True))
        edges = {
            (c.source_node, c.source_output, c.target_node, c.target_input)
            for c in wf.connections
        }
        assert (
            "planner_messages_composer",
            "result.messages",
            "planner_agent",
            "messages",
        ) in edges
        assert (
            "react_messages_composer",
            "result.messages",
            "react_agent",
            "messages",
        ) in edges
        assert (
            "verifier_messages_composer",
            "result.messages",
            "verifier_agent",
            "messages",
        ) in edges
        # The phantom edges the L3 fix removed MUST be gone.
        target_inputs = {(c.target_node, c.target_input) for c in wf.connections}
        assert ("react_agent", "additional_context") not in target_inputs
        assert ("verifier_agent", "answer_to_verify") not in target_inputs

    def test_reasoning_composers_wired_to_llm_messages_ports(self):
        """STRUCTURAL: each ReasoningRAGNode LLM stage's ``messages`` port is fed
        by its composer's ``result.messages``, and the phantom
        `reasoning_plan` / `reasoning_to_verify` LLM-input edges are gone."""
        wf = _build(ReasoningRAGNode())
        edges = {
            (c.source_node, c.source_output, c.target_node, c.target_input)
            for c in wf.connections
        }
        assert (
            "decomposer_messages_composer",
            "result.messages",
            "problem_decomposer",
            "messages",
        ) in edges
        assert (
            "step_reasoner_messages_composer",
            "result.messages",
            "step_reasoner",
            "messages",
        ) in edges
        assert (
            "logic_verifier_messages_composer",
            "result.messages",
            "logic_verifier",
            "messages",
        ) in edges
        # The phantom direct-to-LLM edges the L3 fix removed MUST be gone.
        target_inputs = {(c.target_node, c.target_input) for c in wf.connections}
        assert ("step_reasoner", "reasoning_plan") not in target_inputs
        assert ("logic_verifier", "reasoning_to_verify") not in target_inputs


# ===========================================================================
# O5 output-side proof — every LLM stage's REAL parsed output reaches its
# consumer (Wave: provably correct, not merely importable).
#
# The L3 wave proved the INPUT side (real context reaches each LLM stage via
# `messages`). This wave proves the OUTPUT side: each LLM stage's `response`
# port is PARSED (response.content -> json.loads / prose) by a dedicated
# `parse_*_response` node BEFORE its consumer reads structured fields.
#
# AgenticRAGNode's ReAct loop is a GENUINE pre-existing cycle, so its full
# graph cannot run under a plain `LocalRuntime` (the L3 disposition, unchanged).
# Output-side correctness is proven by (a) the consumer `code=` templates run
# under real `exec` against the PRODUCTION parser output, asserting the real
# parsed field reaches the consumer's published output (read-back), AND (b) a
# STRUCTURAL parser-wiring assertion that each LLM stage's `response` flows
# through its parser (the production guard). ReasoningRAGNode is acyclic and is
# already proven end-to-end above (the decomposition + reasoning chain reach
# their downstream composers via the parser, with the PRODUCTION
# `{"content": <JSON>}` adapter shape).
# ===========================================================================
class TestAgenticOutputSideParsed:
    """Each agentic LLM stage's REAL parsed output reaches its consumer — NOT
    the raw `{"content": ...}` wrapper off which the prior `.get("response")`
    read a non-existent key (state_manager crashed on `None.strip()`; the
    verifier verdict was silently dropped)."""

    # -- state_manager consumes the PARSED ReAct prose (read-back) ------------
    # Post-S6b the state_manager COMPUTE stage is the lifted
    # `_make_state_manager(...)` closure (a `PythonCodeNode.from_function` node).
    # The O5 parsed-output contract is exercised by calling the lifted function
    # directly with the parser OUTPUT shapes the production edges wire to.

    def test_state_manager_parses_react_answer_from_parsed_prose(self):
        """The state_manager line parser receives the reasoning_parser's
        OUTPUT (a bare prose string already unwrapped from `response.content`),
        extracts the Answer, and publishes it in `reasoning_state`. RED pre-O5:
        the consumer read `reasoning_response.get("response")` off the inner
        `{"content": ...}` dict -> None -> `None.strip()` AttributeError."""
        sm = _make_state_manager(5)
        out = sm(
            # plan_parser publishes `result.plan` = parsed planner dict.
            plan={"plan": [], "complexity": "simple"},
            # reasoning_parser publishes `result.reasoning_text` = bare prose str.
            reasoning_response=(
                "Thought: compare growth\nAction: search(revenue)\n"
                "Answer: A overtakes B in 4 years"
            ),
            tool_result=None,
        )
        rs = out["reasoning_state"]
        assert rs["final_answer"] == "A overtakes B in 4 years", (
            "state_manager MUST parse the ReAct Answer from the parsed prose; "
            f"got: {rs['final_answer']!r}"
        )
        assert rs["steps"][0]["thought"] == "compare growth"
        assert rs["steps"][0]["action"] == "search(revenue)"

    def test_state_manager_tolerates_empty_parsed_reasoning(self):
        """When the reasoning_parser emits "" (the honest "no reasoning yet"
        on an empty/missing `response.content`), the state_manager records an
        empty step WITHOUT crashing — no fabricated answer."""
        sm = _make_state_manager(5)
        out = sm(plan={}, reasoning_response="", tool_result=None)
        rs = out["reasoning_state"]
        # No Answer line -> final_answer stays None (honest), no crash.
        assert rs["final_answer"] is None
        assert rs["steps"][0]["thought"] is None

    # -- result_synthesizer consumes the PARSED verifier verdict -------------

    def test_synthesizer_applies_parsed_verifier_confidence(self):
        """The synthesizer receives the verification_parser's OUTPUT (the parsed
        verdict dict already unwrapped + json.loads'd from `response.content`)
        and applies its confidence. RED pre-O5: `verification.get("response")`
        off the inner `{"content": ...}` dict -> None -> verdict silently
        dropped, confidence never adjusted (stuck at base+boost)."""
        synth = _make_result_synthesizer("react", 5)
        out = synth(
            reasoning_state={
                "steps": [
                    {
                        "step_number": 1,
                        "thought": "t",
                        "action": "a",
                        "observation": {"tool": "search"},
                    }
                ],
                "final_answer": "A",
                "completed": True,
            },
            # verification_parser publishes `result.verification` = parsed dict.
            verification={"verified": True, "confidence": 0.5, "issues": []},
            query="q",
        )["agentic_rag_result"]
        # (base 0.7 + boost 0.1) * verdict 0.5 = 0.4 — the verdict WAS applied.
        assert out["confidence"] == pytest.approx(0.4), (
            "synthesizer MUST apply the parsed verifier confidence; "
            f"got: {out['confidence']!r} (0.8 means the verdict was dropped)"
        )
        # The real parsed verdict reaches the published output (read-back).
        assert out["verification"] == {
            "verified": True,
            "confidence": 0.5,
            "issues": [],
        }

    def test_synthesizer_honest_on_parse_error_sentinel(self):
        """When the verification_parser flags malformed verifier output with a
        typed `{"parse_error": ...}` sentinel, the synthesizer leaves confidence
        UNADJUSTED and publishes `verification: None` — it does NOT fabricate a
        0.8 verdict (zero-tolerance Rule 2)."""
        synth = _make_result_synthesizer("react", 5)
        out = synth(
            reasoning_state={
                "steps": [
                    {
                        "step_number": 1,
                        "thought": "t",
                        "action": "a",
                        "observation": {"tool": "search"},
                    }
                ],
                "final_answer": "A",
                "completed": True,
            },
            verification={"parse_error": "non-json-response"},
            query="q",
        )["agentic_rag_result"]
        # base 0.7 + boost 0.1 = 0.8, UNADJUSTED (no usable verdict).
        assert out["confidence"] == pytest.approx(0.8)
        assert out["verification"] is None

    # -- Structural parser-wiring guards (load-bearing — production edge) -----

    def test_agentic_response_ports_flow_through_parsers(self):
        """STRUCTURAL: each agentic LLM stage's `response` port feeds its
        `parse_*_response` parser, and the parser's parsed `result.*` feeds the
        consumer — NOT a direct LLM-`response` -> consumer edge (the pre-O5
        wiring that delivered the raw `{"content": ...}` wrapper)."""
        wf = _build(AgenticRAGNode(verification_enabled=True))
        edges = {
            (c.source_node, c.source_output, c.target_node, c.target_input)
            for c in wf.connections
        }
        # planner.response -> plan_parser -> state_manager.plan
        assert ("planner_agent", "response", "plan_parser", "response") in edges
        assert (
            "plan_parser",
            "result.plan",
            "state_manager",
            "plan",
        ) in edges
        # react.response -> reasoning_parser -> state_manager.reasoning_response
        assert ("react_agent", "response", "reasoning_parser", "response") in edges
        assert (
            "reasoning_parser",
            "result.reasoning_text",
            "state_manager",
            "reasoning_response",
        ) in edges
        # verifier.response -> verification_parser -> synthesizer.verification
        assert (
            "verifier_agent",
            "response",
            "verification_parser",
            "response",
        ) in edges
        assert (
            "verification_parser",
            "result.verification",
            "result_synthesizer",
            "verification",
        ) in edges
        # The pre-O5 direct LLM-response -> consumer edges MUST be gone.
        assert ("planner_agent", "response", "state_manager", "plan") not in edges
        assert (
            "react_agent",
            "response",
            "state_manager",
            "reasoning_response",
        ) not in edges
        assert (
            "verifier_agent",
            "response",
            "result_synthesizer",
            "verification",
        ) not in edges

    def test_reasoning_response_ports_flow_through_parsers(self):
        """STRUCTURAL: the ReasoningRAGNode decomposer + step_reasoner `response`
        ports feed their `parse_*_response` parsers, whose parsed output feeds
        the downstream composer — NOT a direct LLM-`response` -> composer edge."""
        wf = _build(ReasoningRAGNode())
        edges = {
            (c.source_node, c.source_output, c.target_node, c.target_input)
            for c in wf.connections
        }
        # decomposer.response -> decomposition_parser -> step_reasoner composer
        assert (
            "problem_decomposer",
            "response",
            "decomposition_parser",
            "response",
        ) in edges
        assert (
            "decomposition_parser",
            "result.reasoning_plan",
            "step_reasoner_messages_composer",
            "reasoning_plan",
        ) in edges
        # step_reasoner.response -> reasoning_chain_parser -> logic_verifier composer
        assert (
            "step_reasoner",
            "response",
            "reasoning_chain_parser",
            "response",
        ) in edges
        assert (
            "reasoning_chain_parser",
            "result.reasoning_to_verify",
            "logic_verifier_messages_composer",
            "reasoning_to_verify",
        ) in edges
        # The pre-O5 direct decomposer-response -> composer edges MUST be gone.
        assert (
            "problem_decomposer",
            "response",
            "step_reasoner_messages_composer",
            "reasoning_plan",
        ) not in edges
        assert (
            "step_reasoner",
            "response",
            "logic_verifier_messages_composer",
            "reasoning_to_verify",
        ) not in edges
