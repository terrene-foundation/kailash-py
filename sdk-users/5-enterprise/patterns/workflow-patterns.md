# Workflow Architecture Patterns

*Common patterns for structuring workflows in production applications*

## 🎯 Pattern Categories

### 1. **Linear Pipeline Pattern**
Sequential processing with clear stages.

```python
# SDK Setup for example
from kailash import Workflow
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = Workflow("example", name="Example")
workflow.runtime = LocalRuntime()

workflow = Workflow("pipeline", name="Data Pipeline")

# Stage 1: Ingestion
workflow = Workflow("example", name="Example")
workflow.workflow.add_node("ingest", CSVReaderNode(),
    file_path="raw_data.csv")

# Stage 2: Validation
workflow = Workflow("example", name="Example")
workflow.workflow.add_node("validate", DataValidationNode(),
    schema={"required": ["id", "amount"], "types": {"amount": float}})

# Stage 3: Transform
workflow = Workflow("example", name="Example")
workflow.workflow.add_node("transform", DataTransformerNode(),
    operations=[
        {"type": "filter", "condition": "amount > 0"},
        {"type": "map", "expression": "{'id': id, 'amount_usd': amount * 1.1}"}
    ])

# Stage 4: Output
workflow = Workflow("example", name="Example")
workflow.workflow.add_node("output", JSONWriterNode(),
    file_path="processed.json")

# Linear connections
workflow = Workflow("example", name="Example")
workflow.workflow.connect("ingest", "validate")
workflow = Workflow("example", name="Example")
workflow.workflow.connect("validate", "transform")
workflow = Workflow("example", name="Example")
workflow.workflow.connect("transform", "output")

```

**Use when**: Clear sequential steps, ETL processes, data pipelines

### 2. **Fan-Out/Fan-In Pattern**
Parallel processing with aggregation.

```python
# SDK Setup for example
from kailash import Workflow
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = Workflow("example", name="Example")
workflow.runtime = LocalRuntime()

workflow = Workflow("fanout", name="Parallel Processor")

# Single source
workflow = Workflow("example", name="Example")
workflow.workflow.add_node("source", JSONReaderNode(),
    file_path="tasks.json")

# Fan-out to multiple processors
workflow = Workflow("example", name="Example")
workflow.  # Method signature)

workflow = Workflow("example", name="Example")
workflow.  # Method signature)

workflow = Workflow("example", name="Example")
workflow.  # Method signature)

# Fan-in aggregation
workflow = Workflow("example", name="Example")
workflow.workflow.add_node("aggregator", MergeNode())

# Connect fan-out
workflow = Workflow("example", name="Example")
workflow.workflow.connect("source", "processor1")
workflow = Workflow("example", name="Example")
workflow.workflow.connect("source", "processor2")
workflow = Workflow("example", name="Example")
workflow.workflow.connect("source", "processor3")

# Connect fan-in
workflow = Workflow("example", name="Example")
workflow.  # Method signature
workflow = Workflow("example", name="Example")
workflow.  # Method signature
workflow = Workflow("example", name="Example")
workflow.  # Method signature

```

**Use when**: Parallel processing, load distribution, map-reduce patterns

### 3. **Conditional Routing Pattern**
Dynamic path selection based on data.

```python
# SDK Setup for example
from kailash import Workflow
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = Workflow("example", name="Example")
workflow.runtime = LocalRuntime()

workflow = Workflow("router", name="Conditional Router")

# Input
workflow = Workflow("example", name="Example")
workflow.workflow.add_node("input", JSONReaderNode(),
    file_path="requests.json")

# Router
workflow = Workflow("example", name="Example")
workflow.workflow.add_node("router", SwitchNode(),
    conditions=[
        {"output": "premium", "expression": "customer_tier == 'premium'"},
        {"output": "standard", "expression": "customer_tier == 'standard'"},
        {"output": "basic", "expression": "True"}  # Default
    ])

# Different handlers for each tier
workflow = Workflow("example", name="Example")
workflow.workflow.add_node("premium_handler", LLMAgentNode(),
    provider="openai",
    model="gpt-4",
    prompt="Premium support: {query}")

workflow = Workflow("example", name="Example")
workflow.workflow.add_node("standard_handler", LLMAgentNode(),
    provider="openai",
    model="gpt-3.5-turbo",
    prompt="Standard support: {query}")

workflow = Workflow("example", name="Example")
workflow.  # Method signature)

# Result merger
workflow = Workflow("example", name="Example")
workflow.workflow.add_node("merger", MergeNode())

# Connect routing
workflow = Workflow("example", name="Example")
workflow.workflow.connect("input", "router")
workflow = Workflow("example", name="Example")
workflow.  # Method signature
workflow = Workflow("example", name="Example")
workflow.  # Method signature
workflow = Workflow("example", name="Example")
workflow.  # Method signature

# Merge results
workflow = Workflow("example", name="Example")
workflow.  # Method signature
workflow = Workflow("example", name="Example")
workflow.  # Method signature
workflow = Workflow("example", name="Example")
workflow.  # Method signature

```

**Use when**: Different processing paths, A/B testing, tier-based logic

### 4. **Recursive/Cyclic Pattern**
Iterative processing with convergence.

