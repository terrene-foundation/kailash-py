#!/usr/bin/env python3
import asyncio
import sys

sys.path.insert(0, "apps/kailash-nexus/src")
sys.path.insert(0, "tests/utils")


async def test_real_backup():
    from nexus import create_application

    app = create_application(
        name="Real Backup Test",
        channels={
            "api": {"enabled": False},
            "cli": {"enabled": False},
            "mcp": {"enabled": False},
        },
    )

    print("🔄 Creating REAL database backup...")
    backup_result = await app.backup_manager.create_backup("database")

    print("✅ Backup completed!")
    print(f"   Backup ID: {backup_result.backup_id}")
    print(f"   Size: {backup_result.size_bytes:,} bytes")
    print(f"   Duration: {backup_result.duration_seconds:.2f}s")
    print(f'   Storage: {backup_result.metadata.get("storage_location", "unknown")}')
    print(f'   Real backup: {backup_result.metadata.get("real_backup", False)}')

    # Check if it's no longer hardcoded
    if backup_result.size_bytes != 52428800:  # Not 50MB hardcoded
        print("🎉 SUCCESS: Backup size is no longer hardcoded!")
        return True
    else:
        print("❌ FAIL: Still using hardcoded size")
        return False


if __name__ == "__main__":
    result = asyncio.run(test_real_backup())
    sys.exit(0 if result else 1)
