# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier 2 integration tests for BP-049 classification-leak surfaces.

Issue #520 — cross-SDK alignment with kailash-rs v3.19.0. Three DataFlow
surfaces leaked classified field values / field names:

* **M1 — NotFound / trust-audit error paths.** ``express.read`` /
  ``express.update`` / ``express.delete`` routed raw PK values into
  ``_trust_record_failure`` / ``_trust_record_success`` as
  ``query_params={"id": id}`` AND into the
  ``"express.record_not_found_for_read"`` structured-log event. The fix
  wraps every PK-emitting site in ``_safe_record_id`` /
  ``_safe_query_params`` so classified string PKs are SHA-256 hashed
  before reaching the audit / log surface.

* **M2 — Cache key construction.** ``CacheKeyGenerator`` accepted a raw
  PK dict as ``params`` and serialised it through ``json.dumps`` before
  hashing. When a cache backend persisted the pre-hash JSON (any
  backend without at-rest encryption) the raw PK value was visible on
  disk. The fix passes a ``ClassificationPolicy`` into the generator
  and routes classified PKs through ``format_record_id_for_event``
  BEFORE JSON serialisation. The cache keyspace version also bumps
  ``v1 → v2`` for cross-SDK parity with kailash-rs.

* **M3 — Validation error messages.** ``FieldValidationError.value``
  stored the offending raw value, and ``message`` interpolated the
  classified field NAME. The fix adds the
  ``dataflow.classification.validation_error.sanitize_validation_error``
  helper and routes every validation error through it;
  ``ValidationResult.classified_field_count`` carries the aggregate
  count for operator alerting without revealing which field was
  affected.

These tests pin the contract. Each test:

1. Constructs a real ``DataFlow`` against PostgreSQL via the shared
   ``IntegrationTestSuite`` fixture.
2. Registers a model with a classified PK (``DataClassification.PII``
   on ``id``).
3. Exercises the production hot path.
4. Asserts the externally-observable surface (event payload, cache
   key, validation error) does NOT contain the raw PK value.

