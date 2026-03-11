"""
Journey and Pathway Core Classes

Defines the declarative Journey and Pathway classes that form the foundation
of Layer 5 Journey Orchestration. These classes enable multi-phase user journey
definitions with nested pathway classes.

Architecture:
    Journey (JourneyMeta metaclass)
    - Extracts nested Pathway classes automatically
    - Validates entry pathway exists
    - Manages global transitions

    Pathway (PathwayMeta metaclass)
    - Extracts signature, agents, pipeline config
    - Supports various pipeline types (sequential, parallel, router, etc.)
    - Accumulates context across pathways

Runtime Components (manager.py, context.py, state.py):
    - PathwayManager: Enhanced runtime manager with session/context management
    - ContextAccumulator: Field-level merge strategies for cross-pathway state
    - JourneyStateManager: Pluggable session persistence backends

Usage:
    class BookingJourney(Journey):
        __entry_pathway__ = "intake"
        __transitions__ = [
            Transition(trigger=IntentTrigger(["help"]), to_pathway="faq")
        ]

        class IntakePath(Pathway):
            __signature__ = IntakeSignature
            __agents__ = ["intake_agent"]
            __next__ = "booking"

        class BookingPath(Pathway):
            __signature__ = BookingSignature
            __agents__ = ["booking_agent"]
            __accumulate__ = ["customer_name", "booking_date"]

    journey = BookingJourney(session_id="session-123")
    session = await journey.start()
"""

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, ClassVar, Dict, List, Optional, Type

if TYPE_CHECKING:
    from kaizen.core.base_agent import BaseAgent
    from kaizen.orchestration.pipeline import Pipeline
    from kaizen.signatures.core import Signature

from kaizen.journey.behaviors import ReturnBehavior

# ============================================================================
# Data Classes (REQ-JC-005)
# ============================================================================


@dataclass
class JourneyConfig:
    """
    Configuration for Journey execution.

    Controls intent detection, pathway execution, context accumulation,
    and error handling behavior.

    Attributes:
        intent_detection_model: Model for intent classification (default: gpt-4o-mini)
        intent_confidence_threshold: Minimum confidence for intent match (0-1)
        intent_cache_ttl_seconds: Cache TTL for intent results
        max_pathway_depth: Maximum pathway navigation depth (prevents loops)
        pathway_timeout_seconds: Timeout for pathway execution
        max_context_size_bytes: Maximum accumulated context size
        context_persistence: Storage backend ("memory", "dataflow", "redis")
        error_recovery: Error handling strategy ("fail_fast", "graceful", "retry")
        max_retries: Maximum retry attempts for error recovery
    """

    # Intent detection
    intent_detection_model: str = "gpt-4o-mini"
    intent_confidence_threshold: float = 0.7
    intent_cache_ttl_seconds: int = 300

    # Pathway execution
    max_pathway_depth: int = 10
    pathway_timeout_seconds: float = 60.0

    # Context accumulation
    max_context_size_bytes: int = 1024 * 1024  # 1MB
    context_persistence: str = "memory"  # "memory", "dataflow", "redis"

    # Error handling
    error_recovery: str = "graceful"  # "fail_fast", "graceful", "retry"
    max_retries: int = 3


@dataclass
class PathwayContext:
    """
    Execution context for a pathway.

    Contains all the information needed to execute a pathway, including
    session state, user input, accumulated context, and conversation history.

    Attributes:
        session_id: Unique identifier for the journey session
        pathway_id: Current pathway being executed
        user_message: Current user input message
        accumulated_context: Context accumulated from previous pathways
        conversation_history: List of past conversation turns
    """

    session_id: str
    pathway_id: str
    user_message: str
    accumulated_context: Dict[str, Any]
    conversation_history: List[Dict[str, Any]]

    def to_input_dict(self) -> Dict[str, Any]:
        """
        Convert context to pipeline input dictionary.

        Returns:
            Dict with message, context, and history keys for pipeline execution.
        """
        return {
            "message": self.user_message,
            "context": self.accumulated_context,
            "history": self.conversation_history,
        }


