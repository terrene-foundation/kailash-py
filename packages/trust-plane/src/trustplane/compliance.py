# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""SOC2 and ISO 27001 evidence mapping and GRC export for TrustPlane.

Maps TrustPlane records and security patterns to compliance framework controls:

SOC2 Trust Services Criteria:
- DecisionRecord      -> CC6.7 (Restriction of Privileged Access)
- MilestoneRecord     -> CC7.2 (System Monitoring)
- ExecutionRecord     -> CC6.8 (Monitoring)
- HELD/BLOCKED        -> CC7.3 (Evaluation of Security Events)
- Delegation records  -> CC6.3 (Removal of Access)
- Genesis record      -> CC6.2 (Inventory of Information Assets)
- RBAC / OIDC         -> CC6.1 (Logical and Physical Access Controls)
- Input validation    -> CC6.6 (System Operation Controls)
- SIEM export         -> CC7.1 (Detection and Monitoring)
- TLS syslog          -> CC7.4 (Response to Security Incidents)
- Atomic writes       -> CC8.1 (Change Management)

ISO 27001 Annex A:
- DecisionRecord      -> A.9.2 (User Access Management)
- MilestoneRecord     -> A.12.4 (Logging and Monitoring)
- HELD/BLOCKED        -> A.16.1 (Management of Information Security Incidents)
- RBAC roles          -> A.6.1 (Organization of Information Security)
- OIDC / bearer auth  -> A.9.4 (System and Application Access Control)
- Ed25519 / HMAC      -> A.10.1 (Cryptographic Controls)
- Store archival      -> A.12.3 (Information Backup)
- Hardened patterns    -> A.14.2 (Security in Development)
- Shadow retention    -> A.18.1 (Compliance with Legal and Contractual Requirements)
"""

from __future__ import annotations

import csv
import io
import json
import logging
from datetime import datetime, timezone
from typing import Any

from trustplane.holds import HoldRecord
from trustplane.models import (
    DecisionRecord,
    MilestoneRecord,
    VerificationCategory,
    _decision_type_value,
)

logger = logging.getLogger(__name__)

__all__ = [
    "generate_soc2_evidence",
    "generate_iso27001_evidence",
    "export_decisions_csv",
    "export_violations_csv",
    "generate_control_mapping_json",
    "SECURITY_PATTERN_EVIDENCE",
]

# ---------------------------------------------------------------------------
# Control mapping definitions
# ---------------------------------------------------------------------------

SOC2_CONTROL_MAP: dict[str, dict[str, str]] = {
    "CC6.1": {
        "control_id": "CC6.1",
        "title": "Logical and Physical Access Controls",
        "description": (
            "The entity implements logical access security software, "
            "infrastructure, and architectures over protected information "
            "assets. TrustPlane enforces RBAC with four roles (admin, "
            "auditor, delegate, observer) via RBACManager, and supports "
            "OIDC identity verification with JWKS key rotation via "
            "OIDCVerifier for SSO integration."
        ),
        "record_type": "rbac_identity",
        "evidence_sources": [
            "src/trustplane/rbac.py",
            "src/trustplane/identity.py",
        ],
        "test_sources": [
            "tests/integration/test_rbac.py",
            "tests/integration/test_identity.py",
        ],
    },
    "CC6.2": {
        "control_id": "CC6.2",
        "title": "Inventory of Information Assets",
        "description": (
            "The entity inventories system components. "
            "Genesis records establish the project root of trust, "
            "documenting the initial inventory of assets, constraints, "
            "and authority."
        ),
        "record_type": "genesis",
        "evidence_sources": [
            "src/trustplane/project.py",
            "src/trustplane/models.py",
        ],
        "test_sources": [
            "tests/integration/test_project.py",
        ],
    },
    "CC6.3": {
        "control_id": "CC6.3",
        "title": "Removal of Access",
        "description": (
            "The entity removes access to protected information assets "
            "when appropriate. Delegation records track the granting "
            "and revocation of review authority, including cascade "
            "revocation per EATP spec."
        ),
        "record_type": "delegation",
        "evidence_sources": [
            "src/trustplane/delegation.py",
        ],
        "test_sources": [
            "tests/integration/test_delegation.py",
        ],
    },
    "CC6.6": {
        "control_id": "CC6.6",
        "title": "System Operation Controls",
        "description": (
            "The entity implements controls to prevent or detect and "
            "act upon system operation vulnerabilities. All record IDs "
            "are validated via validate_id() to prevent path traversal "
            "(Pattern 1). All file reads use safe_read_json() with "
            "O_NOFOLLOW to prevent symlink attacks (Pattern 2). All "
            "JSON deserialization uses safe_read_json() (Pattern 4). "
            "Numeric constraint fields are validated with math.isfinite() "
            "to reject NaN/Inf (Pattern 5)."
        ),
        "record_type": "input_validation",
        "evidence_sources": [
            "src/trustplane/_locking.py",
            "src/trustplane/models.py",
        ],
        "test_sources": [
            "tests/integration/security/test_security_patterns.py",
            "tests/integration/security/test_static_checks.py",
        ],
    },
    "CC6.7": {
        "control_id": "CC6.7",
        "title": "Restriction of Privileged Access",
        "description": (
            "The entity restricts privileged access. Decision records "
            "capture every access decision with full reasoning trace, "
            "alternatives considered, and confidence levels."
        ),
        "record_type": "decision",
        "evidence_sources": [
            "src/trustplane/models.py",
            "src/trustplane/project.py",
        ],
        "test_sources": [
            "tests/unit/test_models.py",
            "tests/integration/test_project.py",
        ],
    },
    "CC6.8": {
        "control_id": "CC6.8",
        "title": "Monitoring",
        "description": (
            "The entity implements controls to prevent or detect and "
            "act upon the introduction of unauthorized or malicious "
            "software. Execution records log every autonomous AI "
            "action with constraint references and verification "
            "categories."
        ),
        "record_type": "execution",
        "evidence_sources": [
            "src/trustplane/models.py",
            "src/trustplane/proxy.py",
        ],
        "test_sources": [
            "tests/integration/test_proxy.py",
        ],
    },
    "CC7.1": {
        "control_id": "CC7.1",
        "title": "Detection and Monitoring",
        "description": (
            "The entity uses detection and monitoring procedures to "
            "identify anomalies and indicators of compromise. SIEM "
            "export via CEF v0 and OCSF v1.1 formatters enables "
            "enterprise integration with Splunk, Sentinel, QRadar, "
            "and CrowdStrike Falcon. Batch export supports filtering "
            "by timestamp."
        ),
        "record_type": "siem_export",
        "evidence_sources": [
            "src/trustplane/siem.py",
        ],
        "test_sources": [
            "tests/integration/test_siem.py",
        ],
    },
    "CC7.2": {
        "control_id": "CC7.2",
        "title": "System Monitoring",
        "description": (
            "The entity monitors system components for anomalies. "
            "Milestone records provide versioned checkpoints with "
            "file hashes for tamper detection, enabling continuous "
            "monitoring of project state."
        ),
        "record_type": "milestone",
        "evidence_sources": [
            "src/trustplane/models.py",
            "src/trustplane/project.py",
        ],
        "test_sources": [
            "tests/integration/test_project.py",
        ],
    },
    "CC7.3": {
        "control_id": "CC7.3",
        "title": "Evaluation of Security Events",
        "description": (
            "The entity evaluates security events to determine whether "
            "they could or have resulted in failures. HELD and BLOCKED "
            "verdicts represent security events that were evaluated "
            "and escalated for human review."
        ),
        "record_type": "violation",
        "evidence_sources": [
            "src/trustplane/holds.py",
            "src/trustplane/project.py",
        ],
        "test_sources": [
            "tests/integration/test_holds.py",
        ],
    },
    "CC7.4": {
        "control_id": "CC7.4",
        "title": "Response to Security Incidents",
        "description": (
            "The entity responds to identified security incidents. "
            "TLS syslog transport (RFC 5425) provides encrypted "
            "delivery of security events to SIEM platforms. The "
            "create_tls_syslog_handler() enforces TLS 1.2+ with "
            "certificate verification and supports mutual TLS. "
            "Plaintext degradation is prevented by raising "
            "TLSSyslogError on handshake failure."
        ),
        "record_type": "tls_syslog",
        "evidence_sources": [
            "src/trustplane/siem.py",
        ],
        "test_sources": [
            "tests/integration/test_siem.py::TestTLSSyslogHandler",
        ],
    },
    "CC8.1": {
        "control_id": "CC8.1",
        "title": "Change Management",
        "description": (
            "The entity authorizes, designs, develops, configures, "
            "documents, tests, approves, and implements changes. "
            "All record writes use atomic_write() (Pattern 3) for "
            "crash-safe persistence. Store archival bundles include "
            "SHA-256 integrity hashes for chain verification. "
            "PostgreSQL store wraps all writes in transactions."
        ),
        "record_type": "atomic_integrity",
        "evidence_sources": [
            "src/trustplane/_locking.py",
            "src/trustplane/archive.py",
            "src/trustplane/store/postgres.py",
        ],
        "test_sources": [
            "tests/integration/security/test_security_patterns.py::TestPattern3AtomicWrite",
            "tests/integration/test_archive.py",
            "tests/e2e/store/test_postgres_store.py",
        ],
    },
}

ISO27001_CONTROL_MAP: dict[str, dict[str, str]] = {
    "A.6.1": {
        "control_id": "A.6.1",
        "title": "Organization of Information Security",
        "description": (
            "Information security roles and responsibilities shall be "
            "defined and allocated. TrustPlane RBAC defines four roles "
            "(admin, auditor, delegate, observer) with explicit "
            "operation permissions. Role assignments are persisted "
            "atomically and validated via validate_id()."
        ),
        "record_type": "rbac",
        "evidence_sources": [
            "src/trustplane/rbac.py",
        ],
        "test_sources": [
            "tests/integration/test_rbac.py",
        ],
    },
    "A.9.2": {
        "control_id": "A.9.2",
        "title": "User Access Management",
        "description": (
            "Ensure authorized user access and prevent unauthorized "
            "access to systems and services. Decision records document "
            "every access decision with rationale, alternatives, and "
            "confidence levels."
        ),
        "record_type": "decision",
        "evidence_sources": [
            "src/trustplane/models.py",
            "src/trustplane/project.py",
        ],
        "test_sources": [
            "tests/unit/test_models.py",
            "tests/integration/test_project.py",
        ],
    },
    "A.9.4": {
        "control_id": "A.9.4",
        "title": "System and Application Access Control",
        "description": (
            "Access to information and application system functions "
            "shall be restricted in accordance with the access control "
            "policy. OIDC identity verification with JWKS key rotation "
            "enables SSO integration. Dashboard bearer token "
            "authentication restricts API access using "
            "cryptographically secure tokens with hmac.compare_digest() "
            "comparison."
        ),
        "record_type": "oidc_bearer",
        "evidence_sources": [
            "src/trustplane/identity.py",
            "src/trustplane/dashboard.py",
        ],
        "test_sources": [
            "tests/integration/test_identity.py",
            "tests/e2e/test_dashboard.py::TestBearerTokenAuth",
        ],
    },
    "A.10.1": {
        "control_id": "A.10.1",
        "title": "Cryptographic Controls",
        "description": (
            "A policy on the use of cryptographic controls for "
            "protection of information shall be developed and "
            "implemented. Ed25519 is the mandatory signing algorithm "
            "for record attestation. Hash comparisons use "
            "hmac.compare_digest() to prevent timing side-channels "
            "(Pattern 8). Key material is zeroized on revocation "
            "(Pattern 9). Pluggable key managers support AWS KMS, "
            "Azure Key Vault, and HashiCorp Vault. The key manager "
            "error hierarchy ensures provider exceptions are wrapped "
            "in KeyManagerError subclasses."
        ),
        "record_type": "cryptographic",
        "evidence_sources": [
            "src/trustplane/key_manager.py",
            "src/trustplane/key_managers/__init__.py",
            "src/trustplane/exceptions.py",
            "src/trustplane/project.py",
            "src/trustplane/delegation.py",
        ],
        "test_sources": [
            "tests/integration/test_key_managers.py",
            "tests/integration/test_key_protection.py",
            "tests/integration/security/test_security_patterns.py::TestPattern8HmacCompareDigest",
            "tests/integration/security/test_security_patterns.py::TestPattern9KeyZeroization",
        ],
    },
    "A.12.3": {
        "control_id": "A.12.3",
        "title": "Information Backup",
        "description": (
            "Backup copies of information, software and system images "
            "shall be taken and tested regularly. Store archival "
            "creates ZIP bundles with SHA-256 integrity verification "
            "of all archived record IDs. Archive manifests track "
            "record counts and date ranges for verifiable chain "
            "continuity."
        ),
        "record_type": "archive",
        "evidence_sources": [
            "src/trustplane/archive.py",
        ],
        "test_sources": [
            "tests/integration/test_archive.py",
        ],
    },
    "A.12.4": {
        "control_id": "A.12.4",
        "title": "Logging and Monitoring",
        "description": (
            "Event logs recording user activities, exceptions, faults "
            "and information security events shall be produced, kept "
            "and regularly reviewed. Milestone records provide "
            "versioned audit checkpoints with cryptographic hashes."
        ),
        "record_type": "milestone",
        "evidence_sources": [
            "src/trustplane/models.py",
            "src/trustplane/project.py",
        ],
        "test_sources": [
            "tests/integration/test_project.py",
        ],
    },
    "A.14.2": {
        "control_id": "A.14.2",
        "title": "Security in Development and Support Processes",
        "description": (
            "Rules for the development of software and systems shall "
            "be established and applied. Security-critical dataclasses "
            "use frozen=True to prevent post-init mutation (Pattern 10). "
            "Numeric constraint fields validate with math.isfinite() "
            "to reject NaN/Inf (Pattern 5). Collections use "
            "deque(maxlen=10000) to prevent memory exhaustion "
            "(Pattern 6). Monotonic escalation ensures trust state "
            "can only increase, never relax (Pattern 7). from_dict() "
            "validates all required fields to reject malformed records "
            "(Pattern 11)."
        ),
        "record_type": "development_hardening",
        "evidence_sources": [
            "src/trustplane/rbac.py",
            "src/trustplane/models.py",
            "src/trustplane/shadow.py",
            "src/trustplane/proxy.py",
            "src/trustplane/delegation.py",
        ],
        "test_sources": [
            "tests/integration/security/test_security_patterns.py",
            "tests/integration/security/test_static_checks.py",
        ],
    },
    "A.16.1": {
        "control_id": "A.16.1",
        "title": "Management of Information Security Incidents",
        "description": (
            "A consistent and effective approach to the management of "
            "information security incidents, including communication "
            "on security events and weaknesses. HELD and BLOCKED "
            "verdicts capture security incidents requiring human "
            "evaluation."
        ),
        "record_type": "violation",
        "evidence_sources": [
            "src/trustplane/holds.py",
        ],
        "test_sources": [
            "tests/integration/test_holds.py",
        ],
    },
    "A.18.1": {
        "control_id": "A.18.1",
        "title": "Compliance with Legal and Contractual Requirements",
        "description": (
            "All relevant legislative, statutory, regulatory and "
            "contractual requirements shall be explicitly identified "
            "and documented. Shadow store implements configurable "
            "retention policies with age-based, count-based, and "
            "size-based cleanup for observation data. "
            "PostgreSQL store uses connection pooling and wraps all "
            "provider exceptions in TrustPlaneStoreError subclasses "
            "for consistent error handling."
        ),
        "record_type": "retention_compliance",
        "evidence_sources": [
            "src/trustplane/shadow_store.py",
            "src/trustplane/store/postgres.py",
            "src/trustplane/exceptions.py",
        ],
        "test_sources": [
            "tests/integration/test_shadow.py::TestShadowStoreCleanup",
            "tests/e2e/store/test_postgres_store.py::TestExceptionWrapping",
            "tests/integration/test_key_managers.py::TestKeyManagerErrorHierarchy",
        ],
    },
}


# ---------------------------------------------------------------------------
# Security pattern evidence mapping (11 hardened patterns from red teaming)
# ---------------------------------------------------------------------------

SECURITY_PATTERN_EVIDENCE: dict[str, dict[str, Any]] = {
    "pattern_1_validate_id": {
        "pattern_id": 1,
        "title": "validate_id() for path traversal prevention",
        "description": (
            "All externally-sourced record IDs are validated via "
            "validate_id() before use in filesystem paths or SQL queries. "
            "The regex ^[a-zA-Z0-9_-]+$ prevents directory traversal."
        ),
        "implementation": "src/trustplane/_locking.py::validate_id",
        "soc2_controls": ["CC6.6"],
        "iso27001_controls": ["A.14.2"],
        "tests": [
            "tests/integration/security/test_security_patterns.py::TestPattern1ValidateId",
            "tests/integration/security/test_static_checks.py::TestStaticValidateIdUsage",
        ],
    },
    "pattern_2_o_nofollow": {
        "pattern_id": 2,
        "title": "O_NOFOLLOW via safe_read_json() / safe_open()",
        "description": (
            "All file reads use safe_read_json() or safe_read_text() "
            "with O_NOFOLLOW to prevent symlink TOCTOU attacks."
        ),
        "implementation": "src/trustplane/_locking.py::safe_read_json",
        "soc2_controls": ["CC6.6"],
        "iso27001_controls": ["A.14.2"],
        "tests": [
            "tests/integration/security/test_security_patterns.py::TestPattern2ONoFollow",
            "tests/integration/security/test_static_checks.py::TestStaticONoFollow",
        ],
    },
    "pattern_3_atomic_write": {
        "pattern_id": 3,
        "title": "atomic_write() for all record writes",
        "description": (
            "All record writes use atomic_write() (temp file + fsync + "
            "os.replace) for crash-safe persistence."
        ),
        "implementation": "src/trustplane/_locking.py::atomic_write",
        "soc2_controls": ["CC8.1"],
        "iso27001_controls": ["A.14.2"],
        "tests": [
            "tests/integration/security/test_security_patterns.py::TestPattern3AtomicWrite",
            "tests/integration/security/test_static_checks.py::TestStaticAtomicWrite",
        ],
    },
    "pattern_4_safe_deserialization": {
        "pattern_id": 4,
        "title": "safe_read_json() for all JSON deserialization",
        "description": (
            "All JSON file reads use safe_read_json() which combines "
            "O_NOFOLLOW, proper fd lifecycle, and JSON parsing."
        ),
        "implementation": "src/trustplane/_locking.py::safe_read_json",
        "soc2_controls": ["CC6.6"],
        "iso27001_controls": ["A.14.2"],
        "tests": [
            "tests/integration/security/test_security_patterns.py::TestPattern4SafeDeserialization",
            "tests/integration/security/test_static_checks.py::TestStaticNoBareOpen",
        ],
    },
    "pattern_5_isfinite": {
        "pattern_id": 5,
        "title": "math.isfinite() on numeric constraint fields",
        "description": (
            "All numeric constraint fields (max_cost_per_session, "
            "max_cost_per_action, max_session_hours) are validated "
            "with math.isfinite() to reject NaN and Inf."
        ),
        "implementation": "src/trustplane/models.py",
        "soc2_controls": ["CC6.6"],
        "iso27001_controls": ["A.14.2"],
        "tests": [
            "tests/integration/security/test_security_patterns.py::TestPattern5IsFinite",
            "tests/integration/security/test_static_checks.py::TestStaticIsFinite",
        ],
    },
    "pattern_6_bounded_collections": {
        "pattern_id": 6,
        "title": "Bounded collections (deque maxlen)",
        "description": (
            "Long-lived collections use deque(maxlen=10000) to prevent "
            "memory exhaustion in long-running processes."
        ),
        "implementation": "src/trustplane/shadow.py, src/trustplane/proxy.py",
        "soc2_controls": ["CC6.8"],
        "iso27001_controls": ["A.14.2"],
        "tests": [
            "tests/integration/security/test_security_patterns.py::TestPattern6BoundedCollections",
        ],
    },
    "pattern_7_monotonic_escalation": {
        "pattern_id": 7,
        "title": "Monotonic escalation only",
        "description": (
            "Trust state can only escalate (AUTO_APPROVED -> FLAGGED -> "
            "HELD -> BLOCKED), never relax. Delegation revocation is "
            "irreversible."
        ),
        "implementation": "src/trustplane/delegation.py, src/trustplane/models.py",
        "soc2_controls": ["CC6.7", "CC7.3"],
        "iso27001_controls": ["A.9.2", "A.14.2"],
        "tests": [
            "tests/integration/security/test_security_patterns.py::TestPattern7MonotonicEscalation",
        ],
    },
    "pattern_8_hmac_compare_digest": {
        "pattern_id": 8,
        "title": "hmac.compare_digest() for hash comparison",
        "description": (
            "All hash and signature comparisons use hmac.compare_digest() "
            "to prevent timing side-channel attacks."
        ),
        "implementation": (
            "src/trustplane/delegation.py, src/trustplane/project.py, "
            "src/trustplane/dashboard.py, src/trustplane/bundle.py"
        ),
        "soc2_controls": ["CC6.6"],
        "iso27001_controls": ["A.10.1"],
        "tests": [
            "tests/integration/security/test_security_patterns.py::TestPattern8HmacCompareDigest",
            "tests/integration/security/test_static_checks.py::TestStaticCompareDigest",
        ],
    },
    "pattern_9_key_zeroization": {
        "pattern_id": 9,
        "title": "Key material zeroization",
        "description": (
            "Private key references are deleted immediately after "
            "registration. On revocation, key material is overwritten "
            "with empty string tombstones."
        ),
        "implementation": "src/trustplane/project.py, src/trustplane/migrate.py",
        "soc2_controls": ["CC6.7"],
        "iso27001_controls": ["A.10.1"],
        "tests": [
            "tests/integration/security/test_security_patterns.py::TestPattern9KeyZeroization",
            "tests/integration/test_key_protection.py",
        ],
    },
    "pattern_10_frozen_dataclass": {
        "pattern_id": 10,
        "title": "Security-critical dataclasses frozen=True",
        "description": (
            "Security-critical dataclasses (RolePermission) use "
            "frozen=True to prevent post-init field mutation."
        ),
        "implementation": "src/trustplane/rbac.py",
        "soc2_controls": ["CC6.1"],
        "iso27001_controls": ["A.14.2"],
        "tests": [
            "tests/integration/security/test_security_patterns.py::TestPattern10FrozenDataclass",
        ],
    },
    "pattern_11_from_dict_validation": {
        "pattern_id": 11,
        "title": "from_dict() validates all fields",
        "description": (
            "All from_dict() class methods validate required fields "
            "and reject malformed/tampered JSON records loudly."
        ),
        "implementation": (
            "src/trustplane/models.py, src/trustplane/delegation.py, "
            "src/trustplane/rbac.py, src/trustplane/shadow.py"
        ),
        "soc2_controls": ["CC6.6"],
        "iso27001_controls": ["A.14.2"],
        "tests": [
            "tests/integration/security/test_security_patterns.py::TestPattern11FromDictValidation",
            "tests/integration/security/test_static_checks.py::TestStaticFromDictValidation",
        ],
    },
}


def _filter_by_period(
    records: list[Any],
    period_start: datetime | None,
    period_end: datetime | None,
    timestamp_attr: str = "timestamp",
) -> list[Any]:
    """Filter records by time period.

    Args:
        records: List of record objects with a timestamp attribute.
        period_start: Include records at or after this time (inclusive).
        period_end: Include records at or before this time (inclusive).
        timestamp_attr: Name of the timestamp attribute on the record.

    Returns:
        Filtered list of records within the period.
    """
    result = []
    for r in records:
        ts = getattr(r, timestamp_attr, None)
        if ts is None:
            continue
        # Ensure timezone-aware comparison
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        if period_start is not None and ts < period_start:
            continue
        if period_end is not None and ts > period_end:
            continue
        result.append(r)
    return result


def _filter_holds_by_period(
    holds: list[HoldRecord],
    period_start: datetime | None,
    period_end: datetime | None,
) -> list[HoldRecord]:
    """Filter hold records by created_at timestamp."""
    return _filter_by_period(holds, period_start, period_end, "created_at")


def _load_project_data(
    project_or_store: Any,
    period_start: datetime | None = None,
    period_end: datetime | None = None,
) -> dict[str, Any]:
    """Load and filter project data from a TrustProject or TrustPlaneStore.

    Accepts either a TrustProject instance or a TrustPlaneStore instance.
    Returns a dict with filtered decisions, milestones, holds, delegates,
    and manifest.
    """
    from trustplane.project import TrustProject
    from trustplane.store import TrustPlaneStore

    if isinstance(project_or_store, TrustProject):
        project = project_or_store
        decisions = project.get_decisions()
        milestones = project.get_milestones()
        manifest = project.manifest
        # Access store for holds and delegates
        store = project._tp_store
        holds = store.list_holds()
        try:
            delegates = store.list_delegates(active_only=False)
        except Exception:
            delegates = []
    elif isinstance(project_or_store, TrustPlaneStore):
        store = project_or_store
        decisions = store.list_decisions()
        milestones = store.list_milestones()
        holds = store.list_holds()
        try:
            delegates = store.list_delegates(active_only=False)
        except Exception:
            delegates = []
        try:
            manifest = store.get_manifest()
        except (KeyError, Exception):
            manifest = None
    else:
        raise TypeError(
            f"Expected TrustProject or TrustPlaneStore, got {type(project_or_store).__name__}"
        )

    # Apply period filtering
    decisions = _filter_by_period(decisions, period_start, period_end)
    milestones = _filter_by_period(milestones, period_start, period_end)
    holds = _filter_holds_by_period(holds, period_start, period_end)

    return {
        "decisions": decisions,
        "milestones": milestones,
        "holds": holds,
        "delegates": delegates,
        "manifest": manifest,
    }


def _violations_from_holds(holds: list[HoldRecord]) -> list[HoldRecord]:
    """Extract HELD/BLOCKED violations from hold records.

    All holds are violations by definition -- they represent actions
    that were held for human review because they violated or
    exceeded the constraint envelope.
    """
    return holds


def generate_soc2_evidence(
    project_or_store: Any,
    period_start: datetime | None = None,
    period_end: datetime | None = None,
) -> dict[str, Any]:
    """Generate SOC2 evidence mapping from TrustPlane records.

    Maps TrustPlane records to SOC2 Trust Services Criteria controls
    and returns structured evidence data suitable for GRC export.

    Args:
        project_or_store: A TrustProject or TrustPlaneStore instance.
        period_start: Include records at or after this time (inclusive).
        period_end: Include records at or before this time (inclusive).

    Returns:
        Dict with framework metadata, control mappings, and evidence counts.
    """
    data = _load_project_data(project_or_store, period_start, period_end)
    now = datetime.now(timezone.utc)

    manifest = data["manifest"]
    project_name = manifest.project_name if manifest else "Unknown"
    project_id = manifest.project_id if manifest else "unknown"

    violations = _violations_from_holds(data["holds"])

    evidence: dict[str, Any] = {
        "framework": "SOC2",
        "framework_version": "2017",
        "generated_at": now.isoformat(),
        "period": {
            "start": period_start.isoformat() if period_start else None,
            "end": period_end.isoformat() if period_end else None,
        },
        "project": {
            "name": project_name,
            "id": project_id,
            "genesis_id": manifest.genesis_id if manifest else "",
        },
        "summary": {
            "total_decisions": len(data["decisions"]),
            "total_milestones": len(data["milestones"]),
            "total_violations": len(violations),
            "total_delegates": len(data["delegates"]),
        },
        "controls": {},
    }

    # CC6.2: Genesis record
    genesis_evidence: dict[str, Any] = {
        **SOC2_CONTROL_MAP["CC6.2"],
        "evidence_count": 1 if (manifest and manifest.genesis_id) else 0,
        "evidence": [],
    }
    if manifest and manifest.genesis_id:
        genesis_evidence["evidence"].append(
            {
                "type": "genesis_record",
                "genesis_id": manifest.genesis_id,
                "project_name": project_name,
                "created_at": manifest.created_at.isoformat() if manifest else "",
                "author": manifest.author if manifest else "",
            }
        )
    evidence["controls"]["CC6.2"] = genesis_evidence

    # CC6.3: Delegation records
    delegation_evidence: dict[str, Any] = {
        **SOC2_CONTROL_MAP["CC6.3"],
        "evidence_count": len(data["delegates"]),
        "evidence": [d.to_dict() for d in data["delegates"]],
    }
    evidence["controls"]["CC6.3"] = delegation_evidence

    # CC6.7: Decision records
    decision_evidence: dict[str, Any] = {
        **SOC2_CONTROL_MAP["CC6.7"],
        "evidence_count": len(data["decisions"]),
        "evidence": [d.to_dict() for d in data["decisions"]],
    }
    evidence["controls"]["CC6.7"] = decision_evidence

    # CC6.8: Execution records (from milestones as proxy)
    execution_evidence: dict[str, Any] = {
        **SOC2_CONTROL_MAP["CC6.8"],
        "evidence_count": len(data["milestones"]),
        "evidence": [m.to_dict() for m in data["milestones"]],
    }
    evidence["controls"]["CC6.8"] = execution_evidence

    # CC7.2: Milestone records
    milestone_evidence: dict[str, Any] = {
        **SOC2_CONTROL_MAP["CC7.2"],
        "evidence_count": len(data["milestones"]),
        "evidence": [m.to_dict() for m in data["milestones"]],
    }
    evidence["controls"]["CC7.2"] = milestone_evidence

    # CC7.3: HELD/BLOCKED violations
    violation_evidence: dict[str, Any] = {
        **SOC2_CONTROL_MAP["CC7.3"],
        "evidence_count": len(violations),
        "evidence": [h.to_dict() for h in violations],
    }
    evidence["controls"]["CC7.3"] = violation_evidence

    # CC6.1: Logical and Physical Access Controls (RBAC + OIDC)
    evidence["controls"]["CC6.1"] = {
        **SOC2_CONTROL_MAP["CC6.1"],
        "evidence_count": 1,
        "evidence": [
            {
                "type": "implementation_control",
                "modules": SOC2_CONTROL_MAP["CC6.1"]["evidence_sources"],
                "tests": SOC2_CONTROL_MAP["CC6.1"]["test_sources"],
            }
        ],
    }

    # CC6.6: System Operation Controls (input validation)
    evidence["controls"]["CC6.6"] = {
        **SOC2_CONTROL_MAP["CC6.6"],
        "evidence_count": 1,
        "evidence": [
            {
                "type": "implementation_control",
                "modules": SOC2_CONTROL_MAP["CC6.6"]["evidence_sources"],
                "tests": SOC2_CONTROL_MAP["CC6.6"]["test_sources"],
                "security_patterns": [1, 2, 4, 5, 8, 11],
            }
        ],
    }

    # CC7.1: Detection and Monitoring (SIEM export)
    evidence["controls"]["CC7.1"] = {
        **SOC2_CONTROL_MAP["CC7.1"],
        "evidence_count": 1,
        "evidence": [
            {
                "type": "implementation_control",
                "modules": SOC2_CONTROL_MAP["CC7.1"]["evidence_sources"],
                "tests": SOC2_CONTROL_MAP["CC7.1"]["test_sources"],
            }
        ],
    }

    # CC7.4: Response to Security Incidents (TLS syslog)
    evidence["controls"]["CC7.4"] = {
        **SOC2_CONTROL_MAP["CC7.4"],
        "evidence_count": 1,
        "evidence": [
            {
                "type": "implementation_control",
                "modules": SOC2_CONTROL_MAP["CC7.4"]["evidence_sources"],
                "tests": SOC2_CONTROL_MAP["CC7.4"]["test_sources"],
            }
        ],
    }

    # CC8.1: Change Management (atomic writes, archive integrity)
    evidence["controls"]["CC8.1"] = {
        **SOC2_CONTROL_MAP["CC8.1"],
        "evidence_count": 1,
        "evidence": [
            {
                "type": "implementation_control",
                "modules": SOC2_CONTROL_MAP["CC8.1"]["evidence_sources"],
                "tests": SOC2_CONTROL_MAP["CC8.1"]["test_sources"],
                "security_patterns": [3],
            }
        ],
    }

    return evidence


def generate_iso27001_evidence(
    project_or_store: Any,
    period_start: datetime | None = None,
    period_end: datetime | None = None,
) -> dict[str, Any]:
    """Generate ISO 27001 Annex A evidence mapping from TrustPlane records.

    Maps TrustPlane records to ISO 27001 Annex A controls and returns
    structured evidence data suitable for GRC export.

    Args:
        project_or_store: A TrustProject or TrustPlaneStore instance.
        period_start: Include records at or after this time (inclusive).
        period_end: Include records at or before this time (inclusive).

    Returns:
        Dict with framework metadata, control mappings, and evidence counts.
    """
    data = _load_project_data(project_or_store, period_start, period_end)
    now = datetime.now(timezone.utc)

    manifest = data["manifest"]
    project_name = manifest.project_name if manifest else "Unknown"
    project_id = manifest.project_id if manifest else "unknown"

    violations = _violations_from_holds(data["holds"])

    evidence: dict[str, Any] = {
        "framework": "ISO27001",
        "framework_version": "2022",
        "generated_at": now.isoformat(),
        "period": {
            "start": period_start.isoformat() if period_start else None,
            "end": period_end.isoformat() if period_end else None,
        },
        "project": {
            "name": project_name,
            "id": project_id,
            "genesis_id": manifest.genesis_id if manifest else "",
        },
        "summary": {
            "total_decisions": len(data["decisions"]),
            "total_milestones": len(data["milestones"]),
            "total_violations": len(violations),
        },
        "controls": {},
    }

    # A.9.2: Decision records
    decision_evidence: dict[str, Any] = {
        **ISO27001_CONTROL_MAP["A.9.2"],
        "evidence_count": len(data["decisions"]),
        "evidence": [d.to_dict() for d in data["decisions"]],
    }
    evidence["controls"]["A.9.2"] = decision_evidence

    # A.12.4: Milestone records
    milestone_evidence: dict[str, Any] = {
        **ISO27001_CONTROL_MAP["A.12.4"],
        "evidence_count": len(data["milestones"]),
        "evidence": [m.to_dict() for m in data["milestones"]],
    }
    evidence["controls"]["A.12.4"] = milestone_evidence

    # A.16.1: HELD/BLOCKED violations
    violation_evidence: dict[str, Any] = {
        **ISO27001_CONTROL_MAP["A.16.1"],
        "evidence_count": len(violations),
        "evidence": [h.to_dict() for h in violations],
    }
    evidence["controls"]["A.16.1"] = violation_evidence

    # A.6.1: Organization of Information Security (RBAC)
    evidence["controls"]["A.6.1"] = {
        **ISO27001_CONTROL_MAP["A.6.1"],
        "evidence_count": 1,
        "evidence": [
            {
                "type": "implementation_control",
                "modules": ISO27001_CONTROL_MAP["A.6.1"]["evidence_sources"],
                "tests": ISO27001_CONTROL_MAP["A.6.1"]["test_sources"],
            }
        ],
    }

    # A.9.4: System and Application Access Control (OIDC + bearer auth)
    evidence["controls"]["A.9.4"] = {
        **ISO27001_CONTROL_MAP["A.9.4"],
        "evidence_count": 1,
        "evidence": [
            {
                "type": "implementation_control",
                "modules": ISO27001_CONTROL_MAP["A.9.4"]["evidence_sources"],
                "tests": ISO27001_CONTROL_MAP["A.9.4"]["test_sources"],
            }
        ],
    }

    # A.10.1: Cryptographic Controls
    evidence["controls"]["A.10.1"] = {
        **ISO27001_CONTROL_MAP["A.10.1"],
        "evidence_count": 1,
        "evidence": [
            {
                "type": "implementation_control",
                "modules": ISO27001_CONTROL_MAP["A.10.1"]["evidence_sources"],
                "tests": ISO27001_CONTROL_MAP["A.10.1"]["test_sources"],
                "security_patterns": [8, 9],
            }
        ],
    }

    # A.12.3: Information Backup (store archival)
    evidence["controls"]["A.12.3"] = {
        **ISO27001_CONTROL_MAP["A.12.3"],
        "evidence_count": 1,
        "evidence": [
            {
                "type": "implementation_control",
                "modules": ISO27001_CONTROL_MAP["A.12.3"]["evidence_sources"],
                "tests": ISO27001_CONTROL_MAP["A.12.3"]["test_sources"],
            }
        ],
    }

    # A.14.2: Security in Development (hardened patterns)
    evidence["controls"]["A.14.2"] = {
        **ISO27001_CONTROL_MAP["A.14.2"],
        "evidence_count": 1,
        "evidence": [
            {
                "type": "implementation_control",
                "modules": ISO27001_CONTROL_MAP["A.14.2"]["evidence_sources"],
                "tests": ISO27001_CONTROL_MAP["A.14.2"]["test_sources"],
                "security_patterns": [5, 6, 7, 10, 11],
            }
        ],
    }

    # A.18.1: Compliance with Legal Requirements (retention, error handling)
    evidence["controls"]["A.18.1"] = {
        **ISO27001_CONTROL_MAP["A.18.1"],
        "evidence_count": 1,
        "evidence": [
            {
                "type": "implementation_control",
                "modules": ISO27001_CONTROL_MAP["A.18.1"]["evidence_sources"],
                "tests": ISO27001_CONTROL_MAP["A.18.1"]["test_sources"],
            }
        ],
    }

    return evidence


def export_decisions_csv(decisions: list[DecisionRecord]) -> str:
    """Export decision records as CSV text.

    Args:
        decisions: List of DecisionRecord instances.

    Returns:
        CSV-formatted string with header row.
    """
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "decision_id",
            "decision_type",
            "decision",
            "rationale",
            "alternatives",
            "risks",
            "review_requirement",
            "confidence",
            "author",
            "timestamp",
        ]
    )
    for d in decisions:
        writer.writerow(
            [
                d.decision_id,
                _decision_type_value(d.decision_type),
                d.decision,
                d.rationale,
                "; ".join(d.alternatives),
                "; ".join(d.risks),
                d.review_requirement.value,
                d.confidence,
                d.author,
                d.timestamp.isoformat(),
            ]
        )
    return output.getvalue()


def export_violations_csv(holds: list[HoldRecord]) -> str:
    """Export hold/violation records as CSV text.

    Args:
        holds: List of HoldRecord instances.

    Returns:
        CSV-formatted string with header row.
    """
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "hold_id",
            "action",
            "resource",
            "reason",
            "status",
            "created_at",
            "resolved_at",
            "resolved_by",
            "resolution_reason",
        ]
    )
    for h in holds:
        writer.writerow(
            [
                h.hold_id,
                h.action,
                h.resource,
                h.reason,
                h.status,
                h.created_at.isoformat(),
                h.resolved_at.isoformat() if h.resolved_at else "",
                h.resolved_by or "",
                h.resolution_reason or "",
            ]
        )
    return output.getvalue()


def generate_control_mapping_json(framework: str = "soc2") -> dict[str, Any]:
    """Generate a control mapping document for the specified framework.

    Args:
        framework: The compliance framework ("soc2" or "iso27001").

    Returns:
        Dict describing control mappings between TrustPlane records
        and the specified framework's controls.

    Raises:
        ValueError: If the framework is not supported.
    """
    framework_lower = framework.lower()
    if framework_lower == "soc2":
        return {
            "framework": "SOC2",
            "framework_version": "2017",
            "mappings": [
                {
                    **ctrl,
                    "trustplane_source": ctrl["record_type"],
                }
                for ctrl in SOC2_CONTROL_MAP.values()
            ],
        }
    elif framework_lower == "iso27001":
        return {
            "framework": "ISO27001",
            "framework_version": "2022",
            "mappings": [
                {
                    **ctrl,
                    "trustplane_source": ctrl["record_type"],
                }
                for ctrl in ISO27001_CONTROL_MAP.values()
            ],
        }
    else:
        raise ValueError(
            f"Unsupported framework: {framework!r}. Supported: 'soc2', 'iso27001'"
        )


def generate_evidence_summary_md(
    evidence: dict[str, Any],
    verification: dict[str, Any] | None = None,
) -> str:
    """Generate a Markdown evidence summary report.

    Args:
        evidence: Evidence dict from generate_soc2_evidence or
            generate_iso27001_evidence.
        verification: Optional chain verification result.

    Returns:
        Markdown-formatted string.
    """
    framework = evidence.get("framework", "Unknown")
    lines: list[str] = []

    lines.append(f"# {framework} Evidence Summary")
    lines.append("")
    lines.append(f"**Generated**: {evidence.get('generated_at', '')}")
    lines.append("")

    # Period
    period = evidence.get("period", {})
    period_start = period.get("start", "beginning")
    period_end = period.get("end", "present")
    lines.append(
        f"**Period**: {period_start or 'beginning'} to {period_end or 'present'}"
    )
    lines.append("")

    # Project
    project_info = evidence.get("project", {})
    lines.append("## Project")
    lines.append("")
    lines.append(f"- **Name**: {project_info.get('name', 'Unknown')}")
    lines.append(f"- **ID**: {project_info.get('id', 'unknown')}")
    lines.append(f"- **Genesis**: {project_info.get('genesis_id', '')}")
    lines.append("")

    # Summary
    summary = evidence.get("summary", {})
    lines.append("## Evidence Summary")
    lines.append("")
    lines.append(f"- **Total Decisions**: {summary.get('total_decisions', 0)}")
    lines.append(f"- **Total Milestones**: {summary.get('total_milestones', 0)}")
    lines.append(f"- **Total Violations**: {summary.get('total_violations', 0)}")
    if "total_delegates" in summary:
        lines.append(f"- **Total Delegates**: {summary.get('total_delegates', 0)}")
    lines.append("")

    # Chain verification
    if verification:
        lines.append("## Chain Verification")
        lines.append("")
        chain_valid = verification.get("chain_valid", False)
        lines.append(f"- **Chain Valid**: {'Yes' if chain_valid else 'NO'}")
        lines.append(f"- **Total Anchors**: {verification.get('total_anchors', 0)}")
        issues = verification.get("integrity_issues", [])
        if issues:
            lines.append(f"- **Integrity Issues**: {len(issues)}")
            for issue in issues:
                lines.append(f"  - {issue}")
        else:
            lines.append("- **Integrity Issues**: None")
        lines.append("")

    # Control mappings
    controls = evidence.get("controls", {})
    lines.append("## Control Mappings")
    lines.append("")
    for ctrl_id, ctrl_data in sorted(controls.items()):
        count = ctrl_data.get("evidence_count", 0)
        title = ctrl_data.get("title", "")
        lines.append(f"### {ctrl_id}: {title}")
        lines.append("")
        lines.append(f"**Evidence Count**: {count}")
        lines.append("")
        lines.append(ctrl_data.get("description", ""))
        lines.append("")

    return "\n".join(lines)
