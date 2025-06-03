"""Mock node registry for tests."""

from typing import Any, Dict, Type

from kailash.nodes.base import Node, NodeRegistry
from kailash.sdk_exceptions import NodeConfigurationError


class MockNode(Node):
    """Mock node for testing."""

    def __init__(self, node_id: str = None, name: str = None, **kwargs):
        """Initialize mock node."""
        self.node_id = node_id
        self.name = name or node_id
        self.config = kwargs.copy()

    def process(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Process data."""
        return {"value": data.get("value", 0) * 2}

    def execute(self, **kwargs) -> Dict[str, Any]:
        """Execute node with keyword arguments."""
        return self.process(kwargs)

    def get_parameters(self) -> Dict[str, Any]:
        """Get node parameters."""
        return {}


# Register mock nodes with the real registry for tests
NODE_TYPES = [
    "MockNode",
    "DataReader",
    "DataWriter",
    "Processor",
    "Merger",
    "DataFilter",
    "AIProcessor",
    "Transformer",
]

for node_type in NODE_TYPES:
    try:
        NodeRegistry._registry[node_type] = MockNode
    except Exception:
        pass


class MockRegistry:
    """Mock node registry for testing."""

    _registry: Dict[str, Type[Node]] = {node_type: MockNode for node_type in NODE_TYPES}

    @classmethod
    def get(cls, node_type: str) -> Type[Node]:
        """Get node class by type name."""
        if node_type not in cls._registry:
            raise NodeConfigurationError(
                f"Node '{node_type}' not found in registry. "
                f"Available nodes: {list(cls._registry.keys())}"
            )
        return cls._registry[node_type]
