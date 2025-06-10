# Control Flow Patterns

**Essential workflow control patterns** - The building blocks for ALL complex workflows.

## 📋 Pattern Overview

Control flow patterns are fundamental to creating sophisticated workflows that can:
- **Make decisions** based on data or conditions
- **Execute in parallel** for performance optimization
- **Iterate and optimize** through cyclic execution
- **Handle errors gracefully** with proper recovery strategies

## 🎯 Quick Start Examples

### 30-Second Conditional Routing
```python
from kailash import Workflow
from kailash.nodes.logic import SwitchNode
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.transform import DataTransformer
from kailash.runtime import LocalRuntime

# Create workflow with conditional branching
workflow = Workflow("conditional_routing", "Customer Segmentation")

# Read customer data
workflow.add_node("reader", CSVReaderNode())

# Route based on customer value
router = SwitchNode(
    id="value_router",
    condition="customer_value > 1000"
)
workflow.add_node("value_router", router)

# High-value customer processing
workflow.add_node("premium_processing", DataTransformer(
    id="premium_processing",
    transformations=["lambda x: {**x, 'tier': 'premium', 'discount': 0.2}"]
))

# Standard customer processing
workflow.add_node("standard_processing", DataTransformer(
    id="standard_processing",
    transformations=["lambda x: {**x, 'tier': 'standard', 'discount': 0.05}"]
))

# Connect conditional branches
workflow.connect("reader", "value_router", mapping={"data": "data"})
workflow.connect("value_router", "premium_processing", 
                output_key="true_output", mapping={"data": "data"})
workflow.connect("value_router", "standard_processing", 
                output_key="false_output", mapping={"data": "data"})

# Execute
runtime = LocalRuntime()
result = runtime.execute(workflow, parameters={
    "reader": {"file_path": "customers.csv"}
})
```

### Parallel Execution for Performance
```python
from kailash.nodes.api import RestClientNode
from kailash.nodes.logic import MergeNode

workflow = Workflow("parallel_api_calls", "Multi-Source Data Aggregation")

# Parallel API calls to different services
workflow.add_node("weather_api", RestClientNode())
workflow.add_node("traffic_api", RestClientNode())
workflow.add_node("events_api", RestClientNode())

# Merge results
merger = MergeNode(id="data_merger")
workflow.add_node("data_merger", merger)

# Connect all parallel branches to merger
workflow.connect("weather_api", "data_merger", mapping={"response": "weather_data"})
workflow.connect("traffic_api", "data_merger", mapping={"response": "traffic_data"})
workflow.connect("events_api", "data_merger", mapping={"response": "events_data"})

# Execute - all APIs called in parallel
runtime = LocalRuntime()
result = runtime.execute(workflow, parameters={
    "weather_api": {"url": "https://api.weather.com/current"},
    "traffic_api": {"url": "https://api.traffic.com/conditions"},
    "events_api": {"url": "https://api.events.com/today"}
})
```

## 🔀 Control Flow Patterns

### [Conditional Routing](conditional-routing.md)
**Decision-making in workflows** - Route data based on conditions

**Use Cases:**
- Customer segmentation
- Approval workflows
- Data quality routing
- Alert triage
- A/B testing

**Key Features:**
- Boolean conditions
- Multi-way branching
- Default paths
- Nested conditions

### [Parallel Execution](parallel-execution.md)
**Concurrent processing** - Execute multiple paths simultaneously

**Use Cases:**
- Multi-API aggregation
- Batch processing
- Resource optimization
- Performance scaling
- Independent tasks

**Key Features:**
- Automatic parallelization
- Result synchronization
- Resource management
- Error isolation

### [Cyclic Workflows](cyclic-workflows.md)
**Iterative processes** - Workflows that loop until conditions are met

**Use Cases:**
- Optimization algorithms
- Retry mechanisms
- Convergence patterns
- State machines
- Feedback loops

**Key Features:**
- Cycle detection
- State persistence
- Termination conditions
- Performance tracking

### [Error Handling](error-handling.md)
**Fault tolerance** - Graceful error recovery and compensation

**Use Cases:**
- API failures
- Data validation
- Timeout handling
- Compensation logic
- Circuit breakers

