# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier 1 tests for the PACT N4/N5 conformance vector loader + schema.

These tests pin the loader contract:

- A well-formed N4 vector (with ``posture``) parses end-to-end.
- A well-formed N5 vector (with ``evidence_source``) parses end-to-end.
- Schema violations raise :class:`ConformanceVectorError` with informative
  messages.
- Duplicate vector IDs across files raise.
- Missing or non-directory paths raise.
- The loader returns vectors deterministically sorted by ``id``.
- ``TieredAuditEvent.canonical_json`` and ``Evidence.canonical_json`` emit
  the expected byte string for synthetic inputs whose canonical form we
  hand-derived (the runner exercises the real cross-SDK vectors in Shard B).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pact.conformance import (
    ConformanceVector,
    ConformanceVectorError,
    DurabilityTier,
    Evidence,
    GradientZone,
    PactPostureLevel,
    TieredAuditEvent,
    canonical_json_dumps,
    durability_tier_from_posture,
    load_vectors_from_dir,
    parse_vector,
)

# ---------------------------------------------------------------------------
# Synthetic vector fixtures
# ---------------------------------------------------------------------------


def _n4_vector_dict(
    *,
    vector_id: str = "synth_n4_zone1",
    posture: str = "PseudoAgent",
    expected_canonical_json: str | None = None,
) -> dict:
    canonical = expected_canonical_json or (
        '{"event_id":"00000000-0000-4000-8000-000000000001",'
        '"timestamp":"2026-01-01T00:00:00+00:00",'
        '"role_address":"D1-R1","posture":"pseudo_agent",'
        '"action":"ping","zone":"AutoApproved","reason":"ok",'
        '"tier":"zone1_pseudo","tenant_id":null,"signature":null}'
    )
    return {
        "id": vector_id,
        "contract": "N4",
        "description": "synthetic Zone 1 N4 vector",
        "input": {
            "verdict": {
                "zone": "AutoApproved",
                "reason": "ok",
                "action": "ping",
                "role_address": "D1-R1",
                "details": {},
            },
            "posture": posture,
            "fixed_event_id": "00000000-0000-4000-8000-000000000001",
            "fixed_timestamp": "2026-01-01T00:00:00+00:00",
        },
        "expected": {
            "tier": "zone1_pseudo",
            "durable": False,
            "requires_signature": False,
            "requires_replication": False,
            "canonical_json": canonical,
        },
        "hash_algo": "sha256",
    }


def _n5_vector_dict(*, vector_id: str = "synth_n5_blocked") -> dict:
    canonical = (
        '{"schema":"pact.governance.verdict.v1","source":"D1-R1-T1-R1",'
        '"timestamp":"2026-01-01T00:00:00+00:00","gradient":"Blocked",'
        '"action":"wire_transfer","payload":{"details":{},'
        '"reason":"exceeded financial limit",'
        '"role_address":"D1-R1-T1-R1"}}'
    )
    return {
        "id": vector_id,
        "contract": "N5",
        "description": "synthetic blocked-evidence vector",
        "input": {
            "verdict": {
                "zone": "Blocked",
                "reason": "exceeded financial limit",
                "action": "wire_transfer",
                "role_address": "D1-R1-T1-R1",
                "details": {},
            },
            "fixed_timestamp": "2026-01-01T00:00:00+00:00",
            "evidence_source": "D1-R1-T1-R1",
        },
        "expected": {"canonical_json": canonical},
        "hash_algo": "sha256",
    }


# ---------------------------------------------------------------------------
# parse_vector — happy path
# ---------------------------------------------------------------------------


def test_parse_vector_n4_minimal():
    vector = parse_vector(_n4_vector_dict())
    assert isinstance(vector, ConformanceVector)
    assert vector.id == "synth_n4_zone1"
    assert vector.contract == "N4"
    assert vector.input.posture is PactPostureLevel.PSEUDO_AGENT
    assert vector.input.verdict.zone is GradientZone.AUTO_APPROVED
    assert vector.expected.tier is DurabilityTier.ZONE1_PSEUDO
    assert vector.expected.durable is False
    assert vector.expected.requires_signature is False
    assert vector.expected.requires_replication is False
    assert vector.hash_algo == "sha256"


