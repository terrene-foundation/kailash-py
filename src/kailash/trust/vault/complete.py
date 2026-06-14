# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""EATP-12 Complete-level optional knobs (X1 / Wave 5, §4.2 / §4.3).

These are **Complete-level** enhancements — OPTIONAL at Conformant, gated behind
the :class:`ConformanceLevel` flag. A deployment running at
:attr:`ConformanceLevel.CONFORMANT` never invokes them and the Conformant audit
pre-image is byte-unchanged; a deployment running at
:attr:`ConformanceLevel.COMPLETE` composes these gates into the backup/restore
ceremony and the tokens land inside the signed ``event_payload``
(``content_signing_bytes`` per N12-AU-03), so a missing/forged token is
cryptographically detectable.

Three knobs (the 4 Complete-optional conformance IDs):

* **N12-CL-03 / N12-CL-03(c) — governance-approver HELD action.** A deployment
  MAY require an independent approver in addition to the caller's capability.
  :func:`verify_governance_approval` enforces: (a) the approver holds a distinct
  ``vault:approve`` token scoped to the vault's tenant/domain; (b) approver
  ``!=`` requester (distinct principal AND distinct ``delegate_id`` — self-approval
  is non-conforming); (c) the approver's signed approval token verifies over the
  canonical approval pre-image; (d) **fail-closed** — any failure raises
  ``missing-clearance``. The returned payload is embedded in the restore anchor's
  ``event_payload`` (covered by ``content_signing_bytes``). Mandatory ONLY for the
  high-risk paths the spec names (raw-bytes restore N12-IN-03, forced-stale
  N12-SG-03, cooling-off N12-CL-04); OPTIONAL elsewhere.

* **N12-CL-05 — backup ceremony witness.** At Complete the generation/backup path
  MUST require an independent witness — a distinct ``vault:witness``-holding
  principal, ``!=`` requester AND ``!=`` any configured approver — whose identity
  + signed witness token are bound into the ``vault_key_backup`` ``event_payload``.
  :func:`verify_ceremony_witness` enforces it; a self-witness fails.

* **N12-SH-02 — per-holder wrapping.** A shard MAY be wrapped under a per-holder
  passphrase before distribution so a departed holder's shard can be revoked
  without re-running the full ritual. :func:`wrap_shard_for_holder` /
  :func:`unwrap_shard_for_holder` realize the passphrase variant via the HMAC
  primitive; a :class:`HolderRevocationRegistry`-revoked holder's shard fails
  ``revoked-holder`` on unwrap. SHOULD accompany a for-cause revocation, which
  MUST ALSO advance the generation per N12-SH-04 (the R1 surface).

The signature primitive for approval/witness tokens is INJECTED as a
``verify_token`` callable (the deployment's verifier — a real
:class:`~kailash.delegate.verifier.Ed25519Verifier` in Tier-2), so the gate is
verifier-agnostic and never embeds a key.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Dict, Optional, Set

from kailash.trust._json import canonical_json_dumps
from kailash.trust.vault.clearance import domain_covers
from kailash.trust.vault.errors import N12FT01Code, VaultBindingError
from kailash.trust.vault.input_gates import ResolvedKek
from kailash.trust.vault.types import ClearanceContext

logger = logging.getLogger(__name__)

__all__ = [
    "ConformanceLevel",
    "APPROVE_CAPABILITY",
    "WITNESS_CAPABILITY",
    "GovernanceApproval",
    "CeremonyWitness",
    "approval_pre_image",
    "witness_pre_image",
    "verify_governance_approval",
    "verify_ceremony_witness",
    "HolderRevocationRegistry",
    "wrap_shard_for_holder",
    "unwrap_shard_for_holder",
]

#: The capability the governance-approver MUST hold (N12-CL-03(a)) — distinct
#: from ``vault:restore``/``vault:backup``/``vault:rotate``.
APPROVE_CAPABILITY: str = "vault:approve"

#: The capability the backup ceremony witness MUST hold (N12-CL-05).
WITNESS_CAPABILITY: str = "vault:witness"

#: The domain-separated wrap MAC prefix (SH-02 passphrase variant). Distinct
#: from the commitment/KCV domains so a wrap MAC can never collide with them.
_WRAP_DOMAIN_SEP: str = "EATP-12/holder-wrap/v1"


