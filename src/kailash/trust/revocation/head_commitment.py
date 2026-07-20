# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""EATP-12 D5 owner-signed ``HeadCommitment`` epoch anchor + anti-rollback.

This module ADDS the persisted-head ``HeadCommitment`` on top of the signed
RevocationEvent + append-only revocation-ledger tip fold in
:mod:`kailash.trust.revocation.signed_ledger`. It does NOT modify signed_ledger's
byte contract — it BINDS the tip that fold produces into a higher-level anchor
the owner signs once per authenticated state change.

Cross-SDK byte contract (kailash-rs LEADS; see ``specs/trust-eatp.md`` § 11.1
"Signed Revocation Ledger (EATP-12 D5)"). A following SDK MUST reproduce the
signing pre-image byte-for-byte or the owner signature will not re-verify.

**Head-commitment signing pre-image.** :meth:`HeadCommitment.signing_preimage`
builds canonical JSON (JCS: sorted keys, ASCII, no whitespace) of
``{block_count, domain_sep, epoch, revocation_ledger_tip, signed_at, tip_hash}``,
where ``domain_sep`` is the colon-LESS STRING-FIELD constant
:data:`HEAD_COMMITMENT_DOMAIN_SEP` (``"EATP-12/head-commitment/v1"`` — the VALUE
of a JSON field, never a byte prefix, exactly like signed_ledger's
``REVOCATION_EVENT_DOMAIN_SEP``). Both 32-byte hashes are lowercase-hex-encoded in
the pre-image; ``signed_at`` is RFC 3339 with EXACTLY 9 fractional (nanosecond)
digits + ``Z`` and is STRING-PRESERVED end-to-end (never parsed to a ``datetime``
and re-rendered, which would microsecond-truncate the nanosecond tail and diverge
the pre-image from the rs bytes). It uses the SAME shared ``canonical_json_dumps``
encoder signed_ledger matched (``kailash.trust._json``, the raw-UTF-8 JCS family —
``ensure_ascii=False``, ``allow_nan=False``; RFC 8785 JCS emits raw UTF-8, and it
is empirically byte-identical to the pinned rs pre-image on the all-ASCII
conformance vectors, whose hashes are hex + ASCII).

**Owner signature.** :meth:`HeadCommitment.sign` / :meth:`.verify` produce/check an
Ed25519 hex signature over the pre-image bytes DIRECTLY (Ed25519 is deterministic)
via the shared ``kailash.trust.signing.crypto`` primitives.

