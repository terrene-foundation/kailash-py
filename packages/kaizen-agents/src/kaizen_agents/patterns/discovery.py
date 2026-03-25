"""Agent discovery extensions for Enterprise-App integration.

Provides user-filtered agent discovery and skill metadata for UI integration.

See: TODO-204 Enterprise-App Streaming Integration
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .registry import AgentRegistry
from .runtime import AgentMetadata, AgentStatus


@dataclass
class AccessConstraints:
    """Constraints on agent access for a user."""

    max_daily_invocations: Optional[int] = None
    max_tokens_per_session: Optional[int] = None
    max_cost_per_session_usd: Optional[float] = None
    allowed_tools: Optional[List[str]] = None
    blocked_tools: Optional[List[str]] = None
    time_window_start: Optional[str] = None  # ISO time (e.g., "09:00:00")
    time_window_end: Optional[str] = None  # ISO time (e.g., "17:00:00")

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "max_daily_invocations": self.max_daily_invocations,
            "max_tokens_per_session": self.max_tokens_per_session,
            "max_cost_per_session_usd": self.max_cost_per_session_usd,
            "allowed_tools": self.allowed_tools,
            "blocked_tools": self.blocked_tools,
            "time_window_start": self.time_window_start,
            "time_window_end": self.time_window_end,
        }


@dataclass
class AccessMetadata:
    """Access metadata for a user's access to an agent."""

    permission_level: str = "execute"  # execute, view, admin
    constraints: AccessConstraints = field(default_factory=AccessConstraints)
    granted_by: Optional[str] = None  # User/role that granted access
    granted_at: Optional[str] = None  # ISO timestamp
    expires_at: Optional[str] = None  # ISO timestamp

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "permission_level": self.permission_level,
            "constraints": self.constraints.to_dict(),
            "granted_by": self.granted_by,
            "granted_at": self.granted_at,
            "expires_at": self.expires_at,
        }


@dataclass
class AgentWithAccess:
    """Agent metadata combined with access information.

    Returned by find_agents_for_user() to include both agent
    details and the user's access permissions.

    Example:
        >>> agent_with_access = await registry.find_agents_for_user(
        ...     user_id="user-123",
        ...     organization_id="org-456",
        ... )
        >>> print(agent_with_access.metadata.agent_id)
        >>> print(agent_with_access.access.permission_level)
    """

    metadata: AgentMetadata
    access: AccessMetadata

    @property
    def agent_id(self) -> str:
        """Get agent ID."""
        return self.metadata.agent_id

    @property
    def agent(self):
        """Get agent instance."""
        return self.metadata.agent

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "id": self.metadata.agent_id,
            "name": getattr(
                self.metadata.agent, "name", self.metadata.agent.__class__.__name__
            ),
            "status": self.metadata.status.value,
            "capabilities": self._extract_capabilities(),
            "_access": self.access.to_dict(),
        }

    def _extract_capabilities(self) -> List[str]:
        """Extract capabilities from A2A card."""
        if not self.metadata.a2a_card:
            return []

        capabilities = []
        if isinstance(self.metadata.a2a_card, dict):
            if "capability" in self.metadata.a2a_card:
                capabilities.append(self.metadata.a2a_card["capability"])
            if "capabilities" in self.metadata.a2a_card:
                caps = self.metadata.a2a_card["capabilities"]
                if isinstance(caps, list):
                    capabilities.extend(caps)
                elif isinstance(caps, str):
                    capabilities.append(caps)

        return capabilities


