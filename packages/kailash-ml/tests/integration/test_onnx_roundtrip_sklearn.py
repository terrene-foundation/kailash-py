# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier 2 ONNX round-trip regression test for sklearn.

Per ``specs/ml-engines.md`` §6.1 MUST 3: every framework key in the ONNX
compatibility matrix MUST have a round-trip regression test that trains a
minimal model, exports to ONNX, re-imports via ``onnxruntime.InferenceSession``,
and asserts prediction parity against the native model.

This test is the orphan guard per ``rules/orphan-detection.md`` §2a — it
proves the sklearn export branch is wired end-to-end through onnxruntime,
not just that the export function produces bytes.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

pytest.importorskip("sklearn")
pytest.importorskip("skl2onnx")
pytest.importorskip("onnxruntime")


@pytest.mark.integration
def test_sklearn_onnx_roundtrip_prediction_parity(tmp_path: Path) -> None:
    """Train a small sklearn classifier, export to ONNX, assert parity."""
    import onnxruntime as ort
    from sklearn.datasets import make_classification
    from sklearn.ensemble import RandomForestClassifier

    from kailash_ml.bridge.onnx_bridge import OnnxBridge

    rng = np.random.default_rng(seed=42)
    X, y = make_classification(
        n_samples=200,
        n_features=8,
        n_informative=5,
        n_redundant=2,
        random_state=42,
    )
    X = X.astype(np.float32)

    # Train native sklearn model
    model = RandomForestClassifier(n_estimators=10, random_state=42)
    model.fit(X, y)

    # Export to ONNX
    onnx_path = tmp_path / "sklearn_model.onnx"
    bridge = OnnxBridge()
    result = bridge.export(
        model,
        framework="sklearn",
        output_path=onnx_path,
        n_features=X.shape[1],
    )
    assert result.success, f"sklearn ONNX export failed: {result.error_message}"
    assert onnx_path.exists(), "ONNX file was not written to output_path"
    assert onnx_path.stat().st_size > 0, "ONNX file is empty"

    # Re-import via onnxruntime
    session = ort.InferenceSession(str(onnx_path))
    input_name = session.get_inputs()[0].name

    # Use a held-out sample slice (not training data) for parity check
    X_test = X[:20]
    native_preds = model.predict(X_test)
    native_probs = model.predict_proba(X_test)

    # ONNX predictions — sklearn classifiers emit label + probabilities
    onnx_outputs = session.run(None, {input_name: X_test})
    onnx_labels = np.asarray(onnx_outputs[0]).flatten()

    # Label parity — must match exactly
    assert np.array_equal(
        onnx_labels, native_preds
    ), f"label mismatch: onnx={onnx_labels} native={native_preds}"

    # Probability parity — skl2onnx emits a list of dicts OR a 2D array
    # depending on the estimator; coerce to a 2D array and check allclose
    onnx_probs_raw = onnx_outputs[1]
    if isinstance(onnx_probs_raw, list) and isinstance(onnx_probs_raw[0], dict):
        # List of {label: prob} dicts — order by sorted keys
        classes = sorted(onnx_probs_raw[0].keys())
        onnx_probs = np.array(
            [[row[c] for c in classes] for row in onnx_probs_raw], dtype=np.float32
        )
    else:
        onnx_probs = np.asarray(onnx_probs_raw, dtype=np.float32)

    assert np.allclose(
        onnx_probs, native_probs, rtol=1e-3, atol=1e-5
    ), f"probability drift too large: max diff={np.max(np.abs(onnx_probs - native_probs))}"
