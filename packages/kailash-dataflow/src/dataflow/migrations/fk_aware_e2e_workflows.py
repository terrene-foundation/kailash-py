#!/usr/bin/env python3
"""
FK-Aware E2E Workflow Patterns - TODO-138 Phase 3

Complete end-to-end workflow patterns demonstrating the 5 key FK-aware scenarios
with full Kailash Core SDK compliance and seamless DataFlow integration.

KEY E2E SCENARIOS:
1. Complete DataFlow Integration - @db.model changes trigger FK-aware migrations
2. Multi-table Schema Evolution - Coordinated changes across FK-related tables
3. Production Deployment Workflow - Safe deployment with FK preservation
4. Developer Experience Workflow - Seamless FK handling in development
5. Emergency Rollback Workflow - Complete system recovery with FK restoration

CORE SDK PATTERN COMPLIANCE:
- WorkflowBuilder Integration: workflow.add_node("NodeName", "id", {})
- Essential Execution: runtime.execute(workflow.build())
- 4-parameter connections: workflow.add_connection("source", "output", "target", "input")
- 3-method parameter passing: workflow config, connections, runtime parameters

Each pattern demonstrates complete FK-aware operations from analysis to execution
with comprehensive safety guarantees and rollback capabilities.
"""

import asyncio
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

# DataFlow imports
from dataflow.core.engine import DataFlow
from dataflow.migrations.schema_state_manager import ChangeType
from dataflow.migrations.schema_state_manager import MigrationOperation as SchemaChange

from kailash.runtime import AsyncLocalRuntime
from kailash.runtime.local import LocalRuntime

# Core SDK imports (conceptual)
from kailash.workflow.builder import WorkflowBuilder

from .fk_aware_nodes import register_fk_aware_nodes

# FK-aware components
from .fk_aware_workflow_orchestrator import E2EWorkflowType, FKAwareWorkflowOrchestrator

# from dataflow.core.schema_change import SchemaChange, ChangeType


logger = logging.getLogger(__name__)


class E2EWorkflowPattern:
    """Base class for E2E workflow patterns."""

    def __init__(self, pattern_name: str, description: str):
        self.pattern_name = pattern_name
        self.description = description
        self.logger = logging.getLogger(f"{self.__class__.__name__}")

    async def create_workflow(self, **kwargs) -> WorkflowBuilder:
        """Create Core SDK workflow for this pattern."""
        raise NotImplementedError("Subclasses must implement create_workflow")

    async def execute_workflow(
        self, workflow: WorkflowBuilder, **kwargs
    ) -> Dict[str, Any]:
        """
        Execute workflow using Core SDK runtime.

        ✅ FIX: async method must use AsyncLocalRuntime and await
        """
        runtime = AsyncLocalRuntime()
        results, run_id = await runtime.execute_workflow_async(
            workflow.build(), inputs={}
        )
        return {"results": results, "run_id": run_id}

    def get_pattern_description(self) -> Dict[str, Any]:
        """Get detailed pattern description."""
        return {
            "name": self.pattern_name,
            "description": self.description,
            "sdk_compliance": "Full Core SDK pattern compliance",
            "safety_level": "High - FK referential integrity preserved",
        }


