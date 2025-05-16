"""Base node class and node system implementation."""
import json
import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, Type, Set
from datetime import datetime

from pydantic import BaseModel, Field

from kailash.sdk_exceptions import NodeValidationError, NodeExecutionError


class NodeMetadata(BaseModel):
    """Metadata for a node."""
    name: str = Field(..., description="Node name")
    description: str = Field("", description="Node description")
    version: str = Field("1.0.0", description="Node version")
    author: str = Field("", description="Node author")
    created_at: datetime = Field(
        default_factory=datetime.utcnow, description="Node creation date")
    tags: Set[str] = Field(default_factory=set, description="Node tags")


class NodeParameter(BaseModel):
    """Definition of a node parameter."""
    name: str
    type: Type
    required: bool = True
    default: Any = None
    description: str = ""


class Node(ABC):
    """Base class for all nodes in the Kailash system."""
    
    def __init__(self, **kwargs):
        """Initialize the node with configuration parameters."""
        self.id = kwargs.get('id', self.__class__.__name__)
        self.metadata = NodeMetadata(
            name=kwargs.get('name', self.__class__.__name__),
            description=kwargs.get('description', self.__doc__ or ""),
            version=kwargs.get('version', "1.0.0"),
            author=kwargs.get('author', ""),
            tags=kwargs.get('tags', set())
        )
        self.logger = logging.getLogger(f"kailash.nodes.{self.id}")
        self.config = kwargs
        self._validate_config()
    
    @abstractmethod
    def get_parameters(self) -> Dict[str, NodeParameter]:
        """Define the parameters this node accepts.
        
        Returns:
            Dictionary mapping parameter names to their definitions
        """
        pass
    
    @abstractmethod
    def run(self, **kwargs) -> Dict[str, Any]:
        """Execute the node's logic.
        
        Args:
            **kwargs: Input parameters for the node
            
        Returns:
            Dictionary of outputs from the node
            
        Raises:
            NodeExecutionError: If execution fails
        """
        pass
    
    def _validate_config(self):
        """Validate node configuration against defined parameters."""
        params = self.get_parameters()
        
        for param_name, param_def in params.items():
            if param_def.required and param_name not in self.config:
                if param_def.default is None:
                    raise NodeValidationError(
                        f"Required parameter '{param_name}' not provided"
                    )
                else:
                    self.config[param_name] = param_def.default
            
            if param_name in self.config:
                value = self.config[param_name]
                if not isinstance(value, param_def.type):
                    try:
                        self.config[param_name] = param_def.type(value)
                    except (ValueError, TypeError) as e:
                        raise NodeValidationError(
                            f"Parameter '{param_name}' must be of type {param_def.type.__name__}"
                        ) from e
    
    def validate_inputs(self, **kwargs) -> Dict[str, Any]:
        """Validate runtime inputs against node requirements.
        
        Args:
            **kwargs: Runtime inputs to validate
            
        Returns:
            Validated and processed inputs
            
        Raises:
            NodeValidationError: If inputs are invalid
        """
        params = self.get_parameters()
        validated = {}
        
        for param_name, param_def in params.items():
            if param_def.required and param_name not in kwargs:
                raise NodeValidationError(
                    f"Required input '{param_name}' not provided"
                )
            
            if param_name in kwargs:
                value = kwargs[param_name]
                if not isinstance(value, param_def.type):
                    try:
                        validated[param_name] = param_def.type(value)
                    except (ValueError, TypeError) as e:
                        raise NodeValidationError(
                            f"Input '{param_name}' must be of type {param_def.type.__name__}"
                        ) from e
                else:
                    validated[param_name] = value
        
        return validated
    
    def validate_outputs(self, outputs: Dict[str, Any]) -> Dict[str, Any]:
        """Validate outputs are JSON-serializable.
        
        Args:
            outputs: Outputs to validate
            
        Returns:
            Validated outputs
            
        Raises:
            NodeValidationError: If outputs are not JSON-serializable
        """
        try:
            json.dumps(outputs)
            return outputs
        except (TypeError, ValueError) as e:
            raise NodeValidationError(
                f"Node outputs must be JSON-serializable: {e}"
            ) from e
    
    def execute(self, **kwargs) -> Dict[str, Any]:
        """Execute the node with validation and error handling.
        
        Args:
            **kwargs: Input parameters
            
        Returns:
            Dictionary of outputs
            
        Raises:
            NodeExecutionError: If execution fails
        """
        try:
            self.logger.info(f"Executing node {self.id}")
            
            # Validate inputs
            validated_inputs = self.validate_inputs(**kwargs)
            
            # Execute node logic
            outputs = self.run(**validated_inputs)
            
            # Validate outputs
            validated_outputs = self.validate_outputs(outputs)
            
            self.logger.info(f"Node {self.id} executed successfully")
            return validated_outputs
            
        except Exception as e:
            self.logger.error(f"Node {self.id} execution failed: {e}")
            raise NodeExecutionError(f"Node execution failed: {e}") from e
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert node to dictionary representation."""
        return {
            "id": self.id,
            "type": self.__class__.__name__,
            "metadata": self.metadata.model_dump(),
            "config": self.config,
            "parameters": {
                name: {
                    "type": param.type.__name__,
                    "required": param.required,
                    "default": param.default,
                    "description": param.description
                }
                for name, param in self.get_parameters().items()
            }
        }


# Node Registry
class NodeRegistry:
    """Registry for discovering and managing available nodes."""
    
    _instance = None
    _nodes: Dict[str, Type[Node]] = {}
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    @classmethod
    def register(cls, node_class: Type[Node], alias: Optional[str] = None):
        """Register a node class.
        
        Args:
            node_class: Node class to register
            alias: Optional alias for the node
        """
        node_name = alias or node_class.__name__
        cls._nodes[node_name] = node_class
        
    @classmethod
    def get(cls, node_name: str) -> Type[Node]:
        """Get a registered node class by name.
        
        Args:
            node_name: Name of the node
            
        Returns:
            Node class
            
        Raises:
            KeyError: If node is not registered
        """
        if node_name not in cls._nodes:
            raise KeyError(f"Node '{node_name}' not found in registry")
        return cls._nodes[node_name]
    
    @classmethod
    def list_nodes(cls) -> Dict[str, Type[Node]]:
        """List all registered nodes.
        
        Returns:
            Dictionary of node names to classes
        """
        return cls._nodes.copy()
    
    @classmethod
    def clear(cls):
        """Clear all registered nodes."""
        cls._nodes.clear()


def register_node(alias: Optional[str] = None):
    """Decorator to register a node class.
    
    Args:
        alias: Optional alias for the node
    """
    def decorator(node_class: Type[Node]):
        NodeRegistry.register(node_class, alias)
        return node_class
    return decorator