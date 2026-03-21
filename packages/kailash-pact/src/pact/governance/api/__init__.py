# Copyright 2026 Terrene Foundation
# Licensed under the Apache License, Version 2.0
"""Governance REST API -- endpoints, auth, schemas, and WebSocket events."""

from pact.governance.api.auth import GovernanceAuth
from pact.governance.api.events import GovernanceEventType, emit_governance_event
from pact.governance.api.router import create_governance_app, mount_governance_api
from pact.governance.api.schemas import (
    CheckAccessRequest,
    CheckAccessResponse,
    CreateBridgeRequest,
    CreateKSPRequest,
    GrantClearanceRequest,
    OrgNodeResponse,
    OrgSummaryResponse,
    SetEnvelopeRequest,
    VerifyActionRequest,
    VerifyActionResponse,
)

__all__ = [
    # Auth
    "GovernanceAuth",
    # Schemas
    "CheckAccessRequest",
    "CheckAccessResponse",
    "CreateBridgeRequest",
    "CreateKSPRequest",
    "GrantClearanceRequest",
    "OrgNodeResponse",
    "OrgSummaryResponse",
    "SetEnvelopeRequest",
    "VerifyActionRequest",
    "VerifyActionResponse",
    # Events
    "GovernanceEventType",
    "emit_governance_event",
    # Router
    "create_governance_app",
    "mount_governance_api",
]