class DataFlowIntegrationPattern(E2EWorkflowPattern):
    """
    E2E Pattern 1: Complete DataFlow Integration

    Demonstrates seamless @db.model integration where FK operations
    are automatically handled when models change.

    User Experience:
    ```python
    @db.model
    class Product:
        id: int  # Change from INTEGER to BIGINT - handled automatically
        name: str
        category_id: int  # FK reference - coordinated changes
    ```
    """

    def __init__(self):
        super().__init__(
            "DataFlow Integration",
            "Seamless @db.model integration with automatic FK-aware migrations",
        )

    async def create_workflow(
        self, dataflow_instance: DataFlow, model_changes: List[Dict[str, Any]], **kwargs
    ) -> WorkflowBuilder:
        """Create DataFlow integration workflow."""
        workflow = WorkflowBuilder()

        self.logger.info("Creating DataFlow integration workflow with FK awareness")

        # Register FK-aware nodes for this workflow
        register_fk_aware_nodes()

        # Node 1: DataFlow Model Analyzer - Analyze @db.model changes
        workflow.add_node(
            "DataFlowModelAnalyzerNode",
            "model_analyzer",
            {
                "model_changes": model_changes,
                "dataflow_instance_config": self._extract_dataflow_config(
                    dataflow_instance
                ),
                "auto_migration_enabled": getattr(
                    dataflow_instance, "auto_migrate", False
                ),
            },
        )

        # Node 2: FK Impact Analyzer - Analyze FK relationships between models
        workflow.add_node(
            "ForeignKeyAnalyzerNode",
            "fk_analyzer",
            {"execution_mode": "safe", "model_integration": True},
        )

        # Node 3: Model Dependency Resolver - Resolve model dependencies
        workflow.add_node(
            "ModelDependencyResolverNode",
            "dependency_resolver",
            {"resolve_circular_refs": True, "dependency_depth": 5},
        )

        # Node 4: DataFlow Migration Generator - Generate DataFlow migrations
        workflow.add_node(
            "DataFlowMigrationGeneratorNode",
            "migration_generator",
            {
                "generate_migration_files": True,
                "preserve_existing_data": True,
                "fk_aware_operations": True,
            },
        )

        # Node 5: FK-Safe Migration Executor - Execute with FK safety
        workflow.add_node(
            "FKSafeMigrationExecutorNode",
            "migration_executor",
            {
                "workflow_id": f"dataflow_integration_{uuid.uuid4().hex[:8]}",
                "enable_rollback": True,
                "dataflow_integration": True,
            },
        )

        # Node 6: DataFlow Schema Validator - Validate final schema
        workflow.add_node(
            "DataFlowSchemaValidatorNode",
            "schema_validator",
            {
                "validate_models": True,
                "check_fk_constraints": True,
                "verify_data_integrity": True,
            },
        )

        # Create connections (4-parameter pattern)
        workflow.add_connection(
            "model_analyzer", "model_changes", "fk_analyzer", "schema_changes"
        )
        workflow.add_connection(
            "fk_analyzer",
            "fk_impact_reports",
            "dependency_resolver",
            "fk_relationships",
        )
        workflow.add_connection(
            "dependency_resolver",
            "resolved_dependencies",
            "migration_generator",
            "dependency_info",
        )
        workflow.add_connection(
            "migration_generator",
            "dataflow_migrations",
            "migration_executor",
            "safe_migration_plans",
        )
        workflow.add_connection(
            "migration_executor",
            "execution_results",
            "schema_validator",
            "execution_data",
        )

        # Add conditional auto-migration path
        workflow.add_node(
            "AutoMigrationTriggerNode",
            "auto_trigger",
            {
                "auto_migrate": getattr(dataflow_instance, "auto_migrate", False),
                "development_mode": kwargs.get("development_mode", True),
            },
        )

        workflow.add_connection(
            "model_analyzer", "model_changes", "auto_trigger", "trigger_data"
        )
        workflow.add_connection(
            "auto_trigger",
            "auto_migration_signal",
            "migration_executor",
            "auto_execute_flag",
        )

        self.logger.info(
            "DataFlow integration workflow created with 7 nodes and auto-migration support"
        )
        return workflow

    def _extract_dataflow_config(self, dataflow_instance: DataFlow) -> Dict[str, Any]:
        """Extract relevant configuration from DataFlow instance."""
        return {
            "auto_migrate": getattr(dataflow_instance, "auto_migrate", False),
            "existing_schema_mode": getattr(
                dataflow_instance, "existing_schema_mode", True
            ),
            "database_url": getattr(dataflow_instance, "database_url", ""),
            "connection_pool_size": getattr(dataflow_instance, "pool_size", 10),
        }


