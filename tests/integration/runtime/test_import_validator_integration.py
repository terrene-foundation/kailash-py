"""Integration tests for import validator with production deployment simulation."""

import os
import subprocess
import sys
import tempfile
from pathlib import Path
from textwrap import dedent

import pytest
from kailash.runtime.validation import ImportPathValidator
from kailash.runtime.validation.import_validator import ImportIssueType


class TestImportValidatorIntegration:
    """Test import validator in production-like scenarios."""

    def setup_method(self):
        """Set up test environment."""
        self.temp_dir = tempfile.mkdtemp()
        self.validator = ImportPathValidator(repo_root=self.temp_dir)

        # Create a realistic project structure
        self._create_realistic_project()

    def teardown_method(self):
        """Clean up test environment."""
        import shutil

        shutil.rmtree(self.temp_dir)

    def _create_realistic_project(self):
        """Create a realistic SDK project structure."""
        # Main entry point
        main_py = Path(self.temp_dir) / "main.py"
        main_py.write_text(
            dedent(
                """
            import sys
            from src.myapp.workflows.data_processor import DataProcessor

            def main():
                processor = DataProcessor()
                result = processor.run()
                print(f"Result: {result}")
                return result

            if __name__ == "__main__":
                sys.exit(0 if main() else 1)
        """
            ).strip()
        )

        # Create src structure
        src_dir = Path(self.temp_dir) / "src"
        src_dir.mkdir()

        # Create app module
        app_dir = src_dir / "myapp"
        app_dir.mkdir()
        (app_dir / "__init__.py").write_text('"""My application."""')

        # Create contracts
        contracts_dir = app_dir / "contracts"
        contracts_dir.mkdir()
        (contracts_dir / "__init__.py").touch()

        (contracts_dir / "base_contract.py").write_text(
            dedent(
                """
            class BaseContract:
                def validate(self, data):
                    return True
        """
            ).strip()
        )

        (contracts_dir / "user_contract.py").write_text(
            dedent(
                """
            from .base_contract import BaseContract

            class UserContract(BaseContract):
                def validate(self, data):
                    return "name" in data and "email" in data
        """
            ).strip()
        )

        # Create nodes
        nodes_dir = app_dir / "nodes"
        nodes_dir.mkdir()
        (nodes_dir / "__init__.py").touch()

        base_dir = nodes_dir / "base"
        base_dir.mkdir()
        (base_dir / "__init__.py").touch()

        (base_dir / "base_node.py").write_text(
            dedent(
                """
            class BaseNode:
                def execute(self, **kwargs):
                    return self.run(**kwargs)

                def run(self, **kwargs):
                    raise NotImplementedError
        """
            ).strip()
        )

        # Create workflows with problematic imports
        workflows_dir = app_dir / "workflows"
        workflows_dir.mkdir()
        (workflows_dir / "__init__.py").touch()

        # File with relative imports (will fail in production)
        (workflows_dir / "data_processor_bad.py").write_text(
            dedent(
                """
            from ..contracts.user_contract import UserContract
            from ..nodes.base.base_node import BaseNode
            from contracts.base_contract import BaseContract  # Implicit relative

            class DataProcessor(BaseNode):
                def __init__(self):
                    self.contract = UserContract()

                def run(self):
                    return {"status": "processed"}
        """
            ).strip()
        )

        # File with absolute imports (production ready)
        (workflows_dir / "data_processor.py").write_text(
            dedent(
                """
            from src.myapp.contracts.user_contract import UserContract
            from src.myapp.nodes.base.base_node import BaseNode
            from src.myapp.contracts.base_contract import BaseContract

            class DataProcessor(BaseNode):
                def __init__(self):
                    self.contract = UserContract()

                def run(self):
                    return {"status": "processed"}
        """
            ).strip()
        )

    def test_validate_production_structure(self):
        """Test validation of a production-like project structure."""
        app_dir = Path(self.temp_dir) / "src" / "myapp"
        issues = self.validator.validate_directory(app_dir, recursive=True)

        # Should find issues in data_processor_bad.py
        assert len(issues) > 0

        bad_file_issues = [i for i in issues if "data_processor_bad.py" in i.file_path]
        assert len(bad_file_issues) >= 3  # Three import issues

        # Check issue types
        relative_issues = [i for i in bad_file_issues if "Relative import" in i.message]
        implicit_issues = [
            i for i in bad_file_issues if "Implicit relative" in i.message
        ]

        assert len(relative_issues) >= 2
        assert len(implicit_issues) >= 1

    def test_production_deployment_simulation(self):
        """Test that relative imports fail when running from repo root."""
        # Create a test script that uses relative imports
        test_script = Path(self.temp_dir) / "test_imports.py"
        test_script.write_text(
            dedent(
                """
            import sys
            import os

            # Add src to path (simulating production setup)
            sys.path.insert(0, os.path.dirname(__file__))

            try:
                # This should work - absolute import
                from src.myapp.workflows.data_processor import DataProcessor
                print("✅ Absolute import successful")

                # This should fail - module with relative imports
                from src.myapp.workflows.data_processor_bad import DataProcessor as BadProcessor
                print("❌ Relative import should have failed!")
                sys.exit(1)

            except ImportError as e:
                print(f"✅ Relative import failed as expected: {e}")
                sys.exit(0)
        """
            ).strip()
        )

        # Run the test script from repo root
        result = subprocess.run(
            [sys.executable, str(test_script)],
            cwd=self.temp_dir,
            capture_output=True,
            text=True,
        )

        # The script should exit with 0 (relative imports failed as expected)
        assert result.returncode == 0
        assert "Absolute import successful" in result.stdout
        assert "Relative import failed as expected" in result.stdout

    def test_docker_simulation(self):
        """Test import validation for Docker deployment patterns."""
        # Create Dockerfile pattern
        dockerfile = Path(self.temp_dir) / "Dockerfile"
        dockerfile.write_text(
            dedent(
                """
            FROM python:3.9
            WORKDIR /app
            COPY . .
            CMD ["python", "main.py"]
        """
            ).strip()
        )

        # Validate the main entry point
        issues = self.validator.validate_file(Path(self.temp_dir) / "main.py")

        # Main.py uses absolute imports, should be clean
        assert len(issues) == 0

        # Validate the entire source tree
        src_issues = self.validator.validate_directory(
            Path(self.temp_dir) / "src", recursive=True
        )

        # Should find issues in bad files
        assert any("data_processor_bad.py" in issue.file_path for issue in src_issues)

        # Generate deployment readiness report
        report = self.validator.generate_report(src_issues)
        assert "CRITICAL ISSUES" in report
        assert "Will fail in production" in report

    def test_fix_imports_for_production(self):
        """Test fixing imports for production deployment."""
        bad_file = (
            Path(self.temp_dir)
            / "src"
            / "myapp"
            / "workflows"
            / "data_processor_bad.py"
        )

        # Get current issues
        issues_before = self.validator.validate_file(bad_file)
        assert len(issues_before) > 0

        # Get proposed fixes
        fixes = self.validator.fix_imports_in_file(str(bad_file), dry_run=True)

        assert len(fixes) > 0

        # Check that fixes suggest absolute imports
        for original, fixed in fixes:
            if ".." in original:  # Relative import
                assert "src.myapp" in fixed
                assert ".." not in fixed

    def test_package_distribution_compatibility(self):
        """Test validation for package distribution scenarios."""
        # Create setup.py
        setup_py = Path(self.temp_dir) / "setup.py"
        setup_py.write_text(
            dedent(
                """
            from setuptools import setup, find_packages

            setup(
                name="myapp",
                packages=find_packages(where="src"),
                package_dir={"": "src"},
            )
        """
            ).strip()
        )

        # Validate for package distribution
        issues = self.validator.validate_directory(
            Path(self.temp_dir) / "src", recursive=True
        )

        # Report should highlight distribution issues
        report = self.validator.generate_report(issues)

        critical_issues = [i for i in issues if i.severity == "critical"]
        assert len(critical_issues) > 0

        # All critical issues should have production-ready suggestions
        for issue in critical_issues:
            assert "src.myapp" in issue.suggestion

    def test_ci_cd_validation_workflow(self):
        """Test validation as part of CI/CD workflow."""
        # Create a validation script for CI/CD
        ci_script = Path(self.temp_dir) / "validate_imports.py"
        ci_script.write_text(
            dedent(
                """
            from pathlib import Path
            from kailash.runtime.validation import ImportPathValidator

            validator = ImportPathValidator()
            issues = validator.validate_directory("src", recursive=True)

            if issues:
                print(validator.generate_report(issues))
                exit(1)
            else:
                print("✅ All imports are production-ready!")
                exit(0)
        """
            ).strip()
        )

        # Run validation
        result = subprocess.run(
            [sys.executable, str(ci_script)],
            cwd=self.temp_dir,
            capture_output=True,
            text=True,
        )

        # Should fail due to bad imports
        assert result.returncode == 1
        assert "IMPORT VALIDATION REPORT" in result.stdout
        assert "CRITICAL ISSUES" in result.stdout

    def test_migration_path_validation(self):
        """Test validation provides clear migration path."""
        bad_file = (
            Path(self.temp_dir)
            / "src"
            / "myapp"
            / "workflows"
            / "data_processor_bad.py"
        )
        issues = self.validator.validate_file(bad_file)

        # Each issue should have a clear suggestion
        for issue in issues:
            assert issue.suggestion
            assert "from src.myapp" in issue.suggestion

            # Suggestion should be a valid Python import
            assert issue.suggestion.startswith("from ")
            assert " import " in issue.suggestion

    def test_complex_project_validation(self):
        """Test validation of complex project with multiple modules."""
        # Add another module
        other_module = Path(self.temp_dir) / "src" / "other_module"
        other_module.mkdir(parents=True)
        (other_module / "__init__.py").touch()

        # Cross-module import (should be absolute)
        cross_import_file = other_module / "consumer.py"
        cross_import_file.write_text(
            dedent(
                """
            # Bad: trying to use relative import for cross-module
            from ..myapp.contracts import UserContract

            # Good: absolute import
            from src.myapp.contracts.user_contract import UserContract
        """
            ).strip()
        )

        issues = self.validator.validate_file(cross_import_file)

        # Should catch the relative cross-module import
        assert any(
            issue.issue_type == ImportIssueType.RELATIVE_IMPORT for issue in issues
        )

        # Should suggest proper absolute import
        assert any("src.myapp.contracts" in issue.suggestion for issue in issues)
