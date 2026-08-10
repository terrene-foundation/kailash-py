# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier 2 wiring test — kailash_ml.errors re-export identity preservation.

Per ``rules/facade-manager-detection.md §2`` the test imports through the
kailash-ml facade (not the kailash core class directly) and asserts the
externally-observable effect — in this case, that the hierarchy exposed by
kailash-ml is the same Python class object as the one in kailash core.

If a future refactor were to shadow a class with a sibling copy or declare
a local subclass, ``is`` identity would break and the test would fail
immediately.
"""
from __future__ import annotations

import kailash_ml.errors as ml_errors
import pytest

import kailash.ml.errors as core_errors

CORE_NAMES = sorted(core_errors.__all__)


@pytest.mark.integration
def test_every_core_symbol_is_reexported():
    missing = [n for n in CORE_NAMES if n not in ml_errors.__all__]
    assert not missing, (
        f"kailash_ml.errors missing {len(missing)} symbols re-exported from "
        f"kailash.ml.errors: {missing}"
    )


@pytest.mark.integration
@pytest.mark.parametrize("name", CORE_NAMES)
def test_reexport_is_class_identity_preserving(name):
    core_obj = getattr(core_errors, name)
    ml_obj = getattr(ml_errors, name)
    assert core_obj is ml_obj, (
        f"{name} is NOT identity-preserved across the re-export "
        f"(core={core_obj!r}, ml={ml_obj!r}). A sibling copy / local "
        f"subclass / shadowing import has broken the cross-package contract."
    )


@pytest.mark.integration
def test_catch_through_facade_matches_catch_through_core():
    """A raise-through-facade is caught-through-core and vice versa."""
    with pytest.raises(core_errors.MLError):
        raise ml_errors.ModelNotFoundError(reason="test", resource_id="churn_v7")

    with pytest.raises(ml_errors.MLError):
        raise core_errors.ModelNotFoundError(reason="test", resource_id="churn_v7")
