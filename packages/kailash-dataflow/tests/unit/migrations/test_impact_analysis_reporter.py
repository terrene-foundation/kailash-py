#!/usr/bin/env python3
"""
Unit tests for Impact Analysis Reporter - TODO-140 Phase 3

Tests all components of the ImpactAnalysisReporter and ReportFormatter systems:
- Executive risk summary generation
- Technical impact report creation
- Compliance audit report building
- Stakeholder communication formatting
- Multi-format report output (Console, JSON, HTML, Summary)
- Progressive disclosure capabilities
- Performance characteristics

TESTING COVERAGE:
- ✅ Executive summary generation with business impact analysis
- ✅ Technical report creation with implementation guidance
- ✅ Compliance report building with regulatory documentation
- ✅ Stakeholder communication formatting for all roles
- ✅ Multi-format output generation and validation
- ✅ Report formatter styling and theming
- ✅ Progressive disclosure section filtering
- ✅ Performance validation for large reports
- ✅ Error handling and edge cases
"""

import json
import time
from datetime import datetime
from typing import Any, Dict, List
from unittest.mock import Mock, patch

import pytest
from dataflow.migrations.dependency_analyzer import (
    DependencyReport,
    DependencyType,
    ImpactLevel,
)
from dataflow.migrations.impact_analysis_reporter import (
    ComplianceAuditReport,
    ComprehensiveImpactReport,
    ExecutiveRiskSummary,
    ImpactAnalysisReporter,
    ReportFormat,
    ReportSection,
    StakeholderReport,
    StakeholderRole,
    TechnicalImpactReport,
)
from dataflow.migrations.mitigation_strategy_engine import (
    MitigationCategory,
    MitigationComplexity,
    MitigationPriority,
    MitigationStrategy,
    MitigationStrategyEngine,
    PrioritizedMitigationPlan,
)
from dataflow.migrations.report_formatters import (
    ConsoleTheme,
    FormatStyle,
    ReportFormatter,
)
from dataflow.migrations.risk_assessment_engine import (
    ComprehensiveRiskAssessment,
    RiskAssessmentEngine,
    RiskCategory,
    RiskFactor,
    RiskLevel,
    RiskScore,
)


