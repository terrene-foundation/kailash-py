# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""
Kailash Trust Plane — EATP-powered trust environment for human-AI collaborative work.

The trust plane sits between human authority and AI execution, providing
cryptographic attestation for decisions, milestones, and verification in
collaborative projects.

Core types:

- :class:`TrustProject` — Project-scoped trust environment with constraint
  enforcement, delegation, and verification.
- :class:`TrustPlaneStore` — Abstract protocol for record persistence.
- :class:`SqliteTrustPlaneStore` — Default single-file SQLite backend.
- :class:`FileSystemTrustPlaneStore` — Git-friendly JSON file backend.
- :class:`DecisionRecord`, :class:`MilestoneRecord` — Auditable project records.
- :class:`ConstraintEnvelope` — Structured constraints across all 5 EATP
  dimensions (Financial, Operational, Temporal, Data Access, Communication).

Quick start::

    from kailash.trust.plane import TrustProject, DecisionRecord, DecisionType

    project = await TrustProject.create(
        trust_dir="workspaces/my-project/trust-plane",
        project_name="My Project",
        author="Developer",
    )

    await project.record_decision(DecisionRecord(
        decision_type=DecisionType.TECHNICAL,
        decision="Use modular architecture",
        rationale="Separation of concerns",
    ))

    result = await project.verify()
"""

from __future__ import annotations

import logging

# ---------------------------------------------------------------------------
# Models (constraint envelopes, records, enums)
# ---------------------------------------------------------------------------

from kailash.trust.plane.models import (
    CommunicationConstraints,
    ConstraintEnvelope,
    DataAccessConstraints,
    DecisionRecord,
    DecisionType,
    EscalationRecord,
    ExecutionRecord,
    FinancialConstraints,
    HumanCompetency,
    InterventionRecord,
    MilestoneRecord,
    OperationalConstraints,
    ProjectManifest,
    ReviewRequirement,
    TemporalConstraints,
    VerificationCategory,
)

# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

from kailash.trust.plane.exceptions import (
    ArchiveError,
    BudgetExhaustedError,
    ConstraintViolationError,
    IdentityError,
    JWKSError,
    KeyExpiredError,
    KeyManagerError,
    KeyNotFoundError,
    LockTimeoutError,
    RBACError,
    RecordNotFoundError,
    SchemaMigrationError,
    SchemaTooNewError,
    SigningError,
    StoreConnectionError,
    StoreQueryError,
    StoreTransactionError,
    TLSSyslogError,
    TokenVerificationError,
    TrustDecryptionError,
    TrustPlaneError,
    TrustPlaneStoreError,
    VerificationError,
)

# ---------------------------------------------------------------------------
# Project
# ---------------------------------------------------------------------------

from kailash.trust.plane.project import TrustProject

# ---------------------------------------------------------------------------
# Store protocol and backends
# ---------------------------------------------------------------------------

from kailash.trust.plane.store import TrustPlaneStore
from kailash.trust.plane.store.filesystem import FileSystemTrustPlaneStore
from kailash.trust.plane.store.sqlite import SqliteTrustPlaneStore

logger = logging.getLogger(__name__)

__all__ = [
    # --- Project ---
    "TrustProject",
    # --- Store protocol and backends ---
    "TrustPlaneStore",
    "FileSystemTrustPlaneStore",
    "SqliteTrustPlaneStore",
    # --- Exceptions ---
    "TrustPlaneError",
    "TrustPlaneStoreError",
    "TrustDecryptionError",
    "RecordNotFoundError",
    "SchemaTooNewError",
    "SchemaMigrationError",
    "StoreConnectionError",
    "StoreQueryError",
    "StoreTransactionError",
    "ConstraintViolationError",
    "BudgetExhaustedError",
    "IdentityError",
    "TokenVerificationError",
    "JWKSError",
    "KeyManagerError",
    "KeyNotFoundError",
    "KeyExpiredError",
    "SigningError",
    "VerificationError",
    "RBACError",
    "ArchiveError",
    "TLSSyslogError",
    "LockTimeoutError",
    # --- Models ---
    "CommunicationConstraints",
    "ConstraintEnvelope",
    "DataAccessConstraints",
    "DecisionRecord",
    "DecisionType",
    "EscalationRecord",
    "ExecutionRecord",
    "FinancialConstraints",
    "HumanCompetency",
    "InterventionRecord",
    "MilestoneRecord",
    "OperationalConstraints",
    "ProjectManifest",
    "ReviewRequirement",
    "TemporalConstraints",
    "VerificationCategory",
]