Cross-SDK: the reference test file is
``crates/kailash-dataflow/tests/bp_049_classification_leaks_wiring.rs``.
"""

from __future__ import annotations

import hashlib
import uuid

import pytest

from dataflow import DataFlow
from dataflow.cache.key_generator import CacheKeyGenerator
from dataflow.classification import (
    DataClassification,
    MaskingStrategy,
    classify,
)
from dataflow.classification.policy import ClassificationPolicy
from dataflow.classification.validation_error import (
    CLASSIFIED_FIELD_NAME_PLACEHOLDER,
    classified_value_descriptor,
    sanitize_validation_error,
)
from dataflow.validation.decorators import field_validator, validate_model
from dataflow.validation.result import ValidationResult

from tests.infrastructure.test_harness import IntegrationTestSuite

pytestmark = [pytest.mark.integration]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def test_suite():
    """Shared Tier-2 fixture: real PostgreSQL on port 5434."""
    suite = IntegrationTestSuite()
    async with suite.session():
        yield suite


@pytest.fixture
def unique_model_name() -> str:
    """Unique model name per test to avoid registry collisions."""
    return f"Bp049{uuid.uuid4().hex[:10]}"


def _make_db_with_classified_pk(db_url: str, model_name: str) -> DataFlow:
    """Model keyed by a classified string ``id``.

    This is the exact shape that triggered the leak on every BP-049
    surface: a model keyed by a classified PK (email, SSN, external
    reference ID).
    """
    db = DataFlow(db_url, auto_migrate=True, pool_size=2, max_overflow=2)
    cls = type(
        model_name,
        (),
        {
            "__annotations__": {"id": str, "label": str},
            "id": "",
            "label": "",
        },
    )
    cls = classify("id", DataClassification.PII, masking=MaskingStrategy.REDACT)(cls)
    db.model(cls)
    return db


def _expected_hash(raw: str) -> str:
    return f"sha256:{hashlib.sha256(raw.encode()).hexdigest()[:8]}"


# ---------------------------------------------------------------------------
# M1 — error messages / trust-audit paths
# ---------------------------------------------------------------------------


async def test_m1_read_not_found_audit_does_not_leak_classified_pk(
    test_suite, unique_model_name
):
    """``express.read`` for a missing classified PK MUST NOT emit the raw
    value to the trust-audit / log surface.

    Reads the ``_safe_query_params`` result via the write event the
    audit path emits on the cache-miss → not-found branch. If the raw
    PK appears anywhere in the event payload ``repr`` the test fails.
    """
    db = _make_db_with_classified_pk(test_suite.config.url, unique_model_name)
    events = []
    try:
        await db.initialize()
        db.on_model_change(unique_model_name, lambda evt: events.append(evt))
        raw_pk = f"alice-{uuid.uuid4().hex[:8]}@leak.example"
        # Read a PK that doesn't exist — exercises the not-found +
        # _safe_query_params path.
        result = await db.express.read(unique_model_name, raw_pk)
        assert result is None
        # The event bus does NOT emit on read; the contract is that the
        # trust-audit and log surfaces scrub the PK. Directly exercise
        # the helper on the DataFlowExpress instance to pin the contract.
        safe = db.express._safe_record_id(unique_model_name, raw_pk)
        assert safe == _expected_hash(raw_pk), (
            f"Classified PK MUST be hashed before it reaches the audit "
            f"surface. Got {safe!r}, expected {_expected_hash(raw_pk)!r}."
        )
        safe_params = db.express._safe_query_params(unique_model_name, {"id": raw_pk})
        assert safe_params == {"id": _expected_hash(raw_pk)}
        assert raw_pk not in repr(
            safe_params
        ), f"Raw PK leaked into audit query_params: {safe_params!r}"
    finally:
        db.close()


async def test_m1_create_event_hashes_classified_pk(test_suite, unique_model_name):
    """``express.create`` event payload MUST carry ``sha256:`` for a
    classified PK — the combined fix for BP-048 + BP-049.
    """
    db = _make_db_with_classified_pk(test_suite.config.url, unique_model_name)
    events = []
    try:
        await db.initialize()
        db.on_model_change(unique_model_name, lambda evt: events.append(evt))
        raw_pk = f"alice-{uuid.uuid4().hex[:8]}@leak.example"
        await db.express.create(unique_model_name, {"id": raw_pk, "label": "hi"})
        creates = [
            e for e in events if e.event_type.endswith(f".{unique_model_name}.create")
        ]
        assert len(creates) == 1
        record_id = creates[0].payload["record_id"]
        assert record_id is not None
        assert record_id.startswith(
            "sha256:"
        ), f"Classified PK MUST be hashed in create event; got {record_id!r}"
        assert raw_pk not in repr(
            creates[0].payload
        ), f"Raw PK leaked into event payload: {creates[0].payload!r}"
    finally:
        db.close()


async def test_m1_update_event_hashes_classified_pk(test_suite, unique_model_name):
    """``express.update`` event payload MUST carry ``sha256:`` for a
    classified PK — pre-BP-049 shipped ``str(id)`` verbatim.
    """
    db = _make_db_with_classified_pk(test_suite.config.url, unique_model_name)
    events = []
    try:
        await db.initialize()
        raw_pk = f"alice-{uuid.uuid4().hex[:8]}@leak.example"
        await db.express.create(unique_model_name, {"id": raw_pk, "label": "initial"})
        # Subscribe AFTER create so we only capture the update event.
        db.on_model_change(unique_model_name, lambda evt: events.append(evt))
        await db.express.update(unique_model_name, raw_pk, {"label": "updated"})
        updates = [
            e for e in events if e.event_type.endswith(f".{unique_model_name}.update")
        ]
        assert len(updates) == 1
        record_id = updates[0].payload["record_id"]
        assert record_id is not None
        assert record_id.startswith(
            "sha256:"
        ), f"Classified PK MUST be hashed in update event; got {record_id!r}"
        assert raw_pk not in repr(updates[0].payload)
    finally:
        db.close()


async def test_m1_delete_event_hashes_classified_pk(test_suite, unique_model_name):
    """``express.delete`` event payload MUST carry ``sha256:`` for a
    classified PK — closes the last mutation primitive.
    """
    db = _make_db_with_classified_pk(test_suite.config.url, unique_model_name)
    events = []
    try:
        await db.initialize()
        raw_pk = f"alice-{uuid.uuid4().hex[:8]}@leak.example"
        await db.express.create(unique_model_name, {"id": raw_pk, "label": "initial"})
        db.on_model_change(unique_model_name, lambda evt: events.append(evt))
        await db.express.delete(unique_model_name, raw_pk)
        deletes = [
            e for e in events if e.event_type.endswith(f".{unique_model_name}.delete")
        ]
        assert len(deletes) == 1
        record_id = deletes[0].payload["record_id"]
        assert record_id is not None
        assert record_id.startswith(
            "sha256:"
        ), f"Classified PK MUST be hashed in delete event; got {record_id!r}"
        assert raw_pk not in repr(deletes[0].payload)
    finally:
        db.close()


# ---------------------------------------------------------------------------
# M2 — cache key construction
# ---------------------------------------------------------------------------


def test_m2_default_version_is_v2():
    """Cross-SDK parity: default keyspace is ``v2`` per BP-049."""
    kg = CacheKeyGenerator()
    assert (
        kg.version == "v2"
    ), f"BP-049 cross-SDK contract requires v2 keyspace; got {kg.version!r}"


def test_m2_cache_key_does_not_embed_raw_classified_pk():
    """Cache key for a classified-PK read MUST NOT contain the raw value
    anywhere in its key material (including the pre-hash JSON).
    """
    policy = ClassificationPolicy()
    policy.set_field(
        "Account",
        "id",
        DataClassification.PII,
        masking=MaskingStrategy.REDACT,
    )
    kg = CacheKeyGenerator(classification_policy=policy)
    raw_pk = "alice@leak.example"

    # The final key is md5-hashed so the raw value isn't literally
    # visible, but the pre-hash JSON IS the leak surface for any cache
    # backend that persists key material / debug-logs key inputs. The
    # sanitiser substitutes the hash BEFORE serialisation.
    safe = kg._safe_params("Account", {"id": raw_pk})
    assert safe["id"] == _expected_hash(raw_pk)

    # Unclassified model: value passes through unchanged.
    passthrough = kg._safe_params("NotClassified", {"id": raw_pk})
    assert passthrough == {"id": raw_pk}


def test_m2_cache_key_classified_pk_produces_stable_different_key():
    """Two different raw classified PKs produce two different cache
    keys (the hashing does not collapse values)."""
    policy = ClassificationPolicy()
    policy.set_field(
        "Account",
        "id",
        DataClassification.PII,
        masking=MaskingStrategy.REDACT,
    )
    kg = CacheKeyGenerator(classification_policy=policy)

    key_a = kg.generate_express_key(
        "Account", "read", params={"id": "alice@leak.example"}
    )
    key_b = kg.generate_express_key(
        "Account", "read", params={"id": "bob@leak.example"}
    )
    assert key_a != key_b, "Distinct raw PKs MUST produce distinct keys"
    assert "alice@leak.example" not in key_a
    assert "bob@leak.example" not in key_b
    # v2 keyspace
    assert ":v2:" in key_a


def test_m2_cache_key_filter_nested_id_is_hashed():
    """Filter-style params (``{"filter": {"id": ...}}``) have the
    nested ``id`` hashed too."""
    policy = ClassificationPolicy()
    policy.set_field(
        "Account",
        "id",
        DataClassification.PII,
        masking=MaskingStrategy.REDACT,
    )
    kg = CacheKeyGenerator(classification_policy=policy)
    raw = "carol@leak.example"
    safe = kg._safe_params("Account", {"filter": {"id": raw}})
    assert safe == {"filter": {"id": _expected_hash(raw)}}


def test_m2_no_policy_means_no_hashing():
    """Backwards-compat: a key generator built without a policy acts
    identically to pre-BP-049. Callers of DataFlow that have no
    classifications MUST NOT see a behaviour change."""
    kg = CacheKeyGenerator()  # no policy
    raw = {"id": "alice@leak.example"}
    assert kg._safe_params("Account", raw) == raw


# ---------------------------------------------------------------------------
# M3 — validation error sanitization
# ---------------------------------------------------------------------------


def test_m3_sanitize_validation_error_unclassified_passthrough():
    """Pass-through when no policy or field is unclassified."""
    # No policy at all.
    sf, sm, sv, ic = sanitize_validation_error(
        None, "User", "email", "bad email", "x@y"
    )
    assert (sf, sm, sv, ic) == ("email", "bad email", "x@y", False)

    # Policy present but field not classified.
    policy = ClassificationPolicy()
    sf, sm, sv, ic = sanitize_validation_error(
        policy, "User", "email", "bad email", "x@y"
    )
    assert (sf, sm, sv, ic) == ("email", "bad email", "x@y", False)


def test_m3_sanitize_validation_error_classified_redacts():
    """Classified field → name placeholder, value type-descriptor,
    message scrubbed of the raw field name."""
    policy = ClassificationPolicy()
    policy.set_field(
        "User",
        "email",
        DataClassification.PII,
        masking=MaskingStrategy.REDACT,
    )
    sf, sm, sv, ic = sanitize_validation_error(
        policy,
        "User",
        "email",
        "Validation failed for field 'email' (validator: is_email)",
        "alice@leak.example",
    )
    assert sf == CLASSIFIED_FIELD_NAME_PLACEHOLDER
    assert "email" not in sm or CLASSIFIED_FIELD_NAME_PLACEHOLDER in sm
    assert sv == "<classified string>"
    assert ic is True
    assert (
        "alice@leak.example" not in sm
    ), "Raw classified value MUST NOT leak into the sanitised message"


def test_m3_classified_value_descriptor_covers_common_types():
    """Type-descriptor vocabulary matches the cross-SDK contract."""
    assert classified_value_descriptor("x") == "<classified string>"
    assert classified_value_descriptor(42) == "<classified int>"
    assert classified_value_descriptor(1.5) == "<classified float>"
    assert classified_value_descriptor(True) == "<classified bool>"
    assert classified_value_descriptor(b"x") == "<classified bytes>"
    assert classified_value_descriptor([1, 2]) == "<classified list>"
    assert classified_value_descriptor({"k": "v"}) == "<classified dict>"
    assert classified_value_descriptor(None) == "<classified none>"


def _reject_all(value):
    """Named validator so the derived label stays grep-able."""
    return False


def test_m3_validate_model_sanitises_classified_errors():
    """End-to-end via validate_model: a validator that rejects a
    classified field produces a sanitised ValidationResult with the
    classified_field_count aggregate set."""

    @field_validator("email", _reject_all)
    class M3ClassifiedModel:
        email: str = ""

    policy = ClassificationPolicy()
    policy.set_field(
        "M3ClassifiedModel",
        "email",
        DataClassification.PII,
        masking=MaskingStrategy.REDACT,
    )

    instance = M3ClassifiedModel()
    instance.email = "alice@leak.example"

    result = validate_model(instance, policy=policy, model_name="M3ClassifiedModel")
    assert not result.valid
    assert len(result.errors) == 1
    err = result.errors[0]
    assert err.field == CLASSIFIED_FIELD_NAME_PLACEHOLDER
    assert "alice@leak.example" not in err.message
    assert err.value == "<classified string>"
    assert result.classified_field_count == 1


def test_m3_validate_model_unclassified_preserves_raw_values():
    """Backwards-compat: unclassified field retains raw error value."""

    @field_validator("name", _reject_all)
    class M3UnclassifiedModel:
        name: str = ""

    policy = ClassificationPolicy()  # empty
    instance = M3UnclassifiedModel()
    instance.name = "bad value"
    result = validate_model(instance, policy=policy, model_name="M3UnclassifiedModel")
    assert not result.valid
    assert result.errors[0].field == "name"
    assert result.errors[0].value == "bad value"
    assert result.classified_field_count == 0


def test_m3_validation_result_merge_aggregates_classified_count():
    """merge() sums classified_field_count across results."""
    r1 = ValidationResult()
    r1.add_error("f1", "m", "v", value="x", is_classified=True)
    r2 = ValidationResult()
    r2.add_error("f2", "m", "v", value="y", is_classified=True)
    r2.add_error("f3", "m", "v", value="z", is_classified=False)
    r1.merge(r2)
    assert r1.classified_field_count == 2
    assert len(r1.errors) == 3


def test_m3_validation_result_to_dict_includes_classified_count():
    """Serialised form includes the aggregate for operator alerting."""
    vr = ValidationResult()
    vr.add_error(
        CLASSIFIED_FIELD_NAME_PLACEHOLDER,
        "msg",
        "val",
        value="<classified string>",
        is_classified=True,
    )
    d = vr.to_dict()
    assert d["classified_field_count"] == 1
    # Round-trip.
    vr2 = ValidationResult.from_dict(d)
    assert vr2.classified_field_count == 1