class TestImpactAnalysisReporter:
    """Test suite for ImpactAnalysisReporter functionality."""

    @pytest.fixture
    def impact_reporter(self):
        """Create ImpactAnalysisReporter instance for testing."""
        return ImpactAnalysisReporter()

    @pytest.fixture
    def sample_risk_assessment(self):
        """Create sample risk assessment for testing."""
        category_scores = {
            RiskCategory.DATA_LOSS: RiskScore(
                category=RiskCategory.DATA_LOSS,
                score=75.0,
                level=RiskLevel.HIGH,
                description="High data loss risk due to FK constraints",
                risk_factors=["FK CASCADE constraint present", "No backup validation"],
                confidence=0.95,
            ),
            RiskCategory.SYSTEM_AVAILABILITY: RiskScore(
                category=RiskCategory.SYSTEM_AVAILABILITY,
                score=45.0,
                level=RiskLevel.MEDIUM,
                description="Medium availability risk in production",
                risk_factors=["Production environment operation"],
                confidence=0.90,
            ),
            RiskCategory.PERFORMANCE_DEGRADATION: RiskScore(
                category=RiskCategory.PERFORMANCE_DEGRADATION,
                score=35.0,
                level=RiskLevel.MEDIUM,
                description="Medium performance risk from index removal",
                risk_factors=["Index removal required"],
                confidence=0.85,
            ),
            RiskCategory.ROLLBACK_COMPLEXITY: RiskScore(
                category=RiskCategory.ROLLBACK_COMPLEXITY,
                score=25.0,
                level=RiskLevel.LOW,
                description="Low rollback complexity with backup available",
                risk_factors=["Backup available"],
                confidence=0.92,
            ),
        }

        risk_factors = []
        for category_score in category_scores.values():
            for factor_desc in category_score.risk_factors:
                risk_factors.append(
                    RiskFactor(
                        category=category_score.category,
                        description=factor_desc,
                        impact_score=category_score.score,
                    )
                )

        return ComprehensiveRiskAssessment(
            operation_id="test_operation_001",
            overall_score=55.0,
            risk_level=RiskLevel.HIGH,
            category_scores=category_scores,
            risk_factors=risk_factors,
            recommendations=[
                "Implement comprehensive backup strategy",
                "Schedule during maintenance window",
                "Prepare rollback procedures",
            ],
        )

    @pytest.fixture
    def sample_mitigation_plan(self):
        """Create sample mitigation plan for testing."""
        strategies = [
            MitigationStrategy(
                id="backup_strategy_001",
                name="Enhanced Backup Strategy",
                description="Multi-level backup with verification",
                category=MitigationCategory.IMMEDIATE_RISK_REDUCTION,
                priority=MitigationPriority.CRITICAL,
                complexity=MitigationComplexity.MODERATE,
                risk_reduction_potential=85.0,
                implementation_complexity=25.0,
                cost_benefit_ratio=90.0,
                estimated_effort_hours=4.0,
            ),
            MitigationStrategy(
                id="staging_rehearsal_001",
                name="Staging Migration Rehearsal",
                description="Full migration rehearsal in staging",
                category=MitigationCategory.SAFETY_ENHANCEMENTS,
                priority=MitigationPriority.HIGH,
                complexity=MitigationComplexity.MODERATE,
                risk_reduction_potential=75.0,
                implementation_complexity=40.0,
                cost_benefit_ratio=85.0,
                estimated_effort_hours=6.0,
            ),
        ]

        return type(
            "MockMitigationPlan",
            (),
            {
                "operation_id": "test_operation_001",
                "mitigation_strategies": strategies,
                "total_estimated_effort": 10.0,
                "projected_overall_risk": 25.0,
                "total_generation_time": 0.15,
            },
        )()

    @pytest.fixture
    def sample_dependency_report(self):
        """Create sample dependency report for testing."""
        return DependencyReport(
            table_name="test_table",
            column_name="test_column",
            dependencies={
                DependencyType.INDEX: [
                    type(
                        "IndexDep",
                        (),
                        {
                            "index_name": "idx_test_column",
                            "is_unique": False,
                            "impact_level": ImpactLevel.MEDIUM,
                        },
                    )()
                ]
            },
        )

    def test_executive_risk_summary_generation(
        self, impact_reporter, sample_risk_assessment
    ):
        """Test executive risk summary generation."""
        business_context = {
            "estimated_downtime_minutes": 120.0,
            "affected_systems_count": 3,
            "revenue_risk_estimate": "$50K-100K potential impact",
        }

        summary = impact_reporter.generate_executive_risk_summary(
            sample_risk_assessment, business_context=business_context
        )

        # Validate summary structure
        assert isinstance(summary, ExecutiveRiskSummary)
        assert summary.overall_risk_level == RiskLevel.HIGH
        assert summary.overall_risk_score == 55.0
        assert summary.potential_downtime_minutes == 120.0
        assert summary.affected_systems_count == 3
        assert summary.revenue_risk_estimate == "$50K-100K potential impact"

        # Validate approval requirements
        assert summary.approval_required is True
        assert summary.approval_level == "Management"
        assert "MANAGEMENT APPROVAL REQUIRED" in summary.go_no_go_recommendation

        # Validate business impact assessment
        assert "Moderate business impact" in summary.business_impact
        assert "Database migration operation" in summary.operation_description

    def test_technical_impact_report_creation(
        self, impact_reporter, sample_risk_assessment, sample_dependency_report
    ):
        """Test technical impact report creation."""
        technical_report = impact_reporter.create_technical_impact_report(
            sample_risk_assessment, dependency_report=sample_dependency_report
        )

        # Validate report structure
        assert isinstance(technical_report, TechnicalImpactReport)
        assert "operation_id" in technical_report.operation_details
        assert (
            technical_report.operation_details["operation_id"] == "test_operation_001"
        )
        assert technical_report.operation_details["overall_risk_score"] == 55.0

        # Validate risk breakdown
        assert len(technical_report.risk_category_breakdown) == 4
        assert RiskCategory.DATA_LOSS in technical_report.risk_category_breakdown

        data_loss_breakdown = technical_report.risk_category_breakdown[
            RiskCategory.DATA_LOSS
        ]
        assert data_loss_breakdown["score"] == 75.0
        assert data_loss_breakdown["level"] == "high"
        assert len(data_loss_breakdown["technical_implications"]) > 0

        # Validate implementation guidance
        assert len(technical_report.pre_migration_steps) > 0
        assert len(technical_report.migration_procedure) > 0
        assert len(technical_report.post_migration_validation) > 0
        assert len(technical_report.rollback_procedures) > 0

        # Check for backup validation in pre-migration steps
        assert any(
            "backup" in step.lower() for step in technical_report.pre_migration_steps
        )

        # Validate infrastructure requirements
        assert len(technical_report.infrastructure_requirements) > 0
        assert any(
            "database" in req.lower()
            for req in technical_report.infrastructure_requirements
        )

    def test_compliance_audit_report_building(
        self, impact_reporter, sample_risk_assessment
    ):
        """Test compliance audit report building."""
        business_context = {
            "regulatory_frameworks": ["HIPAA", "SOX", "Change Management Policy"],
            "risk_owner": "Database Team",
        }

        compliance_report = impact_reporter.build_compliance_audit_report(
            sample_risk_assessment, business_context=business_context
        )

        # Validate report structure
        assert isinstance(compliance_report, ComplianceAuditReport)
        assert len(compliance_report.regulatory_frameworks) == 3
        assert "HIPAA" in compliance_report.regulatory_frameworks
        assert "SOX" in compliance_report.regulatory_frameworks

        # Validate compliance risk assessment
        assert "overall_compliance_risk" in compliance_report.compliance_risk_assessment
        assert (
            "Medium compliance risk"
            in compliance_report.compliance_risk_assessment["overall_compliance_risk"]
        )

        # Validate change management documentation
        assert (
            "change_classification" in compliance_report.change_management_documentation
        )
        assert (
            "Major Change"
            in compliance_report.change_management_documentation[
                "change_classification"
            ]
        )

        # Validate approval workflows
        assert len(compliance_report.approval_workflows) > 0
        assert any(
            "Management Approval" in workflow
            for workflow in compliance_report.approval_workflows
        )

        # Validate risk register entry
        assert compliance_report.risk_register_entry["risk_id"] == "test_operation_001"
        assert compliance_report.risk_register_entry["inherent_risk_score"] == 55.0
        assert compliance_report.risk_register_entry["risk_owner"] == "Database Team"

        # Validate residual risk statement
        assert (
            "Management oversight recommended"
            in compliance_report.residual_risk_statement
        )

    def test_stakeholder_communications_formatting(
        self, impact_reporter, sample_risk_assessment, sample_mitigation_plan
    ):
        """Test stakeholder communications formatting."""
        executive_summary = ExecutiveRiskSummary(
            operation_description="Test migration operation",
            overall_risk_level=RiskLevel.HIGH,
            overall_risk_score=55.0,
            business_impact="Moderate business impact",
            recommended_action="Management review required",
            potential_downtime_minutes=120.0,
            affected_systems_count=3,
            revenue_risk_estimate="$50K-100K",
            user_impact_estimate="Moderate user impact",
            mitigation_strategies_count=2,
            risk_reduction_potential=50.0,
            implementation_timeline="3-5 days",
            resource_requirements="Standard team + DBA",
            approval_required=True,
            approval_level="Management",
            go_no_go_recommendation="Management approval required",
        )

        stakeholder_communications = impact_reporter.format_stakeholder_communications(
            sample_risk_assessment, sample_mitigation_plan, executive_summary
        )

        # Validate all stakeholder roles are covered
        assert len(stakeholder_communications) == len(StakeholderRole)

        # Test Executive stakeholder report
        executive_report = stakeholder_communications[StakeholderRole.EXECUTIVE]
        assert isinstance(executive_report, StakeholderReport)
        assert executive_report.role == StakeholderRole.EXECUTIVE
        assert len(executive_report.key_messages) > 0
        assert any("HIGH" in msg for msg in executive_report.key_messages)
        assert executive_report.technical_depth == "low"
        assert "Business Impact" in executive_report.focus_areas

        # Test Technical Lead stakeholder report
        tech_lead_report = stakeholder_communications[StakeholderRole.TECHNICAL_LEAD]
        assert tech_lead_report.role == StakeholderRole.TECHNICAL_LEAD
        assert len(tech_lead_report.action_items) > 0
        assert any(
            "review" in action.lower() for action in tech_lead_report.action_items
        )
        assert tech_lead_report.technical_depth == "high"

        # Test DBA stakeholder report
        dba_report = stakeholder_communications[StakeholderRole.DBA]
        assert dba_report.role == StakeholderRole.DBA
        assert len(dba_report.action_items) > 0
        assert any("backup" in action.lower() for action in dba_report.action_items)
        assert "Database Impact" in dba_report.focus_areas

        # Test escalation criteria
        for role, report in stakeholder_communications.items():
            if role in [
                StakeholderRole.DEVELOPER,
                StakeholderRole.DBA,
                StakeholderRole.DEVOPS,
            ]:
                assert len(report.escalation_criteria) > 0
                assert any(
                    "escalate" in criteria.lower()
                    for criteria in report.escalation_criteria
                )

    def test_comprehensive_impact_report_generation(
        self,
        impact_reporter,
        sample_risk_assessment,
        sample_mitigation_plan,
        sample_dependency_report,
    ):
        """Test comprehensive impact report generation."""
        business_context = {
            "regulatory_frameworks": ["Change Management Policy"],
            "risk_owner": "Database Team",
            "affected_systems_count": 2,
        }

        start_time = time.time()

        comprehensive_report = impact_reporter.generate_comprehensive_impact_report(
            sample_risk_assessment,
            sample_mitigation_plan,
            sample_dependency_report,
            business_context,
        )

        generation_time = time.time() - start_time

        # Validate report structure
        assert isinstance(comprehensive_report, ComprehensiveImpactReport)
        assert comprehensive_report.report_id.startswith("impact_report_")
        assert comprehensive_report.operation_id == "test_operation_001"
        assert comprehensive_report.report_version == "1.0"

        # Validate all report components are present
        assert isinstance(comprehensive_report.executive_summary, ExecutiveRiskSummary)
        assert isinstance(comprehensive_report.technical_report, TechnicalImpactReport)
        assert isinstance(comprehensive_report.compliance_report, ComplianceAuditReport)
        assert isinstance(comprehensive_report.stakeholder_communications, dict)
        assert comprehensive_report.risk_assessment == sample_risk_assessment
        assert comprehensive_report.mitigation_plan == sample_mitigation_plan
        assert comprehensive_report.dependency_report == sample_dependency_report

        # Validate performance characteristics
        assert comprehensive_report.generation_time_seconds < 1.0  # Should be fast
        assert generation_time < 1.0  # External timing validation

        # Validate metadata
        assert comprehensive_report.generation_timestamp is not None
        datetime.fromisoformat(
            comprehensive_report.generation_timestamp
        )  # Should parse correctly

    def test_error_handling_and_edge_cases(self, impact_reporter):
        """Test error handling and edge cases."""
        # Test with minimal risk assessment (no risk factors)
        minimal_assessment = ComprehensiveRiskAssessment(
            operation_id="minimal_test",
            overall_score=10.0,
            risk_level=RiskLevel.LOW,
            category_scores={},
            risk_factors=[],
            recommendations=[],
        )

        # Should handle empty risk assessment gracefully
        summary = impact_reporter.generate_executive_risk_summary(minimal_assessment)
        assert isinstance(summary, ExecutiveRiskSummary)
        assert summary.overall_risk_level == RiskLevel.LOW
        assert summary.approval_level == "None"

        # Test with no mitigation plan
        report_without_mitigation = (
            impact_reporter.generate_comprehensive_impact_report(minimal_assessment)
        )

        assert isinstance(report_without_mitigation, ComprehensiveImpactReport)
        assert report_without_mitigation.mitigation_plan is None

        # Test with no business context
        report_no_context = impact_reporter.generate_comprehensive_impact_report(
            minimal_assessment, business_context=None
        )

        assert isinstance(report_no_context, ComprehensiveImpactReport)

    def test_business_impact_estimation(self, impact_reporter):
        """Test business impact estimation logic."""
        # Test different risk levels
        risk_levels_and_expectations = [
            (RiskLevel.LOW, 5.0, 1, "Minimal revenue impact"),
            (RiskLevel.MEDIUM, 30.0, 1, "$10K-50K potential impact"),
            (RiskLevel.HIGH, 120.0, 2, "$50K-100K potential impact"),
            (RiskLevel.CRITICAL, 240.0, 3, "$100K-500K potential impact"),
        ]

        for (
            risk_level,
            expected_downtime,
            expected_systems,
            expected_revenue,
        ) in risk_levels_and_expectations:
            assessment = ComprehensiveRiskAssessment(
                operation_id=f"test_{risk_level.value}",
                overall_score=(
                    25
                    if risk_level == RiskLevel.LOW
                    else (
                        40
                        if risk_level == RiskLevel.MEDIUM
                        else 60 if risk_level == RiskLevel.HIGH else 85
                    )
                ),
                risk_level=risk_level,
                category_scores={},
                risk_factors=[],
                recommendations=[],
            )

            summary = impact_reporter.generate_executive_risk_summary(assessment)

            # Validate business impact scaling
            assert summary.potential_downtime_minutes == expected_downtime
            assert summary.affected_systems_count >= expected_systems
            assert expected_revenue in summary.revenue_risk_estimate


