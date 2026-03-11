"""DataFlow Gateway Integration - Multi-Channel Platform Access.

This module provides unified API/CLI/MCP access to DataFlow functionality
using the Kailash SDK's enterprise gateway patterns.
"""

import asyncio
import logging
from typing import Any, Dict, List, Optional, Union

from nexus import Nexus, create_nexus

from kailash.runtime import AsyncLocalRuntime
from kailash.runtime.local import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder

# Import DataFlow nodes
from .nodes.bulk_create import BulkCreateNode
from .nodes.bulk_delete import BulkDeleteNode
from .nodes.bulk_update import BulkUpdateNode
from .nodes.bulk_upsert import BulkUpsertNode
from .nodes.monitoring_integration import (
    DataFlowComprehensiveMonitoringNode,
    DataFlowDeadlockDetectorNode,
    DataFlowPerformanceAnomalyNode,
    DataFlowTransactionMetricsNode,
)
from .nodes.security_access_control import DataFlowAccessControlNode
from .nodes.security_mfa import DataFlowMFANode
from .nodes.security_threat_detection import DataFlowThreatDetectionNode
from .nodes.transaction_manager import DataFlowTransactionManagerNode
from .nodes.workflow_connection_manager import DataFlowConnectionManager

logger = logging.getLogger(__name__)


