#!/usr/bin/env python3
"""
Risk Assessment Engine for Migration Operations - TODO-140 Phase 1

Provides comprehensive risk scoring and assessment for database migration operations
with multi-dimensional analysis covering data loss, system availability, performance,
and rollback complexity risks.

CORE FEATURES:
- Multi-dimensional risk scoring (0-100 scale)
- Risk level classification (LOW/MEDIUM/HIGH/CRITICAL)
- Integration with DependencyAnalyzer (TODO-137) and ForeignKeyAnalyzer (TODO-138)
- Performance-optimized (<100ms per assessment)
- Configurable risk weights and thresholds

RISK CATEGORIES:
- Data Loss Risk (CRITICAL) - FK CASCADE, data corruption potential
- System Availability Risk (CRITICAL) - Production downtime, system failures
- Performance Degradation Risk (HIGH) - Query performance, index impact
- Compliance Risk (MEDIUM) - Regulatory requirements, audit trails
- Rollback Complexity Risk (MEDIUM) - Recovery difficulty, backup requirements
"""

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Union

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
from .foreign_key_analyzer import FKImpactLevel, FKImpactReport, ForeignKeyAnalyzer

logger = logging.getLogger(__name__)


class RiskCategory(Enum):
    """Risk assessment categories for migration operations."""

    DATA_LOSS = "data_loss"
    SYSTEM_AVAILABILITY = "system_availability"
    PERFORMANCE_DEGRADATION = "performance_degradation"
    COMPLIANCE_RISK = "compliance_risk"
    ROLLBACK_COMPLEXITY = "rollback_complexity"


class RiskLevel(Enum):
    """Risk level classification based on score ranges."""

    LOW = "low"  # 0-25: Safe for automated execution
    MEDIUM = "medium"  # 26-50: Requires technical review
    HIGH = "high"  # 51-75: Requires management approval
    CRITICAL = "critical"  # 76-100: Requires executive approval or blocking


@dataclass
class RiskFactor:
    """Individual risk factor contributing to overall risk."""

    category: RiskCategory
    description: str
    impact_score: float
    confidence: float = 1.0
    mitigation_available: bool = False


@dataclass
class RiskScore:
    """Individual risk category score."""

    category: RiskCategory
    score: float
    level: RiskLevel
    description: str
    risk_factors: List[str] = field(default_factory=list)
    confidence: float = 1.0
    computation_time: float = 0.0


@dataclass
class ComprehensiveRiskAssessment:
    """Complete risk assessment for a migration operation."""

    operation_id: str
    overall_score: float
    risk_level: RiskLevel
    category_scores: Dict[RiskCategory, RiskScore] = field(default_factory=dict)
    risk_factors: List[RiskFactor] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)
    assessment_timestamp: str = field(
        default_factory=lambda: time.strftime("%Y-%m-%d %H:%M:%S")
    )
    total_computation_time: float = 0.0


@dataclass
class BusinessImpactAssessment:
    """Business impact assessment for migrations."""

    estimated_downtime_minutes: float = 0.0
    affected_users: int = 0
    business_critical_systems: List[str] = field(default_factory=list)
    regulatory_implications: List[str] = field(default_factory=list)
    financial_impact_estimate: str = "Unknown"


@dataclass
class MitigationPlan:
    """Risk mitigation plan with actionable steps."""

    risk_category: RiskCategory
    severity: RiskLevel
    mitigation_steps: List[str] = field(default_factory=list)
    estimated_effort_hours: float = 0.0
    prerequisites: List[str] = field(default_factory=list)
    success_criteria: List[str] = field(default_factory=list)


