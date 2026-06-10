"""Tier-1 unit coverage for the 3 ``kaizen.nodes.rag.agentic`` nodes.

F8 shard B3. The value-anchor (verbatim from the workstream brief): "the RAG
capability the user chose to preserve is provably correct, not merely
importable." Agentic is the most defect-prone RAG path per the plan.

``agentic.py`` ships three nodes:

- ``ToolAugmentedRAGNode`` — a ``Node`` with a direct, deterministic ``run()``.
  Detects required tools by keyword, invokes registered tool callables, and
  synthesizes an answer. No LLM key needed — the synthesis is rule-based.
- ``AgenticRAGNode`` — a ``WorkflowNode``; its behavior is a sub-workflow built
  by ``_create_workflow()``. Construction + workflow shape + the ``code=``
  ``PythonCodeNode`` templates are covered here. The LLM-backed sub-workflow
  steps and end-to-end runtime are not exercised (no LLM key in ``[rag]``).
- ``ReasoningRAGNode`` — a ``WorkflowNode``; same coverage shape as
  ``AgenticRAGNode``.

Assertions are structural (output keys, tool lists, confidence ranges, node
counts, typed raises). One test per documented behavior. The ``code=``
templates of the WorkflowNodes are exercised directly via ``exec`` against
malformed input — the B1 codegen-regression pattern.
"""

from __future__ import annotations

import warnings

import pytest

from kaizen.nodes.rag.agentic import (
    AgenticRAGNode,
    ReasoningRAGNode,
    ToolAugmentedRAGNode,
)

pytestmark = pytest.mark.unit


_DOCS = [
    {"id": "d1", "content": "the transformer model and self-attention"},
    {"id": "d2", "content": "a plain document about sequences", "title": "Seqs"},
]