@dataclass
class PathwayResult:
    """
    Result from pathway execution.

    Contains execution outputs, accumulated fields, navigation hints,
    and completion status.

    Attributes:
        outputs: Raw outputs from pipeline execution
        accumulated: Fields extracted for accumulation
        next_pathway: Suggested next pathway (if any)
        is_complete: Whether execution completed successfully
        error: Error message if execution failed
    """

    outputs: Dict[str, Any]
    accumulated: Dict[str, Any]
    next_pathway: Optional[str]
    is_complete: bool
    error: Optional[str] = None


# ============================================================================
# PathwayMeta Metaclass (REQ-JC-003)
# ============================================================================


class PathwayMeta(type):
    """
    Metaclass for processing Pathway class definitions.

    Automatically extracts pathway configuration from class attributes:
    - __signature__: Signature class for I/O contract
    - __agents__: List of agent IDs to execute
    - __pipeline__: Pipeline type (sequential, parallel, router, etc.)
    - __pipeline_config__: Optional dict with pattern-specific settings (REQ-INT-002)
    - __accumulate__: Fields to preserve across pathways
    - __next__: Default next pathway
    - __guidelines__: Pathway-specific behavioral guidelines
    - __return_behavior__: Navigation behavior after completion
    """

    def __new__(
        mcs, name: str, bases: tuple, namespace: Dict[str, Any], **kwargs
    ) -> type:
        """Process Pathway class definition."""
        # Skip processing for the base Pathway class itself
        if name == "Pathway":
            return super().__new__(mcs, name, bases, namespace)

        # Extract pathway configuration from class attributes
        namespace["_signature"] = namespace.get("__signature__")
        namespace["_agents"] = namespace.get("__agents__", [])
        namespace["_pipeline"] = namespace.get("__pipeline__", "sequential")
        namespace["_pipeline_config"] = namespace.get(
            "__pipeline_config__", {}
        )  # REQ-INT-002
        namespace["_accumulate"] = namespace.get("__accumulate__", [])
        namespace["_next"] = namespace.get("__next__")
        namespace["_guidelines"] = namespace.get("__guidelines__", [])
        namespace["_return_behavior"] = namespace.get("__return_behavior__")

        # Validate signature if provided
        sig = namespace["_signature"]
        if sig is not None:
            # Check if it's a class with signature attributes
            # (either _signature_inputs from SignatureMeta or is a Signature subclass)
            is_signature_class = isinstance(sig, type) and (
                hasattr(sig, "_signature_inputs") or hasattr(sig, "_signature_outputs")
            )

            if not is_signature_class:
                raise TypeError(
                    f"__signature__ must be a Signature class, got {type(sig).__name__}"
                )

        return super().__new__(mcs, name, bases, namespace)


# ============================================================================
# Pathway Base Class (REQ-JC-004)
# ============================================================================