class RiskAssessmentEngine:
    """
    Core Risk Assessment Engine for migration operations.

    Analyzes migration operations across multiple risk dimensions and provides
    quantifiable risk scores with actionable insights and mitigation strategies.
    """

    def __init__(
        self,
        dependency_analyzer: Optional[Any] = None,
        fk_analyzer: Optional[ForeignKeyAnalyzer] = None,
        risk_weights: Optional[Dict[str, float]] = None,
    ):
        """
        Initialize the risk assessment engine.

        Args:
            dependency_analyzer: DependencyAnalyzer instance for dependency analysis
            fk_analyzer: ForeignKeyAnalyzer instance for FK analysis
            risk_weights: Custom weights for risk categories (must sum to 1.0)
        """
        self.dependency_analyzer = dependency_analyzer
        self.fk_analyzer = fk_analyzer
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

        # Default risk weights (must sum to 1.0)
        self.risk_weights = risk_weights or {
            "data_loss": 0.35,  # Highest priority - data integrity
            "system_availability": 0.30,  # High priority - system uptime
            "performance": 0.20,  # Medium priority - performance impact
            "rollback_complexity": 0.15,  # Lower priority - operational complexity
        }

        # Validate weights sum to 1.0
        total_weight = sum(self.risk_weights.values())
        if abs(total_weight - 1.0) > 0.001:
            raise ValueError(f"Risk weights must sum to 1.0, got {total_weight}")

        # Risk thresholds for level classification
        self.thresholds = {
            RiskLevel.LOW: (0, 25),
            RiskLevel.MEDIUM: (26, 50),
            RiskLevel.HIGH: (51, 75),
            RiskLevel.CRITICAL: (76, 100),
        }

    def calculate_migration_risk_score(
        self,
        operation: Any,
        dependency_report: DependencyReport,
        fk_impact_report: Optional[FKImpactReport] = None,
    ) -> ComprehensiveRiskAssessment:
        """
        Calculate comprehensive migration risk score across all categories.

        Args:
            operation: Migration operation to assess
            dependency_report: Dependency analysis from TODO-137
            fk_impact_report: FK impact analysis from TODO-138

        Returns:
            ComprehensiveRiskAssessment with overall and category-specific scores
        """
        start_time = time.time()
        operation_id = f"risk_assessment_{int(start_time)}"

        self.logger.info(
            f"Starting comprehensive risk assessment for {operation.table}.{operation.column}"
        )

        # Calculate individual category scores
        category_scores = {}

        # Data Loss Risk (CRITICAL category)
        category_scores[RiskCategory.DATA_LOSS] = self.calculate_data_loss_risk(
            operation, dependency_report
        )

        # System Availability Risk (CRITICAL category)
        category_scores[RiskCategory.SYSTEM_AVAILABILITY] = (
            self.calculate_system_availability_risk(operation, dependency_report)
        )

        # Performance Risk (HIGH category)
        category_scores[RiskCategory.PERFORMANCE_DEGRADATION] = (
            self.calculate_performance_risk(operation, dependency_report)
        )

        # Rollback Complexity Risk (MEDIUM category)
        category_scores[RiskCategory.ROLLBACK_COMPLEXITY] = (
            self.calculate_rollback_complexity_risk(operation, dependency_report)
        )

        # Calculate weighted overall score
        overall_score = self._calculate_weighted_score(category_scores)
        risk_level = self._determine_risk_level(overall_score)

        # Collect all risk factors
        all_risk_factors = []
        for category_score in category_scores.values():
            for factor_desc in category_score.risk_factors:
                risk_factor = RiskFactor(
                    category=category_score.category,
                    description=factor_desc,
                    impact_score=category_score.score,
                    confidence=category_score.confidence,
                )
                all_risk_factors.append(risk_factor)

        # Generate recommendations based on risk level
        recommendations = self._generate_basic_recommendations(
            risk_level, category_scores
        )

        total_time = time.time() - start_time

        assessment = ComprehensiveRiskAssessment(
            operation_id=operation_id,
            overall_score=overall_score,
            risk_level=risk_level,
            category_scores=category_scores,
            risk_factors=all_risk_factors,
            recommendations=recommendations,
            total_computation_time=total_time,
        )

        self.logger.info(
            f"Risk assessment complete: {overall_score:.1f} ({risk_level.value.upper()}) in {total_time:.3f}s"
        )

        return assessment

    def calculate_data_loss_risk(
        self, operation: Any, dependencies: DependencyReport
    ) -> RiskScore:
        """
        Calculate data loss risk based on operation type and dependencies.

        CRITICAL RISK FACTORS:
        - FK CASCADE operations (90-100 points)
        - Primary key column operations (80-95 points)
        - Operations without backups (70-85 points)
        """
        start_time = time.time()
        base_score = 0.0
        risk_factors = []

        # Check foreign key dependencies for CASCADE operations
        fk_dependencies = dependencies.dependencies.get(DependencyType.FOREIGN_KEY, [])

        for fk_dep in fk_dependencies:
            if isinstance(fk_dep, ForeignKeyDependency):
                if fk_dep.on_delete == "CASCADE" or fk_dep.on_update == "CASCADE":
                    # CRITICAL: CASCADE operations can cause cascading data loss
                    base_score = max(base_score, 90)
                    risk_factors.append(
                        f"FK CASCADE constraint {fk_dep.constraint_name} will cause cascading data loss"
                    )

                elif fk_dep.on_delete == "RESTRICT" or fk_dep.on_update == "RESTRICT":
                    # MEDIUM: RESTRICT will block operation but no data loss
                    base_score = max(base_score, 35)
                    risk_factors.append(
                        f"FK RESTRICT constraint {fk_dep.constraint_name} may block operation"
                    )

        # Check for operations without backups in production
        if hasattr(operation, "has_backup") and not operation.has_backup:
            if hasattr(operation, "is_production") and operation.is_production:
                base_score = max(base_score, 75)
                risk_factors.append(
                    "No backup available for production operation - high data loss risk"
                )
            else:
                base_score = max(base_score, 45)
                risk_factors.append("No backup available - moderate data loss risk")

        # Check if we have any dependencies at all
        has_any_dependencies = dependencies.has_dependencies()

        # Base risk for different operation types
        if hasattr(operation, "operation_type"):
            if operation.operation_type == "drop_column":
                if not has_any_dependencies:  # Truly no dependencies
                    base_score = max(base_score, 10)
                    risk_factors.append("Column drop operation with no dependencies")
                elif not risk_factors:  # Some dependencies but none critical
                    base_score = max(base_score, 10)
                    risk_factors.append(
                        "Column drop operation with minimal dependencies"
                    )
            elif operation.operation_type == "drop_table":
                base_score = max(base_score, 60)
                risk_factors.append("Table drop operation - permanent data loss")

        # Default low risk if no dependencies at all
        if not has_any_dependencies and base_score == 0:
            base_score = 5
            risk_factors.append("Operation has no dependencies detected")

        # Determine risk level and create description
        risk_level = self._determine_risk_level(base_score)

        if risk_level == RiskLevel.CRITICAL:
            description = "CRITICAL data loss risk detected - CASCADE constraints or critical dependencies present"
        elif risk_level == RiskLevel.HIGH:
            description = "HIGH data loss risk - Multiple dependencies or production operation without backup"
        elif risk_level == RiskLevel.MEDIUM:
            description = "MEDIUM data loss risk - Some dependencies present with RESTRICT constraints"
        else:
            has_any_dependencies = dependencies.has_dependencies()
            if not has_any_dependencies:
                description = "LOW data loss risk - no dependencies found"
            else:
                description = "LOW data loss risk - no critical dependencies found"

        computation_time = time.time() - start_time

        return RiskScore(
            category=RiskCategory.DATA_LOSS,
            score=base_score,
            level=risk_level,
            description=description,
            risk_factors=risk_factors,
            confidence=0.95,
            computation_time=computation_time,
        )

    def calculate_system_availability_risk(
        self, operation: Any, dependencies: DependencyReport
    ) -> RiskScore:
        """
        Calculate system availability risk based on operation impact on running systems.

        CRITICAL RISK FACTORS:
        - Production environment operations (70-90 points)
        - Large table operations (60-80 points)
        - Operations affecting active views/triggers (50-70 points)
        """
        start_time = time.time()
        base_score = 0.0
        risk_factors = []

        # Production environment risk
        if hasattr(operation, "is_production") and operation.is_production:
            base_score = max(base_score, 70)
            risk_factors.append(
                "Production environment operation increases availability risk"
            )

            # Large table in production
            if (
                hasattr(operation, "estimated_rows")
                and operation.estimated_rows > 100000
            ):
                base_score = max(base_score, 85)
                risk_factors.append(
                    f"Large table ({operation.estimated_rows:,} rows) in production"
                )

            # Very large table in production
            if hasattr(operation, "table_size_mb") and operation.table_size_mb > 100:
                base_score = max(base_score, 90)
                risk_factors.append(
                    f"Very large table ({operation.table_size_mb:.1f}MB) in production"
                )
        else:
            # Development/staging environment
            base_score = max(base_score, 15)
            risk_factors.append(
                "Development environment operation - lower availability risk"
            )

        # View dependencies that could break applications
        view_dependencies = dependencies.dependencies.get(DependencyType.VIEW, [])
        if view_dependencies:
            additional_risk = min(len(view_dependencies) * 15, 60)
            base_score = min(100, base_score + additional_risk)  # Cap at 100
            risk_factors.append(
                f"Operation affects {len(view_dependencies)} views - potential application breakage"
            )

        # Trigger dependencies that could affect functionality
        trigger_dependencies = dependencies.dependencies.get(DependencyType.TRIGGER, [])
        if trigger_dependencies:
            additional_risk = min(len(trigger_dependencies) * 20, 50)
            base_score = min(100, base_score + additional_risk)  # Cap at 100
            risk_factors.append(
                f"Operation affects {len(trigger_dependencies)} triggers - functionality impact"
            )

        # Determine risk level and create description
        risk_level = self._determine_risk_level(base_score)

        if risk_level == RiskLevel.CRITICAL:
            description = "CRITICAL availability risk - Production environment with large tables or many dependencies"
        elif risk_level == RiskLevel.HIGH:
            description = "HIGH availability risk - Production operation or significant dependencies"
        elif risk_level == RiskLevel.MEDIUM:
            description = (
                "MEDIUM availability risk - Some dependencies or moderate table size"
            )
        else:
            description = "LOW availability risk - Development environment with minimal dependencies"

        computation_time = time.time() - start_time

        return RiskScore(
            category=RiskCategory.SYSTEM_AVAILABILITY,
            score=base_score,
            level=risk_level,
            description=description,
            risk_factors=risk_factors,
            confidence=0.90,
            computation_time=computation_time,
        )

    def calculate_performance_risk(
        self, operation: Any, dependencies: DependencyReport
    ) -> RiskScore:
        """
        Calculate performance degradation risk based on index and constraint impact.

        HIGH RISK FACTORS:
        - Unique index removal (60-75 points)
        - Multiple index removal (50-70 points)
        - Large table operations (40-60 points)
        """
        start_time = time.time()
        base_score = 0.0
        risk_factors = []

        # Index dependencies analysis
        index_dependencies = dependencies.dependencies.get(DependencyType.INDEX, [])

        unique_indexes = 0
        total_indexes = len(index_dependencies)

        for index_dep in index_dependencies:
            if isinstance(index_dep, IndexDependency):
                if getattr(index_dep, "is_unique", False):
                    unique_indexes += 1

        # Unique index impact
        if unique_indexes > 0:
            base_score = max(base_score, 60 + (unique_indexes - 1) * 10)
            risk_factors.append(
                f"Operation will remove {unique_indexes} unique index(es) - data uniqueness enforcement lost"
            )

        # Total index impact
        if total_indexes > 0:
            index_risk = min(30 + (total_indexes * 10), 70)
            base_score = max(base_score, index_risk)
            risk_factors.append(
                f"Operation will drop {total_indexes} index(es) - query performance impact expected"
            )

        # Table size performance impact
        if hasattr(operation, "estimated_rows") and operation.estimated_rows > 500000:
            size_risk = min(40 + (operation.estimated_rows // 500000) * 10, 65)
            base_score = max(base_score, size_risk)
            risk_factors.append(
                f"Large table ({operation.estimated_rows:,} rows) - significant performance impact"
            )

        # Constraint dependencies
        constraint_dependencies = dependencies.dependencies.get(
            DependencyType.CONSTRAINT, []
        )
        if constraint_dependencies:
            constraint_risk = min(len(constraint_dependencies) * 15, 45)
            base_score = max(base_score, constraint_risk)
            risk_factors.append(
                f"Operation affects {len(constraint_dependencies)} constraint(s)"
            )

        # Default minimal performance risk
        if base_score == 0:
            base_score = 5
            risk_factors.append(
                "Minimal performance impact expected - no critical indexes affected"
            )

        # Determine risk level and create description
        risk_level = self._determine_risk_level(base_score)

        if risk_level == RiskLevel.CRITICAL:
            description = "CRITICAL performance risk - Multiple unique indexes or very large table operations"
        elif risk_level == RiskLevel.HIGH:
            description = "HIGH performance risk - Unique indexes or large table with many indexes affected"
        elif risk_level == RiskLevel.MEDIUM:
            description = (
                "MEDIUM performance risk - Some indexes or constraints will be affected"
            )
        else:
            description = (
                "LOW performance risk - Minimal impact on query performance expected"
            )

        computation_time = time.time() - start_time

        return RiskScore(
            category=RiskCategory.PERFORMANCE_DEGRADATION,
            score=base_score,
            level=risk_level,
            description=description,
            risk_factors=risk_factors,
            confidence=0.85,
            computation_time=computation_time,
        )

    def calculate_rollback_complexity_risk(
        self, operation: Any, dependencies: DependencyReport
    ) -> RiskScore:
        """
        Calculate rollback complexity risk based on operation reversibility.

        CRITICAL RISK FACTORS:
        - CASCADE FK chains (80-95 points)
        - Operations without backups (70-85 points)
        - Complex dependency chains (60-80 points)
        """
        start_time = time.time()
        base_score = 0.0
        risk_factors = []

        # FK CASCADE chain complexity
        fk_dependencies = dependencies.dependencies.get(DependencyType.FOREIGN_KEY, [])
        cascade_count = 0

        for fk_dep in fk_dependencies:
            if isinstance(fk_dep, ForeignKeyDependency):
                if fk_dep.on_delete == "CASCADE" or fk_dep.on_update == "CASCADE":
                    cascade_count += 1

        if cascade_count > 0:
            cascade_risk = min(70 + (cascade_count * 15), 95)
            base_score = max(base_score, cascade_risk)
            risk_factors.append(
                f"Complex FK CASCADE chain ({cascade_count} constraints) - difficult rollback"
            )

        # Backup availability
        if hasattr(operation, "has_backup"):
            if not operation.has_backup:
                base_score = max(base_score, 80)
                risk_factors.append(
                    "No backup available - rollback requires complex data recreation"
                )
            else:
                # With backup and no other risks, keep risk low
                if base_score == 0:
                    base_score = max(base_score, 15)
                    risk_factors.append(
                        "Backup available - rollback possible but may require coordination"
                    )

        # Multiple dependency types increase rollback complexity
        dependency_types = len(
            [deps for deps in dependencies.dependencies.values() if deps]
        )
        if dependency_types > 2:
            complexity_risk = min(35 + (dependency_types * 10), 70)
            base_score = max(base_score, complexity_risk)
            risk_factors.append(
                f"Multiple dependency types ({dependency_types}) increase rollback complexity"
            )

        # Operation type specific risks
        if hasattr(operation, "operation_type"):
            if operation.operation_type == "drop_table":
                base_score = max(base_score, 85)
                risk_factors.append(
                    "Table drop operation - very difficult to rollback without full backup"
                )
            elif operation.operation_type == "drop_column":
                # Only add complexity if there are actual risks or no backup
                if cascade_count > 0 or (
                    hasattr(operation, "has_backup") and not operation.has_backup
                ):
                    base_score = max(base_score, 55)
                    risk_factors.append(
                        "Column drop operation - moderate rollback complexity"
                    )
                else:
                    # Simple column drop with backup - minimal complexity
                    base_score = max(base_score, 20)
                    if (
                        "Column drop operation - moderate rollback complexity"
                        not in risk_factors
                    ):
                        risk_factors.append(
                            "Simple column drop - minimal rollback complexity"
                        )

        # Default minimal rollback risk
        if base_score <= 15:
            base_score = 10
            risk_factors = ["Simple rollback expected - minimal dependencies"]

        # Determine risk level and create description
        risk_level = self._determine_risk_level(base_score)

        if risk_level == RiskLevel.CRITICAL:
            description = (
                "CRITICAL rollback complexity - CASCADE chains or no backup available"
            )
        elif risk_level == RiskLevel.HIGH:
            description = (
                "HIGH rollback complexity - Multiple dependencies or complex operations"
            )
        elif risk_level == RiskLevel.MEDIUM:
            description = "MEDIUM rollback complexity - Some coordination required"
        else:
            description = "LOW rollback complexity - Simple operation reversal possible"

        computation_time = time.time() - start_time

        return RiskScore(
            category=RiskCategory.ROLLBACK_COMPLEXITY,
            score=base_score,
            level=risk_level,
            description=description,
            risk_factors=risk_factors,
            confidence=0.88,
            computation_time=computation_time,
        )

    def assess_dependency_risk(self, dependencies: List[Any]) -> Any:
        """
        Assess risk from a list of dependencies.

        Args:
            dependencies: List of dependency objects

        Returns:
            DependencyRiskAssessment with risk analysis
        """
        # Placeholder for dependency risk assessment
        # This would analyze the dependency chain complexity
        pass

    def evaluate_business_impact(self, operation: Any) -> BusinessImpactAssessment:
        """
        Evaluate business impact of migration operation.

        Args:
            operation: Migration operation to assess

        Returns:
            BusinessImpactAssessment with business impact analysis
        """
        # Placeholder for business impact evaluation
        return BusinessImpactAssessment()

    def generate_risk_mitigation_plan(self, risks: List[Any]) -> MitigationPlan:
        """
        Generate risk mitigation plan with actionable steps.

        Args:
            risks: List of identified risks

        Returns:
            MitigationPlan with specific mitigation strategies
        """
        # Placeholder for mitigation plan generation
        return MitigationPlan(
            risk_category=RiskCategory.DATA_LOSS, severity=RiskLevel.MEDIUM
        )

    # Helper methods

    def _calculate_weighted_score(
        self, category_scores: Dict[RiskCategory, RiskScore]
    ) -> float:
        """Calculate weighted overall risk score."""
        total_score = 0.0

        weight_mapping = {
            RiskCategory.DATA_LOSS: "data_loss",
            RiskCategory.SYSTEM_AVAILABILITY: "system_availability",
            RiskCategory.PERFORMANCE_DEGRADATION: "performance",
            RiskCategory.ROLLBACK_COMPLEXITY: "rollback_complexity",
        }

        for category, risk_score in category_scores.items():
            weight_key = weight_mapping.get(category)
            if weight_key and weight_key in self.risk_weights:
                weight = self.risk_weights[weight_key]
                total_score += risk_score.score * weight

        return min(total_score, 100.0)  # Cap at 100

    def _determine_risk_level(self, score: float) -> RiskLevel:
        """Determine risk level from numerical score."""
        if score >= 76:
            return RiskLevel.CRITICAL
        elif score >= 51:
            return RiskLevel.HIGH
        elif score >= 26:
            return RiskLevel.MEDIUM
        else:
            return RiskLevel.LOW

    def _generate_basic_recommendations(
        self, risk_level: RiskLevel, category_scores: Dict[RiskCategory, RiskScore]
    ) -> List[str]:
        """Generate basic recommendations based on risk assessment."""
        recommendations = []

        if risk_level == RiskLevel.CRITICAL:
            recommendations.extend(
                [
                    "❌ DO NOT PROCEED - Critical risks detected that could cause data loss",
                    "Obtain executive approval before proceeding with this migration",
                    "Implement comprehensive backup and rollback plan",
                    "Consider breaking operation into smaller, safer steps",
                ]
            )
        elif risk_level == RiskLevel.HIGH:
            recommendations.extend(
                [
                    "⚠️ HIGH RISK - Requires management approval and careful planning",
                    "Execute during maintenance window with full team available",
                    "Ensure backup and rollback procedures are tested",
                    "Monitor system closely after execution",
                ]
            )
        elif risk_level == RiskLevel.MEDIUM:
            recommendations.extend(
                [
                    "🟡 MEDIUM RISK - Requires technical review and coordination",
                    "Schedule during low-traffic period",
                    "Have rollback plan ready",
                    "Test in staging environment first",
                ]
            )
        else:
            recommendations.extend(
                [
                    "✅ LOW RISK - Safe to proceed with standard precautions",
                    "Execute during regular maintenance window",
                    "Basic backup recommended",
                ]
            )

        # Add category-specific recommendations
        for category, score in category_scores.items():
            if score.level in [RiskLevel.HIGH, RiskLevel.CRITICAL]:
                if category == RiskCategory.DATA_LOSS:
                    recommendations.append(
                        "Address FK CASCADE constraints before proceeding"
                    )
                elif category == RiskCategory.SYSTEM_AVAILABILITY:
                    recommendations.append("Plan for potential system downtime")
                elif category == RiskCategory.PERFORMANCE_DEGRADATION:
                    recommendations.append(
                        "Analyze query performance impact and prepare alternatives"
                    )
                elif category == RiskCategory.ROLLBACK_COMPLEXITY:
                    recommendations.append(
                        "Prepare comprehensive rollback documentation"
                    )

        return recommendations
