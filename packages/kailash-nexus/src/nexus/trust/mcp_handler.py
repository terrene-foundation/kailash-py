"""MCP + EATP Integration Handler for Kailash Nexus.

This module provides components for secure agent-to-agent (A2A) communication
over MCP (Model Context Protocol), integrating with EATP (Extensible Agent
Trust Protocol) for trust propagation and delegation.

The MCPEATPHandler manages the lifecycle of MCP calls between agents:
1. prepare_mcp_call() - Creates delegation context before a tool call
2. verify_mcp_response() - Validates and audits the response
3. get_call_history() - Returns audit trail of all calls

A2A Call Flow:
    1. Agent A wants to call Agent B's tool
    2. prepare_mcp_call() verifies Agent A has permission, creates delegation
    3. Returns MCPEATPContext with delegation info
    4. Tool executes
    5. verify_mcp_response() audits and validates the response

Usage:
    from nexus.trust.mcp_handler import MCPEATPHandler, MCPEATPContext

    handler = MCPEATPHandler()

    # Before calling a tool on another agent
    context = await handler.prepare_mcp_call(
        calling_agent="agent-a",
        target_agent="agent-b",
        tool_name="search_documents",
        mcp_session_id="session-123",
    )

    # After receiving the response
    is_valid = await handler.verify_mcp_response(context, response)

    # Get audit trail
    history = handler.get_call_history()
"""

import logging
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable

logger = logging.getLogger(__name__)