class MultiTableEvolutionPattern(E2EWorkflowPattern):
    """
    E2E Pattern 2: Multi-table Schema Evolution

    Demonstrates coordinated changes across FK-related tables with
    complete referential integrity preservation.

    Scenario: Change primary key type from INTEGER to BIGINT across
    multiple related tables with FK references.
    """

    def __init__(self):
        super().__init__(
            "Multi-table Schema Evolution",
            "Coordinated schema changes across FK-related tables",
        )

    async def create_workflow(
        self,
        target_tables: List[str],
        schema_changes: List[SchemaChange],
        coordination_mode: str = "transactional",
        **kwargs,
    ) -> WorkflowBuilder:
        """Create multi-table evolution workflow."""
        workflow = WorkflowBuilder()

        self.logger.info(
            f"Creating multi-table evolution workflow for {len(target_tables)} tables"
        )

        # Node 1: Multi-Table Analyzer - Analyze cross-table dependencies
        workflow.add_node(
            "MultiTableAnalyzerNode",
            "table_analyzer",
            {
                "target_tables": target_tables,
                "schema_changes": [change.to_dict() for change in schema_changes],
                "analyze_fk_chains": True,
                "detect_circular_deps": True,
            },
        )

        # Node 2: FK Chain Mapper - Map complete FK dependency chains
        workflow.add_node(
            "FKChainMapperNode",
            "chain_mapper",
            {
                "max_chain_depth": 10,
                "include_circular_refs": True,
                "optimization_mode": "safety_first",
            },
        )

        # Node 3: Coordination Planner - Plan coordinated execution
        workflow.add_node(
            "CoordinationPlannerNode",
            "coordination_planner",
            {
                "coordination_mode": coordination_mode,
                "transaction_isolation": "SERIALIZABLE",
                "lock_timeout": 300,  # 5 minutes
                "deadlock_detection": True,
            },
        )

        # Node 4: FK Impact Analyzer - Analyze FK impact for all tables
        workflow.add_node(
            "ForeignKeyAnalyzerNode",
            "fk_analyzer",
            {"execution_mode": "multi_table", "coordination_aware": True},
        )

        # Node 5: Multi-Table Migration Executor - Execute coordinated changes
        workflow.add_node(
            "MultiTableMigrationExecutorNode",
            "multi_executor",
            {
                "workflow_id": f"multi_table_{uuid.uuid4().hex[:8]}",
                "coordination_mode": coordination_mode,
                "cross_table_validation": True,
                "atomic_execution": True,
            },
        )

        # Node 6: Cross-Table Validator - Validate changes across all tables
        workflow.add_node(
            "CrossTableValidatorNode",
            "cross_validator",
            {
                "validate_fk_integrity": True,
                "check_data_consistency": True,
                "verify_constraint_restoration": True,
            },
        )

        # Create connections with coordination flow
        workflow.add_connection(
            "table_analyzer", "table_analysis", "chain_mapper", "table_dependencies"
        )
        workflow.add_connection(
            "chain_mapper", "fk_chains", "coordination_planner", "dependency_chains"
        )
        workflow.add_connection(
            "coordination_planner",
            "coordination_plan",
            "fk_analyzer",
            "coordination_context",
        )
        workflow.add_connection(
            "fk_analyzer", "fk_impact_reports", "multi_executor", "coordinated_plans"
        )
        workflow.add_connection(
            "multi_executor",
            "execution_results",
            "cross_validator",
            "multi_table_results",
        )

        # Add emergency rollback path for multi-table operations
        workflow.add_node(
            "MultiTableRollbackNode",
            "multi_rollback",
            {
                "rollback_scope": "all_tables",
                "preserve_relationships": True,
                "emergency_mode": kwargs.get("emergency_mode", False),
            },
        )

        workflow.add_connection(
            "multi_executor", "rollback_trigger", "multi_rollback", "rollback_request"
        )

        self.logger.info(
            "Multi-table evolution workflow created with cross-table coordination"
        )
        return workflow


