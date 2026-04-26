# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""W6-013 Tier-1 unit tests — CatBoostTrainable adapter.

Per ``specs/ml-engines-v2-addendum.md`` § Classical-ML surface +
``specs/ml-engines.md`` §3 (Trainable protocol). These tests cover
the structural contract — protocol conformance, family identifier,
device mapping behaviour for unsupported backends, and the import-
gated extra contract — without requiring the catboost extra.

Tier-2 coverage that exercises a real fit / predict round-trip
against the [catboost] extra lives at
``tests/integration/test_catboost_trainable_real.py`` (skipped when
the extra is absent).
"""
from __future__ import annotations

import pytest

from kailash_ml import CatBoostTrainable, Trainable

# CatBoostTrainable raises kailash_ml._device.UnsupportedFamily — the
# canonical UnsupportedFamily lives in `_device.py` (and is re-exported
# via `kailash_ml.errors` as part of the MLError hierarchy, but the
# concrete class identity differs from the public namespace re-export).
# Match the actual raise site.
from kailash_ml._device import UnsupportedFamily
from kailash_ml.trainable import TrainingContext


# ---------------------------------------------------------------------------
# Importability + protocol conformance
# ---------------------------------------------------------------------------


def test_catboost_trainable_is_importable_from_top_level() -> None:
    """``from kailash_ml import CatBoostTrainable`` MUST resolve."""
    assert CatBoostTrainable is not None


def test_catboost_trainable_in_canonical_all() -> None:
    """``CatBoostTrainable`` MUST appear in ``kailash_ml.__all__`` Group 2."""
    import kailash_ml

    assert "CatBoostTrainable" in kailash_ml.__all__


def test_catboost_trainable_family_name() -> None:
    """The class MUST advertise ``family_name = 'catboost'``."""
    assert CatBoostTrainable.family_name == "catboost"


def test_catboost_trainable_satisfies_trainable_protocol() -> None:
    """An instance MUST satisfy the runtime-checkable Trainable Protocol.

    Construction without the extra raises ImportError, so we use a
    Protocol-Satisfying stub (Tier-1 acceptable per
    ``rules/testing.md`` § "Protocol Adapters") to verify the class
    declares the required surface.
    """
    # The class MUST declare every Protocol method.
    for method in (
        "fit",
        "predict",
        "to_lightning_module",
        "get_param_distribution",
    ):
        assert hasattr(
            CatBoostTrainable, method
        ), f"CatBoostTrainable missing required method: {method}"


# ---------------------------------------------------------------------------
# Device mapping — UnsupportedFamily on non-catboost backends
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("backend", ["mps", "rocm", "xpu", "tpu"])
def test_catboost_trainable_rejects_unsupported_backend(backend: str) -> None:
    """fit() on MPS / ROCm / XPU / TPU MUST raise UnsupportedFamily.

    The error MUST name the family + requested backend + supported
    fallback list per ``ml-backends.md`` §5.
    """
    pytest.importorskip("catboost")  # need an estimator to construct
    pytest.importorskip("polars")

    import polars as pl

    trainable = CatBoostTrainable(target="y", iterations=2)
    df = pl.DataFrame(
        {
            "x0": [0.1, 0.2, 0.3, 0.4],
            "x1": [1.0, 0.5, 0.0, -0.5],
            "y": [0, 1, 0, 1],
        }
    )
    ctx = TrainingContext(
        accelerator="cpu",
        precision="32-true",
        devices=1,
        device_string="cpu",
        backend=backend,
    )

    with pytest.raises(UnsupportedFamily) as excinfo:
        trainable.fit(df, hyperparameters=None, context=ctx)

    err = excinfo.value
    msg = str(err)
    assert "catboost" in msg.lower()
    assert backend in msg
    # Pointer to fallback families per the contract.
    assert "torch" in msg.lower() or "cuda" in msg.lower()


# ---------------------------------------------------------------------------
# Hyperparameter search space surface
# ---------------------------------------------------------------------------


def test_catboost_trainable_hyperparameter_space_is_non_empty() -> None:
    """``get_param_distribution()`` MUST return a non-empty HyperparameterSpace.

    Per ``specs/ml-engines.md`` §3.2 MUST 3 — empty OK, ``None`` not.
    The CatBoost adapter exposes iterations / depth / learning_rate.
    """
    pytest.importorskip("catboost")
    trainable = CatBoostTrainable(target="y", iterations=2)
    space = trainable.get_param_distribution()
    assert space is not None
    assert not space.is_empty()
    names = set(space.names())
    assert {"iterations", "depth", "learning_rate"} <= names


# ---------------------------------------------------------------------------
# to_lightning_module() refuses before fit
# ---------------------------------------------------------------------------


def test_to_lightning_module_before_fit_raises() -> None:
    """Calling to_lightning_module() before fit() MUST raise RuntimeError."""
    pytest.importorskip("catboost")
    trainable = CatBoostTrainable(target="y", iterations=2)
    with pytest.raises(RuntimeError, match="before fit"):
        trainable.to_lightning_module()


def test_predict_before_fit_raises() -> None:
    """Calling predict() before fit() MUST raise RuntimeError."""
    pytest.importorskip("catboost")
    pytest.importorskip("polars")
    import polars as pl

    trainable = CatBoostTrainable(target="y", iterations=2)
    with pytest.raises(RuntimeError, match="before fit"):
        trainable.predict(pl.DataFrame({"x0": [0.1]}))


# ---------------------------------------------------------------------------
# Engine family-alias dispatch wiring (W6-013 invariant)
# ---------------------------------------------------------------------------


def test_engine_family_alias_resolves_catboost() -> None:
    """family='catboost' MUST resolve through MLEngine._build_trainable_from_family()."""
    pytest.importorskip("catboost")
    from kailash_ml.engine import _build_trainable_from_family

    trainable = _build_trainable_from_family("catboost", target="label")
    assert isinstance(trainable, CatBoostTrainable)
    assert trainable.family_name == "catboost"


def test_engine_family_alias_cb_short_form() -> None:
    """The short alias 'cb' MUST resolve to CatBoostTrainable."""
    pytest.importorskip("catboost")
    from kailash_ml.engine import _build_trainable_from_family

    trainable = _build_trainable_from_family("cb", target="label")
    assert isinstance(trainable, CatBoostTrainable)


def test_catboost_trainable_in_runtime_checkable_protocol() -> None:
    """An instantiated CatBoostTrainable MUST satisfy isinstance(t, Trainable).

    Per ``specs/ml-engines.md`` §3.1 + W8 invariant 1 — runtime-checkable.
    """
    pytest.importorskip("catboost")
    trainable = CatBoostTrainable(target="y", iterations=2)
    assert isinstance(trainable, Trainable)
