# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""
EATP SIEM Export (Phase 5b - VA1).

Provides CEF (Common Event Format) and OCSF (Open Cybersecurity Schema
Framework) serializers for EATP trust operations.  This enables direct
ingestion of EATP events into enterprise SIEM platforms such as Splunk,
Sentinel, QRadar, and CrowdStrike Falcon.

Event hierarchy::

    SIEMEvent           -- base event for all EATP operations
      +-- EstablishEvent  -- ESTABLISH operation (genesis, key binding)
      +-- DelegateEvent   -- DELEGATE operation (trust transfer)
      +-- VerifyEvent     -- VERIFY operation (chain validation)
      +-- AuditEvent      -- AUDIT operation (action recording)

Serializers:

    serialize_cef(event)   -> str           CEF v0 one-liner
    serialize_ocsf(event)  -> dict          OCSF 1.1 JSON-ready dict

Factory:

    from_audit_anchor(anchor, authority_id) -> AuditEvent
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from kailash.trust.chain import ActionResult, AuditAnchor

logger = logging.getLogger(__name__)

# ============================================================================
# Constants
# ============================================================================

_CEF_VERSION = "0"
_DEVICE_VENDOR = "Terrene Foundation"
_DEVICE_PRODUCT = "EATP"
_DEVICE_VERSION = "1.0"

# OCSF class_uid for Authentication (3002) / category Identity & Access (3)
_OCSF_CLASS_UID = 3002
_OCSF_CATEGORY_UID = 3

# OCSF activity_id mapping for EATP operations
_OCSF_ACTIVITY_ID: Dict[str, int] = {
    "ESTABLISH": 1,  # Logon / Create
    "DELEGATE": 2,  # Logoff / Assign (repurposed as delegation)
    "VERIFY": 3,  # Authentication Ticket / Verify
    "AUDIT": 4,  # Service Ticket / Record
}

# OCSF status_id mapping for EATP results
_OCSF_STATUS_ID: Dict[str, int] = {
    "SUCCESS": 1,  # Success
    "FAILURE": 2,  # Failure
    "DENIED": 2,  # Failure (access denied is a failure variant)
    "PARTIAL": 99,  # Other
}

# OCSF severity_id mapping from CEF severity (0-10) to OCSF (0-5)
_OCSF_SEVERITY_MAPPING: Dict[int, int] = {
    0: 0,  # Unknown
    1: 1,  # Informational
    2: 1,
    3: 2,  # Low
    4: 2,
    5: 3,  # Medium
    6: 3,
    7: 4,  # High
    8: 4,
    9: 5,  # Critical
    10: 5,
}

# Severity assigned by from_audit_anchor based on ActionResult
_RESULT_SEVERITY: Dict[str, int] = {
    "success": 1,
    "failure": 5,
    "denied": 8,
    "partial": 3,
}

# Human-readable names for CEF Name field
_CEF_EVENT_NAMES: Dict[str, str] = {
    "ESTABLISH": "EATP ESTABLISH Trust",
    "DELEGATE": "EATP DELEGATE Trust",
    "VERIFY": "EATP VERIFY Trust",
    "AUDIT": "EATP AUDIT Action",
}


# ============================================================================
# Data classes
# ============================================================================


@dataclass
class SIEMEvent:
    """Base SIEM event for EATP operations.

    Attributes:
        timestamp: When the event occurred (UTC).
        agent_id: The agent involved in this operation.
        operation: EATP operation name (ESTABLISH, DELEGATE, VERIFY, AUDIT).
        result: Outcome (SUCCESS, FAILURE, DENIED, PARTIAL).
        severity: CEF severity scale 0-10.
        event_id: Unique event identifier (auto-generated UUID).
        authority_id: Authority involved, if any.
        source_ip: Source IP address, if available.
        metadata: Arbitrary additional key-value pairs.
    """

    timestamp: datetime
    agent_id: str
    operation: str  # ESTABLISH, DELEGATE, VERIFY, AUDIT
    result: str  # SUCCESS, FAILURE, DENIED, PARTIAL
    severity: int  # 0-10 (CEF severity scale)
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    authority_id: Optional[str] = None
    source_ip: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class EstablishEvent(SIEMEvent):
    """SIEM event for ESTABLISH operations.

    Attributes:
        public_key_hash: Hash of the agent's public key.
        capabilities_count: Number of capabilities granted.
    """

    public_key_hash: Optional[str] = None
    capabilities_count: int = 0


