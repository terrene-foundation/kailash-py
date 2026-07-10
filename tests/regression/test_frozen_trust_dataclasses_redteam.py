# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression tests for the wave-2 holistic /redteam trust-plane hardening.

Findings hardened here (all against code merged this session -- #1592 EATP v3 +
#1517-b outbound governance):

* **M1 (MED)** -- the security-critical EATP dataclasses enforced their
  construction-time invariants ONLY at ``__post_init__`` (cross-root federation
  denial, re-identification clearance gate, hash-chain linkage, deny-overrides
  verdict). Because they were plain ``@dataclass`` (mutable), an attacker could
  construct a VALID instance and then reassign a field with NO re-validation,
  bypassing the gate. The fix makes them ``@dataclass(frozen=True)`` (per
  ``trust-plane-security.md`` MUST-NOT-4 / ``eatp.md``). These tests assert
  (a) post-construction assignment raises ``FrozenInstanceError``, (b) the
  construct-valid-then-mutate bypass now raises, and (c) ``from_dict(to_dict(x))``
  still round-trips.

* **L2 (LOW)** -- ``OutboundVerdict`` was ``frozen=True`` but its ``governance``
  dict's CONTENTS stayed mutable, weakening the "an audited decision cannot be
  mutated after the fact" guarantee. The fix wraps ``governance`` in a
  ``MappingProxyType`` at construction; ``to_dict`` copies back to a plain dict.
"""

from __future__ import annotations

import dataclasses

import pytest

from kailash.trust import ConfidentialityLevel
from kailash.trust.pact.attestation import (
    ClearanceAttestation,
    new_clearance_attestation,
)
from kailash.trust.pact.audit import SCHEMA_VERSION_V3
from kailash.trust.pact.bilateral import (
    BilateralDelegation,
    PartyAnchor,
    SignerKind,
    new_bilateral_delegation,
)
from kailash.trust.pact.outbound import EffectKind, OutboundEffect, OutboundVerdict
from kailash.trust.pact.verify_chain import ChainLink, ChainVerdict
from kailash.trust.pact.weft import WeftEvent, WeftKind

pytestmark = pytest.mark.regression


# --------------------------------------------------------------------------- #
# Fixtures / builders
# --------------------------------------------------------------------------- #
def _party(addr: str, ref: str = "sha256:anchor") -> PartyAnchor:
    return PartyAnchor(role_address=addr, anchor_ref=ref, signer_kind=SignerKind.PARTY)


def _valid_delegation() -> BilateralDelegation:
    return new_bilateral_delegation(
        delegation_id="del-1",
        root="Eng",
        delegator=_party("Eng-CTO"),
        delegate=_party("Eng-Dev"),
        ts="2026-07-10T00:00:00Z",
    )


# --------------------------------------------------------------------------- #
# M1 -- PartyAnchor
# --------------------------------------------------------------------------- #
def test_party_anchor_is_frozen():
    anchor = _party("Eng-CTO")
    with pytest.raises(dataclasses.FrozenInstanceError):
        anchor.signer_kind = SignerKind.DISPATCHER  # type: ignore[misc]
    with pytest.raises(dataclasses.FrozenInstanceError):
        anchor.anchor_ref = "sha256:forged"  # type: ignore[misc]


# --------------------------------------------------------------------------- #
# M1 -- BilateralDelegation (cross-root federation gate)
# --------------------------------------------------------------------------- #
def test_bilateral_delegation_is_frozen():
    delegation = _valid_delegation()
    with pytest.raises(dataclasses.FrozenInstanceError):
        delegation.root = "Acme"  # type: ignore[misc]


def test_bilateral_delegation_cross_root_gate_cannot_be_mutation_bypassed():
    """Construct a valid single-root delegation, then try to swap the delegator
    for a FOREIGN-root anchor. The cross-root gate only runs at construction, so
    before the freeze this reassignment silently produced a cross-root delegation
    that was never re-validated. Frozen=True now blocks the reassignment."""
    delegation = _valid_delegation()
    foreign = _party("Acme-CFO")  # different D/T/R root
    with pytest.raises(dataclasses.FrozenInstanceError):
        delegation.delegator = foreign  # type: ignore[misc]
    # The gate still fires the legitimate way -- at construction.
    from kailash.trust.pact.bilateral import CrossRootFederationError

    with pytest.raises(CrossRootFederationError):
        BilateralDelegation(
            schema_version=SCHEMA_VERSION_V3,
            delegation_id="del-x",
            root="Eng",
            delegator=foreign,  # Acme root != Eng
            delegate=_party("Eng-Dev"),
            ts="2026-07-10T00:00:00Z",
        )


def test_bilateral_delegation_roundtrip_survives_freeze():
    delegation = _valid_delegation()
    assert BilateralDelegation.from_dict(delegation.to_dict()) == delegation


# --------------------------------------------------------------------------- #
# M1 -- ClearanceAttestation (re-identification clearance gate)
# --------------------------------------------------------------------------- #
def test_clearance_attestation_is_frozen():
    att = new_clearance_attestation(
        attestation_id="att-1",
        subject_ref="pseudo-123",
        required_clearance=ConfidentialityLevel.SECRET,
        ts="2026-07-10T00:00:00Z",
        attested_by_role_address="Eng-CTO",
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        att.required_clearance = ConfidentialityLevel.PUBLIC  # type: ignore[misc]


def test_clearance_attestation_reid_gate_cannot_be_lowered_by_mutation():
    """The re-identification gate reads ``required_clearance``. Before the freeze,
    an attacker could construct a SECRET-gated attestation and then lower it to
    PUBLIC, re-identifying a subject their posture could never clear."""
    att = new_clearance_attestation(
        attestation_id="att-2",
        subject_ref="pseudo-456",
        required_clearance=ConfidentialityLevel.SECRET,
        ts="2026-07-10T00:00:00Z",
        attested_by_role_address="Eng-CTO",
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        att.required_clearance = ConfidentialityLevel.PUBLIC  # type: ignore[misc]


def test_clearance_attestation_roundtrip_survives_freeze():
    att = new_clearance_attestation(
        attestation_id="att-3",
        subject_ref="pseudo-789",
        required_clearance=ConfidentialityLevel.CONFIDENTIAL,
        ts="2026-07-10T00:00:00Z",
        attested_by_role_address="Eng-CTO",
        payload={"k": "v"},
    )
    assert ClearanceAttestation.from_dict(att.to_dict()) == att


# --------------------------------------------------------------------------- #
# M1 -- WeftEvent (hash-chain linkage invariant)
# --------------------------------------------------------------------------- #
def test_weft_event_is_frozen_and_chain_link_immutable():
    event = WeftEvent(
        schema_version=SCHEMA_VERSION_V3,
        kind=WeftKind.MINT,
        ts="2026-07-10T00:00:00Z",
        session="s-1",
        identity_ref="Eng-CTO",
        prev_link="sha256:parent",
    )
    # content_hash still computes over the (now immutable) envelope.
    assert event.content_hash().startswith("sha256:")
    # An attacker cannot re-thread the chain by rewriting prev_link/payload.
    with pytest.raises(dataclasses.FrozenInstanceError):
        event.prev_link = "sha256:forged-parent"  # type: ignore[misc]
    with pytest.raises(dataclasses.FrozenInstanceError):
        event.kind = WeftKind.DISTRIBUTE  # type: ignore[misc]


def test_weft_event_roundtrip_survives_freeze():
    event = WeftEvent(
        schema_version=SCHEMA_VERSION_V3,
        kind=WeftKind.MINT,
        ts="2026-07-10T00:00:00Z",
        session="s-1",
        identity_ref="Eng-CTO",
        payload={"a": 1},
        prev_link=None,
    )
    assert WeftEvent.from_dict(event.to_dict()) == event


# --------------------------------------------------------------------------- #
# M1 -- ChainLink (deny-overrides verdict gate)
# --------------------------------------------------------------------------- #
def test_chain_link_deny_verdict_cannot_be_flipped_to_allow():
    """A DENY link denies the whole chain (deny-overrides). Before the freeze an
    attacker could construct a DENY link and flip ``.verdict`` to ALLOW."""
    link = ChainLink(link_id="link-1", verdict=ChainVerdict.DENY, reason="blocked")
    with pytest.raises(dataclasses.FrozenInstanceError):
        link.verdict = ChainVerdict.ALLOW  # type: ignore[misc]


def test_chain_link_roundtrip_survives_freeze():
    link = ChainLink(link_id="link-2", verdict=ChainVerdict.ALLOW, reason="ok")
    assert ChainLink.from_dict(link.to_dict()) == link


# --------------------------------------------------------------------------- #
# L2 -- OutboundVerdict.governance is deeply immutable
# --------------------------------------------------------------------------- #
def _verdict(governance: dict) -> OutboundVerdict:
    return OutboundVerdict(
        allowed=True,
        level="auto_approved",
        reason="ok",
        effect=OutboundEffect(kind=EffectKind.HTTP, operation="http.GET"),
        governance=governance,
    )


def test_outbound_verdict_governance_contents_are_immutable():
    verdict = _verdict({"x": 0, "nested": {"y": 1}})
    # frozen=True already blocks rebinding the field...
    with pytest.raises(dataclasses.FrozenInstanceError):
        verdict.governance = {"evil": True}  # type: ignore[misc]
    # ...and MappingProxyType now blocks mutating its CONTENTS.
    with pytest.raises(TypeError):
        verdict.governance["x"] = 1  # type: ignore[index]
    with pytest.raises(TypeError):
        del verdict.governance["x"]  # type: ignore[misc]


def test_outbound_verdict_to_dict_returns_plain_mutable_dict():
    verdict = _verdict({"x": 0})
    d = verdict.to_dict()
    gov = d["governance"]
    assert type(gov) is dict  # plain dict, NOT a MappingProxyType
    assert gov == {"x": 0}
    # Mutating the serialized copy MUST NOT affect the verdict's frozen view.
    gov["x"] = 99
    assert verdict.governance["x"] == 0
