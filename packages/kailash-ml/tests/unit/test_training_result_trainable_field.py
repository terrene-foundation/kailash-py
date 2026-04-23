# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for the W33c `TrainingResult.trainable` back-reference field.

Per `specs/ml-registry.md` §5.6.1, every `MLEngine.register(result=...)`
call must be able to locate the fitted model via
``training_result.trainable.model``. This file pins the field's default
behavior, its absence from wire serialization, and its compatibility
with ``dataclasses.replace()`` (the mechanism `MLEngine.fit` uses to
enforce tenant-id propagation).
"""
from __future__ import annotations

from dataclasses import fields, replace

import pytest

from kailash_ml._device_report import DeviceReport
from kailash_ml._result import TrainingResult


def _minimal_device() -> DeviceReport:
    return DeviceReport(
        family="cpu",
        backend="cpu",
        device_string="cpu",
        precision="32-true",
        fallback_reason=None,
        array_api=False,
    )


def _minimal_result(**overrides) -> TrainingResult:
    kwargs = dict(
        model_uri="models://test/1",
        metrics={"accuracy": 0.95},
        device_used="cpu",
        accelerator="cpu",
        precision="32-true",
        elapsed_seconds=0.1,
        tracker_run_id=None,
        tenant_id=None,
        artifact_uris={},
        lightning_trainer_config={},
        family="sklearn",
        device=_minimal_device(),
    )
    kwargs.update(overrides)
    return TrainingResult(**kwargs)


def test_trainable_field_present_in_dataclass_schema() -> None:
    """W33c: the ``trainable`` field MUST be declared on TrainingResult."""
    names = [f.name for f in fields(TrainingResult)]
    assert "trainable" in names, (
        f"TrainingResult is missing the W33c `trainable` field. "
        f"Available fields: {names}"
    )


def test_trainable_field_defaults_to_none() -> None:
    """Direct-user construction (tests / cross-SDK replay) MAY omit trainable."""
    result = _minimal_result()
    assert result.trainable is None, (
        "Default for `trainable` must be None so literal-construction "
        "paths continue to work"
    )


def test_trainable_field_accepts_arbitrary_object_with_model_attr() -> None:
    """Framework paths attach a live Trainable with a .model property."""

    class _FakeTrainable:
        model = "fitted-estimator-sentinel"

    fake = _FakeTrainable()
    result = _minimal_result(trainable=fake)
    assert result.trainable is fake
    assert result.trainable.model == "fitted-estimator-sentinel"


def test_trainable_excluded_from_to_dict_wire_payload() -> None:
    """Live Python Trainables are NOT wire-serializable; to_dict drops it."""

    class _FakeTrainable:
        model = "fitted"

    result = _minimal_result(trainable=_FakeTrainable())
    payload = result.to_dict()
    assert "trainable" not in payload, (
        "to_dict MUST exclude the `trainable` back-reference — a live "
        "Python instance is not a stable wire payload. Registry "
        "persistence uses artifact_uris + family instead."
    )


def test_trainable_excluded_from_from_dict_round_trip() -> None:
    """from_dict payloads (legacy wire shape) must still deserialize."""
    result = _minimal_result()
    payload = result.to_dict()
    # Simulate a legacy wire payload that pre-dates the W33c field.
    round_trip = TrainingResult.from_dict(payload)
    assert round_trip.trainable is None


def test_dataclasses_replace_preserves_trainable() -> None:
    """`MLEngine.fit` uses dataclasses.replace for tenant-id propagation.

    If `replace()` did not preserve the unchanged `trainable` field the
    engine would strip the back-reference before `register()` looks it
    up — regressing the W33c fix invisibly.
    """

    class _FakeTrainable:
        model = "fitted"

    fake = _FakeTrainable()
    original = _minimal_result(trainable=fake, tenant_id=None)
    mutated = replace(original, tenant_id="tenant-xyz")
    assert mutated.trainable is fake, (
        "dataclasses.replace dropped the `trainable` back-reference — "
        "MLEngine.fit's tenant-id override path would break km.register"
    )


def test_trainable_field_is_compare_false() -> None:
    """Two TrainingResults should compare equal even if they carry
    different live Trainable instances — the back-reference is an
    in-process handle, not part of the scientific payload."""

    class _FakeA:
        model = "A"

    class _FakeB:
        model = "B"

    r1 = _minimal_result(trainable=_FakeA())
    r2 = _minimal_result(trainable=_FakeB())
    # If `trainable` participated in compare, r1 != r2 would hold — but
    # the field is compare=False so we expect equality here.
    assert r1 == r2, (
        "trainable field must NOT participate in __eq__: live Python "
        "instances would break legitimate equality checks between "
        "results that share the same scientific payload."
    )