def test_parse_vector_n5_minimal():
    vector = parse_vector(_n5_vector_dict())
    assert vector.contract == "N5"
    assert vector.input.posture is None
    assert vector.input.evidence_source == "D1-R1-T1-R1"
    assert vector.input.verdict.zone is GradientZone.BLOCKED
    assert vector.expected.tier is None  # N5 has no tier
    assert "Blocked" in vector.expected.canonical_json


def test_parse_vector_n4_continuous_insight_maps_to_zone3():
    """ContinuousInsight + SharedPlanning both map to Zone3 (cross-SDK invariant)."""
    raw = _n4_vector_dict(
        vector_id="synth_n4_zone3_ci",
        posture="ContinuousInsight",
        expected_canonical_json=(
            '{"event_id":"00000000-0000-4000-8000-000000000001",'
            '"timestamp":"2026-01-01T00:00:00+00:00",'
            '"role_address":"D1-R1","posture":"continuous_insight",'
            '"action":"ping","zone":"AutoApproved","reason":"ok",'
            '"tier":"zone3_cognate","tenant_id":null,"signature":null}'
        ),
    )
    raw["expected"]["tier"] = "zone3_cognate"
    raw["expected"]["durable"] = True
    raw["expected"]["requires_signature"] = False
    raw["expected"]["requires_replication"] = True
    vector = parse_vector(raw)
    assert vector.input.posture is PactPostureLevel.CONTINUOUS_INSIGHT
    tier = durability_tier_from_posture(vector.input.posture)
    assert tier is DurabilityTier.ZONE3_COGNATE
    assert tier.is_durable() is True
    assert tier.requires_signature() is False
    assert tier.requires_replication() is True


# ---------------------------------------------------------------------------
# parse_vector — schema violations
# ---------------------------------------------------------------------------


def test_parse_vector_rejects_unknown_contract():
    raw = _n4_vector_dict()
    raw["contract"] = "N99"
    with pytest.raises(ConformanceVectorError, match="contract MUST be 'N4' or 'N5'"):
        parse_vector(raw)


def test_parse_vector_rejects_n4_without_posture():
    raw = _n4_vector_dict()
    raw["input"].pop("posture")
    with pytest.raises(
        ConformanceVectorError, match="N4 contract requires input.posture"
    ):
        parse_vector(raw)


def test_parse_vector_rejects_missing_canonical_json():
    raw = _n4_vector_dict()
    raw["expected"].pop("canonical_json")
    with pytest.raises(ConformanceVectorError, match="canonical_json"):
        parse_vector(raw)


def test_parse_vector_rejects_unknown_zone():
    raw = _n4_vector_dict()
    raw["input"]["verdict"]["zone"] = "Sideways"
    with pytest.raises(ConformanceVectorError, match="unknown GradientZone"):
        parse_vector(raw)


def test_parse_vector_rejects_unknown_posture():
    raw = _n4_vector_dict()
    raw["input"]["posture"] = "Hyperdelegated"
    with pytest.raises(ConformanceVectorError, match="unknown PactPostureLevel"):
        parse_vector(raw)


def test_parse_vector_rejects_unknown_durability_tier():
    raw = _n4_vector_dict()
    raw["expected"]["tier"] = "zone99_yolo"
    with pytest.raises(ConformanceVectorError, match="unknown DurabilityTier"):
        parse_vector(raw)


def test_parse_vector_rejects_non_string_id():
    raw = _n4_vector_dict()
    raw["id"] = 42
    with pytest.raises(ConformanceVectorError, match="id MUST be a string"):
        parse_vector(raw)


def test_parse_vector_rejects_top_level_non_object():
    with pytest.raises(ConformanceVectorError, match="top-level MUST be an object"):
        parse_vector("not a dict")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# load_vectors_from_dir
# ---------------------------------------------------------------------------


