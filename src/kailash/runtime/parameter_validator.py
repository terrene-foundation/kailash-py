"""Enhanced parameter validation system for runtime parameter injection.

This module provides strict validation modes and better error reporting
for parameter injection scenarios to address UX issues identified in
bug reports and user feedback.
"""
import logging
from typing import Dict, List, Any, Set, Optional, Tuple
from enum import Enum
from dataclasses import dataclass

from kailash.nodes.base import Node, NodeParameter
from kailash.sdk_exceptions import (
    ParameterValidationError, 
    WorkflowValidationError,
    NodeConfigurationError
)

logger = logging.getLogger(__name__)


class ValidationMode(Enum):
    """Parameter validation strictness levels."""
    WARN = "warn"          # Log warnings but continue (default)
    STRICT = "strict"      # Raise errors for validation issues  
    SILENT = "silent"      # No validation (not recommended)
    DEBUG = "debug"        # Verbose logging for troubleshooting


class ParameterIssueType(Enum):
    """Types of parameter validation issues."""
    UNDECLARED_PARAMETER = "undeclared_parameter"
    MISSING_REQUIRED = "missing_required" 
    TYPE_MISMATCH = "type_mismatch"
    UNUSED_RUNTIME_PARAM = "unused_runtime_param"
    PARAMETER_IGNORED = "parameter_ignored"
    SILENT_OVERRIDE = "silent_override"


