# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""EATP v3 additive-element (#1592) conformance + invariant suite.

Byte-pins the five EATP v3 additive elements against committed vectors and
exercises each element's load-bearing invariants:

* **BilateralDelegation** -- atomic validity (both anchors present or invalid);
  SINGLE-ROOT only (cross-root federation OUT OF SCOPE, terrene#35 G1);
  dispatcher signatures are provenance-only and NEVER non-repudiation.
* **Guarantee-tier taxonomy** -- recorded-by-intermediary / conformant /
  complete-witnessed.
* **ClearanceAttestation** -- posture-gated re-identification; reuses the shared
  ConfidentialityLevel C0..C4 ordinal (the inverted-pair pin: restricted=C1,
  confidential=C2).
* **VERIFY_CHAIN** -- deny-overrides composition (any deny denies the whole;
  empty chain fails closed).
* **GRACEFUL / SUSPEND revocation modes** -- graceful grace-window drain;
  suspend reversible hold.

The same vectors are validated by the Rust SDK for cross-implementation
conformance. ``encoding="utf-8"`` on EVERY vector read is LOAD-BEARING (issue
#1590 Windows-CI fix).
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any

import pytest

from kailash.trust import ConfidentialityLevel, TrustPosture
from kailash.trust.pact.attestation import (
    ClearanceAttestation,
    ReidentificationDeniedError,
    posture_can_reidentify,
)
from kailash.trust.pact.audit import SCHEMA_VERSION_V3
from kailash.trust.pact.bilateral import (
    AtomicValidityError,
    BilateralDelegation,
    CrossRootFederationError,
    GuaranteeTier,
    NonRepudiationClaimError,
    PartyAnchor,
    SignerKind,
    new_bilateral_delegation,
)
from kailash.trust.pact.verify_chain import (
    ChainLink,
    ChainVerdict,
    VerifyChainError,
    verify_chain,
)
from kailash.trust.revocation import (
    CascadeRevocationManager,
    InMemoryDelegationRegistry,
    InMemoryRevocationBroadcaster,
    IrreversibleRevocationError,
    RevocationError,
    RevocationEvent,
    RevocationMode,
    TrustRevocationList,
)

VECTORS_DIR = Path(__file__).parent / "vectors"

# BilateralDelegation vectors carry a citable canonical_json + content_hash.
BILATERAL_VECTORS = [
    "eatp3_bilateral_valid.json",
    "eatp3_bilateral_missing_anchor.json",
    "eatp3_bilateral_dispatcher_provenance.json",
    "eatp3_bilateral_witnessed.json",
]

# The full #1592 EATP-v3 vector family (for the integrity guard).
ALL_EATP3_VECTORS = [
    *BILATERAL_VECTORS,
    "eatp3_guarantee_tier_distinction.json",
    "eatp3_clearance_posture_gate.json",
    "eatp3_clearance_ordinal_inverted_pair.json",
    "eatp3_verify_chain_deny_overrides.json",
    "eatp3_verify_chain_all_allow.json",
    "eatp3_revocation_graceful.json",
    "eatp3_revocation_suspend.json",
]


def _load_vector(filename: str) -> dict[str, Any]:
    """Load a vector JSON file with an explicit utf-8 decode (issue #1590)."""
    with open(VECTORS_DIR / filename, encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# BilateralDelegation -- byte-pin + atomic validity + guarantee tier
# ---------------------------------------------------------------------------


class TestBilateralDelegationVectors:
    """Byte-pin BilateralDelegation serialization + behavior against vectors."""

    @pytest.mark.parametrize("vector_file", BILATERAL_VECTORS)
    def test_canonical_and_hash_match_vector(self, vector_file: str) -> None:
        vector = _load_vector(vector_file)
        delegation = BilateralDelegation.from_dict(vector["input"])

        assert delegation.canonical_json() == vector["expected_canonical_json"], (
            f"BilateralDelegation canonical JSON mismatch for {vector_file}.\n"
            f"Got:      {delegation.canonical_json()}\n"
            f"Expected: {vector['expected_canonical_json']}"
        )
        assert delegation.content_hash() == vector["expected_content_hash"]

    @pytest.mark.parametrize("vector_file", BILATERAL_VECTORS)
    def test_atomic_validity_and_tier_match_vector(self, vector_file: str) -> None:
        vector = _load_vector(vector_file)
        delegation = BilateralDelegation.from_dict(vector["input"])

        assert delegation.is_atomically_valid() == vector["expected_atomic_valid"]
        assert delegation.guarantee_tier().value == vector["expected_guarantee_tier"]
        assert (
            delegation.supports_non_repudiation()
            == vector["expected_supports_non_repudiation"]
        )

    @pytest.mark.parametrize("vector_file", BILATERAL_VECTORS)
    def test_roundtrip_byte_stable(self, vector_file: str) -> None:
        vector = _load_vector(vector_file)
        delegation = BilateralDelegation.from_dict(vector["input"])
        roundtripped = BilateralDelegation.from_dict(delegation.to_dict())
        assert roundtripped.to_dict() == delegation.to_dict()
        assert roundtripped.content_hash() == delegation.content_hash()

    def test_missing_anchor_is_not_atomically_valid(self) -> None:
        """A delegation missing either anchor is invalid (atomic) and asserts fail-closed."""
        vector = _load_vector("eatp3_bilateral_missing_anchor.json")
        delegation = BilateralDelegation.from_dict(vector["input"])
        assert not delegation.is_atomically_valid()
        with pytest.raises(AtomicValidityError) as exc:
            delegation.assert_atomic_validity()
        assert "delegate" in exc.value.details["missing"]

    def test_valid_delegation_passes_atomic_assert(self) -> None:
        vector = _load_vector("eatp3_bilateral_valid.json")
        delegation = BilateralDelegation.from_dict(vector["input"])
        delegation.assert_atomic_validity()  # must not raise
        assert delegation.guarantee_tier() is GuaranteeTier.CONFORMANT

    def test_content_hash_binds_both_anchors(self) -> None:
        """Mutating either party's anchor changes the citable content hash."""
        base = _load_vector("eatp3_bilateral_valid.json")["input"]
        original = BilateralDelegation.from_dict(base)
        mutated = dict(base)
        mutated["delegate"] = dict(base["delegate"])
        mutated["delegate"]["anchor_ref"] = "sha256:" + "f" * 64
        assert (
            BilateralDelegation.from_dict(mutated).content_hash()
            != original.content_hash()
        )


class TestBilateralDelegationInvariants:
    """SINGLE-ROOT + dispatcher-provenance invariants (behavioral)."""

    def test_cross_root_construction_fails_closed(self) -> None:
        """A delegation spanning two roots raises (federation OUT OF SCOPE)."""
        with pytest.raises(CrossRootFederationError) as exc:
            new_bilateral_delegation(
                delegation_id="x",
                root="Eng",
                delegator=PartyAnchor(
                    "Eng-CTO", "sha256:" + "a" * 64, SignerKind.PARTY
                ),
                delegate=PartyAnchor(
                    "Sales-VP", "sha256:" + "b" * 64, SignerKind.PARTY
                ),
                ts="2026-01-15T10:00:00+00:00",
            )
        assert exc.value.details["party"] == "delegate"
        assert exc.value.details["party_root"] == "Sales"

    def test_from_dict_cross_root_fails_closed(self) -> None:
        """A cross-root delegation reconstructed from a dict also fails closed."""
        with pytest.raises(CrossRootFederationError):
            BilateralDelegation.from_dict(
                {
                    "schema_version": SCHEMA_VERSION_V3,
                    "delegation_id": "x",
                    "root": "Eng",
                    "delegator": {
                        "role_address": "Eng-CTO",
                        "anchor_ref": "sha256:" + "a" * 64,
                        "signer_kind": "party",
                    },
                    "delegate": {
                        "role_address": "Ops-Lead",
                        "anchor_ref": "sha256:" + "b" * 64,
                        "signer_kind": "party",
                    },
                    "ts": "2026-01-15T10:00:00+00:00",
                }
            )

    def test_dispatcher_signed_is_provenance_only(self) -> None:
        """A dispatcher-signed anchor is provenance-only -- never non-repudiation."""
        vector = _load_vector("eatp3_bilateral_dispatcher_provenance.json")
        delegation = BilateralDelegation.from_dict(vector["input"])
        assert delegation.guarantee_tier() is GuaranteeTier.RECORDED_BY_INTERMEDIARY
        assert not delegation.supports_non_repudiation()
        with pytest.raises(NonRepudiationClaimError) as exc:
            delegation.assert_non_repudiation()
        assert "delegator" in exc.value.details["dispatcher_signed_parties"]

    def test_both_party_signed_supports_non_repudiation(self) -> None:
        vector = _load_vector("eatp3_bilateral_valid.json")
        delegation = BilateralDelegation.from_dict(vector["input"])
        assert delegation.supports_non_repudiation()
        delegation.assert_non_repudiation()  # must not raise

    def test_witnessed_is_strongest_tier(self) -> None:
        vector = _load_vector("eatp3_bilateral_witnessed.json")
        delegation = BilateralDelegation.from_dict(vector["input"])
        assert delegation.guarantee_tier() is GuaranteeTier.COMPLETE_WITNESSED

    def test_party_anchor_unknown_signer_kind_fails_closed(self) -> None:
        with pytest.raises(Exception):
            PartyAnchor.from_dict(
                {"role_address": "Eng-CTO", "anchor_ref": "x", "signer_kind": "forged"}
            )


class TestGuaranteeTierTaxonomy:
    """The three-tier guarantee taxonomy is distinct + vector-pinned."""

    def test_guarantee_tier_distinction_vector(self) -> None:
        vector = _load_vector("eatp3_guarantee_tier_distinction.json")
        assert vector["expected_tiers_ordered"] == [
            GuaranteeTier.RECORDED_BY_INTERMEDIARY.value,
            GuaranteeTier.CONFORMANT.value,
            GuaranteeTier.COMPLETE_WITNESSED.value,
        ]
        shape = vector["expected_shape_to_tier"]
        assert (
            shape["dispatcher_or_missing_anchor"]
            == GuaranteeTier.RECORDED_BY_INTERMEDIARY.value
        )
        assert shape["both_party_signed_present"] == GuaranteeTier.CONFORMANT.value
        assert (
            shape["conformant_plus_witness"] == GuaranteeTier.COMPLETE_WITNESSED.value
        )

    def test_three_tiers_are_distinct(self) -> None:
        assert (
            len({t.value for t in GuaranteeTier}) == 3
        ), "guarantee taxonomy must have exactly three distinct tiers"


# ---------------------------------------------------------------------------
# ClearanceAttestation -- posture-gated re-identification + ordinal pin
# ---------------------------------------------------------------------------


class TestClearanceAttestation:
    """ClearanceAttestation byte-pin + posture-gated re-identification."""

    def test_posture_gate_vector(self) -> None:
        vector = _load_vector("eatp3_clearance_posture_gate.json")
        att = ClearanceAttestation.from_dict(vector["input"])

        assert att.schema_version == SCHEMA_VERSION_V3
        assert att.canonical_json() == vector["expected_canonical_json"]
        assert att.content_hash() == vector["expected_content_hash"]
        assert att.required_clearance.value == vector["expected_required_clearance"]

        for posture_value, expected in vector["expected_reidentify_by_posture"].items():
            posture = TrustPosture(posture_value)
            assert att.can_reidentify(posture) is expected

    def test_reidentification_denied_below_gate_fails_closed(self) -> None:
        vector = _load_vector("eatp3_clearance_posture_gate.json")
        att = ClearanceAttestation.from_dict(vector["input"])
        # SUPERVISED ceiling is CONFIDENTIAL < SECRET -> denied
        assert not att.can_reidentify(TrustPosture.SUPERVISED)
        with pytest.raises(ReidentificationDeniedError):
            att.assert_reidentification(TrustPosture.SUPERVISED)

    def test_reidentification_permitted_at_or_above_gate(self) -> None:
        vector = _load_vector("eatp3_clearance_posture_gate.json")
        att = ClearanceAttestation.from_dict(vector["input"])
        # DELEGATING ceiling is SECRET == required -> permitted, must not raise
        att.assert_reidentification(TrustPosture.DELEGATING)

    def test_roundtrip_byte_stable(self) -> None:
        vector = _load_vector("eatp3_clearance_posture_gate.json")
        att = ClearanceAttestation.from_dict(vector["input"])
        roundtripped = ClearanceAttestation.from_dict(att.to_dict())
        assert roundtripped.to_dict() == att.to_dict()
        assert roundtripped.content_hash() == att.content_hash()


class TestClearanceOrdinalInvertedPair:
    """Pin the reused ConfidentialityLevel C0..C4 ordinal (inverted-pair)."""

    def test_ordinal_inverted_pair_vector(self) -> None:
        vector = _load_vector("eatp3_clearance_ordinal_inverted_pair.json")
        # The inverted-pair pin: restricted=C1 < confidential=C2.
        assert vector["expected_ordinal"]["restricted"] == 1
        assert vector["expected_ordinal"]["confidential"] == 2
        assert vector["expected_restricted_lt_confidential"] is True
        assert vector["expected_wire_tokens_ordered"] == [
            "public",
            "restricted",
            "confidential",
            "secret",
            "top_secret",
        ]

    def test_live_ordinal_matches_vector(self) -> None:
        """The reused ConfidentialityLevel enum matches the pinned ordinal."""
        assert ConfidentialityLevel.RESTRICTED < ConfidentialityLevel.CONFIDENTIAL
        ordered = sorted(ConfidentialityLevel)
        assert [level.value for level in ordered] == [
            "public",
            "restricted",
            "confidential",
            "secret",
            "top_secret",
        ]

    def test_posture_gate_uses_shared_ordinal(self) -> None:
        # A RESTRICTED-required attestation (C1) is re-identifiable at TOOL
        # (ceiling RESTRICTED) but a CONFIDENTIAL one (C2) is not.
        assert posture_can_reidentify(
            TrustPosture.TOOL, ConfidentialityLevel.RESTRICTED
        )
        assert not posture_can_reidentify(
            TrustPosture.TOOL, ConfidentialityLevel.CONFIDENTIAL
        )


# ---------------------------------------------------------------------------
# VERIFY_CHAIN -- deny-overrides composition
# ---------------------------------------------------------------------------


class TestVerifyChainDenyOverrides:
    """VERIFY_CHAIN composes under deny-overrides; empty fails closed."""

    def test_deny_overrides_vector(self) -> None:
        vector = _load_vector("eatp3_verify_chain_deny_overrides.json")
        links = [ChainLink.from_dict(raw) for raw in vector["input"]["links"]]
        result = verify_chain(links)
        assert result.to_dict() == vector["expected_result"]
        assert result.allowed is vector["expected_allowed"] is False
        assert result.denied_by == vector["expected_denied_by"]

    def test_all_allow_vector(self) -> None:
        vector = _load_vector("eatp3_verify_chain_all_allow.json")
        links = [ChainLink.from_dict(raw) for raw in vector["input"]["links"]]
        result = verify_chain(links)
        assert result.to_dict() == vector["expected_result"]
        assert result.allowed is True
        assert result.denied_by is None

    def test_single_deny_denies_whole_chain(self) -> None:
        result = verify_chain(
            [
                ChainLink("a", ChainVerdict.ALLOW),
                ChainLink("b", ChainVerdict.ALLOW),
                ChainLink("c", ChainVerdict.DENY, "insufficient clearance"),
            ]
        )
        assert not result.allowed
        assert result.denied_by == "c"
        assert result.evaluated == 3

    def test_empty_chain_fails_closed(self) -> None:
        result = verify_chain([])
        assert not result.allowed
        assert result.evaluated == 0

    def test_deny_short_circuits(self) -> None:
        result = verify_chain(
            [
                ChainLink("a", ChainVerdict.DENY),
                ChainLink("b", ChainVerdict.ALLOW),
            ]
        )
        assert result.denied_by == "a"
        assert result.evaluated == 1  # short-circuits at the first deny

    def test_unknown_verdict_token_fails_closed(self) -> None:
        with pytest.raises(VerifyChainError):
            ChainLink.from_dict({"link_id": "a", "verdict": "maybe"})


# ---------------------------------------------------------------------------
# GRACEFUL / SUSPEND revocation modes
# ---------------------------------------------------------------------------


class TestRevocationModes:
    """GRACEFUL grace-window drain + SUSPEND reversible hold (behavioral)."""

    def _fresh_trl(self):
        broadcaster = InMemoryRevocationBroadcaster()
        registry = InMemoryDelegationRegistry()
        manager = CascadeRevocationManager(broadcaster, registry)
        trl = TrustRevocationList(broadcaster)
        trl.initialize()
        return manager, trl, registry

    def test_graceful_vector_roundtrip(self) -> None:
        vector = _load_vector("eatp3_revocation_graceful.json")
        event = RevocationEvent.from_dict(vector["input"])
        assert event.mode is RevocationMode.GRACEFUL
        assert event.mode.value == vector["expected_mode"]
        assert event.effective_at.isoformat() == vector["expected_effective_at"]
        assert event.to_dict() == vector["input"]

    def test_suspend_vector_roundtrip(self) -> None:
        vector = _load_vector("eatp3_revocation_suspend.json")
        event = RevocationEvent.from_dict(vector["input"])
        assert event.mode is RevocationMode.SUSPEND
        assert event.effective_at is None
        assert event.to_dict() == vector["input"]

    def test_backward_compatible_immediate_default(self) -> None:
        """A record with no 'mode' key deserializes to IMMEDIATE (backward compat)."""
        event = RevocationEvent.from_dict(
            {
                "event_id": "rev-old",
                "revocation_type": "agent_revoked",
                "target_id": "agent-x",
                "revoked_by": "admin",
                "reason": "legacy",
                "timestamp": "2026-01-15T10:00:00+00:00",
            }
        )
        assert event.mode is RevocationMode.IMMEDIATE
        assert event.effective_at is None

    def test_graceful_effective_only_after_deadline(self) -> None:
        manager, trl, _ = self._fresh_trl()
        deadline = dt.datetime(2026, 1, 15, 11, 0, 0, tzinfo=dt.timezone.utc)
        manager.cascade_revoke(
            "agent-G",
            "admin",
            "drain",
            mode=RevocationMode.GRACEFUL,
            effective_at=deadline,
        )
        assert trl.is_revoked("agent-G")  # a revocation IS recorded
        before = dt.datetime(2026, 1, 15, 10, 30, tzinfo=dt.timezone.utc)
        after = dt.datetime(2026, 1, 15, 11, 30, tzinfo=dt.timezone.utc)
        assert not trl.is_effective("agent-G", before)  # draining in-flight work
        assert trl.is_effective("agent-G", after)  # hard-revoked past deadline
        trl.close()

    def test_graceful_is_irreversible(self) -> None:
        manager, trl, _ = self._fresh_trl()
        deadline = dt.datetime(2026, 1, 15, 11, 0, 0, tzinfo=dt.timezone.utc)
        manager.cascade_revoke(
            "agent-G",
            "admin",
            "drain",
            mode=RevocationMode.GRACEFUL,
            effective_at=deadline,
        )
        with pytest.raises(IrreversibleRevocationError):
            trl.reinstate("agent-G")
        trl.close()

    def test_suspend_is_reversible(self) -> None:
        manager, trl, _ = self._fresh_trl()
        manager.cascade_revoke(
            "agent-S", "admin", "hold pending review", mode=RevocationMode.SUSPEND
        )
        assert trl.is_revoked("agent-S")
        assert trl.revocation_mode("agent-S") is RevocationMode.SUSPEND
        trl.reinstate("agent-S")
        assert not trl.is_revoked("agent-S")  # reversible hold lifted
        assert trl.revocation_mode("agent-S") is None
        trl.close()

    def test_immediate_is_irreversible(self) -> None:
        manager, trl, _ = self._fresh_trl()
        manager.cascade_revoke(
            "agent-I", "admin", "terminal", mode=RevocationMode.IMMEDIATE
        )
        with pytest.raises(IrreversibleRevocationError):
            trl.reinstate("agent-I")
        trl.close()

    def test_reinstate_unknown_agent_raises(self) -> None:
        _, trl, _ = self._fresh_trl()
        with pytest.raises(RevocationError):
            trl.reinstate("never-revoked")
        trl.close()

    def test_graceful_mode_cascades_to_subtree(self) -> None:
        """Cascaded revocations inherit the initial mode + grace deadline."""
        manager, trl, registry = self._fresh_trl()
        registry.register_delegation("agent-A", "agent-B")
        deadline = dt.datetime(2026, 1, 15, 11, 0, 0, tzinfo=dt.timezone.utc)
        manager.cascade_revoke(
            "agent-A",
            "admin",
            "drain tree",
            mode=RevocationMode.GRACEFUL,
            effective_at=deadline,
        )
        assert trl.revocation_mode("agent-B") is RevocationMode.GRACEFUL
        trl.close()


# ---------------------------------------------------------------------------
# Vector-file integrity
# ---------------------------------------------------------------------------


class TestEatpV3VectorIntegrity:
    """Every EATP-v3 (#1592) vector exists and has the required structure."""

    @pytest.mark.parametrize("vector_file", ALL_EATP3_VECTORS)
    def test_vector_file_exists_and_valid_json(self, vector_file: str) -> None:
        vector = _load_vector(vector_file)
        assert "description" in vector, f"{vector_file} missing 'description'"
        assert "pact_type" in vector, f"{vector_file} missing 'pact_type'"

    def test_all_eatp3_vectors_present(self) -> None:
        actual = sorted(p.name for p in VECTORS_DIR.glob("eatp3_*.json"))
        assert actual == sorted(ALL_EATP3_VECTORS), (
            f"EATP-v3 vector files mismatch.\n"
            f"Expected: {sorted(ALL_EATP3_VECTORS)}\n"
            f"Actual:   {actual}"
        )
