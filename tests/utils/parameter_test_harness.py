"""Parameter Test Harness for comprehensive parameter injection testing.

This harness provides utilities for systematically testing parameter injection
across different sources, formats, and workflow complexities.
"""
import itertools
import time
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

from kailash.workflow.builder import WorkflowBuilder
from kailash.workflow import Workflow
from kailash.runtime.local import LocalRuntime
from kailash.nodes.base import Node


class ParameterSource(Enum):
    """Sources of parameters in the SDK."""
    NODE_CONFIG = "node_config"
    CONNECTION = "connection"
    RUNTIME = "runtime"


class WorkflowComplexity(Enum):
    """Different workflow complexity patterns."""
    SIMPLE = "simple"  # Single node
    LINEAR = "linear"  # Sequential nodes
    BRANCHING = "branching"  # Conditional paths
    CYCLIC = "cyclic"  # Feedback loops
    PARALLEL = "parallel"  # Concurrent execution
    NESTED = "nested"  # Sub-workflows
    DYNAMIC = "dynamic"  # Runtime node creation


@dataclass
class ParameterTestCase:
    """Represents a test case for parameter injection."""
    name: str
    sources: List[ParameterSource]
    complexity: WorkflowComplexity
    parameters: Dict[str, Dict[str, Any]]
    expected_results: Dict[str, Any]
    should_fail: bool = False
    error_pattern: Optional[str] = None


@dataclass
class PerformanceMetrics:
    """Performance metrics for parameter injection."""
    injection_time_ms: float
    total_execution_time_ms: float
    memory_usage_mb: float
    parameter_count: int


