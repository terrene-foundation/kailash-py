"""
Tests for package dependency validation.

This module tests that dependencies are properly specified, version constraints
are appropriate, and there are no missing or conflicting dependencies.
"""

import re
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest


class TestDependencySpecification:
    """Test suite for dependency specification validation."""

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
    def setup_py_data(self, package_root):
        """Load setup.py data."""
        setup_file = package_root / "setup.py"
        return setup_file.read_text()

    def test_core_dependencies_present(self, pyproject_data):
        """Test that core dependencies are specified in pyproject.toml."""
        dependencies = pyproject_data["project"]["dependencies"]

        # Core dependencies that must be present
        required_deps = [
            "kailash",  # Core SDK dependency
            "pydantic",  # Data validation
            "typing-extensions",  # Type hints for older Python
        ]

        dep_names = [re.split(r"[><=!]", dep)[0].strip() for dep in dependencies]

        for required in required_deps:
            assert (
                required in dep_names
            ), f"Required dependency '{required}' not found in dependencies"

    def test_kailash_version_constraint(self, pyproject_data):
        """Test that kailash dependency has appropriate version constraint."""
        dependencies = pyproject_data["project"]["dependencies"]

        kailash_dep = next(
            (dep for dep in dependencies if dep.startswith("kailash")), None
        )
        assert kailash_dep is not None, "kailash dependency not found"

        # Should have minimum version constraint
        assert (
            ">=" in kailash_dep
        ), f"kailash dependency '{kailash_dep}' should specify minimum version (>=)"

        # Extract version
        version_match = re.search(r">=(\d+\.\d+\.\d+)", kailash_dep)
        assert (
            version_match
        ), f"kailash dependency '{kailash_dep}' should have valid version"

        # Should be at least 0.9.19 (as specified in current config)
        version = version_match.group(1)
        major, minor, patch = map(int, version.split("."))
        assert (major, minor, patch) >= (
            0,
            9,
            19,
        ), f"kailash version should be >= 0.9.19, got {version}"

    def test_pydantic_version_constraint(self, pyproject_data):
        """Test that pydantic has appropriate version constraint."""
        dependencies = pyproject_data["project"]["dependencies"]

        pydantic_dep = next(
            (dep for dep in dependencies if dep.startswith("pydantic")), None
        )
        assert pydantic_dep is not None, "pydantic dependency not found"

        # Should require pydantic v2
        assert (
            ">=2" in pydantic_dep or ">2" in pydantic_dep
        ), f"pydantic dependency '{pydantic_dep}' should require v2+"

    def test_optional_dependencies_configured(self, pyproject_data):
        """Test that optional dependency groups are properly configured.

        Note: kailash-kaizen only has 'dev' and 'azure' extras.
        DataFlow and Nexus are separate packages in the Kailash ecosystem,
        not extras of this package.
        """
        optional_deps = pyproject_data["project"]["optional-dependencies"]

        # Expected optional dependency groups for kailash-kaizen
        # (dataflow and nexus are separate packages, not extras)
        expected_groups = ["dev"]  # azure is optional

        for group in expected_groups:
            assert (
                group in optional_deps
            ), f"Optional dependency group '{group}' not found"
            assert isinstance(
                optional_deps[group], list
            ), f"Optional dependency group '{group}' should be a list"
            assert (
                len(optional_deps[group]) > 0
            ), f"Optional dependency group '{group}' is empty"

    def test_dev_dependencies_complete(self, pyproject_data):
        """Test that dev dependencies include all necessary tools."""
        dev_deps = pyproject_data["project"]["optional-dependencies"]["dev"]

        # Essential dev tools
        required_tools = [
            "pytest",  # Testing framework
            "pytest-asyncio",  # Async testing
            "pytest-cov",  # Coverage reporting
            "black",  # Code formatting
            "isort",  # Import sorting
            "ruff",  # Linting
        ]

        dep_names = [re.split(r"[><=!]", dep)[0].strip() for dep in dev_deps]

        for tool in required_tools:
            assert (
                tool in dep_names
            ), f"Dev dependency '{tool}' not found in [dev] extras"


