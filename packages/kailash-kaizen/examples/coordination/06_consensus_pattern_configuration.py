"""
Example 6: Consensus Pattern - Progressive Configuration

This example demonstrates progressive configuration of the ConsensusPattern,
showing how to override specific parameters while keeping others as defaults.

Learning Objectives:
- Progressive configuration (override specific params)
- Custom number of voters
- Different models for different agents
- Voter perspectives for role-based evaluation
- Environment variable usage

Estimated time: 5 minutes
"""

import os

from kaizen.agents.coordination import create_consensus_pattern


def example_1_custom_voters():
    """Example 1: Custom number of voters."""
    print("Example 1: Custom Number of Voters")
    print("-" * 70)

    # Create pattern with 5 voters instead of default 3
    pattern = create_consensus_pattern(num_voters=5)

    print(f"✓ Pattern created with {len(pattern.voters)} voters")
    print(f"  Voter IDs: {[v.agent_id for v in pattern.voters]}")
    print()


def example_2_custom_model():
    """Example 2: Custom model for all agents."""
    print("Example 2: Custom Model")
    print("-" * 70)

    # Use GPT-4 instead of default gpt-3.5-turbo
    pattern = create_consensus_pattern(num_voters=3, model="gpt-4", temperature=0.7)

    print("✓ Pattern created with custom model")
    print("  Model: gpt-4")
    print("  Temperature: 0.7")
    print()


def example_3_voter_perspectives():
    """Example 3: Voters with different perspectives."""
    print("Example 3: Voter Perspectives")
    print("-" * 70)

    # Assign specific perspectives/roles to voters
    # This influences how they evaluate proposals
    pattern = create_consensus_pattern(
        num_voters=4, voter_perspectives=["technical", "business", "security", "ux"]
    )

    print("✓ Pattern created with specialized voters")
    for voter in pattern.voters:
        print(f"  - {voter.agent_id}: perspective = '{voter.perspective}'")
    print()


def example_4_separate_configs():
    """Example 4: Different configs for different agents."""
    print("Example 4: Separate Agent Configurations")
    print("-" * 70)

    # Proposer uses GPT-4 (better at creating proposals)
    # Voters use GPT-3.5-turbo (faster, cheaper for evaluation)
    # Aggregator uses GPT-3.5-turbo (simple aggregation logic)
    pattern = create_consensus_pattern(
        num_voters=3,
        voter_perspectives=["engineering", "product", "design"],
        proposer_config={
            "model": "gpt-4",
            "temperature": 0.5,  # Balanced creativity
            "max_tokens": 1500,
        },
        voter_config={
            "model": "gpt-3.5-turbo",
            "temperature": 0.7,  # More creative evaluation
            "max_tokens": 1000,
        },
        aggregator_config={
            "model": "gpt-3.5-turbo",
            "temperature": 0.2,  # Low for accurate tallying
        },
    )

    print("✓ Pattern created with separate agent configs")
    print("  Proposer: gpt-4 (temp=0.5)")
    print("  Voters: gpt-3.5-turbo (temp=0.7)")
    print(f"    - {pattern.voters[0].agent_id}: {pattern.voters[0].perspective}")
    print(f"    - {pattern.voters[1].agent_id}: {pattern.voters[1].perspective}")
    print(f"    - {pattern.voters[2].agent_id}: {pattern.voters[2].perspective}")
    print("  Aggregator: gpt-3.5-turbo (temp=0.2)")
    print()


def example_5_environment_variables():
    """Example 5: Using environment variables."""
    print("Example 5: Environment Variables")
    print("-" * 70)

    # Set environment variables
    os.environ["KAIZEN_MODEL"] = "gpt-4"
    os.environ["KAIZEN_TEMPERATURE"] = "0.6"
    os.environ["KAIZEN_LLM_PROVIDER"] = "openai"

    # Create pattern - will use environment variables
    pattern = create_consensus_pattern(num_voters=3)

    print("✓ Pattern created using environment variables")
    print(f"  KAIZEN_MODEL: {os.environ.get('KAIZEN_MODEL')}")
    print(f"  KAIZEN_TEMPERATURE: {os.environ.get('KAIZEN_TEMPERATURE')}")
    print(f"  KAIZEN_LLM_PROVIDER: {os.environ.get('KAIZEN_LLM_PROVIDER')}")
    print()

    # Cleanup
    del os.environ["KAIZEN_MODEL"]
    del os.environ["KAIZEN_TEMPERATURE"]
    del os.environ["KAIZEN_LLM_PROVIDER"]


