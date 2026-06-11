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

Defects 1 + 2 were ``_create_workflow()`` codegen-template defects; defects
3 + 4 are ``run()``-path defects. Per the B1 two-path lesson, both the
``run()`` paths and the codegen templates were grepped for each pattern.

POST-MIGRATION (S6b — #1117/#1123 root-cause fix): the ``tool_executor`` /
``state_manager`` / ``result_synthesizer`` COMPUTE stages were lifted from
inline ``code=`` codegen to the module-level functions ``execute_tool_action``
and the ``_make_state_manager`` / ``_make_result_synthesizer`` closure factories,
wired via ``PythonCodeNode.from_function``. Defects 1 + 2 are now exercised
BEHAVIORALLY by calling those lifted functions directly (the structural
successor of exec'ing the codegen template) — same assertion intent, preserved.

All tests are behavioral — they call ``run()`` / the lifted COMPUTE function and
assert success / typed outputs, not source-grep.
"""

from __future__ import annotations

import pytest

from kaizen.nodes.rag.agentic import (
    AgenticRAGNode,
    ToolAugmentedRAGNode,
    _make_result_synthesizer,
    execute_tool_action,
)

pytestmark = pytest.mark.regression


# ---------------------------------------------------------------------------
# Defect 1 — tool_executor None-content / non-dict crash (lifted COMPUTE fn)
# ---------------------------------------------------------------------------
def test_tool_executor_none_content_does_not_crash():
    """The tool_executor search branch must tolerate a document whose
    ``content`` key is present-but-None."""
    out = execute_tool_action(
        reasoning_state={"current_action": 'search("transformer")'},
        documents=[{"id": "n", "content": None}],
    )
    assert out["tool_result"]["tool"] == "search"
    assert out["tool_result"]["count"] == 0


def test_tool_executor_none_title_does_not_crash():
    """A present-but-None ``title`` must not crash the search branch."""
    out = execute_tool_action(
        reasoning_state={"current_action": 'search("transformer")'},
        documents=[{"id": "n", "content": "transformer model", "title": None}],
    )
    assert out["tool_result"]["count"] == 1


def test_tool_executor_non_dict_document_is_skipped():
    """A non-dict element in ``documents`` is skipped, not crashed on."""
    out = execute_tool_action(
        reasoning_state={"current_action": 'search("transformer")'},
        documents=["not a dict", {"id": "g", "content": "transformer here"}],
    )
    assert out["tool_result"]["count"] == 1


def test_tool_executor_none_content_does_not_poison_sibling():
    """A None-content document must not block a well-formed sibling from
    matching the search query."""
    out = execute_tool_action(
        reasoning_state={"current_action": 'search("transformer")'},
        documents=[
            {"id": "bad", "content": None},
            {"id": "good", "content": "the transformer model"},
        ],
    )
    assert out["tool_result"]["count"] == 1
    assert out["tool_result"]["results"][0]["id"] == "good"


# ---------------------------------------------------------------------------
# Defect 2 — result_synthesizer NameError (was literal {self.x}); now the
# lifted `_make_result_synthesizer` closure binds the build-time config.
# ---------------------------------------------------------------------------
def test_result_synthesizer_does_not_raise_nameerror():
    """The result_synthesizer must produce its dict without a NameError — the
    prior plain-string codegen carried literal {self.x} placeholders."""
    synth = _make_result_synthesizer("react", 5)
    out = synth(
        reasoning_state={"steps": [], "final_answer": "x", "completed": True},
        query="q",
    )
    assert "agentic_rag_result" in out


def test_result_synthesizer_binds_constructor_config():
    """The metadata block carries the real constructor config values, not
    the literal placeholder strings."""
    synth = _make_result_synthesizer("tree-of-thought", 11)
    out = synth(
        reasoning_state={"steps": [], "final_answer": "x", "completed": True},
        query="q",
    )
    meta = out["agentic_rag_result"]["metadata"]
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
