#!/usr/bin/env python3
"""
Impact Analysis Reporter for Risk Assessment Engine - TODO-140 Phase 3

Provides comprehensive impact analysis reporting for migration risk assessments,
with executive summaries, technical implementation guides, compliance documentation,
and stakeholder communications. Integrates with Phase 1 RiskAssessmentEngine and
Phase 2 MitigationStrategyEngine.

PHASE 3 IMPLEMENTATION: Impact Analysis Reporter (4h effort)
- Executive dashboard with high-level risk visualization
- Technical implementation reports with detailed guidance
- Compliance audit reports for regulatory requirements
- Stakeholder communications tailored for different roles
- Multi-format output (Console, JSON, HTML, PDF)

REPORT TYPES:
- Executive Risk Summary - Business impact and decision support
- Technical Impact Report - Implementation guidance for dev teams
- Compliance Audit Report - Regulatory documentation
- Stakeholder Communications - Role-specific messaging

INTEGRATION POINTS:
- Uses Phase 1 RiskAssessmentEngine results for risk data
- Uses Phase 2 MitigationStrategyEngine results for strategy reporting
- Extends TODO-137 ImpactReporter patterns for consistency
- Supports multi-channel output formats
"""

import json
import logging
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from html import escape
from typing import Any, Dict, List, Optional, Set, Tuple, Union

from .dependency_analyzer import DependencyReport, DependencyType, ImpactLevel
from .mitigation_strategy_engine import (
    MitigationCategory,
    MitigationComplexity,
    MitigationPriority,
    MitigationStrategy,
    PrioritizedMitigationPlan,
)
from .risk_assessment_engine import (
    BusinessImpactAssessment,
    ComprehensiveRiskAssessment,
    RiskCategory,
    RiskFactor,
    RiskLevel,
    RiskScore,
)

logger = logging.getLogger(__name__)


class StakeholderRole(Enum):
    """Different stakeholder roles requiring tailored communications."""

    EXECUTIVE = "executive"  # C-level, VPs
    MANAGER = "manager"  # Engineering managers, product managers
    TECHNICAL_LEAD = "technical_lead"  # Tech leads, senior engineers
    DEVELOPER = "developer"  # Implementation engineers
    DBA = "dba"  # Database administrators
    DEVOPS = "devops"  # DevOps/SRE teams
    COMPLIANCE = "compliance"  # Compliance/audit teams
    QA = "qa"  # Quality assurance teams


class ReportFormat(Enum):
    """Output formats for impact reports."""

    CONSOLE = "console"  # Rich terminal output
    JSON = "json"  # Structured API data
    HTML = "html"  # Web dashboard format
    PDF = "pdf"  # Executive/compliance docs
    SUMMARY = "summary"  # Brief overview format


class ReportSection(Enum):
    """Sections of impact analysis reports."""

    EXECUTIVE_SUMMARY = "executive_summary"
    RISK_BREAKDOWN = "risk_breakdown"
    MITIGATION_OVERVIEW = "mitigation_overview"
    TECHNICAL_DETAILS = "technical_details"
    COMPLIANCE_AUDIT = "compliance_audit"
    IMPLEMENTATION_GUIDE = "implementation_guide"
    STAKEHOLDER_ACTIONS = "stakeholder_actions"
    APPENDICES = "appendices"


@dataclass
class ExecutiveRiskSummary:
    """Executive-level risk summary for business decision making."""

    operation_description: str
    overall_risk_level: RiskLevel
    overall_risk_score: float
    business_impact: str
    recommended_action: str

    # Business metrics
    potential_downtime_minutes: float
    affected_systems_count: int
    revenue_risk_estimate: str
    user_impact_estimate: str

    # Mitigation summary
    mitigation_strategies_count: int
    risk_reduction_potential: float  # Original risk -> mitigated risk
    implementation_timeline: str
    resource_requirements: str

    # Decision support
    approval_required: bool
    approval_level: str  # "Technical", "Management", "Executive"
    go_no_go_recommendation: str


@dataclass
class TechnicalImpactReport:
    """Technical implementation report for development teams."""

    operation_details: Dict[str, Any]
    risk_category_breakdown: Dict[RiskCategory, Dict[str, Any]]
    dependency_analysis: Dict[str, Any]

    # Implementation guidance
    pre_migration_steps: List[str]
    migration_procedure: List[str]
    post_migration_validation: List[str]
    rollback_procedures: List[str]

    # Technical considerations
    performance_impact_analysis: Dict[str, Any]
    infrastructure_requirements: List[str]
    monitoring_recommendations: List[str]
    testing_strategy: List[str]


@dataclass
class ComplianceAuditReport:
    """Compliance and audit documentation report."""

    regulatory_frameworks: List[str]  # HIPAA, SOX, GDPR, etc.
    compliance_risk_assessment: Dict[str, Any]
    data_protection_impact: Dict[str, Any]

    # Audit requirements
    change_management_documentation: Dict[str, Any]
    risk_acceptance_criteria: List[str]
    audit_trail_requirements: List[str]
    approval_workflows: List[str]

    # Documentation
    risk_register_entry: Dict[str, Any]
    control_effectiveness_assessment: Dict[str, Any]
    residual_risk_statement: str


@dataclass
class StakeholderReport:
    """Role-specific stakeholder communication."""

    role: StakeholderRole
    key_messages: List[str]
    action_items: List[str]
    decision_points: List[str]
    timeline_awareness: str
    escalation_criteria: List[str]

    # Role-specific details
    technical_depth: str  # "high", "medium", "low"
    focus_areas: List[str]  # What they care about most
    communication_format: str  # "detailed", "summary", "bullet_points"


@dataclass
class ComprehensiveImpactReport:
    """Complete impact analysis report with all components."""

    # Report metadata (required fields first)
    report_id: str
    operation_id: str
    generation_timestamp: str
    executive_summary: ExecutiveRiskSummary
    technical_report: TechnicalImpactReport
    compliance_report: ComplianceAuditReport
    stakeholder_communications: Dict[StakeholderRole, StakeholderReport]
    risk_assessment: ComprehensiveRiskAssessment

    # Optional fields with defaults
    report_version: str = "1.0"
    mitigation_plan: Optional[Any] = None  # PrioritizedMitigationPlan when available
    dependency_report: Optional[DependencyReport] = None
    generation_time_seconds: float = 0.0
    report_size_estimate: str = "Unknown"


