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

    def test_max_reasoning_steps_bound_into_state_manager(self):
        """``max_reasoning_steps`` is bound into the lifted state_manager closure.

        Post-S6b the state_manager is a ``PythonCodeNode.from_function`` node
        wrapping ``_make_state_manager(max_reasoning_steps)``; the step cap is
        bound through the closure (was an f-string interpolation). Behavioral
        proof: a single update at the cap marks the reasoning complete."""
        from kaizen.nodes.rag.agentic import _make_state_manager

        sm = _make_state_manager(1)  # cap of 1 → one update completes
        out = sm(
            plan=None,
            reasoning_response="Thought: t\nAction: search(x)",
            tool_result=None,
        )
        # current_step reaches the cap (1) → state marked completed → loop stops.
        assert out["reasoning_state"]["current_step"] == 1
        assert out["continue_reasoning"] is False

    def test_tools_interpolated_into_planner_prompt(self):
        """The constructor ``tools`` list appears in the planner system prompt."""
        wf = _build(AgenticRAGNode(tools=["search", "verify"]))
        prompt = wf.nodes["planner_agent"].config["system_prompt"]
        assert "search, verify" in prompt

    # --- COMPUTE-stage lifted functions (post-S6b from_function migration) ---
    def test_result_synthesizer_fn_binds_config(self):
        """The lifted result_synthesizer closure binds the constructor config
        into metadata and produces the documented result dict.

        Regression guard: the block was once a plain (non-f) string with literal
        ``{self.planning_strategy}`` — invalid Python at runtime. Post-S6b it is
        ``_make_result_synthesizer(planning_strategy, max_reasoning_steps)``."""
        from kaizen.nodes.rag.agentic import _make_result_synthesizer

        synth = _make_result_synthesizer("react", 6)
        out = synth(
            reasoning_state={"steps": [], "final_answer": "ans", "completed": True},
            query="q",
        )
        meta = out["agentic_rag_result"]["metadata"]
        assert meta["planning_strategy"] == "react"
        assert meta["max_steps"] == 6
        assert meta["completed_successfully"] is True

    def test_tool_executor_fn_search_over_documents(self):
        """The lifted ``execute_tool_action`` runs a real keyword search over
        documents when given a search action."""
        from kaizen.nodes.rag.agentic import execute_tool_action

        out = execute_tool_action(
            reasoning_state={"current_action": 'search("transformer")'},
            documents=[{"id": "d", "content": "the transformer model"}],
        )
        tr = out["tool_result"]
        assert tr["tool"] == "search"
        assert tr["count"] == 1

    def test_tool_executor_fn_calculate_action(self):
        """The lifted ``execute_tool_action`` ``calculate`` action evaluates
        safe arithmetic via the AST-walked evaluator."""
        from kaizen.nodes.rag.agentic import execute_tool_action

        out = execute_tool_action(
            reasoning_state={"current_action": "calculate(2 + 3 * 4)"},
            documents=[],
        )
        assert out["tool_result"]["result"] == 14


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


