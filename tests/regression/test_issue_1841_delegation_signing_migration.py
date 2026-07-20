# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Regression tests for #1841 shard 2 — DelegationRecord signing version gate.

Covers the additive + version-gate migration that puts the delegation
sign/verify path behind a ``signing_payload_version`` discriminator while
keeping every existing (pre-migration) record verifying byte-identically:

* backward-compat — a delegation signed the pre-migration way still verifies
  through the migrated dispatch, AND a record deserialized from a wire form with
  NO ``signing_payload_version`` key verifies unchanged;
* byte-identity — the shared dispatch emits the SAME bytes the pre-migration
  ``serialize_for_signing(to_signing_payload())`` did for a legacy record (the
  migration changes zero legacy signing bytes);
* fail-closed — a record declaring a non-legacy version fails closed at verify
  rather than falling through to the legacy verifier;
* the engine-mapping bridge — byte-exact v2/v3 engine pre-images + its
  fail-closed guards (missing structured data, narrowed dimension_scope).

Real Ed25519 crypto throughout (Tier 2 — no mocking).
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from kailash.trust.chain import (
    DELEGATION_SIGNING_VERSION_LEGACY,
    DELEGATION_SIGNING_VERSION_V2,
    DELEGATION_SIGNING_VERSION_V3,
    DelegationRecord,
)
from kailash.trust.exceptions import UnsupportedSigningPayloadVersionError
from kailash.trust.signing import (
    ConstraintDimensions,
    DelegationScope,
    DelegationSigningInput,
    MultiSigSigningPolicy,
    ResourceLimits,
    SigningPayloadVersion,
    TrustLevel,
    build_delegation_signing_input,
    delegation_canonical_payload_str,
    delegation_record_signing_payload,
    delegation_signing_payload,
)
from kailash.trust.signing.crypto import (
    generate_keypair,
    serialize_for_signing,
    sign,
    verify_signature,
)

pytestmark = pytest.mark.regression


def _record(**overrides) -> DelegationRecord:
    base = dict(
        id="del-1841",
        delegator_id="alice",
        delegatee_id="bob",
        task_id="task-1",
        capabilities_delegated=["read"],
        constraint_subset=[],
        delegated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        signature="",
    )
    base.update(overrides)
    return DelegationRecord(**base)


# --------------------------------------------------------------------------- #
# Field default + serde backward-compat                                       #
# --------------------------------------------------------------------------- #


def test_new_record_defaults_to_legacy_version():
    """A freshly-constructed record signs under the pre-migration schema."""
    assert _record().signing_payload_version == DELEGATION_SIGNING_VERSION_LEGACY


def test_from_dict_missing_version_key_defaults_legacy():
    """A pre-migration wire form (no version key) deserializes to legacy."""
    d = _record().to_dict()
    assert d["signing_payload_version"] == DELEGATION_SIGNING_VERSION_LEGACY
    # Simulate a record serialized BEFORE the field existed.
    del d["signing_payload_version"]
    restored = DelegationRecord.from_dict(d)
    assert restored.signing_payload_version == DELEGATION_SIGNING_VERSION_LEGACY


def test_to_dict_from_dict_roundtrips_version():
    d = _record(signing_payload_version=DELEGATION_SIGNING_VERSION_V2).to_dict()
    assert DelegationRecord.from_dict(d).signing_payload_version == (
        DELEGATION_SIGNING_VERSION_V2
    )


# --------------------------------------------------------------------------- #
# Byte-identity: the migration changes zero legacy signing bytes              #
# --------------------------------------------------------------------------- #


def test_legacy_dispatch_byte_identical_to_pre_migration():
    """The shared dispatch emits exactly the pre-migration legacy pre-image."""
    record = _record()
    # The pre-migration signing site did precisely this.
    pre_migration = serialize_for_signing(record.to_signing_payload())
    assert delegation_canonical_payload_str(record) == pre_migration


