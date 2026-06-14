# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""EATP-12 vault-binding input surface — resolver boundary + entry gates (W2-I1).

This module owns the **trusted-module boundary** the handle-based binding
surface composes (issue #1312, shard W2-I1). The public
:func:`kailash.trust.vault.backup.back_up_vault_key` /
:func:`~kailash.trust.vault.backup.restore_vault_key` accept a
:class:`~kailash.trust.vault.types.VaultKeyHandle` (N12-IN-01) — **never** raw
KEK bytes by default — and resolve the KEK INTERNALLY through an injected
:class:`VaultKeyResolver`. The resolver is the deployment-supplied trusted key
store (a vault adapter); a test injects a deterministic in-test resolver
returning known bytes (NOT a production fake — it is the deployment-supplied
trusted resolver per §3.4 / #630).

Conformance IDs owned here (EATP-12 §4.1 / §3.3):

- **N12-IN-01** — handle-based primary input; raw KEK bytes MUST NOT cross the
  public API by default. The resolver is the only place KEK bytes appear.
- **N12-IN-02** — the resolved key MUST be ``KeyClass.KEK``-tagged; a
  DATA-class / non-KEK handle → ``not-a-kek`` BEFORE any sharding.
- **N12-IN-03** — the raw-bytes escape hatch is DISABLED by default, gated
  behind an explicit build/deploy flag (default OFF). Flag absent + raw-bytes
  invocation → ``escape-hatch-disabled``.
- **N12-IN-05** — the resolved KEK is consumed inside the trusted module and
  ``del``-ed in a ``finally`` block; it is returned only as an opaque
  handle/receipt ref, never as bytes. No plaintext in any return/log/anchor.
- **N12-TH-01** — ritual floor ``2 <= k <= n <= 9`` (the vault floor is
  STRICTER than the wrapper's ``threshold>=1``); rejected BEFORE key
  resolution with ``invalid-ritual``.
- **N12-CRY-PIN(d)** — escape-hatch secret length ∈ {16, 32} bytes (128/256
  bits), else ``invalid-secret-length`` BEFORE the wrapper call.
- **N12-CRY-PIN(e)** — CSPRNG-only: the public path carries NO caller-seedable
  entropy parameter (``EntropySource`` is reserved, NOT on the frozen surface).
  Enforced structurally by the public signatures (no entropy/seed kwarg).

The resolver returns a :class:`ResolvedKek` carrying the KEK master-secret
bytes + ``key_class`` + ``kek_generation`` + ``key_id`` + passphrase
provenance. The caller (backup/restore) consumes ``.master_secret`` then calls
:meth:`ResolvedKek.zeroize` in a ``finally`` block (N12-IN-05).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from kailash.trust.key_manager import KeyClass
from kailash.trust.vault.errors import N12FT01Code, VaultBindingError
from kailash.trust.vault.shamir import ShamirRitual
from kailash.trust.vault.types import ClearanceContext, VaultKeyHandle

logger = logging.getLogger(__name__)

__all__ = [
    "VAULT_THRESHOLD_FLOOR_MIN",
    "VAULT_TOTAL_SHARDS_CEILING",
    "VALID_SECRET_BYTE_LENGTHS",
    "BACKUP_CAPABILITY",
    "RESTORE_CAPABILITY",
    "ResolvedKek",
    "VaultKeyResolver",
    "master_secret_bits",
    "require_clearance",
    "require_ritual_floor",
    "require_holders_supplied",
    "require_kek_class",
    "require_escape_hatch_enabled",
    "require_secret_length",
]


# ---------------------------------------------------------------------------
# Pinned constants (N12-TH-01 / N12-CRY-PIN(d))
# ---------------------------------------------------------------------------

#: N12-TH-01 — the vault threshold floor minimum (k >= 2). The wrapper allows
#: threshold>=1; the vault floor is STRICTER. 1-of-n / 1-of-1 forbidden at ALL
#: levels (a single shard reconstructs unilaterally — zero threshold
#: protection).
VAULT_THRESHOLD_FLOOR_MIN: int = 2

#: N12-TH-01 — the vault total-shards ceiling (n <= 9). Stricter than the
#: SLIP-0039 4-bit member-index limit of 16; the vault governance floor caps
#: at 9.
VAULT_TOTAL_SHARDS_CEILING: int = 9

#: N12-CRY-PIN(d) — the pinned SLIP-0039 master-secret byte lengths
#: (128-bit / 256-bit). The escape-hatch path MUST reject any other length
#: BEFORE calling the wrapper.
VALID_SECRET_BYTE_LENGTHS: frozenset[int] = frozenset({16, 32})

#: The capability token the clearance gate checks for a backup (N12-CL-01/02).
BACKUP_CAPABILITY: str = "vault:backup"

#: The capability token the clearance gate checks for a restore (N12-CL-01/02).
RESTORE_CAPABILITY: str = "vault:restore"


def master_secret_bits(secret: bytes) -> int:
    """Return the bit-length of a pinned-length master secret (N12-CRY-PIN(d)).

    The value recorded in ``slip39_params.master_secret_bits`` on the backup
    anchor (passed to D2's :func:`~kailash.trust.vault.anchors.build_backup_anchor`).
    Only the pinned lengths (16 → 128, 32 → 256) are valid; any other length
    is a programming error (the caller MUST have run
    :func:`require_secret_length` first).
    """
    n = len(secret)
    if n not in VALID_SECRET_BYTE_LENGTHS:
        raise VaultBindingError(
            N12FT01Code.INVALID_SECRET_LENGTH,
            f"master_secret_bits: secret length {n} bytes is not a pinned "
            f"SLIP-0039 length (N12-CRY-PIN(d)); valid: "
            f"{sorted(VALID_SECRET_BYTE_LENGTHS)} bytes",
            details={"length_bytes": n},
        )
    return n * 8


# ---------------------------------------------------------------------------
# ResolvedKek — the trusted-module resolution result (N12-IN-05)
# ---------------------------------------------------------------------------


@dataclass
class ResolvedKek:
    """The result of resolving a :class:`VaultKeyHandle` to KEK material.

    NOT frozen and NOT a wire DTO: this object carries the live
    ``master_secret`` KEK bytes inside the trusted module ONLY, for the
    duration of one backup/restore call. It MUST NEVER be serialized, logged,
    returned across the public API, or placed on a receipt/anchor (N12-IN-05).
    The caller consumes ``.master_secret`` then calls :meth:`zeroize` in a
    ``finally`` block; ``to_dict``/``from_dict`` are deliberately NOT provided
    (this is not a metadata DTO — it holds plaintext key material).

    Attributes:
        master_secret: The resolved KEK master-secret bytes (16 or 32 bytes for
            the pinned SLIP-0039 lengths). Plaintext — consume-and-``del``.
        key_class: The resolved key's class. MUST be :attr:`KeyClass.KEK`
            (N12-IN-02); a DATA-class key is rejected before sharding.
        kek_generation: The captured generation bound into the commitment
            (N12-SG-01). Authoritative for this resolution.
        key_id: The resolved KEK's stable key-id (N12-IN-04), recorded on the
            ``BackupReceipt`` and bound at the registry layer (C2a). NOT secret.
        passphrase_provenance: The provenance string bound into the commitment
            (N12-PP-01) — NOT the passphrase bytes.
    """

    master_secret: bytes
    key_class: KeyClass
    kek_generation: int
    key_id: str
    passphrase_provenance: str

    def zeroize(self) -> None:
        """Drop the reference to the KEK bytes (N12-IN-05 consume-and-``del``).

        Replaces ``master_secret`` with empty bytes so the resolved object,
        even if it lingers under GC, no longer references the secret. Python's
        ``bytes`` is immutable so this is best-effort residence-minimization,
        NOT cryptographic zeroization (the SLIP-0039 §3.1 boundary is
        preserved per the spec). The caller invokes this in a ``finally``
        block after consuming ``.master_secret``.
        """
        object.__setattr__(self, "master_secret", b"")


@runtime_checkable
class VaultKeyResolver(Protocol):
    """The trusted-module boundary that resolves a handle to KEK material.

    The deployment supplies a concrete resolver wired to its real vault key
    store; the public :func:`back_up_vault_key` / :func:`restore_vault_key`
    take an injected resolver so raw KEK bytes never cross the public API
    (N12-IN-01). The shipped key manager has NO KEK-bytes resolution /
    encryption hierarchy (the §3.4 net-new gap, #630), so this Protocol is the
    seam a deployment fills.

    A test injects a deterministic in-test resolver returning known bytes —
    this is NOT a production fake (a Tier-2 mock), it is the deployment-supplied
    trusted resolver, exercised through the real backup/restore code path. The
    :class:`~typing.Protocol` is ``runtime_checkable`` so the binding can assert
    an injected object satisfies the contract at the boundary.
    """

    def resolve_kek(self, handle: VaultKeyHandle) -> ResolvedKek:
        """Resolve ``handle`` to a :class:`ResolvedKek`.

        Returns the KEK master-secret bytes + ``key_class`` + ``kek_generation``
        + ``key_id`` + passphrase provenance. The binding consumes the bytes
        inside the trusted module and ``del``-s them in a ``finally`` block
        (N12-IN-05). A resolver MUST fail-closed (raise) when a handle cannot
        be resolved; returning a non-KEK class is allowed (the binding's
        :func:`require_kek_class` gate rejects it with ``not-a-kek``).
        """
        ...


# ---------------------------------------------------------------------------
# Entry gates (ordered, fail-closed) — N12-CL / N12-TH / N12-IN / N12-CRY-PIN
# ---------------------------------------------------------------------------


def require_clearance(clearance: ClearanceContext, capability: str) -> None:
    """Gate 1 — clearance presence (N12-CL-01/02). Fail-closed → ``missing-clearance``.

    Verifies ``clearance`` carries ``capability`` (``vault:backup`` /
    ``vault:restore``). Absence — including a ``None`` / wrong-type clearance —
    denies with ``missing-clearance`` (fail-closed: unknown → deny).
    """
    if not isinstance(clearance, ClearanceContext):
        raise VaultBindingError(
            N12FT01Code.MISSING_CLEARANCE,
            f"clearance MUST be a ClearanceContext (N12-CL-01); got "
            f"{type(clearance).__name__}",
            details={"capability": capability},
        )
    if not clearance.has_capability(capability):
        # Fail-closed: the principal lacks the capability token. NEVER name the
        # capability set the principal DOES hold in the error (avoid leaking
        # the clearance surface); name only the required token.
        raise VaultBindingError(
            N12FT01Code.MISSING_CLEARANCE,
            f"clearance missing required capability {capability!r} " f"(N12-CL-01/02)",
            details={"required_capability": capability},
        )


def require_ritual_floor(ritual: ShamirRitual) -> None:
    """Gate 2 — ritual floor (N12-TH-01). Fail-closed → ``invalid-ritual``.

    Enforces the vault floor ``2 <= k <= n <= 9`` BEFORE key resolution. k is
    ``ritual.threshold``; n is ``ritual.total_shards``. The wrapper allows
    ``threshold>=1``; the vault floor is STRICTER — 1-of-n / 1-of-1 forbidden
    at ALL levels.
    """
    if not isinstance(ritual, ShamirRitual):
        raise VaultBindingError(
            N12FT01Code.INVALID_RITUAL,
            f"ritual MUST be a ShamirRitual (N12-TH-01); got "
            f"{type(ritual).__name__}",
            details={"ritual": repr(ritual)},
        )
    k = ritual.threshold
    n = ritual.total_shards
    if not (VAULT_THRESHOLD_FLOOR_MIN <= k <= n <= VAULT_TOTAL_SHARDS_CEILING):
        raise VaultBindingError(
            N12FT01Code.INVALID_RITUAL,
            f"ritual outside the vault floor "
            f"{VAULT_THRESHOLD_FLOOR_MIN}<=k<=n<={VAULT_TOTAL_SHARDS_CEILING} "
            f"(N12-TH-01): k={k} n={n}",
            details={
                "k": k,
                "n": n,
                "floor_min": VAULT_THRESHOLD_FLOOR_MIN,
                "ceiling": VAULT_TOTAL_SHARDS_CEILING,
            },
        )


def require_holders_supplied(holders: object) -> list[str]:
    """Gate 3 — holders supplied (basic). Fail-closed → ``unregistered-holder``.

    A backup MUST distribute to a holder set; an empty / wrong-type holder
    array is rejected before key resolution. Returns the validated holder-id
    list (verbatim order — the distribution order is recorded, N12-AU-04). The
    DEEPER holder-registry membership check (against the deployment registry,
    N12-SH-01) is a later shard; this gate enforces only basic presence.
    """
    if not isinstance(holders, (list, tuple)):
        raise VaultBindingError(
            N12FT01Code.UNREGISTERED_HOLDER,
            f"holders MUST be a non-empty ordered array of holder-id strings "
            f"(N12-SH-01); got {type(holders).__name__}",
            details={"holders": repr(holders)},
        )
    out: list[str] = []
    for i, h in enumerate(holders):
        if not isinstance(h, str) or not h:
            raise VaultBindingError(
                N12FT01Code.UNREGISTERED_HOLDER,
                f"holders[{i}] MUST be a non-empty holder-id string "
                f"(N12-SH-01); got {h!r}",
                details={"index": i, "value": repr(h)},
            )
        out.append(h)
    if not out:
        raise VaultBindingError(
            N12FT01Code.UNREGISTERED_HOLDER,
            "holders MUST be non-empty (N12-SH-01): a backup MUST distribute "
            "to at least the n shards' holders",
            details={"holders": []},
        )
    return out


def require_kek_class(resolved: ResolvedKek) -> None:
    """Gate 4 — KEK-class type enforcement (N12-IN-02). → ``not-a-kek``.

    The resolved key MUST be :attr:`KeyClass.KEK`-tagged. A DATA-class (or any
    non-KEK) handle is rejected with ``not-a-kek`` BEFORE any sharding — never
    shard a data key. Runs AFTER resolution (the class is only known once the
    resolver returns).
    """
    if resolved.key_class is not KeyClass.KEK:
        raise VaultBindingError(
            N12FT01Code.NOT_A_KEK,
            f"resolved key is class {resolved.key_class.value!r}, not a KEK "
            f"(N12-IN-02): only KEK-class keys may be sharded",
            details={"key_class": resolved.key_class.value},
        )


def require_escape_hatch_enabled(*, escape_hatch_enabled: bool) -> None:
    """Gate (escape-hatch entry) — N12-IN-03. → ``escape-hatch-disabled``.

    The raw-bytes escape hatch is DISABLED by default. The default build MUST
    NOT expose the raw-bytes path; a raw-bytes invocation with the flag absent
    (``escape_hatch_enabled=False``) raises ``escape-hatch-disabled``. The
    flag is an explicit build/deploy decision the deployment passes in — the
    binding NEVER defaults it on.

    Note: the enabled path additionally requires the governance-approver HELD
    action AND a dual-emit of ``vault_key_restore_raw`` to recovery+safety
    (N12-IN-03/N12-CL-03/N12-SG); those extra requirements are a later shard
    (Complete/X1). This gate ships the default-OFF behavior — the load-bearing
    structural defense — and is the ONLY escape-hatch behavior I1 enables.
    """
    if not escape_hatch_enabled:
        raise VaultBindingError(
            N12FT01Code.ESCAPE_HATCH_DISABLED,
            "raw-bytes escape hatch is disabled by default (N12-IN-03); the "
            "default build MUST NOT expose the raw-bytes path. Enable it only "
            "via an explicit build/deploy flag, subject to the "
            "governance-approver HELD action + dual-emit (a later shard).",
            details={"escape_hatch_enabled": escape_hatch_enabled},
        )


def require_secret_length(secret: object) -> bytes:
    """Gate 5 (escape-hatch path only) — secret length (N12-CRY-PIN(d)).

    The escape-hatch secret MUST be a pinned SLIP-0039 length (16 or 32 bytes
    = 128 or 256 bits), else ``invalid-secret-length`` BEFORE the wrapper call.
    Returns the validated bytes.
    """
    if not isinstance(secret, (bytes, bytearray)):
        raise VaultBindingError(
            N12FT01Code.INVALID_SECRET_LENGTH,
            f"escape-hatch secret MUST be bytes (N12-CRY-PIN(d)); got "
            f"{type(secret).__name__}",
            details={"type": type(secret).__name__},
        )
    n = len(secret)
    if n not in VALID_SECRET_BYTE_LENGTHS:
        raise VaultBindingError(
            N12FT01Code.INVALID_SECRET_LENGTH,
            f"escape-hatch secret length {n} bytes is not a pinned SLIP-0039 "
            f"length (N12-CRY-PIN(d)); valid: "
            f"{sorted(VALID_SECRET_BYTE_LENGTHS)} bytes (128/256-bit)",
            details={"length_bytes": n},
        )
    return bytes(secret)
