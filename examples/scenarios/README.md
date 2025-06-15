# Scenario Tests

This directory contains scenario-based tests that demonstrate real-world usage patterns and practical applications of the Kailash SDK. These tests serve as both validation and examples.

## Purpose

These tests focus on:
- **Real-world scenarios** - Practical use cases that users encounter
- **End-to-end workflows** - Complete business processes using SDK components
- **Integration patterns** - How different SDK components work together
- **Best practice examples** - Demonstrating recommended usage patterns

## Contents

### Cyclic Workflow Scenarios
- `test_cycle_scenarios.py` - Real-world cyclic workflow applications
  - ETL pipeline with retry cycles
  - API polling with backoff cycles  
  - Data quality improvement cycles
  - Resource optimization cycles
  - Batch processing with checkpoints

- `test_cycle_scenarios_simplified.py` - Simplified versions of common scenarios
  - Basic retry patterns
  - Simple polling loops
  - Minimal viable cycles
  - Educational examples

## Scenario Categories

### Data Processing Scenarios
- **ETL Pipelines** - Extract, transform, load workflows with error handling
- **Data Quality** - Iterative data cleaning and validation cycles
- **Batch Processing** - Large dataset processing with checkpointing

### API Integration Scenarios  
- **Polling Patterns** - Regular API polling with intelligent backoff
- **Webhook Processing** - Event-driven workflow execution
- **Rate-Limited Operations** - Handling API rate limits gracefully

### Resource Management Scenarios
- **Auto-scaling** - Dynamic resource allocation based on load
- **Optimization Cycles** - Iterative improvement of resource usage
- **Health Monitoring** - Continuous system health validation

## Usage

### Running Scenarios
```bash
# Run all scenario tests
python -m pytest examples/scenarios/ -v

# Run specific scenario category
python -m pytest examples/scenarios/test_cycle_scenarios.py -v

# Run simplified examples only
python -m pytest examples/scenarios/ -k "simplified" -v
```

### Learning from Scenarios
```bash
# Run with detailed output to see workflow progression
python -m pytest examples/scenarios/ -v -s

# Focus on specific use case
python -m pytest examples/scenarios/ -k "etl" -v
```

### Using as Templates
These scenarios can serve as starting points for your own implementations:

1. **Copy scenario code** - Use as template for similar use cases
2. **Modify parameters** - Adapt to your specific requirements  
3. **Extend functionality** - Add additional processing steps
4. **Integrate patterns** - Combine multiple scenario patterns

## Scenario Patterns

### ETL Retry Pattern
```python
class ETLRetryNode(CycleAwareNode):
    """ETL processor with retry capabilities."""
    
    def run(self, **kwargs) -> dict[str, Any]:
        # Implement retry logic
        # Handle failures gracefully
        # Track retry attempts
        pass
```

### API Polling Pattern
```python
class APIPollingNode(CycleAwareNode):
    """API polling with intelligent backoff."""
    
    def run(self, **kwargs) -> dict[str, Any]:
        # Poll API endpoint
        # Implement backoff strategy
        # Handle rate limits
        pass
```

### Resource Optimization Pattern
```python
class ResourceOptimizerNode(CycleAwareNode):
    """Iterative resource optimization."""
    
    def run(self, **kwargs) -> dict[str, Any]:
        # Analyze current resource usage
        # Calculate optimization steps
        # Apply improvements iteratively
        pass
```

## Educational Value

These scenarios provide:
- **Learning examples** - See SDK patterns in action
- **Documentation** - Practical usage documentation
- **Training material** - Examples for SDK training
- **Debugging references** - Working examples for troubleshooting

## Relationship to Other Examples

### vs. Feature Examples (`examples/feature_examples/`)
- **Feature examples** - Test individual SDK components
- **Scenarios** - Show how components work together in real workflows

### vs. Production Workflows (`sdk-users/workflows/`)
- **Production workflows** - Business-ready solutions
- **Scenarios** - Educational and testing examples

### vs. Performance Benchmarks (`examples/performance_benchmarks/`)
- **Performance benchmarks** - Focus on speed and resource usage
- **Scenarios** - Focus on functionality and patterns

## Contributing

When adding new scenarios:

1. **Focus on real use cases** - Based on actual user needs
2. **Include documentation** - Explain the scenario and its value
3. **Provide variations** - Simple and complex versions
4. **Test thoroughly** - Ensure examples work correctly
5. **Add educational notes** - Help users understand the patterns

### Scenario Template
```python
"""
Scenario: [Brief Description]

This scenario demonstrates:
- [Key concept 1]
- [Key concept 2]
- [Key concept 3]

Real-world applications:
- [Use case 1]
- [Use case 2]
"""

class ScenarioNode(CycleAwareNode):
    """[Node description]."""
    
    def get_parameters(self) -> dict[str, NodeParameter]:
        # Define scenario parameters
        pass
    
    def run(self, **kwargs) -> dict[str, Any]:
        # Implement scenario logic
        pass

@pytest.mark.scenario
def test_scenario_functionality():
    """Test the scenario works correctly."""
    # Test scenario execution
    # Validate expected outcomes
    pass
```

This separation allows scenarios to serve their educational and validation purposes without impacting the main test suite performance.