class ProductionDeploymentPattern(E2EWorkflowPattern):
    """
    E2E Pattern 3: Production Deployment Workflow

    Demonstrates safe production deployment with comprehensive FK preservation,
    zero-downtime capabilities, and complete rollback procedures.
    """

    def __init__(self):
        super().__init__(
            "Production Deployment",
            "Safe production deployment with FK preservation and zero-downtime",
        )

    async def create_workflow(
        self,
        deployment_config: Dict[str, Any],
        migration_plans: List[Dict[str, Any]],
        **kwargs,
    ) -> WorkflowBuilder:
        """Create production deployment workflow."""
        workflow = WorkflowBuilder()

        self.logger.info("Creating production deployment workflow with FK awareness")

        # Node 1: Production Safety Checker - Validate production readiness
        workflow.add_node(
            "ProductionSafetyCheckerNode",
            "safety_checker",
            {
                "deployment_config": deployment_config,
                "check_backup_availability": True,
                "validate_rollback_capability": True,
                "verify_staging_tests": True,
                "check_maintenance_window": True,
            },
        )

        # Node 2: Pre-deployment Backup - Create comprehensive backups
        workflow.add_node(
            "PreDeploymentBackupNode",
            "backup_creator",
            {
                "backup_scope": "full_database",
                "include_constraints": True,
                "backup_verification": True,
                "retention_policy": deployment_config.get("backup_retention", "30d"),
            },
        )

        # Node 3: FK Impact Analyzer - Production-grade FK analysis
        workflow.add_node(
            "ForeignKeyAnalyzerNode",
            "production_fk_analyzer",
            {
                "execution_mode": "production",
                "safety_threshold": 0.95,  # Higher threshold for production
                "comprehensive_analysis": True,
            },
        )

        # Node 4: Zero-Downtime Planner - Plan zero-downtime deployment
        workflow.add_node(
            "ZeroDowntimePlannerNode",
            "downtime_planner",
            {
                "deployment_strategy": deployment_config.get("strategy", "rolling"),
                "connection_draining": True,
                "traffic_redirection": True,
                "health_check_intervals": 30,
            },
        )

        # Node 5: Production Migration Executor - Execute with production safety
        workflow.add_node(
            "ProductionMigrationExecutorNode",
            "production_executor",
            {
                "workflow_id": f"production_{uuid.uuid4().hex[:8]}",
                "production_mode": True,
                "monitoring_enabled": True,
                "automatic_rollback_threshold": 0.1,  # Auto-rollback on 10% error rate
                "health_check_validation": True,
            },
        )

        # Node 6: Production Validator - Comprehensive production validation
        workflow.add_node(
            "ProductionValidatorNode",
            "production_validator",
            {
                "validate_performance": True,
                "check_error_rates": True,
                "verify_fk_integrity": True,
                "monitor_resource_usage": True,
                "validation_duration": 300,  # 5 minutes of validation
            },
        )

        # Node 7: Post-deployment Monitor - Continuous monitoring
        workflow.add_node(
            "PostDeploymentMonitorNode",
            "deployment_monitor",
            {
                "monitoring_duration": 3600,  # 1 hour
                "alert_thresholds": deployment_config.get("alert_thresholds", {}),
                "auto_rollback_enabled": True,
                "success_criteria": deployment_config.get("success_criteria", {}),
            },
        )

        # Create production deployment flow
        workflow.add_connection(
            "safety_checker", "safety_report", "backup_creator", "safety_validation"
        )
        workflow.add_connection(
            "backup_creator",
            "backup_confirmation",
            "production_fk_analyzer",
            "backup_status",
        )
        workflow.add_connection(
            "production_fk_analyzer",
            "fk_impact_reports",
            "downtime_planner",
            "fk_analysis",
        )
        workflow.add_connection(
            "downtime_planner",
            "deployment_plan",
            "production_executor",
            "zero_downtime_plan",
        )
        workflow.add_connection(
            "production_executor",
            "execution_results",
            "production_validator",
            "execution_data",
        )
        workflow.add_connection(
            "production_validator",
            "validation_results",
            "deployment_monitor",
            "validation_status",
        )

        # Add comprehensive rollback system
        workflow.add_node(
            "ProductionRollbackOrchestratorNode",
            "rollback_orchestrator",
            {
                "rollback_triggers": [
                    "validation_failure",
                    "performance_degradation",
                    "error_threshold",
                ],
                "rollback_speed": "fast",
                "data_preservation": "complete",
                "notification_channels": deployment_config.get(
                    "notification_channels", []
                ),
            },
        )

        # Rollback connections from multiple trigger points
        workflow.add_connection(
            "production_executor",
            "rollback_trigger",
            "rollback_orchestrator",
            "executor_rollback",
        )
        workflow.add_connection(
            "production_validator",
            "rollback_trigger",
            "rollback_orchestrator",
            "validator_rollback",
        )
        workflow.add_connection(
            "deployment_monitor",
            "rollback_trigger",
            "rollback_orchestrator",
            "monitor_rollback",
        )

        self.logger.info(
            "Production deployment workflow created with comprehensive safety measures"
        )
        return workflow