class DataFlowGateway:
    """DataFlow Gateway providing unified access to DataFlow functionality.

    This gateway integrates with Kailash SDK's enterprise patterns to provide:
    - REST API endpoints for DataFlow operations
    - CLI commands for DataFlow management
    - MCP tools for AI agent integration
    - Enterprise security and monitoring
    """

    def __init__(
        self,
        name: str = "DataFlow Gateway",
        description: str = "Enterprise DataFlow platform with multi-channel access",
        # Channel configuration
        enable_api: bool = True,
        enable_cli: bool = True,
        enable_mcp: bool = True,
        # Database configuration
        default_database_config: Optional[Dict[str, Any]] = None,
        # Security configuration
        enable_security: bool = True,
        security_config: Optional[Dict[str, Any]] = None,
        # Monitoring configuration
        enable_monitoring: bool = True,
        monitoring_config: Optional[Dict[str, Any]] = None,
        # Performance configuration
        enable_connection_pooling: bool = True,
        pool_config: Optional[Dict[str, Any]] = None,
        **kwargs,
    ):
        """Initialize DataFlow Gateway."""
        self.name = name
        self.description = description
        self.default_database_config = default_database_config or {}
        self.security_config = security_config or {}
        self.monitoring_config = monitoring_config or {}
        self.pool_config = pool_config or {}

        # Channel settings
        self.enable_api = enable_api
        self.enable_cli = enable_cli
        self.enable_mcp = enable_mcp
        self.enable_security = enable_security
        self.enable_monitoring = enable_monitoring
        self.enable_connection_pooling = enable_connection_pooling

        # Initialize runtime - detect async context
        try:
            asyncio.get_running_loop()
            # Running in async context - use AsyncLocalRuntime
            self.runtime = AsyncLocalRuntime()
            self._is_async = True
            logger.debug(
                "DataFlowGateway: Detected async context, using AsyncLocalRuntime"
            )
        except RuntimeError:
            # No event loop - use sync LocalRuntime
            self.runtime = LocalRuntime()
            self._is_async = False
            logger.debug("DataFlowGateway: Detected sync context, using LocalRuntime")

        # Pre-configured workflows
        self.workflows = {}

        # Initialize gateway
        self.nexus = None
        self._initialize_workflows()

    def _initialize_workflows(self):
        """Initialize pre-configured DataFlow workflows."""
        # Bulk Operations Workflows
        self.workflows.update(
            {
                "bulk_create_workflow": self._create_bulk_create_workflow(),
                "bulk_update_workflow": self._create_bulk_update_workflow(),
                "bulk_upsert_workflow": self._create_bulk_upsert_workflow(),
                "bulk_delete_workflow": self._create_bulk_delete_workflow(),
            }
        )

        # Enterprise Workflows
        if self.enable_security:
            self.workflows.update(
                {
                    "secure_bulk_workflow": self._create_secure_bulk_workflow(),
                    "audit_workflow": self._create_audit_workflow(),
                }
            )

        if self.enable_monitoring:
            self.workflows.update(
                {
                    "monitoring_workflow": self._create_monitoring_workflow(),
                    "performance_analysis_workflow": self._create_performance_analysis_workflow(),
                }
            )

        # Transaction Management Workflows
        self.workflows.update(
            {
                "distributed_transaction_workflow": self._create_distributed_transaction_workflow(),
                "saga_workflow": self._create_saga_workflow(),
            }
        )

    def _create_bulk_create_workflow(self) -> Dict[str, Any]:
        """Create workflow for bulk create operations."""
        workflow = WorkflowBuilder()

        # Connection pool setup
        if self.enable_connection_pooling:
            workflow.add_node(
                "DataFlowConnectionManager",
                "connection_pool",
                {**self.default_database_config, **self.pool_config},
            )

        # Bulk create operation - provide placeholder values for validation
        bulk_create_config = {
            "table_name": "example_table",  # Placeholder for validation
            "data": [{"example": "data"}],  # Required parameter placeholder
            "batch_size": 1000,
            "conflict_resolution": "error",
            "auto_timestamps": True,
            "multi_tenant": False,
        }

        if self.enable_connection_pooling:
            bulk_create_config["connection_pool_id"] = "connection_pool"
        else:
            bulk_create_config.update(self.default_database_config)

        workflow.add_node("BulkCreateNode", "bulk_create", bulk_create_config)

        # Monitoring
        if self.enable_monitoring:
            workflow.add_node(
                "DataFlowTransactionMetricsNode",
                "metrics",
                {
                    "operation_type": "bulk_create",
                    "transaction_data": {
                        "example": "transaction"
                    },  # Required parameter placeholder
                    **self.monitoring_config,
                },
            )
            workflow.add_connection("bulk_create", "output", "metrics", "input")

        return {
            "workflow": workflow.build(),
            "description": "High-performance bulk create operations with enterprise features",
            "parameters": {
                "table_name": {"type": "string", "required": True},
                "data": {"type": "array", "required": True},
                "batch_size": {"type": "integer", "default": 1000},
                "conflict_resolution": {"type": "string", "default": "error"},
                "auto_timestamps": {"type": "boolean", "default": True},
                "multi_tenant": {"type": "boolean", "default": False},
                "tenant_id": {"type": "string", "required": False},
                "return_ids": {"type": "boolean", "default": False},
            },
        }

    def _create_bulk_update_workflow(self) -> Dict[str, Any]:
        """Create workflow for bulk update operations."""
        workflow = WorkflowBuilder()

        # Connection pool setup
        if self.enable_connection_pooling:
            workflow.add_node(
                "DataFlowConnectionManager",
                "connection_pool",
                {**self.default_database_config, **self.pool_config},
            )

        # Bulk update operation - provide placeholder values for validation
        bulk_update_config = {
            "table_name": "example_table",  # Placeholder for validation
            "filter": {"id": {"$gt": 0}},  # Required parameter placeholder
            "data": {"example": "update"},  # Required parameter placeholder
            "batch_size": 1000,
            "auto_timestamps": True,
            "multi_tenant": False,
            "version_control": False,
        }

        if self.enable_connection_pooling:
            bulk_update_config["connection_pool_id"] = "connection_pool"
        else:
            bulk_update_config.update(self.default_database_config)

        workflow.add_node("BulkUpdateNode", "bulk_update", bulk_update_config)

        # Deadlock detection for updates
        if self.enable_monitoring:
            workflow.add_node(
                "DataFlowDeadlockDetectorNode",
                "deadlock_detector",
                {
                    "operation_data": {
                        "example": "deadlock_monitoring"
                    },  # Required parameter placeholder
                    "database_config": self.default_database_config
                    or {"example": "db_config"},
                    **self.monitoring_config,
                },
            )
            workflow.add_connection(
                "bulk_update", "output", "deadlock_detector", "input"
            )

        return {
            "workflow": workflow.build(),
            "description": "High-performance bulk update operations with deadlock detection",
            "parameters": {
                "table_name": {"type": "string", "required": True},
                "filter": {"type": "object", "required": False},
                "ids": {"type": "array", "required": False},
                "data": {"type": "array", "required": False},
                "update_fields": {"type": "object", "required": False},
                "batch_size": {"type": "integer", "default": 1000},
                "auto_timestamps": {"type": "boolean", "default": True},
                "version_control": {"type": "boolean", "default": False},
                "return_updated": {"type": "boolean", "default": False},
            },
        }

    def _create_bulk_upsert_workflow(self) -> Dict[str, Any]:
        """Create workflow for bulk upsert operations."""
        workflow = WorkflowBuilder()

        # Connection pool setup
        if self.enable_connection_pooling:
            workflow.add_node(
                "DataFlowConnectionManager",
                "connection_pool",
                {**self.default_database_config, **self.pool_config},
            )

        # Bulk upsert operation - provide placeholder values for validation
        bulk_upsert_config = {
            "table_name": "example_table",  # Placeholder for validation
            "data": [{"example": "data"}],  # Required parameter placeholder
            "batch_size": 1000,
            "merge_strategy": "update",
            "conflict_columns": ["email"],
            "auto_timestamps": True,
            "version_control": False,
        }

        if self.enable_connection_pooling:
            bulk_upsert_config["connection_pool_id"] = "connection_pool"
        else:
            bulk_upsert_config.update(self.default_database_config)

        workflow.add_node("BulkUpsertNode", "bulk_upsert", bulk_upsert_config)

        return {
            "workflow": workflow.build(),
            "description": "High-performance bulk upsert operations with conflict resolution",
            "parameters": {
                "table_name": {"type": "string", "required": True},
                "data": {"type": "array", "required": True},
                "batch_size": {"type": "integer", "default": 1000},
                "merge_strategy": {"type": "string", "default": "update"},
                "conflict_columns": {"type": "array", "default": ["email"]},
                "auto_timestamps": {"type": "boolean", "default": True},
                "version_control": {"type": "boolean", "default": False},
                "return_records": {"type": "boolean", "default": False},
            },
        }

    def _create_bulk_delete_workflow(self) -> Dict[str, Any]:
        """Create workflow for bulk delete operations."""
        workflow = WorkflowBuilder()

        # Connection pool setup
        if self.enable_connection_pooling:
            workflow.add_node(
                "DataFlowConnectionManager",
                "connection_pool",
                {**self.default_database_config, **self.pool_config},
            )

        # Bulk delete operation - provide placeholder values for validation
        bulk_delete_config = {
            "table_name": "example_table",  # Placeholder for validation
            "filter": {"deleted": True},  # Required parameter placeholder
            "batch_size": 1000,
            "soft_delete": False,
            "safe_mode": True,
            "archive_before_delete": False,
        }

        if self.enable_connection_pooling:
            bulk_delete_config["connection_pool_id"] = "connection_pool"
        else:
            bulk_delete_config.update(self.default_database_config)

        workflow.add_node("BulkDeleteNode", "bulk_delete", bulk_delete_config)

        return {
            "workflow": workflow.build(),
            "description": "Secure bulk delete operations with safety checks",
            "parameters": {
                "table_name": {"type": "string", "required": True},
                "filter": {"type": "object", "required": False},
                "ids": {"type": "array", "required": False},
                "batch_size": {"type": "integer", "default": 1000},
                "soft_delete": {"type": "boolean", "default": False},
                "safe_mode": {"type": "boolean", "default": True},
                "archive_before_delete": {"type": "boolean", "default": False},
                "confirmed": {"type": "boolean", "default": False},
                "return_deleted": {"type": "boolean", "default": False},
            },
        }

    def _create_secure_bulk_workflow(self) -> Dict[str, Any]:
        """Create workflow with full security integration."""
        workflow = WorkflowBuilder()

        # Security chain - provide placeholder values for validation
        workflow.add_node(
            "DataFlowAccessControlNode",
            "access_control",
            {
                "user_id": "example_user",  # Required parameter placeholder
                "resource": "dataflow_operations",  # Required parameter placeholder
                "action": "bulk_operation",  # Required parameter placeholder
                "user_credentials": {
                    "user": "example_user"
                },  # Required parameter placeholder
                "rbac_enabled": True,
                "required_roles": ["dataflow_user"],
                **self.security_config,
            },
        )

        workflow.add_node(
            "DataFlowMFANode",
            "mfa_check",
            {
                "user_id": "example_user",  # Required parameter placeholder
                "user_credentials": {
                    "user": "example_user"
                },  # Required parameter placeholder
                "require_mfa": True,
                **self.security_config,
            },
        )

        workflow.add_node(
            "DataFlowThreatDetectionNode",
            "threat_detection",
            {
                "user_id": "example_user",  # Required parameter placeholder
                "operation": "bulk_create",  # Required parameter placeholder
                "request_data": {
                    "example": "request"
                },  # Required parameter placeholder
                "enable_sql_injection_detection": True,
                "enable_rate_limiting": True,
                **self.security_config,
            },
        )

        # Connection pool
        if self.enable_connection_pooling:
            workflow.add_node(
                "DataFlowConnectionManager",
                "connection_pool",
                {**self.default_database_config, **self.pool_config},
            )

        # Secure bulk operation (configurable) - provide placeholder values for validation
        secure_bulk_config = {
            "table_name": "example_table",  # Placeholder for validation
            "data": [{"example": "data"}],  # Required parameter placeholder
            "operation_type": "create",  # Placeholder for validation
            "batch_size": 1000,
            "audit_enabled": True,
        }

        if self.enable_connection_pooling:
            secure_bulk_config["connection_pool_id"] = "connection_pool"
        else:
            secure_bulk_config.update(self.default_database_config)

        # Use appropriate bulk node based on operation_type
        workflow.add_node("BulkCreateNode", "secure_bulk_operation", secure_bulk_config)

        # Create security chain
        workflow.add_connection("access_control", "output", "mfa_check", "input")
        workflow.add_connection("mfa_check", "output", "threat_detection", "input")
        workflow.add_connection(
            "threat_detection", "output", "secure_bulk_operation", "input"
        )

        return {
            "workflow": workflow.build(),
            "description": "Enterprise-secure bulk operations with full security chain",
            "parameters": {
                "table_name": {"type": "string", "required": True},
                "operation_type": {"type": "string", "required": True},
                "data": {"type": "array", "required": True},
                "user_credentials": {"type": "object", "required": True},
                "mfa_token": {"type": "string", "required": False},
                "batch_size": {"type": "integer", "default": 1000},
            },
        }

    def _create_monitoring_workflow(self) -> Dict[str, Any]:
        """Create comprehensive monitoring workflow."""
        workflow = WorkflowBuilder()

        # Comprehensive monitoring - provide placeholder values for validation
        workflow.add_node(
            "DataFlowComprehensiveMonitoringNode",
            "comprehensive_monitoring",
            {
                "operation_data": {
                    "example": "monitoring_data"
                },  # Required parameter placeholder
                "database_config": {
                    "example": "db_config"
                },  # Required parameter placeholder
                **self.monitoring_config,
                "enable_transaction_metrics": True,
                "enable_deadlock_detection": True,
                "enable_anomaly_detection": True,
            },
        )

        return {
            "workflow": workflow.build(),
            "description": "Comprehensive DataFlow monitoring and analytics",
            "parameters": {
                "operation_data": {"type": "object", "required": True},
                "database_config": {"type": "object", "required": True},
                "monitoring_config": {"type": "object", "required": False},
            },
        }

    def _create_performance_analysis_workflow(self) -> Dict[str, Any]:
        """Create performance analysis workflow."""
        workflow = WorkflowBuilder()

        # Performance anomaly detection - provide placeholder values for validation
        workflow.add_node(
            "DataFlowPerformanceAnomalyNode",
            "anomaly_detection",
            {
                "performance_data": {
                    "example": "performance_metrics"
                },  # Required parameter placeholder
                **self.monitoring_config,
            },
        )

        # Transaction metrics
        workflow.add_node(
            "DataFlowTransactionMetricsNode",
            "metrics_analysis",
            {
                "operation_type": "performance_analysis",
                "transaction_data": {
                    "example": "performance_data"
                },  # Required parameter placeholder
                **self.monitoring_config,
            },
        )

        workflow.add_connection(
            "anomaly_detection", "output", "metrics_analysis", "input"
        )

        return {
            "workflow": workflow.build(),
            "description": "Advanced performance analysis and anomaly detection",
            "parameters": {
                "performance_data": {"type": "object", "required": True},
                "baseline_metrics": {"type": "object", "required": False},
                "anomaly_threshold": {"type": "number", "default": 2.0},
            },
        }

    def _create_distributed_transaction_workflow(self) -> Dict[str, Any]:
        """Create distributed transaction workflow."""
        workflow = WorkflowBuilder()

        # Transaction coordinator - provide placeholder values for validation
        workflow.add_node(
            "DataFlowTransactionManagerNode",
            "transaction_manager",
            {
                "operations": [
                    {"example": "operation"}
                ],  # Required parameter placeholder
                "transaction_type": "saga",
                "timeout_seconds": 30,
                "retry_attempts": 3,
            },
        )

        return {
            "workflow": workflow.build(),
            "description": "Distributed transaction management with compensation logic",
            "parameters": {
                "transaction_type": {"type": "string", "default": "saga"},
                "operations": {"type": "array", "required": True},
                "timeout_seconds": {"type": "integer", "default": 30},
                "retry_attempts": {"type": "integer", "default": 3},
            },
        }

    def _create_saga_workflow(self) -> Dict[str, Any]:
        """Create Saga pattern workflow using the main transaction manager."""
        workflow = WorkflowBuilder()

        # Use the main transaction manager with saga configuration - provide placeholder values for validation
        workflow.add_node(
            "DataFlowTransactionManagerNode",
            "saga_coordinator",
            {
                "operations": [
                    {"example": "operation"}
                ],  # Required parameter placeholder
                "saga_steps": [{"example": "step"}],  # Required parameter placeholder
                "compensation_steps": [
                    {"example": "compensation"}
                ],  # Required parameter placeholder
                "transaction_type": "saga",
                "timeout_seconds": 30,
                "enable_compensation": True,
                "auto_rollback": True,
            },
        )

        return {
            "workflow": workflow.build(),
            "description": "Saga pattern implementation for distributed transactions",
            "parameters": {
                "saga_steps": {"type": "array", "required": True},
                "compensation_steps": {"type": "array", "required": True},
                "timeout_seconds": {"type": "integer", "default": 30},
                "auto_rollback": {"type": "boolean", "default": True},
            },
        }

    def _create_audit_workflow(self) -> Dict[str, Any]:
        """Create audit and compliance workflow."""
        workflow = WorkflowBuilder()

        # Access control check - provide placeholder values for validation
        workflow.add_node(
            "DataFlowAccessControlNode",
            "audit_access_control",
            {
                "user_id": "example_user",  # Required parameter placeholder
                "resource": "audit_operations",  # Required parameter placeholder
                "action": "audit_log",  # Required parameter placeholder
                "operation_details": {
                    "example": "audit_operation"
                },  # Required parameter placeholder
                "user_context": {
                    "user": "example_user"
                },  # Required parameter placeholder
                "audit_mode": True,
                "log_all_access": True,
                **self.security_config,
            },
        )

        return {
            "workflow": workflow.build(),
            "description": "Audit and compliance monitoring for DataFlow operations",
            "parameters": {
                "operation_details": {"type": "object", "required": True},
                "user_context": {"type": "object", "required": True},
                "audit_level": {"type": "string", "default": "standard"},
            },
        }

    async def create_nexus_gateway(self, **nexus_kwargs) -> Any:
        """Create and configure the Nexus gateway."""
        # Merge default configuration with provided kwargs
        base_config = {
            "enable_api": self.enable_api,
            "enable_cli": self.enable_cli,
            "enable_mcp": self.enable_mcp,
            **nexus_kwargs,
        }

        # Filter out parameters that Nexus doesn't accept
        valid_nexus_params = {
            "api_port",
            "mcp_port",
            "enable_auth",
            "enable_monitoring",
            "rate_limit",
            "auto_discovery",
        }
        nexus_config = {k: v for k, v in base_config.items() if k in valid_nexus_params}

        # Create Nexus gateway
        self.nexus = Nexus(**nexus_config)

        # Register workflows after creation
        for name, workflow_info in self.workflows.items():
            # Extract the actual workflow from the info dict
            if isinstance(workflow_info, dict) and "workflow" in workflow_info:
                actual_workflow = workflow_info["workflow"]
            else:
                actual_workflow = workflow_info
            self.nexus.register(name, actual_workflow)

        logger.info(
            f"DataFlow Gateway '{self.name}' created with {len(self.workflows)} workflows"
        )
        logger.info(
            f"Channels enabled: API={self.enable_api}, CLI={self.enable_cli}, MCP={self.enable_mcp}"
        )

        return self.nexus

    async def start(self, **kwargs) -> None:
        """Start the DataFlow gateway."""
        if not self.nexus:
            await self.create_nexus_gateway(**kwargs)

        logger.info(f"Starting DataFlow Gateway: {self.name}")
        await self.nexus.start()

    async def stop(self) -> None:
        """Stop the DataFlow gateway."""
        if self.nexus:
            logger.info(f"Stopping DataFlow Gateway: {self.name}")
            await self.nexus.stop()

    def get_workflow_info(self) -> Dict[str, Any]:
        """Get information about available workflows."""
        workflow_info = {}
        for name, workflow_def in self.workflows.items():
            workflow_info[name] = {
                "description": workflow_def.get("description", ""),
                "parameters": workflow_def.get("parameters", {}),
                "enterprise_features": {
                    "security_enabled": self.enable_security,
                    "monitoring_enabled": self.enable_monitoring,
                    "connection_pooling": self.enable_connection_pooling,
                },
            }
        return workflow_info

    def get_gateway_status(self) -> Dict[str, Any]:
        """Get gateway status information."""
        return {
            "name": self.name,
            "description": self.description,
            "channels": {
                "api_enabled": self.enable_api,
                "cli_enabled": self.enable_cli,
                "mcp_enabled": self.enable_mcp,
            },
            "enterprise_features": {
                "security_enabled": self.enable_security,
                "monitoring_enabled": self.enable_monitoring,
                "connection_pooling": self.enable_connection_pooling,
            },
            "workflows_available": len(self.workflows),
            "status": "running" if self.nexus else "not_started",
        }


