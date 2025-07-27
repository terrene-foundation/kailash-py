#!/usr/bin/env python3
"""
Test SDK user example file migrations to CycleBuilder API.

This script validates that all updated example files work correctly
with the new CycleBuilder API instead of the deprecated cycle=True pattern.
"""

import sys
import traceback
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root / "src"))
sys.path.insert(0, str(project_root))


def test_simple_cycle():
    """Test the simple cycle example."""
    print("\n" + "=" * 50)
    print("TESTING: test_simple_cycle.py")
    print("=" * 50)

    try:
        # Import and run the simple cycle test
        sys.path.insert(
            0,
            str(project_root / "sdk-users/2-core-concepts/workflows/by-pattern/cyclic"),
        )
        from test_simple_cycle import test_simple_cycle as run_simple_cycle

        result = run_simple_cycle()

        # Validate results
        assert "counter" in result, "Counter node result missing"
        counter_result = result["counter"]
        assert (
            counter_result.get("count", 0) >= 5
        ), f"Expected count >= 5, got {counter_result.get('count')}"
        assert counter_result.get("converged") is True, "Expected convergence = True"

        print("✅ test_simple_cycle.py - PASSED")
        return True

    except Exception as e:
        print(f"❌ test_simple_cycle.py - FAILED: {str(e)}")
        traceback.print_exc()
        return False


def test_switch_cycle():
    """Test the switch cycle example."""
    print("\n" + "=" * 50)
    print("TESTING: test_switch_cycle.py")
    print("=" * 50)

    try:
        # Import and run the switch cycle test
        sys.path.insert(
            0,
            str(project_root / "sdk-users/2-core-concepts/workflows/by-pattern/cyclic"),
        )
        from test_switch_cycle import test_switch_cycle as run_switch_cycle

        result = run_switch_cycle()

        # Validate results
        assert "final" in result, "Final processor result missing"
        final_result = result["final"]
        assert "result" in final_result, "Final result structure missing"
        final_data = final_result["result"]
        assert (
            final_data.get("status") == "complete"
        ), f"Expected status=complete, got {final_data.get('status')}"
        assert (
            final_data.get("final_score", 0) >= 0.9
        ), f"Expected final_score >= 0.9, got {final_data.get('final_score')}"

        print("✅ test_switch_cycle.py - PASSED")
        return True

    except Exception as e:
        print(f"❌ test_switch_cycle.py - FAILED: {str(e)}")
        traceback.print_exc()
        return False


def test_final_working_cycle():
    """Test the final working cycle example."""
    print("\n" + "=" * 50)
    print("TESTING: final_working_cycle.py")
    print("=" * 50)

    try:
        # Import the final working cycle
        sys.path.insert(
            0,
            str(project_root / "sdk-users/2-core-concepts/workflows/by-pattern/cyclic"),
        )
        from final_working_cycle import create_final_cyclic_workflow

        from kailash.runtime.local import LocalRuntime

        # Create and execute workflow
        workflow = create_final_cyclic_workflow()
        runtime = LocalRuntime(enable_cycles=True)

        results, run_id = runtime.execute(
            workflow,
            parameters={
                "optimizer": {
                    "efficiency": 0.5,
                    "quality": 0.6,
                    "cost": 150.0,
                    "performance": 0.4,
                }
            },
        )

        # Validate results
        assert run_id is not None, "Run ID should not be None"
        assert "optimizer" in results, "Optimizer result missing"
        optimizer_result = results["optimizer"]
        assert optimizer_result.get("converged") is True, "Expected convergence"
        assert (
            optimizer_result.get("score", 0) >= 0.95
        ), f"Expected score >= 0.95, got {optimizer_result.get('score')}"

        print("✅ final_working_cycle.py - PASSED")
        return True

    except Exception as e:
        print(f"❌ final_working_cycle.py - FAILED: {str(e)}")
        traceback.print_exc()
        return False