# ==========================================================================
# F31-FU2 Shard B — direct-call Tier-1 coverage of the pure parser / composer
# `from_function` targets in ``agentic.py`` (module-level functions wired into
# the inner workflows via ``PythonCodeNode.from_function``). These are pure
# data rendering / tool-result parsing (the permitted deterministic exceptions
# per rules/agent-reasoning.md #3 + #6) — NOT agent decision-making. Called
# DIRECTLY (no LocalRuntime, no mocking — they are pure functions).
#
# NOTE on agentic-vs-query_processing divergence (read the source, reconciled):
# ``agentic.py`` has NO shared ``_loads_response_object`` helper. Each parser
# is hand-written and the sentinel shape DIFFERS PER PARSER:
#   * parse_reasoning_response / parse_reasoning_chain_response are PROSE / raw
#     forwarders — they NEVER emit a ``parse_error`` and NEVER json.loads the
#     content into a sentinel; an empty/None content yields an HONEST empty
#     string (``""``), not an ``"empty-response"`` sentinel.
#   * parse_plan_response / parse_verification_response ARE JSON stages with a
#     typed sentinel — BUT their EMPTY default is an honest ``{}`` with NO
#     ``parse_error`` key (query_processing.py emits ``parse_error ==
#     "empty-response"`` on empty; agentic does NOT). Malformed content DOES
#     carry the typed sentinel: ``non-json-response`` / ``non-object-json`` /
#     ``unexpected-content-type``.
#   * parse_decomposition_response / parse_reasoning_chain_response FORWARD the
#     raw value faithfully: a non-JSON string is forwarded AS-IS (no sentinel);
#     a JSON array/scalar is forwarded as the PARSED list/number (NOT a
#     ``non-object-json`` sentinel — the decomposition/chain composers render
#     whatever shape is present); a non-str/non-dict content is coerced to text.
# Every EMPTY / MALFORMED assertion below asserts the parser's OWN honest
# default (zero-tolerance Rule 2) — never a fabricated value borrowed from the
# query_processing contract.
# ==========================================================================

import json

from kaizen.nodes.rag.agentic import (
    _unwrap_response_content,
    compose_decomposer_messages,
    compose_logic_verifier_messages,
    compose_planner_messages,
    compose_react_messages,
    compose_step_reasoner_messages,
    compose_verifier_messages,
    parse_decomposition_response,
    parse_plan_response,
    parse_reasoning_chain_response,
    parse_reasoning_response,
    parse_verification_response,
)


def _wrap(obj) -> dict:
    """Build the LLMAgentNode ``response`` port shape with JSON-string content."""
    return {"content": json.dumps(obj)}


class TestUnwrapResponseContent:
    """``_unwrap_response_content``: dict -> .content, bare value -> passthrough."""

    def test_unwrap_dict_returns_content(self):
        assert _unwrap_response_content({"content": "hello"}) == "hello"

    def test_unwrap_dict_missing_content_returns_none(self):
        # A dict without a "content" key -> .get("content") -> None.
        assert _unwrap_response_content({"other": "x"}) is None

    def test_unwrap_bare_string_passthrough(self):
        assert _unwrap_response_content("raw string") == "raw string"

    def test_unwrap_none_passthrough(self):
        assert _unwrap_response_content(None) is None


# --------------------------------------------------------------------------
# PROSE parser — parse_reasoning_response. Returns {"reasoning_text": <str>};
# NEVER a json.loads sentinel. None/empty -> honest "" (not "empty-response").
# --------------------------------------------------------------------------


class TestParseReasoningResponse:
    def test_parse_reasoning_valid_prose_returns_text(self):
        prose = "Thought: search\nAction: search(x)\nAnswer: done"
        result = parse_reasoning_response({"content": prose})
        assert result["reasoning_text"] == prose
        assert "parse_error" not in result  # PROSE stage never flags

    def test_parse_reasoning_none_returns_empty_text(self):
        # None content -> honest "" (no fabricated reasoning), NOT a sentinel.
        result = parse_reasoning_response(None)
        assert result["reasoning_text"] == ""
        assert "parse_error" not in result

    def test_parse_reasoning_dict_missing_content_returns_empty_text(self):
        # {"other": ...} -> .get("content") is None -> honest "".
        result = parse_reasoning_response({"other": "x"})
        assert result["reasoning_text"] == ""

    def test_parse_reasoning_bare_string_passthrough(self):
        # Defensive: a bare string (not wrapped) is used directly.
        result = parse_reasoning_response("plain prose")
        assert result["reasoning_text"] == "plain prose"

    def test_parse_reasoning_preparsed_dict_coerced_to_text(self):
        # A pre-parsed dict from some providers -> _coerce_text faithfully.
        result = parse_reasoning_response({"content": {"answer": "42"}})
        assert isinstance(result["reasoning_text"], str)
        assert "42" in result["reasoning_text"]


