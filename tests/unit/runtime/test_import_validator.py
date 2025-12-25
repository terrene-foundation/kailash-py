"""Unit tests for import path validator."""

import os
import tempfile
from pathlib import Path
from textwrap import dedent

import pytest
from kailash.runtime.validation import ImportIssue, ImportIssueType, ImportPathValidator


class TestImportPathValidator:
    """Test import path validation functionality."""

    def setup_method(self):
        """Set up test environment."""
        self.temp_dir = tempfile.mkdtemp()
        self.validator = ImportPathValidator(repo_root=self.temp_dir)

        # Create a mock project structure
        self._create_test_structure()

    def teardown_method(self):
        """Clean up test environment."""
        import shutil

        shutil.rmtree(self.temp_dir)

    def _create_test_structure(self):
        """Create test directory structure."""
        # Create src structure
        src_dir = Path(self.temp_dir) / "src"
        src_dir.mkdir()

        # Create module structure
        module_dir = src_dir / "mymodule"
        module_dir.mkdir()
        (module_dir / "__init__.py").touch()

        # Create sub-packages
        contracts_dir = module_dir / "contracts"
        contracts_dir.mkdir()
        (contracts_dir / "__init__.py").touch()

        nodes_dir = module_dir / "nodes"
        nodes_dir.mkdir()
        (nodes_dir / "__init__.py").touch()

        core_dir = module_dir / "core"
        core_dir.mkdir()
        (core_dir / "__init__.py").touch()

    def _create_test_file(self, relative_path: str, content: str) -> Path:
        """Create a test file with given content."""
        file_path = Path(self.temp_dir) / relative_path
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(dedent(content).strip())
        return file_path

    def test_detect_relative_import(self):
        """Test detection of explicit relative imports."""
        test_file = self._create_test_file(
            "src/mymodule/nodes/processor.py",
            """
            from . import base
            from .. import contracts
            from ...utils import helpers
            """,
        )

        issues = self.validator.validate_file(test_file)

        assert len(issues) == 3
        assert all(
            issue.issue_type == ImportIssueType.RELATIVE_IMPORT for issue in issues
        )
        assert all(issue.severity == "critical" for issue in issues)
        assert "will fail in production deployment" in issues[0].message

    def test_detect_implicit_relative_import(self):
        """Test detection of implicit relative imports."""
        test_file = self._create_test_file(
            "src/mymodule/nodes/processor.py",
            """
            from contracts.user_contract import UserContract
            from nodes.base import BaseNode
            from core.utils import validate
            """,
        )

        issues = self.validator.validate_file(test_file)

        assert len(issues) == 3
        assert all(
            issue.issue_type == ImportIssueType.IMPLICIT_RELATIVE for issue in issues
        )
        assert all(issue.severity == "critical" for issue in issues)
        assert "Implicit relative import" in issues[0].message
        assert "will fail when run from repo root" in issues[0].message

    def test_accept_absolute_imports(self):
        """Test that absolute imports are accepted."""
        test_file = self._create_test_file(
            "src/mymodule/nodes/processor.py",
            """
            from src.mymodule.contracts.user_contract import UserContract
            from src.mymodule.nodes.base import BaseNode
            from src.mymodule.core.utils import validate
            import os
            import json
            from typing import Dict, List
            """,
        )

        issues = self.validator.validate_file(test_file)

        assert len(issues) == 0

    def test_generate_absolute_import_suggestions(self):
        """Test generation of correct absolute import suggestions."""
        test_file = self._create_test_file(
            "src/mymodule/nodes/processor.py",
            """
            from ..contracts.user_contract import UserContract
            from .base import BaseNode
            """,
        )

        issues = self.validator.validate_file(test_file)

        assert len(issues) == 2

        # Check first suggestion (parent relative)
        assert "src.mymodule.contracts.user_contract" in issues[0].suggestion

        # Check second suggestion (current dir relative)
        assert "src.mymodule.nodes.base" in issues[1].suggestion

    def test_detect_local_module_imports(self):
        """Test detection of ambiguous local module imports."""
        # Create a local module file
        self._create_test_file("src/mymodule/utils.py", "# Utils module")

        test_file = self._create_test_file(
            "src/mymodule/processor.py",
            """
            import utils
            import contracts
            """,
        )

        issues = self.validator.validate_file(test_file)

        assert len(issues) >= 1
        assert any(issue.issue_type == ImportIssueType.LOCAL_IMPORT for issue in issues)
        assert any(issue.severity == "warning" for issue in issues)

    def test_skip_standard_library_imports(self):
        """Test that standard library imports are not flagged."""
        test_file = self._create_test_file(
            "src/mymodule/processor.py",
            """
            import os
            import sys
            import json
            from pathlib import Path
            from typing import Dict, List
            import logging
            """,
        )

        issues = self.validator.validate_file(test_file)

        assert len(issues) == 0

    def test_skip_third_party_imports(self):
        """Test that common third-party imports are not flagged."""
        test_file = self._create_test_file(
            "src/mymodule/processor.py",
            """
            import pytest
            import numpy as np
            import pandas as pd
            from requests import Session
            """,
        )

        issues = self.validator.validate_file(test_file)

        assert len(issues) == 0

    def test_validate_directory(self):
        """Test validating an entire directory."""
        # Create multiple test files
        self._create_test_file("src/mymodule/file1.py", "from .base import Base")
        self._create_test_file(
            "src/mymodule/file2.py", "from contracts import Contract"
        )
        self._create_test_file(
            "src/mymodule/file3.py", "from src.mymodule.core import Core"  # Valid
        )

        module_dir = Path(self.temp_dir) / "src" / "mymodule"
        issues = self.validator.validate_directory(module_dir)

        assert len(issues) == 2  # file1 and file2 have issues
        assert any("file1.py" in issue.file_path for issue in issues)
        assert any("file2.py" in issue.file_path for issue in issues)

    def test_skip_test_files(self):
        """Test that test files are skipped by default."""
        self._create_test_file(
            "src/mymodule/test_processor.py", "from .processor import process"
        )
        self._create_test_file(
            "src/mymodule/processor_test.py", "from .processor import process"
        )

        module_dir = Path(self.temp_dir) / "src" / "mymodule"
        issues = self.validator.validate_directory(module_dir)

        assert len(issues) == 0  # Test files should be skipped

    def test_generate_report(self):
        """Test report generation."""
        # Create files with different issue types
        test_file = self._create_test_file(
            "src/mymodule/processor.py",
            """
            from ..contracts import Contract  # Critical
            import utils  # Warning
            """,
        )

        issues = self.validator.validate_file(test_file)
        report = self.validator.generate_report(issues)

        assert "IMPORT VALIDATION REPORT" in report
        assert "CRITICAL ISSUES" in report
        assert "WARNINGS" in report
        assert "sdk-users/7-gold-standards/absolute-imports-gold-standard.md" in report

    def test_generate_report_no_issues(self):
        """Test report generation when no issues found."""
        report = self.validator.generate_report([])

        assert "✅ No import issues found" in report
        assert "production-ready" in report

    def test_fix_imports_dry_run(self):
        """Test import fixing in dry run mode."""
        test_file = self._create_test_file(
            "src/mymodule/nodes/processor.py",
            """
            from ..contracts import Contract
            from .base import BaseNode
            """,
        )

        fixes = self.validator.fix_imports_in_file(str(test_file), dry_run=True)

        assert len(fixes) == 2
        assert all(isinstance(fix, tuple) and len(fix) == 2 for fix in fixes)

        # Check that file wasn't modified
        content = test_file.read_text()
        assert "from ..contracts" in content  # Original still there

    def test_complex_import_scenarios(self):
        """Test various complex import scenarios."""
        test_file = self._create_test_file(
            "src/mymodule/subpackage/deep/module.py",
            """
            # Various import patterns
            from . import sibling
            from .. import parent_module
            from ...nodes import NodeClass
            from contracts.base import BaseContract
            from src.mymodule.core import absolute_import
            import typing
            from dataclasses import dataclass
            """,
        )

        issues = self.validator.validate_file(test_file)

        # Should detect relative and implicit relative imports
        relative_issues = [
            i for i in issues if i.issue_type == ImportIssueType.RELATIVE_IMPORT
        ]
        implicit_issues = [
            i for i in issues if i.issue_type == ImportIssueType.IMPLICIT_RELATIVE
        ]

        assert len(relative_issues) == 3  # Three explicit relative imports
        assert len(implicit_issues) >= 1  # At least one implicit relative

        # Absolute imports and stdlib should be fine
        assert not any(
            "src.mymodule.core" in issue.import_statement for issue in issues
        )
        assert not any("typing" in issue.import_statement for issue in issues)
        assert not any("dataclasses" in issue.import_statement for issue in issues)

    def test_multiline_imports(self):
        """Test handling of multiline import statements."""
        test_file = self._create_test_file(
            "src/mymodule/processor.py",
            """
            from ..contracts import (
                UserContract,
                AdminContract,
                GuestContract
            )
            """,
        )

        issues = self.validator.validate_file(test_file)

        assert len(issues) == 1
        assert issues[0].issue_type == ImportIssueType.RELATIVE_IMPORT

    def test_import_as_statements(self):
        """Test handling of import with aliases."""
        test_file = self._create_test_file(
            "src/mymodule/processor.py",
            """
            from ..contracts import UserContract as UC
            from .base import BaseNode as BN
            import contracts as c
            """,
        )

        issues = self.validator.validate_file(test_file)

        assert len(issues) >= 2  # At least the two relative imports

    def test_star_imports(self):
        """Test handling of star imports."""
        test_file = self._create_test_file(
            "src/mymodule/processor.py",
            """
            from ..contracts import *
            from nodes import *
            """,
        )

        issues = self.validator.validate_file(test_file)

        assert len(issues) == 2
        assert issues[0].issue_type == ImportIssueType.RELATIVE_IMPORT
        assert issues[1].issue_type == ImportIssueType.IMPLICIT_RELATIVE
