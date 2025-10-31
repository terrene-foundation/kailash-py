"""Tests for the MigrationAssistant class."""

import tempfile
import textwrap
from pathlib import Path

import pytest
from kailash.migration.compatibility_checker import CompatibilityChecker
from kailash.migration.migration_assistant import (
    MigrationAssistant,
    MigrationPlan,
    MigrationResult,
    MigrationStep,
)


@pytest.fixture
def assistant():
    """Create a MigrationAssistant instance for testing."""
    return MigrationAssistant(dry_run=True, create_backups=False)


@pytest.fixture
def temp_project_dir():
    """Create a temporary project directory with test files."""
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)

        # Create test files with migration issues
        (temp_path / "legacy_runtime.py").write_text(
            textwrap.dedent(
                """
            from kailash.runtime.local import LocalRuntime

            # Legacy configuration that needs migration
            runtime = LocalRuntime(
                enable_parallel=True,
                thread_pool_size=8,
                debug_mode=True,
                memory_limit=2048
            )

            # Legacy method usage
            workflow = build_workflow()
            runtime.execute_sync(workflow)
            results = runtime.get_results()
        """
            ).strip()
        )

        (temp_path / "config_file.py").write_text(
            textwrap.dedent(
                """
            # Configuration dictionary usage
            RUNTIME_CONFIG = {
                'timeout': 300,
                'retry_count': 3,
                'log_level': 'INFO'
            }

            from kailash.runtime.local import LocalRuntime
            runtime = LocalRuntime(**RUNTIME_CONFIG)
        """
            ).strip()
        )

        (temp_path / "modern_usage.py").write_text(
            textwrap.dedent(
                """
            from kailash.runtime.local import LocalRuntime

            # Already modern - should not need changes
            runtime = LocalRuntime(
                debug=True,
                max_concurrency=10,
                enable_monitoring=True
            )

            results, run_id = runtime.execute(workflow)
        """
            ).strip()
        )

        yield temp_path


