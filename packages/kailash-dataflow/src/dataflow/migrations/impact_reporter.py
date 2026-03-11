#!/usr/bin/env python3
"""
Impact Assessment Reporting System - TODO-137 Phase 3

Provides user-friendly impact reporting and visualization for column removal operations,
with clear risk communication, actionable recommendations, and multiple output formats.

PHASE 3 IMPLEMENTATION: Impact Assessment Reporting
- Clear visual impact reports with emoji indicators
- Actionable recommendations with specific user steps
- Progressive disclosure (overview + detailed drill-down)
- Multiple output formats (Console, JSON, HTML)
- Integration with existing DependencyAnalyzer and ColumnRemovalManager
"""

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from html import escape
from typing import Any, Dict, List, Optional, Union

from .column_removal_manager import RemovalPlan, SafetyValidation
from .dependency_analyzer import (
    ConstraintDependency,
    DependencyReport,
    DependencyType,
    ForeignKeyDependency,
    ImpactLevel,
    IndexDependency,
    TriggerDependency,
    ViewDependency,
)

logger = logging.getLogger(__name__)


class RecommendationType(Enum):
    """Types of recommendations."""

    DO_NOT_REMOVE = "do_not_remove"
    REQUIRES_FIXES = "requires_fixes"
    PROCEED_WITH_CAUTION = "proceed_with_caution"
    SAFE_TO_REMOVE = "safe_to_remove"
    REVIEW_REQUIRED = "review_required"


class OutputFormat(Enum):
    """Output formats for reports."""

    CONSOLE = "console"
    JSON = "json"
    HTML = "html"
    SUMMARY = "summary"


@dataclass
class Recommendation:
    """A specific recommendation for column removal."""

    type: RecommendationType
    title: str
    description: str
    action_steps: List[str] = field(default_factory=list)
    priority: ImpactLevel = ImpactLevel.MEDIUM
    dependency_object: Optional[str] = None
    sql_example: Optional[str] = None


@dataclass
class ImpactAssessment:
    """Assessment of column removal impact."""

    table_name: str
    column_name: str
    overall_risk: ImpactLevel
    total_dependencies: int
    critical_dependencies: int
    high_impact_dependencies: int
    medium_impact_dependencies: int
    low_impact_dependencies: int
    estimated_data_rows: int = 0
    estimated_backup_size: str = "Unknown"


