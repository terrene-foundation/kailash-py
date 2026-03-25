# Healthcare Referral Journey Example

A comprehensive reference implementation demonstrating **Layer 5 Journey Orchestration** in the Kaizen AI framework. This example shows how to build a multi-pathway healthcare referral conversation system with intelligent intent detection, context accumulation, and dynamic pathway transitions.

## Overview

The Healthcare Referral Journey guides patients through a complete specialist booking process:

```
[Patient] --> [Intake] --> [Booking] --> [Confirmation]
                 |            |
                 v            v
              [FAQ]      [Persuasion]
            (detour)     (hesitation)
```

### Key Features Demonstrated

1. **Multi-Pathway Navigation**: 5 interconnected pathways with clear transitions
2. **Intent-Driven Transitions**: Pattern matching + LLM fallback for robust intent detection
3. **Context Accumulation**: Symptoms, preferences, and rejected doctors persist across turns
4. **Return Behaviors**: FAQ pathway returns to previous location preserving context
5. **Conditional Transitions**: State-based transitions (e.g., `ready_for_booking == True`)
6. **Global Transitions**: FAQ and cancellation accessible from any pathway

## Architecture

### Pathways

| Pathway | Purpose | Transition To |
|---------|---------|---------------|
| **Intake** | Collect symptoms, severity, preferences, insurance | Booking (when ready) |
| **Booking** | Find specialists, handle rejections, book slot | Confirmation (when complete) |
| **FAQ** | Answer healthcare questions | Returns to previous |
| **Persuasion** | Address hesitations empathetically | Back to Booking |
| **Confirmation** | Summarize and confirm appointment | End |

### Transitions

```python
# Global - accessible from any pathway
FAQ:          IntentTrigger(["what is", "how does", "explain", ...])
Cancellation: IntentTrigger(["cancel", "stop", "quit", ...])

# Conditional - state-based
Intake->Booking:       ConditionTrigger("ready_for_booking")
Booking->Confirmation: ConditionTrigger("booking_complete")

# Pathway-specific
Booking->Persuasion:   IntentTrigger(["not sure", "maybe later", ...])
```

### Context Accumulation

```python
class IntakePath(Pathway):
    __accumulate__ = ["symptoms", "severity", "preferences", "insurance_info"]

class BookingPath(Pathway):
    __accumulate__ = ["rejected_doctors", "selected_doctor", "selected_slot"]
```

## Installation

```bash
# Ensure you have Kaizen installed
pip install kailash-kaizen

# Clone or navigate to the examples directory
cd packages/kailash-kaizen/examples/journey/healthcare_referral
```

## Quick Start

### Demo Mode (Scripted Conversation)

```bash
# With OpenAI (default)
export OPENAI_API_KEY="your-key"
python -m examples.journey.healthcare_referral.main

# With Ollama (free, local)
ollama pull llama3.2:3b
python -m examples.journey.healthcare_referral.main --provider ollama --model llama3.2:3b
```

### Interactive Mode

```bash
# Chat directly with the healthcare referral system
python -m examples.journey.healthcare_referral.main --interactive
```

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `OPENAI_API_KEY` | OpenAI API key | Required for OpenAI |
| `KAIZEN_LLM_PROVIDER` | LLM provider | `openai` |
| `KAIZEN_MODEL` | Model name | `gpt-4o` |

## Project Structure

```
healthcare_referral/
├── __init__.py              # Package exports
├── journey.py               # Journey definition with 5 pathways
├── main.py                  # Demo and interactive modes
├── README.md                # This documentation
│
├── signatures/              # Type-safe agent interfaces
│   ├── __init__.py
│   ├── intake.py            # IntakeSignature
│   ├── booking.py           # BookingSignature
│   ├── faq.py               # FAQSignature
│   ├── persuasion.py        # PersuasionSignature
│   └── confirmation.py      # ConfirmationSignature
│
├── agents/                  # Agent implementations
│   ├── __init__.py
│   ├── intake_agent.py      # Symptom collection
│   ├── booking_agent.py     # Doctor matching + MockDoctorDatabase
│   ├── faq_agent.py         # Question answering
│   ├── persuasion_agent.py  # Hesitation handling
│   └── confirmation_agent.py # Booking confirmation
│
└── tests/                   # Comprehensive test suite
    ├── __init__.py
    ├── test_journey.py      # Unit tests (Tier 1)
    ├── test_transitions.py  # Transition detection tests
    ├── test_integration.py  # Integration tests with Ollama (Tier 2)
    └── test_e2e.py          # E2E tests with OpenAI (Tier 3)
```

