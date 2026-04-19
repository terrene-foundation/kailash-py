# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier 2 ONNX round-trip regression test for LightGBM.

Per ``specs/ml-engines.md`` §6.1 MUST 3. Orphan guard per
``rules/orphan-detection.md`` §2a.
"""
from __future__ import annotations

import platform
import sys
from pathlib import Path

import numpy as np
import pytest

pytest.importorskip("lightgbm")
pytest.importorskip("onnxmltools")
pytest.importorskip("onnxruntime")

# LightGBM 4.x segfaults on darwin-arm + py3.13 during __init_from_np2d.
_LIGHTGBM_SEGFAULT_HOST = (
    sys.platform == "darwin"
    and platform.machine() == "arm64"
    and sys.version_info[:2] >= (3, 13)
)


@pytest.mark.integration
@pytest.mark.skipif(
    _LIGHTGBM_SEGFAULT_HOST,
    reason=(
        "LightGBM 4.x segfaults on darwin-arm + py3.13 during __init_from_np2d; "
        "Tier 2 coverage deferred to Linux CI."
    ),
)
def test_lightgbm_onnx_roundtrip_prediction_parity(tmp_path: Path) -> None:
    """Train a small LightGBM classifier, export to ONNX, assert parity."""
    import lightgbm as lgb
    import onnxruntime as ort
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

    model = lgb.LGBMClassifier(
        n_estimators=10,
        max_depth=3,
        random_state=42,
        verbose=-1,
        n_jobs=1,
    )
    model.fit(X, y)

    onnx_path = tmp_path / "lightgbm_model.onnx"
    bridge = OnnxBridge()
    result = bridge.export(
        model,
        framework="lightgbm",
        output_path=onnx_path,
        n_features=X.shape[1],
    )
    assert result.success, f"lightgbm ONNX export failed: {result.error_message}"
    assert onnx_path.exists()
    assert onnx_path.stat().st_size > 0

    session = ort.InferenceSession(str(onnx_path))
    input_name = session.get_inputs()[0].name

    X_test = X[:20]
    native_probs = model.predict_proba(X_test)
    native_labels = model.predict(X_test)

    onnx_outputs = session.run(None, {input_name: X_test})
    onnx_labels = np.asarray(onnx_outputs[0]).flatten()

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
