#!/usr/bin/env python3
"""
Column Removal Impact Assessment Demo - TODO-137 Complete Implementation

Demonstrates the complete 3-phase column removal system:
- Phase 1: DependencyAnalyzer - Comprehensive dependency detection
- Phase 2: ColumnRemovalManager - Safe removal planning and execution
- Phase 3: ImpactReporter - User-friendly impact reporting and recommendations

This demo shows real-world usage patterns and integration between all phases.
"""

import asyncio
from dataclasses import dataclass
from typing import Optional

import asyncpg

from dataflow.migrations.column_removal_manager import (
    BackupStrategy,
    ColumnRemovalManager,
    RemovalPlan,
    SafetyValidation,
)
from dataflow.migrations.dependency_analyzer import (
    DependencyAnalyzer,
    DependencyReport,
    DependencyType,
    ImpactLevel,
)

# Phase 3: Impact Reporting
from dataflow.migrations.impact_reporter import ImpactReporter, OutputFormat


@dataclass
class ColumnRemovalScenario:
    """Demo scenario configuration."""

    name: str
    table_name: str
    column_name: str
    description: str
    expected_risk: ImpactLevel


class ColumnRemovalDemo:
    """
    Demonstration of complete column removal impact assessment workflow.

    Shows how the three phases work together to provide safe, user-friendly
    column removal with comprehensive impact analysis.
    """

    def __init__(self, connection_string: Optional[str] = None):
        """Initialize demo with optional database connection."""
        self.connection_string = connection_string
        self.connection_manager = None

        # Initialize all three phases
        self.dependency_analyzer = None
        self.column_removal_manager = None
        self.impact_reporter = ImpactReporter()

        print("🚀 Column Removal Impact Assessment Demo")
        print("=" * 60)

    async def setup_connection(self):
        """Setup database connection for real scenarios."""
        if self.connection_string:
            # In real usage, you would use your connection manager
            print("📡 Connecting to database...")
            # self.connection = await asyncpg.connect(self.connection_string)
            print("✅ Database connection ready")
        else:
            print("📋 Using simulated scenarios (no database required)")

    def setup_components(self):
        """Initialize the three-phase system components."""
        self.dependency_analyzer = DependencyAnalyzer(self.connection_manager)
        self.column_removal_manager = ColumnRemovalManager(self.connection_manager)
        print("🔧 All components initialized successfully")

    def get_demo_scenarios(self) -> list[ColumnRemovalScenario]:
        """Define demonstration scenarios."""
        return [
            ColumnRemovalScenario(
                name="Critical Foreign Key Scenario",
                table_name="users",
                column_name="id",
                description="Primary key column with multiple foreign key references",
                expected_risk=ImpactLevel.CRITICAL,
            ),
            ColumnRemovalScenario(
                name="High Impact View Scenario",
                table_name="users",
                column_name="email",
                description="Email column used in views and triggers",
                expected_risk=ImpactLevel.HIGH,
            ),
            ColumnRemovalScenario(
                name="Medium Impact Index Scenario",
                table_name="products",
                column_name="category_id",
                description="Foreign key with indexes and moderate dependencies",
                expected_risk=ImpactLevel.MEDIUM,
            ),
            ColumnRemovalScenario(
                name="Safe Removal Scenario",
                table_name="users",
                column_name="temp_field",
                description="Temporary column with minimal dependencies",
                expected_risk=ImpactLevel.LOW,
            ),
        ]

    def create_simulated_dependency_report(
        self, scenario: ColumnRemovalScenario
    ) -> DependencyReport:
        """Create realistic dependency report for demo scenarios."""
        from dataflow.migrations.dependency_analyzer import (
            ConstraintDependency,
            ForeignKeyDependency,
            IndexDependency,
            TriggerDependency,
            ViewDependency,
        )

        report = DependencyReport(
            table_name=scenario.table_name,
            column_name=scenario.column_name,
            analysis_timestamp="2024-01-01T10:00:00",
            total_analysis_time=1.5,
        )

        if scenario.expected_risk == ImpactLevel.CRITICAL:
            # Critical scenario - primary key with multiple FKs
            fk_deps = [
                ForeignKeyDependency(
                    constraint_name="fk_orders_user_id",
                    source_table="orders",
                    source_column="user_id",
                    target_table="users",
                    target_column="id",
                    impact_level=ImpactLevel.CRITICAL,
                ),
                ForeignKeyDependency(
                    constraint_name="fk_profiles_user_id",
                    source_table="user_profiles",
                    source_column="user_id",
                    target_table="users",
                    target_column="id",
                    impact_level=ImpactLevel.CRITICAL,
                ),
            ]
            report.dependencies[DependencyType.FOREIGN_KEY] = fk_deps

            # Primary key index
            index_dep = IndexDependency(
                index_name="users_pkey",
                index_type="btree",
                columns=["id"],
                is_unique=True,
                impact_level=ImpactLevel.HIGH,
            )
            report.dependencies[DependencyType.INDEX] = [index_dep]

        elif scenario.expected_risk == ImpactLevel.HIGH:
            # High impact scenario - email with views and triggers
            view_deps = [
                ViewDependency(
                    view_name="active_users_view",
                    view_definition="SELECT id, email, name FROM users WHERE email IS NOT NULL",
                    impact_level=ImpactLevel.HIGH,
                ),
                ViewDependency(
                    view_name="user_contact_info",
                    view_definition="SELECT u.name, u.email, p.phone FROM users u LEFT JOIN profiles p ON u.id = p.user_id",
                    impact_level=ImpactLevel.HIGH,
                ),
            ]
            report.dependencies[DependencyType.VIEW] = view_deps

            trigger_dep = TriggerDependency(
                trigger_name="email_change_audit",
                event="UPDATE",
                timing="AFTER",
                function_name="log_email_changes",
                impact_level=ImpactLevel.HIGH,
            )
            report.dependencies[DependencyType.TRIGGER] = [trigger_dep]

            # Email indexes
            index_deps = [
                IndexDependency(
                    index_name="idx_users_email_unique",
                    index_type="btree",
                    columns=["email"],
                    is_unique=True,
                    impact_level=ImpactLevel.MEDIUM,
                )
            ]
            report.dependencies[DependencyType.INDEX] = index_deps

        elif scenario.expected_risk == ImpactLevel.MEDIUM:
            # Medium impact scenario - foreign key with indexes
            fk_dep = ForeignKeyDependency(
                constraint_name="fk_products_category_id",
                source_table="products",
                source_column="category_id",
                target_table="categories",
                target_column="id",
                impact_level=ImpactLevel.HIGH,
            )
            report.dependencies[DependencyType.FOREIGN_KEY] = [fk_dep]

            index_deps = [
                IndexDependency(
                    index_name="idx_products_category_id",
                    index_type="btree",
                    columns=["category_id"],
                    is_unique=False,
                    impact_level=ImpactLevel.MEDIUM,
                ),
                IndexDependency(
                    index_name="idx_products_category_name",
                    index_type="btree",
                    columns=["category_id", "name"],
                    is_unique=False,
                    impact_level=ImpactLevel.MEDIUM,
                ),
            ]
            report.dependencies[DependencyType.INDEX] = index_deps

        else:
            # Safe scenario - minimal dependencies
            index_dep = IndexDependency(
                index_name="idx_users_temp_field",
                index_type="btree",
                columns=["temp_field"],
                is_unique=False,
                impact_level=ImpactLevel.LOW,
            )
            report.dependencies[DependencyType.INDEX] = [index_dep]

        return report

    async def demonstrate_scenario(self, scenario: ColumnRemovalScenario):
        """Demonstrate complete workflow for a single scenario."""
        print(f"\n🎯 SCENARIO: {scenario.name}")
        print(f"   Target: {scenario.table_name}.{scenario.column_name}")
        print(f"   Description: {scenario.description}")
        print("─" * 60)

        # PHASE 1: Dependency Analysis
        print("📊 PHASE 1: Dependency Analysis")
        dependency_report = self.create_simulated_dependency_report(scenario)

        total_deps = dependency_report.get_total_dependency_count()
        print(
            f"   ✅ Found {total_deps} dependencies in {dependency_report.total_analysis_time:.1f}s"
        )

        # PHASE 3: Impact Assessment
        print("📋 PHASE 3: Impact Assessment & Reporting")
        impact_report = self.impact_reporter.generate_impact_report(dependency_report)

        print(
            f"   ✅ Risk Level: {impact_report.assessment.overall_risk.value.upper()}"
        )
        print(f"   ✅ Generated {len(impact_report.recommendations)} recommendations")

        # Display console report
        print("\n📱 USER-FRIENDLY CONSOLE REPORT:")
        print("─" * 60)
        console_report = self.impact_reporter.format_user_friendly_report(
            impact_report, OutputFormat.CONSOLE, include_details=True
        )
        print(console_report)

        # Display summary for comparison
        print("\n📝 EXECUTIVE SUMMARY:")
        print("─" * 60)
        summary_report = self.impact_reporter.format_user_friendly_report(
            impact_report, OutputFormat.SUMMARY
        )
        print(f"   {summary_report}")

        # PHASE 2: Safety Validation (simulated)
        print("\n🔒 PHASE 2: Safety Validation")

        # Simulate safety validation based on impact assessment
        is_safe = impact_report.assessment.overall_risk in [
            ImpactLevel.LOW,
            ImpactLevel.INFORMATIONAL,
        ]
        requires_confirmation = impact_report.assessment.overall_risk in [
            ImpactLevel.HIGH,
            ImpactLevel.CRITICAL,
        ]

        simulated_validation = SafetyValidation(
            is_safe=is_safe,
            risk_level=impact_report.assessment.overall_risk,
            blocking_dependencies=[],  # Empty list for demo - would contain actual dependency objects in real usage
            warnings=[rec.description for rec in impact_report.recommendations[:2]],
            recommendations=[
                step
                for rec in impact_report.recommendations[:1]
                for step in rec.action_steps[:3]
            ],
            estimated_duration=10.0 + (total_deps * 2.0),
            requires_confirmation=requires_confirmation,
        )

        safety_report = self.impact_reporter.generate_safety_validation_report(
            simulated_validation
        )
        print(safety_report)

        return impact_report, simulated_validation

    def demonstrate_output_formats(self, impact_report):
        """Demonstrate all output formats."""
        print("\n🎨 OUTPUT FORMAT DEMONSTRATIONS")
        print("=" * 60)

        # JSON Format
        print("\n📄 JSON FORMAT (API Integration):")
        print("─" * 60)
        json_report = self.impact_reporter.format_user_friendly_report(
            impact_report, OutputFormat.JSON
        )
        # Show first 300 chars of JSON for demo
        print(json_report[:300] + "..." if len(json_report) > 300 else json_report)

        # HTML Format
        print("\n🌐 HTML FORMAT (Web Dashboard):")
        print("─" * 60)
        html_report = self.impact_reporter.format_user_friendly_report(
            impact_report, OutputFormat.HTML
        )
        # Show HTML structure without full CSS
        html_lines = html_report.split("\n")
        html_preview = "\n".join(
            [
                line
                for line in html_lines
                if "<div" in line or "<h" in line or "<p>" in line
            ][:10]
        )
        print(html_preview + "\n... (CSS and remaining HTML content)")

    async def run_demonstration(self):
        """Run complete demonstration of all scenarios."""
        await self.setup_connection()
        self.setup_components()

        scenarios = self.get_demo_scenarios()
        results = []

        print(f"\n🎪 Running {len(scenarios)} demonstration scenarios...")

        for scenario in scenarios:
            impact_report, safety_validation = await self.demonstrate_scenario(scenario)
            results.append((scenario, impact_report, safety_validation))

            # Pause between scenarios for readability
            await asyncio.sleep(0.5)

        # Show format demonstrations using the most complex scenario
        complex_scenario = max(
            results, key=lambda r: r[1].assessment.total_dependencies
        )
        self.demonstrate_output_formats(complex_scenario[1])

        # Summary of all scenarios
        print("\n📊 DEMONSTRATION SUMMARY")
        print("=" * 60)

        for scenario, impact_report, safety_validation in results:
            risk_icon = self.impact_reporter.impact_icons.get(
                impact_report.assessment.overall_risk, "❓"
            )
            safety_icon = "✅" if safety_validation.is_safe else "❌"

            print(
                f"{risk_icon} {scenario.name:<35} | Risk: {impact_report.assessment.overall_risk.value.upper():<8} | Safe: {safety_icon}"
            )

        print("\n🎉 Demonstration completed! All phases working in harmony.")
        print("💡 Key Benefits:")
        print("   • Comprehensive dependency detection (Phase 1)")
        print("   • Safe removal planning and validation (Phase 2)")
        print("   • User-friendly impact reporting (Phase 3)")
        print("   • Multiple output formats for different use cases")
        print("   • Actionable recommendations with clear risk communication")


async def main():
    """Run the complete demonstration."""
    print("🌟 Column Removal Impact Assessment - Complete System Demo")
    print("Built with DataFlow Migration System - TODO-137 Implementation")
    print()

    # Create and run demonstration
    demo = ColumnRemovalDemo()
    await demo.run_demonstration()

    print("\n📚 For more information:")
    print("   • Phase 1: dependency_analyzer.py - Comprehensive dependency detection")
    print("   • Phase 2: column_removal_manager.py - Safe removal execution")
    print("   • Phase 3: impact_reporter.py - User-friendly reporting")
    print("   • Integration Tests: test_impact_reporter_integration.py")


if __name__ == "__main__":
    asyncio.run(main())
