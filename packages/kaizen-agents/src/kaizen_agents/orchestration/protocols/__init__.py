"""Communication protocols: delegation, clarification, escalation, completion."""

from kaizen_agents.orchestration.protocols.clarification import ClarificationProtocol
from kaizen_agents.orchestration.protocols.delegation import DelegationProtocol
from kaizen_agents.orchestration.protocols.escalation import EscalationAction, EscalationProtocol

__all__ = [
    "ClarificationProtocol",
    "DelegationProtocol",
    "EscalationAction",
    "EscalationProtocol",
]