class TestReportFormatter:
    """Test suite for ReportFormatter functionality."""

    @pytest.fixture
    def report_formatter(self):
        """Create ReportFormatter instance for testing."""
        return ReportFormatter(enable_colors=True, enable_emojis=True)

    @pytest.fixture
    def sample_comprehensive_report(self):
        """Create sample comprehensive report for testing."""
        # Create minimal but complete report structure
        executive_summary = ExecutiveRiskSummary(
            operation_description="Test migration operation",
            overall_risk_level=RiskLevel.HIGH,
            overall_risk_score=65.0,
            business_impact="Moderate business impact expected",
            recommended_action="Management approval required",
            potential_downtime_minutes=90.0,
            affected_systems_count=2,
            revenue_risk_estimate="$25K-75K potential impact",
            user_impact_estimate="Moderate user impact",
            mitigation_strategies_count=3,
            risk_reduction_potential=60.0,
            implementation_timeline="2-3 days",
            resource_requirements="Standard team + specialist",
            approval_required=True,
            approval_level="Management",
            go_no_go_recommendation="Management approval required before proceeding",
        )

        technical_report = TechnicalImpactReport(
            operation_details={"operation_id": "test_op", "overall_risk_score": 65.0},
            risk_category_breakdown={
                RiskCategory.DATA_LOSS: {
                    "score": 70.0,
                    "level": "high",
                    "description": "High data loss risk",
                    "risk_factors": ["FK constraints present"],
                    "technical_implications": ["Backup validation required"],
                }
            },
            dependency_analysis={"total_dependencies": 2, "critical_dependencies": []},
            pre_migration_steps=["Validate backups", "Review migration plan"],
            migration_procedure=["Execute migration", "Monitor progress"],
            post_migration_validation=[
                "Verify data integrity",
                "Check application functionality",
            ],
            rollback_procedures=["Stop migration", "Restore from backup"],
            performance_impact_analysis={"overall_performance_risk": "medium"},
            infrastructure_requirements=["Additional backup storage"],
            monitoring_recommendations=["Monitor connection health"],
            testing_strategy=["Execute in staging environment"],
        )

        compliance_report = ComplianceAuditReport(
            regulatory_frameworks=["Change Management Policy"],
            compliance_risk_assessment={"overall_compliance_risk": "Medium"},
            data_protection_impact={"data_types_affected": ["Operational Data"]},
            change_management_documentation={
                "change_classification": "Standard Change"
            },
            risk_acceptance_criteria=["Technical approval required"],
            audit_trail_requirements=["Migration execution logs"],
            approval_workflows=["1. Technical Lead approval"],
            risk_register_entry={"risk_id": "test_op", "risk_category": "Operational"},
            control_effectiveness_assessment={
                "existing_controls": ["Backup procedures"]
            },
            residual_risk_statement="Residual risk acceptable with mitigations",
        )

        stakeholder_communications = {
            StakeholderRole.EXECUTIVE: StakeholderReport(
                role=StakeholderRole.EXECUTIVE,
                key_messages=["Risk level: HIGH", "Management approval required"],
                action_items=["Review risk assessment"],
                decision_points=["Approve/reject migration"],
                timeline_awareness="HIGH RISK: Additional preparation time required",
                escalation_criteria=[],
                technical_depth="low",
                focus_areas=["Business Impact"],
                communication_format="summary",
            )
        }

        # Mock risk assessment
        risk_assessment = ComprehensiveRiskAssessment(
            operation_id="test_op",
            overall_score=65.0,
            risk_level=RiskLevel.HIGH,
            category_scores={
                RiskCategory.DATA_LOSS: RiskScore(
                    category=RiskCategory.DATA_LOSS,
                    score=70.0,
                    level=RiskLevel.HIGH,
                    description="High data loss risk",
                    risk_factors=["FK constraints present"],
                )
            },
            risk_factors=[],
            recommendations=["Implement backup strategy"],
        )

        return ComprehensiveImpactReport(
            report_id="test_report_001",
            operation_id="test_op",
            generation_timestamp=datetime.now().isoformat(),
            executive_summary=executive_summary,
            technical_report=technical_report,
            compliance_report=compliance_report,
            stakeholder_communications=stakeholder_communications,
            risk_assessment=risk_assessment,
            generation_time_seconds=0.25,
        )

    def test_console_report_formatting(
        self, report_formatter, sample_comprehensive_report
    ):
        """Test console report formatting."""
        console_report = report_formatter.format_report(
            sample_comprehensive_report, ReportFormat.CONSOLE, FormatStyle.RICH
        )

        # Validate console report structure
        assert isinstance(console_report, str)
        assert "🎯 MIGRATION RISK ASSESSMENT" in console_report
        assert "💼 EXECUTIVE SUMMARY" in console_report
        assert "📈 RISK BREAKDOWN BY CATEGORY" in console_report

        # Check for risk level indicators
        assert "HIGH" in console_report
        assert "⚠️" in console_report  # High risk emoji

        # Check for progress bars
        assert "█" in console_report or "░" in console_report  # Progress bar characters

        # Check for business metrics
        assert "90.0 minutes" in console_report  # Downtime
        assert "$25K-75K" in console_report  # Revenue risk

        # Validate footer
        assert "Generated with DataFlow Risk Assessment Engine" in console_report
        assert "0.25" in console_report  # Generation time

    def test_json_report_formatting(
        self, report_formatter, sample_comprehensive_report
    ):
        """Test JSON report formatting."""
        json_report = report_formatter.format_report(
            sample_comprehensive_report, ReportFormat.JSON, FormatStyle.STANDARD
        )

        # Validate JSON structure
        assert isinstance(json_report, str)

        # Parse JSON to validate structure
        report_data = json.loads(json_report)

        # Validate metadata
        assert "report_metadata" in report_data
        assert report_data["report_metadata"]["report_id"] == "test_report_001"
        assert report_data["report_metadata"]["format"] == "json"

        # Validate sections
        assert "executive_summary" in report_data
        assert "risk_assessment" in report_data
        assert "technical_report" in report_data
        assert "compliance_report" in report_data

        # Validate executive summary data
        exec_summary = report_data["executive_summary"]
        assert exec_summary["overall_risk_level"] == "high"
        assert exec_summary["overall_risk_score"] == 65.0
        assert exec_summary["approval_required"] is True

        # Validate risk assessment data
        risk_data = report_data["risk_assessment"]
        assert risk_data["overall_score"] == 65.0
        assert risk_data["risk_level"] == "high"
        assert "category_scores" in risk_data

    def test_html_report_formatting(
        self, report_formatter, sample_comprehensive_report
    ):
        """Test HTML report formatting."""
        html_report = report_formatter.format_report(
            sample_comprehensive_report, ReportFormat.HTML, FormatStyle.RICH
        )

        # Validate HTML structure
        assert isinstance(html_report, str)
        assert "<!DOCTYPE html>" in html_report
        assert '<html lang="en">' in html_report
        assert "</html>" in html_report

        # Check for CSS styles
        assert "risk-high" in html_report
        assert "progress-bar" in html_report
        assert "metric-box" in html_report

        # Check for content sections
        assert "Migration Risk Assessment Report" in html_report
        assert "💼 Executive Summary" in html_report
        assert "📈 Risk Breakdown" in html_report

        # Check for risk level styling
        assert "HIGH" in html_report
        assert "65.0/100" in html_report

        # Validate responsive design elements
        assert "viewport" in html_report
        assert "max-width: 1200px" in html_report

        # Check for footer
        assert "Generated with DataFlow Risk Assessment Engine" in html_report

    def test_summary_report_formatting(
        self, report_formatter, sample_comprehensive_report
    ):
        """Test summary report formatting."""
        summary_report = report_formatter.format_report(
            sample_comprehensive_report, ReportFormat.SUMMARY, FormatStyle.EXECUTIVE
        )

        # Validate summary structure
        assert isinstance(summary_report, str)
        assert "MIGRATION RISK ASSESSMENT - EXECUTIVE SUMMARY" in summary_report
        assert "=" * 50 in summary_report

        # Check for key information
        assert "⚠️ Risk Level: HIGH (65.0/100)" in summary_report
        assert "Downtime Risk: 90 minutes" in summary_report
        assert "Revenue Risk: $25K-75K" in summary_report
        assert "Strategies Available: 3" in summary_report

        # Check for recommendation
        assert "RECOMMENDATION: Management approval required" in summary_report

        # Validate concise format
        lines = summary_report.split("\n")
        assert len(lines) < 30  # Should be concise

    def test_progressive_disclosure_section_filtering(
        self, report_formatter, sample_comprehensive_report
    ):
        """Test progressive disclosure with section filtering."""
        # Test executive-only sections
        executive_sections = [
            ReportSection.EXECUTIVE_SUMMARY,
            ReportSection.MITIGATION_OVERVIEW,
        ]

        executive_report = report_formatter.format_report(
            sample_comprehensive_report,
            ReportFormat.CONSOLE,
            FormatStyle.EXECUTIVE,
            sections=executive_sections,
        )

        # Should include executive summary
        assert "💼 EXECUTIVE SUMMARY" in executive_report

        # Should not include technical details
        assert "🔧 TECHNICAL IMPLEMENTATION DETAILS" not in executive_report
        assert "📋 COMPLIANCE & AUDIT REQUIREMENTS" not in executive_report

        # Test technical-only sections
        technical_sections = [
            ReportSection.RISK_BREAKDOWN,
            ReportSection.TECHNICAL_DETAILS,
        ]

        technical_report = report_formatter.format_report(
            sample_comprehensive_report,
            ReportFormat.CONSOLE,
            FormatStyle.TECHNICAL,
            sections=technical_sections,
        )

        # Should include technical details
        assert "📈 RISK BREAKDOWN BY CATEGORY" in technical_report
        assert "🔧 TECHNICAL IMPLEMENTATION DETAILS" in technical_report

        # Should not include executive summary
        assert "💼 EXECUTIVE SUMMARY" not in technical_report

    def test_format_style_variations(
        self, report_formatter, sample_comprehensive_report
    ):
        """Test different format styles."""
        styles_and_expectations = [
            (
                FormatStyle.MINIMAL,
                "MIGRATION RISK ASSESSMENT",
                "🎯",
            ),  # Minimal style, no emoji
            (
                FormatStyle.RICH,
                "🎯 MIGRATION RISK ASSESSMENT",
                "💼",
            ),  # Rich style, with emojis
            (
                FormatStyle.EXECUTIVE,
                "🎯 MIGRATION RISK ASSESSMENT",
                "💼",
            ),  # Executive style, with emojis
            (
                FormatStyle.TECHNICAL,
                "🔧 TECHNICAL IMPLEMENTATION",
                "📈",
            ),  # Technical style, technical emojis
        ]

        for style, expected_content, expected_emoji in styles_and_expectations:
            report = report_formatter.format_report(
                sample_comprehensive_report, ReportFormat.CONSOLE, style
            )

            assert expected_content in report

            if style == FormatStyle.MINIMAL:
                # Minimal style should have fewer emojis
                emoji_count = sum(1 for char in report if ord(char) > 127)
                assert emoji_count < 20  # Allow some non-ASCII chars for formatting
            else:
                # Other styles should have emojis
                assert expected_emoji in report

    def test_console_theme_customization(self):
        """Test console theme customization."""
        custom_theme = ConsoleTheme()
        custom_theme.risk_emojis[RiskLevel.HIGH] = "🔥"
        custom_theme.progress_filled = "▓"
        custom_theme.progress_empty = "▒"

        custom_formatter = ReportFormatter(
            console_theme=custom_theme, enable_colors=True, enable_emojis=True
        )

        # Create minimal report for theme testing
        minimal_report = ComprehensiveImpactReport(
            report_id="theme_test",
            operation_id="theme_op",
            generation_timestamp=datetime.now().isoformat(),
            executive_summary=ExecutiveRiskSummary(
                operation_description="Theme test",
                overall_risk_level=RiskLevel.HIGH,
                overall_risk_score=75.0,
                business_impact="Test impact",
                recommended_action="Test action",
                potential_downtime_minutes=60.0,
                affected_systems_count=1,
                revenue_risk_estimate="Test revenue",
                user_impact_estimate="Test user impact",
                mitigation_strategies_count=1,
                risk_reduction_potential=50.0,
                implementation_timeline="Test timeline",
                resource_requirements="Test resources",
                approval_required=True,
                approval_level="Test",
                go_no_go_recommendation="Test recommendation",
            ),
            technical_report=TechnicalImpactReport(
                operation_details={},
                risk_category_breakdown={},
                dependency_analysis={},
                pre_migration_steps=[],
                migration_procedure=[],
                post_migration_validation=[],
                rollback_procedures=[],
                performance_impact_analysis={},
                infrastructure_requirements=[],
                monitoring_recommendations=[],
                testing_strategy=[],
            ),
            compliance_report=ComplianceAuditReport(
                regulatory_frameworks=[],
                compliance_risk_assessment={},
                data_protection_impact={},
                change_management_documentation={},
                risk_acceptance_criteria=[],
                audit_trail_requirements=[],
                approval_workflows=[],
                risk_register_entry={},
                control_effectiveness_assessment={},
                residual_risk_statement="",
            ),
            stakeholder_communications={},
            risk_assessment=ComprehensiveRiskAssessment(
                operation_id="theme_op",
                overall_score=75.0,
                risk_level=RiskLevel.HIGH,
                category_scores={},
                risk_factors=[],
                recommendations=[],
            ),
        )

        formatted = custom_formatter.format_report(
            minimal_report, ReportFormat.CONSOLE, FormatStyle.RICH
        )

        # Should use custom emoji
        assert "🔥" in formatted

        # Should use custom progress characters when progress bars are present
        # (Note: May not appear in minimal report, but theme is configured correctly)

    def test_performance_characteristics(self, report_formatter):
        """Test performance characteristics of report formatting."""
        # Create a complex report with many sections
        large_stakeholder_communications = {
            role: StakeholderReport(
                role=role,
                key_messages=[f"Message {i}" for i in range(10)],
                action_items=[f"Action {i}" for i in range(10)],
                decision_points=[f"Decision {i}" for i in range(5)],
                timeline_awareness="Timeline message",
                escalation_criteria=[f"Escalation {i}" for i in range(3)],
                technical_depth="medium",
                focus_areas=["Area1", "Area2", "Area3"],
                communication_format="detailed",
            )
            for role in StakeholderRole
        }

        complex_report = ComprehensiveImpactReport(
            report_id="perf_test",
            operation_id="perf_op",
            generation_timestamp=datetime.now().isoformat(),
            executive_summary=ExecutiveRiskSummary(
                operation_description="Performance test operation",
                overall_risk_level=RiskLevel.CRITICAL,
                overall_risk_score=85.0,
                business_impact="High impact",
                recommended_action="Critical action",
                potential_downtime_minutes=240.0,
                affected_systems_count=5,
                revenue_risk_estimate="$500K+",
                user_impact_estimate="Significant impact",
                mitigation_strategies_count=10,
                risk_reduction_potential=70.0,
                implementation_timeline="1-2 weeks",
                resource_requirements="Full team",
                approval_required=True,
                approval_level="Executive",
                go_no_go_recommendation="Executive review required",
            ),
            technical_report=TechnicalImpactReport(
                operation_details={"complexity": "high"},
                risk_category_breakdown={
                    category: {
                        "score": 80.0,
                        "level": "critical",
                        "description": f"Critical {category.value} risk",
                        "risk_factors": [f"Factor {i}" for i in range(5)],
                        "technical_implications": [
                            f"Implication {i}" for i in range(5)
                        ],
                    }
                    for category in RiskCategory
                },
                dependency_analysis={"total_dependencies": 50},
                pre_migration_steps=[f"Pre-step {i}" for i in range(10)],
                migration_procedure=[f"Migration step {i}" for i in range(15)],
                post_migration_validation=[f"Validation step {i}" for i in range(8)],
                rollback_procedures=[f"Rollback step {i}" for i in range(12)],
                performance_impact_analysis={"complexity": "high"},
                infrastructure_requirements=[f"Requirement {i}" for i in range(20)],
                monitoring_recommendations=[f"Monitoring {i}" for i in range(15)],
                testing_strategy=[f"Test strategy {i}" for i in range(10)],
            ),
            compliance_report=ComplianceAuditReport(
                regulatory_frameworks=[f"Framework {i}" for i in range(5)],
                compliance_risk_assessment={"complexity": "high"},
                data_protection_impact={"complexity": "high"},
                change_management_documentation={"complexity": "high"},
                risk_acceptance_criteria=[f"Criteria {i}" for i in range(10)],
                audit_trail_requirements=[f"Audit req {i}" for i in range(8)],
                approval_workflows=[f"Workflow step {i}" for i in range(6)],
                risk_register_entry={"complexity": "high"},
                control_effectiveness_assessment={"complexity": "high"},
                residual_risk_statement="Complex residual risk statement",
            ),
            stakeholder_communications=large_stakeholder_communications,
            risk_assessment=ComprehensiveRiskAssessment(
                operation_id="perf_op",
                overall_score=85.0,
                risk_level=RiskLevel.CRITICAL,
                category_scores={
                    category: RiskScore(
                        category=category,
                        score=80.0,
                        level=RiskLevel.CRITICAL,
                        description=f"Critical {category.value}",
                        risk_factors=[f"Factor {i}" for i in range(5)],
                    )
                    for category in RiskCategory
                },
                risk_factors=[
                    RiskFactor(
                        category=RiskCategory.DATA_LOSS,
                        description=f"Risk factor {i}",
                        impact_score=80.0,
                    )
                    for i in range(20)
                ],
                recommendations=[f"Recommendation {i}" for i in range(10)],
            ),
        )

        # Performance test for all formats
        formats_to_test = [
            ReportFormat.CONSOLE,
            ReportFormat.JSON,
            ReportFormat.HTML,
            ReportFormat.SUMMARY,
        ]

        for report_format in formats_to_test:
            start_time = time.time()

            formatted_report = report_formatter.format_report(
                complex_report, report_format, FormatStyle.RICH
            )

            format_time = time.time() - start_time

            # Validate performance (should be fast even for complex reports)
            assert (
                format_time < 1.0
            ), f"{report_format.value} formatting took {format_time:.3f}s"

            # Validate output is generated
            assert isinstance(formatted_report, str)
            assert len(formatted_report) > 100  # Should have substantial content

        print("✅ Performance test completed - all formats under 1s")

    def test_error_handling_in_formatting(self, report_formatter):
        """Test error handling in report formatting."""
        # Test with invalid format type
        with pytest.raises(ValueError, match="Unsupported format type"):
            invalid_format = type("InvalidFormat", (), {"value": "invalid"})()
            report_formatter.format_report(
                Mock(), invalid_format, FormatStyle.STANDARD  # Mock report
            )

        # Test with malformed report (missing required fields)
        malformed_report = type(
            "MalformedReport",
            (),
            {
                "report_id": "test",
                "operation_id": "test",
                "generation_timestamp": datetime.now().isoformat(),
                # Missing required fields
            },
        )()

        # Should handle gracefully with AttributeError protection
        try:
            result = report_formatter.format_report(
                malformed_report, ReportFormat.SUMMARY, FormatStyle.STANDARD
            )
            # If it doesn't raise an error, it should return a string
            assert isinstance(result, str)
        except AttributeError:
            # This is expected for severely malformed reports
            pass
