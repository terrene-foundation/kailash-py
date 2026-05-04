"""Regression test for issue #814 — research/adapter.py:119 dict→List corruption.

Pre-fix bug:
    `ResearchAdapter.create_signature_adapter()` constructed an inner
    `ResearchSignature` whose `__init__` invoked
    `super().__init__(inputs={name: f"Input {name}"...}, outputs={"result": "..."})`.
    `Signature.__init__` declares `inputs: Optional[List[str]]` and
    `outputs: Optional[List[Union[str, List[str]]]]`. Passing dicts silently
    broke the `Signature._inputs_list: List[str]` invariant because
    `_inputs_list = inputs` ran without type-checking, leaving the list
    populated with whatever iter-order the dict produced (just keys, not
    name-description pairs).

Post-fix:
    The adapter now passes `inputs = list(param_names)` (a List[str] of
    the actual implementation function's parameter names) and
    `outputs = ["result"]`. `_inputs_list` is now a proper List[str] of
    parameter names.

This test calls the public entrypoint, then asserts the resulting
`Signature._inputs_list` is a list of str, in the canonical order of
the implementation function's parameters.
"""

from __future__ import annotations

import sys
import types

import pytest

from kaizen.research.adapter import ResearchAdapter
from kaizen.research.parser import ResearchPaper


@pytest.fixture
def fake_implementation_module(monkeypatch):
    """Install a synthetic implementation module that exposes a function with
    two known parameters (`query`, `limit`) so the adapter can introspect them.
    """
    module_name = "kaizen_test_research_impl_issue_814"
    mod = types.ModuleType(module_name)

    def search(query: str, limit: int = 10) -> dict:
        """Synthetic research implementation."""
        return {"query": query, "limit": limit, "results": []}

    mod.search = search  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, module_name, mod)
    return module_name


@pytest.mark.regression
def test_issue_814_adapter_inputs_list_is_list_of_param_names(
    fake_implementation_module,
):
    """adapter.py:119 must hand Signature a List[str] of param names, not a dict."""
    paper = ResearchPaper(
        arxiv_id="2026.00814",
        title="Test Paper",
        authors=["Author"],
        abstract="abstract",
        methodology="methodology",
    )

    adapter = ResearchAdapter()
    SignatureCls = adapter.create_signature_adapter(
        paper=paper,
        implementation_module=fake_implementation_module,
        main_function="search",
    )

    sig = SignatureCls()

    # Behavior assertion: _inputs_list is a List[str] of param names.
    assert isinstance(
        sig._inputs_list, list
    ), f"_inputs_list must be list, got {type(sig._inputs_list).__name__}"
    assert all(isinstance(item, str) for item in sig._inputs_list), (
        f"_inputs_list entries must all be str, got "
        f"{[type(x).__name__ for x in sig._inputs_list]}"
    )
    assert sig._inputs_list == ["query", "limit"], (
        f"_inputs_list must contain function param names in order; "
        f"got {sig._inputs_list!r}"
    )

    # Pre-fix this would have been a dict-keys-derived list of f"Input {name}"
    # strings; post-fix it is the actual parameter names.
    assert "Input query" not in sig._inputs_list
    assert "Input limit" not in sig._inputs_list


@pytest.mark.regression
def test_issue_814_adapter_inputs_list_falls_back_to_input_when_no_params(
    monkeypatch,
):
    """When the implementation function has zero params, _inputs_list defaults
    to ['input'] — not an empty list and not a dict."""
    module_name = "kaizen_test_research_impl_issue_814_noparams"
    mod = types.ModuleType(module_name)

    def noop() -> dict:
        return {}

    mod.noop = noop  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, module_name, mod)

    paper = ResearchPaper(
        arxiv_id="2026.00814b",
        title="Test Paper No Params",
        authors=["Author"],
        abstract="abstract",
        methodology="methodology",
    )

    adapter = ResearchAdapter()
    SignatureCls = adapter.create_signature_adapter(
        paper=paper,
        implementation_module=module_name,
        main_function="noop",
    )

    sig = SignatureCls()

    assert isinstance(sig._inputs_list, list)
    assert sig._inputs_list == ["input"]