# --------------------------------------------------------------------------
# JSON parsers with typed sentinel — parse_plan_response /
# parse_verification_response. EMPTY default is an HONEST {} with NO
# parse_error (agentic diverges from query_processing here — read source).
# Malformed content DOES carry the typed sentinel.
# --------------------------------------------------------------------------


class TestParsePlanResponse:
    def test_parse_plan_valid_returns_dict(self):
        obj = {"plan": [{"step": 1, "action": "search"}], "complexity": "moderate"}
        result = parse_plan_response(_wrap(obj))
        assert result["plan"] == obj
        assert "parse_error" not in result["plan"]

    def test_parse_plan_already_dict_returns_dict(self):
        obj = {"plan": [{"step": 1}]}
        result = parse_plan_response({"content": obj})
        assert result["plan"] == obj
        assert "parse_error" not in result["plan"]

    def test_parse_plan_none_returns_honest_empty_no_sentinel(self):
        # agentic's HONEST empty default is {} with NO parse_error
        # (query_processing emits "empty-response"; agentic does NOT).
        result = parse_plan_response(None)
        assert result["plan"] == {}
        assert "parse_error" not in result["plan"]

    def test_parse_plan_empty_content_returns_honest_empty_no_sentinel(self):
        result = parse_plan_response({"content": ""})
        assert result["plan"] == {}
        assert "parse_error" not in result["plan"]

    def test_parse_plan_non_json_returns_non_json_sentinel(self):
        result = parse_plan_response({"content": "not json{"})
        assert result["plan"] == {"parse_error": "non-json-response"}

    def test_parse_plan_array_returns_non_object_sentinel(self):
        result = parse_plan_response({"content": "[1,2,3]"})
        assert result["plan"] == {"parse_error": "non-object-json"}

    def test_parse_plan_bad_content_type_returns_unexpected_sentinel(self):
        result = parse_plan_response({"content": 42})
        assert result["plan"] == {"parse_error": "unexpected-content-type"}


class TestParseVerificationResponse:
    def test_parse_verification_valid_returns_dict(self):
        obj = {"verified": True, "confidence": 0.9, "issues": []}
        result = parse_verification_response(_wrap(obj))
        assert result["verification"] == obj
        assert "parse_error" not in result["verification"]

    def test_parse_verification_already_dict_returns_dict(self):
        obj = {"verified": False, "confidence": 0.4}
        result = parse_verification_response({"content": obj})
        assert result["verification"] == obj
        assert "parse_error" not in result["verification"]

    def test_parse_verification_none_returns_honest_empty_no_sentinel(self):
        # Honest empty {} — a flagged/fabricated verdict would silently
        # inflate or deflate confidence downstream (zero-tolerance Rule 2).
        result = parse_verification_response(None)
        assert result["verification"] == {}
        assert "parse_error" not in result["verification"]

    def test_parse_verification_empty_content_returns_honest_empty(self):
        result = parse_verification_response({"content": "   "})
        assert result["verification"] == {}
        assert "parse_error" not in result["verification"]

    def test_parse_verification_non_json_returns_non_json_sentinel(self):
        result = parse_verification_response({"content": "not json{"})
        assert result["verification"] == {"parse_error": "non-json-response"}

    def test_parse_verification_array_returns_non_object_sentinel(self):
        result = parse_verification_response({"content": "[1,2,3]"})
        assert result["verification"] == {"parse_error": "non-object-json"}

    def test_parse_verification_bad_content_type_returns_unexpected_sentinel(self):
        result = parse_verification_response({"content": 42})
        assert result["verification"] == {"parse_error": "unexpected-content-type"}


# --------------------------------------------------------------------------
# FORWARDING parsers — parse_decomposition_response /
# parse_reasoning_chain_response. They FORWARD the real value faithfully (the
# downstream composer's _render_reasoning_plan renders whatever shape is
# present). NO typed parse_error sentinel: non-JSON prose is forwarded AS-IS,
# a JSON array/scalar is forwarded as the PARSED value, a non-str/dict is
# coerced to text. None -> honest "" (not a sentinel).
# --------------------------------------------------------------------------


