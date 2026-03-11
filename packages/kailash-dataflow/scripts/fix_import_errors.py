#!/usr/bin/env python3
"""
Fix import placement errors in test files.

The real_infrastructure import was inserted in the wrong place in many files.
"""

import re
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent


def fix_import_placement(file_path: Path) -> bool:
    """Fix misplaced real_infrastructure import."""
    try:
        with open(file_path, "r") as f:
            content = f.read()

        original = content

        # Pattern 1: Import inserted in the middle of parentheses
        pattern1 = r"from dataflow\.nodes import \(\nfrom tests\.utils\.real_infrastructure import real_infra\n"
        if pattern1 in content:
            # Remove the misplaced import
            content = content.replace(
                "from dataflow.nodes import (\nfrom tests.utils.real_infrastructure import real_infra\n",
                "from dataflow.nodes import (\n",
            )
            # Add it after the closing parenthesis
            content = re.sub(
                r"(from dataflow\.nodes import \([^)]+\))",
                r"\1\nfrom tests.utils.real_infrastructure import real_infra",
                content,
            )

        # Pattern 2: Import in wrong location (general fix)
        if "from tests.utils.real_infrastructure import real_infra" in content:
            # Remove all instances
            content = content.replace(
                "from tests.utils.real_infrastructure import real_infra\n", ""
            )
            content = content.replace(
                "from tests.utils.real_infrastructure import real_infra", ""
            )

            # Add it in the right place (after other imports, before classes)
            # Find the last import statement
            import_lines = []
            lines = content.split("\n")
            last_import_idx = 0

            for i, line in enumerate(lines):
                if line.startswith("import ") or line.startswith("from "):
                    last_import_idx = i
                elif (
                    line.startswith("class ")
                    or line.startswith("def ")
                    or line.startswith("@")
                ):
                    break

            # Insert the import after the last import
            lines.insert(
                last_import_idx + 1,
                "from tests.utils.real_infrastructure import real_infra",
            )
            content = "\n".join(lines)

        if content != original:
            with open(file_path, "w") as f:
                f.write(content)
            return True

        return False
    except Exception as e:
        print(f"Error fixing {file_path}: {e}")
        return False


def main():
    """Main execution."""
    print("🔧 Fixing import placement errors...")

    # Files to fix
    files_to_fix = [
        "tests/integration/dataflow/test_multi_database_integration.py",
        "tests/integration/dataflow/test_multi_tenancy_integration.py",
        "tests/integration/migration/test_column_type_conversion.py",
        "tests/integration/migration/test_critical_migration_scenarios.py",
        "tests/integration/dataflow/test_asyncsql_integration.py",
        "tests/integration/dataflow/test_cache_integration.py",
        "tests/integration/dataflow/test_connection_pool_integration.py",
        "tests/integration/dataflow/test_engine_relationship_integration.py",
        "tests/integration/dataflow/test_enterprise_features_integration.py",
        "tests/integration/dataflow/test_generated_node_integration.py",
        "tests/integration/dataflow/test_multi_database_support.py",
        "tests/integration/dataflow/test_performance_validation.py",
        "tests/integration/dataflow/test_real_schema_discovery.py",
        "tests/integration/dataflow/test_smart_nodes_workflow_integration.py",
        "tests/integration/dataflow/test_sql_query_optimizer_integration.py",
        "tests/integration/dataflow/test_workflow_analyzer_integration.py",
        "tests/integration/dataflow/test_workflow_connection_integration.py",
    ]

    fixed_count = 0
    for file_name in files_to_fix:
        file_path = BASE_DIR / file_name
        if file_path.exists():
            if fix_import_placement(file_path):
                print(f"✅ Fixed {file_name}")
                fixed_count += 1

    print(f"\n📊 Fixed {fixed_count} files")

    # Test that imports work now
    print("\n🧪 Testing fixed imports...")
    import subprocess

    result = subprocess.run(
        ["python", "-m", "pytest", "tests/integration", "--co", "-q"],
        capture_output=True,
        text=True,
        cwd=BASE_DIR,
    )

    if "error" not in result.stdout.lower() and result.returncode == 0:
        print("✅ All imports working correctly!")
    else:
        errors = result.stdout.count("ERROR")
        print(f"⚠️ Still {errors} import errors remaining")


if __name__ == "__main__":
    main()
