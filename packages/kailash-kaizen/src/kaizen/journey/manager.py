"""
Enhanced PathwayManager for Journey Orchestration.

Provides the runtime engine for journey execution, managing sessions,
pathway transitions, context accumulation, state persistence, and hooks integration.

Components:
    - JourneyResponse: Response from journey message processing
    - PathwayManager: Main runtime manager for journey execution
    - JourneyHookEvent: Hook event types for journey lifecycle (REQ-INT-007)

Architecture:
    PathwayManager
    - Session management (start, restore, persist)
    - Pathway execution delegation
    - Global transition handling (intent-based navigation)
    - Context accumulation coordination
    - Return behavior handling
    - Hooks integration for lifecycle events (REQ-INT-007)

Message Processing Flow:
    1. Trigger PRE_SESSION_START hook (if new session)
    2. Check for global transitions (intent detection)
    3. If transition triggered:
       - Trigger PRE_PATHWAY_TRANSITION hook
       - Switch pathway (push to stack)
       - Trigger POST_PATHWAY_TRANSITION hook
    4. Trigger PRE_PATHWAY_EXECUTE hook
    5. Execute current pathway
    6. Trigger POST_PATHWAY_EXECUTE hook
    7. Accumulate outputs
    8. Handle next pathway (if specified and no transition)
    9. Handle return behavior (if applicable)
    10. Persist session state
    11. Return JourneyResponse

Usage:
    from kaizen.journey.manager import PathwayManager, JourneyResponse, JourneyHookEvent
    from kaizen.journey.core import Journey, JourneyConfig

    journey = MyJourney(session_id="user-123")
    manager = PathwayManager(journey.journey_instance, "user-123", JourneyConfig())

    # Register hooks for observability
    manager.register_hook(JourneyHookEvent.PRE_PATHWAY_EXECUTE, my_logging_hook)
    manager.register_hook(JourneyHookEvent.POST_PATHWAY_EXECUTE, my_metrics_hook)

    # Register agents
    manager.register_agent("intake_agent", intake_agent)
    manager.register_agent("booking_agent", booking_agent)

    # Start session and process messages
    session = await manager.start_session()
    response = await manager.process_message("I want to book an appointment")

References:
    - docs/plans/03-journey/05-runtime.md
    - docs/plans/03-journey/06-integration.md
    - TODO-JO-004: Runtime Components
    - TODO-JO-005: Integration Requirements
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import TYPE_CHECKING, Any, Awaitable, Callable, Dict, List, Optional, Type

from kaizen.journey.context import ContextAccumulator
from kaizen.journey.errors import (
    MaxPathwayDepthError,
    PathwayNotFoundError,
    SessionNotStartedError,
)
from kaizen.journey.state import JourneySession, JourneyStateManager
from kaizen.journey.transitions import TransitionResult

if TYPE_CHECKING:
    from kaizen.core.base_agent import BaseAgent
    from kaizen.journey.core import (
        Journey,
        JourneyConfig,
        Pathway,
        PathwayContext,
        PathwayResult,
    )
    from kaizen.journey.intent import IntentDetector
    from kaizen.journey.transitions import IntentTrigger, Transition

logger = logging.getLogger(__name__)


# ============================================================================
# Journey Hook Types (REQ-INT-007)
# ============================================================================


class JourneyHookEvent(Enum):
    """
    Lifecycle events for journey hooks (REQ-INT-007).

    These events allow external systems to observe and extend journey
    execution without modifying core logic. Follows the same pattern
    as kaizen.core.autonomy.hooks for consistency.

    Events:
        PRE_SESSION_START: Before session is created
        POST_SESSION_START: After session is created
        PRE_SESSION_RESTORE: Before session is restored from persistence
        POST_SESSION_RESTORE: After session is restored

        PRE_PATHWAY_EXECUTE: Before pathway execution
        POST_PATHWAY_EXECUTE: After pathway execution (success or failure)

        PRE_PATHWAY_TRANSITION: Before pathway switch
        POST_PATHWAY_TRANSITION: After pathway switch

        PRE_MESSAGE_PROCESS: Before message is processed
        POST_MESSAGE_PROCESS: After message is processed
    """

    # Session lifecycle
    PRE_SESSION_START = "pre_session_start"
    POST_SESSION_START = "post_session_start"
    PRE_SESSION_RESTORE = "pre_session_restore"
    POST_SESSION_RESTORE = "post_session_restore"

    # Pathway execution
    PRE_PATHWAY_EXECUTE = "pre_pathway_execute"
    POST_PATHWAY_EXECUTE = "post_pathway_execute"

    # Pathway transitions
    PRE_PATHWAY_TRANSITION = "pre_pathway_transition"
    POST_PATHWAY_TRANSITION = "post_pathway_transition"

    # Message processing
    PRE_MESSAGE_PROCESS = "pre_message_process"
    POST_MESSAGE_PROCESS = "post_message_process"


@dataclass
class JourneyHookContext:
    """
    Context passed to journey hook handlers.

    Contains event information, session state, and event-specific data.

    Attributes:
        event_type: Type of lifecycle event
        session_id: Session identifier
        pathway_id: Current pathway ID (may be None for session events)
        timestamp: Event timestamp
        data: Event-specific data
        metadata: Additional metadata
    """

    event_type: JourneyHookEvent
    session_id: str
    pathway_id: Optional[str]
    timestamp: float
    data: Dict[str, Any]
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class JourneyHookResult:
    """
    Result returned by journey hook handlers.

    Attributes:
        success: Whether hook executed successfully
        data: Optional data returned by hook
        error: Error message if failed
        duration_ms: Execution duration in milliseconds
    """

    success: bool
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    duration_ms: float = 0.0


# Type alias for hook handlers
JourneyHookHandler = Callable[[JourneyHookContext], Awaitable[JourneyHookResult]]


# ============================================================================
# JourneyResponse (REQ-PM-001)
# ============================================================================


@dataclass
class JourneyResponse:
    """
    Response from journey message processing.

    Contains the response message, current pathway state, transition metadata,
    and accumulated context for the client.

    Attributes:
        message: Assistant response message
        pathway_id: Current pathway ID after processing
        pathway_changed: Whether pathway changed during this message
        accumulated_context: Current accumulated context
        metadata: Additional metadata (pathway_stack, transition info, etc.)

    Example:
        >>> response = await manager.process_message("Hello")
        >>> print(response.message)
        "Welcome! How can I help you today?"
        >>> print(response.pathway_id)
        "intake"
        >>> print(response.pathway_changed)
        False
    """

    message: str
    pathway_id: str
    pathway_changed: bool
    accumulated_context: Dict[str, Any]
    metadata: Dict[str, Any] = field(default_factory=dict)


# ============================================================================
# PathwayManager (REQ-PM-001)
# ============================================================================


class PathwayManager:
    """
    Runtime manager for Journey execution.

    The PathwayManager is the core runtime component that coordinates:
    - Session management (start, restore, persist)
    - Agent registration and lookup
    - Pathway execution delegation
    - Global transition handling (intent-based navigation)
    - Context accumulation coordination
    - Return behavior handling (ReturnToPrevious, ReturnToSpecific)

    Responsibilities:
    - Manage active sessions
    - Execute pathways
    - Handle transitions
    - Accumulate context
    - Persist state

    Attributes:
        journey: Parent Journey instance
        session_id: Unique session identifier
        config: Journey configuration
        _agents: Registered agent instances
        _intent_detector: Intent detection for transitions
        _context_accumulator: Cross-pathway context manager
        _state_manager: Session persistence manager
        _session: Current session state

    Example:
        >>> from kaizen.journey.manager import PathwayManager
        >>> from kaizen.journey.core import JourneyConfig
        >>>
        >>> manager = PathwayManager(journey, "session-123", JourneyConfig())
        >>> manager.register_agent("intake_agent", intake_agent)
        >>> session = await manager.start_session()
        >>> response = await manager.process_message("Hello")
    """

    def __init__(
        self,
        journey: "Journey",
        session_id: str,
        config: "JourneyConfig",
    ):
        """
        Initialize PathwayManager.

        Args:
            journey: Parent Journey instance
            session_id: Unique session identifier
            config: Journey configuration
        """
        self.journey = journey
        self.session_id = session_id
        self.config = config

        # Agent registry
        self._agents: Dict[str, "BaseAgent"] = {}

        # Runtime components (lazy initialization)
        self._intent_detector: Optional["IntentDetector"] = None
        self._context_accumulator = ContextAccumulator(config)
        self._state_manager = JourneyStateManager(config)

        # Session state
        self._session: Optional[JourneySession] = None
        self._pathway_instances: Dict[str, "Pathway"] = {}

        # Hooks registry (REQ-INT-007)
        self._hooks: Dict[JourneyHookEvent, List[JourneyHookHandler]] = {
            event: [] for event in JourneyHookEvent
        }
        self._hook_timeout: float = 5.0  # Default timeout for hooks

    # ========================================================================
    # Agent Management
    # ========================================================================

    def register_agent(self, agent_id: str, agent: "BaseAgent") -> None:
        """
        Register an agent for use in pathways.

        Agents must be registered before pathways can use them.

        Args:
            agent_id: Unique identifier for the agent
            agent: BaseAgent instance to register
        """
        self._agents[agent_id] = agent

    def get_agent(self, agent_id: str) -> Optional["BaseAgent"]:
        """
        Get registered agent by ID.

        Args:
            agent_id: Agent identifier

        Returns:
            BaseAgent instance or None if not registered
        """
        return self._agents.get(agent_id)

    def list_agents(self) -> List[str]:
        """
        List all registered agent IDs.

        Returns:
            List of registered agent IDs
        """
        return list(self._agents.keys())

    # ========================================================================
    # Hooks Management (REQ-INT-007)
    # ========================================================================

    def register_hook(
        self,
        event_type: JourneyHookEvent,
        handler: JourneyHookHandler,
    ) -> None:
        """
        Register a hook handler for a journey lifecycle event.

        Hook handlers are async functions that receive JourneyHookContext
        and return JourneyHookResult. Hooks are executed in registration order.

        Args:
            event_type: Event to trigger hook on
            handler: Async handler function

        Example:
            async def my_logging_hook(context: JourneyHookContext) -> JourneyHookResult:
                logger.info(f"Pathway {context.pathway_id} executing")
                return JourneyHookResult(success=True)

            manager.register_hook(JourneyHookEvent.PRE_PATHWAY_EXECUTE, my_logging_hook)
        """
        self._hooks[event_type].append(handler)
        logger.debug(f"Registered hook for {event_type.value}")

    def unregister_hook(
        self,
        event_type: JourneyHookEvent,
        handler: Optional[JourneyHookHandler] = None,
    ) -> int:
        """
        Unregister hook handler(s) for an event.

        Args:
            event_type: Event type to unregister from
            handler: Specific handler to remove (None = remove all)

        Returns:
            Number of handlers removed
        """
        if handler is None:
            count = len(self._hooks[event_type])
            self._hooks[event_type] = []
            return count

        original_count = len(self._hooks[event_type])
        self._hooks[event_type] = [h for h in self._hooks[event_type] if h != handler]
        return original_count - len(self._hooks[event_type])

    async def _trigger_hooks(
        self,
        event_type: JourneyHookEvent,
        pathway_id: Optional[str] = None,
        data: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> List[JourneyHookResult]:
        """
        Trigger all hooks for an event type.

        Executes hooks in registration order with error isolation.
        Individual hook failures don't affect other hooks or journey execution.

        Args:
            event_type: Event that occurred
            pathway_id: Current pathway ID (if applicable)
            data: Event-specific data
            metadata: Additional metadata

        Returns:
            List of JourneyHookResult from each executed hook
        """
        import asyncio

        handlers = self._hooks.get(event_type, [])
        if not handlers:
            return []

        context = JourneyHookContext(
            event_type=event_type,
            session_id=self.session_id,
            pathway_id=pathway_id,
            timestamp=time.time(),
            data=data or {},
            metadata=metadata or {},
        )

        results = []
        for handler in handlers:
            result = await self._execute_hook(handler, context)
            results.append(result)

        return results

    async def _execute_hook(
        self,
        handler: JourneyHookHandler,
        context: JourneyHookContext,
    ) -> JourneyHookResult:
        """
        Execute a single hook with error handling and timeout.

        Args:
            handler: Hook handler to execute
            context: Hook context

        Returns:
            JourneyHookResult with success/failure status
        """
        import asyncio

        try:
            start_time = time.perf_counter()

            # Execute with timeout
            result = await asyncio.wait_for(
                handler(context),
                timeout=self._hook_timeout,
            )

            result.duration_ms = (time.perf_counter() - start_time) * 1000
            return result

        except asyncio.TimeoutError:
            handler_name = getattr(handler, "__name__", repr(handler))
            error_msg = f"Hook timeout: {handler_name}"
            logger.warning(error_msg)
            return JourneyHookResult(
                success=False,
                error=error_msg,
                duration_ms=self._hook_timeout * 1000,
            )

        except Exception as e:
            handler_name = getattr(handler, "__name__", repr(handler))
            error_msg = f"Hook error ({handler_name}): {str(e)}"
            logger.exception(error_msg)
            return JourneyHookResult(
                success=False,
                error=error_msg,
                duration_ms=0.0,
            )

    def set_hook_timeout(self, timeout_seconds: float) -> None:
        """
        Set timeout for hook execution.

        Args:
            timeout_seconds: Timeout in seconds (default: 5.0)
        """
        self._hook_timeout = timeout_seconds

    # ========================================================================
    # Session Management
    # ========================================================================

    async def start_session(
        self,
        initial_context: Optional[Dict[str, Any]] = None,
    ) -> JourneySession:
        """
        Start a new journey session at entry pathway.

        Creates a new session and persists initial state.
        Triggers PRE_SESSION_START and POST_SESSION_START hooks.

        Args:
            initial_context: Optional initial accumulated context

        Returns:
            JourneySession for tracking session state

        Raises:
            ValueError: If journey has no entry pathway defined
        """
        entry_pathway = self.journey.entry_pathway
        if not entry_pathway:
            raise ValueError("Journey has no entry pathway defined")

        # Trigger PRE_SESSION_START hook (REQ-INT-007)
        await self._trigger_hooks(
            JourneyHookEvent.PRE_SESSION_START,
            pathway_id=entry_pathway,
            data={
                "initial_context": initial_context,
                "entry_pathway": entry_pathway,
            },
        )

        self._session = JourneySession(
            session_id=self.session_id,
            journey_class=type(self.journey),
            current_pathway_id=entry_pathway,
            pathway_stack=[entry_pathway],
            accumulated_context=initial_context or {},
        )

        # Persist initial state
        await self._state_manager.save_session(self._session)

        # Trigger POST_SESSION_START hook (REQ-INT-007)
        await self._trigger_hooks(
            JourneyHookEvent.POST_SESSION_START,
            pathway_id=entry_pathway,
            data={
                "session": {
                    "session_id": self._session.session_id,
                    "current_pathway_id": self._session.current_pathway_id,
                    "accumulated_context": self._session.accumulated_context,
                },
            },
        )

        return self._session

    async def get_session_state(self) -> Optional[JourneySession]:
        """
        Get current session state.

        Returns:
            Current JourneySession or None if not started
        """
        return self._session

    async def restore_session(self, session_id: str) -> Optional[JourneySession]:
        """
        Restore session from persistence.

        Triggers PRE_SESSION_RESTORE and POST_SESSION_RESTORE hooks.

        Args:
            session_id: Session ID to restore

        Returns:
            Restored JourneySession or None if not found
        """
        # Trigger PRE_SESSION_RESTORE hook (REQ-INT-007)
        await self._trigger_hooks(
            JourneyHookEvent.PRE_SESSION_RESTORE,
            pathway_id=None,
            data={"session_id": session_id},
        )

        self._session = await self._state_manager.load_session(session_id)
        if self._session:
            # Restore journey class reference
            self._session.journey_class = type(self.journey)

            # Trigger POST_SESSION_RESTORE hook (REQ-INT-007)
            await self._trigger_hooks(
                JourneyHookEvent.POST_SESSION_RESTORE,
                pathway_id=self._session.current_pathway_id,
                data={
                    "session": {
                        "session_id": self._session.session_id,
                        "current_pathway_id": self._session.current_pathway_id,
                        "accumulated_context": self._session.accumulated_context,
                    },
                    "restored": True,
                },
            )

        return self._session

    # ========================================================================
    # Message Processing (REQ-PM-001)
    # ========================================================================

    async def process_message(self, message: str) -> JourneyResponse:
        """
        Process user message in current pathway.

        Flow (with hooks - REQ-INT-007):
        1. Trigger PRE_MESSAGE_PROCESS hook
        2. Check for global transitions (intent detection)
        3. If transition triggered:
           - Trigger PRE_PATHWAY_TRANSITION hook
           - Switch pathway
           - Trigger POST_PATHWAY_TRANSITION hook
        4. Trigger PRE_PATHWAY_EXECUTE hook
        5. Execute current pathway with message
        6. Trigger POST_PATHWAY_EXECUTE hook
        7. Accumulate outputs
        8. Handle next pathway (if specified)
        9. Handle return behavior (if applicable)
        10. Trigger POST_MESSAGE_PROCESS hook
        11. Return response

        Args:
            message: User input message

        Returns:
            JourneyResponse with result and navigation state

        Raises:
            SessionNotStartedError: If session not started
        """
        if self._session is None:
            raise SessionNotStartedError()

        # Validate message is not empty or whitespace-only
        if not message or not message.strip():
            logger.warning(
                f"Empty or whitespace-only message received for session "
                f"{self._session.session_id}. Returning empty response."
            )
            return JourneyResponse(
                message="",
                pathway_id=self._session.current_pathway_id,
                pathway_changed=False,
                accumulated_context=self._session.accumulated_context.copy(),
            )

        # Trigger PRE_MESSAGE_PROCESS hook (REQ-INT-007)
        await self._trigger_hooks(
            JourneyHookEvent.PRE_MESSAGE_PROCESS,
            pathway_id=self._session.current_pathway_id,
            data={
                "message": message,
                "pathway_id": self._session.current_pathway_id,
            },
        )

        # Add message to history
        self._session.conversation_history.append(
            {
                "role": "user",
                "content": message,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "pathway": self._session.current_pathway_id,
            }
        )

        # Step 1: Check for global transitions
        transition_result = await self._check_transitions(message)

        if transition_result.matched:
            # Trigger PRE_PATHWAY_TRANSITION hook (REQ-INT-007)
            transition = transition_result.transition
            target_pathway = transition.to_pathway if transition else ""

            await self._trigger_hooks(
                JourneyHookEvent.PRE_PATHWAY_TRANSITION,
                pathway_id=self._session.current_pathway_id,
                data={
                    "from_pathway": self._session.current_pathway_id,
                    "to_pathway": target_pathway,
                    "trigger": str(transition.trigger) if transition else None,
                },
            )

            # Step 2: Switch pathway
            preserve_context = True
            if transition and transition.context_update:
                # Context update may indicate clearing context
                preserve_context = "clear" not in transition.context_update

            if target_pathway:
                await self._switch_pathway(target_pathway, preserve_context)

            # Trigger POST_PATHWAY_TRANSITION hook (REQ-INT-007)
            await self._trigger_hooks(
                JourneyHookEvent.POST_PATHWAY_TRANSITION,
                pathway_id=self._session.current_pathway_id,
                data={
                    "from_pathway": (
                        self._session.pathway_stack[-1]
                        if self._session.pathway_stack
                        else None
                    ),
                    "to_pathway": self._session.current_pathway_id,
                    "preserve_context": preserve_context,
                },
            )

        # Trigger PRE_PATHWAY_EXECUTE hook (REQ-INT-007)
        await self._trigger_hooks(
            JourneyHookEvent.PRE_PATHWAY_EXECUTE,
            pathway_id=self._session.current_pathway_id,
            data={
                "message": message,
                "accumulated_context": self._session.accumulated_context.copy(),
            },
        )

        # Step 3: Execute current pathway
        pathway_result = await self._execute_current_pathway(message)

        # Trigger POST_PATHWAY_EXECUTE hook (REQ-INT-007)
        await self._trigger_hooks(
            JourneyHookEvent.POST_PATHWAY_EXECUTE,
            pathway_id=self._session.current_pathway_id,
            data={
                "result": {
                    "outputs": pathway_result.outputs,
                    "accumulated": pathway_result.accumulated,
                    "is_complete": pathway_result.is_complete,
                    "error": pathway_result.error,
                },
            },
        )

        # Step 4: Accumulate outputs
        if pathway_result.accumulated:
            self._context_accumulator.accumulate(
                self._session.accumulated_context,
                pathway_result.accumulated,
                source_pathway=self._session.current_pathway_id,
            )

        # Step 5: Handle next pathway
        pathway_changed = transition_result.matched
        if pathway_result.next_pathway and not transition_result.matched:
            await self._advance_to_pathway(pathway_result.next_pathway)
            pathway_changed = True

        # Step 6: Handle return behavior
        current_pathway = self._get_current_pathway()
        if current_pathway and current_pathway.return_behavior:
            # Only trigger return if pathway execution is complete
            if pathway_result.is_complete and not pathway_result.error:
                await self._handle_return_behavior(current_pathway, pathway_result)
                pathway_changed = True

        # Extract response message using configurable response field
        # Default order: "response" -> "answer" -> "result"
        response_field = (
            getattr(current_pathway, "__response_field__", "response")
            if current_pathway
            else "response"
        )
        response_message = pathway_result.outputs.get(response_field, "")

        # Fallback to alternative keys if primary field not found
        if not response_message:
            # Try alternative keys with logging for debugging
            for alt_key in ["response", "answer", "result"]:
                if alt_key != response_field and alt_key in pathway_result.outputs:
                    response_message = pathway_result.outputs.get(alt_key, "")
                    if response_message:
                        logger.debug(
                            f"Pathway '{self._session.current_pathway_id}' response field "
                            f"'{response_field}' not found, using fallback key '{alt_key}'. "
                            f"Available keys: {list(pathway_result.outputs.keys())}"
                        )
                        break

        # Log warning if no response found at all
        if not response_message and pathway_result.outputs:
            logger.warning(
                f"Pathway '{self._session.current_pathway_id}' did not produce expected "
                f"response field '{response_field}'. Available output keys: {list(pathway_result.outputs.keys())}. "
                f"Set __response_field__ on Pathway class to specify the correct field."
            )

        # Add assistant response to history
        self._session.conversation_history.append(
            {
                "role": "assistant",
                "content": response_message,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "pathway": self._session.current_pathway_id,
            }
        )

        # Update session timestamp
        self._session.updated_at = datetime.now(timezone.utc)

        # Step 7: Persist session state
        await self._state_manager.save_session(self._session)

        # Build metadata
        matched_intent = ""
        if transition_result.matched and transition_result.trigger_result:
            matched_intent = transition_result.trigger_result.get("intent", "")

        response = JourneyResponse(
            message=response_message,
            pathway_id=self._session.current_pathway_id,
            pathway_changed=pathway_changed,
            accumulated_context=self._session.accumulated_context.copy(),
            metadata={
                "pathway_stack": self._session.pathway_stack.copy(),
                "transition_triggered": transition_result.matched,
                "transition_intent": matched_intent,
                "error": pathway_result.error,
            },
        )

        # Trigger POST_MESSAGE_PROCESS hook (REQ-INT-007)
        await self._trigger_hooks(
            JourneyHookEvent.POST_MESSAGE_PROCESS,
            pathway_id=self._session.current_pathway_id,
            data={
                "message": message,
                "response": response_message,
                "pathway_changed": pathway_changed,
                "accumulated_context": self._session.accumulated_context.copy(),
            },
        )

        return response

    # ========================================================================
    # Transition Handling
    # ========================================================================

    async def _check_transitions(self, message: str) -> TransitionResult:
        """
        Check if any global transitions should trigger.

        Evaluates transitions in priority order, returning the first match.

        Args:
            message: User message to check

        Returns:
            TransitionResult with match status and transition details
        """
        transitions = self.journey.transitions

        if not transitions:
            return TransitionResult(matched=False)

        for transition in sorted(transitions, key=lambda t: -t.priority):
            # Check if transition matches current pathway
            if not transition.matches(
                self._session.current_pathway_id,
                message,
                self._session.accumulated_context,
            ):
                continue

            # Check if target pathway exists
            if transition.to_pathway not in self.journey.pathways:
                logger.warning(f"Transition target '{transition.to_pathway}' not found")
                continue

            # Build trigger result metadata
            trigger_result = {}
            if hasattr(transition.trigger, "get_intent_name"):
                trigger_result["intent"] = transition.trigger.get_intent_name()

            return TransitionResult(
                matched=True,
                transition=transition,
                trigger_result=trigger_result,
            )

        return TransitionResult(matched=False)

    async def _switch_pathway(
        self,
        target_pathway: str,
        preserve_context: bool = True,
    ) -> None:
        """
        Switch to a different pathway (push to stack).

        Used for transition-triggered navigation. The current pathway
        is pushed to the stack for potential return.

        Args:
            target_pathway: Pathway ID to switch to
            preserve_context: Whether to preserve accumulated context

        Raises:
            PathwayNotFoundError: If target pathway doesn't exist
            MaxPathwayDepthError: If pathway stack exceeds max depth
        """
        if target_pathway not in self.journey.pathways:
            raise PathwayNotFoundError(
                target_pathway, list(self.journey.pathways.keys())
            )

        # Check max depth
        if len(self._session.pathway_stack) >= self.config.max_pathway_depth:
            raise MaxPathwayDepthError(
                len(self._session.pathway_stack) + 1,
                self.config.max_pathway_depth,
                self._session.pathway_stack,
            )

        # Push current pathway to stack (for return navigation)
        self._session.pathway_stack.append(self._session.current_pathway_id)

        # Switch to target
        self._session.current_pathway_id = target_pathway

        if not preserve_context:
            # Clear accumulated context (rare case)
            self._session.accumulated_context = {}

        logger.info(
            f"Switched pathway: {self._session.pathway_stack[-1]} -> {target_pathway}"
        )

    async def _advance_to_pathway(self, next_pathway: str) -> None:
        """
        Advance to the next pathway in the flow (no stack push).

        Used for natural flow progression (__next__), not transition-triggered.
        Does not modify the pathway stack.

        Args:
            next_pathway: Pathway ID to advance to

        Raises:
            PathwayNotFoundError: If next pathway doesn't exist
        """
        if next_pathway not in self.journey.pathways:
            raise PathwayNotFoundError(next_pathway, list(self.journey.pathways.keys()))

        logger.info(
            f"Advanced pathway: {self._session.current_pathway_id} -> {next_pathway}"
        )
        self._session.current_pathway_id = next_pathway

    # ========================================================================
    # Pathway Execution
    # ========================================================================

    async def _execute_current_pathway(self, message: str) -> "PathwayResult":
        """
        Execute the current pathway with user message.

        Creates pathway context and delegates to pathway.execute().
        Implements error recovery based on config.error_recovery:
        - fail_fast: Re-raise errors immediately
        - graceful: Return error in PathwayResult, don't raise
        - retry: Retry up to max_retries times before failing

        Args:
            message: User message

        Returns:
            PathwayResult with outputs, accumulated fields, and status
        """
        from kaizen.journey.core import PathwayContext, PathwayResult

        pathway = self._get_current_pathway()
        if pathway is None:
            return PathwayResult(
                outputs={},
                accumulated={},
                next_pathway=None,
                is_complete=False,
                error=f"Pathway '{self._session.current_pathway_id}' not found",
            )

        context = PathwayContext(
            session_id=self.session_id,
            pathway_id=self._session.current_pathway_id,
            user_message=message,
            accumulated_context=self._session.accumulated_context.copy(),
            conversation_history=self._session.conversation_history.copy(),
        )

        # Execute with error recovery based on config
        error_recovery = self.config.error_recovery
        max_retries = self.config.max_retries

        if error_recovery == "fail_fast":
            # No error handling - let exceptions propagate
            return await pathway.execute(context)

        elif error_recovery == "retry":
            # Retry up to max_retries times
            last_error = None
            for attempt in range(max_retries):
                try:
                    return await pathway.execute(context)
                except Exception as e:
                    last_error = e
                    logger.warning(
                        f"Pathway execution attempt {attempt + 1}/{max_retries} "
                        f"failed: {e}"
                    )
                    if attempt < max_retries - 1:
                        # Exponential backoff: 0.1s, 0.2s, 0.4s, ...
                        await asyncio.sleep(0.1 * (2**attempt))
            # All retries exhausted
            return PathwayResult(
                outputs={},
                accumulated={},
                next_pathway=None,
                is_complete=False,
                error=f"Pathway execution failed after {max_retries} attempts: {last_error}",
            )

        else:  # graceful (default)
            # Catch exceptions and return as error in result
            try:
                return await pathway.execute(context)
            except Exception as e:
                logger.exception(f"Pathway execution error (graceful recovery): {e}")
                return PathwayResult(
                    outputs={},
                    accumulated={},
                    next_pathway=None,
                    is_complete=False,
                    error=f"Pathway execution error: {str(e)}",
                )

    def _get_current_pathway(self) -> Optional["Pathway"]:
        """
        Get current pathway instance.

        Lazily instantiates pathways on first access.

        Returns:
            Pathway instance or None if session not started or pathway not found
        """
        if self._session is None:
            return None

        pathway_id = self._session.current_pathway_id

        # Check cache
        if pathway_id in self._pathway_instances:
            return self._pathway_instances[pathway_id]

        # Get pathway class and instantiate
        pathway_class = self.journey.pathways.get(pathway_id)
        if pathway_class is None:
            return None

        # Instantiate with self as manager
        pathway = pathway_class(self)
        self._pathway_instances[pathway_id] = pathway

        return pathway

    # ========================================================================
    # Return Behavior Handling
    # ========================================================================

    async def _handle_return_behavior(
        self,
        pathway: "Pathway",
        result: "PathwayResult",
    ) -> None:
        """
        Handle return behavior after pathway completion.

        Supports:
        - ReturnToPrevious: Pop from stack and return
        - ReturnToSpecific: Navigate to specific pathway

        Args:
            pathway: Current pathway (with return_behavior set)
            result: Pathway execution result
        """
        from kaizen.journey.behaviors import ReturnToPrevious, ReturnToSpecific

        behavior = pathway.return_behavior

        if isinstance(behavior, ReturnToPrevious):
            if self._session.pathway_stack:
                # Pop from stack to get previous pathway
                previous = self._session.pathway_stack.pop()
                self._session.current_pathway_id = previous
                logger.info(f"Returned to previous pathway: {previous}")

        elif isinstance(behavior, ReturnToSpecific):
            target = behavior.target_pathway
            if target in self.journey.pathways:
                self._session.current_pathway_id = target
                logger.info(f"Returned to specific pathway: {target}")
            else:
                logger.warning(f"Return target pathway '{target}' not found")

    # ========================================================================
    # Component Access
    # ========================================================================

    @property
    def context_accumulator(self) -> ContextAccumulator:
        """Get the context accumulator."""
        return self._context_accumulator

    @property
    def state_manager(self) -> JourneyStateManager:
        """Get the state manager."""
        return self._state_manager

    def get_intent_detector(self) -> Optional["IntentDetector"]:
        """
        Get or create the intent detector.

        Lazily initializes the intent detector on first access.

        Returns:
            IntentDetector instance
        """
        if self._intent_detector is None:
            from kaizen.journey.intent import IntentDetector

            self._intent_detector = IntentDetector(
                model=self.config.intent_detection_model,
                cache_ttl_seconds=self.config.intent_cache_ttl_seconds,
                confidence_threshold=self.config.intent_confidence_threshold,
            )
        return self._intent_detector


__all__ = [
    # Core classes
    "JourneyResponse",
    "PathwayManager",
    # Hook types (REQ-INT-007)
    "JourneyHookEvent",
    "JourneyHookContext",
    "JourneyHookResult",
    "JourneyHookHandler",
]