def test_signing_payload_version_not_in_legacy_preimage():
    """The discriminator MUST NOT enter the legacy signed bytes (byte-compat)."""
    record = _record()
    assert "signing_payload_version" not in record.to_signing_payload()
    assert "signing_payload_version" not in delegation_canonical_payload_str(record)


# --------------------------------------------------------------------------- #
# Backward-compat: existing legacy record still verifies (real crypto)        #
# --------------------------------------------------------------------------- #


def test_existing_legacy_record_still_verifies():
    """A delegation signed the pre-migration way verifies via the migrated path."""
    private_key, public_key = generate_keypair()
    record = _record()

    # Sign the pre-migration way (what a record already on disk carries).
    legacy_payload = serialize_for_signing(record.to_signing_payload())
    record.signature = sign(legacy_payload, private_key)

    # Verify through the migrated dispatch — MUST succeed byte-identically.
    verify_payload = delegation_canonical_payload_str(record)
    assert verify_signature(verify_payload, record.signature, public_key) is True


def test_record_deserialized_without_version_key_still_verifies():
    """A record persisted before the field existed round-trips + verifies."""
    private_key, public_key = generate_keypair()
    record = _record()
    record.signature = sign(
        serialize_for_signing(record.to_signing_payload()), private_key
    )

    # Round-trip through a wire form that predates the version field.
    wire = record.to_dict()
    del wire["signing_payload_version"]
    restored = DelegationRecord.from_dict(wire)

    assert restored.signing_payload_version == DELEGATION_SIGNING_VERSION_LEGACY
    assert (
        verify_signature(
            delegation_canonical_payload_str(restored),
            restored.signature,
            public_key,
        )
        is True
    )


# --------------------------------------------------------------------------- #
# Fail-closed: a non-legacy version does NOT fall through to the legacy path  #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    # v2-complete (S2b-1) and v3-complete (S2b-2, multi-sig) are BOTH WIRED (see
    # the v2/v3 tests below + tests/regression/test_issue_1841_s2b2_v3_*.py). Only
    # a genuinely UNRECOGNISED version still fails closed with
    # UnsupportedSigningPayloadVersionError at dispatch.
    "version",
    ["future-vX", "v9-bogus"],
)
def test_non_legacy_version_fails_closed_at_dispatch(version):
    record = _record(signing_payload_version=version)
    with pytest.raises(UnsupportedSigningPayloadVersionError) as exc:
        delegation_canonical_payload_str(record)
    assert exc.value.version == version
    assert exc.value.record_id == "del-1841"


def test_v2_labeled_record_without_structured_fields_fails_closed():
    """A v2-labeled record lacking the structured fold fields fails closed.

    #1841 S2b-1 wires v2, but the engine bridge REQUIRES the structured
    constraints / resource_limits / scope. A record stamped v2 without them is an
    inconsistent state (select_signing_version never produces it) and MUST fail
    closed at the bridge rather than emit guessed bytes — never fall through to
    legacy.
    """
    record = _record(signing_payload_version=DELEGATION_SIGNING_VERSION_V2)
    with pytest.raises(ValueError, match="constraints"):
        delegation_canonical_payload_str(record)


def test_v3_labeled_record_without_structured_fields_fails_closed():
    """A v3-labeled record lacking the structured fold fields fails closed.

    #1841 S2b-2 wires v3, but the engine bridge REQUIRES the structured
    constraints / resource_limits / scope (AND a multi_sig policy). A record
    stamped v3 without them is an inconsistent state (select_signing_version
    never produces it) and MUST fail closed at the bridge (ValueError) rather
    than emit guessed bytes — never fall through to legacy. Swept from the former
    v3-unwired deferral assertion per orphan-detection.md Rule 4a.
    """
    record = _record(signing_payload_version=DELEGATION_SIGNING_VERSION_V3)
    with pytest.raises(ValueError, match="constraints"):
        delegation_canonical_payload_str(record)


