# Control Flow Patterns

Dynamic workflow routing and conditional logic patterns using SwitchNode and other control structures.

## Quick Reference

For practical implementation patterns and troubleshooting, see:
- **[SwitchNode Conditional Routing](../cheatsheet/020-switchnode-conditional-routing.md)** - Working examples and common mistakes
- **[Cyclic Workflows Basics](../cheatsheet/019-cyclic-workflows-basics.md)** - Data flow patterns in cycles
- **[Cycle State Persistence](../cheatsheet/030-cycle-state-persistence-patterns.md)** - State handling in control flow

Common Issues:
- **[SwitchNode Mapping Issues](../../mistakes/072-switchnode-mapping-specificity.md)** - Fixing `input_data` mapping errors
- **[Parameter Passing Issues](../../mistakes/071-cyclic-workflow-parameter-passing-patterns.md)** - Data flow in multi-node cycles
- **[Generic Output Mapping Fails](../../mistakes/074-generic-output-mapping-in-cycles.md)** - Field-specific mapping for state persistence ⚠️

## 1. Simple Boolean Routing

**Purpose**: Route workflow based on true/false conditions

```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.nodes.logic import SwitchNode
from kailash.nodes.code import PythonCodeNode
from kailash.runtime.local import LocalRuntime

workflow = WorkflowBuilder()

# Validation node that sets is_valid flag
workflow.add_node("PythonCodeNode", "validator", {}),
    code="""
# Validate data
is_valid = True
errors = []

for record in data:
    if not record.get('email') or '@' not in record['email']:
        errors.append(f"Invalid email: {record}")
        is_valid = False

result = {
    'data': data,
    'is_valid': is_valid,
    'errors': errors
}
"""
)

# Switch node for boolean routing
workflow.add_node("SwitchNode", "switch", {}),
    condition_field="is_valid",
    true_# route removed,
    false_# route removed)

# Success path
workflow.add_node("PythonCodeNode", "success_handler", {}),
    code="result = {'status': 'success', 'processed': len(data)}"
)

# Error path
workflow.add_node("PythonCodeNode", "error_handler", {}),
    code="result = {'status': 'failed', 'errors': errors}"
)

# Connections
workflow.add_connection("validator", "switch", "result", "input")
workflow.add_connection("switch", "result", "success_handler", "input")
workflow.add_connection("switch", "result", "error_handler", "input")

# Execute
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow, parameters={
    "validator": {"data": [{"email": "test@example.com"}, {"email": "invalid"}]}
})

```

## 2. Multi-Case Status Routing

**Purpose**: Route based on multiple possible values

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

# Route based on data size categories
workflow = WorkflowBuilder()
workflow.add_node("PythonCodeNode", "categorizer", {}),
    code="""
size = len(data)
if size == 0:
    status = "empty"
elif size < 100:
    status = "small"
elif size < 1000:
    status = "medium"
else:
    status = "large"

result = {"data": data, "status": status, "size": size}
"""
)

workflow = WorkflowBuilder()
workflow.add_node("SwitchNode", "router", {}),
    condition_field="status",
    routes={
        "empty": "error_handler",
        "small": "simple_processor",
        "medium": "standard_processor",
        "large": "batch_processor"
    }
)

# Different processors for each size
workflow = WorkflowBuilder()
workflow.add_node("PythonCodeNode", "error_handler", {}),
    code="result = {'error': 'No data to process'}"
)

workflow = WorkflowBuilder()
workflow.add_node("PythonCodeNode", "simple_processor", {}),
    code="result = [item * 2 for item in data]"  # Process all at once
)

workflow = WorkflowBuilder()
workflow.add_node("PythonCodeNode", "standard_processor", {}),
    code="""
# Process with progress tracking
result = []
for i, item in enumerate(data):
    result.append(item * 2)
    if i % 10 == 0:
        print(f"Processed {i}/{len(data)}")
"""
)

