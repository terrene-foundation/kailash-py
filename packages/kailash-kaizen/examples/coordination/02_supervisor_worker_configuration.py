"""
Example 2: Supervisor-Worker Pattern - Progressive Configuration

This example demonstrates progressive configuration of the SupervisorWorkerPattern,
showing how to override specific parameters while keeping others as defaults.

Learning Objectives:
- Progressive configuration (override specific params)
- Custom number of workers
- Different models for different agents
- Environment variable usage

Estimated time: 5 minutes
"""

import os

from kaizen.agents.coordination import create_supervisor_worker_pattern


def example_1_custom_workers():
    """Example 1: Custom number of workers."""
    print("Example 1: Custom Number of Workers")
    print("-" * 70)

    # Create pattern with 5 workers instead of default 3
    pattern = create_supervisor_worker_pattern(num_workers=5)

    print(f"✓ Pattern created with {len(pattern.workers)} workers")
    print(f"  Worker IDs: {[w.agent_id for w in pattern.workers]}")
    print()


def example_2_custom_model():
    """Example 2: Custom model for all agents."""
    print("Example 2: Custom Model")
    print("-" * 70)

    # Use GPT-4 instead of default gpt-3.5-turbo
    pattern = create_supervisor_worker_pattern(
        num_workers=3, model="gpt-4", temperature=0.7
    )

    print("✓ Pattern created with custom model")
    print("  Model: gpt-4")
    print("  Temperature: 0.7")
    print()


def example_3_separate_configs():
    """Example 3: Different configs for different agents."""
    print("Example 3: Separate Agent Configurations")
    print("-" * 70)

    # Supervisor uses GPT-4 (more capable for coordination)
    # Workers use GPT-3.5-turbo (faster, cheaper for execution)
    pattern = create_supervisor_worker_pattern(
        num_workers=4,
        supervisor_config={
            "model": "gpt-4",
            "temperature": 0.3,  # Lower temp for deterministic delegation
            "max_tokens": 1000,
        },
        worker_config={
            "model": "gpt-3.5-turbo",
            "temperature": 0.7,  # Higher temp for creative execution
            "max_tokens": 1500,
        },
        coordinator_config={
            "model": "gpt-3.5-turbo",
            "temperature": 0.1,  # Very low for accurate monitoring
        },
    )

    print("✓ Pattern created with separate agent configs")
    print("  Supervisor: gpt-4 (temp=0.3)")
    print("  Workers: gpt-3.5-turbo (temp=0.7)")
    print("  Coordinator: gpt-3.5-turbo (temp=0.1)")
    print()


def example_4_environment_variables():
    """Example 4: Using environment variables."""
    print("Example 4: Environment Variables")
    print("-" * 70)

    # Set environment variables
    os.environ["KAIZEN_MODEL"] = "gpt-4"
    os.environ["KAIZEN_TEMPERATURE"] = "0.5"
    os.environ["KAIZEN_LLM_PROVIDER"] = "openai"

    # Create pattern - will use environment variables
    pattern = create_supervisor_worker_pattern(num_workers=2)

    print("✓ Pattern created using environment variables")
    print(f"  KAIZEN_MODEL: {os.environ.get('KAIZEN_MODEL')}")
    print(f"  KAIZEN_TEMPERATURE: {os.environ.get('KAIZEN_TEMPERATURE')}")
    print(f"  KAIZEN_LLM_PROVIDER: {os.environ.get('KAIZEN_LLM_PROVIDER')}")
    print()

    # Cleanup
    del os.environ["KAIZEN_MODEL"]
    del os.environ["KAIZEN_TEMPERATURE"]
    del os.environ["KAIZEN_LLM_PROVIDER"]


def example_5_custom_shared_memory():
    """Example 5: Using custom shared memory."""
    print("Example 5: Custom Shared Memory")
    print("-" * 70)

    from kaizen.memory import SharedMemoryPool

    # Create custom shared memory (e.g., with persistence, custom config)
    shared_memory = SharedMemoryPool()

    # Create pattern with custom shared memory
    pattern = create_supervisor_worker_pattern(
        num_workers=3, shared_memory=shared_memory
    )

    print("✓ Pattern created with custom shared memory")
    print("  Shared memory instance provided: YES")
    print(
        f"  All agents share same memory: {all(a.shared_memory is shared_memory for a in pattern.get_agents() if hasattr(a, 'shared_memory'))}"
    )
    print()


def main():
    print("=" * 70)
    print("Supervisor-Worker Pattern - Progressive Configuration Examples")
    print("=" * 70)
    print()

    # Run all examples
    example_1_custom_workers()
    example_2_custom_model()
    example_3_separate_configs()
    example_4_environment_variables()
    example_5_custom_shared_memory()

    # Summary
    print("=" * 70)
    print("Configuration Examples Complete!")
    print("=" * 70)
    print()
    print("Configuration Options Summary:")
    print()
    print("Basic Parameters:")
    print("  - num_workers: int (default: 3)")
    print("  - llm_provider: str (default: 'openai' or KAIZEN_LLM_PROVIDER)")
    print("  - model: str (default: 'gpt-3.5-turbo' or KAIZEN_MODEL)")
    print("  - temperature: float (default: 0.7 or KAIZEN_TEMPERATURE)")
    print("  - max_tokens: int (default: 1000 or KAIZEN_MAX_TOKENS)")
    print()
    print("Advanced Parameters:")
    print("  - shared_memory: SharedMemoryPool (default: creates new)")
    print("  - supervisor_config: Dict[str, Any] (default: uses basic params)")
    print("  - worker_config: Dict[str, Any] (default: uses basic params)")
    print("  - coordinator_config: Dict[str, Any] (default: uses basic params)")
    print()
    print("Environment Variables (used if not overridden):")
    print("  - KAIZEN_LLM_PROVIDER")
    print("  - KAIZEN_MODEL")
    print("  - KAIZEN_TEMPERATURE")
    print("  - KAIZEN_MAX_TOKENS")
    print()


if __name__ == "__main__":
    main()