**Unified epoch.** ``epoch`` is the SAME unified ``u64`` counter signed_ledger folds
(monotonic; it spans block-appends AND revocation-appends). Its monotonicity is the
anti-rollback signal: :class:`HeadCommitmentAnchor` retains a high-water epoch across
persisted-head reads and REJECTS (fail-closed) a persisted ``HeadCommitment`` whose
epoch is LOWER than the retained high-water — a replay/rollback of a stale head.
"""

from __future__ import annotations

import base64
import re
from dataclasses import dataclass
from typing import Any, Dict

from kailash.trust._json import canonical_json_dumps
from kailash.trust.exceptions import InvalidSignatureError
from kailash.trust.signing import crypto

# --- Domain constant (cross-SDK byte contract; kailash-rs LEADS) -------------

#: JCS ``domain_sep`` STRING FIELD value inside the head-commitment pre-image.
#: Colon-LESS (it is the VALUE of a JSON field, never a byte prefix) — the same
#: shape as signed_ledger's ``REVOCATION_EVENT_DOMAIN_SEP``, contrasting the
#: colon-suffixed raw-byte ``REVOCATION_LEDGER_DOMAIN`` hash-chain prefix.
HEAD_COMMITMENT_DOMAIN_SEP = "EATP-12/head-commitment/v1"

#: Number of bytes in each pinned hash slot (``tip_hash`` / ``revocation_ledger_tip``).
_HASH_LEN = 32

#: Upper bound of the unified ``u64`` epoch (exclusive). rs LEADS and parses the
#: epoch into a ``u64``, so an out-of-range value serializes as a JSON number rs
#: cannot ingest, making the signed pre-image unreproducible cross-SDK.
_U64_EXCLUSIVE_MAX = 2**64

# RFC 3339, EXACTLY 9 fractional (nanosecond) digits, UTC ``Z``. The pre-image pins
# nanosecond fidelity (HC3 boundary vector), so a malformed / truncated timestamp
# MUST fail closed rather than silently normalize.
_SIGNED_AT_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{9}Z$")


class HeadCommitmentError(ValueError):
    """Raised on a malformed ``HeadCommitment`` or an anti-rollback violation."""


def _validate_u64(value: Any, field_name: str) -> None:
    """Reject a non-``int`` / ``bool`` / out-of-u64-range ``value`` (fail-closed).

    ``bool`` is a subclass of ``int`` and would serialize as ``true``/``false`` in a
    numeric slot, so it is rejected explicitly.
    """
    if not isinstance(value, int) or isinstance(value, bool):
        raise HeadCommitmentError(
            f"{field_name} must be an int, got {type(value).__name__}"
        )
    if not (0 <= value < _U64_EXCLUSIVE_MAX):
        raise HeadCommitmentError(
            f"{field_name} must be in the u64 range [0, 2**64), got {value}"
        )


def _validate_hash(value: Any, field_name: str) -> None:
    """Reject a non-``bytes`` / wrong-length 32-byte hash slot (fail-closed)."""
    if not isinstance(value, (bytes, bytearray)):
        raise HeadCommitmentError(
            f"{field_name} must be 32 bytes, got {type(value).__name__}"
        )
    if len(value) != _HASH_LEN:
        raise HeadCommitmentError(
            f"{field_name} must be exactly {_HASH_LEN} bytes, got {len(value)}"
        )


@dataclass(frozen=True)
class HeadCommitment:
    """An owner-signed persisted-head epoch anchor (EATP-12 D5).

    Frozen: the signing pre-image is a byte-for-byte cross-SDK contract, so an
    instance MUST be immutable once constructed (mutation would silently invalidate
    a produced owner signature).

    Args:
        epoch: The unified ``u64`` epoch — the SAME monotonic counter
            :func:`kailash.trust.revocation.signed_ledger.revocation_ledger_tip`
            folds (spanning block-appends + revocation-appends). MUST be a
            non-negative ``int`` in ``[0, 2**64)`` (``bool`` is rejected).
        block_count: The ``u64`` count of blocks in the chain at this head.
        tip_hash: The 32-byte chain tip hash (the block hash chain's running tip).
        revocation_ledger_tip: The 32-byte revocation-ledger tip — the value
            :func:`revocation_ledger_tip` returns (``GENESIS_TIP`` for an empty
            ledger).
        signed_at: RFC 3339 timestamp with EXACTLY 9 fractional (nanosecond) digits
            + ``Z`` (e.g. ``"2026-07-17T12:34:56.123456789Z"``). Stored and
            serialized verbatim — never re-rendered from a ``datetime``.

    Raises:
        HeadCommitmentError: If any field is malformed (fail-closed).
    """

    epoch: int
    block_count: int
    tip_hash: bytes
    revocation_ledger_tip: bytes
    signed_at: str

    def __post_init__(self) -> None:
        _validate_u64(self.epoch, "epoch")
        _validate_u64(self.block_count, "block_count")
        _validate_hash(self.tip_hash, "tip_hash")
        _validate_hash(self.revocation_ledger_tip, "revocation_ledger_tip")
        if not isinstance(self.signed_at, str) or not _SIGNED_AT_RE.match(
            self.signed_at
        ):
            raise HeadCommitmentError(
                "signed_at must be RFC 3339 with 9 fractional (nanosecond) digits "
                f"+ 'Z' (e.g. '2026-07-17T00:00:00.000000000Z'), "
                f"got {self.signed_at!r}"
            )
        # Normalize bytearray inputs to immutable bytes so a frozen instance cannot
        # be mutated through an aliased bytearray after construction.
        if not isinstance(self.tip_hash, bytes):
            object.__setattr__(self, "tip_hash", bytes(self.tip_hash))
        if not isinstance(self.revocation_ledger_tip, bytes):
            object.__setattr__(
                self, "revocation_ledger_tip", bytes(self.revocation_ledger_tip)
            )

    def signing_preimage(self) -> str:
        """Return the canonical-JSON signing pre-image string.

        JCS: sorted keys, ASCII, no whitespace, of
        ``{block_count, domain_sep, epoch, revocation_ledger_tip, signed_at,
        tip_hash}`` with ``domain_sep`` = :data:`HEAD_COMMITMENT_DOMAIN_SEP` and both
        hashes lowercase-hex-encoded. Uses the shared ``canonical_json_dumps`` encoder
        (raw-UTF-8 JCS family, ``allow_nan`` already False).
        """
        return canonical_json_dumps(
            {
                "block_count": self.block_count,
                "domain_sep": HEAD_COMMITMENT_DOMAIN_SEP,
                "epoch": self.epoch,
                "revocation_ledger_tip": self.revocation_ledger_tip.hex(),
                "signed_at": self.signed_at,
                "tip_hash": self.tip_hash.hex(),
            }
        )

    def signing_preimage_bytes(self) -> bytes:
        """Return the UTF-8 bytes of :meth:`signing_preimage` (the signed operand)."""
        return self.signing_preimage().encode("utf-8")

    def sign(self, private_key_seed: bytes) -> str:
        """Ed25519-sign the pre-image; return the signature as lowercase hex.

        The owner signs the pre-image bytes DIRECTLY (Ed25519 is deterministic).

        Args:
            private_key_seed: The 32-byte Ed25519 seed (RFC 8032 secret key).

        Returns:
            The 64-byte Ed25519 signature, lowercase hex-encoded.
        """
        b64_priv = base64.b64encode(private_key_seed).decode("ascii")
        try:
            b64_sig = crypto.sign(self.signing_preimage(), b64_priv)
        finally:
            # Drop the base64 secret-key copy immediately after use to minimize
            # its in-memory lifetime (trust-plane-security.md MUST-NOT-3). Python
            # cannot zeroize the immutable str's buffer, but dropping the reference
            # lets it be reclaimed at the earliest GC (mirrors the SignedRevocationEvent
            # signing site in signed_ledger.py).
            del b64_priv
        return base64.b64decode(b64_sig).hex()

    def verify(self, signature_hex: str, public_key: bytes) -> bool:
        """Verify a hex Ed25519 signature over this head's pre-image.

        Args:
            signature_hex: Lowercase-hex 64-byte Ed25519 signature.
            public_key: The 32-byte Ed25519 public key.

        Returns:
            True iff the signature is valid for this head's pre-image. Fail-closed: a
            malformed / short / non-hex / wrong-length ``signature_hex`` returns False
            (never raises an off-contract ``ValueError`` / ``InvalidSignatureError``).
        """
        try:
            sig_bytes = bytes.fromhex(signature_hex)
            b64_pub = base64.b64encode(public_key).decode("ascii")
            b64_sig = base64.b64encode(sig_bytes).decode("ascii")
            return crypto.verify_signature(self.signing_preimage(), b64_sig, b64_pub)
        except (ValueError, TypeError, InvalidSignatureError):
            # Malformed hex (ValueError/TypeError) OR a wrong-length signature the
            # crypto layer rejects (InvalidSignatureError) → fail closed.
            return False

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to a JSON-friendly dict (hashes as lowercase hex)."""
        return {
            "epoch": self.epoch,
            "block_count": self.block_count,
            "tip_hash": self.tip_hash.hex(),
            "revocation_ledger_tip": self.revocation_ledger_tip.hex(),
            "signed_at": self.signed_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "HeadCommitment":
        """Reconstruct from a dict (hashes are lowercase hex; validates via
        ``__post_init__``).

        Raises:
            HeadCommitmentError: If a required field is missing (typed, names the
                field) or a hex hash is malformed — not a bare ``KeyError`` /
                ``ValueError``.
        """
        for field_name in (
            "epoch",
            "block_count",
            "tip_hash",
            "revocation_ledger_tip",
            "signed_at",
        ):
            if field_name not in data:
                raise HeadCommitmentError(f"missing required field {field_name!r}")
        try:
            tip_hash = bytes.fromhex(data["tip_hash"])
            revocation_ledger_tip = bytes.fromhex(data["revocation_ledger_tip"])
        except (ValueError, TypeError) as exc:
            raise HeadCommitmentError(f"malformed hex hash field: {exc}") from exc
        return cls(
            epoch=data["epoch"],
            block_count=data["block_count"],
            tip_hash=tip_hash,
            revocation_ledger_tip=revocation_ledger_tip,
            signed_at=data["signed_at"],
        )


class HeadCommitmentAnchor:
    """Retains a high-water epoch across persisted-head reads; rejects a rollback.

    Anti-rollback (replay) defense on the PERSISTED read path: a persisted
    :class:`HeadCommitment` whose ``epoch`` is LOWER than the retained high-water is
    a stale-head replay and is REJECTED fail-closed. An epoch EQUAL to the high-water
    is accepted (re-reading the current head is legitimate) and a strictly-greater
    epoch advances the high-water. Equal-epoch defense-in-depth: a same-epoch head
    whose ``tip_hash`` differs from the retained one is REJECTED as an equivocation /
    same-epoch fork (under the strict-monotonic-epoch invariant two legitimate heads
    at one epoch cannot exist, so a differing same-epoch tip is a forgery signal).

    **DURABILITY CONTRACT (MUST — this is IN-MEMORY, monotonic only within ONE
    instance lifetime).** The high-water epoch (and pinned tip) live ONLY in this
    object; a freshly-constructed ``HeadCommitmentAnchor()`` with the default
    ``initial_epoch=0`` fails OPEN — it accepts ANY epoch ``>= 0`` (correct ONLY for
    genuine first-use with no prior head history). A caller that persists heads
    across process restarts MUST:

    1. Persist :attr:`high_water_epoch` (and, to also carry the equivocation defense,
       :attr:`high_water_tip_hash`) to a durable store after each :meth:`accept`.
    2. RE-SEED ``initial_epoch`` (and ``initial_tip_hash``) from that durable store
       when reconstructing the anchor on the persisted-head read path.

    Constructing a BARE ``HeadCommitmentAnchor()`` on a persisted-head read path
    (rather than re-seeding from the durable high-water store) is a ROLLBACK
    VULNERABILITY: every restart resets the high-water to 0 and would ACCEPT a stale
    lower-epoch head with no error, defeating the whole anti-rollback purpose. The
    durability WIRING (which store, when to persist) is #1842-S3's job; THIS shard
    ships the enforced-as-documented in-memory contract + the re-seed handles.

    The high-water epoch is the anchor's ONLY monotonic state; it never decreases
    within one lifetime, including across a rejected replay.
    """

    def __init__(
        self, initial_epoch: int = 0, initial_tip_hash: bytes | None = None
    ) -> None:
        """Initialize (or S3-re-seed) the anchor's retained high-water.

        Args:
            initial_epoch: The starting high-water epoch (default 0 — the genesis
                head, epoch 0, is accepted since ``0 >= 0``). MUST be a non-negative
                ``int`` in ``[0, 2**64)``. On the persisted-head read path a caller
                MUST re-seed this from the durable high-water store (see the class
                DURABILITY CONTRACT), NOT rely on the default.
            initial_tip_hash: The 32-byte ``tip_hash`` pinned at ``initial_epoch``
                (for the equivocation defense across a restart), or ``None`` (default)
                when there is no prior head — the first accept at ``initial_epoch``
                then records its tip without an equivocation check (no baseline to
                compare against).

        Raises:
            HeadCommitmentError: If ``initial_epoch`` or ``initial_tip_hash`` is
                malformed (fail-closed).
        """
        _validate_u64(initial_epoch, "initial_epoch")
        if initial_tip_hash is not None:
            _validate_hash(initial_tip_hash, "initial_tip_hash")
            initial_tip_hash = bytes(initial_tip_hash)
        self._high_water_epoch = initial_epoch
        self._high_water_tip_hash = initial_tip_hash

    @property
    def high_water_epoch(self) -> int:
        """The retained high-water epoch (persist this for S3 durability re-seeding)."""
        return self._high_water_epoch

    @property
    def high_water_tip_hash(self) -> bytes | None:
        """The ``tip_hash`` pinned at the high-water epoch, or ``None`` if no head has
        been accepted yet (persist this alongside :attr:`high_water_epoch` to carry the
        equivocation defense across an S3 durability re-seed)."""
        return self._high_water_tip_hash

    def accept(self, commitment: HeadCommitment) -> None:
        """Accept a persisted head, advancing the high-water; reject a rollback or
        same-epoch equivocation.

        Args:
            commitment: The persisted :class:`HeadCommitment` being read back.

        Raises:
            HeadCommitmentError: If ``commitment.epoch`` is strictly LOWER than the
                retained high-water epoch (fail-closed anti-rollback), OR if it EQUALS
                the high-water but its ``tip_hash`` differs from the pinned one
                (fail-closed equivocation / same-epoch fork detection).
        """
        if commitment.epoch < self._high_water_epoch:
            raise HeadCommitmentError(
                f"anti-rollback violation: epoch {commitment.epoch} is lower than "
                f"the retained high-water epoch {self._high_water_epoch} "
                f"(a persisted head cannot roll back to an earlier epoch)"
            )
        if (
            commitment.epoch == self._high_water_epoch
            and self._high_water_tip_hash is not None
            and commitment.tip_hash != self._high_water_tip_hash
        ):
            raise HeadCommitmentError(
                f"equivocation detected: two distinct heads at epoch "
                f"{commitment.epoch} — retained tip_hash "
                f"{self._high_water_tip_hash.hex()} vs presented "
                f"{commitment.tip_hash.hex()} (under strict-monotonic epochs a single "
                f"epoch has at most one head; a differing same-epoch tip is a fork)"
            )
        self._high_water_epoch = commitment.epoch
        self._high_water_tip_hash = commitment.tip_hash


__all__ = [
    "HEAD_COMMITMENT_DOMAIN_SEP",
    "HeadCommitmentError",
    "HeadCommitment",
    "HeadCommitmentAnchor",
]