workflow = WorkflowBuilder()
workflow.add_node("PythonCodeNode", "batch_processor", {}),
    code="""
# Process in batches
batch_size = 100
result = []
for i in range(0, len(data), batch_size):
    batch = data[i:i+batch_size]
    processed_batch = [item * 2 for item in batch]
    result.extend(processed_batch)
    print(f"Processed batch {i//batch_size + 1}")
"""
)

# Connect all routes
workflow = WorkflowBuilder()
workflow.add_connection("source", "result", "target", "input")  # Fixed complex parameters
workflow = WorkflowBuilder()
workflow.add_connection("source", "result", "target", "input")  # Fixed complex parameters
workflow = WorkflowBuilder()
# Workflow setup goes here  # Method signature
workflow = WorkflowBuilder()
# Workflow setup goes here  # Method signature
workflow = WorkflowBuilder()
# Workflow setup goes here  # Method signature

```

## 3. Critical Pattern: Conditional Cycles (A→B→C→D→Switch→B|E)

**Purpose**: Quality improvement loops with conditional exits

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

# A: Input node
workflow = WorkflowBuilder()
workflow.add_node("PythonCodeNode", "input", {}),
    code="result = {'text': text, 'iteration': 0}"
)

# B: Processor node
workflow = WorkflowBuilder()
workflow.add_node("PythonCodeNode", "processor", {}),
    code="""
# Enhance text quality
enhanced = text.strip().capitalize()
if 'iteration' in kwargs.get('context', {}).get('cycle', {}):
    iteration = kwargs['context']['cycle']['iteration'] + 1
    enhanced = f"[v{iteration}] {enhanced}"
else:
    iteration = 1

result = {
    'text': enhanced,
    'iteration': iteration
}
"""
)

# C: Transformer node
workflow = WorkflowBuilder()
workflow.add_node("PythonCodeNode", "transformer", {}),
    code="""
# Add metadata
import datetime
result = {
    'text': text,
    'timestamp': datetime.datetime.now().isoformat(),
    'length': len(text),
    'iteration': iteration
}
"""
)

# D: Quality checker node
workflow = WorkflowBuilder()
workflow.add_node("PythonCodeNode", "checker", {}),
    code="""
# Check quality metrics
quality_score = min(1.0, length / 100)  # Simple quality metric
should_continue = quality_score < 0.8 and iteration < 5

result = {
    'data': {
        'text': text,
        'quality': quality_score,
        'iteration': iteration
    },
    'route_decision': 'retry' if should_continue else 'finish',
    'should_continue': should_continue
}
"""
)

# Switch node for routing decision
workflow = WorkflowBuilder()
workflow.add_node("SwitchNode", "switch", {}),
    condition_field="route_decision",
    routes={
        "retry": "processor",
        "finish": "output"
    }
)

# E: Output node
workflow = WorkflowBuilder()
workflow.add_node("PythonCodeNode", "output", {}),
    code="""
result = {
    'final_text': data['text'],
    'quality_score': data['quality'],
    'iterations': data['iteration'],
    'status': 'completed'
}
"""
)

# Linear flow: A → B → C → D → Switch
workflow = WorkflowBuilder()
# Workflow setup goes here  # Method signature
workflow = WorkflowBuilder()
# Workflow setup goes here  # Method signature
workflow = WorkflowBuilder()
# Workflow setup goes here  # Method signature
workflow = WorkflowBuilder()
# Workflow setup goes here  # Method signature

# Conditional routing from switch
workflow = WorkflowBuilder()
# Workflow setup goes here  # Method signature

workflow = WorkflowBuilder()
# Workflow setup goes here  # Method signature

# Execute with initial data
runtime = LocalRuntime()
runtime = LocalRuntime()
# Parameters setup
workflow.{
    "input": {"text": "hello world"}
})

```

**Key Benefits**:
- Quality improvement loops with conditional exits
- Error handling with retry logic
- Dynamic workflow behavior based on data conditions
- Clean separation of business logic and routing logic

## 4. Multi-Level Decision Trees

**Purpose**: Complex nested routing logic

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

# Customer routing workflow
workflow = WorkflowBuilder()

