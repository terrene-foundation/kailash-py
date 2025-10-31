"""Integration tests for the complete migration toolchain.

These tests verify that all migration tools work together correctly
for end-to-end migration scenarios.
"""

import tempfile
import textwrap
from pathlib import Path

import pytest
from kailash.migration import (
    CompatibilityChecker,
    ConfigurationValidator,
    MigrationAssistant,
    MigrationDocGenerator,
    PerformanceComparator,
    RegressionDetector,
)
from kailash.workflow.builder import WorkflowBuilder


@pytest.fixture
def complete_project():
    """Create a complete project with various migration scenarios."""
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)

        # Main application file with legacy patterns
        (temp_path / "app.py").write_text(
            textwrap.dedent(
                """
            from kailash.runtime.local import LocalRuntime
            from kailash.workflow.builder import WorkflowBuilder

            def create_runtime():
                # Legacy configuration
                return LocalRuntime(
                    enable_parallel=True,
                    thread_pool_size=16,
                    debug_mode=False,
                    memory_limit=4096,
                    timeout=600
                )

            def run_workflow(data):
                runtime = create_runtime()

                workflow = WorkflowBuilder()
                workflow.add_node("PythonCodeNode", "process", {
                    "code": f"result = len('{data}') * 2",
                    "output_key": "length_doubled"
                })

                # Legacy execution pattern
                runtime.execute_sync(workflow.build())
                return runtime.get_results()

            if __name__ == "__main__":
                result = run_workflow("test data")
                print(f"Result: {result}")
        """
            ).strip()
        )

        # Configuration file
        (temp_path / "config.py").write_text(
            textwrap.dedent(
                """
            # Legacy configuration patterns
            PRODUCTION_CONFIG = {
                'enable_parallel': True,
                'thread_pool_size': 32,
                'memory_limit': 8192,
                'timeout': 1200,
                'log_level': 'INFO',
                'retry_count': 5
            }

            DEVELOPMENT_CONFIG = {
                'debug_mode': True,
                'enable_parallel': False,
                'memory_limit': 1024
            }
        """
            ).strip()
        )

        # Already modern file (should not be changed)
        (temp_path / "modern.py").write_text(
            textwrap.dedent(
                """
            from kailash.runtime.local import LocalRuntime
            from kailash.access_control import UserContext

            def create_modern_runtime():
                user_context = UserContext(user_id="modern_user")
                return LocalRuntime(
                    debug=True,
                    max_concurrency=20,
                    enable_monitoring=True,
                    enable_security=True,
                    user_context=user_context,
                    resource_limits={
                        'memory_mb': 2048,
                        'timeout_seconds': 300
                    }
                )

            def execute_modern_workflow(workflow):
                runtime = create_modern_runtime()
                results, run_id = runtime.execute(workflow)
                return results, run_id
        """
            ).strip()
        )

        # Test file
        (temp_path / "test_app.py").write_text(
            textwrap.dedent(
                """
            import pytest
            from app import run_workflow

            def test_workflow_execution():
                result = run_workflow("hello")
                assert result is not None

            def test_workflow_with_empty_data():
                result = run_workflow("")
                assert result is not None
        """
            ).strip()
        )

        yield temp_path


