# Workflow Binding Examples

Practical examples demonstrating DataFlow's workflow binding API introduced in
TODO-154. This API provides a higher-level interface for composing workflows using
model names and operation names instead of raw node type strings.

---

## Table of Contents

- [Setup](#setup)
- [Basic Single-Model CRUD Workflow](#basic-single-model-crud-workflow)
- [Cross-Model Workflow](#cross-model-workflow)
- [Bulk Operations Workflow](#bulk-operations-workflow)
- [Workflow with Connections Between Nodes](#workflow-with-connections-between-nodes)
- [Discovering Available Nodes](#discovering-available-nodes)
- [Error Handling Patterns](#error-handling-patterns)
- [Using a Custom Runtime](#using-a-custom-runtime)
- [Combining with Raw WorkflowBuilder](#combining-with-raw-workflowbuilder)

---

## Setup

All examples assume the following setup:

```python
from dataflow import DataFlow

db = DataFlow("sqlite:///app.db")

@db.model
class User:
    name: str
    email: str
    active: bool = True

@db.model
class Order:
    user_id: int
    product: str
    quantity: int = 1
    total: float = 0.0

@db.model
class Product:
    name: str
    price: float
    in_stock: bool = True
```

---

## Basic Single-Model CRUD Workflow

### Create a User

```python
workflow = db.create_workflow("create_user")
db.add_node(workflow, "User", "Create", "create_user", {
    "name": "Alice",
    "email": "alice@example.com",
})

results, run_id = db.execute_workflow(workflow)
created_user = results["create_user"]
print(f"Created user with run_id: {run_id}")
```

### Read a User

```python
workflow = db.create_workflow("read_user")
db.add_node(workflow, "User", "Read", "read_user", {
    "id": 1,
})

results, run_id = db.execute_workflow(workflow)
user = results["read_user"]
```

### Update a User

```python
workflow = db.create_workflow("update_user")
db.add_node(workflow, "User", "Update", "update_user", {
    "filter": {"id": 1},
    "fields": {"name": "Alice Updated", "email": "alice.new@example.com"},
})

results, run_id = db.execute_workflow(workflow)
```

### Delete a User

```python
workflow = db.create_workflow("delete_user")
db.add_node(workflow, "User", "Delete", "delete_user", {
    "filter": {"id": 1},
})

results, run_id = db.execute_workflow(workflow)
```

### List Users

```python
workflow = db.create_workflow("list_users")
db.add_node(workflow, "User", "List", "list_users", {})

results, run_id = db.execute_workflow(workflow)
all_users = results["list_users"]
```

### Count Users

```python
workflow = db.create_workflow("count_users")
db.add_node(workflow, "User", "Count", "count_users", {})

results, run_id = db.execute_workflow(workflow)
total = results["count_users"]
```

### Upsert a User

```python
workflow = db.create_workflow("upsert_user")
db.add_node(workflow, "User", "Upsert", "upsert_user", {
    "filter": {"email": "alice@example.com"},
    "fields": {"name": "Alice", "email": "alice@example.com", "active": True},
})

results, run_id = db.execute_workflow(workflow)
```

---

## Cross-Model Workflow

Build a workflow that spans multiple models. This example creates a user, a product,
and an order in a single workflow execution.

```python
workflow = db.create_workflow("full_order_flow")

# Step 1: Create the user
db.add_node(workflow, "User", "Create", "create_user", {
    "name": "Bob",
    "email": "bob@example.com",
})

# Step 2: Create the product
db.add_node(workflow, "Product", "Create", "create_product", {
    "name": "Widget Pro",
    "price": 29.99,
    "in_stock": True,
})

# Step 3: Create the order
# Note: node parameters are static at workflow build time.
# For dynamic values from previous nodes, use connections.
db.add_node(workflow, "Order", "Create", "create_order", {
    "user_id": 1,
    "product": "Widget Pro",
    "quantity": 3,
    "total": 89.97,
})

results, run_id = db.execute_workflow(workflow)
print(f"User: {results['create_user']}")
print(f"Product: {results['create_product']}")
print(f"Order: {results['create_order']}")
```

---

## Bulk Operations Workflow

### Bulk Create

```python
workflow = db.create_workflow("bulk_create_users")
db.add_node(workflow, "User", "BulkCreate", "bulk_create", {
    "records": [
        {"name": "Charlie", "email": "charlie@example.com"},
        {"name": "Diana", "email": "diana@example.com"},
        {"name": "Eve", "email": "eve@example.com"},
    ],
})

results, run_id = db.execute_workflow(workflow)
created = results["bulk_create"]
print(f"Created {len(created)} users")
```

### Bulk Update

```python
workflow = db.create_workflow("bulk_update_users")
db.add_node(workflow, "User", "BulkUpdate", "bulk_update", {
    "records": [
        {"filter": {"id": 1}, "fields": {"active": False}},
        {"filter": {"id": 2}, "fields": {"active": False}},
    ],
})

results, run_id = db.execute_workflow(workflow)
```

### Bulk Delete

```python
workflow = db.create_workflow("bulk_delete_users")
db.add_node(workflow, "User", "BulkDelete", "bulk_delete", {
    "records": [
        {"filter": {"id": 1}},
        {"filter": {"id": 2}},
    ],
})

results, run_id = db.execute_workflow(workflow)
```

### Bulk Upsert

```python
workflow = db.create_workflow("bulk_upsert_products")
db.add_node(workflow, "Product", "BulkUpsert", "bulk_upsert", {
    "records": [
        {
            "filter": {"name": "Widget Pro"},
            "fields": {"name": "Widget Pro", "price": 24.99, "in_stock": True},
        },
        {
            "filter": {"name": "Gadget Plus"},
            "fields": {"name": "Gadget Plus", "price": 49.99, "in_stock": True},
        },
    ],
})

results, run_id = db.execute_workflow(workflow)
```

---

## Workflow with Connections Between Nodes

Use connections to pass output from one node as input to the next. This enables
dynamic workflows where later nodes depend on earlier results.

```python
workflow = db.create_workflow("connected_flow")

# Step 1: List all active users
db.add_node(workflow, "User", "List", "list_users", {
    "filter": {"active": True},
})

# Step 2: Count all users (runs independently, no connection needed)
db.add_node(workflow, "User", "Count", "count_users", {})

# Step 3: Create a product, connected to receive user list as context
# The connections dict maps "source_node_id.output_key" -> "target_param"
db.add_node(
    workflow,
    "Product",
    "Create",
    "create_product",
    {"name": "New Product", "price": 19.99},
    connections={"list_users": "context_data"},  # pass list_users output
)

results, run_id = db.execute_workflow(workflow)
```

---

## Discovering Available Nodes

Use `get_available_nodes()` to inspect which models and operations are registered.

### List All Available Nodes

```python
all_nodes = db.get_available_nodes()
print(all_nodes)
# Output:
# {
#     'User': ['Create', 'Read', 'Update', 'Delete', 'List',
#              'Upsert', 'Count', 'BulkCreate', 'BulkUpdate',
#              'BulkDelete', 'BulkUpsert'],
#     'Order': ['Create', 'Read', 'Update', 'Delete', 'List',
#               'Upsert', 'Count', 'BulkCreate', 'BulkUpdate',
#               'BulkDelete', 'BulkUpsert'],
#     'Product': ['Create', 'Read', 'Update', 'Delete', 'List',
#                 'Upsert', 'Count', 'BulkCreate', 'BulkUpdate',
#                 'BulkDelete', 'BulkUpsert'],
# }
```

### Filter by Model

```python
user_nodes = db.get_available_nodes("User")
print(user_nodes)
# Output:
# {
#     'User': ['Create', 'Read', 'Update', 'Delete', 'List',
#              'Upsert', 'Count', 'BulkCreate', 'BulkUpdate',
#              'BulkDelete', 'BulkUpsert']
# }
```

### Dynamic Workflow Construction

Use `get_available_nodes()` to build workflows programmatically:

```python
available = db.get_available_nodes()

for model_name, operations in available.items():
    if "Count" in operations:
        workflow = db.create_workflow(f"count_{model_name.lower()}")
        db.add_node(workflow, model_name, "Count", f"count_{model_name.lower()}", {})
        results, _ = db.execute_workflow(workflow)
        print(f"{model_name}: {results[f'count_{model_name.lower()}']} records")
```

---

## Error Handling Patterns

The workflow binding API provides clear error messages when something goes wrong.

### Unregistered Model

```python
try:
    workflow = db.create_workflow("bad_workflow")
    db.add_node(workflow, "Invoice", "Create", "create_invoice", {"amount": 100})
except ValueError as e:
    print(e)
    # "Model 'Invoice' is not registered with this DataFlow instance.
    #  Available models: ['User', 'Order', 'Product'].
    #  Ensure @db.model is applied to Invoice before creating workflows."
```

### Invalid Operation

```python
try:
    workflow = db.create_workflow("bad_op")
    db.add_node(workflow, "User", "Archive", "archive_user", {"id": 1})
except ValueError as e:
    print(e)
    # "Invalid operation 'Archive' for model 'User'.
    #  Available operations: ['Create', 'Read', 'Update', 'Delete', 'List',
    #  'Upsert', 'Count', 'BulkCreate', 'BulkUpdate', 'BulkDelete', 'BulkUpsert']"
```

### Execution Errors

```python
try:
    workflow = db.create_workflow("error_flow")
    db.add_node(workflow, "User", "Read", "read_user", {"id": 99999})
    results, run_id = db.execute_workflow(workflow)
except Exception as e:
    print(f"Workflow execution failed: {e}")
```

### Wrapping Multiple Operations with Error Recovery

```python
def safe_create_user(db, name, email):
    """Create a user with error handling."""
    workflow = db.create_workflow(f"create_{name.lower()}")
    db.add_node(workflow, "User", "Create", "create_user", {
        "name": name,
        "email": email,
    })
    try:
        results, run_id = db.execute_workflow(workflow)
        return results["create_user"]
    except Exception as e:
        print(f"Failed to create user {name}: {e}")
        return None

user = safe_create_user(db, "Frank", "frank@example.com")
```

---

## Using a Custom Runtime

By default, `db.execute_workflow()` creates a `LocalRuntime`. You can pass your own
runtime for advanced configuration.

### With LocalRuntime Options

```python
from kailash.runtime import LocalRuntime

runtime = LocalRuntime(debug=True)

workflow = db.create_workflow("debug_flow")
db.add_node(workflow, "User", "List", "list_users", {})

results, run_id = db.execute_workflow(workflow, runtime=runtime)
```

### With AsyncLocalRuntime

```python
from kailash.runtime import AsyncLocalRuntime

async def run_async_workflow():
    runtime = AsyncLocalRuntime()

    workflow = db.create_workflow("async_flow")
    db.add_node(workflow, "User", "List", "list_users", {})

    results, run_id = db.execute_workflow(workflow, runtime=runtime)
    return results
```

---

## Combining with Raw WorkflowBuilder

You can mix the workflow binding API with the raw `WorkflowBuilder` when needed. Since
`db.create_workflow()` returns a standard `WorkflowBuilder`, you can add non-DataFlow
nodes directly.

```python
from kailash.runtime import LocalRuntime

workflow = db.create_workflow("mixed_flow")

# Use the binding API for DataFlow nodes
db.add_node(workflow, "User", "List", "list_users", {})

# Use the raw API for custom nodes (e.g., PythonCode, API calls)
workflow.add_node("PythonCode", "process_users", {
    "code": "result = len(inputs.get('users', []))",
}, {"list_users": "users"})

runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())
```

This flexibility ensures you are never locked into one approach and can choose the
right level of abstraction for each part of your workflow.
