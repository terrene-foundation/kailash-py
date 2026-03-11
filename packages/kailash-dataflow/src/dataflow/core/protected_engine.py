"""
Protected DataFlow Engine

Extended DataFlow engine with comprehensive write protection capabilities.
Seamlessly integrates protection with existing DataFlow patterns.
"""

import logging
from typing import Any, Dict, Optional, Type

from .engine import DataFlow
from .nodes import NodeGenerator
from .protection import WriteProtectionConfig, WriteProtectionEngine
from .protection_middleware import (
    AsyncSQLProtectionWrapper,
    DataFlowProtectionMixin,
    ProtectedDataFlowRuntime,
)

logger = logging.getLogger(__name__)


class ProtectedNodeGenerator(NodeGenerator):
    """
    Enhanced NodeGenerator that creates protection-aware nodes.

    This generator wraps all generated nodes with protection checks
    while maintaining full compatibility with the existing API.
    """

    def __init__(self, dataflow_instance):
        super().__init__(dataflow_instance)
        self.protection_engine = getattr(dataflow_instance, "_protection_engine", None)

    def _create_node_class(
        self, model_name: str, operation: str, fields: Dict[str, Any]
    ) -> Type:
        """Override to create protection-aware nodes."""
        # Get the base node class from parent
        base_node_class = super()._create_node_class(model_name, operation, fields)

        # Wrap with protection if protection engine is available
        if self.protection_engine:
            from .protection_middleware import protect_dataflow_node

            return protect_dataflow_node(base_node_class)

        return base_node_class