class TestParseDecompositionResponse:
    def test_parse_decomposition_valid_json_forwards_parsed_dict(self):
        obj = {"steps": [{"step": 1, "goal": "x"}], "assumptions": []}
        result = parse_decomposition_response(_wrap(obj))
        assert result["reasoning_plan"] == obj
        assert "parse_error" not in result

    def test_parse_decomposition_already_dict_forwards_dict(self):
        obj = {"steps": [{"step": 1}]}
        result = parse_decomposition_response({"content": obj})
        assert result["reasoning_plan"] == obj

    def test_parse_decomposition_none_returns_honest_empty_string(self):
        # None -> "" (honest no-decomposition), NEVER a fabricated sentinel.
        result = parse_decomposition_response(None)
        assert result["reasoning_plan"] == ""
        assert "parse_error" not in result

    def test_parse_decomposition_non_json_forwards_raw_prose(self):
        # Non-JSON prose is FORWARDED AS-IS (the composer renders it) — agentic
        # does NOT emit a "non-json-response" sentinel here. Read source.
        result = parse_decomposition_response({"content": "Step 1: do x"})
        assert result["reasoning_plan"] == "Step 1: do x"
        assert "parse_error" not in result

    def test_parse_decomposition_array_forwards_parsed_list(self):
        # Valid JSON array is FORWARDED as the parsed list — NOT a
        # "non-object-json" sentinel (diverges from the plan parser).
        result = parse_decomposition_response({"content": "[1,2,3]"})
        assert result["reasoning_plan"] == [1, 2, 3]
        assert "parse_error" not in result

    def test_parse_decomposition_bad_content_type_coerced_to_text(self):
        # Non-str/non-dict content is _coerce_text'd faithfully, no sentinel.
        result = parse_decomposition_response({"content": 42})
        assert result["reasoning_plan"] == "42"
        assert "parse_error" not in result


class TestParseReasoningChainResponse:
    def test_parse_chain_valid_json_forwards_parsed(self):
        obj = {"steps": [{"step": 1, "goal": "y"}]}
        result = parse_reasoning_chain_response(_wrap(obj))
        assert result["reasoning_to_verify"] == obj
        assert "parse_error" not in result

    def test_parse_chain_already_dict_forwards_dict(self):
        obj = {"conclusion": "z"}
        result = parse_reasoning_chain_response({"content": obj})
        assert result["reasoning_to_verify"] == obj

    def test_parse_chain_none_returns_honest_empty_string(self):
        result = parse_reasoning_chain_response(None)
        assert result["reasoning_to_verify"] == ""
        assert "parse_error" not in result

    def test_parse_chain_non_json_forwards_raw_prose(self):
        result = parse_reasoning_chain_response({"content": "the logic holds"})
        assert result["reasoning_to_verify"] == "the logic holds"
        assert "parse_error" not in result

    def test_parse_chain_array_forwards_parsed_list(self):
        result = parse_reasoning_chain_response({"content": "[1,2,3]"})
        assert result["reasoning_to_verify"] == [1, 2, 3]
        assert "parse_error" not in result

    def test_parse_chain_bad_content_type_coerced_to_text(self):
        result = parse_reasoning_chain_response({"content": 42})
        assert result["reasoning_to_verify"] == "42"
        assert "parse_error" not in result


# --------------------------------------------------------------------------
# Composers — one direct test per variant (VALID interpolation + EMPTY).
# Each returns a well-formed {"messages": [{"role","content"}, ...]} shape.
# --------------------------------------------------------------------------


def _assert_messages_shape(result):
    """Assert the composer return is a well-formed OpenAI chat ``messages`` list."""
    assert isinstance(result, dict)
    assert "messages" in result
    msgs = result["messages"]
    assert isinstance(msgs, list) and len(msgs) >= 1
    for m in msgs:
        assert isinstance(m, dict)
        assert "role" in m and "content" in m
    return msgs


