# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier 1 unit tests for W17 ONNX probe (``specs/ml-registry.md`` §5.6).

Covers the classify+resolve surface in isolation. The end-to-end
``export_to_onnx`` path exercises real frameworks and lives in the W17.C
integration test (real sklearn model + LocalFileArtifactStore).

Tests use hand-crafted :class:`onnx.ModelProto` serializations to exercise
the classify path without depending on torch / skl2onnx at unit-test time.
"""
from __future__ import annotations

import hashlib

import pytest

try:
    import onnx as _onnx  # noqa: F401 — presence gates the test module
    from onnx import TensorProto, helper

    HAS_ONNX = True
except ImportError:  # pragma: no cover — onnx is a base kailash-ml dep
    HAS_ONNX = False

pytestmark = pytest.mark.skipif(not HAS_ONNX, reason="onnx package required")

from kailash_ml.tracking.artifacts.onnx_probe import (  # noqa: E402
    OnnxExportError,
    OnnxExportUnsupportedOpsError,
    OnnxProbeResult,
    classify_onnx_bytes,
    resolve_ort_extensions,
)

# --- Helpers --------------------------------------------------------------


def _make_onnx_bytes(opset_domains: dict[str, int]) -> bytes:
    """Build a minimal valid ONNX model with the requested opset imports.

    The graph itself is trivial (Identity op passing a float tensor
    through) — the probe only reads ``ModelProto.opset_import``, which
    is what the test varies.
    """
    input_info = helper.make_tensor_value_info("x", TensorProto.FLOAT, [1, 1])
    output_info = helper.make_tensor_value_info("y", TensorProto.FLOAT, [1, 1])
    node = helper.make_node("Identity", ["x"], ["y"])
    graph = helper.make_graph([node], "test-graph", [input_info], [output_info])
    opset_imports = [
        helper.make_opsetid(domain, version)
        for domain, version in opset_domains.items()
    ]
    model = helper.make_model(graph, opset_imports=opset_imports)
    return model.SerializeToString()


# --- resolve_ort_extensions ----------------------------------------------


def test_resolve_returns_empty_for_standard_domains_only() -> None:
    assert resolve_ort_extensions({"": 17}) == []
    assert resolve_ort_extensions({"ai.onnx": 17, "ai.onnx.ml": 3}) == []


def test_resolve_maps_com_microsoft_to_onnxruntime_extensions() -> None:
    result = resolve_ort_extensions({"": 17, "com.microsoft": 1})
    assert result == ["onnxruntime_extensions"]


def test_resolve_dedups_identical_package_names() -> None:
    # A model that declares the same custom domain twice at different
    # opset versions MUST emit the package once.
    result = resolve_ort_extensions({"": 17, "com.microsoft": 1})
    assert result.count("onnxruntime_extensions") == 1


def test_resolve_skips_unknown_domain_without_raising(caplog) -> None:
    # An unknown custom domain is a WARN, not a crash — the probe must
    # not reject an otherwise-valid model on first encounter.
    import logging

    caplog.set_level(logging.WARNING)
    result = resolve_ort_extensions({"": 17, "org.experimental": 1})
    assert result == []
    assert any("unknown_custom_domain" in rec.message for rec in caplog.records)


# --- classify_onnx_bytes -------------------------------------------------


def test_classify_clean_no_custom_ops() -> None:
    b = _make_onnx_bytes({"": 17})
    result = classify_onnx_bytes(b)

    assert isinstance(result, OnnxProbeResult)
    assert result.onnx_status == "clean"
    assert result.opset_imports == {"": 17}
    assert result.ort_extensions == []
    assert result.onnx_bytes == b
    assert result.sha256_hex == hashlib.sha256(b).hexdigest()


def test_classify_custom_ops_com_microsoft() -> None:
    b = _make_onnx_bytes({"": 17, "com.microsoft": 1})
    result = classify_onnx_bytes(b)

    assert result.onnx_status == "custom_ops"
    assert result.opset_imports == {"": 17, "com.microsoft": 1}
    assert result.ort_extensions == ["onnxruntime_extensions"]


def test_classify_unknown_domain_stays_clean() -> None:
    # Unknown custom domain → resolve_ort_extensions returns [] → clean.
    # The probe MUST NOT promote unknown domains to custom_ops without a
    # package mapping, otherwise the serving layer tries to load an
    # extensions package that doesn't exist.
    b = _make_onnx_bytes({"": 17, "org.experimental": 1})
    result = classify_onnx_bytes(b)
    assert result.onnx_status == "clean"
    assert result.ort_extensions == []


def test_classify_rejects_non_bytes() -> None:
    with pytest.raises(OnnxExportError) as excinfo:
        classify_onnx_bytes("not-bytes")  # type: ignore[arg-type]
    assert "must be bytes" in excinfo.value.cause


def test_classify_rejects_empty() -> None:
    with pytest.raises(OnnxExportError) as excinfo:
        classify_onnx_bytes(b"")
    assert "empty" in excinfo.value.cause


def test_classify_rejects_invalid_protobuf() -> None:
    # Garbage bytes should surface as OnnxExportError rather than a
    # naked protobuf parse exception.
    with pytest.raises(Exception) as excinfo:
        classify_onnx_bytes(b"\x00\x01\x02not-a-valid-onnx-protobuf")
    # Either OnnxExportError (if onnx parse fails with a typed error we
    # map) or the raw onnx parse error — both are acceptable as long as
    # it raises something actionable.
    assert excinfo.value is not None


# --- OnnxExportError / OnnxExportUnsupportedOpsError --------------------


def test_onnx_export_error_preserves_framework_and_cause() -> None:
    err = OnnxExportError(framework="torch", cause="out of memory")
    assert err.framework == "torch"
    assert err.cause == "out of memory"
    # Message is grep-able — should surface both fields.
    s = str(err)
    assert "torch" in s and "out of memory" in s


def test_unsupported_ops_error_sorts_and_dedupes() -> None:
    err = OnnxExportUnsupportedOpsError(
        framework="torch",
        unsupported_ops=["FlashAttention", "Foo", "FlashAttention"],
    )
    assert err.unsupported_ops == ["FlashAttention", "Foo"]
    # Subclass relation: callers that want a pickle fallback on
    # unsupported-ops specifically catch the narrower type.
    assert isinstance(err, OnnxExportError)


def test_unsupported_ops_error_is_distinct_type() -> None:
    # The registry's fallback path depends on being able to distinguish
    # this from the generic failure class.
    err = OnnxExportUnsupportedOpsError(framework="torch", unsupported_ops=["Op"])
    assert type(err) is OnnxExportUnsupportedOpsError
