#!/usr/bin/env python3
"""
Critical Faults Test - Verify the most serious implementation issues
"""

import asyncio
import sys
from pathlib import Path

# Add paths for testing
sys.path.insert(0, str(Path(__file__).parent / "apps/kailash-dataflow/src"))
sys.path.insert(0, str(Path(__file__).parent / "apps/kailash-nexus/src"))
sys.path.insert(0, str(Path(__file__).parent / "tests/utils"))

from docker_config import is_postgres_available, is_redis_available


def test_dataflow_basic_functionality():
    """Test DataFlow basic functionality."""
    print("🔍 Testing DataFlow Basic Functionality...")

    try:
        from dataflow import DataFlow, DataFlowConfig, DataFlowModel

        print("✅ DataFlow imports successful")

        # Test initialization
        db = DataFlow()
        print("✅ DataFlow initialization successful")

        # Test model decorator
        @db.model
        class TestUser:
            name: str
            email: str
            active: bool = True

        print("✅ Model decorator working")

        # Test model registration
        models = db.get_models()
        if "TestUser" in models:
            print("✅ Model registration working")
        else:
            print("❌ Model registration failed")
            return False

        # Test health check
        health = db.health_check()
        if health.get("status") == "healthy":
            print("✅ Health check working")
        else:
            print("❌ Health check failed")
            return False

        print("✅ DataFlow: ALL BASIC TESTS PASSED")
        return True

    except Exception as e:
        print(f"❌ DataFlow basic test failed: {e}")
        return False


async def test_nexus_enterprise_backup():
    """Test if Nexus backup is real or simulated."""
    print("\n🔍 Testing Nexus Enterprise Backup...")

    try:
        import sys

        sys.path.insert(0, str(Path(__file__).parent / "apps/kailash-nexus/src"))
        from nexus import create_application

        app = create_application(
            name="Backup Test",
            channels={
                "api": {"enabled": False},
                "cli": {"enabled": False},
                "mcp": {"enabled": False},
            },
        )

        # Test backup functionality
        backup_result = await app.backup_manager.create_backup("database")

        # Check if this is real or simulated
        if backup_result.metadata.get("storage_location", "").startswith("s3://"):
            print("⚠️  Backup storage location is simulated S3 URL")

        if backup_result.size_bytes == 1024 * 1024 * 50:  # Exactly 50MB
            print("❌ CRITICAL: Backup size is hardcoded simulation (50MB)")
            print(f"   Backup metadata: {backup_result.metadata}")
            return False

        print("✅ Backup appears to have real implementation")
        return True

    except Exception as e:
        print(f"❌ Nexus backup test failed: {e}")
        return False


async def test_nexus_disaster_recovery():
    """Test if Nexus disaster recovery is real or simulated."""
    print("\n🔍 Testing Nexus Disaster Recovery...")

    try:
        import sys

        sys.path.insert(0, str(Path(__file__).parent / "apps/kailash-nexus/src"))
        from nexus import create_application
        from nexus.enterprise.disaster_recovery import DRSite, DRStatus

        app = create_application(
            name="DR Test",
            channels={
                "api": {"enabled": False},
                "cli": {"enabled": False},
                "mcp": {"enabled": False},
            },
        )

        # Add a DR site with real test endpoints
        dr_site = DRSite(
            site_id="test_dr",
            name="Test DR Site",
            region="us-east-1",
            status=DRStatus.HEALTHY,
            is_primary=False,
            endpoints={
                "api": "http://localhost:8080",  # Use real test endpoint
                "database": "localhost:5434",
                "cache": "localhost:6380",
            },
        )

        result = app.disaster_recovery.add_dr_site(dr_site)
        print(f"✅ DR site added: {result}")

        # Test failover - this should reveal if it's simulated
        import time

        start_time = time.time()

        try:
            failover_result = await app.disaster_recovery.initiate_failover("test_dr")
            duration = time.time() - start_time

            # Check if duration matches simulation sleep times (5.0 seconds total + overhead)
            if 4.5 <= duration <= 7.0:
                print(
                    f"❌ CRITICAL: Failover took {duration:.2f}s - likely simulation with asyncio.sleep()"
                )
                print(
                    "   Real failover should be much faster (<1s) or much slower (>30s)"
                )
                return False
            else:
                print(
                    f"✅ Failover duration {duration:.2f}s suggests real implementation"
                )
                return True

        except Exception as e:
            print(f"❌ Failover test failed: {e}")
            return False

    except Exception as e:
        print(f"❌ Nexus DR test failed: {e}")
        return False


def test_infrastructure_availability():
    """Test if required infrastructure is available."""
    print("\n🔍 Testing Infrastructure Availability...")

    postgres_ok = is_postgres_available()
    redis_ok = is_redis_available()

    print(f"PostgreSQL (port 5434): {'✅' if postgres_ok else '❌'}")
    print(f"Redis (port 6380): {'✅' if redis_ok else '❌'}")

    if not postgres_ok or not redis_ok:
        print("⚠️  Some infrastructure not available - integration tests may fail")
        print("   Run: ./tests/utils/test-env up")
        return False

    print("✅ All required infrastructure available")
    return True


async def main():
    """Run all critical fault tests."""
    print("🧠 CRITICAL FAULTS VERIFICATION")
    print("=" * 50)

    results = {}

    # Test 1: DataFlow basic functionality
    results["dataflow_basic"] = test_dataflow_basic_functionality()

    # Test 2: Infrastructure availability
    results["infrastructure"] = test_infrastructure_availability()

    # Test 3: Nexus enterprise backup
    results["nexus_backup"] = await test_nexus_enterprise_backup()

    # Test 4: Nexus disaster recovery
    results["nexus_dr"] = await test_nexus_disaster_recovery()

    # Summary
    print("\n" + "=" * 50)
    print("🚨 CRITICAL FAULTS SUMMARY")
    print("=" * 50)

    passed = sum(results.values())
    total = len(results)

    for test_name, passed_test in results.items():
        status = "✅ PASS" if passed_test else "❌ FAIL"
        print(f"{test_name}: {status}")

    print(f"\nOVERALL: {passed}/{total} tests passed")

    if passed == total:
        print("🎉 All critical tests PASSED!")
        return 0
    else:
        print("💥 CRITICAL FAULTS CONFIRMED - Need immediate fixes")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
