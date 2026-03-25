"""
Nexus Deployment Integration for Journey Orchestration (REQ-INT-005).

Provides JourneyNexusAdapter for deploying journeys as Nexus workflows,
enabling multi-channel access (REST API, CLI, MCP) with unified session
management across all channels.

Components:
    - JourneyNexusAdapter: Converts Journey to Nexus-compatible workflow
    - JourneySessionManager: Session management for multi-user deployments
    - JourneyWorkflow: Nexus workflow wrapper for journey execution

Architecture:
    Journey Orchestration (Layer 5)
    +-- JourneyNexusAdapter
        +-- to_workflow() -> Nexus Workflow
        +-- register_with_nexus()
        +-- JourneySessionManager
            +-- Multi-user session isolation
            +-- Channel-agnostic state

    Nexus Platform (Layer 4)
    +-- REST API: POST /workflows/journey_name
    +-- CLI: nexus run journey_name
    +-- MCP: journey_name tool for AI assistants

Usage:
    from nexus import Nexus
    from kaizen_agents.journey import Journey
    from kaizen_agents.journey.nexus import JourneyNexusAdapter

    # Create journey
    class BookingJourney(Journey):
        __entry_pathway__ = "intake"
        ...

    # Create adapter
    adapter = JourneyNexusAdapter(BookingJourney)

    # Deploy to Nexus
    nexus = Nexus(title="Booking Platform")
    adapter.register_with_nexus(nexus)

    # Now available on all channels:
    # - REST: POST /workflows/booking_journey
    # - CLI: nexus run booking_journey
    # - MCP: booking_journey tool

References:
    - docs/plans/03-journey/06-integration.md
    - TODO-JO-005: Integration Requirements
    - .claude/skills/03-nexus/SKILL.md
"""

import json
import logging
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional, Type

if TYPE_CHECKING:
    from nexus import Nexus

    from kaizen_agents.journey.core import Journey, JourneyConfig, PathwayManager

logger = logging.getLogger(__name__)


# ============================================================================
# Session Manager for Multi-User Deployments
# ============================================================================


@dataclass
class NexusSessionInfo:
    """
    Session information for Nexus deployment.

    Tracks session state, user association, and channel metadata for
    multi-user journey deployments.

    Attributes:
        session_id: Unique session identifier
        user_id: Associated user/client identifier
        channel: Access channel (api, cli, mcp)
        journey_class_name: Name of the journey class
        created_at: Session creation timestamp
        last_accessed: Last access timestamp
        metadata: Additional session metadata
    """

    session_id: str
    user_id: str = ""
    channel: str = "api"
    journey_class_name: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_accessed: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: Dict[str, Any] = field(default_factory=dict)