class DeveloperExperiencePattern(E2EWorkflowPattern):
    """
    E2E Pattern 4: Developer Experience Workflow

    Demonstrates seamless FK handling in development environment with
    fast feedback loops and developer-friendly error messages.
    """

    def __init__(self):
        super().__init__(
            "Developer Experience",
            "Seamless FK handling in development with fast feedback",
        )

    async def create_workflow(
        self, dev_config: Dict[str, Any], interactive_mode: bool = True, **kwargs
    ) -> WorkflowBuilder:
        """Create developer experience workflow."""
        workflow = WorkflowBuilder()

        self.logger.info("Creating developer experience workflow with FK awareness")

        # Node 1: Dev Environment Detector - Detect development setup
        workflow.add_node(
            "DevEnvironmentDetectorNode",
            "dev_detector",
            {
                "detect_local_database": True,
                "check_test_data": True,
                "verify_development_mode": True,
                "interactive_mode": interactive_mode,
            },
        )

        # Node 2: Fast FK Analyzer - Quick FK analysis for development
        workflow.add_node(
            "FastFKAnalyzerNode",
            "fast_analyzer",
            {
                "quick_analysis_mode": True,
                "skip_performance_intensive_checks": True,
                "focus_on_safety": True,
                "developer_friendly_messages": True,
            },
        )

        # Node 3: Interactive Planner - Interactive migration planning
        workflow.add_node(
            "InteractivePlannerNode",
            "interactive_planner",
            {
                "interactive_mode": interactive_mode,
                "show_impact_preview": True,
                "suggest_alternatives": True,
                "explain_fk_relationships": True,
            },
        )

        # Node 4: Dev Migration Executor - Development-optimized execution
        workflow.add_node(
            "DevMigrationExecutorNode",
            "dev_executor",
            {
                "workflow_id": f"dev_{uuid.uuid4().hex[:8]}",
                "development_mode": True,
                "fast_execution": True,
                "detailed_logging": True,
                "pause_on_warnings": interactive_mode,
            },
        )

        # Node 5: Dev Feedback Provider - Provide developer feedback
        workflow.add_node(
            "DevFeedbackProviderNode",
            "feedback_provider",
            {
                "provide_suggestions": True,
                "show_fk_visualizations": dev_config.get("show_visualizations", True),
                "explain_safety_decisions": True,
                "offer_learning_resources": True,
            },
        )

        # Create development flow with feedback loops
        workflow.add_connection(
            "dev_detector", "dev_environment", "fast_analyzer", "env_context"
        )
        workflow.add_connection(
            "fast_analyzer", "quick_analysis", "interactive_planner", "fk_analysis"
        )
        workflow.add_connection(
            "interactive_planner",
            "interactive_plan",
            "dev_executor",
            "dev_migration_plan",
        )
        workflow.add_connection(
            "dev_executor", "execution_results", "feedback_provider", "execution_data"
        )

        # Add interactive learning path
        workflow.add_node(
            "FKLearningAssistantNode",
            "learning_assistant",
            {
                "provide_fk_education": True,
                "show_best_practices": True,
                "interactive_tutorials": interactive_mode,
                "context_aware_help": True,
            },
        )

        workflow.add_connection(
            "fast_analyzer",
            "learning_opportunities",
            "learning_assistant",
            "learning_context",
        )
        workflow.add_connection(
            "learning_assistant",
            "educational_content",
            "feedback_provider",
            "learning_content",
        )

        # Add quick rollback for experimentation
        workflow.add_node(
            "QuickRollbackNode",
            "quick_rollback",
            {
                "experimental_mode": True,
                "preserve_learning_state": True,
                "fast_recovery": True,
            },
        )

        workflow.add_connection(
            "dev_executor", "experiment_rollback", "quick_rollback", "rollback_request"
        )

        self.logger.info(
            "Developer experience workflow created with interactive features"
        )
        return workflow