**Key Features:**
- Try-catch patterns
- Retry strategies
- Fallback paths
- Error aggregation

## 🎨 Pattern Combinations

### Advanced Decision Trees
```python
# Multi-level conditional routing
workflow = Workflow("decision_tree", "Complex Routing")

# First level: Check data quality
quality_check = SwitchNode(id="quality_check", condition="quality_score > 0.8")
workflow.add_node("quality_check", quality_check)

# Second level: Check customer type (for good quality data)
customer_type = SwitchNode(id="customer_type", condition="type == 'enterprise'")
workflow.add_node("customer_type", customer_type)

# Connect decision tree
workflow.connect("quality_check", "customer_type", 
                output_key="true_output", mapping={"data": "data"})
workflow.connect("quality_check", "data_cleansing", 
                output_key="false_output", mapping={"data": "data"})
```

### Parallel with Error Handling
```python
# Parallel execution with individual error handling
workflow = Workflow("resilient_parallel", "Fault-Tolerant Aggregation")

# Each parallel branch has its own error handling
for service in ["service_a", "service_b", "service_c"]:
    # API call
    workflow.add_node(f"{service}_api", RestClientNode())
    
    # Error handler for this service
    workflow.add_node(f"{service}_error_handler", SwitchNode(
        condition="status_code == 200"
    ))
    
    # Fallback for failed calls
    workflow.add_node(f"{service}_fallback", DataTransformer(
        transformations=["lambda x: {'data': 'default', 'source': 'fallback'}"]
    ))
    
    # Connect with error handling
    workflow.connect(f"{service}_api", f"{service}_error_handler")
    workflow.connect(f"{service}_error_handler", "merger", 
                    output_key="true_output", mapping={"response": f"{service}_data"})
    workflow.connect(f"{service}_error_handler", f"{service}_fallback", 
                    output_key="false_output")
    workflow.connect(f"{service}_fallback", "merger", 
                    mapping={"result": f"{service}_data"})
```

### Cyclic Optimization with Conditions
```python
# Iterative optimization with convergence checking
from kailash.workflow.cycle_builder import CycleBuilder

cycle_builder = CycleBuilder()
cycle_workflow = cycle_builder.create_workflow(
    "optimization_cycle",
    "Iterative Model Training"
)

# Define cycle components
cycle_builder.add_cycle_node(
    "model_trainer",
    DataTransformer(transformations=["lambda x: train_model(x)"])
)

cycle_builder.add_cycle_node(
    "convergence_check",
    SwitchNode(condition="improvement < 0.001")
)

# Connect cycle with exit condition
cycle_builder.connect_cycle_nodes(
    "model_trainer", "convergence_check",
    mapping={"result": "metrics"}
)

# Exit cycle when converged
cycle_builder.set_cycle_exit_condition(
    "convergence_check",
    exit_on="true_output"
)

# Set maximum iterations
cycle_builder.set_max_iterations(100)
```

## 📊 Best Practices

### Conditional Routing
- **Clear conditions**: Use explicit, testable conditions
- **Default paths**: Always handle the "else" case
- **Avoid deep nesting**: Flatten complex decision trees
- **Document logic**: Explain routing decisions

### Parallel Execution
- **Independent tasks**: Ensure parallel paths don't share state
- **Resource limits**: Set appropriate concurrency limits
- **Timeout handling**: Set timeouts for each parallel branch
- **Result merging**: Plan how to combine parallel results

### Cyclic Workflows
- **Exit conditions**: Always define clear termination criteria
- **State management**: Track progress across iterations
- **Performance limits**: Set maximum iteration counts
- **Monitoring**: Log iteration metrics

### Error Handling
- **Specific catches**: Handle specific error types
- **Retry logic**: Implement exponential backoff
- **Circuit breakers**: Prevent cascade failures
- **Logging**: Capture detailed error context

## 🔗 See Also

- [Data Processing Patterns](../data-processing/) - ETL and transformation patterns
- [API Integration Patterns](../api-integration/) - External system integration
- [AI/ML Patterns](../ai-ml/) - Machine learning workflows
- [Monitoring Patterns](../monitoring/) - Observability and tracking

---

*Control flow patterns are the foundation of sophisticated workflow automation. Master these patterns to build resilient, scalable, and maintainable workflows.*