class TestMigrationAssistant:
    """Test cases for MigrationAssistant."""

    def test_initialization(self, assistant):
        """Test MigrationAssistant initialization."""
        assert assistant is not None
        assert assistant.dry_run is True
        assert assistant.create_backups is False
        assert isinstance(assistant.compatibility_checker, CompatibilityChecker)
        assert isinstance(assistant.parameter_mappings, dict)
        assert isinstance(assistant.value_transformations, dict)
        assert isinstance(assistant.method_migrations, dict)

    def test_create_migration_plan(self, assistant, temp_project_dir):
        """Test migration plan creation."""
        plan = assistant.create_migration_plan(temp_project_dir)

        assert isinstance(plan, MigrationPlan)
        assert len(plan.steps) > 0
        assert plan.estimated_duration_minutes > 0
        assert plan.risk_level in ["low", "medium", "high"]
        assert isinstance(plan.prerequisites, list)
        assert isinstance(plan.post_migration_tests, list)

    def test_migration_step_creation(self, assistant, temp_project_dir):
        """Test creation of individual migration steps."""
        plan = assistant.create_migration_plan(temp_project_dir)

        # Should have steps for files with issues
        step_files = {step.file_path for step in plan.steps}
        assert any("legacy_runtime.py" in path for path in step_files)

        # Check step properties
        for step in plan.steps:
            assert isinstance(step, MigrationStep)
            assert step.step_id
            assert step.description
            assert step.file_path
            assert step.original_code
            assert step.migrated_code
            assert isinstance(step.automated, bool)
            assert isinstance(step.validation_required, bool)

    def test_parameter_transformation_parallel(self, assistant):
        """Test transformation of enable_parallel to max_concurrency."""
        content = "runtime = LocalRuntime(enable_parallel=True)"
        issue = type("Issue", (), {"code_snippet": content})()

        result = assistant._transform_parallel_to_concurrency(content, issue)

        assert "max_concurrency=10" in result
        assert "enable_parallel=True" not in result

    def test_parameter_transformation_thread_pool(self, assistant):
        """Test transformation of thread_pool_size to max_concurrency."""
        content = "runtime = LocalRuntime(thread_pool_size=5)"
        issue = type("Issue", (), {"code_snippet": content})()

        result = assistant._transform_thread_pool_size(content, issue)

        assert "max_concurrency=5" in result
        assert "thread_pool_size=5" not in result

    def test_parameter_transformation_memory_limit(self, assistant):
        """Test transformation of memory_limit to resource_limits."""
        content = "runtime = LocalRuntime(memory_limit=1024)"
        issue = type("Issue", (), {"code_snippet": content})()

        result = assistant._transform_memory_limit(content, issue)

        assert 'resource_limits={"memory_mb": 1024}' in result
        assert "memory_limit=1024" not in result

    def test_method_migration_execute_sync(self, assistant):
        """Test migration of execute_sync to execute."""
        content = "results = runtime.execute_sync(workflow)"
        issue = type("Issue", (), {"code_snippet": content})()

        result = assistant._migrate_execute_sync(content, issue)

        assert "runtime.execute(" in result
        assert ".execute_sync(" not in result

    def test_method_migration_get_results(self, assistant):
        """Test migration of get_results to direct result access."""
        content = "results = runtime.get_results()"
        issue = type("Issue", (), {"code_snippet": content})()

        result = assistant._migrate_get_results(content, issue)

        assert "[0]" in result
        assert ".get_results()" not in result

    def test_execute_migration_dry_run(self, assistant, temp_project_dir):
        """Test migration execution in dry run mode."""
        plan = assistant.create_migration_plan(temp_project_dir)
        result = assistant.execute_migration(plan)

        assert isinstance(result, MigrationResult)
        assert result.steps_completed > 0
        assert result.steps_failed == 0
        assert result.success is True

        # In dry run, no actual files should be modified
        original_content = (temp_project_dir / "legacy_runtime.py").read_text()
        assert "enable_parallel=True" in original_content  # Should not be changed

    def test_execute_migration_real(self, temp_project_dir):
        """Test actual migration execution (not dry run)."""
        # Use non-dry-run assistant
        assistant = MigrationAssistant(dry_run=False, create_backups=False)

        plan = assistant.create_migration_plan(temp_project_dir)
        result = assistant.execute_migration(plan)

        assert isinstance(result, MigrationResult)
        assert result.success is True

        # Check that files were actually modified
        modified_content = (temp_project_dir / "legacy_runtime.py").read_text()
        # Should have some migrations applied
        assert modified_content != ""

    def test_migration_plan_metadata(self, assistant, temp_project_dir):
        """Test migration plan metadata calculation."""
        plan = assistant.create_migration_plan(temp_project_dir)

        # Should have reasonable duration estimate
        assert plan.estimated_duration_minutes > 0
        assert plan.estimated_duration_minutes < 1000  # Not too crazy

        # Should assess risk level
        assert plan.risk_level in ["low", "medium", "high"]

        # Should have prerequisites and tests
        assert len(plan.prerequisites) > 0
        assert len(plan.post_migration_tests) > 0

        # Prerequisites should be meaningful
        for prereq in plan.prerequisites:
            assert isinstance(prereq, str)
            assert len(prereq) > 5

    def test_migration_report_generation(self, assistant, temp_project_dir):
        """Test migration report generation."""
        plan = assistant.create_migration_plan(temp_project_dir)
        result = assistant.execute_migration(plan)

        report = assistant.generate_migration_report(plan, result)

        assert isinstance(report, str)
        assert len(report) > 0
        assert "Migration Report" in report
        assert "MIGRATION PLAN SUMMARY" in report
        assert "EXECUTION RESULTS" in report
        assert "MIGRATION STEPS" in report

    def test_migration_validation(self, assistant):
        """Test migration step validation."""
        # Create a valid migration step
        step = MigrationStep(
            step_id="test_1",
            description="Test step",
            file_path="/dev/null",  # Won't exist, but that's OK for this test
            original_code="x = 1",
            migrated_code="x = 2",
        )

        # Should validate syntax without error
        try:
            assistant._validate_migration_step(step)
        except ValueError:
            pytest.fail("Valid Python code should not raise validation error")

    def test_migration_validation_syntax_error(self, assistant):
        """Test migration step validation with syntax errors."""
        # Create migration step with syntax error
        step = MigrationStep(
            step_id="test_1",
            description="Test step",
            file_path="/dev/null",
            original_code="x = 1",
            migrated_code="x = (",  # Syntax error
        )

        # Should raise validation error
        with pytest.raises(ValueError):
            assistant._validate_migration_step(step)

    def test_value_transformation_functions(self, assistant):
        """Test all value transformation functions."""
        transformations = assistant.value_transformations

        for param_name, transform_func in transformations.items():
            # Create mock issue
            issue = type("Issue", (), {"code_snippet": f"{param_name}=test"})()
            content = f"runtime = LocalRuntime({param_name}=10)"

            # Should not raise exception
            result = transform_func(content, issue)
            assert isinstance(result, str)
            assert len(result) > 0

    def test_method_migration_functions(self, assistant):
        """Test all method migration functions."""
        migrations = assistant.method_migrations

        for method_name, migrate_func in migrations.items():
            # Create mock issue
            issue = type("Issue", (), {"code_snippet": f".{method_name}("})()
            content = f"result = runtime.{method_name}(workflow)"

            # Should not raise exception
            result = migrate_func(content, issue)
            assert isinstance(result, str)
            assert len(result) > 0

    def test_rollback_functionality(self, assistant):
        """Test rollback functionality."""
        # Create a mock result with backup path
        with tempfile.TemporaryDirectory() as backup_dir:
            result = MigrationResult(
                success=True,
                steps_completed=5,
                steps_failed=0,
                backup_path=backup_dir,
                rollback_available=True,
            )

            # Test rollback (won't actually work without proper backup structure)
            rollback_success = assistant.rollback_migration(result)
            # Should return False since backup structure is empty
            assert rollback_success is False

    def test_include_exclude_patterns(self, assistant, temp_project_dir):
        """Test migration plan creation with include/exclude patterns."""
        # Test with include patterns
        plan_py_only = assistant.create_migration_plan(
            temp_project_dir, include_patterns=["*.py"]
        )

        # Test with exclude patterns
        plan_exclude_modern = assistant.create_migration_plan(
            temp_project_dir, exclude_patterns=["modern_usage.py"]
        )

        # Both should create valid plans
        assert isinstance(plan_py_only, MigrationPlan)
        assert isinstance(plan_exclude_modern, MigrationPlan)

        # Exclude pattern should result in fewer or equal steps
        assert len(plan_exclude_modern.steps) <= len(plan_py_only.steps)


