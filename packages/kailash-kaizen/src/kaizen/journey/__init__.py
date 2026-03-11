"""
Kaizen Journey Orchestration - Layer 5

Journey Orchestration provides declarative multi-phase user journey definitions
with automatic pathway management, context accumulation, and intent-based navigation.

Key Components:
    - Journey: Base class for declarative journey definition with nested pathways
    - Pathway: Phase in a user journey with signature, agents, and pipeline config
    - JourneyConfig: Configuration for journey execution
    - PathwayContext: Execution context for pathway processing
    - PathwayResult: Result from pathway execution

Return Behaviors:
    - ReturnBehavior: Base class for pathway return behaviors
    - ReturnToPrevious: Return to previous pathway (for detours like FAQ)
    - ReturnToSpecific: Return to a specific named pathway

Transitions & Intent Detection:
    - Transition: Rule for switching between pathways
    - IntentTrigger: LLM-powered intent detection with pattern matching
    - ConditionTrigger: Context-condition based transitions
    - IntentDetector: Orchestrates pattern matching, caching, and LLM classification
    - IntentMatch: Result of intent detection

Runtime Components (TODO-JO-004):
    - PathwayManager: Enhanced runtime manager with session/context management
    - ContextAccumulator: Field-level merge strategies for cross-pathway state
    - MergeStrategy: Enum for context merge strategies (REPLACE, APPEND, UNION, etc.)
    - JourneyStateManager: Pluggable session persistence backends
    - StateBackend: Abstract backend interface (MemoryStateBackend, DataFlowStateBackend)

Error Handling:
    - JourneyError: Base exception for journey errors
    - PathwayNotFoundError: When pathway doesn't exist
    - SessionNotStartedError: When operating on unstarted session
    - ContextSizeExceededError: When context exceeds size limit
    - MaxPathwayDepthError: When navigation stack exceeds max depth

Quick Start:
    from kaizen.journey import Journey, Pathway, JourneyConfig
    from kaizen.journey.behaviors import ReturnToPrevious
    from kaizen.signatures import Signature, InputField, OutputField

    # Define signatures
    class IntakeSignature(Signature):
        message: str = InputField(desc="User message")
        response: str = OutputField(desc="Agent response")
        customer_name: str = OutputField(desc="Extracted customer name")

    # Define journey with nested pathways
    class CustomerJourney(Journey):
        __entry_pathway__ = "intake"

        class IntakePath(Pathway):
            __signature__ = IntakeSignature
            __agents__ = ["intake_agent"]
            __accumulate__ = ["customer_name"]
            __next__ = "service"

        class ServicePath(Pathway):
            __signature__ = ServiceSignature
            __agents__ = ["service_agent"]

        class FAQPath(Pathway):
            __signature__ = FAQSignature
            __agents__ = ["faq_agent"]
            __return_behavior__ = ReturnToPrevious()

    # Usage
    journey = CustomerJourney(session_id="user-123")
    journey.register_agent("intake_agent", intake_agent)
    journey.register_agent("service_agent", service_agent)
    journey.register_agent("faq_agent", faq_agent)

    session = await journey.start()
    response = await journey.process_message("Hi, I need help")

Architecture:
    Layer 5 (Journey Orchestration)
    - Declarative journey definition
    - Multi-pathway navigation
    - Context accumulation

    Layer 4 (Pipeline Patterns)
    - Agent coordination (sequential, parallel, router, etc.)

    Layer 3 (BaseAgent)
    - Individual agent execution
    - Tool calling, memory, etc.

    Layer 2 (Signatures)
    - Type-safe I/O contracts
    - Guidelines and intent

    Layer 1 (Core SDK)
    - Workflow execution
    - Node-based processing

See Also:
    - docs/plans/03-journey/03-journey-core.md: Design specification
    - docs/plans/03-journey/05-runtime.md: Runtime components specification
    - kaizen.orchestration.pipeline: Pipeline patterns for agent coordination
    - kaizen.signatures: Signature-based programming
"""

# Return behaviors
from kaizen.journey.behaviors import ReturnBehavior, ReturnToPrevious, ReturnToSpecific

# Context accumulation (TODO-JO-004)
from kaizen.journey.context import (
    AccumulatedField,
    ContextAccumulator,
    ContextSnapshot,
    MergeStrategy,
)