def test_non_legacy_record_does_not_verify_under_legacy_bytes():
    """A v2 record signed over LEGACY bytes MUST fail verification.

    Core security property (now testable with v2 wired, #1841 S2b-1): a record
    whose declared shape (v2, carrying structured fields) differs from the bytes
    a naive legacy signer produced can never verify — the version gate emits the
    v2 pre-image, which does not match a legacy-bytes signature.
    """
    private_key, public_key = generate_keypair()
    constraints, limits, scope = _supervised_structured()
    record = _record(
        constraints=constraints,
        resource_limits=limits,
        scope=scope,
        signing_payload_version=DELEGATION_SIGNING_VERSION_V2,
    )
    # Attacker/legacy signs over the LEGACY bytes but the record is a v2 record.
    record.signature = sign(
        serialize_for_signing(record.to_signing_payload()), private_key
    )

    # The dispatch emits the v2 pre-image (≠ the signed legacy bytes) → verify fails.
    v2_payload = delegation_canonical_payload_str(record)
    assert verify_signature(v2_payload, record.signature, public_key) is False


# --------------------------------------------------------------------------- #
# Engine-mapping bridge — byte-exact v2/v3 + fail-closed guards               #
# --------------------------------------------------------------------------- #


def _supervised_structured():
    return (
        ConstraintDimensions.for_level(TrustLevel.SUPERVISED),
        ResourceLimits.for_level(TrustLevel.SUPERVISED),
        DelegationScope.new("engineering").with_operation("read"),
    )


def test_bridge_v2_byte_exact_against_direct_engine():
    """The bridge's v2 pre-image equals the direct engine pre-image."""
    record = _record()
    constraints, limits, scope = _supervised_structured()

    via_bridge = delegation_record_signing_payload(
        record,
        SigningPayloadVersion.V2_COMPLETE,
        constraints=constraints,
        resource_limits=limits,
        scope=scope,
    )
    via_engine = delegation_signing_payload(
        DelegationSigningInput(
            delegation_id=record.id,
            delegator=record.delegator_id,
            delegate=record.delegatee_id,
            capabilities=tuple(record.capabilities_delegated),
            created_at=record.delegated_at,
            constraints=constraints,
            resource_limits=limits,
            scope=scope,
            expires_at=record.expires_at,
            parent_delegation_id=record.parent_delegation_id,
        ),
        SigningPayloadVersion.V2_COMPLETE,
    )
    assert via_bridge == via_engine


def test_bridge_v3_folds_multisig_policy():
    record = _record()
    constraints, limits, scope = _supervised_structured()
    policy = MultiSigSigningPolicy.new(2, [b"\x01" * 32, b"\x02" * 32])

    payload = delegation_record_signing_payload(
        record,
        SigningPayloadVersion.V3_COMPLETE,
        constraints=constraints,
        resource_limits=limits,
        scope=scope,
        multi_sig=True,
        multi_sig_policy=policy,
    )
    assert b"multi_sig_threshold" in payload
    assert b"multi_sig_authorized_signers" in payload


@pytest.mark.parametrize("missing", ["constraints", "resource_limits", "scope"])
def test_bridge_fails_closed_on_missing_structured_field(missing):
    record = _record()
    constraints, limits, scope = _supervised_structured()
    kwargs = {"constraints": constraints, "resource_limits": limits, "scope": scope}
    kwargs[missing] = None
    with pytest.raises(ValueError, match=missing):
        build_delegation_signing_input(record, **kwargs)


def test_bridge_fails_closed_on_narrowed_dimension_scope():
    """A scoped record MUST NOT sign under v2/v3 (its scope binding is un-pinned)."""
    record = _record(dimension_scope=frozenset({"financial"}))
    constraints, limits, scope = _supervised_structured()
    with pytest.raises(ValueError, match="dimension_scope"):
        delegation_record_signing_payload(
            record,
            SigningPayloadVersion.V2_COMPLETE,
            constraints=constraints,
            resource_limits=limits,
            scope=scope,
        )
