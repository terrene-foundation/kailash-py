# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression tests for issue #685 — DataFlowEngine.register_model.

Pre-fix: ``DataFlowEngine.register_model`` called
``self._dataflow.register_model(model)`` on the DataFlow primitive,
which did not have a ``register_model`` method. Every non-decorator
registration path raised ``AttributeError`` before any work happened.

Post-fix:
1. ``DataFlow.register_model(model_cls)`` is the canonical entry point
   (DPI-C1) — both ``@db.model`` and ``DataFlowEngine.register_model``
   route through it.
2. ``DataFlowEngine.register_model(None, Model)`` works end-to-end;
   the ``registry`` param is kept for cross-SDK parity per
   ``rules/cross-sdk-inspection.md`` § 3a.

These tests use a file-backed SQLite URL (per
``packages/kailash-dataflow/tests/regression/conftest.py::sqlite_file_url``)
because the fixes touched no PG-specific behaviour and Tier-2
SQLite is the appropriate carve-out for surface-level engine tests.
"""

from __future__ import annotations

import pytest

from dataflow import DataFlow, DataFlowEngine
from dataflow.classification import (
    ClassificationPolicy,
    DataClassification,
    MaskingStrategy,
    classify,
)


@pytest.mark.regression
def test_register_model_does_not_raise_attributeerror(sqlite_file_url):
    """Repro from issue #685.

    Pre-fix: ``engine.register_model(None, Foo)`` raised
    ``AttributeError: 'DataFlow' object has no attribute 'register_model'``.

    Post-fix: completes without raising and the model is registered on
    BOTH the underlying DataFlow primitive AND the engine's
    ``_registered_models`` list.
    """
    engine = DataFlowEngine.builder(sqlite_file_url).build_sync()

    class Foo:
        name: str
        active: bool = True

    # Must not raise AttributeError.
    engine.register_model(None, Foo)

    # State assertions: both the DataFlow primitive AND the engine's
    # tracking list must show the registration.
    assert "Foo" in engine.dataflow._models
    assert Foo in engine._registered_models
    assert "Foo" in engine.dataflow._model_fields


@pytest.mark.regression
def test_register_model_with_classification_policy(sqlite_file_url):
    """Classification-policy passthrough still works after DPI-C1/DPI-C2.

    When the engine has a ``ClassificationPolicy`` set via
    ``.classification_policy(policy)``, ``register_model`` MUST
    propagate the model to the policy so per-field classification
    metadata is registered in BOTH the engine's policy AND the
    DataFlow primitive's policy.
    """
    policy = ClassificationPolicy()

    engine = (
        DataFlowEngine.builder(sqlite_file_url)
        .classification_policy(policy)
        .build_sync()
    )

    @classify(
        "email",
        DataClassification.PII,
        masking=MaskingStrategy.REDACT,
    )
    class User:
        email: str
        name: str

    engine.register_model(None, User)

    # Engine-level classification policy registration: the
    # classification helper used for get_model_classification_report
    # is the @classify decorator metadata stored on the class itself.
    report = engine.get_model_classification_report(User)
    assert "email" in report
    assert report["email"]["classification"] == DataClassification.PII.value


@pytest.mark.regression
def test_get_model_classification_report_after_register(sqlite_file_url):
    """Full round-trip from issue #685 acceptance criteria.

    Pre-fix: the AttributeError fired before any registration could
    happen, so the classification report could not be built.

    Post-fix: a model registered via ``engine.register_model`` exposes
    its ``@classify`` metadata via ``get_model_classification_report``.
    """
    engine = DataFlowEngine.builder(sqlite_file_url).build_sync()

    @classify(
        "ssn",
        DataClassification.PII,
        masking=MaskingStrategy.REDACT,
    )
    @classify(
        "salary",
        DataClassification.HIGHLY_CONFIDENTIAL,
        masking=MaskingStrategy.REDACT,
    )
    class Employee:
        name: str
        ssn: str
        salary: float

    engine.register_model(None, Employee)

    report = engine.get_model_classification_report(Employee)

    assert "ssn" in report
    assert "salary" in report
    assert report["ssn"]["classification"] == DataClassification.PII.value
    assert (
        report["salary"]["classification"]
        == DataClassification.HIGHLY_CONFIDENTIAL.value
    )


@pytest.mark.regression
def test_dataflow_register_model_idempotency_raises(sqlite_file_url):
    """DPI-C1 idempotency contract.

    Calling ``DataFlow.register_model(Foo)`` twice without ``replace=True``
    raises ``ValueError`` per the destructive-confirmation pattern in
    rules/dataflow-identifier-safety.md Rule 4.
    """
    db = DataFlow(sqlite_file_url)

    class Foo:
        name: str

    db.register_model(Foo)

    with pytest.raises(ValueError, match="already registered"):
        db.register_model(Foo)


@pytest.mark.regression
def test_dataflow_register_model_replace_requires_force_drop(sqlite_file_url):
    """DPI-C1 destructive-confirmation contract.

    ``register_model(Foo, replace=True)`` without ``force_drop=True``
    is refused — re-registration may DROP the underlying table, which
    is irreversible per rules/dataflow-identifier-safety.md Rule 4.
    """
    db = DataFlow(sqlite_file_url)

    class Bar:
        value: int

    db.register_model(Bar)

    with pytest.raises(ValueError, match="force_drop=True"):
        db.register_model(Bar, replace=True)


@pytest.mark.regression
def test_dataflow_register_model_replace_with_force_drop_succeeds(
    sqlite_file_url,
):
    """DPI-C1 explicit re-registration path.

    Passing both ``replace=True`` AND ``force_drop=True`` allows
    re-registration. The class is returned for chaining.
    """
    db = DataFlow(sqlite_file_url)

    class Baz:
        amount: int

    db.register_model(Baz)
    assert "Baz" in db._models

    # Re-register the same class — the explicit double-flag path.
    result = db.register_model(Baz, replace=True, force_drop=True)
    assert result is Baz
    assert "Baz" in db._models  # Re-registered, not removed.


@pytest.mark.regression
def test_register_model_decorator_and_method_produce_identical_state(
    sqlite_file_url,
):
    """DPI-C1 contract: ``@db.model`` and ``db.register_model`` produce
    identical state.

    Both paths must populate the same DataFlow internal state
    (``_models``, ``_registered_models``, ``_model_fields``,
    ``_pending_relationship_detection``) so downstream consumers
    cannot tell which path the user took.
    """
    db1 = DataFlow(sqlite_file_url)
    db2 = DataFlow(sqlite_file_url)

    @db1.model
    class ModelA:
        name: str
        active: bool = True

    class ModelB:  # Identical structure, different class identity
        name: str
        active: bool = True

    ModelB.__name__ = "ModelA"  # Match the decorator path's keyspace
    db2.register_model(ModelB)

    # Per-keyspace structural equality — both paths registered "ModelA".
    assert "ModelA" in db1._models
    assert "ModelA" in db2._models

    fields_a = db1._model_fields["ModelA"]
    fields_b = db2._model_fields["ModelA"]
    assert set(fields_a.keys()) == set(fields_b.keys())
    for fname in fields_a:
        assert fields_a[fname]["type"] == fields_b[fname]["type"]
        assert fields_a[fname]["required"] == fields_b[fname]["required"]