class EmergencyRollbackPattern(E2EWorkflowPattern):
    """
    E2E Pattern 5: Emergency Rollback Workflow

    Demonstrates complete system recovery with FK restoration,
    data preservation, and comprehensive system validation.
    """

    def __init__(self):
        super().__init__(
            "Emergency Rollback", "Complete system recovery with FK restoration"
        )

    async def create_workflow(
        self,
        emergency_context: Dict[str, Any],
        rollback_scope: str = "complete",
        **kwargs,
    ) -> WorkflowBuilder:
        """Create emergency rollback workflow."""
        workflow = WorkflowBuilder()

        self.logger.info("Creating emergency rollback workflow")

        # Node 1: Emergency Assessor - Assess emergency situation
        workflow.add_node(
            "EmergencyAssessorNode",
            "emergency_assessor",
            {
                "emergency_context": emergency_context,
                "assess_damage_scope": True,
                "identify_affected_systems": True,
                "prioritize_recovery_actions": True,
            },
        )

        # Node 2: FK State Analyzer - Analyze current FK state
        workflow.add_node(
            "FKStateAnalyzerNode",
            "fk_state_analyzer",
            {
                "analyze_constraint_violations": True,
                "detect_data_inconsistencies": True,
                "identify_orphaned_records": True,
                "emergency_mode": True,
            },
        )

        # Node 3: Rollback Strategy Selector - Select optimal rollback strategy
        workflow.add_node(
            "RollbackStrategySelectorNode",
            "strategy_selector",
            {
                "rollback_scope": rollback_scope,
                "preservation_priority": "data_integrity",
                "speed_vs_safety_balance": "safety_first",
                "multi_phase_rollback": True,
            },
        )

        # Node 4: Emergency Backup Creator - Create emergency backup
        workflow.add_node(
            "EmergencyBackupCreatorNode",
            "emergency_backup",
            {
                "backup_current_state": True,
                "preserve_evidence": True,
                "quick_backup_mode": True,
                "verify_backup_integrity": False,  # Skip verification for speed
            },
        )

        # Node 5: FK Constraint Restorer - Restore FK constraints
        workflow.add_node(
            "FKConstraintRestorerNode",
            "constraint_restorer",
            {
                "restore_all_constraints": True,
                "handle_constraint_conflicts": True,
                "emergency_constraint_fixes": True,
                "data_repair_mode": True,
            },
        )

        # Node 6: Data Integrity Repairer - Repair data integrity issues
        workflow.add_node(
            "DataIntegrityRepairerNode",
            "integrity_repairer",
            {
                "repair_orphaned_records": True,
                "fix_constraint_violations": True,
                "preserve_data_when_possible": True,
                "log_all_repairs": True,
            },
        )

        # Node 7: System Validator - Validate system recovery
        workflow.add_node(
            "SystemValidatorNode",
            "system_validator",
            {
                "comprehensive_validation": True,
                "check_all_constraints": True,
                "verify_data_integrity": True,
                "performance_validation": False,  # Skip for emergency
            },
        )

        # Node 8: Recovery Reporter - Generate recovery report
        workflow.add_node(
            "RecoveryReporterNode",
            "recovery_reporter",
            {
                "generate_detailed_report": True,
                "include_lessons_learned": True,
                "document_data_changes": True,
                "provide_prevention_recommendations": True,
            },
        )

        # Create emergency rollback flow
        workflow.add_connection(
            "emergency_assessor",
            "emergency_assessment",
            "fk_state_analyzer",
            "emergency_context",
        )
        workflow.add_connection(
            "fk_state_analyzer",
            "fk_state_analysis",
            "strategy_selector",
            "current_state",
        )
        workflow.add_connection(
            "strategy_selector",
            "rollback_strategy",
            "emergency_backup",
            "strategy_info",
        )
        workflow.add_connection(
            "emergency_backup",
            "backup_status",
            "constraint_restorer",
            "backup_confirmation",
        )
        workflow.add_connection(
            "constraint_restorer",
            "constraint_status",
            "integrity_repairer",
            "constraint_restoration",
        )
        workflow.add_connection(
            "integrity_repairer", "repair_results", "system_validator", "repair_status"
        )
        workflow.add_connection(
            "system_validator",
            "validation_results",
            "recovery_reporter",
            "validation_status",
        )

        # Add parallel emergency notifications
        workflow.add_node(
            "EmergencyNotifierNode",
            "emergency_notifier",
            {
                "notification_channels": emergency_context.get(
                    "notification_channels", []
                ),
                "escalation_rules": emergency_context.get("escalation_rules", {}),
                "status_updates": True,
                "real_time_notifications": True,
            },
        )

        # Connect notifications to all critical stages
        workflow.add_connection(
            "emergency_assessor",
            "notification_trigger",
            "emergency_notifier",
            "assessment_status",
        )
        workflow.add_connection(
            "constraint_restorer",
            "notification_trigger",
            "emergency_notifier",
            "restoration_status",
        )
        workflow.add_connection(
            "system_validator",
            "notification_trigger",
            "emergency_notifier",
            "validation_status",
        )

        self.logger.info(
            "Emergency rollback workflow created with comprehensive recovery measures"
        )
        return workflow


