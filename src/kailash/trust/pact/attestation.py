# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""ClearanceAttestation -- posture-gated re-identification for EATP v3 (#1592).

A :class:`ClearanceAttestation` binds a *pseudonymous* subject handle
(``subject_ref``) to the confidentiality clearance required to *re-identify* it
-- to resolve the handle back to the real subject. Re-identification is
**posture-gated**: a requester may re-identify the subject ONLY when their trust
posture's clearance ceiling MEETS the attestation's ``required_clearance``.

The clearance ordinal is the existing :class:`~kailash.trust.ConfidentialityLevel`
(``C0`` ``PUBLIC`` < ``C1`` ``RESTRICTED`` < ``C2`` ``CONFIDENTIAL`` < ``C3``
``SECRET`` < ``C4`` ``TOP_SECRET``) -- this module REUSES that ordinal (defined
in ``kailash.trust.reasoning.traces``) and does NOT define a parallel one. Note
the inverted-pair wire tokens the ordinal pins: ``"restricted"`` is ``C1`` and
``"confidential"`` is ``C2`` (``restricted < confidential``), which the
conformance vectors byte-pin.

The posture -> clearance-ceiling mapping REUSES ``POSTURE_CEILING`` from
:mod:`kailash.trust.pact.clearance` (the same ceiling that caps
:func:`~kailash.trust.pact.clearance.effective_clearance`). So re-identification
is permitted iff ``POSTURE_CEILING[requester_posture] >= required_clearance`` --
framework-first, no parallel gating logic. :meth:`assert_reidentification`
fails CLOSED (raises :class:`ReidentificationDeniedError`) below the gate.

Follows the EATP dataclass conventions (``eatp.md``).
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from typing import Any

from kailash.trust import ConfidentialityLevel, TrustPosture
from kailash.trust._jcs import jcs_encode
from kailash.trust.pact.audit import SCHEMA_VERSION_V3
from kailash.trust.pact.clearance import POSTURE_CEILING
from kailash.trust.pact.exceptions import PactError

logger = logging.getLogger(__name__)

__all__ = [
    "ClearanceAttestation",
    "ClearanceAttestationError",
    "ReidentificationDeniedError",
    "posture_can_reidentify",
]


class ClearanceAttestationError(PactError):
    """Base class for clearance-attestation errors.

    Inherits ``PactError`` (structured ``.details`` dict) so failures are caught
    by the PACT trust-layer catch blocks rather than surfacing as unstructured
    crashes.
    """


class ReidentificationDeniedError(ClearanceAttestationError):
    """Raised when a requester's posture is below the re-identification gate.

    Fail-closed: a requester whose posture ceiling does not meet the
    attestation's ``required_clearance`` is DENIED re-identification -- the
    absence of sufficient posture never silently permits it.
    """


def posture_can_reidentify(
    requester_posture: TrustPosture,
    required_clearance: ConfidentialityLevel,
) -> bool:
    """Return ``True`` iff ``requester_posture`` clears ``required_clearance``.

    Posture-gated re-identification: the requester's posture-ceiling clearance
    (``POSTURE_CEILING[requester_posture]``) MUST be at least the required
    clearance, compared on the shared ``ConfidentialityLevel`` ordinal.

    An unknown posture (absent from ``POSTURE_CEILING``) fails CLOSED (returns
    ``False``) rather than raising -- the caller's gate is a boolean, not an
    exception surface.
    """
    ceiling = POSTURE_CEILING.get(requester_posture)
    if ceiling is None:
        logger.warning(
            "attestation.reidentify.unknown_posture",
            extra={"posture": getattr(requester_posture, "value", requester_posture)},
        )
        return False
    return ceiling >= required_clearance