def example_6_custom_shared_memory():
    """Example 6: Using custom shared memory."""
    print("Example 6: Custom Shared Memory")
    print("-" * 70)

    from kaizen.memory import SharedMemoryPool

    # Create custom shared memory (e.g., with persistence, custom config)
    shared_memory = SharedMemoryPool()

    # Create pattern with custom shared memory
    pattern = create_consensus_pattern(num_voters=3, shared_memory=shared_memory)

    print("✓ Pattern created with custom shared memory")
    print("  Shared memory instance provided: YES")
    print(
        f"  All agents share same memory: {all(a.shared_memory is shared_memory for a in pattern.get_agents() if hasattr(a, 'shared_memory'))}"
    )
    print()


def example_7_complete_workflow():
    """Example 7: Complete workflow with custom config."""
    print("Example 7: Complete Workflow with Custom Config")
    print("-" * 70)

    # Create pattern with multi-expert perspectives
    pattern = create_consensus_pattern(
        num_voters=5,
        voter_perspectives=[
            "security",
            "performance",
            "scalability",
            "maintainability",
            "cost",
        ],
        model="gpt-4",
        temperature=0.6,
    )

    print("✓ Multi-expert panel created:")
    for voter in pattern.voters:
        print(f"  - {voter.agent_id}: {voter.perspective} expert")
    print()

    # Create proposal
    topic = "Should we migrate to microservices architecture?"
    context = "Current monolithic app has scaling issues but team is small"

    proposal = pattern.create_proposal(topic, context)
    print(f"✓ Proposal created: {proposal['topic'][:60]}...")
    print()

    # Experts vote
    print("Experts evaluating proposal:")
    for voter in pattern.voters:
        vote = voter.vote(proposal)
        print(
            f"  {voter.perspective:15} → {vote['vote']:8} (confidence: {vote['confidence']:.2f})"
        )

    print()

    # Determine consensus
    result = pattern.determine_consensus(proposal["proposal_id"])
    print(f"✓ Consensus: {result['consensus_reached'].upper()}")
    print(f"  Decision: {result['final_decision']}")
    print()


def main():
    print("=" * 70)
    print("Consensus Pattern - Progressive Configuration Examples")
    print("=" * 70)
    print()

    # Run all examples
    example_1_custom_voters()
    example_2_custom_model()
    example_3_voter_perspectives()
    example_4_separate_configs()
    example_5_environment_variables()
    example_6_custom_shared_memory()
    example_7_complete_workflow()

    # Summary
    print("=" * 70)
    print("Configuration Examples Complete!")
    print("=" * 70)
    print()
    print("Configuration Options Summary:")
    print()
    print("Basic Parameters:")
    print("  - num_voters: int (default: 3)")
    print("  - voter_perspectives: List[str] (default: ['general'] * num_voters)")
    print("  - llm_provider: str (default: 'openai' or KAIZEN_LLM_PROVIDER)")
    print("  - model: str (default: 'gpt-3.5-turbo' or KAIZEN_MODEL)")
    print("  - temperature: float (default: 0.7 or KAIZEN_TEMPERATURE)")
    print("  - max_tokens: int (default: 1000 or KAIZEN_MAX_TOKENS)")
    print()
    print("Advanced Parameters:")
    print("  - shared_memory: SharedMemoryPool (default: creates new)")
    print("  - proposer_config: Dict[str, Any] (default: uses basic params)")
    print("  - voter_config: Dict[str, Any] (default: uses basic params)")
    print("  - aggregator_config: Dict[str, Any] (default: uses basic params)")
    print()
    print("Environment Variables (used if not overridden):")
    print("  - KAIZEN_LLM_PROVIDER")
    print("  - KAIZEN_MODEL")
    print("  - KAIZEN_TEMPERATURE")
    print("  - KAIZEN_MAX_TOKENS")
    print()
    print("Voter Perspectives:")
    print("  Common perspectives for different use cases:")
    print("  - Technical: 'technical', 'engineering', 'security', 'performance'")
    print("  - Business: 'business', 'product', 'marketing', 'sales'")
    print("  - Design: 'ux', 'ui', 'design', 'accessibility'")
    print("  - Operations: 'operations', 'devops', 'cost', 'scalability'")
    print()


if __name__ == "__main__":
    main()
