# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""BilateralDelegation -- atomic two-party delegation for EATP v3 (#1592).

A :class:`BilateralDelegation` binds exactly two parties -- a ``delegator`` and a
``delegate`` -- each carrying a citable :class:`PartyAnchor` (a reference to the
party's audit anchor). The load-bearing invariant is **atomic validity**: the
delegation is valid ONLY when BOTH parties' anchors are present. A delegation
missing either anchor is invalid, fail-closed -- one party's anchor never
half-authorizes the delegation.

Two further invariants shape the guarantee this delegation carries:

1. **SINGLE-ROOT ONLY.** Both parties MUST share the same D/T/R root. The
   cross-root *federation-anchor* variant (a delegation spanning two independent
   organizational roots) is gated on ``terrene#35 G1`` and is OUT OF SCOPE for
   #1592 -- constructing one raises :class:`CrossRootFederationError` (fail-closed,
   never silently accepted).

2. **Dispatcher signatures are provenance-only -- NEVER non-repudiation.** A
   :class:`PartyAnchor` signed by a ``DISPATCHER`` (an intermediary that merely
   *recorded* the delegation) carries provenance weight only. Non-repudiation --
   the property that a party cannot later disown the delegation -- requires the
   party ITSELF to have signed (``PARTY``). :meth:`BilateralDelegation.
   supports_non_repudiation` returns ``False`` whenever either anchor is
   dispatcher-signed, and :meth:`assert_non_repudiation` raises fail-closed.

The **guarantee-tier taxonomy** (:class:`GuaranteeTier`) grades the strength of
a delegation's provenance guarantee:

* ``RECORDED_BY_INTERMEDIARY`` -- a dispatcher recorded it (provenance only), OR
  an anchor is missing. The weakest tier.
* ``CONFORMANT`` -- both parties' anchors are present AND both are party-signed.
* ``COMPLETE_WITNESSED`` -- conformant PLUS an independent ``witness_ref`` anchor.

