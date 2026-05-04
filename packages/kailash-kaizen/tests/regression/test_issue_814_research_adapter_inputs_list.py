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

import importlib.util
import sys
import types
from pathlib import Path

import pytest

# Load `adapter.py` and `parser.py` directly from disk via spec-from-file
# rather than `from kaizen.research.adapter import ...`. The parent package
# `kaizen.research.__init__` carries vestigial imports of moved modules
# (`advanced_patterns`, `experimental`, `intelligent_optimizer`) that were
# relocated to `kaizen-agents` by PR #75 and not yet deleted from the
# `__init__` re-export list — pre-existing condition handled by Shard 2 of
# issue #814. Loading the adapter module directly bypasses that broken
# init and exercises the unit under test.
_research_dir = Path(__file__).resolve().parents[2] / "src" / "kaizen" / "research"


def _load_module(name: str, path: Path) -> types.ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


# parser.py first so adapter.py's `from .parser import ResearchPaper`
# resolves against this loaded copy.
_parser_mod = _load_module("kaizen.research.parser", _research_dir / "parser.py")
# adapter.py imports `from .parser import ResearchPaper` — that relative
# import will look up `kaizen.research.parser` in sys.modules, which we
# just populated, and skip re-executing the parent `kaizen.research`
# init. We register a stub package module to satisfy the relative import
# machinery.
if "kaizen.research" not in sys.modules:
    _stub = types.ModuleType("kaizen.research")
    _stub.__path__ = [str(_research_dir)]  # type: ignore[attr-defined]
    sys.modules["kaizen.research"] = _stub
    sys.modules["kaizen.research"].parser = _parser_mod  # type: ignore[attr-defined]

_adapter_mod = _load_module("kaizen.research.adapter", _research_dir / "adapter.py")
ResearchAdapter = _adapter_mod.ResearchAdapter
ResearchPaper = _parser_mod.ResearchPaper


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
