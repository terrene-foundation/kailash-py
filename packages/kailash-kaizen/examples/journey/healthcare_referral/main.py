"""
Healthcare Referral Journey - Main Example

Demonstrates a complete healthcare referral conversation flow including:
- Intake (symptom collection)
- Booking (doctor selection)
- FAQ detour (returns to previous)
- Hesitation handling
- Confirmation

Usage:
    # With OpenAI (default)
    python -m examples.journey.healthcare_referral.main

    # With Ollama (free, local)
    KAIZEN_LLM_PROVIDER=ollama KAIZEN_MODEL=llama3.2:3b python -m examples.journey.healthcare_referral.main

    # Interactive mode
    python -m examples.journey.healthcare_referral.main --interactive

Requirements:
    - OpenAI API key in .env (OPENAI_API_KEY) for default provider
    - OR Ollama running locally with llama3.2 model
"""

import asyncio
import os
import sys
from typing import Optional

# Load environment variables
try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass  # dotenv is optional

from examples.journey.healthcare_referral.agents import (
    BookingAgent,
    BookingAgentConfig,
    ConfirmationAgent,
    ConfirmationAgentConfig,
    FAQAgent,
    FAQAgentConfig,
    IntakeAgent,
    IntakeAgentConfig,
    PersuasionAgent,
    PersuasionAgentConfig,
)
from examples.journey.healthcare_referral.journey import (
    HealthcareReferralJourney,
    default_config,
)


def get_agent_config(base_config_class):
    """
    Get agent config with provider from environment.

    Uses KAIZEN_LLM_PROVIDER and KAIZEN_MODEL environment variables,
    defaulting to OpenAI gpt-4o.
    """
    provider = os.getenv("KAIZEN_LLM_PROVIDER", "openai")
    model = os.getenv("KAIZEN_MODEL", "gpt-4o")

    return base_config_class(
        llm_provider=provider,
        model=model,
    )


async def run_demo_conversation():
    """
    Run a complete demo conversation showing all journey features.

    Demonstrates:
    - Intake pathway (symptom collection)
    - FAQ detour (question during booking)
    - Booking pathway (doctor selection)
    - Hesitation handling
    - Confirmation
    """
    print("=" * 70)
    print("HEALTHCARE REFERRAL JOURNEY - DEMO")
    print("=" * 70)
    print()

    # Create agents with environment-based config
    intake_agent = IntakeAgent(get_agent_config(IntakeAgentConfig))
    booking_agent = BookingAgent(get_agent_config(BookingAgentConfig))
    faq_agent = FAQAgent(get_agent_config(FAQAgentConfig))
    persuasion_agent = PersuasionAgent(get_agent_config(PersuasionAgentConfig))
    confirmation_agent = ConfirmationAgent(get_agent_config(ConfirmationAgentConfig))

    # Create journey instance
    journey = HealthcareReferralJourney(
        session_id="demo-patient-001",
        config=default_config,
    )

    # Register agents
    journey.register_agent("intake_agent", intake_agent)
    journey.register_agent("booking_agent", booking_agent)
    journey.register_agent("faq_agent", faq_agent)
    journey.register_agent("persuasion_agent", persuasion_agent)
    journey.register_agent("confirmation_agent", confirmation_agent)

    # Start session
    session = await journey.start()
    print(f"Started journey at pathway: {session.current_pathway_id}")
    print()

    # Demo conversation messages
    demo_messages = [
        # Intake phase
        "I've been having back pain for a few weeks now",
        "It's moderate, worse in the mornings. I prefer a female doctor if possible.",
        "Yes, I have Blue Cross insurance. I'd prefer morning appointments.",
        # Transition to booking
        "What are my options?",
        # FAQ detour during booking
        "Actually, what's the difference between an orthopedist and a chiropractor?",
        # Return to booking (after FAQ)
        "Thanks! I'll go with Dr. Chen",
        # Hesitation
        "Hmm, actually I'm not sure if I want to do this right now...",
        # Back to booking after persuasion
        "You're right, I should take care of this. Let's book Dr. Chen for the 9am slot.",
        # Confirmation
        "Yes, please confirm the appointment",
    ]

    for message in demo_messages:
        print("-" * 70)
        print(f"PATIENT: {message}")
        print()

        try:
            response = await journey.process_message(message)

            print(f"ASSISTANT: {response.message}")
            print()
            print(f"  [Pathway: {response.pathway_id}]")
            if response.pathway_changed:
                print("  [Pathway Changed!]")
            if response.accumulated_context:
                context_summary = {
                    k: (v[:50] + "..." if isinstance(v, str) and len(v) > 50 else v)
                    for k, v in response.accumulated_context.items()
                    if v  # Only non-empty values
                }
                if context_summary:
                    print(f"  [Context: {context_summary}]")
            print()

        except Exception as e:
            print(f"  [Error: {e}]")
            print()

    # Show final accumulated context
    print("=" * 70)
    print("JOURNEY COMPLETE - ACCUMULATED CONTEXT")
    print("=" * 70)

    try:
        session_state = await journey.manager.get_session_state()
        for key, value in session_state.accumulated_context.items():
            if isinstance(value, str) and len(value) > 100:
                value = value[:100] + "..."
            print(f"  {key}: {value}")
    except Exception as e:
        print(f"  Error getting session state: {e}")