@dataclass
class DelegateEvent(SIEMEvent):
    """SIEM event for DELEGATE operations.

    Attributes:
        delegator_id: Agent performing the delegation.
        delegation_depth: Distance from original human authority.
        constraints_count: Number of constraints applied.
    """

    delegator_id: Optional[str] = None
    delegation_depth: int = 0
    constraints_count: int = 0


@dataclass
class VerifyEvent(SIEMEvent):
    """SIEM event for VERIFY operations.

    Attributes:
        verification_level: Level of verification (QUICK, STANDARD, FULL).
        trust_score: Computed trust score (0-100).
        action_verified: The action that was being verified.
    """

    verification_level: Optional[str] = None
    trust_score: Optional[int] = None
    action_verified: Optional[str] = None


@dataclass
class AuditEvent(SIEMEvent):
    """SIEM event for AUDIT operations.

    Attributes:
        action: The action that was audited.
        resource: The resource affected by the action.
        chain_hash: Trust chain hash at the time of action.
    """

    action: Optional[str] = None
    resource: Optional[str] = None
    chain_hash: Optional[str] = None


# ============================================================================
# CEF Serializer
# ============================================================================


def _escape_cef_header_value(value: str) -> str:
    """Escape special characters in CEF header fields.

    In CEF header fields, only backslash and pipe need escaping.

    Args:
        value: Raw string value.

    Returns:
        Escaped string safe for CEF header fields.
    """
    value = value.replace("\\", "\\\\")
    value = value.replace("|", "\\|")
    return value


def _escape_cef_extension_value(value: str) -> str:
    """Escape special characters in CEF extension values.

    CEF extension values require escaping of: backslash, equals,
    newline, and pipe characters.

    Args:
        value: Raw string value.

    Returns:
        Escaped string safe for CEF extension values.
    """
    value = value.replace("\\", "\\\\")
    value = value.replace("|", "\\|")
    value = value.replace("=", "\\=")
    value = value.replace("\n", "\\n")
    value = value.replace("\r", "\\r")
    return value


def _build_cef_extensions(event: SIEMEvent) -> str:
    """Build the CEF extension key=value pairs for an event.

    Args:
        event: The SIEM event to serialize.

    Returns:
        Space-separated CEF extension string.
    """
    extensions: list[str] = []

    def _add(key: str, value: Any) -> None:
        if value is not None:
            extensions.append(f"{key}={_escape_cef_extension_value(str(value))}")

    # Standard CEF extensions
    _add("externalId", event.event_id)
    _add("duser", event.agent_id)

    # Timestamp as epoch millis for CEF rt field
    epoch_ms = int(event.timestamp.timestamp() * 1000)
    _add("rt", epoch_ms)

    _add("outcome", event.result)

    if event.authority_id is not None:
        _add("suser", event.authority_id)

    if event.source_ip is not None:
        _add("src", event.source_ip)

    # Type-specific extensions
    if isinstance(event, EstablishEvent):
        if event.public_key_hash is not None:
            _add("cs1", event.public_key_hash)
            _add("cs1Label", "publicKeyHash")
        _add("cn1", event.capabilities_count)
        _add("cn1Label", "capabilitiesCount")

    elif isinstance(event, DelegateEvent):
        if event.delegator_id is not None:
            _add("cs1", event.delegator_id)
            _add("cs1Label", "delegatorId")
        _add("cn1", event.delegation_depth)
        _add("cn1Label", "delegationDepth")
        _add("cn2", event.constraints_count)
        _add("cn2Label", "constraintsCount")

    elif isinstance(event, VerifyEvent):
        if event.verification_level is not None:
            _add("cs1", event.verification_level)
            _add("cs1Label", "verificationLevel")
        if event.trust_score is not None:
            _add("cn1", event.trust_score)
            _add("cn1Label", "trustScore")
        if event.action_verified is not None:
            _add("cs2", event.action_verified)
            _add("cs2Label", "actionVerified")

    elif isinstance(event, AuditEvent):
        if event.action is not None:
            _add("act", event.action)
        if event.resource is not None:
            _add("cs1", event.resource)
            _add("cs1Label", "resource")
        if event.chain_hash is not None:
            _add("cs2", event.chain_hash)
            _add("cs2Label", "chainHash")

    return " ".join(extensions)


