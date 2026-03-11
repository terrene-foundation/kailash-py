#!/usr/bin/env python3
"""
Multi-Format Report Formatters for Impact Analysis Reporter - TODO-140 Phase 3

Provides comprehensive formatting capabilities for impact analysis reports across
multiple output formats: Console (rich terminal), JSON (API integration),
HTML (web dashboards), and Summary (brief overviews).

FORMATTING CAPABILITIES:
- Console: Rich terminal output with emoji indicators, progress bars, and colored sections
- JSON: Structured data format for API integration and system consumption
- HTML: Responsive web dashboard format with charts and interactive elements
- Summary: Brief executive overview format for quick consumption

VISUAL ELEMENTS:
- Risk level indicators with emoji and color coding
- Progress charts for risk reduction roadmaps
- Executive dashboard layouts with key metrics
- Technical implementation guides with step-by-step formatting
- Compliance audit reports with formal documentation structure

INTEGRATION POINTS:
- Uses Phase 1 RiskAssessmentEngine data for risk visualization
- Uses Phase 2 MitigationStrategyEngine data for strategy presentation
- Integrates with ImpactAnalysisReporter for complete report formatting
- Supports progressive disclosure from summary to detailed views
"""

import json
import logging
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from enum import Enum
from html import escape
from typing import Any, Dict, List, Optional, Tuple, Union

from .impact_analysis_reporter import (
    ComplianceAuditReport,
    ComprehensiveImpactReport,
    ExecutiveRiskSummary,
    ReportFormat,
    ReportSection,
    StakeholderReport,
    StakeholderRole,
    TechnicalImpactReport,
)
from .mitigation_strategy_engine import (
    MitigationPriority,
    MitigationStrategy,
    PrioritizedMitigationPlan,
)
from .risk_assessment_engine import ComprehensiveRiskAssessment, RiskCategory, RiskLevel

logger = logging.getLogger(__name__)


class FormatStyle(Enum):
    """Visual styling options for reports."""

    MINIMAL = "minimal"  # Clean, minimal formatting
    STANDARD = "standard"  # Standard business formatting
    RICH = "rich"  # Rich formatting with colors/emojis
    EXECUTIVE = "executive"  # High-level executive presentation
    TECHNICAL = "technical"  # Detailed technical formatting


@dataclass
class ConsoleTheme:
    """Console color and emoji theme configuration."""

    # Risk level colors (ANSI codes)
    risk_colors: Dict[RiskLevel, str] = None

    # Risk level emojis
    risk_emojis: Dict[RiskLevel, str] = None

    # Section separators
    section_separator: str = "─" * 80
    subsection_separator: str = "─" * 60

    # Progress indicators
    progress_filled: str = "█"
    progress_empty: str = "░"
    progress_width: int = 40

    def __post_init__(self):
        if self.risk_colors is None:
            self.risk_colors = {
                RiskLevel.LOW: "\033[32m",  # Green
                RiskLevel.MEDIUM: "\033[33m",  # Yellow
                RiskLevel.HIGH: "\033[31m",  # Red
                RiskLevel.CRITICAL: "\033[35m",  # Magenta
            }

        if self.risk_emojis is None:
            self.risk_emojis = {
                RiskLevel.LOW: "✅",
                RiskLevel.MEDIUM: "🟡",
                RiskLevel.HIGH: "⚠️",
                RiskLevel.CRITICAL: "❌",
            }


