# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""SOC 2 / ISO 27001 compliance evidence generation for EATP.

Maps EATP trust operations to SOC 2 Trust Services Criteria control
objectives and generates audit-ready evidence reports suitable for
compliance teams and external auditors.

Control mapping rationale:
    ESTABLISH -> CC6.1 (Logical Access), CC6.2 (User Provisioning)
        Trust establishment is analogous to user provisioning and
        access control setup in SOC 2.
    DELEGATE  -> CC6.1 (Logical Access), CC6.3 (Role-Based Access)
        Delegation maps to role-based access assignment and
        access control enforcement.
    VERIFY    -> CC7.2 (System Monitoring), CC7.3 (Anomaly Detection)
        Verification is continuous monitoring and detection of
        anomalous trust chain states.
    AUDIT     -> CC7.1 (Monitoring), CC8.1 (Change Management)
        Audit anchors provide monitoring evidence and change
        management records.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ============================================================================
# SOC 2 Control Mappings
# ============================================================================

# Maps EATP operations to SOC 2 Trust Services Criteria control objectives.
# Each operation maps to the most relevant controls from the CC (Common
# Criteria) framework.
SOC2_CONTROL_MAPPINGS: Dict[str, List[str]] = {
    "ESTABLISH": ["CC6.1", "CC6.2"],  # Access control, user provisioning
    "DELEGATE": ["CC6.1", "CC6.3"],  # Access control, role-based access
    "VERIFY": ["CC7.2", "CC7.3"],  # System monitoring, anomaly detection
    "AUDIT": ["CC7.1", "CC8.1"],  # Monitoring, change management
}

# Maps audit service action names to EATP operation types.
# This allows the evidence generator to classify diverse action names
# from the audit store into the four canonical EATP operations.
_ACTION_TO_OPERATION: Dict[str, str] = {
    "trust_established": "ESTABLISH",
    "trust_delegated": "DELEGATE",
    "verify_trust": "VERIFY",
    "audit_action": "AUDIT",
}


# ============================================================================
# Data classes
# ============================================================================


@dataclass
class ComplianceEvidenceRecord:
    """Single evidence record for compliance reporting.

    Represents one auditable event that maps to specific SOC 2 or ISO 27001
    control objectives. Evidence records are the atomic unit of compliance
    reporting -- each record ties a specific EATP operation to the controls
    it satisfies.

    Attributes:
        record_id: Unique identifier for this evidence record.
        timestamp: When the underlying event occurred (UTC).
        operation: EATP operation type (ESTABLISH, DELEGATE, VERIFY, AUDIT).
        agent_id: The agent involved in the operation.
        result: Outcome of the operation (e.g., "success", "failure").
        control_objectives: SOC 2 control IDs this record provides evidence for.
        evidence_data: Structured evidence payload (counts, details, etc.).
        authority_id: Authority that performed or authorized the operation.
    """

    record_id: str
    timestamp: datetime
    operation: str  # ESTABLISH, DELEGATE, VERIFY, AUDIT
    agent_id: str
    result: str
    control_objectives: List[str]  # SOC 2 control IDs
    evidence_data: Dict[str, Any]
    authority_id: Optional[str] = None


@dataclass
class ComplianceEvidenceReport:
    """Full compliance evidence report for a time period.

    Aggregates all evidence records for a reporting period and provides
    control coverage statistics and summary metrics for auditor review.

    Attributes:
        report_id: Unique identifier for this report.
        generated_at: When this report was generated (UTC).
        period_start: Start of the reporting period.
        period_end: End of the reporting period.
        framework: Compliance framework (e.g., "SOC2", "ISO27001").
        records: All evidence records in the report.
        control_coverage: Map of control_id to count of evidence records.
        summary: Aggregate statistics for the reporting period.
    """

    report_id: str
    generated_at: datetime
    period_start: datetime
    period_end: datetime
    framework: str  # "SOC2" or "ISO27001"
    records: List[ComplianceEvidenceRecord]
    control_coverage: Dict[str, int]  # control_id -> record_count
    summary: Dict[str, Any]


# ============================================================================
# Evidence Generation
# ============================================================================


def _classify_operation(action_name: str) -> Optional[str]:
    """Classify an audit action name into an EATP operation type.

    Uses the _ACTION_TO_OPERATION mapping to determine which EATP
    operation a given audit action name belongs to. Returns None
    if the action name cannot be classified.

    Args:
        action_name: The action name from the audit store.

    Returns:
        EATP operation string or None if unclassifiable.
    """
    return _ACTION_TO_OPERATION.get(action_name)


