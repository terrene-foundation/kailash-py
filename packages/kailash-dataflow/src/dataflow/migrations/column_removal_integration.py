#!/usr/bin/env python3
"""
Integration adapter for Column Removal Manager with updated Dependency Analyzer

Provides compatibility layer between the column removal system and the updated
dependency analyzer that uses DependencyReport and specialized dependency types.

This adapter handles:
- Converting DependencyReport to RemovalPlan dependencies
- Mapping specialized dependency types to removal stages
- Risk level compatibility between systems
"""

import logging
from typing import List, Union

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


class UnifiedDependency:
    """Unified dependency representation for column removal."""

    def __init__(
        self,
        object_name: str,
        dependency_type: DependencyType,
        risk_level: ImpactLevel,
        details: dict = None,
    ):
        self.object_name = object_name
        self.dependency_type = dependency_type
        self.risk_level = risk_level
        self.details = details or {}


class DependencyReportAdapter:
    """Adapter to convert DependencyReport to removal-compatible format."""

    @staticmethod
    def convert_report_to_dependencies(
        report: DependencyReport,
    ) -> List[UnifiedDependency]:
        """
        Convert DependencyReport to list of UnifiedDependency objects.

        Args:
            report: DependencyReport from dependency analyzer

        Returns:
            List of UnifiedDependency objects for removal planning
        """
        dependencies = []

        # Convert foreign key dependencies
        for fk_dep in report.foreign_key_dependencies:
            dependencies.append(
                UnifiedDependency(
                    object_name=fk_dep.constraint_name,
                    dependency_type=DependencyType.FOREIGN_KEY,
                    risk_level=fk_dep.impact_level,
                    details={
                        "source_table": fk_dep.source_table,
                        "source_columns": fk_dep.source_columns,
                        "target_table": fk_dep.target_table,
                        "target_columns": fk_dep.target_columns,
                        "on_delete": fk_dep.on_delete,
                        "on_update": fk_dep.on_update,
                    },
                )
            )

        # Convert view dependencies
        for view_dep in report.view_dependencies:
            dependencies.append(
                UnifiedDependency(
                    object_name=view_dep.view_name,
                    dependency_type=DependencyType.VIEW,
                    risk_level=view_dep.impact_level,
                    details={
                        "schema_name": view_dep.schema_name,
                        "is_materialized": view_dep.is_materialized,
                        "view_definition": view_dep.view_definition,
                    },
                )
            )

        # Convert trigger dependencies
        for trigger_dep in report.trigger_dependencies:
            dependencies.append(
                UnifiedDependency(
                    object_name=trigger_dep.trigger_name,
                    dependency_type=DependencyType.TRIGGER,
                    risk_level=trigger_dep.impact_level,
                    details={
                        "event": trigger_dep.event,
                        "timing": trigger_dep.timing,
                        "function_name": trigger_dep.function_name,
                        "action_statement": trigger_dep.action_statement,
                    },
                )
            )

        # Convert index dependencies
        for index_dep in report.index_dependencies:
            dependencies.append(
                UnifiedDependency(
                    object_name=index_dep.index_name,
                    dependency_type=DependencyType.INDEX,
                    risk_level=index_dep.impact_level,
                    details={
                        "index_columns": index_dep.index_columns,
                        "is_unique": index_dep.is_unique,
                        "is_primary": index_dep.is_primary,
                        "is_single_column": len(index_dep.index_columns) == 1,
                    },
                )
            )

        # Convert constraint dependencies
        for constraint_dep in report.constraint_dependencies:
            dependencies.append(
                UnifiedDependency(
                    object_name=constraint_dep.constraint_name,
                    dependency_type=DependencyType.CONSTRAINT,
                    risk_level=constraint_dep.impact_level,
                    details={
                        "constraint_type": constraint_dep.constraint_type,
                        "constraint_definition": constraint_dep.constraint_definition,
                        "columns_referenced": constraint_dep.columns_referenced,
                    },
                )
            )

        logger.info(f"Converted dependency report: {len(dependencies)} dependencies")
        return dependencies

    @staticmethod
    def get_highest_risk_level(dependencies: List[UnifiedDependency]) -> ImpactLevel:
        """Get the highest risk level from a list of dependencies."""
        if not dependencies:
            return ImpactLevel.INFORMATIONAL

        risk_priority = {
            ImpactLevel.CRITICAL: 4,
            ImpactLevel.HIGH: 3,
            ImpactLevel.MEDIUM: 2,
            ImpactLevel.LOW: 1,
            ImpactLevel.INFORMATIONAL: 0,
        }

        highest_priority = max(
            risk_priority.get(dep.risk_level, 0) for dep in dependencies
        )

        for level, priority in risk_priority.items():
            if priority == highest_priority:
                return level

        return ImpactLevel.INFORMATIONAL

    @staticmethod
    def get_blocking_dependencies(
        dependencies: List[UnifiedDependency],
    ) -> List[UnifiedDependency]:
        """Get dependencies that block column removal (CRITICAL risk level)."""
        return [dep for dep in dependencies if dep.risk_level == ImpactLevel.CRITICAL]

    @staticmethod
    def group_dependencies_by_type(dependencies: List[UnifiedDependency]) -> dict:
        """Group dependencies by their type for stage planning."""
        groups = {}

        for dep in dependencies:
            if dep.dependency_type not in groups:
                groups[dep.dependency_type] = []
            groups[dep.dependency_type].append(dep)

        return groups

    @staticmethod
    def estimate_removal_duration(dependencies: List[UnifiedDependency]) -> float:
        """Estimate removal duration based on dependencies."""
        base_time = 5.0  # Base overhead

        # Time per dependency type
        type_times = {
            DependencyType.INDEX: 2.0,
            DependencyType.FOREIGN_KEY: 3.0,
            DependencyType.CONSTRAINT: 1.0,
            DependencyType.TRIGGER: 2.0,
            DependencyType.VIEW: 1.0,
        }

        total_time = base_time
        for dep in dependencies:
            total_time += type_times.get(dep.dependency_type, 1.0)

        return total_time

    @staticmethod
    def generate_removal_warnings(dependencies: List[UnifiedDependency]) -> List[str]:
        """Generate warnings based on dependency analysis."""
        warnings = []

        blocking_deps = DependencyReportAdapter.get_blocking_dependencies(dependencies)
        if blocking_deps:
            warnings.append(
                f"CRITICAL dependencies found: {len(blocking_deps)} objects would be broken"
            )

        high_risk_deps = [
            dep for dep in dependencies if dep.risk_level == ImpactLevel.HIGH
        ]
        if high_risk_deps:
            warnings.append(
                f"HIGH risk dependencies found: {len(high_risk_deps)} objects"
            )

        # Specific warnings by type
        fk_deps = [
            dep
            for dep in dependencies
            if dep.dependency_type == DependencyType.FOREIGN_KEY
        ]
        if fk_deps:
            incoming_fks = [
                dep
                for dep in fk_deps
                if dep.details.get("source_table") != dep.details.get("target_table")
            ]
            if incoming_fks:
                warnings.append(
                    "Incoming foreign key constraints detected - removal may break referencing tables"
                )

        view_deps = [
            dep for dep in dependencies if dep.dependency_type == DependencyType.VIEW
        ]
        if view_deps:
            materialized_views = [
                dep for dep in view_deps if dep.details.get("is_materialized")
            ]
            if materialized_views:
                warnings.append(
                    "Materialized views detected - removal will require view recreation"
                )

        return warnings

    @staticmethod
    def generate_removal_recommendations(
        dependencies: List[UnifiedDependency],
    ) -> List[str]:
        """Generate recommendations based on dependency analysis."""
        recommendations = []

        blocking_deps = DependencyReportAdapter.get_blocking_dependencies(dependencies)
        if blocking_deps:
            recommendations.append(
                "Remove or modify dependent objects before column removal"
            )

        high_risk_deps = [
            dep for dep in dependencies if dep.risk_level == ImpactLevel.HIGH
        ]
        if high_risk_deps:
            recommendations.append("Review dependent objects and consider impact")

        # Type-specific recommendations
        view_deps = [
            dep for dep in dependencies if dep.dependency_type == DependencyType.VIEW
        ]
        if view_deps:
            recommendations.append("Consider recreating views after column removal")

        trigger_deps = [
            dep for dep in dependencies if dep.dependency_type == DependencyType.TRIGGER
        ]
        if trigger_deps:
            recommendations.append("Review trigger logic after column removal")

        index_deps = [
            dep for dep in dependencies if dep.dependency_type == DependencyType.INDEX
        ]
        composite_indexes = [
            dep for dep in index_deps if not dep.details.get("is_single_column", True)
        ]
        if composite_indexes:
            recommendations.append(
                "Monitor query performance after composite index removal"
            )

        return recommendations
