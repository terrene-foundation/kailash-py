# Kailash Python SDK Examples

This directory contains comprehensive examples demonstrating the capabilities of the Kailash Python SDK. Each example is designed to showcase specific features and best practices for building workflows.

## Quick Start

To run any example:

```bash
cd examples
python basic_workflow.py
```

Make sure you have the Kailash SDK installed:

```bash
pip install -e ..
```

## Examples Overview

### 1. Basic Workflow (`basic_workflow.py`)
A simple ETL workflow that demonstrates:
- Reading data from CSV files
- Basic data transformation
- Writing results to files
- Workflow validation and visualization
- Export for Kailash integration

**Key concepts**: Node creation, workflow building, connections, validation

### 2. Complex Workflow (`complex_workflow.py`)
An advanced multi-node workflow featuring:
- Multiple data sources (CSV, JSON, API)
- Conditional logic and routing
- Parallel processing branches
- AI/ML integration
- Task tracking and monitoring
- Error handling

**Key concepts**: Complex workflows, parallel execution, conditional routing, task management

### 3. AI/ML Pipeline (`ai_pipeline.py`)
A complete machine learning pipeline including:
- Text data ingestion and preprocessing
- Feature engineering
- Multiple ML models (sentiment analysis, classification, NER)
- Model ensemble
- LLM-based insights generation
- Report generation

**Key concepts**: ML workflows, model integration, AI agents, performance monitoring

### 4. Data Transformation (`data_transformation.py`)
Comprehensive data transformation examples:
- Schema validation and type conversion
- Data cleaning and normalization
- Feature engineering
- Data aggregation and pivoting
- Custom transformation logic
- Streaming/incremental processing

**Key concepts**: Data validation, transformation operations, quality checks

### 5. Task Tracking (`task_tracking_example.py`)
Production-ready task management features:
- Task creation and lifecycle management
- Workflow execution monitoring
- Resource usage tracking
- Task dependencies and scheduling
- Error tracking and recovery
- Performance analytics

**Key concepts**: Task management, monitoring, resource tracking, error recovery

### 6. CLI Usage (`cli_example.sh`)
Command-line interface demonstration:
- Project initialization
- Node and workflow creation
- Workflow execution and monitoring
- Configuration management
- Deployment commands
- Advanced CLI features

**Key concepts**: CLI commands, configuration, deployment

### 7. Custom Node (`custom_node.py`)
Creating custom nodes by extending the SDK:
- Sentiment analysis node
- Data validation node
- API connector node
- Error handling patterns
- Node templates

**Key concepts**: Node extension, custom logic, error handling

### 8. Error Handling (`error_handling.py`)
Robust error handling patterns:
- Node-level error handling
- Workflow-level error management
- Circuit breaker pattern
- Error recovery strategies
- Error aggregation and reporting
- Custom error handlers

**Key concepts**: Error management, resilience patterns, recovery strategies

### 9. Visualization (`visualization_example.py`)
Workflow visualization capabilities:
- Basic workflow diagrams
- Advanced layouts and styling
- Execution flow visualization
- Performance metrics visualization
- Error path highlighting
- Interactive visualizations
- Export to multiple formats

**Key concepts**: Visualization, monitoring dashboards, export formats

### 10. Export Workflow (`export_workflow.py`)
Workflow export for Kailash deployment:
- Basic export to YAML/JSON
- Export with metadata and validation
- Task history inclusion
- Custom export configurations
- Batch export
- Format transformations
- Kailash-specific deployment exports

**Key concepts**: Export formats, deployment preparation, configuration

## Required Data Files

Some examples expect data files in the `data/` directory. You can create sample data files or modify the examples to use your own data:

```bash
mkdir -p data
echo "customer_id,name,email,age,purchase_total" > data/customers.csv
echo "C001,John Doe,john@example.com,30,1500.00" >> data/customers.csv
```

## Sample Data Structure

```
examples/
├── data/
│   ├── customers.csv          # Customer data
│   ├── transactions.json      # Transaction records
│   ├── support_tickets/       # Text files for NLP examples
│   └── exports/              # Export output directory
```

## Running All Examples

To run all examples sequentially:

```bash
# Make the run script executable
chmod +x run_all_examples.sh

# Run all examples
./run_all_examples.sh
```

The script will:
1. Test all examples to ensure they import correctly
2. Run basic examples that are fully functional
3. Run export examples that generate output files
4. List demonstration examples that require more setup

## Environment Variables

Some examples use environment variables for configuration:

```bash
export KAILASH_CONFIG_PATH=~/.kailash/config.yml
export KAILASH_LOG_LEVEL=INFO
export KAILASH_RUNTIME=local
```

## Example Dependencies

The examples may require additional packages:

```bash
pip install -r requirements.txt
```

## Troubleshooting

### Common Issues

1. **ImportError**: Make sure the Kailash SDK is installed:
   ```bash
   pip install -e ..
   ```

2. **FileNotFoundError**: Create the required data directory:
   ```bash
   mkdir -p data
   ```

3. **Permission Errors**: Some examples create files. Ensure you have write permissions:
   ```bash
   chmod +w data/
   ```

## Contributing

To add a new example:

1. Create a new Python file following the naming convention
2. Include comprehensive comments explaining the concepts
3. Add error handling and validation
4. Update this README with a description
5. Test the example with various inputs

## Best Practices Demonstrated

- **Code Organization**: Clear structure with imports, functions, and main entry point
- **Error Handling**: Comprehensive try-catch blocks with meaningful error messages
- **Documentation**: Detailed comments explaining each step
- **Validation**: Input validation and workflow verification
- **Resource Management**: Proper cleanup and resource disposal
- **Configuration**: Flexible configuration options
- **Logging**: Informative logging at appropriate levels

## Advanced Usage

### Custom Configuration

Create a custom configuration file:

```python
config = {
    "runtime": {
        "parallel": True,
        "max_workers": 4
    },
    "storage": {
        "backend": "filesystem",
        "path": "./data"
    }
}
```

### Extending Examples

Each example can be extended with additional features:

```python
# Add custom node to any workflow
from examples.custom_node import SentimentAnalyzerNode

sentiment_node = SentimentAnalyzerNode(name="analyze_sentiment")
workflow.add_node(sentiment_node)
```

## Support

For questions or issues:
1. Check the example code comments
2. Review the main SDK documentation
3. Open an issue on GitHub

## License

These examples are part of the Kailash Python SDK and are subject to the same license terms.