def serialize_cef(event: SIEMEvent) -> str:
    """Serialize SIEM event to CEF (Common Event Format).

    Format::

        CEF:0|Terrene Foundation|EATP|1.0|{sig_id}|{name}|{severity}|{extensions}

    CEF header fields:
        - Version: 0
        - Device Vendor: Terrene Foundation
        - Device Product: EATP
        - Device Version: 1.0
        - Signature ID: operation name (e.g., "ESTABLISH")
        - Name: human-readable event name
        - Severity: 0-10

    CEF extension fields map EATP event attributes to standard CEF keys:
        duser=agent_id, rt=timestamp (epoch ms), outcome=result,
        suser=authority_id, src=source_ip, externalId=event_id.

    Args:
        event: The SIEM event to serialize.

    Returns:
        A single-line CEF v0 string.

    Raises:
        ValueError: If event is None.
    """
    if event is None:
        raise ValueError("Cannot serialize None event to CEF")

    sig_id = _escape_cef_header_value(event.operation)
    name = _escape_cef_header_value(_CEF_EVENT_NAMES.get(event.operation, f"EATP {event.operation}"))
    severity = str(event.severity)
    extensions = _build_cef_extensions(event)

    return (
        f"CEF:{_CEF_VERSION}"
        f"|{_DEVICE_VENDOR}"
        f"|{_DEVICE_PRODUCT}"
        f"|{_DEVICE_VERSION}"
        f"|{sig_id}"
        f"|{name}"
        f"|{severity}"
        f"|{extensions}"
    )


# ============================================================================
# OCSF Serializer
# ============================================================================


def _build_ocsf_unmapped(event: SIEMEvent) -> Dict[str, Any]:
    """Build OCSF unmapped dict for type-specific fields.

    Fields that do not have a direct OCSF mapping are placed in the
    ``unmapped`` dict, which is a standard OCSF extension point.

    Args:
        event: The SIEM event to extract unmapped fields from.

    Returns:
        Dict of unmapped field names to values.
    """
    unmapped: Dict[str, Any] = {}

    if isinstance(event, EstablishEvent):
        if event.public_key_hash is not None:
            unmapped["public_key_hash"] = event.public_key_hash
        unmapped["capabilities_count"] = event.capabilities_count

    elif isinstance(event, DelegateEvent):
        if event.delegator_id is not None:
            unmapped["delegator_id"] = event.delegator_id
        unmapped["delegation_depth"] = event.delegation_depth
        unmapped["constraints_count"] = event.constraints_count

    elif isinstance(event, VerifyEvent):
        if event.verification_level is not None:
            unmapped["verification_level"] = event.verification_level
        if event.trust_score is not None:
            unmapped["trust_score"] = event.trust_score
        if event.action_verified is not None:
            unmapped["action_verified"] = event.action_verified

    elif isinstance(event, AuditEvent):
        if event.action is not None:
            unmapped["action"] = event.action
        if event.resource is not None:
            unmapped["resource"] = event.resource
        if event.chain_hash is not None:
            unmapped["chain_hash"] = event.chain_hash

    return unmapped


