# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier 2 ONNX round-trip regression test for XGBoost.

Per ``specs/ml-engines.md`` §6.1 MUST 3. Orphan guard per
``rules/orphan-detection.md`` §2a.
"""
from __future__ import annotations

import platform
import sys
from pathlib import Path

import numpy as np
import pytest

pytest.importorskip("xgboost")
pytest.importorskip("onnxmltools")
pytest.importorskip("onnxruntime")

# XGBoost 2.x segfaults on darwin-arm + py3.13 during _meta_from_numpy.
# Same skip pattern as test_trainable_backend_matrix.py / test_predictions_device_matrix.py.
_XGBOOST_SEGFAULT_HOST = (
    sys.platform == "darwin"
    and platform.machine() == "arm64"
    and sys.version_info[:2] >= (3, 13)
)


@pytest.mark.integration
@pytest.mark.skipif(
    _XGBOOST_SEGFAULT_HOST,
    reason=(
        "XGBoost 2.x segfaults on darwin-arm + py3.13 during _meta_from_numpy; "
        "Tier 2 coverage deferred to Linux CI."
    ),
)
def test_xgboost_onnx_roundtrip_prediction_parity(tmp_path: Path) -> None:
    """Train a small XGBoost classifier, export to ONNX, assert parity."""
    import onnxruntime as ort
    import xgboost as xgb
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

    # Train native XGBoost sklearn-API model (onnxmltools supports it)
    model = xgb.XGBClassifier(
        n_estimators=10,
        max_depth=3,
        random_state=42,
        tree_method="hist",
        n_jobs=1,
    )
    model.fit(X, y)

    # Export to ONNX
    onnx_path = tmp_path / "xgboost_model.onnx"
    bridge = OnnxBridge()
    result = bridge.export(
        model,
        framework="xgboost",
        output_path=onnx_path,
        n_features=X.shape[1],
    )
    assert result.success, f"xgboost ONNX export failed: {result.error_message}"
    assert onnx_path.exists()
    assert onnx_path.stat().st_size > 0

    # Re-import via onnxruntime
    session = ort.InferenceSession(str(onnx_path))
    input_name = session.get_inputs()[0].name

    X_test = X[:20]
    native_probs = model.predict_proba(X_test)

    onnx_outputs = session.run(None, {input_name: X_test})
    # XGBoost onnx: outputs[0] = labels, outputs[1] = probabilities
    onnx_labels = np.asarray(onnx_outputs[0]).flatten()
    native_labels = model.predict(X_test)

    assert np.array_equal(
        onnx_labels, native_labels
    ), f"label mismatch: onnx={onnx_labels} native={native_labels}"

    # Coerce onnx probs to ndarray (onnxmltools may emit list-of-dicts)
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