# Core classes
from kaizen.journey.core import (
    DetailedJourneyResponse,  # Full response with PathwayResult
)
from kaizen.journey.core import (
    JourneyResponse,  # Alias for DetailedJourneyResponse (backward compat)
)
from kaizen.journey.core import (  # Data classes; Metaclasses (for advanced use); Base classes; Internal (for testing/extension)
    Journey,
    JourneyConfig,
    JourneyMeta,
    JourneySession,
    Pathway,
    PathwayContext,
    PathwayManager,
    PathwayMeta,
    PathwayResult,
)

# Error handling (TODO-JO-004)
from kaizen.journey.errors import (
    ContextSizeExceededError,
    JourneyError,
    MaxPathwayDepthError,
    PathwayNotFoundError,
    SessionNotStartedError,
    StateError,
    TransitionError,
)

# Intent detection (TODO-JO-003)
from kaizen.journey.intent import (
    IntentClassificationSignature,
    IntentDetector,
    IntentMatch,
)

# Hook types (TODO-JO-005 REQ-INT-007)
# Enhanced manager (TODO-JO-004)
from kaizen.journey.manager import (
    JourneyHookContext,
    JourneyHookEvent,
    JourneyHookResult,
)
from kaizen.journey.manager import JourneyResponse as EnhancedJourneyResponse
from kaizen.journey.manager import PathwayManager as EnhancedPathwayManager

# DataFlow models (TODO-JO-005 REQ-INT-004)
from kaizen.journey.models import (
    EnhancedDataFlowStateBackend,
    IntentCacheModel,
    JourneyConversationModel,
    JourneySessionModel,
    register_journey_models,
)

# Nexus integration (TODO-JO-005 REQ-INT-005)
from kaizen.journey.nexus import (
    JourneyNexusAdapter,
    JourneySessionManager,
    NexusSessionInfo,
    deploy_journey_to_nexus,
)

# State management (TODO-JO-004)
from kaizen.journey.state import (
    DataFlowStateBackend,
    JourneyStateManager,
    MemoryStateBackend,
    StateBackend,
)

# Transitions (TODO-JO-003)
from kaizen.journey.transitions import (
    AlwaysTrigger,
    BaseTrigger,
    ConditionTrigger,
    IntentTrigger,
    Transition,
    TransitionResult,
)

__all__ = [
    # Core classes
    "Journey",
    "Pathway",
    "JourneyConfig",
    "PathwayContext",
    "PathwayResult",
    "JourneySession",
    "JourneyResponse",  # Alias for DetailedJourneyResponse (backward compat)
    "DetailedJourneyResponse",  # Full response with PathwayResult
    # Metaclasses
    "JourneyMeta",
    "PathwayMeta",
    # Return behaviors
    "ReturnBehavior",
    "ReturnToPrevious",
    "ReturnToSpecific",
    # Transitions (TODO-JO-003)
    "Transition",
    "TransitionResult",
    "BaseTrigger",
    "IntentTrigger",
    "ConditionTrigger",
    "AlwaysTrigger",
    # Intent detection (TODO-JO-003)
    "IntentClassificationSignature",
    "IntentDetector",
    "IntentMatch",
    # Context accumulation (TODO-JO-004)
    "ContextAccumulator",
    "MergeStrategy",
    "AccumulatedField",
    "ContextSnapshot",
    # State management (TODO-JO-004)
    "JourneyStateManager",
    "StateBackend",
    "MemoryStateBackend",
    "DataFlowStateBackend",
    # Enhanced runtime (TODO-JO-004)
    "EnhancedPathwayManager",
    "EnhancedJourneyResponse",
    # Error handling (TODO-JO-004)
    "JourneyError",
    "PathwayNotFoundError",
    "SessionNotStartedError",
    "ContextSizeExceededError",
    "MaxPathwayDepthError",
    "TransitionError",
    "StateError",
    # Hook types (TODO-JO-005 REQ-INT-007)
    "JourneyHookEvent",
    "JourneyHookContext",
    "JourneyHookResult",
    # DataFlow models (TODO-JO-005 REQ-INT-004)
    "JourneySessionModel",
    "JourneyConversationModel",
    "IntentCacheModel",
    "register_journey_models",
    "EnhancedDataFlowStateBackend",
    # Nexus integration (TODO-JO-005 REQ-INT-005)
    "NexusSessionInfo",
    "JourneySessionManager",
    "JourneyNexusAdapter",
    "deploy_journey_to_nexus",
    # Internal
    "PathwayManager",
]
