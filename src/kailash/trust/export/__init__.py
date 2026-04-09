# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""
EATP Export Module.

Provides serializers for exporting EATP operations to SIEM systems
in industry-standard formats (CEF, OCSF), and compliance evidence
generation for SOC 2 / ISO 27001 audits.
"""

from __future__ import annotations

from kailash.trust.export.compliance import (
    SOC2_CONTROL_MAPPINGS,
    ComplianceEvidenceRecord,
    ComplianceEvidenceReport,
    generate_soc2_evidence,
)
from kailash.trust.export.siem import (
    AuditOperationEvent,
    DelegateEvent,
    EstablishEvent,
    SIEMEvent,
    VerifyEvent,
    from_audit_anchor,
    serialize_cef,
    serialize_ocsf,
)

__all__ = [
    # SIEM exports
    "SIEMEvent",
    "EstablishEvent",
    "DelegateEvent",
    "VerifyEvent",
    "AuditOperationEvent",
    "serialize_cef",
    "serialize_ocsf",
    "from_audit_anchor",
    # Compliance evidence exports
    "SOC2_CONTROL_MAPPINGS",
    "ComplianceEvidenceRecord",
    "ComplianceEvidenceReport",
    "generate_soc2_evidence",
]
