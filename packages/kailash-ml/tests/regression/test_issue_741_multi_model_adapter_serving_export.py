# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression for GH issue #741 — ``MultiModelAdapter`` missing from
``kailash_ml.serving.__all__``.

Per ``rules/orphan-detection.md`` §6 every public symbol imported at
module scope into a package's ``__init__.py`` MUST appear in that
module's ``__all__``.

Background
----------

* ``specs/ml-serving.md`` §2.6.1 advertises ``MultiModelAdapter`` as
  the documented 1.5.0 → 1.6.0 hard-break recovery shim, importable
  from ``kailash_ml.serving``.
* The class exists at
  ``kailash_ml.serving.multi_model_adapter.MultiModelAdapter`` and is
  exported from top-level ``kailash_ml.MultiModelAdapter`` (per #700).
* Until 1.7.1 the symbol was NOT re-exported through
  ``kailash_ml.serving.__init__``, so the spec-documented import path
  (``from kailash_ml.serving import MultiModelAdapter``) raised
  ``ImportError`` on a fresh install.

Asserts
-------

1. ``from kailash_ml.serving import MultiModelAdapter`` resolves.
2. ``"MultiModelAdapter"`` appears in ``kailash_ml.serving.__all__``
   (verified via ``ast.parse`` per ``rules/testing.md`` §
   "``__all__`` / Re-export Symbol Counts Use Structural Enumeration,
   Not Grep").
3. ``kailash_ml.serving.MultiModelAdapter is
   kailash_ml.MultiModelAdapter`` — both surfaces resolve to the
   identical class object (no parallel definition).

Behavioral, not source-grep — the AST walk is over the parsed
``__all__`` literal, NOT a substring search.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest


@pytest.mark.regression
def test_issue_741_multi_model_adapter_importable_from_serving() -> None:
    """Spec-documented import path must resolve on a fresh install."""
    from kailash_ml.serving import MultiModelAdapter  # noqa: F401

    # Identity: same class object as the canonical module path.
    from kailash_ml.serving.multi_model_adapter import (
        MultiModelAdapter as CanonicalMultiModelAdapter,
    )

    assert MultiModelAdapter is CanonicalMultiModelAdapter


@pytest.mark.regression
def test_issue_741_multi_model_adapter_in_serving_all_via_ast() -> None:
    """``__all__`` enumeration must include ``MultiModelAdapter``.

    Uses ``ast.parse`` per ``rules/testing.md`` § "``__all__`` /
    Re-export Symbol Counts Use Structural Enumeration, Not Grep" —
    avoids `grep` false positives from comments / line continuations.
    """
    init_path = (
        Path(__file__).resolve().parents[2]
        / "src"
        / "kailash_ml"
        / "serving"
        / "__init__.py"
    )
    tree = ast.parse(init_path.read_text())
    all_entries: list[str] | None = None
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id == "__all__"
            and isinstance(node.value, ast.List)
        ):
            all_entries = [
                elt.value
                for elt in node.value.elts
                if isinstance(elt, ast.Constant) and isinstance(elt.value, str)
            ]
            break
    assert (
        all_entries is not None
    ), "kailash_ml/serving/__init__.py must define `__all__` as a list literal"
    assert "MultiModelAdapter" in all_entries, (
        f"`MultiModelAdapter` missing from kailash_ml.serving.__all__; "
        f"found: {all_entries}"
    )


@pytest.mark.regression
def test_issue_741_serving_and_top_level_resolve_to_same_class() -> None:
    """Defensive identity: both public surfaces are the same object."""
    import kailash_ml
    from kailash_ml.serving import MultiModelAdapter as FromServing

    assert FromServing is kailash_ml.MultiModelAdapter
