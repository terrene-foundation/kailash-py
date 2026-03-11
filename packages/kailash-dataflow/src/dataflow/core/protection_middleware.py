"""
DataFlow Protection Middleware

Integrates write protection with DataFlow's workflow execution system.
Provides runtime enforcement through node execution interception.
"""

import logging
from functools import wraps
from typing import Any, Dict, Optional, Type

from kailash.nodes.base import Node
from kailash.runtime.local import LocalRuntime
from kailash.workflow.graph import Workflow

from .protection import (
    OperationType,
    ProtectionViolation,
    WriteProtectionConfig,
    WriteProtectionEngine,
)

logger = logging.getLogger(__name__)


class ProtectedDataFlowRuntime(LocalRuntime):
    """
    Extended LocalRuntime with write protection enforcement.

    This runtime intercepts node execution to enforce protection rules
    before any database operations are performed.
    """

    def __init__(self, protection_config: WriteProtectionConfig, **kwargs):
        super().__init__(**kwargs)
        self.protection_engine = WriteProtectionEngine(protection_config)

    def execute(self, workflow, task_manager=None, parameters=None):
        """Override execute to handle ProtectionViolations specially."""
        # Call parent execute which returns (results, run_id)
        results, run_id = super().execute(workflow, task_manager, parameters)

        # Check results for protection violations
        for node_id, node_result in results.items():
            if isinstance(node_result, dict):
                # Check if this node failed with a protection violation
                error_msg = node_result.get("error", "")
                error_type = node_result.get("error_type", "")
                failed = node_result.get("failed", False)

                if failed and (
                    "Global protection blocks" in error_msg
                    or "Model protection blocks" in error_msg
                    or "Connection protection blocks" in error_msg
                    or "Field protection blocks" in error_msg
                ):

                    # Extract operation from message
                    operation_type = OperationType.CREATE  # Default
                    if "create" in error_msg.lower():
                        operation_type = OperationType.CREATE
                    elif "update" in error_msg.lower():
                        operation_type = OperationType.UPDATE
                    elif "delete" in error_msg.lower():
                        operation_type = OperationType.DELETE
                    elif "read" in error_msg.lower():
                        operation_type = OperationType.READ

                    # Create and raise ProtectionViolation
                    violation = ProtectionViolation(
                        message=error_msg,
                        operation=operation_type,
                        level=self.protection_engine.config.global_protection.protection_level,
                    )
                    logger.error(
                        f"Protection violation detected in results: {violation}"
                    )
                    raise violation

        return results, run_id


class DataFlowProtectionMixin:
    """
    Mixin for DataFlow to add write protection capabilities.

    This mixin extends the DataFlow class with protection features
    without requiring inheritance changes.
    """

    def __init__(
        self, *args, protection_config: Optional[WriteProtectionConfig] = None, **kwargs
    ):
        super().__init__(*args, **kwargs)
        self._protection_config = protection_config or WriteProtectionConfig()
        self._protection_engine = WriteProtectionEngine(self._protection_config)

    def set_protection_config(self, config: WriteProtectionConfig):
        """Update the protection configuration."""
        self._protection_config = config
        self._protection_engine = WriteProtectionEngine(config)

    def add_model_protection(self, model_name: str, **protection_kwargs):
        """Add protection for a specific model."""
        from .protection import ModelProtection

        protection = ModelProtection(model_name=model_name, **protection_kwargs)
        self._protection_config.model_protections.append(protection)
        self._protection_engine = WriteProtectionEngine(self._protection_config)

    def add_field_protection(
        self, model_name: str, field_name: str, **protection_kwargs
    ):
        """Add protection for a specific field."""
        from .protection import FieldProtection

        # Find or create model protection
        model_protection = None
        for prot in self._protection_config.model_protections:
            if prot.model_name == model_name:
                model_protection = prot
                break

        if not model_protection:
            from .protection import ModelProtection

            model_protection = ModelProtection(model_name=model_name)
            self._protection_config.model_protections.append(model_protection)

        # Add field protection
        field_protection = FieldProtection(field_name=field_name, **protection_kwargs)
        model_protection.protected_fields.append(field_protection)
        self._protection_engine = WriteProtectionEngine(self._protection_config)

    def enable_read_only_mode(self, reason: str = "Read-only mode enabled"):
        """Enable global read-only mode."""
        config = WriteProtectionConfig.read_only_global(reason)
        self.set_protection_config(config)

    def enable_business_hours_protection(self, start_hour: int = 9, end_hour: int = 17):
        """Enable business hours protection."""
        config = WriteProtectionConfig.business_hours_protection(start_hour, end_hour)
        self.set_protection_config(config)

    def get_protection_audit_log(self) -> list:
        """Get the protection audit log."""
        return self._protection_config.auditor.events

    def create_protected_runtime(self, **runtime_kwargs) -> ProtectedDataFlowRuntime:
        """Create a runtime with protection enforcement."""
        return ProtectedDataFlowRuntime(
            protection_config=self._protection_config, **runtime_kwargs
        )


