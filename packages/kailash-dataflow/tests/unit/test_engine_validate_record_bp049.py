# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression: ``DataFlowEngine.validate_record`` MUST route BP-049 sanitiser.

Context
-------

The BP-049 fix (kailash-dataflow 2.0.11) landed ``policy`` + ``model_name``
plumbing on :func:`dataflow.validation.decorators.validate_model` so
validation errors never echo classified field names / values. Every
caller had to be updated to forward both kwargs.

Post-release review found :meth:`dataflow.engine.DataFlowEngine.validate_record`
called ``validate_model(instance)`` without kwargs, so validation
errors from the engine's public validation path still leaked classified
identifiers. This test pins the fix.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from dataflow.engine import DataFlowEngine


@pytest.mark.regression
def test_validate_record_forwards_policy_and_model_name() -> None:
    """``validate_record`` MUST pass policy+model_name to validate_model."""
    dataflow = MagicMock()
    policy_sentinel = object()
    dataflow._classification_policy = policy_sentinel

    engine = DataFlowEngine.__new__(DataFlowEngine)
    engine._dataflow = dataflow

    class User:
        pass

    instance = User()

    captured: dict = {}

    def fake_validate_model(inst, policy=None, model_name=None):
        captured["instance"] = inst
        captured["policy"] = policy
        captured["model_name"] = model_name
        return MagicMock(valid=True)

    with patch(
        "dataflow.validation.decorators.validate_model",
        side_effect=fake_validate_model,
    ):
        engine.validate_record(instance)

    assert captured["instance"] is instance
    assert captured["policy"] is policy_sentinel, (
        "validate_record did not forward the classification policy; "
        "BP-049 sanitiser is bypassed for every engine-level "
        "validation error."
    )
    assert captured["model_name"] == "User", (
        f"validate_record did not forward model_name (got "
        f"{captured['model_name']!r}); sanitiser cannot look up field "
        f"classifications without it."
    )