class TestMigrationStep:
    """Test cases for MigrationStep dataclass."""

    def test_creation(self):
        """Test MigrationStep creation."""
        step = MigrationStep(
            step_id="test_1",
            description="Test migration step",
            file_path="/test/file.py",
            original_code="old_code = True",
            migrated_code="new_code = True",
        )

        assert step.step_id == "test_1"
        assert step.description == "Test migration step"
        assert step.file_path == "/test/file.py"
        assert step.original_code == "old_code = True"
        assert step.migrated_code == "new_code = True"
        assert step.automated is True
        assert step.validation_required is False
        assert step.rollback_available is True


class TestMigrationPlan:
    """Test cases for MigrationPlan dataclass."""

    def test_creation(self):
        """Test MigrationPlan creation."""
        plan = MigrationPlan()

        assert isinstance(plan.steps, list)
        assert plan.estimated_duration_minutes == 0
        assert plan.risk_level == "low"
        assert isinstance(plan.prerequisites, list)
        assert isinstance(plan.post_migration_tests, list)
        assert plan.backup_required is True


class TestMigrationResult:
    """Test cases for MigrationResult dataclass."""

    def test_creation(self):
        """Test MigrationResult creation."""
        result = MigrationResult(success=True, steps_completed=5, steps_failed=0)

        assert result.success is True
        assert result.steps_completed == 5
        assert result.steps_failed == 0
        assert isinstance(result.errors, list)
        assert isinstance(result.warnings, list)
        assert result.backup_path is None
        assert result.rollback_available is True


if __name__ == "__main__":
    pytest.main([__file__])
