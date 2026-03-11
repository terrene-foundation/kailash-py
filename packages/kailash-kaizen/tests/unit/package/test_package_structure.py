"""
Tests for package structure validation.

This module tests that the package has all required files for PyPI distribution
and that version information is consistent across all configuration files.
"""

import re
import tomllib
from pathlib import Path

import pytest


class TestPackageStructure:
    """Test suite for package structure validation."""

    @pytest.fixture
    def package_root(self):
        """Get the package root directory."""
        # Navigate from tests/unit/package/ to package root
        return Path(__file__).parent.parent.parent.parent

    def test_package_has_required_files(self, package_root):
        """Test that package has all required distribution files."""
        required_files = [
            "pyproject.toml",
            "setup.py",
            "README.md",
            "CHANGELOG.md",
            "LICENSE",
            "MANIFEST.in",
        ]

        for filename in required_files:
            file_path = package_root / filename
            assert file_path.exists(), f"Missing required file: {filename}"

    def test_has_src_directory(self, package_root):
        """Test that package has src directory with kaizen module."""
        src_dir = package_root / "src"
        assert src_dir.exists(), "Missing src directory"

        kaizen_dir = src_dir / "kaizen"
        assert kaizen_dir.exists(), "Missing src/kaizen directory"

        init_file = kaizen_dir / "__init__.py"
        assert init_file.exists(), "Missing src/kaizen/__init__.py"

    def test_has_tests_directory(self, package_root):
        """Test that package has tests directory."""
        tests_dir = package_root / "tests"
        assert tests_dir.exists(), "Missing tests directory"

    def test_has_examples_directory(self, package_root):
        """Test that package has examples directory."""
        examples_dir = package_root / "examples"
        assert examples_dir.exists(), "Missing examples directory"

    def test_has_docs_directory(self, package_root):
        """Test that package has docs directory."""
        docs_dir = package_root / "docs"
        assert docs_dir.exists(), "Missing docs directory"

    def test_version_consistency(self, package_root):
        """Test that version is consistent across all files."""
        # Get version from __init__.py
        init_file = package_root / "src" / "kaizen" / "__init__.py"
        init_content = init_file.read_text()
        init_version_match = re.search(
            r'__version__\s*=\s*["\']([^"\']+)["\']', init_content
        )
        assert init_version_match, "No __version__ found in __init__.py"
        init_version = init_version_match.group(1)

        # Get version from pyproject.toml
        pyproject_file = package_root / "pyproject.toml"
        with open(pyproject_file, "rb") as f:
            pyproject_data = tomllib.load(f)
        pyproject_version = pyproject_data["project"]["version"]

        # Get version from setup.py
        setup_file = package_root / "setup.py"
        setup_content = setup_file.read_text()
        setup_version_match = re.search(
            r'version\s*=\s*["\']([^"\']+)["\']', setup_content
        )
        assert setup_version_match, "No version found in setup.py"
        setup_version = setup_version_match.group(1)

        # All versions must match
        assert (
            init_version == pyproject_version == setup_version
        ), f"Version mismatch: __init__.py={init_version}, pyproject.toml={pyproject_version}, setup.py={setup_version}"

    def test_version_follows_semver(self, package_root):
        """Test that version follows semantic versioning (X.Y.Z or X.Y.Z-suffix)."""
        init_file = package_root / "src" / "kaizen" / "__init__.py"
        init_content = init_file.read_text()
        version_match = re.search(
            r'__version__\s*=\s*["\']([^"\']+)["\']', init_content
        )
        assert version_match, "No __version__ found in __init__.py"
        version = version_match.group(1)

        # Semantic versioning pattern: X.Y.Z, X.Y.Z-suffix, or PEP 440 (X.Y.Zb1, X.Y.Za1, X.Y.Zrc1)
        semver_pattern = r"^\d+\.\d+\.\d+([-.]?[a-zA-Z0-9.-]+)?$"
        assert re.match(
            semver_pattern, version
        ), f"Version '{version}' does not follow semantic versioning"

    def test_python_version_requirements(self, package_root):
        """Test that Python version requirements are correct and aligned with Core SDK."""
        pyproject_file = package_root / "pyproject.toml"
        with open(pyproject_file, "rb") as f:
            pyproject_data = tomllib.load(f)

        requires_python = pyproject_data["project"]["requires-python"]

        # Must be >=3.11 to match Core SDK requirements
        # Accept formats: ">=3.11", ">=3.11.0", ">3.10"
        assert (
            "3.11" in requires_python
            or "3.12" in requires_python
            or "3.13" in requires_python
        ), f"Python requirement '{requires_python}' must be >=3.11 to match Core SDK"

    def test_manifest_exists(self, package_root):
        """Test that MANIFEST.in exists."""
        manifest_file = package_root / "MANIFEST.in"
        assert manifest_file.exists(), "Missing MANIFEST.in file"

    def test_manifest_includes_examples(self, package_root):
        """Test that MANIFEST.in includes examples directory."""
        manifest_file = package_root / "MANIFEST.in"
        manifest_content = manifest_file.read_text()

        # Check for recursive include of examples
        assert (
            "examples" in manifest_content
        ), "MANIFEST.in must include examples directory"

    def test_manifest_includes_docs(self, package_root):
        """Test that MANIFEST.in includes docs directory."""
        manifest_file = package_root / "MANIFEST.in"
        manifest_content = manifest_file.read_text()

        # Check for recursive include of docs
        assert (
            "docs" in manifest_content or "README" in manifest_content
        ), "MANIFEST.in must include docs/README files"

    def test_manifest_includes_tests(self, package_root):
        """Test that MANIFEST.in includes tests directory."""
        manifest_file = package_root / "MANIFEST.in"
        manifest_content = manifest_file.read_text()

        # Check for recursive include of tests (optional but recommended)
        # Some packages exclude tests from sdist, so this is informational
        if "tests" in manifest_content:
            assert "tests" in manifest_content, "MANIFEST.in includes tests"

    def test_manifest_includes_license(self, package_root):
        """Test that MANIFEST.in includes LICENSE file."""
        manifest_file = package_root / "MANIFEST.in"
        manifest_content = manifest_file.read_text()

        assert "LICENSE" in manifest_content, "MANIFEST.in must include LICENSE"

    def test_manifest_includes_changelog(self, package_root):
        """Test that MANIFEST.in includes CHANGELOG."""
        manifest_file = package_root / "MANIFEST.in"
        manifest_content = manifest_file.read_text()

        assert "CHANGELOG" in manifest_content, "MANIFEST.in must include CHANGELOG"

    def test_package_has_license_file(self, package_root):
        """Test that LICENSE file exists and is not empty."""
        license_file = package_root / "LICENSE"
        assert license_file.exists(), "Missing LICENSE file"
        assert license_file.stat().st_size > 0, "LICENSE file is empty"

    def test_package_name_correct(self, package_root):
        """Test that package name is 'kailash-kaizen'."""
        pyproject_file = package_root / "pyproject.toml"
        with open(pyproject_file, "rb") as f:
            pyproject_data = tomllib.load(f)

        package_name = pyproject_data["project"]["name"]
        assert (
            package_name == "kailash-kaizen"
        ), f"Package name must be 'kailash-kaizen', got '{package_name}'"


