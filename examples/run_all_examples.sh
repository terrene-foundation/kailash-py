#!/usr/bin/env bash
# Script to run all Kailash SDK examples

# Set up error handling
set -e
EXAMPLES_DIR=$(dirname "$0")
cd "$EXAMPLES_DIR"
echo "Running Kailash Python SDK examples from directory: $EXAMPLES_DIR"

# First run the example validator to ensure everything imports correctly
echo -e "\n=== Testing Example Imports ===\n"
python test_all_examples.py

# Create output directory for example results
mkdir -p data/outputs

# List of basic examples that should run completely
BASIC_EXAMPLES=(
    "basic_workflow.py"
    "simple_workflow_example.py"
    "python_code_node_example.py"
    "direct_vs_workflow_example.py"
)

# List of examples that generate output files
EXPORT_EXAMPLES=(
    "export_workflow.py"
)

# List of examples that focus on demonstration instead of execution
DEMO_EXAMPLES=(
    "custom_node.py"
    "data_transformation.py" 
    "error_handling.py"
    "visualization_example.py"
    "task_tracking_example.py"
    "complex_workflow.py"
)

# Run basic examples
echo -e "\n=== Running Basic Examples ===\n"
for example in "${BASIC_EXAMPLES[@]}"; do
    if [ -f "$example" ]; then
        echo -e "\n>> Running $example..."
        python "$example"
        if [ $? -eq 0 ]; then
            echo "✓ $example executed successfully"
        else
            echo "✗ $example failed"
        fi
    else
        echo "! $example not found"
    fi
done

# Run export examples
echo -e "\n=== Running Export Examples ===\n"
for example in "${EXPORT_EXAMPLES[@]}"; do
    if [ -f "$example" ]; then
        echo -e "\n>> Running $example..."
        python "$example"
        if [ $? -eq 0 ]; then
            echo "✓ $example executed successfully"
        else
            echo "✗ $example failed"
        fi
    else
        echo "! $example not found"
    fi
done

# Print demonstration examples
echo -e "\n=== Demonstration Examples ===\n"
echo "The following examples are for demonstration purposes:"
for example in "${DEMO_EXAMPLES[@]}"; do
    if [ -f "$example" ]; then
        echo "- $example"
    fi
done

echo -e "\nTo run a demonstration example, use: python examples/<example_name>"
echo -e "\nAll examples completed successfully!"