# First level: Active/Inactive status
workflow = WorkflowBuilder()
workflow.add_node("SwitchNode", "status_router", {}),
    condition_field="status",
    routes={
        "active": "tier_router",
        "inactive": "reactivation_flow"
    }
)

# Second level: Customer tier (for active customers)
workflow = WorkflowBuilder()
workflow.add_node("SwitchNode", "tier_router", {}),
    condition_field="tier",
    routes={
        "gold": "gold_benefits",
        "silver": "silver_benefits",
        "bronze": "bronze_benefits"
    }
)

# Third level: Region-specific processing (example for gold)
workflow = WorkflowBuilder()
workflow.add_node("SwitchNode", "gold_region_router", {}),
    condition_field="region",
    routes={
        "us": "us_gold_processor",
        "eu": "eu_gold_processor",
        "asia": "asia_gold_processor"
    }
)

# Connect the decision tree
workflow = WorkflowBuilder()
workflow.add_connection("source", "result", "target", "input")  # Fixed complex parameters
workflow = WorkflowBuilder()
workflow.add_connection("source", "result", "target", "input")  # Fixed complex parameters
workflow = WorkflowBuilder()
workflow.add_connection("source", "result", "target", "input")  # Fixed complex parameters

workflow = WorkflowBuilder()
workflow.add_connection("source", "result", "target", "input")  # Fixed complex parameters
workflow = WorkflowBuilder()
workflow.add_connection("source", "result", "target", "input")  # Fixed complex parameters

workflow = WorkflowBuilder()
workflow.add_connection("source", "result", "target", "input")  # Fixed complex parameters
workflow = WorkflowBuilder()
workflow.add_connection("source", "result", "target", "input")  # Fixed complex parameters
workflow = WorkflowBuilder()
workflow.add_connection("source", "result", "target", "input")  # Fixed complex parameters

```

## 5. Dynamic Route Generation

**Purpose**: Create routes based on runtime data

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
workflow.add_node("PythonCodeNode", "dynamic_router", {}),
    code="""
# Determine route based on complex logic
if data.get('priority') == 'high' and data.get('value') > 1000:
    # route removed, 0) > 0.7:
    # route removed):
    # route removed,
    'selected_route': route,
    'reasoning': f"Routed to {route} based on business rules"
}
"""
)

# Use the dynamic route
workflow = WorkflowBuilder()
workflow.add_node("SwitchNode", "route_switch", {}),
    condition_field="selected_route",
    routes={
        "vip_processing": "vip_handler",
        "manual_review": "review_queue",
        "auto_processing": "automated_handler",
        "standard_processing": "standard_handler"
    }
)

```

## Best Practices

1. **Route Naming**: Use clear, descriptive route names
2. **Default Routes**: Always include error/default handling
3. **Route Documentation**: Document routing logic clearly
4. **Testing**: Test all possible routes thoroughly
5. **Monitoring**: Log routing decisions for debugging

## Common Patterns

### Error Recovery Pattern
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
workflow.add_node("SwitchNode", "error_switch", {}),
    condition_field="error_type",
    routes={
        "retryable": "retry_handler",
        "permanent": "error_logger",
        "unknown": "manual_intervention"
    }
)

```

### A/B Testing Pattern
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
workflow.add_node("PythonCodeNode", "ab_test_router", {}),
    code="""
import random
# 50/50 split for A/B test
# route removed) < 0.5 else 'variant_b'
result = {'data': data, 'variant': route}
"""
)

```

### Load Balancing Pattern
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
workflow.add_node("PythonCodeNode", "load_balancer", {}),
    code="""
# Round-robin between processors
processor_count = 3
selected = hash(data.get('id', '')) % processor_count
result = {'data': data, 'processor': f'processor_{selected}'}
"""
)

```

## See Also
- [Core Patterns](01-core-patterns.md) - Basic workflow structures
- [Data Processing Patterns](03-data-processing-patterns.md) - Complex data handling
- [Error Handling Patterns](05-error-handling-patterns.md) - Resilient routing
