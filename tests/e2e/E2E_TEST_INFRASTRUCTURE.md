# E2E Test Infrastructure Guide

## Overview

This guide explains the robust E2E test infrastructure that ensures tests are:
- **Self-contained**: Each test manages its own data
- **Reliable**: No dependencies on external state
- **Maintainable**: Clear patterns and helpers
- **Debuggable**: Clear error messages and logging

## Architecture

### 1. Base Test Class (`test_durable_gateway_base.py`)

The `DurableGatewayTestBase` class provides:

```python
class DurableGatewayTestBase:
    # Automatic database setup/teardown
    async def setup_class(cls)
    async def teardown_class(cls)

    # Per-test gateway management
    async def setup_method(self)
    async def teardown_method(self)

    # Test data helpers
    def get_test_customer(index: int)
    def get_test_product(index: int)
    async def create_test_order(customer_id: str)
```

### 2. Configuration (`config.py`)

Centralized configuration for all tests:

```python
class E2ETestConfig:
    DATABASE = {...}  # Database connection details
    OLLAMA = {...}    # AI service configuration

    @classmethod
    def get_async_db_code(cls, operation: str) -> str
    # Generates database connection code for AsyncPythonCodeNode
```

### 3. Workflow Helpers (`workflow_helpers.py`)

Common patterns for workflow creation:

```python
class WorkflowHelpers:
    @staticmethod
    def add_db_fetch_node(workflow, node_id, query, params)
    # Adds a node that fetches from database

    @staticmethod
    def add_db_execute_node(workflow, node_id, query, params)
    # Adds a node that executes database commands
```

## Key Design Decisions

### 1. No WorkflowConnectionPool in HTTP Context

**Problem**: `WorkflowConnectionPool` objects cannot be serialized for HTTP transport.

**Solution**: All database operations use direct connections:

```python
# ❌ Don't do this
workflow.add_node("AsyncPythonCodeNode", "fetch", {
    "code": "result = await pool.process(...)",
    "inputs": {"pool": pool}  # Cannot serialize!
})

# ✅ Do this instead
workflow.add_node("AsyncPythonCodeNode", "fetch", {
    "code": """
import asyncpg
conn = await asyncpg.connect(host="localhost", ...)
try:
    result = await conn.fetch(...)
finally:
    await conn.close()
"""
})
```

### 2. Test Data Isolation

**Problem**: Tests fail due to missing or conflicting data.

**Solution**: Each test class maintains its own test data:

```python
# Test data is created with consistent IDs
test_cust_0001, test_cust_0002, ...
test_prod_0001, test_prod_0002, ...

# Tests use helper methods to get valid data
customer = self.get_test_customer(0)
order_data = await self.create_test_order(customer["customer_id"])
```

### 3. Database Schema Management

**Problem**: Tests assume database schema exists.

**Solution**: Base class manages schema lifecycle:

```python
@classmethod
async def setup_class(cls):
    # Creates all required tables
    await cls._create_test_schema(conn)
    # Seeds with test data
    await cls._seed_test_data(conn)

@classmethod
async def teardown_class(cls):
    # Cleans up test data
    await cls._cleanup_test_data(conn)
```

## Writing New E2E Tests

### Step 1: Extend the Base Class

```python
from tests.e2e.test_durable_gateway_base import DurableGatewayTestBase

class TestMyFeature(DurableGatewayTestBase):
    async def _register_test_workflows(self, gateway):
        # Register your workflows
        my_workflow = self._create_my_workflow()
        gateway.register_workflow("my_workflow", my_workflow)
```

### Step 2: Create Workflows with Proper DB Connections

```python
def _create_my_workflow(self) -> WorkflowBuilder:
    workflow = WorkflowBuilder()

    # Use the config for database operations
    workflow.add_node("AsyncPythonCodeNode", "fetch_data", {
        "code": E2ETestConfig.get_async_db_code('''
            rows = await conn.fetch("SELECT * FROM my_table")
            result = [dict(row) for row in rows]
        ''')
    })

    return workflow.build()
```

