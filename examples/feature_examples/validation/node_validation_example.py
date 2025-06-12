"""Example demonstrating enhanced node validation with helpful error messages.

This example shows how the NodeValidator provides context-aware suggestions
when configuration errors occur.
"""

from kailash.workflow import Workflow
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.data import SQLDatabaseNode, CSVReaderNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.validation import NodeValidator, validate_node_decorator


def demonstrate_validation_errors():
    """Show common errors and how validation helps."""
    print("=== Node Validation Examples ===\n")
    
    # Example 1: PythonCodeNode without result wrapper
    print("1. PythonCodeNode Missing Result Wrapper:")
    try:
        # This will fail
        node = PythonCodeNode(
            name="processor",
            code="data = input_data * 2; return data"  # Missing {"result": ...}
        )
    except Exception as e:
        # Show how validation would help
        error_msg = NodeValidator.format_error_with_suggestions(
            e,
            "PythonCodeNode",
            {"code": "data = input_data * 2; return data"},
            {"workflow_name": "DataProcessing", "node_id": "processor"}
        )
        print(error_msg)
    
    print("\n" + "="*60 + "\n")
    
    # Example 2: File path validation
    print("2. Relative File Path Issue:")
    suggestions = NodeValidator.validate_node_config(
        "CSVReaderNode",
        {"file_path": "data.csv"}  # Relative path
    )
    
    if suggestions:
        print("💡 Validation suggestions:")
        for suggestion in suggestions:
            print(f"   - {suggestion.message}")
            if suggestion.code_example:
                print(f"     Example: {suggestion.code_example}")
    
    print("\n" + "="*60 + "\n")
    
    # Example 3: SQL injection risk
    print("3. SQL Security Warning:")
    user_id = "123; DROP TABLE users; --"
    suggestions = NodeValidator.validate_node_config(
        "SQLDatabaseNode",
        {"query": f"SELECT * FROM users WHERE id = {user_id}"}
    )
    
    if suggestions:
        for suggestion in suggestions:
            print(f"⚠️  {suggestion.message}")
            if suggestion.code_example:
                print(f"   Better approach: {suggestion.code_example}")


def demonstrate_enhanced_errors():
    """Show enhanced error messages in action."""
    print("\n=== Enhanced Error Messages ===\n")
    
    # Apply validation decorator
    @validate_node_decorator
    class ValidatedPythonCodeNode(PythonCodeNode):
        pass
    
    # This will show enhanced error
    try:
        node = ValidatedPythonCodeNode(
            code=123  # Wrong type
        )
    except Exception as e:
        print("Enhanced error message:")
        print(str(e))


def demonstrate_alternative_suggestions():
    """Show how validator suggests alternative nodes."""
    print("\n=== Alternative Node Suggestions ===\n")
    
    use_cases = [
        "csv processing",
        "api calls",
        "data storage",
        "llm tasks",
        "authentication"
    ]
    
    for use_case in use_cases:
        alternatives = NodeValidator.suggest_alternative_nodes(use_case)
        if alternatives:
            print(f"{use_case.title()}:")
            print(f"   Recommended nodes: {', '.join(alternatives)}")


def demonstrate_validation_patterns():
    """Show validation patterns for different scenarios."""
    print("\n=== Validation Patterns ===\n")
    
    # Pattern 1: Validate before workflow execution
    workflow = Workflow(
        workflow_id="validated_workflow",
        name="Workflow with Validation"
    )
    
    # Add nodes with potential issues
    configs = [
        ("reader", "CSVReaderNode", {"file_path": "/data/input.csv"}),
        ("processor", "PythonCodeNode", {"code": 'return {"result": data}'}),
        ("api_call", "HTTPRequestNode", {"url": "https://api.example.com"})
    ]
    
    print("Validating workflow nodes:")
    for node_id, node_type, config in configs:
        suggestions = NodeValidator.validate_node_config(node_type, config)
        status = "✅ Valid" if not suggestions else "⚠️  Has suggestions"
        print(f"   {node_id} ({node_type}): {status}")
        
        if suggestions:
            for suggestion in suggestions:
                print(f"      - {suggestion.message}")
    
    # Pattern 2: Runtime validation
    print("\n\nRuntime validation example:")
    
    class SmartWorkflow(Workflow):
        """Workflow with built-in validation."""
        
        def add_node(self, node_id, node_class, **config):
            """Add node with validation."""
            # Validate before adding
            suggestions = NodeValidator.validate_node_config(
                node_class.__name__,
                config
            )
            
            if suggestions:
                print(f"\n⚠️  Validation warnings for {node_id}:")
                for suggestion in suggestions:
                    print(f"   - {suggestion.message}")
                    if suggestion.code_example:
                        print(f"     {suggestion.code_example}")
            
            # Still add the node
            super().add_node(node_id, node_class, **config)
    
    # Use smart workflow
    smart_workflow = SmartWorkflow(
        workflow_id="smart",
        name="Smart Validated Workflow"
    )
    
    # This will show validation warnings
    smart_workflow.add_node(
        "bad_sql",
        SQLDatabaseNode,
        query="SELECT * FROM users WHERE name = '" + "user_input" + "'"
    )


def demonstrate_custom_validation():
    """Show how to add custom validation rules."""
    print("\n\n=== Custom Validation Rules ===\n")
    
    # Add custom patterns
    import re
    from kailash.nodes.validation import ValidationSuggestion
    
    # Add organization-specific rules
    NodeValidator.PARAMETER_PATTERNS.update({
        r"prod_": ValidationSuggestion(
            message="Production identifiers should not be hardcoded",
            code_example="Use environment variables: os.environ.get('PROD_API_KEY')",
            doc_link="internal/security-guidelines.md"
        ),
        r"TODO|FIXME": ValidationSuggestion(
            message="Unfinished code detected",
            code_example="Complete implementation before deployment"
        )
    })
    
    # Test custom validation
    config = {"api_key": "prod_abc123", "code": "# TODO: implement this"}
    suggestions = NodeValidator.validate_node_config("PythonCodeNode", config)
    
    print("Custom validation results:")
    for suggestion in suggestions:
        print(f"   ❌ {suggestion.message}")


if __name__ == "__main__":
    # Run demonstrations
    demonstrate_validation_errors()
    demonstrate_enhanced_errors()
    demonstrate_alternative_suggestions()
    demonstrate_validation_patterns()
    demonstrate_custom_validation()
    
    print("\n\n✅ Validation helps catch errors early and provides helpful guidance!")
    print("   Use NodeValidator to improve your workflow development experience.")