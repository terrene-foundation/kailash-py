# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""TrustPlane — EATP-powered trust environment for human-AI collaborative work."""

__version__ = "0.2.0"

from trustplane.models import (
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
from trustplane.exceptions import (
    RecordNotFoundError,
    SchemaMigrationError,
    SchemaTooNewError,
    TrustDecryptionError,
    TrustPlaneError,
    TrustPlaneStoreError,
)
from trustplane.project import TrustProject
from trustplane.store import TrustPlaneStore
from trustplane.store.filesystem import FileSystemTrustPlaneStore
from trustplane.store.sqlite import SqliteTrustPlaneStore

__all__ = [
    "TrustProject",
    "TrustPlaneStore",
    "FileSystemTrustPlaneStore",
    "SqliteTrustPlaneStore",
    "TrustPlaneError",
    "TrustPlaneStoreError",
    "TrustDecryptionError",
    "RecordNotFoundError",
    "SchemaTooNewError",
    "SchemaMigrationError",
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
