#!/usr/bin/env python3
"""
Unit tests for Impact Assessment Reporting System - TODO-137 Phase 3

Tests user-friendly impact reporting, recommendations engine, and multiple output formats.
Validates integration with existing DependencyAnalyzer and ColumnRemovalManager components.
"""

import json
from dataclasses import dataclass
from datetime import datetime

import pytest
from dataflow.migrations.column_removal_manager import SafetyValidation
from dataflow.migrations.dependency_analyzer import (
    ConstraintDependency,
    DependencyReport,
    DependencyType,
    ForeignKeyDependency,
    ImpactLevel,
    IndexDependency,
    TriggerDependency,
    ViewDependency,
)
from dataflow.migrations.impact_reporter import (
    ImpactAssessment,
    ImpactReport,
    ImpactReporter,
    OutputFormat,
    Recommendation,
    RecommendationType,
)


class TestImpactReporter:
    """Test the core ImpactReporter functionality."""

    @pytest.fixture
    def impact_reporter(self):
        """Create ImpactReporter instance for testing."""
        return ImpactReporter()

    @pytest.fixture
    def sample_dependency_report(self):
        """Create sample dependency report with various dependency types."""
        report = DependencyReport(
            table_name="users",
            column_name="email",
            analysis_timestamp="2024-01-01T12:00:00",
            total_analysis_time=2.5,
        )

        # Add critical foreign key dependency
        fk_dep = ForeignKeyDependency(
            constraint_name="fk_orders_user_email",
            source_table="orders",
            source_column="user_email",
            target_table="users",
            target_column="email",
            on_delete="CASCADE",
            on_update="RESTRICT",
            impact_level=ImpactLevel.CRITICAL,
        )
        report.dependencies[DependencyType.FOREIGN_KEY] = [fk_dep]

        # Add high impact view dependency
        view_dep = ViewDependency(
            view_name="user_summary",
            view_definition="SELECT id, email, name FROM users WHERE email IS NOT NULL",
            schema_name="public",
            is_materialized=False,
            impact_level=ImpactLevel.HIGH,
        )
        report.dependencies[DependencyType.VIEW] = [view_dep]

        # Add medium impact trigger dependency
        trigger_dep = TriggerDependency(
            trigger_name="audit_email_changes",
            event="UPDATE",
            timing="AFTER",
            function_name="log_email_change",
            impact_level=ImpactLevel.MEDIUM,
        )
        report.dependencies[DependencyType.TRIGGER] = [trigger_dep]

        # Add low impact index dependencies
        index_deps = [
            IndexDependency(
                index_name="idx_users_email_unique",
                index_type="btree",
                columns=["email"],
                is_unique=True,
                impact_level=ImpactLevel.LOW,
            ),
            IndexDependency(
                index_name="idx_users_email_status",
                index_type="btree",
                columns=["email", "status"],
                is_unique=False,
                impact_level=ImpactLevel.MEDIUM,
            ),
        ]
        report.dependencies[DependencyType.INDEX] = index_deps

        return report

    @pytest.fixture
    def minimal_dependency_report(self):
        """Create minimal dependency report for safe removal."""
        report = DependencyReport(
            table_name="users",
            column_name="temp_field",
            analysis_timestamp="2024-01-01T12:00:00",
            total_analysis_time=0.5,
        )

        # Only a low-impact index
        index_dep = IndexDependency(
            index_name="idx_temp_field",
            index_type="btree",
            columns=["temp_field"],
            is_unique=False,
            impact_level=ImpactLevel.LOW,
        )
        report.dependencies[DependencyType.INDEX] = [index_dep]

        return report

    def test_impact_reporter_initialization(self, impact_reporter):
        """Test ImpactReporter initialization."""
        assert impact_reporter is not None
        assert hasattr(impact_reporter, "impact_icons")
        assert hasattr(impact_reporter, "dependency_icons")

        # Verify icon mappings are complete
        assert len(impact_reporter.impact_icons) == len(ImpactLevel)
        assert len(impact_reporter.dependency_icons) == len(DependencyType)

    def test_generate_impact_report_critical_scenario(
        self, impact_reporter, sample_dependency_report
    ):
        """Test impact report generation for critical scenario."""
        report = impact_reporter.generate_impact_report(sample_dependency_report)

        assert isinstance(report, ImpactReport)
        assert report.assessment.table_name == "users"
        assert report.assessment.column_name == "email"
        assert report.assessment.overall_risk == ImpactLevel.CRITICAL
        assert (
            report.assessment.total_dependencies == 5
        )  # 1 FK + 1 view + 1 trigger + 2 indexes
        assert report.assessment.critical_dependencies == 1
        assert report.assessment.high_impact_dependencies == 1
        assert (
            report.assessment.medium_impact_dependencies == 2
        )  # trigger + composite index
        assert report.assessment.low_impact_dependencies == 1

        # Verify recommendations are generated
        assert len(report.recommendations) > 0
        primary_rec = report.recommendations[0]
        assert primary_rec.type == RecommendationType.DO_NOT_REMOVE
        assert "CRITICAL" in primary_rec.title.upper()
        assert len(primary_rec.action_steps) > 0

        # Verify dependency details are populated
        assert len(report.dependency_details) > 0
        assert "foreign_key" in report.dependency_details
        assert "view" in report.dependency_details
        assert "trigger" in report.dependency_details
        assert "index" in report.dependency_details

    def test_generate_impact_report_safe_scenario(
        self, impact_reporter, minimal_dependency_report
    ):
        """Test impact report generation for safe removal scenario."""
        report = impact_reporter.generate_impact_report(minimal_dependency_report)

        assert report.assessment.overall_risk == ImpactLevel.LOW
        assert report.assessment.total_dependencies == 1
        assert report.assessment.critical_dependencies == 0
        assert report.assessment.high_impact_dependencies == 0
        assert report.assessment.medium_impact_dependencies == 0
        assert report.assessment.low_impact_dependencies == 1

        # Verify safe removal recommendation
        primary_rec = report.recommendations[0]
        assert primary_rec.type == RecommendationType.SAFE_TO_REMOVE
        assert "SAFE" in primary_rec.title.upper()

    def test_create_removal_recommendations_critical(self, impact_reporter):
        """Test recommendation creation for critical scenario."""
        assessment = ImpactAssessment(
            table_name="users",
            column_name="id",
            overall_risk=ImpactLevel.CRITICAL,
            total_dependencies=3,
            critical_dependencies=2,
            high_impact_dependencies=1,
            medium_impact_dependencies=0,
            low_impact_dependencies=0,
        )

        recommendations = impact_reporter.create_removal_recommendations(assessment)

        assert len(recommendations) >= 1
        primary_rec = recommendations[0]
        assert primary_rec.type == RecommendationType.DO_NOT_REMOVE
        assert primary_rec.priority == ImpactLevel.CRITICAL
        assert "foreign key" in " ".join(primary_rec.action_steps).lower()
        assert "views and triggers" in " ".join(primary_rec.action_steps).lower()

    def test_create_removal_recommendations_high_impact(self, impact_reporter):
        """Test recommendation creation for high impact scenario."""
        assessment = ImpactAssessment(
            table_name="users",
            column_name="status",
            overall_risk=ImpactLevel.HIGH,
            total_dependencies=2,
            critical_dependencies=0,
            high_impact_dependencies=2,
            medium_impact_dependencies=0,
            low_impact_dependencies=0,
        )

        recommendations = impact_reporter.create_removal_recommendations(assessment)

        primary_rec = recommendations[0]
        assert primary_rec.type == RecommendationType.REQUIRES_FIXES
        assert primary_rec.priority == ImpactLevel.HIGH
        assert "staging environment" in " ".join(primary_rec.action_steps).lower()

    def test_create_removal_recommendations_medium_impact(self, impact_reporter):
        """Test recommendation creation for medium impact scenario."""
        assessment = ImpactAssessment(
            table_name="users",
            column_name="last_login",
            overall_risk=ImpactLevel.MEDIUM,
            total_dependencies=3,
            critical_dependencies=0,
            high_impact_dependencies=0,
            medium_impact_dependencies=3,
            low_impact_dependencies=0,
        )

        recommendations = impact_reporter.create_removal_recommendations(assessment)

        primary_rec = recommendations[0]
        assert primary_rec.type == RecommendationType.PROCEED_WITH_CAUTION
        assert primary_rec.priority == ImpactLevel.MEDIUM
        assert "performance" in " ".join(primary_rec.action_steps).lower()

    def test_create_removal_recommendations_safe(self, impact_reporter):
        """Test recommendation creation for safe scenario."""
        assessment = ImpactAssessment(
            table_name="users",
            column_name="temp_field",
            overall_risk=ImpactLevel.LOW,
            total_dependencies=1,
            critical_dependencies=0,
            high_impact_dependencies=0,
            medium_impact_dependencies=0,
            low_impact_dependencies=1,
        )

        recommendations = impact_reporter.create_removal_recommendations(assessment)

        primary_rec = recommendations[0]
        assert primary_rec.type == RecommendationType.SAFE_TO_REMOVE
        assert "backup" in " ".join(primary_rec.action_steps).lower()

    def test_dependency_specific_recommendations(
        self, impact_reporter, sample_dependency_report
    ):
        """Test creation of dependency-specific recommendations."""
        assessment = ImpactAssessment(
            table_name="users",
            column_name="email",
            overall_risk=ImpactLevel.CRITICAL,
            total_dependencies=5,
            critical_dependencies=1,
            high_impact_dependencies=1,
            medium_impact_dependencies=2,
            low_impact_dependencies=1,
        )

        recommendations = impact_reporter.create_removal_recommendations(
            assessment, sample_dependency_report
        )

        # Should have primary recommendation plus dependency-specific ones
        assert len(recommendations) >= 2

        # Check for foreign key specific recommendation
        fk_recs = [r for r in recommendations if "Foreign Key" in r.title]
        assert len(fk_recs) >= 1
        fk_rec = fk_recs[0]
        assert "referencing tables" in " ".join(fk_rec.action_steps).lower()
        assert fk_rec.sql_example is not None

        # Check for view specific recommendation
        view_recs = [r for r in recommendations if "Views" in r.title]
        assert len(view_recs) >= 1
        view_rec = view_recs[0]
        assert "view definition" in " ".join(view_rec.action_steps).lower()

    def test_format_console_report(self, impact_reporter, sample_dependency_report):
        """Test console format output."""
        report = impact_reporter.generate_impact_report(sample_dependency_report)
        console_output = impact_reporter.format_user_friendly_report(
            report, OutputFormat.CONSOLE
        )

        assert isinstance(console_output, str)
        assert len(console_output) > 0

        # Check for key elements in console output
        assert "users.email" in console_output
        assert "CRITICAL IMPACT DETECTED" in console_output
        assert "🔴 BREAKS" in console_output
        assert "RECOMMENDATION:" in console_output
        assert "RECOMMENDED ACTIONS:" in console_output

        # Check for visual elements
        assert "╭" in console_output or "┌" in console_output  # Box borders
        assert "🔴" in console_output  # Critical icon
        assert "❌" in console_output or "✅" in console_output  # Recommendation icons

    def test_format_console_report_safe_scenario(
        self, impact_reporter, minimal_dependency_report
    ):
        """Test console format for safe removal scenario."""
        report = impact_reporter.generate_impact_report(minimal_dependency_report)
        console_output = impact_reporter.format_user_friendly_report(
            report, OutputFormat.CONSOLE
        )

        assert "SAFE TO REMOVE" in console_output
        assert "✅" in console_output
        assert "🟢" in console_output or "minimal" in console_output.lower()

    def test_format_json_report(self, impact_reporter, sample_dependency_report):
        """Test JSON format output."""
        report = impact_reporter.generate_impact_report(sample_dependency_report)
        json_output = impact_reporter.format_user_friendly_report(
            report, OutputFormat.JSON
        )

        assert isinstance(json_output, str)

        # Validate JSON structure
        parsed = json.loads(json_output)
        assert "assessment" in parsed
        assert "recommendations" in parsed
        assert "dependency_details" in parsed
        assert "generation_timestamp" in parsed

        # Validate assessment structure
        assessment = parsed["assessment"]
        assert assessment["table_name"] == "users"
        assert assessment["column_name"] == "email"
        assert assessment["overall_risk"] == "critical"
        assert assessment["total_dependencies"] == 5

    def test_format_html_report(self, impact_reporter, sample_dependency_report):
        """Test HTML format output."""
        report = impact_reporter.generate_impact_report(sample_dependency_report)
        html_output = impact_reporter.format_user_friendly_report(
            report, OutputFormat.HTML
        )

        assert isinstance(html_output, str)
        assert len(html_output) > 0

        # Check for HTML elements
        assert "<div" in html_output
        assert "<style>" in html_output
        assert "<h2>" in html_output
        assert "<code>users.email</code>" in html_output
        assert "critical-risk" in html_output
        assert "Critical: 1" in html_output

    def test_format_summary_report(self, impact_reporter, sample_dependency_report):
        """Test summary format output."""
        report = impact_reporter.generate_impact_report(sample_dependency_report)
        summary_output = impact_reporter.format_user_friendly_report(
            report, OutputFormat.SUMMARY
        )

        assert isinstance(summary_output, str)
        assert len(summary_output) < 200  # Should be concise

        # Check for key elements
        assert "users.email" in summary_output
        assert "Dependencies: 5 total" in summary_output
        assert "Risk: CRITICAL" in summary_output
        assert "DO NOT REMOVE" in summary_output

    def test_generate_safety_validation_report(self, impact_reporter):
        """Test safety validation report generation."""
        validation = SafetyValidation(
            is_safe=False,
            risk_level=ImpactLevel.CRITICAL,
            blocking_dependencies=[],
            warnings=["Critical foreign key found", "View will be broken"],
            recommendations=["Remove FK first", "Update view definition"],
            estimated_duration=45.0,
            requires_confirmation=True,
        )

        report = impact_reporter.generate_safety_validation_report(validation)

        assert isinstance(report, str)
        assert "SAFETY VALIDATION REPORT" in report
        assert "❌ UNSAFE" in report
        assert "🔴 CRITICAL" in report
        assert "45.0 seconds" in report
        assert "Yes" in report  # Requires confirmation
        assert "WARNINGS" in report
        assert "RECOMMENDATIONS" in report

        # Check warnings and recommendations are included
        assert "Critical foreign key found" in report
        assert "Remove FK first" in report

    def test_generate_safety_validation_report_safe(self, impact_reporter):
        """Test safety validation report for safe scenario."""
        validation = SafetyValidation(
            is_safe=True,
            risk_level=ImpactLevel.LOW,
            blocking_dependencies=[],
            warnings=[],
            recommendations=["Create backup before removal"],
            estimated_duration=5.0,
            requires_confirmation=False,
        )

        report = impact_reporter.generate_safety_validation_report(validation)

        assert "✅ SAFE" in report
        assert "🟢 LOW" in report
        assert "5.0 seconds" in report
        assert "No" in report  # Requires confirmation


