"""
Tests for package installation validation.

This module tests that the package can be built, installed, and used correctly
across different installation methods (source dist, wheel, editable, with extras).
"""

import re
import shutil
import subprocess
import sys
import tempfile
import tomllib
import venv
from pathlib import Path

import pytest


class TestPackageBuild:
    """Test suite for package build validation."""

    @pytest.fixture
    def package_root(self):
        """Get the package root directory."""
        return Path(__file__).parent.parent.parent.parent

    @pytest.fixture
    def clean_build_dir(self, package_root):
        """Ensure clean build directory for tests."""
        build_dirs = ["build", "dist", "*.egg-info"]
        for pattern in build_dirs:
            for path in package_root.glob(pattern):
                if path.exists():
                    if path.is_dir():
                        shutil.rmtree(path)
                    else:
                        path.unlink()
        yield
        # Cleanup after test
        for pattern in build_dirs:
            for path in package_root.glob(pattern):
                if path.exists():
                    if path.is_dir():
                        shutil.rmtree(path)
                    else:
                        path.unlink()

    def test_source_distribution_builds(self, package_root, clean_build_dir):
        """Test that source distribution builds successfully."""
        result = subprocess.run(
            [sys.executable, "-m", "build", "--sdist", str(package_root)],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0, f"Source dist build failed: {result.stderr}"

        # Verify sdist was created
        dist_dir = package_root / "dist"
        sdist_files = list(dist_dir.glob("*.tar.gz"))
        assert len(sdist_files) > 0, "No source distribution file created"

        # Verify naming convention
        sdist_name = sdist_files[0].name
        assert sdist_name.startswith(
            "kailash_kaizen-"
        ), f"Source dist name '{sdist_name}' should start with 'kailash_kaizen-'"

    def test_wheel_distribution_builds(self, package_root, clean_build_dir):
        """Test that wheel distribution builds successfully."""
        result = subprocess.run(
            [sys.executable, "-m", "build", "--wheel", str(package_root)],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0, f"Wheel build failed: {result.stderr}"

        # Verify wheel was created
        dist_dir = package_root / "dist"
        wheel_files = list(dist_dir.glob("*.whl"))
        assert len(wheel_files) > 0, "No wheel file created"

        # Verify naming convention (kailash_kaizen-version-py3-none-any.whl)
        wheel_name = wheel_files[0].name
        assert wheel_name.startswith(
            "kailash_kaizen-"
        ), f"Wheel name '{wheel_name}' should start with 'kailash_kaizen-'"
        assert wheel_name.endswith(
            "-py3-none-any.whl"
        ), f"Wheel name '{wheel_name}' should end with '-py3-none-any.whl' for pure Python"

    def test_both_distributions_build(self, package_root, clean_build_dir):
        """Test that both sdist and wheel can be built together."""
        result = subprocess.run(
            [sys.executable, "-m", "build", str(package_root)],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0, f"Build failed: {result.stderr}"

        # Verify both distributions created
        dist_dir = package_root / "dist"
        sdist_files = list(dist_dir.glob("*.tar.gz"))
        wheel_files = list(dist_dir.glob("*.whl"))

        assert len(sdist_files) > 0, "No source distribution created"
        assert len(wheel_files) > 0, "No wheel created"

    def test_build_backend_configured(self, package_root):
        """Test that build backend is properly configured."""
        pyproject_file = package_root / "pyproject.toml"
        with open(pyproject_file, "rb") as f:
            pyproject_data = tomllib.load(f)

        assert (
            "build-system" in pyproject_data
        ), "Missing build-system in pyproject.toml"
        build_system = pyproject_data["build-system"]

        assert "requires" in build_system, "Missing requires in build-system"
        assert "build-backend" in build_system, "Missing build-backend in build-system"

        # Verify modern build tools
        requires = build_system["requires"]
        assert any(
            "setuptools" in req for req in requires
        ), "setuptools should be in requires"
        assert (
            build_system["build-backend"] == "setuptools.build_meta"
        ), "build-backend should be setuptools.build_meta"


@pytest.mark.timeout(300)  # 5 minutes for installation tests
class TestPackageInstallation:
    """Test suite for package installation validation."""

    @pytest.fixture
    def package_root(self):
        """Get the package root directory."""
        return Path(__file__).parent.parent.parent.parent

    @pytest.fixture
    def isolated_venv(self):
        """Create isolated virtual environment for testing installation."""
        with tempfile.TemporaryDirectory() as temp_dir:
            venv_path = Path(temp_dir) / "test_venv"
            venv.create(venv_path, with_pip=True, clear=True)

            # Get paths to python and pip in venv
            if sys.platform == "win32":
                python_path = venv_path / "Scripts" / "python.exe"
                pip_path = venv_path / "Scripts" / "pip.exe"
            else:
                python_path = venv_path / "bin" / "python"
                pip_path = venv_path / "bin" / "pip"

            yield {
                "venv_path": venv_path,
                "python": str(python_path),
                "pip": str(pip_path),
            }

    def test_install_from_source_dist(self, package_root, isolated_venv):
        """Test installation from source distribution."""
        # Build source distribution first
        subprocess.run(
            [sys.executable, "-m", "build", "--sdist", str(package_root)],
            capture_output=True,
            check=True,
        )

        # Get the sdist file
        dist_dir = package_root / "dist"
        sdist_files = list(dist_dir.glob("*.tar.gz"))
        assert len(sdist_files) > 0, "No source distribution found"
        sdist_path = sdist_files[0]

        # Install from sdist
        result = subprocess.run(
            [isolated_venv["pip"], "install", str(sdist_path)],
            capture_output=True,
            text=True,
        )

        assert (
            result.returncode == 0
        ), f"Installation from sdist failed: {result.stderr}"

        # Verify package is importable
        import_test = subprocess.run(
            [isolated_venv["python"], "-c", "import kaizen; print(kaizen.__version__)"],
            capture_output=True,
            text=True,
        )

        assert (
            import_test.returncode == 0
        ), f"Package import failed: {import_test.stderr}"
        assert len(import_test.stdout.strip()) > 0, "No version string returned"

    def test_install_from_wheel(self, package_root, isolated_venv):
        """Test installation from wheel distribution."""
        # Build wheel first
        subprocess.run(
            [sys.executable, "-m", "build", "--wheel", str(package_root)],
            capture_output=True,
            check=True,
        )

        # Get the wheel file
        dist_dir = package_root / "dist"
        wheel_files = list(dist_dir.glob("*.whl"))
        assert len(wheel_files) > 0, "No wheel found"
        wheel_path = wheel_files[0]

        # Install from wheel
        result = subprocess.run(
            [isolated_venv["pip"], "install", str(wheel_path)],
            capture_output=True,
            text=True,
        )

        assert (
            result.returncode == 0
        ), f"Installation from wheel failed: {result.stderr}"

        # Verify package is importable
        import_test = subprocess.run(
            [isolated_venv["python"], "-c", "import kaizen; print(kaizen.__version__)"],
            capture_output=True,
            text=True,
        )

        assert (
            import_test.returncode == 0
        ), f"Package import failed: {import_test.stderr}"
        assert len(import_test.stdout.strip()) > 0, "No version string returned"

    def test_editable_installation(self, package_root, isolated_venv):
        """Test editable (development) installation."""
        result = subprocess.run(
            [isolated_venv["pip"], "install", "-e", str(package_root)],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0, f"Editable install failed: {result.stderr}"

        # Verify package is importable
        import_test = subprocess.run(
            [isolated_venv["python"], "-c", "import kaizen; print(kaizen.__version__)"],
            capture_output=True,
            text=True,
        )

        assert (
            import_test.returncode == 0
        ), f"Package import failed: {import_test.stderr}"

    def test_install_with_dev_extras(self, package_root, isolated_venv):
        """Test installation with dev extra dependencies."""
        result = subprocess.run(
            [isolated_venv["pip"], "install", "-e", f"{package_root}[dev]"],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0, f"Install with [dev] failed: {result.stderr}"

        # Verify dev dependencies are installed
        dev_packages = [
            "pytest",
            "pytest-asyncio",
            "pytest-cov",
            "black",
            "isort",
            "ruff",
        ]
        for pkg in dev_packages:
            check_result = subprocess.run(
                [isolated_venv["pip"], "show", pkg],
                capture_output=True,
                text=True,
            )
            assert check_result.returncode == 0, f"Dev package '{pkg}' not installed"

    def test_clean_installation_no_warnings(self, package_root, isolated_venv):
        """Test that installation produces no warnings or errors."""
        result = subprocess.run(
            [isolated_venv["pip"], "install", "-e", str(package_root)],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0, f"Installation failed: {result.stderr}"

        # Check for common warning patterns
        warning_patterns = [
            r"WARNING",
            r"ERROR",
            r"deprecated",
            r"missing.*required",
        ]

        for pattern in warning_patterns:
            matches = re.findall(pattern, result.stderr, re.IGNORECASE)
            # Allow some warnings but not critical ones
            if pattern in [r"ERROR", r"missing.*required"]:
                assert (
                    len(matches) == 0
                ), f"Installation produced critical warnings/errors: {matches}"


@pytest.mark.timeout(300)  # 5 minutes for installation validation tests
class TestInstallationValidation:
    """Test suite for post-installation validation."""

    @pytest.fixture
    def package_root(self):
        """Get the package root directory."""
        return Path(__file__).parent.parent.parent.parent

    @pytest.fixture
    def isolated_venv(self):
        """Create isolated virtual environment for testing installation."""
        with tempfile.TemporaryDirectory() as temp_dir:
            venv_path = Path(temp_dir) / "test_venv"
            venv.create(venv_path, with_pip=True, clear=True)

            if sys.platform == "win32":
                python_path = venv_path / "Scripts" / "python.exe"
                pip_path = venv_path / "Scripts" / "pip.exe"
            else:
                python_path = venv_path / "bin" / "python"
                pip_path = venv_path / "bin" / "pip"

            # Install package in editable mode
            subprocess.run(
                [
                    str(pip_path),
                    "install",
                    "-e",
                    str(Path(__file__).parent.parent.parent.parent),
                ],
                capture_output=True,
                check=True,
            )

            yield {
                "venv_path": venv_path,
                "python": str(python_path),
                "pip": str(pip_path),
            }

    def test_package_version_accessible(self, isolated_venv):
        """Test that package version is accessible after installation."""
        result = subprocess.run(
            [isolated_venv["python"], "-c", "import kaizen; print(kaizen.__version__)"],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0, f"Version check failed: {result.stderr}"
        output = result.stdout.strip()
        assert len(output) > 0, "Version output is empty"
        # Extract the last line which should be the version
        # (other lines may be debug output from module loading)
        version = output.split("\n")[-1].strip()
        assert re.match(
            r"\d+\.\d+\.\d+", version
        ), f"Version '{version}' does not match semver pattern"

    def test_core_modules_importable(self, isolated_venv):
        """Test that core modules are importable after installation."""
        modules = [
            "kaizen",
            "kaizen.core",
            "kaizen.core.base_agent",
            "kaizen.signatures",
            "kaizen.strategies",
        ]

        for module in modules:
            result = subprocess.run(
                [isolated_venv["python"], "-c", f"import {module}"],
                capture_output=True,
                text=True,
            )
            assert (
                result.returncode == 0
            ), f"Module '{module}' import failed: {result.stderr}"

    def test_dependencies_installed(self, isolated_venv):
        """Test that required dependencies are installed."""
        # Get dependencies from pyproject.toml
        package_root = Path(__file__).parent.parent.parent.parent
        pyproject_file = package_root / "pyproject.toml"
        with open(pyproject_file, "rb") as f:
            pyproject_data = tomllib.load(f)

        dependencies = pyproject_data["project"]["dependencies"]

        # Extract package names (without version constraints)
        for dep in dependencies:
            pkg_name = re.split(r"[><=!]", dep)[0].strip()
            result = subprocess.run(
                [isolated_venv["pip"], "show", pkg_name],
                capture_output=True,
                text=True,
            )
            assert result.returncode == 0, f"Dependency '{pkg_name}' not installed"

    def test_no_missing_dependencies(self, isolated_venv):
        """Test that there are no missing dependencies on import."""
        result = subprocess.run(
            [
                isolated_venv["python"],
                "-c",
                "import kaizen; from kaizen.core.base_agent import BaseAgent",
            ],
            capture_output=True,
            text=True,
        )

        assert (
            result.returncode == 0
        ), f"Import failed with missing dependencies: {result.stderr}"
        assert (
            "ModuleNotFoundError" not in result.stderr
        ), f"Missing dependencies detected: {result.stderr}"
        assert (
            "ImportError" not in result.stderr
        ), f"Import errors detected: {result.stderr}"

    def test_package_metadata_accessible(self, isolated_venv):
        """Test that package metadata is accessible via pip."""
        result = subprocess.run(
            [isolated_venv["pip"], "show", "kailash-kaizen"],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0, "Package metadata not accessible"

        # Verify key metadata fields
        metadata = result.stdout
        assert "Name: kailash-kaizen" in metadata, "Package name not in metadata"
        assert "Version:" in metadata, "Version not in metadata"
        assert (
            "Summary:" in metadata or "Description:" in metadata
        ), "Description not in metadata"
