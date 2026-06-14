# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""EATP-12 vault-binding core types (§4.1/§4.4/§4.5 type surface).

Frozen dataclasses carrying only metadata — **never** secret key material,
reconstructed KEK bytes, or passphrase bytes (EATP-12 §4.1 / `rules/trust-plane-security.md`
MUST NOT §3). The handle-based surface (N12-IN-01) means callers pass a
:class:`VaultKeyHandle` (an opaque reference), not raw bytes; the reconstructed
KEK is consumed inside the trusted module and returned only as an opaque handle
(N12-IN-05).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

_HEX16 = re.compile(r"\A[0-9a-f]{16}\Z")  # 8-byte KCV, lowercase hex
_HEX64 = re.compile(r"\A[0-9a-f]{64}\Z")  # SHA-256 commitment, lowercase hex

__all__ = [
    "HolderId",
    "PassphraseRef",
    "ClearanceContext",
    "VaultKeyHandle",
    "BackupReceipt",
    "RestoreReceipt",
    "RotationReceipt",
]


@dataclass(frozen=True)
class HolderId:
    """A shard-holder identifier drawn from the deployment registry (N12-SH-01).

    Carries only the opaque holder identity string — never shard contents.
    """

    holder_id: str

    def __post_init__(self) -> None:
        if not self.holder_id or not isinstance(self.holder_id, str):
            raise ValueError("holder_id must be a non-empty string")

    def to_dict(self) -> Dict[str, Any]:
        return {"holder_id": self.holder_id}

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "HolderId":
        return cls(holder_id=d["holder_id"])


@dataclass(frozen=True)
class PassphraseRef:
    """A reference to passphrase *provenance* — NOT the passphrase bytes (N12-PP-01).

    ``provenance`` is the value bound into the KEK-identity commitment (e.g.
    ``"vault-derived:v1"``); the actual passphrase bytes are excluded from every
    audit envelope (§4.4.1) and never live on a DTO.
    """

    provenance: str

    def __post_init__(self) -> None:
        if not self.provenance or not isinstance(self.provenance, str):
            raise ValueError("passphrase provenance must be a non-empty string")

    def to_dict(self) -> Dict[str, Any]:
        return {"provenance": self.provenance}

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "PassphraseRef":
        return cls(provenance=d["provenance"])