@dataclass
class AgentSkillMetadata:
    """Metadata for agent as skill in Enterprise-App UI.

    Provides all information needed to display an agent/skill
    in the Enterprise-App platform UI.

    Example:
        >>> skill = AgentSkillMetadata.from_agent(agent)
        >>> print(f"{skill.name}: {skill.description}")
    """

    id: str
    name: str
    description: str
    capabilities: List[str] = field(default_factory=list)
    suggested_prompts: List[str] = field(default_factory=list)
    input_schema: Optional[Dict[str, Any]] = None
    output_types: List[str] = field(default_factory=list)
    avg_execution_time_seconds: float = 0.0
    avg_cost_cents: float = 0.0
    tags: List[str] = field(default_factory=list)
    icon: Optional[str] = None
    category: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "capabilities": self.capabilities,
            "suggested_prompts": self.suggested_prompts,
            "input_schema": self.input_schema,
            "output_types": self.output_types,
            "avg_execution_time_seconds": self.avg_execution_time_seconds,
            "avg_cost_cents": self.avg_cost_cents,
            "tags": self.tags,
            "icon": self.icon,
            "category": self.category,
        }

    @classmethod
    def from_agent(
        cls,
        agent: Any,
        agent_id: Optional[str] = None,
        suggested_prompts: Optional[List[str]] = None,
        avg_execution_time: float = 0.0,
        avg_cost_cents: float = 0.0,
    ) -> "AgentSkillMetadata":
        """
        Create skill metadata from an agent instance.

        Args:
            agent: The agent instance
            agent_id: Optional agent ID (uses agent.agent_id if available)
            suggested_prompts: Optional example prompts
            avg_execution_time: Average execution time in seconds
            avg_cost_cents: Average cost in cents

        Returns:
            AgentSkillMetadata instance
        """
        # Extract basic info
        aid = agent_id or getattr(agent, "agent_id", None) or f"agent-{id(agent)}"
        name = getattr(agent, "name", None) or agent.__class__.__name__

        # Extract description from docstring or attribute
        description = (
            getattr(agent, "description", None)
            or getattr(agent, "__doc__", None)
            or f"{name} agent"
        )
        if description:
            description = description.strip().split("\n")[0]

        # Extract capabilities from A2A card
        capabilities = []
        a2a_card = getattr(agent, "_a2a_card", None)
        if a2a_card and isinstance(a2a_card, dict):
            if "capabilities" in a2a_card:
                caps = a2a_card["capabilities"]
                if isinstance(caps, list):
                    capabilities.extend(caps)
                elif isinstance(caps, str):
                    capabilities.append(caps)

        # Extract input schema from signature
        input_schema = None
        signature = getattr(agent, "_signature", None) or getattr(
            agent, "signature", None
        )
        if signature:
            input_schema = cls._extract_input_schema(signature)

        # Extract output types
        output_types = cls._extract_output_types(signature) if signature else []

        return cls(
            id=aid,
            name=name,
            description=description,
            capabilities=capabilities,
            suggested_prompts=suggested_prompts or [],
            input_schema=input_schema,
            output_types=output_types,
            avg_execution_time_seconds=avg_execution_time,
            avg_cost_cents=avg_cost_cents,
        )

    @classmethod
    def from_specialist_definition(
        cls,
        definition: Any,
        specialist_name: str,
    ) -> "AgentSkillMetadata":
        """
        Create skill metadata from a SpecialistDefinition.

        Args:
            definition: SpecialistDefinition instance
            specialist_name: Name of the specialist

        Returns:
            AgentSkillMetadata instance
        """
        return cls(
            id=specialist_name,
            name=specialist_name.replace("-", " ").replace("_", " ").title(),
            description=getattr(
                definition, "description", f"{specialist_name} specialist"
            ),
            capabilities=getattr(definition, "available_tools", []),
            suggested_prompts=getattr(definition, "suggested_prompts", []),
            input_schema=None,
            output_types=["text"],
            avg_execution_time_seconds=getattr(definition, "avg_execution_time", 0.0),
            avg_cost_cents=getattr(definition, "avg_cost_cents", 0.0),
            tags=getattr(definition, "tags", []),
            category=getattr(definition, "category", None),
        )

    @staticmethod
    def _extract_input_schema(signature: Any) -> Optional[Dict[str, Any]]:
        """Extract JSON schema from signature input fields."""
        schema = {
            "type": "object",
            "properties": {},
            "required": [],
        }

        try:
            for name, field_value in signature.__class__.__dict__.items():
                if hasattr(field_value, "__class__"):
                    field_class = field_value.__class__.__name__
                    if field_class == "InputField":
                        desc = getattr(field_value, "desc", "") or getattr(
                            field_value, "description", ""
                        )
                        schema["properties"][name] = {
                            "type": "string",
                            "description": desc,
                        }
                        # Check if required (no default)
                        if (
                            not hasattr(field_value, "default")
                            or field_value.default is None
                        ):
                            schema["required"].append(name)

            if not schema["properties"]:
                return None

            return schema
        except Exception:
            return None

    @staticmethod
    def _extract_output_types(signature: Any) -> List[str]:
        """Extract output types from signature."""
        output_types = []

        try:
            for name, field_value in signature.__class__.__dict__.items():
                if hasattr(field_value, "__class__"):
                    field_class = field_value.__class__.__name__
                    if field_class == "OutputField":
                        output_types.append(name)

            return output_types if output_types else ["text"]
        except Exception:
            return ["text"]


