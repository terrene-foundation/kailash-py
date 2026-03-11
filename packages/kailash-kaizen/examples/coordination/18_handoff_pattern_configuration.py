"""
Example 18: Handoff Pattern - Progressive Configuration

This example demonstrates progressive configuration of the HandoffPattern,
showing how to customize tiers, models, and routing behavior.

Learning Objectives:
- Progressive configuration (override specific params)
- Custom tier configurations
- Different models per tier
- Pre-built tier agents

Estimated time: 5 minutes
"""

import os

from kaizen.agents.coordination import create_handoff_pattern
from kaizen.agents.coordination.handoff_pattern import HandoffAgent
from kaizen.core.base_agent import BaseAgentConfig


def example_1_custom_tier_count():
    """Example 1: Custom number of tiers."""
    print("Example 1: Custom Tier Count")
    print("-" * 70)

    # Create 5-tier system
    handoff = create_handoff_pattern(num_tiers=5)

    print(f"✓ Handoff pattern created with {len(handoff.tiers)} tiers")
    print(f"  Tiers: {sorted(handoff.tiers.keys())}")
    print()


def example_2_tier_specific_models():
    """Example 2: Different models for different tiers."""
    print("Example 2: Tier-Specific Models")
    print("-" * 70)

    # Tier 1: Fast model for simple tasks
    # Tier 2: Balanced model
    # Tier 3: Powerful model for complex tasks
    handoff = create_handoff_pattern(
        tier_configs={
            1: {"model": "gpt-3.5-turbo", "temperature": 0.3},  # Fast, deterministic
            2: {"model": "gpt-4", "temperature": 0.5},  # Balanced
            3: {"model": "gpt-4-turbo", "temperature": 0.7},  # Powerful, creative
        }
    )

    print("✓ Handoff pattern with tier-specific models")
    print("  Tier 1: gpt-3.5-turbo (temp=0.3) - Simple tasks")
    print("  Tier 2: gpt-4 (temp=0.5) - Moderate tasks")
    print("  Tier 3: gpt-4-turbo (temp=0.7) - Complex tasks")
    print()


def example_3_environment_variables():
    """Example 3: Using environment variables."""
    print("Example 3: Environment Variables")
    print("-" * 70)

    # Set environment variables
    os.environ["KAIZEN_MODEL"] = "gpt-4"
    os.environ["KAIZEN_TEMPERATURE"] = "0.6"

    # Create pattern - uses env vars for all tiers
    handoff = create_handoff_pattern(num_tiers=3)

    print("✓ Pattern created using environment variables")
    print(f"  KAIZEN_MODEL: {os.environ.get('KAIZEN_MODEL')}")
    print(f"  KAIZEN_TEMPERATURE: {os.environ.get('KAIZEN_TEMPERATURE')}")
    print(f"  Applied to all {len(handoff.tiers)} tiers")
    print()

    # Cleanup
    del os.environ["KAIZEN_MODEL"]
    del os.environ["KAIZEN_TEMPERATURE"]


def example_4_pre_built_tiers():
    """Example 4: Using pre-built tier agents."""
    print("Example 4: Pre-Built Tier Agents")
    print("-" * 70)

    from kaizen.memory import SharedMemoryPool

    # Create shared memory
    shared_memory = SharedMemoryPool()

    # Create custom tier agents
    tier1 = HandoffAgent(
        config=BaseAgentConfig(model="gpt-3.5-turbo", temperature=0.3),
        shared_memory=shared_memory,
        tier_level=1,
        agent_id="junior_support",
    )

    tier2 = HandoffAgent(
        config=BaseAgentConfig(model="gpt-4", temperature=0.5),
        shared_memory=shared_memory,
        tier_level=2,
        agent_id="senior_support",
    )

    tier3 = HandoffAgent(
        config=BaseAgentConfig(model="gpt-4-turbo", temperature=0.7),
        shared_memory=shared_memory,
        tier_level=3,
        agent_id="expert_engineer",
    )

    # Create pattern with pre-built tiers
    handoff = create_handoff_pattern(tiers={1: tier1, 2: tier2, 3: tier3})

    print("✓ Pattern created with pre-built tiers")
    print(f"  Tier 1: {tier1.agent_id}")
    print(f"  Tier 2: {tier2.agent_id}")
    print(f"  Tier 3: {tier3.agent_id}")
    print()