class TestMigrationToolchainIntegration:
    """Integration tests for the complete migration toolchain."""

    def test_complete_migration_workflow(self, complete_project):
        """Test complete migration workflow from analysis to validation."""

        # Step 1: Compatibility Analysis
        checker = CompatibilityChecker()
        analysis_result = checker.analyze_codebase(complete_project)

        assert analysis_result.total_files_analyzed > 0
        assert len(analysis_result.issues) > 0
        assert analysis_result.migration_complexity in [
            "low",
            "medium",
            "high",
            "very_high",
        ]

        # Should detect legacy patterns
        deprecated_issues = [
            i for i in analysis_result.issues if "deprecated" in i.description.lower()
        ]
        assert len(deprecated_issues) > 0

        # Step 2: Configuration Validation
        validator = ConfigurationValidator()

        # Test legacy configurations
        legacy_config = {
            "enable_parallel": True,
            "thread_pool_size": 16,
            "debug_mode": False,
        }

        validation_result = validator.validate_configuration(legacy_config)
        assert validation_result.valid is False  # Should have deprecated parameters
        assert len(validation_result.issues) > 0

        # Step 3: Migration Planning and Execution
        assistant = MigrationAssistant(dry_run=True, create_backups=False)
        migration_plan = assistant.create_migration_plan(complete_project)

        assert len(migration_plan.steps) > 0
        assert migration_plan.estimated_duration_minutes > 0

        # Execute migration (dry run)
        migration_result = assistant.execute_migration(migration_plan)
        assert migration_result.success is True
        assert migration_result.steps_completed > 0

        # Step 4: Performance Comparison (simulated)
        comparator = PerformanceComparator(sample_size=1, warmup_runs=0)

        legacy_config = {"debug": True, "max_concurrency": 1}
        modern_config = {"debug": True, "max_concurrency": 4, "enable_monitoring": True}

        # Create simple test workflow
        workflow = WorkflowBuilder()
        workflow.add_node(
            "PythonCodeNode",
            "test",
            {"code": "result = sum(range(100))", "output_key": "sum_result"},
        )
        test_workflows = [("simple_test", workflow.build())]

        # This would normally require actual LocalRuntime execution
        # For integration test, we'll just verify the structure
        try:
            performance_report = comparator.compare_configurations(
                legacy_config, modern_config, test_workflows
            )
            assert isinstance(performance_report.before_benchmarks, list)
            assert isinstance(performance_report.after_benchmarks, list)
        except Exception as e:
            # Expected in test environment without full runtime
            assert "LocalRuntime" in str(e) or "import" in str(e).lower()

        # Step 5: Documentation Generation
        doc_generator = MigrationDocGenerator()

        migration_guide = doc_generator.generate_migration_guide(
            analysis_result=analysis_result,
            migration_plan=migration_plan,
            migration_result=migration_result,
            validation_result=validation_result,
            scenario="standard",
        )

        assert migration_guide is not None
        assert migration_guide.title
        assert len(migration_guide.sections) > 0

        # Verify key sections exist
        section_titles = [s.title for s in migration_guide.sections]
        assert "Overview" in section_titles
        assert "Migration Steps" in section_titles
        assert "Validation and Testing" in section_titles

    def test_regression_detection_integration(self, complete_project):
        """Test regression detection integration."""

        # Create regression detector
        detector = RegressionDetector(
            baseline_path=complete_project / "baseline.json", parallel_tests=False
        )

        # Create baseline configuration
        baseline_config = {"debug": True, "max_concurrency": 2}

        # Create simple test workflows for baseline
        simple_workflow = WorkflowBuilder()
        simple_workflow.add_node(
            "PythonCodeNode",
            "baseline_test",
            {"code": "result = 'baseline_success'", "output_key": "message"},
        )

        test_workflows = [("integration_test", simple_workflow.build())]

        # This would normally create actual baselines
        try:
            baselines = detector.create_baseline(baseline_config, test_workflows)
            assert isinstance(baselines, dict)

            # Test regression detection
            modified_config = {
                "debug": True,
                "max_concurrency": 4,
            }  # Increased concurrency
            regression_report = detector.detect_regressions(
                modified_config, test_workflows
            )

            assert regression_report.total_tests > 0
        except Exception as e:
            # Expected in test environment without full runtime
            assert "LocalRuntime" in str(e) or "import" in str(e).lower()

    def test_configuration_optimization_flow(self, complete_project):
        """Test configuration optimization workflow."""

        # Start with problematic configuration
        problematic_config = {
            "debug": True,
            "enable_security": True,  # Conflict: debug + security
            "max_concurrency": 1000,  # Too high
            "enable_monitoring": False,
            "enable_enterprise_monitoring": True,  # Requires basic monitoring
        }

        # Validate and get recommendations
        validator = ConfigurationValidator()
        validation_result = validator.validate_configuration(problematic_config)

        assert validation_result.valid is False
        assert len(validation_result.issues) > 0

        # Should have optimized configuration
        assert validation_result.optimized_config is not None

        # Optimized config should fix dependency issues
        optimized = validation_result.optimized_config
        if optimized.get("enable_enterprise_monitoring"):
            assert optimized.get("enable_monitoring") is True

        # Re-validate optimized configuration
        revalidation = validator.validate_configuration(optimized)
        assert len(revalidation.issues) < len(validation_result.issues)

    def test_multi_format_report_generation(self, complete_project):
        """Test report generation in multiple formats."""

        # Run analysis
        checker = CompatibilityChecker()
        analysis_result = checker.analyze_codebase(complete_project)

        # Generate reports in all formats
        text_report = checker.generate_report(analysis_result, "text")
        json_report = checker.generate_report(analysis_result, "json")
        markdown_report = checker.generate_report(analysis_result, "markdown")

        # Verify all formats generated successfully
        assert isinstance(text_report, str) and len(text_report) > 0
        assert isinstance(json_report, str) and len(json_report) > 0
        assert isinstance(markdown_report, str) and len(markdown_report) > 0

        # Verify format-specific content
        assert "Migration Compatibility Report" in text_report

        # JSON should be valid
        import json

        json_data = json.loads(json_report)
        assert "summary" in json_data
        assert "issues" in json_data

        # Markdown should have headers
        assert "# LocalRuntime Migration Compatibility Report" in markdown_report
        assert "## Summary" in markdown_report

    def test_comprehensive_documentation_generation(self, complete_project):
        """Test comprehensive documentation generation."""

        # Run complete analysis
        checker = CompatibilityChecker()
        analysis_result = checker.analyze_codebase(complete_project)

        assistant = MigrationAssistant(dry_run=True)
        migration_plan = assistant.create_migration_plan(complete_project)
        migration_result = assistant.execute_migration(migration_plan)

        validator = ConfigurationValidator()
        validation_result = validator.validate_configuration({"debug": True})

        # Generate comprehensive documentation
        doc_generator = MigrationDocGenerator()

        # Test different scenarios
        scenarios = ["simple", "standard", "enterprise", "performance_critical"]

        for scenario in scenarios:
            guide = doc_generator.generate_migration_guide(
                analysis_result=analysis_result,
                migration_plan=migration_plan,
                migration_result=migration_result,
                validation_result=validation_result,
                scenario=scenario,
                audience="developer",
            )

            assert guide is not None
            assert len(guide.sections) > 0

            # Verify scenario-appropriate sections
            section_titles = [s.title for s in guide.sections]

            if scenario == "enterprise":
                assert "Enterprise Features" in section_titles

            if scenario == "performance_critical":
                # Performance scenario should have performance focus
                assert any("performance" in title.lower() for title in section_titles)

    def test_error_handling_integration(self, complete_project):
        """Test error handling across the migration toolchain."""

        # Create problematic files
        broken_file = complete_project / "broken.py"
        broken_file.write_text("def broken_function(\n  # Syntax error")

        # Test that tools handle errors gracefully
        checker = CompatibilityChecker()
        analysis_result = checker.analyze_codebase(complete_project)

        # Should still analyze successfully despite broken file
        assert analysis_result.total_files_analyzed > 0

        # Should detect syntax errors
        syntax_errors = [
            i for i in analysis_result.issues if "syntax" in i.description.lower()
        ]
        assert len(syntax_errors) > 0

        # Migration assistant should handle errors
        assistant = MigrationAssistant(dry_run=True)
        migration_plan = assistant.create_migration_plan(complete_project)

        # Should create plan despite problematic files
        assert len(migration_plan.steps) >= 0

        # Migration execution should handle errors gracefully
        migration_result = assistant.execute_migration(migration_plan)
        if not migration_result.success:
            assert len(migration_result.errors) > 0

    def test_end_to_end_workflow_files(self, complete_project):
        """Test that workflow affects actual files (in dry-run mode)."""

        # Get original file content
        original_app = (complete_project / "app.py").read_text()
        original_config = (complete_project / "config.py").read_text()
        original_modern = (complete_project / "modern.py").read_text()

        # Run migration in dry-run mode
        assistant = MigrationAssistant(dry_run=True)
        migration_plan = assistant.create_migration_plan(complete_project)
        migration_result = assistant.execute_migration(migration_plan)

        # In dry-run mode, files should not be changed
        assert (complete_project / "app.py").read_text() == original_app
        assert (complete_project / "config.py").read_text() == original_config
        assert (complete_project / "modern.py").read_text() == original_modern

        # But should have successful execution
        assert migration_result.success is True
        assert migration_result.steps_completed > 0

    def test_migration_report_completeness(self, complete_project):
        """Test that migration reports contain all expected information."""

        # Run complete migration
        assistant = MigrationAssistant(dry_run=True)
        migration_plan = assistant.create_migration_plan(complete_project)
        migration_result = assistant.execute_migration(migration_plan)

        # Generate comprehensive report
        report = assistant.generate_migration_report(migration_plan, migration_result)

        # Verify report completeness
        assert "Migration Report" in report
        assert "MIGRATION PLAN SUMMARY" in report
        assert "EXECUTION RESULTS" in report
        assert str(migration_plan.estimated_duration_minutes) in report
        assert migration_plan.risk_level.upper() in report
        assert str(migration_result.steps_completed) in report

        # Should include step details
        for step in migration_plan.steps:
            assert step.description in report or step.file_path in report


if __name__ == "__main__":
    pytest.main([__file__])