class ConformanceLevel(str, Enum):
    """The deployment conformance level (N12 Complete-level gate).

    ``CONFORMANT`` runs only the Conformant-mandatory gates; the Complete-level
    knobs in this module are NOT invoked and the audit pre-image is unchanged.
    ``COMPLETE`` composes the approver (N12-CL-03), witness (N12-CL-05), and
    per-holder wrapping (N12-SH-02) knobs into the ceremony.
    """

    CONFORMANT = "conformant"
    COMPLETE = "complete"


# ---------------------------------------------------------------------------
# Canonical pre-images for the approval / witness tokens
# ---------------------------------------------------------------------------


def approval_pre_image(
    *,
    vault_id: str,
    kek_generation: int,
    operation: str,
    requester_principal: str,
) -> bytes:
    """Canonical pre-image the approver signs (N12-CL-03(c)).

    Binds the approval to the SPECIFIC operation (e.g. ``"restore"`` /
    ``"restore-forced-stale"``), vault, generation, and requester — so an
    approval cannot be replayed for a different operation or requester. The
    approver's signature over THIS pre-image is the ``approval_signature``
    embedded in the anchor ``event_payload``.
    """
    return canonical_json_dumps(
        {
            "domain_sep": "EATP-12/governance-approval/v1",
            "kek_generation": kek_generation,
            "operation": operation,
            "requester_principal": requester_principal,
            "vault_id": vault_id,
        }
    ).encode("utf-8")


def witness_pre_image(
    *,
    vault_id: str,
    kek_generation: int,
    operation: str,
    requester_principal: str,
) -> bytes:
    """Canonical pre-image the witness signs (N12-CL-05). See :func:`approval_pre_image`."""
    return canonical_json_dumps(
        {
            "domain_sep": "EATP-12/ceremony-witness/v1",
            "kek_generation": kek_generation,
            "operation": operation,
            "requester_principal": requester_principal,
            "vault_id": vault_id,
        }
    ).encode("utf-8")


# ---------------------------------------------------------------------------
# Approval / witness DTOs (embedded in the signed event_payload)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GovernanceApproval:
    """An independent governance-approver's HELD authorization (N12-CL-03).

    Carries the approver's identity (principal + ``delegate_id``) and the
    approver's signature over the :func:`approval_pre_image`. The whole DTO is
    embedded (via :meth:`to_payload`) into the restore anchor's ``event_payload``,
    so it is covered by ``content_signing_bytes`` — a missing or forged approval
    is cryptographically detectable (N12-CL-03(c)).
    """

    approver_principal: str
    approver_delegate_id: str
    approval_signature: str  # hex, the approver's sig over approval_pre_image

    def to_payload(self) -> Dict[str, Any]:
        """The sub-object embedded under ``event_payload["approval"]``."""
        return {
            "approver_principal": self.approver_principal,
            "approver_delegate_id": self.approver_delegate_id,
            "approval_signature": self.approval_signature,
        }


@dataclass(frozen=True)
class CeremonyWitness:
    """An independent backup-ceremony witness (N12-CL-05). Mirrors GovernanceApproval."""

    witness_principal: str
    witness_delegate_id: str
    witness_signature: str  # hex, the witness's sig over witness_pre_image

    def to_payload(self) -> Dict[str, Any]:
        """The sub-object embedded under ``event_payload["witness"]``."""
        return {
            "witness_principal": self.witness_principal,
            "witness_delegate_id": self.witness_delegate_id,
            "witness_signature": self.witness_signature,
        }


# ---------------------------------------------------------------------------
# N12-CL-03 — governance-approver verification (fail-closed)
# ---------------------------------------------------------------------------