def protect_dataflow_node(original_class: Type[Node]) -> Type[Node]:
    """
    Decorator to add protection checks to DataFlow-generated nodes.

    This decorator wraps the run method of generated nodes to
    perform protection checks before database operations.
    """

    class ProtectedNode(original_class):
        def run(self, **kwargs) -> Dict[str, Any]:
            """Override run to add protection checks."""
            logger.debug(f"ProtectedNode.run called for {self.__class__.__name__}")
            logger.debug(f"Has dataflow_instance: {hasattr(self, 'dataflow_instance')}")

            # Get protection engine from DataFlow instance
            if hasattr(self, "dataflow_instance"):
                df = self.dataflow_instance
                logger.debug(
                    f"Has _protection_engine: {hasattr(df, '_protection_engine')}"
                )

                if hasattr(df, "_protection_engine"):
                    protection_engine = df._protection_engine
                    logger.debug(
                        f"Protection engine found: {protection_engine is not None}"
                    )

                    # Only check if protection engine is actually enabled
                    if protection_engine is not None:
                        # Detect operation from node class name
                        class_name = self.__class__.__name__
                        operation = "unknown"
                        if "Create" in class_name:
                            operation = "create"
                        elif "Update" in class_name:
                            operation = "update"
                        elif "Delete" in class_name:
                            operation = "delete"
                        elif "Read" in class_name or "List" in class_name:
                            operation = "read"

                        # Extract model name from class name (e.g., "TestUserCreateNode" -> "TestUser")
                        model_name = getattr(self, "model_name", None)
                        if not model_name and "Node" in class_name:
                            # Remove operation suffix and "Node"
                            for op in [
                                "Create",
                                "Update",
                                "Delete",
                                "Read",
                                "List",
                                "BulkCreate",
                                "BulkUpdate",
                                "BulkDelete",
                                "BulkUpsert",
                            ]:
                                if op + "Node" in class_name:
                                    model_name = class_name.replace(op + "Node", "")
                                    break

                        # Extract context
                        context = {
                            "node_id": getattr(self, "node_id", "unknown"),
                            "model_fields": getattr(self, "model_fields", {}),
                            "inputs": kwargs,
                        }

                        # Get connection string
                        connection_string = kwargs.get("database_url")
                        if not connection_string and hasattr(self, "dataflow_instance"):
                            df = self.dataflow_instance
                            if hasattr(df, "database_url"):
                                connection_string = df.database_url

                        # Perform protection check
                        try:
                            protection_engine.check_operation(
                                operation=operation,
                                model_name=model_name,
                                connection_string=connection_string,
                                context=context,
                            )
                        except ProtectionViolation as e:
                            logger.error(
                                f"Protection violation in node {getattr(self, 'node_id', 'unknown')}: {e}"
                            )
                            raise

            # Execute original method if protection passes
            return super().run(**kwargs)

    # Preserve class metadata
    ProtectedNode.__name__ = original_class.__name__
    ProtectedNode.__qualname__ = original_class.__qualname__
    ProtectedNode.__module__ = original_class.__module__

    return ProtectedNode


class AsyncSQLProtectionWrapper:
    """
    Wrapper for AsyncSQLDatabaseNode to add write protection.

    This wrapper intercepts AsyncSQLDatabaseNode creation and execution
    to enforce write protection at the lowest level.
    """

    def __init__(self, protection_engine: WriteProtectionEngine):
        self.protection_engine = protection_engine

    def wrap_async_sql_node(self, node_class: Type):
        """Wrap AsyncSQLDatabaseNode with protection checks."""
        original_execute = node_class.execute
        protection_engine = self.protection_engine  # Capture in closure
        detect_operation = self._detect_operation_from_sql  # Capture in closure

        @wraps(original_execute)
        def protected_execute(node_self, **kwargs):
            # Analyze SQL to determine operation type
            query = kwargs.get("query", "")
            operation = detect_operation(query)  # Use captured function

            # Extract connection information
            connection_string = kwargs.get("connection_string", "")

            # Check protection
            try:
                protection_engine.check_operation(  # Use captured engine
                    operation=operation,
                    connection_string=connection_string,
                    context={"query": query, "params": kwargs.get("params", {})},
                )
            except ProtectionViolation:
                raise

            # Execute if protection passes
            return original_execute(node_self, **kwargs)

        node_class.execute = protected_execute
        return node_class

    def _detect_operation_from_sql(self, query: str) -> str:
        """Detect operation type from SQL query."""
        query = query.strip().upper()

        if query.startswith("SELECT") or query.startswith("WITH"):
            return "read"
        elif query.startswith("INSERT"):
            return "create"
        elif query.startswith("UPDATE"):
            return "update"
        elif query.startswith("DELETE"):
            return "delete"
        elif any(query.startswith(stmt) for stmt in ["CREATE", "ALTER", "DROP"]):
            return "custom_query"
        else:
            return "custom_query"