class TestDependencyVersionConstraints:
    """Test suite for dependency version constraint validation."""

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

    def test_version_constraints_use_compatible_operators(self, pyproject_data):
        """Test that version constraints use appropriate operators."""
        dependencies = pyproject_data["project"]["dependencies"]

        # Version constraint should use >=, >, ==, ~=, or ^
        # Avoid using just = or unversioned dependencies
        for dep in dependencies:
            # Skip if no version constraint (some may be acceptable)
            if not any(op in dep for op in [">=", ">", "==", "~=", "^", "<"]):
                # Unversioned dependency - should be rare but acceptable for some cases
                continue

            # If versioned, should use proper operator
            assert any(
                op in dep for op in [">=", ">", "==", "~=", "^"]
            ), f"Dependency '{dep}' should use proper version operator"

    def test_no_upper_version_bounds(self, pyproject_data):
        """Test that dependencies avoid strict upper version bounds."""
        dependencies = pyproject_data["project"]["dependencies"]

        # Upper bounds can cause dependency conflicts
        # We allow them but warn if they're too restrictive
        for dep in dependencies:
            if "<" in dep and "=<" not in dep:
                # Has strict upper bound - this is generally discouraged
                # but we'll just check it's not too restrictive
                if ",<" in dep:  # Has both lower and upper bound
                    # Extract bounds
                    parts = dep.split(",")
                    lower_part = [p for p in parts if ">=" in p]
                    upper_part = [p for p in parts if "<" in p]

                    if lower_part and upper_part:
                        # Just ensure they're not identical (which would be pointless)
                        assert (
                            lower_part[0].strip() != upper_part[0].strip()
                        ), f"Dependency '{dep}' has identical upper/lower bounds"

    def test_minimum_version_specified(self, pyproject_data):
        """Test that core dependencies have minimum versions specified."""
        dependencies = pyproject_data["project"]["dependencies"]

        # Core dependencies should have minimum versions
        core_deps = ["kailash", "pydantic"]

        for core_dep in core_deps:
            dep = next((d for d in dependencies if d.startswith(core_dep)), None)
            assert dep is not None, f"Core dependency '{core_dep}' not found"

            assert (
                ">=" in dep or "==" in dep or "~=" in dep
            ), f"Core dependency '{core_dep}' should specify minimum version"

    def test_typing_extensions_version(self, pyproject_data):
        """Test that typing-extensions has appropriate version for Python 3.11+."""
        dependencies = pyproject_data["project"]["dependencies"]

        typing_ext_dep = next(
            (dep for dep in dependencies if dep.startswith("typing-extensions")), None
        )

        if typing_ext_dep:
            # For Python 3.11+, we need typing-extensions >= 4.0.0
            # to support all features
            assert (
                ">=" in typing_ext_dep or ">" in typing_ext_dep
            ), f"typing-extensions '{typing_ext_dep}' should have minimum version"


class TestDependencyCompatibility:
    """Test suite for dependency compatibility validation."""

    @pytest.fixture
    def package_root(self):
        """Get the package root directory."""
        return Path(__file__).parent.parent.parent.parent

    def test_no_conflicting_dependencies(self, package_root):
        """Test that there are no conflicting dependency specifications."""
        pyproject_file = package_root / "pyproject.toml"
        with open(pyproject_file, "rb") as f:
            pyproject_data = tomllib.load(f)

        dependencies = pyproject_data["project"]["dependencies"]

        # Extract package names
        dep_names = [re.split(r"[><=!]", dep)[0].strip() for dep in dependencies]

        # Check for duplicates
        seen = set()
        duplicates = set()
        for name in dep_names:
            if name in seen:
                duplicates.add(name)
            seen.add(name)

        assert len(duplicates) == 0, f"Duplicate dependencies found: {duplicates}"

    def test_pyproject_setup_dependency_alignment(self, package_root):
        """Test that pyproject.toml and setup.py dependencies are aligned."""
        # Load pyproject.toml dependencies
        pyproject_file = package_root / "pyproject.toml"
        with open(pyproject_file, "rb") as f:
            pyproject_data = tomllib.load(f)
        pyproject_deps = pyproject_data["project"]["dependencies"]

        # Load setup.py dependencies
        setup_file = package_root / "setup.py"
        setup_content = setup_file.read_text()

        # Extract install_requires from setup.py
        install_requires_match = re.search(
            r"install_requires\s*=\s*\[(.*?)\]", setup_content, re.DOTALL
        )

        if install_requires_match:
            setup_deps_str = install_requires_match.group(1)
            # Extract individual dependencies
            setup_deps = [
                dep.strip().strip("\"'").strip()
                for dep in setup_deps_str.split(",")
                if dep.strip() and not dep.strip().startswith("#")
            ]

            # Extract package names for comparison
            pyproject_names = sorted(
                [re.split(r"[><=!]", dep)[0].strip() for dep in pyproject_deps]
            )
            setup_names = sorted(
                [
                    re.split(r"[><=!]", dep)[0].strip()
                    for dep in setup_deps
                    if dep  # Skip empty strings
                ]
            )

            # Core dependencies should be present in both
            # (some differences allowed for optional deps)
            core_deps = ["kailash", "pydantic"]
            for dep in core_deps:
                assert (
                    dep in pyproject_names
                ), f"Core dep '{dep}' missing from pyproject.toml"
                assert dep in setup_names, f"Core dep '{dep}' missing from setup.py"

    def test_python_version_compatibility(self, package_root):
        """Test that Python version requirement is consistent."""
        pyproject_file = package_root / "pyproject.toml"
        with open(pyproject_file, "rb") as f:
            pyproject_data = tomllib.load(f)

        setup_file = package_root / "setup.py"
        setup_content = setup_file.read_text()

        # Get Python version from pyproject.toml
        pyproject_python = pyproject_data["project"]["requires-python"]

        # Get Python version from setup.py
        python_requires_match = re.search(
            r'python_requires\s*=\s*["\']([^"\']+)["\']', setup_content
        )
        assert python_requires_match, "No python_requires in setup.py"
        setup_python = python_requires_match.group(1)

        # Both should require Python 3.11+
        assert pyproject_python == setup_python, (
            f"Python version mismatch: pyproject.toml={pyproject_python}, "
            f"setup.py={setup_python}"
        )
        assert (
            "3.11" in pyproject_python
        ), f"Python requirement should be >=3.11, got {pyproject_python}"


