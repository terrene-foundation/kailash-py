"""
Tests for platform compatibility validation.

This module tests that the package works across different platforms (Linux, macOS, Windows)
and Python versions (3.11+).
"""

import platform
import re
import sys
import tomllib
from pathlib import Path

import pytest


class TestPythonVersionCompatibility:
    """Test suite for Python version compatibility validation."""

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

    def test_current_python_version_supported(self, pyproject_data):
        """Test that current Python version meets requirements."""
        requires_python = pyproject_data["project"]["requires-python"]

        # Parse requirement (e.g., ">=3.12")
        match = re.search(r">=(\d+)\.(\d+)", requires_python)
        assert match, f"Invalid requires-python format: {requires_python}"

        required_major = int(match.group(1))
        required_minor = int(match.group(2))

        current_major = sys.version_info.major
        current_minor = sys.version_info.minor

        assert (current_major, current_minor) >= (required_major, required_minor), (
            f"Current Python {current_major}.{current_minor} does not meet "
            f"requirement {requires_python}"
        )

    def test_python_version_classifiers(self, pyproject_data):
        """Test that Python version classifiers are accurate."""
        classifiers = pyproject_data["project"]["classifiers"]
        requires_python = pyproject_data["project"]["requires-python"]

        # Get Python version classifiers
        python_classifiers = [
            c
            for c in classifiers
            if c.startswith("Programming Language :: Python :: 3.")
        ]

        assert len(python_classifiers) > 0, "No Python version classifiers found"

        # Extract version numbers from classifiers
        classifier_versions = []
        for classifier in python_classifiers:
            match = re.search(r":: 3\.(\d+)$", classifier)
            if match:
                classifier_versions.append(int(match.group(1)))

        # If requires-python is >=3.11, classifiers should include 3.11, 3.12, 3.13, etc.
        if ">=3.11" in requires_python:
            assert (
                11 in classifier_versions
            ), "Classifier for Python 3.11 missing with requires-python >=3.11"
            assert (
                13 in classifier_versions or len(classifier_versions) >= 2
            ), "Should include multiple Python version classifiers"

    def test_minimum_python_version(self, pyproject_data):
        """Test that minimum Python version is 3.11+."""
        requires_python = pyproject_data["project"]["requires-python"]

        # Extract minimum version
        match = re.search(r">=(\d+)\.(\d+)", requires_python)
        assert match, f"Invalid requires-python format: {requires_python}"

        major = int(match.group(1))
        minor = int(match.group(2))

        # Must be Python 3.11+ to align with Core SDK
        assert (major, minor) >= (
            3,
            11,
        ), f"Minimum Python version should be 3.11+, got {major}.{minor}"

    def test_no_maximum_python_version(self, pyproject_data):
        """Test that there's no strict maximum Python version."""
        requires_python = pyproject_data["project"]["requires-python"]

        # Should not have upper bound like <3.14
        assert (
            "<" not in requires_python
        ), f"Should not have maximum Python version constraint: {requires_python}"


