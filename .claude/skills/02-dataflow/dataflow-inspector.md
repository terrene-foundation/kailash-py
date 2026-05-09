---
name: dataflow-inspector
description: "Inspector API for DataFlow workflow introspection, debugging, and validation. Use when debugging workflows, tracing parameters, analyzing connections, finding broken links, validating structure, or need workflow analysis."
---

# DataFlow Inspector — Workflow Introspection API

18 inspection methods for workflows, nodes, connections, and parameters. Zero configuration, <1ms per method (cached).

## Basic Usage

```python
from dataflow import DataFlow
from dataflow.platform.inspector import Inspector
from kailash.workflow.builder import WorkflowBuilder

db = DataFlow("postgresql://localhost/mydb")

@db.model
class User:
    id: str
    name: str
    email: str

workflow = WorkflowBuilder()
workflow.add_node("UserCreateNode", "create", {"data": {"name": "Alice", "email": "alice@example.com"}})

inspector = Inspector(db)
inspector.workflow_obj = workflow.build()

connections = inspector.connections()
order = inspector.execution_order()
summary = inspector.workflow_summary()
```

## Connection Analysis (5 methods)

```python
connections = inspector.connections()
# [{'source': 'prepare_data', 'source_output': 'result', 'target': 'create_user', 'target_input': 'data'}]

result = inspector.validate_connections()
# {'is_valid': True/False, 'errors': [...], 'warnings': [...]}

broken = inspector.find_broken_connections()
# [{'connection': {...}, 'reason': 'Source output not found'}]

chain = inspector.connection_chain("prepare_data", "create_user")
# [('prepare_data', 'result'), ('create_user', 'data')]

graph = inspector.connection_graph()  # NetworkX-compatible graph
```

## Parameter Tracing (5 methods)

```python
trace = inspector.trace_parameter("create_user", "data")
# {'node': 'create_user', 'parameter': 'data', 'source_node': 'prepare_data', 'source_output': 'result'}

flow = inspector.parameter_flow("initial_input", "final_output")
# [('initial_input', 'data'), ('transform_1', 'input'), ('final_output', 'data')]

source = inspector.find_parameter_source("create_user", "data")
# {'node': 'prepare_data', 'output': 'result'}

deps = inspector.parameter_dependencies("create_user")
# {'data': {'source_node': 'prepare_data', 'source_output': 'result'}}

consumers = inspector.parameter_consumers("prepare_data", "result")
# [{'node': 'create_user', 'parameter': 'data'}, ...]
```

## Node Analysis (5 methods)

```python
deps = inspector.node_dependencies("create_user")       # ['prepare_data', 'validate_input']
dependents = inspector.node_dependents("create_user")    # ['send_email', 'log_creation']
order = inspector.execution_order()                       # ['input', 'validate', 'prepare_data', 'create_user']
schema = inspector.node_schema("create_user")            # {'inputs': {...}, 'outputs': {...}, 'node_type': '...'}
diff = inspector.compare_nodes("create_user", "create_product")  # {'common_inputs': [...], 'unique_inputs_1': [...]}
```

## Workflow Analysis (3 methods)

```python
summary = inspector.workflow_summary()
# {'total_nodes': 5, 'total_connections': 4, 'entry_nodes': ['input'],
#  'exit_nodes': ['send_email'], 'longest_path': 4, 'cyclic': False}

metrics = inspector.workflow_metrics()
# {'complexity': 'medium', 'branching_factor': 1.8, 'max_fan_out': 3, 'critical_path_length': 5}

report = inspector.workflow_validation_report()
# {'is_valid': True/False, 'errors': [...], 'warnings': [...], 'suggestions': [...]}
```

## Validate Before Execution

```python
inspector = Inspector(db)
inspector.workflow_obj = workflow.build()
report = inspector.workflow_validation_report()

if report['is_valid']:
    results, run_id = runtime.execute(workflow.build())
else:
    for error in report['errors']:
        print(f"  - {error}")
```

## Diagnose Missing Parameters

```python
trace = inspector.trace_parameter("create_user", "data")
if trace is None:
    deps = inspector.parameter_dependencies("create_user")
    print(f"Current dependencies: {deps}")
```

## CLI Integration

```bash
dataflow-validate workflow.py --output text       # Uses workflow_validation_report()
dataflow-analyze workflow.py --verbosity 2        # Uses workflow_metrics()
dataflow-debug workflow.py --inspect-node create_user  # Uses node_schema(), parameter_dependencies()
```

## Performance

| Operation                    | Complexity | Time |
| ---------------------------- | ---------- | ---- |
| connections()                | O(n)       | <1ms |
| execution_order()            | O(n+e)     | <2ms |
| node_dependencies()          | O(d)       | <1ms |
| trace_parameter()            | O(d)       | <1ms |
| workflow_validation_report() | O(n+e)     | <5ms |

Results cached per workflow instance. DataFlow 0.8.0+ required.
