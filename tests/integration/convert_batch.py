#!/usr/bin/env python3
"""Batch convert mock-based integration tests to Docker-based tests."""

import os
import re
import shutil
from pathlib import Path
from typing import List, Tuple


class BatchConverter:
    """Convert multiple mock-based tests to Docker-based tests."""

    def __init__(self):
        self.integration_dir = Path("tests/integration")
        self.converted_dir = self.integration_dir / "converted"
        self.converted_dir.mkdir(exist_ok=True)

        # Map of common mock patterns to Docker replacements
        self.replacements = {
            # Import replacements
            r"from unittest\.mock import.*": "import pytest\nimport asyncio",
            r"import mock": "# Removed mock import",
            # Fixture replacements
            r'@patch\([\'"].*[\'"].*\)': "@pytest.fixture",
            r"Mock\(\)": "Real service from fixture",
            r"MagicMock\(\)": "Real service instance",
            r"AsyncMock\(\)": "Real async service",
            # Common mock patterns
            r"mock_\w+\.return_value\s*=": "# Use real service:",
            r"\.assert_called.*\(\)": "# Verify with real service",
            r"\.call_count": "# Check real service state",
        }

        # Service-specific templates
        self.service_templates = {
            "postgres": '''
    @pytest.fixture
    async def test_table(self, test_database):
        """Create test table in real PostgreSQL."""
        await test_database.execute("""
            CREATE TABLE test_data (
                id SERIAL PRIMARY KEY,
                name VARCHAR(255),
                value JSONB
            )
        """)
        yield test_database
''',
            "redis": '''
    @pytest.fixture
    def test_cache(self, redis_client):
        """Setup test data in real Redis."""
        self.create_redis_test_data(redis_client, "test")
        yield redis_client
''',
            "http": '''
    @pytest.fixture
    async def test_server(self, http_client):
        """Use real HTTP client for API testing."""
        yield http_client
''',
        }

    def detect_service_type(self, content: str) -> List[str]:
        """Detect which services are mocked in the test."""
        services = []

        if re.search(r"(postgres|postgresql|asyncpg|sql)", content, re.I):
            services.append("postgres")
        if re.search(r"redis", content, re.I):
            services.append("redis")
        if re.search(r"(http|api|rest|client)", content, re.I):
            services.append("http")
        if re.search(r"ollama", content, re.I):
            services.append("ollama")
        if re.search(r"mcp", content, re.I):
            services.append("mcp")

        return services

    def convert_file(self, file_path: Path) -> Tuple[bool, str]:
        """Convert a single file from mocks to Docker."""
        try:
            with open(file_path, "r") as f:
                content = f.read()

            # Skip if already converted
            if "DockerIntegrationTestBase" in content:
                return False, "Already converted"

            # Detect services
            services = self.detect_service_type(content)
            if not services:
                return False, "No services detected"

            # Apply replacements
            converted = content
            for pattern, replacement in self.replacements.items():
                converted = re.sub(pattern, replacement, converted)

            # Add Docker base class import
            if "import pytest" not in converted:
                converted = "import pytest\n" + converted

            converted = re.sub(
                r"(import pytest.*\n)",
                r"\1from tests.integration.docker_test_base import DockerIntegrationTestBase\n",
                converted,
            )

            # Update class definitions
            converted = re.sub(
                r"class (Test\w+)(?:\([^)]*\))?:",
                r"@pytest.mark.integration\n@pytest.mark.requires_docker\nclass \1(DockerIntegrationTestBase):",
                converted,
            )

            # Add service fixtures
            fixtures_added = False
            for service in services:
                if service in self.service_templates:
                    # Find first test method and insert fixture before it
                    pattern = r"(\n    def test_\w+)"
                    if not fixtures_added and re.search(pattern, converted):
                        converted = re.sub(
                            pattern,
                            self.service_templates[service] + r"\1",
                            converted,
                            count=1,
                        )
                        fixtures_added = True

            # Save converted file
            new_name = file_path.stem.replace("_functional", "_docker")
            if not new_name.endswith("_docker"):
                new_name += "_docker"
            new_path = self.converted_dir / f"{new_name}.py"

            with open(new_path, "w") as f:
                f.write(converted)

            return True, f"Converted to {new_path}"

        except Exception as e:
            return False, f"Error: {str(e)}"

    def convert_batch(self, file_pattern: str = "*_functional*.py", limit: int = 10):
        """Convert a batch of files matching pattern."""
        files = list(self.integration_dir.rglob(file_pattern))
        converted_count = 0

        print(f"Found {len(files)} files matching pattern '{file_pattern}'")

        for file_path in files[:limit]:
            if file_path.parent == self.converted_dir:
                continue

            print(f"\nProcessing: {file_path.relative_to(self.integration_dir)}")
            success, message = self.convert_file(file_path)

            if success:
                converted_count += 1
                print(f"  ✓ {message}")
            else:
                print(f"  ✗ {message}")

        print(f"\nConverted {converted_count}/{min(len(files), limit)} files")
        return converted_count


def main():
    """Run batch conversion."""
    converter = BatchConverter()

    # Convert high-priority functional tests
    print("=== Converting functional tests ===")
    converter.convert_batch("*_functional*.py", limit=5)

    # Convert other integration tests
    print("\n=== Converting other integration tests ===")
    converter.convert_batch("test_*.py", limit=5)

    print(f"\nConverted files saved to: {converter.converted_dir}")


if __name__ == "__main__":
    main()
