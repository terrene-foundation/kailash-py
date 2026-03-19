#!/usr/bin/env python3
"""Run the MCP integration tests to verify implementation."""

import subprocess
import sys

# Add kaizen source to path
sys.path.insert(0, "")


def run_implementation_test():
    """Run our implementation test."""
    print("🚀 Running MCP Implementation Test...")
    result = subprocess.run(
        [sys.executable, "test_mcp_implementation.py"],
        cwd="",
        capture_output=True,
        text=True,
    )

    print("STDOUT:")
    print(result.stdout)
    if result.stderr:
        print("STDERR:")
        print(result.stderr)

    return result.returncode == 0


def run_error_handling_test():
    """Run error handling test."""
    print("\n🛡️ Running MCP Error Handling Test...")
    result = subprocess.run(
        [sys.executable, "test_mcp_error_handling.py"],
        cwd="",
        capture_output=True,
        text=True,
    )

    print("STDOUT:")
    print(result.stdout)
    if result.stderr:
        print("STDERR:")
        print(result.stderr)

    return result.returncode == 0


def run_comprehensive_test():
    """Run comprehensive integration test."""
    print("\n🎯 Running Comprehensive MCP Integration Test...")
    result = subprocess.run(
        [sys.executable, "test_mcp_integration_comprehensive.py"],
        cwd="",
        capture_output=True,
        text=True,
    )

    print("STDOUT:")
    print(result.stdout)
    if result.stderr:
        print("STDERR:")
        print(result.stderr)

    return result.returncode == 0


def run_original_failing_tests():
    """Run the original failing tests to see if they pass now."""
    print("\n🧪 Running Original Failing Tests...")

    # Try to run specific test methods that were originally failing
    test_commands = [
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/unit/test_mcp_integration_missing.py::TestMCPIntegrationMissingMethods::test_agent_expose_as_mcp_tool_method_exists",
            "-v",
        ],
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/unit/test_mcp_integration_missing.py::TestMCPIntegrationMissingMethods::test_agent_expose_as_mcp_tool_basic_functionality",
            "-v",
        ],
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/unit/test_mcp_integration_missing.py::TestMCPIntegrationMissingMethods::test_framework_expose_agent_as_mcp_tool_method_exists",
            "-v",
        ],
    ]

    success_count = 0
    total_tests = len(test_commands)

    for i, cmd in enumerate(test_commands, 1):
        print(f"\n📝 Running Test {i}/{total_tests}...")
        result = subprocess.run(
            cmd,
            cwd="",
            capture_output=True,
            text=True,
        )

        if result.returncode == 0:
            print(f"✅ Test {i} PASSED")
            success_count += 1
        else:
            print(f"❌ Test {i} FAILED")
            print("STDOUT:", result.stdout)
            print("STDERR:", result.stderr)

    print(f"\n📊 Test Results: {success_count}/{total_tests} passed")
    return success_count == total_tests


if __name__ == "__main__":
    print("🗺 MCP Integration Testing Suite")
    print("=" * 50)

    # Run all tests
    impl_success = run_implementation_test()
    error_success = run_error_handling_test()
    comp_success = run_comprehensive_test()
    orig_success = run_original_failing_tests()

    print("\n" + "=" * 50)
    print("📋 FINAL RESULTS:")
    print(f"Implementation Test: {'PASS' if impl_success else 'FAIL'}")
    print(f"Error Handling Test: {'PASS' if error_success else 'FAIL'}")
    print(f"Comprehensive Test: {'PASS' if comp_success else 'FAIL'}")
    print(f"Original Tests: {'PASS' if orig_success else 'FAIL'}")

    total_passed = sum([impl_success, error_success, comp_success, orig_success])
    total_tests = 4

    print(f"\n📊 Overall Results: {total_passed}/{total_tests} test suites passed")

    if total_passed == total_tests:
        print("🎉 ALL TESTS PASSED! MCP integration is working correctly.")
        print("✅ Ready for production use!")
        sys.exit(0)
    else:
        print("❌ Some tests failed. See output above for details.")
        print(f"🔧 {total_tests - total_passed} test suite(s) need attention.")
        sys.exit(1)