@dataclass(frozen=True)
class ClearanceContext:
    """The bound authorization context the clearance gate (§4.2) evaluates.

    Carries the principal, the bound role's tenant + domain, and the capability
    tokens — the inputs to N12-CL-01/02/02a/04. No secret material.
    """

    principal: str
    tenant: str
    domain: str
    capabilities: Tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for name in ("principal", "tenant", "domain"):
            v = getattr(self, name)
            if not v or not isinstance(v, str):
                raise ValueError(f"{name} must be a non-empty string")
        if not isinstance(self.capabilities, tuple):
            object.__setattr__(self, "capabilities", tuple(self.capabilities))

    def has_capability(self, token: str) -> bool:
        """Membership check (N12-CL-01/02). Fail-closed: absence → False."""
        return token in self.capabilities

    def to_dict(self) -> Dict[str, Any]:
        return {
            "principal": self.principal,
            "tenant": self.tenant,
            "domain": self.domain,
            "capabilities": list(self.capabilities),
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ClearanceContext":
        return cls(
            principal=d["principal"],
            tenant=d["tenant"],
            domain=d["domain"],
            capabilities=tuple(d.get("capabilities", ())),
        )


@dataclass(frozen=True)
class VaultKeyHandle:
    """An opaque handle to a KEK-class key (N12-IN-01/IN-02).

    The public binding surface accepts this — never raw KEK bytes. It references
    the key by its stable ``key_id`` and pins the captured ``kek_generation``; it
    does NOT carry key material. Per N12-IN-04 the resolved ``key_id`` is recorded
    on the :class:`BackupReceipt` and bound at the registry layer (C2a) — it is
    NOT in the §12.2 commitment pre-image (which is ``vault_id``-keyed to stay
    cross-SDK byte-exact). See :mod:`kailash.trust.vault.commitment` for the
    layering rationale.
    """

    key_id: str
    vault_id: str
    kek_generation: int

    def __post_init__(self) -> None:
        if not self.key_id or not isinstance(self.key_id, str):
            raise ValueError("key_id must be a non-empty string")
        if not self.vault_id or not isinstance(self.vault_id, str):
            raise ValueError("vault_id must be a non-empty string")
        if (
            not isinstance(self.kek_generation, int)
            or isinstance(self.kek_generation, bool)
            or self.kek_generation < 0
        ):
            raise ValueError("kek_generation must be a non-negative int")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "key_id": self.key_id,
            "vault_id": self.vault_id,
            "kek_generation": self.kek_generation,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "VaultKeyHandle":
        return cls(
            key_id=d["key_id"],
            vault_id=d["vault_id"],
            kek_generation=int(d["kek_generation"]),
        )


@dataclass(frozen=True)
class BackupReceipt:
    """The metadata receipt returned by a successful backup (§4.4).

    Carries the commitment + KCV + recorded algorithm + shard topology — the
    offline-verifiable proof of the backup. NO shard ciphertext, NO secret.
    """

    vault_id: str
    kek_generation: int
    kek_commitment_alg: str  # EATP-08 §3.3 registry token (e.g. "eatp-v1")
    kek_identity_commitment: str  # hex SHA-256 (N12-CB-01)
    kcv: str  # 16-hex, key-free domain-separated (N12-CB-04(d))
    k: int
    n: int
    holders: Tuple[str, ...] = ()
    side_channel_hardened: bool = False

    def __post_init__(self) -> None:
        if not _HEX16.match(self.kcv):
            raise ValueError(
                f"kcv must be 16 lowercase-hex chars (8 bytes), got {self.kcv!r}"
            )
        if not _HEX64.match(self.kek_identity_commitment):
            raise ValueError(
                "kek_identity_commitment must be 64 lowercase-hex chars (SHA-256), "
                f"got {self.kek_identity_commitment!r}"
            )
        if not (2 <= self.k <= self.n <= 9):
            raise ValueError(
                f"ritual outside the 2<=k<=n<=9 floor: k={self.k} n={self.n}"
            )
        if not isinstance(self.holders, tuple):
            object.__setattr__(self, "holders", tuple(self.holders))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "vault_id": self.vault_id,
            "kek_generation": self.kek_generation,
            "kek_commitment_alg": self.kek_commitment_alg,
            "kek_identity_commitment": self.kek_identity_commitment,
            "kcv": self.kcv,
            "k": self.k,
            "n": self.n,
            "holders": list(self.holders),
            "side_channel_hardened": self.side_channel_hardened,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "BackupReceipt":
        return cls(
            vault_id=d["vault_id"],
            kek_generation=int(d["kek_generation"]),
            kek_commitment_alg=d["kek_commitment_alg"],
            kek_identity_commitment=d["kek_identity_commitment"],
            kcv=d["kcv"],
            k=int(d["k"]),
            n=int(d["n"]),
            holders=tuple(d.get("holders", ())),
            side_channel_hardened=bool(d.get("side_channel_hardened", False)),
        )


@dataclass(frozen=True)
class RestoreReceipt:
    """The metadata receipt returned by a successful restore (§4.5).

    References the re-established KEK by handle (N12-IN-05 — never plaintext) and
    records the audit-anchor reference + the generation that was restored.
    """

    restored_handle: VaultKeyHandle
    kek_generation: int
    audit_anchor_ref: Optional[str] = None
    forced_stale: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "restored_handle": self.restored_handle.to_dict(),
            "kek_generation": self.kek_generation,
            "audit_anchor_ref": self.audit_anchor_ref,
            "forced_stale": self.forced_stale,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "RestoreReceipt":
        return cls(
            restored_handle=VaultKeyHandle.from_dict(d["restored_handle"]),
            kek_generation=int(d["kek_generation"]),
            audit_anchor_ref=d.get("audit_anchor_ref"),
            forced_stale=bool(d.get("forced_stale", False)),
            metadata=dict(d.get("metadata", {})),
        )


@dataclass(frozen=True)
class RotationReceipt:
    """The metadata receipt returned by a successful rotation (§5).

    Covers BOTH rotation shapes (R1 / Wave 5):

    * **Amicable holder rotation** (N12-RT-01/02/03): ``for_cause=False``,
      ``kek_generation == prior_kek_generation`` (an amicable holder rotation
      does NOT advance the generation — only the shard distribution changes,
      §5.1). ``kek_identity_commitment`` is ``None`` (the commitment binds the
      unchanged ``(vault_id, generation, secret, provenance)`` so the
      already-registered commitment still verifies — no new commitment is
      registered).
    * **For-cause generation-advancing rotation** (N12-SH-04 / N12-RT-06):
      ``for_cause=True``, ``kek_generation == prior_kek_generation + 1`` (the
      for-cause revocation escalates to a KEK rotation that advances the
      generation so the departed holder's retained shards become stale, §5.2).
      ``kek_identity_commitment`` carries the NEW generation's commitment (the
      one registered for ``(vault_id, kek_generation)`` and recorded on the
      ``vault_kek_rotation`` anchor).

    NO shard ciphertext, NO secret — only the post-rotation distribution
    topology (the new ``shard_commitments``, the new ``holders``) and the
    audit-anchor reference. The new shards are produced + distributed inside
    the trusted-module ceremony and ``del``-ed (N12-IN-05); they never ride
    the receipt.
    """

    vault_id: str
    prior_kek_generation: int
    kek_generation: int  # advanced (+1) for for-cause; unchanged for amicable
    for_cause: bool
    k: int
    n: int
    holders: Tuple[str, ...] = ()
    shard_commitments: Tuple[str, ...] = ()
    kek_identity_commitment: Optional[str] = None  # new-gen commitment (for-cause only)
    kek_commitment_alg: Optional[str] = None
    audit_anchor_ref: Optional[str] = None

    def __post_init__(self) -> None:
        if not (2 <= self.k <= self.n <= 9):
            raise ValueError(
                f"ritual outside the 2<=k<=n<=9 floor: k={self.k} n={self.n}"
            )
        if self.for_cause:
            if self.kek_generation != self.prior_kek_generation + 1:
                raise ValueError(
                    "for-cause rotation MUST advance the generation by exactly 1 "
                    f"(N12-SH-04): prior={self.prior_kek_generation} "
                    f"new={self.kek_generation}"
                )
            if self.kek_identity_commitment is None or not _HEX64.match(
                self.kek_identity_commitment
            ):
                raise ValueError(
                    "for-cause rotation MUST carry the new-generation "
                    "kek_identity_commitment (64 lowercase-hex, N12-RT-06); got "
                    f"{self.kek_identity_commitment!r}"
                )
        else:
            if self.kek_generation != self.prior_kek_generation:
                raise ValueError(
                    "amicable holder rotation MUST NOT advance the generation "
                    f"(N12-RT-03): prior={self.prior_kek_generation} "
                    f"new={self.kek_generation}"
                )
        if not isinstance(self.holders, tuple):
            object.__setattr__(self, "holders", tuple(self.holders))
        if not isinstance(self.shard_commitments, tuple):
            object.__setattr__(self, "shard_commitments", tuple(self.shard_commitments))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "vault_id": self.vault_id,
            "prior_kek_generation": self.prior_kek_generation,
            "kek_generation": self.kek_generation,
            "for_cause": self.for_cause,
            "k": self.k,
            "n": self.n,
            "holders": list(self.holders),
            "shard_commitments": list(self.shard_commitments),
            "kek_identity_commitment": self.kek_identity_commitment,
            "kek_commitment_alg": self.kek_commitment_alg,
            "audit_anchor_ref": self.audit_anchor_ref,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "RotationReceipt":
        return cls(
            vault_id=d["vault_id"],
            prior_kek_generation=int(d["prior_kek_generation"]),
            kek_generation=int(d["kek_generation"]),
            for_cause=bool(d["for_cause"]),
            k=int(d["k"]),
            n=int(d["n"]),
            holders=tuple(d.get("holders", ())),
            shard_commitments=tuple(d.get("shard_commitments", ())),
            kek_identity_commitment=d.get("kek_identity_commitment"),
            kek_commitment_alg=d.get("kek_commitment_alg"),
            audit_anchor_ref=d.get("audit_anchor_ref"),
        )