class JourneySessionManager:
    """
    Thread-safe session manager for multi-user Nexus deployments.

    Manages session lifecycle for multiple concurrent users across different
    channels (API, CLI, MCP). Provides session isolation and state tracking.
    All methods are thread-safe using a threading.Lock.

    Features:
    - Multi-user session isolation
    - Channel-agnostic session state
    - Automatic session cleanup
    - Session lookup by user/session ID
    - Thread-safe for concurrent access

    Attributes:
        _sessions: Dict mapping session_id -> NexusSessionInfo
        _user_sessions: Dict mapping user_id -> list of session_ids
        _journey_managers: Dict mapping session_id -> PathwayManager
        _lock: threading.Lock for thread-safe access

    Example:
        manager = JourneySessionManager()

        # Create session for user
        session_id = manager.create_session(
            user_id="user-123",
            channel="api",
            journey_class_name="BookingJourney"
        )

        # Get or create journey manager
        pathway_manager = manager.get_journey_manager(session_id, journey_class)

        # Cleanup
        manager.cleanup_session(session_id)
    """

    def __init__(self):
        """Initialize session manager with thread-safe lock."""
        self._sessions: Dict[str, NexusSessionInfo] = {}
        self._user_sessions: Dict[str, List[str]] = {}
        self._journey_managers: Dict[str, "PathwayManager"] = {}
        self._lock = threading.Lock()  # Thread-safe access to session data

    def create_session(
        self,
        user_id: str,
        channel: str,
        journey_class_name: str,
        session_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Create a new session (thread-safe).

        Args:
            user_id: User identifier (can be empty for anonymous)
            channel: Access channel (api, cli, mcp)
            journey_class_name: Name of the journey class
            session_id: Optional specific session ID
            metadata: Optional additional metadata

        Returns:
            Session ID
        """
        if session_id is None:
            session_id = str(uuid.uuid4())

        session_info = NexusSessionInfo(
            session_id=session_id,
            user_id=user_id,
            channel=channel,
            journey_class_name=journey_class_name,
            metadata=metadata or {},
        )

        with self._lock:
            self._sessions[session_id] = session_info

            # Track user sessions
            if user_id:
                if user_id not in self._user_sessions:
                    self._user_sessions[user_id] = []
                self._user_sessions[user_id].append(session_id)

        logger.info(f"Created session {session_id} for user {user_id} via {channel}")
        return session_id

    def get_session(self, session_id: str) -> Optional[NexusSessionInfo]:
        """
        Get session information (thread-safe).

        Args:
            session_id: Session identifier

        Returns:
            NexusSessionInfo or None if not found
        """
        with self._lock:
            session = self._sessions.get(session_id)
            if session:
                session.last_accessed = datetime.now(timezone.utc)
            return session

    def get_user_sessions(self, user_id: str) -> List[str]:
        """
        Get all session IDs for a user (thread-safe).

        Args:
            user_id: User identifier

        Returns:
            List of session IDs
        """
        with self._lock:
            return self._user_sessions.get(user_id, []).copy()

    def get_journey_manager(
        self,
        session_id: str,
        journey_class: Type["Journey"],
        config: Optional["JourneyConfig"] = None,
    ) -> Optional["PathwayManager"]:
        """
        Get or create PathwayManager for a session (thread-safe).

        Args:
            session_id: Session identifier
            journey_class: Journey class to instantiate
            config: Optional journey configuration

        Returns:
            PathwayManager instance or None if session doesn't exist
        """
        with self._lock:
            if session_id not in self._sessions:
                return None

            if session_id not in self._journey_managers:
                # Create journey instance and extract manager
                from kaizen_agents.journey.core import JourneyConfig

                journey_instance = journey_class(
                    session_id=session_id,
                    config=config or JourneyConfig(),
                )
                self._journey_managers[session_id] = journey_instance.manager

            return self._journey_managers.get(session_id)

    def set_journey_manager(
        self,
        session_id: str,
        manager: "PathwayManager",
    ) -> None:
        """
        Set PathwayManager for a session (thread-safe).

        Args:
            session_id: Session identifier
            manager: PathwayManager instance
        """
        with self._lock:
            self._journey_managers[session_id] = manager

    def cleanup_session(self, session_id: str) -> bool:
        """
        Clean up a session and associated resources (thread-safe).

        Args:
            session_id: Session identifier

        Returns:
            True if session was cleaned up, False if not found
        """
        with self._lock:
            session = self._sessions.pop(session_id, None)
            if session is None:
                return False

            # Remove from user sessions
            if session.user_id and session.user_id in self._user_sessions:
                self._user_sessions[session.user_id] = [
                    sid
                    for sid in self._user_sessions[session.user_id]
                    if sid != session_id
                ]

            # Remove journey manager
            self._journey_managers.pop(session_id, None)

        logger.info(f"Cleaned up session {session_id}")
        return True

    def cleanup_user_sessions(self, user_id: str) -> int:
        """
        Clean up all sessions for a user (thread-safe).

        Note: Uses thread-safe methods internally. Safe for concurrent access
        even if sessions are modified between get and cleanup operations.

        Args:
            user_id: User identifier

        Returns:
            Number of sessions cleaned up
        """
        session_ids = self.get_user_sessions(user_id)
        count = 0
        for session_id in session_ids:
            if self.cleanup_session(session_id):
                count += 1
        return count


# ============================================================================
# Journey Nexus Adapter (REQ-INT-005)
# ============================================================================


class JourneyNexusAdapter:
    """
    Adapter for deploying Journey as Nexus workflow.

    Converts a Journey class to a Nexus-compatible workflow, enabling
    multi-channel deployment (REST API, CLI, MCP) with unified session
    management.

    Features:
    - Journey to workflow conversion
    - Multi-channel support (API, CLI, MCP)
    - Session management for multi-user deployments
    - Agent registration support
    - Custom hooks for request/response processing

    Attributes:
        journey_class: Journey class to deploy
        workflow_name: Name for the Nexus workflow
        config: Journey configuration
        session_manager: Session manager for multi-user support
        _agents: Registered agents for the journey

    Example:
        from nexus import Nexus
        from kaizen_agents.journey import Journey, Pathway
        from kaizen_agents.journey.nexus import JourneyNexusAdapter

        class BookingJourney(Journey):
            __entry_pathway__ = "intake"

            class IntakePath(Pathway):
                __signature__ = IntakeSignature
                __agents__ = ["intake_agent"]

        # Create adapter
        adapter = JourneyNexusAdapter(
            BookingJourney,
            workflow_name="booking_journey"
        )

        # Register agents
        adapter.register_agent("intake_agent", intake_agent)

        # Deploy to Nexus
        nexus = Nexus(title="Booking Platform")
        adapter.register_with_nexus(nexus)

        # Now available:
        # - POST /workflows/booking_journey
        # - nexus run booking_journey
        # - MCP tool: booking_journey
    """

    def __init__(
        self,
        journey_class: Type["Journey"],
        workflow_name: Optional[str] = None,
        config: Optional["JourneyConfig"] = None,
        description: Optional[str] = None,
    ):
        """
        Initialize adapter.

        Args:
            journey_class: Journey class to deploy
            workflow_name: Optional workflow name (defaults to snake_case class name)
            config: Optional journey configuration
            description: Optional workflow description
        """
        self.journey_class = journey_class
        self.workflow_name = workflow_name or self._to_snake_case(
            journey_class.__name__
        )
        self.config = config
        self.description = description or f"Journey: {journey_class.__name__}"
        self.session_manager = JourneySessionManager()
        self._agents: Dict[str, Any] = {}
        self._pre_process_hooks: List[Callable] = []
        self._post_process_hooks: List[Callable] = []

    def register_agent(self, agent_id: str, agent: Any) -> None:
        """
        Register an agent for the journey.

        Args:
            agent_id: Agent identifier (must match __agents__ in pathways)
            agent: BaseAgent instance
        """
        self._agents[agent_id] = agent
        logger.info(f"Registered agent {agent_id} for journey {self.workflow_name}")

    def add_pre_process_hook(self, hook: Callable) -> None:
        """
        Add pre-processing hook for requests.

        Hook signature: hook(request: dict) -> dict

        Args:
            hook: Callable that receives and returns request dict
        """
        self._pre_process_hooks.append(hook)

    def add_post_process_hook(self, hook: Callable) -> None:
        """
        Add post-processing hook for responses.

        Hook signature: hook(response: dict) -> dict

        Args:
            hook: Callable that receives and returns response dict
        """
        self._post_process_hooks.append(hook)

    def to_workflow(self) -> Dict[str, Any]:
        """
        Convert Journey to Nexus workflow definition.

        Creates a workflow definition that can be registered with Nexus.
        The workflow handles session management and message processing.

        Returns:
            Dict with workflow definition including name, handler, and metadata
        """
        adapter = self

        async def workflow_handler(
            message: str,
            session_id: Optional[str] = None,
            user_id: str = "",
            channel: str = "api",
            initial_context: Optional[Dict[str, Any]] = None,
        ) -> Dict[str, Any]:
            """
            Workflow handler for Nexus integration.

            Args:
                message: User message to process
                session_id: Optional existing session ID
                user_id: User identifier
                channel: Access channel (api, cli, mcp)
                initial_context: Optional initial context for new sessions

            Returns:
                Dict with response, session_id, pathway_id, and metadata
            """
            # Pre-process hooks
            request = {
                "message": message,
                "session_id": session_id,
                "user_id": user_id,
                "channel": channel,
                "initial_context": initial_context,
            }

            for hook in adapter._pre_process_hooks:
                request = hook(request)

            message = request["message"]
            session_id = request.get("session_id")
            user_id = request.get("user_id", "")
            channel = request.get("channel", "api")
            initial_context = request.get("initial_context")

            # Create or restore session
            is_new_session = False
            if session_id is None:
                session_id = adapter.session_manager.create_session(
                    user_id=user_id,
                    channel=channel,
                    journey_class_name=adapter.journey_class.__name__,
                )
                is_new_session = True

            # Get or create journey manager
            manager = adapter.session_manager.get_journey_manager(
                session_id,
                adapter.journey_class,
                adapter.config,
            )

            if manager is None:
                return {
                    "error": f"Session {session_id} not found",
                    "session_id": session_id,
                }

            # Register agents with manager
            for agent_id, agent in adapter._agents.items():
                manager.register_agent(agent_id, agent)

            # Start session if new
            if is_new_session:
                await manager.start_session(initial_context=initial_context)

            # Process message
            try:
                response = await manager.process_message(message)

                result = {
                    "response": response.message,
                    "session_id": session_id,
                    "pathway_id": response.pathway_id,
                    "pathway_changed": response.pathway_changed,
                    "accumulated_context": response.accumulated_context,
                    "metadata": response.metadata,
                }

            except Exception as e:
                logger.exception(f"Journey processing error: {e}")
                result = {
                    "error": str(e),
                    "session_id": session_id,
                }

            # Post-process hooks
            for hook in adapter._post_process_hooks:
                result = hook(result)

            return result

        return {
            "name": self.workflow_name,
            "handler": workflow_handler,
            "description": self.description,
            "input_schema": {
                "type": "object",
                "properties": {
                    "message": {
                        "type": "string",
                        "description": "User message to process",
                    },
                    "session_id": {
                        "type": "string",
                        "description": "Optional session ID for continuing a conversation",
                    },
                    "user_id": {
                        "type": "string",
                        "description": "User identifier",
                    },
                    "channel": {
                        "type": "string",
                        "enum": ["api", "cli", "mcp"],
                        "description": "Access channel",
                    },
                    "initial_context": {
                        "type": "object",
                        "description": "Optional initial context for new sessions",
                    },
                },
                "required": ["message"],
            },
            "output_schema": {
                "type": "object",
                "properties": {
                    "response": {
                        "type": "string",
                        "description": "Agent response message",
                    },
                    "session_id": {
                        "type": "string",
                        "description": "Session identifier",
                    },
                    "pathway_id": {
                        "type": "string",
                        "description": "Current pathway ID",
                    },
                    "pathway_changed": {
                        "type": "boolean",
                        "description": "Whether pathway changed during processing",
                    },
                    "accumulated_context": {
                        "type": "object",
                        "description": "Accumulated context from the journey",
                    },
                    "metadata": {
                        "type": "object",
                        "description": "Additional response metadata",
                    },
                },
            },
        }

    def register_with_nexus(self, nexus: "Nexus") -> None:
        """
        Register journey workflow with Nexus platform.

        Creates a proper Kailash Workflow that wraps the journey handler,
        then registers it with Nexus.

        Args:
            nexus: Nexus instance to register with

        Example:
            nexus = Nexus(title="My Platform")
            adapter.register_with_nexus(nexus)
            nexus.run(port=8000)
        """
        from kailash.workflow.builder import WorkflowBuilder

        # Create a workflow using WorkflowBuilder
        # We use AsyncPythonCodeNode to wrap the async handler
        workflow_def = self.to_workflow()
        handler = workflow_def["handler"]

        # Store the handler and adapter reference for the workflow code to access
        # We need to make these accessible within the PythonCodeNode execution context
        self._workflow_handler = handler

        # Build a workflow that delegates to our handler
        # The workflow accepts inputs and passes them to the journey handler
        builder = WorkflowBuilder()

        # Use AsyncPythonCodeNode to execute the journey handler
        # The handler is stored on the adapter instance which is accessible via closure
        adapter_ref = self

        # Create the workflow code that calls our async handler
        code = """
import asyncio

# Extract inputs from workflow execution
message = inputs.get("message", "")
session_id = inputs.get("session_id")
user_id = inputs.get("user_id", "")
channel = inputs.get("channel", "api")
initial_context = inputs.get("initial_context")

# Get the handler from the adapter (passed via global context)
handler = globals().get("_journey_handler")
if handler is None:
    result = {"error": "Journey handler not available"}
else:
    # Call the async handler
    result = await handler(
        message=message,
        session_id=session_id,
        user_id=user_id,
        channel=channel,
        initial_context=initial_context,
    )
"""

        builder.add_node(
            "AsyncPythonCodeNode",
            "journey_executor",
            {
                "code": code,
                "description": workflow_def["description"],
            },
        )

        workflow = builder.build()

        # Store metadata for Nexus
        workflow.metadata["description"] = workflow_def["description"]
        workflow.metadata["input_schema"] = workflow_def["input_schema"]
        workflow.metadata["output_schema"] = workflow_def["output_schema"]
        workflow.metadata["_journey_handler"] = handler

        # Register with Nexus
        nexus.register(self.workflow_name, workflow)

        logger.info(f"Registered journey {self.workflow_name} with Nexus")

    def create_rest_endpoint(self) -> Dict[str, Any]:
        """
        Create REST API endpoint definition.

        Returns:
            Dict with endpoint definition for manual registration

        Example:
            endpoint = adapter.create_rest_endpoint()
            # Returns: {
            #     "path": "/journeys/booking_journey",
            #     "method": "POST",
            #     "handler": <async function>,
            #     "request_model": {...},
            #     "response_model": {...}
            # }
        """
        workflow_def = self.to_workflow()

        return {
            "path": f"/journeys/{self.workflow_name}",
            "method": "POST",
            "handler": workflow_def["handler"],
            "request_model": workflow_def["input_schema"],
            "response_model": workflow_def["output_schema"],
            "description": self.description,
        }

    def create_cli_command(self) -> Dict[str, Any]:
        """
        Create CLI command definition.

        Returns:
            Dict with CLI command definition

        Example:
            cmd = adapter.create_cli_command()
            # Returns: {
            #     "name": "booking_journey",
            #     "handler": <async function>,
            #     "args": [...],
            #     "description": "..."
            # }
        """
        workflow_def = self.to_workflow()

        return {
            "name": self.workflow_name,
            "handler": workflow_def["handler"],
            "args": [
                {"name": "message", "type": "string", "required": True},
                {"name": "--session-id", "type": "string", "required": False},
                {"name": "--user-id", "type": "string", "required": False},
            ],
            "description": self.description,
        }

    def create_mcp_tool(self) -> Dict[str, Any]:
        """
        Create MCP tool definition.

        Returns:
            Dict with MCP tool definition for AI assistant integration

        Example:
            tool = adapter.create_mcp_tool()
            # Returns: {
            #     "name": "booking_journey",
            #     "description": "...",
            #     "inputSchema": {...},
            #     "handler": <async function>
            # }
        """
        workflow_def = self.to_workflow()

        return {
            "name": self.workflow_name,
            "description": self.description,
            "inputSchema": workflow_def["input_schema"],
            "handler": workflow_def["handler"],
        }

    @staticmethod
    def _to_snake_case(name: str) -> str:
        """Convert CamelCase to snake_case."""
        import re

        s1 = re.sub("(.)([A-Z][a-z]+)", r"\1_\2", name)
        return re.sub("([a-z0-9])([A-Z])", r"\1_\2", s1).lower()


# ============================================================================
# Convenience Function
# ============================================================================


def deploy_journey_to_nexus(
    journey_class: Type["Journey"],
    nexus: "Nexus",
    agents: Optional[Dict[str, Any]] = None,
    workflow_name: Optional[str] = None,
    config: Optional["JourneyConfig"] = None,
) -> JourneyNexusAdapter:
    """
    Convenience function to deploy a Journey to Nexus.

    Creates adapter, registers agents, and registers with Nexus in one call.

    Args:
        journey_class: Journey class to deploy
        nexus: Nexus instance
        agents: Dict of agent_id -> agent instance
        workflow_name: Optional workflow name
        config: Optional journey configuration

    Returns:
        JourneyNexusAdapter instance (for further customization)

    Example:
        from nexus import Nexus
        from kaizen_agents.journey.nexus import deploy_journey_to_nexus

        nexus = Nexus(title="My Platform")
        adapter = deploy_journey_to_nexus(
            BookingJourney,
            nexus,
            agents={
                "intake_agent": intake_agent,
                "booking_agent": booking_agent,
            }
        )
        nexus.run(port=8000)
    """
    adapter = JourneyNexusAdapter(
        journey_class=journey_class,
        workflow_name=workflow_name,
        config=config,
    )

    # Register agents
    if agents:
        for agent_id, agent in agents.items():
            adapter.register_agent(agent_id, agent)

    # Register with Nexus
    adapter.register_with_nexus(nexus)

    return adapter


__all__ = [
    "NexusSessionInfo",
    "JourneySessionManager",
    "JourneyNexusAdapter",
    "deploy_journey_to_nexus",
]
