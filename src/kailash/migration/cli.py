#!/usr/bin/env python3
"""Command-line interface for LocalRuntime migration tools.

This module provides a simple CLI for accessing all migration tools
and utilities from the command line.
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict

from .compatibility_checker import CompatibilityChecker
from .configuration_validator import ConfigurationValidator
from .documentation_generator import MigrationDocGenerator
from .migration_assistant import MigrationAssistant
from .performance_comparator import PerformanceComparator
from .regression_detector import RegressionDetector


def cmd_analyze(args):
    """Run compatibility analysis."""
    print("🔍 Running compatibility analysis...")

    checker = CompatibilityChecker()
    result = checker.analyze_codebase(
        args.path, include_patterns=args.include, exclude_patterns=args.exclude
    )

    if args.output:
        report = checker.generate_report(result, args.format)
        Path(args.output).write_text(report)
        print(f"📄 Analysis report saved to: {args.output}")
    else:
        print(checker.generate_report(result, "text"))


def cmd_validate(args):
    """Run configuration validation."""
    print("⚙️ Running configuration validation...")

    # Load configuration from file or command line
    if args.config_file:
        with open(args.config_file) as f:
            config = json.load(f)
    else:
        # Parse config from command line args
        config = {}
        if args.debug is not None:
            config["debug"] = args.debug
        if args.max_concurrency:
            config["max_concurrency"] = args.max_concurrency
        if args.enable_monitoring is not None:
            config["enable_monitoring"] = args.enable_monitoring
        if args.enable_security is not None:
            config["enable_security"] = args.enable_security

    validator = ConfigurationValidator()
    result = validator.validate_configuration(config)

    if args.output:
        report = validator.generate_validation_report(result, args.format)
        Path(args.output).write_text(report)
        print(f"📄 Validation report saved to: {args.output}")
    else:
        print(validator.generate_validation_report(result, "text"))


def cmd_migrate(args):
    """Run migration planning and execution."""
    print("🚀 Running migration planning...")

    assistant = MigrationAssistant(dry_run=args.dry_run, create_backups=args.backup)

    # Create migration plan
    plan = assistant.create_migration_plan(
        args.path, include_patterns=args.include, exclude_patterns=args.exclude
    )

    print(f"Created migration plan with {len(plan.steps)} steps")
    print(f"Estimated duration: {plan.estimated_duration_minutes} minutes")
    print(f"Risk level: {plan.risk_level}")

    if not args.plan_only:
        print("\n🔄 Executing migration...")
        result = assistant.execute_migration(plan)

        print(f"Migration {'successful' if result.success else 'failed'}")
        print(f"Steps completed: {result.steps_completed}")
        if result.steps_failed > 0:
            print(f"Steps failed: {result.steps_failed}")
            for error in result.errors:
                print(f"❌ Error: {error}")

    if args.output:
        report = assistant.generate_migration_report(
            plan, result if not args.plan_only else None
        )
        Path(args.output).write_text(report)
        print(f"📄 Migration report saved to: {args.output}")


def cmd_compare(args):
    """Run performance comparison."""
    print("📊 Running performance comparison...")

    # Load configurations
    with open(args.before_config) as f:
        before_config = json.load(f)

    with open(args.after_config) as f:
        after_config = json.load(f)

    comparator = PerformanceComparator(
        sample_size=args.samples, warmup_runs=args.warmup
    )

    try:
        report = comparator.compare_configurations(before_config, after_config)

        print(f"Performance change: {report.overall_change_percentage:+.1f}%")
        print(
            f"Status: {'Improvement' if report.overall_improvement else 'Regression'}"
        )
        print(f"Risk: {report.risk_assessment}")

        if args.output:
            perf_report = comparator.generate_performance_report(report, args.format)
            Path(args.output).write_text(perf_report)
            print(f"📄 Performance report saved to: {args.output}")

    except Exception as e:
        print(f"❌ Performance comparison failed: {e}")
        print("   Ensure LocalRuntime is properly installed and configured")


def cmd_baseline(args):
    """Create regression baseline."""
    print("📊 Creating regression baseline...")

    with open(args.config) as f:
        config = json.load(f)

    detector = RegressionDetector(baseline_path=args.baseline_file)

    try:
        baselines = detector.create_baseline(config)
        print(f"Created {len(baselines)} baseline snapshots")
        print(f"Baseline saved to: {args.baseline_file}")
    except Exception as e:
        print(f"❌ Baseline creation failed: {e}")


def cmd_regress(args):
    """Run regression detection."""
    print("🔍 Running regression detection...")

    with open(args.config) as f:
        config = json.load(f)

    detector = RegressionDetector(baseline_path=args.baseline_file)

    try:
        report = detector.detect_regressions(config)

        print(f"Tests run: {report.total_tests}")
        print(f"Passed: {report.passed_tests}")
        print(f"Failed: {report.failed_tests}")
        print(f"Status: {report.overall_status}")

        if args.output:
            regression_report = detector.generate_regression_report(report, args.format)
            Path(args.output).write_text(regression_report)
            print(f"📄 Regression report saved to: {args.output}")

    except Exception as e:
        print(f"❌ Regression detection failed: {e}")


def cmd_docs(args):
    """Generate migration documentation."""
    print("📚 Generating migration documentation...")

    generator = MigrationDocGenerator()

    # Load results from previous analysis if available
    analysis_result = None
    if args.analysis_file:
        # This would need to load from saved analysis
        print("Loading previous analysis results...")

    guide = generator.generate_migration_guide(
        analysis_result=analysis_result, scenario=args.scenario, audience=args.audience
    )

    generator.export_guide(guide, args.output, args.format)
    print(f"📄 Migration guide saved to: {args.output}")


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="LocalRuntime Migration Tools CLI", prog="kailash-migrate"
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Analyze command
    analyze_parser = subparsers.add_parser("analyze", help="Run compatibility analysis")
    analyze_parser.add_argument("path", type=Path, help="Project path to analyze")
    analyze_parser.add_argument(
        "--include", nargs="*", default=["*.py"], help="Include patterns"
    )
    analyze_parser.add_argument("--exclude", nargs="*", help="Exclude patterns")
    analyze_parser.add_argument("--output", "-o", help="Output file path")
    analyze_parser.add_argument(
        "--format", choices=["text", "json", "markdown"], default="text"
    )
    analyze_parser.set_defaults(func=cmd_analyze)

    # Validate command
    validate_parser = subparsers.add_parser("validate", help="Validate configuration")
    validate_parser.add_argument("--config-file", help="Configuration file (JSON)")
    validate_parser.add_argument("--debug", type=bool, help="Debug mode")
    validate_parser.add_argument("--max-concurrency", type=int, help="Max concurrency")
    validate_parser.add_argument(
        "--enable-monitoring", type=bool, help="Enable monitoring"
    )
    validate_parser.add_argument("--enable-security", type=bool, help="Enable security")
    validate_parser.add_argument("--output", "-o", help="Output file path")
    validate_parser.add_argument(
        "--format", choices=["text", "json", "markdown"], default="text"
    )
    validate_parser.set_defaults(func=cmd_validate)

    # Migrate command
    migrate_parser = subparsers.add_parser("migrate", help="Run migration")
    migrate_parser.add_argument("path", type=Path, help="Project path to migrate")
    migrate_parser.add_argument(
        "--include", nargs="*", default=["*.py"], help="Include patterns"
    )
    migrate_parser.add_argument("--exclude", nargs="*", help="Exclude patterns")
    migrate_parser.add_argument(
        "--dry-run", action="store_true", default=True, help="Dry run mode"
    )
    migrate_parser.add_argument(
        "--no-dry-run",
        dest="dry_run",
        action="store_false",
        help="Execute actual migration",
    )
    migrate_parser.add_argument(
        "--backup", action="store_true", default=True, help="Create backups"
    )
    migrate_parser.add_argument(
        "--no-backup", dest="backup", action="store_false", help="Skip backups"
    )
    migrate_parser.add_argument(
        "--plan-only", action="store_true", help="Only create plan, don't execute"
    )
    migrate_parser.add_argument("--output", "-o", help="Output file path")
    migrate_parser.set_defaults(func=cmd_migrate)

    # Compare command
    compare_parser = subparsers.add_parser("compare", help="Compare performance")
    compare_parser.add_argument(
        "before_config", help="Before configuration file (JSON)"
    )
    compare_parser.add_argument("after_config", help="After configuration file (JSON)")
    compare_parser.add_argument(
        "--samples", type=int, default=3, help="Number of samples"
    )
    compare_parser.add_argument("--warmup", type=int, default=1, help="Warmup runs")
    compare_parser.add_argument("--output", "-o", help="Output file path")
    compare_parser.add_argument(
        "--format", choices=["text", "json", "markdown"], default="text"
    )
    compare_parser.set_defaults(func=cmd_compare)

    # Baseline command
    baseline_parser = subparsers.add_parser(
        "baseline", help="Create regression baseline"
    )
    baseline_parser.add_argument("config", help="Configuration file (JSON)")
    baseline_parser.add_argument(
        "--baseline-file", default="baseline.json", help="Baseline file path"
    )
    baseline_parser.set_defaults(func=cmd_baseline)

    # Regression command
    regress_parser = subparsers.add_parser("regress", help="Run regression detection")
    regress_parser.add_argument("config", help="Configuration file (JSON)")
    regress_parser.add_argument(
        "--baseline-file", default="baseline.json", help="Baseline file path"
    )
    regress_parser.add_argument("--output", "-o", help="Output file path")
    regress_parser.add_argument(
        "--format", choices=["text", "json", "markdown"], default="text"
    )
    regress_parser.set_defaults(func=cmd_regress)

    # Documentation command
    docs_parser = subparsers.add_parser("docs", help="Generate documentation")
    docs_parser.add_argument("output", help="Output file path")
    docs_parser.add_argument(
        "--scenario",
        choices=["simple", "standard", "enterprise", "performance_critical"],
        default="standard",
        help="Documentation scenario",
    )
    docs_parser.add_argument(
        "--audience",
        choices=["developer", "admin", "architect", "all"],
        default="developer",
        help="Target audience",
    )
    docs_parser.add_argument("--analysis-file", help="Previous analysis results file")
    docs_parser.add_argument(
        "--format", choices=["markdown", "html"], default="markdown"
    )
    docs_parser.set_defaults(func=cmd_docs)

    # Parse arguments and execute
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    try:
        args.func(args)
        return 0
    except Exception as e:
        print(f"❌ Error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
