# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""SIEM export for TrustPlane records.

Provides CEF (Common Event Format), OCSF (Open Cybersecurity Schema
Framework), and syslog formatters for TrustPlane trust records.  Enables
enterprise SIEM integration for platforms like Splunk, Sentinel, QRadar,
and CrowdStrike Falcon.

Supported record types:
    - DecisionRecord  -> CEF/OCSF event
    - MilestoneRecord -> CEF/OCSF event
    - HoldRecord      -> CEF/OCSF event
    - ExecutionRecord  -> CEF/OCSF event
    - EscalationRecord -> CEF/OCSF event
    - InterventionRecord -> CEF/OCSF event

Functions:
    format_cef(record, project_name, version)  -> str  (CEF v0 line)
    format_ocsf(record, project_name)          -> dict (OCSF 1.1 JSON)
    create_syslog_handler(host, port, protocol) -> SysLogHandler
    export_events(store, format, since)        -> list[str | dict]
"""

from __future__ import annotations

import json
import logging
import logging.handlers
import socket
import uuid
from datetime import datetime, timezone
from typing import Any, Union

from trustplane.exceptions import TLSSyslogError
from trustplane.holds import HoldRecord
from trustplane.models import (
    DecisionRecord,
    EscalationRecord,
    ExecutionRecord,
    InterventionRecord,
    MilestoneRecord,
    VerificationCategory,
    _decision_type_value,
)

logger = logging.getLogger(__name__)

__all__ = [
    "format_cef",
    "format_ocsf",
    "create_syslog_handler",
    "create_tls_syslog_handler",
    "export_events",
]

# Type alias for all supported record types
SIEMRecord = Union[
    DecisionRecord,
    MilestoneRecord,
    HoldRecord,
    ExecutionRecord,
    EscalationRecord,
    InterventionRecord,
]

# ============================================================================
# Constants
# ============================================================================

_CEF_VERSION = "0"
_DEVICE_VENDOR = "TerreneFoundation"
_DEVICE_PRODUCT = "TrustPlane"
_DEFAULT_VERSION = "0.2.0"

# OCSF category_uid for Application Activity
_OCSF_CATEGORY_UID = 6

# OCSF class_uid for API Activity (6003)
_OCSF_CLASS_UID = 6003

# OCSF severity_id mapping from CEF severity (0-10) to OCSF (0-5)
_OCSF_SEVERITY_MAP = {
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

# VerificationCategory -> CEF severity range
_VERIFICATION_CATEGORY_SEVERITY = {
    VerificationCategory.AUTO_APPROVED: 1,
    VerificationCategory.FLAGGED: 4,
    VerificationCategory.HELD: 7,
    VerificationCategory.BLOCKED: 9,
}

# HoldRecord status -> CEF severity
_HOLD_STATUS_SEVERITY = {
    "pending": 7,
    "approved": 3,
    "denied": 9,
}


# ============================================================================
# CEF Helpers
# ============================================================================


def _escape_cef_header(value: str) -> str:
    """Escape special characters in CEF header fields.

    In CEF header fields, backslash, pipe, and newlines need escaping.
    Newlines in header fields would split the CEF event into multiple
    syslog messages, enabling log injection attacks.
    """
    value = value.replace("\\", "\\\\")
    value = value.replace("|", "\\|")
    value = value.replace("\n", " ")
    value = value.replace("\r", " ")
    return value


def _escape_cef_extension(value: str) -> str:
    """Escape special characters in CEF extension values.

    CEF extension values require escaping of backslash, equals,
    newline, and pipe characters.
    """
    value = value.replace("\\", "\\\\")
    value = value.replace("|", "\\|")
    value = value.replace("=", "\\=")
    value = value.replace("\n", "\\n")
    value = value.replace("\r", "\\r")
    return value


def _cef_extensions(pairs: list[tuple[str, Any]]) -> str:
    """Build CEF extension key=value string from pairs, skipping None values."""
    parts: list[str] = []
    for key, val in pairs:
        if val is not None:
            parts.append(f"{key}={_escape_cef_extension(str(val))}")
    return " ".join(parts)


# ============================================================================
# Record -> CEF severity
# ============================================================================


def _severity_for_record(record: SIEMRecord) -> int:
    """Determine CEF severity (0-10) for a record."""
    if isinstance(record, DecisionRecord):
        # Map review requirement to a base severity
        review_map = {"quick": 1, "standard": 2, "full": 3}
        return review_map.get(record.review_requirement.value, 2)

    if isinstance(record, MilestoneRecord):
        return 1

    if isinstance(record, HoldRecord):
        return _HOLD_STATUS_SEVERITY.get(record.status, 7)

    if isinstance(record, ExecutionRecord):
        return _VERIFICATION_CATEGORY_SEVERITY.get(record.verification_category, 1)

    if isinstance(record, EscalationRecord):
        return _VERIFICATION_CATEGORY_SEVERITY.get(record.verification_category, 7)

    if isinstance(record, InterventionRecord):
        return _VERIFICATION_CATEGORY_SEVERITY.get(record.verification_category, 5)

    return 1


# ============================================================================
# Record -> event ID / name
# ============================================================================


def _event_id_for_record(record: SIEMRecord) -> str:
    """Return a stable event identifier for a record."""
    if isinstance(record, DecisionRecord):
        return record.decision_id
    if isinstance(record, MilestoneRecord):
        return record.milestone_id
    if isinstance(record, HoldRecord):
        return record.hold_id
    if isinstance(record, ExecutionRecord):
        return record.execution_id
    if isinstance(record, EscalationRecord):
        return record.escalation_id
    if isinstance(record, InterventionRecord):
        return record.intervention_id
    return str(uuid.uuid4())


def _event_name_for_record(record: SIEMRecord) -> str:
    """Return a human-readable event name for a record."""
    if isinstance(record, DecisionRecord):
        dt_val = _decision_type_value(record.decision_type)
        return f"TrustPlane Decision ({dt_val})"
    if isinstance(record, MilestoneRecord):
        return f"TrustPlane Milestone ({record.version})"
    if isinstance(record, HoldRecord):
        return f"TrustPlane Hold ({record.status})"
    if isinstance(record, ExecutionRecord):
        return f"TrustPlane Execution ({record.verification_category.value})"
    if isinstance(record, EscalationRecord):
        return f"TrustPlane Escalation ({record.verification_category.value})"
    if isinstance(record, InterventionRecord):
        return f"TrustPlane Intervention ({record.verification_category.value})"
    return "TrustPlane Event"


def _timestamp_for_record(record: SIEMRecord) -> datetime:
    """Extract the timestamp from a record."""
    if isinstance(record, DecisionRecord):
        return record.timestamp
    if isinstance(record, MilestoneRecord):
        return record.timestamp
    if isinstance(record, HoldRecord):
        return record.created_at
    if isinstance(record, ExecutionRecord):
        return record.timestamp
    if isinstance(record, EscalationRecord):
        return record.timestamp
    if isinstance(record, InterventionRecord):
        return record.timestamp
    return datetime.now(timezone.utc)


# ============================================================================
# CEF Formatter
# ============================================================================


def format_cef(
    record: SIEMRecord,
    project_name: str = "",
    version: str = _DEFAULT_VERSION,
) -> str:
    """Format a TrustPlane record as a CEF (Common Event Format) line.

    CEF header format::

        CEF:0|TerreneFoundation|TrustPlane|<version>|<eventId>|<eventName>|<severity>|<extensions>

    Args:
        record: The TrustPlane record to format.
        project_name: Project name for extension context.
        version: Product version string.

    Returns:
        A single-line CEF v0 string.
    """
    event_id = _escape_cef_header(_event_id_for_record(record))
    event_name = _escape_cef_header(_event_name_for_record(record))
    severity = _severity_for_record(record)
    timestamp = _timestamp_for_record(record)
    epoch_ms = int(timestamp.timestamp() * 1000)

    # Build extension pairs
    ext_pairs: list[tuple[str, Any]] = [
        ("rt", epoch_ms),
        ("externalId", _event_id_for_record(record)),
    ]

    if project_name:
        ext_pairs.append(("cs1", project_name))
        ext_pairs.append(("cs1Label", "projectName"))

    # Record-specific extensions
    if isinstance(record, DecisionRecord):
        ext_pairs.append(("act", "decision"))
        ext_pairs.append(("msg", record.decision))
        ext_pairs.append(("reason", record.rationale))
        ext_pairs.append(("duser", record.author))
        ext_pairs.append(("cn1", record.confidence))
        ext_pairs.append(("cn1Label", "confidence"))

    elif isinstance(record, MilestoneRecord):
        ext_pairs.append(("act", "milestone"))
        ext_pairs.append(("msg", record.description))
        ext_pairs.append(("duser", record.author))
        ext_pairs.append(("cs2", record.version))
        ext_pairs.append(("cs2Label", "milestoneVersion"))
        if record.file_hash:
            ext_pairs.append(("fileHash", record.file_hash))

    elif isinstance(record, HoldRecord):
        ext_pairs.append(("act", record.action))
        ext_pairs.append(("msg", record.reason))
        ext_pairs.append(("cs2", record.resource))
        ext_pairs.append(("cs2Label", "resource"))
        ext_pairs.append(("outcome", record.status))
        if record.resolved_by:
            ext_pairs.append(("suser", record.resolved_by))

    elif isinstance(record, ExecutionRecord):
        ext_pairs.append(("act", record.action))
        ext_pairs.append(("outcome", record.verification_category.value))
        ext_pairs.append(("cn1", record.confidence))
        ext_pairs.append(("cn1Label", "confidence"))

    elif isinstance(record, EscalationRecord):
        ext_pairs.append(("act", "escalation"))
        ext_pairs.append(("msg", record.trigger))
        ext_pairs.append(("outcome", record.verification_category.value))
        ext_pairs.append(("cn1", record.confidence))
        ext_pairs.append(("cn1Label", "confidence"))
        if record.human_authority:
            ext_pairs.append(("suser", record.human_authority))

    elif isinstance(record, InterventionRecord):
        ext_pairs.append(("act", "intervention"))
        ext_pairs.append(("msg", record.observation))
        ext_pairs.append(("outcome", record.verification_category.value))
        if record.human_authority:
            ext_pairs.append(("suser", record.human_authority))

    extensions = _cef_extensions(ext_pairs)

    return (
        f"CEF:{_CEF_VERSION}"
        f"|{_DEVICE_VENDOR}"
        f"|{_DEVICE_PRODUCT}"
        f"|{_escape_cef_header(version)}"
        f"|{event_id}"
        f"|{event_name}"
        f"|{severity}"
        f"|{extensions}"
    )


# ============================================================================
# OCSF Formatter
# ============================================================================


def format_ocsf(
    record: SIEMRecord,
    project_name: str = "",
) -> dict[str, Any]:
    """Format a TrustPlane record as an OCSF v1.1 event dict.

    Maps records to the ``api_activity`` event class (class_uid: 6003)
    under Application Activity (category_uid: 6).

    Args:
        record: The TrustPlane record to format.
        project_name: Project name for metadata context.

    Returns:
        A JSON-serializable dict conforming to OCSF 1.1 structure.
    """
    severity = _severity_for_record(record)
    ocsf_severity = _OCSF_SEVERITY_MAP.get(severity, 0)
    timestamp = _timestamp_for_record(record)
    epoch_ms = int(timestamp.timestamp() * 1000)
    event_id = _event_id_for_record(record)

    # Determine activity name and actor
    activity_name = _event_name_for_record(record)
    actor: dict[str, Any] = {}
    api: dict[str, Any] = {}
    unmapped: dict[str, Any] = {}

    if isinstance(record, DecisionRecord):
        actor = {
            "user": {"uid": record.author, "type": "Human"},
        }
        api = {
            "operation": "decision",
            "request": {
                "uid": record.decision_id,
            },
        }
        unmapped = {
            "decision_type": _decision_type_value(record.decision_type),
            "decision": record.decision,
            "rationale": record.rationale,
            "confidence": record.confidence,
            "review_requirement": record.review_requirement.value,
        }
        if record.alternatives:
            unmapped["alternatives"] = record.alternatives
        if record.risks:
            unmapped["risks"] = record.risks

    elif isinstance(record, MilestoneRecord):
        actor = {
            "user": {"uid": record.author, "type": "Human"},
        }
        api = {
            "operation": "milestone",
            "request": {
                "uid": record.milestone_id,
            },
        }
        unmapped = {
            "version": record.version,
            "description": record.description,
            "decision_count": record.decision_count,
        }
        if record.file_hash:
            unmapped["file_hash"] = record.file_hash

    elif isinstance(record, HoldRecord):
        actor = {
            "user": {"uid": record.resolved_by or "system", "type": "System"},
        }
        api = {
            "operation": "hold",
            "request": {
                "uid": record.hold_id,
            },
        }
        unmapped = {
            "action": record.action,
            "resource": record.resource,
            "reason": record.reason,
            "status": record.status,
        }
        if record.resolution_reason:
            unmapped["resolution_reason"] = record.resolution_reason

    elif isinstance(record, ExecutionRecord):
        actor = {
            "user": {"uid": "ai-agent", "type": "Agent"},
        }
        api = {
            "operation": "execution",
            "request": {
                "uid": record.execution_id,
            },
        }
        unmapped = {
            "action": record.action,
            "verification_category": record.verification_category.value,
            "confidence": record.confidence,
        }

    elif isinstance(record, EscalationRecord):
        actor = {
            "user": {"uid": record.human_authority or "ai-agent", "type": "Agent"},
        }
        api = {
            "operation": "escalation",
            "request": {
                "uid": record.escalation_id,
            },
        }
        unmapped = {
            "trigger": record.trigger,
            "verification_category": record.verification_category.value,
            "confidence": record.confidence,
        }
        if record.recommendation:
            unmapped["recommendation"] = record.recommendation
        if record.human_response:
            unmapped["human_response"] = record.human_response

    elif isinstance(record, InterventionRecord):
        actor = {
            "user": {
                "uid": record.human_authority or "human",
                "type": "Human",
            },
        }
        api = {
            "operation": "intervention",
            "request": {
                "uid": record.intervention_id,
            },
        }
        unmapped = {
            "observation": record.observation,
            "verification_category": record.verification_category.value,
            "confidence": record.confidence,
        }
        if record.action_taken:
            unmapped["action_taken"] = record.action_taken

    # Build OCSF envelope
    ocsf: dict[str, Any] = {
        "class_uid": _OCSF_CLASS_UID,
        "category_uid": _OCSF_CATEGORY_UID,
        "activity_id": 1,  # Create / Record
        "activity_name": activity_name,
        "severity_id": ocsf_severity,
        "severity": _ocsf_severity_label(ocsf_severity),
        "time": epoch_ms,
        "uid": event_id,
        "status": "Success",
        "status_id": 1,
        "actor": actor,
        "api": api,
        "metadata": {
            "product": {
                "vendor_name": "Terrene Foundation",
                "name": "TrustPlane",
                "version": _DEFAULT_VERSION,
            },
            "version": "1.1.0",
        },
    }

    if project_name:
        ocsf["metadata"]["project_name"] = project_name

    if unmapped:
        ocsf["unmapped"] = unmapped

    return ocsf


def _ocsf_severity_label(severity_id: int) -> str:
    """Map OCSF severity_id to human-readable label."""
    labels = {
        0: "Unknown",
        1: "Informational",
        2: "Low",
        3: "Medium",
        4: "High",
        5: "Critical",
    }
    return labels.get(severity_id, "Unknown")


# ============================================================================
# Syslog Handler
# ============================================================================


def create_syslog_handler(
    host: str = "localhost",
    port: int = 514,
    protocol: str = "udp",
) -> logging.handlers.SysLogHandler:
    """Create a SysLogHandler for streaming events to a SIEM.

    Args:
        host: Syslog server hostname or IP.
        port: Syslog server port (default 514).
        protocol: Transport protocol - "udp" (default) or "tcp".

    Returns:
        A configured SysLogHandler instance.

    Raises:
        ValueError: If protocol is not "udp" or "tcp".
    """
    protocol = protocol.lower()
    if protocol not in ("udp", "tcp"):
        raise ValueError(f"Invalid protocol '{protocol}'. Must be 'udp' or 'tcp'.")

    socktype = socket.SOCK_DGRAM if protocol == "udp" else socket.SOCK_STREAM

    handler = logging.handlers.SysLogHandler(
        address=(host, port),
        socktype=socktype,
    )
    handler.setFormatter(logging.Formatter("%(message)s"))
    return handler


def create_tls_syslog_handler(
    host: str,
    port: int = 6514,
    ca_cert: str | None = None,
    client_cert: str | None = None,
    client_key: str | None = None,
) -> logging.Handler:
    """Create a TLS-encrypted syslog handler (RFC 5425).

    Uses TLS 1.2+ with certificate verification for encrypted syslog
    transport. Enterprise compliance requires encrypted transport for
    security events.

    Args:
        host: Syslog server hostname or IP.
        port: Syslog TLS port (default 6514 per RFC 5425).
        ca_cert: Path to CA certificate file for server verification.
            If None, uses system default CA bundle.
        client_cert: Path to client certificate for mutual TLS.
        client_key: Path to client private key for mutual TLS.

    Returns:
        A logging.Handler that sends messages over TLS-encrypted TCP.

    Raises:
        TLSSyslogError: If TLS handshake fails or certificates are invalid.
        ValueError: If client_cert is provided without client_key.
    """
    import ssl

    if client_cert and not client_key:
        raise ValueError(
            "client_key is required when client_cert is provided (mutual TLS)"
        )

    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.minimum_version = ssl.TLSVersion.TLSv1_2

    if ca_cert:
        context.load_verify_locations(ca_cert)
    else:
        context.load_default_certs()

    if client_cert and client_key:
        context.load_cert_chain(certfile=client_cert, keyfile=client_key)

    try:
        raw_sock = socket.create_connection((host, port), timeout=10)
        try:
            tls_sock = context.wrap_socket(raw_sock, server_hostname=host)
        except Exception:
            raw_sock.close()  # Prevent socket leak on TLS handshake failure
            raise
    except ssl.SSLError as exc:
        raise TLSSyslogError(f"TLS handshake failed with {host}:{port}: {exc}") from exc
    except OSError as exc:
        raise TLSSyslogError(f"Cannot connect to {host}:{port}: {exc}") from exc

    handler = logging.handlers.SocketHandler.__new__(logging.handlers.SocketHandler)
    handler.host = host
    handler.port = port
    handler.sock = tls_sock
    handler.closeOnError = False
    handler.retryTime = None
    handler.retryStart = 1.0
    handler.retryMax = 30.0
    handler.retryFactor = 2.0

    # Use a simple emit that sends the formatted message over the TLS socket
    class _TLSSyslogHandler(logging.Handler):
        """Syslog handler that writes to a pre-established TLS socket."""

        def __init__(self, sock: Any) -> None:
            super().__init__()
            self._sock = sock
            self.setFormatter(logging.Formatter("%(message)s"))

        def emit(self, record: logging.LogRecord) -> None:
            try:
                msg = self.format(record)
                # RFC 5425 octet-framing: length SP message
                encoded = msg.encode("utf-8")
                framed = f"{len(encoded)} ".encode("ascii") + encoded
                self._sock.sendall(framed)
            except Exception:
                self.handleError(record)

        def close(self) -> None:
            try:
                self._sock.close()
            except Exception:
                pass
            super().close()

    return _TLSSyslogHandler(tls_sock)


# ============================================================================
# Batch Export
# ============================================================================


def export_events(
    store: Any,
    fmt: str = "cef",
    since: datetime | None = None,
    project_name: str = "",
    version: str = _DEFAULT_VERSION,
) -> list[str | dict[str, Any]]:
    """Export all trust records from a store in the specified format.

    Collects decisions, milestones, and holds from the store, optionally
    filters by timestamp, and formats each record.

    Args:
        store: A TrustPlaneStore instance.
        fmt: Output format - "cef" or "ocsf".
        since: If provided, only include records after this datetime.
        project_name: Project name for event context.
        version: Product version string.

    Returns:
        List of formatted events (str for CEF, dict for OCSF).
    """
    records: list[SIEMRecord] = []

    # Collect records with explicit limits (Store Contract: BOUNDED_RESULTS)
    _EXPORT_LIMIT = 100_000

    for dec in store.list_decisions(limit=_EXPORT_LIMIT):
        records.append(dec)

    for ms in store.list_milestones(limit=_EXPORT_LIMIT):
        records.append(ms)

    for hold in store.list_holds(limit=_EXPORT_LIMIT):
        records.append(hold)

    # Filter by timestamp if since is provided
    if since is not None:
        # Ensure since is timezone-aware
        if since.tzinfo is None:
            since = since.replace(tzinfo=timezone.utc)
        records = [r for r in records if _timestamp_for_record(r) >= since]

    # Sort by timestamp
    records.sort(key=lambda r: _timestamp_for_record(r))

    # Format
    events: list[str | dict[str, Any]] = []
    for record in records:
        if fmt == "cef":
            events.append(
                format_cef(record, project_name=project_name, version=version)
            )
        elif fmt == "ocsf":
            events.append(format_ocsf(record, project_name=project_name))
        else:
            raise ValueError(f"Unsupported format '{fmt}'. Use 'cef' or 'ocsf'.")

    return events
