# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""EATP-12 D5 signed RevocationEvent + append-only revocation-ledger tip fold.

This module implements the cross-SDK byte contract for the persisted-head
``revocation_ledger_tip`` (kailash-rs LEADS; see ``specs/trust-eatp.md``
§ "Revocation Ledger — Signed Store (S1)"). It is an ADDITIVE standalone store
that lives ALONGSIDE the in-memory pub/sub cascade in
``kailash.trust.revocation.broadcaster`` / ``.cascade`` — it does NOT replace or
rewire them. The runtime cascade's own ``RevocationEvent`` (pub/sub notification
record) is a DIFFERENT type from :class:`SignedRevocationEvent` here (the signed,
epoch-keyed ledger entry).

Two byte contracts, DISTINCT by design:

* **Event signing pre-image** — canonical JSON (JCS: sorted keys, no whitespace)
  of ``{delegation_id, domain_sep, epoch, revoked_at}`` where ``domain_sep`` is
  the colon-LESS STRING FIELD :data:`REVOCATION_EVENT_DOMAIN_SEP`
  (``"EATP-12/revocation-event/v1"``). Produced via
  ``kailash.trust._json.canonical_json_dumps`` (the DELEGATE / raw-UTF-8 JCS
  family — RFC 8785 emits raw UTF-8, not ``\\uXXXX`` escapes; empirically
  byte-identical to the pinned rs pre-image on the all-ASCII conformance
  vectors). Signed with Ed25519 via the shared
  ``kailash.trust.signing.crypto`` primitives.

* **Ledger tip fold** — a SHA-256 hash chain domain-separated by the RAW-BYTE
  prefix :data:`REVOCATION_LEDGER_DOMAIN` (``b"EATP-12/revocation-ledger/v1:"``
  — WITH a trailing colon, contrasting the colon-less event ``domain_sep``
  string field). ``tip_0 = 32 zero bytes``; ``tip_i = SHA-256(DOMAIN ||
  tip_{i-1} || signing_preimage(e_i))``. Signature-INDEPENDENT: the fold binds
  each event's signing pre-image, NOT its Ed25519 signature, so a following SDK
  reproduces the tip from ``{delegation_id, epoch, revoked_at}`` inputs alone.
  The fold is ORDER-DEPENDENT — reordering or deleting any event changes every
  subsequent tip (the revocation-deletion / reorder detection the persisted-head
  signature relies on).