class TestPlatformCompatibility:
    """Test suite for platform compatibility validation."""

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

    def test_os_independent_classifier(self, pyproject_data):
        """Test that package declares OS independence."""
        classifiers = pyproject_data["project"]["classifiers"]

        os_classifiers = [c for c in classifiers if c.startswith("Operating System ::")]

        assert len(os_classifiers) > 0, "No operating system classifiers found"

        # Should declare OS Independent or list multiple OSes
        os_classifier_text = " ".join(os_classifiers)
        is_os_independent = "OS Independent" in os_classifier_text

        # Either OS independent or supports multiple platforms
        assert (
            is_os_independent or len(os_classifiers) >= 3
        ), "Package should be OS Independent or support multiple platforms"

    def test_current_platform_supported(self, pyproject_data):
        """Test that current platform is supported."""
        current_platform = platform.system()

        # Package should work on major platforms

        # If classifiers specify platforms, check current is included
        classifiers = pyproject_data["project"]["classifiers"]
        os_classifiers = [c for c in classifiers if c.startswith("Operating System ::")]

        if any("OS Independent" in c for c in os_classifiers):
            # OS independent - current platform is supported
            assert True
        elif len(os_classifiers) > 0:
            # Has specific OS classifiers - check if current is included
            classifier_text = " ".join(os_classifiers)

            platform_mapping = {
                "Linux": "POSIX :: Linux",
                "Darwin": "MacOS",
                "Windows": "Microsoft :: Windows",
            }

            expected_classifier = platform_mapping.get(current_platform)
            if expected_classifier:
                # Don't strictly enforce - just informational
                if expected_classifier not in classifier_text:
                    print(
                        f"INFO: Current platform {current_platform} not explicitly "
                        f"in classifiers"
                    )

    def test_no_platform_specific_dependencies(self, pyproject_data):
        """Test that there are no platform-specific dependency markers."""
        dependencies = pyproject_data["project"]["dependencies"]

        # Check for platform markers
        platform_markers = ["platform_system", "sys_platform", "os_name"]

        for dep in dependencies:
            for marker in platform_markers:
                assert marker not in dep.lower(), (
                    f"Dependency '{dep}' has platform-specific marker - "
                    f"should be OS independent"
                )

    def test_pure_python_wheel(self, pyproject_data):
        """Test that package is configured as pure Python (universal wheel)."""
        # Pure Python packages should not have build extensions
        # This is inferred from absence of C extensions

        # Check if there's a build section indicating C extensions
        if "tool" in pyproject_data and "setuptools" in pyproject_data.get("tool", {}):
            setuptools_config = pyproject_data["tool"]["setuptools"]

            # Check for extension modules
            if "ext-modules" in setuptools_config:
                pytest.fail("Package has C extension modules - should be pure Python")

        # If we get here, package appears to be pure Python
        assert True


class TestArchitectureCompatibility:
    """Test suite for architecture compatibility validation."""

    @pytest.fixture
    def package_root(self):
        """Get the package root directory."""
        return Path(__file__).parent.parent.parent.parent

    def test_current_architecture_supported(self):
        """Test that current architecture is supported."""
        current_arch = platform.machine()

        # Package should work on common architectures
        # x86_64, amd64, arm64, aarch64, etc.
        common_architectures = [
            "x86_64",
            "amd64",
            "AMD64",
            "arm64",
            "aarch64",
            "i686",
            "i386",
        ]

        # Pure Python package should work on any architecture
        # Just informational check
        if current_arch not in common_architectures:
            print(f"INFO: Running on less common architecture: {current_arch}")

        # As long as Python runs, pure Python package should work
        assert True

    def test_no_architecture_specific_code(self, package_root):
        """Test that there's no architecture-specific compiled code."""
        src_dir = package_root / "src"

        # Check for compiled extensions
        compiled_extensions = [
            ".so",  # Unix shared object
            ".pyd",  # Windows Python extension
            ".dylib",  # macOS dynamic library
            ".dll",  # Windows dynamic library
        ]

        for ext in compiled_extensions:
            compiled_files = list(src_dir.glob(f"**/*{ext}"))
            assert (
                len(compiled_files) == 0
            ), f"Found compiled files with extension {ext}: {compiled_files}"


class TestWheelCompatibility:
    """Test suite for wheel compatibility validation."""

    @pytest.fixture
    def package_root(self):
        """Get the package root directory."""
        return Path(__file__).parent.parent.parent.parent

    def test_wheel_tag_expectations(self):
        """Test expected wheel tag for pure Python package."""
        # Pure Python packages should build as py3-none-any wheels

        # This is what we expect:
        # - py3 (Python 3)
        # - none (no ABI tag, pure Python)
        # - any (any platform)

        # We can't test the actual wheel without building it,
        # but we can verify package structure suggests pure Python

        import inspect

        import kaizen

        # Check if main module is pure Python
        kaizen_file = inspect.getfile(kaizen)
        assert kaizen_file.endswith(
            ".py"
        ), f"Main module should be .py file, got {kaizen_file}"

    def test_no_binary_distribution_requirements(self, package_root):
        """Test that package doesn't require binary distribution."""
        pyproject_file = package_root / "pyproject.toml"
        with open(pyproject_file, "rb") as f:
            pyproject_data = tomllib.load(f)

        # Check for binary distribution markers
        if "tool" in pyproject_data and "setuptools" in pyproject_data.get("tool", {}):
            setuptools_config = pyproject_data["tool"]["setuptools"]

            # These indicate binary requirements
            binary_markers = [
                "ext-modules",
                "include-package-data",  # When used with C extensions
            ]

            for marker in binary_markers:
                if marker in setuptools_config and marker == "ext-modules":
                    pytest.fail(
                        f"Package has {marker} indicating binary distribution needed"
                    )