class Pathway(metaclass=PathwayMeta):
    """
    A phase in a user journey.

    Pathways define:
    - Signature: I/O contract for this phase
    - Agents: Which agents handle this pathway
    - Pipeline: How agents are coordinated (sequential, parallel, etc.)
    - Accumulate: Which output fields to preserve across pathways
    - Next: Default next pathway (if no transition triggered)
    - Guidelines: Pathway-specific guidelines (merged with signature)
    - ReturnBehavior: Navigation behavior after completion

    Example:
        class IntakePath(Pathway):
            \"\"\"Initial intake pathway for customer information.\"\"\"
            __signature__ = IntakeSignature
            __agents__ = ["intake_agent"]
            __pipeline__ = "sequential"
            __accumulate__ = ["customer_name", "customer_email"]
            __next__ = "booking"
            __guidelines__ = ["Be welcoming", "Collect name first"]

        class FAQPath(Pathway):
            \"\"\"FAQ detour that returns to previous pathway.\"\"\"
            __signature__ = FAQSignature
            __agents__ = ["faq_agent"]
            __return_behavior__ = ReturnToPrevious()
    """

    # Class variables (set by PathwayMeta)
    _signature: ClassVar[Optional[Type["Signature"]]] = None
    _agents: ClassVar[List[str]] = []
    _pipeline: ClassVar[str] = "sequential"
    _pipeline_config: ClassVar[Dict[str, Any]] = (
        {}
    )  # REQ-INT-002: Pattern-specific config
    _accumulate: ClassVar[List[str]] = []
    _next: ClassVar[Optional[str]] = None
    _guidelines: ClassVar[List[str]] = []
    _return_behavior: ClassVar[Optional[ReturnBehavior]] = None

    def __init__(self, manager: "PathwayManager"):
        """
        Initialize pathway instance.

        Args:
            manager: PathwayManager that owns this pathway instance
        """
        self.manager = manager
        self._signature_instance: Optional["Signature"] = None
        self._pipeline_instance: Optional["Pipeline"] = None

    @property
    def signature(self) -> Optional["Signature"]:
        """
        Get instantiated signature for this pathway.

        Lazily instantiates the signature and merges pathway guidelines
        with any signature-level guidelines. Implements REQ-INT-001.

        Guideline Merge Strategy:
        - Signature guidelines come first (base behavior)
        - Pathway guidelines are appended (pathway-specific behavior)
        - Result: Combined list of guidelines for agent prompt generation

        Returns:
            Signature instance with merged guidelines, or None if no signature.
        """
        if self._signature_instance is None and self._signature is not None:
            sig = self._signature()

            # Merge pathway guidelines with signature guidelines (REQ-INT-001)
            if self._guidelines:
                if hasattr(sig, "with_guidelines"):
                    # Use the signature's with_guidelines method for proper merging
                    sig = sig.with_guidelines(self._guidelines)
                else:
                    # Fallback: manually merge guidelines if method not available
                    existing_guidelines = getattr(sig, "_guidelines", [])
                    if hasattr(sig, "__class__") and hasattr(
                        sig.__class__, "__guidelines__"
                    ):
                        existing_guidelines = list(sig.__class__.__guidelines__)
                    sig._guidelines = existing_guidelines + list(self._guidelines)

            self._signature_instance = sig
        return self._signature_instance

    @property
    def guidelines(self) -> List[str]:
        """
        Get merged guidelines from signature and pathway.

        Returns:
            Combined list of guidelines (signature + pathway).
        """
        result = []

        # Get signature guidelines
        if self._signature is not None:
            sig_guidelines = getattr(self._signature, "__guidelines__", [])
            result.extend(sig_guidelines)

        # Add pathway guidelines
        result.extend(self._guidelines)

        return result

    @property
    def agent_ids(self) -> List[str]:
        """Get list of agent IDs for this pathway."""
        return self._agents.copy()

    @property
    def pipeline_type(self) -> str:
        """Get pipeline type for agent coordination."""
        return self._pipeline

    @property
    def accumulate_fields(self) -> List[str]:
        """Get list of fields to accumulate from results."""
        return self._accumulate.copy()

    @property
    def next_pathway(self) -> Optional[str]:
        """Get default next pathway ID."""
        return self._next

    @property
    def return_behavior(self) -> Optional[ReturnBehavior]:
        """Get return behavior for navigation after completion."""
        return self._return_behavior

    @property
    def pipeline_config(self) -> Dict[str, Any]:
        """
        Get pipeline-specific configuration (REQ-INT-002).

        Returns:
            Dict with pattern-specific settings (e.g., routing_strategy, top_k, etc.)
        """
        return self._pipeline_config.copy()

    def validate_outputs(self, result: Dict[str, Any]) -> Dict[str, bool]:
        """
        Validate outputs against signature contract (REQ-INT-001).

        Checks that all required output fields from the signature are present
        in the result with non-None values.

        Args:
            result: Pipeline execution result to validate

        Returns:
            Dict mapping field_name -> is_valid for each output field

        Example:
            >>> pathway = MyPathway(manager)
            >>> result = {"response": "Hello", "confidence": None}
            >>> pathway.validate_outputs(result)
            {'response': True, 'confidence': False}
        """
        validation = {}

        if self._signature is None:
            return validation

        # Get signature output fields
        sig_outputs = getattr(self._signature, "_signature_outputs", {})
        for field_name in sig_outputs:
            # Field is valid if present and not None
            is_valid = field_name in result and result.get(field_name) is not None
            validation[field_name] = is_valid

        return validation

    def get_missing_outputs(self, result: Dict[str, Any]) -> List[str]:
        """
        Get list of missing required output fields (REQ-INT-001).

        Args:
            result: Pipeline execution result to check

        Returns:
            List of field names that are missing or None
        """
        validation = self.validate_outputs(result)
        return [field for field, is_valid in validation.items() if not is_valid]

    async def execute(self, context: PathwayContext) -> PathwayResult:
        """
        Execute pathway with given context.

        Resolves agents, builds pipeline, prepares inputs from context,
        executes the pipeline, and extracts accumulated fields.

        Args:
            context: Execution context with session state and user input

        Returns:
            PathwayResult with outputs, accumulated fields, and status
        """
        try:
            # Resolve agent IDs to agent instances
            agents = self._resolve_agents()

            # Build pipeline from agents
            pipeline = self._build_pipeline(agents)

            # Prepare input from context
            inputs = context.to_input_dict()

            # Add signature fields from accumulated context
            if self.signature is not None:
                # Get signature input field names
                sig_inputs = getattr(self.signature, "_signature_inputs", {})
                for field_name in sig_inputs:
                    if field_name in context.accumulated_context:
                        inputs[field_name] = context.accumulated_context[field_name]

            # Execute pipeline
            if hasattr(pipeline, "execute"):
                result = await pipeline.execute(inputs)
            elif hasattr(pipeline, "run"):
                # Synchronous pipeline - wrap in dict if needed
                result = pipeline.run(**inputs)
                if not isinstance(result, dict):
                    result = {"result": result}
            else:
                raise ValueError("Pipeline must have execute() or run() method")

            # Extract accumulated fields
            accumulated = self._extract_accumulated_fields(result)

            return PathwayResult(
                outputs=result,
                accumulated=accumulated,
                next_pathway=self._next,
                is_complete=True,
            )

        except Exception as e:
            return PathwayResult(
                outputs={},
                accumulated={},
                next_pathway=None,
                is_complete=False,
                error=str(e),
            )

    def _resolve_agents(self) -> List["BaseAgent"]:
        """
        Resolve agent IDs to agent instances from registry.

        Returns:
            List of BaseAgent instances

        Raises:
            ValueError: If an agent ID is not registered
        """
        agents = []
        for agent_id in self._agents:
            agent = self.manager.get_agent(agent_id)
            if agent is None:
                raise ValueError(f"Agent '{agent_id}' not registered")
            agents.append(agent)
        return agents

    def _build_pipeline(self, agents: List["BaseAgent"]) -> "Pipeline":
        """
        Build pipeline from agents based on pipeline type (REQ-INT-002).

        Supports all pipeline patterns with optional configuration via
        __pipeline_config__ class attribute:
        - sequential: Linear agent execution
        - parallel: Concurrent agent execution
        - router: Intelligent task routing (A2A semantic matching)
        - ensemble: Multi-perspective collaboration
        - supervisor_worker: Hierarchical delegation

        Args:
            agents: List of agent instances

        Returns:
            Pipeline instance configured for execution

        Raises:
            ValueError: If no agents provided or unknown pipeline type

        Example:
            class MyPathway(Pathway):
                __pipeline__ = "router"
                __pipeline_config__ = {
                    "routing_strategy": "semantic",
                    "error_handling": "graceful"
                }
        """
        from kaizen.orchestration.pipeline import Pipeline

        if len(agents) == 0:
            raise ValueError("Pathway requires at least one agent")

        if len(agents) == 1:
            # Single agent, wrap in minimal sequential pipeline
            return Pipeline.sequential(agents)

        # Get pipeline-specific config
        config = self._pipeline_config.copy()

        # Build pipeline based on type with optional config
        pipeline_type = self._pipeline

        if pipeline_type == "sequential":
            return Pipeline.sequential(agents)

        elif pipeline_type == "parallel":
            return Pipeline.parallel(
                agents=agents,
                aggregator=config.get("aggregator"),
                max_workers=config.get("max_workers", 10),
                error_handling=config.get("error_handling", "graceful"),
                timeout=config.get("timeout"),
            )

        elif pipeline_type == "router":
            return Pipeline.router(
                agents=agents,
                routing_strategy=config.get("routing_strategy", "semantic"),
                error_handling=config.get("error_handling", "graceful"),
            )

        elif pipeline_type == "ensemble":
            # Last agent is synthesizer by default, or use config
            synthesizer = config.get("synthesizer", agents[-1])
            agent_pool = config.get(
                "agents", agents[:-1] if len(agents) > 1 else agents
            )
            return Pipeline.ensemble(
                agents=agent_pool,
                synthesizer=synthesizer,
                discovery_mode=config.get("discovery_mode", "a2a"),
                top_k=config.get("top_k", 3),
                error_handling=config.get("error_handling", "graceful"),
            )

        elif pipeline_type == "supervisor_worker":
            return Pipeline.supervisor_worker(
                supervisor=agents[0],
                workers=agents[1:],
                shared_memory=config.get("shared_memory"),
                selection_mode=config.get("selection_mode", "semantic"),
            )

        else:
            raise ValueError(f"Unknown pipeline type: {pipeline_type}")

    def _extract_accumulated_fields(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract fields to accumulate from result.

        Only extracts fields that are explicitly listed in __accumulate__
        and have non-None values in the result.

        Args:
            result: Pipeline execution result

        Returns:
            Dict of field_name -> value for accumulation
        """
        return {
            field_name: result.get(field_name)
            for field_name in self._accumulate
            if field_name in result and result.get(field_name) is not None
        }


# ============================================================================
# JourneyMeta Metaclass (REQ-JC-001)
# ============================================================================


class JourneyMeta(type):
    """
    Metaclass for processing Journey class definitions.

    Automatically extracts:
    - Nested Pathway classes (converted to snake_case IDs)
    - Entry pathway reference
    - Global transitions

    Validates that entry pathway exists in extracted pathways.
    """

    def __new__(
        mcs, name: str, bases: tuple, namespace: Dict[str, Any], **kwargs
    ) -> type:
        """Process Journey class definition."""
        # Skip processing for the base Journey class itself
        if name == "Journey":
            return super().__new__(mcs, name, bases, namespace)

        # Extract nested Pathway classes
        pathways: Dict[str, Type[Pathway]] = {}
        for attr_name, attr_value in list(namespace.items()):
            if isinstance(attr_value, type) and issubclass(attr_value, Pathway):
                if attr_value is not Pathway:  # Skip base Pathway class
                    pathway_id = mcs._to_pathway_id(attr_name)
                    pathways[pathway_id] = attr_value

        # Validate entry pathway
        entry_pathway = namespace.get("__entry_pathway__")
        if pathways and entry_pathway and entry_pathway not in pathways:
            available = list(pathways.keys())
            raise ValueError(
                f"Entry pathway '{entry_pathway}' not found. "
                f"Available pathways: {available}"
            )

        # Default to first pathway if not specified
        if pathways and not entry_pathway:
            entry_pathway = list(pathways.keys())[0]

        # Store as class variables
        namespace["_pathways"] = pathways
        namespace["_entry_pathway"] = entry_pathway
        namespace["_transitions"] = namespace.get("__transitions__", [])

        return super().__new__(mcs, name, bases, namespace)

    @staticmethod
    def _to_pathway_id(class_name: str) -> str:
        """
        Convert PathwayClassName to pathway_id (snake_case).

        Removes 'Path' or 'Pathway' suffix and converts CamelCase to snake_case.

        Args:
            class_name: PascalCase class name (e.g., "IntakePath", "UserRegistrationPathway")

        Returns:
            snake_case pathway ID (e.g., "intake", "user_registration")

        Examples:
            IntakePath -> intake
            IntakePathway -> intake
            FAQPath -> faq
            UserRegistrationPath -> user_registration
        """
        # Remove 'Path' or 'Pathway' suffix
        name = class_name
        for suffix in ("Pathway", "Path"):
            if name.endswith(suffix):
                name = name[: -len(suffix)]
                break

        # Convert CamelCase to snake_case
        # Insert underscore before uppercase letters that follow lowercase
        s1 = re.sub("(.)([A-Z][a-z]+)", r"\1_\2", name)
        # Insert underscore before uppercase letters that follow lowercase/digits
        return re.sub("([a-z0-9])([A-Z])", r"\1_\2", s1).lower()


# ============================================================================
# Runtime Components (Re-exported from manager.py and state.py)
# ============================================================================

# Import enhanced PathwayManager from manager.py
# This provides full session management, context accumulation, and state persistence
from kaizen.journey.manager import JourneyResponse as EnhancedJourneyResponse
from kaizen.journey.manager import PathwayManager as EnhancedPathwayManager
from kaizen.journey.state import JourneySession


# Alias for backward compatibility - the placeholder PathwayManager in core.py
# is now replaced by the enhanced version from manager.py
class PathwayManager(EnhancedPathwayManager):
    """
    Runtime manager for Journey execution.

    This class is re-exported from kaizen.journey.manager for backward
    compatibility. See manager.py for full documentation.

    Features:
    - Session management (start, restore, persist)
    - Agent registration and lookup
    - Pathway execution delegation
    - Global transition handling (intent-based navigation)
    - Context accumulation coordination
    - Return behavior handling (ReturnToPrevious, ReturnToSpecific)
    """

    pass


# DetailedJourneyResponse - response with PathwayResult for Journey.process_message()
# Note: The simpler JourneyResponse is in manager.py (exported as JourneyResponse from __init__)
@dataclass
class DetailedJourneyResponse:
    """
    Detailed response from Journey.process_message().

    This response includes the full PathwayResult for advanced use cases.
    For simpler use cases, use JourneyResponse from kaizen.journey.manager
    which only has message, pathway_id, pathway_changed, accumulated_context, metadata.

    Attributes:
        pathway_id: Current pathway ID
        result: Pathway execution result (PathwayResult)
        next_pathway_id: Next pathway (if navigation occurred)
        accumulated_context: Current accumulated context
        message: Response message (for convenience)
        pathway_changed: Whether pathway changed during processing
        metadata: Additional metadata (transition info, etc.)
    """

    pathway_id: str
    result: PathwayResult
    next_pathway_id: Optional[str]
    accumulated_context: Dict[str, Any]
    message: str = ""
    pathway_changed: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)


# Alias for backward compatibility
JourneyResponse = DetailedJourneyResponse


# ============================================================================
# Journey Base Class (REQ-JC-002)
# ============================================================================


class Journey(metaclass=JourneyMeta):
    """
    Base class for declarative journey definition.

    Journeys define multi-phase user experiences with:
    - Multiple pathways (nested classes extending Pathway)
    - Entry pathway for session start
    - Global transitions for intent-based navigation

    Example:
        class BookingJourney(Journey):
            __entry_pathway__ = "intake"
            __transitions__ = [
                Transition(trigger=IntentTrigger(["help"]), to_pathway="faq")
            ]

            class IntakePath(Pathway):
                __signature__ = IntakeSignature
                __agents__ = ["intake_agent"]
                __next__ = "booking"

            class BookingPath(Pathway):
                __signature__ = BookingSignature
                __agents__ = ["booking_agent"]

            class FAQPath(Pathway):
                __signature__ = FAQSignature
                __agents__ = ["faq_agent"]
                __return_behavior__ = ReturnToPrevious()

        # Usage
        journey = BookingJourney(session_id="user-123")
        session = await journey.start()
        response = await journey.process_message("I want to book a flight")
    """

    # Class variables (set by JourneyMeta)
    _pathways: ClassVar[Dict[str, Type[Pathway]]] = {}
    _entry_pathway: ClassVar[Optional[str]] = None
    _transitions: ClassVar[List[Any]] = []

    def __init__(
        self,
        session_id: str,
        config: Optional[JourneyConfig] = None,
    ):
        """
        Initialize Journey instance.

        Creates an enhanced PathwayManager with full runtime capabilities:
        - Session management with persistence
        - Context accumulation with field-level merge strategies
        - Intent-based transition handling
        - Return behavior navigation

        Args:
            session_id: Unique identifier for this session
            config: Optional journey configuration
        """
        self.session_id = session_id
        self.config = config or JourneyConfig()

        # Use enhanced PathwayManager from manager.py
        from kaizen.journey.manager import PathwayManager as RuntimePathwayManager

        self.manager = RuntimePathwayManager(
            journey=self,
            session_id=session_id,
            config=self.config,
        )

    @property
    def pathways(self) -> Dict[str, Type[Pathway]]:
        """Get all registered pathways (copy to prevent mutation)."""
        return self._pathways.copy()

    @property
    def entry_pathway(self) -> Optional[str]:
        """Get entry pathway ID."""
        return self._entry_pathway

    @property
    def transitions(self) -> List[Any]:
        """Get global transition rules (copy to prevent mutation)."""
        return self._transitions.copy()

    def register_agent(self, agent_id: str, agent: "BaseAgent") -> None:
        """
        Register an agent with the journey.

        Args:
            agent_id: Unique identifier for the agent
            agent: BaseAgent instance to register
        """
        self.manager.register_agent(agent_id, agent)

    async def start(
        self, initial_context: Optional[Dict[str, Any]] = None
    ) -> JourneySession:
        """
        Start journey session at entry pathway.

        Args:
            initial_context: Optional initial accumulated context

        Returns:
            JourneySession with initial state
        """
        return await self.manager.start_session(initial_context)

    async def process_message(self, message: str) -> DetailedJourneyResponse:
        """
        Process user message in current pathway.

        Uses the enhanced PathwayManager which provides:
        - Global transition handling (intent-based navigation)
        - Context accumulation with merge strategies
        - Return behavior handling
        - Session state persistence

        Args:
            message: User input message

        Returns:
            DetailedJourneyResponse with result, navigation, and accumulated context
        """
        # Get response from manager (returns manager.JourneyResponse)
        from kaizen.journey.manager import JourneyResponse as ManagerResponse

        response = await self.manager.process_message(message)

        # Convert to DetailedJourneyResponse which includes PathwayResult
        if isinstance(response, ManagerResponse):
            return DetailedJourneyResponse(
                pathway_id=response.pathway_id,
                result=PathwayResult(
                    outputs={"response": response.message},
                    accumulated={},
                    next_pathway=None,
                    is_complete=True,
                ),
                next_pathway_id=response.pathway_id,
                accumulated_context=response.accumulated_context,
                message=response.message,
                pathway_changed=response.pathway_changed,
                metadata=response.metadata,
            )
        return response


__all__ = [
    # Data classes
    "JourneyConfig",
    "PathwayContext",
    "PathwayResult",
    "JourneySession",
    "JourneyResponse",  # Alias for DetailedJourneyResponse (backward compat)
    "DetailedJourneyResponse",  # Full response with PathwayResult
    # Metaclasses
    "JourneyMeta",
    "PathwayMeta",
    # Base classes
    "Journey",
    "Pathway",
    # Internal
    "PathwayManager",
]