def test_load_vectors_from_dir_happy_path(tmp_path: Path) -> None:
    n4 = _n4_vector_dict(vector_id="b_n4")
    n5 = _n5_vector_dict(vector_id="a_n5")
    (tmp_path / "b.json").write_text(json.dumps(n4), encoding="utf-8")
    (tmp_path / "a.json").write_text(json.dumps(n5), encoding="utf-8")

    vectors = load_vectors_from_dir(tmp_path)
    # Sorted by id (a_n5 < b_n4)
    assert [v.id for v in vectors] == ["a_n5", "b_n4"]
    # source_path propagated
    assert vectors[0].source_path == tmp_path / "a.json"
    assert vectors[1].source_path == tmp_path / "b.json"


def test_load_vectors_from_dir_skips_non_json(tmp_path: Path) -> None:
    (tmp_path / "vector.json").write_text(
        json.dumps(_n4_vector_dict()), encoding="utf-8"
    )
    (tmp_path / "README.md").write_text("not a vector", encoding="utf-8")
    (tmp_path / "vector.json.bak").write_text("not loaded", encoding="utf-8")
    vectors = load_vectors_from_dir(tmp_path)
    assert len(vectors) == 1


def test_load_vectors_from_dir_rejects_duplicate_ids(tmp_path: Path) -> None:
    (tmp_path / "one.json").write_text(json.dumps(_n4_vector_dict()), encoding="utf-8")
    (tmp_path / "two.json").write_text(json.dumps(_n4_vector_dict()), encoding="utf-8")
    with pytest.raises(ConformanceVectorError, match="duplicate vector id"):
        load_vectors_from_dir(tmp_path)


def test_load_vectors_from_dir_rejects_missing_dir(tmp_path: Path) -> None:
    missing = tmp_path / "does_not_exist"
    with pytest.raises(ConformanceVectorError, match="does not exist"):
        load_vectors_from_dir(missing)


def test_load_vectors_from_dir_rejects_non_directory(tmp_path: Path) -> None:
    file_path = tmp_path / "file.json"
    file_path.write_text("{}", encoding="utf-8")
    with pytest.raises(ConformanceVectorError, match="not a directory"):
        load_vectors_from_dir(file_path)


def test_load_vectors_from_dir_empty_returns_empty(tmp_path: Path) -> None:
    assert load_vectors_from_dir(tmp_path) == []


def test_load_vectors_from_dir_rejects_malformed_json(tmp_path: Path) -> None:
    (tmp_path / "bad.json").write_text("{not: valid json", encoding="utf-8")
    with pytest.raises(ConformanceVectorError, match="failed to decode JSON"):
        load_vectors_from_dir(tmp_path)


# ---------------------------------------------------------------------------
# TieredAuditEvent.canonical_json — byte equality vs hand-derived shape
# ---------------------------------------------------------------------------


def test_tiered_audit_event_canonical_json_zone1():
    """The synthetic Zone 1 vector's canonical_json matches the
    TieredAuditEvent canonicalisation byte-for-byte. This pins the field
    declaration order (event_id, timestamp, role_address, posture, action,
    zone, reason, tier, tenant_id, signature) and the exact serde output
    shape for null tenant_id / signature."""
    vector = parse_vector(_n4_vector_dict())
    assert vector.input.posture is not None  # narrowed for typecheck
    event = TieredAuditEvent.from_verdict(
        vector.input.verdict,
        vector.input.posture,
        event_id=vector.input.fixed_event_id or "",
        timestamp=vector.input.fixed_timestamp or "",
    )
    actual = event.canonical_json()
    assert actual == vector.expected.canonical_json


def test_tiered_audit_event_canonical_json_delegated_zone4():
    """Delegated -> zone4_delegated; tier maps correctly and the canonical
    JSON pins ``"tier":"zone4_delegated"``."""
    expected = (
        '{"event_id":"00000000-0000-4000-8000-000000000001",'
        '"timestamp":"2026-01-01T00:00:00+00:00",'
        '"role_address":"D1-R1","posture":"delegated",'
        '"action":"ping","zone":"AutoApproved","reason":"ok",'
        '"tier":"zone4_delegated","tenant_id":null,"signature":null}'
    )
    raw = _n4_vector_dict(
        vector_id="synth_n4_z4",
        posture="Delegated",
        expected_canonical_json=expected,
    )
    raw["expected"]["tier"] = "zone4_delegated"
    raw["expected"]["durable"] = True
    raw["expected"]["requires_signature"] = True
    raw["expected"]["requires_replication"] = True
    vector = parse_vector(raw)
    event = TieredAuditEvent.from_verdict(
        vector.input.verdict,
        vector.input.posture,
        event_id=vector.input.fixed_event_id or "",
        timestamp=vector.input.fixed_timestamp or "",
    )
    assert event.canonical_json() == vector.expected.canonical_json


