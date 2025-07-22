"""Parameter debugging utilities for runtime parameter injection troubleshooting.

This module provides comprehensive debugging tools to help users understand
parameter flow, identify issues, and troubleshoot parameter injection problems.
"""
import json
import logging
from typing import Dict, List, Any, Set, Optional, Tuple
from dataclasses import dataclass, asdict
from enum import Enum

from kailash.nodes.base import Node, NodeParameter
from kailash.workflow import Workflow

logger = logging.getLogger(__name__)


@dataclass
class ParameterFlowStep:
    """Represents a step in parameter flow analysis."""
    step: str
    source: str
    target: str
    parameter_name: str
    parameter_value: Any
    status: str  # "passed", "blocked", "transformed", "ignored"
    reason: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for logging."""
        return {
            "step": self.step,
            "source": self.source,
            "target": self.target,
            "parameter_name": self.parameter_name,
            "parameter_value": str(self.parameter_value)[:100] if self.parameter_value else None,
            "status": self.status,
            "reason": self.reason
        }


@dataclass 
class NodeParameterInfo:
    """Information about a node's parameter capabilities."""
    node_id: str
    node_class: str
    declared_parameters: Dict[str, Dict[str, Any]]
    accepts_kwargs: bool
    config_parameters: Dict[str, Any]
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for reporting."""
        return {
            "node_id": self.node_id,
            "node_class": self.node_class,
            "declared_parameters": self.declared_parameters,
            "accepts_kwargs": self.accepts_kwargs,
            "config_parameters": self.config_parameters
        }


class ParameterDebugger:
    """Comprehensive parameter debugging utility."""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.flow_steps: List[ParameterFlowStep] = []
        
    def trace_parameter_flow(
        self,
        workflow: Workflow,
        runtime_parameters: Dict[str, Any],
        node_configs: Optional[Dict[str, Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """
        Trace parameter flow through the workflow.
        
        Args:
            workflow: Workflow to analyze
            runtime_parameters: Runtime parameters provided
            node_configs: Optional node configurations
            
        Returns:
            Comprehensive parameter flow analysis
        """
        self.flow_steps = []
        node_configs = node_configs or {}
        
        # Get workflow nodes
        workflow_nodes = getattr(workflow, '_node_instances', {})
        if not workflow_nodes:
            workflow_nodes = {node_id: node for node_id, node in workflow.nodes.items()}
            
        # Analyze node parameter capabilities
        node_info = self._analyze_node_capabilities(workflow_nodes)
        
        # Trace parameter format separation
        node_specific_params, workflow_level_params = self._separate_parameters(
            runtime_parameters, workflow_nodes.keys()
        )
        
        # Trace node-specific parameter injection
        node_injection_results = {}
        for node_id, params in node_specific_params.items():
            if node_id in workflow_nodes:
                results = self._trace_node_parameter_injection(
                    node_id, workflow_nodes[node_id], params, node_configs.get(node_id, {})
                )
                node_injection_results[node_id] = results
            else:
                self.flow_steps.append(ParameterFlowStep(
                    step="node_lookup",
                    source="runtime",
                    target=node_id,
                    parameter_name="*",
                    parameter_value=params,
                    status="blocked",
                    reason=f"Node '{node_id}' not found in workflow"
                ))
        
        # Trace workflow-level parameter distribution
        workflow_distribution_results = {}
        if workflow_level_params:
            workflow_distribution_results = self._trace_workflow_parameter_distribution(
                workflow_nodes, workflow_level_params
            )
        
        # Generate comprehensive report
        report = {
            "parameter_format_analysis": {
                "node_specific_parameters": {
                    node_id: list(params.keys()) 
                    for node_id, params in node_specific_params.items()
                },
                "workflow_level_parameters": list(workflow_level_params.keys())
            },
            "node_capabilities": [info.to_dict() for info in node_info.values()],
            "parameter_flow_trace": [step.to_dict() for step in self.flow_steps],
            "injection_results": {
                "node_specific": node_injection_results,
                "workflow_level": workflow_distribution_results
            },
            "summary": self._generate_flow_summary()
        }
        
        return report
    
    def _analyze_node_capabilities(
        self, workflow_nodes: Dict[str, Node]
    ) -> Dict[str, NodeParameterInfo]:
        """Analyze parameter capabilities of each node."""
        node_info = {}
        
        for node_id, node_instance in workflow_nodes.items():
            # Get declared parameters
            declared_params = {}
            try:
                param_defs = node_instance.get_parameters()
                for param_name, param_def in param_defs.items():
                    declared_params[param_name] = {
                        "type": getattr(param_def, 'type', None).__name__ if hasattr(param_def, 'type') and param_def.type else "any",
                        "required": getattr(param_def, 'required', False),
                        "default": getattr(param_def, 'default', None),
                        "description": getattr(param_def, 'description', ""),
                        "workflow_alias": getattr(param_def, 'workflow_alias', None),
                        "auto_map_from": getattr(param_def, 'auto_map_from', None)
                    }
            except Exception as e:
                declared_params = {"error": f"Failed to get parameters: {e}"}
            
            # Check if node accepts **kwargs
            accepts_kwargs = self._node_accepts_kwargs(node_instance)
            
            # Get node configuration
            config_params = getattr(node_instance, 'config', {})
            
            node_info[node_id] = NodeParameterInfo(
                node_id=node_id,
                node_class=node_instance.__class__.__name__,
                declared_parameters=declared_params,
                accepts_kwargs=accepts_kwargs,
                config_parameters=config_params
            )
            
        return node_info
    
    def _separate_parameters(
        self, parameters: Dict[str, Any], node_ids: Set[str]
    ) -> Tuple[Dict[str, Dict[str, Any]], Dict[str, Any]]:
        """Separate node-specific from workflow-level parameters with tracing."""
        node_specific = {}
        workflow_level = {}
        
        for key, value in parameters.items():
            if key in node_ids and isinstance(value, dict):
                node_specific[key] = value
                self.flow_steps.append(ParameterFlowStep(
                    step="parameter_separation",
                    source="runtime",
                    target=key,
                    parameter_name="*",
                    parameter_value=list(value.keys()) if isinstance(value, dict) else value,
                    status="passed",
                    reason="Recognized as node-specific parameters"
                ))
            else:
                workflow_level[key] = value
                self.flow_steps.append(ParameterFlowStep(
                    step="parameter_separation",
                    source="runtime",
                    target="workflow",
                    parameter_name=key,
                    parameter_value=value,
                    status="passed",
                    reason="Classified as workflow-level parameter"
                ))
        
        return node_specific, workflow_level
    
    def _trace_node_parameter_injection(
        self,
        node_id: str,
        node_instance: Node,
        runtime_params: Dict[str, Any],
        node_config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Trace parameter injection for a specific node."""
        param_defs = {}
        try:
            param_defs = node_instance.get_parameters()
        except Exception as e:
            self.flow_steps.append(ParameterFlowStep(
                step="parameter_definition_lookup",
                source=node_id,
                target=node_id,
                parameter_name="*",
                parameter_value=None,
                status="blocked",
                reason=f"Failed to get parameter definitions: {e}"
            ))
            return {"error": str(e)}
        
        injection_results = {
            "declared_parameters": list(param_defs.keys()),
            "provided_parameters": list(runtime_params.keys()),
            "injected_parameters": [],
            "blocked_parameters": [],
            "parameter_details": {}
        }
        
        # Check each provided parameter
        for param_name, param_value in runtime_params.items():
            if param_name in param_defs:
                # Parameter is declared - should be injected
                injection_results["injected_parameters"].append(param_name)
                injection_results["parameter_details"][param_name] = {
                    "status": "injected",
                    "reason": "Parameter declared in node definition"
                }
                self.flow_steps.append(ParameterFlowStep(
                    step="parameter_injection",
                    source="runtime",
                    target=node_id,
                    parameter_name=param_name,
                    parameter_value=param_value,
                    status="passed",
                    reason="Parameter declared in node.get_parameters()"
                ))
            elif self._node_accepts_kwargs(node_instance):
                # Node accepts arbitrary parameters
                injection_results["injected_parameters"].append(param_name)
                injection_results["parameter_details"][param_name] = {
                    "status": "injected",
                    "reason": "Node accepts **kwargs parameters"
                }
                self.flow_steps.append(ParameterFlowStep(
                    step="parameter_injection",
                    source="runtime",
                    target=node_id,
                    parameter_name=param_name,
                    parameter_value=param_value,
                    status="passed",
                    reason="Node accepts **kwargs (undeclared parameters allowed)"
                ))
            else:
                # Parameter will be blocked
                injection_results["blocked_parameters"].append(param_name)
                injection_results["parameter_details"][param_name] = {
                    "status": "blocked",
                    "reason": "Parameter not declared and node doesn't accept **kwargs"
                }
                self.flow_steps.append(ParameterFlowStep(
                    step="parameter_injection",
                    source="runtime",
                    target=node_id,
                    parameter_name=param_name,
                    parameter_value=param_value,
                    status="blocked",
                    reason="Parameter not declared in node.get_parameters() and node doesn't accept **kwargs"
                ))
        
        # Check for missing required parameters
        for param_name, param_def in param_defs.items():
            if (getattr(param_def, 'required', False) and 
                param_name not in runtime_params and 
                param_name not in node_config):
                injection_results["parameter_details"][param_name] = {
                    "status": "missing_required",
                    "reason": "Required parameter not provided"
                }
                self.flow_steps.append(ParameterFlowStep(
                    step="required_parameter_check",
                    source=node_id,
                    target=node_id,
                    parameter_name=param_name,
                    parameter_value=None,
                    status="blocked",
                    reason="Required parameter not provided in runtime parameters or node config"
                ))
        
        return injection_results
    
    def _trace_workflow_parameter_distribution(
        self, workflow_nodes: Dict[str, Node], workflow_params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Trace workflow-level parameter distribution to nodes."""
        distribution_results = {
            "workflow_parameters": list(workflow_params.keys()),
            "distribution_map": {},
            "unused_parameters": []
        }
        
        for param_name, param_value in workflow_params.items():
            accepting_nodes = []
            
            # Check which nodes can accept this parameter
            for node_id, node_instance in workflow_nodes.items():
                try:
                    param_defs = node_instance.get_parameters()
                    
                    if (param_name in param_defs or 
                        self._parameter_matches_alias(param_name, param_defs) or
                        self._node_accepts_kwargs(node_instance)):
                        accepting_nodes.append(node_id)
                        
                        self.flow_steps.append(ParameterFlowStep(
                            step="workflow_parameter_distribution",
                            source="workflow",
                            target=node_id,
                            parameter_name=param_name,
                            parameter_value=param_value,
                            status="passed",
                            reason=f"Node can accept parameter: {self._get_acceptance_reason(param_name, param_defs, node_instance)}"
                        ))
                except Exception as e:
                    self.flow_steps.append(ParameterFlowStep(
                        step="workflow_parameter_distribution",
                        source="workflow",
                        target=node_id,
                        parameter_name=param_name,
                        parameter_value=param_value,
                        status="blocked",
                        reason=f"Failed to check node parameter compatibility: {e}"
                    ))
            
            if accepting_nodes:
                distribution_results["distribution_map"][param_name] = accepting_nodes
            else:
                distribution_results["unused_parameters"].append(param_name)
                self.flow_steps.append(ParameterFlowStep(
                    step="workflow_parameter_distribution",
                    source="workflow",
                    target="*",
                    parameter_name=param_name,
                    parameter_value=param_value,
                    status="blocked",
                    reason="No nodes can accept this workflow parameter"
                ))
        
        return distribution_results
    
    def _node_accepts_kwargs(self, node_instance: Node) -> bool:
        """Check if a node accepts **kwargs."""
        # PythonCodeNode typically accepts **kwargs
        if hasattr(node_instance, '__class__') and "PythonCode" in node_instance.__class__.__name__:
            return True
            
        # Check method signature
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
    
    def _get_acceptance_reason(self, param_name: str, param_defs: Dict[str, NodeParameter], node_instance: Node) -> str:
        """Get reason why a node accepts a parameter."""
        if param_name in param_defs:
            return "direct parameter match"
        
        for param_def in param_defs.values():
            if hasattr(param_def, 'workflow_alias') and param_def.workflow_alias == param_name:
                return "workflow alias match"
            if hasattr(param_def, 'auto_map_from') and param_name in param_def.auto_map_from:
                return "auto-mapping match"
        
        if self._node_accepts_kwargs(node_instance):
            return "node accepts **kwargs"
            
        return "unknown"
    
    def _generate_flow_summary(self) -> Dict[str, Any]:
        """Generate a summary of parameter flow analysis."""
        total_steps = len(self.flow_steps)
        passed_steps = len([s for s in self.flow_steps if s.status == "passed"])
        blocked_steps = len([s for s in self.flow_steps if s.status == "blocked"])
        
        # Group issues by reason
        blocking_reasons = {}
        for step in self.flow_steps:
            if step.status == "blocked" and step.reason:
                if step.reason not in blocking_reasons:
                    blocking_reasons[step.reason] = 0
                blocking_reasons[step.reason] += 1
        
        return {
            "total_parameter_operations": total_steps,
            "successful_operations": passed_steps,
            "blocked_operations": blocked_steps,
            "success_rate": f"{(passed_steps / total_steps * 100):.1f}%" if total_steps > 0 else "0%",
            "common_blocking_reasons": blocking_reasons,
            "recommendations": self._generate_recommendations()
        }
    
    def _generate_recommendations(self) -> List[str]:
        """Generate troubleshooting recommendations based on flow analysis."""
        recommendations = []
        
        # Check for common issues
        blocked_undeclared = len([
            s for s in self.flow_steps 
            if s.status == "blocked" and "not declared" in s.reason.lower()
        ])
        
        if blocked_undeclared > 0:
            recommendations.append(
                f"Found {blocked_undeclared} parameters blocked due to missing declarations. "
                "Add these parameters to the node's get_parameters() method."
            )
        
        missing_nodes = len([
            s for s in self.flow_steps 
            if s.status == "blocked" and "not found" in s.reason.lower()
        ])
        
        if missing_nodes > 0:
            recommendations.append(
                f"Found {missing_nodes} references to non-existent nodes. "
                "Check node ID spelling in runtime parameters."
            )
        
        unused_workflow_params = len([
            s for s in self.flow_steps 
            if s.step == "workflow_parameter_distribution" and s.status == "blocked"
        ])
        
        if unused_workflow_params > 0:
            recommendations.append(
                f"Found {unused_workflow_params} unused workflow-level parameters. "
                "Consider removing them or adding parameter declarations to nodes."
            )
        
        return recommendations
    
    def print_parameter_flow_report(self, report: Dict[str, Any]):
        """Print a human-readable parameter flow report."""
        print("=" * 60)
        print("PARAMETER FLOW ANALYSIS REPORT")
        print("=" * 60)
        
        # Summary
        summary = report["summary"]
        print(f"\n📊 SUMMARY:")
        print(f"  Total Operations: {summary['total_parameter_operations']}")
        print(f"  Success Rate: {summary['success_rate']}")
        print(f"  Blocked Operations: {summary['blocked_operations']}")
        
        # Parameter format analysis
        format_analysis = report["parameter_format_analysis"]
        print(f"\n📋 PARAMETER FORMAT:")
        print(f"  Node-specific parameters: {len(format_analysis['node_specific_parameters'])} nodes")
        for node_id, params in format_analysis['node_specific_parameters'].items():
            print(f"    {node_id}: {params}")
        print(f"  Workflow-level parameters: {format_analysis['workflow_level_parameters']}")
        
        # Common blocking reasons
        if summary["common_blocking_reasons"]:
            print(f"\n🚫 COMMON ISSUES:")
            for reason, count in summary["common_blocking_reasons"].items():
                print(f"  ({count}x) {reason}")
        
        # Recommendations
        if summary["recommendations"]:
            print(f"\n💡 RECOMMENDATIONS:")
            for i, rec in enumerate(summary["recommendations"], 1):
                print(f"  {i}. {rec}")
        
        print("\n" + "=" * 60)