def create_dataflow_gateway(
    # Basic configuration
    name: str = "DataFlow Enterprise Gateway",
    description: str = "High-performance database operations with enterprise features",
    # Database configuration
    database_type: str = "postgresql",
    connection_string: Optional[str] = None,
    # Channel configuration
    enable_api: bool = True,
    enable_cli: bool = True,
    enable_mcp: bool = True,
    # Enterprise features
    enable_security: bool = True,
    enable_monitoring: bool = True,
    enable_connection_pooling: bool = True,
    # Performance configuration
    default_batch_size: int = 1000,
    max_connections: int = 20,
    # Security configuration
    require_authentication: bool = True,
    enable_audit_logging: bool = True,
    # Monitoring configuration
    enable_performance_tracking: bool = True,
    enable_anomaly_detection: bool = True,
    # Custom configuration
    **kwargs,
) -> DataFlowGateway:
    """Create a DataFlow Gateway with enterprise defaults.

    This is the main entry point for creating a DataFlow gateway that provides
    unified API/CLI/MCP access to DataFlow functionality with enterprise features.

    Args:
        name: Gateway name
        description: Gateway description
        database_type: Database type (postgresql, mysql, sqlite)
        connection_string: Database connection string
        enable_api: Enable REST API access
        enable_cli: Enable CLI access
        enable_mcp: Enable MCP (Model Context Protocol) access
        enable_security: Enable enterprise security features
        enable_monitoring: Enable monitoring and analytics
        enable_connection_pooling: Enable connection pooling
        default_batch_size: Default batch size for bulk operations
        max_connections: Maximum database connections
        require_authentication: Require authentication for operations
        enable_audit_logging: Enable audit logging
        enable_performance_tracking: Enable performance tracking
        enable_anomaly_detection: Enable anomaly detection
        **kwargs: Additional configuration options

    Returns:
        DataFlowGateway: Configured DataFlow gateway instance

    Example:
        >>> # Create enterprise gateway
        >>> gateway = create_dataflow_gateway(
        ...     name="Production DataFlow",
        ...     connection_string="postgresql://user:pass@localhost/db",
        ...     enable_security=True,
        ...     enable_monitoring=True
        ... )
        >>>
        >>> # Start the gateway
        >>> await gateway.start()
    """
    # Build database configuration
    database_config = {
        "database_type": database_type,
    }
    if connection_string:
        database_config["connection_string"] = connection_string

    # Build security configuration
    security_config = {
        "require_authentication": require_authentication,
        "enable_audit_logging": enable_audit_logging,
    }

    # Build monitoring configuration
    monitoring_config = {
        "enable_performance_tracking": enable_performance_tracking,
        "enable_anomaly_detection": enable_anomaly_detection,
        "performance_thresholds": {
            "min_records_per_second": default_batch_size / 2,
            "min_success_rate": 0.95,
            "max_duration": 60.0,
        },
    }

    # Build pool configuration
    pool_config = {
        "max_connections": max_connections,
        "min_connections": max(2, max_connections // 4),
        "pool_pre_ping": True,
        "pool_recycle": 3600,
    }

    # Create gateway
    gateway = DataFlowGateway(
        name=name,
        description=description,
        enable_api=enable_api,
        enable_cli=enable_cli,
        enable_mcp=enable_mcp,
        default_database_config=database_config,
        enable_security=enable_security,
        security_config=security_config,
        enable_monitoring=enable_monitoring,
        monitoring_config=monitoring_config,
        enable_connection_pooling=enable_connection_pooling,
        pool_config=pool_config,
        **kwargs,
    )

    return gateway


# Export main classes and functions
__all__ = ["DataFlowGateway", "create_dataflow_gateway"]