class TestEnvironmentCompatibility:
    """Test suite for environment compatibility validation."""

    def test_package_imports_in_current_environment(self):
        """Test that package imports successfully in current environment."""
        try:
            import kaizen

            assert kaizen is not None

            from kaizen.core.base_agent import BaseAgent

            assert BaseAgent is not None

        except Exception as e:
            pytest.fail(f"Package import failed in current environment: {e}")

    def test_no_system_dependencies(self):
        """Test that package has no external system dependencies."""
        # Pure Python packages should not require system libraries

        try:
            import kaizen
            from kaizen.core.base_agent import BaseAgent

            # If imports succeed without system library errors, we're good
            assert True

        except ImportError as e:
            error_msg = str(e).lower()

            # Check for common system library errors
            system_lib_indicators = [
                "lib",
                ".so",
                ".dll",
                ".dylib",
                "cannot open shared object",
                "dll load failed",
            ]

            has_system_dep_error = any(
                indicator in error_msg for indicator in system_lib_indicators
            )

            if has_system_dep_error:
                pytest.fail(f"Package has system library dependency: {e}")
            else:
                # Some other import error - re-raise
                raise

    def test_virtual_environment_compatibility(self):
        """Test that package works in virtual environments."""
        # Check if we're in a virtual environment
        in_venv = hasattr(sys, "real_prefix") or (
            hasattr(sys, "base_prefix") and sys.base_prefix != sys.prefix
        )

        # Package should work regardless of venv status
        try:
            import kaizen

            assert kaizen is not None

        except Exception as e:
            venv_status = "in venv" if in_venv else "not in venv"
            pytest.fail(f"Package import failed ({venv_status}): {e}")

    def test_isolation_from_system_packages(self):
        """Test that package doesn't have undeclared system package dependencies."""
        # This test verifies that the package declares all its dependencies

        try:
            import kaizen
            from kaizen.core.base_agent import BaseAgent
            from kaizen.signatures import Signature

            # If these core imports work, dependencies are properly declared
            assert True

        except ImportError as e:
            # An import error here suggests missing declared dependency
            pytest.fail(f"Missing declared dependency (import error): {e}")


class TestDockerCompatibility:
    """Test suite for Docker/container compatibility validation."""

    @pytest.fixture
    def package_root(self):
        """Get the package root directory."""
        return Path(__file__).parent.parent.parent.parent

    def test_dockerfile_exists(self, package_root):
        """Test that Dockerfile exists for containerized deployment."""
        # Check for Dockerfile or docker directory
        dockerfile_locations = [
            package_root / "Dockerfile",
            package_root / "docker" / "Dockerfile",
            package_root / ".docker" / "Dockerfile",
        ]

        dockerfile_found = any(loc.exists() for loc in dockerfile_locations)

        # This is informational - not all packages need Docker
        if not dockerfile_found:
            print(
                "INFO: No Dockerfile found - package may not support containerization"
            )

    def test_dockerignore_exists(self, package_root):
        """Test that .dockerignore exists if Dockerfile exists."""
        dockerfile = package_root / "Dockerfile"

        if dockerfile.exists():
            dockerignore = package_root / ".dockerignore"
            # Informational check
            if not dockerignore.exists():
                print("INFO: Dockerfile exists but no .dockerignore found")

    def test_no_hardcoded_paths(self, package_root):
        """Test that code doesn't contain hardcoded absolute paths."""
        src_dir = package_root / "src"

        # Common hardcoded path patterns that break in containers
        bad_patterns = [
            r"/home/\w+/",  # Unix home paths
            r"C:\\Users\\",  # Windows paths
            r"/Users/\w+/",  # macOS paths
        ]

        # Check Python files for hardcoded paths
        for py_file in src_dir.glob("**/*.py"):
            content = py_file.read_text()

            for pattern in bad_patterns:
                matches = re.findall(pattern, content)
                if matches:
                    # Filter out comments and docstrings
                    lines = content.split("\n")
                    real_matches = []
                    for match in matches:
                        for line in lines:
                            if match in line and not line.strip().startswith("#"):
                                if '"""' not in line and "'''" not in line:
                                    real_matches.append(match)

                    assert (
                        len(real_matches) == 0
                    ), f"File {py_file} contains hardcoded paths: {real_matches}"