class TestImpactAssessmentEdgeCases:
    """Test edge cases and error conditions."""

    @pytest.fixture
    def impact_reporter(self):
        """Create ImpactReporter instance for testing."""
        return ImpactReporter()

    def test_empty_dependency_report(self, impact_reporter):
        """Test handling of empty dependency report."""
        report = DependencyReport(table_name="users", column_name="unused_field")
        # No dependencies added

        impact_report = impact_reporter.generate_impact_report(report)

        assert impact_report.assessment.overall_risk == ImpactLevel.INFORMATIONAL
        assert impact_report.assessment.total_dependencies == 0
        assert len(impact_report.recommendations) >= 1

        # Should still get a safe removal recommendation
        primary_rec = impact_report.recommendations[0]
        assert primary_rec.type == RecommendationType.SAFE_TO_REMOVE

    def test_mixed_impact_levels(self, impact_reporter):
        """Test handling of mixed impact levels."""
        report = DependencyReport(table_name="users", column_name="email")

        # Mix of impact levels - critical should dominate
        deps = [
            ForeignKeyDependency(
                constraint_name="fk_critical",
                source_table="orders",
                source_column="user_id",
                impact_level=ImpactLevel.CRITICAL,
            ),
            IndexDependency(
                index_name="idx_high",
                index_type="btree",
                columns=["email"],
                impact_level=ImpactLevel.HIGH,
            ),
            IndexDependency(
                index_name="idx_low",
                index_type="btree",
                columns=["email"],
                impact_level=ImpactLevel.LOW,
            ),
        ]

        report.dependencies[DependencyType.FOREIGN_KEY] = [deps[0]]
        report.dependencies[DependencyType.INDEX] = deps[1:]

        impact_report = impact_reporter.generate_impact_report(report)

        # Critical should dominate overall risk
        assert impact_report.assessment.overall_risk == ImpactLevel.CRITICAL
        assert impact_report.assessment.critical_dependencies == 1
        assert impact_report.assessment.high_impact_dependencies == 1
        assert impact_report.assessment.low_impact_dependencies == 1

    def test_large_dependency_count(self, impact_reporter):
        """Test handling of large number of dependencies."""
        report = DependencyReport(table_name="users", column_name="email")

        # Create many index dependencies
        index_deps = []
        for i in range(20):
            index_deps.append(
                IndexDependency(
                    index_name=f"idx_test_{i}",
                    index_type="btree",
                    columns=["email"],
                    impact_level=ImpactLevel.MEDIUM,
                )
            )

        report.dependencies[DependencyType.INDEX] = index_deps

        impact_report = impact_reporter.generate_impact_report(report)

        assert impact_report.assessment.total_dependencies == 20
        assert impact_report.assessment.medium_impact_dependencies == 20

        # Console output should handle large lists gracefully
        console_output = impact_reporter.format_user_friendly_report(
            impact_report, OutputFormat.CONSOLE
        )
        assert "... and" in console_output  # Should truncate long lists

    def test_unicode_and_special_characters(self, impact_reporter):
        """Test handling of unicode and special characters in names."""
        report = DependencyReport(table_name="ü̃sers", column_name="émáil")

        # Dependency with unicode characters
        view_dep = ViewDependency(
            view_name="üser_summäry",
            view_definition="SELECT * FROM ü̃sers WHERE émáil LIKE '%@test.com'",
            impact_level=ImpactLevel.HIGH,
        )
        report.dependencies[DependencyType.VIEW] = [view_dep]

        impact_report = impact_reporter.generate_impact_report(report)

        assert impact_report.assessment.table_name == "ü̃sers"
        assert impact_report.assessment.column_name == "émáil"

        # All formats should handle unicode gracefully
        for format_type in OutputFormat:
            output = impact_reporter.format_user_friendly_report(
                impact_report, format_type
            )
            assert isinstance(output, str)
            assert len(output) > 0