class TestComposePlannerMessages:
    def test_compose_planner_valid_interpolates_query(self):
        msgs = _assert_messages_shape(
            compose_planner_messages(query="Compare revenue growth")
        )
        assert "Compare revenue growth" in msgs[0]["content"]

    def test_compose_planner_empty_returns_wellformed(self):
        msgs = _assert_messages_shape(compose_planner_messages(query=""))
        # Honest no-query content — structurally valid, no crash.
        assert "No query" in msgs[0]["content"]


class TestComposeReactMessages:
    def test_compose_react_valid_interpolates_query_and_observations(self):
        msgs = _assert_messages_shape(
            compose_react_messages(
                query="What is BERT?",
                context_for_agent="Thought: search\nObservation: found",
            )
        )
        content = msgs[0]["content"]
        assert "What is BERT?" in content
        # Real accumulated observations rendered into the ReAct messages.
        assert "Observation: found" in content

    def test_compose_react_empty_query_no_observations_returns_wellformed(self):
        # First-pass honesty: no tool has run yet -> explicit "no observations".
        msgs = _assert_messages_shape(
            compose_react_messages(query="", context_for_agent=None)
        )
        content = msgs[0]["content"]
        assert "(empty)" in content
        assert "No observations gathered yet" in content


class TestComposeVerifierMessages:
    def test_compose_verifier_valid_renders_transcript(self):
        state = {
            "steps": [{"thought": "t", "action": "a", "observation": "o"}],
            "final_answer": "the answer",
        }
        msgs = _assert_messages_shape(compose_verifier_messages(reasoning_state=state))
        content = msgs[0]["content"]
        # The answer AND its supporting evidence (observations) are rendered.
        assert "the answer" in content
        assert "Observation: o" in content

    def test_compose_verifier_empty_state_returns_wellformed(self):
        msgs = _assert_messages_shape(compose_verifier_messages(reasoning_state=None))
        assert "No answer or evidence" in msgs[0]["content"]


class TestComposeDecomposerMessages:
    def test_compose_decomposer_valid_interpolates_query(self):
        msgs = _assert_messages_shape(
            compose_decomposer_messages(query="Solve this multi-step problem")
        )
        assert "Solve this multi-step problem" in msgs[0]["content"]

    def test_compose_decomposer_empty_returns_wellformed(self):
        msgs = _assert_messages_shape(compose_decomposer_messages(query=""))
        assert "No problem" in msgs[0]["content"]


class TestComposeStepReasonerMessages:
    def test_compose_step_reasoner_valid_interpolates_query_and_plan(self):
        plan = {"steps": [{"step": 1, "goal": "compute growth"}]}
        msgs = _assert_messages_shape(
            compose_step_reasoner_messages(query="Revenue math", reasoning_plan=plan)
        )
        content = msgs[0]["content"]
        assert "Revenue math" in content
        # The real upstream decomposition is rendered into the reasoner's input.
        assert "compute growth" in content

    def test_compose_step_reasoner_empty_query_none_plan_returns_wellformed(self):
        msgs = _assert_messages_shape(
            compose_step_reasoner_messages(query="", reasoning_plan=None)
        )
        content = msgs[0]["content"]
        assert "(empty)" in content
        # Always appends the explicit next-step instruction.
        assert "Execute the next reasoning step." in content


class TestComposeLogicVerifierMessages:
    def test_compose_logic_verifier_valid_renders_chain(self):
        chain = {"steps": [{"step": 1, "goal": "premise A"}]}
        msgs = _assert_messages_shape(
            compose_logic_verifier_messages(reasoning_to_verify=chain)
        )
        assert "premise A" in msgs[0]["content"]

    def test_compose_logic_verifier_empty_returns_wellformed(self):
        msgs = _assert_messages_shape(
            compose_logic_verifier_messages(reasoning_to_verify=None)
        )
        assert "No reasoning chain" in msgs[0]["content"]