class E2EWorkflowPatternFactory:
    """Factory for creating E2E workflow patterns."""

    _patterns = {
        "dataflow_integration": DataFlowIntegrationPattern,
        "multi_table_evolution": MultiTableEvolutionPattern,
        "production_deployment": ProductionDeploymentPattern,
        "developer_experience": DeveloperExperiencePattern,
        "emergency_rollback": EmergencyRollbackPattern,
    }

    @classmethod
    def create_pattern(cls, pattern_name: str) -> E2EWorkflowPattern:
        """Create workflow pattern by name."""
        if pattern_name not in cls._patterns:
            raise ValueError(f"Unknown pattern: {pattern_name}")

        return cls._patterns[pattern_name]()

    @classmethod
    def get_available_patterns(cls) -> List[str]:
        """Get list of available pattern names."""
        return list(cls._patterns.keys())

    @classmethod
    def get_pattern_descriptions(cls) -> Dict[str, Dict[str, Any]]:
        """Get descriptions of all patterns."""
        descriptions = {}
        for name, pattern_class in cls._patterns.items():
            pattern_instance = pattern_class()
            descriptions[name] = pattern_instance.get_pattern_description()
        return descriptions


# Demonstration and Usage Functions


async def demonstrate_all_patterns():
    """Demonstrate all 5 E2E workflow patterns."""
    logger.info("Demonstrating all FK-aware E2E workflow patterns")

    factory = E2EWorkflowPatternFactory()

    for pattern_name in factory.get_available_patterns():
        logger.info(f"\n=== Demonstrating {pattern_name} pattern ===")

        pattern = factory.create_pattern(pattern_name)
        description = pattern.get_pattern_description()

        logger.info(f"Pattern: {description['name']}")
        logger.info(f"Description: {description['description']}")
        logger.info(f"SDK Compliance: {description['sdk_compliance']}")
        logger.info(f"Safety Level: {description['safety_level']}")

        # Create and show workflow structure
        try:
            if pattern_name == "dataflow_integration":
                # Mock DataFlow instance for demonstration
                dataflow_instance = type(
                    "MockDataFlow",
                    (),
                    {
                        "auto_migrate": True,
                        "existing_schema_mode": True,
                        "database_url": "postgresql://localhost/test",
                    },
                )()

                workflow = await pattern.create_workflow(
                    dataflow_instance=dataflow_instance,
                    model_changes=[{"model": "Product", "change": "id_type_change"}],
                )
            elif pattern_name == "multi_table_evolution":
                workflow = await pattern.create_workflow(
                    target_tables=["products", "categories", "orders"],
                    schema_changes=[],  # Simplified
                )
            elif pattern_name == "production_deployment":
                workflow = await pattern.create_workflow(
                    deployment_config={
                        "strategy": "rolling",
                        "backup_retention": "30d",
                    },
                    migration_plans=[],
                )
            elif pattern_name == "developer_experience":
                workflow = await pattern.create_workflow(
                    dev_config={"show_visualizations": True}, interactive_mode=True
                )
            elif pattern_name == "emergency_rollback":
                workflow = await pattern.create_workflow(
                    emergency_context={
                        "severity": "critical",
                        "affected_tables": ["products"],
                    },
                    rollback_scope="complete",
                )

            logger.info(f"✅ {pattern_name} workflow created successfully")

        except Exception as e:
            logger.error(f"❌ Failed to create {pattern_name} workflow: {e}")

    logger.info("\n=== All patterns demonstrated ===")


async def create_comprehensive_fk_workflow(
    scenario: str, configuration: Dict[str, Any]
) -> Tuple[WorkflowBuilder, Dict[str, Any]]:
    """
    Create comprehensive FK-aware workflow for any scenario.

    Args:
        scenario: One of the 5 E2E scenario names
        configuration: Scenario-specific configuration

    Returns:
        Tuple of (WorkflowBuilder, execution_metadata)
    """
    factory = E2EWorkflowPatternFactory()

    if scenario not in factory.get_available_patterns():
        raise ValueError(
            f"Unknown scenario: {scenario}. Available: {factory.get_available_patterns()}"
        )

    pattern = factory.create_pattern(scenario)
    workflow = await pattern.create_workflow(**configuration)

    metadata = {
        "scenario": scenario,
        "pattern_description": pattern.get_pattern_description(),
        "workflow_created": datetime.now().isoformat(),
        "configuration": configuration,
        "core_sdk_compliance": True,
        "fk_aware": True,
    }

    return workflow, metadata


if __name__ == "__main__":
    # Demonstrate all patterns
    asyncio.run(demonstrate_all_patterns())