async def run_interactive():
    """
    Run an interactive conversation with the journey.

    Type messages to interact with the healthcare referral journey.
    Type 'quit' or 'exit' to end.
    """
    print("=" * 70)
    print("HEALTHCARE REFERRAL JOURNEY - INTERACTIVE MODE")
    print("=" * 70)
    print()
    print("Type your messages to interact with the healthcare referral system.")
    print("Type 'quit' or 'exit' to end.")
    print()

    # Create agents
    intake_agent = IntakeAgent(get_agent_config(IntakeAgentConfig))
    booking_agent = BookingAgent(get_agent_config(BookingAgentConfig))
    faq_agent = FAQAgent(get_agent_config(FAQAgentConfig))
    persuasion_agent = PersuasionAgent(get_agent_config(PersuasionAgentConfig))
    confirmation_agent = ConfirmationAgent(get_agent_config(ConfirmationAgentConfig))

    # Create journey
    journey = HealthcareReferralJourney(
        session_id="interactive-patient",
        config=default_config,
    )

    # Register agents
    journey.register_agent("intake_agent", intake_agent)
    journey.register_agent("booking_agent", booking_agent)
    journey.register_agent("faq_agent", faq_agent)
    journey.register_agent("persuasion_agent", persuasion_agent)
    journey.register_agent("confirmation_agent", confirmation_agent)

    # Start session
    session = await journey.start()
    print(f"[Started at pathway: {session.current_pathway_id}]")
    print()

    # Initial greeting
    print(
        "ASSISTANT: Hello! I'm here to help you book an appointment with a specialist."
    )
    print("           What brings you in today?")
    print()

    while True:
        try:
            user_input = input("YOU: ").strip()

            if not user_input:
                continue

            if user_input.lower() in ("quit", "exit", "q"):
                print()
                print("Thank you for using the Healthcare Referral System. Goodbye!")
                break

            print()

            response = await journey.process_message(user_input)

            print(f"ASSISTANT: {response.message}")
            print()
            print(f"  [Pathway: {response.pathway_id}]")

            if response.pathway_changed:
                print("  [Pathway Changed!]")

            print()

        except KeyboardInterrupt:
            print()
            print("Session interrupted. Goodbye!")
            break
        except Exception as e:
            print(f"  [Error: {e}]")
            print()


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Healthcare Referral Journey Example")
    parser.add_argument(
        "--interactive", "-i", action="store_true", help="Run in interactive mode"
    )
    parser.add_argument(
        "--provider", type=str, default=None, help="LLM provider (openai, ollama, etc.)"
    )
    parser.add_argument(
        "--model", type=str, default=None, help="Model name (gpt-4o, llama3.2:3b, etc.)"
    )

    args = parser.parse_args()

    # Override environment variables if provided
    if args.provider:
        os.environ["KAIZEN_LLM_PROVIDER"] = args.provider
    if args.model:
        os.environ["KAIZEN_MODEL"] = args.model

    # Run appropriate mode
    if args.interactive:
        asyncio.run(run_interactive())
    else:
        asyncio.run(run_demo_conversation())


if __name__ == "__main__":
    main()