@dataclass(frozen=True)
class ClearanceAttestation:
    """A posture-gated re-identification attestation with a citable JCS hash.

    Attributes:
        schema_version: The #1590 schema discriminator (default ``"v3"``).
        attestation_id: Stable identifier for this attestation.
        subject_ref: The PSEUDONYMOUS subject handle (never the real identity).
        required_clearance: The :class:`~kailash.trust.ConfidentialityLevel` a
            requester's posture ceiling MUST meet to re-identify the subject.
        ts: ISO-8601 timestamp of the attestation.
        attested_by_role_address: The D/T/R address that issued the attestation.
        payload: Structured, attestation-specific data (JSON-native / typed-scalar).
    """

    schema_version: str
    attestation_id: str
    subject_ref: str
    required_clearance: ConfidentialityLevel
    ts: str
    attested_by_role_address: str
    payload: dict[str, Any] = field(default_factory=dict)

    def can_reidentify(self, requester_posture: TrustPosture) -> bool:
        """Return ``True`` iff ``requester_posture`` may re-identify the subject."""
        return posture_can_reidentify(requester_posture, self.required_clearance)

    def assert_reidentification(self, requester_posture: TrustPosture) -> None:
        """Raise :class:`ReidentificationDeniedError` if below the posture gate.

        Fail-closed: re-identification is DENIED unless the requester's posture
        ceiling meets ``required_clearance``.
        """
        if not self.can_reidentify(requester_posture):
            ceiling = POSTURE_CEILING.get(requester_posture)
            raise ReidentificationDeniedError(
                f"Re-identification denied for attestation "
                f"{self.attestation_id!r}: requester posture "
                f"{getattr(requester_posture, 'value', requester_posture)!r} "
                f"(ceiling "
                f"{getattr(ceiling, 'value', None)!r}) does not meet required "
                f"clearance {self.required_clearance.value!r}.",
                details={
                    "attestation_id": self.attestation_id,
                    "requester_posture": getattr(
                        requester_posture, "value", str(requester_posture)
                    ),
                    "posture_ceiling": getattr(ceiling, "value", None),
                    "required_clearance": self.required_clearance.value,
                },
            )

    def to_dict(self) -> dict[str, Any]:
        """Serialize the envelope to a JSON-native dict.

        ``required_clearance`` serializes as its wire value (e.g. ``"secret"``).
        """
        return {
            "schema_version": self.schema_version,
            "attestation_id": self.attestation_id,
            "subject_ref": self.subject_ref,
            "required_clearance": self.required_clearance.value,
            "ts": self.ts,
            "attested_by_role_address": self.attested_by_role_address,
            "payload": self.payload,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ClearanceAttestation:
        """Deserialize STRICTLY from a dict.

        Raises:
            ClearanceAttestationError: if a required field is missing.
            ValueError: if ``required_clearance`` is not a valid
                :class:`~kailash.trust.ConfidentialityLevel` wire value.
        """
        for required in (
            "schema_version",
            "attestation_id",
            "subject_ref",
            "required_clearance",
            "ts",
            "attested_by_role_address",
        ):
            if required not in data:
                raise ClearanceAttestationError(
                    f"ClearanceAttestation.from_dict: missing required field "
                    f"{required!r}",
                    details={"missing_field": required},
                )
        return cls(
            schema_version=data["schema_version"],
            attestation_id=data["attestation_id"],
            subject_ref=data["subject_ref"],
            required_clearance=ConfidentialityLevel(data["required_clearance"]),
            ts=data["ts"],
            attested_by_role_address=data["attested_by_role_address"],
            payload=data.get("payload", {}),
        )

    def canonical_json(self) -> str:
        """Return the RFC 8785 (JCS) canonical JSON string of the envelope.

        Reuses the #1590 JCS keystone; a ``NaN`` / ``Infinity`` in ``payload``
        fails CLOSED here before it can enter a citable pre-image.
        """
        return jcs_encode(self.to_dict())

    def content_hash(self) -> str:
        """Return ``"sha256:<hex>"`` -- the citable content hash of the envelope."""
        encoded = self.canonical_json().encode("utf-8")
        return "sha256:" + hashlib.sha256(encoded).hexdigest()


def new_clearance_attestation(
    *,
    attestation_id: str,
    subject_ref: str,
    required_clearance: ConfidentialityLevel,
    ts: str,
    attested_by_role_address: str,
    payload: dict[str, Any] | None = None,
) -> ClearanceAttestation:
    """Construct a v3 :class:`ClearanceAttestation` (schema_version pinned to v3)."""
    return ClearanceAttestation(
        schema_version=SCHEMA_VERSION_V3,
        attestation_id=attestation_id,
        subject_ref=subject_ref,
        required_clearance=required_clearance,
        ts=ts,
        attested_by_role_address=attested_by_role_address,
        payload=payload or {},
    )
