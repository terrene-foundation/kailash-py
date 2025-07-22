#!/usr/bin/env python3
"""
EXACT Bug Reproduction Test - Following the bug report precisely
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.base import Node, NodeParameter, NodeRegistry

# Ensure clean registry
NodeRegistry._nodes.clear()

# 1. Define a node EXACTLY as in the bug report
class TestNode(Node):
    def get_parameters(self):
        return {
            "param1": NodeParameter(name="param1", type=str, required=False),
            "param2": NodeParameter(name="param2", type=dict, required=False)
        }
    
    def run(self, **kwargs):
        print(f"TestNode.run called with kwargs: {kwargs}")
        return {"received_params": list(kwargs.keys())}

# Register the node
NodeRegistry.register(TestNode, "TestNode")

def test_exact_bug_scenario():
    """Test the EXACT scenario from the bug report"""
    print("=" * 50)
    print("TESTING EXACT BUG SCENARIO")
    print("=" * 50)
    
    # 2. Create workflow with empty node config - EXACTLY as in bug report
    workflow = WorkflowBuilder()
    workflow.add_node("TestNode", "test_node", {})  # Empty config!
    
    print("✓ Workflow created with empty node config: {}")
    print("✓ All node parameters are optional (required=False)")
    print("✓ No workflow connections")
    
    # 3. Execute with runtime parameters - EXACTLY as in bug report
    runtime = LocalRuntime(debug=True)
    
    runtime_params = {
        "test_node": {
            "param1": "value1",
            "param2": {"key": "value"}
        }
    }
    
    print(f"✓ Runtime parameters provided: {runtime_params}")
    print()
    
    try:
        results, _ = runtime.execute(workflow.build(), parameters=runtime_params)
        
        print("RESULTS:")
        print(f"  Full results: {results}")
        print(f"  Node results: {results.get('test_node', 'NO RESULTS')}")
        
        if "test_node" in results:
            received_params = results["test_node"].get("received_params", [])
            print(f"  Received parameters: {received_params}")
            
            # Test the bug claim
            if len(received_params) == 0:
                print("🔴 BUG CONFIRMED: Node received NO parameters")
                return False
            elif "param1" in received_params and "param2" in received_params:
                print("🟢 BUG NOT REPRODUCED: Node received expected parameters")
                return True
            else:
                print(f"🟡 PARTIAL BUG: Node received {received_params} but expected ['param1', 'param2']")
                return False
        else:
            print("🔴 CRITICAL: Node did not execute at all")
            return False
            
    except Exception as e:
        print(f"🔴 ERROR during execution: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_workaround_1_add_config():
    """Test workaround 1: Add any config value"""
    print("=" * 50)
    print("TESTING WORKAROUND 1: Add config value")
    print("=" * 50)
    
    workflow = WorkflowBuilder()
    workflow.add_node("TestNode", "test_node", {"param1": None})  # Add config!
    
    runtime = LocalRuntime(debug=True)
    runtime_params = {
        "test_node": {
            "param1": "value1",
            "param2": {"key": "value"}
        }
    }
    
    try:
        results, _ = runtime.execute(workflow.build(), parameters=runtime_params)
        received_params = results["test_node"]["received_params"]
        print(f"  Workaround 1 results: {received_params}")
        return len(received_params) > 0
    except Exception as e:
        print(f"🔴 Workaround 1 failed: {e}")
        return False

def test_workaround_3_workflow_level():
    """Test workaround 3: Use workflow-level parameters"""
    print("=" * 50)
    print("TESTING WORKAROUND 3: Workflow-level parameters")
    print("=" * 50)
    
    workflow = WorkflowBuilder()
    workflow.add_node("TestNode", "test_node", {})  # Empty config
    
    runtime = LocalRuntime(debug=True)
    # Use workflow-level parameters instead of node-specific
    runtime_params = {
        "param1": "value1",  # Not nested under node_id
        "param2": {"key": "value"}
    }
    
    try:
        results, _ = runtime.execute(workflow.build(), parameters=runtime_params)
        received_params = results["test_node"]["received_params"]
        print(f"  Workaround 3 results: {received_params}")
        return len(received_params) > 0
    except Exception as e:
        print(f"🔴 Workaround 3 failed: {e}")
        return False

if __name__ == "__main__":
    print("EXACT BUG REPRODUCTION TEST")
    print("Following the bug report step by step...")
    print()
    
    # Test the exact bug scenario
    bug_exists = not test_exact_bug_scenario()
    print()
    
    if bug_exists:
        print("🔴 BUG CONFIRMED - Testing workarounds...")
        print()
        
        # Test workarounds
        workaround1_works = test_workaround_1_add_config()
        print()
        
        workaround3_works = test_workaround_3_workflow_level()
        print()
        
        print("=" * 50)
        print("SUMMARY")
        print("=" * 50)
        print("🔴 Main bug: CONFIRMED")
        print(f"🟢 Workaround 1 (add config): {'WORKS' if workaround1_works else 'FAILS'}")
        print(f"🟢 Workaround 3 (workflow-level): {'WORKS' if workaround3_works else 'FAILS'}")
        
        if workaround1_works or workaround3_works:
            print("\n✓ At least one workaround is functional")
            print("✓ This confirms the bug is in the specific edge case logic")
        else:
            print("\n🔴 NO workarounds work - deeper issue")
            
    else:
        print("🟢 BUG NOT REPRODUCED - Runtime parameter injection working correctly")
        
    print("\nTest complete.")