def _build(node):
    """Build a WorkflowNode's sub-workflow, silencing the cosmetic
    PythonCodeNode 'exceeds recommended line count' UserWarnings."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return node._create_workflow()


# ===========================================================================
# ToolAugmentedRAGNode — direct run() path
# ===========================================================================
class TestToolAugmentedRAGNode:
    """``ToolAugmentedRAGNode.run()`` — keyword tool detection + synthesis."""

    def test_get_parameters_declares_query_required(self):
        params = ToolAugmentedRAGNode().get_parameters()
        assert params["query"].required is True
        assert params["query"].type is str
        assert params["documents"].required is False
        assert params["tool_registry"].required is False
        assert params["auto_detect_tools"].required is False

    def test_golden_path_returns_documented_keys(self):
        """``run()`` returns the four documented keys."""
        result = ToolAugmentedRAGNode().run(query="summarize the docs", documents=_DOCS)
        assert sorted(result.keys()) == [
            "answer",
            "confidence",
            "tool_outputs",
            "tools_invoked",
        ]
        assert isinstance(result["answer"], str)
        assert isinstance(result["tools_invoked"], list)

    def test_calculator_tool_detected_by_keyword(self):
        """A query containing 'calculate' detects the calculator tool."""
        result = ToolAugmentedRAGNode().run(query="calculate the sum", documents=[])
        assert "calculator" in result["tools_invoked"]

    def test_unit_converter_and_date_tools_detected(self):
        """'convert' detects unit_converter; 'days' detects date_calculator."""
        r1 = ToolAugmentedRAGNode().run(query="convert these units", documents=[])
        assert "unit_converter" in r1["tools_invoked"]
        r2 = ToolAugmentedRAGNode().run(query="how many days remain", documents=[])
        assert "date_calculator" in r2["tools_invoked"]

    def test_no_tool_keyword_yields_empty_tools_invoked(self):
        """A query with no tool keyword invokes no tools."""
        result = ToolAugmentedRAGNode().run(query="what is the topic", documents=_DOCS)
        assert result["tools_invoked"] == []

    def test_confidence_higher_when_tools_produce_output(self):
        """Confidence is 0.9 when a registered tool produced output, else 0.7."""
        registry = {"calculator": lambda _q, _c: {"value": 42}}
        with_tool = ToolAugmentedRAGNode(tool_registry=registry).run(
            query="calculate sum", documents=[]
        )
        assert with_tool["confidence"] == 0.9
        no_tool = ToolAugmentedRAGNode().run(query="describe the docs", documents=[])
        assert no_tool["confidence"] == 0.7

    def test_unregistered_detected_tool_yields_no_output(self):
        """A tool detected by keyword but absent from the registry simply
        produces no tool output — it is still listed in tools_invoked."""
        result = ToolAugmentedRAGNode(tool_registry={}).run(
            query="calculate the total", documents=[]
        )
        assert "calculator" in result["tools_invoked"]
        assert result["tool_outputs"] == {}
        assert result["confidence"] == 0.7

    def test_failing_tool_callable_is_captured_as_error(self):
        """A registered tool that raises is captured as an {'error': ...}
        entry rather than crashing run()."""

        def boom(_query, _context):
            raise RuntimeError("tool exploded")

        result = ToolAugmentedRAGNode(tool_registry={"calculator": boom}).run(
            query="calculate", documents=[]
        )
        assert "error" in result["tool_outputs"]["calculator"]
        assert "tool exploded" in result["tool_outputs"]["calculator"]["error"]

    # --- documented edge cases ------------------------------------------
    def test_empty_query_and_documents_does_not_crash(self):
        result = ToolAugmentedRAGNode().run(query="", documents=[])
        assert result["tools_invoked"] == []
        assert result["confidence"] == 0.7

    def test_missing_documents_kwarg_defaults_to_empty(self):
        """``documents`` is optional; omitting it defaults to []."""
        result = ToolAugmentedRAGNode().run(query="calculate sum")
        assert "0 documents" in result["answer"]

    def test_malformed_documents_do_not_crash_run(self):
        """Non-dict elements, {} and {"content": None} are tolerated —
        synthesis only counts len(documents)."""
        result = ToolAugmentedRAGNode().run(
            query="describe", documents=["not a dict", {}, {"content": None}]
        )
        assert "3 documents" in result["answer"]

    def test_unicode_query_is_preserved_in_answer(self):
        result = ToolAugmentedRAGNode().run(query="résumé café 日本語", documents=[])
        assert "résumé café 日本語" in result["answer"]


# ===========================================================================
# AgenticRAGNode — WorkflowNode construction + sub-workflow shape
# ===========================================================================
class TestAgenticRAGNode:
    """``AgenticRAGNode`` is a ``WorkflowNode``; coverage is its construction
    and the shape of the workflow ``_create_workflow()`` builds."""

    def test_constructs_with_defaults(self):
        # The constructor resolves `tools or [...]` defaults onto instance
        # attributes; node.config captures the *raw* kwarg (None for a default
        # tools=), so the instance attrs are the canonical post-construction
        # surface. The @register_node decorator erases the concrete type to
        # the Node base, hence the targeted attr-defined ignores below.
        node = AgenticRAGNode()
        assert node.tools == ["search", "calculator", "database"]  # type: ignore[attr-defined]
        assert node.max_reasoning_steps == 5  # type: ignore[attr-defined]
        assert node.planning_strategy == "react"  # type: ignore[attr-defined]
        assert node.verification_enabled is True  # type: ignore[attr-defined]

    def test_constructor_config_overrides_apply(self):
        node = AgenticRAGNode(
            tools=["search"],
            max_reasoning_steps=9,
            planning_strategy="tree-of-thought",
            verification_enabled=False,
        )
        assert node.tools == ["search"]  # type: ignore[attr-defined]
        assert node.max_reasoning_steps == 9  # type: ignore[attr-defined]
        assert node.planning_strategy == "tree-of-thought"  # type: ignore[attr-defined]
        assert node.verification_enabled is False  # type: ignore[attr-defined]

    def test_workflow_has_twelve_nodes_with_verification(self):
        """With verification enabled the sub-workflow has twelve nodes: the 6
        original nodes, the 3 L3 messages-composers (planner / react / verifier)
        that render real context into each LLM stage's ``messages`` port, AND
        the 3 O5 output-side response parsers (plan / reasoning / verification)
        that unwrap each LLM stage's ``response.content`` before its consumer."""
        wf = _build(AgenticRAGNode(verification_enabled=True))
        assert set(wf.nodes) == {
            "planner_agent",
            "react_agent",
            "tool_executor",
            "state_manager",
            "verifier_agent",
            "result_synthesizer",
            "planner_messages_composer",
            "react_messages_composer",
            "verifier_messages_composer",
            "plan_parser",
            "reasoning_parser",
            "verification_parser",
        }

    def test_workflow_omits_verifier_when_disabled(self):
        """With verification disabled the verifier_agent node, its
        messages-composer, AND the verification_parser are omitted — nine nodes
        remain (5 original + planner/react composers + plan/reasoning parsers)."""
        wf = _build(AgenticRAGNode(verification_enabled=False))
        assert "verifier_agent" not in wf.nodes
        assert "verifier_messages_composer" not in wf.nodes
        assert "verification_parser" not in wf.nodes
        assert len(wf.nodes) == 9

    def test_max_reasoning_steps_interpolated_into_state_manager(self):
        """``max_reasoning_steps`` flows into the state_manager code template."""
        wf = _build(AgenticRAGNode(max_reasoning_steps=8))
        code = wf.nodes["state_manager"].config["code"]
        assert 'state["current_step"] >= 8' in code

    def test_tools_interpolated_into_planner_prompt(self):
        """The constructor ``tools`` list appears in the planner system prompt."""
        wf = _build(AgenticRAGNode(tools=["search", "verify"]))
        prompt = wf.nodes["planner_agent"].config["system_prompt"]
        assert "search, verify" in prompt

    # --- result_synthesizer code template (B1 codegen-regression pattern) -
    def test_result_synthesizer_template_executes(self):
        """The result_synthesizer ``code=`` template runs without NameError
        and interpolates the constructor config into metadata.

        Regression guard: the block was once a plain (non-f) string with
        literal ``{self.planning_strategy}`` — invalid Python at runtime."""
        wf = _build(AgenticRAGNode(planning_strategy="react", max_reasoning_steps=6))
        code = wf.nodes["result_synthesizer"].config["code"]
        ns = {
            "reasoning_state": {"steps": [], "final_answer": "ans", "completed": True},
            "query": "q",
        }
        exec(code, ns)
        meta = ns["result"]["agentic_rag_result"]["metadata"]
        assert meta["planning_strategy"] == "react"
        assert meta["max_steps"] == 6
        assert meta["completed_successfully"] is True

    def test_tool_executor_template_search_over_documents(self):
        """The tool_executor ``code=`` template runs a real keyword search
        over documents when given a search action."""
        wf = _build(AgenticRAGNode())
        code = wf.nodes["tool_executor"].config["code"]
        ns = {
            "reasoning_state": {"current_action": 'search("transformer")'},
            "documents": [{"id": "d", "content": "the transformer model"}],
        }
        exec(code, ns)
        tr = ns["result"]["tool_result"]
        assert tr["tool"] == "search"
        assert tr["count"] == 1

    def test_tool_executor_template_calculate_action(self):
        """The tool_executor ``calculate`` action evaluates safe arithmetic."""
        wf = _build(AgenticRAGNode())
        code = wf.nodes["tool_executor"].config["code"]
        ns = {
            "reasoning_state": {"current_action": "calculate(2 + 3 * 4)"},
            "documents": [],
        }
        exec(code, ns)
        assert ns["result"]["tool_result"]["result"] == 14


