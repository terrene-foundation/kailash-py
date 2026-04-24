# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""W23.b Tier-2 wiring test — sklearn autolog end-to-end.

Per ``specs/ml-autolog.md §8.1`` MUST:

- Fit a TOY model (small, CPU-only, ≤1 second).
- File-backed SQLite (NOT ``:memory:``) so ``list_metrics`` +
  ``list_artifacts`` exercise the full write/read round-trip.
- Assert ≥3 metrics + 1 artifact emitted under the ambient run.
- Verify patched ``fit`` methods are restored on CM exit (detach
  discipline per §3.2 + §1.3 non-goal).

Per ``rules/testing.md §Tier 2`` — real scikit-learn, real disk
SQLite, no mocks. The only non-real bit is the toy dataset shape
(16 rows × 4 features), chosen so ``RandomForestClassifier.fit()``
completes in well under 1 second on CPU.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import numpy as np
import pytest
from kailash_ml.autolog import autolog
from kailash_ml.tracking import SqliteTrackerStore, track


pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest.fixture
async def backend(tmp_path: Path):
    """File-backed SqliteTrackerStore per spec §8.1 MUST."""
    be = SqliteTrackerStore(tmp_path / "autolog_sklearn_tracker.db")
    await be.initialize()
    try:
        yield be
    finally:
        await be.close()


@pytest.fixture
def toy_classification_data() -> tuple[np.ndarray, np.ndarray]:
    """Tiny deterministic binary classification set — 16 rows × 4 feats."""
    rng = np.random.default_rng(seed=42)
    X = rng.standard_normal((16, 4))
    # Linearly separable-ish target — first feature sign drives the class.
    y = (X[:, 0] > 0).astype(int)
    return X, y


def _defining_class(cls: type, method_name: str) -> Optional[type]:
    """Return the first class in ``cls.__mro__`` whose ``__dict__``
    defines ``method_name``.

    Used because most sklearn estimators don't define ``fit`` directly —
    e.g. ``RandomForestClassifier`` inherits ``fit`` from ``BaseForest``
    several levels up. The SklearnIntegration patches each defining
    class; the test must inspect that SAME class.
    """
    for candidate in cls.__mro__:
        if method_name in candidate.__dict__:
            return candidate
    return None


async def test_sklearn_autolog_emits_metrics_params_and_artifact(
    backend: SqliteTrackerStore,
    toy_classification_data: tuple[np.ndarray, np.ndarray],
) -> None:
    """RandomForestClassifier.fit() inside km.autolog("sklearn") emits
    metrics + params + artifacts to the ambient run.
    """
    from sklearn.ensemble import RandomForestClassifier

    X, y = toy_classification_data

    async with track("w23b-sklearn-wiring", backend=backend) as run:
        async with autolog("sklearn") as handle:
            assert handle.attached_integrations == ("sklearn",)
            clf = RandomForestClassifier(n_estimators=3, max_depth=2, random_state=42)
            clf.fit(X, y)
        run_id = run.run_id

    # Assertions per §8.1 MUST — metrics + params + artifacts all
    # round-tripped through real on-disk SQLite.
    metrics = await backend.list_metrics(run_id)
    artifacts = await backend.list_artifacts(run_id)
    run_row = await backend.get_run(run_id)
    assert run_row is not None, "run row should exist post-exit"
    persisted_params = run_row.get("params") or {}

    # Score metric MUST be present.
    metric_keys = {row["key"] for row in metrics}
    assert any(
        k.endswith(".score") for k in metric_keys
    ), f"expected at least one *.score metric, got {metric_keys}"

    # get_params(deep=True) emits many params; assert the common sklearn
    # ones appear prefixed with the class name.
    param_keys = set(persisted_params.keys())
    assert any(
        k.startswith("RandomForestClassifier.") for k in param_keys
    ), f"expected RandomForestClassifier.* params, got {sorted(param_keys)[:10]}"
    assert (
        "RandomForestClassifier.n_estimators" in param_keys
    ), f"param n_estimators missing from {sorted(param_keys)[:10]}"

    # Artifacts — expect the ONNX model OR pickle fallback plus
    # classifier figures (confusion matrix + classification_report).
    artifact_names = {row["name"] for row in artifacts}
    model_artifacts = [n for n in artifact_names if "RandomForestClassifier.model" in n]
    assert (
        model_artifacts
    ), f"expected RandomForestClassifier.model.* artifact, got {artifact_names}"
    figure_artifacts = [
        n
        for n in artifact_names
        if "RandomForestClassifier.confusion_matrix" in n
        or "RandomForestClassifier.classification_report" in n
    ]
    assert figure_artifacts, f"expected classifier figures, got {artifact_names}"


async def test_sklearn_autolog_restores_fit_on_exit(
    backend: SqliteTrackerStore,
    toy_classification_data: tuple[np.ndarray, np.ndarray],
) -> None:
    """Per §3.2 + §1.3: detach MUST restore every patched ``fit``.

    RandomForestClassifier inherits ``fit`` from ``BaseForest`` (an
    MRO-parent). The SklearnIntegration patches ``BaseForest.fit`` at
    attach; this test verifies BaseForest's ``__dict__["fit"]`` is
    restored on exit.
    """
    from sklearn.ensemble import RandomForestClassifier

    defining_cls = _defining_class(RandomForestClassifier, "fit")
    assert defining_cls is not None, "sklearn invariant broken: no fit in MRO"
    original_fit = defining_cls.__dict__["fit"]

    async with track("w23b-sklearn-restore", backend=backend):
        async with autolog("sklearn"):
            # Inside the block, fit is wrapped — verify the wrapper is
            # actually installed (functools.wraps preserves __wrapped__).
            wrapped = defining_cls.__dict__["fit"]
            assert wrapped is not original_fit, (
                f"SklearnIntegration.attach did NOT replace "
                f"{defining_cls.__name__}.fit; wrap is a no-op"
            )
            assert hasattr(
                wrapped, "__wrapped__"
            ), "wrapped fit missing __wrapped__ — functools.wraps not applied"
    # After exit, fit is restored.
    assert defining_cls.__dict__["fit"] is original_fit, (
        f"SklearnIntegration.detach did NOT restore "
        f"{defining_cls.__name__}.fit; class-level patch LEAKED per §1.3"
    )


async def test_sklearn_autolog_restores_fit_even_when_body_raises(
    backend: SqliteTrackerStore,
) -> None:
    """Per §8.5 + §3.2: detach runs in ``finally:`` even when the
    wrapped block raises, and fit is still restored.
    """
    from sklearn.ensemble import RandomForestClassifier

    defining_cls = _defining_class(RandomForestClassifier, "fit")
    assert defining_cls is not None
    original_fit = defining_cls.__dict__["fit"]

    async with track("w23b-sklearn-restore-on-raise", backend=backend):
        with pytest.raises(ValueError, match="user body error"):
            async with autolog("sklearn"):
                raise ValueError("user body error")
    assert (
        defining_cls.__dict__["fit"] is original_fit
    ), f"SklearnIntegration.detach did NOT restore {defining_cls.__name__}.fit after raising body"
