# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Selective disclosure for EATP audit export.

Allows exporting audit records with selectively redacted fields for
witness verification. Witnesses can verify hash chain integrity
without seeing all audit data.
"""

from __future__ import annotations

import hashlib
import hmac as hmac_mod
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, FrozenSet, List, Optional

from kailash.trust.audit_store import AuditRecord
from kailash.trust.pact.audit import GENESIS_HASH
from kailash.trust.reasoning.traces import ConfidentialityLevel
from kailash.trust.signing.crypto import sign, verify_signature

logger = logging.getLogger(__name__)

# ConfidentialityLevel threshold: traces at this level or above are redacted
# PUBLIC and RESTRICTED are kept; CONFIDENTIAL, SECRET, TOP_SECRET are redacted
_REASONING_REDACTION_THRESHOLD = ConfidentialityLevel.CONFIDENTIAL

# Fields that MUST NOT be redacted — integrity-critical
NON_REDACTABLE_FIELDS: FrozenSet[str] = frozenset(
    {
        "id",
        "timestamp",
        "chain_hash",
        "previous_hash",
        "agent_id",
        "action_result",
    }
)


def _hash_value(value: Any) -> str:
    """Create SHA-256 hash of a value for redaction."""
    data = json.dumps(value, sort_keys=True, default=str)
    return f"REDACTED:sha256:{hashlib.sha256(data.encode()).hexdigest()}"


def _is_redacted(value: Any) -> bool:
    """Check if a value has been redacted."""
    return isinstance(value, str) and value.startswith("REDACTED:sha256:")


@dataclass
class RedactedAuditRecord:
    """An audit record with selectively redacted fields.

    Redacted fields are replaced with their SHA-256 hash, allowing
    integrity verification without revealing the original data.
    """

    data: Dict[str, Any]
    disclosed_fields: List[str]
    redacted_fields: List[str]

    @property
    def id(self) -> str:
        return self.data.get("id", "")

    @property
    def agent_id(self) -> str:
        return self.data.get("agent_id", "")

    @property
    def timestamp(self) -> str:
        return self.data.get("timestamp", "")

    def is_field_redacted(self, field_name: str) -> bool:
        """Check if a specific field is redacted."""
        return field_name in self.redacted_fields


@dataclass
class ExportPackage:
    """Package of selectively disclosed audit records for witness verification.

    Contains redacted audit records, metadata about the export, and a
    signature for integrity verification.
    """

    records: List[RedactedAuditRecord]
    export_metadata: Dict[str, Any]
    chain_hashes: List[str]
    signature: str
    exported_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> Dict[str, Any]:
        """Serialize export package to dictionary."""
        return {
            "records": [
                {
                    "data": r.data,
                    "disclosed_fields": r.disclosed_fields,
                    "redacted_fields": r.redacted_fields,
                }
                for r in self.records
            ],
            "export_metadata": self.export_metadata,
            "chain_hashes": self.chain_hashes,
            "signature": self.signature,
            "exported_at": self.exported_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ExportPackage":
        """Deserialize export package from dictionary."""
        records = [
            RedactedAuditRecord(
                data=r["data"],
                disclosed_fields=r["disclosed_fields"],
                redacted_fields=r["redacted_fields"],
            )
            for r in data["records"]
        ]
        return cls(
            records=records,
            export_metadata=data["export_metadata"],
            chain_hashes=data["chain_hashes"],
            signature=data["signature"],
            exported_at=datetime.fromisoformat(data["exported_at"]),
        )


@dataclass
class WitnessVerificationResult:
    """Result of verifying a witness export package."""

    valid: bool
    signature_valid: bool
    chain_integrity_valid: bool
    disclosed_field_count: int
    redacted_field_count: int
    record_count: int
    errors: List[str] = field(default_factory=list)


def _audit_record_to_dict(record: AuditRecord) -> Dict[str, Any]:
    """Convert an AuditRecord to a flat dictionary for redaction."""
    data: Dict[str, Any] = {}

    # Extract all fields from the record
    if hasattr(record, "__dataclass_fields__"):
        for field_name in record.__dataclass_fields__:
            value = getattr(record, field_name, None)
            if isinstance(value, datetime):
                data[field_name] = value.isoformat()
            else:
                data[field_name] = value
    elif hasattr(record, "to_dict"):
        data = record.to_dict()  # type: ignore[attr-defined]
    else:
        # Fallback: use __dict__
        for k, v in vars(record).items():
            if not k.startswith("_"):
                if isinstance(v, datetime):
                    data[k] = v.isoformat()
                else:
                    data[k] = v

    return data


def _should_keep_reasoning_trace(value: Any) -> bool:
    """Determine if a reasoning_trace value should be kept (not redacted).

    Applies confidentiality-based redaction rules:
    - PUBLIC and RESTRICTED: keep the trace visible
    - CONFIDENTIAL, SECRET, TOP_SECRET: redact to hash only

    If the value is not a dict or lacks a 'confidentiality' key,
    standard redaction applies (returns False).

    Args:
        value: The reasoning_trace field value

    Returns:
        True if the trace should be kept visible, False to redact
    """
    if not isinstance(value, dict):
        return False

    confidentiality_str = value.get("confidentiality")
    if confidentiality_str is None:
        return False

    try:
        level = ConfidentialityLevel(confidentiality_str)
    except ValueError:
        logger.warning(
            f"[SELECTIVE_DISCLOSURE] Unknown confidentiality level "
            f"'{confidentiality_str}' in reasoning_trace — redacting"
        )
        return False

    return level < _REASONING_REDACTION_THRESHOLD


def _redact_record(
    record_data: Dict[str, Any],
    disclosed_fields: List[str],
) -> RedactedAuditRecord:
    """Redact fields from an audit record.

    Non-redactable fields (timestamps, hashes, IDs) are always disclosed.
    Specified disclosed_fields are kept visible.
    All other fields are replaced with SHA-256 hashes.

    Special handling for reasoning_trace: applies confidentiality-based
    redaction. PUBLIC/RESTRICTED traces are kept visible; CONFIDENTIAL+
    traces are redacted to hash only. Explicitly disclosed reasoning_trace
    fields override confidentiality-based redaction.

    Args:
        record_data: The audit record as a dictionary
        disclosed_fields: Fields to keep visible

    Returns:
        RedactedAuditRecord with appropriate redactions
    """
    all_disclosed = set(disclosed_fields) | NON_REDACTABLE_FIELDS
    redacted_data: Dict[str, Any] = {}
    redacted_fields: List[str] = []
    actual_disclosed: List[str] = []

    for field_name, value in record_data.items():
        if field_name in all_disclosed:
            redacted_data[field_name] = value
            actual_disclosed.append(field_name)
        elif field_name == "reasoning_trace" and _should_keep_reasoning_trace(value):
            # Confidentiality-based reasoning trace disclosure:
            # PUBLIC/RESTRICTED traces are kept visible
            redacted_data[field_name] = value
            actual_disclosed.append(field_name)
        else:
            redacted_data[field_name] = _hash_value(value)
            redacted_fields.append(field_name)

    return RedactedAuditRecord(
        data=redacted_data,
        disclosed_fields=actual_disclosed,
        redacted_fields=redacted_fields,
    )


def _compute_chain_hash(records: List[Dict[str, Any]]) -> List[str]:
    """Compute hash chain over audit records.

    Each hash includes the previous hash, creating a tamper-evident chain.
    Uses the redacted data so witnesses can verify chain integrity.
    """
    hashes: List[str] = []
    prev_hash = GENESIS_HASH

    for record in records:
        payload = json.dumps(
            {"previous_hash": prev_hash, "record": record},
            sort_keys=True,
            default=str,
        )
        current_hash = hashlib.sha256(payload.encode()).hexdigest()
        hashes.append(current_hash)
        prev_hash = current_hash

    return hashes


def export_for_witness(
    audit_records: List[AuditRecord],
    disclosed_fields: List[str],
    signing_key: str,
    witness_id: Optional[str] = None,
) -> ExportPackage:
    """Export audit records with selective redaction for witness verification.

    Creates a signed export package where specified fields are visible
    and all other fields are replaced with SHA-256 hashes. The hash chain
    remains verifiable even with redacted fields.

    Args:
        audit_records: The audit records to export
        disclosed_fields: Field names to keep visible
        signing_key: Private key for signing the export
        witness_id: Optional identifier for the intended witness

    Returns:
        ExportPackage with redacted records and integrity proofs
    """
    # Convert records to dicts
    record_dicts = [_audit_record_to_dict(r) for r in audit_records]

    # Redact each record
    redacted_records = [_redact_record(rd, disclosed_fields) for rd in record_dicts]

    # Compute chain hashes over redacted data (witnesses verify this)
    chain_hashes = _compute_chain_hash([r.data for r in redacted_records])

    # Build export metadata
    metadata = {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "record_count": len(audit_records),
        "disclosed_fields": disclosed_fields,
        "non_redactable_fields": sorted(NON_REDACTABLE_FIELDS),
        "hash_algorithm": "sha256",
    }
    if witness_id:
        metadata["witness_id"] = witness_id

    # Sign the package
    sign_payload = json.dumps(
        {
            "chain_hashes": chain_hashes,
            "metadata": metadata,
            "record_count": len(redacted_records),
        },
        sort_keys=True,
    )
    signature = sign(sign_payload, signing_key)

    return ExportPackage(
        records=redacted_records,
        export_metadata=metadata,
        chain_hashes=chain_hashes,
        signature=signature,
    )


def verify_witness_export(
    export: ExportPackage,
    authority_public_key: str,
) -> WitnessVerificationResult:
    """Verify a witness export package for integrity and authenticity.

    Checks:
    1. Signature validity (was this signed by the claimed authority?)
    2. Hash chain integrity (have records been tampered with?)
    3. Redaction consistency (are non-redactable fields present?)

    Args:
        export: The export package to verify
        authority_public_key: Public key of the signing authority

    Returns:
        WitnessVerificationResult with verification details
    """
    errors: List[str] = []
    total_disclosed = 0
    total_redacted = 0

    # 1. Verify signature
    sign_payload = json.dumps(
        {
            "chain_hashes": export.chain_hashes,
            "metadata": export.export_metadata,
            "record_count": len(export.records),
        },
        sort_keys=True,
    )

    try:
        signature_valid = verify_signature(
            sign_payload, export.signature, authority_public_key
        )
    except Exception as e:
        signature_valid = False
        errors.append(f"Signature verification failed: {e}")

    # 2. Verify hash chain
    recomputed_hashes = _compute_chain_hash([r.data for r in export.records])
    chain_valid = hmac_mod.compare_digest(
        json.dumps(recomputed_hashes, sort_keys=True),
        json.dumps(export.chain_hashes, sort_keys=True),
    )
    if not chain_valid:
        errors.append(
            "Hash chain integrity check failed — records may have been tampered with"
        )

    # 3. Verify non-redactable fields are present
    for record in export.records:
        total_disclosed += len(record.disclosed_fields)
        total_redacted += len(record.redacted_fields)

        for required_field in NON_REDACTABLE_FIELDS:
            if required_field in record.data:
                if _is_redacted(record.data[required_field]):
                    errors.append(
                        f"Non-redactable field '{required_field}' is redacted in record {record.id}"
                    )

    return WitnessVerificationResult(
        valid=signature_valid and chain_valid and len(errors) == 0,
        signature_valid=signature_valid,
        chain_integrity_valid=chain_valid,
        disclosed_field_count=total_disclosed,
        redacted_field_count=total_redacted,
        record_count=len(export.records),
        errors=errors,
    )


__all__ = [
    "export_for_witness",
    "verify_witness_export",
    "ExportPackage",
    "RedactedAuditRecord",
    "WitnessVerificationResult",
    "NON_REDACTABLE_FIELDS",
]
