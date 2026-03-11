# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""
Data models for the Agent Registry.

This module defines the core data structures for representing
agents in the registry, including their metadata, status, and
registration requests.

Key Components:
- AgentStatus: Enum representing agent availability states
- AgentMetadata: Complete metadata about a registered agent
- RegistrationRequest: Request object for registering new agents
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional


class AgentStatus(Enum):
    """
    Enumeration of possible agent statuses.

    Status values indicate the current availability and trust state
    of an agent in the registry.

    Values:
        ACTIVE: Agent is active and available for discovery and delegation.
            This is the normal operating state for healthy agents.

        INACTIVE: Agent is registered but not currently active.
            Used when an agent voluntarily goes offline or pauses operation.

        REVOKED: Agent's trust has been revoked by an authority.
            This is a permanent state indicating the agent should not be trusted.
            Revocation happens through the trust system, not the registry.

        SUSPENDED: Agent is temporarily suspended due to inactivity.
            Used by health monitoring when an agent stops sending heartbeats.
            Can be reactivated when the agent resumes operation.

        UNKNOWN: Status cannot be determined.
            Used when there's an error checking agent status.
    """

    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    REVOKED = "REVOKED"
    SUSPENDED = "SUSPENDED"
    UNKNOWN = "UNKNOWN"

    def is_available(self) -> bool:
        """
        Check if this status indicates the agent is available.

        Returns:
            True only if status is ACTIVE, False otherwise.

        Example:
            >>> AgentStatus.ACTIVE.is_available()
            True
            >>> AgentStatus.SUSPENDED.is_available()
            False
        """
        return self == AgentStatus.ACTIVE


