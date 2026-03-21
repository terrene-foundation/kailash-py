# Copyright 2026 Terrene Foundation
# Licensed under the Apache License, Version 2.0
# Timestamp naming: timestamp (generic), created_at (creation), <verb>_at (lifecycle events)
"""
PACT — Governed operational model for running organizations
with AI agents under EATP trust governance.

Architecture:
    pact.trust       — EATP trust layer (genesis, delegation, verification)
    pact.trust.constraint  — Constraint envelope evaluation (5 dimensions)
    pact.use.execution   — Agent execution plane (Kaizen-based runtime)
    pact.trust.audit       — Audit anchor chain (tamper-evident records)
    pact.build.workspace   — Workspace-as-knowledge-base management
    pact.build.config      — Platform configuration and agent definitions
"""

__version__ = "0.2.0"

# --- Audit ---
# --- Config ---
from pact.build.config.schema import (
    AgentConfig,
    ConstraintEnvelopeConfig,
    PactConfig,
    PlatformConfig,
    TeamConfig,
    WorkspaceConfig,
)

# --- Workspace ---
from pact.build.workspace.models import Workspace, WorkspacePhase, WorkspaceRegistry

# --- Trust ---
from pact.trust.attestation import CapabilityAttestation
from pact.trust.audit.anchor import AuditAnchor, AuditChain

# --- Constraint ---
from pact.trust.constraint.envelope import ConstraintEnvelope, EvaluationResult
from pact.trust.constraint.gradient import GradientEngine
from pact.trust.posture import TrustPosture
from pact.trust.scoring import TrustScore, calculate_trust_score

# --- Execution ---
from pact.use.execution.agent import AgentDefinition, TeamDefinition
from pact.use.execution.approval import ApprovalQueue, PendingAction, UrgencyLevel
from pact.use.execution.registry import AgentRecord, AgentRegistry, AgentStatus
from pact.use.execution.session import (
    PactSession,
    PlatformSession,
    SessionCheckpoint,
    SessionManager,
    SessionState,
)

__all__ = [
    # Config
    "PactConfig",
    "PlatformConfig",
    "AgentConfig",
    "TeamConfig",
    "WorkspaceConfig",
    "ConstraintEnvelopeConfig",
    # Constraint
    "ConstraintEnvelope",
    "GradientEngine",
    "EvaluationResult",
    # Trust
    "TrustPosture",
    "CapabilityAttestation",
    "TrustScore",
    "calculate_trust_score",
    # Audit
    "AuditAnchor",
    "AuditChain",
    # Workspace
    "Workspace",
    "WorkspacePhase",
    "WorkspaceRegistry",
    # Execution
    "AgentDefinition",
    "TeamDefinition",
    "ApprovalQueue",
    "PendingAction",
    "UrgencyLevel",
    "AgentRecord",
    "AgentRegistry",
    "AgentStatus",
    "PactSession",
    "PlatformSession",
    "SessionCheckpoint",
    "SessionManager",
    "SessionState",
]
