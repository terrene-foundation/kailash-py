"""
Example 11: Debate Pattern - Advanced Usage

This example demonstrates advanced features of the DebatePattern,
including multi-round debates, tie scenarios, confidence analysis, and debate strategies.

Learning Objectives:
- Multi-round debate with rebuttals
- Tie scenario handling
- Confidence analysis
- Rebuttal strength evaluation
- Debate pattern variations

Estimated time: 10 minutes
"""

from typing import Any, Dict

from kaizen.agents.coordination import create_debate_pattern


def analyze_debate_strength(result: Dict[str, Any], judgment: Dict[str, Any]):
    """Analyze the strength of a debate."""
    print("Debate Strength Analysis:")
    print(f"  - Rounds completed: {result['rounds']}")
    print(f"  - Judge confidence: {judgment['confidence']:.2f}")
    print()

    # Interpret confidence
    conf = judgment["confidence"]
    if conf > 0.8:
        strength = "Very clear winner"
    elif conf > 0.6:
        strength = "Clear winner"
    elif conf > 0.4:
        strength = "Slight edge"
    else:
        strength = "Very close / near tie"

    print(f"  Decision strength: {strength}")
    print()


def main():
    print("=" * 70)
    print("Debate Pattern - Advanced Usage Example")
    print("=" * 70)
    print()

    # ==================================================================
    # SCENARIO 1: Single-Round Debate (Basic)
    # ==================================================================
    print("Scenario 1: Single-Round Debate")
    print("-" * 70)

    pattern = create_debate_pattern()

    # Simple debate with no rebuttals
    topic1 = "Should companies implement 4-day work weeks?"
    result1 = pattern.debate(topic1, rounds=1)

    judgment1 = pattern.get_judgment(result1["debate_id"])

    print(f"Topic: {topic1}")
    print(f"Winner: {judgment1['winner'].upper()}")
    print(f"Confidence: {judgment1['confidence']:.2f}")
    print()

    analyze_debate_strength(result1, judgment1)

    # Clear memory for next scenario
    pattern.clear_shared_memory()

    # ==================================================================
    # SCENARIO 2: Multi-Round Debate with Rebuttals
    # ==================================================================
    print("Scenario 2: Multi-Round Debate (3 rounds)")
    print("-" * 70)

    pattern2 = create_debate_pattern(model="gpt-4")

    # Multi-round debate allows rebuttals
    topic2 = "Should AI models be trained on copyrighted content?"
    context2 = "Considering fair use, creator rights, and innovation"

    print(f"Topic: {topic2}")
    print()

    # 3 rounds = initial arguments + 2 rounds of rebuttals
    result2 = pattern2.debate(topic2, context2, rounds=3)

    print("✓ 3-round debate completed")
    print("  - Initial arguments exchanged")
    print("  - Round 2 rebuttals exchanged")
    print("  - Round 3 rebuttals exchanged")
    print()

    judgment2 = pattern2.get_judgment(result2["debate_id"])

    print("Judge's Final Decision:")
    print(f"  Winner: {judgment2['winner'].upper()}")
    print(f"  Confidence: {judgment2['confidence']:.2f}")
    print(f"  Reasoning: {judgment2['reasoning'][:200]}...")
    print()

    analyze_debate_strength(result2, judgment2)

    pattern2.clear_shared_memory()

    # ==================================================================
    # SCENARIO 3: Balanced Debate (Potential Tie)
    # ==================================================================
    print("Scenario 3: Balanced Debate (Potential Tie)")
    print("-" * 70)

    pattern3 = create_debate_pattern()

    # Topic with strong arguments on both sides
    topic3 = "Should social media platforms use algorithmic content curation?"
    context3 = """
    FOR: Personalization, discovery, user engagement
    AGAINST: Filter bubbles, manipulation, echo chambers
    """

    result3 = pattern3.debate(topic3, context3, rounds=2)
    judgment3 = pattern3.get_judgment(result3["debate_id"])

    print(f"Topic: {topic3}")
    print()
    print("Judge's Decision:")
    print(f"  Decision: {judgment3['decision']}")
    print(f"  Winner: {judgment3['winner']}")
    print(f"  Confidence: {judgment3['confidence']:.2f}")
    print()

    if judgment3["decision"] == "tie":
        print("  ⚖️  TIE DECLARED - Both arguments equally compelling")
        print("  Resolution options:")
        print("    → Add more rounds for deeper exploration")
        print("    → Use tiebreaker criteria")
        print("    → Escalate to higher authority")
    elif judgment3["confidence"] < 0.5:
        print("  → Low confidence decision - arguments were very balanced")
    else:
        print("  → Clear winner despite strong opposition")

    print()
    pattern3.clear_shared_memory()

    # ==================================================================
    # SCENARIO 4: Confidence Analysis Across Rounds
    # ==================================================================
    print("Scenario 4: Confidence Analysis Across Rounds")
    print("-" * 70)

    pattern4 = create_debate_pattern(model="gpt-4")

    topic4 = "Should cryptocurrencies replace traditional banking?"

    # Compare 1-round vs 3-round confidence
    print("Testing how multiple rounds affect judge confidence...")
    print()

    # 1-round debate
    result_1r = pattern4.debate(topic4, rounds=1)
    judgment_1r = pattern4.get_judgment(result_1r["debate_id"])

    print("1-Round Debate:")
    print(f"  Winner: {judgment_1r['winner']}")
    print(f"  Confidence: {judgment_1r['confidence']:.2f}")
    print()

    # Clear and run 3-round
    pattern4.clear_shared_memory()

    result_3r = pattern4.debate(topic4, rounds=3)
    judgment_3r = pattern4.get_judgment(result_3r["debate_id"])

    print("3-Round Debate:")
    print(f"  Winner: {judgment_3r['winner']}")
    print(f"  Confidence: {judgment_3r['confidence']:.2f}")
    print()

    # Compare
    if judgment_3r["confidence"] > judgment_1r["confidence"]:
        print("  → Multi-round debate increased confidence")
        print("    (More thorough argument exploration)")
    elif judgment_3r["confidence"] < judgment_1r["confidence"]:
        print("  → Multi-round debate decreased confidence")
        print("    (Rebuttals revealed complexity)")
    else:
        print("  → Confidence unchanged (consistent position)")

    print()
    pattern4.clear_shared_memory()

    # ==================================================================
    # SCENARIO 5: Sequential Debates (Memory Isolation)
    # ==================================================================
    print("Scenario 5: Sequential Debates (Memory Isolation)")
    print("-" * 70)

    pattern5 = create_debate_pattern()

    # Debate 1
    topic5a = "Should offices have mandatory in-person days?"
    result5a = pattern5.debate(topic5a, rounds=1)
    judgment5a = pattern5.get_judgment(result5a["debate_id"])

    print("Debate 1:")
    print(f"  Topic: {topic5a}")
    print(f"  Winner: {judgment5a['winner']}")
    print()

    # Don't clear memory - test isolation

    # Debate 2
    topic5b = "Should code reviews be synchronous or asynchronous?"
    result5b = pattern5.debate(topic5b, rounds=1)
    judgment5b = pattern5.get_judgment(result5b["debate_id"])

    print("Debate 2:")
    print(f"  Topic: {topic5b}")
    print(f"  Winner: {judgment5b['winner']}")
    print()

    # Verify isolation
    print("✓ Debate isolation verified:")
    print(f"  - Debate 1 ID: {result5a['debate_id']}")
    print(f"  - Debate 2 ID: {result5b['debate_id']}")
    print("  - Different IDs ensure no interference")
    print()

    pattern5.clear_shared_memory()

    # ==================================================================
    # SCENARIO 6: Rebuttal Strength Patterns
    # ==================================================================
    print("Scenario 6: Rebuttal Strength Patterns")
    print("-" * 70)

    pattern6 = create_debate_pattern()

    topic6 = "Should programming be taught starting in elementary school?"
    context6 = "Early education curriculum design"

    # Run 2-round debate to get rebuttals
    result6 = pattern6.debate(topic6, context6, rounds=2)
    judgment6 = pattern6.get_judgment(result6["debate_id"])

    print(f"Topic: {topic6}")
    print()
    print("Debate Analysis:")
    print(f"  - Rounds: {result6['rounds']}")
    print(f"  - Final winner: {judgment6['winner']}")
    print(f"  - Final confidence: {judgment6['confidence']:.2f}")
    print()

    # Interpret rebuttal effectiveness
    if judgment6["confidence"] > 0.7:
        print("  → Strong consensus - rebuttals reinforced position")
    elif judgment6["confidence"] > 0.5:
        print("  → Moderate consensus - rebuttals showed balanced strength")
    else:
        print("  → Weak consensus - rebuttals created uncertainty")

    print()

    # ==================================================================
    # Summary
    # ==================================================================
    print("=" * 70)
    print("Advanced Example Complete!")
    print("=" * 70)
    print()
    print("What you learned:")
    print("  ✓ How to run multi-round debates with rebuttals")
    print("  ✓ How to handle tie scenarios")
    print("  ✓ How to analyze judge confidence levels")
    print("  ✓ How round count affects debate thoroughness")
    print("  ✓ How debate isolation works (unique debate_id)")
    print("  ✓ How to interpret rebuttal strength")
    print()
    print("Advanced Patterns:")
    print("  → Weighted arguments (by expertise)")
    print("  → Multiple judges (consensus judgment)")
    print("  → Evidence-based scoring")
    print("  → Moderated debates (with intervention)")
    print("  → Structured debate formats (Oxford, Lincoln-Douglas)")
    print()
    print("Best Practices:")
    print("  → Use 1 round for quick decisions")
    print("  → Use 2-3 rounds for thorough exploration")
    print("  → Use 3+ rounds for complex, high-stakes decisions")
    print("  → Analyze confidence to gauge decision strength")
    print("  → Clear memory between unrelated debates")
    print("  → Use GPT-4 for better arguments and judgments")
    print()


if __name__ == "__main__":
    main()
