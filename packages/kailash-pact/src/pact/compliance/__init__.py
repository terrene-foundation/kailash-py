# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""SOC 2 compliance-evidence tooling for the PACT governance layer.

Derives SOC 2-aligned evidence packages from the primitives the SDK already
emits (RBAC/ABAC grants, the hash-chained immutable audit log, tenant
isolation, trust/delegation records, governance-config changes). This is
evidence *tooling*, not an attestation — the deploying organization remains the
attesting party.

Public API::

    from pact.compliance import EvidenceCollector

    collector = EvidenceCollector(audit_store)
    package = await collector.collect(
        tenant_id="acme",
        period_start=start,
        period_end=end,
    )
    package.to_dict()  # structured, exportable
"""

from __future__ import annotations

from pact.compliance.evidence import (
    ControlEvidence,
    CriterionEvidence,
    EvidenceCollectionError,
    EvidenceCollector,
    EvidenceItem,
    EvidencePackage,
)
from pact.compliance.vocabulary import (
    CONTROL_SPECS,
    EMITTED_ACTION_VOCABULARY,
    IMPLEMENTED_CONTROLS,
    ControlSpec,
    CriterionSpec,
)

__all__ = [
    "EvidenceCollector",
    "EvidencePackage",
    "ControlEvidence",
    "CriterionEvidence",
    "EvidenceItem",
    "EvidenceCollectionError",
    "CONTROL_SPECS",
    "IMPLEMENTED_CONTROLS",
    "EMITTED_ACTION_VOCABULARY",
    "ControlSpec",
    "CriterionSpec",
]