```python
# SDK Setup for example
from kailash import Workflow
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = Workflow("example", name="Example")
workflow.runtime = LocalRuntime()

workflow = Workflow("cyclic", name="Iterative Optimizer")

# Initial data
workflow = Workflow("example", name="Example")
workflow.  # Method signature)

# Iterative processor
workflow = Workflow("example", name="Example")
workflow.  # Method signature
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
workflow = Workflow("example", name="Example")
workflow.  # Method signature

# Create cycle
workflow = Workflow("example", name="Example")
workflow.  # Method signature

```

**Use when**: Optimization, refinement, iterative algorithms

### 5. **Event-Driven Pattern**
Reactive processing triggered by events.

```python
# SDK Setup for example
from kailash import Workflow
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = Workflow("example", name="Example")
workflow.runtime = LocalRuntime()

workflow = Workflow("event-driven", name="Event Processor")

# Event listener
workflow = Workflow("example", name="Example")
workflow.  # Method signature)

# Event router
workflow = Workflow("example", name="Example")
workflow.workflow.add_node("router", SwitchNode(),
    conditions=[
        {"output": "created", "expression": "event_type == 'order.created'"},
        {"output": "updated", "expression": "event_type == 'order.updated'"},
        {"output": "cancelled", "expression": "event_type == 'order.cancelled'"}
    ])

# Event handlers
workflow = Workflow("example", name="Example")
workflow.workflow.add_node("handle_created", WorkflowNode(
    workflow=order_creation_workflow
))

workflow = Workflow("example", name="Example")
workflow.workflow.add_node("handle_updated", WorkflowNode(
    workflow=order_update_workflow
))

workflow = Workflow("example", name="Example")
workflow.workflow.add_node("handle_cancelled", WorkflowNode(
    workflow=order_cancellation_workflow
))

# Connect event flow
workflow = Workflow("example", name="Example")
workflow.  # Method signature
workflow = Workflow("example", name="Example")
workflow.  # Method signature
workflow = Workflow("example", name="Example")
workflow.  # Method signature
workflow = Workflow("example", name="Example")
workflow.  # Method signature

```

**Use when**: Message queues, webhooks, real-time systems

### 6. **Saga Pattern**
Distributed transactions with compensation.

```python
# SDK Setup for example
from kailash import Workflow
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = Workflow("example", name="Example")
workflow.runtime = LocalRuntime()

workflow = Workflow("saga", name="Order Saga")

# Transaction steps
workflow = Workflow("example", name="Example")
workflow.workflow.add_node("reserve_inventory", HTTPRequestNode(),
    url="${INVENTORY_API}/reserve",
    method="POST")

workflow = Workflow("example", name="Example")
workflow.workflow.add_node("charge_payment", HTTPRequestNode(),
    url="${PAYMENT_API}/charge",
    method="POST")

workflow = Workflow("example", name="Example")
workflow.workflow.add_node("create_shipment", HTTPRequestNode(),
    url="${SHIPPING_API}/create",
    method="POST")

# Compensation steps
workflow = Workflow("example", name="Example")
workflow.workflow.add_node("release_inventory", HTTPRequestNode(),
    url="${INVENTORY_API}/release",
    method="POST")

workflow = Workflow("example", name="Example")
workflow.workflow.add_node("refund_payment", HTTPRequestNode(),
    url="${PAYMENT_API}/refund",
    method="POST")

# Saga coordinator
workflow = Workflow("example", name="Example")
workflow.  # Method signature)

```

**Use when**: Distributed transactions, microservices, rollback support

## 🏗️ Composition Patterns

### Nested Workflows
```python
# SDK Setup for example
from kailash import Workflow
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = Workflow("example", name="Example")
workflow.runtime = LocalRuntime()

# Main workflow
main_workflow = Workflow("main", name="Main Process")

# Sub-workflows
validation_workflow = create_validation_workflow()
processing_workflow = create_processing_workflow()
reporting_workflow = create_reporting_workflow()

# Compose using WorkflowNode
workflow = Workflow("example", name="Example")
workflow.workflow.add_node("validate", WorkflowNode(
    workflow=validation_workflow
))
workflow = Workflow("example", name="Example")
workflow.workflow.add_node("process", WorkflowNode(
    workflow=processing_workflow
))
workflow = Workflow("example", name="Example")
workflow.workflow.add_node("report", WorkflowNode(
    workflow=reporting_workflow
))

# Connect sub-workflows
workflow = Workflow("example", name="Example")
workflow.workflow.connect("validate", "process")
workflow = Workflow("example", name="Example")
workflow.workflow.connect("process", "report")

```

### Dynamic Workflow Generation
```python
# SDK Setup for example
from kailash import Workflow
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = Workflow("example", name="Example")
workflow.runtime = LocalRuntime()

def workflow.()  # Type signature example -> Workflow:
    """Generate workflow based on configuration."""
    workflow = Workflow("example", name="Example")
workflow.method()  # Example
    # Add nodes based on config
    for node_config in config['nodes']:
        node_class = globals()[node_config['type']]
        node = node_class(**node_config['params'])
workflow = Workflow("example", name="Example")
workflow.workflow.add_node(node_config['id'], node)

    # Add connections
    for conn in config['connections']:
workflow = Workflow("example", name="Example")
workflow.workflow.connect(
            conn['from'],
            conn['to'],
            mapping=conn.get('mapping')
        )

    return workflow

# Usage
workflow = Workflow("example", name="Example")
workflow.workflow.yaml")
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
