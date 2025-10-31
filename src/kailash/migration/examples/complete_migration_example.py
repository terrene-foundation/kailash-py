#!/usr/bin/env python3
"""Complete LocalRuntime migration example.

This script demonstrates the complete migration workflow using all available
migration tools and utilities. It serves as both a practical example and
a comprehensive test of the migration toolchain.
"""

import argparse
import tempfile
import textwrap
from pathlib import Path

from kailash.migration import (
    CompatibilityChecker,
    ConfigurationValidator,
    MigrationAssistant,
    MigrationDocGenerator,
    PerformanceComparator,
    RegressionDetector,
)
from kailash.workflow.builder import WorkflowBuilder


def create_sample_project(project_path: Path) -> None:
    """Create a sample project with various migration scenarios."""
    project_path.mkdir(exist_ok=True)

    print(f"Creating sample project in: {project_path}")

    # Legacy application file
    (project_path / "legacy_app.py").write_text(
        textwrap.dedent(
            """
        from kailash.runtime.local import LocalRuntime
        from kailash.workflow.builder import WorkflowBuilder

        class LegacyWorkflowRunner:
            def __init__(self):
                # Legacy configuration patterns
                self.runtime = LocalRuntime(
                    enable_parallel=True,
                    thread_pool_size=12,
                    debug_mode=False,
                    memory_limit=2048,
                    timeout=600,
                    retry_count=3
                )

            def run_data_processing(self, input_data):
                # Create workflow
                workflow = WorkflowBuilder()

                # Data validation step
                workflow.add_node("PythonCodeNode", "validate", {
                    "code": '''
        if not input_data:
            raise ValueError("Input data is required")
        result = {"valid": True, "data": input_data}
        ''',
                    "input_mapping": {"input_data": "input_data"},
                    "output_key": "validated_data"
                })

                # Processing step
                workflow.add_node("PythonCodeNode", "process", {
                    "code": '''
        import json
        data = validated_data["data"]
        processed = {
            "items_count": len(data) if isinstance(data, list) else 1,
            "processed_at": "2024-01-01T00:00:00Z",
            "status": "completed"
        }
        result = processed
        ''',
                    "input_mapping": {"validated_data": "validate.validated_data"},
                    "output_key": "processed_result"
                })

                # Legacy execution pattern
                self.runtime.execute_sync(workflow.build(), parameters={"input_data": input_data})
                return self.runtime.get_results()

            def cleanup(self):
                # Manual cleanup (legacy pattern)
                self.runtime.set_context(None)
    """
        ).strip()
    )

    # Configuration file with multiple legacy patterns
    (project_path / "config.py").write_text(
        textwrap.dedent(
            """
        # Legacy configuration patterns

        DEVELOPMENT_CONFIG = {
            'debug_mode': True,
            'enable_parallel': False,
            'memory_limit': 1024,
            'log_level': 'DEBUG'
        }

        PRODUCTION_CONFIG = {
            'enable_parallel': True,
            'thread_pool_size': 32,
            'memory_limit': 8192,
            'timeout': 1800,
            'retry_count': 5,
            'cache_enabled': True
        }

        TESTING_CONFIG = {
            'debug_mode': True,
            'thread_pool_size': 2,
            'timeout': 300
        }

        def get_runtime_config(environment='development'):
            configs = {
                'development': DEVELOPMENT_CONFIG,
                'production': PRODUCTION_CONFIG,
                'testing': TESTING_CONFIG
            }
            return configs.get(environment, DEVELOPMENT_CONFIG)
    """
        ).strip()
    )

    # Already modernized file (should not be changed)
    (project_path / "modern_service.py").write_text(
        textwrap.dedent(
            """
        from kailash.runtime.local import LocalRuntime
        from kailash.access_control import UserContext
        from kailash.workflow.builder import WorkflowBuilder

        class ModernWorkflowService:
            def __init__(self, user_id: str):
                # Modern configuration
                self.user_context = UserContext(
                    user_id=user_id,
                    roles=["data_processor", "workflow_admin"]
                )

                self.runtime = LocalRuntime(
                    debug=False,
                    max_concurrency=20,
                    enable_monitoring=True,
                    enable_security=True,
                    enable_audit=True,
                    user_context=self.user_context,
                    resource_limits={
                        'memory_mb': 4096,
                        'timeout_seconds': 1200
                    },
                    retry_policy_config={
                        'max_retries': 3,
                        'backoff_factor': 2.0
                    }
                )

            def execute_workflow(self, workflow):
                # Modern execution pattern
                results, run_id = self.runtime.execute(workflow)
                return {
                    'results': results,
                    'run_id': run_id,
                    'user': self.user_context.user_id
                }

            def create_analytics_workflow(self):
                workflow = WorkflowBuilder()

                workflow.add_node("PythonCodeNode", "analyze", {
                    "code": '''
        import datetime
        result = {
            "analysis_timestamp": datetime.datetime.now().isoformat(),
            "metrics": {
                "total_processed": 100,
                "success_rate": 0.95,
                "avg_duration_ms": 250
            }
        }
        ''',
                    "output_key": "analytics"
                })

                return workflow.build()
    """
        ).strip()
    )

    # Test file
    (project_path / "test_workflows.py").write_text(
        textwrap.dedent(
            """
        import pytest
        from legacy_app import LegacyWorkflowRunner
        from modern_service import ModernWorkflowService

        def test_legacy_workflow():
            runner = LegacyWorkflowRunner()
            result = runner.run_data_processing(["item1", "item2", "item3"])
            assert result is not None
            runner.cleanup()

        def test_modern_workflow():
            service = ModernWorkflowService("test_user")
            workflow = service.create_analytics_workflow()
            result = service.execute_workflow(workflow)

            assert result is not None
            assert "results" in result
            assert "run_id" in result
            assert "user" in result
            assert result["user"] == "test_user"

        def test_data_validation():
            runner = LegacyWorkflowRunner()

            # Test with valid data
            result = runner.run_data_processing(["valid", "data"])
            assert result is not None

            # Test with empty data (should handle gracefully)
            try:
                runner.run_data_processing([])
                # Should either work or fail gracefully
            except Exception as e:
                assert "required" in str(e).lower()

            runner.cleanup()
    """
        ).strip()
    )

    # README file
    (project_path / "README.md").write_text(
        textwrap.dedent(
            """
        # Sample Migration Project

        This is a sample project demonstrating LocalRuntime migration patterns.

        ## Files

        - `legacy_app.py` - Contains legacy LocalRuntime usage patterns
        - `config.py` - Configuration files with deprecated parameters
        - `modern_service.py` - Already modernized code (should not be changed)
        - `test_workflows.py` - Test cases for both legacy and modern patterns

        ## Migration Notes

        This project contains various migration scenarios:

        1. **Legacy Configuration**: Old parameter names and patterns
        2. **Legacy Execution**: `execute_sync()` and `get_results()` patterns
        3. **Manual Resource Management**: Manual cleanup patterns
        4. **Mixed Patterns**: Some modern and some legacy code

        The migration tools should identify and fix these issues automatically.
    """
        ).strip()
    )

    print("✅ Sample project created successfully")


