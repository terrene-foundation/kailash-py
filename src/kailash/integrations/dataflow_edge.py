"""DataFlow edge integration for Kailash SDK.

This module provides integration between DataFlow models and edge computing
infrastructure, allowing models to specify edge requirements that are
automatically propagated to generated nodes.
"""

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class DataFlowEdgeIntegration:
    """Integration layer between DataFlow and edge infrastructure."""

    @staticmethod
    def extract_edge_config(model_class: type) -> Optional[Dict[str, Any]]:
        """Extract edge configuration from a DataFlow model.

        Args:
            model_class: The DataFlow model class

        Returns:
            Edge configuration dictionary or None
        """
        # Check for __dataflow__ attribute
        dataflow_config = getattr(model_class, "__dataflow__", {})

        # Look for edge_config in the __dataflow__ dictionary
        edge_config = dataflow_config.get("edge_config", None)

        if edge_config:
            logger.debug(
                f"Found edge config for model {model_class.__name__}: {edge_config}"
            )

        return edge_config

    @staticmethod
    def enhance_node_config(
        node_config: Dict[str, Any], edge_config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Enhance node configuration with edge requirements.

        Args:
            node_config: Base node configuration
            edge_config: Edge configuration from model

        Returns:
            Enhanced node configuration
        """
        enhanced = node_config.copy()

        # Map DataFlow edge config to node parameters
        if "compliance_classification" in edge_config:
            enhanced["data_classification"] = edge_config["compliance_classification"]

        if "preferred_regions" in edge_config:
            enhanced["preferred_locations"] = edge_config["preferred_regions"]

        if "required_compliance" in edge_config:
            enhanced["compliance_zones"] = edge_config["required_compliance"]

        if "replication_strategy" in edge_config:
            # Map to edge data node parameters
            enhanced["replication_factor"] = edge_config.get("replication_factor", 3)
            enhanced["consistency"] = edge_config.get("consistency_model", "eventual")

        if "encryption_required" in edge_config:
            enhanced["enable_encryption"] = edge_config["encryption_required"]

        # Mark as edge-enabled for WorkflowBuilder detection
        enhanced["_edge_enabled"] = True

        logger.debug(f"Enhanced node config with edge capabilities: {enhanced}")

        return enhanced

    @staticmethod
    def should_use_edge_node(operation: str, edge_config: Dict[str, Any]) -> bool:
        """Determine if an operation should use edge nodes.

        Args:
            operation: The CRUD operation (create, read, update, delete, list)
            edge_config: Edge configuration from model

        Returns:
            True if edge nodes should be used
        """
        # Always use edge nodes if compliance is required
        if edge_config.get("required_compliance"):
            return True

        # Use edge nodes for geo-distributed operations
        if edge_config.get("geo_distributed", False):
            return True

        # Use edge nodes for operations requiring low latency
        if edge_config.get("low_latency_required", False):
            return True

        # Check operation-specific settings
        edge_operations = edge_config.get("edge_operations", [])
        if operation in edge_operations:
            return True

        # Default to using edge nodes if any edge config is present
        return bool(edge_config)

    @staticmethod
    def create_edge_workflow_config(
        model_name: str, edge_config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Create workflow-level edge configuration for a model.

        Args:
            model_name: Name of the DataFlow model
            edge_config: Edge configuration from model

        Returns:
            Workflow edge configuration
        """
        workflow_edge_config = {
            "discovery": {
                "locations": edge_config.get("edge_locations", []),
                "selection_strategy": edge_config.get("selection_strategy", "balanced"),
            },
            "compliance": {
                "strict_mode": edge_config.get("strict_compliance", True),
                "default_classification": edge_config.get(
                    "compliance_classification", "pii"
                ),
            },
            "performance": {
                "connection_pool_size": edge_config.get("connection_pool_size", 10),
                "health_check_interval": edge_config.get("health_check_interval", 60),
            },
        }

        # Add model-specific metadata
        workflow_edge_config["dataflow_model"] = model_name

        return workflow_edge_config


# Monkey-patch helper for DataFlow NodeGenerator
def enhance_dataflow_node_generator():
    """Enhance DataFlow's NodeGenerator to support edge configuration.

    This function should be called during DataFlow initialization to add
    edge support to generated nodes.
    """
    try:
        from dataflow.core.nodes import NodeGenerator

        # Store original _create_node_class method
        original_create_node_class = NodeGenerator._create_node_class

        def _create_node_class_with_edge(
            self, model_name: str, operation: str, fields: Dict[str, Any]
        ):
            """Enhanced node creation with edge support."""
            # Get the model class if available
            model_class = getattr(self.dataflow_instance, f"_{model_name}_model", None)

            if model_class:
                # Extract edge configuration
                edge_config = DataFlowEdgeIntegration.extract_edge_config(model_class)

                if edge_config and DataFlowEdgeIntegration.should_use_edge_node(
                    operation, edge_config
                ):
                    # Create edge-enabled node
                    logger.info(
                        f"Creating edge-enabled node for {model_name}.{operation}"
                    )

                    # Create base node class
                    node_class = original_create_node_class(
                        self, model_name, operation, fields
                    )

                    # Enhance node class with edge capabilities
                    original_init = node_class.__init__

                    def edge_enhanced_init(node_self, **config):
                        # Enhance config with edge settings
                        enhanced_config = DataFlowEdgeIntegration.enhance_node_config(
                            config, edge_config
                        )

                        # Determine if this should be an EdgeDataNode
                        if operation in ["create", "read", "update", "delete"]:
                            # These operations benefit from EdgeDataNode
                            enhanced_config["_preferred_node_type"] = "EdgeDataNode"

                        original_init(node_self, **enhanced_config)

                    node_class.__init__ = edge_enhanced_init

                    return node_class

            # Fall back to original implementation
            return original_create_node_class(self, model_name, operation, fields)

        # Replace the method
        NodeGenerator._create_node_class = _create_node_class_with_edge

        logger.info("DataFlow NodeGenerator enhanced with edge support")

    except ImportError:
        logger.warning("DataFlow not available, edge integration not applied")


# Example usage in DataFlow model
"""
Example DataFlow model with edge configuration:

```python
from dataflow import DataFlow

db = DataFlow()

@db.model
class SensitiveData:
    user_id: int
    personal_info: dict
    location: str

    __dataflow__ = {
        'multi_tenant': True,
        'soft_delete': True,
        'edge_config': {
            'compliance_classification': 'pii',
            'required_compliance': ['GDPR', 'CCPA'],
            'preferred_regions': ['eu-west-1', 'us-west-2'],
            'replication_strategy': 'multi-region',
            'replication_factor': 3,
            'consistency_model': 'strong',
            'encryption_required': True,
            'edge_operations': ['create', 'read', 'update'],  # Use edge for these
            'geo_distributed': True,
            'low_latency_required': True
        }
    }

# When using generated nodes in workflows:
workflow = WorkflowBuilder(edge_config=DataFlowEdgeIntegration.create_edge_workflow_config(
    'SensitiveData',
    SensitiveData.__dataflow__['edge_config']
))

# Nodes will automatically use edge infrastructure
workflow.add_node("SensitiveDataCreateNode", "create", {
    "user_id": 123,
    "personal_info": {"name": "John Doe"},
    "location": "EU"
})
```
"""