### Step 3: Write Tests Using Test Data

```python
@pytest.mark.asyncio
async def test_my_feature(self):
    # Use test data helpers
    customer = self.get_test_customer(0)
    products = self.get_random_test_products(3)

    # Make API calls
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"http://localhost:{self.port}/my_workflow/execute",
            json={"inputs": {"node_id": {"customer_id": customer["customer_id"]}}}
        )

    assert response.status_code == 200
```

## Common Patterns

### 1. Database Fetch Pattern

```python
workflow.add_node("AsyncPythonCodeNode", "fetch_orders", {
    "code": E2ETestConfig.get_async_db_code('''
        rows = await conn.fetch(
            "SELECT * FROM orders WHERE customer_id = $1",
            customer_id
        )
        result = {"orders": [dict(row) for row in rows]}
    ''')
})
```

### 2. Database Update Pattern

```python
workflow.add_node("AsyncPythonCodeNode", "update_status", {
    "code": E2ETestConfig.get_async_db_code('''
        await conn.execute(
            "UPDATE orders SET status = $1 WHERE order_id = $2",
            new_status, order_id
        )
        result = {"updated": True}
    ''')
})
```

### 3. Transaction Pattern

```python
workflow.add_node("AsyncPythonCodeNode", "complex_operation", {
    "code": E2ETestConfig.get_async_db_code('''
        async with conn.transaction():
            # Multiple operations in a transaction
            await conn.execute("INSERT INTO orders ...", ...)
            await conn.execute("UPDATE inventory ...", ...)
            await conn.execute("INSERT INTO payments ...", ...)
        result = {"success": True}
    ''')
})
```

## Debugging Tips

### 1. Check Test Data Creation

```python
# In your test
print(f"Test customers: {self._test_customers}")
print(f"Test products: {self._test_products}")
```

### 2. Verify Database State

```python
# Add debug node to workflow
workflow.add_node("AsyncPythonCodeNode", "debug_state", {
    "code": E2ETestConfig.get_async_db_code('''
        count = await conn.fetchval("SELECT COUNT(*) FROM customers")
        print(f"Customer count: {count}")
        result = {"count": count}
    ''')
})
```

### 3. Check Gateway Health

```python
# In your test
async with httpx.AsyncClient() as client:
    health = await client.get(f"http://localhost:{self.port}/health")
    print(f"Gateway health: {health.json()}")
```

## Migration Guide

To migrate existing tests:

1. **Extend Base Class**:
   ```python
   # Old
   class TestDurableGateway:

   # New
   class TestDurableGateway(DurableGatewayTestBase):
   ```

2. **Replace Pool Usage**:
   ```python
   # Old
   "code": "result = await pool.process(...)"

   # New
   "code": E2ETestConfig.get_async_db_code("...")
   ```

3. **Use Test Data**:
   ```python
   # Old
   customer_id = f"cust_{uuid.uuid4().hex}"

   # New
   customer = self.get_test_customer(0)
   customer_id = customer["customer_id"]
   ```

## Best Practices

1. **Always use test data helpers** - Don't create random IDs
2. **Close database connections** - Use try/finally blocks
3. **Handle errors gracefully** - Check for None/empty results
4. **Use transactions for complex operations** - Ensure data consistency
5. **Add logging for debugging** - Print important state changes
6. **Test both success and failure paths** - Ensure robustness

## Troubleshooting

### "Foreign key constraint violation"
- You're using an ID that doesn't exist
- Solution: Use test data helpers or create the parent record first

### "Pool is not defined"
- You're trying to use WorkflowConnectionPool in HTTP context
- Solution: Use direct database connections

### "Table does not exist"
- Schema wasn't created properly
- Solution: Check setup_class is being called

### "Connection refused"
- Database isn't running or wrong port
- Solution: Check Docker containers are running