def serialize_ocsf(event: SIEMEvent) -> Dict[str, Any]:
    """Serialize SIEM event to OCSF (Open Cybersecurity Schema Framework).

    Maps EATP operations to OCSF activity categories and returns a
    JSON-serializable dict suitable for ingestion by OCSF-compatible
    SIEM platforms.

    OCSF fields produced:
        class_uid, category_uid, activity_id, activity_name,
        severity_id, time (epoch ms), uid, status, status_id,
        actor, metadata, src_endpoint (if source_ip present),
        unmapped (type-specific EATP fields).

    Args:
        event: The SIEM event to serialize.

    Returns:
        A JSON-serializable dict conforming to OCSF 1.1 structure.

    Raises:
        ValueError: If event is None.
    """
    if event is None:
        raise ValueError("Cannot serialize None event to OCSF")

    activity_id = _OCSF_ACTIVITY_ID.get(event.operation, 0)
    activity_name = _CEF_EVENT_NAMES.get(event.operation, f"EATP {event.operation}")
    severity_id = _OCSF_SEVERITY_MAPPING.get(event.severity, 0)
    status_id = _OCSF_STATUS_ID.get(event.result, 0)
    epoch_ms = int(event.timestamp.timestamp() * 1000)

    # Build actor
    actor: Dict[str, Any] = {
        "user": {
            "uid": event.agent_id,
            "type": "Agent",
        },
    }
    if event.authority_id is not None:
        actor["authorizations"] = [
            {"uid": event.authority_id, "type": "Authority"},
        ]

    # Build OCSF envelope
    ocsf: Dict[str, Any] = {
        "class_uid": _OCSF_CLASS_UID,
        "category_uid": _OCSF_CATEGORY_UID,
        "activity_id": activity_id,
        "activity_name": activity_name,
        "severity_id": severity_id,
        "time": epoch_ms,
        "uid": event.event_id,
        "status": event.result,
        "status_id": status_id,
        "actor": actor,
        "metadata": {
            "product": {
                "vendor_name": _DEVICE_VENDOR,
                "name": _DEVICE_PRODUCT,
                "version": _DEVICE_VERSION,
            },
            "version": "1.1.0",
        },
    }

    # Optional: source endpoint
    if event.source_ip is not None:
        ocsf["src_endpoint"] = {"ip": event.source_ip}

    # Unmapped type-specific fields
    unmapped = _build_ocsf_unmapped(event)
    if unmapped:
        ocsf["unmapped"] = unmapped

    # Include event-level metadata if present
    if event.metadata:
        ocsf["unmapped"] = ocsf.get("unmapped", {})
        ocsf["unmapped"]["event_metadata"] = event.metadata

    return ocsf


# ============================================================================
# Factory function
# ============================================================================


def from_audit_anchor(anchor: AuditAnchor, authority_id: Optional[str] = None) -> AuditEvent:
    """Create an AuditEvent from an existing AuditAnchor.

    Maps AuditAnchor fields to AuditEvent fields, translating
    ActionResult enum values to SIEM-friendly strings and assigning
    severity based on the action result.

    Severity mapping:
        - SUCCESS -> 1 (low)
        - PARTIAL -> 3 (low-medium)
        - FAILURE -> 5 (medium)
        - DENIED  -> 8 (high)

    Args:
        anchor: The AuditAnchor to convert.
        authority_id: Optional authority ID to attach to the event.

    Returns:
        An AuditEvent populated from the anchor's fields.

    Raises:
        ValueError: If anchor is None.
    """
    if anchor is None:
        raise ValueError("Cannot create AuditEvent from None anchor. Provide a valid AuditAnchor instance.")

    result_str = anchor.result.value.upper()
    severity = _RESULT_SEVERITY.get(anchor.result.value, 3)

    return AuditEvent(
        timestamp=anchor.timestamp,
        agent_id=anchor.agent_id,
        operation="AUDIT",
        result=result_str,
        severity=severity,
        authority_id=authority_id,
        action=anchor.action,
        resource=anchor.resource,
        chain_hash=anchor.trust_chain_hash,
        metadata={"context": anchor.context} if anchor.context else {},
    )


__all__ = [
    "SIEMEvent",
    "EstablishEvent",
    "DelegateEvent",
    "VerifyEvent",
    "AuditEvent",
    "serialize_cef",
    "serialize_ocsf",
    "from_audit_anchor",
]
