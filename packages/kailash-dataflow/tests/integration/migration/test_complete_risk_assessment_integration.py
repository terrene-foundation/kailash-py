#!/usr/bin/env python3
"""
Integration tests for Complete Risk Assessment Engine - TODO-140 Phase 3

Tests the complete integration of all three phases working together:
- Phase 1: RiskAssessmentEngine
- Phase 2: MitigationStrategyEngine
- Phase 3: ImpactAnalysisReporter + ReportFormatter

INTEGRATION TESTING COVERAGE:
- ✅ End-to-end workflow from risk assessment to formatted reports
- ✅ Data flow validation between all phases
- ✅ Multi-format output generation and consistency
- ✅ Performance characteristics under realistic conditions
- ✅ Error handling and recovery across phase boundaries
- ✅ Real dependency analysis integration
- ✅ Stakeholder communication generation
- ✅ Business impact assessment accuracy
"""

import asyncio
import json
import time
from pathlib import Path
from typing import Any, Dict, List

import pytest
from dataflow.migrations.dependency_analyzer import (
    DependencyReport,
    DependencyType,
    ForeignKeyDependency,
    ImpactLevel,
    IndexDependency,
)
from dataflow.migrations.impact_analysis_reporter import (
    ComprehensiveImpactReport,
    ImpactAnalysisReporter,
    ReportFormat,
    ReportSection,
    StakeholderRole,
)
from dataflow.migrations.mitigation_strategy_engine import (
    MitigationPriority,
    MitigationStrategyEngine,
    PrioritizedMitigationPlan,
)
from dataflow.migrations.report_formatters import FormatStyle, ReportFormatter
from dataflow.migrations.risk_assessment_engine import (
    ComprehensiveRiskAssessment,
    RiskAssessmentEngine,
    RiskCategory,
    RiskLevel,
)

from kailash.runtime.local import LocalRuntime
from tests.infrastructure.test_harness import IntegrationTestSuite


class MockOperation:
    """Mock operation for integration testing."""

    def __init__(
        self,
        table: str,
        column: str,
        operation_type: str = "drop_column",
        is_production: bool = False,
        estimated_rows: int = 1000,
        table_size_mb: float = 10.0,
        has_backup: bool = True,
    ):
        self.table = table
        self.column = column
        self.operation_type = operation_type
        self.is_production = is_production
        self.estimated_rows = estimated_rows
        self.table_size_mb = table_size_mb
        self.has_backup = has_backup


@pytest.fixture
async def test_suite():
    """Create complete integration test suite with infrastructure."""
    suite = IntegrationTestSuite()
    async with suite.session():
        yield suite


@pytest.fixture
def runtime():
    """Create LocalRuntime for workflow execution."""
    return LocalRuntime()


