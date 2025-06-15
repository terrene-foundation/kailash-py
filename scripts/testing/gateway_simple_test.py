"""Test simple gateway functionality."""

from kailash.api.gateway import WorkflowAPIGateway
from kailash.nodes.code import PythonCodeNode
from kailash.workflow import Workflow


def create_hello_workflow() -> Workflow:
    """Create a simple hello world workflow."""
    workflow = Workflow(
        workflow_id="hello_001",
        name="Hello World",
        description="Simple hello world workflow",
    )

    # Create a simple Python node that doesn't require config
    hello_node = PythonCodeNode(
        name="greeting",
        code="""
name = input_data.get('name', 'World')
output = f"Hello, {name}!"
""",
    )
    workflow.add_node("greet", hello_node)

    return workflow


def create_math_workflow() -> Workflow:
    """Create a simple math workflow."""
    workflow = Workflow(
        workflow_id="math_001",
        name="Math Operations",
        description="Simple math operations workflow",
    )

    # Add operation
    add_node = PythonCodeNode(
        name="addition",
        code="""
a = input_data.get('a', 0)
b = input_data.get('b', 0)
output = {'sum': a + b, 'operation': 'addition'}
""",
    )
    workflow.add_node("add", add_node)

    # Multiply operation
    multiply_node = PythonCodeNode(
        name="multiplication",
        code="""
a = input_data.get('a', 0)
b = input_data.get('b', 0)
output = {'product': a * b, 'operation': 'multiplication'}
""",
    )
    workflow.add_node("multiply", multiply_node)

    return workflow


def main():
    """Test the gateway with simple workflows."""
    print("=== Testing Simple Gateway ===\n")

    # Create gateway
    gateway = WorkflowAPIGateway(
        title="Test Gateway", description="Simple test gateway", version="1.0.0"
    )

    # Register workflows
    print("Registering workflows...")

    gateway.register_workflow(
        "hello", create_hello_workflow(), description="Simple greeting workflow"
    )

    gateway.register_workflow(
        "math", create_math_workflow(), description="Math operations workflow"
    )

    print("✓ Registered 2 workflows\n")

    # Display endpoints
    print("Available Endpoints:")
    print("-" * 50)
    print("Gateway Info:    http://localhost:8000/")
    print("Workflows:       http://localhost:8000/workflows")
    print()
    print("Hello Workflow:")
    print("  Execute:       http://localhost:8000/hello/execute")
    print("  Info:          http://localhost:8000/hello/workflow/info")
    print()
    print("Math Workflow:")
    print("  Execute:       http://localhost:8000/math/execute")
    print("  Info:          http://localhost:8000/math/workflow/info")
    print()

    print("Example Calls:")
    print("-" * 50)
    print("curl -X POST http://localhost:8000/hello/execute \\")
    print('  -H "Content-Type: application/json" \\')
    print('  -d \'{"greet": {"name": "Alice"}}\'')
    print()
    print("curl -X POST http://localhost:8000/math/execute \\")
    print('  -H "Content-Type: application/json" \\')
    print('  -d \'{"add": {"a": 10, "b": 20}, "multiply": {"a": 5, "b": 6}}\'')

    return gateway


if __name__ == "__main__":
    gateway = main()
    print("\n\nGateway setup complete!")
    print("To start the server, run: gateway.execute(port=8000)")