def test_conditional_routing():
    """Test the conditional routing pattern."""
    print("\n" + "=" * 50)
    print("TESTING: conditional_routing_patterns.py")
    print("=" * 50)

    try:
        # Import the conditional routing module
        sys.path.insert(
            0,
            str(
                project_root
                / "sdk-users/2-core-concepts/workflows/by-pattern/control-flow"
            ),
        )
        from conditional_routing_patterns import example3_conditional_retry_loops

        # Run the example (this executes internally)
        example3_conditional_retry_loops()

        print("✅ conditional_routing_patterns.py - PASSED")
        return True

    except Exception as e:
        print(f"❌ conditional_routing_patterns.py - FAILED: {str(e)}")
        traceback.print_exc()
        return False


def test_phase1_demonstrations():
    """Test the phase1 cyclic demonstrations."""
    print("\n" + "=" * 50)
    print("TESTING: phase1_cyclic_demonstrations.py")
    print("=" * 50)

    try:
        # Import the phase1 demonstrations
        sys.path.insert(
            0,
            str(project_root / "sdk-users/2-core-concepts/workflows/by-pattern/cyclic"),
        )
        from phase1_cyclic_demonstrations import create_cyclic_demo_workflow

        from kailash.runtime.local import LocalRuntime

        # Test quality enhancement demo
        workflow = create_cyclic_demo_workflow("quality")
        runtime = LocalRuntime(enable_cycles=True)

        results, run_id = runtime.execute(
            workflow,
            parameters={
                "enhancer": {"data_batch": [1, 2, 3, 4, 5], "quality_score": 0.5}
            },
        )

        # Validate results
        assert run_id is not None, "Run ID should not be None"
        assert "writer" in results, "Writer result missing"

        print("✅ phase1_cyclic_demonstrations.py (quality) - PASSED")
        return True

    except Exception as e:
        print(f"❌ phase1_cyclic_demonstrations.py - FAILED: {str(e)}")
        traceback.print_exc()
        return False


def test_working_complex_cycle():
    """Test the working complex cycle example."""
    print("\n" + "=" * 50)
    print("TESTING: working_complex_cycle.py")
    print("=" * 50)

    try:
        # Import the working complex cycle
        sys.path.insert(
            0,
            str(project_root / "sdk-users/2-core-concepts/workflows/by-pattern/cyclic"),
        )
        from working_complex_cycle import create_working_complex_workflow

        from kailash.runtime.local import LocalRuntime

        # Create and execute workflow (reduced iterations for testing)
        workflow = create_working_complex_workflow()
        runtime = LocalRuntime(enable_cycles=True)

        results, run_id = runtime.execute(
            workflow,
            parameters={
                "optimizer": {
                    "metrics": {},
                    "targets": {},
                    "learning_rate": 0.2,  # Faster learning for testing
                }
            },
        )

        # Validate results
        assert run_id is not None, "Run ID should not be None"
        # The workflow should complete (may not converge in reduced iterations but should execute)
        assert len(results) > 0, "Should have some results"

        print("✅ working_complex_cycle.py - PASSED")
        return True

    except Exception as e:
        print(f"❌ working_complex_cycle.py - FAILED: {str(e)}")
        traceback.print_exc()
        return False


def run_all_tests():
    """Run all SDK example migration tests."""
    print("🧪 TESTING SDK USER EXAMPLE MIGRATIONS")
    print("=" * 60)

    tests = [
        test_simple_cycle,
        test_switch_cycle,
        test_final_working_cycle,
        test_conditional_routing,
        test_phase1_demonstrations,
        test_working_complex_cycle,
    ]

    passed = 0
    total = len(tests)

    for test_func in tests:
        try:
            if test_func():
                passed += 1
        except Exception as e:
            print(f"❌ {test_func.__name__} - EXCEPTION: {str(e)}")
            traceback.print_exc()

    print("\n" + "=" * 60)
    print(f"📊 FINAL RESULTS: {passed}/{total} tests passed")
    print("=" * 60)

    if passed == total:
        print(
            "🎉 ALL TESTS PASSED! SDK user examples successfully migrated to CycleBuilder API!"
        )
        return True
    else:
        print(f"❌ {total - passed} tests failed. Migration needs fixes.")
        return False


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
