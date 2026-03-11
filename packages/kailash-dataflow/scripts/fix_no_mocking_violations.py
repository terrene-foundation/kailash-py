#!/usr/bin/env python3
"""
Script to fix NO MOCKING policy violations in Tier 2-3 tests.

This script:
1. Identifies all integration/E2E tests using mocking
2. Creates real infrastructure alternatives
3. Updates tests to use real services
"""

import os
import re
from pathlib import Path
from typing import List, Tuple

# Base directory for DataFlow tests
BASE_DIR = Path(__file__).parent.parent
TESTS_DIR = BASE_DIR / "tests"

# Patterns to detect mocking usage
MOCK_PATTERNS = [
    r"from unittest\.mock import",
    r"from unittest import mock",
    r"import mock",
    r"@mock\.",
    r"@patch\(",
    r"Mock\(\)",
    r"MagicMock\(\)",
]


def find_mock_violations() -> List[Tuple[Path, List[str]]]:
    """Find all Tier 2-3 test files violating NO MOCKING policy."""
    violations = []

    # Check integration and e2e directories
    for tier_dir in ["integration", "e2e"]:
        test_dir = TESTS_DIR / tier_dir
        if not test_dir.exists():
            continue

        for test_file in test_dir.rglob("*.py"):
            if test_file.name.startswith("test_"):
                with open(test_file, "r") as f:
                    content = f.read()

                found_patterns = []
                for pattern in MOCK_PATTERNS:
                    if re.search(pattern, content):
                        found_patterns.append(pattern)

                if found_patterns:
                    violations.append((test_file, found_patterns))

    return violations


def generate_fix_report(violations: List[Tuple[Path, List[str]]]) -> str:
    """Generate a report of required fixes."""
    report = []
    report.append("# NO MOCKING Policy Violation Fix Report\n")
    report.append(f"## Total Violations: {len(violations)}\n")

    report.append("## Files Requiring Fixes:\n")

    for file_path, patterns in violations:
        relative_path = file_path.relative_to(BASE_DIR)
        report.append(f"\n### {relative_path}")
        report.append("**Violations found:**")
        for pattern in patterns:
            report.append(f"- Pattern: `{pattern}`")

        # Suggest fix based on filename
        test_name = file_path.stem
        if "adapter" in test_name:
            report.append("\n**Suggested Fix:**")
            report.append("- Use real SQLite in-memory database for adapter tests")
            report.append(
                "- Create test database connections with `sqlite:///:memory:`"
            )
        elif "migration" in test_name:
            report.append("\n**Suggested Fix:**")
            report.append(
                "- Use PostgreSQL test container from `./tests/utils/test-env`"
            )
            report.append("- Create real database connections with test credentials")
        elif "registry" in test_name or "model" in test_name:
            report.append("\n**Suggested Fix:**")
            report.append("- Use real SQLite or PostgreSQL test database")
            report.append("- Perform actual model registration and queries")
        else:
            report.append("\n**Suggested Fix:**")
            report.append("- Identify the mocked service and use real implementation")
            report.append(
                "- If external service, use test instance or Docker container"
            )

    report.append("\n## Implementation Strategy:\n")
    report.append(
        "1. **SQLite Tests**: Use `:memory:` database for fast, isolated tests"
    )
    report.append("2. **PostgreSQL Tests**: Use test container from `test-env` script")
    report.append("3. **Connection Tests**: Create real database connections")
    report.append("4. **Migration Tests**: Execute real migrations on test databases")
    report.append("5. **External Services**: Use Docker containers or test instances")

    return "\n".join(report)


def create_real_infrastructure_helper():
    """Create helper module for real infrastructure testing."""
    helper_content = '''"""
Real Infrastructure Testing Utilities.

Provides real database connections and services for Tier 2-3 tests.
NO MOCKING allowed - all infrastructure must be real.
"""

import os
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Optional

from dataflow import DataFlow
from dataflow.adapters.sqlite import SQLiteAdapter
from dataflow.adapters.postgresql import PostgreSQLAdapter


class RealInfrastructure:
    """Provides real infrastructure for testing."""

    @staticmethod
    def get_sqlite_memory_db() -> DataFlow:
        """Get an in-memory SQLite database for testing."""
        return DataFlow(":memory:")

    @staticmethod
    def get_sqlite_file_db() -> DataFlow:
        """Get a temporary file-based SQLite database."""
        temp_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        return DataFlow(f"sqlite:///{temp_file.name}")

    @staticmethod
    def get_postgresql_test_db() -> Optional[DataFlow]:
        """Get PostgreSQL test database if available."""
        # Use test environment PostgreSQL
        host = os.getenv("TEST_DB_HOST", "localhost")
        port = os.getenv("TEST_DB_PORT", "5434")
        user = os.getenv("TEST_DB_USER", "test_user")
        password = os.getenv("TEST_DB_PASSWORD", "test_password")
        database = os.getenv("TEST_DB_NAME", "test_db")

        try:
            conn_str = f"postgresql://{user}:{password}@{host}:{port}/{database}"
            return DataFlow(conn_str)
        except Exception:
            return None

    @staticmethod
    @contextmanager
    def temporary_sqlite_db():
        """Context manager for temporary SQLite database."""
        temp_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        temp_path = Path(temp_file.name)

        try:
            db = DataFlow(f"sqlite:///{temp_path}")
            yield db
        finally:
            if temp_path.exists():
                temp_path.unlink()

    @staticmethod
    def get_test_adapter(db_type: str = "sqlite"):
        """Get a real database adapter for testing."""
        if db_type == "sqlite":
            return SQLiteAdapter(":memory:")
        elif db_type == "postgresql":
            # Use test PostgreSQL
            return PostgreSQLAdapter(
                "postgresql://test_user:test_password@localhost:5434/test_db"
            )
        else:
            raise ValueError(f"Unsupported database type: {db_type}")


# Global instance for easy access
real_infra = RealInfrastructure()
'''

    helper_path = TESTS_DIR / "utils" / "real_infrastructure.py"
    helper_path.parent.mkdir(parents=True, exist_ok=True)

    with open(helper_path, "w") as f:
        f.write(helper_content)

    print(f"✅ Created real infrastructure helper: {helper_path}")


def main():
    """Main execution."""
    print("🔍 Scanning for NO MOCKING policy violations...")

    violations = find_mock_violations()

    if not violations:
        print(
            "✅ No violations found! All Tier 2-3 tests comply with NO MOCKING policy."
        )
        return

    print(f"⚠️ Found {len(violations)} files violating NO MOCKING policy")

    # Generate and save report
    report = generate_fix_report(violations)
    report_path = BASE_DIR / "NO_MOCKING_VIOLATIONS_REPORT.md"

    with open(report_path, "w") as f:
        f.write(report)

    print(f"📄 Violation report saved to: {report_path}")

    # Create helper module
    create_real_infrastructure_helper()

    print("\n📋 Next Steps:")
    print("1. Review the violation report")
    print("2. Use real_infrastructure.py helper for test conversions")
    print("3. Replace all Mock() with real database connections")
    print("4. Ensure test-env PostgreSQL is running for integration tests")
    print("5. Re-run tests to verify fixes")


if __name__ == "__main__":
    main()
