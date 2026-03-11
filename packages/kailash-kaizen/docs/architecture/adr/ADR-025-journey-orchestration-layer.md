# ADR-025: Journey Orchestration Layer (Layer 5)

## Status
**Proposed** - Implementation Planning Complete

## Document Information
- **Created**: 2026-01-12
- **Authors**: Requirements Analysis Specialist (Claude)
- **Related ADRs**: ADR-020 (Unified Agent API), ADR-007 (Signature Programming)
- **Target Version**: v0.9.0
- **Reference**: kaizen-narrative.md Layer 5 specification

---

## Executive Summary

This ADR documents the comprehensive implementation plan for Kaizen's Layer 5: Journey Orchestration, including Layer 2 Signature enhancements. The design enables declarative user journey definition with intent-driven pathway transitions, building on the existing multi-agent orchestration infrastructure (Layer 4).

**Key Deliverables**:
1. Layer 2 Enhancements: `__intent__` and `__guidelines__` Signature attributes
2. Layer 5 Components: Journey, Pathway, Transition, IntentTrigger, PathwayManager, ContextAccumulator

**Use Case**: Healthcare Referral AI Assistant with multiple pathways (intake, booking, FAQ, persuasion, confirmation)

---

## Table of Contents

1. [Context](#1-context)
2. [Decision](#2-decision)
3. [Component Breakdown](#3-component-breakdown)
4. [Layer 2 Signature Enhancements](#4-layer-2-signature-enhancements)
5. [Layer 5 Journey Components](#5-layer-5-journey-components)
6. [Integration Architecture](#6-integration-architecture)
7. [Healthcare Referral Use Case](#7-healthcare-referral-use-case)
8. [Risk Assessment](#8-risk-assessment)
9. [Implementation Roadmap](#9-implementation-roadmap)
10. [Consequences](#10-consequences)
11. [Alternatives Considered](#11-alternatives-considered)

---

## 1. Context

### 1.1 Problem Statement

Kaizen's Layer 4 (Multi-Agent Orchestration) handles **task-level coordination** - multiple agents working together on a single complex task. However, real-world conversational AI systems require **user journey orchestration**:

| Aspect | Layer 4 (Current) | Layer 5 (Needed) |
|--------|-------------------|------------------|
| Scope | Single complex task | Entire user session |
| Trigger | Task decomposition | User intent |
| Duration | One execution | Multiple turns/sessions |
| State | Shared memory for task | Journey context across pathways |
| Flow | Agent coordination patterns | User pathway transitions |

### 1.2 Use Case Driver: Healthcare Referral AI

A healthcare referral booking system requires:
1. **Multiple Pathways**: Intake, Booking, FAQ, Persuasion, Confirmation
2. **Intent Detection**: User asks a question mid-booking -> FAQ pathway
3. **Context Accumulation**: Remember rejected doctors, preferences across pathways
4. **Return-to-Previous**: Answer FAQ, return to where user left off
5. **Graceful Transitions**: Smooth context handoff between pathways

### 1.3 Existing Infrastructure

The following Kaizen components are available for integration:

```
kaizen/
├── signatures/core.py           # Signature, InputField, OutputField, SignatureMeta
├── orchestration/
│   ├── pipeline.py              # 9 pipeline patterns
│   ├── patterns/                # SupervisorWorker, Consensus, Debate, etc.
│   ├── runtime.py               # OrchestrationRuntime (10-100 agents)
│   ├── state_manager.py         # DataFlow-based state persistence
│   └── models.py                # WorkflowState, AgentExecutionRecord
├── memory/
│   ├── conversation_base.py     # KaizenMemory abstract base
│   ├── shared_memory.py         # SharedMemoryPool
│   └── tiers.py                 # Hot/Warm/Cold tier system
└── core/base_agent.py           # BaseAgent with A2A, memory, tools
```

---

## 2. Decision

Implement Layer 5 Journey Orchestration with the following architecture:

### 2.1 Architectural Principles

1. **Declarative Definition**: Journey structure defined as class hierarchy
2. **Intent-Driven Transitions**: LLM-powered intent detection for pathway switching
3. **Context Accumulation**: Cross-pathway state persistence
4. **Pipeline Composition**: Pathways leverage existing Layer 4 patterns
5. **Return-to-Previous**: Stack-based pathway navigation for detours

### 2.2 Component Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         LAYER 5: JOURNEY ORCHESTRATION                      │
│                                                                              │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────────────────┐  │
│  │     Journey     │  │    Pathway      │  │       Transition            │  │
│  │  (declarative)  │  │   (phase)       │  │  (switching rules)          │  │
│  │                 │  │                 │  │                              │  │
│  │ __entry_path__  │  │ __signature__   │  │  trigger: IntentTrigger     │  │
│  │ __transitions__ │  │ __agents__      │  │  from_pathway: str          │  │
│  │ nested Pathways │  │ __pipeline__    │  │  to_pathway: str            │  │
│  │                 │  │ __accumulate__  │  │  context_update: dict       │  │
│  │                 │  │ __next__        │  │                              │  │
│  └────────┬────────┘  └────────┬────────┘  └──────────────┬──────────────┘  │
│           │                    │                          │                  │
│           ▼                    ▼                          ▼                  │
│  ┌─────────────────────────────────────────────────────────────────────────┐│
│  │                       PathwayManager (Runtime)                          ││
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────────────┐  ││
│  │  │IntentDetector│  │PathwayStack  │  │   ContextAccumulator         │  ││
│  │  │(LLM-powered) │  │(return nav)  │  │   (cross-pathway state)      │  ││
│  │  └──────────────┘  └──────────────┘  └──────────────────────────────┘  ││
│  └─────────────────────────────────────────────────────────────────────────┘│
│                                    │                                         │
│                    ┌───────────────┴───────────────┐                        │
│                    ▼                               ▼                        │
│  ┌─────────────────────────────┐  ┌─────────────────────────────────────┐  │
│  │   Layer 4: Pipeline         │  │   OrchestrationStateManager         │  │
│  │   (agent coordination)      │  │   (DataFlow persistence)            │  │
│  └─────────────────────────────┘  └─────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Component Breakdown

### 3.1 Functional Requirements Matrix

| REQ-ID | Component | Description | Input | Output | Business Logic | Edge Cases | SDK Mapping |
|--------|-----------|-------------|-------|--------|----------------|------------|-------------|
| REQ-001 | Journey | Declarative journey definition | Class definition | JourneyInstance | Parse pathways, transitions | Empty pathways, circular refs | JourneyMeta metaclass |
| REQ-002 | Pathway | Journey phase with agents | Signature + agents | Pathway results | Execute pipeline, accumulate | Agent failures, timeouts | Pipeline patterns |
| REQ-003 | Transition | Pathway switching rules | Trigger + context | Target pathway | Match intent, update context | Ambiguous intents | IntentTrigger |
| REQ-004 | IntentTrigger | LLM intent detection | User message | Intent match | Pattern + LLM classification | No match, multiple matches | LLMAgentNode |
| REQ-005 | PathwayManager | Runtime state | Journey + session | Execution results | Navigate, accumulate, persist | Session expiry, crashes | AsyncLocalRuntime |
| REQ-006 | ContextAccumulator | Cross-pathway state | Field specs | Accumulated context | Merge, version, persist | Conflicts, overflow | DataFlow models |
| REQ-007 | ReturnToPrevious | Detour handling | Previous pathway | Return navigation | Stack push/pop | Deep nesting, cycles | PathwayStack |

### 3.2 Non-Functional Requirements

#### Performance Requirements
```
- Intent detection latency: < 200ms (LLM call included)
- Pathway transition overhead: < 50ms
- Context accumulator merge: < 10ms
- Session state persistence: < 100ms (async)
- Memory overhead per session: < 50MB
```

#### Security Requirements
```
- Session isolation: Multi-tenant safe
- Context encryption: Optional AES-256 for sensitive journeys
- Audit trail: All pathway transitions logged
- Input validation: Sanitize user inputs before intent detection
```

#### Scalability Requirements
```
- Concurrent sessions: 10,000+ per instance
- Pathway depth: 10 levels max (prevent stack overflow)
- Context size: 1MB max per session
- Persistence: PostgreSQL for production, SQLite for dev
```

---

## 4. Layer 2 Signature Enhancements

### 4.1 Purpose and Responsibility

Enhance the Signature class to support explicit intent and behavioral guidelines, enabling:
1. **Explicit Intent**: WHY the agent exists (beyond docstring)
2. **Behavioral Constraints**: HOW the agent should behave
3. **Immutable Composition**: Create variants without modifying original

### 4.2 Key Interfaces and Methods

```python
# File: kaizen/signatures/core.py

class SignatureMeta(type):
    """Enhanced metaclass to process __intent__ and __guidelines__."""

    def __new__(mcs, name, bases, namespace, **kwargs):
        # Existing field extraction logic...

        # NEW: Extract intent and guidelines
        intent = namespace.get("__intent__", "")
        guidelines = namespace.get("__guidelines__", [])

        # Store as class variables
        namespace["_signature_intent"] = intent
        namespace["_signature_guidelines"] = list(guidelines)

        return super().__new__(mcs, name, bases, namespace)


class Signature(metaclass=SignatureMeta):
    """Enhanced Signature with intent and guidelines support."""

    # Class variables (set by SignatureMeta)
    _signature_intent: ClassVar[str] = ""
    _signature_guidelines: ClassVar[List[str]] = []
    _signature_description: ClassVar[str] = ""  # Existing

    @property
    def intent(self) -> str:
        """Get the signature's intent (WHY it exists)."""
        return self._signature_intent

    @property
    def guidelines(self) -> List[str]:
        """Get behavioral guidelines (HOW it should behave)."""
        return self._signature_guidelines.copy()

    @property
    def instructions(self) -> str:
        """DSPy-compatible: Returns __doc__ (docstring)."""
        return self._signature_description

    def with_instructions(self, new_instructions: str) -> "Signature":
        """
        Create new Signature instance with modified instructions.

        Immutable: Returns NEW instance, doesn't modify self.

        Args:
            new_instructions: New instruction text

        Returns:
            New Signature instance with updated instructions
        """
        # Create shallow copy with updated instructions
        new_sig = self._clone()
        new_sig._signature_description = new_instructions
        return new_sig

    def with_guidelines(self, additional_guidelines: List[str]) -> "Signature":
        """
        Create new Signature instance with additional guidelines.

        Immutable: Returns NEW instance, doesn't modify self.

        Args:
            additional_guidelines: Guidelines to append

        Returns:
            New Signature instance with extended guidelines
        """
        new_sig = self._clone()
        new_sig._signature_guidelines = self._signature_guidelines + list(additional_guidelines)
        return new_sig

    def _clone(self) -> "Signature":
        """Create shallow clone of signature for immutable operations."""
        # Implementation handles both class-based and programmatic signatures
        ...
```

### 4.3 Usage Example

```python
from kaizen.signatures import Signature, InputField, OutputField

class CustomerSupportSignature(Signature):
    """You are a helpful customer support agent."""

    __intent__ = "Resolve customer issues efficiently and empathetically"

    __guidelines__ = [
        "Acknowledge the customer's concern before providing solutions",
        "Use empathetic language throughout the conversation",
        "Escalate to human support if issue cannot be resolved in 3 turns"
    ]

    query: str = InputField(description="Customer's question or issue")
    context: str = InputField(description="Previous conversation context", default="")

    response: str = OutputField(description="Helpful response addressing the concern")
    sentiment: str = OutputField(description="Detected sentiment: positive/neutral/negative")

# Access properties
sig = CustomerSupportSignature()
print(sig.intent)       # "Resolve customer issues efficiently..."
print(sig.guidelines)   # ["Acknowledge...", "Use empathetic...", "Escalate..."]
print(sig.instructions) # "You are a helpful customer support agent."

# Immutable composition
escalation_sig = sig.with_guidelines([
    "Always offer callback option before escalation"
])
# sig.guidelines is unchanged
# escalation_sig.guidelines has 4 items
```

### 4.4 Dependencies

| Component | Dependency | Integration Point |
|-----------|------------|-------------------|
| SignatureMeta | None (existing) | Enhanced __new__ method |
| Signature | SignatureMeta | Instance methods added |
| BaseAgent | Signature | Reads intent/guidelines for prompt |
| LLMAgentNode | Signature | Uses instructions for system prompt |

### 4.5 Test Scenarios

```python
# Test: Intent extraction
class TestIntentExtraction:
    def test_intent_from_class_attribute(self):
        class MySig(Signature):
            __intent__ = "Test intent"
            question: str = InputField(desc="Q")
            answer: str = OutputField(desc="A")

        sig = MySig()
        assert sig.intent == "Test intent"

    def test_missing_intent_defaults_to_empty(self):
        class MySig(Signature):
            question: str = InputField(desc="Q")
            answer: str = OutputField(desc="A")

        sig = MySig()
        assert sig.intent == ""

# Test: Guidelines extraction
class TestGuidelinesExtraction:
    def test_guidelines_from_class_attribute(self):
        class MySig(Signature):
            __guidelines__ = ["G1", "G2"]
            q: str = InputField(desc="Q")
            a: str = OutputField(desc="A")

        sig = MySig()
        assert sig.guidelines == ["G1", "G2"]

    def test_guidelines_are_copied(self):
        """Ensure guidelines property returns copy, not reference."""
        class MySig(Signature):
            __guidelines__ = ["G1"]
            q: str = InputField(desc="Q")
            a: str = OutputField(desc="A")

        sig = MySig()
        guidelines = sig.guidelines
        guidelines.append("G2")
        assert sig.guidelines == ["G1"]  # Original unchanged

# Test: Immutable composition
class TestImmutableComposition:
    def test_with_instructions_creates_new_instance(self):
        class MySig(Signature):
            """Original instructions."""
            q: str = InputField(desc="Q")
            a: str = OutputField(desc="A")

        sig1 = MySig()
        sig2 = sig1.with_instructions("New instructions.")

        assert sig1.instructions == "Original instructions."
        assert sig2.instructions == "New instructions."
        assert sig1 is not sig2

    def test_with_guidelines_appends(self):
        class MySig(Signature):
            __guidelines__ = ["G1"]
            q: str = InputField(desc="Q")
            a: str = OutputField(desc="A")

        sig1 = MySig()
        sig2 = sig1.with_guidelines(["G2", "G3"])

        assert sig1.guidelines == ["G1"]
        assert sig2.guidelines == ["G1", "G2", "G3"]
```

---

## 5. Layer 5 Journey Components

### 5.1 Journey Class

#### Purpose and Responsibility
Top-level declarative container for user journey definition. Contains nested Pathway classes and global transition rules.

#### Key Interfaces

```python
# File: kaizen/journey/core.py

from typing import ClassVar, Dict, List, Type, Optional, Any
from dataclasses import dataclass


class JourneyMeta(type):
    """Metaclass for processing Journey class definitions."""

    def __new__(mcs, name, bases, namespace, **kwargs):
        if name == "Journey":
            return super().__new__(mcs, name, bases, namespace)

        # Extract nested Pathway classes
        pathways: Dict[str, Type["Pathway"]] = {}
        for attr_name, attr_value in namespace.items():
            if isinstance(attr_value, type) and issubclass(attr_value, Pathway):
                pathway_id = _to_snake_case(attr_name.replace("Path", "").replace("Pathway", ""))
                pathways[pathway_id] = attr_value

        # Validate entry pathway
        entry_pathway = namespace.get("__entry_pathway__")
        if entry_pathway and entry_pathway not in pathways:
            raise ValueError(f"Entry pathway '{entry_pathway}' not found. Available: {list(pathways.keys())}")

        # Store as class variables
        namespace["_pathways"] = pathways
        namespace["_entry_pathway"] = entry_pathway or list(pathways.keys())[0] if pathways else None
        namespace["_transitions"] = namespace.get("__transitions__", [])

        return super().__new__(mcs, name, bases, namespace)


class Journey(metaclass=JourneyMeta):
    """
    Base class for declarative journey definition.

    Journeys contain nested Pathway classes and global transition rules.

    Example:
        class BookingJourney(Journey):
            __entry_pathway__ = "intake"

            class IntakePath(Pathway):
                __signature__ = IntakeSignature
                __agents__ = ["intake_agent"]
                __next__ = "booking"

            class BookingPath(Pathway):
                __signature__ = BookingSignature
                __agents__ = ["slot_finder", "doctor_matcher"]
                __pipeline__ = "parallel"

            __transitions__ = [
                Transition(trigger=IntentTrigger(["help"]), from_pathway="*", to_pathway="faq")
            ]
    """

    # Class variables (set by JourneyMeta)
    _pathways: ClassVar[Dict[str, Type["Pathway"]]] = {}
    _entry_pathway: ClassVar[Optional[str]] = None
    _transitions: ClassVar[List["Transition"]] = []

    def __init__(self, session_id: str, config: Optional["JourneyConfig"] = None):
        """
        Initialize journey instance for a user session.

        Args:
            session_id: Unique session identifier
            config: Optional journey configuration
        """
        self.session_id = session_id
        self.config = config or JourneyConfig()

        # Instantiate pathway manager
        self.manager = PathwayManager(
            journey=self,
            session_id=session_id,
            config=self.config
        )

    @property
    def pathways(self) -> Dict[str, Type["Pathway"]]:
        """Get all registered pathways."""
        return self._pathways.copy()

    @property
    def entry_pathway(self) -> str:
        """Get entry pathway ID."""
        return self._entry_pathway

    @property
    def transitions(self) -> List["Transition"]:
        """Get global transition rules."""
        return self._transitions.copy()

    async def start(self, initial_context: Optional[Dict[str, Any]] = None) -> "JourneySession":
        """
        Start journey session at entry pathway.

        Args:
            initial_context: Initial context values

        Returns:
            JourneySession for interaction
        """
        return await self.manager.start_session(initial_context)

    async def process_message(self, message: str) -> "JourneyResponse":
        """
        Process user message in current pathway.

        Args:
            message: User input message

        Returns:
            JourneyResponse with agent response and state
        """
        return await self.manager.process_message(message)


@dataclass
class JourneyConfig:
    """Configuration for Journey execution."""

    # Intent detection
    intent_detection_model: str = "gpt-4o-mini"
    intent_confidence_threshold: float = 0.7

    # Pathway execution
    max_pathway_depth: int = 10
    pathway_timeout_seconds: float = 60.0

    # Context accumulation
    max_context_size_bytes: int = 1024 * 1024  # 1MB
    context_persistence: str = "dataflow"  # "memory", "dataflow", "redis"

    # Error handling
    error_recovery: str = "graceful"  # "fail_fast", "graceful", "retry"
    max_retries: int = 3
```

#### Dependencies

| Component | Dependency | Integration Point |
|-----------|------------|-------------------|
| Journey | JourneyMeta | Metaclass processes class definition |
| Journey | PathwayManager | Runtime execution manager |
| Journey | Pathway | Nested pathway classes |
| Journey | Transition | Global transition rules |
| JourneyMeta | Pathway | Validates pathway references |

### 5.2 Pathway Class

#### Purpose and Responsibility
A phase in the user journey that executes a specific agent pipeline with a defined signature.

#### Key Interfaces

```python
# File: kaizen/journey/core.py

from typing import ClassVar, List, Optional, Any, Union, Type
from kaizen.signatures import Signature


class PathwayMeta(type):
    """Metaclass for processing Pathway class definitions."""

    def __new__(mcs, name, bases, namespace, **kwargs):
        if name == "Pathway":
            return super().__new__(mcs, name, bases, namespace)

        # Extract pathway configuration
        namespace["_signature"] = namespace.get("__signature__")
        namespace["_agents"] = namespace.get("__agents__", [])
        namespace["_pipeline"] = namespace.get("__pipeline__", "sequential")
        namespace["_accumulate"] = namespace.get("__accumulate__", [])
        namespace["_next"] = namespace.get("__next__")
        namespace["_return_behavior"] = namespace.get("__return_behavior__")

        return super().__new__(mcs, name, bases, namespace)


class Pathway(metaclass=PathwayMeta):
    """
    A phase in a user journey.

    Pathways define:
    - Signature: I/O contract for this phase
    - Agents: Which agents handle this pathway
    - Pipeline: How agents are coordinated
    - Accumulate: Which fields to preserve across pathways
    - Next: Default next pathway (if no transition triggered)

    Example:
        class BookingPath(Pathway):
            __signature__ = BookingSignature
            __agents__ = ["slot_finder", "doctor_matcher"]
            __pipeline__ = "parallel"
            __accumulate__ = ["rejected_doctors", "preferences"]
            __next__ = "confirmation"
    """

    # Class variables (set by PathwayMeta)
    _signature: ClassVar[Optional[Type[Signature]]] = None
    _agents: ClassVar[List[str]] = []
    _pipeline: ClassVar[str] = "sequential"
    _accumulate: ClassVar[List[str]] = []
    _next: ClassVar[Optional[str]] = None
    _return_behavior: ClassVar[Optional["ReturnBehavior"]] = None

    def __init__(self, manager: "PathwayManager"):
        """
        Initialize pathway instance.

        Args:
            manager: Parent pathway manager
        """
        self.manager = manager
        self._signature_instance = None
        self._pipeline_instance = None

    @property
    def signature(self) -> Optional[Signature]:
        """Get instantiated signature for this pathway."""
        if self._signature_instance is None and self._signature is not None:
            self._signature_instance = self._signature()
        return self._signature_instance

    @property
    def agent_ids(self) -> List[str]:
        """Get list of agent IDs for this pathway."""
        return self._agents.copy()

    @property
    def pipeline_type(self) -> str:
        """Get pipeline pattern type."""
        return self._pipeline

    @property
    def accumulate_fields(self) -> List[str]:
        """Get fields to accumulate across pathways."""
        return self._accumulate.copy()

    @property
    def next_pathway(self) -> Optional[str]:
        """Get default next pathway ID."""
        return self._next

    @property
    def return_behavior(self) -> Optional["ReturnBehavior"]:
        """Get return behavior for detour pathways."""
        return self._return_behavior

    async def execute(self, context: "PathwayContext") -> "PathwayResult":
        """
        Execute pathway with given context.

        Args:
            context: Current pathway execution context

        Returns:
            PathwayResult with outputs and state
        """
        # Build pipeline from registered agents
        agents = self._resolve_agents()
        pipeline = self._build_pipeline(agents)

        # Execute pipeline
        result = await pipeline.execute(context.to_input_dict())

        # Accumulate specified fields
        accumulated = self._extract_accumulated_fields(result)

        return PathwayResult(
            outputs=result,
            accumulated=accumulated,
            next_pathway=self._next,
            is_complete=True
        )

    def _resolve_agents(self) -> List["BaseAgent"]:
        """Resolve agent IDs to agent instances from registry."""
        return [self.manager.get_agent(aid) for aid in self._agents]

    def _build_pipeline(self, agents: List["BaseAgent"]) -> "Pipeline":
        """Build pipeline from agents based on pipeline type."""
        from kaizen.orchestration.pipeline import Pipeline

        pipeline_builders = {
            "sequential": Pipeline.sequential,
            "parallel": Pipeline.parallel,
            "router": lambda a: Pipeline.router(a, routing_strategy="semantic"),
            "ensemble": Pipeline.ensemble,
        }

        builder = pipeline_builders.get(self._pipeline, Pipeline.sequential)
        return builder(agents)

    def _extract_accumulated_fields(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """Extract fields to accumulate from result."""
        return {
            field: result.get(field)
            for field in self._accumulate
            if field in result
        }


@dataclass
class PathwayResult:
    """Result from pathway execution."""
    outputs: Dict[str, Any]
    accumulated: Dict[str, Any]
    next_pathway: Optional[str]
    is_complete: bool
    error: Optional[str] = None


@dataclass
class PathwayContext:
    """Execution context for a pathway."""
    session_id: str
    pathway_id: str
    user_message: str
    accumulated_context: Dict[str, Any]
    conversation_history: List[Dict[str, Any]]

    def to_input_dict(self) -> Dict[str, Any]:
        """Convert context to pipeline input dictionary."""
        return {
            "message": self.user_message,
            "context": self.accumulated_context,
            "history": self.conversation_history,
        }
```

#### Dependencies

| Component | Dependency | Integration Point |
|-----------|------------|-------------------|
| Pathway | PathwayMeta | Metaclass processes class definition |
| Pathway | Signature | I/O contract for pathway |
| Pathway | Pipeline | Agent coordination pattern |
| Pathway | PathwayManager | Parent manager for agent resolution |
| Pathway | BaseAgent | Executes pathway logic |

### 5.3 Transition Class

#### Purpose and Responsibility
Rules for switching between pathways based on triggers (intent, conditions, etc.).

#### Key Interfaces

```python
# File: kaizen/journey/transitions.py

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Union


@dataclass
class Transition:
    """
    Rule for switching between pathways.

    Transitions define:
    - trigger: When to activate (IntentTrigger, ConditionTrigger)
    - from_pathway: Source pathway ("*" for any)
    - to_pathway: Destination pathway
    - context_update: How to update context on transition

    Example:
        Transition(
            trigger=IntentTrigger(patterns=["help", "what is"]),
            from_pathway="*",
            to_pathway="faq"
        )
    """

    trigger: "BaseTrigger"
    from_pathway: str = "*"  # "*" matches any pathway
    to_pathway: str = ""
    context_update: Optional[Dict[str, str]] = None
    priority: int = 0  # Higher priority evaluated first

    def matches(
        self,
        current_pathway: str,
        message: str,
        context: Dict[str, Any]
    ) -> bool:
        """
        Check if transition should activate.

        Args:
            current_pathway: Current pathway ID
            message: User message
            context: Current context

        Returns:
            True if transition should activate
        """
        # Check pathway match
        if self.from_pathway != "*" and self.from_pathway != current_pathway:
            return False

        # Check trigger
        return self.trigger.evaluate(message, context)

    def apply_context_update(self, context: Dict[str, Any], result: Dict[str, Any]) -> Dict[str, Any]:
        """
        Apply context updates specified in transition.

        Supports special syntax:
        - "append:field_name" - Append current value to list
        - "set:value" - Set literal value
        - "copy:field_name" - Copy from result

        Args:
            context: Current context
            result: Current pathway result

        Returns:
            Updated context
        """
        if not self.context_update:
            return context

        new_context = context.copy()

        for target_field, update_spec in self.context_update.items():
            if update_spec.startswith("append:"):
                source_field = update_spec.split(":", 1)[1]
                source_value = result.get(source_field)
                if source_value is not None:
                    existing = new_context.get(target_field, [])
                    if not isinstance(existing, list):
                        existing = [existing]
                    existing.append(source_value)
                    new_context[target_field] = existing

            elif update_spec.startswith("set:"):
                value = update_spec.split(":", 1)[1]
                new_context[target_field] = value

            elif update_spec.startswith("copy:"):
                source_field = update_spec.split(":", 1)[1]
                new_context[target_field] = result.get(source_field)

            else:
                # Direct field reference
                new_context[target_field] = result.get(update_spec)

        return new_context


class BaseTrigger:
    """Base class for transition triggers."""

    def evaluate(self, message: str, context: Dict[str, Any]) -> bool:
        """Evaluate if trigger condition is met."""
        raise NotImplementedError


@dataclass
class IntentTrigger(BaseTrigger):
    """
    LLM-powered intent detection trigger.

    Uses pattern matching with optional LLM fallback for complex intent detection.

    Example:
        IntentTrigger(patterns=["help", "question", "what is"])
    """

    patterns: List[str] = field(default_factory=list)
    use_llm_fallback: bool = True
    llm_model: str = "gpt-4o-mini"
    confidence_threshold: float = 0.7

    def evaluate(self, message: str, context: Dict[str, Any]) -> bool:
        """
        Evaluate if message matches intent patterns.

        First checks simple pattern matching, then uses LLM if enabled.
        """
        # Fast path: simple pattern matching
        message_lower = message.lower()
        for pattern in self.patterns:
            if pattern.lower() in message_lower:
                return True

        # Slow path: LLM intent classification (if enabled)
        if self.use_llm_fallback:
            return self._llm_intent_match(message)

        return False

    def _llm_intent_match(self, message: str) -> bool:
        """Use LLM for complex intent matching."""
        # Implemented by IntentDetector in PathwayManager
        # Returns cached result if available
        return False  # Placeholder


@dataclass
class ConditionTrigger(BaseTrigger):
    """
    Condition-based trigger using context values.

    Example:
        ConditionTrigger(
            condition=lambda ctx: ctx.get("retry_count", 0) >= 3
        )
    """

    condition: Callable[[Dict[str, Any]], bool] = None

    def evaluate(self, message: str, context: Dict[str, Any]) -> bool:
        """Evaluate condition against context."""
        if self.condition is None:
            return False
        return self.condition(context)


@dataclass
class ReturnToPrevious:
    """
    Behavior for detour pathways (e.g., FAQ).

    After detour completes, return to previous pathway.

    Example:
        class FAQPath(Pathway):
            __return_behavior__ = ReturnToPrevious()
    """

    preserve_context: bool = True
    max_depth: int = 5
```

#### Dependencies

| Component | Dependency | Integration Point |
|-----------|------------|-------------------|
| Transition | BaseTrigger | Polymorphic trigger evaluation |
| IntentTrigger | LLMAgentNode | LLM fallback for intent detection |
| ConditionTrigger | None | Lambda evaluation |
| ReturnToPrevious | PathwayStack | Stack-based navigation |

### 5.4 IntentTrigger / IntentDetector

#### Purpose and Responsibility
LLM-powered intent detection for pathway transitions with pattern matching fast-path.

#### Key Interfaces

```python
# File: kaizen/journey/intent.py

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from kaizen.signatures import Signature, InputField, OutputField


class IntentClassificationSignature(Signature):
    """Signature for LLM intent classification."""

    __intent__ = "Classify user intent from message"

    message: str = InputField(description="User message to classify")
    available_intents: str = InputField(description="JSON list of possible intents")
    context: str = InputField(description="Current conversation context", default="")

    intent: str = OutputField(description="Detected intent name or 'unknown'")
    confidence: float = OutputField(description="Confidence score 0.0-1.0")
    reasoning: str = OutputField(description="Brief explanation of classification")


@dataclass
class IntentMatch:
    """Result of intent detection."""
    intent: str
    confidence: float
    reasoning: str
    trigger: Optional["IntentTrigger"] = None


class IntentDetector:
    """
    LLM-powered intent detector with caching.

    Provides fast pattern matching with LLM fallback for complex cases.
    """

    def __init__(
        self,
        model: str = "gpt-4o-mini",
        cache_ttl_seconds: int = 300,
        confidence_threshold: float = 0.7
    ):
        self.model = model
        self.cache_ttl_seconds = cache_ttl_seconds
        self.confidence_threshold = confidence_threshold

        # Cache: message hash -> IntentMatch
        self._cache: Dict[str, IntentMatch] = {}
        self._cache_timestamps: Dict[str, float] = {}

    async def detect_intent(
        self,
        message: str,
        available_triggers: List["IntentTrigger"],
        context: Dict[str, Any]
    ) -> Optional[IntentMatch]:
        """
        Detect intent from message.

        Args:
            message: User message
            available_triggers: List of IntentTrigger to check
            context: Current context

        Returns:
            IntentMatch if intent detected, None otherwise
        """
        # Fast path: pattern matching
        for trigger in available_triggers:
            if trigger.evaluate(message, context):
                return IntentMatch(
                    intent=trigger.patterns[0] if trigger.patterns else "matched",
                    confidence=1.0,
                    reasoning="Pattern match",
                    trigger=trigger
                )

        # Check cache
        cache_key = self._cache_key(message, available_triggers)
        cached = self._get_cached(cache_key)
        if cached:
            return cached

        # LLM classification
        result = await self._llm_classify(message, available_triggers, context)

        # Cache result
        if result:
            self._cache[cache_key] = result
            import time
            self._cache_timestamps[cache_key] = time.time()

        return result

    async def _llm_classify(
        self,
        message: str,
        triggers: List["IntentTrigger"],
        context: Dict[str, Any]
    ) -> Optional[IntentMatch]:
        """Use LLM for intent classification."""
        from kaizen.core.base_agent import BaseAgent

        # Build intent list from triggers
        intent_list = []
        for t in triggers:
            intent_list.extend(t.patterns)

        # Create agent with classification signature
        agent = BaseAgent(
            config={"model": self.model, "llm_provider": "openai"},
            signature=IntentClassificationSignature()
        )

        # Execute classification
        import json
        result = await agent.run_async(
            message=message,
            available_intents=json.dumps(intent_list),
            context=json.dumps(context)
        )

        # Parse result
        confidence = float(result.get("confidence", 0.0))
        if confidence >= self.confidence_threshold:
            # Find matching trigger
            detected_intent = result.get("intent", "unknown")
            for t in triggers:
                if detected_intent in t.patterns:
                    return IntentMatch(
                        intent=detected_intent,
                        confidence=confidence,
                        reasoning=result.get("reasoning", ""),
                        trigger=t
                    )

        return None

    def _cache_key(self, message: str, triggers: List["IntentTrigger"]) -> str:
        """Generate cache key from message and triggers."""
        import hashlib
        patterns_str = "|".join(sorted(p for t in triggers for p in t.patterns))
        content = f"{message}:{patterns_str}"
        return hashlib.md5(content.encode()).hexdigest()

    def _get_cached(self, key: str) -> Optional[IntentMatch]:
        """Get cached result if not expired."""
        import time
        if key not in self._cache:
            return None

        timestamp = self._cache_timestamps.get(key, 0)
        if time.time() - timestamp > self.cache_ttl_seconds:
            del self._cache[key]
            del self._cache_timestamps[key]
            return None

        return self._cache[key]
```

#### Dependencies

| Component | Dependency | Integration Point |
|-----------|------------|-------------------|
| IntentDetector | BaseAgent | LLM classification |
| IntentDetector | IntentClassificationSignature | Structured output |
| IntentTrigger | IntentDetector | Delegate LLM evaluation |

### 5.5 PathwayManager

#### Purpose and Responsibility
Runtime manager for journey execution, handling pathway navigation, context accumulation, and state persistence.

#### Key Interfaces

```python
# File: kaizen/journey/manager.py

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Type
import asyncio


@dataclass
class JourneySession:
    """Active journey session state."""
    session_id: str
    journey_id: str
    current_pathway: str
    pathway_stack: List[str]  # For return navigation
    accumulated_context: Dict[str, Any]
    conversation_history: List[Dict[str, Any]]
    created_at: str
    updated_at: str


@dataclass
class JourneyResponse:
    """Response from journey message processing."""
    message: str  # Agent response
    pathway: str  # Current pathway after processing
    transition_occurred: bool
    transition_to: Optional[str]
    accumulated: Dict[str, Any]
    is_journey_complete: bool


class PathwayManager:
    """
    Runtime manager for journey execution.

    Handles:
    - Pathway navigation and transitions
    - Context accumulation across pathways
    - State persistence via DataFlow
    - Return-to-previous navigation
    """

    def __init__(
        self,
        journey: "Journey",
        session_id: str,
        config: "JourneyConfig"
    ):
        self.journey = journey
        self.session_id = session_id
        self.config = config

        # Runtime state
        self._session: Optional[JourneySession] = None
        self._pathway_instances: Dict[str, "Pathway"] = {}
        self._agent_registry: Dict[str, "BaseAgent"] = {}

        # Components
        self._intent_detector = IntentDetector(
            model=config.intent_detection_model,
            confidence_threshold=config.intent_confidence_threshold
        )
        self._context_accumulator = ContextAccumulator(
            max_size_bytes=config.max_context_size_bytes
        )
        self._state_manager: Optional["JourneyStateManager"] = None

    async def start_session(
        self,
        initial_context: Optional[Dict[str, Any]] = None
    ) -> JourneySession:
        """
        Start new journey session at entry pathway.

        Args:
            initial_context: Initial context values

        Returns:
            New JourneySession
        """
        from datetime import datetime

        self._session = JourneySession(
            session_id=self.session_id,
            journey_id=self.journey.__class__.__name__,
            current_pathway=self.journey.entry_pathway,
            pathway_stack=[],
            accumulated_context=initial_context or {},
            conversation_history=[],
            created_at=datetime.now().isoformat(),
            updated_at=datetime.now().isoformat()
        )

        # Persist initial state
        await self._persist_session()

        return self._session

    async def process_message(self, message: str) -> JourneyResponse:
        """
        Process user message in current pathway.

        1. Check for transition triggers
        2. Execute current pathway if no transition
        3. Handle transition if triggered
        4. Accumulate context
        5. Persist state

        Args:
            message: User input message

        Returns:
            JourneyResponse with agent response and state
        """
        if not self._session:
            raise RuntimeError("Session not started. Call start_session() first.")

        # Step 1: Check for transitions
        transition = await self._check_transitions(message)

        if transition:
            # Step 2a: Handle transition
            response = await self._handle_transition(transition, message)
        else:
            # Step 2b: Execute current pathway
            response = await self._execute_current_pathway(message)

        # Step 3: Update conversation history
        self._session.conversation_history.append({
            "role": "user",
            "content": message
        })
        self._session.conversation_history.append({
            "role": "assistant",
            "content": response.message
        })

        # Step 4: Persist state
        await self._persist_session()

        return response

    async def _check_transitions(self, message: str) -> Optional[Transition]:
        """Check if any transition should trigger."""
        # Get all applicable triggers
        triggers = [
            t.trigger for t in self.journey.transitions
            if t.from_pathway == "*" or t.from_pathway == self._session.current_pathway
        ]

        # Detect intent
        intent_match = await self._intent_detector.detect_intent(
            message=message,
            available_triggers=[t for t in triggers if isinstance(t, IntentTrigger)],
            context=self._session.accumulated_context
        )

        if intent_match and intent_match.trigger:
            # Find matching transition
            for transition in self.journey.transitions:
                if transition.trigger == intent_match.trigger:
                    if transition.matches(
                        self._session.current_pathway,
                        message,
                        self._session.accumulated_context
                    ):
                        return transition

        # Check condition triggers
        for transition in self.journey.transitions:
            if isinstance(transition.trigger, ConditionTrigger):
                if transition.matches(
                    self._session.current_pathway,
                    message,
                    self._session.accumulated_context
                ):
                    return transition

        return None

    async def _handle_transition(
        self,
        transition: Transition,
        message: str
    ) -> JourneyResponse:
        """Handle pathway transition."""
        from_pathway = self._session.current_pathway
        to_pathway = transition.to_pathway

        # Get target pathway class
        target_class = self.journey.pathways.get(to_pathway)
        if not target_class:
            raise ValueError(f"Target pathway '{to_pathway}' not found")

        # Check for return behavior (detour handling)
        if target_class._return_behavior:
            # Push current pathway to stack
            self._session.pathway_stack.append(from_pathway)
            if len(self._session.pathway_stack) > self.config.max_pathway_depth:
                raise RuntimeError(f"Pathway stack overflow (max depth: {self.config.max_pathway_depth})")

        # Update current pathway
        self._session.current_pathway = to_pathway

        # Execute new pathway
        result = await self._execute_pathway(to_pathway, message)

        # Apply context update from transition
        if transition.context_update:
            self._session.accumulated_context = transition.apply_context_update(
                self._session.accumulated_context,
                result.outputs
            )

        # Check if return to previous needed
        target_instance = self._get_pathway_instance(to_pathway)
        if target_instance.return_behavior and result.is_complete:
            await self._return_to_previous()

        return JourneyResponse(
            message=result.outputs.get("response", ""),
            pathway=self._session.current_pathway,
            transition_occurred=True,
            transition_to=to_pathway,
            accumulated=self._session.accumulated_context,
            is_journey_complete=False
        )

    async def _return_to_previous(self):
        """Return to previous pathway from stack."""
        if self._session.pathway_stack:
            previous = self._session.pathway_stack.pop()
            self._session.current_pathway = previous

    async def _execute_current_pathway(self, message: str) -> JourneyResponse:
        """Execute current pathway without transition."""
        result = await self._execute_pathway(
            self._session.current_pathway,
            message
        )

        # Accumulate context
        self._session.accumulated_context = self._context_accumulator.merge(
            self._session.accumulated_context,
            result.accumulated
        )

        # Check for default next pathway
        if result.next_pathway and result.is_complete:
            self._session.current_pathway = result.next_pathway

        return JourneyResponse(
            message=result.outputs.get("response", ""),
            pathway=self._session.current_pathway,
            transition_occurred=False,
            transition_to=None,
            accumulated=self._session.accumulated_context,
            is_journey_complete=not result.next_pathway and result.is_complete
        )

    async def _execute_pathway(
        self,
        pathway_id: str,
        message: str
    ) -> "PathwayResult":
        """Execute a specific pathway."""
        pathway = self._get_pathway_instance(pathway_id)

        context = PathwayContext(
            session_id=self.session_id,
            pathway_id=pathway_id,
            user_message=message,
            accumulated_context=self._session.accumulated_context,
            conversation_history=self._session.conversation_history
        )

        return await pathway.execute(context)

    def _get_pathway_instance(self, pathway_id: str) -> "Pathway":
        """Get or create pathway instance."""
        if pathway_id not in self._pathway_instances:
            pathway_class = self.journey.pathways.get(pathway_id)
            if not pathway_class:
                raise ValueError(f"Pathway '{pathway_id}' not found")
            self._pathway_instances[pathway_id] = pathway_class(self)
        return self._pathway_instances[pathway_id]

    def get_agent(self, agent_id: str) -> "BaseAgent":
        """Get registered agent by ID."""
        if agent_id not in self._agent_registry:
            raise ValueError(f"Agent '{agent_id}' not registered")
        return self._agent_registry[agent_id]

    def register_agent(self, agent_id: str, agent: "BaseAgent"):
        """Register agent for pathway use."""
        self._agent_registry[agent_id] = agent

    async def _persist_session(self):
        """Persist session state to storage."""
        if self._state_manager:
            await self._state_manager.save_session(self._session)
```

#### Dependencies

| Component | Dependency | Integration Point |
|-----------|------------|-------------------|
| PathwayManager | Journey | Parent journey definition |
| PathwayManager | IntentDetector | Intent-based transitions |
| PathwayManager | ContextAccumulator | Cross-pathway state |
| PathwayManager | JourneyStateManager | State persistence |
| PathwayManager | Pathway | Pathway execution |

### 5.6 ContextAccumulator

#### Purpose and Responsibility
Manages cross-pathway context persistence with merge semantics, versioning, and size limits.

#### Key Interfaces

```python
# File: kaizen/journey/context.py

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
import json


@dataclass
class ContextVersion:
    """Version record for context changes."""
    version: int
    pathway: str
    timestamp: str
    changes: Dict[str, Any]


class ContextAccumulator:
    """
    Cross-pathway context accumulation with merge semantics.

    Supports:
    - Field-level merging
    - List append for array fields
    - Size limiting to prevent overflow
    - Version history for debugging
    """

    def __init__(
        self,
        max_size_bytes: int = 1024 * 1024,
        max_versions: int = 100
    ):
        self.max_size_bytes = max_size_bytes
        self.max_versions = max_versions
        self._versions: List[ContextVersion] = []

    def merge(
        self,
        base: Dict[str, Any],
        updates: Dict[str, Any],
        pathway: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Merge updates into base context.

        Merge semantics:
        - Scalar values: Replace
        - Lists: Append (deduplicated)
        - Dicts: Deep merge

        Args:
            base: Base context
            updates: Updates to merge
            pathway: Pathway that produced updates (for versioning)

        Returns:
            Merged context

        Raises:
            ValueError: If result exceeds max size
        """
        result = self._deep_merge(base.copy(), updates)

        # Check size
        size = len(json.dumps(result))
        if size > self.max_size_bytes:
            raise ValueError(
                f"Context size ({size} bytes) exceeds limit ({self.max_size_bytes} bytes)"
            )

        # Record version
        if pathway:
            from datetime import datetime
            self._versions.append(ContextVersion(
                version=len(self._versions) + 1,
                pathway=pathway,
                timestamp=datetime.now().isoformat(),
                changes=updates
            ))

            # Trim old versions
            if len(self._versions) > self.max_versions:
                self._versions = self._versions[-self.max_versions:]

        return result

    def _deep_merge(
        self,
        base: Dict[str, Any],
        updates: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Deep merge two dictionaries."""
        for key, value in updates.items():
            if key in base:
                base_value = base[key]

                if isinstance(base_value, list) and isinstance(value, list):
                    # Append and deduplicate
                    combined = base_value + value
                    # Preserve order, remove duplicates for hashable items
                    seen = set()
                    deduped = []
                    for item in combined:
                        try:
                            if item not in seen:
                                seen.add(item)
                                deduped.append(item)
                        except TypeError:
                            # Unhashable item, keep it
                            deduped.append(item)
                    base[key] = deduped

                elif isinstance(base_value, dict) and isinstance(value, dict):
                    # Deep merge
                    base[key] = self._deep_merge(base_value, value)

                else:
                    # Replace
                    base[key] = value
            else:
                base[key] = value

        return base

    def get_versions(self) -> List[ContextVersion]:
        """Get version history."""
        return self._versions.copy()

    def rollback_to_version(
        self,
        base: Dict[str, Any],
        target_version: int
    ) -> Dict[str, Any]:
        """
        Rollback context to a specific version.

        Args:
            base: Current context (to replay from empty)
            target_version: Version number to rollback to

        Returns:
            Context at target version
        """
        result = {}

        for version in self._versions:
            if version.version > target_version:
                break
            result = self._deep_merge(result, version.changes)

        return result
```

#### Dependencies

| Component | Dependency | Integration Point |
|-----------|------------|-------------------|
| ContextAccumulator | None | Standalone utility |
| PathwayManager | ContextAccumulator | Context merge operations |

---

## 6. Integration Architecture

### 6.1 Integration with Existing Kaizen Components

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              LAYER 5: JOURNEY                                    │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐│
│  │   Journey   │  │   Pathway   │  │ Transition  │  │    PathwayManager       ││
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘  └───────────┬─────────────┘│
│         │                │                │                      │              │
│         │                │                │                      │              │
└─────────┼────────────────┼────────────────┼──────────────────────┼──────────────┘
          │                │                │                      │
          ▼                ▼                ▼                      ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              LAYER 4: ORCHESTRATION                              │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────────────────────┐ │
│  │  Pipeline   │◀─│ Pathway     │  │      OrchestrationStateManager         │ │
│  │  Patterns   │  │ _pipeline   │  │      (DataFlow persistence)            │ │
│  └─────────────┘  └─────────────┘  └─────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────────────┘
          │                                          │
          ▼                                          ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              LAYER 3: AGENTS                                     │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐│
│  │  BaseAgent  │◀─│ Pathway     │  │ A2AAgentCard│  │    IntentDetector       ││
│  │             │  │ _agents     │  │             │  │    (LLM classification) ││
│  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────────────────┘│
└─────────────────────────────────────────────────────────────────────────────────┘
          │                                          │
          ▼                                          ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              LAYER 2: SIGNATURE                                  │
│  ┌─────────────────────────────────────────────────────────────────────────────┐│
│  │  Signature (enhanced with __intent__, __guidelines__)                       ││
│  │  ├── _signature_intent: str                                                 ││
│  │  ├── _signature_guidelines: List[str]                                       ││
│  │  ├── with_instructions(str) -> Signature                                    ││
│  │  └── with_guidelines(List[str]) -> Signature                                ││
│  └─────────────────────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────────────────────┘
          │
          ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              LAYER 1: FOUNDATION                                 │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────────────────────┐ │
│  │ Workflow    │  │ Async       │  │          DataFlow                       │ │
│  │ Builder     │  │ LocalRuntime│  │          (persistence)                  │ │
│  └─────────────┘  └─────────────┘  └─────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────────────┘
```

### 6.2 Module Organization

```
kaizen/
├── journey/                     # Layer 5: Journey Orchestration
│   ├── __init__.py              # Public API exports
│   ├── core.py                  # Journey, Pathway, JourneyMeta, PathwayMeta
│   ├── transitions.py           # Transition, BaseTrigger, IntentTrigger, ConditionTrigger
│   ├── intent.py                # IntentDetector, IntentMatch, IntentClassificationSignature
│   ├── manager.py               # PathwayManager, JourneySession, JourneyResponse
│   ├── context.py               # ContextAccumulator, ContextVersion
│   ├── state.py                 # JourneyStateManager (DataFlow integration)
│   └── behaviors.py             # ReturnToPrevious, other return behaviors
├── signatures/
│   └── core.py                  # Enhanced Signature (add __intent__, __guidelines__)
```

### 6.3 Reusable Components Analysis

| Component | Reuse Strategy | Notes |
|-----------|----------------|-------|
| Pipeline patterns | Direct reuse | Pathway._build_pipeline() uses existing patterns |
| OrchestrationStateManager | Extend | Add JourneyState, PathwayExecutionRecord models |
| SharedMemoryPool | Direct reuse | Context accumulator can use for caching |
| BaseAgent | Direct reuse | Pathways resolve to BaseAgent instances |
| IntentClassificationSignature | New | Purpose-built for intent detection |
| LLMAgentNode | Direct reuse | Powers IntentDetector |

---

## 7. Healthcare Referral Use Case

### 7.1 Complete Implementation

```python
# File: examples/5-journey/healthcare_referral.py

from kaizen.journey import Journey, Pathway, Transition, IntentTrigger, ReturnToPrevious
from kaizen.signatures import Signature, InputField, OutputField


# ============================================================================
# SIGNATURES
# ============================================================================

class IntakeSignature(Signature):
    """Collect patient information and referral documents."""

    __intent__ = "Gather patient details and validate referral eligibility"
    __guidelines__ = [
        "Verify insurance information before proceeding",
        "Ask for all required documents upfront",
        "Flag any eligibility concerns immediately"
    ]

    patient_message: str = InputField(description="Patient input")
    documents: str = InputField(description="Uploaded documents", default="")

    response: str = OutputField(description="Acknowledgment and next steps")
    patient_info: dict = OutputField(description="Extracted patient information")
    eligibility_status: str = OutputField(description="eligible|pending|ineligible")


class BookingSignature(Signature):
    """Find and book specialist appointment."""

    __intent__ = "Match patient with best available specialist"
    __guidelines__ = [
        "Prioritize patient preferences (location, time, gender)",
        "Explain why each doctor is a good match",
        "Track rejected doctors to avoid re-suggesting"
    ]

    patient_message: str = InputField(description="Patient input")
    preferences: dict = InputField(description="Patient preferences", default={})
    rejected_doctors: list = InputField(description="Previously rejected doctors", default=[])

    response: str = OutputField(description="Doctor recommendations or confirmation")
    selected_doctor: dict = OutputField(description="Selected doctor details")
    available_slots: list = OutputField(description="Available appointment slots")


class FAQSignature(Signature):
    """Answer patient questions about the referral process."""

    __intent__ = "Provide clear, helpful answers to patient questions"
    __guidelines__ = [
        "Answer concisely but completely",
        "Cite relevant policy when applicable",
        "Offer to return to booking when question is answered"
    ]

    question: str = InputField(description="Patient question")
    context: str = InputField(description="Current booking context", default="")

    response: str = OutputField(description="Answer to the question")
    follow_up_needed: bool = OutputField(description="Whether follow-up is needed")


class PersuasionSignature(Signature):
    """Persuade hesitant patient to complete booking."""

    __intent__ = "Address concerns and encourage booking completion"
    __guidelines__ = [
        "Acknowledge the patient's hesitation",
        "Provide reassurance based on their specific concerns",
        "Never pressure - always respect patient autonomy"
    ]

    patient_message: str = InputField(description="Patient hesitation/concern")
    rejected_doctors: list = InputField(description="Previously rejected options")

    response: str = OutputField(description="Reassuring response")
    resolution: str = OutputField(description="resolved|needs_alternatives|escalate")


class ConfirmationSignature(Signature):
    """Confirm appointment and provide next steps."""

    __intent__ = "Finalize booking and ensure patient is informed"
    __guidelines__ = [
        "Summarize all appointment details",
        "Provide preparation instructions",
        "Offer easy rescheduling options"
    ]

    booking_details: dict = InputField(description="Confirmed booking details")

    response: str = OutputField(description="Confirmation message")
    confirmation_number: str = OutputField(description="Booking confirmation number")


# ============================================================================
# JOURNEY DEFINITION
# ============================================================================

class HealthcareReferralJourney(Journey):
    """Complete healthcare referral booking journey."""

    __entry_pathway__ = "intake"

    class IntakePath(Pathway):
        """Patient intake and document collection."""
        __signature__ = IntakeSignature
        __agents__ = ["document_processor", "eligibility_checker"]
        __pipeline__ = "sequential"
        __accumulate__ = ["patient_info", "eligibility_status"]
        __next__ = "booking"

    class BookingPath(Pathway):
        """Doctor matching and appointment booking."""
        __signature__ = BookingSignature
        __agents__ = ["slot_finder", "doctor_matcher", "preference_analyzer"]
        __pipeline__ = "parallel"
        __accumulate__ = ["rejected_doctors", "preferences", "selected_doctor"]
        __next__ = "confirmation"

    class FAQPath(Pathway):
        """Answer patient questions (detour pathway)."""
        __signature__ = FAQSignature
        __agents__ = ["rag_faq_agent"]
        __pipeline__ = "sequential"
        __return_behavior__ = ReturnToPrevious()

    class PersuasionPath(Pathway):
        """Handle hesitant patients."""
        __signature__ = PersuasionSignature
        __agents__ = ["persuasion_agent"]
        __pipeline__ = "sequential"
        __next__ = "booking"  # Return to booking after persuasion

    class ConfirmationPath(Pathway):
        """Final confirmation and next steps."""
        __signature__ = ConfirmationSignature
        __agents__ = ["confirmation_agent"]
        __pipeline__ = "sequential"
        # No __next__ - journey ends here

    # Transition rules
    __transitions__ = [
        # FAQ detour: Any pathway -> FAQ (return to previous after)
        Transition(
            trigger=IntentTrigger(patterns=["question", "help", "what is", "how do I", "why"]),
            from_pathway="*",
            to_pathway="faq",
            priority=10
        ),

        # Doctor rejection: Stay in booking, track rejected doctor
        Transition(
            trigger=IntentTrigger(patterns=["different doctor", "another option", "don't want"]),
            from_pathway="booking",
            to_pathway="booking",
            context_update={"rejected_doctors": "append:selected_doctor"},
            priority=5
        ),

        # Hesitation detection: Booking -> Persuasion
        Transition(
            trigger=IntentTrigger(patterns=["not sure", "maybe later", "let me think", "hesitant"]),
            from_pathway="booking",
            to_pathway="persuasion",
            priority=5
        ),

        # Escalation: Any pathway -> Escalation (not shown for brevity)
        Transition(
            trigger=ConditionTrigger(condition=lambda ctx: ctx.get("escalation_count", 0) >= 3),
            from_pathway="*",
            to_pathway="escalation",
            priority=100
        ),
    ]


# ============================================================================
# USAGE EXAMPLE
# ============================================================================

async def main():
    from kaizen.agents import SimpleQAAgent, RAGResearchAgent
    from dataclasses import dataclass

    # Configure agents
    @dataclass
    class AgentConfig:
        llm_provider: str = "openai"
        model: str = "gpt-4o"

    # Create journey instance
    journey = HealthcareReferralJourney(session_id="patient_12345")

    # Register agents
    journey.manager.register_agent("document_processor", SimpleQAAgent(AgentConfig()))
    journey.manager.register_agent("eligibility_checker", SimpleQAAgent(AgentConfig()))
    journey.manager.register_agent("slot_finder", SimpleQAAgent(AgentConfig()))
    journey.manager.register_agent("doctor_matcher", SimpleQAAgent(AgentConfig()))
    journey.manager.register_agent("preference_analyzer", SimpleQAAgent(AgentConfig()))
    journey.manager.register_agent("rag_faq_agent", RAGResearchAgent(AgentConfig()))
    journey.manager.register_agent("persuasion_agent", SimpleQAAgent(AgentConfig()))
    journey.manager.register_agent("confirmation_agent", SimpleQAAgent(AgentConfig()))

    # Start journey
    session = await journey.start(initial_context={
        "insurance_id": "INS-123456",
        "referral_source": "primary_care"
    })

    # Simulate conversation
    print("=== Healthcare Referral Journey ===\n")

    # Turn 1: Intake
    response = await journey.process_message(
        "Hi, I need to book an appointment with a cardiologist. Here's my referral."
    )
    print(f"[{response.pathway}] Assistant: {response.message}\n")

    # Turn 2: FAQ detour
    response = await journey.process_message(
        "Wait, what is the copay for specialist visits?"
    )
    print(f"[{response.pathway}] Assistant: {response.message}")
    print(f"  (Transition: {response.transition_to})\n")

    # Turn 3: Back to booking (automatically)
    response = await journey.process_message(
        "Thanks! Now show me the available doctors."
    )
    print(f"[{response.pathway}] Assistant: {response.message}\n")

    # Turn 4: Reject a doctor
    response = await journey.process_message(
        "I don't want Dr. Smith. Can you show me another option?"
    )
    print(f"[{response.pathway}] Assistant: {response.message}")
    print(f"  Accumulated rejected_doctors: {response.accumulated.get('rejected_doctors')}\n")

    # Turn 5: Confirm booking
    response = await journey.process_message(
        "Dr. Johnson looks great. Book the Tuesday 2pm slot."
    )
    print(f"[{response.pathway}] Assistant: {response.message}")
    print(f"  Journey complete: {response.is_journey_complete}")


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
```

### 7.2 Test Scenarios

```python
# File: tests/unit/journey/test_healthcare_referral.py

import pytest
from kaizen.journey import Journey, Pathway, Transition, IntentTrigger


class TestHealthcareReferralJourney:
    """Test suite for Healthcare Referral Journey."""

    # Intent Detection Tests
    @pytest.mark.asyncio
    async def test_faq_intent_triggers_transition(self):
        """FAQ intent should trigger transition from any pathway."""
        journey = HealthcareReferralJourney(session_id="test")
        await journey.start()

        # Simulate question during booking
        journey.manager._session.current_pathway = "booking"
        response = await journey.process_message("What is the copay?")

        assert response.transition_occurred
        assert response.transition_to == "faq"

    @pytest.mark.asyncio
    async def test_return_to_previous_after_faq(self):
        """After FAQ, should return to previous pathway."""
        journey = HealthcareReferralJourney(session_id="test")
        await journey.start()

        # Go through intake -> booking
        journey.manager._session.current_pathway = "booking"

        # FAQ detour
        await journey.process_message("What is the copay?")
        assert journey.manager._session.current_pathway == "faq"

        # Answer should return to booking
        await journey.process_message("Thanks for the info")
        assert journey.manager._session.current_pathway == "booking"

    # Context Accumulation Tests
    @pytest.mark.asyncio
    async def test_rejected_doctors_accumulate(self):
        """Rejected doctors should accumulate across turns."""
        journey = HealthcareReferralJourney(session_id="test")
        await journey.start()

        journey.manager._session.current_pathway = "booking"
        journey.manager._session.accumulated_context = {"selected_doctor": {"id": "dr1"}}

        # Reject first doctor
        await journey.process_message("I don't want this doctor")

        assert "rejected_doctors" in journey.manager._session.accumulated_context
        assert {"id": "dr1"} in journey.manager._session.accumulated_context["rejected_doctors"]

    # Pathway Execution Tests
    @pytest.mark.asyncio
    async def test_intake_proceeds_to_booking(self):
        """Successful intake should proceed to booking."""
        journey = HealthcareReferralJourney(session_id="test")
        await journey.start()

        # Complete intake
        response = await journey.process_message("Here's my referral and insurance info")

        # Should proceed to booking
        assert journey.manager._session.current_pathway == "booking"

    # Edge Cases
    @pytest.mark.asyncio
    async def test_pathway_stack_overflow_protection(self):
        """Should prevent deep pathway nesting."""
        journey = HealthcareReferralJourney(session_id="test")
        journey.config.max_pathway_depth = 3
        await journey.start()

        # Manually create deep nesting
        journey.manager._session.pathway_stack = ["a", "b", "c"]
        journey.manager._session.current_pathway = "faq"

        # Should raise on further nesting
        with pytest.raises(RuntimeError, match="stack overflow"):
            await journey.process_message("Another question")

    @pytest.mark.asyncio
    async def test_ambiguous_intent_uses_llm(self):
        """Ambiguous messages should use LLM for classification."""
        journey = HealthcareReferralJourney(session_id="test")
        await journey.start()

        # Ambiguous message (doesn't match patterns exactly)
        response = await journey.process_message(
            "I'm wondering about the process"  # Could be FAQ or hesitation
        )

        # Should have used LLM (verify via mock or logs)
        # This test would require mocking the LLM call
        assert response.message  # Should have a response
```

---

## 8. Risk Assessment

### 8.1 Critical Risks (Mitigate Immediately)

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Intent detection latency | High | High | Implement caching, pattern matching fast-path |
| Pathway stack overflow | Medium | High | Enforce max depth, detect cycles |
| Context size explosion | Medium | High | Size limits, automatic pruning |
| State persistence failures | Low | Critical | Retry logic, graceful degradation |

### 8.2 Medium Risks (Monitor)

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Ambiguous intent classification | High | Medium | LLM fallback, confidence thresholds |
| Agent registration errors | Medium | Medium | Validation at journey start |
| Memory leaks in long sessions | Medium | Medium | Session timeout, cleanup hooks |
| Breaking changes to Pipeline API | Low | Medium | Adapter layer for isolation |

### 8.3 Low Risks (Accept)

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Metaclass complexity | Low | Low | Comprehensive documentation, examples |
| Learning curve for Journey DSL | Medium | Low | Migration guide, IDE support |

---

## 9. Implementation Roadmap

### Phase 1: Foundation (2 weeks)
**Focus**: Layer 2 Signature enhancements + core Journey infrastructure

| Task | Effort | Deliverables |
|------|--------|--------------|
| Enhance SignatureMeta for __intent__/__guidelines__ | 2 days | Updated core.py |
| Add with_instructions()/with_guidelines() methods | 1 day | Immutable composition |
| Implement JourneyMeta and PathwayMeta | 3 days | journey/core.py |
| Create Transition and trigger classes | 2 days | journey/transitions.py |
| Unit tests for Phase 1 | 2 days | 95%+ coverage |

### Phase 2: Intent Detection (1.5 weeks)
**Focus**: IntentDetector with LLM integration and caching

| Task | Effort | Deliverables |
|------|--------|--------------|
| Implement IntentDetector | 3 days | journey/intent.py |
| Create IntentClassificationSignature | 1 day | Structured output schema |
| Add caching layer | 1 day | Cache with TTL |
| Integration tests with real LLM | 2 days | Tier 2/3 tests |

### Phase 3: PathwayManager (2 weeks)
**Focus**: Runtime orchestration and context management

| Task | Effort | Deliverables |
|------|--------|--------------|
| Implement PathwayManager | 4 days | journey/manager.py |
| Create ContextAccumulator | 2 days | journey/context.py |
| Add return-to-previous navigation | 1 day | PathwayStack |
| Integrate with OrchestrationStateManager | 2 days | DataFlow persistence |
| Integration tests | 3 days | E2E journey execution |

### Phase 4: Healthcare Use Case (1 week)
**Focus**: Complete example and documentation

| Task | Effort | Deliverables |
|------|--------|--------------|
| Implement HealthcareReferralJourney | 2 days | Complete example |
| Create all signature classes | 1 day | Domain signatures |
| Write comprehensive tests | 2 days | All scenarios covered |
| Documentation and guides | 2 days | User documentation |

### Total Estimated Effort: 6.5 weeks

---

## 10. Consequences

### 10.1 Positive

1. **Declarative Journey Definition**: Developers can define complex user journeys as class hierarchies
2. **Intent-Driven Transitions**: LLM-powered intent detection enables natural conversation flow
3. **Context Persistence**: Cross-pathway state accumulation with versioning and rollback
4. **Return-to-Previous**: Detour handling (FAQ, help) without losing context
5. **Layer 4 Reuse**: Pathways leverage existing Pipeline patterns for agent coordination
6. **Signature Enhancement**: __intent__ and __guidelines__ provide explicit behavioral contracts

### 10.2 Negative

1. **Complexity**: Metaclass-based DSL adds learning curve
2. **LLM Dependency**: Intent detection requires LLM calls (mitigated by caching)
3. **State Management**: Cross-pathway context requires careful size management
4. **Testing Complexity**: Journey testing requires mocking multiple pathways

### 10.3 Trade-offs Accepted

1. **DSL over Configuration**: Class-based DSL chosen over YAML/JSON for IDE support
2. **LLM over Rules**: Intent detection uses LLM for flexibility over rule-based systems
3. **DataFlow over Custom**: State persistence uses existing DataFlow integration

---

## 11. Alternatives Considered

### 11.1 YAML-Based Journey Definition

```yaml
journey:
  entry: intake
  pathways:
    intake:
      signature: IntakeSignature
      agents: [document_processor]
      next: booking
```

**Rejected Because**:
- No IDE autocomplete or type checking
- Harder to debug
- No runtime composition methods

### 11.2 Rule-Based Intent Detection

```python
class IntentRule:
    patterns: List[str]
    priority: int

    def match(self, message: str) -> bool:
        return any(p in message.lower() for p in self.patterns)
```

**Rejected Because**:
- Cannot handle paraphrasing or complex queries
- Requires exhaustive pattern lists
- Poor generalization to new intents

### 11.3 Separate Journey and Pathway Classes (Non-Nested)

```python
class IntakePath(Pathway):
    ...

class BookingPath(Pathway):
    ...

journey = Journey(
    pathways=[IntakePath, BookingPath],
    transitions=[...]
)
```

**Rejected Because**:
- Loses co-location of pathway definitions
- Harder to see journey structure at a glance
- More boilerplate for simple journeys

---

## Appendix A: API Reference Summary

### Layer 2 Signature Enhancements

| Component | Method/Property | Description |
|-----------|-----------------|-------------|
| Signature | __intent__ | Class attribute for intent declaration |
| Signature | __guidelines__ | Class attribute for behavioral guidelines |
| Signature | intent | Property to access intent |
| Signature | guidelines | Property to access guidelines (copy) |
| Signature | instructions | Property for DSPy compatibility |
| Signature | with_instructions() | Create new signature with modified instructions |
| Signature | with_guidelines() | Create new signature with additional guidelines |

### Layer 5 Journey Components

| Component | Purpose | Key Methods |
|-----------|---------|-------------|
| Journey | Declarative journey container | start(), process_message() |
| Pathway | Journey phase with agents | execute() |
| Transition | Pathway switching rule | matches(), apply_context_update() |
| IntentTrigger | LLM intent detection | evaluate() |
| ConditionTrigger | Context condition check | evaluate() |
| IntentDetector | LLM classification engine | detect_intent() |
| PathwayManager | Runtime orchestration | start_session(), process_message() |
| ContextAccumulator | Cross-pathway state | merge(), rollback_to_version() |
| ReturnToPrevious | Detour behavior | (used as flag) |

---

## Appendix B: File Structure

```
kaizen/
├── signatures/
│   └── core.py                  # MODIFIED: Add __intent__, __guidelines__
│
└── journey/                     # NEW: Layer 5 module
    ├── __init__.py              # Public exports
    ├── core.py                  # Journey, Pathway, JourneyMeta, PathwayMeta
    ├── transitions.py           # Transition, BaseTrigger, IntentTrigger, ConditionTrigger
    ├── intent.py                # IntentDetector, IntentMatch
    ├── manager.py               # PathwayManager, JourneySession, JourneyResponse
    ├── context.py               # ContextAccumulator, ContextVersion
    ├── state.py                 # JourneyStateManager
    └── behaviors.py             # ReturnToPrevious
```

---

## Document History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0.0 | 2026-01-12 | Requirements Analyst | Initial ADR creation |
