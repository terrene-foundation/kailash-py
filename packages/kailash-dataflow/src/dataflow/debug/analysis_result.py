"""Analysis result with root cause and affected components.

This module provides the AnalysisResult data structure that represents the
output of error context analysis performed by ContextAnalyzer.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class AnalysisResult:
    """Analysis result with root cause and affected components.

    The AnalysisResult contains structured information about an error after
    analyzing its context using the Inspector API. This includes:
    - Human-readable root cause description
    - List of affected workflow components (nodes, connections, models)
    - Structured context data for solution matching
    - Preliminary suggestions for resolution

    Attributes:
        root_cause: Human-readable description of error root cause
        affected_nodes: List of node IDs involved in the error
        affected_connections: List of connection descriptions (source → target format)
        affected_models: List of DataFlow model names involved
        context_data: Structured context extracted from Inspector (node types,
                     schemas, parameters, etc.)
        suggestions: Preliminary resolution suggestions (before solution matching)

    Example:
        >>> result = AnalysisResult(
        ...     root_cause="Node 'create_user' is missing required parameter 'id'",
        ...     affected_nodes=["create_user"],
        ...     affected_connections=[],
        ...     affected_models=["User"],
        ...     context_data={
        ...         "node_type": "UserCreateNode",
        ...         "missing_parameter": "id",
        ...         "field_type": "str"
        ...     },
        ...     suggestions=["Add 'id' parameter to node 'create_user'"]
        ... )
        >>> print(result.root_cause)
        Node 'create_user' is missing required parameter 'id'
    """

    root_cause: str
    affected_nodes: List[str] = field(default_factory=list)
    affected_connections: List[str] = field(default_factory=list)
    affected_models: List[str] = field(default_factory=list)
    context_data: Dict[str, Any] = field(default_factory=dict)
    suggestions: List[str] = field(default_factory=list)

    @classmethod
    def unknown(cls) -> "AnalysisResult":
        """Create AnalysisResult for unknown/uncategorized errors.

        Returns an AnalysisResult with generic root cause and no specific
        context. Used when error category is UNKNOWN or analysis fails.

        Returns:
            AnalysisResult with generic unknown error information

        Example:
            >>> result = AnalysisResult.unknown()
            >>> result.root_cause
            'Unknown error - unable to determine root cause'
            >>> result.affected_nodes
            []
        """
        return cls(
            root_cause="Unknown error - unable to determine root cause",
            affected_nodes=[],
            affected_connections=[],
            affected_models=[],
            context_data={},
            suggestions=["Review error message and stack trace for details"],
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert AnalysisResult to dictionary for serialization.

        Returns:
            Dictionary representation of AnalysisResult with all fields

        Example:
            >>> result = AnalysisResult(
            ...     root_cause="Missing parameter",
            ...     affected_nodes=["create_user"]
            ... )
            >>> data = result.to_dict()
            >>> data["root_cause"]
            'Missing parameter'
            >>> data["affected_nodes"]
            ['create_user']
        """
        return {
            "root_cause": self.root_cause,
            "affected_nodes": self.affected_nodes,
            "affected_connections": self.affected_connections,
            "affected_models": self.affected_models,
            "context_data": self.context_data,
            "suggestions": self.suggestions,
        }

    def __repr__(self) -> str:
        """Debug representation of AnalysisResult.

        Returns:
            String representation with root cause and affected components count

        Example:
            >>> result = AnalysisResult(
            ...     root_cause="Missing parameter",
            ...     affected_nodes=["node1", "node2"]
            ... )
            >>> repr(result)
            "AnalysisResult(root_cause='Missing parameter', nodes=2, connections=0, models=0)"
        """
        return (
            f"AnalysisResult("
            f"root_cause='{self.root_cause}', "
            f"nodes={len(self.affected_nodes)}, "
            f"connections={len(self.affected_connections)}, "
            f"models={len(self.affected_models)})"
        )
