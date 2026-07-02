# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Hold/Approve workflow for HELD actions.

When trust_check returns HELD, a HoldRecord is created. The human
resolves it via CLI (approve/deny). Every resolution is Ed25519-signed
over a canonical payload that binds the reviewed hold's decision-relevant
disclosure (action, resource, reason, context — the last carries the
submitter/caller, capability, and agent identity) together with the
decision itself (approved/denied, resolver, resolution reason). The
signature is recomputed from the *queued* hold at verification time, so a
resolution signed over a disclosure that differs from the stored hold
fails verification (see :meth:`HoldManager.verify_resolution`).
"""

from __future__ import annotations

import hashlib
import logging
import os
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from kailash.trust._locking import file_lock, safe_read_text
from kailash.trust.signing.crypto import generate_keypair, sign, verify_signature

if TYPE_CHECKING:
    from kailash.trust.plane.store import TrustPlaneStore

logger = logging.getLogger(__name__)


@dataclass
class HoldRecord:
    """A held action awaiting human resolution."""

    hold_id: str
    action: str
    resource: str
    context: dict
    reason: str
    status: str = "pending"  # pending / approved / denied
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    resolved_at: datetime | None = None
    resolved_by: str | None = None
    resolution_reason: str | None = None
    # Ed25519 signature (base64) binding the reviewed disclosure + decision,
    # and the base64 public key it verifies against. Populated on resolution;
    # ``None`` while the hold is pending. See HoldManager.verify_resolution.
    resolution_signature: str | None = None
    signing_pubkey: str | None = None

    def to_dict(self) -> dict:
        return {
            "hold_id": self.hold_id,
            "action": self.action,
            "resource": self.resource,
            "context": self.context,
            "reason": self.reason,
            "status": self.status,
            "created_at": self.created_at.isoformat(),
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
            "resolved_by": self.resolved_by,
            "resolution_reason": self.resolution_reason,
            "resolution_signature": self.resolution_signature,
            "signing_pubkey": self.signing_pubkey,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "HoldRecord":
        return cls(
            hold_id=data["hold_id"],
            action=data["action"],
            resource=data["resource"],
            context=data.get("context", {}),
            reason=data["reason"],
            status=data.get("status", "pending"),
            created_at=datetime.fromisoformat(data["created_at"]),
            resolved_at=(
                datetime.fromisoformat(data["resolved_at"])
                if data.get("resolved_at")
                else None
            ),
            resolved_by=data.get("resolved_by"),
            resolution_reason=data.get("resolution_reason"),
            resolution_signature=data.get("resolution_signature"),
            signing_pubkey=data.get("signing_pubkey"),
        )


def generate_hold_id(action: str, resource: str) -> str:
    """Generate a unique hold ID with random nonce to prevent collisions."""
    now = datetime.now(timezone.utc).isoformat()
    nonce = secrets.token_hex(4)
    content = f"hold:{action}:{resource}:{now}:{nonce}"
    return f"hold-{hashlib.sha256(content.encode()).hexdigest()[:12]}"


def _resolution_signing_payload(hold: "HoldRecord") -> dict:
    """Canonical payload a resolution signature binds.

    Folds the reviewed hold's decision-relevant disclosure — ``action``,
    ``resource``, ``reason``, and the ``context`` dict (which carries the
    submitter/caller, requested capability, and agent identity) — together
    with the decision (status, resolver, resolution reason, timestamp). Both
    the signer (:meth:`HoldManager.resolve`) and the verifier
    (:meth:`HoldManager.verify_resolution`) build this from the *queued* hold,
    so a resolution signed over a disclosure that differs from the stored hold
    fails verification. The signature fields themselves are excluded (they are
    the output, not the input).
    """
    return {
        "hold_id": hold.hold_id,
        "action": hold.action,
        "resource": hold.resource,
        "reason": hold.reason,
        "context": hold.context,
        "status": hold.status,
        "resolved_by": hold.resolved_by,
        "resolution_reason": hold.resolution_reason,
        "resolved_at": hold.resolved_at.isoformat() if hold.resolved_at else None,
    }


def _load_or_create_signing_keys(keys_dir: Path) -> tuple[str, str]:
    """Load the trust-plane keypair, generating and persisting one if absent.

    Reuses the same ``keys/private.key`` / ``keys/public.key`` layout the
    plane project writes, so a HoldManager attached to an initialized project
    signs with that project's authority key. The private key is written with
    ``0o600`` and ``O_NOFOLLOW`` (no symlink redirection), matching the
    trust-plane key-at-rest contract.
    """
    priv_path = keys_dir / "private.key"
    pub_path = keys_dir / "public.key"

    if priv_path.exists() and pub_path.exists():
        return safe_read_text(priv_path), safe_read_text(pub_path)

    private_key, public_key = generate_keypair()
    keys_dir.mkdir(parents=True, exist_ok=True)

    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(str(priv_path), flags, 0o600)
    try:
        os.write(fd, private_key.encode())
    finally:
        os.close(fd)

    pub_flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    if hasattr(os, "O_NOFOLLOW"):
        pub_flags |= os.O_NOFOLLOW
    pub_fd = os.open(str(pub_path), pub_flags, 0o644)
    try:
        os.write(pub_fd, public_key.encode())
    finally:
        os.close(pub_fd)

    return private_key, public_key


class HoldManager:
    """Manages held actions in the trust plane directory.

    Accepts an optional ``store`` parameter (any object satisfying the
    :class:`~trustplane.store.TrustPlaneStore` protocol).  When *store*
    is ``None`` (the default), a :class:`FileSystemTrustPlaneStore` is
    created internally for backward compatibility.
    """

    def __init__(
        self,
        trust_dir: Path,
        store: "TrustPlaneStore | None" = None,
    ) -> None:
        from kailash.trust.plane.store.filesystem import FileSystemTrustPlaneStore

        if store is not None:
            self._store = store
        else:
            self._store = FileSystemTrustPlaneStore(trust_dir)
            self._store.initialize()
        self._holds_dir = trust_dir / "holds"
        self._holds_dir.mkdir(parents=True, exist_ok=True)
        self._lock_path = self._holds_dir / ".lock"
        self._keys_dir = trust_dir / "keys"
        # Signing keys are loaded lazily on first resolution so read-only
        # operations (list/get) never create key material as a side effect.
        self._signing_keys: tuple[str, str] | None = None

    def _get_signing_keys(self) -> tuple[str, str]:
        """Return (private_key, public_key), loading/generating on first use."""
        if self._signing_keys is None:
            self._signing_keys = _load_or_create_signing_keys(self._keys_dir)
        return self._signing_keys

    def create_hold(
        self, action: str, resource: str, reason: str, context: dict | None = None
    ) -> HoldRecord:
        """Create a new hold for a HELD action."""
        hold = HoldRecord(
            hold_id=generate_hold_id(action, resource),
            action=action,
            resource=resource,
            context=context or {},
            reason=reason,
        )
        with file_lock(self._lock_path):
            self._store.store_hold(hold)
        logger.info("Created hold %s for action '%s'", hold.hold_id, action)
        return hold

    def resolve(
        self, hold_id: str, approved: bool, resolved_by: str, reason: str
    ) -> HoldRecord:
        """Resolve a pending hold."""
        # Lock for status check + save (prevents TOCTOU: two processes
        # both see "pending" and both resolve the same hold)
        with file_lock(self._lock_path):
            hold = self.get(hold_id)
            if hold.status != "pending":
                raise ValueError(f"Hold {hold_id} is already {hold.status}")

            hold.status = "approved" if approved else "denied"
            hold.resolved_at = datetime.now(timezone.utc)
            hold.resolved_by = resolved_by
            hold.resolution_reason = reason

            # Sign the reviewed disclosure + decision BEFORE the durable write.
            # If signing raises, the store is never updated and the hold stays
            # pending (fail-closed — no half-resolved, unsigned record persists).
            private_key, public_key = self._get_signing_keys()
            payload = _resolution_signing_payload(hold)
            hold.resolution_signature = sign(payload, private_key)
            hold.signing_pubkey = public_key

            self._store.update_hold(hold)
        logger.info("Resolved hold %s: %s by %s", hold_id, hold.status, resolved_by)
        return hold

    def verify_resolution(self, hold_id: str) -> bool:
        """Verify a resolved hold's signature against its *queued* disclosure.

        Recomputes the canonical resolution payload from the stored hold's
        current fields and verifies the stored Ed25519 signature. A resolution
        signed over a disclosure that differs from the stored hold — e.g. the
        reviewed action, resource, reason, or context (submitter/caller,
        capability, agent identity) was altered after the human decided —
        fails verification. Fail-closed: a pending or unsigned hold returns
        ``False``. This method never mutates or deletes the hold, so a hold
        that fails verification survives for a correct decision.
        """
        hold = self.get(hold_id)
        if (
            hold.status == "pending"
            or not hold.resolution_signature
            or not hold.signing_pubkey
        ):
            return False
        payload = _resolution_signing_payload(hold)
        try:
            return verify_signature(
                payload, hold.resolution_signature, hold.signing_pubkey
            )
        except Exception:
            # Any verification error (malformed signature/key, decode failure)
            # is a failed verification, never an exception to the caller.
            return False

    def get(self, hold_id: str) -> HoldRecord:
        """Get a hold by ID."""
        return self._store.get_hold(hold_id)

    def list_pending(self) -> list[HoldRecord]:
        """List all pending holds."""
        return self._store.list_holds(status="pending")

    def list_all(self) -> list[HoldRecord]:
        """List all holds (pending and resolved)."""
        return self._store.list_holds()