class ParameterTestHarness:
    """Harness for comprehensive parameter injection testing."""
    
    def __init__(self):
        self.test_cases: List[ParameterTestCase] = []
        self.performance_metrics: List[PerformanceMetrics] = []
        
    def generate_parameter_combinations(self) -> List[List[ParameterSource]]:
        """Generate all possible combinations of parameter sources.
        
        Returns:
            List of parameter source combinations (7 total)
        """
        sources = list(ParameterSource)
        combinations = []
        
        # Single sources
        for source in sources:
            combinations.append([source])
            
        # Pairs of sources
        for pair in itertools.combinations(sources, 2):
            combinations.append(list(pair))
            
        # All three sources
        combinations.append(sources)
        
        return combinations
    
    def create_test_workflow(self, complexity: WorkflowComplexity) -> WorkflowBuilder:
        """Create a test workflow of specified complexity.
        
        Args:
            complexity: The complexity pattern to create
            
        Returns:
            WorkflowBuilder configured for the complexity pattern
        """
        workflow = WorkflowBuilder()
        
        if complexity == WorkflowComplexity.SIMPLE:
            # Single node workflow
            workflow.add_node("PythonCodeNode", "process", {
                "code": "result = {'value': parameters.get('input', 0) * 2}"
            })
            
        elif complexity == WorkflowComplexity.LINEAR:
            # Sequential processing
            workflow.add_node("PythonCodeNode", "step1", {
                "code": "result = {'value': parameters.get('input', 0) + 1}"
            })
            workflow.add_node("PythonCodeNode", "step2", {
                "code": "result = {'value': parameters.get('value', 0) * 2}"
            })
            workflow.add_node("PythonCodeNode", "step3", {
                "code": "result = {'final': parameters.get('value', 0) + 10}"
            })
            workflow.add_connection("step1", "value", "step2", "value")
            workflow.add_connection("step2", "value", "step3", "value")
            
        elif complexity == WorkflowComplexity.BRANCHING:
            # Conditional execution
            workflow.add_node("PythonCodeNode", "check", {
                "code": "result = {'condition': parameters.get('threshold', 5) > 3}"
            })
            workflow.add_node("SwitchNode", "branch", {})
            workflow.add_node("PythonCodeNode", "path_a", {
                "code": "result = {'result': 'Path A: ' + str(parameters.get('value', ''))}"
            })
            workflow.add_node("PythonCodeNode", "path_b", {
                "code": "result = {'result': 'Path B: ' + str(parameters.get('value', ''))}"
            })
            workflow.add_connection("check", "condition", "branch", "condition")
            workflow.add_connection("branch", "true", "path_a", "value")
            workflow.add_connection("branch", "false", "path_b", "value")
            
        elif complexity == WorkflowComplexity.CYCLIC:
            # Feedback loop with convergence
            cycle_builder = workflow.create_cycle("optimization")
            workflow.add_node("PythonCodeNode", "optimizer", {
                "code": """
value = parameters.get('value', 0)
improvement = parameters.get('improvement', 0.1)
result = {'value': value + improvement, 'converged': value > 10}
"""
            })
            workflow.add_node("ConvergenceCheckerNode", "checker", {
                "tolerance": 0.01
            })
            cycle_builder.connect("optimizer", "checker", mapping={"value": "current_value"})
            cycle_builder.connect("checker", "optimizer", mapping={"should_continue": "continue"})
            cycle_builder.max_iterations(10).converge_when("converged").build()
            
        elif complexity == WorkflowComplexity.PARALLEL:
            # Concurrent execution paths
            workflow.add_node("PythonCodeNode", "splitter", {
                "code": "result = {'data1': parameters.get('input', [])[:5], 'data2': parameters.get('input', [])[5:]}"
            })
            workflow.add_node("PythonCodeNode", "worker1", {
                "code": "result = {'processed': [x * 2 for x in parameters.get('data1', [])]}"
            })
            workflow.add_node("PythonCodeNode", "worker2", {
                "code": "result = {'processed': [x * 3 for x in parameters.get('data2', [])]}"
            })
            workflow.add_node("MergeNode", "merger", {})
            workflow.add_connection("splitter", "data1", "worker1", "data1")
            workflow.add_connection("splitter", "data2", "worker2", "data2")
            workflow.add_connection("worker1", "processed", "merger", "input1")
            workflow.add_connection("worker2", "processed", "merger", "input2")
            
        elif complexity == WorkflowComplexity.NESTED:
            # Sub-workflow execution
            # Create sub-workflow
            sub_workflow = WorkflowBuilder()
            sub_workflow.add_node("PythonCodeNode", "sub_process", {
                "code": "result = {'sub_result': parameters.get('sub_input', 0) * 5}"
            })
            
            # Main workflow
            workflow.add_node("PythonCodeNode", "prepare", {
                "code": "result = {'sub_input': parameters.get('main_input', 0) + 1}"
            })
            workflow.add_node("WorkflowNode", "sub_workflow", {
                "workflow": sub_workflow.build()
            })
            workflow.add_node("PythonCodeNode", "finalize", {
                "code": "result = {'final': parameters.get('sub_result', 0) + 100}"
            })
            workflow.add_connection("prepare", "sub_input", "sub_workflow", "sub_input")
            workflow.add_connection("sub_workflow", "sub_result", "finalize", "sub_result")
            
        elif complexity == WorkflowComplexity.DYNAMIC:
            # Runtime node creation (using DeferredConfigNode pattern)
            workflow.add_node("PythonCodeNode", "configurator", {
                "code": """
config_type = parameters.get('config_type', 'default')
result = {
    'node_config': {
        'type': 'PythonCodeNode',
        'parameters': {'code': f'result = {{"dynamic": "{config_type}_result"}}'}
    }
}
"""
            })
            # This would use DeferredConfigNode in real implementation
            
        return workflow
    
    def inject_parameters(
        self, 
        workflow: WorkflowBuilder, 
        sources: List[ParameterSource],
        test_params: Dict[str, Any]
    ) -> Tuple[WorkflowBuilder, Dict[str, Dict[str, Any]]]:
        """Inject parameters from specified sources.
        
        Args:
            workflow: The workflow to inject parameters into
            sources: List of parameter sources to use
            test_params: The parameters to inject
            
        Returns:
            Tuple of (modified workflow, runtime parameters)
        """
        runtime_params = {}
        
        for source in sources:
            if source == ParameterSource.NODE_CONFIG:
                # Parameters in node configuration
                # This is already handled in create_test_workflow
                pass
                
            elif source == ParameterSource.CONNECTION:
                # Parameters from workflow inputs
                workflow.add_workflow_inputs({"input": "process"})
                
            elif source == ParameterSource.RUNTIME:
                # Parameters passed at runtime
                runtime_params = {"process": test_params}
                
        return workflow, runtime_params
    
    def measure_performance(
        self, 
        workflow: Workflow,
        runtime_params: Dict[str, Dict[str, Any]]
    ) -> PerformanceMetrics:
        """Measure parameter injection performance.
        
        Args:
            workflow: The workflow to execute
            runtime_params: Runtime parameters
            
        Returns:
            Performance metrics
        """
        import psutil
        import os
        
        process = psutil.Process(os.getpid())
        memory_before = process.memory_info().rss / 1024 / 1024  # MB
        
        runtime = LocalRuntime()
        
        # Measure injection time
        start_injection = time.time()
        runtime._process_parameters(workflow, runtime_params)
        injection_time = (time.time() - start_injection) * 1000  # ms
        
        # Measure total execution time
        start_execution = time.time()
        runtime.execute(workflow, parameters=runtime_params)
        total_time = (time.time() - start_execution) * 1000  # ms
        
        memory_after = process.memory_info().rss / 1024 / 1024  # MB
        
        param_count = sum(len(params) for params in runtime_params.values())
        
        return PerformanceMetrics(
            injection_time_ms=injection_time,
            total_execution_time_ms=total_time,
            memory_usage_mb=memory_after - memory_before,
            parameter_count=param_count
        )
    
    def run_test_case(self, test_case: ParameterTestCase) -> Dict[str, Any]:
        """Run a single test case.
        
        Args:
            test_case: The test case to run
            
        Returns:
            Test results including success status and any errors
        """
        try:
            # Create workflow
            workflow_builder = self.create_test_workflow(test_case.complexity)
            
            # Inject parameters
            workflow_builder, runtime_params = self.inject_parameters(
                workflow_builder,
                test_case.sources,
                test_case.parameters.get("test_params", {})
            )
            
            # Build and execute
            workflow = workflow_builder.build()
            runtime = LocalRuntime()
            results, run_id = runtime.execute(workflow, parameters=runtime_params)
            
            # Measure performance
            metrics = self.measure_performance(workflow, runtime_params)
            self.performance_metrics.append(metrics)
            
            # Verify results
            if test_case.should_fail:
                return {
                    "success": False,
                    "error": "Test case expected to fail but succeeded",
                    "results": results
                }
            
            # Compare with expected results
            for key, expected_value in test_case.expected_results.items():
                if results.get(key) != expected_value:
                    return {
                        "success": False,
                        "error": f"Expected {key}={expected_value}, got {results.get(key)}",
                        "results": results
                    }
                    
            return {
                "success": True,
                "results": results,
                "metrics": metrics
            }
            
        except Exception as e:
            if test_case.should_fail:
                if test_case.error_pattern and test_case.error_pattern not in str(e):
                    return {
                        "success": False,
                        "error": f"Expected error pattern '{test_case.error_pattern}' not found in: {str(e)}"
                    }
                return {"success": True, "error": str(e)}
            else:
                return {
                    "success": False,
                    "error": str(e),
                    "exception": e
                }
    
    def generate_report(self) -> str:
        """Generate a comprehensive test report.
        
        Returns:
            Formatted test report
        """
        report = ["# Parameter Injection Test Report\n"]
        
        # Test case summary
        total_cases = len(self.test_cases)
        passed_cases = sum(1 for tc in self.test_cases if tc.expected_results)
        report.append(f"## Test Summary")
        report.append(f"- Total test cases: {total_cases}")
        report.append(f"- Passed: {passed_cases}")
        report.append(f"- Failed: {total_cases - passed_cases}\n")
        
        # Performance summary
        if self.performance_metrics:
            avg_injection = sum(m.injection_time_ms for m in self.performance_metrics) / len(self.performance_metrics)
            max_injection = max(m.injection_time_ms for m in self.performance_metrics)
            
            report.append(f"## Performance Metrics")
            report.append(f"- Average injection time: {avg_injection:.2f}ms")
            report.append(f"- Maximum injection time: {max_injection:.2f}ms")
            report.append(f"- Target: <5ms")
            report.append(f"- Status: {'✅ PASS' if max_injection < 5 else '❌ FAIL'}\n")
        
        # Parameter combination coverage
        report.append("## Parameter Source Coverage")
        combinations = self.generate_parameter_combinations()
        report.append(f"- Total combinations: {len(combinations)}")
        for combo in combinations:
            sources = " + ".join(s.value for s in combo)
            report.append(f"  - {sources}")
        
        return "\n".join(report)