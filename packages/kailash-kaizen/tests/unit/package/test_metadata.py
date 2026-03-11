"""
Tests for package metadata validation.

This module tests that the package metadata is complete and correct for PyPI
publication, including dependencies, classifiers, and optional extras.
"""

import re
import tomllib
from pathlib import Path

import pytest


class TestPackageMetadata:
    """Test suite for package metadata validation."""

    @pytest.fixture
    def package_root(self):
        """Get the package root directory."""
        return Path(__file__).parent.parent.parent.parent

    @pytest.fixture
    def pyproject_data(self, package_root):
        """Load pyproject.toml data."""
        pyproject_file = package_root / "pyproject.toml"
        with open(pyproject_file, "rb") as f:
            return tomllib.load(f)

    def test_package_metadata_complete(self, pyproject_data):
        """Test that package metadata is complete for PyPI."""
        project = pyproject_data["project"]

        # Required fields
        assert "name" in project, "Missing 'name' in project metadata"
        assert "version" in project, "Missing 'version' in project metadata"
        assert "description" in project, "Missing 'description' in project metadata"
        assert "authors" in project, "Missing 'authors' in project metadata"
        assert "license" in project, "Missing 'license' in project metadata"
        assert "readme" in project, "Missing 'readme' in project metadata"
        assert (
            "requires-python" in project
        ), "Missing 'requires-python' in project metadata"

    def test_package_has_urls(self, pyproject_data):
        """Test that package has project URLs."""
        project = pyproject_data["project"]
        assert "urls" in project, "Missing 'urls' in project metadata"

        urls = project["urls"]
        # Check for essential URLs
        assert (
            "Homepage" in urls or "Repository" in urls
        ), "Must have at least Homepage or Repository URL"

    def test_package_has_keywords(self, pyproject_data):
        """Test that package has keywords for discoverability."""
        project = pyproject_data["project"]
        assert "keywords" in project, "Missing 'keywords' in project metadata"
        assert len(project["keywords"]) > 0, "Keywords list is empty"

        # Check for relevant keywords
        keywords_str = " ".join(project["keywords"]).lower()
        assert any(
            kw in keywords_str for kw in ["ai", "agent", "workflow", "kailash"]
        ), "Keywords should include relevant terms like 'ai', 'agent', 'workflow', or 'kailash'"

    def test_dependencies_specified(self, pyproject_data):
        """Test that dependencies are correctly specified."""
        project = pyproject_data["project"]
        assert "dependencies" in project, "Missing 'dependencies' in project metadata"

        dependencies = project["dependencies"]

        # Must depend on Core SDK
        core_sdk_dep = next((d for d in dependencies if d.startswith("kailash")), None)
        assert core_sdk_dep is not None, "Must depend on 'kailash' (Core SDK)"
        assert (
            ">=0.9.19" in core_sdk_dep or ">=" in core_sdk_dep
        ), "Core SDK dependency must specify minimum version"

        # Check for essential dependencies
        dep_str = " ".join(dependencies).lower()
        assert "pydantic" in dep_str, "Must depend on 'pydantic'"
        assert (
            "typing-extensions" in dep_str or "typing_extensions" in dep_str
        ), "Must depend on 'typing-extensions'"

    def test_optional_dependencies_dev(self, pyproject_data):
        """Test that dev optional dependencies are defined."""
        project = pyproject_data["project"]
        assert (
            "optional-dependencies" in project
        ), "Missing 'optional-dependencies' in project metadata"

        optional_deps = project["optional-dependencies"]
        assert "dev" in optional_deps, "Missing 'dev' optional dependencies"

        dev_deps = optional_deps["dev"]
        dev_deps_str = " ".join(dev_deps).lower()

        # Check for essential dev tools
        assert "pytest" in dev_deps_str, "Dev dependencies must include 'pytest'"
        assert "black" in dev_deps_str, "Dev dependencies must include 'black'"
        assert "isort" in dev_deps_str, "Dev dependencies must include 'isort'"
        assert "ruff" in dev_deps_str, "Dev dependencies must include 'ruff'"

    def test_optional_dependencies_dataflow(self, pyproject_data):
        """Test that dataflow optional dependencies are defined."""
        project = pyproject_data["project"]
        optional_deps = project.get("optional-dependencies", {})

        if "dataflow" in optional_deps:
            dataflow_deps = optional_deps["dataflow"]
            dataflow_deps_str = " ".join(dataflow_deps).lower()
            assert (
                "kailash-dataflow" in dataflow_deps_str
            ), "DataFlow dependencies must include 'kailash-dataflow'"

    def test_optional_dependencies_nexus(self, pyproject_data):
        """Test that nexus optional dependencies are defined."""
        project = pyproject_data["project"]
        optional_deps = project.get("optional-dependencies", {})

        if "nexus" in optional_deps:
            nexus_deps = optional_deps["nexus"]
            nexus_deps_str = " ".join(nexus_deps).lower()
            assert (
                "kailash-nexus" in nexus_deps_str
            ), "Nexus dependencies must include 'kailash-nexus'"

    def test_optional_dependencies_all(self, pyproject_data):
        """Test that 'all' optional dependencies are defined."""
        project = pyproject_data["project"]
        optional_deps = project.get("optional-dependencies", {})

        if "all" in optional_deps:
            all_deps = optional_deps["all"]
            assert len(all_deps) > 0, "'all' optional dependencies should not be empty"

    def test_classifiers_appropriate(self, pyproject_data):
        """Test that PyPI classifiers are appropriate."""
        project = pyproject_data["project"]
        assert "classifiers" in project, "Missing 'classifiers' in project metadata"

        classifiers = project["classifiers"]
        "\n".join(classifiers)

        # Check for essential classifiers
        assert any(
            "Development Status" in c for c in classifiers
        ), "Must have 'Development Status' classifier"

        assert any(
            "License ::" in c for c in classifiers
        ), "Must have 'License' classifier"

        assert any(
            "Programming Language :: Python" in c for c in classifiers
        ), "Must have 'Programming Language :: Python' classifier"

        # Should specify Python 3.11 support
        assert any(
            "3.11" in c for c in classifiers
        ), "Should specify Python 3.11 support in classifiers"

    def test_license_classifier_matches_license(self, pyproject_data):
        """Test that license classifier matches license field."""
        project = pyproject_data["project"]

        license_field = project.get("license", {})
        if isinstance(license_field, dict):
            license_text = license_field.get("text", "")
        else:
            license_text = str(license_field)

        classifiers = project.get("classifiers", [])
        classifier_str = "\n".join(classifiers)

        # If license mentions Apache, classifier should too
        if "Apache" in license_text:
            assert (
                "Apache" in classifier_str
            ), "License classifier should match license field (Apache)"

    def test_description_not_empty(self, pyproject_data):
        """Test that description is not empty."""
        project = pyproject_data["project"]
        description = project.get("description", "")
        assert len(description) > 0, "Description should not be empty"
        assert (
            len(description) < 200
        ), "Description should be concise (< 200 chars), use README for details"

    def test_authors_not_empty(self, pyproject_data):
        """Test that authors list is not empty."""
        project = pyproject_data["project"]
        authors = project.get("authors", [])
        assert len(authors) > 0, "Authors list should not be empty"

        # Check that authors have required fields
        for author in authors:
            assert (
                "name" in author or "email" in author
            ), "Each author must have 'name' or 'email'"

    def test_readme_specified(self, pyproject_data, package_root):
        """Test that readme is specified and file exists."""
        project = pyproject_data["project"]
        readme = project.get("readme", "")
        assert readme, "README file must be specified"

        readme_file = package_root / readme
        assert readme_file.exists(), f"README file '{readme}' does not exist"

    def test_no_duplicate_dependencies(self, pyproject_data):
        """Test that there are no duplicate dependencies."""
        project = pyproject_data["project"]
        dependencies = project.get("dependencies", [])

        # Extract package names (before version specifiers)
        package_names = []
        for dep in dependencies:
            # Split on comparison operators
            name = re.split(r"[<>=!]", dep)[0].strip()
            package_names.append(name.lower())

        # Check for duplicates
        duplicates = [name for name in package_names if package_names.count(name) > 1]
        assert not duplicates, f"Duplicate dependencies found: {set(duplicates)}"

    def test_build_system_specified(self, pyproject_data):
        """Test that build system is specified."""
        assert "build-system" in pyproject_data, "Missing 'build-system' section"

        build_system = pyproject_data["build-system"]
        assert "requires" in build_system, "Missing 'requires' in build-system"
        assert (
            "build-backend" in build_system
        ), "Missing 'build-backend' in build-system"

        # Should use setuptools or similar
        backend = build_system["build-backend"]
        assert (
            "setuptools" in backend or "flit" in backend or "poetry" in backend
        ), f"Build backend '{backend}' should be setuptools, flit, or poetry"


