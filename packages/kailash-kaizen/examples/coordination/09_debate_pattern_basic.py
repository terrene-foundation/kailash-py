"""
Example 9: Debate Pattern - Basic Usage

This example demonstrates the basic usage of the DebatePattern with zero-configuration.
A proponent argues FOR a position, an opponent argues AGAINST, and a judge makes the final decision.

Learning Objectives:
- Zero-config pattern creation
- Structured debate flow
- Adversarial reasoning
- Judgment and decision-making

Estimated time: 5 minutes
"""

from kaizen.agents.coordination import create_debate_pattern


def main():
    print("=" * 70)
    print("Debate Pattern - Basic Usage Example")
    print("=" * 70)
    print()

    # ==================================================================
    # STEP 1: Create Pattern (Zero-Config!)
    # ==================================================================
    print("Step 1: Creating debate pattern...")
    print("-" * 70)

    # Create pattern with default settings
    # - Uses gpt-3.5-turbo (default model)
    # - Uses environment variables if set (KAIZEN_MODEL, etc.)
    pattern = create_debate_pattern()

    print("✓ Pattern created successfully!")
    print(f"  - Proponent: {pattern.proponent.agent_id}")
    print(f"  - Opponent: {pattern.opponent.agent_id}")
    print(f"  - Judge: {pattern.judge.agent_id}")
    print(f"  - Shared Memory: {pattern.shared_memory is not None}")
    print()

    # ==================================================================
    # STEP 2: Validate Pattern
    # ==================================================================
    print("Step 2: Validating pattern initialization...")
    print("-" * 70)

    if pattern.validate_pattern():
        print("✓ Pattern validation passed!")
        print(f"  - All agents initialized: {len(pattern.get_agents())} agents")
        print(f"  - Unique agent IDs: {pattern.get_agent_ids()}")
        print("  - Shared memory configured: YES")
    else:
        print("✗ Pattern validation failed!")
        return

    print()

    # ==================================================================
    # STEP 3: Start Debate (Single Round)
    # ==================================================================
    print("Step 3: Starting single-round debate...")
    print("-" * 70)

    # Define debate topic
    topic = "Should companies prioritize AI safety over rapid AI development?"
    context = """
    Context:
    - AI capabilities are advancing rapidly
    - Safety concerns are increasing
    - Competitive pressure is high
    - Regulatory landscape is uncertain
    """

    print(f"Topic: {topic}")
    print(f"Context: {context.strip()[:100]}...")
    print()

    # Run debate (1 round = initial arguments only)
    result = pattern.debate(topic, context, rounds=1)

    print("✓ Debate started!")
    print(f"  - Debate ID: {result['debate_id']}")
    print(f"  - Rounds: {result['rounds']}")
    print()

    # ==================================================================
    # STEP 4: Review Arguments
    # ==================================================================
    print("Step 4: Reviewing arguments...")
    print("-" * 70)

    print("\nProponent Argument (FOR):")
    print(f"  {result['proponent_argument'][:200]}...")
    print("\n  Key Points:")
    for i, point in enumerate(result.get("proponent_key_points", [])[:3], 1):
        print(f"    {i}. {point}")

    print("\nOpponent Argument (AGAINST):")
    print(f"  {result['opponent_argument'][:200]}...")
    print("\n  Key Points:")
    for i, point in enumerate(result.get("opponent_key_points", [])[:3], 1):
        print(f"    {i}. {point}")

    print()

    # ==================================================================
    # STEP 5: Get Judgment
    # ==================================================================
    print("Step 5: Rendering judgment...")
    print("-" * 70)

    # Judge evaluates arguments and makes decision
    judgment = pattern.get_judgment(result["debate_id"])

    print("Judge's Decision:")
    print(f"  - Winner: {judgment['winner'].upper()}")
    print(f"  - Decision: {judgment['decision']}")
    print(f"  - Confidence: {judgment['confidence']:.2f}")
    print()
    print("Reasoning:")
    print(f"  {judgment['reasoning'][:300]}...")
    print()

    # ==================================================================
    # STEP 6: Interpret Results
    # ==================================================================
    print("Step 6: Interpreting results...")
    print("-" * 70)

    # Determine winner
    if judgment["decision"] == "for":
        print("✓ PROPONENT WINS (FOR position)")
        print("  The argument in favor was more compelling")
    elif judgment["decision"] == "against":
        print("✓ OPPONENT WINS (AGAINST position)")
        print("  The argument against was more compelling")
    else:
        print("⚖️  TIE - Both arguments equally compelling")

    print()

    # Judge confidence interpretation
    confidence = judgment["confidence"]
    if confidence > 0.8:
        print(f"  → Very high confidence ({confidence:.2f})")
    elif confidence > 0.6:
        print(f"  → High confidence ({confidence:.2f})")
    elif confidence > 0.4:
        print(f"  → Moderate confidence ({confidence:.2f})")
    else:
        print(f"  → Low confidence ({confidence:.2f})")

    print()

    # ==================================================================
    # STEP 7: Cleanup (Optional)
    # ==================================================================
    print("Step 7: Cleanup (optional)...")
    print("-" * 70)

    # Clear shared memory if you want to reuse the pattern
    pattern.clear_shared_memory()
    print("✓ Shared memory cleared (pattern ready for next debate)")
    print()

    # ==================================================================
    # Summary
    # ==================================================================
    print("=" * 70)
    print("Example Complete!")
    print("=" * 70)
    print()
    print("What you learned:")
    print("  ✓ How to create a debate pattern (zero-config)")
    print("  ✓ How to structure a debate on a topic")
    print("  ✓ How proponents and opponents construct arguments")
    print("  ✓ How judges evaluate and make decisions")
    print("  ✓ How to interpret judgment confidence")
    print("  ✓ How to cleanup shared memory for reuse")
    print()
    print("Next steps:")
    print("  → Try example 10: Progressive configuration")
    print("  → Try example 11: Multi-round debates with rebuttals")
    print("  → Try example 12: Real-world product decision debate")
    print()


if __name__ == "__main__":
    main()