# ---------------------------------------------------------------------------
# Evidence.canonical_json — byte equality vs hand-derived shape
# ---------------------------------------------------------------------------


def test_evidence_canonical_json_blocked():
    """The synthetic blocked-evidence vector's canonical_json matches the
    Evidence canonicalisation byte-for-byte. Pins the top-level order
    (schema, source, timestamp, gradient, action, payload) and the payload
    sub-object order (details, reason, role_address)."""
    vector = parse_vector(_n5_vector_dict())
    evidence = Evidence.from_verdict(
        vector.input.verdict,
        source=vector.input.evidence_source or "",
        timestamp=vector.input.fixed_timestamp or "",
    )
    assert evidence.canonical_json() == vector.expected.canonical_json


def test_evidence_with_schema_override_changes_output():
    vector = parse_vector(_n5_vector_dict())
    evidence = Evidence.from_verdict(
        vector.input.verdict,
        source=vector.input.evidence_source or "",
        timestamp=vector.input.fixed_timestamp or "",
    ).with_schema("pact.governance.custom.v1")
    actual = evidence.canonical_json()
    assert actual.startswith('{"schema":"pact.governance.custom.v1"')


# ---------------------------------------------------------------------------
# DurabilityTier semantic invariants (mirrors Rust ``zone1_not_durable_zone4_signed``)
# ---------------------------------------------------------------------------


def test_durability_tier_invariants():
    assert DurabilityTier.ZONE1_PSEUDO.is_durable() is False
    assert DurabilityTier.ZONE2_GUARDIAN.is_durable() is True
    assert DurabilityTier.ZONE3_COGNATE.is_durable() is True
    assert DurabilityTier.ZONE4_DELEGATED.is_durable() is True

    assert DurabilityTier.ZONE1_PSEUDO.requires_signature() is False
    assert DurabilityTier.ZONE2_GUARDIAN.requires_signature() is False
    assert DurabilityTier.ZONE3_COGNATE.requires_signature() is False
    assert DurabilityTier.ZONE4_DELEGATED.requires_signature() is True

    assert DurabilityTier.ZONE1_PSEUDO.requires_replication() is False
    assert DurabilityTier.ZONE2_GUARDIAN.requires_replication() is False
    assert DurabilityTier.ZONE3_COGNATE.requires_replication() is True
    assert DurabilityTier.ZONE4_DELEGATED.requires_replication() is True


def test_durability_tier_from_posture_table():
    """Mirrors Rust ``DurabilityTier::from_posture`` exactly."""
    table = {
        PactPostureLevel.PSEUDO_AGENT: DurabilityTier.ZONE1_PSEUDO,
        PactPostureLevel.SUPERVISED: DurabilityTier.ZONE2_GUARDIAN,
        PactPostureLevel.SHARED_PLANNING: DurabilityTier.ZONE3_COGNATE,
        PactPostureLevel.CONTINUOUS_INSIGHT: DurabilityTier.ZONE3_COGNATE,
        PactPostureLevel.DELEGATED: DurabilityTier.ZONE4_DELEGATED,
    }
    for posture, expected_tier in table.items():
        assert durability_tier_from_posture(posture) is expected_tier


# ---------------------------------------------------------------------------
# canonical_json_dumps — shape invariants
# ---------------------------------------------------------------------------


def test_canonical_json_dumps_no_whitespace():
    encoded = canonical_json_dumps({"a": 1, "b": [2, 3]})
    assert " " not in encoded
    assert encoded == '{"a":1,"b":[2,3]}'


def test_canonical_json_dumps_preserves_insertion_order():
    encoded = canonical_json_dumps({"z": 1, "a": 2})
    # Insertion order, NOT sorted -- struct field declaration order wins.
    assert encoded == '{"z":1,"a":2}'