class ProtectedDataFlow(DataFlowProtectionMixin, DataFlow):
    """
    Enhanced DataFlow with comprehensive write protection.

    This class extends the standard DataFlow with multi-level write protection
    while maintaining 100% API compatibility for existing code.

    Features:
    - Global protection (entire DataFlow instance)
    - Connection-level protection (database URL patterns)
    - Model-level protection (specific models)
    - Operation-level protection (CRUD operations)
    - Field-level protection (specific fields)
    - Time-based protection (business hours, maintenance windows)
    - Dynamic protection (context-aware rules)
    - Comprehensive audit logging

    Example:
        # Basic usage - identical to DataFlow
        db = ProtectedDataFlow("postgresql://user:pass@host/db")

        # Add protection
        db.enable_read_only_mode("Maintenance in progress")

        # Model-specific protection
        db.add_model_protection("User", allowed_operations={OperationType.READ})

        # Field-specific protection
        db.add_field_protection("User", "password", protection_level=ProtectionLevel.BLOCK)

        # Business hours protection
        db.enable_business_hours_protection(9, 17)  # 9 AM - 5 PM read-only

        # Use protected runtime
        runtime = db.create_protected_runtime()
        results, run_id = runtime.execute(workflow.build())
    """

    def __init__(
        self,
        *args,
        protection_config: Optional[WriteProtectionConfig] = None,
        enable_protection: bool = True,
        **kwargs,
    ):
        """
        Initialize ProtectedDataFlow.

        Args:
            *args: Standard DataFlow arguments
            protection_config: Write protection configuration
            enable_protection: Enable protection by default
            **kwargs: Standard DataFlow keyword arguments
        """
        # Initialize DataFlow first
        super().__init__(*args, **kwargs)

        # Initialize protection system
        if enable_protection:
            # Use provided config or create default
            self._protection_config = protection_config or WriteProtectionConfig()
            self._protection_engine = WriteProtectionEngine(self._protection_config)

            # Replace node generator with protected version
            self._node_generator = ProtectedNodeGenerator(self)

            # Wrap AsyncSQLDatabaseNode if available
            self._wrap_async_sql_node()

            logger.info("DataFlow write protection enabled")
        else:
            self._protection_config = None
            self._protection_engine = None
            logger.info("DataFlow write protection disabled")

    def model(self, cls: Type) -> Type:
        """Override model decorator to ensure protection is applied to nodes."""
        # Call parent model decorator first
        result = super().model(cls)

        # If protection is enabled and we have a node generator, wrap nodes with protection
        if self._protection_engine:
            model_name = cls.__name__
            # Get the nodes that were just generated
            node_names = [
                f"{model_name}CreateNode",
                f"{model_name}ReadNode",
                f"{model_name}UpdateNode",
                f"{model_name}DeleteNode",
                f"{model_name}ListNode",
                f"{model_name}BulkCreateNode",
                f"{model_name}BulkUpdateNode",
                f"{model_name}BulkDeleteNode",
                f"{model_name}BulkUpsertNode",
            ]

            # Import protect_dataflow_node here to avoid circular import
            from .protection_middleware import protect_dataflow_node

            # Wrap each generated node with protection
            for node_name in node_names:
                if node_name in self._nodes:
                    original_node = self._nodes[node_name]
                    protected_node = protect_dataflow_node(original_node)
                    self._nodes[node_name] = protected_node
                    logger.debug(f"Applied protection to {node_name}")

        return result

    def _wrap_async_sql_node(self):
        """Wrap AsyncSQLDatabaseNode with protection checks."""
        try:
            from kailash.nodes.data.async_sql import AsyncSQLDatabaseNode

            if self._protection_engine:
                wrapper = AsyncSQLProtectionWrapper(self._protection_engine)
                wrapper.wrap_async_sql_node(AsyncSQLDatabaseNode)
                logger.debug("AsyncSQLDatabaseNode wrapped with protection")
        except ImportError:
            logger.warning("AsyncSQLDatabaseNode not available for protection wrapping")

    def create_workflow(self, workflow_id: str = None, **kwargs):
        """
        Create a workflow with protection capabilities.

        This method creates standard workflows but when executed with
        create_protected_runtime(), protection rules are enforced.
        """
        from kailash.workflow.builder import WorkflowBuilder

        return WorkflowBuilder(workflow_id=workflow_id, **kwargs)

    def execute_protected(self, workflow, **runtime_kwargs):
        """
        Execute a workflow with protection enforcement.

        Args:
            workflow: Workflow to execute
            **runtime_kwargs: Arguments for ProtectedDataFlowRuntime

        Returns:
            Tuple of (results, run_id)
        """
        runtime = self.create_protected_runtime(**runtime_kwargs)
        return runtime.execute(
            workflow.build() if hasattr(workflow, "build") else workflow
        )

    def get_protection_status(self) -> Dict[str, Any]:
        """Get current protection status and configuration."""
        if not self._protection_engine or not self._protection_config:
            return {"protection_enabled": False}

        config = self._protection_config
        return {
            "protection_enabled": True,
            "global_protection": {
                "level": config.global_protection.protection_level.value,
                "allowed_operations": [
                    op.value for op in config.global_protection.allowed_operations
                ],
                "reason": config.global_protection.reason,
            },
            "connection_protections": len(config.connection_protections),
            "model_protections": len(config.model_protections),
            "audit_events": len(config.auditor.events),
        }

    def disable_protection(self):
        """Temporarily disable all protection (use with caution)."""
        from .protection import (
            GlobalProtection,
            OperationType,
            ProtectionLevel,
            WriteProtectionConfig,
        )

        # Create a disabled configuration rather than None
        disabled_config = WriteProtectionConfig()
        disabled_config.global_protection = GlobalProtection(
            protection_level=ProtectionLevel.OFF,
            allowed_operations={
                OperationType.READ,
                OperationType.CREATE,
                OperationType.UPDATE,
                OperationType.DELETE,
            },
            reason="Protection disabled",
        )
        self._protection_config = disabled_config
        self._protection_engine = None  # Set engine to None to truly disable
        logger.warning("DataFlow protection disabled")

    def enable_protection(self, config: Optional[WriteProtectionConfig] = None):
        """Re-enable protection with optional new configuration."""
        self._protection_config = config or WriteProtectionConfig()
        self._protection_engine = WriteProtectionEngine(self._protection_config)
        logger.info("DataFlow protection enabled")

    # Convenience methods for common protection scenarios
    def protect_production(self):
        """Apply production-safe protection patterns."""
        config = WriteProtectionConfig.production_safe()
        self.set_protection_config(config)
        return self

    def protect_during_maintenance(self, reason: str = "Maintenance in progress"):
        """Enable read-only mode for maintenance."""
        self.enable_read_only_mode(reason)
        return self

    def protect_sensitive_models(
        self, model_names: list, allowed_operations: set = None
    ):
        """Protect specific models with custom operations."""
        from .protection import ModelProtection, OperationType

        if allowed_operations is None:
            allowed_operations = {OperationType.READ}

        for model_name in model_names:
            self.add_model_protection(
                model_name,
                allowed_operations=allowed_operations,
                reason=f"Sensitive model protection: {model_name}",
            )
        return self

    def protect_pii_fields(self, field_mappings: Dict[str, list]):
        """Protect PII fields across models."""
        from .protection import OperationType

        for model_name, field_names in field_mappings.items():
            for field_name in field_names:
                self.add_field_protection(
                    model_name,
                    field_name,
                    allowed_operations={OperationType.READ},
                    reason=f"PII protection: {field_name}",
                )
        return self


# Compatibility alias - allows existing code to work unchanged
# while new code can explicitly use ProtectedDataFlow
def create_dataflow(*args, enable_protection: bool = False, **kwargs) -> DataFlow:
    """
    Factory function to create DataFlow instances with optional protection.

    Args:
        *args: DataFlow constructor arguments
        enable_protection: Whether to enable write protection
        **kwargs: DataFlow constructor keyword arguments

    Returns:
        DataFlow or ProtectedDataFlow instance
    """
    if enable_protection:
        return ProtectedDataFlow(*args, **kwargs)
    else:
        return DataFlow(*args, **kwargs)


# Export enhanced classes for direct use
__all__ = [
    "ProtectedDataFlow",
    "ProtectedNodeGenerator",
    "ProtectedDataFlowRuntime",
    "create_dataflow",
]