class TestImpactReporterIntegration:
    """Test integration with existing components."""

    @pytest.fixture
    def impact_reporter(self):
        return ImpactReporter()

    def test_integration_with_dependency_report(self, impact_reporter):
        """Test seamless integration with DependencyReport from Phase 1."""
        # Create a realistic dependency report as would come from DependencyAnalyzer
        report = DependencyReport(
            table_name="products",
            column_name="category_id",
            analysis_timestamp="2024-01-01T10:30:00",
            total_analysis_time=3.2,
        )

        # Add realistic dependencies
        fk_dep = ForeignKeyDependency(
            constraint_name="fk_products_category",
            source_table="products",
            source_column="category_id",
            target_table="categories",
            target_column="id",
            impact_level=ImpactLevel.CRITICAL,
        )

        view_dep = ViewDependency(
            view_name="product_catalog",
            view_definition="SELECT p.*, c.name as category_name FROM products p JOIN categories c ON p.category_id = c.id",
            impact_level=ImpactLevel.HIGH,
        )

        report.dependencies[DependencyType.FOREIGN_KEY] = [fk_dep]
        report.dependencies[DependencyType.VIEW] = [view_dep]

        # Generate impact report
        impact_report = impact_reporter.generate_impact_report(report)

        # Verify proper integration
        assert impact_report.assessment.table_name == report.table_name
        assert impact_report.assessment.column_name == report.column_name
        assert (
            impact_report.assessment.total_dependencies
            == report.get_total_dependency_count()
        )

        # Verify dependency details preserve original data
        assert "foreign_key" in impact_report.dependency_details
        fk_detail = impact_report.dependency_details["foreign_key"][0]
        assert fk_detail["source_table"] == fk_dep.source_table
        assert fk_detail["target_table"] == fk_dep.target_table

    def test_integration_with_safety_validation(self, impact_reporter):
        """Test integration with SafetyValidation from Phase 2."""
        # Create safety validation as would come from ColumnRemovalManager
        validation = SafetyValidation(
            is_safe=False,
            risk_level=ImpactLevel.HIGH,
            blocking_dependencies=[],
            warnings=["View dependency detected", "Index will be dropped"],
            recommendations=[
                "Update view definition",
                "Review query performance impact",
            ],
            estimated_duration=30.5,
            requires_confirmation=True,
        )

        report_text = impact_reporter.generate_safety_validation_report(validation)

        # Verify proper formatting and content
        assert "HIGH" in report_text
        assert "30.5 seconds" in report_text
        assert "View dependency detected" in report_text
        assert "Update view definition" in report_text
        assert "❌ UNSAFE" in report_text

    def test_end_to_end_reporting_workflow(self, impact_reporter):
        """Test complete workflow from dependency analysis to user report."""
        # Simulate Phase 1 output (DependencyAnalyzer)
        dependency_report = DependencyReport(
            table_name="orders", column_name="customer_id"
        )

        # Critical FK dependency (would prevent removal)
        critical_fk = ForeignKeyDependency(
            constraint_name="fk_orders_customer_id",
            source_table="orders",
            source_column="customer_id",
            target_table="customers",
            target_column="id",
            impact_level=ImpactLevel.CRITICAL,
        )
        dependency_report.dependencies[DependencyType.FOREIGN_KEY] = [critical_fk]

        # Phase 3: Generate impact report
        impact_report = impact_reporter.generate_impact_report(dependency_report)

        # Simulate Phase 2 safety validation (would use the impact report)
        safety_validation = SafetyValidation(
            is_safe=False,
            risk_level=impact_report.assessment.overall_risk,
            blocking_dependencies=[critical_fk],
            warnings=["Critical dependency prevents safe removal"],
            recommendations=["Remove foreign key constraint first"],
            requires_confirmation=True,
        )

        # Generate user-facing reports
        console_report = impact_reporter.format_user_friendly_report(
            impact_report, OutputFormat.CONSOLE
        )
        json_report = impact_reporter.format_user_friendly_report(
            impact_report, OutputFormat.JSON
        )
        safety_report = impact_reporter.generate_safety_validation_report(
            safety_validation
        )

        # Verify end-to-end consistency
        assert "orders.customer_id" in console_report
        assert "DO NOT REMOVE" in console_report
        assert "CRITICAL" in console_report

        parsed_json = json.loads(json_report)
        assert parsed_json["assessment"]["overall_risk"] == "critical"

        assert "UNSAFE" in safety_report
        assert "Critical dependency" in safety_report
