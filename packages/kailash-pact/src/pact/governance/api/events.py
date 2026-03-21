# Copyright 2026 Terrene Foundation
# Licensed under the Apache License, Version 2.0
"""WebSocket event types for governance decisions.

Extends the platform EventBus with governance-specific event types:
- ACCESS_CHECKED -- result of a check-access evaluation
- ACTION_VERIFIED -- result of a verify-action evaluation
- CLEARANCE_GRANTED -- clearance granted to a role
- CLEARANCE_REVOKED -- clearance revoked from a role
- BRIDGE_CREATED -- Cross-Functional Bridge established
- KSP_CREATED -- Knowledge Share Policy created
- ENVELOPE_SET -- role or task envelope configured

These events are emitted by the governance API endpoints when mutations
occur, enabling real-time dashboard updates via WebSocket.
"""

from __future__ import annotations

import logging
from enum import Enum
from typing import Any

from pact.use.api.events import EventType, PlatformEvent, event_bus

logger = logging.getLogger(__name__)

__all__ = ["GovernanceEventType", "emit_governance_event"]


class GovernanceEventType(str, Enum):
    """Event types specific to governance operations."""

    ACCESS_CHECKED = "governance.access_checked"
    ACTION_VERIFIED = "governance.action_verified"
    CLEARANCE_GRANTED = "governance.clearance_granted"
    CLEARANCE_REVOKED = "governance.clearance_revoked"
    BRIDGE_CREATED = "governance.bridge_created"
    KSP_CREATED = "governance.ksp_created"
    ENVELOPE_SET = "governance.envelope_set"


async def emit_governance_event(
    event_type: GovernanceEventType,
    data: dict[str, Any],
    *,
    source_role_address: str = "",
) -> PlatformEvent | None:
    """Emit a governance event to the platform EventBus.

    Creates a PlatformEvent with EventType.VERIFICATION_RESULT (the closest
    existing platform event type for governance decisions) and attaches
    the governance-specific event type in the data payload.

    Args:
        event_type: The governance-specific event type.
        data: Event payload (must be JSON-serializable).
        source_role_address: Optional role that triggered the event.

    Returns:
        The emitted PlatformEvent, or None if emission failed.
    """
    try:
        enriched_data = {
            "governance_event_type": event_type.value,
            **data,
        }
        event = PlatformEvent(
            EventType.VERIFICATION_RESULT,
            enriched_data,
            source_agent_id=source_role_address,
        )
        await event_bus.publish(event)
        logger.debug(
            "Emitted governance event: type=%s role=%s",
            event_type.value,
            source_role_address,
        )
        return event
    except Exception:
        logger.exception(
            "Failed to emit governance event: type=%s -- continuing without event",
            event_type.value,
        )
        return None