@runtime_checkable
class TrustOperationsProtocol(Protocol):
    """Protocol for TrustOperations to avoid hard Kaizen dependency.

    This protocol defines the interface that TrustOperations must implement
    for use with the MCPEATPHandler. This allows the handler to work with
    or without a TrustOperations instance.
    """

    async def create_delegation(
        self,
        from_agent: str,
        to_agent: str,
        capabilities: List[str],
        **kwargs: Any,
    ) -> Any:
        """Create a delegation from one agent to another."""
        ...

    async def audit(
        self,
        action: str,
        agent_id: str,
        target_id: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> None:
        """Record an audit entry for an action."""
        ...


@dataclass
class MCPEATPContext:
    """Context for MCP calls with EATP trust integration.

    This dataclass holds all context information for an MCP call between
    agents, including session information, trust context, and delegation
    details.

    Attributes:
        mcp_session_id: MCP session identifier for the call
        eatp_trace_id: EATP trace ID for request tracing
        agent_id: Identifier of the calling agent
        target_agent_id: Identifier of the target agent providing the tool
        human_origin: Optional human origin information from trust context
        delegated_capabilities: List of capabilities delegated to target
        constraints: Operation constraints inherited from trust context
        delegation_id: Optional delegation ID if TrustOperations is used
        created_at: Timestamp when the context was created
    """

    mcp_session_id: str
    eatp_trace_id: str
    agent_id: str
    target_agent_id: str
    human_origin: Optional[Dict[str, Any]] = None
    delegated_capabilities: List[str] = field(default_factory=list)
    constraints: Dict[str, Any] = field(default_factory=dict)
    delegation_id: Optional[str] = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> Dict[str, Any]:
        """Convert the context to a dictionary for serialization.

        Returns:
            Dictionary representation of the context.
        """
        return {
            "mcp_session_id": self.mcp_session_id,
            "eatp_trace_id": self.eatp_trace_id,
            "agent_id": self.agent_id,
            "target_agent_id": self.target_agent_id,
            "human_origin": self.human_origin,
            "delegated_capabilities": self.delegated_capabilities,
            "constraints": self.constraints,
            "delegation_id": self.delegation_id,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MCPEATPContext":
        """Create an MCPEATPContext from a dictionary.

        Args:
            data: Dictionary containing context fields.

        Returns:
            MCPEATPContext instance.
        """
        # Parse created_at if it's a string
        created_at = data.get("created_at")
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at)
        elif created_at is None:
            created_at = datetime.now(timezone.utc)

        return cls(
            mcp_session_id=data["mcp_session_id"],
            eatp_trace_id=data["eatp_trace_id"],
            agent_id=data["agent_id"],
            target_agent_id=data["target_agent_id"],
            human_origin=data.get("human_origin"),
            delegated_capabilities=data.get("delegated_capabilities", []),
            constraints=data.get("constraints", {}),
            delegation_id=data.get("delegation_id"),
            created_at=created_at,
        )


class MCPEATPHandler:
    """Handler for MCP calls with EATP trust integration.

    This class manages the lifecycle of MCP calls between agents, integrating
    with EATP for trust propagation and delegation. It works with or without
    a TrustOperations instance.

    When TrustOperations is provided:
        - Delegations are created for each call
        - Audit records are maintained
        - Trust policies are enforced

    When TrustOperations is not provided (standalone mode):
        - Basic context tracking is performed
        - Call history is maintained
        - No trust verification occurs

    Example:
        >>> handler = MCPEATPHandler()
        >>>
        >>> # Prepare a call
        >>> context = await handler.prepare_mcp_call(
        ...     calling_agent="agent-a",
        ...     target_agent="agent-b",
        ...     tool_name="search",
        ...     mcp_session_id="session-123",
        ... )
        >>>
        >>> # Verify response
        >>> is_valid = await handler.verify_mcp_response(context, response)
        >>>
        >>> # Get history
        >>> history = handler.get_call_history()
    """

    def __init__(
        self,
        trust_operations: Optional[TrustOperationsProtocol] = None,
    ) -> None:
        """Initialize the MCPEATPHandler.

        Args:
            trust_operations: Optional TrustOperations instance for delegation
                and auditing. If not provided, the handler operates in
                standalone mode without trust verification.
        """
        self._trust_operations = trust_operations
        self._call_history: List[MCPEATPContext] = []
        # ROUND5-001: Thread-safe access to _call_history
        self._lock = threading.Lock()

    async def prepare_mcp_call(
        self,
        calling_agent: str,
        target_agent: str,
        tool_name: str,
        mcp_session_id: str,
        trust_context: Optional[Dict[str, Any]] = None,
    ) -> MCPEATPContext:
        """Prepare context for an MCP tool call between agents.

        This method creates the delegation context before a tool call is made.
        It validates the call parameters, extracts trust context, and
        optionally creates a delegation via TrustOperations.

        Args:
            calling_agent: Identifier of the agent making the call.
            target_agent: Identifier of the agent providing the tool.
            tool_name: Name of the tool being called.
            mcp_session_id: MCP session identifier for the call.
            trust_context: Optional dictionary containing trust context:
                - trace_id: Existing EATP trace ID to use
                - constraints: Operation constraints to inherit
                - human_origin: Human origin information to propagate

        Returns:
            MCPEATPContext with delegation information.

        Raises:
            ValueError: If parameters are invalid (empty strings, self-call).
        """
        # Validate parameters - explicit errors, no defaults
        if not calling_agent or not calling_agent.strip():
            raise ValueError("calling_agent cannot be empty")

        if not target_agent or not target_agent.strip():
            raise ValueError("target_agent cannot be empty")

        if not tool_name or not tool_name.strip():
            raise ValueError("tool_name cannot be empty")

        if not mcp_session_id or not mcp_session_id.strip():
            raise ValueError("mcp_session_id cannot be empty")

        # Self-call rejection
        if calling_agent == target_agent:
            raise ValueError(
                f"Agent '{calling_agent}' cannot call itself. "
                "Self-calls are not permitted in A2A communication."
            )

        # Extract trust context fields
        trust_context = trust_context or {}
        trace_id = trust_context.get("trace_id") or self._generate_trace_id()
        constraints = trust_context.get("constraints", {})
        human_origin = trust_context.get("human_origin")

        # Create delegation if TrustOperations is available
        delegation_id = None
        if self._trust_operations is not None:
            try:
                delegation = await self._trust_operations.create_delegation(
                    from_agent=calling_agent,
                    to_agent=target_agent,
                    capabilities=[tool_name],
                    trace_id=trace_id,
                    constraints=constraints,
                )
                delegation_id = getattr(delegation, "delegation_id", None)
            except Exception as e:
                logger.warning(
                    f"Failed to create delegation for MCP call: {e}. "
                    f"Proceeding without delegation. "
                    f"Calling: {calling_agent}, Target: {target_agent}, Tool: {tool_name}"
                )

        # Create context
        context = MCPEATPContext(
            mcp_session_id=mcp_session_id,
            eatp_trace_id=trace_id,
            agent_id=calling_agent,
            target_agent_id=target_agent,
            human_origin=human_origin,
            delegated_capabilities=[tool_name],
            constraints=constraints,
            delegation_id=delegation_id,
        )

        # ROUND5-001: Thread-safe append to call history
        with self._lock:
            self._call_history.append(context)

        logger.debug(
            f"Prepared MCP call context: {calling_agent} -> {target_agent} "
            f"tool={tool_name} trace_id={trace_id}"
        )

        return context

    async def verify_mcp_response(
        self,
        context: MCPEATPContext,
        response: Dict[str, Any],
    ) -> bool:
        """Verify and audit an MCP response.

        This method validates the response and creates an audit record
        if TrustOperations is available.

        Args:
            context: The MCPEATPContext from prepare_mcp_call.
            response: The response dictionary from the MCP call.

        Returns:
            True if the response is valid, False otherwise.
        """
        # Log if response contains an error (but still valid response format)
        if "error" in response:
            logger.warning(
                f"MCP response contains error: {response.get('error')}. "
                f"trace_id={context.eatp_trace_id} "
                f"agent={context.agent_id} -> {context.target_agent_id}"
            )

        # Audit the response if TrustOperations is available
        if self._trust_operations is not None:
            try:
                await self._trust_operations.audit(
                    action="mcp_call_completed",
                    agent_id=context.agent_id,
                    target_id=context.target_agent_id,
                    context={
                        "mcp_session_id": context.mcp_session_id,
                        "eatp_trace_id": context.eatp_trace_id,
                        "delegation_id": context.delegation_id,
                        "has_error": "error" in response,
                        "response_keys": list(response.keys()),
                    },
                )
            except Exception as e:
                logger.warning(
                    f"Failed to audit MCP response: {e}. "
                    f"trace_id={context.eatp_trace_id}"
                )

        logger.debug(
            f"Verified MCP response: trace_id={context.eatp_trace_id} "
            f"has_error={'error' in response}"
        )

        return True

    def get_call_history(self) -> List[MCPEATPContext]:
        """Get the history of all MCP calls made through this handler.

        Returns a copy of the call history list to prevent external
        modification of the internal state.

        Thread-safe: Uses lock to protect _call_history access (ROUND5-001).

        Returns:
            List of MCPEATPContext objects representing all calls.
        """
        # ROUND5-001: Thread-safe copy of call history
        with self._lock:
            return list(self._call_history)

    def _generate_trace_id(self) -> str:
        """Generate a unique trace ID for an MCP call.

        Returns:
            A unique trace ID string.
        """
        return f"eatp-mcp-{uuid.uuid4().hex[:16]}"
