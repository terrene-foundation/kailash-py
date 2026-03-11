"""
Example 10: Debate Pattern - Progressive Configuration

This example demonstrates progressive configuration of the DebatePattern,
showing how to override specific parameters while keeping others as defaults.

Learning Objectives:
- Progressive configuration (override specific params)
- Different models for different agents
- Multi-round debate configuration
- Environment variable usage

Estimated time: 5 minutes
"""

import os

from kaizen.agents.coordination import create_debate_pattern


def example_1_custom_model():
    """Example 1: Custom model for all agents."""
    print("Example 1: Custom Model")
    print("-" * 70)

    # Use GPT-4 instead of default gpt-3.5-turbo
    pattern = create_debate_pattern(model="gpt-4", temperature=0.7)

    print("✓ Pattern created with custom model")
    print("  Model: gpt-4")
    print("  Temperature: 0.7")
    print()


def example_2_separate_configs():
    """Example 2: Different configs for different agents."""
    print("Example 2: Separate Agent Configurations")
    print("-" * 70)

    # Proponent and Opponent use GPT-4 (better arguments)
    # Judge uses GPT-4 (better judgment)
    pattern = create_debate_pattern(
        proponent_config={
            "model": "gpt-4",
            "temperature": 0.7,  # Creative arguments
            "max_tokens": 1500,
        },
        opponent_config={
            "model": "gpt-4",
            "temperature": 0.7,  # Creative counter-arguments
            "max_tokens": 1500,
        },
        judge_config={
            "model": "gpt-4",
            "temperature": 0.3,  # Balanced judgment
            "max_tokens": 1000,
        },
    )

    print("✓ Pattern created with separate agent configs")
    print("  Proponent: gpt-4 (temp=0.7)")
    print("  Opponent: gpt-4 (temp=0.7)")
    print("  Judge: gpt-4 (temp=0.3)")
    print()


def example_3_environment_variables():
    """Example 3: Using environment variables."""
    print("Example 3: Environment Variables")
    print("-" * 70)

    # Set environment variables
    os.environ["KAIZEN_MODEL"] = "gpt-4"
    os.environ["KAIZEN_TEMPERATURE"] = "0.6"
    os.environ["KAIZEN_LLM_PROVIDER"] = "openai"

    # Create pattern - will use environment variables
    pattern = create_debate_pattern()

    print("✓ Pattern created using environment variables")
    print(f"  KAIZEN_MODEL: {os.environ.get('KAIZEN_MODEL')}")
    print(f"  KAIZEN_TEMPERATURE: {os.environ.get('KAIZEN_TEMPERATURE')}")
    print(f"  KAIZEN_LLM_PROVIDER: {os.environ.get('KAIZEN_LLM_PROVIDER')}")
    print()

    # Cleanup
    del os.environ["KAIZEN_MODEL"]
    del os.environ["KAIZEN_TEMPERATURE"]
    del os.environ["KAIZEN_LLM_PROVIDER"]


def example_4_custom_shared_memory():
    """Example 4: Using custom shared memory."""
    print("Example 4: Custom Shared Memory")
    print("-" * 70)

    from kaizen.memory import SharedMemoryPool

    # Create custom shared memory (e.g., with persistence, custom config)
    shared_memory = SharedMemoryPool()

    # Create pattern with custom shared memory
    pattern = create_debate_pattern(shared_memory=shared_memory)

    print("✓ Pattern created with custom shared memory")
    print("  Shared memory instance provided: YES")
    print(
        f"  All agents share same memory: {all(a.shared_memory is shared_memory for a in pattern.get_agents() if hasattr(a, 'shared_memory'))}"
    )
    print()


def example_5_multi_round_debate():
    """Example 5: Multi-round debate configuration."""
    print("Example 5: Multi-Round Debate")
    print("-" * 70)

    # Create pattern
    pattern = create_debate_pattern(model="gpt-4")

    # Run 3-round debate (initial arguments + 2 rounds of rebuttals)
    topic = "Should remote work be the default for tech companies?"
    context = "Post-pandemic work environment evaluation"

    result = pattern.debate(topic, context, rounds=3)

    print("✓ Multi-round debate completed")
    print(f"  Topic: {topic}")
    print(f"  Rounds: {result['rounds']}")
    print()

    # Get judgment
    judgment = pattern.get_judgment(result["debate_id"])
    print("Judge's Decision:")
    print(f"  Winner: {judgment['winner']}")
    print(f"  Confidence: {judgment['confidence']:.2f}")
    print()


def example_6_complete_workflow():
    """Example 6: Complete workflow with custom config."""
    print("Example 6: Complete Workflow with Custom Config")
    print("-" * 70)

    # Create pattern with optimal config
    pattern = create_debate_pattern(model="gpt-4", temperature=0.7, max_tokens=2000)

    # Run debate
    topic = "Should AI development be open source or proprietary?"
    context = """
    Considerations:
    - Innovation speed vs safety
    - Accessibility vs competitive advantage
    - Community development vs corporate control
    """

    print(f"Debate Topic: {topic}")
    print()

    # 2-round debate
    result = pattern.debate(topic, context, rounds=2)

    print("Debate Summary:")
    print(f"  - Debate ID: {result['debate_id']}")
    print(f"  - Rounds: {result['rounds']}")
    print()

    # Get judgment
    judgment = pattern.get_judgment(result["debate_id"])

    print("Final Judgment:")
    print(f"  Winner: {judgment['winner'].upper()}")
    print(f"  Decision: {judgment['decision']}")
    print(f"  Confidence: {judgment['confidence']:.2f}")
    print(f"  Reasoning: {judgment['reasoning'][:150]}...")
    print()


def main():
    print("=" * 70)
    print("Debate Pattern - Progressive Configuration Examples")
    print("=" * 70)
    print()

    # Run all examples
    example_1_custom_model()
    example_2_separate_configs()
    example_3_environment_variables()
    example_4_custom_shared_memory()
    example_5_multi_round_debate()
    example_6_complete_workflow()

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
    print()
    print("Advanced Parameters:")
    print("  - shared_memory: SharedMemoryPool (default: creates new)")
    print("  - proponent_config: Dict[str, Any] (default: uses basic params)")
    print("  - opponent_config: Dict[str, Any] (default: uses basic params)")
    print("  - judge_config: Dict[str, Any] (default: uses basic params)")
    print()
    print("Debate Parameters:")
    print("  - rounds: int (default: 1)")
    print("    - 1 round: Initial arguments only")
    print("    - 2+ rounds: Initial arguments + rebuttals")
    print()
    print("Environment Variables (used if not overridden):")
    print("  - KAIZEN_LLM_PROVIDER")
    print("  - KAIZEN_MODEL")
    print("  - KAIZEN_TEMPERATURE")
    print("  - KAIZEN_MAX_TOKENS")
    print()
    print("Recommended Configurations:")
    print()
    print("  Cost-Optimized:")
    print("    model='gpt-3.5-turbo', rounds=1")
    print()
    print("  Quality-Optimized:")
    print("    model='gpt-4', temperature=0.7, rounds=3")
    print()
    print("  Balanced:")
    print("    proponent/opponent='gpt-4', judge='gpt-3.5-turbo', rounds=2")
    print()


if __name__ == "__main__":
    main()
