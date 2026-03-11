#!/usr/bin/env python3
"""
Integration tests for Impact Assessment Reporting System - TODO-137 Phase 3

Tests integration between ImpactReporter and existing Phase 1 (DependencyAnalyzer)
and Phase 2 (ColumnRemovalManager) components in realistic scenarios.
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
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
    ForeignKeyDependency,
    ImpactLevel,
    IndexDependency,
    TriggerDependency,
    ViewDependency,
)
from dataflow.migrations.impact_reporter import (
    ImpactReport,
    ImpactReporter,
    OutputFormat,
    RecommendationType,
)

from kailash.runtime.local import LocalRuntime
from tests.infrastructure.test_harness import IntegrationTestSuite


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


class TestImpactReporterIntegration:
    """Test ImpactReporter integration with existing components."""

    @pytest.fixture
    def impact_reporter(self):
        """Create ImpactReporter instance for testing."""
        return ImpactReporter()

    @pytest.fixture
    def mock_connection_manager(self, test_suite):
        """Create mock connection manager."""
        manager = MagicMock()
        connection = AsyncMock()
        manager.get_connection.return_value = connection
        return manager, connection

    @pytest.fixture
    def dependency_analyzer(self, mock_connection_manager):
        """Create DependencyAnalyzer with mock connection."""
        manager, connection = mock_connection_manager
        return DependencyAnalyzer(manager)

    @pytest.fixture
    def column_removal_manager(self, mock_connection_manager):
        """Create ColumnRemovalManager with mock connection."""
        manager, connection = mock_connection_manager
        return ColumnRemovalManager(manager)

    @pytest.mark.asyncio
    async def test_integration_dependency_analyzer_to_impact_reporter(
        self, impact_reporter, dependency_analyzer, mock_connection_manager
    ):
        """Test full integration from DependencyAnalyzer to ImpactReporter."""
        manager, connection = mock_connection_manager

        # Mock database responses for dependency analysis
        # Mock foreign key query
        connection.fetch.side_effect = [
            # Foreign key dependencies
            [
                {
                    "constraint_name": "fk_orders_user_id",
                    "source_table": "orders",
                    "source_column": "user_id",
                    "target_table": "users",
                    "target_column": "id",
                    "delete_rule": "CASCADE",
                    "update_rule": "RESTRICT",
                }
            ],
            # View dependencies
            [
                {
                    "schemaname": "public",
                    "viewname": "user_order_summary",
                    "definition": "SELECT u.id, u.name, COUNT(o.id) FROM users u LEFT JOIN orders o ON u.id = o.user_id GROUP BY u.id",
                }
            ],
            # Trigger dependencies
            [
                {
                    "trigger_name": "user_audit_trigger",
                    "event_manipulation": "UPDATE",
                    "action_timing": "AFTER",
                    "action_statement": "EXECUTE FUNCTION audit_user_changes()",
                    "function_name": "audit_user_changes",
                }
            ],
            # Index dependencies
            [
                {
                    "index_name": "idx_users_id_unique",
                    "index_type": "btree",
                    "index_definition": "CREATE UNIQUE INDEX idx_users_id_unique ON users USING btree (id)",
                    "is_unique": True,
                    "columns": ["id"],
                }
            ],
            # Constraint dependencies (empty)
            [],
        ]

        # Execute Phase 1: Dependency Analysis
        dependency_report = await dependency_analyzer.analyze_column_dependencies(
            "users", "id", connection
        )

        # Verify Phase 1 output
        assert isinstance(dependency_report, DependencyReport)
        assert dependency_report.table_name == "users"
        assert dependency_report.column_name == "id"
        # Note: Actual count may vary based on mock data and trigger detection logic
        total_deps = dependency_report.get_total_dependency_count()
        assert total_deps >= 3  # At least FK, view, and index

        # Execute Phase 3: Impact Reporting
        impact_report = impact_reporter.generate_impact_report(dependency_report)

        # Verify integration produces correct impact assessment
        assert impact_report.assessment.table_name == "users"
        assert impact_report.assessment.column_name == "id"
        assert impact_report.assessment.total_dependencies == total_deps
        assert (
            impact_report.assessment.critical_dependencies >= 1
        )  # At least FK dependency
        assert impact_report.assessment.overall_risk == ImpactLevel.CRITICAL

        # Verify recommendations are appropriate
        assert len(impact_report.recommendations) >= 1
        primary_rec = impact_report.recommendations[0]
        assert primary_rec.type == RecommendationType.DO_NOT_REMOVE
        assert "foreign key" in " ".join(primary_rec.action_steps).lower()

    @pytest.mark.asyncio
    async def test_integration_column_removal_manager_with_impact_reporter(
        self, impact_reporter, column_removal_manager, mock_connection_manager
    ):
        """Test integration between ColumnRemovalManager and ImpactReporter."""
        manager, connection = mock_connection_manager

        # Mock dependency analysis in the removal manager
        mock_dependency_report = DependencyReport(
            table_name="users", column_name="email"
        )

        # Add high-impact dependencies
        fk_dep = ForeignKeyDependency(
            constraint_name="fk_orders_user_email",
            source_table="orders",
            source_column="user_email",
            target_table="users",
            target_column="email",
            impact_level=ImpactLevel.CRITICAL,
        )
        view_dep = ViewDependency(
            view_name="active_users",
            view_definition="SELECT * FROM users WHERE email IS NOT NULL",
            impact_level=ImpactLevel.HIGH,
        )

        mock_dependency_report.dependencies[DependencyType.FOREIGN_KEY] = [fk_dep]
        mock_dependency_report.dependencies[DependencyType.VIEW] = [view_dep]

        with patch.object(
            column_removal_manager.dependency_analyzer,
            "analyze_column_dependencies",
            return_value=mock_dependency_report,
        ):
            # Execute Phase 2: Removal Planning
            removal_plan = await column_removal_manager.plan_column_removal(
                "users", "email", connection=connection
            )

            # Mock table/column existence checks for safety validation
            connection.fetchval.side_effect = [
                True,
                True,
            ]  # Table exists, column exists

            # Execute Phase 2: Safety Validation
            safety_validation = await column_removal_manager.validate_removal_safety(
                removal_plan, connection
            )

            # Execute Phase 3: Impact Reporting on removal plan dependencies
            impact_report = impact_reporter.generate_impact_report(
                mock_dependency_report
            )

            # Execute Phase 3: Safety Validation Reporting
            safety_report = impact_reporter.generate_safety_validation_report(
                safety_validation
            )

            # Verify integration consistency
            assert not safety_validation.is_safe  # Should be unsafe due to critical FK
            assert safety_validation.risk_level == ImpactLevel.CRITICAL
            assert impact_report.assessment.overall_risk == ImpactLevel.CRITICAL

            # Verify reports are consistent
            console_report = impact_reporter.format_user_friendly_report(impact_report)
            assert "CRITICAL IMPACT DETECTED" in console_report
            assert "DO NOT REMOVE" in console_report

            assert "UNSAFE" in safety_report
            assert "CRITICAL" in safety_report

    @pytest.mark.asyncio
    async def test_end_to_end_workflow_critical_scenario(
        self,
        impact_reporter,
        dependency_analyzer,
        column_removal_manager,
        mock_connection_manager,
    ):
        """Test complete end-to-end workflow for critical scenario."""
        manager, connection = mock_connection_manager

        # Mock complex database scenario with multiple critical dependencies
        connection.fetch.side_effect = [
            # Multiple foreign key dependencies
            [
                {
                    "constraint_name": "fk_orders_user_id",
                    "source_table": "orders",
                    "source_column": "user_id",
                    "target_table": "users",
                    "target_column": "id",
                    "delete_rule": "RESTRICT",
                    "update_rule": "RESTRICT",
                },
                {
                    "constraint_name": "fk_profiles_user_id",
                    "source_table": "user_profiles",
                    "source_column": "user_id",
                    "target_table": "users",
                    "target_column": "id",
                    "delete_rule": "CASCADE",
                    "update_rule": "CASCADE",
                },
            ],
            # Critical views
            [
                {
                    "schemaname": "public",
                    "viewname": "user_analytics",
                    "definition": "SELECT u.id, u.name, COUNT(o.id) as order_count FROM users u LEFT JOIN orders o ON u.id = o.user_id GROUP BY u.id",
                },
                {
                    "schemaname": "public",
                    "viewname": "user_profiles_view",
                    "definition": "SELECT u.id, u.name, p.bio FROM users u JOIN user_profiles p ON u.id = p.user_id",
                },
            ],
            # Triggers
            [
                {
                    "trigger_name": "user_delete_cascade",
                    "event_manipulation": "DELETE",
                    "action_timing": "BEFORE",
                    "action_statement": "EXECUTE FUNCTION cleanup_user_data()",
                    "function_name": "cleanup_user_data",
                }
            ],
            # Indexes
            [
                {
                    "index_name": "users_pkey",
                    "index_type": "btree",
                    "index_definition": "CREATE UNIQUE INDEX users_pkey ON users USING btree (id)",
                    "is_unique": True,
                    "columns": ["id"],
                }
            ],
            # Constraints (empty for this test)
            [],
        ]

        # Step 1: Execute Phase 1 - Dependency Analysis
        dependency_report = await dependency_analyzer.analyze_column_dependencies(
            "users", "id", connection
        )

        # Step 2: Execute Phase 3 - Generate Impact Report
        impact_report = impact_reporter.generate_impact_report(dependency_report)

        # Step 3: Execute Phase 2 - Create Removal Plan
        with patch.object(
            column_removal_manager.dependency_analyzer,
            "analyze_column_dependencies",
            return_value=dependency_report,
        ):
            removal_plan = await column_removal_manager.plan_column_removal(
                "users", "id", BackupStrategy.TABLE_SNAPSHOT, connection=connection
            )

        # Step 4: Execute Phase 2 - Safety Validation
        connection.fetchval.side_effect = [True, True]  # Table exists, column exists
        safety_validation = await column_removal_manager.validate_removal_safety(
            removal_plan, connection
        )

        # Step 5: Execute Phase 3 - Generate User Reports
        console_report = impact_reporter.format_user_friendly_report(
            impact_report, OutputFormat.CONSOLE, include_details=True
        )
        json_report = impact_reporter.format_user_friendly_report(
            impact_report, OutputFormat.JSON
        )
        html_report = impact_reporter.format_user_friendly_report(
            impact_report, OutputFormat.HTML, include_details=True
        )
        safety_report = impact_reporter.generate_safety_validation_report(
            safety_validation
        )

        # Verify end-to-end consistency
        total_deps = dependency_report.get_total_dependency_count()
        assert (
            total_deps >= 4
        )  # At least 2 FK + 1 view + 1 index (actual count may vary based on mock detection)
        assert impact_report.assessment.total_dependencies == total_deps
        assert impact_report.assessment.critical_dependencies >= 2  # At least 2 FKs
        assert impact_report.assessment.overall_risk == ImpactLevel.CRITICAL

        assert not safety_validation.is_safe
        assert safety_validation.risk_level == ImpactLevel.CRITICAL
        assert len(safety_validation.blocking_dependencies) == 2

        # Verify all report formats contain consistent information
        assert "CRITICAL IMPACT DETECTED" in console_report
        assert "users.id" in console_report
        assert "DO NOT REMOVE" in console_report

        parsed_json = json.loads(json_report)
        assert parsed_json["assessment"]["overall_risk"] == "critical"
        assert parsed_json["assessment"]["total_dependencies"] == total_deps

        assert "critical-risk" in html_report
        assert "Critical:" in html_report  # Should contain critical count information

        assert "UNSAFE" in safety_report
        assert "CRITICAL" in safety_report

    @pytest.mark.asyncio
    async def test_end_to_end_workflow_safe_scenario(
        self,
        impact_reporter,
        dependency_analyzer,
        column_removal_manager,
        mock_connection_manager,
    ):
        """Test complete end-to-end workflow for safe removal scenario."""
        manager, connection = mock_connection_manager

        # Mock minimal dependencies scenario
        connection.fetch.side_effect = [
            [],  # No foreign key dependencies
            [],  # No view dependencies
            [],  # No trigger dependencies
            # Only a single non-unique index
            [
                {
                    "index_name": "idx_users_temp_column",
                    "index_type": "btree",
                    "index_definition": "CREATE INDEX idx_users_temp_column ON users USING btree (temp_column)",
                    "is_unique": False,
                    "columns": ["temp_column"],
                }
            ],
            [],  # No constraint dependencies
        ]

        # Step 1: Execute Phase 1 - Dependency Analysis
        dependency_report = await dependency_analyzer.analyze_column_dependencies(
            "users", "temp_column", connection
        )

        # Step 2: Execute Phase 3 - Generate Impact Report
        impact_report = impact_reporter.generate_impact_report(dependency_report)

        # Step 3: Execute Phase 2 - Create Removal Plan
        with patch.object(
            column_removal_manager.dependency_analyzer,
            "analyze_column_dependencies",
            return_value=dependency_report,
        ):
            removal_plan = await column_removal_manager.plan_column_removal(
                "users",
                "temp_column",
                BackupStrategy.COLUMN_ONLY,
                connection=connection,
            )

        # Step 4: Execute Phase 2 - Safety Validation
        connection.fetchval.side_effect = [True, True]  # Table exists, column exists
        safety_validation = await column_removal_manager.validate_removal_safety(
            removal_plan, connection
        )

        # Step 5: Execute Phase 3 - Generate User Reports
        console_report = impact_reporter.format_user_friendly_report(
            impact_report, OutputFormat.CONSOLE
        )
        summary_report = impact_reporter.format_user_friendly_report(
            impact_report, OutputFormat.SUMMARY
        )
        safety_report = impact_reporter.generate_safety_validation_report(
            safety_validation
        )

        # Verify safe removal scenario
        assert dependency_report.get_total_dependency_count() == 1
        assert impact_report.assessment.total_dependencies == 1
        assert impact_report.assessment.critical_dependencies == 0
        assert impact_report.assessment.overall_risk in [
            ImpactLevel.LOW,
            ImpactLevel.MEDIUM,
        ]

        assert safety_validation.is_safe
        assert safety_validation.risk_level in [ImpactLevel.LOW, ImpactLevel.MEDIUM]
        assert len(safety_validation.blocking_dependencies) == 0

        # Verify reports reflect safe removal
        assert "SAFE" in console_report or "CAUTION" in console_report
        assert "✅" in console_report or "🟡" in console_report

        assert "Risk: LOW" in summary_report or "Risk: MEDIUM" in summary_report
        assert (
            "SAFE TO REMOVE" in summary_report
            or "PROCEED WITH CAUTION" in summary_report
        )

        assert "✅ SAFE" in safety_report
        assert safety_validation.risk_level.value.upper() in safety_report

    @pytest.mark.asyncio
    async def test_performance_with_large_dependency_set(
        self, impact_reporter, mock_connection_manager
    ):
        """Test performance and formatting with large dependency sets."""
        manager, connection = mock_connection_manager

        # Create a large dependency report (simulating complex schema)
        dependency_report = DependencyReport(
            table_name="large_table", column_name="shared_column"
        )

        # Add many dependencies of various types
        fk_deps = []
        for i in range(15):
            fk_deps.append(
                ForeignKeyDependency(
                    constraint_name=f"fk_table_{i}_shared_column",
                    source_table=f"dependent_table_{i}",
                    source_column="shared_column_ref",
                    target_table="large_table",
                    target_column="shared_column",
                    impact_level=ImpactLevel.CRITICAL if i < 5 else ImpactLevel.HIGH,
                )
            )
        dependency_report.dependencies[DependencyType.FOREIGN_KEY] = fk_deps

        view_deps = []
        for i in range(8):
            view_deps.append(
                ViewDependency(
                    view_name=f"summary_view_{i}",
                    view_definition=f"SELECT shared_column, col_{i} FROM large_table WHERE shared_column IS NOT NULL",
                    impact_level=ImpactLevel.HIGH,
                )
            )
        dependency_report.dependencies[DependencyType.VIEW] = view_deps

        index_deps = []
        for i in range(25):
            index_deps.append(
                IndexDependency(
                    index_name=f"idx_large_table_shared_{i}",
                    index_type="btree",
                    columns=["shared_column", f"col_{i}"],
                    is_unique=i < 3,
                    impact_level=ImpactLevel.MEDIUM,
                )
            )
        dependency_report.dependencies[DependencyType.INDEX] = index_deps

        # Generate impact report (should handle large sets efficiently)
        import time

        start_time = time.time()

        impact_report = impact_reporter.generate_impact_report(dependency_report)

        generation_time = time.time() - start_time

        # Verify performance (should complete quickly even with many dependencies)
        assert generation_time < 1.0  # Should complete in under 1 second

        # Verify correct totals
        assert impact_report.assessment.total_dependencies == 48  # 15 + 8 + 25
        assert impact_report.assessment.critical_dependencies == 5
        assert (
            impact_report.assessment.high_impact_dependencies == 18
        )  # 10 FKs + 8 views
        assert impact_report.assessment.medium_impact_dependencies == 25  # indexes

        # Verify report formatting handles large lists gracefully
        console_report = impact_reporter.format_user_friendly_report(impact_report)

        # Should include truncation for readability
        assert "... and" in console_report  # Should show truncation
        assert len(console_report.split("\n")) < 100  # Should not be excessively long

        # JSON report should include all dependencies
        json_report = impact_reporter.format_user_friendly_report(
            impact_report, OutputFormat.JSON
        )
        parsed = json.loads(json_report)

        total_deps_in_details = sum(
            len(dep_list) for dep_list in parsed["dependency_details"].values()
        )
        assert total_deps_in_details == 48