class ReportFormatter:
    """
    Multi-format report formatter for impact analysis reports.

    Provides comprehensive formatting across console, JSON, HTML, and summary
    formats with consistent styling and progressive disclosure capabilities.
    """

    def __init__(
        self,
        console_theme: Optional[ConsoleTheme] = None,
        html_template_path: Optional[str] = None,
        enable_colors: bool = True,
        enable_emojis: bool = True,
    ):
        """
        Initialize the report formatter.

        Args:
            console_theme: Console color and emoji theme
            html_template_path: Path to custom HTML templates
            enable_colors: Enable colored console output
            enable_emojis: Enable emoji indicators
        """
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

        self.console_theme = console_theme or ConsoleTheme()
        self.html_template_path = html_template_path
        self.enable_colors = enable_colors
        self.enable_emojis = enable_emojis

        # Color reset code
        self.color_reset = "\033[0m" if enable_colors else ""

        # Initialize HTML templates
        self._initialize_html_templates()

    def format_report(
        self,
        report: ComprehensiveImpactReport,
        format_type: ReportFormat,
        style: FormatStyle = FormatStyle.STANDARD,
        sections: Optional[List[ReportSection]] = None,
    ) -> str:
        """
        Format comprehensive impact report in specified format.

        Args:
            report: Complete impact analysis report
            format_type: Output format (Console, JSON, HTML, Summary)
            style: Visual styling preference
            sections: Specific sections to include (default: all)

        Returns:
            Formatted report string
        """
        start_time = time.time()

        if sections is None:
            sections = list(ReportSection)

        self.logger.debug(
            f"Formatting report {report.report_id} as {format_type.value}"
        )

        try:
            if format_type == ReportFormat.CONSOLE:
                formatted = self._format_console_report(report, style, sections)
            elif format_type == ReportFormat.JSON:
                formatted = self._format_json_report(report, sections)
            elif format_type == ReportFormat.HTML:
                formatted = self._format_html_report(report, style, sections)
            elif format_type == ReportFormat.SUMMARY:
                formatted = self._format_summary_report(report, style)
            else:
                raise ValueError(f"Unsupported format type: {format_type}")

            format_time = time.time() - start_time
            self.logger.debug(f"Report formatted in {format_time:.3f}s")

            return formatted

        except Exception as e:
            self.logger.error(f"Failed to format report: {e}")
            raise

    # Console formatting methods

    def _format_console_report(
        self,
        report: ComprehensiveImpactReport,
        style: FormatStyle,
        sections: List[ReportSection],
    ) -> str:
        """Format report for rich console output."""
        # Override emoji and theme settings for MINIMAL style
        original_enable_emojis = self.enable_emojis
        original_theme = self.console_theme
        if style == FormatStyle.MINIMAL:
            self.enable_emojis = False
            # Use ASCII-only theme for minimal style
            minimal_theme = ConsoleTheme()
            minimal_theme.section_separator = "-" * 80
            minimal_theme.subsection_separator = "-" * 60
            minimal_theme.progress_filled = "="
            minimal_theme.progress_empty = "-"
            minimal_theme.progress_width = 40
            minimal_theme.risk_colors = original_theme.risk_colors
            minimal_theme.risk_emojis = {}
            self.console_theme = minimal_theme

        output = []

        # Report header
        output.append(self._format_console_header(report, style))

        # Executive summary section
        if ReportSection.EXECUTIVE_SUMMARY in sections:
            output.append(
                self._format_console_executive_summary(report.executive_summary, style)
            )

        # Risk breakdown section
        if ReportSection.RISK_BREAKDOWN in sections:
            output.append(
                self._format_console_risk_breakdown(report.risk_assessment, style)
            )

        # Mitigation overview section
        if ReportSection.MITIGATION_OVERVIEW in sections and report.mitigation_plan:
            output.append(
                self._format_console_mitigation_overview(report.mitigation_plan, style)
            )

        # Technical details section
        if ReportSection.TECHNICAL_DETAILS in sections:
            output.append(
                self._format_console_technical_details(report.technical_report, style)
            )

        # Compliance audit section
        if ReportSection.COMPLIANCE_AUDIT in sections:
            output.append(
                self._format_console_compliance_audit(report.compliance_report, style)
            )

        # Stakeholder actions section
        if ReportSection.STAKEHOLDER_ACTIONS in sections:
            output.append(
                self._format_console_stakeholder_actions(
                    report.stakeholder_communications, style
                )
            )

        # Report footer
        output.append(self._format_console_footer(report, style))

        # Restore original settings
        self.enable_emojis = original_enable_emojis
        if style == FormatStyle.MINIMAL:
            self.console_theme = original_theme

        return "\n\n".join(output)

    def _format_console_header(
        self, report: ComprehensiveImpactReport, style: FormatStyle
    ) -> str:
        """Format console report header."""
        header = []

        if style in [FormatStyle.RICH, FormatStyle.EXECUTIVE]:
            header.append("🎯 MIGRATION RISK ASSESSMENT - IMPACT ANALYSIS REPORT")
        else:
            header.append("MIGRATION RISK ASSESSMENT - IMPACT ANALYSIS REPORT")

        header.append(self.console_theme.section_separator)
        header.append(f"Report ID: {report.report_id}")
        header.append(f"Operation ID: {report.operation_id}")
        header.append(f"Generated: {report.generation_timestamp}")
        header.append(f"Version: {report.report_version}")

        return "\n".join(header)

    def _format_console_executive_summary(
        self, summary: ExecutiveRiskSummary, style: FormatStyle
    ) -> str:
        """Format executive summary for console."""
        output = []

        # Section header
        if style in [FormatStyle.RICH, FormatStyle.EXECUTIVE]:
            output.append("💼 EXECUTIVE SUMMARY")
        else:
            output.append("EXECUTIVE SUMMARY")
        output.append(self.console_theme.subsection_separator)

        # Risk level with color and emoji
        risk_color = self.console_theme.risk_colors.get(summary.overall_risk_level, "")
        risk_emoji = self.console_theme.risk_emojis.get(summary.overall_risk_level, "")

        if self.enable_colors and self.enable_emojis:
            risk_display = f"{risk_color}{risk_emoji} {summary.overall_risk_level.value.upper()} ({summary.overall_risk_score:.1f}/100){self.color_reset}"
        elif self.enable_colors:
            risk_display = f"{risk_color}{summary.overall_risk_level.value.upper()} ({summary.overall_risk_score:.1f}/100){self.color_reset}"
        else:
            risk_display = f"{summary.overall_risk_level.value.upper()} ({summary.overall_risk_score:.1f}/100)"

        # Executive summary content
        output.append(f"Operation: {summary.operation_description}")
        output.append(f"Risk Level: {risk_display}")
        output.append(f"Business Impact: {summary.business_impact}")
        output.append(f"Approval Required: {summary.approval_level}")
        output.append("")

        # Business metrics box
        if style in [FormatStyle.RICH, FormatStyle.EXECUTIVE]:
            output.append("📊 BUSINESS METRICS:")
        else:
            output.append("BUSINESS METRICS:")

        output.append(
            f"  • Potential Downtime: {summary.potential_downtime_minutes:.1f} minutes"
        )
        output.append(f"  • Affected Systems: {summary.affected_systems_count}")
        output.append(f"  • Revenue Risk: {summary.revenue_risk_estimate}")
        output.append(f"  • User Impact: {summary.user_impact_estimate}")
        output.append("")

        # Mitigation summary
        if style in [FormatStyle.RICH, FormatStyle.EXECUTIVE]:
            output.append("🛡️ MITIGATION SUMMARY:")
        else:
            output.append("MITIGATION SUMMARY:")

        output.append(
            f"  • Strategies Available: {summary.mitigation_strategies_count}"
        )
        output.append(
            f"  • Risk Reduction Potential: {summary.risk_reduction_potential:.1f}%"
        )
        output.append(f"  • Implementation Timeline: {summary.implementation_timeline}")
        output.append(f"  • Resource Requirements: {summary.resource_requirements}")
        output.append("")

        # Decision recommendation
        if summary.overall_risk_level == RiskLevel.CRITICAL:
            decision_icon = "🚫" if self.enable_emojis else ""
        elif summary.overall_risk_level == RiskLevel.HIGH:
            decision_icon = "⚠️" if self.enable_emojis else ""
        else:
            decision_icon = "✅" if self.enable_emojis else ""

        output.append(
            f"{decision_icon} RECOMMENDATION: {summary.go_no_go_recommendation}"
        )

        return "\n".join(output)

    def _format_console_risk_breakdown(
        self, assessment: ComprehensiveRiskAssessment, style: FormatStyle
    ) -> str:
        """Format risk breakdown for console."""
        output = []

        # Section header
        if style in [FormatStyle.RICH, FormatStyle.TECHNICAL]:
            output.append("📈 RISK BREAKDOWN BY CATEGORY")
        else:
            output.append("RISK BREAKDOWN BY CATEGORY")
        output.append(self.console_theme.subsection_separator)

        # Risk categories with progress bars
        for category, risk_score in assessment.category_scores.items():
            category_name = category.value.replace("_", " ").title()

            # Risk score progress bar
            progress_bar = self._create_console_progress_bar(
                risk_score.score, 100, self.console_theme.progress_width
            )

            # Risk level indicator
            risk_color = self.console_theme.risk_colors.get(risk_score.level, "")
            risk_emoji = self.console_theme.risk_emojis.get(risk_score.level, "")

            if self.enable_colors and self.enable_emojis:
                level_display = f"{risk_color}{risk_emoji} {risk_score.level.value.upper()}{self.color_reset}"
            elif self.enable_colors:
                level_display = (
                    f"{risk_color}{risk_score.level.value.upper()}{self.color_reset}"
                )
            else:
                level_display = risk_score.level.value.upper()

            output.append(
                f"{category_name:20} [{progress_bar}] {risk_score.score:5.1f} {level_display}"
            )
            output.append(f"  └─ {risk_score.description}")

            # Show top risk factors
            if risk_score.risk_factors and style in [
                FormatStyle.TECHNICAL,
                FormatStyle.RICH,
            ]:
                for factor in risk_score.risk_factors[:2]:  # Show top 2 factors
                    output.append(f"     • {factor}")

            output.append("")

        return "\n".join(output)

    def _format_console_mitigation_overview(
        self, mitigation_plan: Any, style: FormatStyle
    ) -> str:
        """Format mitigation overview for console."""
        output = []

        # Section header
        if style in [FormatStyle.RICH, FormatStyle.EXECUTIVE]:
            output.append("🛡️ MITIGATION STRATEGY OVERVIEW")
        else:
            output.append("MITIGATION STRATEGY OVERVIEW")
        output.append(self.console_theme.subsection_separator)

        if hasattr(mitigation_plan, "mitigation_strategies"):
            strategies = mitigation_plan.mitigation_strategies

            # Summary statistics
            total_strategies = len(strategies)
            critical_strategies = len(
                [
                    s
                    for s in strategies
                    if hasattr(s, "priority") and s.priority.value == "critical"
                ]
            )
            high_strategies = len(
                [
                    s
                    for s in strategies
                    if hasattr(s, "priority") and s.priority.value == "high"
                ]
            )

            output.append(f"Total Strategies: {total_strategies}")
            output.append(f"Critical Priority: {critical_strategies}")
            output.append(f"High Priority: {high_strategies}")

            if hasattr(mitigation_plan, "total_estimated_effort"):
                output.append(
                    f"Total Effort: {mitigation_plan.total_estimated_effort:.1f} hours"
                )

            output.append("")

            # Top strategies by priority
            output.append("TOP PRIORITY STRATEGIES:")

            # Sort strategies by priority for display
            priority_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
            sorted_strategies = sorted(
                strategies[:5],  # Top 5
                key=lambda s: priority_order.get(
                    getattr(s, "priority", type("", (), {"value": "low"})).value, 99
                ),
            )

            for i, strategy in enumerate(sorted_strategies, 1):
                priority_emoji = {
                    "critical": "🔴",
                    "high": "🟠",
                    "medium": "🟡",
                    "low": "🟢",
                }.get(
                    getattr(strategy, "priority", type("", (), {"value": "low"})).value,
                    "⚪",
                )

                if self.enable_emojis:
                    output.append(
                        f"{i}. {priority_emoji} {getattr(strategy, 'name', 'Unknown Strategy')}"
                    )
                else:
                    priority_text = getattr(
                        strategy, "priority", type("", (), {"value": "low"})
                    ).value.upper()
                    output.append(
                        f"{i}. [{priority_text}] {getattr(strategy, 'name', 'Unknown Strategy')}"
                    )

                if hasattr(strategy, "description"):
                    output.append(f"   {strategy.description}")

                if hasattr(strategy, "estimated_effort_hours"):
                    output.append(
                        f"   Effort: {strategy.estimated_effort_hours:.1f} hours"
                    )

                output.append("")

        return "\n".join(output)

    def _format_console_technical_details(
        self, technical_report: TechnicalImpactReport, style: FormatStyle
    ) -> str:
        """Format technical details for console."""
        output = []

        # Section header
        if style in [FormatStyle.RICH, FormatStyle.TECHNICAL]:
            output.append("🔧 TECHNICAL IMPLEMENTATION DETAILS")
        else:
            output.append("TECHNICAL IMPLEMENTATION DETAILS")
        output.append(self.console_theme.subsection_separator)

        # Pre-migration steps
        output.append("PRE-MIGRATION STEPS:")
        for i, step in enumerate(technical_report.pre_migration_steps, 1):
            output.append(f"  {i}. {step}")
        output.append("")

        # Migration procedure
        output.append("MIGRATION PROCEDURE:")
        for i, step in enumerate(technical_report.migration_procedure, 1):
            output.append(f"  {i}. {step}")
        output.append("")

        # Post-migration validation
        output.append("POST-MIGRATION VALIDATION:")
        for i, step in enumerate(technical_report.post_migration_validation, 1):
            output.append(f"  {i}. {step}")
        output.append("")

        # Rollback procedures
        if style in [FormatStyle.TECHNICAL, FormatStyle.RICH]:
            output.append("ROLLBACK PROCEDURES:")
            for i, step in enumerate(technical_report.rollback_procedures, 1):
                output.append(f"  {i}. {step}")
            output.append("")

        # Infrastructure requirements
        if technical_report.infrastructure_requirements:
            output.append("INFRASTRUCTURE REQUIREMENTS:")
            for req in technical_report.infrastructure_requirements:
                output.append(f"  • {req}")
            output.append("")

        return "\n".join(output)

    def _format_console_compliance_audit(
        self, compliance_report: ComplianceAuditReport, style: FormatStyle
    ) -> str:
        """Format compliance audit information for console."""
        output = []

        # Section header
        if style in [FormatStyle.RICH, FormatStyle.EXECUTIVE]:
            output.append("📋 COMPLIANCE & AUDIT REQUIREMENTS")
        else:
            output.append("COMPLIANCE & AUDIT REQUIREMENTS")
        output.append(self.console_theme.subsection_separator)

        # Regulatory frameworks
        output.append("APPLICABLE REGULATIONS:")
        for framework in compliance_report.regulatory_frameworks:
            output.append(f"  • {framework}")
        output.append("")

        # Change classification
        if "change_classification" in compliance_report.change_management_documentation:
            output.append(
                f"Change Classification: {compliance_report.change_management_documentation['change_classification']}"
            )

        # Approval workflow
        if compliance_report.approval_workflows:
            output.append("APPROVAL WORKFLOW:")
            for i, step in enumerate(compliance_report.approval_workflows, 1):
                output.append(f"  {step}")
        output.append("")

        # Documentation requirements
        if compliance_report.change_management_documentation.get(
            "documentation_requirements"
        ):
            output.append("DOCUMENTATION REQUIREMENTS:")
            for req in compliance_report.change_management_documentation[
                "documentation_requirements"
            ]:
                output.append(f"  • {req}")
        output.append("")

        # Risk acceptance criteria
        if compliance_report.risk_acceptance_criteria:
            output.append("RISK ACCEPTANCE CRITERIA:")
            for criteria in compliance_report.risk_acceptance_criteria:
                output.append(f"  • {criteria}")

        return "\n".join(output)

    def _format_console_stakeholder_actions(
        self,
        stakeholder_communications: Dict[StakeholderRole, StakeholderReport],
        style: FormatStyle,
    ) -> str:
        """Format stakeholder actions for console."""
        output = []

        # Section header
        if style in [FormatStyle.RICH, FormatStyle.EXECUTIVE]:
            output.append("👥 STAKEHOLDER ACTION ITEMS")
        else:
            output.append("STAKEHOLDER ACTION ITEMS")
        output.append(self.console_theme.subsection_separator)

        # Key stakeholder roles with actions
        key_roles = [
            StakeholderRole.EXECUTIVE,
            StakeholderRole.MANAGER,
            StakeholderRole.TECHNICAL_LEAD,
            StakeholderRole.DBA,
        ]

        for role in key_roles:
            if role in stakeholder_communications:
                stakeholder_report = stakeholder_communications[role]

                role_name = role.value.replace("_", " ").title()

                if stakeholder_report.action_items:
                    output.append(f"{role_name.upper()}:")
                    for action in stakeholder_report.action_items:
                        output.append(f"  • {action}")
                    output.append("")

        return "\n".join(output)

    def _format_console_footer(
        self, report: ComprehensiveImpactReport, style: FormatStyle
    ) -> str:
        """Format console report footer."""
        footer = []

        footer.append(self.console_theme.section_separator)
        footer.append(
            f"Report generated in {report.generation_time_seconds:.3f} seconds"
        )
        footer.append(f"Report size: {report.report_size_estimate}")

        if style in [FormatStyle.RICH, FormatStyle.EXECUTIVE]:
            footer.append("")
            footer.append("🤖 Generated with DataFlow Risk Assessment Engine")
        else:
            footer.append("")
            footer.append("Generated with DataFlow Risk Assessment Engine")

        return "\n".join(footer)

    # JSON formatting methods

    def _convert_enums_to_values(self, obj: Any) -> Any:
        """Recursively convert enum values to their string representation."""
        if isinstance(obj, Enum):
            return obj.value
        elif isinstance(obj, dict):
            return {
                self._convert_enums_to_values(k): self._convert_enums_to_values(v)
                for k, v in obj.items()
            }
        elif isinstance(obj, list):
            return [self._convert_enums_to_values(item) for item in obj]
        elif isinstance(obj, tuple):
            return tuple(self._convert_enums_to_values(item) for item in obj)
        else:
            return obj

    def _format_json_report(
        self, report: ComprehensiveImpactReport, sections: List[ReportSection]
    ) -> str:
        """Format report as structured JSON."""

        # Build JSON structure with only requested sections
        json_data = {
            "report_metadata": {
                "report_id": report.report_id,
                "operation_id": report.operation_id,
                "generation_timestamp": report.generation_timestamp,
                "report_version": report.report_version,
                "generation_time_seconds": report.generation_time_seconds,
                "format": "json",
            }
        }

        # Add sections based on request
        if ReportSection.EXECUTIVE_SUMMARY in sections:
            exec_summary_dict = asdict(report.executive_summary)
            json_data["executive_summary"] = self._convert_enums_to_values(
                exec_summary_dict
            )

        if ReportSection.RISK_BREAKDOWN in sections:
            json_data["risk_assessment"] = self._risk_assessment_to_dict(
                report.risk_assessment
            )

        if ReportSection.MITIGATION_OVERVIEW in sections and report.mitigation_plan:
            json_data["mitigation_plan"] = self._mitigation_plan_to_dict(
                report.mitigation_plan
            )

        if ReportSection.TECHNICAL_DETAILS in sections:
            tech_report_dict = asdict(report.technical_report)
            # Convert enums to values in the technical report
            json_data["technical_report"] = self._convert_enums_to_values(
                tech_report_dict
            )

        if ReportSection.COMPLIANCE_AUDIT in sections:
            compliance_dict = asdict(report.compliance_report)
            json_data["compliance_report"] = self._convert_enums_to_values(
                compliance_dict
            )

        if ReportSection.STAKEHOLDER_ACTIONS in sections:
            stakeholder_data = {}
            for role, stakeholder_report in report.stakeholder_communications.items():
                report_dict = asdict(stakeholder_report)
                stakeholder_data[role.value] = self._convert_enums_to_values(
                    report_dict
                )
            json_data["stakeholder_communications"] = stakeholder_data

        return json.dumps(json_data, indent=2, default=str)

    # HTML formatting methods

    def _format_html_report(
        self,
        report: ComprehensiveImpactReport,
        style: FormatStyle,
        sections: List[ReportSection],
    ) -> str:
        """Format report as HTML dashboard."""

        html_parts = []

        # HTML header
        html_parts.append(self._get_html_header(report, style))

        # Executive dashboard
        if ReportSection.EXECUTIVE_SUMMARY in sections:
            html_parts.append(
                self._format_html_executive_summary(report.executive_summary, style)
            )

        # Risk visualization
        if ReportSection.RISK_BREAKDOWN in sections:
            html_parts.append(
                self._format_html_risk_breakdown(report.risk_assessment, style)
            )

        # Mitigation strategies
        if ReportSection.MITIGATION_OVERVIEW in sections and report.mitigation_plan:
            html_parts.append(
                self._format_html_mitigation_overview(report.mitigation_plan, style)
            )

        # Technical details
        if ReportSection.TECHNICAL_DETAILS in sections:
            html_parts.append(
                self._format_html_technical_details(report.technical_report, style)
            )

        # HTML footer
        html_parts.append(self._get_html_footer(report))

        return "\n".join(html_parts)

    def _format_summary_report(
        self, report: ComprehensiveImpactReport, style: FormatStyle
    ) -> str:
        """Format brief executive summary report."""

        summary = report.executive_summary
        assessment = report.risk_assessment

        # Risk level indicator
        risk_emoji = self.console_theme.risk_emojis.get(summary.overall_risk_level, "")

        lines = []
        lines.append("MIGRATION RISK ASSESSMENT - EXECUTIVE SUMMARY")
        lines.append("=" * 50)
        lines.append("")

        if self.enable_emojis:
            lines.append(
                f"{risk_emoji} Risk Level: {summary.overall_risk_level.value.upper()} ({summary.overall_risk_score:.1f}/100)"
            )
        else:
            lines.append(
                f"Risk Level: {summary.overall_risk_level.value.upper()} ({summary.overall_risk_score:.1f}/100)"
            )

        lines.append(f"Operation: {summary.operation_description}")
        lines.append(f"Business Impact: {summary.business_impact}")
        lines.append(f"Approval Required: {summary.approval_level}")
        lines.append("")

        lines.append("KEY METRICS:")
        lines.append(
            f"• Downtime Risk: {summary.potential_downtime_minutes:.0f} minutes"
        )
        lines.append(f"• Systems Affected: {summary.affected_systems_count}")
        lines.append(f"• Revenue Risk: {summary.revenue_risk_estimate}")
        lines.append("")

        lines.append("MITIGATION:")
        lines.append(f"• Strategies Available: {summary.mitigation_strategies_count}")
        lines.append(f"• Risk Reduction: {summary.risk_reduction_potential:.1f}%")
        lines.append(f"• Timeline: {summary.implementation_timeline}")
        lines.append("")

        lines.append(f"RECOMMENDATION: {summary.go_no_go_recommendation}")
        lines.append("")

        lines.append(f"Generated: {report.generation_timestamp}")

        return "\n".join(lines)

    # Helper methods

    def _create_console_progress_bar(
        self, current: float, maximum: float, width: int
    ) -> str:
        """Create ASCII progress bar."""
        if maximum == 0:
            percentage = 0
        else:
            percentage = min(current / maximum, 1.0)

        filled_width = int(width * percentage)
        empty_width = width - filled_width

        bar = (
            self.console_theme.progress_filled * filled_width
            + self.console_theme.progress_empty * empty_width
        )

        return bar

    def _risk_assessment_to_dict(
        self, assessment: ComprehensiveRiskAssessment
    ) -> Dict[str, Any]:
        """Convert risk assessment to dictionary for JSON serialization."""
        return {
            "operation_id": assessment.operation_id,
            "overall_score": assessment.overall_score,
            "risk_level": assessment.risk_level.value,
            "category_scores": {
                category.value: {
                    "score": score.score,
                    "level": score.level.value,
                    "description": score.description,
                    "risk_factors": score.risk_factors,
                    "confidence": score.confidence,
                }
                for category, score in assessment.category_scores.items()
            },
            "total_risk_factors": len(assessment.risk_factors),
            "assessment_timestamp": assessment.assessment_timestamp,
            "computation_time": assessment.total_computation_time,
        }

    def _mitigation_plan_to_dict(self, mitigation_plan: Any) -> Dict[str, Any]:
        """Convert mitigation plan to dictionary for JSON serialization."""
        result = {
            "operation_id": getattr(mitigation_plan, "operation_id", "unknown"),
            "total_strategies": len(
                getattr(mitigation_plan, "mitigation_strategies", [])
            ),
            "total_estimated_effort": getattr(
                mitigation_plan, "total_estimated_effort", 0.0
            ),
            "generation_time": getattr(mitigation_plan, "total_generation_time", 0.0),
        }

        if hasattr(mitigation_plan, "mitigation_strategies"):
            result["strategies"] = []
            for strategy in mitigation_plan.mitigation_strategies:
                strategy_dict = {
                    "id": getattr(strategy, "id", "unknown"),
                    "name": getattr(strategy, "name", "Unknown Strategy"),
                    "priority": getattr(
                        strategy, "priority", type("", (), {"value": "unknown"})
                    ).value,
                    "category": getattr(
                        strategy, "category", type("", (), {"value": "unknown"})
                    ).value,
                    "risk_reduction_potential": getattr(
                        strategy, "risk_reduction_potential", 0.0
                    ),
                    "estimated_effort_hours": getattr(
                        strategy, "estimated_effort_hours", 0.0
                    ),
                }
                result["strategies"].append(strategy_dict)

        return result

    def _initialize_html_templates(self):
        """Initialize HTML templates for report formatting."""
        self.html_templates = {
            "header": """
            <!DOCTYPE html>
            <html lang="en">
            <head>
                <meta charset="UTF-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <title>Migration Risk Assessment Report</title>
                <style>
                    body {{ font-family: Arial, sans-serif; margin: 20px; background-color: #f5f5f5; }}
                    .container {{ max-width: 1200px; margin: 0 auto; background-color: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
                    .header {{ text-align: center; border-bottom: 2px solid #333; padding-bottom: 10px; margin-bottom: 20px; }}
                    .risk-critical {{ color: #e74c3c; font-weight: bold; }}
                    .risk-high {{ color: #f39c12; font-weight: bold; }}
                    .risk-medium {{ color: #f1c40f; font-weight: bold; }}
                    .risk-low {{ color: #27ae60; font-weight: bold; }}
                    .section {{ margin: 20px 0; padding: 15px; border-left: 4px solid #3498db; background-color: #f8f9fa; }}
                    .metric-box {{ display: inline-block; margin: 10px; padding: 15px; background-color: #ecf0f1; border-radius: 5px; min-width: 150px; text-align: center; }}
                    .progress-bar {{ width: 100%; height: 20px; background-color: #ecf0f1; border-radius: 10px; overflow: hidden; margin: 5px 0; }}
                    .progress-fill {{ height: 100%; background-color: #3498db; transition: width 0.3s ease; }}
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="header">
                        <h1>🎯 Migration Risk Assessment Report</h1>
                        <p>Report ID: {report_id} | Generated: {timestamp}</p>
                    </div>
            """,
            "footer": """
                    <div class="footer" style="text-align: center; margin-top: 40px; padding-top: 20px; border-top: 1px solid #bdc3c7; color: #7f8c8d;">
                        <p>🤖 Generated with DataFlow Risk Assessment Engine</p>
                        <p>Report generated in {{generation_time:.3f}} seconds</p>
                    </div>
                </div>
            </body>
            </html>
            """,
        }

    def _get_html_header(
        self, report: ComprehensiveImpactReport, style: FormatStyle
    ) -> str:
        """Get HTML header for report."""
        return self.html_templates["header"].format(
            report_id=report.report_id, timestamp=report.generation_timestamp
        )

    def _format_html_executive_summary(
        self, summary: ExecutiveRiskSummary, style: FormatStyle
    ) -> str:
        """Format executive summary as HTML."""
        risk_class = f"risk-{summary.overall_risk_level.value}"

        html = f"""
        <div class="section">
            <h2>💼 Executive Summary</h2>

            <div class="metric-box">
                <h3>Risk Level</h3>
                <div class="{risk_class}">{summary.overall_risk_level.value.upper()}</div>
                <div>{summary.overall_risk_score:.1f}/100</div>
            </div>

            <div class="metric-box">
                <h3>Downtime Risk</h3>
                <div>{summary.potential_downtime_minutes:.0f} min</div>
            </div>

            <div class="metric-box">
                <h3>Systems Affected</h3>
                <div>{summary.affected_systems_count}</div>
            </div>

            <div class="metric-box">
                <h3>Revenue Risk</h3>
                <div>{summary.revenue_risk_estimate}</div>
            </div>

            <h3>Business Impact</h3>
            <p>{summary.business_impact}</p>

            <h3>Recommendation</h3>
            <p><strong>{summary.go_no_go_recommendation}</strong></p>

            <h3>Approval Required</h3>
            <p>{summary.approval_level} level approval required</p>
        </div>
        """

        return html

    def _format_html_risk_breakdown(
        self, assessment: ComprehensiveRiskAssessment, style: FormatStyle
    ) -> str:
        """Format risk breakdown as HTML with progress bars."""
        html_parts = []

        html_parts.append('<div class="section">')
        html_parts.append("<h2>📈 Risk Breakdown</h2>")

        for category, risk_score in assessment.category_scores.items():
            category_name = category.value.replace("_", " ").title()
            risk_class = f"risk-{risk_score.level.value}"
            progress_percent = risk_score.score

            html_parts.append(
                f"""
            <h3>{category_name}</h3>
            <div class="progress-bar">
                <div class="progress-fill" style="width: {progress_percent}%"></div>
            </div>
            <p class="{risk_class}">{risk_score.level.value.upper()} ({risk_score.score:.1f}/100)</p>
            <p>{risk_score.description}</p>
            """
            )

        html_parts.append("</div>")

        return "\n".join(html_parts)

    def _format_html_mitigation_overview(
        self, mitigation_plan: Any, style: FormatStyle
    ) -> str:
        """Format mitigation overview as HTML."""
        html = f"""
        <div class="section">
            <h2>🛡️ Mitigation Strategies</h2>
            <div class="metric-box">
                <h3>Total Strategies</h3>
                <div>{len(getattr(mitigation_plan, 'mitigation_strategies', []))}</div>
            </div>
            <div class="metric-box">
                <h3>Total Effort</h3>
                <div>{getattr(mitigation_plan, 'total_estimated_effort', 0):.1f} hours</div>
            </div>
        </div>
        """

        return html

    def _format_html_technical_details(
        self, technical_report: TechnicalImpactReport, style: FormatStyle
    ) -> str:
        """Format technical details as HTML."""
        html_parts = []

        html_parts.append('<div class="section">')
        html_parts.append("<h2>🔧 Technical Implementation</h2>")

        html_parts.append("<h3>Pre-Migration Steps</h3>")
        html_parts.append("<ol>")
        for step in technical_report.pre_migration_steps:
            html_parts.append(f"<li>{escape(step)}</li>")
        html_parts.append("</ol>")

        html_parts.append("<h3>Migration Procedure</h3>")
        html_parts.append("<ol>")
        for step in technical_report.migration_procedure:
            html_parts.append(f"<li>{escape(step)}</li>")
        html_parts.append("</ol>")

        html_parts.append("</div>")

        return "\n".join(html_parts)

    def _get_html_footer(self, report: ComprehensiveImpactReport) -> str:
        """Get HTML footer for report."""
        return self.html_templates["footer"].format(
            generation_time=report.generation_time_seconds
        )

    def format_comprehensive_report(self, report: ComprehensiveImpactReport) -> str:
        """
        Format a comprehensive impact report (alias for format_report).

        Args:
            report: The comprehensive impact report to format

        Returns:
            Formatted report string
        """
        return self.format_report(report, format_type=ReportFormat.CONSOLE)

    def format_stakeholder_report(
        self, stakeholder_report: StakeholderReport, role: StakeholderRole
    ) -> str:
        """
        Format a stakeholder-specific report.

        Args:
            stakeholder_report: The stakeholder report to format
            role: The stakeholder role

        Returns:
            Formatted stakeholder report string
        """
        # Create a simple formatted report for the stakeholder
        output = []

        # Add header
        output.append(f"\n{'=' * 60}")
        output.append(f"Stakeholder Report for: {role.value.upper()}")
        output.append(f"{'=' * 60}\n")

        # Add message if available
        if hasattr(stakeholder_report, "message") and stakeholder_report.message:
            output.append(f"Message:\n{stakeholder_report.message}\n")

        # Add required actions if available
        if (
            hasattr(stakeholder_report, "required_actions")
            and stakeholder_report.required_actions
        ):
            output.append("Required Actions:")
            for action in stakeholder_report.required_actions:
                output.append(f"  • {action}")
            output.append("")

        # Add timeline if available
        if hasattr(stakeholder_report, "timeline") and stakeholder_report.timeline:
            output.append(f"Timeline: {stakeholder_report.timeline}\n")

        # Add impact if available
        if (
            hasattr(stakeholder_report, "impact_summary")
            and stakeholder_report.impact_summary
        ):
            output.append(f"Impact Summary:\n{stakeholder_report.impact_summary}\n")

        # Add footer
        output.append(f"{'=' * 60}\n")

        return "\n".join(output)