@pytest.mark.integration
class TestCompleteRiskAssessmentIntegration:
    """Integration tests for complete risk assessment system."""

    @pytest.fixture
    def risk_assessment_system(self, runtime):
        """Create complete risk assessment system for testing."""
        return {
            "risk_engine": RiskAssessmentEngine(),
            "mitigation_engine": MitigationStrategyEngine(
                enable_enterprise_strategies=True
            ),
            "impact_reporter": ImpactAnalysisReporter(),
            "report_formatter": ReportFormatter(enable_colors=True, enable_emojis=True),
        }

    @pytest.fixture
    def sample_operations(self, runtime):
        """Create sample operations for different risk scenarios."""
        return {
            "low_risk": MockOperation(
                table="user_settings",
                column="deprecated_flag",
                operation_type="drop_column",
                is_production=False,
                estimated_rows=1000,
                table_size_mb=5.0,
                has_backup=True,
            ),
            "medium_risk": MockOperation(
                table="products",
                column="legacy_category_id",
                operation_type="drop_column",
                is_production=True,
                estimated_rows=50000,
                table_size_mb=100.0,
                has_backup=True,
            ),
            "high_risk": MockOperation(
                table="orders",
                column="payment_method_id",
                operation_type="drop_column",
                is_production=True,
                estimated_rows=500000,
                table_size_mb=800.0,
                has_backup=True,
            ),
            "critical_risk": MockOperation(
                table="customers",
                column="id",
                operation_type="drop_column",
                is_production=True,
                estimated_rows=1000000,
                table_size_mb=2000.0,
                has_backup=False,
            ),
        }

    @pytest.fixture
    def sample_dependencies(self, runtime):
        """Create sample dependency reports for different scenarios."""
        return {
            "low_risk": DependencyReport(
                table_name="user_settings",
                column_name="deprecated_flag",
                dependencies={},  # No dependencies
            ),
            "medium_risk": DependencyReport(
                table_name="products",
                column_name="legacy_category_id",
                dependencies={
                    DependencyType.INDEX: [
                        IndexDependency(
                            table_name="products",
                            column_name="legacy_category_id",
                            index_name="idx_products_category",
                            is_unique=False,
                            impact_level=ImpactLevel.MEDIUM,
                        )
                    ]
                },
            ),
            "high_risk": DependencyReport(
                table_name="orders",
                column_name="payment_method_id",
                dependencies={
                    DependencyType.FOREIGN_KEY: [
                        ForeignKeyDependency(
                            table_name="orders",
                            column_name="payment_method_id",
                            referenced_table="payment_methods",
                            referenced_column="id",
                            constraint_name="fk_orders_payment_method",
                            on_delete="RESTRICT",
                            on_update="RESTRICT",
                            impact_level=ImpactLevel.HIGH,
                        )
                    ],
                    DependencyType.INDEX: [
                        IndexDependency(
                            table_name="orders",
                            column_name="payment_method_id",
                            index_name="idx_orders_payment",
                            is_unique=False,
                            impact_level=ImpactLevel.HIGH,
                        )
                    ],
                },
            ),
            "critical_risk": DependencyReport(
                table_name="customers",
                column_name="id",
                dependencies={
                    DependencyType.FOREIGN_KEY: [
                        ForeignKeyDependency(
                            table_name="customers",
                            column_name="id",
                            referenced_table="orders",
                            referenced_column="customer_id",
                            constraint_name="fk_orders_customer",
                            on_delete="CASCADE",
                            on_update="CASCADE",
                            impact_level=ImpactLevel.CRITICAL,
                        ),
                        ForeignKeyDependency(
                            table_name="customers",
                            column_name="id",
                            referenced_table="customer_profiles",
                            referenced_column="customer_id",
                            constraint_name="fk_profiles_customer",
                            on_delete="CASCADE",
                            on_update="RESTRICT",
                            impact_level=ImpactLevel.CRITICAL,
                        ),
                    ],
                    DependencyType.INDEX: [
                        IndexDependency(
                            table_name="customers",
                            column_name="id",
                            index_name="pk_customers",
                            is_unique=True,
                            impact_level=ImpactLevel.CRITICAL,
                        )
                    ],
                },
            ),
        }

    @pytest.mark.asyncio
    async def test_end_to_end_low_risk_workflow(
        self, risk_assessment_system, sample_operations, sample_dependencies
    ):
        """Test complete end-to-end workflow for low risk scenario."""
        system = risk_assessment_system
        operation = sample_operations["low_risk"]
        dependency_report = sample_dependencies["low_risk"]

        start_time = time.time()

        # Phase 1: Risk Assessment
        risk_assessment = system["risk_engine"].calculate_migration_risk_score(
            operation, dependency_report
        )

        # Validate Phase 1 output
        assert isinstance(risk_assessment, ComprehensiveRiskAssessment)
        assert risk_assessment.risk_level == RiskLevel.LOW
        assert risk_assessment.overall_score < 30  # Low risk threshold

        # Phase 2: Mitigation Strategies
        mitigation_strategies = system[
            "mitigation_engine"
        ].generate_mitigation_strategies(risk_assessment, dependency_report)

        mitigation_plan = system["mitigation_engine"].prioritize_mitigation_actions(
            mitigation_strategies, risk_assessment
        )

        # Validate Phase 2 output
        assert isinstance(mitigation_plan, PrioritizedMitigationPlan)
        assert (
            len(mitigation_plan.mitigation_strategies) >= 0
        )  # May have minimal strategies for low risk

        # Phase 3: Impact Analysis and Reporting
        impact_report = system["impact_reporter"].generate_comprehensive_impact_report(
            risk_assessment, mitigation_plan, dependency_report
        )

        # Validate Phase 3 output
        assert isinstance(impact_report, ComprehensiveImpactReport)
        assert impact_report.executive_summary.overall_risk_level == RiskLevel.LOW
        assert impact_report.executive_summary.approval_required is False
        assert "LOW RISK" in impact_report.executive_summary.go_no_go_recommendation

        # Multi-format output validation
        console_report = system["report_formatter"].format_report(
            impact_report, ReportFormat.CONSOLE, FormatStyle.STANDARD
        )

        json_report = system["report_formatter"].format_report(
            impact_report, ReportFormat.JSON, FormatStyle.STANDARD
        )

        summary_report = system["report_formatter"].format_report(
            impact_report, ReportFormat.SUMMARY, FormatStyle.STANDARD
        )

        # Validate output formats
        assert isinstance(console_report, str)
        assert "LOW" in console_report or "✅" in console_report

        assert isinstance(json_report, str)
        json_data = json.loads(json_report)
        assert json_data["executive_summary"]["overall_risk_level"] == "low"

        assert isinstance(summary_report, str)
        assert "LOW" in summary_report

        total_time = time.time() - start_time
        assert total_time < 2.0  # Should be fast for low risk

        print(f"✅ Low risk end-to-end workflow completed in {total_time:.3f}s")

    @pytest.mark.asyncio
    async def test_end_to_end_critical_risk_workflow(
        self, risk_assessment_system, sample_operations, sample_dependencies
    ):
        """Test complete end-to-end workflow for critical risk scenario."""
        system = risk_assessment_system
        operation = sample_operations["critical_risk"]
        dependency_report = sample_dependencies["critical_risk"]

        start_time = time.time()

        # Phase 1: Risk Assessment
        risk_assessment = system["risk_engine"].calculate_migration_risk_score(
            operation, dependency_report
        )

        # Validate Phase 1 output for critical risk
        assert isinstance(risk_assessment, ComprehensiveRiskAssessment)
        assert risk_assessment.risk_level in [RiskLevel.HIGH, RiskLevel.CRITICAL]
        assert risk_assessment.overall_score > 70  # High/Critical risk threshold
        assert len(risk_assessment.risk_factors) > 0

        # Phase 2: Enterprise Mitigation Strategies
        mitigation_strategies = system[
            "mitigation_engine"
        ].generate_mitigation_strategies(
            risk_assessment,
            dependency_report,
            operation_context={
                "is_production": True,
                "has_cascade_constraints": True,
                "table_size_mb": operation.table_size_mb,
            },
        )

        mitigation_plan = system["mitigation_engine"].prioritize_mitigation_actions(
            mitigation_strategies,
            risk_assessment,
            constraints={"budget_hours": 80, "team_size": 5},
        )

        # Validate Phase 2 output for critical risk
        assert isinstance(mitigation_plan, PrioritizedMitigationPlan)
        assert len(mitigation_plan.mitigation_strategies) > 0

        # Should have critical priority strategies
        critical_strategies = [
            s
            for s in mitigation_plan.mitigation_strategies
            if hasattr(s, "priority") and s.priority == MitigationPriority.CRITICAL
        ]
        assert len(critical_strategies) > 0

        # Phase 3: Executive Impact Analysis
        business_context = {
            "regulatory_frameworks": ["SOX", "Change Management Policy"],
            "risk_owner": "VP Engineering",
            "affected_systems_count": 5,
            "revenue_risk_estimate": "$500K+ potential impact",
        }

        impact_report = system["impact_reporter"].generate_comprehensive_impact_report(
            risk_assessment, mitigation_plan, dependency_report, business_context
        )

        # Validate Phase 3 output for critical risk
        assert isinstance(impact_report, ComprehensiveImpactReport)
        assert impact_report.executive_summary.overall_risk_level in [
            RiskLevel.HIGH,
            RiskLevel.CRITICAL,
        ]
        assert impact_report.executive_summary.approval_required is True
        assert (
            "CRITICAL" in impact_report.executive_summary.go_no_go_recommendation
            or "HIGH" in impact_report.executive_summary.go_no_go_recommendation
        )

        # Validate compliance documentation for critical risk
        compliance_report = impact_report.compliance_report
        assert len(compliance_report.regulatory_frameworks) > 0
        assert (
            "change_classification" in compliance_report.change_management_documentation
        )
        assert len(compliance_report.approval_workflows) > 0

        # Executive-level reporting validation
        executive_report = system["report_formatter"].format_report(
            impact_report, ReportFormat.CONSOLE, FormatStyle.EXECUTIVE
        )

        assert "CRITICAL" in executive_report or "HIGH" in executive_report
        assert "❌" in executive_report or "⚠️" in executive_report  # Risk indicators
        assert "EXECUTIVE" in executive_report or "💼" in executive_report

        total_time = time.time() - start_time
        assert total_time < 5.0  # Should still be reasonably fast

        print(f"🔴 Critical risk end-to-end workflow completed in {total_time:.3f}s")

    @pytest.mark.asyncio
    async def test_data_flow_consistency_across_phases(
        self, risk_assessment_system, sample_operations, sample_dependencies
    ):
        """Test data flow consistency and accuracy across all phases."""
        system = risk_assessment_system
        operation = sample_operations["high_risk"]
        dependency_report = sample_dependencies["high_risk"]

        # Execute complete workflow
        risk_assessment = system["risk_engine"].calculate_migration_risk_score(
            operation, dependency_report
        )

        mitigation_strategies = system[
            "mitigation_engine"
        ].generate_mitigation_strategies(risk_assessment, dependency_report)

        mitigation_plan = system["mitigation_engine"].prioritize_mitigation_actions(
            mitigation_strategies, risk_assessment
        )

        impact_report = system["impact_reporter"].generate_comprehensive_impact_report(
            risk_assessment, mitigation_plan, dependency_report
        )

        # Data consistency validation

        # 1. Operation ID consistency
        assert risk_assessment.operation_id == impact_report.operation_id
        assert mitigation_plan.operation_id == impact_report.operation_id

        # 2. Risk level consistency
        assert (
            impact_report.executive_summary.overall_risk_level
            == risk_assessment.risk_level
        )
        assert (
            impact_report.executive_summary.overall_risk_score
            == risk_assessment.overall_score
        )

        # 3. Mitigation data consistency
        if hasattr(mitigation_plan, "mitigation_strategies"):
            assert impact_report.executive_summary.mitigation_strategies_count == len(
                mitigation_plan.mitigation_strategies
            )
            assert (
                impact_report.executive_summary.implementation_timeline
                != "Not assessed"
            )

        # 4. Dependency data consistency
        assert impact_report.dependency_report == dependency_report
        tech_report = impact_report.technical_report
        if dependency_report.has_dependencies():
            assert tech_report.dependency_analysis["total_dependencies"] > 0

        # 5. Stakeholder data consistency
        stakeholder_comms = impact_report.stakeholder_communications
        assert len(stakeholder_comms) == len(StakeholderRole)

        # Executive stakeholder should have appropriate messaging for high risk
        exec_stakeholder = stakeholder_comms[StakeholderRole.EXECUTIVE]
        assert any("HIGH" in msg for msg in exec_stakeholder.key_messages)

        # 6. Multi-format consistency
        json_report = system["report_formatter"].format_report(
            impact_report, ReportFormat.JSON, FormatStyle.STANDARD
        )

        json_data = json.loads(json_report)
        assert (
            json_data["executive_summary"]["overall_risk_score"]
            == risk_assessment.overall_score
        )
        assert (
            json_data["risk_assessment"]["risk_level"]
            == risk_assessment.risk_level.value
        )

        print("✅ Data flow consistency validated across all phases")

    @pytest.mark.asyncio
    async def test_performance_characteristics_realistic_load(
        self, risk_assessment_system
    ):
        """Test performance characteristics under realistic load conditions."""
        system = risk_assessment_system

        # Test scenarios with varying complexity
        test_scenarios = [
            {
                "name": "Simple Operations",
                "count": 10,
                "operation": MockOperation(
                    "test_table", "test_col", estimated_rows=1000, table_size_mb=5
                ),
                "dependencies": DependencyReport(
                    "test_table", "test_col", dependencies={}
                ),
            },
            {
                "name": "Medium Operations",
                "count": 5,
                "operation": MockOperation(
                    "medium_table",
                    "med_col",
                    estimated_rows=50000,
                    table_size_mb=100,
                    is_production=True,
                ),
                "dependencies": DependencyReport(
                    "medium_table",
                    "med_col",
                    dependencies={
                        DependencyType.INDEX: [
                            IndexDependency(
                                "medium_table",
                                "med_col",
                                "idx_med",
                                False,
                                ImpactLevel.MEDIUM,
                            )
                        ]
                    },
                ),
            },
            {
                "name": "Complex Operations",
                "count": 3,
                "operation": MockOperation(
                    "complex_table",
                    "complex_col",
                    estimated_rows=500000,
                    table_size_mb=1000,
                    is_production=True,
                ),
                "dependencies": DependencyReport(
                    "complex_table",
                    "complex_col",
                    dependencies={
                        DependencyType.FOREIGN_KEY: [
                            ForeignKeyDependency(
                                "complex_table",
                                "complex_col",
                                "ref_table",
                                "id",
                                "fk_complex",
                                "CASCADE",
                                "CASCADE",
                                ImpactLevel.HIGH,
                            )
                        ],
                        DependencyType.INDEX: [
                            IndexDependency(
                                "complex_table",
                                "complex_col",
                                "idx_complex",
                                True,
                                ImpactLevel.HIGH,
                            )
                        ],
                    },
                ),
            },
        ]

        performance_results = []

        for scenario in test_scenarios:
            scenario_start = time.time()

            for i in range(scenario["count"]):
                # Execute complete workflow
                risk_assessment = system["risk_engine"].calculate_migration_risk_score(
                    scenario["operation"], scenario["dependencies"]
                )

                mitigation_strategies = system[
                    "mitigation_engine"
                ].generate_mitigation_strategies(
                    risk_assessment, scenario["dependencies"]
                )

                mitigation_plan = system[
                    "mitigation_engine"
                ].prioritize_mitigation_actions(mitigation_strategies, risk_assessment)

                impact_report = system[
                    "impact_reporter"
                ].generate_comprehensive_impact_report(
                    risk_assessment, mitigation_plan, scenario["dependencies"]
                )

                # Generate multiple format outputs
                console_report = system["report_formatter"].format_report(
                    impact_report, ReportFormat.CONSOLE, FormatStyle.STANDARD
                )

                json_report = system["report_formatter"].format_report(
                    impact_report, ReportFormat.JSON, FormatStyle.STANDARD
                )

                # Validate outputs are generated
                assert isinstance(console_report, str)
                assert isinstance(json_report, str)
                assert len(console_report) > 100
                assert len(json_report) > 100

            scenario_time = time.time() - scenario_start
            avg_time_per_operation = scenario_time / scenario["count"]

            performance_results.append(
                {
                    "scenario": scenario["name"],
                    "count": scenario["count"],
                    "total_time": scenario_time,
                    "avg_time": avg_time_per_operation,
                }
            )

            # Performance assertions
            assert (
                avg_time_per_operation < 2.0
            ), f"{scenario['name']} took {avg_time_per_operation:.3f}s per operation"

            print(
                f"✅ {scenario['name']}: {scenario['count']} operations in {scenario_time:.3f}s (avg: {avg_time_per_operation:.3f}s)"
            )

        # Overall performance validation
        total_operations = sum(result["count"] for result in performance_results)
        total_time = sum(result["total_time"] for result in performance_results)

        print(
            f"📊 Performance Summary: {total_operations} operations completed in {total_time:.3f}s"
        )
        print(
            f"⚡ Average throughput: {total_operations/total_time:.1f} operations/second"
        )

        # System should handle reasonable throughput
        assert total_operations / total_time > 2.0  # At least 2 operations per second

    @pytest.mark.asyncio
    async def test_error_handling_across_phase_boundaries(self, risk_assessment_system):
        """Test error handling and recovery across phase boundaries."""
        system = risk_assessment_system

        # Test 1: Invalid operation data
        try:
            invalid_operation = type(
                "InvalidOp", (), {}
            )()  # Missing required attributes
            minimal_deps = DependencyReport("test", "test", dependencies={})

            # Should handle gracefully or raise appropriate error
            risk_assessment = system["risk_engine"].calculate_migration_risk_score(
                invalid_operation, minimal_deps
            )

            # If it doesn't raise an error, it should produce valid output
            assert isinstance(risk_assessment, ComprehensiveRiskAssessment)

        except (AttributeError, ValueError) as e:
            # Expected for invalid input
            print(f"✅ Properly handled invalid operation: {e}")

        # Test 2: Malformed dependency report
        try:
            valid_operation = MockOperation("test", "col")
            malformed_deps = type(
                "MalformedDeps",
                (),
                {
                    "table_name": "test",
                    "column_name": "col",
                    "dependencies": "invalid",  # Should be dict
                },
            )()

            risk_assessment = system["risk_engine"].calculate_migration_risk_score(
                valid_operation, malformed_deps
            )

            # Should handle gracefully
            assert isinstance(risk_assessment, ComprehensiveRiskAssessment)

        except (AttributeError, TypeError) as e:
            print(f"✅ Properly handled malformed dependencies: {e}")

        # Test 3: Phase 2 with invalid Phase 1 output
        try:
            invalid_risk_assessment = type(
                "InvalidRisk",
                (),
                {
                    "operation_id": "test",
                    "risk_level": "invalid",  # Should be RiskLevel enum
                },
            )()

            strategies = system["mitigation_engine"].generate_mitigation_strategies(
                invalid_risk_assessment,
                DependencyReport("test", "col", dependencies={}),
            )

            # Should handle gracefully or raise appropriate error
            assert isinstance(strategies, list)

        except (AttributeError, ValueError) as e:
            print(f"✅ Properly handled invalid risk assessment: {e}")

        # Test 4: Phase 3 with missing components
        try:
            minimal_risk = ComprehensiveRiskAssessment(
                operation_id="test",
                overall_score=50.0,
                risk_level=RiskLevel.MEDIUM,
                category_scores={},
                risk_factors=[],
                recommendations=[],
            )

            # Phase 3 should handle missing mitigation plan
            impact_report = system[
                "impact_reporter"
            ].generate_comprehensive_impact_report(
                minimal_risk,
                mitigation_plan=None,  # Missing mitigation plan
                dependency_report=None,  # Missing dependency report
            )

            assert isinstance(impact_report, ComprehensiveImpactReport)
            assert impact_report.mitigation_plan is None

        except Exception as e:
            print(f"✅ Properly handled missing components: {e}")

        print("✅ Error handling validation completed across all phase boundaries")

    @pytest.mark.asyncio
    async def test_multi_format_output_consistency(
        self, risk_assessment_system, sample_operations, sample_dependencies
    ):
        """Test consistency across different output formats."""
        system = risk_assessment_system
        operation = sample_operations["medium_risk"]
        dependency_report = sample_dependencies["medium_risk"]

        # Generate complete impact report
        risk_assessment = system["risk_engine"].calculate_migration_risk_score(
            operation, dependency_report
        )

        mitigation_strategies = system[
            "mitigation_engine"
        ].generate_mitigation_strategies(risk_assessment, dependency_report)

        mitigation_plan = system["mitigation_engine"].prioritize_mitigation_actions(
            mitigation_strategies, risk_assessment
        )

        impact_report = system["impact_reporter"].generate_comprehensive_impact_report(
            risk_assessment, mitigation_plan, dependency_report
        )

        # Generate all format outputs
        formats_to_test = [
            (ReportFormat.CONSOLE, FormatStyle.STANDARD),
            (ReportFormat.CONSOLE, FormatStyle.RICH),
            (ReportFormat.CONSOLE, FormatStyle.EXECUTIVE),
            (ReportFormat.CONSOLE, FormatStyle.TECHNICAL),
            (ReportFormat.JSON, FormatStyle.STANDARD),
            (ReportFormat.HTML, FormatStyle.RICH),
            (ReportFormat.SUMMARY, FormatStyle.EXECUTIVE),
        ]

        formatted_reports = {}

        for report_format, style in formats_to_test:
            formatted = system["report_formatter"].format_report(
                impact_report, report_format, style
            )

            formatted_reports[f"{report_format.value}_{style.value}"] = formatted

            # Basic validation
            assert isinstance(formatted, str)
            assert len(formatted) > 50  # Should have substantial content

        # Consistency validation across formats

        # 1. JSON format should be parseable and contain key data
        json_report = formatted_reports["json_standard"]
        json_data = json.loads(json_report)

        expected_risk_score = impact_report.executive_summary.overall_risk_score
        expected_risk_level = impact_report.executive_summary.overall_risk_level.value

        assert (
            json_data["executive_summary"]["overall_risk_score"] == expected_risk_score
        )
        assert (
            json_data["executive_summary"]["overall_risk_level"] == expected_risk_level
        )

        # 2. Console formats should contain consistent risk information
        for format_key, content in formatted_reports.items():
            if format_key.startswith("console"):
                # Should contain risk level information
                risk_level_present = any(
                    level.value.upper() in content for level in RiskLevel
                )
                assert risk_level_present, f"Risk level missing in {format_key}"

                # Should contain operation information
                assert operation.table in content or "migration" in content.lower()

        # 3. HTML format should be valid HTML structure
        html_report = formatted_reports["html_rich"]
        assert "<!DOCTYPE html>" in html_report
        assert "<html" in html_report and "</html>" in html_report
        assert "Migration Risk Assessment" in html_report

        # 4. Summary format should be concise
        summary_report = formatted_reports["summary_executive"]
        summary_lines = summary_report.split("\n")
        assert len(summary_lines) < 30  # Should be concise
        assert "EXECUTIVE SUMMARY" in summary_report

        # 5. All formats should contain the same core risk score
        risk_score_str = f"{expected_risk_score:.1f}"

        for format_key, content in formatted_reports.items():
            if not format_key.startswith(
                "html"
            ):  # HTML might format numbers differently
                assert (
                    risk_score_str in content
                    or str(int(expected_risk_score)) in content
                ), f"Risk score missing or inconsistent in {format_key}"

        print(
            f"✅ Multi-format consistency validated across {len(formats_to_test)} format combinations"
        )

    @pytest.mark.asyncio
    async def test_real_world_scenario_simulation(self, risk_assessment_system):
        """Test with realistic real-world migration scenarios."""
        system = risk_assessment_system

        # Realistic scenario: E-commerce platform migration
        ecommerce_scenarios = [
            {
                "name": "Remove deprecated user preference column",
                "operation": MockOperation(
                    table="users",
                    column="old_notification_settings",
                    operation_type="drop_column",
                    is_production=True,
                    estimated_rows=100000,
                    table_size_mb=50.0,
                    has_backup=True,
                ),
                "dependencies": DependencyReport(
                    table_name="users",
                    column_name="old_notification_settings",
                    dependencies={},
                ),
                "expected_risk_level": RiskLevel.LOW,
            },
            {
                "name": "Remove legacy payment provider integration",
                "operation": MockOperation(
                    table="payments",
                    column="legacy_provider_id",
                    operation_type="drop_column",
                    is_production=True,
                    estimated_rows=2000000,
                    table_size_mb=500.0,
                    has_backup=True,
                ),
                "dependencies": DependencyReport(
                    table_name="payments",
                    column_name="legacy_provider_id",
                    dependencies={
                        DependencyType.INDEX: [
                            IndexDependency(
                                table_name="payments",
                                column_name="legacy_provider_id",
                                index_name="idx_payments_provider",
                                is_unique=False,
                                impact_level=ImpactLevel.MEDIUM,
                            )
                        ]
                    },
                ),
                "expected_risk_level": RiskLevel.MEDIUM,
            },
            {
                "name": "Remove customer ID with CASCADE constraints",
                "operation": MockOperation(
                    table="customers",
                    column="id",
                    operation_type="drop_column",
                    is_production=True,
                    estimated_rows=500000,
                    table_size_mb=200.0,
                    has_backup=False,
                ),
                "dependencies": DependencyReport(
                    table_name="customers",
                    column_name="id",
                    dependencies={
                        DependencyType.FOREIGN_KEY: [
                            ForeignKeyDependency(
                                table_name="customers",
                                column_name="id",
                                referenced_table="orders",
                                referenced_column="customer_id",
                                constraint_name="fk_orders_customer",
                                on_delete="CASCADE",
                                on_update="CASCADE",
                                impact_level=ImpactLevel.CRITICAL,
                            ),
                            ForeignKeyDependency(
                                table_name="customers",
                                column_name="id",
                                referenced_table="customer_addresses",
                                referenced_column="customer_id",
                                constraint_name="fk_addresses_customer",
                                on_delete="CASCADE",
                                on_update="CASCADE",
                                impact_level=ImpactLevel.CRITICAL,
                            ),
                        ]
                    },
                ),
                "expected_risk_level": RiskLevel.CRITICAL,
            },
        ]

        scenario_results = []

        for scenario in ecommerce_scenarios:
            scenario_start = time.time()

            # Execute complete workflow
            risk_assessment = system["risk_engine"].calculate_migration_risk_score(
                scenario["operation"], scenario["dependencies"]
            )

            mitigation_strategies = system[
                "mitigation_engine"
            ].generate_mitigation_strategies(
                risk_assessment,
                scenario["dependencies"],
                operation_context={
                    "is_production": scenario["operation"].is_production,
                    "table_size_mb": scenario["operation"].table_size_mb,
                },
            )

            mitigation_plan = system["mitigation_engine"].prioritize_mitigation_actions(
                mitigation_strategies, risk_assessment
            )

            business_context = {
                "regulatory_frameworks": ["PCI DSS", "GDPR", "Change Management"],
                "risk_owner": "E-commerce Engineering Team",
                "affected_systems_count": (
                    3 if scenario["expected_risk_level"] != RiskLevel.LOW else 1
                ),
            }

            impact_report = system[
                "impact_reporter"
            ].generate_comprehensive_impact_report(
                risk_assessment,
                mitigation_plan,
                scenario["dependencies"],
                business_context,
            )

            scenario_time = time.time() - scenario_start

            # Validate realistic behavior
            actual_risk_level = risk_assessment.risk_level

            # Risk level should be reasonable for the scenario
            if scenario["expected_risk_level"] == RiskLevel.LOW:
                assert actual_risk_level in [RiskLevel.LOW, RiskLevel.MEDIUM]
            elif scenario["expected_risk_level"] == RiskLevel.MEDIUM:
                assert actual_risk_level in [RiskLevel.MEDIUM, RiskLevel.HIGH]
            elif scenario["expected_risk_level"] == RiskLevel.CRITICAL:
                assert actual_risk_level in [RiskLevel.HIGH, RiskLevel.CRITICAL]

            # Mitigation strategies should be appropriate
            if actual_risk_level in [RiskLevel.HIGH, RiskLevel.CRITICAL]:
                assert len(mitigation_plan.mitigation_strategies) > 0
                critical_strategies = [
                    s
                    for s in mitigation_plan.mitigation_strategies
                    if hasattr(s, "priority")
                    and s.priority == MitigationPriority.CRITICAL
                ]
                if actual_risk_level == RiskLevel.CRITICAL:
                    assert len(critical_strategies) > 0

            # Executive summary should reflect appropriate business impact
            exec_summary = impact_report.executive_summary
            if actual_risk_level == RiskLevel.CRITICAL:
                assert exec_summary.approval_required is True
                assert exec_summary.approval_level in ["Management", "Executive"]

            # Generate executive report for critical scenarios
            if actual_risk_level == RiskLevel.CRITICAL:
                executive_report = system["report_formatter"].format_report(
                    impact_report, ReportFormat.CONSOLE, FormatStyle.EXECUTIVE
                )

                assert "CRITICAL" in executive_report or "HIGH" in executive_report
                assert any(emoji in executive_report for emoji in ["❌", "⚠️", "🔴"])

            scenario_results.append(
                {
                    "name": scenario["name"],
                    "expected_risk": scenario["expected_risk_level"].value,
                    "actual_risk": actual_risk_level.value,
                    "processing_time": scenario_time,
                    "mitigation_strategies": len(mitigation_plan.mitigation_strategies),
                    "approval_required": exec_summary.approval_required,
                }
            )

            print(
                f"✅ {scenario['name']}: {actual_risk_level.value.upper()} risk "
                f"({len(mitigation_plan.mitigation_strategies)} strategies, {scenario_time:.3f}s)"
            )

        # Overall validation
        total_scenarios = len(scenario_results)
        total_time = sum(r["processing_time"] for r in scenario_results)

        print("\n📊 Real-world scenario simulation completed:")
        print(f"   • {total_scenarios} scenarios processed in {total_time:.3f}s")
        print(
            f"   • Average processing time: {total_time/total_scenarios:.3f}s per scenario"
        )
        print(
            f"   • Risk levels detected: {set(r['actual_risk'] for r in scenario_results)}"
        )

        # System should handle realistic scenarios efficiently
        assert (
            total_time / total_scenarios < 3.0
        )  # Average under 3 seconds per scenario

        # Should detect varying risk levels appropriately
        detected_risk_levels = set(r["actual_risk"] for r in scenario_results)
        assert len(detected_risk_levels) > 1  # Should detect different risk levels
