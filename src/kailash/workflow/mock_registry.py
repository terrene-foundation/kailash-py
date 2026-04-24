"""Mock node registry for tests."""

from typing import Any

from kailash.nodes.base import Node, NodeRegistry
from kailash.sdk_exceptions import NodeConfigurationError


class MockNode(Node):
    """Mock node for testing."""

    def __init__(
        self, node_id: str | None = None, name: str | None = None, **kwargs: Any
    ):
        """Initialize mock node."""
        super().__init__(**kwargs)
        self.node_id = node_id
        self.name = name or node_id
        self.config = kwargs.copy()

    def process(self, data: dict[str, Any]) -> dict[str, Any]:
        """Process data."""
        return {"value": data.get("value", 0) * 2}

    def run(self, **kwargs) -> dict[str, Any]:
        """Execute the node's logic (Node ABC contract)."""
        return self.execute(**kwargs)

    def execute(self, **kwargs) -> dict[str, Any]:
        """Execute node with keyword arguments."""
        return self.process(kwargs)

    def get_parameters(self) -> dict[str, Any]:
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
        NodeRegistry._nodes[node_type] = MockNode
    except Exception:
        pass


class MockRegistry:
    """Mock node registry for testing."""

    _registry: dict[str, type[Node]] = {node_type: MockNode for node_type in NODE_TYPES}

    @classmethod
    def get(cls, node_type: str) -> type[Node]:
        """Get node class by type name."""
        if node_type not in cls._registry:
            raise NodeConfigurationError(
                f"Node '{node_type}' not found in registry. "
                f"Available nodes: {list(cls._registry.keys())}"
            )
        return cls._registry[node_type]