## Usage Examples

### Programmatic Usage

```python
import asyncio
from examples.journey.healthcare_referral.journey import (
    HealthcareReferralJourney,
    default_config,
)
from examples.journey.healthcare_referral.agents import (
    IntakeAgent, IntakeAgentConfig,
    BookingAgent, BookingAgentConfig,
    FAQAgent, FAQAgentConfig,
    PersuasionAgent, PersuasionAgentConfig,
    ConfirmationAgent, ConfirmationAgentConfig,
)

async def main():
    # Create journey
    journey = HealthcareReferralJourney(
        session_id="patient-001",
        config=default_config,
    )

    # Register agents
    journey.register_agent("intake_agent", IntakeAgent(IntakeAgentConfig()))
    journey.register_agent("booking_agent", BookingAgent(BookingAgentConfig()))
    journey.register_agent("faq_agent", FAQAgent(FAQAgentConfig()))
    journey.register_agent("persuasion_agent", PersuasionAgent(PersuasionAgentConfig()))
    journey.register_agent("confirmation_agent", ConfirmationAgent(ConfirmationAgentConfig()))

    # Start session
    session = await journey.start()
    print(f"Started at: {session.current_pathway_id}")  # "intake"

    # Process messages
    response = await journey.process_message(
        "I've been having back pain for two weeks"
    )
    print(f"Response: {response.message}")
    print(f"Pathway: {response.pathway_id}")
    print(f"Context: {response.accumulated_context}")

asyncio.run(main())
```

### Custom Doctor Database

```python
from typing import Protocol, List, Dict, Any

class DoctorDatabase(Protocol):
    async def find_specialists(
        self,
        symptoms: List[str],
        preferences: Dict[str, Any],
        exclude_ids: List[str],
    ) -> List[Dict[str, Any]]:
        ...

# Implement your own database
class RealDoctorDatabase:
    async def find_specialists(self, symptoms, preferences, exclude_ids):
        # Query your real database
        ...

# Use with BookingAgent
booking_agent = BookingAgent(config, doctor_database=RealDoctorDatabase())
```

## Testing

### Unit Tests (Tier 1 - No External Dependencies)

```bash
pytest examples/journey/healthcare_referral/tests/test_journey.py -v
pytest examples/journey/healthcare_referral/tests/test_transitions.py -v
```

### Integration Tests (Tier 2 - Ollama Required)

```bash
# Start Ollama
ollama serve
ollama pull llama3.2:3b

# Run tests
pytest examples/journey/healthcare_referral/tests/test_integration.py -v -m integration
```

### E2E Tests (Tier 3 - OpenAI Required)

```bash
# Set API key
export OPENAI_API_KEY="your-key"

# Run tests (approx. $0.50 total cost)
pytest examples/journey/healthcare_referral/tests/test_e2e.py -v -m e2e
```

### Run All Tests

```bash
# All tests
pytest examples/journey/healthcare_referral/tests/ -v

# Skip E2E (no OpenAI key)
pytest examples/journey/healthcare_referral/tests/ -v -m "not e2e"

# Skip integration (no Ollama)
pytest examples/journey/healthcare_referral/tests/ -v -m "not integration"
```

## Demo Conversation Flow

The demo mode shows a complete conversation including:

1. **Intake Phase** - Patient describes symptoms, preferences
2. **FAQ Detour** - Patient asks about specialist types
3. **Return to Booking** - Continue doctor selection
4. **Hesitation** - Patient expresses doubt
5. **Persuasion** - Empathetic encouragement
6. **Booking Complete** - Select doctor and time slot
7. **Confirmation** - Appointment summary

Example output:

