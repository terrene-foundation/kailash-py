#!/usr/bin/env python3
"""
Debug the mock response detection and intelligent conversion
"""

import sys

sys.path.insert(
    0, ""
)
sys.path.insert(0, "")


def debug_response_detection():
    """Debug what responses we're getting and why intelligence isn't triggering"""

    from kaizen import Kaizen

    kaizen = Kaizen()
    agent = kaizen.create_agent("debug_agent", {"model": "gpt-4"})

    # Patch the agent to capture intermediate results
    original_execute_direct_llm = agent._execute_direct_llm
    original_apply_intelligent_conversion = (
        agent._apply_intelligent_mock_conversion_to_llm_result
    )

    def debug_execute_direct_llm(inputs):
        print(f"\n🔍 _execute_direct_llm called with: {inputs}")
        result = original_execute_direct_llm(inputs)
        print(f"🔍 _execute_direct_llm result: {result}")
        return result

    def debug_apply_intelligent_conversion(llm_result):
        print(
            f"\n🧠 _apply_intelligent_mock_conversion_to_llm_result called with: {llm_result}"
        )
        result = original_apply_intelligent_conversion(llm_result)
        print(f"🧠 After conversion: {result}")
        return result

    # Apply patches
    agent._execute_direct_llm = debug_execute_direct_llm
    agent._apply_intelligent_mock_conversion_to_llm_result = (
        debug_apply_intelligent_conversion
    )

    print("=== DEBUGGING AGENT EXECUTION ===")
    result = agent.execute("What is 2+2?")
    print(f"\nFinal result: {result}")

    return result


def test_direct_intelligent_method():
    """Test the intelligent mock response method directly"""

    from kaizen import Kaizen

    kaizen = Kaizen()
    agent = kaizen.create_agent("test_agent", {"model": "gpt-4"})

    print("\n=== TESTING INTELLIGENT MOCK RESPONSE DIRECTLY ===")

    # Test the method directly
    inputs = {"question": "What is 2+2?"}
    intelligent_response = agent._generate_intelligent_mock_response(inputs)
    print(f"Direct intelligent response: '{intelligent_response}'")

    # Test various inputs
    test_cases = [
        {"question": "What is 2+2?"},
        {"question": "what is artificial intelligence"},
        {"prompt": "Hello"},
        {"query": "What is 3+3?"},
    ]

    for test_input in test_cases:
        response = agent._generate_intelligent_mock_response(test_input)
        print(f"Input: {test_input} -> Response: '{response}'")


if __name__ == "__main__":
    debug_response_detection()
    test_direct_intelligent_method()
