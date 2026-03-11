#!/usr/bin/env python3
"""
Fix remaining test import issues.

This script fixes syntax errors and import issues in integration tests.
"""

import os
import re
from pathlib import Path


def fix_batched_executor_integration_test():
    """Fix import syntax error in batched_migration_executor_integration test."""
    filepath = Path(
        "./repos/projects/kailash_python_sdk/packages/kailash-dataflow/tests/integration/test_batched_migration_executor_integration.py"
    )

    if filepath.exists():
        with open(filepath, "r") as f:
            content = f.read()

        # Fix the import syntax error (lines 11-15 are messed up)
        broken_import = """from dataflow.migrations.batched_migration_executor import BatchedMigrationExecutor
from dataflow.migrations.migration_connection_manager import (
from tests.utils.real_infrastructure import real_infra
    MigrationConnectionManager,
    ConnectionPoolConfig
)"""

        fixed_import = """from dataflow.migrations.batched_migration_executor import BatchedMigrationExecutor
from dataflow.migrations.migration_connection_manager import (
    MigrationConnectionManager,
    ConnectionPoolConfig
)
from tests.utils.real_infrastructure import real_infra"""

        content = content.replace(broken_import, fixed_import)

        with open(filepath, "w") as f:
            f.write(content)

        print(f"Fixed import syntax in {filepath.name}")


def add_missing_methods_to_real_infrastructure():
    """Add missing methods to real_infrastructure module."""
    filepath = Path(
        "./repos/projects/kailash_python_sdk/packages/kailash-dataflow/tests/utils/real_infrastructure.py"
    )

    if filepath.exists():
        with open(filepath, "r") as f:
            content = f.read()

        # Add missing methods before the global instance line
        if "get_sqlite_memory_db" not in content:
            additional_methods = '''
    def get_sqlite_memory_db(self):
        """Get SQLite in-memory database for testing."""
        from dataflow import DataFlow
        return DataFlow(":memory:")

    def get_postgresql_test_db(self):
        """Get PostgreSQL test database."""
        from dataflow import DataFlow
        url = self.get_postgres_url()
        try:
            return DataFlow(url)
        except Exception as e:
            print(f"Failed to connect to PostgreSQL: {e}")
            return None

    def get_mysql_test_db(self):
        """Get MySQL test database (placeholder)."""
        # MySQL support not yet implemented
        return None


'''
            # Insert before "# Global instance"
            content = content.replace(
                "# Global instance", additional_methods + "# Global instance"
            )

        with open(filepath, "w") as f:
            f.write(content)

        print(f"Added missing methods to {filepath.name}")


def fix_all_integration_tests():
    """Fix common import issues in all integration tests."""
    integration_dir = Path(
        "./repos/projects/kailash_python_sdk/packages/kailash-dataflow/tests/integration"
    )

    problem_files = [
        "test_migration_history_manager.py",
        "test_gateway_integration.py",
        "test_engine_schema_state_integration.py",
        "test_migration_performance_tracker_integration.py",
        "test_migration_test_framework_integration.py",
        "test_model_registry.py",
        "test_postgresql_migration_system_integration.py",
        "test_postgresql_test_manager_integration.py",
        "test_schema_state_manager_integration.py",
    ]

    for filename in problem_files:
        filepath = integration_dir / filename
        if filepath.exists():
            with open(filepath, "r") as f:
                content = f.read()

            # Ensure real_infrastructure import if missing
            if "from tests.utils.real_infrastructure import real_infra" not in content:
                # Add after other imports
                if "import pytest" in content:
                    content = content.replace(
                        "import pytest",
                        "import pytest\nfrom tests.utils.real_infrastructure import real_infra",
                    )

            # Fix any relative imports that might be broken
            content = content.replace(
                "from ..utils.real_infrastructure",
                "from tests.utils.real_infrastructure",
            )

            with open(filepath, "w") as f:
                f.write(content)

            print(f"Fixed imports in {filename}")


def fix_monitoring_tests():
    """Fix monitoring test imports."""
    monitoring_dir = Path(
        "./repos/projects/kailash_python_sdk/packages/kailash-dataflow/tests/integration/monitoring"
    )

    if monitoring_dir.exists():
        for filepath in monitoring_dir.glob("*.py"):
            if filepath.name.startswith("test_"):
                with open(filepath, "r") as f:
                    content = f.read()

                # Add real_infrastructure import
                if (
                    "from tests.utils.real_infrastructure import real_infra"
                    not in content
                ):
                    if "import pytest" in content:
                        content = content.replace(
                            "import pytest",
                            "import pytest\nfrom tests.utils.real_infrastructure import real_infra",
                        )
                    else:
                        content = (
                            "from tests.utils.real_infrastructure import real_infra\n"
                            + content
                        )

                with open(filepath, "w") as f:
                    f.write(content)

                print(f"Fixed imports in {filepath.name}")


def fix_dataflow_integration_tests():
    """Fix dataflow subdirectory integration tests."""
    dataflow_dir = Path(
        "./repos/projects/kailash_python_sdk/packages/kailash-dataflow/tests/integration/dataflow"
    )

    if dataflow_dir.exists():
        for filepath in dataflow_dir.rglob("test_*.py"):
            with open(filepath, "r") as f:
                content = f.read()

            # Add real_infrastructure import
            if "from tests.utils.real_infrastructure import real_infra" not in content:
                if "import pytest" in content:
                    content = content.replace(
                        "import pytest",
                        "import pytest\nfrom tests.utils.real_infrastructure import real_infra",
                    )
                else:
                    content = (
                        "from tests.utils.real_infrastructure import real_infra\n"
                        + content
                    )

            with open(filepath, "w") as f:
                f.write(content)

            print(f"Fixed imports in {filepath.name}")


def main():
    """Run all fixes."""
    print("Fixing remaining test import issues...\n")

    fix_batched_executor_integration_test()
    add_missing_methods_to_real_infrastructure()
    fix_all_integration_tests()
    fix_monitoring_tests()
    fix_dataflow_integration_tests()

    print("\n✅ All import fixes applied!")
    print("\nNext steps:")
    print("1. Run: python -m pytest tests/integration/ --collect-only")
    print("2. Run: python -m pytest tests/e2e/ --collect-only")

    return 0


if __name__ == "__main__":
    exit(main())