```
PATIENT: I've been having back pain for a few weeks now
ASSISTANT: I'm sorry to hear you've been experiencing back pain. To help
           find the right specialist for you, could you tell me more about
           the pain? Is it constant or does it come and go?
  [Pathway: intake]

PATIENT: It's moderate, worse in the mornings. I prefer a female doctor.
ASSISTANT: Thank you for sharing those details. It sounds like the morning
           stiffness could be significant. Do you have insurance?
  [Pathway: intake]
  [Context: {'symptoms': ['back pain'], 'severity': 'moderate', ...}]

...

PATIENT: What's the difference between an orthopedist and a chiropractor?
ASSISTANT: Great question! An orthopedist is a medical doctor who
           specializes in the musculoskeletal system...
  [Pathway: faq]
  [Pathway Changed!]

...

PATIENT: Yes, please confirm the appointment
ASSISTANT: Your appointment is confirmed! Here's your summary:
           - Doctor: Dr. Sarah Chen, Orthopedics
           - Date: January 15, 2025 at 9:00 AM
           - Location: Downtown Medical Center
           - Confirmation #: HC-2025-A7X9K3
  [Pathway: confirmation]
```

## Configuration

### Journey Configuration

```python
from kaizen.journey import JourneyConfig

# Development config
dev_config = JourneyConfig(
    intent_detection_model="gpt-4o-mini",
    intent_confidence_threshold=0.75,
    max_pathway_depth=15,
    pathway_timeout_seconds=60.0,
    error_recovery="graceful",
    context_persistence="memory",
)

# Production config
prod_config = JourneyConfig(
    intent_detection_model="gpt-4o",
    intent_confidence_threshold=0.85,
    max_pathway_depth=20,
    pathway_timeout_seconds=120.0,
    error_recovery="graceful",
    context_persistence="dataflow",  # Database-backed
    max_retries=5,
)
```

### Agent Configuration

```python
from dataclasses import dataclass

@dataclass
class IntakeAgentConfig:
    llm_provider: str = "openai"
    model: str = "gpt-4o"
    temperature: float = 0.7
    max_tokens: int = 1024
```

## Key Patterns

### 1. Signature with Intent and Guidelines

```python
class IntakeSignature(Signature):
    __intent__ = "Collect comprehensive patient symptoms and preferences"
    __guidelines__ = [
        "Start by acknowledging the patient's concern",
        "Ask about symptoms before demographics",
        "Use empathetic, non-clinical language",
    ]

    # Inputs
    patient_message: str = InputField(description="Patient's message")

    # Outputs
    symptoms: List[str] = OutputField(description="Extracted symptoms")
    ready_for_booking: bool = OutputField(description="Ready to proceed")
```

### 2. Pathway with Accumulation

```python
class IntakePath(Pathway):
    __signature__ = IntakeSignature
    __agents__ = ["intake_agent"]
    __accumulate__ = ["symptoms", "severity", "preferences", "insurance_info"]
    __next__ = "booking"
    __pipeline__ = "sequential"
    __guidelines__ = [
        "Don't proceed until you have at least one symptom",
    ]
```

### 3. Return Behavior for Detours

```python
class FAQPath(Pathway):
    __signature__ = FAQSignature
    __agents__ = ["faq_agent"]
    __return_behavior__ = ReturnToPrevious(
        preserve_context=True,
        max_depth=3,
    )
```

### 4. Word Boundary Pattern Matching

```python
# FAQ transition - matches "help" but not "helpful"
Transition(
    trigger=IntentTrigger(
        patterns=[r"\bwhat\b", r"\bhow\b", r"\bhelp\b"],
        use_llm_fallback=True,
    ),
    from_pathway="*",  # Global
    to_pathway="faq",
    priority=10,
)
```

## Best Practices

1. **Define clear intents**: Each signature should have a focused `__intent__`
2. **Use guidelines liberally**: Help the LLM understand context and constraints
3. **Accumulate judiciously**: Only accumulate what's needed across turns
4. **Test transitions thoroughly**: Pattern matching can have edge cases
5. **Use condition triggers**: For state-based transitions (not intent-based)
6. **Implement real database**: Replace MockDoctorDatabase in production
7. **Handle errors gracefully**: Use `error_recovery="graceful"` in config

## Related Documentation

- [Journey Orchestration Guide](../../../docs/guides/journey-orchestration-guide.md)
- [Signature Programming](../../../docs/guides/signature-programming.md)
- [BaseAgent Architecture](../../../docs/guides/baseagent-architecture.md)
- [Testing Strategies](../../../docs/guides/testing-strategies.md)

## License

This example is part of the Kailash Kaizen framework.
