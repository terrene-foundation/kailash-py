"""Communication protocols: delegation, clarification, escalation, completion."""

from kaizen_agents.protocols.clarification import ClarificationProtocol
from kaizen_agents.protocols.delegation import DelegationProtocol
from kaizen_agents.protocols.escalation import EscalationAction, EscalationProtocol

__all__ = [
    "ClarificationProtocol",
    "DelegationProtocol",
    "EscalationAction",
    "EscalationProtocol",
]
