# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""W9 unit tests — Lightning adapter invariants.

Per `todos/active/W09-lightning-adapters.md` DoD:

1. 4 adapter files (sklearn / xgboost / lightgbm / catboost) + shared base.
2. NaN/Inf hyperparameters -> ``ParamValueError``.
3. ``family_name: str`` class attribute present on every adapter.
4. Pickle round-trip preserves adapter state.

These tests are Tier 1 — they do NOT require a GPU, DL extra, or an
actual Lightning training run; the adapter classes are exercised for
construction-time invariants only.
"""
from __future__ import annotations

import pickle

import pytest
from kailash_ml.errors import ParamValueError
from kailash_ml.estimators.adapters import (
    CatBoostLightningAdapter,
    LightGBMLightningAdapter,
    LightningAdapterBase,
    SklearnLightningAdapter,
    XGBoostLightningAdapter,
    validate_hyperparameters,
)

# ---------------------------------------------------------------------------
# Import-level wiring (W9 invariant 7 + orphan-detection §1)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_all_four_adapters_exported_from_package():
    """The adapters package re-exports all four + the shared base."""
    from kailash_ml.estimators import adapters as pkg

    for name in (
        "SklearnLightningAdapter",
        "XGBoostLightningAdapter",
        "LightGBMLightningAdapter",
        "CatBoostLightningAdapter",
        "LightningAdapterBase",
        "validate_hyperparameters",
    ):
        assert hasattr(pkg, name), f"{name} missing from kailash_ml.estimators.adapters"
        assert name in pkg.__all__, f"{name} missing from __all__"


@pytest.mark.unit
@pytest.mark.parametrize(
    "adapter_cls, expected_name",
    [
        (SklearnLightningAdapter, "sklearn"),
        (XGBoostLightningAdapter, "xgboost"),
        (LightGBMLightningAdapter, "lightgbm"),
        (CatBoostLightningAdapter, "catboost"),
    ],
)
def test_family_name_class_attribute_present(adapter_cls, expected_name):
    """W9 invariant 7: every adapter exposes ``family_name: str``."""
    assert hasattr(adapter_cls, "family_name")
    assert adapter_cls.family_name == expected_name


# ---------------------------------------------------------------------------
# NaN/Inf hyperparameter validation (W9 invariant 6)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_validate_hyperparameters_rejects_nan():
    """NaN value -> ParamValueError."""
    with pytest.raises(ParamValueError, match="not.*finite"):
        validate_hyperparameters({"learning_rate": float("nan")}, family="sklearn")


@pytest.mark.unit
def test_validate_hyperparameters_rejects_positive_inf():
    with pytest.raises(ParamValueError, match="not.*finite"):
        validate_hyperparameters({"max_depth": float("inf")}, family="xgboost")


@pytest.mark.unit
def test_validate_hyperparameters_rejects_negative_inf():
    with pytest.raises(ParamValueError, match="not.*finite"):
        validate_hyperparameters({"learning_rate": float("-inf")}, family="lightgbm")


@pytest.mark.unit
def test_validate_hyperparameters_passes_finite_numeric():
    """Finite numerics pass through unchanged."""
    result = validate_hyperparameters(
        {"max_depth": 3, "learning_rate": 0.1, "n_estimators": 100},
        family="xgboost",
    )
    assert result == {"max_depth": 3, "learning_rate": 0.1, "n_estimators": 100}


@pytest.mark.unit
def test_validate_hyperparameters_passes_non_numeric():
    """Strings / enums / bools pass through unchanged."""
    result = validate_hyperparameters(
        {"criterion": "gini", "verbose": True, "n_jobs": -1},
        family="sklearn",
    )
    assert result == {"criterion": "gini", "verbose": True, "n_jobs": -1}


@pytest.mark.unit
def test_validate_hyperparameters_none_returns_empty_dict():
    """``None`` is treated as an empty hyperparameter set."""
    assert validate_hyperparameters(None, family="sklearn") == {}


# ---------------------------------------------------------------------------
# Adapter construction-time validation
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_sklearn_adapter_rejects_nan_at_construction():
    """Adapter __init__ propagates NaN rejection from the base helper."""
    from sklearn.ensemble import RandomForestClassifier

    with pytest.raises(ParamValueError):
        SklearnLightningAdapter(
            RandomForestClassifier(n_estimators=5),
            hyperparameters={"learning_rate": float("nan")},
        )


@pytest.mark.unit
def test_xgboost_adapter_rejects_inf_at_construction():
    pytest.importorskip("xgboost")
    with pytest.raises(ParamValueError):
        XGBoostLightningAdapter(hyperparameters={"max_depth": float("inf")})


@pytest.mark.unit
def test_lightgbm_adapter_rejects_nan_at_construction():
    pytest.importorskip("lightgbm")
    with pytest.raises(ParamValueError):
        LightGBMLightningAdapter(hyperparameters={"num_leaves": float("nan")})


@pytest.mark.unit
def test_catboost_adapter_rejects_nan_at_construction():
    pytest.importorskip("catboost")
    with pytest.raises(ParamValueError):
        CatBoostLightningAdapter(hyperparameters={"depth": float("nan")})


# ---------------------------------------------------------------------------
# Protocol conformance (W9 invariant 1 — LightningAdapterBase runtime_checkable)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_sklearn_adapter_satisfies_lightning_adapter_base():
    from sklearn.ensemble import RandomForestClassifier

    adapter = SklearnLightningAdapter(RandomForestClassifier(n_estimators=5))
    assert isinstance(adapter, LightningAdapterBase)


@pytest.mark.unit
def test_xgboost_adapter_satisfies_lightning_adapter_base():
    pytest.importorskip("xgboost")
    adapter = XGBoostLightningAdapter()
    assert isinstance(adapter, LightningAdapterBase)


@pytest.mark.unit
def test_lightgbm_adapter_satisfies_lightning_adapter_base():
    pytest.importorskip("lightgbm")
    adapter = LightGBMLightningAdapter()
    assert isinstance(adapter, LightningAdapterBase)


@pytest.mark.unit
def test_catboost_adapter_satisfies_lightning_adapter_base():
    pytest.importorskip("catboost")
    adapter = CatBoostLightningAdapter()
    assert isinstance(adapter, LightningAdapterBase)


# ---------------------------------------------------------------------------
# Pickle round-trip (W9 Tier-1 DoD)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_sklearn_adapter_pickle_round_trip():
    from sklearn.ensemble import RandomForestClassifier

    adapter = SklearnLightningAdapter(
        RandomForestClassifier(n_estimators=5, random_state=42)
    )
    data = pickle.dumps(adapter)
    restored = pickle.loads(data)
    assert isinstance(restored, SklearnLightningAdapter)
    assert restored.family_name == "sklearn"


@pytest.mark.unit
def test_xgboost_adapter_pickle_round_trip():
    pytest.importorskip("xgboost")
    adapter = XGBoostLightningAdapter()
    data = pickle.dumps(adapter)
    restored = pickle.loads(data)
    assert isinstance(restored, XGBoostLightningAdapter)
    assert restored.family_name == "xgboost"


@pytest.mark.unit
def test_lightgbm_adapter_pickle_round_trip():
    pytest.importorskip("lightgbm")
    adapter = LightGBMLightningAdapter()
    data = pickle.dumps(adapter)
    restored = pickle.loads(data)
    assert isinstance(restored, LightGBMLightningAdapter)
    assert restored.family_name == "lightgbm"


@pytest.mark.unit
def test_catboost_adapter_pickle_round_trip():
    pytest.importorskip("catboost")
    adapter = CatBoostLightningAdapter()
    data = pickle.dumps(adapter)
    restored = pickle.loads(data)
    assert isinstance(restored, CatBoostLightningAdapter)
    assert restored.family_name == "catboost"
