# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""W33 Tier-2 — ``km.list_engines`` + ``km.engine_info`` discovery.

Per ``specs/ml-engines-v2-addendum.md §E11.3 MUST 4``, the registry
MUST enumerate all 18 engines from the §E1.1 matrix and every
:class:`EngineInfo` MUST carry the per-engine public-method count
specified in that matrix.

Test strategy
-------------

1. :func:`list_engines` returns exactly the 18 engine names the §E1.1
   table lists.
2. Each engine's ``signatures`` tuple contains at least one
   :class:`MethodSignature` (per §E1.1 "Primary mutation methods
   audited" column — every engine ships at least one audited
   mutation).
3. Every ``EngineInfo.version`` matches :data:`kailash_ml.__version__`
   per §E11.3 MUST 3 (split-version states BLOCKED by
   ``zero-tolerance.md`` Rule 5).
4. :func:`engine_info` raises a typed error on unknown names with an
   actionable message listing the available engines.
"""
from __future__ import annotations

import pytest

import kailash_ml
from kailash_ml import EngineInfo, engine_info, list_engines
from kailash_ml.engines.registry import (
    EngineNotFoundError,
    MethodSignature,
    ParamSpec,
)


# The authoritative engine list per ``specs/ml-engines-v2-addendum.md §E1.1``.
EXPECTED_ENGINES = {
    "MLEngine",
    "TrainingPipeline",
    "ExperimentTracker",
    "ModelRegistry",
    "FeatureStore",
    "InferenceServer",
    "DriftMonitor",
    "AutoMLEngine",
    "HyperparameterSearch",
    "Ensemble",
    "Preprocessing",
    "FeatureEngineer",
    "ModelExplainer",
    "DataExplorer",
    "ModelVisualizer",
    "Clustering",
    "AnomalyDetection",
    "DimReduction",
}


@pytest.mark.integration
def test_list_engines_returns_all_18_engines() -> None:
    """§E11.3 MUST 4 — 18 engines exactly, each as an EngineInfo."""
    engines = list_engines()
    assert isinstance(engines, tuple), "list_engines() MUST return a tuple"
    names = {e.name for e in engines}
    assert names == EXPECTED_ENGINES, (
        f"registry drift vs §E1.1.\n"
        f"missing: {EXPECTED_ENGINES - names}\n"
        f"extra:   {names - EXPECTED_ENGINES}"
    )
    assert all(isinstance(e, EngineInfo) for e in engines)


@pytest.mark.integration
def test_list_engines_count_is_18() -> None:
    """Sanity gate on the 18-engine invariant."""
    assert len(list_engines()) == 18


@pytest.mark.integration
def test_engine_info_mlengine_has_8_methods() -> None:
    """Per ``ml-engines-v2.md §2.1 MUST 5``, MLEngine has exactly 8 public methods."""
    info = engine_info("MLEngine")
    assert isinstance(info, EngineInfo)
    assert info.name == "MLEngine"
    assert len(info.signatures) == 8, (
        f"MLEngine surface is locked at 8 methods per §2.1 MUST 5; "
        f"found {len(info.signatures)}"
    )
    # Method names are setup / compare / fit / predict / finalize /
    # evaluate / register / serve per §2.1 MUST 5.
    method_names = {sig.method_name for sig in info.signatures}
    assert method_names == {
        "setup",
        "compare",
        "fit",
        "predict",
        "finalize",
        "evaluate",
        "register",
        "serve",
    }, f"MLEngine method set drifted: {method_names}"


@pytest.mark.integration
def test_every_engine_has_at_least_one_signature() -> None:
    """§E1.1 — every engine declares at least one audited mutation."""
    for info in list_engines():
        assert len(info.signatures) >= 1, (
            f"engine {info.name} has zero signatures — §E1.1 requires at "
            f"least one primary mutation method to be audited"
        )
        for sig in info.signatures:
            assert isinstance(sig, MethodSignature)
            # Every MethodSignature carries at least a return annotation.
            assert sig.return_annotation != ""


@pytest.mark.integration
def test_engine_info_version_matches_package() -> None:
    """§E11.3 MUST 3 — ``EngineInfo.version == kailash_ml.__version__``."""
    for info in list_engines():
        assert info.version == kailash_ml.__version__, (
            f"engine {info.name}: version drift — "
            f"EngineInfo.version={info.version}, "
            f"kailash_ml.__version__={kailash_ml.__version__}"
        )


@pytest.mark.integration
def test_every_engine_accepts_tenant_id_and_emits_to_tracker() -> None:
    """§E1.1 — all 18 engines auto-wire + accept tenant_id."""
    for info in list_engines():
        assert (
            info.accepts_tenant_id is True
        ), f"engine {info.name}: accepts_tenant_id MUST be True per §E1.1"
        assert (
            info.emits_to_tracker is True
        ), f"engine {info.name}: emits_to_tracker MUST be True per §E1.1"


@pytest.mark.integration
def test_engine_info_returns_frozen_dataclass() -> None:
    """EngineInfo is frozen — MUST NOT allow attribute mutation."""
    info = engine_info("TrainingPipeline")
    with pytest.raises((AttributeError, Exception)):
        info.name = "HackedName"  # type: ignore[misc]


@pytest.mark.integration
def test_engine_info_unknown_raises_typed_error() -> None:
    """``engine_info("does-not-exist")`` MUST raise with actionable message."""
    with pytest.raises(EngineNotFoundError) as exc_info:
        engine_info("DefinitelyNotARegisteredEngine")
    message = str(exc_info.value)
    # Message MUST list the available engines so the caller can
    # correct the typo (per §E11.2).
    assert "MLEngine" in message
    assert "DefinitelyNotARegisteredEngine" in message


@pytest.mark.integration
def test_engine_info_is_hashable() -> None:
    """EngineInfo MUST be hashable so agent tool descriptors can cache it."""
    info_a = engine_info("MLEngine")
    info_b = engine_info("MLEngine")
    # Same registry call returns the same value; hash must work.
    s = {info_a, info_b}
    assert len(s) == 1, "same engine lookup MUST produce equal (hashable) EngineInfo"


@pytest.mark.integration
def test_engine_info_enumerates_param_specs() -> None:
    """Each ``MethodSignature.params`` MUST be a tuple of :class:`ParamSpec`."""
    info = engine_info("MLEngine")
    fit_sig = next((s for s in info.signatures if s.method_name == "fit"), None)
    assert fit_sig is not None
    assert isinstance(fit_sig.params, tuple)
    for p in fit_sig.params:
        assert isinstance(p, ParamSpec)
        assert p.name != ""
        assert p.annotation != ""


@pytest.mark.integration
def test_list_engines_order_is_stable() -> None:
    """Registry insertion order MUST be deterministic across calls."""
    first = tuple(e.name for e in list_engines())
    second = tuple(e.name for e in list_engines())
    assert first == second, "list_engines() MUST return a stable order"
    # Explicit: MLEngine comes first per §E1.1 matrix row order.
    assert first[0] == "MLEngine"