Follows the EATP dataclass conventions (``eatp.md``): ``@dataclass`` with
``to_dict`` / ``from_dict``, ``str``-backed ``Enum``s, an explicit ``__all__``,
``from __future__ import annotations``, JCS (#1590) canonicalization for the
citable ``content_hash``, and a ``PactError``-derived error hierarchy that fails
closed on unknown / error states.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from kailash.trust._jcs import jcs_encode
from kailash.trust.pact.audit import SCHEMA_VERSION_V3
from kailash.trust.pact.exceptions import PactError

logger = logging.getLogger(__name__)

__all__ = [
    "SignerKind",
    "GuaranteeTier",
    "PartyAnchor",
    "BilateralDelegation",
    "BilateralDelegationError",
    "AtomicValidityError",
    "CrossRootFederationError",
    "NonRepudiationClaimError",
]


class SignerKind(str, Enum):
    """Who signed a party's anchor -- the non-repudiation discriminator.

    ``str``-backed so it serializes to its wire name directly in JSON.
    """

    PARTY = "party"
    """The party itself signed the anchor. Non-repudiation eligible."""

    DISPATCHER = "dispatcher"
    """An intermediary/dispatcher recorded the anchor on the party's behalf.

    Provenance ONLY. A dispatcher signature attests that the delegation was
    *seen and recorded* by the intermediary -- it does NOT bind the party, and
    it can NEVER be relied on for non-repudiation.
    """


class GuaranteeTier(str, Enum):
    """The strength of a bilateral delegation's provenance guarantee.

    Ordered weakest -> strongest:
    ``RECORDED_BY_INTERMEDIARY`` < ``CONFORMANT`` < ``COMPLETE_WITNESSED``.
    """

    RECORDED_BY_INTERMEDIARY = "recorded_by_intermediary"
    """A dispatcher recorded the delegation (provenance only), OR an anchor is
    missing. The weakest tier -- carries NO non-repudiation guarantee."""

    CONFORMANT = "conformant"
    """Both parties' anchors are present AND both are party-signed. Supports
    non-repudiation."""

    COMPLETE_WITNESSED = "complete_witnessed"
    """Conformant PLUS an independent witness anchor observed the delegation --
    the strongest tier."""


class BilateralDelegationError(PactError):
    """Base class for bilateral-delegation errors.

    Inherits ``PactError`` (structured ``.details`` dict) so failures are caught
    by the PACT trust-layer catch blocks rather than surfacing as unstructured
    crashes.
    """


class AtomicValidityError(BilateralDelegationError):
    """Raised when a delegation missing a party anchor is used as if valid.

    Fail-closed: a delegation is atomically valid ONLY when BOTH anchors are
    present. The absence of either anchor DENIES validity -- it never
    half-authorizes.
    """


class CrossRootFederationError(BilateralDelegationError):
    """Raised when a delegation spans two distinct D/T/R roots.

    The cross-root federation-anchor variant is gated on ``terrene#35 G1`` and
    is OUT OF SCOPE for #1592. Constructing one fails closed here rather than
    silently accepting an unsupported federation.
    """


class NonRepudiationClaimError(BilateralDelegationError):
    """Raised when non-repudiation is asserted on a dispatcher-signed delegation.

    A dispatcher signature is provenance-only; claiming non-repudiation on it is
    a fail-closed error -- the intermediary's recording never binds the party.
    """


def _root_of(role_address: str) -> str:
    """Return the D/T/R root (leading Department segment) of an address.

    The root is the first ``-``-delimited segment (e.g. ``"Eng"`` for
    ``"Eng-CTO-Backend-Lead"``). An empty address yields ``""`` (which will fail
    the single-root check downstream, fail-closed).
    """
    return role_address.split("-", 1)[0]


@dataclass
class PartyAnchor:
    """A citable reference to one party's audit anchor in a bilateral delegation.

    Attributes:
        role_address: The party's D/T/R positional address.
        anchor_ref: A citable reference to the party's audit anchor (e.g. an
            ``AuditAnchor`` content hash). An empty string denotes an ABSENT
            anchor -- the atomic-validity invariant treats it as not present.
        signer_kind: Who signed the anchor (:class:`SignerKind`). ``DISPATCHER``
            signatures are provenance-only and never support non-repudiation.
    """

    role_address: str
    anchor_ref: str
    signer_kind: SignerKind

    def is_present(self) -> bool:
        """Return ``True`` iff this party's anchor is present (non-empty ref)."""
        return bool(self.anchor_ref)

    def supports_non_repudiation(self) -> bool:
        """Return ``True`` iff this anchor can bind the party (non-repudiation).

        Requires the anchor be present AND party-signed. A dispatcher-signed
        anchor is provenance-only and returns ``False``.
        """
        return self.is_present() and self.signer_kind is SignerKind.PARTY

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-native dict (``signer_kind`` as its wire value)."""
        return {
            "role_address": self.role_address,
            "anchor_ref": self.anchor_ref,
            "signer_kind": self.signer_kind.value,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PartyAnchor:
        """Deserialize STRICTLY from a dict.

        Raises:
            BilateralDelegationError: if a required field is missing or
                ``signer_kind`` is not a recognized :class:`SignerKind`.
        """
        for required in ("role_address", "anchor_ref", "signer_kind"):
            if required not in data:
                raise BilateralDelegationError(
                    f"PartyAnchor.from_dict: missing required field {required!r}",
                    details={"missing_field": required},
                )
        raw_kind = data["signer_kind"]
        try:
            signer_kind = SignerKind(raw_kind)
        except ValueError as exc:
            raise BilateralDelegationError(
                f"PartyAnchor.from_dict: unrecognized signer_kind {raw_kind!r}; "
                f"known kinds are {[k.value for k in SignerKind]}",
                details={"signer_kind": raw_kind},
            ) from exc
        return cls(
            role_address=data["role_address"],
            anchor_ref=data["anchor_ref"],
            signer_kind=signer_kind,
        )


@dataclass
class BilateralDelegation:
    """An atomic two-party delegation with a citable, JCS-hashed envelope.

    Attributes:
        schema_version: The #1590 schema discriminator (default ``"v3"``).
        delegation_id: Stable identifier for this delegation.
        root: The single D/T/R root both parties share. SINGLE-ROOT ONLY --
            a party whose root differs raises :class:`CrossRootFederationError`.
        delegator: The delegating party's :class:`PartyAnchor`.
        delegate: The receiving party's :class:`PartyAnchor`.
        ts: ISO-8601 timestamp of the delegation.
        witness_ref: Optional independent witness anchor. Its presence (with a
            conformant delegation) elevates the guarantee tier to
            ``COMPLETE_WITNESSED``.
        payload: Structured, delegation-specific data (JSON-native / typed-scalar).
    """

    schema_version: str
    delegation_id: str
    root: str
    delegator: PartyAnchor
    delegate: PartyAnchor
    ts: str
    witness_ref: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Enforce the SINGLE-ROOT invariant at construction (fail-closed).

        Both parties MUST share ``self.root``. A party under a different root is
        the cross-root federation variant gated on ``terrene#35 G1`` (OUT OF
        SCOPE for #1592) and raises :class:`CrossRootFederationError`.
        """
        for label, party in (
            ("delegator", self.delegator),
            ("delegate", self.delegate),
        ):
            party_root = _root_of(party.role_address)
            if party_root != self.root:
                raise CrossRootFederationError(
                    f"BilateralDelegation is SINGLE-ROOT only: {label} root "
                    f"{party_root!r} != delegation root {self.root!r}. The "
                    f"cross-root federation-anchor variant is gated on "
                    f"terrene#35 G1 and is OUT OF SCOPE for #1592.",
                    details={
                        "delegation_id": self.delegation_id,
                        "party": label,
                        "party_root": party_root,
                        "delegation_root": self.root,
                    },
                )

    def is_atomically_valid(self) -> bool:
        """Return ``True`` iff BOTH parties' anchors are present.

        The atomic-validity invariant: one party's anchor never half-authorizes
        the delegation. Missing either anchor => invalid (fail-closed).
        """
        return self.delegator.is_present() and self.delegate.is_present()

    def assert_atomic_validity(self) -> None:
        """Raise :class:`AtomicValidityError` if the delegation is not atomically valid."""
        if not self.is_atomically_valid():
            missing = [
                label
                for label, party in (
                    ("delegator", self.delegator),
                    ("delegate", self.delegate),
                )
                if not party.is_present()
            ]
            raise AtomicValidityError(
                f"BilateralDelegation {self.delegation_id!r} is not atomically "
                f"valid: missing anchor(s) for {missing}. Both parties' anchors "
                f"MUST be present.",
                details={"delegation_id": self.delegation_id, "missing": missing},
            )

    def supports_non_repudiation(self) -> bool:
        """Return ``True`` iff BOTH parties are present AND party-signed.

        A dispatcher-signed anchor is provenance-only; if EITHER party is
        dispatcher-signed the delegation does NOT support non-repudiation.
        """
        return (
            self.delegator.supports_non_repudiation()
            and self.delegate.supports_non_repudiation()
        )

    def assert_non_repudiation(self) -> None:
        """Raise :class:`NonRepudiationClaimError` if non-repudiation cannot hold.

        Fail-closed: a dispatcher-signed (provenance-only) anchor can NEVER be
        labelled non-repudiation.
        """
        if not self.supports_non_repudiation():
            dispatcher_parties = [
                label
                for label, party in (
                    ("delegator", self.delegator),
                    ("delegate", self.delegate),
                )
                if party.signer_kind is SignerKind.DISPATCHER
            ]
            raise NonRepudiationClaimError(
                f"BilateralDelegation {self.delegation_id!r} does not support "
                f"non-repudiation: dispatcher-signed anchors are provenance-only "
                f"(parties={dispatcher_parties or 'missing-anchor'}).",
                details={
                    "delegation_id": self.delegation_id,
                    "dispatcher_signed_parties": dispatcher_parties,
                },
            )

    def guarantee_tier(self) -> GuaranteeTier:
        """Grade the delegation's provenance guarantee (:class:`GuaranteeTier`).

        * A dispatcher-signed anchor OR a missing anchor => the weakest tier,
          ``RECORDED_BY_INTERMEDIARY``.
        * Both anchors present + party-signed => ``CONFORMANT``.
        * Conformant PLUS a ``witness_ref`` => ``COMPLETE_WITNESSED``.
        """
        if not self.supports_non_repudiation():
            # Dispatcher-signed or missing anchor: provenance only.
            return GuaranteeTier.RECORDED_BY_INTERMEDIARY
        if self.witness_ref:
            return GuaranteeTier.COMPLETE_WITNESSED
        return GuaranteeTier.CONFORMANT

    def to_dict(self) -> dict[str, Any]:
        """Serialize the envelope to a JSON-native dict."""
        return {
            "schema_version": self.schema_version,
            "delegation_id": self.delegation_id,
            "root": self.root,
            "delegator": self.delegator.to_dict(),
            "delegate": self.delegate.to_dict(),
            "ts": self.ts,
            "witness_ref": self.witness_ref,
            "payload": self.payload,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BilateralDelegation:
        """Deserialize STRICTLY from a dict.

        Raises:
            BilateralDelegationError: if a required field is missing.
            CrossRootFederationError: if the reconstructed delegation is cross-root.
        """
        for required in (
            "schema_version",
            "delegation_id",
            "root",
            "delegator",
            "delegate",
            "ts",
        ):
            if required not in data:
                raise BilateralDelegationError(
                    f"BilateralDelegation.from_dict: missing required field "
                    f"{required!r}",
                    details={"missing_field": required},
                )
        return cls(
            schema_version=data["schema_version"],
            delegation_id=data["delegation_id"],
            root=data["root"],
            delegator=PartyAnchor.from_dict(data["delegator"]),
            delegate=PartyAnchor.from_dict(data["delegate"]),
            ts=data["ts"],
            witness_ref=data.get("witness_ref"),
            payload=data.get("payload", {}),
        )

    def canonical_json(self) -> str:
        """Return the RFC 8785 (JCS) canonical JSON string of the envelope.

        Reuses the #1590 JCS keystone (:func:`kailash.trust._jcs.jcs_encode`),
        which rejects non-finite floats -- a ``NaN`` / ``Infinity`` in ``payload``
        fails CLOSED here before it can enter a citable pre-image
        (``trust-plane-security.md`` MUST-8).
        """
        return jcs_encode(self.to_dict())

    def content_hash(self) -> str:
        """Return ``"sha256:<hex>"`` -- the citable content hash of the envelope.

        Byte-stable across SDKs because the pre-image is the JCS canonicalization.
        """
        encoded = self.canonical_json().encode("utf-8")
        return "sha256:" + hashlib.sha256(encoded).hexdigest()


def new_bilateral_delegation(
    *,
    delegation_id: str,
    root: str,
    delegator: PartyAnchor,
    delegate: PartyAnchor,
    ts: str,
    witness_ref: str | None = None,
    payload: dict[str, Any] | None = None,
) -> BilateralDelegation:
    """Construct a v3 :class:`BilateralDelegation` (schema_version pinned to v3).

    A thin convenience constructor mirroring the WEFT distributor's v3-stamping:
    every delegation minted through this path carries ``SCHEMA_VERSION_V3``.
    """
    return BilateralDelegation(
        schema_version=SCHEMA_VERSION_V3,
        delegation_id=delegation_id,
        root=root,
        delegator=delegator,
        delegate=delegate,
        ts=ts,
        witness_ref=witness_ref,
        payload=payload or {},
    )
