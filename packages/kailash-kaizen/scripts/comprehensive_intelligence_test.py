#!/usr/bin/env python3
"""
Comprehensive test of intelligent responses across various question types
"""

import sys

sys.path.insert(0, "")
sys.path.insert(0, "")


def test_comprehensive_intelligence():
    """Test various question types for intelligent responses"""

    from kaizen import Kaizen

    # Test cases mapping questions to expected intelligent responses
    test_cases = [
        # Math questions
        ("What is 2+2?", "4"),
        ("What is 3+3?", "6"),  # Should use the number detection rule
        ("What is 10+15?", "25"),
        # Science questions
        ("What is artificial intelligence?", "Artificial Intelligence"),
        ("what is h2o?", "water"),
        ("Why is the sky blue?", "Rayleigh scattering"),
        # Geography
        ("What is the capital of France?", "Paris"),
        ("What is the largest planet?", "Jupiter"),
        # Greetings
        ("Hello", "Hello!"),
        ("Hi there", "Hello!"),
        # Technology
        ("What is quantum computing?", "quantum mechanical phenomena"),
        # Default case
        (
            "What is xeronexarion?",
            "Based on your question",
        ),  # Should trigger default response
    ]

    print("=== COMPREHENSIVE INTELLIGENCE TEST ===")

    kaizen = Kaizen()
    agent = kaizen.create_agent("intel_test", {"model": "gpt-4"})

    passed = 0
    total = len(test_cases)

    for i, (question, expected_keyword) in enumerate(test_cases, 1):
        print(f"\n{i}. Testing: '{question}'")
        result = agent.execute(question)
        response = result.get("answer", "")

        print(f"   Response: '{response}'")

        # Check if the expected keyword appears in the response
        is_intelligent = expected_keyword.lower() in response.lower()
        status = "✓ PASS" if is_intelligent else "✗ FAIL"
        print(f"   Expected keyword: '{expected_keyword}' -> {status}")

        if is_intelligent:
            passed += 1

    print("\n=== RESULTS ===")
    print(f"Passed: {passed}/{total} ({passed / total * 100:.1f}%)")
    print(
        f"Intelligence system working: {'✓ YES' if passed >= total * 0.8 else '✗ NO'}"
    )


def test_execution_method_consistency():
    """Test that different execution methods work consistently"""

    from kaizen import Kaizen

    print("\n=== EXECUTION METHOD CONSISTENCY TEST ===")

    kaizen = Kaizen()
    agent = kaizen.create_agent(
        "consistency_test", {"model": "gpt-4", "signature": "question -> answer"}
    )

    question = "What is 2+2?"

    # Test direct execution
    result1 = agent.execute(question)
    print(f"execute(string): {result1}")

    # Test keyword execution
    result2 = agent.execute(question=question)
    print(f"execute(question=): {result2}")

    # Test ReAct execution
    result3 = agent.execute_react(question=question)
    print(f"execute_react(): {result3}")

    # Test CoT execution
    result4 = agent.execute_cot(question=question)
    print(f"execute_cot(): {result4}")

    # Check consistency - all should have intelligent "4" somewhere
    responses = [str(result1), str(result2), str(result3), str(result4)]

    intelligent_count = sum(1 for r in responses if "4" in r)
    print(f"\nIntelligent responses: {intelligent_count}/4")
    print(f"Consistency check: {'✓ PASS' if intelligent_count >= 3 else '✗ FAIL'}")


if __name__ == "__main__":
    test_comprehensive_intelligence()
    test_execution_method_consistency()
