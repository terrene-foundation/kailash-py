#!/usr/bin/env python3
"""
Organize test files from examples/ directory.
- Move actual pytest files to tests/
- Rename example files to remove 'test' from name
- Ensure all tests use Docker infrastructure
"""

import os
import shutil
from pathlib import Path

# Project root
PROJECT_ROOT = Path(__file__).parent.parent.parent

# Directories
EXAMPLES_DIR = PROJECT_ROOT / "examples"
TESTS_DIR = PROJECT_ROOT / "tests"

# Docker connection config that all tests should use
DOCKER_CONFIG = """
# Docker infrastructure configuration
import os

# PostgreSQL configuration - using Docker on port 5433
DATABASE_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", "5433")),
    "database": os.getenv("DB_NAME", "kailash_test"),
    "user": os.getenv("DB_USER", "admin"),
    "password": os.getenv("DB_PASSWORD", "admin"),
}

# Redis configuration
REDIS_CONFIG = {
    "host": os.getenv("REDIS_HOST", "localhost"),
    "port": int(os.getenv("REDIS_PORT", "6379")),
}

# MongoDB configuration
MONGODB_CONFIG = {
    "host": os.getenv("MONGO_HOST", "localhost"),
    "port": int(os.getenv("MONGO_PORT", "27017")),
    "username": os.getenv("MONGO_USER", "kailash"),
    "password": os.getenv("MONGO_PASSWORD", "kailash123"),
}

# Kafka configuration
KAFKA_CONFIG = {
    "bootstrap_servers": os.getenv("KAFKA_SERVERS", "localhost:9092"),
}

# Ollama configuration
OLLAMA_CONFIG = {
    "host": os.getenv("OLLAMA_HOST", "http://localhost:11434"),
}

# OAuth2 configuration
OAUTH2_CONFIG = {
    "host": os.getenv("OAUTH2_HOST", "http://localhost:8080"),
}
"""


def has_pytest_markers(content):
    """Check if file has pytest markers."""
    pytest_indicators = [
        "import pytest",
        "from pytest",
        "@pytest.",
        "def test_",
        "class Test",
        "pytest.fixture",
        "pytest.mark",
    ]
    return any(indicator in content for indicator in pytest_indicators)


def determine_test_location(file_path, content):
    """Determine where a test file should go."""
    # Check for e2e patterns
    if any(
        pattern in content
        for pattern in ["end-to-end", "e2e", "full workflow", "complete scenario"]
    ):
        return "e2e"

    # Check for integration patterns
    if any(
        pattern in content
        for pattern in [
            "integration",
            "multiple components",
            "with database",
            "with redis",
        ]
    ):
        return "integration"

    # Default to unit
    return "unit"


def get_new_example_name(file_name):
    """Convert test filename to example filename."""
    # Remove 'test_' prefix
    if file_name.startswith("test_"):
        file_name = file_name[5:]

    # Replace '_test.py' with '_example.py'
    if file_name.endswith("_test.py"):
        return file_name[:-8] + "_example.py"

    # Replace 'test.py' with 'example.py'
    if file_name.endswith("test.py"):
        return file_name[:-7] + "_example.py"

    return file_name


def process_test_files():
    """Process all test files in examples directory."""
    test_files = list(EXAMPLES_DIR.rglob("*test*.py"))

    moves = []
    renames = []

    for test_file in test_files:
        if "__pycache__" in str(test_file):
            continue

        try:
            content = test_file.read_text()

            if has_pytest_markers(content):
                # This is a real test - move to tests/
                test_type = determine_test_location(test_file, content)
                relative_path = test_file.relative_to(EXAMPLES_DIR)

                # Determine subdirectory based on original location
                if "feature_examples" in str(relative_path):
                    category = (
                        relative_path.parts[1]
                        if len(relative_path.parts) > 2
                        else "misc"
                    )
                else:
                    category = (
                        relative_path.parts[0]
                        if len(relative_path.parts) > 1
                        else "misc"
                    )

                new_path = TESTS_DIR / test_type / category / test_file.name
                moves.append((test_file, new_path))
            else:
                # This is an example - rename it
                new_name = get_new_example_name(test_file.name)
                if new_name != test_file.name:
                    new_path = test_file.parent / new_name
                    renames.append((test_file, new_path))

        except Exception as e:
            print(f"Error processing {test_file}: {e}")

    return moves, renames


def create_docker_config_file():
    """Create Docker configuration file for tests."""
    config_path = TESTS_DIR / "docker_config.py"
    config_path.write_text(DOCKER_CONFIG)
    print(f"Created Docker configuration at {config_path}")


def main(auto_run=True):
    """Main function."""
    print("Analyzing test files in examples directory...")

    moves, renames = process_test_files()

    print(f"\nFound {len(moves)} files to move to tests/")
    print(f"Found {len(renames)} files to rename")

    # Show what will be done
    if moves:
        print("\nFiles to move to tests/:")
        for src, dst in moves[:5]:  # Show first 5
            print(
                f"  {src.relative_to(PROJECT_ROOT)} -> {dst.relative_to(PROJECT_ROOT)}"
            )
        if len(moves) > 5:
            print(f"  ... and {len(moves) - 5} more")

    if renames:
        print("\nFiles to rename:")
        for src, dst in renames[:5]:  # Show first 5
            print(f"  {src.name} -> {dst.name}")
        if len(renames) > 5:
            print(f"  ... and {len(renames) - 5} more")

    # Auto-proceed for automated run
    print("\nProceeding with reorganization...")

    # Create Docker config
    create_docker_config_file()

    # Perform moves
    for src, dst in moves:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))
        print(f"Moved {src.name} to tests/")

    # Perform renames
    for src, dst in renames:
        src.rename(dst)
        print(f"Renamed {src.name} to {dst.name}")

    print("\nReorganization complete!")
    print(f"- Moved {len(moves)} test files to tests/")
    print(f"- Renamed {len(renames)} example files")
    print("- Created Docker configuration for tests")

    # Update conftest.py to use Docker
    update_conftest_for_docker()


def update_conftest_for_docker():
    """Update conftest.py to use Docker infrastructure."""
    conftest_path = TESTS_DIR / "conftest.py"

    # Add import at the top of conftest.py
    docker_import = """
# Import Docker configuration
from tests.docker_config import (
    DATABASE_CONFIG,
    REDIS_CONFIG,
    MONGODB_CONFIG,
    KAFKA_CONFIG,
    OLLAMA_CONFIG,
    OAUTH2_CONFIG,
)
"""

    if conftest_path.exists():
        content = conftest_path.read_text()
        if "docker_config" not in content:
            # Find the imports section and add our import
            lines = content.split("\n")
            import_index = 0
            for i, line in enumerate(lines):
                if line.startswith("import") or line.startswith("from"):
                    import_index = i

            # Insert after imports
            lines.insert(import_index + 1, docker_import)
            conftest_path.write_text("\n".join(lines))
            print("Updated conftest.py to use Docker configuration")


if __name__ == "__main__":
    main()