@dataclass
class ParameterIssue:
    """Represents a parameter validation issue."""
    issue_type: ParameterIssueType
    node_id: str
    parameter_name: str
    message: str
    suggestion: Optional[str] = None
    severity: str = "warning"
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for logging/reporting."""
        return {
            "issue_type": self.issue_type.value,
            "node_id": self.node_id,
            "parameter_name": self.parameter_name,
            "message": self.message,
            "suggestion": self.suggestion,
            "severity": self.severity
        }


class EnhancedParameterValidator:
    """Enhanced parameter validator with strict modes and better error reporting."""
    
    def __init__(self, validation_mode: ValidationMode = ValidationMode.WARN):
        self.validation_mode = validation_mode
        self.logger = logging.getLogger(__name__)
        self.issues: List[ParameterIssue] = []
    
    def validate_runtime_parameters(
        self,
        workflow_nodes: Dict[str, Node],
        runtime_parameters: Dict[str, Any],
        node_configs: Dict[str, Dict[str, Any]] = None
    ) -> Tuple[Dict[str, Dict[str, Any]], List[ParameterIssue]]:
        """
        Validate runtime parameters against workflow nodes.
        
        Args:
            workflow_nodes: Dictionary of node_id -> Node instances
            runtime_parameters: Runtime parameters to validate
            node_configs: Optional node configurations for context
            
        Returns:
            Tuple of (validated_parameters, validation_issues)
            
        Raises:
            ParameterValidationError: In strict mode when validation fails
        """
        self.issues = []
        node_configs = node_configs or {}
        
        # Separate parameter formats
        node_specific_params, workflow_level_params = self._separate_parameter_formats(
            runtime_parameters, workflow_nodes.keys()
        )
        
        validated_params = {}
        
        # Validate node-specific parameters
        for node_id, params in node_specific_params.items():
            if node_id not in workflow_nodes:
                self._add_issue(
                    ParameterIssueType.UNUSED_RUNTIME_PARAM,
                    node_id,
                    "*",
                    f"Runtime parameters provided for non-existent node '{node_id}'",
                    suggestion=f"Check node ID spelling. Available nodes: {list(workflow_nodes.keys())}"
                )
                continue
                
            node_instance = workflow_nodes[node_id]
            node_param_defs = node_instance.get_parameters()
            node_config = node_configs.get(node_id, {})
            
            validated_node_params = self._validate_node_parameters(
                node_id, node_instance, params, node_param_defs, node_config
            )
            
            if validated_node_params:
                validated_params[node_id] = validated_node_params
        
        # Validate workflow-level parameters
        if workflow_level_params:
            workflow_validated = self._validate_workflow_level_parameters(
                workflow_nodes, workflow_level_params
            )
            validated_params.update(workflow_validated)
        
        # Handle validation issues based on mode
        self._handle_validation_issues()
        
        return validated_params, self.issues
    
    def _separate_parameter_formats(
        self, 
        parameters: Dict[str, Any], 
        node_ids: Set[str]
    ) -> Tuple[Dict[str, Dict[str, Any]], Dict[str, Any]]:
        """Separate node-specific from workflow-level parameters."""
        node_specific = {}
        workflow_level = {}
        
        for key, value in parameters.items():
            if key in node_ids and isinstance(value, dict):
                node_specific[key] = value
            else:
                workflow_level[key] = value
                
        if self.validation_mode == ValidationMode.DEBUG:
            self.logger.debug(
                f"Parameter separation: node_specific={list(node_specific.keys())}, "
                f"workflow_level={list(workflow_level.keys())}"
            )
        
        return node_specific, workflow_level
    
    def _validate_node_parameters(
        self,
        node_id: str,
        node_instance: Node,
        runtime_params: Dict[str, Any],
        param_defs: Dict[str, NodeParameter],
        node_config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Validate runtime parameters for a specific node."""
        validated = {}
        
        # Check for undeclared parameters
        for param_name, param_value in runtime_params.items():
            if param_name not in param_defs:
                self._add_issue(
                    ParameterIssueType.UNDECLARED_PARAMETER,
                    node_id,
                    param_name,
                    f"Runtime parameter '{param_name}' not declared in node's get_parameters()",
                    suggestion=f"Add '{param_name}' to {node_instance.__class__.__name__}.get_parameters() or remove from runtime parameters"
                )
                
                # In strict mode, skip undeclared parameters
                if self.validation_mode == ValidationMode.STRICT:
                    continue
                    
                # In warn mode, check if node accepts **kwargs (like PythonCodeNode)
                if self._node_accepts_kwargs(node_instance):
                    validated[param_name] = param_value
                    if self.validation_mode == ValidationMode.DEBUG:
                        self.logger.debug(f"Allowing undeclared parameter '{param_name}' for **kwargs node")
                continue
            
            param_def = param_defs[param_name]
            
            # Validate parameter type
            if not self._validate_parameter_type(param_value, param_def):
                self._add_issue(
                    ParameterIssueType.TYPE_MISMATCH,
                    node_id,
                    param_name,
                    f"Parameter '{param_name}' type mismatch. Expected {param_def.type}, got {type(param_value)}",
                    suggestion=f"Convert parameter to {param_def.type} or update parameter definition"
                )
                
                if self.validation_mode == ValidationMode.STRICT:
                    continue
            
            # Check for parameter overrides
            if param_name in node_config:
                self._add_issue(
                    ParameterIssueType.SILENT_OVERRIDE,
                    node_id,
                    param_name,
                    f"Runtime parameter '{param_name}' overrides node config value",
                    suggestion="This is expected behavior - runtime parameters have highest precedence"
                )
            
            validated[param_name] = param_value
        
        # Check for missing required parameters
        for param_name, param_def in param_defs.items():
            if param_def.required and param_name not in runtime_params and param_name not in node_config:
                self._add_issue(
                    ParameterIssueType.MISSING_REQUIRED,
                    node_id,
                    param_name,
                    f"Required parameter '{param_name}' not provided in runtime parameters or node config",
                    suggestion=f"Add '{param_name}' to runtime parameters or node configuration"
                )
        
        return validated
    
    def _validate_workflow_level_parameters(
        self,
        workflow_nodes: Dict[str, Node],
        workflow_params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Validate workflow-level parameters and distribute to nodes."""
        distributed_params = {}
        used_params = set()
        
        for param_name, param_value in workflow_params.items():
            # Find nodes that can accept this parameter
            accepting_nodes = []
            
            for node_id, node_instance in workflow_nodes.items():
                param_defs = node_instance.get_parameters()
                
                if (param_name in param_defs or 
                    self._parameter_matches_alias(param_name, param_defs) or
                    self._node_accepts_kwargs(node_instance)):
                    accepting_nodes.append(node_id)
            
            if accepting_nodes:
                used_params.add(param_name)
                for node_id in accepting_nodes:
                    if node_id not in distributed_params:
                        distributed_params[node_id] = {}
                    distributed_params[node_id][param_name] = param_value
                    
                if self.validation_mode == ValidationMode.DEBUG:
                    self.logger.debug(
                        f"Distributed workflow parameter '{param_name}' to nodes: {accepting_nodes}"
                    )
            else:
                self._add_issue(
                    ParameterIssueType.UNUSED_RUNTIME_PARAM,
                    "*",
                    param_name,
                    f"Workflow-level parameter '{param_name}' not used by any node",
                    suggestion="Remove unused parameter or add parameter declarations to nodes"
                )
        
        return distributed_params
    
    def _node_accepts_kwargs(self, node_instance: Node) -> bool:
        """Check if a node can accept arbitrary keyword arguments."""
        # Check for PythonCodeNode or similar nodes that accept **kwargs
        if hasattr(node_instance, '__class__') and "PythonCode" in node_instance.__class__.__name__:
            return True
            
        # Check if the node has a method signature that accepts **kwargs
        if hasattr(node_instance, 'run'):
            import inspect
            try:
                sig = inspect.signature(node_instance.run)
                return any(
                    param.kind == inspect.Parameter.VAR_KEYWORD
                    for param in sig.parameters.values()
                )
            except (ValueError, TypeError):
                pass
                
        return False
    
    def _parameter_matches_alias(self, param_name: str, param_defs: Dict[str, NodeParameter]) -> bool:
        """Check if parameter matches any workflow aliases."""
        for param_def in param_defs.values():
            if hasattr(param_def, 'workflow_alias') and param_def.workflow_alias == param_name:
                return True
            if hasattr(param_def, 'auto_map_from') and param_name in param_def.auto_map_from:
                return True
        return False
    
    def _validate_parameter_type(self, value: Any, param_def: NodeParameter) -> bool:
        """Validate parameter value against its type definition."""
        if not hasattr(param_def, 'type') or param_def.type is None:
            return True  # No type constraint
            
        expected_type = param_def.type
        
        # Handle special cases
        if expected_type == object:
            return True  # Any type allowed
            
        try:
            if isinstance(value, expected_type):
                return True
                
            # Try type coercion for basic types
            if expected_type in (int, float, str, bool):
                expected_type(value)
                return True
                
        except (ValueError, TypeError):
            return False
            
        return False
    
    def _add_issue(
        self,
        issue_type: ParameterIssueType,
        node_id: str,
        parameter_name: str,
        message: str,
        suggestion: Optional[str] = None
    ):
        """Add a validation issue."""
        severity = "error" if self.validation_mode == ValidationMode.STRICT else "warning"
        
        issue = ParameterIssue(
            issue_type=issue_type,
            node_id=node_id,
            parameter_name=parameter_name,
            message=message,
            suggestion=suggestion,
            severity=severity
        )
        
        self.issues.append(issue)
        
        if self.validation_mode == ValidationMode.DEBUG:
            self.logger.debug(f"Parameter validation issue: {issue.to_dict()}")
        elif self.validation_mode == ValidationMode.WARN:
            self.logger.warning(f"{message} (Node: {node_id}, Parameter: {parameter_name})")
    
    def _handle_validation_issues(self):
        """Handle validation issues based on the current mode."""
        if self.validation_mode == ValidationMode.STRICT and self.issues:
            error_issues = [issue for issue in self.issues if issue.severity == "error"]
            if error_issues:
                error_messages = [issue.message for issue in error_issues]
                raise ParameterValidationError(
                    f"Parameter validation failed: {'; '.join(error_messages)}"
                )
    
    def get_validation_report(self) -> Dict[str, Any]:
        """Generate a comprehensive validation report."""
        report = {
            "validation_mode": self.validation_mode.value,
            "total_issues": len(self.issues),
            "issues_by_type": {},
            "issues_by_severity": {"warning": 0, "error": 0},
            "detailed_issues": [issue.to_dict() for issue in self.issues]
        }
        
        for issue in self.issues:
            issue_type = issue.issue_type.value
            if issue_type not in report["issues_by_type"]:
                report["issues_by_type"][issue_type] = 0
            report["issues_by_type"][issue_type] += 1
            
            report["issues_by_severity"][issue.severity] += 1
        
        return report