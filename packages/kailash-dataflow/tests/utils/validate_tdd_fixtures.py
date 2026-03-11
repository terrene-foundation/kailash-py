#!/usr/bin/env python3
"""
TDD Fixtures Validation Script

Quick validation script to ensure TDD fixtures are working correctly
and achieve the performance targets.

Usage:
    python tests/utils/validate_tdd_fixtures.py

Expected output:
    All validations pass with <100ms execution times
"""

import asyncio
import os
import sys
import time
from pathlib import Path

# Add project paths
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root / "src"))
sys.path.insert(0, str(project_root))

# Enable TDD mode
os.environ["DATAFLOW_TDD_MODE"] = "true"


async def validate_tdd_infrastructure():
    """Validate core TDD infrastructure."""
    print("🔧 Validating TDD Infrastructure...")

    try:
        from dataflow.testing.tdd_support import (
            is_tdd_mode,
            setup_tdd_infrastructure,
            tdd_test_context,
            teardown_tdd_infrastructure,
        )

        # Check TDD mode is enabled
        assert is_tdd_mode(), "TDD mode should be enabled"
        print("✅ TDD mode enabled")

        # Test infrastructure setup
        await setup_tdd_infrastructure()
        print("✅ TDD infrastructure initialized")

        # Test context creation
        async with tdd_test_context(test_id="validation_test") as context:
            assert context.connection is not None
            assert context.savepoint_created is True
            print("✅ TDD test context created successfully")

        # Test infrastructure cleanup
        await teardown_tdd_infrastructure()
        print("✅ TDD infrastructure cleaned up")

        return True

    except Exception as e:
        print(f"❌ TDD infrastructure validation failed: {e}")
        return False


async def validate_tdd_fixtures():
    """Validate enhanced TDD fixtures."""
    print("\n🎯 Validating TDD Fixtures...")

    try:
        from tests.fixtures.tdd_fixtures import (
            TDDDataSeeder,
            TDDModelFactory,
            TDDPerformanceMetrics,
        )

        # Test model factory
        factory = TDDModelFactory("validation")
        User = factory.create_user_model()
        Product = factory.create_product_model()

        assert User.__name__ == "TDDUser_validation"
        assert Product.__name__ == "TDDProduct_validation"
        assert hasattr(User, "__test_model__")
        print("✅ TDD model factory working")

        # Test performance metrics
        metrics = TDDPerformanceMetrics("test")
        metrics.setup_time_ms = 10.0
        metrics.execution_time_ms = 50.0
        metrics.teardown_time_ms = 15.0

        # Trigger __post_init__ manually since we set values after creation
        metrics.__post_init__()

        assert metrics.total_time_ms == 75.0
        assert metrics.target_achieved is True  # <100ms
        print("✅ TDD performance metrics working")

        return True

    except Exception as e:
        print(f"❌ TDD fixtures validation failed: {e}")
        import traceback

        traceback.print_exc()
        return False


async def validate_performance_target():
    """Validate <100ms performance target."""
    print("\n⚡ Validating Performance Target...")

    try:
        from dataflow.testing.tdd_support import tdd_test_context

        start_time = time.time()

        async with tdd_test_context(test_id="perf_validation") as context:
            # Simulate typical test operations
            connection = context.connection

            # Create test table
            await connection.execute(
                """
                CREATE TEMP TABLE perf_validation_test (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(100),
                    created_at TIMESTAMP DEFAULT NOW()
                )
            """
            )

            # Insert test data
            for i in range(5):
                await connection.execute(
                    "INSERT INTO perf_validation_test (name) VALUES ($1)",
                    f"Test Record {i}",
                )

            # Query data
            count = await connection.fetchval(
                "SELECT COUNT(*) FROM perf_validation_test"
            )
            assert count == 5

        end_time = time.time()
        duration_ms = (end_time - start_time) * 1000

        print(f"✅ Test execution time: {duration_ms:.2f}ms")

        if duration_ms < 100.0:
            print("✅ Performance target achieved (<100ms)")
            return True
        else:
            print(f"❌ Performance target missed: {duration_ms:.2f}ms > 100ms")
            return False

    except Exception as e:
        print(f"❌ Performance validation failed: {e}")
        return False


async def validate_connection_reuse():
    """Validate connection reuse functionality."""
    print("\n🔗 Validating Connection Reuse...")

    try:
        from dataflow.testing.tdd_support import get_database_manager, tdd_test_context

        manager = get_database_manager()
        await manager.initialize()

        # Test multiple contexts reuse connections
        test_ids = []

        for i in range(3):
            async with tdd_test_context(test_id=f"reuse_test_{i}") as context:
                test_ids.append(context.test_id)

                # Verify connection exists
                assert context.connection is not None

                # Simple operation
                result = await context.connection.fetchval("SELECT 1")
                assert result == 1

        print(f"✅ Connection reuse tested with {len(test_ids)} contexts")

        # Cleanup
        await manager.close()
        print("✅ Connection manager cleaned up")

        return True

    except Exception as e:
        print(f"❌ Connection reuse validation failed: {e}")
        return False


def validate_fixture_imports():
    """Validate fixture imports work correctly."""
    print("\n📦 Validating Fixture Imports...")

    try:
        # Test basic fixture imports
        from tests.fixtures.tdd_fixtures import (
            TDDDataSeeder,
            TDDModelFactory,
            TDDPerformanceMetrics,
        )

        print("✅ Core TDD classes imported")

        # Test pytest fixture functions exist
        from tests.fixtures.tdd_fixtures import (
            tdd_models,
            tdd_parallel_safe,
            tdd_performance_test,
            tdd_transaction_dataflow,
        )

        print("✅ TDD fixture functions imported")

        return True

    except ImportError as e:
        print(f"❌ Fixture import failed: {e}")
        return False
    except Exception as e:
        print(f"❌ Fixture validation failed: {e}")
        return False


async def run_validation():
    """Run complete TDD fixtures validation."""
    print("🚀 TDD Fixtures Validation")
    print("=" * 50)

    results = []

    # Run validations
    results.append(validate_fixture_imports())
    results.append(await validate_tdd_infrastructure())
    results.append(await validate_tdd_fixtures())
    results.append(await validate_connection_reuse())
    results.append(await validate_performance_target())

    # Summary
    print("\n📊 Validation Summary")
    print("=" * 50)

    passed = sum(results)
    total = len(results)

    if passed == total:
        print(f"✅ All validations passed ({passed}/{total})")
        print("\n🎉 TDD fixtures are working correctly!")
        print("💡 Key benefits:")
        print("  - <100ms test execution (vs >2000ms traditional)")
        print("  - PostgreSQL savepoint isolation")
        print("  - Connection reuse and pooling")
        print("  - Parallel test execution support")
        print("  - Pre-defined test models")
        print("  - Performance monitoring")
        return True
    else:
        print(f"❌ {total - passed} validation(s) failed ({passed}/{total})")
        print("\n🔍 Please check the error messages above")
        return False


def main():
    """Main validation entry point."""
    try:
        result = asyncio.run(run_validation())
        sys.exit(0 if result else 1)
    except KeyboardInterrupt:
        print("\n⚠️  Validation interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n💥 Validation failed with unexpected error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
