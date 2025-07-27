# Workflow Architecture Patterns

*Common patterns for structuring workflows in production applications*

## 🎯 Pattern Categories

### 1. **Linear Pipeline Pattern**
Sequential processing with clear stages.

```python
# SDK Setup for example
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = WorkflowBuilder()
# Runtime should be created separately
runtime = LocalRuntime()

workflow = WorkflowBuilder()

# Stage 1: Ingestion
workflow.add_node("CSVReaderNode", "ingest", {
    "file_path": "raw_data.csv"})

# Stage 2: Validation
workflow.add_node("DataValidationNode", "validate", {
    "schema": {"required": ["id", "amount"], "types": {"amount": float}}})

# Stage 3: Transform
workflow.add_node("DataTransformerNode", "transform", {
    "operations": [
        {"type": "filter", "condition": "amount > 0"},
        {"type": "map", "expression": "{'id': id, 'amount_usd': amount * 1.1}"}
    ]})

# Stage 4: Output
workflow.add_node("JSONWriterNode", "output", {
    "file_path": "processed.json"})

# Linear connections
workflow.add_connection("ingest", "result", "validate", "input")
workflow.add_connection("validate", "result", "transform", "input")
workflow.add_connection("transform", "result", "output", "input")

```

**Use when**: Clear sequential steps, ETL processes, data pipelines

### 2. **Fan-Out/Fan-In Pattern**
Parallel processing with aggregation.

```python
# SDK Setup for example
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = WorkflowBuilder()
# Runtime should be created separately
runtime = LocalRuntime()

workflow = WorkflowBuilder()

# Single source
workflow.add_node("JSONReaderNode", "source", {
    "file_path": "tasks.json"})

# Fan-out to multiple processors
workflow.add_node("LLMAgentNode", "processor1", {
    "model": "gpt-4",
    "system_prompt": "Process task type A"})

workflow.add_node("LLMAgentNode", "processor2", {
    "model": "gpt-4",
    "system_prompt": "Process task type B"})

workflow.add_node("LLMAgentNode", "processor3", {
    "model": "gpt-4",
    "system_prompt": "Process task type C"})

# Fan-in aggregation
workflow.add_node("MergeNode", "aggregator", {"merge_strategy": "concat"})
workflow.add_node("MergeNode", "aggregator", {}))

# Connect fan-out
workflow = WorkflowBuilder()
workflow.add_connection("source", "result", "processor1", "input")
workflow = WorkflowBuilder()
workflow.add_connection("source", "result", "processor2", "input")
workflow = WorkflowBuilder()
workflow.add_connection("source", "result", "processor3", "input")

# Connect fan-in
workflow = WorkflowBuilder()
# Workflow setup goes here  # Method signature
workflow = WorkflowBuilder()
# Workflow setup goes here  # Method signature
workflow = WorkflowBuilder()
# Workflow setup goes here  # Method signature

```

**Use when**: Parallel processing, load distribution, map-reduce patterns

### 3. **Conditional Routing Pattern**
Dynamic path selection based on data.

```python
# SDK Setup for example
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = WorkflowBuilder()
# Runtime should be created separately
runtime = LocalRuntime()

workflow = WorkflowBuilder()

# Input
workflow = WorkflowBuilder()
workflow.add_node("JSONReaderNode", "input", {}),
    file_path="requests.json")

# Router
workflow = WorkflowBuilder()
workflow.add_node("SwitchNode", "router", {}),
    conditions=[
        {"output": "premium", "expression": "customer_tier == 'premium'"},
        {"output": "standard", "expression": "customer_tier == 'standard'"},
        {"output": "basic", "expression": "True"}  # Default
    ])

# Different handlers for each tier
workflow = WorkflowBuilder()
workflow.add_node("LLMAgentNode", "premium_handler", {}),
    provider="openai",
    model="gpt-4",
    prompt="Premium support: {query}")

workflow = WorkflowBuilder()
workflow.add_node("LLMAgentNode", "standard_handler", {}),
    provider="openai",
    model="gpt-3.5-turbo",
    prompt="Standard support: {query}")

workflow = WorkflowBuilder()
# Workflow setup goes here  # Method signature)

# Result merger
workflow = WorkflowBuilder()
workflow.add_node("MergeNode", "merger", {}))

# Connect routing
workflow = WorkflowBuilder()
workflow.add_connection("source", "result", "target", "input")  # Fixed complex parameters
workflow = WorkflowBuilder()
# Workflow setup goes here  # Method signature
workflow = WorkflowBuilder()
# Workflow setup goes here  # Method signature
workflow = WorkflowBuilder()
# Workflow setup goes here  # Method signature

# Merge results
workflow = WorkflowBuilder()
# Workflow setup goes here  # Method signature
workflow = WorkflowBuilder()
# Workflow setup goes here  # Method signature
workflow = WorkflowBuilder()
# Workflow setup goes here  # Method signature

```

**Use when**: Different processing paths, A/B testing, tier-based logic

### 4. **Recursive/Cyclic Pattern**
Iterative processing with convergence.

```python
# SDK Setup for example
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = WorkflowBuilder()
# Runtime should be created separately
runtime = LocalRuntime()

workflow = WorkflowBuilder()

# Initial data
workflow = WorkflowBuilder()
# Workflow setup goes here  # Method signature)

# Iterative processor
workflow = WorkflowBuilder()
# Workflow setup goes here  # Method signature
converged = abs(new_value - target) < 0.01

result = {
    'value': new_value,
    'target': target,
    'step': step + 1,
    'converged': converged,
    'history': f"Step {step}: {value:.2f} → {new_value:.2f}"
}
''',
    input_types={"value": float, "target": float, "step": int}
))

# Connect initial
workflow = WorkflowBuilder()
# Workflow setup goes here  # Method signature

# Create cycle
workflow = WorkflowBuilder()
# Workflow setup goes here  # Method signature

```