class TestMetadataConsistency:
    """Test suite for metadata consistency between pyproject.toml and setup.py."""

    @pytest.fixture
    def package_root(self):
        """Get the package root directory."""
        return Path(__file__).parent.parent.parent.parent

    @pytest.fixture
    def pyproject_data(self, package_root):
        """Load pyproject.toml data."""
        pyproject_file = package_root / "pyproject.toml"
        with open(pyproject_file, "rb") as f:
            return tomllib.load(f)

    @pytest.fixture
    def setup_content(self, package_root):
        """Load setup.py content."""
        setup_file = package_root / "setup.py"
        return setup_file.read_text()

    def test_version_matches_setup_py(self, pyproject_data, setup_content):
        """Test that version in pyproject.toml matches setup.py."""
        pyproject_version = pyproject_data["project"]["version"]

        version_match = re.search(r'version\s*=\s*["\']([^"\']+)["\']', setup_content)
        assert version_match, "No version found in setup.py"
        setup_version = version_match.group(1)

        assert (
            pyproject_version == setup_version
        ), f"Version mismatch: pyproject.toml={pyproject_version}, setup.py={setup_version}"

    def test_name_matches_setup_py(self, pyproject_data, setup_content):
        """Test that name in pyproject.toml matches setup.py."""
        pyproject_name = pyproject_data["project"]["name"]

        name_match = re.search(r'name\s*=\s*["\']([^"\']+)["\']', setup_content)
        assert name_match, "No name found in setup.py"
        setup_name = name_match.group(1)

        assert (
            pyproject_name == setup_name
        ), f"Name mismatch: pyproject.toml={pyproject_name}, setup.py={setup_name}"

    def test_description_matches_setup_py(self, pyproject_data, setup_content):
        """Test that description in pyproject.toml matches setup.py."""
        pyproject_description = pyproject_data["project"]["description"]

        description_match = re.search(
            r'description\s*=\s*["\']([^"\']+)["\']', setup_content
        )
        if description_match:
            setup_description = description_match.group(1)
            assert (
                pyproject_description == setup_description
            ), f"Description mismatch: pyproject.toml={pyproject_description}, setup.py={setup_description}"