# ===========================================================================
# ReasoningRAGNode — WorkflowNode construction + sub-workflow shape
# ===========================================================================
class TestReasoningRAGNode:
    """``ReasoningRAGNode`` is a ``WorkflowNode``; coverage is its
    construction and the shape of the workflow ``_create_workflow()`` builds."""

    def test_constructs_with_defaults(self):
        # Instance attrs are the canonical post-construction surface — see the
        # AgenticRAGNode note above for the @register_node type-erasure.
        node = ReasoningRAGNode()
        assert node.reasoning_depth == 3  # type: ignore[attr-defined]
        assert node.strategy == "chain_of_thought"  # type: ignore[attr-defined]

    def test_constructor_config_overrides_apply(self):
        node = ReasoningRAGNode(reasoning_depth=5, strategy="tree_of_thought")
        assert node.reasoning_depth == 5  # type: ignore[attr-defined]
        assert node.strategy == "tree_of_thought"  # type: ignore[attr-defined]

    def test_workflow_has_eight_nodes(self):
        """The reasoning sub-workflow always has eight nodes: the 3 LLM stages,
        the 3 L3 messages-composers (one per LLM stage) that render real context
        into each ``messages`` port, AND the 2 O5 output-side response parsers
        (decomposition / reasoning-chain) that unwrap the decomposer's and
        step_reasoner's ``response.content`` before the downstream composer."""
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

    def test_strategy_and_depth_interpolated_into_decomposer_prompt(self):
        """``strategy`` and ``reasoning_depth`` flow into the decomposer
        system prompt."""
        wf = _build(ReasoningRAGNode(reasoning_depth=4, strategy="tree_of_thought"))
        prompt = wf.nodes["problem_decomposer"].config["system_prompt"]
        assert "Strategy: tree_of_thought" in prompt
        assert "Max depth: 4" in prompt
