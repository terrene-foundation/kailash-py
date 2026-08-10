# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression test — kailash_ml.engines.model_registry.ModelNotFoundError
MUST be the same class object as kailash_ml.errors.ModelNotFoundError (which
re-exports the canonical kailash.ml.errors.ModelNotFoundError).

Pre-W7 follow-up there was a local ``class ModelNotFoundError(Exception)``
defined inside model_registry.py that diverged from the canonical class.
A user's ``except ModelNotFoundError:`` block — depending on import path —
caught one OR the other but never both. The canonical class is a subclass
of ``ModelRegistryError → MLError``; the local class was a bare ``Exception``
subclass. Removing the local definition and routing all raises through the
canonical class closes the divergence.

If a future refactor reintroduces a local ``ModelNotFoundError`` class
anywhere in the kailash-ml package, this test fails loudly. See
``rules/orphan-detection.md`` § 1 (every facade attribute must have one
production class — duplicate parallel classes are the orphan pattern at
class-identity granularity).
"""
from __future__ import annotations

import pytest


@pytest.mark.regression
def test_model_registry_module_re_exports_canonical():
    """``engines.model_registry.ModelNotFoundError`` IS canonical."""
    import kailash_ml.engines.model_registry as registry_module
    import kailash_ml.errors as kml_errors

    import kailash.ml.errors as canonical_errors

    assert registry_module.ModelNotFoundError is canonical_errors.ModelNotFoundError, (
        "engines.model_registry.ModelNotFoundError diverged from canonical "
        "(kailash.ml.errors.ModelNotFoundError). User code that catches one "
        "via either import path will silently miss the other."
    )
    assert (
        kml_errors.ModelNotFoundError is canonical_errors.ModelNotFoundError
    ), "kailash_ml.errors.ModelNotFoundError diverged from canonical."


@pytest.mark.regression
def test_canonical_is_mlerror_subclass():
    """Canonical ModelNotFoundError MUST inherit MLError (typed exception)."""
    from kailash.ml.errors import MLError, ModelNotFoundError, ModelRegistryError

    assert issubclass(ModelNotFoundError, ModelRegistryError)
    assert issubclass(ModelNotFoundError, MLError)
    assert issubclass(ModelNotFoundError, Exception)


@pytest.mark.regression
def test_no_local_modelnotfounderror_class_in_registry_source():
    """Source-file invariant — engines/model_registry.py MUST NOT define a
    local ``class ModelNotFoundError``. Any future re-introduction of a
    local class is the failure mode this test guards against."""
    import ast
    from pathlib import Path

    import kailash_ml.engines.model_registry as registry_module

    source_path = Path(registry_module.__file__)
    tree = ast.parse(source_path.read_text())
    local_classes = [
        node.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ClassDef) and node.name == "ModelNotFoundError"
    ]
    assert local_classes == [], (
        f"Local class definition for ModelNotFoundError reappeared at "
        f"{source_path}. The canonical class is "
        f"kailash.ml.errors.ModelNotFoundError; the registry MUST re-export "
        f"via `from kailash_ml.errors import ModelNotFoundError`, not redefine."
    )
