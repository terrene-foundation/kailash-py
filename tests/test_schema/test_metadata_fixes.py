"""Test script to verify metadata and method fixes."""
import sys
import traceback

tests_passed = 0
tests_failed = 0

def test_node_structure(module_path, class_name):
    """Test importing a class and checking its structure without instantiation."""
    global tests_passed, tests_failed
    try:
        # Dynamic import
        module = __import__(module_path, fromlist=[class_name])
        cls = getattr(module, class_name)
        
        # Verify metadata
        if hasattr(cls, 'metadata'):
            metadata = cls.metadata
            # Check that metadata doesn't have invalid 'parameters' field
            if hasattr(metadata, 'parameters'):
                print(f"✗ {module_path}.{class_name}: metadata has invalid 'parameters' field")
                tests_failed += 1
                return
            # Check required metadata fields
            required_fields = ['name', 'description', 'version']
            for field in required_fields:
                if not hasattr(metadata, field):
                    print(f"✗ {module_path}.{class_name}: metadata missing '{field}' field")
                    tests_failed += 1
                    return
            print(f"✓ {module_path}.{class_name}: metadata is valid")
        else:
            print(f"✓ {module_path}.{class_name}: imported successfully")
        
        # Check for required methods without instantiating
        if not hasattr(cls, 'get_parameters'):
            print(f"✗ {module_path}.{class_name}: missing get_parameters method")
            tests_failed += 1
            return
            
        if not hasattr(cls, 'run'):
            print(f"✗ {module_path}.{class_name}: missing run method")
            tests_failed += 1
            return
            
        print(f"✓ {module_path}.{class_name}: has required methods")
        tests_passed += 1
        
    except Exception as e:
        print(f"✗ {module_path}.{class_name}: {type(e).__name__}: {e}")
        traceback.print_exc()
        tests_failed += 1

# Test our fixed nodes
print("Testing vector_db nodes...")
test_node_structure("kailash.nodes.data.vector_db", "EmbeddingNode")
test_node_structure("kailash.nodes.data.vector_db", "VectorDatabaseNode")
test_node_structure("kailash.nodes.data.vector_db", "TextSplitterNode")

print("\nTesting streaming nodes...")
test_node_structure("kailash.nodes.data.streaming", "KafkaConsumerNode")
test_node_structure("kailash.nodes.data.streaming", "StreamPublisherNode")
test_node_structure("kailash.nodes.data.streaming", "WebSocketNode") 
test_node_structure("kailash.nodes.data.streaming", "EventStreamNode")

print("\nTesting code nodes...")
# Fix import path - it's in kailash.nodes.code.python
test_node_structure("kailash.nodes.code.python", "PythonCodeNode")

# Test tracking models
print("\nTesting tracking models...")
try:
    from kailash.tracking.models import TaskRun, WorkflowRun
    
    # Try creating instances to ensure validators work
    task = TaskRun(run_id="test", node_id="node1", node_type="test_type")
    print("✓ TaskRun: Created successfully with pydantic v2 validators")
    tests_passed += 1
    
    workflow = WorkflowRun(workflow_name="test_workflow")
    print("✓ WorkflowRun: Created successfully with pydantic v2 validators")
    tests_passed += 1
    
except Exception as e:
    print(f"✗ Tracking models: {type(e).__name__}: {e}")
    traceback.print_exc()
    tests_failed += 1

print(f"\n=== Summary ===")
print(f"Tests passed: {tests_passed}")
print(f"Tests failed: {tests_failed}")
print(f"Total tests: {tests_passed + tests_failed}")

if tests_failed > 0:
    sys.exit(1)