**Use when**: Optimization, refinement, iterative algorithms

### 5. **Event-Driven Pattern**
Reactive processing triggered by events.

```python
# SDK Setup for example
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = WorkflowBuilder()
# Runtime should be created separately
runtime = LocalRuntime()

workflow = WorkflowBuilder()

# Event listener
workflow = WorkflowBuilder()
# Workflow setup goes here  # Method signature)

# Event router
workflow = WorkflowBuilder()
workflow.add_node("SwitchNode", "router", {}),
    conditions=[
        {"output": "created", "expression": "event_type == 'order.created'"},
        {"output": "updated", "expression": "event_type == 'order.updated'"},
        {"output": "cancelled", "expression": "event_type == 'order.cancelled'"}
    ])

# Event handlers
workflow = WorkflowBuilder()
workflow.add_node("WorkflowNode", "handle_created", {}))

workflow = WorkflowBuilder()
workflow.add_node("WorkflowNode", "handle_updated", {}))

workflow = WorkflowBuilder()
workflow.add_node("WorkflowNode", "handle_cancelled", {}))

# Connect event flow
workflow = WorkflowBuilder()
# Workflow setup goes here  # Method signature
workflow = WorkflowBuilder()
# Workflow setup goes here  # Method signature
workflow = WorkflowBuilder()
# Workflow setup goes here  # Method signature
workflow = WorkflowBuilder()
# Workflow setup goes here  # Method signature

```

**Use when**: Message queues, webhooks, real-time systems

### 6. **Saga Pattern**
Distributed transactions with compensation.

```python
# SDK Setup for example
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = WorkflowBuilder()
# Runtime should be created separately
runtime = LocalRuntime()

workflow = WorkflowBuilder()

# Transaction steps
workflow = WorkflowBuilder()
workflow.add_node("HTTPRequestNode", "reserve_inventory", {}),
    url="${INVENTORY_API}/reserve",
    method="POST")

workflow = WorkflowBuilder()
workflow.add_node("HTTPRequestNode", "charge_payment", {}),
    url="${PAYMENT_API}/charge",
    method="POST")

workflow = WorkflowBuilder()
workflow.add_node("HTTPRequestNode", "create_shipment", {}),
    url="${SHIPPING_API}/create",
    method="POST")

# Compensation steps
workflow = WorkflowBuilder()
workflow.add_node("HTTPRequestNode", "release_inventory", {}),
    url="${INVENTORY_API}/release",
    method="POST")

workflow = WorkflowBuilder()
workflow.add_node("HTTPRequestNode", "refund_payment", {}),
    url="${PAYMENT_API}/refund",
    method="POST")

# Saga coordinator
workflow = WorkflowBuilder()
# Workflow setup goes here  # Method signature)

```

**Use when**: Distributed transactions, microservices, rollback support

## 🏗️ Composition Patterns

### Nested Workflows
```python
# SDK Setup for example
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = WorkflowBuilder()
# Runtime should be created separately
runtime = LocalRuntime()

# Main workflow
main_workflow = WorkflowBuilder()

# Sub-workflows
validation_workflow = create_validation_workflow()
processing_workflow = create_processing_workflow()
reporting_workflow = create_reporting_workflow()

# Compose using WorkflowNode
workflow = WorkflowBuilder()
workflow.add_node("WorkflowNode", "validate", {}))
workflow = WorkflowBuilder()
workflow.add_node("WorkflowNode", "process", {}))
workflow = WorkflowBuilder()
workflow.add_node("WorkflowNode", "report", {}))

# Connect sub-workflows
workflow = WorkflowBuilder()
workflow.add_connection("validate", "result", "process", "input")
workflow = WorkflowBuilder()
workflow.add_connection("process", "result", "report", "input")

```

### Dynamic Workflow Generation
```python
# SDK Setup for example
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = WorkflowBuilder()
# Runtime should be created separately
runtime = LocalRuntime()

def workflow.()  # Type signature example -> Workflow:
    """Generate workflow based on configuration."""
    workflow = WorkflowBuilder()
workflow.method()  # Example
    # Add nodes based on config
    for node_config in config['nodes']:
        node_class = globals()[node_config['type']]
        node = node_class(**node_config['params'])
workflow = WorkflowBuilder()
workflow.add_node(node_config['id'], node)

    # Add connections
    for conn in config['connections']:
workflow = WorkflowBuilder()
workflow.add_connection(conn['from'], "result", conn['to'], "input")
        )

    return workflow

# Usage
workflow = WorkflowBuilder()
workflow.yaml")
workflow = create_dynamic_workflow(config)

```

## 🎯 Choosing the Right Pattern

| **Scenario** | **Recommended Pattern** |
|-------------|------------------------|
| Data ETL | Linear Pipeline |
| Batch processing | Fan-Out/Fan-In |
| User tier handling | Conditional Routing |
| ML training | Recursive/Cyclic |
| Real-time processing | Event-Driven |
| Distributed transactions | Saga |

## 💡 Best Practices

1. **Keep workflows focused** - Single responsibility principle
2. **Use composition** - Combine simple workflows for complex logic
3. **Handle errors gracefully** - Add error handlers at key points
4. **Monitor critical paths** - Add logging and metrics
5. **Test edge cases** - Validate with various data scenarios

## 🔗 Next Steps

- [Performance Patterns](performance-patterns.md) - Optimization strategies
- [Security Patterns](security-patterns.md) - Security architectures
- [Developer Guide](../developer/) - Implementation details