def run_complete_migration_example(project_path: Path, output_dir: Path) -> None:
    """Run the complete migration example."""
    print("\n" + "=" * 60)
    print("LOCALRUNTIME MIGRATION TOOLCHAIN EXAMPLE")
    print("=" * 60)

    output_dir.mkdir(exist_ok=True)

    # Step 1: Compatibility Analysis
    print("\n🔍 Step 1: Compatibility Analysis")
    print("-" * 35)

    checker = CompatibilityChecker()
    analysis_result = checker.analyze_codebase(project_path)

    print(f"Files analyzed: {analysis_result.total_files_analyzed}")
    print(f"Issues found: {len(analysis_result.issues)}")
    print(f"Migration complexity: {analysis_result.migration_complexity}")
    print(f"Estimated effort: {analysis_result.estimated_effort_days} days")

    # Save analysis report
    analysis_report = checker.generate_report(analysis_result, "markdown")
    (output_dir / "01_compatibility_analysis.md").write_text(analysis_report)
    print("📄 Analysis report saved to: 01_compatibility_analysis.md")

    # Step 2: Configuration Validation
    print("\n⚙️ Step 2: Configuration Validation")
    print("-" * 37)

    validator = ConfigurationValidator()

    # Test various configurations
    configs_to_test = [
        (
            "Legacy Development",
            {"debug_mode": True, "enable_parallel": False, "memory_limit": 1024},
        ),
        (
            "Legacy Production",
            {
                "enable_parallel": True,
                "thread_pool_size": 32,
                "memory_limit": 8192,
                "timeout": 1800,
                "retry_count": 5,
            },
        ),
        (
            "Modern Configuration",
            {
                "debug": True,
                "max_concurrency": 10,
                "enable_monitoring": True,
                "resource_limits": {"memory_mb": 2048},
            },
        ),
    ]

    validation_reports = []
    for config_name, config in configs_to_test:
        print(f"\nValidating {config_name} configuration:")
        validation_result = validator.validate_configuration(config)

        print(f"  Valid: {'Yes' if validation_result.valid else 'No'}")
        print(f"  Issues: {len(validation_result.issues)}")
        print(f"  Security score: {validation_result.security_score}/100")
        print(f"  Performance score: {validation_result.performance_score}/100")

        # Save validation report
        config_report = validator.generate_validation_report(
            validation_result, "markdown"
        )
        safe_name = config_name.lower().replace(" ", "_")
        report_file = output_dir / f"02_validation_{safe_name}.md"
        report_file.write_text(
            f"# {config_name} Configuration Validation\n\n{config_report}"
        )

        validation_reports.append((config_name, validation_result))

    print("📄 Configuration validation reports saved")

    # Step 3: Migration Planning and Execution
    print("\n🚀 Step 3: Migration Planning and Execution")
    print("-" * 45)

    assistant = MigrationAssistant(dry_run=True, create_backups=True)
    migration_plan = assistant.create_migration_plan(project_path)

    print(f"Migration steps: {len(migration_plan.steps)}")
    print(f"Estimated duration: {migration_plan.estimated_duration_minutes} minutes")
    print(f"Risk level: {migration_plan.risk_level}")

    # Execute migration (dry run)
    migration_result = assistant.execute_migration(migration_plan)

    print(f"Migration success: {'Yes' if migration_result.success else 'No'}")
    print(f"Steps completed: {migration_result.steps_completed}")
    print(f"Steps failed: {migration_result.steps_failed}")

    # Save migration report
    migration_report = assistant.generate_migration_report(
        migration_plan, migration_result
    )
    (output_dir / "03_migration_execution.md").write_text(migration_report)
    print("📄 Migration report saved to: 03_migration_execution.md")

    # Step 4: Performance Analysis
    print("\n📊 Step 4: Performance Analysis")
    print("-" * 33)

    comparator = PerformanceComparator(sample_size=2, warmup_runs=1)

    # Compare legacy vs modern configurations
    legacy_config = {"debug": True, "max_concurrency": 1}
    modern_config = {
        "debug": True,
        "max_concurrency": 8,
        "enable_monitoring": True,
        "persistent_mode": True,
    }

    try:
        # Create test workflows for performance comparison
        simple_workflow = WorkflowBuilder()
        simple_workflow.add_node(
            "PythonCodeNode",
            "perf_test",
            {
                "code": "result = sum(i*i for i in range(1000))",
                "output_key": "sum_squares",
            },
        )
        test_workflows = [("performance_test", simple_workflow.build())]

        print("Comparing legacy vs modern configurations...")
        performance_report = comparator.compare_configurations(
            legacy_config, modern_config, test_workflows
        )

        print(
            f"Overall performance change: {performance_report.overall_change_percentage:+.1f}%"
        )
        print(
            f"Performance status: {'Improvement' if performance_report.overall_improvement else 'Regression'}"
        )
        print(f"Risk assessment: {performance_report.risk_assessment}")

        # Save performance report
        perf_report = comparator.generate_performance_report(
            performance_report, "markdown"
        )
        (output_dir / "04_performance_analysis.md").write_text(perf_report)
        print("📄 Performance report saved to: 04_performance_analysis.md")

    except Exception as e:
        print(f"⚠️ Performance analysis skipped (requires full LocalRuntime): {e}")
        print("   In a real migration, this would provide detailed performance metrics")

    # Step 5: Regression Detection
    print("\n🔍 Step 5: Regression Detection")
    print("-" * 32)

    try:
        detector = RegressionDetector(
            baseline_path=output_dir / "baseline.json", parallel_tests=False
        )

        # Create baseline
        print("Creating performance baseline...")
        baseline_config = {"debug": True, "max_concurrency": 2}

        simple_workflow = WorkflowBuilder()
        simple_workflow.add_node(
            "PythonCodeNode",
            "regression_test",
            {"code": "result = 'regression_test_passed'", "output_key": "test_result"},
        )
        test_workflows = [("regression_check", simple_workflow.build())]

        baselines = detector.create_baseline(baseline_config, test_workflows)
        print(f"Created {len(baselines)} baseline snapshots")

        # Test for regressions
        print("Checking for regressions...")
        modified_config = {"debug": True, "max_concurrency": 4}
        regression_report = detector.detect_regressions(modified_config, test_workflows)

        print(f"Tests run: {regression_report.total_tests}")
        print(f"Passed: {regression_report.passed_tests}")
        print(f"Failed: {regression_report.failed_tests}")
        print(f"Regression issues: {len(regression_report.regression_issues)}")
        print(f"Overall status: {regression_report.overall_status}")

        # Save regression report
        regression_text = detector.generate_regression_report(
            regression_report, "markdown"
        )
        (output_dir / "05_regression_detection.md").write_text(regression_text)
        print("📄 Regression report saved to: 05_regression_detection.md")

    except Exception as e:
        print(f"⚠️ Regression detection skipped (requires full LocalRuntime): {e}")
        print(
            "   In a real migration, this would detect performance and functional regressions"
        )

    # Step 6: Documentation Generation
    print("\n📚 Step 6: Documentation Generation")
    print("-" * 36)

    doc_generator = MigrationDocGenerator()

    # Generate comprehensive migration guide
    migration_guide = doc_generator.generate_migration_guide(
        analysis_result=analysis_result,
        migration_plan=migration_plan,
        migration_result=migration_result,
        validation_result=validation_reports[0][1],  # Use first validation result
        scenario="enterprise",
        audience="developer",
    )

    print(f"Generated migration guide with {len(migration_guide.sections)} sections")

    # Export guide as markdown
    guide_path = output_dir / "06_complete_migration_guide.md"
    doc_generator.export_guide(migration_guide, guide_path, "markdown")
    print("📄 Complete migration guide saved to: 06_complete_migration_guide.md")

    # Generate audience-specific guides
    audiences = ["developer", "admin", "architect"]
    for audience in audiences:
        audience_guide = doc_generator.generate_migration_guide(
            analysis_result=analysis_result,
            migration_plan=migration_plan,
            scenario="standard",
            audience=audience,
        )

        audience_path = output_dir / f"06_migration_guide_{audience}.md"
        doc_generator.export_guide(audience_guide, audience_path, "markdown")

    print("📄 Audience-specific guides generated")

    # Step 7: Summary Report
    print("\n📋 Step 7: Summary Report")
    print("-" * 25)

    summary_report = generate_summary_report(
        analysis_result, migration_plan, migration_result, validation_reports
    )

    (output_dir / "00_migration_summary.md").write_text(summary_report)
    print("📄 Migration summary saved to: 00_migration_summary.md")

    print("\n" + "=" * 60)
    print("MIGRATION ANALYSIS COMPLETE")
    print("=" * 60)
    print(f"\nAll reports have been saved to: {output_dir}")
    print("\nFiles generated:")
    for report_file in sorted(output_dir.glob("*.md")):
        print(f"  📄 {report_file.name}")

    print("\n✅ Complete migration toolchain example finished successfully!")


