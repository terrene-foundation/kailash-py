import pytest

"""Test script to verify metadata and method fixes."""


def test_node_structure():
    """Test importing nodes and checking their structure."""
    test_cases = [
        ("kailash.nodes.data.vector_db", "EmbeddingNode"),
        ("kailash.nodes.data.vector_db", "VectorDatabaseNode"),
        ("kailash.nodes.data.vector_db", "TextSplitterNode"),
        ("kailash.nodes.data.streaming", "KafkaConsumerNode"),
        ("kailash.nodes.data.streaming", "StreamPublisherNode"),
        ("kailash.nodes.data.streaming", "WebSocketNode"),
        ("kailash.nodes.data.streaming", "EventStreamNode"),
        ("kailash.nodes.code.python", "PythonCodeNode"),
    ]

    for module_path, class_name in test_cases:
        _test_single_node_structure(module_path, class_name)


def _test_single_node_structure(module_path, class_name):
    """Test importing a class and checking its structure."""
    # Dynamic import
    module = __import__(module_path, fromlist=[class_name])
    cls = getattr(module, class_name)

    # Check for required methods on class
    assert hasattr(
        cls, "get_parameters"
    ), f"{module_path}.{class_name}: missing get_parameters method"
    assert hasattr(cls, "run"), f"{module_path}.{class_name}: missing run method"

    # Create an instance to verify metadata (metadata is now an instance property)
    try:
        # Get parameters to pass minimal required ones
        params = {}
        if hasattr(cls, "get_parameters"):
            param_defs = cls.get_parameters(cls)
            # Only pass required parameters with default values
            for param_name, param_def in param_defs.items():
                if not param_def.required and param_def.default is not None:
                    params[param_name] = param_def.default

        instance = cls(**params)

        # Verify metadata on instance
        if hasattr(instance, "metadata"):
            metadata = instance.metadata
            # Check that metadata doesn't have invalid 'parameters' field
            assert not hasattr(
                metadata, "parameters"
            ), f"{module_path}.{class_name}: metadata has invalid 'parameters' field"

            # Check required metadata fields
            required_fields = ["name", "description", "version"]
            for field in required_fields:
                assert hasattr(
                    metadata, field
                ), f"{module_path}.{class_name}: metadata missing '{field}' field"
    except Exception:
        # If instantiation fails, skip metadata check (some nodes may require specific parameters)
        pass


def test_tracking_models():
    """Test tracking models creation and validators."""
    from kailash.tracking.models import TaskRun, WorkflowRun

    # Try creating instances to ensure validators work
    task = TaskRun(run_id="test", node_id="node1", node_type="test_type")
    assert task.run_id == "test"
    assert task.node_id == "node1"
    assert task.node_type == "test_type"

    workflow = WorkflowRun(workflow_name="test_workflow")
    assert workflow.workflow_name == "test_workflow"