def example_5_complete_workflow():
    """Example 5: Complete workflow with optimized config."""
    print("Example 5: Complete Workflow - Customer Support")
    print("-" * 70)

    # Optimized tier configuration for customer support
    handoff = create_handoff_pattern(
        tier_configs={
            1: {
                "model": "gpt-3.5-turbo",
                "temperature": 0.3,
                "max_tokens": 500,
            },  # Quick responses
            2: {
                "model": "gpt-4",
                "temperature": 0.5,
                "max_tokens": 1000,
            },  # Detailed help
            3: {
                "model": "gpt-4-turbo",
                "temperature": 0.7,
                "max_tokens": 1500,
            },  # Expert troubleshooting
        }
    )

    # Execute support request
    result = handoff.execute_with_handoff(
        task="My application crashes when I try to export large datasets (>10GB). How can I fix this?",
        context="Customer support - production issue",
        max_tier=3,
    )

    print("Support Request Handling:")
    print(f"  - Handled by: Tier {result['final_tier']}")
    print(f"  - Escalations: {result['escalation_count']}")
    print(f"  - Confidence: {result['confidence']:.2f}")
    print()

    print("Response Preview:")
    print(f"  {result['result'][:150]}...")
    print()

    # Get escalation trail
    history = handoff.get_handoff_history(result["execution_id"])
    print("Escalation Trail:")
    for decision in history:
        action = (
            "✓ Handled"
            if decision["can_handle"] == "yes"
            else f"→ Escalate to tier {decision['requires_tier']}"
        )
        print(
            f"  Tier {decision['tier_level']}: {action} (complexity: {decision['complexity_score']:.2f})"
        )
    print()


def main():
    print("=" * 70)
    print("Handoff Pattern - Progressive Configuration Examples")
    print("=" * 70)
    print()

    # Run all examples
    example_1_custom_tier_count()
    example_2_tier_specific_models()
    example_3_environment_variables()
    example_4_pre_built_tiers()
    example_5_complete_workflow()

    # Summary
    print("=" * 70)
    print("Configuration Examples Complete!")
    print("=" * 70)
    print()
    print("Configuration Options Summary:")
    print()
    print("Basic Parameters:")
    print("  - llm_provider: str (default: 'openai' or KAIZEN_LLM_PROVIDER)")
    print("  - model: str (default: 'gpt-3.5-turbo' or KAIZEN_MODEL)")
    print("  - temperature: float (default: 0.7 or KAIZEN_TEMPERATURE)")
    print("  - max_tokens: int (default: 1000 or KAIZEN_MAX_TOKENS)")
    print("  - num_tiers: int (default: 3)")
    print()
    print("Advanced Parameters:")
    print("  - shared_memory: SharedMemoryPool (default: creates new)")
    print("  - tier_configs: Dict[int, Dict] (default: uses basic params)")
    print("  - tiers: Dict[int, HandoffAgent] (default: creates from tier_configs)")
    print()
    print("Configuration Levels:")
    print()
    print("  Level 1: Zero-config")
    print("    handoff = create_handoff_pattern()")
    print()
    print("  Level 2: Custom tier count")
    print("    handoff = create_handoff_pattern(num_tiers=5)")
    print()
    print("  Level 3: Tier-specific configs")
    print("    handoff = create_handoff_pattern(tier_configs={1: {...}, 2: {...}})")
    print()
    print("  Level 4: Pre-built tier agents")
    print("    handoff = create_handoff_pattern(tiers={1: agent1, 2: agent2})")
    print()
    print("Recommended Configurations:")
    print()
    print("  Cost-Optimized (Fewer Tiers):")
    print("    num_tiers=2, model='gpt-3.5-turbo'")
    print()
    print("  Quality-Optimized (More Tiers):")
    print("    num_tiers=5, tier_configs with gpt-4-turbo for top tier")
    print()
    print("  Balanced (Mixed Models):")
    print(
        "    tier_configs: gpt-3.5-turbo (tier1) → gpt-4 (tier2) → gpt-4-turbo (tier3)"
    )
    print()


if __name__ == "__main__":
    main()
