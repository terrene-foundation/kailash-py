# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier 2 ONNX round-trip regression test for CatBoost.

Per ``specs/ml-engines.md`` §6.1 MUST 3. Orphan guard per
``rules/orphan-detection.md`` §2a.

CatBoost is declared as an optional extra (``kailash-ml[catboost]``), so
the test is skipped gracefully when the framework is not installed.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

pytest.importorskip("catboost")
pytest.importorskip("onnxruntime")


@pytest.mark.integration
def test_catboost_onnx_roundtrip_prediction_parity(tmp_path: Path) -> None:
    """Train a small CatBoost classifier, export to ONNX, assert parity."""
    import onnxruntime as ort
    from catboost import CatBoostClassifier
    from sklearn.datasets import make_classification

    from kailash_ml.bridge.onnx_bridge import OnnxBridge

    X, y = make_classification(
        n_samples=200,
        n_features=8,
        n_informative=5,
        n_redundant=2,
        random_state=42,
    )
    X = X.astype(np.float32)

    model = CatBoostClassifier(
        iterations=20,
        depth=3,
        random_seed=42,
        verbose=False,
        thread_count=1,
    )
    model.fit(X, y)

    onnx_path = tmp_path / "catboost_model.onnx"
    bridge = OnnxBridge()
    result = bridge.export(
        model,
        framework="catboost",
        output_path=onnx_path,
    )
    assert result.success, f"catboost ONNX export failed: {result.error_message}"
    assert onnx_path.exists()
    assert onnx_path.stat().st_size > 0

    session = ort.InferenceSession(str(onnx_path))
    input_name = session.get_inputs()[0].name

    X_test = X[:20]
    native_probs = model.predict_proba(X_test)
    native_labels = model.predict(X_test).flatten().astype(np.int64)

    onnx_outputs = session.run(None, {input_name: X_test})
    # CatBoost ONNX: outputs[0] = label, outputs[1] = probabilities (list of dicts)
    onnx_labels = np.asarray(onnx_outputs[0]).flatten().astype(np.int64)

    assert np.array_equal(
        onnx_labels, native_labels
    ), f"label mismatch: onnx={onnx_labels} native={native_labels}"

    onnx_probs_raw = onnx_outputs[1]
    if isinstance(onnx_probs_raw, list) and isinstance(onnx_probs_raw[0], dict):
        classes = sorted(onnx_probs_raw[0].keys())
        onnx_probs = np.array(
            [[row[c] for c in classes] for row in onnx_probs_raw], dtype=np.float32
        )
    else:
        onnx_probs = np.asarray(onnx_probs_raw, dtype=np.float32)

    assert np.allclose(
        onnx_probs, native_probs, rtol=1e-3, atol=1e-5
    ), f"probability drift too large: max diff={np.max(np.abs(onnx_probs - native_probs))}"
