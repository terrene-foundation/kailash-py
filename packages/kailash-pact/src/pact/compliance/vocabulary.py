# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""SOC 2 evidence vocabulary — the producer↔consumer contract.

Every SOC 2 evidence collector derives its findings ONLY from action names the
SDK *actually emits*. The two authoritative producer vocabularies are:

* :class:`kailash.trust.pact.audit.PactAuditAction` — the PACT governance
  action types recorded on the tamper-evident audit chain (thesis §5.7).
* :class:`kailash.trust.audit_store.AuditEventType` — the well-known
  trust-plane audit event types written to the ``AuditStore``.

``EMITTED_ACTION_VOCABULARY`` is the union of both enums' ``.value`` strings.
Every ``CriterionSpec.source_actions`` entry is built by referencing an enum
member's ``.value`` directly, so a collector filter can NEVER name an action no
producer emits. The "dead collector" guard (an evidence filter matching a name
no producer emits) is closed *by construction* here, and asserted by the
producer↔consumer contract test.

A criterion with a non-empty ``unverifiable_reason`` has NO emitting producer in
the SDK (e.g. MFA enrollment state, an external monitoring/alerting system).
Such criteria report ``verified=False`` in the evidence package — an honest
"the SDK cannot measure this control", never a fabricated pass.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from kailash.trust.audit_store import AuditEventType as _AET
from kailash.trust.pact.audit import PactAuditAction as _PAA

logger = logging.getLogger(__name__)

__all__ = [
    "EMITTED_ACTION_VOCABULARY",
    "CriterionSpec",
    "ControlSpec",
    "CONTROL_SPECS",
    "IMPLEMENTED_CONTROLS",
]


# ---------------------------------------------------------------------------
# The authoritative emitted action vocabulary (union of both producer enums)
# ---------------------------------------------------------------------------

EMITTED_ACTION_VOCABULARY: frozenset[str] = frozenset(
    [member.value for member in _PAA] + [member.value for member in _AET]
)
"""Every action string the SDK's governance/trust producers actually emit."""


# ---------------------------------------------------------------------------
# Spec dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CriterionSpec:
    """One measurable (or honestly-unmeasurable) SOC 2 sub-criterion.

    Args:
        key: Stable machine-readable identifier for the criterion.
        description: Human-readable description of what the criterion evidences.
        source_actions: The emitted action names this criterion derives from.
            EVERY entry MUST be a member of ``EMITTED_ACTION_VOCABULARY`` — the
            producer↔consumer contract. Empty for an unmeasurable criterion.
        unverifiable_reason: When non-None, the SDK has NO producer for this
            criterion; the collector reports ``verified=False`` and surfaces
            this reason instead of fabricating a pass.
    """

    key: str
    description: str
    source_actions: tuple[str, ...]
    unverifiable_reason: str | None = None
    kind: str = "records"
    """How the criterion is measured. ``"records"`` (default) filters emitted
    audit records by ``source_actions``; ``"chain_integrity"`` derives its
    evidence from the audit store's hash-chain verification result instead of
    an action filter (and so carries no ``source_actions``)."""


@dataclass(frozen=True)
class ControlSpec:
    """A SOC 2 Common Criteria control and its sub-criteria."""

    control: str
    title: str
    criteria: tuple[CriterionSpec, ...]


# ---------------------------------------------------------------------------
# CC6 — Logical and Physical Access Controls
#   Derived from real emitted access/clearance/bridge/delegation records.
# ---------------------------------------------------------------------------

_CC6 = ControlSpec(
    control="CC6",
    title="Logical and Physical Access Controls",
    criteria=(
        CriterionSpec(
            key="logical_access_grants",
            description=(
                "Access permissions granted: role clearances, access grants, "
                "knowledge-sharing partnerships, approved cross-unit bridges, "
                "and delegations."
            ),
            source_actions=(
                _PAA.CLEARANCE_GRANTED.value,
                _PAA.KSP_CREATED.value,
                _PAA.BRIDGE_APPROVED.value,
                _PAA.BRIDGE_ESTABLISHED.value,
                _PAA.BRIDGE_CONSENT.value,
                _AET.ACCESS_GRANTED.value,
                _AET.DELEGATION_CREATED.value,
                _AET.TRUST_ESTABLISHED.value,
            ),
        ),
        CriterionSpec(
            key="access_revocations",
            description=(
                "Access permissions withdrawn: clearance revocations and "
                "transitions, partnership/bridge/delegation revocations, and "
                "suspended vacancies."
            ),
            source_actions=(
                _PAA.CLEARANCE_REVOKED.value,
                _PAA.CLEARANCE_TRANSITIONED.value,
                _PAA.KSP_REVOKED.value,
                _PAA.BRIDGE_REVOKED.value,
                _PAA.BRIDGE_REJECTED.value,
                _PAA.VACANCY_SUSPENDED.value,
                _AET.DELEGATION_REVOKED.value,
                _AET.TRUST_REVOKED.value,
            ),
        ),
        CriterionSpec(
            key="access_enforcement",
            description=(
                "Access-control enforcement decisions: containment/isolation "
                "barrier enforcement and denied access attempts (the 5-step "
                "access-enforcement fail-closed path)."
            ),
            source_actions=(
                _PAA.BARRIER_ENFORCED.value,
                _AET.ACCESS_DENIED.value,
                _AET.ACTION_DENIED.value,
                _AET.TRUST_DENIED.value,
            ),
        ),
        CriterionSpec(
            key="mfa_state",
            description="Multi-factor-authentication enrollment and enforcement state.",
            source_actions=(),
            unverifiable_reason=(
                "No MFA-state producer emits to the trust-plane audit store; MFA "
                "enrollment and enforcement live in the deploying organization's "
                "identity provider, outside the SDK's emission surface."
            ),
        ),
    ),
)


