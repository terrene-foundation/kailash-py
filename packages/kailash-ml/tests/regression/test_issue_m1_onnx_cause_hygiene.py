# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression: M1 — onnx-export partial-failure WARN MUST NOT leak raw cause.

Origin: 2026-04-20 late-session audit finding M1
(``packages/kailash-ml/src/kailash_ml/engine.py:2787-2794``) — the
``engine.register.onnx_partial_failure`` WARN log embedded ``cause=`` in
its ``extra`` payload. That string is the raw exception chain from the
ONNX exporter (``bridge.export``), which typically reveals torch
internals, framework API boundaries, and in some cases user model
names that surface through nested ``RuntimeError`` / ``ValueError``
messages.

Per ``rules/observability.md`` §8 — schema-revealing field names and
exception chain text MUST be logged at DEBUG (or hashed) when emitted
at WARN. The operational signal ("ONNX export partially failed during
format='both' register") is preserved via a hashed ``model_name``
fingerprint + the framework token; the raw cause moves to a sibling
DEBUG line for forensic use.

This is a behavioural regression test per
``rules/testing.md`` § "MUST: Behavioral Regression Tests Over
Source-Grep": it dispatches the private
``MLEngine._export_and_save_onnx`` coroutine through a stubbed
``OnnxBridge`` that fails, captures ``caplog`` records, and asserts:

1. A WARN-level record ``engine.register.onnx_partial_failure`` is
   emitted.
2. That WARN record does NOT contain the raw cause string anywhere in
   its ``extra``, ``msg``, or ``getMessage()`` output.
3. That WARN record does NOT contain the raw model name anywhere in
   its ``extra``, ``msg``, or ``getMessage()`` output — only the
   hashed fingerprint.
4. A DEBUG-level sibling record
   ``engine.register.onnx_partial_failure.detail`` carries the raw
   cause and raw model_name for investigation.
"""
from __future__ import annotations

import asyncio
import logging
from unittest.mock import MagicMock

import pytest


@pytest.mark.regression
def test_m1_onnx_partial_failure_warn_omits_raw_cause_and_name(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """WARN log on ONNX partial-failure MUST NOT contain raw cause or model_name."""
    # Arrange: stub OnnxBridge.export() to return a failed export result
    # with a distinctive cause string that we can search for in log output.
    from kailash_ml.bridge import onnx_bridge as onnx_bridge_module

    sentinel_cause = (
        "RuntimeError: Unsupported op 'torch.special.scaled_modified_bessel_k0' "
        "when tracing model 'UserSchemaDisclosingName'"
    )
    sentinel_model_name = "customer-ssn-classifier-v3"

    class _FailedResult:
        success = False
        error_message = sentinel_cause

    class _StubBridge:
        def export(self, model, framework, output_path):  # noqa: ARG002
            return _FailedResult()

    monkeypatch.setattr(onnx_bridge_module, "OnnxBridge", _StubBridge)

    # Import the engine module lazily so the monkeypatch above is in place
    # before MLEngine resolves OnnxBridge.
    from kailash_ml.engine import MLEngine

    # Build a minimal engine instance: we only exercise the coroutine
    # that emits the log; we never touch the feature store / registry.
    engine = MLEngine.__new__(MLEngine)
    engine._tenant_id = None  # exercised by sibling WARN sites, not this one

    # Act: call the private coroutine with format="both" so the partial
    # failure path (not the raising path) triggers.
    async def _run() -> None:
        with caplog.at_level(logging.DEBUG, logger="kailash_ml.engine"):
            await engine._export_and_save_onnx(
                model=MagicMock(),
                framework="torch",
                name=sentinel_model_name,
                version=1,
                format="both",
                artifact_store=MagicMock(),
            )

    asyncio.run(_run())

    # Assert 1: WARN record was emitted with the expected event name.
    warn_records = [
        r
        for r in caplog.records
        if r.levelno == logging.WARNING
        and r.getMessage() == "engine.register.onnx_partial_failure"
    ]
    assert len(warn_records) == 1, (
        "Expected exactly one WARN for onnx_partial_failure; "
        f"got {len(warn_records)}: {[r.getMessage() for r in caplog.records]}"
    )
    warn = warn_records[0]

    # Assert 2: WARN record's extras / message MUST NOT contain the raw
    # cause string. The cause lives at DEBUG only.
    warn_payload = repr(vars(warn))
    assert sentinel_cause not in warn_payload, (
        "WARN record leaked the raw cause string; per observability §8 "
        "exception chain text stays at DEBUG."
    )
    # Extras should not carry a 'cause' key at all
    assert (
        not hasattr(warn, "cause") or getattr(warn, "cause", None) is None
    ), "WARN record carries a 'cause' attribute; must move to DEBUG sibling."

    # Assert 3: WARN record MUST NOT contain the raw model name (schema
    # identifier). A hashed fingerprint field IS required.
    assert sentinel_model_name not in warn_payload, (
        "WARN record leaked the raw model_name; per observability §8 "
        "schema-revealing field names stay at DEBUG or are hashed."
    )
    assert hasattr(warn, "model_name_fingerprint"), (
        "WARN record missing 'model_name_fingerprint' field — operators "
        "cannot correlate the warning with the corresponding DEBUG entry."
    )
    assert isinstance(warn.model_name_fingerprint, str)
    assert (
        len(warn.model_name_fingerprint) == 4
    ), f"Fingerprint is not 4 hex chars: {warn.model_name_fingerprint!r}"

    # Assert 4: a sibling DEBUG record carries the raw cause + raw
    # model_name for investigation.
    detail_records = [
        r
        for r in caplog.records
        if r.levelno == logging.DEBUG
        and r.getMessage() == "engine.register.onnx_partial_failure.detail"
    ]
    assert len(detail_records) == 1, (
        "Expected exactly one DEBUG detail sibling record; "
        f"got {len(detail_records)}"
    )
    detail = detail_records[0]
    assert getattr(detail, "cause", None) == sentinel_cause
    assert getattr(detail, "model_name", None) == sentinel_model_name
    assert getattr(detail, "framework", None) == "torch"
