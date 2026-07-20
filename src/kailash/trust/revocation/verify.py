# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""EATP-12 D5 signed-ledger revocation verify + durable anti-rollback re-seed.

This module wires the append-only signed revocation ledger
(:mod:`kailash.trust.revocation.signed_ledger`) and the owner-signed persisted
head (:mod:`kailash.trust.revocation.head_commitment`) into the AUTHORITATIVE
revocation decision on the delegation verify path (#1842 shard 3).

Two durable artifacts persist under a store directory:

* ``revocation_head.json`` — the full ledger event set + the current
  owner-signed :class:`HeadCommitment` + its Ed25519 signature (hex). The event
  set is what lets a verifier RECOMPUTE the ledger tip and detect a store-writer
  who added / deleted / reordered an event (the tip changes → head signature no
  longer binds it → detected).
* ``revocation_highwater.json`` — the durable anti-rollback high-water
  (``epoch`` + pinned ``tip_hash``). The persisted-head READ path RE-SEEDS a
  :class:`HeadCommitmentAnchor` from this file (NOT a bare anchor), so a
  process-restart replay of a lower-epoch head is REJECTED — the rollback
  vulnerability :class:`HeadCommitmentAnchor`'s DURABILITY CONTRACT calls out.

**Fail-closed (``rules/eatp.md`` / ``rules/security.md``).** The signed ledger is
the AUTHORITATIVE revocation source. If the persisted head cannot be verified —
missing/malformed store, bad owner signature, a recomputed ledger tip that does
not match the signed head's tip, or an anti-rollback / equivocation violation —
the verifier RAISES :class:`RevocationVerificationError` and the caller MUST deny
(treat as revoked). It NEVER falls open to the unsigned ``revoked`` flag / the
in-memory cascade. An ABSENT store (no revocation ever persisted) is the
legitimate genesis / empty-ledger case and yields an EMPTY revoked set (not a
deny) — distinct from a PRESENT-but-unverifiable store, which denies.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple

from kailash.trust._locking import atomic_write, file_lock, safe_read_json
from kailash.trust.exceptions import TrustError
from kailash.trust.revocation.head_commitment import (
    HeadCommitment,
    HeadCommitmentAnchor,
    HeadCommitmentError,
)
from kailash.trust.revocation.signed_ledger import (
    RevocationLedgerError,
    SignedRevocationEvent,
    revocation_ledger_tip,
)

logger = logging.getLogger(__name__)

#: Filename of the persisted signed head + ledger event set.
HEAD_FILENAME = "revocation_head.json"

#: Filename of the durable anti-rollback high-water.
HIGHWATER_FILENAME = "revocation_highwater.json"


class RevocationVerificationError(TrustError):
    """Raised (fail-closed) when the signed revocation ledger/head cannot be
    verified — a missing owner signature, a store-tamper tip mismatch, or an
    anti-rollback / equivocation violation. The caller MUST deny (treat as
    revoked); it MUST NOT fall open to the unsigned ``revoked`` flag.
    """


class DurableHighWaterStore:
    """Durable anti-rollback high-water store (a single JSON record).

    Persists :attr:`HeadCommitmentAnchor.high_water_epoch` + the pinned
    :attr:`HeadCommitmentAnchor.high_water_tip_hash` after each accepted head, and
    RE-SEEDS a fresh :class:`HeadCommitmentAnchor` from that record on the
    persisted-head read path. Reconstructing a BARE ``HeadCommitmentAnchor()``
    instead is the rollback vulnerability the head-commitment DURABILITY CONTRACT
    documents; :meth:`load_anchor` closes it.

    Uses the trust-plane single-record persistence idiom
    (``_locking.atomic_write`` + ``safe_read_json`` + ``file_lock`` — the same
    crash-safe temp-file-rename + O_NOFOLLOW symlink guard the delegation WAL
    uses), NOT a bespoke store.
    """

    def __init__(self, store_dir: Path, owner_public_key: bytes) -> None:
        """Initialize the durable high-water store.

        Args:
            store_dir: Directory holding ``revocation_highwater.json``.
            owner_public_key: The 32-byte Ed25519 owner public key. The persisted
                high-water is itself an owner-SIGNED head (see the class
                docstring's FIX-3 note); the signature is verified on every read so
                a store-writer cannot forge an arbitrary lower epoch — only replay
                a PREVIOUSLY-VALID owner-signed head (the documented residual).
        """
        self._store_dir = Path(store_dir)
        self._path = self._store_dir / HIGHWATER_FILENAME
        self._lock_path = self._store_dir / f".{HIGHWATER_FILENAME}.lock"
        self._owner_public_key = owner_public_key

    @property
    def owner_public_key(self) -> bytes:
        """The owner public key the persisted high-water head is verified under.

        Exposed so :class:`SignedRevocationVerifier` can assert at construction
        that its own owner key and this store's key are the SAME — a mis-wired
        factory passing two different owner keys would otherwise verify the
        high-water head against the WRONG key (a latent key-confusion footgun).
        """
        return self._owner_public_key

    def _load_anchor_unlocked(self) -> HeadCommitmentAnchor:
        """Re-seed the anchor from the durable (owner-signed) high-water record.

        Caller MUST hold ``self._lock_path``. A missing file yields a genesis
        anchor (``initial_epoch=0``) — the legitimate first-use case. A present
        record is an owner-signed head; its signature is verified before the epoch
        is trusted (FIX 3). Fail-closed on absent-signature / malformed / bad-sig —
        NEVER silently reset to 0 (which would defeat anti-rollback).
        """
        if not self._path.exists():
            return HeadCommitmentAnchor()
        try:
            data = safe_read_json(self._path)
            head = HeadCommitment.from_dict(data["head"])
            signature_hex = data["head_signature"]
            if not isinstance(signature_hex, str):
                raise ValueError("head_signature must be a hex string")
        except (
            OSError,
            json.JSONDecodeError,
            KeyError,
            ValueError,
            TypeError,
            HeadCommitmentError,
        ) as exc:
            raise RevocationVerificationError(
                "durable high-water store is present but unreadable/malformed "
                "(fail-closed — refusing to reset the anti-rollback high-water "
                f"to 0): {exc}"
            ) from exc
        # FIX 3 — bind the durable high-water to the owner signature. A store-writer
        # who lowers the persisted epoch must present a validly-owner-signed head at
        # that epoch, not forge an arbitrary number; an unsigned/forged high-water
        # fails closed here. RESIDUAL (documented): a full-local-write adversary can
        # still REPLAY a previously-valid owner-signed head at an earlier epoch —
        # complete defense against a local store-writer requires an EXTERNAL
        # monotonic/append-only anchor outside the store's write scope, out of scope
        # for local persistence.
        if not head.verify(signature_hex, self._owner_public_key):
            raise RevocationVerificationError(
                "durable high-water head signature did not verify (fail-closed — "
                "the persisted anti-rollback high-water was tampered)"
            )
        return HeadCommitmentAnchor(
            initial_epoch=head.epoch, initial_tip_hash=head.tip_hash
        )

    def load_anchor(self) -> HeadCommitmentAnchor:
        """Re-seed the anchor from durable state (read-only, off the CAS path).

        Used by the head-absent tamper check (a persisted high-water at epoch ≥ 1
        with the signed-head store deleted is a resurrection signal). Held under the
        file lock for a consistent read.

        Raises:
            RevocationVerificationError: If the persisted high-water record is
                present but malformed or its owner signature does not verify
                (fail-closed).
        """
        with file_lock(self._lock_path):
            return self._load_anchor_unlocked()

    def accept_and_persist(
        self, commitment: HeadCommitment, head_signature_hex: str
    ) -> None:
        """Atomic anti-rollback compare-and-swap under ONE file lock (FIX 2).

        Reads the current durable high-water, re-seeds an anchor from it, and
        ``accept``s ``commitment`` — all inside a SINGLE ``file_lock`` so no
        concurrent verifier can interleave a stale read between another's
        accept and persist (the non-monotonic-regression race). ``accept`` enforces
        ``commitment.epoch >= current`` (rollback → raise) and equal-epoch tip
        equality (equivocation → raise), so the persisted high-water is
        monotonic-non-decreasing by construction. Persists the accepted head as the
        new owner-signed high-water record (FIX 3).

        Args:
            commitment: The verified :class:`HeadCommitment` being accepted.
            head_signature_hex: The owner's Ed25519 signature over ``commitment``
                (already verified by the caller; re-verified on the next load).

        Raises:
            RevocationVerificationError: On rollback / equivocation (fail-closed),
                or if the current durable record is unverifiable.
        """
        with file_lock(self._lock_path):
            anchor = self._load_anchor_unlocked()
            try:
                anchor.accept(commitment)
            except HeadCommitmentError as exc:
                raise RevocationVerificationError(
                    f"anti-rollback check rejected the persisted head: {exc}"
                ) from exc
            record: Dict[str, Any] = {
                "head": commitment.to_dict(),
                "head_signature": head_signature_hex,
            }
            atomic_write(self._path, record)


class SignedRevocationStore:
    """Persists the ledger event set + the owner-signed :class:`HeadCommitment`.

    The event set is persisted ALONGSIDE the head so a verifier can RECOMPUTE the
    ledger tip and confirm it matches the tip the owner signed — the store-tamper
    (revocation-resurrection / deletion) detection. Same crash-safe atomic-write +
    O_NOFOLLOW idiom as :class:`DurableHighWaterStore`.
    """

    def __init__(self, store_dir: Path) -> None:
        self._store_dir = Path(store_dir)
        self._path = self._store_dir / HEAD_FILENAME
        self._lock_path = self._store_dir / f".{HEAD_FILENAME}.lock"

    def persist_head(
        self,
        events: Sequence[SignedRevocationEvent],
        head: HeadCommitment,
        head_signature_hex: str,
    ) -> None:
        """Persist the ledger events + the owner-signed head + its signature.

        Args:
            events: The signed revocation events, in epoch-ascending fold order —
                the exact sequence whose fold produced ``head.revocation_ledger_tip``.
            head: The owner-signed :class:`HeadCommitment` binding that tip.
            head_signature_hex: The owner's Ed25519 signature over ``head`` (hex).
        """
        record: Dict[str, Any] = {
            "events": [e.to_dict() for e in events],
            "head": head.to_dict(),
            "head_signature": head_signature_hex,
        }
        with file_lock(self._lock_path):
            atomic_write(self._path, record)

    def load_head(
        self,
    ) -> Tuple[List[SignedRevocationEvent], HeadCommitment, str] | None:
        """Load the persisted events + head + signature.

        Returns:
            ``(events, head, signature_hex)`` if a head is persisted, or ``None``
            when the store is ABSENT (the legitimate empty-ledger / genesis case —
            NOT a fail-closed condition).

        Raises:
            RevocationVerificationError: If the store is PRESENT but malformed
                (fail-closed — a corrupt store is a tamper signal, not an empty
                ledger).
        """
        if not self._path.exists():
            return None
        try:
            data = safe_read_json(self._path)
            events = [SignedRevocationEvent.from_dict(e) for e in data["events"]]
            head = HeadCommitment.from_dict(data["head"])
            signature_hex = data["head_signature"]
            if not isinstance(signature_hex, str):
                raise ValueError("head_signature must be a hex string")
            return events, head, signature_hex
        except (
            OSError,
            json.JSONDecodeError,
            KeyError,
            ValueError,
            TypeError,
            RevocationLedgerError,
            HeadCommitmentError,
        ) as exc:
            raise RevocationVerificationError(
                "signed revocation head store is present but "
                f"unreadable/malformed (fail-closed deny): {exc}"
            ) from exc


class SignedRevocationVerifier:
    """AUTHORITATIVE revocation decision, derived from the signed ledger.

    The in-memory cascade (:class:`~kailash.trust.revocation.broadcaster.TrustRevocationList`)
    and the CRL may remain a fast-path cache, but the AUTHORITATIVE revocation
    decision on the verify path MUST derive from THIS verifier — the signed
    ledger verified against the owner-signed head, with a durable anti-rollback
    anchor. It NEVER trusts the mutable unsigned ``revoked`` flag.

    A store-writer who flips a persisted ``revoked`` flag at rest changes NOTHING
    here: the signed ledger + head are the source of truth. Conversely, a
    store-writer who DELETES a revocation event from the ledger changes the
    recomputed tip → the owner's head signature no longer binds it → detected and
    denied.
    """

    def __init__(
        self,
        owner_public_key: bytes,
        signed_store: SignedRevocationStore,
        highwater_store: DurableHighWaterStore,
    ) -> None:
        """Initialize the verifier.

        Args:
            owner_public_key: The 32-byte Ed25519 public key the persisted head is
                signed under.
            signed_store: The durable signed-head + event-set store.
            highwater_store: The durable anti-rollback high-water store (re-seeds
                the :class:`HeadCommitmentAnchor` on every read). Its
                ``owner_public_key`` MUST equal ``owner_public_key`` — the verifier
                and the store verify the SAME owner signatures, so a mismatch is a
                mis-wiring.

        Raises:
            RevocationVerificationError: If ``highwater_store.owner_public_key``
                differs from ``owner_public_key`` — a key-confusion mis-wiring that
                would verify the persisted high-water head against the WRONG key
                (fail-closed at construction; a mismatch is unconstructable).
        """
        if highwater_store.owner_public_key != owner_public_key:
            raise RevocationVerificationError(
                "owner-public-key mismatch: the SignedRevocationVerifier and its "
                "DurableHighWaterStore were wired with DIFFERENT owner keys — both "
                "MUST verify the same owner signatures (key-confusion mis-wiring)"
            )
        self._owner_public_key = owner_public_key
        self._signed_store = signed_store
        self._highwater_store = highwater_store

    def verified_revoked_set(self) -> set[str]:
        """Return the set of revoked delegation ids, verified fail-closed.

        Performs, in order (any failure RAISES — fail-closed, the caller denies):

        1. Load the persisted head + event set. ABSENT store → empty set (genesis).
        2. Verify the owner's Ed25519 signature over the head.
        3. Recompute the ledger tip from the persisted events and confirm it
           matches ``head.revocation_ledger_tip`` (store-tamper / resurrection
           detection).
        4. Re-seed the :class:`HeadCommitmentAnchor` from the durable high-water
           and ``accept`` the head (anti-rollback + equivocation). Persist the
           advanced high-water on success.

        Returns:
            The set of ``delegation_id`` present in the verified signed ledger
            (empty when the store is absent).

        Raises:
            RevocationVerificationError: On any unverifiable condition
                (fail-closed). The caller MUST deny.
        """
        loaded = self._signed_store.load_head()
        if loaded is None:
            # FIX 1 (CRITICAL) — a MISSING signed-head store is NOT unconditionally
            # "nothing revoked". A store-writer who deletes ONLY
            # revocation_head.json (leaving the durable high-water at epoch ≥ 1)
            # would silently un-revoke EVERY delegation. Consult the durable
            # high-water FIRST: if a head was ever accepted (high_water_epoch > 0),
            # an absent signed-head store is a resurrection/tamper signal → deny.
            # ONLY head-absent AND high-water-at-genesis(0) is the legitimate
            # empty-ledger case.
            anchor = self._highwater_store.load_anchor()
            if anchor.high_water_epoch > 0:
                raise RevocationVerificationError(
                    "signed revocation head store is absent but the durable "
                    f"high-water is at epoch {anchor.high_water_epoch} — the "
                    "persisted head was deleted (resurrection attempt); "
                    "fail-closed deny"
                )
            # Genesis / empty ledger — nothing revoked. NOT a fail-closed deny.
            return set()
        events, head, signature_hex = loaded

        # (2) Owner signature over the head — fail-closed if it does not verify.
        if not head.verify(signature_hex, self._owner_public_key):
            raise RevocationVerificationError(
                "persisted revocation head owner signature did not verify "
                "(fail-closed deny — refusing to fall open to the unsigned "
                "revoked flag)"
            )

        # (3) Recompute the ledger tip from the persisted events and confirm the
        # owner-signed head binds THIS event set. A store-writer who added,
        # deleted, or reordered an event changes the recomputed tip; the head
        # signature (verified above) binds the ORIGINAL tip, so a mismatch is a
        # tamper signal → deny.
        recomputed_tip = revocation_ledger_tip(events)
        if recomputed_tip != head.revocation_ledger_tip:
            raise RevocationVerificationError(
                "recomputed revocation-ledger tip does not match the "
                "owner-signed head tip — the persisted event set was tampered "
                "(added/deleted/reordered); fail-closed deny"
            )

        # (4) Anti-rollback: re-seed the anchor from the DURABLE high-water (never
        # a bare anchor) and accept the head — as ONE atomic compare-and-swap under
        # a single file lock (FIX 2), so a concurrent verifier cannot interleave a
        # stale read and regress the high-water. A restart replay of a lower-epoch
        # head — or a same-epoch equivocating fork — raises here. The accepted head
        # is persisted as the new owner-signed high-water (FIX 3).
        self._highwater_store.accept_and_persist(head, signature_hex)

        return {e.delegation_id for e in events}

    def is_revoked(self, delegation_id: str) -> bool:
        """Return True iff ``delegation_id`` is revoked per the signed ledger.

        Raises:
            RevocationVerificationError: On any unverifiable condition
                (fail-closed). The caller MUST deny rather than treat the raise as
                "not revoked".
        """
        return delegation_id in self.verified_revoked_set()


__all__ = [
    "HEAD_FILENAME",
    "HIGHWATER_FILENAME",
    "RevocationVerificationError",
    "DurableHighWaterStore",
    "SignedRevocationStore",
    "SignedRevocationVerifier",
]