# ---------------------------------------------------------------------------
# CC8 — Change Management
#   Derived from real emitted governance-config / authorization-structure
#   change records. Deployment/version/promotion CI records are NOT emitted by
#   the SDK, so that criterion is honestly reported verified=False.
# ---------------------------------------------------------------------------

_CC8 = ControlSpec(
    control="CC8",
    title="Change Management",
    criteria=(
        CriterionSpec(
            key="governance_config_changes",
            description=(
                "Changes to governance configuration: constraint-envelope "
                "creation and modification, and policy changes."
            ),
            source_actions=(
                _PAA.ENVELOPE_CREATED.value,
                _PAA.ENVELOPE_MODIFIED.value,
                _AET.POLICY_CHANGED.value,
            ),
        ),
        CriterionSpec(
            key="authorization_structure_changes",
            description=(
                "Changes to the authorization structure: vacancy designations "
                "and address (D/T/R) computations."
            ),
            source_actions=(
                _PAA.VACANCY_DESIGNATED.value,
                _PAA.ADDRESS_COMPUTED.value,
            ),
        ),
        CriterionSpec(
            key="deployment_records",
            description="Application deployment, version, and promotion records.",
            source_actions=(),
            unverifiable_reason=(
                "The SDK emits no deployment/version/promotion record primitive; "
                "CI/CD deployment evidence is the deploying organization's "
                "pipeline responsibility. The governance-configuration change "
                "records above are the SDK's change-management evidence."
            ),
        ),
    ),
)


# ---------------------------------------------------------------------------
# CC7 — System Operations
#   Hash-chain integrity of the immutable audit log + emitted security /
#   operational-suspension events. External monitoring/alerting/incident
#   systems are the deploying org's and are honestly reported verified=False.
# ---------------------------------------------------------------------------

_CC7 = ControlSpec(
    control="CC7",
    title="System Operations",
    criteria=(
        CriterionSpec(
            key="audit_chain_integrity",
            description=(
                "Tamper-evidence: the immutable audit log's hash chain verified "
                "intact over the period (Merkle/hash-chain verification)."
            ),
            source_actions=(),
            kind="chain_integrity",
        ),
        CriterionSpec(
            key="security_events",
            description=(
                "Security-relevant operational events: constraint violations, "
                "denied actions/trust, barrier enforcement, and workflow/node "
                "errors."
            ),
            source_actions=(
                _AET.CONSTRAINT_VIOLATED.value,
                _AET.ACTION_DENIED.value,
                _AET.TRUST_DENIED.value,
                _AET.WORKFLOW_ERROR.value,
                _AET.NODE_ERROR.value,
                _AET.SYSTEM_EVENT.value,
                _PAA.BARRIER_ENFORCED.value,
            ),
        ),
        CriterionSpec(
            key="operational_suspensions",
            description=(
                "Operational suspensions and resumptions: governance plan "
                "suspend/resume and resume-condition updates."
            ),
            source_actions=(
                _PAA.PLAN_SUSPENDED.value,
                _PAA.PLAN_RESUMED.value,
                _PAA.RESUME_CONDITION_UPDATED.value,
            ),
        ),
        CriterionSpec(
            key="monitoring_alerts",
            description="External monitoring, alerting, and incident/escalation records.",
            source_actions=(),
            unverifiable_reason=(
                "The SDK emits no monitoring/alert/incident/escalation record "
                "primitive; operational monitoring and incident response run in "
                "the deploying organization's observability and on-call systems, "
                "outside the SDK's emission surface."
            ),
        ),
    ),
)


# ---------------------------------------------------------------------------
# Registry of implemented controls
# ---------------------------------------------------------------------------

CONTROL_SPECS: dict[str, ControlSpec] = {
    _CC6.control: _CC6,
    _CC7.control: _CC7,
    _CC8.control: _CC8,
}
"""Implemented SOC 2 controls, keyed by control id."""

IMPLEMENTED_CONTROLS: tuple[str, ...] = tuple(CONTROL_SPECS)
