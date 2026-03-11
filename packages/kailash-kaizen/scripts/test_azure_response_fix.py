#!/usr/bin/env python3
"""
Test script to verify the Azure OpenAI response format fix (Kaizen SDK 0.9.4+).

This script tests that Agent.run() with Azure OpenAI returns proper results
instead of error dicts like {'error': 'Missing required output field: answer', ...}.

Usage:
    # Set Azure credentials first:
    export AZURE_OPENAI_ENDPOINT="https://your-endpoint.openai.azure.com/"
    export AZURE_OPENAI_API_KEY="your-api-key"
    export AZURE_OPENAI_API_VERSION="2025-01-01-preview"  # or your version

    # Run the test:
    python scripts/test_azure_response_fix.py

Expected Results (After Fix):
    - Simple Q&A returns dict with "response" key (validation bypass)
    - No more "Missing required output field: answer" errors
    - API calls complete successfully

Root Cause (Fixed):
    When Azure returns content like "4", json.loads("4") succeeds and returns
    integer 4 (not a dict). This primitive value then fails signature validation.
    The fix wraps primitives in {"response": value} to trigger validation bypass.
"""

import os
import sys
from pathlib import Path

# Add src to path for local development
src_path = Path(__file__).parent.parent / "src"
if src_path.exists():
    sys.path.insert(0, str(src_path))


def test_azure_simple_qa():
    """Test simple Q&A with Azure OpenAI."""
    from kaizen import Agent

    print("\n" + "=" * 70)
    print("TEST: Azure OpenAI Simple Q&A")
    print("=" * 70)

    # Check for Azure credentials
    required_vars = [
        "AZURE_OPENAI_ENDPOINT",
        "AZURE_OPENAI_API_KEY",
    ]

    missing = [var for var in required_vars if not os.environ.get(var)]
    if missing:
        print(f"SKIP: Missing environment variables: {missing}")
        print("Set these variables to run Azure tests.")
        return None

    # Get deployment name from env or use default
    model = os.environ.get("AZURE_OPENAI_DEPLOYMENT", "gpt-4o")

    try:
        # Create agent with Azure provider
        agent = Agent(
            model=model,
            llm_provider="azure",
            agent_type="simple",
            show_startup_banner=False,
        )

        # Run a simple prompt
        print(f"\nUsing model: {model}")
        print("Prompt: 'What is 2+2? Answer with just the number.'")

        result = agent.run("What is 2+2? Answer with just the number.")

        print(f"\nResult type: {type(result)}")
        print(f"Result: {result}")

        # Check for the old bug pattern
        if isinstance(result, dict) and result.get("error"):
            if "Missing required output field" in str(result.get("error", "")):
                print("\n[FAIL] Bug still present - validation error returned!")
                return False
            elif result.get("success") is False:
                print(f"\n[FAIL] Error occurred: {result.get('error')}")
                return False

        # Check for successful result
        if isinstance(result, dict):
            if "response" in result:
                print("\n[PASS] Response received with 'response' key (bypass working)")
                return True
            elif "answer" in result:
                print(
                    "\n[PASS] Response received with 'answer' key (signature extracted)"
                )
                return True
            else:
                print(f"\n[WARN] Unexpected result structure: {list(result.keys())}")
                return True  # Still a success if no error

        print("\n[PASS] Received valid response")
        return True

    except Exception as e:
        print(f"\n[ERROR] Exception occurred: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_parse_result_primitive_handling():
    """Test that parse_result correctly wraps primitives."""
    from kaizen.strategies.async_single_shot import AsyncSingleShotStrategy
    from kaizen.strategies.multi_cycle import MultiCycleStrategy
    from kaizen.strategies.single_shot import SingleShotStrategy

    print("\n" + "=" * 70)
    print("TEST: parse_result() Primitive Handling")
    print("=" * 70)

    # Test cases: (input_content, expected_type, description)
    test_cases = [
        ("4", int, "JSON integer"),
        ('"hello"', str, "JSON string"),
        ("true", bool, "JSON boolean"),
        ("[1, 2, 3]", list, "JSON array"),
        ('{"answer": "4"}', dict, "JSON object (passthrough)"),
        ("The answer is 4.", str, "Plain text (fallback)"),
    ]

    all_passed = True

    for content, expected_type, description in test_cases:
        raw_result = {"agent_exec": {"response": {"content": content}}}

        # Test sync strategy
        sync_strategy = SingleShotStrategy()
        sync_result = sync_strategy.parse_result(raw_result)

        # Test async strategy
        async_strategy = AsyncSingleShotStrategy()
        async_result = async_strategy.parse_result(raw_result)

        # Test multi-cycle strategy
        multi_strategy = MultiCycleStrategy(max_cycles=3)
        multi_result = multi_strategy.parse_result(raw_result)

        # Verify results
        sync_ok = isinstance(sync_result, dict)
        async_ok = isinstance(async_result, dict)
        multi_ok = isinstance(multi_result, dict)

        if expected_type == dict and content.startswith("{"):
            # Dict should pass through without wrapping
            sync_ok = sync_ok and "response" not in sync_result
            async_ok = async_ok and "response" not in async_result
            multi_ok = multi_ok and "response" not in multi_result
        else:
            # Primitives and errors should have "response" key
            sync_ok = sync_ok and "response" in sync_result
            async_ok = async_ok and "response" in async_result
            multi_ok = multi_ok and "response" in multi_result

        status = "[PASS]" if (sync_ok and async_ok and multi_ok) else "[FAIL]"
        print(f"{status} {description}: content={content[:20]}...")

        if not (sync_ok and async_ok and multi_ok):
            all_passed = False
            print(f"  Sync result: {sync_result}")
            print(f"  Async result: {async_result}")
            print(f"  Multi result: {multi_result}")

    return all_passed


def main():
    """Run all tests."""
    print("=" * 70)
    print("Azure OpenAI Response Format Fix Verification")
    print("Kaizen SDK 0.9.4+")
    print("=" * 70)

    results = []

    # Test 1: parse_result primitive handling (unit test level)
    results.append(("parse_result primitives", test_parse_result_primitive_handling()))

    # Test 2: Azure OpenAI integration (requires credentials)
    results.append(("Azure OpenAI Q&A", test_azure_simple_qa()))

    # Summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)

    for name, result in results:
        if result is None:
            status = "SKIPPED"
        elif result:
            status = "PASSED"
        else:
            status = "FAILED"
        print(f"  {name}: {status}")

    # Exit code
    failed = sum(1 for _, r in results if r is False)
    if failed > 0:
        print(f"\n{failed} test(s) failed!")
        sys.exit(1)
    else:
        print("\nAll tests passed!")
        sys.exit(0)


if __name__ == "__main__":
    main()
