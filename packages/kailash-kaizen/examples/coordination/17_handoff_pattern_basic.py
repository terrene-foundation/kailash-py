"""
Example 17: Handoff Pattern - Basic Usage

This example demonstrates the basic usage of the HandoffPattern with zero-configuration.
Tasks are automatically routed to appropriate expertise tiers based on complexity.

Learning Objectives:
- Zero-config pattern creation
- Dynamic tier-based routing
- Automatic escalation
- Handoff history tracking

Estimated time: 5 minutes
"""

from kaizen.agents.coordination import create_handoff_pattern


def main():
    print("=" * 70)
    print("Handoff Pattern - Basic Usage Example")
    print("=" * 70)
    print()

    # ==================================================================
    # STEP 1: Create Pattern (Zero-Config!)
    # ==================================================================
    print("Step 1: Creating handoff pattern...")
    print("-" * 70)

    # Create pattern with default settings (creates 3 tiers automatically)
    handoff = create_handoff_pattern()

    print("✓ Pattern created successfully!")
    print("  - Default tiers: 3 (Tier 1, Tier 2, Tier 3)")
    print("  - Routing: Automatic based on complexity")
    print(f"  - Shared Memory: {handoff.shared_memory is not None}")
    print()

    # ==================================================================
    # STEP 2: Validate Pattern
    # ==================================================================
    print("Step 2: Validating pattern initialization...")
    print("-" * 70)

    if handoff.validate_pattern():
        print("✓ Pattern validation passed!")
        print(f"  - Tiers configured: {sorted(handoff.tiers.keys())}")
        print(f"  - Agent IDs: {handoff.get_agent_ids()}")
    else:
        print("✗ Pattern validation failed!")
        return

    print()

    # ==================================================================
    # STEP 3: Execute Simple Task (Tier 1 Handles)
    # ==================================================================
    print("Step 3: Executing simple task...")
    print("-" * 70)

    simple_task = "What is 2 + 2?"

    print(f"Task: {simple_task}")
    print()

    result1 = handoff.execute_with_handoff(
        task=simple_task, context="Basic arithmetic question", max_tier=3
    )

    print("Execution Results:")
    print(f"  - Handled by: Tier {result1['final_tier']}")
    print(f"  - Escalations: {result1['escalation_count']}")
    print(f"  - Result: {result1['result'][:100]}...")
    print()

    # ==================================================================
    # STEP 4: Execute Complex Task (Escalation Expected)
    # ==================================================================
    print("Step 4: Executing complex task...")
    print("-" * 70)

    complex_task = """
    Analyze the performance bottlenecks in a distributed microservices architecture
    with 50+ services, implement monitoring, and recommend optimization strategies.
    """

    print(f"Task: {complex_task.strip()[:80]}...")
    print()

    result2 = handoff.execute_with_handoff(
        task=complex_task, context="Production system optimization", max_tier=3
    )

    print("Execution Results:")
    print(f"  - Handled by: Tier {result2['final_tier']}")
    print(f"  - Escalations: {result2['escalation_count']}")
    print(f"  - Result: {result2['result'][:100]}...")
    print()

    # ==================================================================
    # STEP 5: Review Handoff History
    # ==================================================================
    print("Step 5: Reviewing handoff history...")
    print("-" * 70)

    history = handoff.get_handoff_history(result2["execution_id"])

    print("Handoff Trail for Complex Task:")
    print(f"  - Total decisions: {len(history)}")
    print()

    for idx, decision in enumerate(history, 1):
        print(f"  Decision {idx}:")
        print(f"    Tier: {decision['tier_level']}")
        print(f"    Can handle: {decision['can_handle']}")
        print(f"    Complexity: {decision['complexity_score']:.2f}")
        print(f"    Action: {decision['handoff_decision']}")
        if decision["can_handle"] == "no":
            print(f"    Requires tier: {decision['requires_tier']}")
        print()

    # ==================================================================
    # STEP 6: Execute with Max Tier Limit
    # ==================================================================
    print("Step 6: Executing with tier limit...")
    print("-" * 70)

    result3 = handoff.execute_with_handoff(
        task=complex_task,
        context="Production system optimization",
        max_tier=2,  # Limit to tier 2
    )

    print("Execution with max_tier=2:")
    print(f"  - Final tier: {result3['final_tier']}")
    print(f"  - Escalations: {result3['escalation_count']}")
    print("  - Note: Capped at tier 2 even if tier 3 needed")
    print()

    # ==================================================================
    # Summary
    # ==================================================================
    print("=" * 70)
    print("Example Complete!")
    print("=" * 70)
    print()
    print("What you learned:")
    print("  ✓ How to create a handoff pattern (zero-config)")
    print("  ✓ How tasks are automatically routed by complexity")
    print("  ✓ How escalation works (tier1 → tier2 → tier3)")
    print("  ✓ How to review handoff history")
    print("  ✓ How to limit maximum tier level")
    print()
    print("Next steps:")
    print("  → Try example 18: Progressive configuration")
    print("  → Try example 19: Advanced escalation scenarios")
    print("  → Try example 20: Real-world customer support system")
    print()


if __name__ == "__main__":
    main()