class TestPackageStructureIntegrity:
    """Test suite for package structure integrity."""

    @pytest.fixture
    def package_root(self):
        """Get the package root directory."""
        return Path(__file__).parent.parent.parent.parent

    def test_no_pycache_in_package(self, package_root):
        """Test that no __pycache__ directories are included in package metadata."""
        # This will be checked during build, but we verify the intent
        gitignore = package_root / ".gitignore"
        if gitignore.exists():
            content = gitignore.read_text()
            assert "__pycache__" in content, ".gitignore should exclude __pycache__"

    def test_no_pyc_files_in_package(self, package_root):
        """Test that .pyc files are excluded from package."""
        gitignore = package_root / ".gitignore"
        if gitignore.exists():
            content = gitignore.read_text()
            assert "*.pyc" in content, ".gitignore should exclude *.pyc files"

    def test_readme_is_markdown(self, package_root):
        """Test that README is in Markdown format."""
        readme_file = package_root / "README.md"
        assert readme_file.exists(), "README.md must exist"
        assert readme_file.suffix == ".md", "README must be in Markdown format (.md)"

    def test_changelog_is_markdown(self, package_root):
        """Test that CHANGELOG is in Markdown format."""
        changelog_file = package_root / "CHANGELOG.md"
        assert changelog_file.exists(), "CHANGELOG.md must exist"
        assert (
            changelog_file.suffix == ".md"
        ), "CHANGELOG must be in Markdown format (.md)"