class ImpactAnalysisReporter:
    """
    Core Impact Analysis Reporter for migration risk assessments.

    Generates comprehensive impact reports with executive summaries,
    technical implementation guides, compliance documentation, and
    stakeholder communications across multiple output formats.
    """

    def __init__(
        self,
        risk_weight_factors: Optional[Dict[str, float]] = None,
        stakeholder_preferences: Optional[Dict[StakeholderRole, Dict[str, Any]]] = None,
    ):
        """
        Initialize the impact analysis reporter.

        Args:
            risk_weight_factors: Custom weighting for different risk factors in reports
            stakeholder_preferences: Customization for different stakeholder communications
        """
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

        # Report weighting factors
        self.risk_weight_factors = risk_weight_factors or {
            "business_impact": 0.40,  # Business consequences weight
            "technical_complexity": 0.35,  # Technical difficulty weight
            "compliance_risk": 0.15,  # Regulatory/audit weight
            "operational_impact": 0.10,  # Day-to-day operations weight
        }

        # Stakeholder communication preferences
        self.stakeholder_preferences = (
            stakeholder_preferences or self._default_stakeholder_preferences()
        )

        # Report templates and formatting
        self.report_templates = self._initialize_report_templates()

    def generate_comprehensive_impact_report(
        self,
        risk_assessment: ComprehensiveRiskAssessment,
        mitigation_plan: Optional[Any] = None,
        dependency_report: Optional[DependencyReport] = None,
        business_context: Optional[Dict[str, Any]] = None,
    ) -> ComprehensiveImpactReport:
        """
        Generate comprehensive impact report with all components.

        Args:
            risk_assessment: Results from Phase 1 RiskAssessmentEngine
            mitigation_plan: Results from Phase 2 MitigationStrategyEngine
            dependency_report: Dependency analysis results
            business_context: Additional business context for impact assessment

        Returns:
            ComprehensiveImpactReport with executive, technical, compliance, and stakeholder components
        """
        start_time = time.time()
        report_id = f"impact_report_{int(start_time)}"

        self.logger.info(f"Generating comprehensive impact report {report_id}")

        try:
            # Generate executive risk summary
            executive_summary = self.generate_executive_risk_summary(
                risk_assessment, mitigation_plan, business_context
            )

            # Generate technical implementation report
            technical_report = self.create_technical_impact_report(
                risk_assessment, mitigation_plan, dependency_report
            )

            # Generate compliance audit report
            compliance_report = self.build_compliance_audit_report(
                risk_assessment, business_context
            )

            # Generate stakeholder communications
            stakeholder_communications = self.format_stakeholder_communications(
                risk_assessment, mitigation_plan, executive_summary
            )

            generation_time = time.time() - start_time

            comprehensive_report = ComprehensiveImpactReport(
                report_id=report_id,
                operation_id=risk_assessment.operation_id,
                generation_timestamp=datetime.now().isoformat(),
                executive_summary=executive_summary,
                technical_report=technical_report,
                compliance_report=compliance_report,
                stakeholder_communications=stakeholder_communications,
                risk_assessment=risk_assessment,
                mitigation_plan=mitigation_plan,
                dependency_report=dependency_report,
                generation_time_seconds=generation_time,
            )

            self.logger.info(
                f"Impact report generated successfully in {generation_time:.3f}s"
            )

            return comprehensive_report

        except Exception as e:
            self.logger.error(f"Failed to generate comprehensive impact report: {e}")
            raise

    def generate_executive_risk_summary(
        self,
        risk_assessment: ComprehensiveRiskAssessment,
        mitigation_plan: Optional[Any] = None,
        business_context: Optional[Dict[str, Any]] = None,
    ) -> ExecutiveRiskSummary:
        """
        Generate executive-level risk summary for business decision making.

        Args:
            risk_assessment: Risk assessment results
            mitigation_plan: Mitigation strategies (if available)
            business_context: Business impact context

        Returns:
            ExecutiveRiskSummary with high-level business impact analysis
        """
        self.logger.debug("Generating executive risk summary")

        # Extract business context or use defaults
        context = business_context or {}

        # Determine approval requirements based on risk level
        approval_required = risk_assessment.risk_level in [
            RiskLevel.HIGH,
            RiskLevel.CRITICAL,
        ]

        if risk_assessment.risk_level == RiskLevel.CRITICAL:
            approval_level = "Executive"
            go_no_go = "DO NOT PROCEED - Critical risks require executive review"
        elif risk_assessment.risk_level == RiskLevel.HIGH:
            approval_level = "Management"
            go_no_go = "MANAGEMENT APPROVAL REQUIRED - High risk operation"
        elif risk_assessment.risk_level == RiskLevel.MEDIUM:
            approval_level = "Technical"
            go_no_go = "PROCEED WITH CAUTION - Technical review completed"
        else:
            approval_level = "None"
            go_no_go = "APPROVED - Low risk operation"

        # Calculate mitigation effectiveness if available
        mitigation_count = 0
        risk_reduction = 0.0
        implementation_timeline = "Not assessed"
        resource_requirements = "Standard migration resources"

        if mitigation_plan:
            if hasattr(mitigation_plan, "strategies"):
                mitigation_count = len(mitigation_plan.strategies)
            if hasattr(mitigation_plan, "risk_reduction_potential"):
                risk_reduction = mitigation_plan.risk_reduction_potential
            if hasattr(mitigation_plan, "estimated_timeline"):
                implementation_timeline = mitigation_plan.estimated_timeline
            if hasattr(mitigation_plan, "resource_estimate"):
                resource_requirements = mitigation_plan.resource_estimate

        # Business impact estimates
        potential_downtime = context.get(
            "estimated_downtime_minutes", self._estimate_downtime(risk_assessment)
        )
        affected_systems = context.get(
            "affected_systems_count", self._estimate_affected_systems(risk_assessment)
        )
        revenue_risk = context.get(
            "revenue_risk_estimate", self._estimate_revenue_risk(risk_assessment)
        )
        user_impact = context.get(
            "user_impact_estimate", self._estimate_user_impact(risk_assessment)
        )

        operation_desc = self._generate_operation_description(risk_assessment)
        business_impact_desc = self._generate_business_impact_description(
            risk_assessment, context
        )
        recommended_action = self._generate_recommended_action(
            risk_assessment, mitigation_plan
        )

        return ExecutiveRiskSummary(
            operation_description=operation_desc,
            overall_risk_level=risk_assessment.risk_level,
            overall_risk_score=risk_assessment.overall_score,
            business_impact=business_impact_desc,
            recommended_action=recommended_action,
            potential_downtime_minutes=potential_downtime,
            affected_systems_count=affected_systems,
            revenue_risk_estimate=revenue_risk,
            user_impact_estimate=user_impact,
            mitigation_strategies_count=mitigation_count,
            risk_reduction_potential=risk_reduction,
            implementation_timeline=implementation_timeline,
            resource_requirements=resource_requirements,
            approval_required=approval_required,
            approval_level=approval_level,
            go_no_go_recommendation=go_no_go,
        )

    def create_technical_impact_report(
        self,
        risk_assessment: ComprehensiveRiskAssessment,
        mitigation_plan: Optional[Any] = None,
        dependency_report: Optional[DependencyReport] = None,
    ) -> TechnicalImpactReport:
        """
        Create technical implementation report for development teams.

        Args:
            risk_assessment: Risk assessment results
            mitigation_plan: Mitigation strategies
            dependency_report: Dependency analysis

        Returns:
            TechnicalImpactReport with detailed technical guidance
        """
        self.logger.debug("Creating technical impact report")

        # Extract operation details
        operation_details = {
            "operation_id": risk_assessment.operation_id,
            "overall_risk_score": risk_assessment.overall_score,
            "risk_level": risk_assessment.risk_level.value,
            "assessment_timestamp": risk_assessment.assessment_timestamp,
            "computation_time": risk_assessment.total_computation_time,
        }

        # Risk category breakdown with technical details
        risk_breakdown = {}
        for category, risk_score in risk_assessment.category_scores.items():
            risk_breakdown[category] = {
                "score": risk_score.score,
                "level": risk_score.level.value,
                "description": risk_score.description,
                "risk_factors": risk_score.risk_factors,
                "confidence": risk_score.confidence,
                "technical_implications": self._get_technical_implications(
                    category, risk_score
                ),
            }

        # Dependency analysis summary
        dependency_analysis = {}
        if dependency_report:
            dependency_analysis = {
                "total_dependencies": len(dependency_report.all_dependencies),
                "dependency_types": list(dependency_report.dependencies.keys()),
                "high_impact_dependencies": [
                    dep
                    for deps in dependency_report.dependencies.values()
                    for dep in deps
                    if getattr(dep, "impact_level", None) == ImpactLevel.HIGH
                ],
                "critical_dependencies": [
                    dep
                    for deps in dependency_report.dependencies.values()
                    for dep in deps
                    if getattr(dep, "impact_level", None) == ImpactLevel.CRITICAL
                ],
            }

        # Generate implementation steps
        pre_migration_steps = self._generate_pre_migration_steps(
            risk_assessment, mitigation_plan
        )
        migration_procedure = self._generate_migration_procedure(risk_assessment)
        post_migration_validation = self._generate_post_migration_validation(
            risk_assessment
        )
        rollback_procedures = self._generate_rollback_procedures(risk_assessment)

        # Technical analysis
        performance_impact = self._analyze_performance_impact(
            risk_assessment, dependency_report
        )
        infrastructure_requirements = self._determine_infrastructure_requirements(
            risk_assessment
        )
        monitoring_recommendations = self._generate_monitoring_recommendations(
            risk_assessment
        )
        testing_strategy = self._generate_testing_strategy(risk_assessment)

        return TechnicalImpactReport(
            operation_details=operation_details,
            risk_category_breakdown=risk_breakdown,
            dependency_analysis=dependency_analysis,
            pre_migration_steps=pre_migration_steps,
            migration_procedure=migration_procedure,
            post_migration_validation=post_migration_validation,
            rollback_procedures=rollback_procedures,
            performance_impact_analysis=performance_impact,
            infrastructure_requirements=infrastructure_requirements,
            monitoring_recommendations=monitoring_recommendations,
            testing_strategy=testing_strategy,
        )

    def build_compliance_audit_report(
        self,
        risk_assessment: ComprehensiveRiskAssessment,
        business_context: Optional[Dict[str, Any]] = None,
    ) -> ComplianceAuditReport:
        """
        Build compliance audit report for regulatory requirements.

        Args:
            risk_assessment: Risk assessment results
            business_context: Business and regulatory context

        Returns:
            ComplianceAuditReport with regulatory documentation
        """
        self.logger.debug("Building compliance audit report")

        context = business_context or {}

        # Determine applicable regulatory frameworks
        regulatory_frameworks = context.get(
            "regulatory_frameworks",
            self._determine_applicable_regulations(risk_assessment),
        )

        # Compliance risk assessment
        compliance_risk = {
            "overall_compliance_risk": self._assess_compliance_risk(risk_assessment),
            "regulatory_violations_potential": self._assess_regulatory_violations(
                risk_assessment
            ),
            "data_governance_impact": self._assess_data_governance_impact(
                risk_assessment
            ),
            "audit_trail_requirements": self._determine_audit_trail_requirements(
                risk_assessment
            ),
        }

        # Data protection impact assessment
        data_protection_impact = {
            "data_types_affected": context.get(
                "data_types_affected", ["Operational Data"]
            ),
            "personal_data_impact": self._assess_personal_data_impact(risk_assessment),
            "data_retention_implications": self._assess_data_retention_impact(
                risk_assessment
            ),
            "cross_border_transfer_impact": context.get(
                "cross_border_impact", "Not Applicable"
            ),
        }

        # Change management documentation
        change_management = {
            "change_classification": self._classify_change(risk_assessment),
            "approval_workflow": self._determine_approval_workflow(risk_assessment),
            "documentation_requirements": self._determine_documentation_requirements(
                risk_assessment
            ),
            "stakeholder_notification": self._determine_stakeholder_notifications(
                risk_assessment
            ),
        }

        # Risk acceptance criteria
        risk_acceptance_criteria = self._generate_risk_acceptance_criteria(
            risk_assessment
        )
        audit_trail_requirements = self._generate_audit_trail_requirements(
            risk_assessment
        )
        approval_workflows = self._generate_approval_workflows(risk_assessment)

        # Risk register entry
        risk_register_entry = {
            "risk_id": risk_assessment.operation_id,
            "risk_category": "Operational Risk - Database Migration",
            "inherent_risk_score": risk_assessment.overall_score,
            "inherent_risk_level": risk_assessment.risk_level.value,
            "mitigation_status": (
                "In Progress" if any(risk_assessment.recommendations) else "Not Started"
            ),
            "risk_owner": context.get("risk_owner", "Database Team"),
            "review_date": context.get("next_review_date", "TBD"),
        }

        # Control effectiveness assessment
        control_effectiveness = {
            "existing_controls": self._assess_existing_controls(risk_assessment),
            "control_gaps": self._identify_control_gaps(risk_assessment),
            "recommended_controls": self._recommend_additional_controls(
                risk_assessment
            ),
            "testing_requirements": self._determine_control_testing_requirements(
                risk_assessment
            ),
        }

        # Residual risk statement
        residual_risk = self._generate_residual_risk_statement(risk_assessment)

        return ComplianceAuditReport(
            regulatory_frameworks=regulatory_frameworks,
            compliance_risk_assessment=compliance_risk,
            data_protection_impact=data_protection_impact,
            change_management_documentation=change_management,
            risk_acceptance_criteria=risk_acceptance_criteria,
            audit_trail_requirements=audit_trail_requirements,
            approval_workflows=approval_workflows,
            risk_register_entry=risk_register_entry,
            control_effectiveness_assessment=control_effectiveness,
            residual_risk_statement=residual_risk,
        )

    def format_stakeholder_communications(
        self,
        risk_assessment: ComprehensiveRiskAssessment,
        mitigation_plan: Optional[Any] = None,
        executive_summary: Optional[ExecutiveRiskSummary] = None,
    ) -> Dict[StakeholderRole, StakeholderReport]:
        """
        Format stakeholder communications for different organizational roles.

        Args:
            risk_assessment: Risk assessment results
            mitigation_plan: Mitigation strategies
            executive_summary: Executive summary (if available)

        Returns:
            Dict mapping StakeholderRole to tailored StakeholderReport
        """
        self.logger.debug("Formatting stakeholder communications")

        stakeholder_reports = {}

        # Generate report for each stakeholder role
        for role in StakeholderRole:
            preferences = self.stakeholder_preferences.get(role, {})

            key_messages = self._generate_key_messages_for_role(
                role, risk_assessment, executive_summary
            )
            action_items = self._generate_action_items_for_role(
                role, risk_assessment, mitigation_plan
            )
            decision_points = self._generate_decision_points_for_role(
                role, risk_assessment
            )
            timeline_awareness = self._generate_timeline_awareness_for_role(
                role, risk_assessment
            )
            escalation_criteria = self._generate_escalation_criteria_for_role(
                role, risk_assessment
            )

            stakeholder_report = StakeholderReport(
                role=role,
                key_messages=key_messages,
                action_items=action_items,
                decision_points=decision_points,
                timeline_awareness=timeline_awareness,
                escalation_criteria=escalation_criteria,
                technical_depth=preferences.get("technical_depth", "medium"),
                focus_areas=preferences.get("focus_areas", ["Risk Level", "Timeline"]),
                communication_format=preferences.get("communication_format", "summary"),
            )

            stakeholder_reports[role] = stakeholder_report

        return stakeholder_reports

    # Helper methods for generating report components

    def _default_stakeholder_preferences(self) -> Dict[StakeholderRole, Dict[str, Any]]:
        """Define default stakeholder communication preferences."""
        return {
            StakeholderRole.EXECUTIVE: {
                "technical_depth": "low",
                "focus_areas": [
                    "Business Impact",
                    "Risk Level",
                    "Approval Required",
                    "Timeline",
                ],
                "communication_format": "summary",
            },
            StakeholderRole.MANAGER: {
                "technical_depth": "medium",
                "focus_areas": [
                    "Risk Level",
                    "Resource Requirements",
                    "Timeline",
                    "Team Impact",
                ],
                "communication_format": "detailed",
            },
            StakeholderRole.TECHNICAL_LEAD: {
                "technical_depth": "high",
                "focus_areas": [
                    "Technical Risks",
                    "Implementation Strategy",
                    "Architecture Impact",
                ],
                "communication_format": "detailed",
            },
            StakeholderRole.DEVELOPER: {
                "technical_depth": "high",
                "focus_areas": [
                    "Implementation Steps",
                    "Code Changes",
                    "Testing Requirements",
                ],
                "communication_format": "bullet_points",
            },
            StakeholderRole.DBA: {
                "technical_depth": "high",
                "focus_areas": [
                    "Database Impact",
                    "Performance",
                    "Backup/Recovery",
                    "Dependencies",
                ],
                "communication_format": "detailed",
            },
            StakeholderRole.DEVOPS: {
                "technical_depth": "high",
                "focus_areas": [
                    "Infrastructure Impact",
                    "Deployment",
                    "Monitoring",
                    "Rollback",
                ],
                "communication_format": "bullet_points",
            },
            StakeholderRole.COMPLIANCE: {
                "technical_depth": "low",
                "focus_areas": [
                    "Regulatory Impact",
                    "Documentation",
                    "Audit Trail",
                    "Approval Workflow",
                ],
                "communication_format": "detailed",
            },
            StakeholderRole.QA: {
                "technical_depth": "medium",
                "focus_areas": [
                    "Testing Strategy",
                    "Quality Risks",
                    "Validation Requirements",
                ],
                "communication_format": "bullet_points",
            },
        }

    def _initialize_report_templates(self) -> Dict[str, Any]:
        """Initialize report templates for different formats."""
        return {
            "console": {"width": 80, "use_colors": True, "emoji_indicators": True},
            "html": {
                "bootstrap_version": "5.0",
                "chart_library": "chart.js",
                "responsive": True,
            },
            "pdf": {"page_size": "A4", "margins": "1in", "font_family": "Arial"},
        }

    # Business impact estimation methods

    def _estimate_downtime(self, risk_assessment: ComprehensiveRiskAssessment) -> float:
        """Estimate potential downtime based on risk factors."""
        if risk_assessment.risk_level == RiskLevel.CRITICAL:
            return 240.0  # 4 hours
        elif risk_assessment.risk_level == RiskLevel.HIGH:
            return 120.0  # 2 hours
        elif risk_assessment.risk_level == RiskLevel.MEDIUM:
            return 30.0  # 30 minutes
        else:
            return 5.0  # 5 minutes

    def _estimate_affected_systems(
        self, risk_assessment: ComprehensiveRiskAssessment
    ) -> int:
        """Estimate number of affected systems."""
        # Base estimate on dependency counts and risk factors
        total_factors = len(risk_assessment.risk_factors)
        if risk_assessment.risk_level == RiskLevel.CRITICAL:
            return max(3, total_factors)
        elif risk_assessment.risk_level == RiskLevel.HIGH:
            return max(2, total_factors // 2)
        else:
            return 1

    def _estimate_revenue_risk(
        self, risk_assessment: ComprehensiveRiskAssessment
    ) -> str:
        """Estimate potential revenue risk."""
        if risk_assessment.risk_level == RiskLevel.CRITICAL:
            return "$100K-500K potential impact"
        elif risk_assessment.risk_level == RiskLevel.HIGH:
            return "$50K-100K potential impact"
        elif risk_assessment.risk_level == RiskLevel.MEDIUM:
            return "$10K-50K potential impact"
        else:
            return "Minimal revenue impact"

    def _estimate_user_impact(
        self, risk_assessment: ComprehensiveRiskAssessment
    ) -> str:
        """Estimate user impact."""
        if risk_assessment.risk_level == RiskLevel.CRITICAL:
            return "Significant user disruption expected"
        elif risk_assessment.risk_level == RiskLevel.HIGH:
            return "Moderate user impact possible"
        elif risk_assessment.risk_level == RiskLevel.MEDIUM:
            return "Minor user impact expected"
        else:
            return "No significant user impact"

    # Report content generation methods

    def _generate_operation_description(
        self, risk_assessment: ComprehensiveRiskAssessment
    ) -> str:
        """Generate human-readable operation description."""
        return f"Database migration operation {risk_assessment.operation_id} with risk score {risk_assessment.overall_score:.1f}"

    def _generate_business_impact_description(
        self, risk_assessment: ComprehensiveRiskAssessment, context: Dict[str, Any]
    ) -> str:
        """Generate business impact description."""
        risk_level = risk_assessment.risk_level

        if risk_level == RiskLevel.CRITICAL:
            return "High business impact with potential for significant system disruption and data loss"
        elif risk_level == RiskLevel.HIGH:
            return "Moderate business impact with potential system availability issues"
        elif risk_level == RiskLevel.MEDIUM:
            return "Limited business impact with some operational considerations"
        else:
            return "Minimal business impact with standard operational procedures"

    def _generate_recommended_action(
        self,
        risk_assessment: ComprehensiveRiskAssessment,
        mitigation_plan: Optional[Any],
    ) -> str:
        """Generate recommended action based on risk level."""
        risk_level = risk_assessment.risk_level

        if risk_level == RiskLevel.CRITICAL:
            return "Halt migration - Critical risks require comprehensive mitigation before proceeding"
        elif risk_level == RiskLevel.HIGH:
            return "Management review required - Implement risk mitigation strategies before execution"
        elif risk_level == RiskLevel.MEDIUM:
            return "Technical review recommended - Proceed with enhanced monitoring and mitigation"
        else:
            return "Proceed with standard precautions and monitoring"

    def _get_technical_implications(
        self, category: RiskCategory, risk_score: RiskScore
    ) -> List[str]:
        """Get technical implications for a specific risk category."""
        implications = []

        if category == RiskCategory.DATA_LOSS:
            if risk_score.level in [RiskLevel.HIGH, RiskLevel.CRITICAL]:
                implications.extend(
                    [
                        "Backup and restore procedures must be validated",
                        "Data integrity verification required post-migration",
                        "Consider staged migration approach",
                    ]
                )
        elif category == RiskCategory.SYSTEM_AVAILABILITY:
            if risk_score.level in [RiskLevel.HIGH, RiskLevel.CRITICAL]:
                implications.extend(
                    [
                        "Plan maintenance window during low-traffic period",
                        "Prepare service degradation notifications",
                        "Have rollback plan ready for immediate execution",
                    ]
                )
        elif category == RiskCategory.PERFORMANCE_DEGRADATION:
            if risk_score.level in [RiskLevel.HIGH, RiskLevel.CRITICAL]:
                implications.extend(
                    [
                        "Performance baseline required before migration",
                        "Query optimization may be needed post-migration",
                        "Consider index recreation strategy",
                    ]
                )
        elif category == RiskCategory.ROLLBACK_COMPLEXITY:
            if risk_score.level in [RiskLevel.HIGH, RiskLevel.CRITICAL]:
                implications.extend(
                    [
                        "Detailed rollback documentation required",
                        "Practice rollback procedures in staging",
                        "Extended recovery time planning needed",
                    ]
                )

        return implications

    def _generate_pre_migration_steps(
        self,
        risk_assessment: ComprehensiveRiskAssessment,
        mitigation_plan: Optional[Any],
    ) -> List[str]:
        """Generate pre-migration implementation steps."""
        steps = [
            "Validate backup procedures and recovery testing",
            "Review and approve migration plan with stakeholders",
            "Prepare monitoring and alerting for migration window",
        ]

        if risk_assessment.risk_level in [RiskLevel.HIGH, RiskLevel.CRITICAL]:
            steps.extend(
                [
                    "Conduct migration rehearsal in staging environment",
                    "Prepare detailed communication plan for stakeholders",
                    "Set up enhanced monitoring and logging",
                ]
            )

        if mitigation_plan and hasattr(mitigation_plan, "strategies"):
            steps.append("Implement risk mitigation strategies per mitigation plan")

        return steps

    def _generate_migration_procedure(
        self, risk_assessment: ComprehensiveRiskAssessment
    ) -> List[str]:
        """Generate migration execution procedure."""
        return [
            "Execute pre-migration validation checks",
            "Begin migration with checkpoint logging",
            "Monitor system performance and error rates during migration",
            "Validate data integrity at completion checkpoints",
            "Execute post-migration validation procedures",
        ]

    def _generate_post_migration_validation(
        self, risk_assessment: ComprehensiveRiskAssessment
    ) -> List[str]:
        """Generate post-migration validation steps."""
        return [
            "Verify data integrity and consistency",
            "Validate application functionality and performance",
            "Confirm all dependent systems are operational",
            "Review migration logs for any issues or warnings",
            "Update documentation and migration records",
        ]

    def _generate_rollback_procedures(
        self, risk_assessment: ComprehensiveRiskAssessment
    ) -> List[str]:
        """Generate rollback procedures."""
        procedures = [
            "Stop current migration process immediately",
            "Restore from validated backup (if available)",
            "Verify system functionality after rollback",
        ]

        if risk_assessment.risk_level in [RiskLevel.HIGH, RiskLevel.CRITICAL]:
            procedures.extend(
                [
                    "Execute comprehensive data validation",
                    "Notify all stakeholders of rollback execution",
                    "Conduct post-rollback analysis and documentation",
                ]
            )

        return procedures

    def _analyze_performance_impact(
        self,
        risk_assessment: ComprehensiveRiskAssessment,
        dependency_report: Optional[DependencyReport],
    ) -> Dict[str, Any]:
        """Analyze performance impact details."""
        analysis = {
            "overall_performance_risk": "Unknown",
            "query_impact_expected": False,
            "index_changes_required": False,
            "monitoring_requirements": [],
        }

        # Check for performance-related risk factors
        perf_risks = [
            rf
            for rf in risk_assessment.risk_factors
            if rf.category == RiskCategory.PERFORMANCE_DEGRADATION
        ]

        if perf_risks:
            analysis["overall_performance_risk"] = risk_assessment.category_scores[
                RiskCategory.PERFORMANCE_DEGRADATION
            ].level.value
            analysis["query_impact_expected"] = any(
                "query" in rf.description.lower() for rf in perf_risks
            )
            analysis["index_changes_required"] = any(
                "index" in rf.description.lower() for rf in perf_risks
            )
            analysis["monitoring_requirements"] = [
                "Monitor query execution times",
                "Track database connection counts",
                "Monitor system resource usage",
            ]

        return analysis

    def _determine_infrastructure_requirements(
        self, risk_assessment: ComprehensiveRiskAssessment
    ) -> List[str]:
        """Determine infrastructure requirements."""
        requirements = ["Standard database migration resources"]

        if risk_assessment.risk_level in [RiskLevel.HIGH, RiskLevel.CRITICAL]:
            requirements.extend(
                [
                    "Additional backup storage capacity",
                    "Enhanced monitoring and logging infrastructure",
                    "Dedicated rollback environment preparation",
                ]
            )

        return requirements

    def _generate_monitoring_recommendations(
        self, risk_assessment: ComprehensiveRiskAssessment
    ) -> List[str]:
        """Generate monitoring recommendations."""
        recommendations = [
            "Monitor database connection health",
            "Track migration progress and performance metrics",
        ]

        if risk_assessment.risk_level in [RiskLevel.HIGH, RiskLevel.CRITICAL]:
            recommendations.extend(
                [
                    "Implement real-time alerting for error conditions",
                    "Monitor application error rates and response times",
                    "Set up automated rollback triggers for critical failures",
                ]
            )

        return recommendations

    def _generate_testing_strategy(
        self, risk_assessment: ComprehensiveRiskAssessment
    ) -> List[str]:
        """Generate testing strategy."""
        strategy = [
            "Execute migration in staging environment",
            "Validate application functionality post-migration",
        ]

        if risk_assessment.risk_level in [RiskLevel.HIGH, RiskLevel.CRITICAL]:
            strategy.extend(
                [
                    "Perform comprehensive integration testing",
                    "Execute performance testing with production-like load",
                    "Validate rollback procedures in staging environment",
                ]
            )

        return strategy

    # Compliance and audit methods

    def _determine_applicable_regulations(
        self, risk_assessment: ComprehensiveRiskAssessment
    ) -> List[str]:
        """Determine applicable regulatory frameworks."""
        # Default regulations - would be customized based on business context
        return ["Change Management Policy", "Data Governance Standards"]

    def _assess_compliance_risk(
        self, risk_assessment: ComprehensiveRiskAssessment
    ) -> str:
        """Assess overall compliance risk level."""
        if risk_assessment.risk_level == RiskLevel.CRITICAL:
            return "High compliance risk - regulatory review required"
        elif risk_assessment.risk_level == RiskLevel.HIGH:
            return "Medium compliance risk - documentation review needed"
        else:
            return "Low compliance risk - standard procedures apply"

    def _assess_regulatory_violations(
        self, risk_assessment: ComprehensiveRiskAssessment
    ) -> str:
        """Assess potential for regulatory violations."""
        if risk_assessment.risk_level in [RiskLevel.HIGH, RiskLevel.CRITICAL]:
            return "Potential for compliance violations if not properly managed"
        else:
            return "Low risk of regulatory violations with standard procedures"

    def _assess_data_governance_impact(
        self, risk_assessment: ComprehensiveRiskAssessment
    ) -> str:
        """Assess data governance impact."""
        data_loss_risk = risk_assessment.category_scores.get(RiskCategory.DATA_LOSS)
        if data_loss_risk and data_loss_risk.level in [
            RiskLevel.HIGH,
            RiskLevel.CRITICAL,
        ]:
            return "Significant data governance implications - data steward review required"
        else:
            return "Standard data governance procedures apply"

    def _determine_audit_trail_requirements(
        self, risk_assessment: ComprehensiveRiskAssessment
    ) -> str:
        """Determine audit trail requirements."""
        if risk_assessment.risk_level in [RiskLevel.HIGH, RiskLevel.CRITICAL]:
            return "Enhanced audit trail required - detailed logging and approval documentation"
        else:
            return "Standard audit trail - basic migration logging"

    def _assess_personal_data_impact(
        self, risk_assessment: ComprehensiveRiskAssessment
    ) -> str:
        """Assess impact on personal data."""
        return "Assessment required based on specific data types involved"

    def _assess_data_retention_impact(
        self, risk_assessment: ComprehensiveRiskAssessment
    ) -> str:
        """Assess data retention implications."""
        return "Review data retention policies for affected data"

    def _classify_change(self, risk_assessment: ComprehensiveRiskAssessment) -> str:
        """Classify the change for change management."""
        if risk_assessment.risk_level == RiskLevel.CRITICAL:
            return "Emergency Change - High Risk"
        elif risk_assessment.risk_level == RiskLevel.HIGH:
            return "Major Change - Management Approval Required"
        elif risk_assessment.risk_level == RiskLevel.MEDIUM:
            return "Standard Change - Technical Approval Required"
        else:
            return "Minor Change - Automated Approval"

    def _determine_approval_workflow(
        self, risk_assessment: ComprehensiveRiskAssessment
    ) -> List[str]:
        """Determine approval workflow steps."""
        workflow = ["Technical Review"]

        if risk_assessment.risk_level == RiskLevel.CRITICAL:
            workflow.extend(["Management Approval", "Executive Sign-off"])
        elif risk_assessment.risk_level == RiskLevel.HIGH:
            workflow.append("Management Approval")

        return workflow

    def _determine_documentation_requirements(
        self, risk_assessment: ComprehensiveRiskAssessment
    ) -> List[str]:
        """Determine documentation requirements."""
        requirements = ["Migration Plan", "Risk Assessment Report"]

        if risk_assessment.risk_level in [RiskLevel.HIGH, RiskLevel.CRITICAL]:
            requirements.extend(
                [
                    "Detailed Rollback Plan",
                    "Stakeholder Communication Plan",
                    "Post-Implementation Review Plan",
                ]
            )

        return requirements

    def _determine_stakeholder_notifications(
        self, risk_assessment: ComprehensiveRiskAssessment
    ) -> List[str]:
        """Determine required stakeholder notifications."""
        notifications = ["Technical Team"]

        if risk_assessment.risk_level == RiskLevel.CRITICAL:
            notifications.extend(["Executive Team", "All Affected Business Units"])
        elif risk_assessment.risk_level == RiskLevel.HIGH:
            notifications.extend(["Management Team", "Affected Business Units"])
        elif risk_assessment.risk_level == RiskLevel.MEDIUM:
            notifications.append("Team Leads")

        return notifications

    def _generate_risk_acceptance_criteria(
        self, risk_assessment: ComprehensiveRiskAssessment
    ) -> List[str]:
        """Generate risk acceptance criteria."""
        criteria = []

        if risk_assessment.risk_level == RiskLevel.CRITICAL:
            criteria.extend(
                [
                    "Executive approval with documented risk acceptance",
                    "Comprehensive mitigation plan implementation",
                    "24/7 support team availability during migration",
                ]
            )
        elif risk_assessment.risk_level == RiskLevel.HIGH:
            criteria.extend(
                [
                    "Management approval with mitigation plan",
                    "Enhanced monitoring during migration window",
                ]
            )
        else:
            criteria.append("Standard technical approval and monitoring")

        return criteria

    def _generate_audit_trail_requirements(
        self, risk_assessment: ComprehensiveRiskAssessment
    ) -> List[str]:
        """Generate audit trail requirements."""
        requirements = ["Migration execution logs", "Approval documentation"]

        if risk_assessment.risk_level in [RiskLevel.HIGH, RiskLevel.CRITICAL]:
            requirements.extend(
                [
                    "Detailed decision rationale documentation",
                    "Risk acceptance sign-off records",
                    "Post-migration validation results",
                ]
            )

        return requirements

    def _generate_approval_workflows(
        self, risk_assessment: ComprehensiveRiskAssessment
    ) -> List[str]:
        """Generate approval workflow specifications."""
        workflows = []

        if risk_assessment.risk_level == RiskLevel.CRITICAL:
            workflows.extend(
                [
                    "1. Technical Lead approval",
                    "2. Management Approval",
                    "3. VP Engineering approval",
                    "4. Executive risk acceptance",
                ]
            )
        elif risk_assessment.risk_level == RiskLevel.HIGH:
            workflows.extend(["1. Technical Lead approval", "2. Management Approval"])
        else:
            workflows.append("1. Technical Lead approval")

        return workflows

    def _assess_existing_controls(
        self, risk_assessment: ComprehensiveRiskAssessment
    ) -> List[str]:
        """Assess existing risk controls."""
        controls = [
            "Standard backup and recovery procedures",
            "Change management process",
            "Migration testing in staging",
        ]

        return controls

    def _identify_control_gaps(
        self, risk_assessment: ComprehensiveRiskAssessment
    ) -> List[str]:
        """Identify gaps in existing controls."""
        gaps = []

        if risk_assessment.risk_level in [RiskLevel.HIGH, RiskLevel.CRITICAL]:
            gaps.extend(
                [
                    "Enhanced monitoring during migration execution",
                    "Automated rollback procedures for failure conditions",
                    "Real-time stakeholder communication during issues",
                ]
            )

        return gaps

    def _recommend_additional_controls(
        self, risk_assessment: ComprehensiveRiskAssessment
    ) -> List[str]:
        """Recommend additional risk controls."""
        recommendations = []

        if risk_assessment.risk_level == RiskLevel.CRITICAL:
            recommendations.extend(
                [
                    "Implement automated migration checkpoints",
                    "Deploy real-time monitoring with automatic alerts",
                    "Establish dedicated war room for migration execution",
                ]
            )
        elif risk_assessment.risk_level == RiskLevel.HIGH:
            recommendations.extend(
                [
                    "Enhance pre-migration validation procedures",
                    "Implement additional backup validation steps",
                ]
            )

        return recommendations

    def _determine_control_testing_requirements(
        self, risk_assessment: ComprehensiveRiskAssessment
    ) -> List[str]:
        """Determine control testing requirements."""
        requirements = ["Validate backup and recovery procedures"]

        if risk_assessment.risk_level in [RiskLevel.HIGH, RiskLevel.CRITICAL]:
            requirements.extend(
                [
                    "Test rollback procedures in staging environment",
                    "Validate monitoring and alerting systems",
                    "Test stakeholder communication procedures",
                ]
            )

        return requirements

    def _generate_residual_risk_statement(
        self, risk_assessment: ComprehensiveRiskAssessment
    ) -> str:
        """Generate residual risk statement."""
        if risk_assessment.risk_level == RiskLevel.CRITICAL:
            return "After implementing all recommended mitigations, residual risk remains HIGH due to inherent complexity. Executive acceptance required."
        elif risk_assessment.risk_level == RiskLevel.HIGH:
            return "With proper mitigation implementation, residual risk can be reduced to MEDIUM level. Management oversight recommended."
        elif risk_assessment.risk_level == RiskLevel.MEDIUM:
            return "Standard mitigations will reduce residual risk to LOW level. Technical oversight sufficient."
        else:
            return "Residual risk remains LOW with standard operational procedures."

    # Stakeholder communication methods

    def _generate_key_messages_for_role(
        self,
        role: StakeholderRole,
        risk_assessment: ComprehensiveRiskAssessment,
        executive_summary: Optional[ExecutiveRiskSummary],
    ) -> List[str]:
        """Generate key messages tailored for specific stakeholder role."""
        messages = []

        if role == StakeholderRole.EXECUTIVE:
            messages.extend(
                [
                    f"Migration risk level: {risk_assessment.risk_level.value.upper()}",
                    f"Business impact: {executive_summary.business_impact if executive_summary else 'Assessment in progress'}",
                    f"Approval required: {executive_summary.approval_level if executive_summary else 'TBD'}",
                ]
            )

        elif role == StakeholderRole.MANAGER:
            messages.extend(
                [
                    f"Risk score: {risk_assessment.overall_score:.1f}/100",
                    f"Team coordination required for risk level: {risk_assessment.risk_level.value}",
                    f"Estimated timeline impact: {executive_summary.implementation_timeline if executive_summary else 'TBD'}",
                ]
            )

        elif role == StakeholderRole.TECHNICAL_LEAD:
            high_risk_categories = [
                cat.value
                for cat, score in risk_assessment.category_scores.items()
                if score.level in [RiskLevel.HIGH, RiskLevel.CRITICAL]
            ]
            messages.extend(
                [
                    f"High-risk categories: {', '.join(high_risk_categories) if high_risk_categories else 'None'}",
                    f"Risk factors identified: {len(risk_assessment.risk_factors)}",
                    "Technical coordination required with DBA and DevOps teams",
                ]
            )

        elif role == StakeholderRole.DEVELOPER:
            messages.extend(
                [
                    "Code changes may be required based on dependency analysis",
                    f"Testing strategy needs to account for {risk_assessment.risk_level.value} risk level",
                    "Application monitoring should be enhanced during migration window",
                ]
            )

        elif role in [StakeholderRole.DBA, StakeholderRole.DEVOPS]:
            messages.extend(
                [
                    f"Database operation risk level: {risk_assessment.risk_level.value}",
                    f"Backup and recovery procedures criticality: {'HIGH' if risk_assessment.risk_level in [RiskLevel.HIGH, RiskLevel.CRITICAL] else 'STANDARD'}",
                    "Enhanced monitoring required during migration execution",
                ]
            )

        elif role == StakeholderRole.COMPLIANCE:
            messages.extend(
                [
                    f"Change classification: {self._classify_change(risk_assessment)}",
                    "Audit trail and documentation requirements apply",
                    f"Regulatory review required: {'Yes' if risk_assessment.risk_level in [RiskLevel.HIGH, RiskLevel.CRITICAL] else 'No'}",
                ]
            )

        elif role == StakeholderRole.QA:
            messages.extend(
                [
                    f"Testing scope should reflect {risk_assessment.risk_level.value} risk level",
                    "Pre-migration validation testing is critical",
                    "Post-migration validation testing required",
                ]
            )

        return messages

    def _generate_action_items_for_role(
        self,
        role: StakeholderRole,
        risk_assessment: ComprehensiveRiskAssessment,
        mitigation_plan: Optional[Any],
    ) -> List[str]:
        """Generate action items tailored for specific stakeholder role."""
        actions = []

        if role == StakeholderRole.EXECUTIVE:
            if risk_assessment.risk_level == RiskLevel.CRITICAL:
                actions.append(
                    "Review and approve migration with full risk understanding"
                )
            elif risk_assessment.risk_level == RiskLevel.HIGH:
                actions.append("Approve enhanced risk mitigation budget and resources")

        elif role == StakeholderRole.MANAGER:
            actions.extend(
                [
                    "Coordinate team availability for migration window",
                    "Review resource allocation for risk mitigation activities",
                ]
            )
            if risk_assessment.risk_level in [RiskLevel.HIGH, RiskLevel.CRITICAL]:
                actions.append("Plan for extended team availability during migration")

        elif role == StakeholderRole.TECHNICAL_LEAD:
            actions.extend(
                [
                    "Review technical risk assessment details",
                    "Coordinate with DBA team on migration execution plan",
                ]
            )
            if mitigation_plan:
                actions.append("Implement technical risk mitigation strategies")

        elif role == StakeholderRole.DEVELOPER:
            actions.extend(
                [
                    "Review application impact analysis",
                    "Update application monitoring and logging",
                ]
            )

        elif role == StakeholderRole.DBA:
            actions.extend(
                [
                    "Validate backup and recovery procedures",
                    "Prepare rollback plan and procedures",
                ]
            )
            if risk_assessment.risk_level in [RiskLevel.HIGH, RiskLevel.CRITICAL]:
                actions.append("Conduct migration rehearsal in staging")

        elif role == StakeholderRole.DEVOPS:
            actions.extend(
                [
                    "Prepare enhanced monitoring for migration window",
                    "Validate infrastructure capacity for rollback scenarios",
                ]
            )

        elif role == StakeholderRole.COMPLIANCE:
            actions.extend(
                [
                    "Review change management documentation",
                    "Validate audit trail procedures",
                ]
            )

        elif role == StakeholderRole.QA:
            actions.extend(
                [
                    "Develop comprehensive testing plan",
                    "Execute pre-migration validation testing",
                ]
            )

        return actions

    def _generate_decision_points_for_role(
        self, role: StakeholderRole, risk_assessment: ComprehensiveRiskAssessment
    ) -> List[str]:
        """Generate decision points for specific stakeholder role."""
        decisions = []

        if role == StakeholderRole.EXECUTIVE:
            if risk_assessment.risk_level == RiskLevel.CRITICAL:
                decisions.extend(
                    [
                        "Approve/reject migration execution",
                        "Approve additional budget for risk mitigation",
                    ]
                )
        elif role == StakeholderRole.MANAGER:
            decisions.extend(
                [
                    "Approve team resource allocation",
                    "Decide on migration timing based on risk level",
                ]
            )
        elif role == StakeholderRole.TECHNICAL_LEAD:
            decisions.extend(
                [
                    "Approve technical migration approach",
                    "Decide on additional safety measures",
                ]
            )

        return decisions

    def _generate_timeline_awareness_for_role(
        self, role: StakeholderRole, risk_assessment: ComprehensiveRiskAssessment
    ) -> str:
        """Generate timeline awareness message for role."""
        if risk_assessment.risk_level == RiskLevel.CRITICAL:
            return "CRITICAL: Migration timeline may be extended for comprehensive risk mitigation"
        elif risk_assessment.risk_level == RiskLevel.HIGH:
            return "HIGH RISK: Plan for additional preparation time before migration"
        elif risk_assessment.risk_level == RiskLevel.MEDIUM:
            return "MEDIUM RISK: Standard timeline with enhanced coordination"
        else:
            return "LOW RISK: Standard migration timeline expected"

    def _generate_escalation_criteria_for_role(
        self, role: StakeholderRole, risk_assessment: ComprehensiveRiskAssessment
    ) -> List[str]:
        """Generate escalation criteria for specific role."""
        criteria = []

        if role in [
            StakeholderRole.DEVELOPER,
            StakeholderRole.DBA,
            StakeholderRole.DEVOPS,
        ]:
            criteria.extend(
                [
                    "Escalate to Technical Lead if migration issues arise",
                    "Immediate escalation for any data integrity concerns",
                ]
            )
            if risk_assessment.risk_level in [RiskLevel.HIGH, RiskLevel.CRITICAL]:
                criteria.append("Escalate to Manager for any deviation from plan")

        elif role == StakeholderRole.TECHNICAL_LEAD:
            criteria.extend(
                [
                    "Escalate to Manager if risk mitigation fails",
                    "Immediate escalation for critical system impacts",
                ]
            )

        elif role == StakeholderRole.MANAGER:
            if risk_assessment.risk_level in [RiskLevel.HIGH, RiskLevel.CRITICAL]:
                criteria.append("Escalate to Executive team for critical issues")

        return criteria
