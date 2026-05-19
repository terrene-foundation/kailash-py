"""Regression: four latent ``kaizen.nodes.rag.agentic`` defects.

F8 shard B3 surfaced four crashes via behavioral coverage of the agentic RAG
nodes. Each is fixed in ``agentic.py`` in the same shard.

Defect 1 — tool_executor codegen None-content / non-dict crash.
  The ``tool_executor`` ``code=`` template's ``search`` branch extracted
  document text via ``doc.get("content", "").lower()``. The ``""`` default
  applies ONLY to a MISSING key; a document ``{"content": None}`` returned
  ``None`` and ``.lower()`` raised ``AttributeError``. A non-dict document
  element also crashed on ``str.get``.
  Fix: ``isinstance(doc, dict)`` skip + ``(doc.get("content") or "")``.

Defect 2 — result_synthesizer codegen NameError.
  The ``result_synthesizer`` ``code=`` block was a plain (non-f) string yet
  embedded ``{self.planning_strategy}`` / ``{self.max_reasoning_steps}``
  meant for interpolation. At ``PythonCodeNode`` sandbox runtime these
  became invalid ``self.x`` references raising ``NameError`` — the agentic
  result-synthesis step never produced its metadata block.
  Fix: convert the block to an f-string with doubled literal braces,
  matching the sibling ``state_manager`` template.

Defect 3 — ToolAugmentedRAGNode None-query crash.
  ``_detect_required_tools()`` called ``query.lower()``; an explicit
  ``query=None`` raised ``AttributeError``.
  Fix: ``(query or "").lower()``.

Defect 4 — ToolAugmentedRAGNode non-dict tool-output crash.
  ``_synthesize_with_tools()`` ran ``"error" not in output``; a registered
  tool callable returning a non-dict value (tools are arbitrary user
  callables with no return-shape contract) raised ``TypeError``.
  Fix: ``not isinstance(output, dict) or "error" not in output``.

Defects 1 + 2 are ``_create_workflow()`` codegen-template defects; defects
3 + 4 are ``run()``-path defects. Per the B1 two-path lesson, both the
``run()`` paths and the codegen templates were grepped for each pattern.

All tests are behavioral — they call ``run()`` / exec the real codegen
template and assert success / typed outputs, not source-grep.
"""

from __future__ import annotations

import warnings

import pytest

from kaizen.nodes.rag.agentic import AgenticRAGNode, ToolAugmentedRAGNode

pytestmark = pytest.mark.regression


def _template(node, node_id):
    """Return a built sub-workflow node's code= template, silencing the
    cosmetic PythonCodeNode line-count UserWarnings."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return node._create_workflow().nodes[node_id].config["code"]


# ---------------------------------------------------------------------------
# Defect 1 — tool_executor codegen None-content / non-dict crash
# ---------------------------------------------------------------------------
def test_tool_executor_none_content_does_not_crash():
    """The tool_executor search branch must tolerate a document whose
    ``content`` key is present-but-None."""
    code = _template(AgenticRAGNode(), "tool_executor")
    ns = {
        "reasoning_state": {"current_action": 'search("transformer")'},
        "documents": [{"id": "n", "content": None}],
    }
    exec(code, ns)
    assert ns["result"]["tool_result"]["tool"] == "search"
    assert ns["result"]["tool_result"]["count"] == 0


def test_tool_executor_none_title_does_not_crash():
    """A present-but-None ``title`` must not crash the search branch."""
    code = _template(AgenticRAGNode(), "tool_executor")
    ns = {
        "reasoning_state": {"current_action": 'search("transformer")'},
        "documents": [{"id": "n", "content": "transformer model", "title": None}],
    }
    exec(code, ns)
    assert ns["result"]["tool_result"]["count"] == 1


def test_tool_executor_non_dict_document_is_skipped():
    """A non-dict element in ``documents`` is skipped, not crashed on."""
    code = _template(AgenticRAGNode(), "tool_executor")
    ns = {
        "reasoning_state": {"current_action": 'search("transformer")'},
        "documents": ["not a dict", {"id": "g", "content": "transformer here"}],
    }
    exec(code, ns)
    assert ns["result"]["tool_result"]["count"] == 1


def test_tool_executor_none_content_does_not_poison_sibling():
    """A None-content document must not block a well-formed sibling from
    matching the search query."""
    code = _template(AgenticRAGNode(), "tool_executor")
    ns = {
        "reasoning_state": {"current_action": 'search("transformer")'},
        "documents": [
            {"id": "bad", "content": None},
            {"id": "good", "content": "the transformer model"},
        ],
    }
    exec(code, ns)
    assert ns["result"]["tool_result"]["count"] == 1
    assert ns["result"]["tool_result"]["results"][0]["id"] == "good"


# ---------------------------------------------------------------------------
# Defect 2 — result_synthesizer codegen NameError
# ---------------------------------------------------------------------------
def test_result_synthesizer_template_does_not_raise_nameerror():
    """The result_synthesizer ``code=`` template must execute without a
    NameError — it was once a plain string with literal {self.x}."""
    code = _template(AgenticRAGNode(), "result_synthesizer")
    ns = {
        "reasoning_state": {"steps": [], "final_answer": "x", "completed": True},
        "query": "q",
    }
    exec(code, ns)  # must not raise NameError: name 'self' is not defined
    assert "agentic_rag_result" in ns["result"]


def test_result_synthesizer_interpolates_constructor_config():
    """The metadata block carries the real constructor config values, not
    the literal placeholder strings."""
    node = AgenticRAGNode(planning_strategy="tree-of-thought", max_reasoning_steps=11)
    code = _template(node, "result_synthesizer")
    ns = {
        "reasoning_state": {"steps": [], "final_answer": "x", "completed": True},
        "query": "q",
    }
    exec(code, ns)
    meta = ns["result"]["agentic_rag_result"]["metadata"]
    assert meta["planning_strategy"] == "tree-of-thought"
    assert meta["max_steps"] == 11
    # The literal placeholder must NOT survive into the output.
    assert meta["planning_strategy"] != "{self.planning_strategy}"


# ---------------------------------------------------------------------------
# Defect 3 — ToolAugmentedRAGNode None-query crash
# ---------------------------------------------------------------------------
def test_tool_augmented_none_query_does_not_crash():
    """An explicit ``query=None`` must not crash run()'s tool detection."""
    result = ToolAugmentedRAGNode().run(query=None, documents=[])
    assert result["tools_invoked"] == []
    assert result["confidence"] == 0.7


# ---------------------------------------------------------------------------
# Defect 4 — ToolAugmentedRAGNode non-dict tool-output crash
# ---------------------------------------------------------------------------
def test_tool_augmented_non_dict_tool_output_does_not_crash():
    """A registered tool returning a non-dict value (here a bare int) must
    not crash answer synthesis — non-dict outputs have no error key and are
    treated as successful results."""
    result = ToolAugmentedRAGNode(tool_registry={"calculator": lambda _q, _c: 42}).run(
        query="calculate the sum", documents=[]
    )
    assert result["tool_outputs"]["calculator"] == 42
    assert "calculator" in result["answer"]


def test_tool_augmented_non_dict_tool_output_string_return():
    """A tool returning a bare string is likewise tolerated."""
    result = ToolAugmentedRAGNode(
        tool_registry={"calculator": lambda _q, _c: "computed: ok"}
    ).run(query="calculate the average", documents=[])
    assert result["tool_outputs"]["calculator"] == "computed: ok"
    assert "computed: ok" in result["answer"]
