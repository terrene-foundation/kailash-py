# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""
Certificate Revocation List (CRL) for delegation certificates.

Implements a snapshot-based, cacheable revocation list suitable for offline
and distributed revocation checking. Unlike TrustRevocationList (real-time,
event-based), CRL is designed for offline/distributed use with support for
signing and verification.

Part of CARE-013: Certificate Revocation List (CRL).
"""

from __future__ import annotations

import hashlib
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from eatp.crypto import serialize_for_signing, sign, verify_signature

logger = logging.getLogger(__name__)


@dataclass
class CRLEntry:
    """
    An entry in the Certificate Revocation List.

    Represents a single revoked delegation certificate with metadata
    about when and why it was revoked.

    Attributes:
        delegation_id: Unique identifier of the revoked delegation
        agent_id: The agent whose delegation was revoked
        revoked_at: When the revocation occurred
        reason: Human-readable reason for revocation
        revoked_by: Who performed the revocation
        expires_at: When this CRL entry expires (not the cert expiry)
    """

    delegation_id: str
    agent_id: str
    revoked_at: datetime
    reason: str
    revoked_by: str
    expires_at: Optional[datetime] = None

    def is_expired(self) -> bool:
        """Check if this CRL entry has expired."""
        if self.expires_at is None:
            return False
        return datetime.now(timezone.utc) > self.expires_at

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary.

        Returns:
            Dictionary representation of the entry
        """
        return {
            "delegation_id": self.delegation_id,
            "agent_id": self.agent_id,
            "revoked_at": self.revoked_at.isoformat(),
            "reason": self.reason,
            "revoked_by": self.revoked_by,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CRLEntry":
        """Deserialize from dictionary.

        Args:
            data: Dictionary with CRLEntry fields

        Returns:
            CRLEntry instance
        """
        return cls(
            delegation_id=data["delegation_id"],
            agent_id=data["agent_id"],
            revoked_at=datetime.fromisoformat(data["revoked_at"]),
            reason=data["reason"],
            revoked_by=data["revoked_by"],
            expires_at=(
                datetime.fromisoformat(data["expires_at"])
                if data.get("expires_at")
                else None
            ),
        )


@dataclass
class CRLMetadata:
    """
    Metadata for a Certificate Revocation List.

    Contains information about the CRL itself, including its issuer,
    issue time, and signature for integrity verification.

    Attributes:
        crl_id: Unique identifier for this CRL
        issuer_id: Authority that issued this CRL
        issued_at: When the CRL was issued
        next_update: When the CRL should be refreshed
        entry_count: Number of entries in the CRL
        signature: Optional signature for integrity verification
    """

    crl_id: str
    issuer_id: str
    issued_at: datetime
    next_update: Optional[datetime] = None
    entry_count: int = 0
    signature: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary.

        Returns:
            Dictionary representation of the metadata
        """
        return {
            "crl_id": self.crl_id,
            "issuer_id": self.issuer_id,
            "issued_at": self.issued_at.isoformat(),
            "next_update": self.next_update.isoformat() if self.next_update else None,
            "entry_count": self.entry_count,
            "signature": self.signature,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CRLMetadata":
        """Deserialize from dictionary.

        Args:
            data: Dictionary with CRLMetadata fields

        Returns:
            CRLMetadata instance
        """
        return cls(
            crl_id=data["crl_id"],
            issuer_id=data["issuer_id"],
            issued_at=datetime.fromisoformat(data["issued_at"]),
            next_update=(
                datetime.fromisoformat(data["next_update"])
                if data.get("next_update")
                else None
            ),
            entry_count=data.get("entry_count", 0),
            signature=data.get("signature"),
        )


@dataclass
class CRLVerificationResult:
    """
    Result of verifying a delegation against the CRL.

    Attributes:
        valid: True if delegation is NOT revoked, False if revoked
        reason: Explanation of the result
        delegation_id: The delegation that was checked
        entry: The CRL entry if revoked, None otherwise
    """

    valid: bool
    reason: str = ""
    delegation_id: str = ""
    entry: Optional[CRLEntry] = None


class CertificateRevocationList:
    """
    Certificate Revocation List for delegation certificates.

    A snapshot-based, cacheable list of revoked delegation certificates
    suitable for offline and distributed revocation checking.

    Two modes:
    - Online: Syncs with RevocationBroadcaster for real-time updates
    - Offline: Uses cached snapshot for offline verification

    Example:
        >>> crl = CertificateRevocationList(issuer_id="org-acme")
        >>> entry = crl.add_revocation(
        ...     delegation_id="del-001",
        ...     agent_id="agent-001",
        ...     reason="Key compromise",
        ...     revoked_by="admin"
        ... )
        >>> crl.is_revoked("del-001")
        True
        >>> crl.is_agent_revoked("agent-001")
        True
    """

    def __init__(self, issuer_id: str = "default", cache_ttl_seconds: int = 3600):
        """
        Initialize a new Certificate Revocation List.

        Args:
            issuer_id: Authority that issues this CRL
            cache_ttl_seconds: How long cached CRL data is valid (default: 1 hour)
        """
        self._entries: Dict[str, CRLEntry] = {}  # delegation_id -> entry
        self._agent_index: Dict[str, List[str]] = {}  # agent_id -> [delegation_ids]
        self._cache_ttl = cache_ttl_seconds
        self._last_refresh: Optional[datetime] = None

        # Initialize metadata
        now = datetime.now(timezone.utc)
        self._metadata = CRLMetadata(
            crl_id=f"crl-{uuid.uuid4()}",
            issuer_id=issuer_id,
            issued_at=now,
            next_update=now + timedelta(seconds=cache_ttl_seconds),
            entry_count=0,
        )

        logger.debug(f"CRL initialized with issuer_id={issuer_id}")

    def add_revocation(
        self,
        delegation_id: str,
        agent_id: str,
        reason: str,
        revoked_by: str = "system",
        expires_at: Optional[datetime] = None,
    ) -> CRLEntry:
        """
        Add a revocation entry to the CRL.

        If a delegation_id already exists, it will be updated with the new data.

        Args:
            delegation_id: The delegation being revoked
            agent_id: The agent whose delegation is revoked
            reason: Human-readable reason for revocation
            revoked_by: Who is performing the revocation
            expires_at: When this CRL entry should expire (optional)

        Returns:
            The created or updated CRLEntry
        """
        entry = CRLEntry(
            delegation_id=delegation_id,
            agent_id=agent_id,
            revoked_at=datetime.now(timezone.utc),
            reason=reason,
            revoked_by=revoked_by,
            expires_at=expires_at,
        )

        # Check if this is an update (delegation_id exists)
        is_update = delegation_id in self._entries
        old_agent_id = None
        if is_update:
            old_agent_id = self._entries[delegation_id].agent_id

        # Store the entry
        self._entries[delegation_id] = entry

        # Update agent index
        if old_agent_id and old_agent_id != agent_id:
            # Remove from old agent's index
            if old_agent_id in self._agent_index:
                if delegation_id in self._agent_index[old_agent_id]:
                    self._agent_index[old_agent_id].remove(delegation_id)

        if agent_id not in self._agent_index:
            self._agent_index[agent_id] = []

        if delegation_id not in self._agent_index[agent_id]:
            self._agent_index[agent_id].append(delegation_id)

        # Update metadata
        self._metadata.entry_count = len(self._entries)
        self._metadata.signature = None  # Invalidate signature on change

        logger.debug(
            f"Added revocation for delegation_id={delegation_id}, agent_id={agent_id}"
        )

        return entry

    def remove_revocation(self, delegation_id: str) -> bool:
        """
        Remove a revocation entry from the CRL.

        Typically used for CRL cleanup of expired entries.

        Args:
            delegation_id: The delegation to remove from CRL

        Returns:
            True if entry was removed, False if not found
        """
        if delegation_id not in self._entries:
            return False

        entry = self._entries[delegation_id]
        agent_id = entry.agent_id

        # Remove from main storage
        del self._entries[delegation_id]

        # Remove from agent index
        if agent_id in self._agent_index:
            if delegation_id in self._agent_index[agent_id]:
                self._agent_index[agent_id].remove(delegation_id)
            # Clean up empty lists
            if not self._agent_index[agent_id]:
                del self._agent_index[agent_id]

        # Update metadata
        self._metadata.entry_count = len(self._entries)
        self._metadata.signature = None  # Invalidate signature on change

        logger.debug(f"Removed revocation for delegation_id={delegation_id}")

        return True

    def is_revoked(self, delegation_id: str) -> bool:
        """
        Check if a delegation is revoked.

        Args:
            delegation_id: The delegation to check

        Returns:
            True if the delegation is in the CRL, False otherwise
        """
        return delegation_id in self._entries

    def is_agent_revoked(self, agent_id: str) -> bool:
        """
        Check if any delegation for an agent is revoked.

        Args:
            agent_id: The agent to check

        Returns:
            True if the agent has any revoked delegations, False otherwise
        """
        if agent_id not in self._agent_index:
            return False
        return len(self._agent_index[agent_id]) > 0

    def get_entry(self, delegation_id: str) -> Optional[CRLEntry]:
        """
        Get CRL entry for a delegation.

        Args:
            delegation_id: The delegation to look up

        Returns:
            The CRLEntry if found, None otherwise
        """
        return self._entries.get(delegation_id)

    def get_entries_for_agent(self, agent_id: str) -> List[CRLEntry]:
        """
        Get all CRL entries for an agent.

        Args:
            agent_id: The agent to look up

        Returns:
            List of CRLEntry for the agent's revoked delegations
        """
        if agent_id not in self._agent_index:
            return []

        return [
            self._entries[del_id]
            for del_id in self._agent_index[agent_id]
            if del_id in self._entries
        ]

    def list_entries(self, limit: int = 100, offset: int = 0) -> List[CRLEntry]:
        """
        List CRL entries with pagination.

        Args:
            limit: Maximum number of entries to return
            offset: Number of entries to skip

        Returns:
            List of CRLEntry within the specified range
        """
        entries = list(self._entries.values())
        # Sort by revoked_at for deterministic ordering
        entries.sort(key=lambda e: e.revoked_at, reverse=True)
        return entries[offset : offset + limit]

    @property
    def entry_count(self) -> int:
        """Get the number of entries in the CRL."""
        return len(self._entries)

    @property
    def metadata(self) -> CRLMetadata:
        """Get CRL metadata."""
        # Ensure entry_count is up to date
        self._metadata.entry_count = len(self._entries)
        return self._metadata

    def is_cache_valid(self) -> bool:
        """
        Check if cached CRL data is still valid.

        Returns:
            True if cache is valid, False if it needs refresh
        """
        if self._last_refresh is None:
            return False

        elapsed = datetime.now(timezone.utc) - self._last_refresh
        return elapsed.total_seconds() < self._cache_ttl

    def refresh_from_broadcaster(self, broadcaster_history: List[Any]) -> int:
        """
        Sync CRL from broadcaster event history.

        Processes revocation events from the broadcaster's history
        and adds them to this CRL.

        Args:
            broadcaster_history: List of RevocationEvent from broadcaster

        Returns:
            Count of new entries added
        """
        from eatp.revocation import RevocationEvent, RevocationType

        added_count = 0

        for event in broadcaster_history:
            if not isinstance(event, RevocationEvent):
                continue

            # Only process delegation revocations and agent revocations
            if event.revocation_type in (
                RevocationType.DELEGATION_REVOKED,
                RevocationType.AGENT_REVOKED,
                RevocationType.CASCADE_REVOCATION,
            ):
                # Use target_id as both delegation_id and agent_id
                # In a real system, these might be different
                delegation_id = f"{event.target_id}-{event.event_id}"

                if delegation_id not in self._entries:
                    self.add_revocation(
                        delegation_id=delegation_id,
                        agent_id=event.target_id,
                        reason=event.reason,
                        revoked_by=event.revoked_by,
                    )
                    added_count += 1

        # Update refresh timestamp
        self._last_refresh = datetime.now(timezone.utc)

        logger.info(f"Refreshed CRL from broadcaster: {added_count} new entries")

        return added_count

    def cleanup_expired(self) -> int:
        """
        Remove expired CRL entries.

        Returns:
            Count of entries removed
        """
        expired_ids = [
            del_id for del_id, entry in self._entries.items() if entry.is_expired()
        ]

        for del_id in expired_ids:
            self.remove_revocation(del_id)

        if expired_ids:
            logger.info(f"Cleaned up {len(expired_ids)} expired CRL entries")

        return len(expired_ids)

    def _get_signing_payload(self) -> Dict[str, Any]:
        """Get the canonical payload for signing/verification."""
        # Sort entries by delegation_id for deterministic ordering
        sorted_entries = sorted(self._entries.items(), key=lambda x: x[0])

        return {
            "crl_id": self._metadata.crl_id,
            "issuer_id": self._metadata.issuer_id,
            "issued_at": self._metadata.issued_at.isoformat(),
            "entries": [entry.to_dict() for _, entry in sorted_entries],
        }

    def sign(self, private_key: str) -> str:
        """
        Sign the CRL for integrity verification.

        Creates a cryptographic signature of the CRL contents using the
        provided private key.

        Args:
            private_key: Base64-encoded Ed25519 private key

        Returns:
            Base64-encoded signature
        """
        payload = self._get_signing_payload()
        signature = sign(payload, private_key)
        self._metadata.signature = signature

        logger.debug(f"Signed CRL {self._metadata.crl_id}")

        return signature

    def verify_signature(self, public_key: str) -> bool:
        """
        Verify CRL signature.

        Args:
            public_key: Base64-encoded Ed25519 public key

        Returns:
            True if signature is valid, False otherwise
        """
        if self._metadata.signature is None:
            return False

        payload = self._get_signing_payload()

        try:
            return verify_signature(payload, self._metadata.signature, public_key)
        except Exception as e:
            logger.warning(f"Signature verification failed: {e}")
            return False

    def to_dict(self) -> Dict[str, Any]:
        """
        Serialize entire CRL for distribution.

        Returns:
            Dictionary representation suitable for JSON serialization
        """
        return {
            "metadata": self._metadata.to_dict(),
            "entries": [entry.to_dict() for entry in self._entries.values()],
            "agent_index": {k: list(v) for k, v in self._agent_index.items()},
            "cache_ttl_seconds": self._cache_ttl,
            "last_refresh": (
                self._last_refresh.isoformat() if self._last_refresh else None
            ),
            "version": "1.0",
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CertificateRevocationList":
        """
        Deserialize CRL from distributed format.

        Args:
            data: Dictionary from to_dict()

        Returns:
            Reconstructed CertificateRevocationList
        """
        metadata_data = data.get("metadata", {})
        issuer_id = metadata_data.get("issuer_id", "default")
        cache_ttl = data.get("cache_ttl_seconds", 3600)

        crl = cls(issuer_id=issuer_id, cache_ttl_seconds=cache_ttl)

        # Restore metadata
        if metadata_data:
            crl._metadata = CRLMetadata.from_dict(metadata_data)

        # Restore entries
        for entry_data in data.get("entries", []):
            entry = CRLEntry.from_dict(entry_data)
            crl._entries[entry.delegation_id] = entry

        # Restore agent index
        crl._agent_index = {k: list(v) for k, v in data.get("agent_index", {}).items()}

        # Restore last refresh
        if data.get("last_refresh"):
            crl._last_refresh = datetime.fromisoformat(data["last_refresh"])

        return crl

    def export_pem_style(self) -> str:
        """
        Export CRL in a PEM-like text format for debugging.

        Returns:
            Human-readable text representation of the CRL
        """
        lines = [
            "-----BEGIN CERTIFICATE REVOCATION LIST-----",
            f"CRL ID: {self._metadata.crl_id}",
            f"Issuer: {self._metadata.issuer_id}",
            f"Issued At: {self._metadata.issued_at.isoformat()}",
            f"Next Update: {self._metadata.next_update.isoformat() if self._metadata.next_update else 'None'}",
            f"Entry Count: {self._metadata.entry_count}",
            f"Signature: {self._metadata.signature[:32] + '...' if self._metadata.signature else 'None'}",
            "",
            "Revoked Delegations:",
            "-" * 60,
        ]

        for entry in self._entries.values():
            lines.append(f"  Delegation ID: {entry.delegation_id}")
            lines.append(f"  Agent ID: {entry.agent_id}")
            lines.append(f"  Revoked At: {entry.revoked_at.isoformat()}")
            lines.append(f"  Reason: {entry.reason}")
            lines.append(f"  Revoked By: {entry.revoked_by}")
            lines.append(
                f"  Expires At: {entry.expires_at.isoformat() if entry.expires_at else 'Never'}"
            )
            lines.append("-" * 60)

        lines.append("-----END CERTIFICATE REVOCATION LIST-----")

        return "\n".join(lines)


def verify_delegation_with_crl(
    delegation_id: str, crl: CertificateRevocationList
) -> CRLVerificationResult:
    """
    Verify a delegation against the CRL.

    Checks if the delegation is in the CRL and returns a verification result.

    Args:
        delegation_id: The delegation to verify
        crl: The CRL to check against

    Returns:
        CRLVerificationResult with valid=False if revoked, valid=True otherwise
    """
    entry = crl.get_entry(delegation_id)

    if entry is not None:
        return CRLVerificationResult(
            valid=False,
            reason=f"Delegation revoked: {entry.reason}",
            delegation_id=delegation_id,
            entry=entry,
        )

    return CRLVerificationResult(
        valid=True,
        reason="Delegation not in CRL",
        delegation_id=delegation_id,
        entry=None,
    )


__all__ = [
    "CRLEntry",
    "CRLMetadata",
    "CRLVerificationResult",
    "CertificateRevocationList",
    "verify_delegation_with_crl",
]