@dataclass
class AgentMetadata:
    """
    Complete metadata about a registered agent.

    This dataclass holds all information about an agent that is stored
    in the registry, including identity, capabilities, constraints,
    and operational state.

    Attributes:
        agent_id: Unique identifier for the agent. Must be unique across
            the entire registry. Typically matches the trust chain agent_id.

        agent_type: Type classification of the agent. Common values include:
            - "supervisor": Agents that coordinate other agents
            - "worker": Agents that perform specific tasks
            - "autonomous": Self-directed agents with broad capabilities
            - Custom types for domain-specific categorization

        capabilities: List of capabilities this agent possesses. These must
            be a subset of the capabilities in the agent's trust chain.
            Used for capability-based discovery.

        constraints: List of active constraints on the agent. These come
            from the agent's trust chain and limit what the agent can do.
            Used to exclude agents from certain tasks.

        status: Current operational status of the agent. See AgentStatus
            for possible values and their meanings.

        trust_chain_hash: Hash of the agent's current trust chain. Used
            to verify that the agent's trust hasn't been modified since
            registration. Updated when trust chain changes.

        registered_at: Timestamp when the agent was first registered.
            Set automatically during registration and never changes.

        last_seen: Timestamp of the agent's most recent activity. Updated
            by heartbeat calls and used for stale agent detection.

        metadata: Additional key-value metadata about the agent. Can include:
            - version: Agent software version
            - description: Human-readable description
            - tags: List of searchable tags
            - Custom application-specific data

        endpoint: Optional network endpoint for remote agents. Used in
            distributed deployments where agents may be on different nodes.
            Format: "host:port" or full URL.

        public_key: Optional public key for agent verification. Used for
            cryptographic verification of agent identity in secure deployments.

    Example:
        >>> metadata = AgentMetadata(
        ...     agent_id="data-analyst-001",
        ...     agent_type="worker",
        ...     capabilities=["analyze_financial_data", "query_database"],
        ...     constraints=["read_only", "q4_data_only"],
        ...     status=AgentStatus.ACTIVE,
        ...     trust_chain_hash="abc123...",
        ...     registered_at=datetime.now(timezone.utc),
        ...     last_seen=datetime.now(timezone.utc),
        ...     metadata={"version": "1.0.0", "description": "Financial analyst"}
        ... )
    """

    agent_id: str
    agent_type: str
    capabilities: List[str]
    constraints: List[str]
    status: AgentStatus
    trust_chain_hash: str
    registered_at: datetime
    last_seen: datetime
    metadata: Dict[str, Any] = field(default_factory=dict)
    endpoint: Optional[str] = None
    public_key: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert metadata to a dictionary for serialization.

        Returns:
            Dictionary representation of the metadata with all fields.
            Datetime fields are converted to ISO format strings.
            Enum values are converted to their string values.

        Example:
            >>> data = metadata.to_dict()
            >>> data["agent_id"]
            'data-analyst-001'
        """
        return {
            "agent_id": self.agent_id,
            "agent_type": self.agent_type,
            "capabilities": self.capabilities,
            "constraints": self.constraints,
            "status": self.status.value,
            "trust_chain_hash": self.trust_chain_hash,
            "registered_at": self.registered_at.isoformat(),
            "last_seen": self.last_seen.isoformat(),
            "metadata": self.metadata,
            "endpoint": self.endpoint,
            "public_key": self.public_key,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AgentMetadata":
        """
        Create AgentMetadata from a dictionary.

        Args:
            data: Dictionary containing metadata fields. Must include
                all required fields. Datetime fields can be ISO strings
                or datetime objects.

        Returns:
            AgentMetadata instance with the provided data.

        Raises:
            KeyError: If required fields are missing.
            ValueError: If status is not a valid AgentStatus value.

        Example:
            >>> metadata = AgentMetadata.from_dict({
            ...     "agent_id": "agent-001",
            ...     "agent_type": "worker",
            ...     "capabilities": ["analyze_data"],
            ...     "constraints": [],
            ...     "status": "ACTIVE",
            ...     "trust_chain_hash": "abc123",
            ...     "registered_at": "2024-01-01T00:00:00",
            ...     "last_seen": "2024-01-01T00:00:00",
            ... })
        """
        # Parse datetime fields
        registered_at = data["registered_at"]
        if isinstance(registered_at, str):
            registered_at = datetime.fromisoformat(registered_at)

        last_seen = data["last_seen"]
        if isinstance(last_seen, str):
            last_seen = datetime.fromisoformat(last_seen)

        # Parse status enum
        status = data["status"]
        if isinstance(status, str):
            status = AgentStatus(status)

        return cls(
            agent_id=data["agent_id"],
            agent_type=data["agent_type"],
            capabilities=data.get("capabilities", []),
            constraints=data.get("constraints", []),
            status=status,
            trust_chain_hash=data["trust_chain_hash"],
            registered_at=registered_at,
            last_seen=last_seen,
            metadata=data.get("metadata", {}),
            endpoint=data.get("endpoint"),
            public_key=data.get("public_key"),
        )


@dataclass
class RegistrationRequest:
    """
    Request object for registering an agent in the registry.

    This dataclass contains all the information needed to register
    a new agent, including identity, capabilities, and trust verification
    parameters.

    Attributes:
        agent_id: Unique identifier for the agent to register. Must match
            an existing trust chain agent_id if verify_trust is True.

        agent_type: Type classification for the agent. See AgentMetadata
            for common values.

        capabilities: List of capabilities to register. If verify_trust is
            True, these must all be present in the agent's trust chain.

        constraints: List of constraints on the agent. Should match
            the constraints in the agent's trust chain.

        metadata: Additional metadata about the agent. See AgentMetadata
            for common keys.

        trust_chain_hash: Hash of the agent's current trust chain. Used
            to verify the trust chain hasn't changed since the request
            was created.

        endpoint: Optional network endpoint for the agent.

        public_key: Optional public key for agent verification.

        verify_trust: Whether to verify the agent's trust chain before
            registration. Default is True for security. Set to False
            only in trusted environments or for testing.

    Example:
        >>> request = RegistrationRequest(
        ...     agent_id="agent-001",
        ...     agent_type="worker",
        ...     capabilities=["analyze_data", "query_database"],
        ...     constraints=["read_only"],
        ...     metadata={"version": "1.0.0"},
        ...     trust_chain_hash="abc123...",
        ...     verify_trust=True
        ... )
        >>> errors = request.validate()
        >>> if not errors:
        ...     metadata = await registry.register(request)
    """

    agent_id: str
    agent_type: str
    capabilities: List[str]
    constraints: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    trust_chain_hash: str = ""
    endpoint: Optional[str] = None
    public_key: Optional[str] = None
    verify_trust: bool = True

    def validate(self) -> List[str]:
        """
        Validate the registration request.

        Checks all required fields and formats for validity. Does not
        check trust chain validity - that happens during registration.

        Returns:
            List of validation error messages. Empty list means valid.

        Validation checks:
            - agent_id is not empty
            - agent_type is not empty
            - capabilities list is not empty
            - trust_chain_hash is not empty (if verify_trust is True)

        Example:
            >>> request = RegistrationRequest(agent_id="", ...)
            >>> errors = request.validate()
            >>> "agent_id cannot be empty" in errors
            True
        """
        errors: List[str] = []

        # Check agent_id
        if not self.agent_id or not self.agent_id.strip():
            errors.append("agent_id cannot be empty")

        # Check agent_type
        if not self.agent_type or not self.agent_type.strip():
            errors.append("agent_type cannot be empty")

        # Check capabilities
        if not self.capabilities:
            errors.append("capabilities cannot be empty")

        # Check trust_chain_hash (required if verify_trust is True)
        if self.verify_trust and (
            not self.trust_chain_hash or not self.trust_chain_hash.strip()
        ):
            errors.append("trust_chain_hash cannot be empty when verify_trust is True")

        return errors