The timestamp ``revoked_at`` is RFC 3339 with EXACTLY 9 fractional (nanosecond)
digits + ``Z``, and is STRING-PRESERVED end-to-end — never parsed to a
``datetime`` and re-rendered (that would microsecond-truncate the nanosecond
tail and diverge the pre-image from the rs bytes).
"""

from __future__ import annotations

import base64
import hashlib
import logging
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Sequence

from kailash.trust._json import canonical_json_dumps
from kailash.trust.signing import crypto

logger = logging.getLogger(__name__)

# --- Domain constants (cross-SDK byte contract; kailash-rs LEADS) ------------

#: JCS ``domain_sep`` STRING FIELD value inside the event pre-image. Colon-LESS
#: (it is the VALUE of a JSON field, never a byte prefix). Contrast
#: :data:`REVOCATION_LEDGER_DOMAIN`.
REVOCATION_EVENT_DOMAIN_SEP = "EATP-12/revocation-event/v1"

#: RAW-BYTE domain prefix for the ledger tip hash chain. WITH a trailing colon
#: (``:``) — a deliberate, load-bearing byte separator, UNLIKE the colon-less
#: JCS ``domain_sep`` string field above. Distinct from every per-record domain
#: so the ledger tip can never collide with a single record's signing pre-image.
REVOCATION_LEDGER_DOMAIN = b"EATP-12/revocation-ledger/v1:"

#: Genesis / empty-ledger tip: 32 zero bytes (matches the epoch-0 genesis
#: ``HeadCommitment``).
GENESIS_TIP = bytes(32)

# RFC 3339, EXACTLY 9 fractional (nanosecond) digits, UTC ``Z``. The fold pins
# nanosecond fidelity (RE3 / boundary vectors), so a malformed or truncated
# timestamp MUST fail closed rather than silently normalize.
_REVOKED_AT_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{9}Z$")


class RevocationLedgerError(ValueError):
    """Raised on a malformed signed revocation event or an append-only violation."""


@dataclass(frozen=True)
class SignedRevocationEvent:
    """A signed, epoch-keyed revocation-ledger entry (EATP-12 D5).

    Frozen: the signing pre-image is a byte-for-byte cross-SDK contract, so an
    instance MUST be immutable once constructed (mutation would silently
    invalidate a produced signature / folded tip).

    Args:
        delegation_id: The revoked delegation's identifier.
        epoch: The unified ``u64`` epoch at which the revocation was recorded
            (the SAME counter the head commitment folds). MUST be a non-negative
            ``int`` (``bool`` is rejected — it is an ``int`` subclass that would
            serialize as ``true``/``false``).
        revoked_at: RFC 3339 timestamp with EXACTLY 9 fractional (nanosecond)
            digits + ``Z`` (e.g. ``"2026-07-17T12:34:56.123456789Z"``). Stored
            and serialized verbatim — never re-rendered from a ``datetime``.

    Raises:
        RevocationLedgerError: If any field is malformed (fail-closed).
    """

    delegation_id: str
    epoch: int
    revoked_at: str

    def __post_init__(self) -> None:
        if not isinstance(self.delegation_id, str) or not self.delegation_id:
            raise RevocationLedgerError(
                f"delegation_id must be a non-empty str, got {self.delegation_id!r}"
            )
        # bool is a subclass of int; reject it explicitly so it can never
        # serialize as a JSON boolean in the epoch slot.
        if not isinstance(self.epoch, int) or isinstance(self.epoch, bool):
            raise RevocationLedgerError(
                f"epoch must be an int, got {type(self.epoch).__name__}"
            )
        if self.epoch < 0:
            raise RevocationLedgerError(f"epoch must be >= 0, got {self.epoch}")
        if not isinstance(self.revoked_at, str) or not _REVOKED_AT_RE.match(
            self.revoked_at
        ):
            raise RevocationLedgerError(
                "revoked_at must be RFC 3339 with 9 fractional (nanosecond) "
                f"digits + 'Z' (e.g. '2026-07-17T00:00:00.000000000Z'), "
                f"got {self.revoked_at!r}"
            )

    def signing_preimage(self) -> str:
        """Return the canonical-JSON signing pre-image string.

        JCS: sorted keys, ASCII, no whitespace, of
        ``{delegation_id, domain_sep, epoch, revoked_at}`` with ``domain_sep`` =
        :data:`REVOCATION_EVENT_DOMAIN_SEP`. Uses the shared
        ``canonical_json_dumps`` encoder (raw-UTF-8 JCS family, ``allow_nan``
        already False).
        """
        return canonical_json_dumps(
            {
                "delegation_id": self.delegation_id,
                "domain_sep": REVOCATION_EVENT_DOMAIN_SEP,
                "epoch": self.epoch,
                "revoked_at": self.revoked_at,
            }
        )

    def signing_preimage_bytes(self) -> bytes:
        """Return the UTF-8 bytes of :meth:`signing_preimage` (the folded operand)."""
        return self.signing_preimage().encode("utf-8")

    def sign(self, private_key_seed: bytes) -> str:
        """Ed25519-sign the pre-image; return the signature as lowercase hex.

        Args:
            private_key_seed: The 32-byte Ed25519 seed (RFC 8032 secret key).

        Returns:
            The 64-byte Ed25519 signature, lowercase hex-encoded.
        """
        b64_priv = base64.b64encode(private_key_seed).decode("ascii")
        b64_sig = crypto.sign(self.signing_preimage(), b64_priv)
        return base64.b64decode(b64_sig).hex()

    def verify(self, signature_hex: str, public_key: bytes) -> bool:
        """Verify a hex Ed25519 signature over this event's pre-image.

        Args:
            signature_hex: Lowercase-hex 64-byte Ed25519 signature.
            public_key: The 32-byte Ed25519 public key.

        Returns:
            True iff the signature is valid for this event's pre-image.
        """
        b64_pub = base64.b64encode(public_key).decode("ascii")
        b64_sig = base64.b64encode(bytes.fromhex(signature_hex)).decode("ascii")
        return crypto.verify_signature(self.signing_preimage(), b64_sig, b64_pub)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to a JSON-friendly dict."""
        return {
            "delegation_id": self.delegation_id,
            "epoch": self.epoch,
            "revoked_at": self.revoked_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SignedRevocationEvent":
        """Reconstruct from a dict (validates via ``__post_init__``)."""
        return cls(
            delegation_id=data["delegation_id"],
            epoch=data["epoch"],
            revoked_at=data["revoked_at"],
        )


def revocation_ledger_tip(events: Sequence[SignedRevocationEvent]) -> bytes:
    """Fold a sequence of signed revocation events into the 32-byte ledger tip.

    The fold is the SHA-256 hash chain (cross-SDK byte contract, kailash-rs
    LEADS)::

        tip_0 = GENESIS_TIP                                         (empty ledger)
        tip_i = SHA-256( REVOCATION_LEDGER_DOMAIN
                         || tip_{i-1}
                         || e_i.signing_preimage_bytes() )   for i = 1..=n

    Folds events in the ORDER GIVEN — it is signature-INDEPENDENT (binds each
    event's signing pre-image, not its signature) and ORDER-DEPENDENT (reordering
    or removing any event changes every subsequent tip). In canonical operation
    the events are in epoch-ascending order (see :class:`RevocationLedger`, which
    enforces that on append); this pure function folds whatever order it is
    handed so callers can verify order-dependence.

    Args:
        events: The revocation events, in fold order.

    Returns:
        The 32-byte running tip (``GENESIS_TIP`` for an empty sequence).
    """
    tip = GENESIS_TIP
    for event in events:
        tip = hashlib.sha256(
            REVOCATION_LEDGER_DOMAIN + tip + event.signing_preimage_bytes()
        ).digest()
    return tip


class RevocationLedger:
    """Append-only revocation ledger with an epoch-ascending tip fold.

    Enforces the canonical append-only invariant: each appended event MUST carry
    a strictly-greater ``epoch`` than the previous one (a distinct unified epoch
    per authenticated state change), so events can never be reordered or
    re-inserted out of order, and there is NO delete/mutate surface. The tip is
    :func:`revocation_ledger_tip` over the internal ascending sequence.
    """

    def __init__(self) -> None:
        self._events: List[SignedRevocationEvent] = []

    def append(self, event: SignedRevocationEvent) -> None:
        """Append an event, enforcing strictly-ascending epoch (append-only).

        Raises:
            RevocationLedgerError: If ``event.epoch`` is not strictly greater than
                the last appended event's epoch (fail-closed on reorder / replay).
        """
        if self._events and event.epoch <= self._events[-1].epoch:
            raise RevocationLedgerError(
                f"append-only violation: epoch {event.epoch} is not strictly "
                f"greater than the current tip epoch {self._events[-1].epoch}"
            )
        self._events.append(event)

    @property
    def events(self) -> tuple[SignedRevocationEvent, ...]:
        """The appended events, in epoch-ascending order (immutable view)."""
        return tuple(self._events)

    def tip(self) -> bytes:
        """Return the current 32-byte ledger tip over the ascending sequence."""
        return revocation_ledger_tip(self._events)

    def tip_hex(self) -> str:
        """Return :meth:`tip` as lowercase hex."""
        return self.tip().hex()

    def __len__(self) -> int:
        return len(self._events)


__all__ = [
    "REVOCATION_EVENT_DOMAIN_SEP",
    "REVOCATION_LEDGER_DOMAIN",
    "GENESIS_TIP",
    "RevocationLedgerError",
    "SignedRevocationEvent",
    "revocation_ledger_tip",
    "RevocationLedger",
]