def generate_summary_report(
    analysis_result, migration_plan, migration_result, validation_reports
):
    """Generate a comprehensive summary report."""

    report_lines = [
        "# LocalRuntime Migration Summary",
        "",
        f"*Generated: {migration_result.backup_path or 'N/A'}*",
        "",
        "## Executive Summary",
        "",
        f"- **Files Analyzed**: {analysis_result.total_files_analyzed}",
        f"- **Issues Identified**: {len(analysis_result.issues)}",
        f"- **Migration Complexity**: {analysis_result.migration_complexity.title()}",
        f"- **Estimated Effort**: {analysis_result.estimated_effort_days} days",
        f"- **Migration Success**: {'Yes' if migration_result.success else 'No'}",
        f"- **Steps Completed**: {migration_result.steps_completed}/{len(migration_plan.steps)}",
        "",
        "## Issues Breakdown",
        "",
        f"- Critical Issues: {analysis_result.summary.get('critical_issues', 0)}",
        f"- High Priority: {analysis_result.summary.get('high_issues', 0)}",
        f"- Medium Priority: {analysis_result.summary.get('medium_issues', 0)}",
        f"- Low Priority: {analysis_result.summary.get('low_issues', 0)}",
        f"- Breaking Changes: {analysis_result.summary.get('breaking_changes', 0)}",
        f"- Automated Fixes: {analysis_result.summary.get('automated_fixes', 0)}",
        "",
        "## Configuration Analysis",
        "",
    ]

    for config_name, validation_result in validation_reports:
        report_lines.extend(
            [
                f"### {config_name}",
                "",
                f"- **Valid**: {'Yes' if validation_result.valid else 'No'}",
                f"- **Issues**: {len(validation_result.issues)}",
                f"- **Security Score**: {validation_result.security_score}/100",
                f"- **Performance Score**: {validation_result.performance_score}/100",
                f"- **Enterprise Readiness**: {validation_result.enterprise_readiness}/100",
                "",
            ]
        )

    report_lines.extend(
        [
            "## Migration Plan",
            "",
            f"- **Total Steps**: {len(migration_plan.steps)}",
            f"- **Estimated Duration**: {migration_plan.estimated_duration_minutes} minutes",
            f"- **Risk Level**: {migration_plan.risk_level.title()}",
            f"- **Prerequisites**: {len(migration_plan.prerequisites)}",
            f"- **Post-Migration Tests**: {len(migration_plan.post_migration_tests)}",
            "",
            "## Recommendations",
            "",
        ]
    )

    # Add recommendations based on analysis
    if analysis_result.summary.get("critical_issues", 0) > 0:
        report_lines.append(
            "🚨 **CRITICAL**: Address critical issues before proceeding with migration"
        )
    elif analysis_result.summary.get("breaking_changes", 0) > 0:
        report_lines.append(
            "⚠️ **HIGH PRIORITY**: Review breaking changes and update code accordingly"
        )
    elif migration_result.success:
        report_lines.append("✅ **SUCCESS**: Migration completed successfully")
    else:
        report_lines.append(
            "❌ **FAILED**: Migration encountered errors - review and retry"
        )

    report_lines.extend(
        [
            "",
            "## Next Steps",
            "",
            "1. Review detailed analysis reports",
            "2. Address critical and high-priority issues",
            "3. Execute migration plan (remove dry-run mode)",
            "4. Run comprehensive tests",
            "5. Monitor performance post-migration",
            "",
            "## Report Files",
            "",
            "- `01_compatibility_analysis.md` - Detailed compatibility analysis",
            "- `02_validation_*.md` - Configuration validation reports",
            "- `03_migration_execution.md` - Migration execution details",
            "- `04_performance_analysis.md` - Performance comparison (if available)",
            "- `05_regression_detection.md` - Regression analysis (if available)",
            "- `06_complete_migration_guide.md` - Comprehensive migration guide",
            "- `06_migration_guide_*.md` - Audience-specific guides",
        ]
    )

    return "\n".join(report_lines)


def main():
    """Main function for the migration example script."""
    parser = argparse.ArgumentParser(
        description="LocalRuntime Migration Toolchain Example"
    )
    parser.add_argument(
        "--project-path",
        type=Path,
        help="Path to existing project (if not provided, creates sample project)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("migration_reports"),
        help="Directory for output reports (default: migration_reports)",
    )
    parser.add_argument(
        "--create-sample",
        action="store_true",
        help="Create a sample project for demonstration",
    )

    args = parser.parse_args()

    try:
        if args.create_sample or not args.project_path:
            # Create sample project
            with tempfile.TemporaryDirectory() as temp_dir:
                project_path = Path(temp_dir) / "sample_project"
                create_sample_project(project_path)
                run_complete_migration_example(project_path, args.output_dir)
        else:
            # Use existing project
            if not args.project_path.exists():
                print(f"❌ Error: Project path does not exist: {args.project_path}")
                return 1

            run_complete_migration_example(args.project_path, args.output_dir)

        return 0

    except Exception as e:
        print(f"❌ Error during migration analysis: {e}")
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit(main())