class UserFilteredAgentDiscovery:
    """
    Extension for AgentRegistry to provide user-filtered agent discovery.

    Wraps an AgentRegistry and adds user permission filtering.

    Example:
        >>> registry = AgentRegistry()
        >>> discovery = UserFilteredAgentDiscovery(registry)
        >>> agents = await discovery.find_agents_for_user(
        ...     user_id="user-123",
        ...     organization_id="org-456",
        ... )
    """

    def __init__(
        self,
        registry: AgentRegistry,
        permission_checker: Optional[Any] = None,
    ):
        """
        Initialize discovery extension.

        Args:
            registry: The AgentRegistry to wrap
            permission_checker: Optional permission checker (TrustOperations)
        """
        self._registry = registry
        self._permission_checker = permission_checker

    async def find_agents_for_user(
        self,
        user_id: str,
        organization_id: str,
        status_filter: Optional[AgentStatus] = AgentStatus.ACTIVE,
        capability_filter: Optional[str] = None,
    ) -> List[AgentWithAccess]:
        """
        Find agents accessible to a specific user.

        Args:
            user_id: User identifier
            organization_id: Organization identifier
            status_filter: Optional status filter (default: ACTIVE)
            capability_filter: Optional capability filter

        Returns:
            List of AgentWithAccess with access metadata
        """
        # Get all agents from registry
        if capability_filter:
            agents = await self._registry.find_agents_by_capability(
                capability_filter, status_filter
            )
        else:
            agents = await self._registry.list_agents(status_filter=status_filter)

        # Filter by user permissions and add access metadata
        results = []
        for agent_metadata in agents:
            # Check permission
            has_access, access_meta = await self._check_user_access(
                user_id, organization_id, agent_metadata
            )

            if has_access:
                results.append(
                    AgentWithAccess(
                        metadata=agent_metadata,
                        access=access_meta,
                    )
                )

        return results

    async def _check_user_access(
        self,
        user_id: str,
        organization_id: str,
        agent_metadata: AgentMetadata,
    ) -> tuple[bool, AccessMetadata]:
        """
        Check if user has access to agent.

        Args:
            user_id: User identifier
            organization_id: Organization identifier
            agent_metadata: Agent metadata

        Returns:
            Tuple of (has_access, access_metadata)
        """
        # If permission checker is available, use it
        if self._permission_checker:
            try:
                result = await self._permission_checker.verify(
                    agent_id=agent_metadata.agent_id,
                    action="execute",
                    user_id=user_id,
                    organization_id=organization_id,
                )
                if hasattr(result, "valid") and not result.valid:
                    return False, AccessMetadata()

                # Extract constraints from verification result
                constraints = AccessConstraints()
                if hasattr(result, "constraints"):
                    if "max_daily_invocations" in result.constraints:
                        constraints.max_daily_invocations = result.constraints[
                            "max_daily_invocations"
                        ]
                    if "max_tokens" in result.constraints:
                        constraints.max_tokens_per_session = result.constraints[
                            "max_tokens"
                        ]

                return True, AccessMetadata(
                    permission_level="execute",
                    constraints=constraints,
                )
            except Exception:
                # Fall through to default behavior
                pass

        # Default: grant access with default constraints
        return True, AccessMetadata(
            permission_level="execute",
            constraints=AccessConstraints(),
        )

    async def get_skill_metadata(
        self,
        agent_id: str,
    ) -> Optional[AgentSkillMetadata]:
        """
        Get skill metadata for an agent.

        Args:
            agent_id: Agent identifier

        Returns:
            AgentSkillMetadata or None if agent not found
        """
        agent_metadata = await self._registry.get_agent(agent_id)
        if not agent_metadata:
            return None

        return AgentSkillMetadata.from_agent(
            agent=agent_metadata.agent,
            agent_id=agent_id,
        )

    async def list_skill_metadata(
        self,
        user_id: Optional[str] = None,
        organization_id: Optional[str] = None,
    ) -> List[AgentSkillMetadata]:
        """
        List skill metadata for all accessible agents.

        Args:
            user_id: Optional user ID for filtering
            organization_id: Optional organization ID for filtering

        Returns:
            List of AgentSkillMetadata
        """
        if user_id and organization_id:
            agents = await self.find_agents_for_user(user_id, organization_id)
            return [
                AgentSkillMetadata.from_agent(a.metadata.agent, a.agent_id)
                for a in agents
            ]
        else:
            agents = await self._registry.list_agents()
            return [AgentSkillMetadata.from_agent(a.agent, a.agent_id) for a in agents]


__all__ = [
    "AccessConstraints",
    "AccessMetadata",
    "AgentWithAccess",
    "AgentSkillMetadata",
    "UserFilteredAgentDiscovery",
]