def verify_governance_approval(
    approval: GovernanceApproval,
    *,
    vault_id: str,
    requester_principal: str,
    requester_delegate_id: str,
    approver_clearance: ClearanceContext,
    resolved: ResolvedKek,
    operation: str,
    verify_token: Callable[[bytes, str, str], bool],
) -> Dict[str, Any]:
    """Verify a governance-approver HELD authorization (N12-CL-03). Fail-closed.

    Enforces, in order (each failure → ``missing-clearance``, fail-closed per
    N12-CL-03(d)):

    1. **(a) capability** — ``approver_clearance`` holds ``vault:approve``;
    2. **(a) tenant/domain scope** — the approver's bound tenant equals the
       vault's tenant AND the approver's domain COVERS the vault's domain (the
       same fail-closed tenant→domain cascade B1's CL-02a uses);
    3. **(b) distinctness** — approver principal ``!=`` requester principal AND
       approver ``delegate_id`` ``!=`` requester ``delegate_id`` (self-approval,
       even via a second credential under the same principal, is non-conforming);
    4. **(c) signed token** — ``verify_token`` verifies ``approval_signature``
       over :func:`approval_pre_image` under the approver's ``delegate_id``.

    Args:
        approval: The approver's identity + signed approval token.
        requester_principal: The acting (restore) principal.
        requester_delegate_id: The acting principal's signing ``delegate_id``.
        approver_clearance: The approver's bound authorization context (carries
            ``vault:approve`` + the approver's tenant/domain).
        resolved: The resolved KEK (source of the vault's tenant/domain + gen).
        operation: The operation being approved (bound into the pre-image).
        verify_token: ``(pre_image, signature_hex, delegate_id) -> bool`` — the
            deployment verifier (a real ``Ed25519Verifier`` in Tier-2) checking
            the approver's signature over the approval pre-image.

    Returns:
        The approval payload (``approval.to_payload()``) to embed under
        ``event_payload["approval"]`` (covered by ``content_signing_bytes``).

    Raises:
        VaultBindingError: ``MISSING_CLEARANCE`` on any failure (fail-closed).
    """
    if not isinstance(approver_clearance, ClearanceContext):
        raise VaultBindingError(
            N12FT01Code.MISSING_CLEARANCE,
            "approver_clearance MUST be a ClearanceContext (N12-CL-03); got "
            f"{type(approver_clearance).__name__}",
            details={"required_capability": APPROVE_CAPABILITY},
        )

    # (a) capability.
    if not approver_clearance.has_capability(APPROVE_CAPABILITY):
        raise VaultBindingError(
            N12FT01Code.MISSING_CLEARANCE,
            "governance approver lacks the vault:approve capability " "(N12-CL-03(a))",
            details={"required_capability": APPROVE_CAPABILITY},
        )

    # (a) tenant/domain scope (fail-closed tenant FIRST, then domain).
    if approver_clearance.tenant != resolved.vault_tenant:
        raise VaultBindingError(
            N12FT01Code.MISSING_CLEARANCE,
            "approver tenant does not match the vault's tenant "
            "(N12-CL-03(a), fail-closed: tenant checked first)",
            details={"required_capability": APPROVE_CAPABILITY},
        )
    if not domain_covers(approver_clearance.domain, resolved.vault_domain):
        raise VaultBindingError(
            N12FT01Code.MISSING_CLEARANCE,
            "approver domain does not cover the vault's domain (N12-CL-03(a))",
            details={"required_capability": APPROVE_CAPABILITY},
        )

    # (b) distinctness — forbid self-approval on BOTH axes.
    if approval.approver_principal == requester_principal:
        raise VaultBindingError(
            N12FT01Code.MISSING_CLEARANCE,
            "self-approval is non-conforming: approver principal == requester "
            "(N12-CL-03(b))",
            details={"required_capability": APPROVE_CAPABILITY},
        )
    if approval.approver_delegate_id == requester_delegate_id:
        raise VaultBindingError(
            N12FT01Code.MISSING_CLEARANCE,
            "self-approval is non-conforming: approver delegate_id == requester "
            "delegate_id (N12-CL-03(b) — a second credential under the same "
            "actor does not satisfy the distinctness check)",
            details={"required_capability": APPROVE_CAPABILITY},
        )

    # (c) the approver's signed token MUST verify over the canonical pre-image.
    pre_image = approval_pre_image(
        vault_id=vault_id,
        kek_generation=resolved.kek_generation,
        operation=operation,
        requester_principal=requester_principal,
    )
    if not verify_token(
        pre_image, approval.approval_signature, approval.approver_delegate_id
    ):
        raise VaultBindingError(
            N12FT01Code.MISSING_CLEARANCE,
            "governance approval signature does not verify over the approval "
            "pre-image (N12-CL-03(c)); a missing/forged approval is rejected "
            "fail-closed (N12-CL-03(d))",
            details={"required_capability": APPROVE_CAPABILITY},
        )

    logger.info(
        "vault.complete.approval.ok",
        extra={
            "approver_principal": approval.approver_principal,
            "operation": operation,
            "kek_generation": resolved.kek_generation,
        },
    )
    return approval.to_payload()


# ---------------------------------------------------------------------------
# N12-CL-05 — backup ceremony witness verification (fail-closed)
# ---------------------------------------------------------------------------


