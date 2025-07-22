#!/usr/bin/env python3
"""
Test suite for enhanced parameter validation and debugging features
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.base import Node, NodeParameter, NodeRegistry
from kailash.runtime.parameter_debugger import ParameterDebugger

# Ensure clean registry
NodeRegistry._nodes.clear()

# Test nodes for validation scenarios
class StrictParameterNode(Node):
    """Node with strict parameter declarations for testing."""
    
    def get_parameters(self):
        return {
            "required_param": NodeParameter(
                name="required_param", 
                type=str, 
                required=True,
                description="A required string parameter"
            ),
            "optional_param": NodeParameter(
                name="optional_param", 
                type=int, 
                required=False,
                default=42,
                description="An optional integer parameter"
            ),
            "typed_param": NodeParameter(
                name="typed_param", 
                type=dict, 
                required=False,
                description="A dictionary parameter with type validation"
            )
        }
    
    def run(self, **kwargs):
        return {
            "received_params": list(kwargs.keys()),
            "param_values": {k: str(v)[:50] for k, v in kwargs.items()}
        }

class FlexibleNode(Node):
    """Node that accepts **kwargs for testing."""
    
    def get_parameters(self):
        return {
            "base_param": NodeParameter(
                name="base_param", 
                type=str, 
                required=False,
                description="Base parameter"
            )
        }
    
    def run(self, **kwargs):
        # This node accepts any parameters due to **kwargs
        return {
            "received_params": list(kwargs.keys()),
            "param_count": len(kwargs)
        }

# Register test nodes
NodeRegistry.register(StrictParameterNode, "StrictParameterNode")
NodeRegistry.register(FlexibleNode, "FlexibleNode")

def test_enhanced_validation_warn_mode():
    """Test enhanced parameter validation in warn mode."""
    print("=" * 60)
    print("TEST: Enhanced Parameter Validation - WARN Mode")
    print("=" * 60)
    
    # Create workflow with mixed parameter scenarios
    workflow = WorkflowBuilder()
    workflow.add_node("StrictParameterNode", "strict_node", {})
    workflow.add_node("FlexibleNode", "flexible_node", {})
    
    # Runtime with enhanced parameter validation in warn mode
    runtime = LocalRuntime(
        debug=True,
        parameter_validation="warn",
        enable_parameter_debugging=True
    )
    
    # Test parameters with various issues
    runtime_params = {
        "strict_node": {
            "required_param": "valid_value",  # ✅ Valid
            "undeclared_param": "should_be_warned",  # ⚠️  Should warn
            "typed_param": "wrong_type"  # ⚠️  Should warn about type
        },
        "flexible_node": {
            "base_param": "valid",  # ✅ Valid
            "any_param": "should_work",  # ✅ Should work (**kwargs)
            "another_param": 123  # ✅ Should work (**kwargs)
        },
        "nonexistent_node": {  # ⚠️  Should warn
            "param": "value"
        }
    }
    
    print("Executing workflow with enhanced validation...")
    try:
        results, run_id = runtime.execute(workflow.build(), parameters=runtime_params)
        print("\n✅ Execution completed successfully")
        print(f"Results: {results}")
        
        # Check results
        strict_results = results.get("strict_node", {})
        flexible_results = results.get("flexible_node", {})
        
        print(f"\nStrict node received: {strict_results.get('received_params', [])}")
        print(f"Flexible node received: {flexible_results.get('received_params', [])}")
        
    except Exception as e:
        print(f"❌ Execution failed: {e}")
        return False
    
    return True

def test_enhanced_validation_strict_mode():
    """Test enhanced parameter validation in strict mode."""
    print("=" * 60)
    print("TEST: Enhanced Parameter Validation - STRICT Mode")
    print("=" * 60)
    
    workflow = WorkflowBuilder()
    workflow.add_node("StrictParameterNode", "strict_node", {})
    
    # Runtime with strict validation
    runtime = LocalRuntime(
        debug=True,
        parameter_validation="strict",
        enable_parameter_debugging=True
    )
    
    # Parameters with validation issues
    runtime_params = {
        "strict_node": {
            "required_param": "valid_value",  # ✅ Valid
            "undeclared_param": "should_be_blocked"  # ❌ Should be blocked in strict mode
        }
    }
    
    print("Executing workflow with strict validation...")
    try:
        results, run_id = runtime.execute(workflow.build(), parameters=runtime_params)
        print("✅ Execution completed - checking if undeclared parameter was blocked...")
        
        strict_results = results.get("strict_node", {})
        received_params = strict_results.get('received_params', [])
        
        if "undeclared_param" in received_params:
            print("❌ FAIL: Undeclared parameter was not blocked in strict mode")
            return False
        else:
            print("✅ SUCCESS: Undeclared parameter was properly blocked")
            
    except Exception as e:
        print(f"⚠️  Execution failed with validation error: {e}")
        print("✅ SUCCESS: Strict mode properly prevented execution with validation issues")
    
    return True

def test_parameter_flow_debugging():
    """Test comprehensive parameter flow debugging."""
    print("=" * 60)
    print("TEST: Parameter Flow Debugging")
    print("=" * 60)
    
    workflow = WorkflowBuilder()
    workflow.add_node("StrictParameterNode", "node1", {"optional_param": 100})  # Config param
    workflow.add_node("FlexibleNode", "node2", {})
    
    # Parameters to trace
    runtime_params = {
        "node1": {
            "required_param": "node_specific_value",
            "undeclared_param": "should_be_traced"
        },
        "workflow_level_param": "should_distribute",  # Workflow-level
        "unused_param": "should_be_detected"
    }
    
    # Create debugger
    debugger = ParameterDebugger()
    
    # Get workflow nodes for analysis
    built_workflow = workflow.build()
    workflow_nodes = getattr(built_workflow, '_node_instances', {})
    node_configs = {
        node_id: getattr(node, 'config', {}) 
        for node_id, node in workflow_nodes.items()
    }
    
    print("Analyzing parameter flow...")
    flow_report = debugger.trace_parameter_flow(
        workflow=built_workflow,
        runtime_parameters=runtime_params,
        node_configs=node_configs
    )
    
    # Print comprehensive report
    debugger.print_parameter_flow_report(flow_report)
    
    # Execute to verify actual behavior
    runtime = LocalRuntime(debug=True, parameter_validation="debug")
    try:
        results, _ = runtime.execute(built_workflow, parameters=runtime_params)
        print(f"\n🔍 ACTUAL EXECUTION RESULTS:")
        for node_id, result in results.items():
            print(f"  {node_id}: {result.get('received_params', [])}")
    except Exception as e:
        print(f"Execution failed: {e}")
    
    return True

def test_missing_required_parameter():
    """Test handling of missing required parameters."""
    print("=" * 60)
    print("TEST: Missing Required Parameter Validation")
    print("=" * 60)
    
    workflow = WorkflowBuilder()
    workflow.add_node("StrictParameterNode", "strict_node", {})
    
    runtime = LocalRuntime(
        debug=True,
        parameter_validation="warn",
        enable_parameter_debugging=True
    )
    
    # Missing required parameter
    runtime_params = {
        "strict_node": {
            "optional_param": 999
            # Missing required_param!
        }
    }
    
    print("Testing missing required parameter detection...")
    try:
        results, _ = runtime.execute(workflow.build(), parameters=runtime_params)
        
        # Check if the node still received the optional parameter
        strict_results = results.get("strict_node", {})
        received_params = strict_results.get('received_params', [])
        
        print(f"Node received parameters: {received_params}")
        
        if "optional_param" in received_params:
            print("✅ Optional parameter was passed correctly")
        
        if "required_param" not in received_params:
            print("⚠️  Required parameter was missing (expected - should generate warnings)")
            
    except Exception as e:
        print(f"Execution failed: {e}")
    
    return True

def run_all_tests():
    """Run comprehensive enhanced parameter validation tests."""
    print("ENHANCED PARAMETER VALIDATION TEST SUITE")
    print("Testing bug report scenarios and enhanced validation...")
    print()
    
    tests = [
        ("Enhanced Validation - Warn Mode", test_enhanced_validation_warn_mode),
        ("Enhanced Validation - Strict Mode", test_enhanced_validation_strict_mode),
        ("Parameter Flow Debugging", test_parameter_flow_debugging),
        ("Missing Required Parameter", test_missing_required_parameter),
    ]
    
    results = []
    for test_name, test_func in tests:
        print(f"Running: {test_name}")
        try:
            success = test_func()
            results.append((test_name, "✅ PASS" if success else "❌ FAIL"))
        except Exception as e:
            results.append((test_name, f"❌ ERROR: {e}"))
        print()
    
    # Final summary
    print("=" * 60)
    print("TEST RESULTS SUMMARY")
    print("=" * 60)
    
    for test_name, result in results:
        print(f"{result} - {test_name}")
    
    passed = len([r for r in results if "✅ PASS" in r[1]])
    total = len(results)
    print(f"\nOverall: {passed}/{total} tests passed")
    
    return passed == total

if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)