@dataclass
class ImpactReport:
    """Comprehensive impact report for column removal."""

    assessment: ImpactAssessment
    recommendations: List[Recommendation] = field(default_factory=list)
    dependency_details: Dict[str, List[Dict[str, Any]]] = field(default_factory=dict)
    safety_validation: Optional[SafetyValidation] = None
    generation_timestamp: str = field(
        default_factory=lambda: datetime.now().isoformat()
    )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""

        def convert_enums(obj):
            """Recursively convert Enum values to strings for JSON serialization."""
            if isinstance(obj, dict):
                return {k: convert_enums(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [convert_enums(item) for item in obj]
            elif hasattr(obj, "value"):  # Enum
                return obj.value
            else:
                return obj

        data = asdict(self)
        return convert_enums(data)


class ImpactReporter:
    """
    User-friendly impact reporting and visualization for column removal operations.

    Provides clear risk communication, actionable recommendations, and multiple
    output formats for database administrators and developers.
    """

    def __init__(self):
        """Initialize the impact reporter."""
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

        # Icon mappings for visual indicators
        self.impact_icons = {
            ImpactLevel.CRITICAL: "🔴",
            ImpactLevel.HIGH: "🟡",
            ImpactLevel.MEDIUM: "🟠",
            ImpactLevel.LOW: "🟢",
            ImpactLevel.INFORMATIONAL: "🔵",
        }

        self.dependency_icons = {
            DependencyType.FOREIGN_KEY: "🔗",
            DependencyType.VIEW: "👁️",
            DependencyType.TRIGGER: "⚡",
            DependencyType.INDEX: "📊",
            DependencyType.CONSTRAINT: "🔒",
        }

    def generate_impact_report(self, dependencies: DependencyReport) -> ImpactReport:
        """
        Generate comprehensive impact report from dependency analysis.

        Args:
            dependencies: DependencyReport from Phase 1 analysis

        Returns:
            ImpactReport with assessment and recommendations
        """
        self.logger.info(
            f"Generating impact report for {dependencies.table_name}.{dependencies.column_name}"
        )

        # Create impact assessment
        assessment = self._create_impact_assessment(dependencies)

        # Generate recommendations
        recommendations = self.create_removal_recommendations(assessment, dependencies)

        # Create detailed dependency breakdown
        dependency_details = self._create_dependency_details(dependencies)

        report = ImpactReport(
            assessment=assessment,
            recommendations=recommendations,
            dependency_details=dependency_details,
        )

        self.logger.info(
            f"Impact report generated: {assessment.total_dependencies} dependencies, "
            f"{len(recommendations)} recommendations, risk={assessment.overall_risk.value}"
        )

        return report

    def create_removal_recommendations(
        self,
        assessment: ImpactAssessment,
        dependencies: Optional[DependencyReport] = None,
    ) -> List[Recommendation]:
        """
        Create actionable recommendations based on impact assessment.

        Args:
            assessment: Impact assessment results
            dependencies: Optional dependency report for detailed analysis

        Returns:
            List of actionable recommendations
        """
        recommendations = []

        # Overall recommendation based on risk level
        if assessment.overall_risk == ImpactLevel.CRITICAL:
            recommendations.append(
                Recommendation(
                    type=RecommendationType.DO_NOT_REMOVE,
                    title="❌ DO NOT REMOVE - Critical Dependencies Detected",
                    description=f"Removing {assessment.table_name}.{assessment.column_name} will break {assessment.critical_dependencies} critical objects and cause system failures.",
                    action_steps=[
                        "Review and remove all foreign key constraints first",
                        "Update or remove dependent views and triggers",
                        "Ensure no active applications use this column",
                        "Plan migration for referencing tables",
                        "Re-run analysis after fixing dependencies",
                    ],
                    priority=ImpactLevel.CRITICAL,
                )
            )
        elif assessment.overall_risk == ImpactLevel.HIGH:
            recommendations.append(
                Recommendation(
                    type=RecommendationType.REQUIRES_FIXES,
                    title="⚠️ REQUIRES FIXES - High Impact Dependencies",
                    description=f"Column removal will affect {assessment.high_impact_dependencies} high-impact objects. Fix dependencies first.",
                    action_steps=[
                        "Review and update dependent views",
                        "Update or disable affected triggers",
                        "Coordinate with application teams",
                        "Plan deployment during maintenance window",
                        "Test in staging environment first",
                    ],
                    priority=ImpactLevel.HIGH,
                )
            )
        elif assessment.overall_risk == ImpactLevel.MEDIUM:
            recommendations.append(
                Recommendation(
                    type=RecommendationType.PROCEED_WITH_CAUTION,
                    title="🟡 PROCEED WITH CAUTION - Performance Impact Expected",
                    description=f"Column removal will drop {assessment.medium_impact_dependencies} indexes and may affect query performance.",
                    action_steps=[
                        "Review query performance impact",
                        "Create backup of affected data",
                        "Monitor system after removal",
                        "Have rollback plan ready",
                        "Schedule during low-traffic period",
                    ],
                    priority=ImpactLevel.MEDIUM,
                )
            )
        else:
            recommendations.append(
                Recommendation(
                    type=RecommendationType.SAFE_TO_REMOVE,
                    title="✅ SAFE TO REMOVE - Minimal Impact",
                    description=f"Column {assessment.column_name} has minimal dependencies and can be safely removed.",
                    action_steps=[
                        "Create data backup (recommended)",
                        "Execute removal during maintenance window",
                        "Verify removal success",
                        "Clean up any backup data if not needed",
                    ],
                    priority=ImpactLevel.LOW,
                )
            )

        # Add specific dependency recommendations
        if dependencies:
            recommendations.extend(
                self._create_dependency_specific_recommendations(dependencies)
            )

        return recommendations

    def format_user_friendly_report(
        self,
        report: ImpactReport,
        format_type: OutputFormat = OutputFormat.CONSOLE,
        include_details: bool = True,
    ) -> str:
        """
        Format impact report for user-friendly display.

        Args:
            report: Impact report to format
            format_type: Output format (console, JSON, HTML, summary)
            include_details: Whether to include detailed dependency information

        Returns:
            Formatted report string
        """
        if format_type == OutputFormat.JSON:
            return self._format_json_report(report)
        elif format_type == OutputFormat.HTML:
            return self._format_html_report(report, include_details)
        elif format_type == OutputFormat.SUMMARY:
            return self._format_summary_report(report)
        else:
            return self._format_console_report(report, include_details)

    def generate_safety_validation_report(self, validation: SafetyValidation) -> str:
        """
        Generate user-friendly safety validation report.

        Args:
            validation: Safety validation from Phase 2

        Returns:
            Formatted safety validation report
        """
        risk_icon = self.impact_icons.get(validation.risk_level, "❓")
        safety_status = "✅ SAFE" if validation.is_safe else "❌ UNSAFE"

        lines = [
            "",
            f"{'═' * 60}",
            "  SAFETY VALIDATION REPORT",
            f"{'═' * 60}",
            "",
            f"Status: {safety_status}",
            f"Risk Level: {risk_icon} {validation.risk_level.value.upper()}",
            f"Estimated Duration: {validation.estimated_duration:.1f} seconds",
            f"Requires Confirmation: {'Yes' if validation.requires_confirmation else 'No'}",
            "",
        ]

        if validation.blocking_dependencies:
            lines.extend(
                [
                    f"🚫 BLOCKING DEPENDENCIES ({len(validation.blocking_dependencies)}):",
                    f"{'─' * 50}",
                ]
            )
            for dep in validation.blocking_dependencies:
                dep_icon = self.dependency_icons.get(dep.dependency_type, "📋")
                lines.append(
                    f"  {dep_icon} {dep.constraint_name or dep.__class__.__name__}"
                )
            lines.append("")

        if validation.warnings:
            lines.extend(
                [
                    f"⚠️  WARNINGS ({len(validation.warnings)}):",
                    f"{'─' * 50}",
                ]
            )
            for warning in validation.warnings:
                lines.append(f"  • {warning}")
            lines.append("")

        if validation.recommendations:
            lines.extend(
                [
                    "💡 RECOMMENDATIONS:",
                    f"{'─' * 50}",
                ]
            )
            for rec in validation.recommendations:
                lines.append(f"  • {rec}")
            lines.append("")

        return "\n".join(lines)

    # Private helper methods

    def _create_impact_assessment(
        self, dependencies: DependencyReport
    ) -> ImpactAssessment:
        """Create impact assessment from dependency report."""
        impact_summary = dependencies.generate_impact_summary()

        return ImpactAssessment(
            table_name=dependencies.table_name,
            column_name=dependencies.column_name,
            overall_risk=self._determine_overall_risk(impact_summary),
            total_dependencies=dependencies.get_total_dependency_count(),
            critical_dependencies=impact_summary[ImpactLevel.CRITICAL],
            high_impact_dependencies=impact_summary[ImpactLevel.HIGH],
            medium_impact_dependencies=impact_summary[ImpactLevel.MEDIUM],
            low_impact_dependencies=impact_summary[ImpactLevel.LOW],
            estimated_data_rows=0,  # Could be enhanced with actual row count
            estimated_backup_size="Unknown",  # Could be enhanced with size estimation
        )

    def _determine_overall_risk(
        self, impact_summary: Dict[ImpactLevel, int]
    ) -> ImpactLevel:
        """Determine overall risk level from impact summary."""
        if impact_summary[ImpactLevel.CRITICAL] > 0:
            return ImpactLevel.CRITICAL
        elif impact_summary[ImpactLevel.HIGH] > 0:
            return ImpactLevel.HIGH
        elif impact_summary[ImpactLevel.MEDIUM] > 0:
            return ImpactLevel.MEDIUM
        elif impact_summary[ImpactLevel.LOW] > 0:
            return ImpactLevel.LOW
        else:
            return ImpactLevel.INFORMATIONAL

    def _create_dependency_details(
        self, dependencies: DependencyReport
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Create detailed dependency breakdown."""
        details = {}

        for dep_type, dep_list in dependencies.dependencies.items():
            if dep_list:
                details[dep_type.value] = []
                for dep in dep_list:
                    dep_dict = {
                        "name": getattr(dep, "constraint_name", None)
                        or getattr(dep, "view_name", None)
                        or getattr(dep, "trigger_name", None)
                        or getattr(dep, "index_name", None)
                        or "unknown",
                        "impact_level": dep.impact_level.value,
                        "type": dep.dependency_type.value,
                    }

                    # Add type-specific details
                    if isinstance(dep, ForeignKeyDependency):
                        dep_dict.update(
                            {
                                "source_table": dep.source_table,
                                "source_column": dep.source_column,
                                "target_table": dep.target_table,
                                "target_column": dep.target_column,
                                "on_delete": dep.on_delete,
                                "on_update": dep.on_update,
                            }
                        )
                    elif isinstance(dep, ViewDependency):
                        dep_dict.update(
                            {
                                "schema_name": dep.schema_name,
                                "is_materialized": dep.is_materialized,
                                "definition": (
                                    dep.view_definition[:100] + "..."
                                    if len(dep.view_definition) > 100
                                    else dep.view_definition
                                ),
                            }
                        )
                    elif isinstance(dep, TriggerDependency):
                        dep_dict.update(
                            {
                                "event": dep.event,
                                "timing": dep.timing,
                                "function_name": dep.function_name,
                            }
                        )
                    elif isinstance(dep, IndexDependency):
                        dep_dict.update(
                            {
                                "index_type": dep.index_type,
                                "columns": dep.columns,
                                "is_unique": dep.is_unique,
                                "is_partial": dep.is_partial,
                            }
                        )
                    elif isinstance(dep, ConstraintDependency):
                        dep_dict.update(
                            {
                                "constraint_type": dep.constraint_type,
                                "definition": dep.definition,
                                "columns": dep.columns,
                            }
                        )

                    details[dep_type.value].append(dep_dict)

        return details

    def _create_dependency_specific_recommendations(
        self, dependencies: DependencyReport
    ) -> List[Recommendation]:
        """Create recommendations for specific dependency types."""
        recommendations = []

        # Foreign key specific recommendations
        fk_deps = dependencies.dependencies.get(DependencyType.FOREIGN_KEY, [])
        if fk_deps:
            critical_fks = [
                dep for dep in fk_deps if dep.impact_level == ImpactLevel.CRITICAL
            ]
            if critical_fks:
                recommendations.append(
                    Recommendation(
                        type=RecommendationType.REQUIRES_FIXES,
                        title="🔗 Foreign Key Dependencies Require Action",
                        description=f"Found {len(critical_fks)} foreign key constraints that must be addressed.",
                        action_steps=[
                            "Identify all referencing tables",
                            "Update application code to handle missing column",
                            "Drop foreign key constraints in correct order",
                            "Consider data migration if needed",
                        ],
                        priority=ImpactLevel.CRITICAL,
                        sql_example="ALTER TABLE referencing_table DROP CONSTRAINT fk_constraint_name;",
                    )
                )

        # View specific recommendations
        view_deps = dependencies.dependencies.get(DependencyType.VIEW, [])
        if view_deps:
            recommendations.append(
                Recommendation(
                    type=RecommendationType.REVIEW_REQUIRED,
                    title="👁️ Views Will Be Affected",
                    description=f"Found {len(view_deps)} views that reference this column.",
                    action_steps=[
                        "Review each view definition",
                        "Update view queries to exclude the column",
                        "Test view functionality after updates",
                        "Coordinate with teams using these views",
                    ],
                    priority=ImpactLevel.HIGH,
                    sql_example="CREATE OR REPLACE VIEW view_name AS SELECT col1, col2 FROM table;",
                )
            )

        # Index specific recommendations
        index_deps = dependencies.dependencies.get(DependencyType.INDEX, [])
        if index_deps:
            unique_indexes = [
                dep for dep in index_deps if getattr(dep, "is_unique", False)
            ]
            if unique_indexes:
                recommendations.append(
                    Recommendation(
                        type=RecommendationType.PROCEED_WITH_CAUTION,
                        title="📊 Unique Indexes Will Be Dropped",
                        description=f"Found {len(unique_indexes)} unique indexes that will be automatically removed.",
                        action_steps=[
                            "Verify no application logic depends on uniqueness",
                            "Consider alternative uniqueness constraints",
                            "Monitor for constraint violations after removal",
                        ],
                        priority=ImpactLevel.MEDIUM,
                    )
                )

        return recommendations

    def _format_console_report(
        self, report: ImpactReport, include_details: bool = True
    ) -> str:
        """Format report for console display."""
        assessment = report.assessment
        risk_icon = self.impact_icons.get(assessment.overall_risk, "❓")

        # Determine header style based on risk
        if assessment.overall_risk == ImpactLevel.CRITICAL:
            header_text = f"{risk_icon} CRITICAL IMPACT DETECTED"
            border_char = "═"
        elif assessment.overall_risk == ImpactLevel.HIGH:
            header_text = f"{risk_icon} HIGH IMPACT DETECTED"
            border_char = "─"
        else:
            header_text = f"{risk_icon} IMPACT ANALYSIS COMPLETE"
            border_char = "─"

        lines = [
            "",
            f"╭{border_char * 59}╮",
            f"│ {header_text:<57} │",
            f"│ Removing column '{assessment.table_name}.{assessment.column_name}' will affect: {'':<17} │",
            f"│{' ' * 59}│",
        ]

        # Add impact breakdown
        if assessment.critical_dependencies > 0:
            lines.append(
                f"│ 🔴 BREAKS ({assessment.critical_dependencies} objects): {'':<39} │"
            )
            lines.extend(self._format_critical_dependencies_summary(report))
            lines.append(f"│{' ' * 59}│")

        if assessment.high_impact_dependencies > 0:
            lines.append(
                f"│ 🟡 PERFORMANCE IMPACT ({assessment.high_impact_dependencies} objects): {'':<27} │"
            )
            lines.extend(self._format_high_impact_dependencies_summary(report))
            lines.append(f"│{' ' * 59}│")

        # Add data backup info
        if assessment.estimated_data_rows > 0:
            lines.append(
                f"│ 💾 DATA BACKUP: {assessment.estimated_data_rows:,} rows to backup {'':<24} │"
            )
            lines.append(f"│{' ' * 59}│")

        # Add primary recommendation
        if report.recommendations:
            primary_rec = report.recommendations[0]
            rec_icon = (
                "❌" if primary_rec.type == RecommendationType.DO_NOT_REMOVE else "✅"
            )
            lines.append(
                f"│ {rec_icon} RECOMMENDATION: {primary_rec.type.value.replace('_', ' ').upper()} {'':<20} │"
            )

            # Add recommendation description (wrapped)
            description_words = primary_rec.description.split()
            current_line = "│    "
            for word in description_words:
                if len(current_line) + len(word) + 1 > 58:
                    lines.append(f"{current_line:<59} │")
                    current_line = f"│    {word}"
                else:
                    current_line += f" {word}" if current_line != "│    " else word
            if current_line.strip() != "│":
                lines.append(f"{current_line:<59} │")

        lines.append(f"╰{border_char * 59}╯")
        lines.append("")

        # Add detailed breakdown if requested
        if include_details and report.dependency_details:
            lines.append("📋 DETAILED DEPENDENCY BREAKDOWN:")
            lines.append("─" * 50)

            for dep_type, dep_list in report.dependency_details.items():
                if dep_list:
                    icon = self.dependency_icons.get(DependencyType(dep_type), "📋")
                    lines.append(
                        f"\n{icon} {dep_type.upper().replace('_', ' ')} ({len(dep_list)}):"
                    )

                    for dep in dep_list[:5]:  # Limit to first 5 for readability
                        impact_icon = self.impact_icons.get(
                            ImpactLevel(dep["impact_level"]), "❓"
                        )
                        lines.append(f"  {impact_icon} {dep['name']}")

                    if len(dep_list) > 5:
                        lines.append(f"  ... and {len(dep_list) - 5} more")

        # Add action steps from primary recommendation
        if report.recommendations and report.recommendations[0].action_steps:
            lines.append("\n🔧 RECOMMENDED ACTIONS:")
            lines.append("─" * 30)
            for i, step in enumerate(report.recommendations[0].action_steps, 1):
                lines.append(f"{i}. {step}")

        return "\n".join(lines)

    def _format_critical_dependencies_summary(self, report: ImpactReport) -> List[str]:
        """Format critical dependencies summary for console display."""
        lines = []
        critical_deps = []

        # Collect critical dependencies
        for dep_type_name, dep_list in report.dependency_details.items():
            for dep in dep_list:
                if dep["impact_level"] == "critical":
                    dep_icon = self.dependency_icons.get(
                        DependencyType(dep_type_name), "📋"
                    )
                    critical_deps.append(f"{dep_icon} {dep['name']}")

        # Add up to 3 critical dependencies to the summary box
        for dep in critical_deps[:3]:
            lines.append(f"│   • {dep:<53} │")

        if len(critical_deps) > 3:
            lines.append(
                f"│   ... and {len(critical_deps) - 3} more critical dependencies {'':<16} │"
            )

        return lines

    def _format_high_impact_dependencies_summary(
        self, report: ImpactReport
    ) -> List[str]:
        """Format high impact dependencies summary for console display."""
        lines = []
        high_impact_deps = []

        # Collect high impact dependencies
        for dep_type_name, dep_list in report.dependency_details.items():
            for dep in dep_list:
                if dep["impact_level"] == "high":
                    dep_icon = self.dependency_icons.get(
                        DependencyType(dep_type_name), "📋"
                    )
                    high_impact_deps.append(f"{dep_icon} {dep['name']}")

        # Add up to 2 high impact dependencies to the summary box
        for dep in high_impact_deps[:2]:
            lines.append(f"│   • {dep:<53} │")

        if len(high_impact_deps) > 2:
            lines.append(
                f"│   ... and {len(high_impact_deps) - 2} more high impact objects {'':<17} │"
            )

        return lines

    def _format_json_report(self, report: ImpactReport) -> str:
        """Format report as JSON."""
        return json.dumps(report.to_dict(), indent=2, ensure_ascii=False)

    def _format_html_report(
        self, report: ImpactReport, include_details: bool = True
    ) -> str:
        """Format report as HTML."""
        assessment = report.assessment
        risk_class = assessment.overall_risk.value.lower()

        html = f"""
        <div class="impact-report {risk_class}-risk">
            <div class="report-header">
                <h2>{self.impact_icons.get(assessment.overall_risk, '')} Column Removal Impact Report</h2>
                <p class="target-column">Target: <code>{assessment.table_name}.{assessment.column_name}</code></p>
            </div>

            <div class="impact-summary">
                <div class="risk-indicator {risk_class}">
                    Risk Level: {assessment.overall_risk.value.upper()}
                </div>
                <div class="dependency-counts">
                    <span class="critical">Critical: {assessment.critical_dependencies}</span>
                    <span class="high">High: {assessment.high_impact_dependencies}</span>
                    <span class="medium">Medium: {assessment.medium_impact_dependencies}</span>
                    <span class="low">Low: {assessment.low_impact_dependencies}</span>
                </div>
            </div>

            <div class="recommendations">
                <h3>Recommendations</h3>
        """

        for rec in report.recommendations:
            rec_class = rec.type.value.replace("_", "-")
            html += f"""
                <div class="recommendation {rec_class}">
                    <h4>{escape(rec.title)}</h4>
                    <p>{escape(rec.description)}</p>
                    <ul class="action-steps">
            """
            for step in rec.action_steps:
                html += f"<li>{escape(step)}</li>"
            html += "</ul></div>"

        if include_details and report.dependency_details:
            html += '<div class="dependency-details"><h3>Dependency Details</h3>'

            for dep_type, dep_list in report.dependency_details.items():
                if dep_list:
                    icon = self.dependency_icons.get(DependencyType(dep_type), "📋")
                    html += f"""
                        <div class="dependency-group">
                            <h4>{icon} {dep_type.replace('_', ' ').title()} ({len(dep_list)})</h4>
                            <ul>
                    """
                    for dep in dep_list:
                        impact_icon = self.impact_icons.get(
                            ImpactLevel(dep["impact_level"]), "❓"
                        )
                        html += f"<li class='{dep['impact_level']}-impact'>{impact_icon} {escape(dep['name'])}</li>"
                    html += "</ul></div>"

            html += "</div>"

        html += "</div>"

        # Add CSS for styling
        css = """
        <style>
        .impact-report { font-family: Arial, sans-serif; max-width: 800px; margin: 20px; }
        .report-header { background: #f5f5f5; padding: 20px; border-radius: 8px; margin-bottom: 20px; }
        .critical-risk .report-header { background: #ffebee; border-left: 4px solid #f44336; }
        .high-risk .report-header { background: #fff3e0; border-left: 4px solid #ff9800; }
        .target-column { font-size: 18px; margin-top: 10px; }
        .impact-summary { display: flex; gap: 20px; margin-bottom: 20px; }
        .risk-indicator { padding: 10px 15px; border-radius: 4px; font-weight: bold; }
        .risk-indicator.critical { background: #ffcdd2; color: #c62828; }
        .risk-indicator.high { background: #ffe0b2; color: #e65100; }
        .risk-indicator.medium { background: #fff9c4; color: #f57f17; }
        .dependency-counts span { margin-right: 15px; }
        .recommendation { border: 1px solid #ddd; border-radius: 4px; padding: 15px; margin-bottom: 15px; }
        .recommendation.do-not-remove { border-color: #f44336; background: #ffebee; }
        .recommendation.safe-to-remove { border-color: #4caf50; background: #e8f5e8; }
        .action-steps { margin-top: 10px; }
        .dependency-group { margin-bottom: 20px; }
        .critical-impact { color: #c62828; font-weight: bold; }
        .high-impact { color: #e65100; }
        </style>
        """

        return css + html

    def _format_summary_report(self, report: ImpactReport) -> str:
        """Format brief summary report."""
        assessment = report.assessment
        risk_icon = self.impact_icons.get(assessment.overall_risk, "❓")

        summary_lines = [
            f"{risk_icon} Column: {assessment.table_name}.{assessment.column_name}",
            f"Dependencies: {assessment.total_dependencies} total",
            f"Risk: {assessment.overall_risk.value.upper()}",
        ]

        if report.recommendations:
            primary_rec = report.recommendations[0]
            summary_lines.append(
                f"Action: {primary_rec.type.value.replace('_', ' ').upper()}"
            )

        return " | ".join(summary_lines)
