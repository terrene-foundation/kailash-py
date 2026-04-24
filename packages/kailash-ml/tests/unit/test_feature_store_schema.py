# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier-1 unit tests: FeatureSchema + FeatureField invariants.

Covers schema versioning, dtype allowlist, identifier validation, and
content-hash determinism. No DB / no polars execution — this is pure
value-object behaviour.
"""
from __future__ import annotations

import pytest

from kailash_ml.features import FeatureField, FeatureSchema


# ---------------------------------------------------------------------------
# FeatureField
# ---------------------------------------------------------------------------


def test_feature_field_construct_minimal() -> None:
    f = FeatureField(name="age", dtype="float64")
    assert f.name == "age"
    assert f.dtype == "float64"
    assert f.nullable is True
    assert f.description == ""


@pytest.mark.parametrize(
    "synonym,canonical",
    [
        ("float", "float64"),
        ("FLOAT", "float64"),
        ("double", "float64"),
        ("int", "int64"),
        ("str", "utf8"),
        ("text", "utf8"),
        ("string", "utf8"),
        ("boolean", "bool"),
    ],
)
def test_feature_field_dtype_synonyms_normalise(synonym: str, canonical: str) -> None:
    f = FeatureField(name="x", dtype=synonym)
    assert f.dtype == canonical


def test_feature_field_dtype_disallowed_raises() -> None:
    with pytest.raises(ValueError, match="polars-native dtype"):
        FeatureField(name="x", dtype="complex128")


def test_feature_field_dtype_non_string_raises() -> None:
    with pytest.raises(TypeError, match="must be a string"):
        FeatureField(name="x", dtype=42)  # type: ignore[arg-type]


def test_feature_field_name_invalid_raises() -> None:
    with pytest.raises(ValueError, match=r"\^\[a-zA-Z_\]"):
        FeatureField(name="1abc", dtype="float64")


def test_feature_field_name_injection_not_echoed() -> None:
    # The raw name must never appear in the error message (fingerprint only).
    try:
        FeatureField(name="'; DROP TABLE x; --", dtype="float64")
    except ValueError as e:
        assert "DROP TABLE" not in str(e)
        assert "fingerprint=" in str(e)
    else:
        raise AssertionError("expected ValueError")


def test_feature_field_frozen() -> None:
    f = FeatureField(name="age", dtype="int64")
    with pytest.raises(Exception):  # FrozenInstanceError
        f.name = "other"  # type: ignore[misc]


def test_feature_field_roundtrip_dict() -> None:
    f = FeatureField(name="age", dtype="float64", nullable=False, description="d")
    d = f.to_dict()
    assert d == {
        "name": "age",
        "dtype": "float64",
        "nullable": False,
        "description": "d",
    }
    assert FeatureField.from_dict(d) == f


# ---------------------------------------------------------------------------
# FeatureSchema — construction
# ---------------------------------------------------------------------------


def _mk_fields() -> tuple[FeatureField, ...]:
    return (
        FeatureField(name="age", dtype="float64"),
        FeatureField(name="tenure", dtype="int64"),
    )


def test_feature_schema_minimal() -> None:
    s = FeatureSchema(name="u", fields=_mk_fields())
    assert s.name == "u"
    assert s.version == 1
    assert s.entity_id_column == "entity_id"
    assert s.timestamp_column is None
    assert s.field_names == ["age", "tenure"]
    assert len(s.content_hash) == 16  # sha256 truncated to 16 hex


def test_feature_schema_accepts_list_of_fields() -> None:
    # list input is normalised to tuple.
    s = FeatureSchema(name="u", fields=list(_mk_fields()))
    assert isinstance(s.fields, tuple)


def test_feature_schema_requires_fields() -> None:
    with pytest.raises(ValueError, match="at least one field"):
        FeatureSchema(name="u", fields=())


def test_feature_schema_rejects_duplicate_field_names() -> None:
    with pytest.raises(ValueError, match="duplicate field name"):
        FeatureSchema(
            name="u",
            fields=(
                FeatureField(name="age", dtype="float64"),
                FeatureField(name="age", dtype="int64"),
            ),
        )


def test_feature_schema_version_must_be_int() -> None:
    with pytest.raises(TypeError, match="must be int"):
        FeatureSchema(name="u", version="1", fields=_mk_fields())  # type: ignore[arg-type]


def test_feature_schema_version_rejects_bool() -> None:
    # bool is subclass of int; reject at the type gate.
    with pytest.raises(TypeError, match="must be int"):
        FeatureSchema(name="u", version=True, fields=_mk_fields())  # type: ignore[arg-type]


def test_feature_schema_version_must_be_positive() -> None:
    with pytest.raises(ValueError, match=">= 1"):
        FeatureSchema(name="u", version=0, fields=_mk_fields())


def test_feature_schema_name_invalid_raises() -> None:
    with pytest.raises(ValueError, match="^FeatureSchema.name"):
        FeatureSchema(name="1bad", fields=_mk_fields())


def test_feature_schema_entity_id_column_invalid_raises() -> None:
    with pytest.raises(ValueError, match="FeatureSchema.entity_id_column"):
        FeatureSchema(
            name="u",
            fields=_mk_fields(),
            entity_id_column="1bad",
        )


def test_feature_schema_timestamp_column_invalid_raises() -> None:
    with pytest.raises(ValueError, match="FeatureSchema.timestamp_column"):
        FeatureSchema(
            name="u",
            fields=_mk_fields(),
            timestamp_column="1bad",
        )


# ---------------------------------------------------------------------------
# FeatureSchema — content hash determinism + version bump semantics
# ---------------------------------------------------------------------------


def test_content_hash_identical_for_same_spec() -> None:
    s1 = FeatureSchema(name="u", fields=_mk_fields())
    s2 = FeatureSchema(name="u", fields=_mk_fields())
    assert s1.content_hash == s2.content_hash


def test_content_hash_differs_on_version_bump() -> None:
    s1 = FeatureSchema(name="u", version=1, fields=_mk_fields())
    s2 = FeatureSchema(name="u", version=2, fields=_mk_fields())
    assert s1.content_hash != s2.content_hash


def test_content_hash_differs_on_field_addition() -> None:
    s1 = FeatureSchema(name="u", fields=_mk_fields())
    s2 = FeatureSchema(
        name="u",
        fields=_mk_fields() + (FeatureField(name="score", dtype="float64"),),
    )
    assert s1.content_hash != s2.content_hash


def test_content_hash_stable_across_equivalent_dtype_strings() -> None:
    # Synonyms normalise, so hashes must match.
    s1 = FeatureSchema(name="u", fields=(FeatureField(name="v", dtype="float"),))
    s2 = FeatureSchema(name="u", fields=(FeatureField(name="v", dtype="float64"),))
    assert s1.content_hash == s2.content_hash


def test_content_hash_differs_on_dtype_change() -> None:
    s1 = FeatureSchema(name="u", fields=(FeatureField(name="v", dtype="float64"),))
    s2 = FeatureSchema(name="u", fields=(FeatureField(name="v", dtype="int64"),))
    assert s1.content_hash != s2.content_hash


def test_feature_schema_roundtrip_dict() -> None:
    s = FeatureSchema(
        name="u",
        version=3,
        fields=_mk_fields(),
        entity_id_column="user_id",
        timestamp_column="event_time",
    )
    restored = FeatureSchema.from_dict(s.to_dict())
    assert restored.name == s.name
    assert restored.version == s.version
    assert restored.fields == s.fields
    assert restored.entity_id_column == s.entity_id_column
    assert restored.timestamp_column == s.timestamp_column
    assert restored.content_hash == s.content_hash


def test_feature_schema_frozen() -> None:
    s = FeatureSchema(name="u", fields=_mk_fields())
    with pytest.raises(Exception):  # FrozenInstanceError
        s.version = 9  # type: ignore[misc]