def verify_ceremony_witness(
    witness: CeremonyWitness,
    *,
    vault_id: str,
    requester_principal: str,
    requester_delegate_id: str,
    resolved: ResolvedKek,
    operation: str,
    verify_token: Callable[[bytes, str, str], bool],
    witness_clearance: ClearanceContext,
    approver_principal: Optional[str] = None,
    approver_delegate_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Verify a backup-ceremony witness (N12-CL-05). Fail-closed.

    Mirrors :func:`verify_governance_approval` for the backup/generation path:
    requires ``vault:witness`` scoped to the vault tenant/domain, the witness
    DISTINCT from the requester AND from any configured approver (on both
    principal and ``delegate_id``), and the witness's signed token verifying over
    :func:`witness_pre_image`. A self-witness fails.

    Returns the witness payload to embed under ``event_payload["witness"]``.

    Raises:
        VaultBindingError: ``MISSING_CLEARANCE`` on any failure (fail-closed).
    """
    if not isinstance(witness_clearance, ClearanceContext):
        raise VaultBindingError(
            N12FT01Code.MISSING_CLEARANCE,
            "witness_clearance MUST be a ClearanceContext (N12-CL-05); got "
            f"{type(witness_clearance).__name__}",
            details={"required_capability": WITNESS_CAPABILITY},
        )

    if not witness_clearance.has_capability(WITNESS_CAPABILITY):
        raise VaultBindingError(
            N12FT01Code.MISSING_CLEARANCE,
            "ceremony witness lacks the vault:witness capability (N12-CL-05)",
            details={"required_capability": WITNESS_CAPABILITY},
        )

    if witness_clearance.tenant != resolved.vault_tenant:
        raise VaultBindingError(
            N12FT01Code.MISSING_CLEARANCE,
            "witness tenant does not match the vault's tenant (N12-CL-05, "
            "fail-closed: tenant first)",
            details={"required_capability": WITNESS_CAPABILITY},
        )
    if not domain_covers(witness_clearance.domain, resolved.vault_domain):
        raise VaultBindingError(
            N12FT01Code.MISSING_CLEARANCE,
            "witness domain does not cover the vault's domain (N12-CL-05)",
            details={"required_capability": WITNESS_CAPABILITY},
        )

    # Distinct from requester (self-witness fails) AND from any approver.
    if witness.witness_principal == requester_principal:
        raise VaultBindingError(
            N12FT01Code.MISSING_CLEARANCE,
            "self-witness is non-conforming: witness principal == requester "
            "(N12-CL-05)",
            details={"required_capability": WITNESS_CAPABILITY},
        )
    if witness.witness_delegate_id == requester_delegate_id:
        raise VaultBindingError(
            N12FT01Code.MISSING_CLEARANCE,
            "self-witness is non-conforming: witness delegate_id == requester "
            "delegate_id (N12-CL-05)",
            details={"required_capability": WITNESS_CAPABILITY},
        )
    if (
        approver_principal is not None
        and witness.witness_principal == approver_principal
    ):
        raise VaultBindingError(
            N12FT01Code.MISSING_CLEARANCE,
            "witness principal == configured approver (N12-CL-05: witness MUST "
            "be independent of the approver)",
            details={"required_capability": WITNESS_CAPABILITY},
        )
    if (
        approver_delegate_id is not None
        and witness.witness_delegate_id == approver_delegate_id
    ):
        raise VaultBindingError(
            N12FT01Code.MISSING_CLEARANCE,
            "witness delegate_id == configured approver delegate_id (N12-CL-05)",
            details={"required_capability": WITNESS_CAPABILITY},
        )

    pre_image = witness_pre_image(
        vault_id=vault_id,
        kek_generation=resolved.kek_generation,
        operation=operation,
        requester_principal=requester_principal,
    )
    if not verify_token(
        pre_image, witness.witness_signature, witness.witness_delegate_id
    ):
        raise VaultBindingError(
            N12FT01Code.MISSING_CLEARANCE,
            "ceremony witness signature does not verify over the witness "
            "pre-image (N12-CL-05); a missing/forged witness is rejected "
            "fail-closed",
            details={"required_capability": WITNESS_CAPABILITY},
        )

    logger.info(
        "vault.complete.witness.ok",
        extra={
            "witness_principal": witness.witness_principal,
            "operation": operation,
            "kek_generation": resolved.kek_generation,
        },
    )
    return witness.to_payload()


# ---------------------------------------------------------------------------
# N12-SH-02 — per-holder wrapping (passphrase variant via HMAC)
# ---------------------------------------------------------------------------


class HolderRevocationRegistry:
    """Per-vault registry of revoked holder ids (N12-SH-02 revocation).

    When per-holder wrapping is used, revoking a departed holder records the
    holder id here; a subsequent :func:`unwrap_shard_for_holder` presenting that
    holder's shard fails ``revoked-holder``. The durable record is the audited
    holder-revocation event; the in-memory set is the conformant shape for this
    wave + the Tier-2 tests (mirrors the C2a registry disposition).
    """

    def __init__(self) -> None:
        self._revoked: Set[str] = set()

    def revoke(self, holder_id: str) -> None:
        """Record ``holder_id`` as revoked (N12-SH-02). Idempotent."""
        if not isinstance(holder_id, str) or not holder_id:
            raise ValueError("holder_id MUST be a non-empty string")
        self._revoked.add(holder_id)
        logger.warning("vault.complete.holder_revoked", extra={"holder_id": holder_id})

    def is_revoked(self, holder_id: str) -> bool:
        """Membership check. Fail-closed: a malformed id → not revoked here."""
        return holder_id in self._revoked


def _wrap_mac(holder_id: str, holder_passphrase: bytes, serialized_shard: str) -> str:
    """Domain-separated HMAC tag binding the holder id + shard under the passphrase."""
    msg = canonical_json_dumps(
        {
            "domain_sep": _WRAP_DOMAIN_SEP,
            "holder_id": holder_id,
            "serialized_shard": serialized_shard,
        }
    ).encode("utf-8")
    return hmac.new(holder_passphrase, msg, hashlib.sha256).hexdigest()


def wrap_shard_for_holder(
    serialized_shard: str,
    *,
    holder_id: str,
    holder_passphrase: bytes,
) -> Dict[str, str]:
    """Wrap a serialized shard under a per-holder passphrase (N12-SH-02).

    The passphrase variant binds the shard to the holder via a domain-separated
    HMAC tag (the HMAC primitive the spec names). The wrapped object carries the
    holder id, the serialized shard, and the tag; :func:`unwrap_shard_for_holder`
    re-derives the tag under the holder's passphrase and rejects a tamper /
    wrong-passphrase / revoked-holder. The cross-SDK reproducibility surface is
    the UNWRAPPED ``serialized_shard`` (§7), not the wrap tag.
    """
    if not isinstance(holder_passphrase, bytes) or not holder_passphrase:
        raise ValueError("holder_passphrase MUST be non-empty bytes (N12-SH-02)")
    return {
        "holder_id": holder_id,
        "serialized_shard": serialized_shard,
        "wrap_mac": _wrap_mac(holder_id, holder_passphrase, serialized_shard),
    }


def unwrap_shard_for_holder(
    wrapped: Dict[str, str],
    *,
    holder_passphrase: bytes,
    revocation_registry: Optional[HolderRevocationRegistry] = None,
) -> str:
    """Unwrap a per-holder-wrapped shard (N12-SH-02). Fail-closed.

    Returns the serialized shard iff (a) the holder is NOT revoked, and (b) the
    HMAC tag re-derived under ``holder_passphrase`` matches (constant-time). A
    revoked holder fails ``revoked-holder``; a tamper / wrong passphrase fails
    ``corrupted-shard`` (the integrity-only code, never conflated with the
    foreign-shard ``unknown-shard``).
    """
    holder_id = wrapped.get("holder_id", "")
    serialized_shard = wrapped.get("serialized_shard", "")
    presented = wrapped.get("wrap_mac", "")

    if revocation_registry is not None and revocation_registry.is_revoked(holder_id):
        raise VaultBindingError(
            N12FT01Code.REVOKED_HOLDER,
            f"holder {holder_id!r} is revoked (N12-SH-02): the wrapped shard is "
            "no longer unwrappable; subsequent reconstruction MUST fail "
            "revoked-holder",
            details={"holder_id": holder_id},
        )

    expected = _wrap_mac(holder_id, holder_passphrase, serialized_shard)
    if not hmac.compare_digest(expected, presented):
        # Integrity ONLY (tamper / wrong passphrase) — NOT foreign-shard.
        raise VaultBindingError(
            N12FT01Code.CORRUPTED_SHARD,
            "per-holder wrap MAC does not verify (N12-SH-02): tampered wrap or "
            "wrong holder passphrase",
            details={"holder_id": holder_id},
        )
    return serialized_shard
