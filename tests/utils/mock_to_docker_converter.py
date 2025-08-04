"""Utility to help convert mock-based integration tests to Docker-based tests."""

import os
import re
from pathlib import Path
from typing import List, Tuple


class MockToDockerConverter:
    """Analyzes integration tests and helps convert from mocks to Docker services."""

    def __init__(self, integration_test_dir: str = "tests/integration"):
        self.test_dir = Path(integration_test_dir)
        self.mock_patterns = [
            r"from unittest\.mock import",
            r"from mock import",
            r"import mock",
            r"@patch\(",
            r"@mock\.",
            r"Mock\(",
            r"MagicMock\(",
            r"AsyncMock\(",
            r"patch\.",
        ]

        self.docker_replacements = {
            "Mock()": "Real service connection",
            "MagicMock()": "Real service instance",
            "AsyncMock()": "Real async service connection",
            "@patch": "@pytest.fixture with real service",
            "mock_": "real_",
        }

    def find_mock_based_tests(self) -> List[Tuple[Path, List[str]]]:
        """Find all integration tests using mocks."""
        mock_tests = []

        for py_file in self.test_dir.rglob("*.py"):
            if "__pycache__" in str(py_file):
                continue

            mock_lines = []
            try:
                with open(py_file, "r") as f:
                    for i, line in enumerate(f, 1):
                        for pattern in self.mock_patterns:
                            if re.search(pattern, line):
                                mock_lines.append((i, line.strip()))
                                break

                if mock_lines:
                    mock_tests.append((py_file, mock_lines))
            except Exception as e:
                print(f"Error reading {py_file}: {e}")

        return mock_tests

    def analyze_mock_usage(self, file_path: Path) -> dict:
        """Analyze how mocks are used in a test file."""
        analysis = {
            "file": str(file_path),
            "mocked_services": [],
            "mock_fixtures": [],
            "patched_methods": [],
            "conversion_suggestions": [],
        }

        with open(file_path, "r") as f:
            content = f.read()

        # Find mocked services
        service_patterns = [
            (r"Mock.*Database", "PostgreSQL"),
            (r"Mock.*Redis", "Redis"),
            (r"Mock.*MySQL", "MySQL"),
            (r"Mock.*Mongo", "MongoDB"),
            (r"Mock.*HTTP", "HTTP Client"),
            (r"Mock.*API", "API Service"),
            (r"Mock.*Ollama", "Ollama"),
        ]

        for pattern, service in service_patterns:
            if re.search(pattern, content, re.IGNORECASE):
                analysis["mocked_services"].append(service)

        # Find mock fixtures
        fixture_pattern = (
            r"@pytest\.fixture.*\n.*def\s+(\w+).*\n.*(?:Mock|MagicMock|AsyncMock)"
        )
        fixtures = re.findall(fixture_pattern, content, re.MULTILINE | re.DOTALL)
        analysis["mock_fixtures"] = list(set(fixtures))

        # Find patched methods
        patch_pattern = r'@patch\([\'"]([^\'")]+)[\'"]\)'
        patches = re.findall(patch_pattern, content)
        analysis["patched_methods"] = patches

        # Generate conversion suggestions
        if "PostgreSQL" in analysis["mocked_services"]:
            analysis["conversion_suggestions"].append(
                "Use 'postgres_conn' fixture from DockerIntegrationTestBase"
            )

        if "Redis" in analysis["mocked_services"]:
            analysis["conversion_suggestions"].append(
                "Use 'redis_client' fixture from DockerIntegrationTestBase"
            )

        if (
            "HTTP Client" in analysis["mocked_services"]
            or "API Service" in analysis["mocked_services"]
        ):
            analysis["conversion_suggestions"].append(
                "Use 'http_client' fixture for real HTTP requests"
            )

        return analysis

    def generate_conversion_template(self, original_file: Path) -> str:
        """Generate a template for converting a mock-based test to Docker-based."""
        analysis = self.analyze_mock_usage(original_file)

        template = f'''"""Docker-based integration test converted from {original_file.name}"""

import pytest
from tests.integration.docker_test_base import DockerIntegrationTestBase

# Original mocked services: {', '.join(analysis['mocked_services'])}
# Original mock fixtures: {', '.join(analysis['mock_fixtures'])}


@pytest.mark.integration
@pytest.mark.requires_docker
class Test{original_file.stem.replace("test_", "").title()}Docker(DockerIntegrationTestBase):
    """Docker-based version of {original_file.stem}."""

'''

        if "PostgreSQL" in analysis["mocked_services"]:
            template += '''    @pytest.fixture
    async def test_data(self, test_database):
        """Setup test data in real PostgreSQL."""
        # Create tables and insert test data
        await self.create_test_table(test_database, "test_table")
        await self.insert_test_data(test_database, "test_table", [
            {"name": "test1", "value": {"key": "value1"}},
            {"name": "test2", "value": {"key": "value2"}},
        ])
        yield test_database

'''

        if "Redis" in analysis["mocked_services"]:
            template += '''    @pytest.fixture
    def test_cache(self, redis_client):
        """Setup test data in real Redis."""
        self.create_redis_test_data(redis_client, "test")
        yield redis_client

'''

        template += """    # TODO: Convert test methods from mocked to Docker-based
    # - Replace Mock() with real service connections
    # - Use fixtures from DockerIntegrationTestBase
    # - Remove @patch decorators
    # - Test against real service behavior
"""

        return template

    def generate_report(self) -> str:
        """Generate a report of all mock-based integration tests."""
        mock_tests = self.find_mock_based_tests()

        report = "# Mock-based Integration Tests Report\n\n"
        report += f"Total files with mocks: {len(mock_tests)}\n\n"

        # Group by directory
        by_dir = {}
        for file_path, mock_lines in mock_tests:
            dir_name = file_path.parent.relative_to(self.test_dir)
            if dir_name not in by_dir:
                by_dir[dir_name] = []
            by_dir[dir_name].append((file_path, mock_lines))

        # Generate report by directory
        for dir_name, files in sorted(by_dir.items()):
            report += f"\n## {dir_name}\n"
            for file_path, mock_lines in files:
                report += f"\n### {file_path.name}\n"
                report += f"Mock usage on lines: {', '.join(str(line_no) for line_no, _ in mock_lines[:5])}"
                if len(mock_lines) > 5:
                    report += f" (and {len(mock_lines) - 5} more)"
                report += "\n"

                # Add analysis
                analysis = self.analyze_mock_usage(file_path)
                if analysis["mocked_services"]:
                    report += (
                        f"- Mocked services: {', '.join(analysis['mocked_services'])}\n"
                    )
                if analysis["conversion_suggestions"]:
                    report += "- Conversion suggestions:\n"
                    for suggestion in analysis["conversion_suggestions"]:
                        report += f"  - {suggestion}\n"

        return report


def main():
    """Run the converter analysis."""
    converter = MockToDockerConverter()

    # Generate report
    report = converter.generate_report()
    with open("tests/integration/MOCK_CONVERSION_REPORT.md", "w") as f:
        f.write(report)
    print("Generated MOCK_CONVERSION_REPORT.md")

    # Find priority files (those with most mocks)
    mock_tests = converter.find_mock_based_tests()
    priority_files = sorted(mock_tests, key=lambda x: len(x[1]), reverse=True)[:10]

    print("\nTop 10 files with most mock usage:")
    for file_path, mock_lines in priority_files:
        print(
            f"- {file_path.relative_to('tests/integration')}: {len(mock_lines)} mock usages"
        )

    # Generate conversion template for the top file
    if priority_files:
        top_file = priority_files[0][0]
        template = converter.generate_conversion_template(top_file)

        new_name = top_file.stem.replace("test_", "test_") + "_docker.py"
        new_path = top_file.parent / new_name

        print(f"\nGenerated conversion template: {new_path}")
        print("\nTemplate preview:")
        print(template[:500] + "...")


if __name__ == "__main__":
    main()