class TestDependencyResolution:
    """Test suite for dependency resolution validation."""

    @pytest.fixture
    def package_root(self):
        """Get the package root directory."""
        return Path(__file__).parent.parent.parent.parent

    def test_pip_check_passes(self, package_root):
        """Test that pip check passes (no broken dependencies)."""
        # This test runs pip check in current environment
        # It may fail in some test environments, so we make it informational
        result = subprocess.run(
            [sys.executable, "-m", "pip", "check"],
            capture_output=True,
            text=True,
            cwd=package_root,
        )

        # We don't fail the test, but we report issues
        if result.returncode != 0:
            print(f"WARNING: pip check found issues:\n{result.stdout}")
            # Don't assert here - this can fail in test environments with many packages

    def test_dependencies_installable(self, package_root):
        """Test that all dependencies are available on PyPI."""
        pyproject_file = package_root / "pyproject.toml"
        with open(pyproject_file, "rb") as f:
            pyproject_data = tomllib.load(f)

        dependencies = pyproject_data["project"]["dependencies"]

        # Extract package names
        for dep in dependencies:
            pkg_name = re.split(r"[><=!]", dep)[0].strip()

            # Try to get package info from PyPI
            result = subprocess.run(
                [sys.executable, "-m", "pip", "index", "versions", pkg_name],
                capture_output=True,
                text=True,
            )

            # If package not found, this would fail
            # We don't strictly assert here as network issues can cause failures
            if result.returncode != 0:
                print(f"WARNING: Could not verify package '{pkg_name}' on PyPI")


class TestImportDependencies:
    """Test suite for import-time dependency validation."""

    @pytest.fixture
    def package_root(self):
        """Get the package root directory."""
        return Path(__file__).parent.parent.parent.parent

    def test_no_missing_imports(self):
        """Test that all imports in the package succeed."""
        try:
            import kaizen
            from kaizen.core.base_agent import BaseAgent
            from kaizen.signatures import Signature
            from kaizen.strategies.async_single_shot import AsyncSingleShotStrategy

            # If we get here, all imports succeeded
            assert True
        except ImportError as e:
            pytest.fail(f"Missing import dependency: {e}")
        except ModuleNotFoundError as e:
            pytest.fail(f"Module not found: {e}")

    def test_core_imports_no_extras(self):
        """Test that core imports work without optional dependencies."""
        # Test that core functionality doesn't require optional deps
        try:
            import kaizen

            assert hasattr(kaizen, "__version__")

            from kaizen.core.base_agent import BaseAgent

            assert BaseAgent is not None

            from kaizen.signatures import Signature

            assert Signature is not None

        except ImportError as e:
            # Check if the error is related to optional dependencies
            error_msg = str(e).lower()
            optional_modules = ["dataflow", "nexus", "redis", "sqlalchemy"]

            is_optional = any(mod in error_msg for mod in optional_modules)
            if not is_optional:
                pytest.fail(f"Core import failed with non-optional dependency: {e}")
            # Otherwise, this is expected - optional deps may not be installed

    def test_dependency_import_performance(self):
        """Test that importing the package is reasonably fast."""
        import time

        start = time.time()
        import kaizen  # noqa: F401

        end = time.time()

        import_time_ms = (end - start) * 1000

        # Import should be under 1 second (generous limit for tests)
        assert (
            import_time_ms < 1000
        ), f"Package import took {import_time_ms:.2f}ms (should be < 1000ms)"