def _build_evidence_record(
    operation: str,
    action_name: str,
    action_summary: Any,
    timestamp: datetime,
    authority_id: Optional[str],
) -> ComplianceEvidenceRecord:
    """Build a single ComplianceEvidenceRecord from an action summary.

    Args:
        operation: EATP operation type.
        action_name: Original action name from audit store.
        action_summary: Action summary object from compliance report.
        timestamp: Timestamp for the evidence record.
        authority_id: Optional authority filter.

    Returns:
        A populated ComplianceEvidenceRecord.
    """
    control_objectives = SOC2_CONTROL_MAPPINGS[operation]
    total = action_summary.total_count
    success = action_summary.success_count
    failure = action_summary.failure_count
    denied = action_summary.denied_count

    success_rate = success / total if total > 0 else 0.0

    evidence_data: Dict[str, Any] = {
        "action_name": action_name,
        "total_count": total,
        "success_count": success,
        "failure_count": failure,
        "denied_count": denied,
        "success_rate": round(success_rate, 4),
    }

    # Determine overall result: if any denied, flag as "denied";
    # if any failures, flag as "partial"; otherwise "success"
    if denied > 0:
        result = "denied"
    elif failure > 0:
        result = "partial"
    else:
        result = "success"

    return ComplianceEvidenceRecord(
        record_id=f"evi-{uuid.uuid4().hex[:12]}",
        timestamp=timestamp,
        operation=operation,
        agent_id="fleet",  # Fleet-level evidence
        result=result,
        control_objectives=list(control_objectives),
        evidence_data=evidence_data,
        authority_id=authority_id,
    )


async def generate_soc2_evidence(
    audit_service: Any,  # AuditQueryService
    start_time: datetime,
    end_time: datetime,
    authority_id: Optional[str] = None,
) -> ComplianceEvidenceReport:
    """Generate SOC 2 compliance evidence from audit records.

    Queries the audit service for a compliance report covering the specified
    time range, then transforms the audit data into SOC 2 evidence records
    mapped to Trust Services Criteria control objectives.

    The generated report includes:
        - Evidence records for each EATP operation type found in the audit data
        - Control coverage statistics (which controls have evidence)
        - Aggregate summary with total counts and violation status

    Args:
        audit_service: An AuditQueryService instance for querying audit data.
        start_time: Start of the evidence collection period (UTC).
        end_time: End of the evidence collection period (UTC).
        authority_id: Optional filter to scope evidence to a specific authority.

    Returns:
        A ComplianceEvidenceReport containing all evidence records,
        control coverage data, and summary statistics.

    Raises:
        ValueError: If start_time is after end_time.
    """
    if start_time >= end_time:
        raise ValueError(
            f"start_time ({start_time.isoformat()}) must be before "
            f"end_time ({end_time.isoformat()})"
        )

    # Query the audit service for the compliance report
    compliance_report = await audit_service.generate_compliance_report(
        start_time=start_time,
        end_time=end_time,
        authority_id=authority_id,
    )

    # Build evidence records from action summaries
    records: List[ComplianceEvidenceRecord] = []
    now = datetime.now(timezone.utc)

    for action_name, action_summary in compliance_report.action_summaries.items():
        operation = _classify_operation(action_name)
        if operation is None:
            logger.debug(
                "Skipping unclassified action '%s' in evidence generation",
                action_name,
            )
            continue

        record = _build_evidence_record(
            operation=operation,
            action_name=action_name,
            action_summary=action_summary,
            timestamp=now,
            authority_id=authority_id,
        )
        records.append(record)

    # Compute control coverage: count how many records reference each control
    control_coverage: Dict[str, int] = {}
    for record in records:
        for control_id in record.control_objectives:
            control_coverage[control_id] = control_coverage.get(control_id, 0) + 1

    # Build summary
    summary: Dict[str, Any] = {
        "total_records": len(records),
        "total_agents": compliance_report.total_agents,
        "total_actions": compliance_report.total_actions,
        "violations_found": compliance_report.any_violations,
        "success_count": compliance_report.success_count,
        "failure_count": compliance_report.failure_count,
        "denied_count": compliance_report.denied_count,
        "control_coverage_count": len(control_coverage),
    }

    report = ComplianceEvidenceReport(
        report_id=f"soc2-{uuid.uuid4().hex[:12]}",
        generated_at=now,
        period_start=start_time,
        period_end=end_time,
        framework="SOC2",
        records=records,
        control_coverage=control_coverage,
        summary=summary,
    )

    logger.info(
        "Generated SOC 2 evidence report %s: %d records, %d controls covered, "
        "period %s to %s",
        report.report_id,
        len(records),
        len(control_coverage),
        start_time.isoformat(),
        end_time.isoformat(),
    )

    return report


__all__ = [
    "SOC2_CONTROL_MAPPINGS",
    "ComplianceEvidenceRecord",
    "ComplianceEvidenceReport",
    "generate_soc2_evidence",
]
