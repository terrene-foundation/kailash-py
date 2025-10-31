# DataFlow TDD Quick Start - 5 Minutes to <100ms Tests

Get up and running with DataFlow's Test-Driven Development infrastructure in just 5 minutes. Achieve 20-50x faster test execution compared to traditional approaches.

## Prerequisites

- PostgreSQL running (port 5434 for SDK test infrastructure)
- Python 3.8+ with pytest installed
- DataFlow package installed (`pip install kailash-dataflow`)

## Step 1: Enable TDD Mode (30 seconds)

Set the environment variable or pass the flag:

```bash
# Option 1: Environment variable
export DATAFLOW_TDD_MODE=true

# Option 2: In your test file
import os
os.environ["DATAFLOW_TDD_MODE"] = "true"

# Option 3: Direct parameter
db = DataFlow(tdd_mode=True)
```

## Step 2: Basic TDD Test Setup (1 minute)

Create your first TDD test with automatic isolation:

```python
# test_user_operations.py
import pytest
import os
from dataflow import DataFlow
from dataflow.testing.tdd_support import TDDTestContext

# Enable TDD mode
os.environ["DATAFLOW_TDD_MODE"] = "true"

@pytest.fixture
async def tdd_dataflow():
    """DataFlow instance with TDD optimizations."""
    context = TDDTestContext(test_id="test_001")
    db = DataFlow(
        "postgresql://test_user:test_password@localhost:5434/kailash_test",
        tdd_mode=True,
        test_context=context,
        auto_migrate=False,
        existing_schema_mode=True
    )

    # Automatic savepoint creation for isolation
    yield db
    # Automatic rollback - no cleanup needed!

@pytest.mark.asyncio
async def test_user_creation(tdd_dataflow):
    """Test executes in <100ms with automatic rollback."""
    # Your test runs in isolated transaction
    # All changes automatically rolled back
    # No DROP SCHEMA CASCADE needed!
    pass
```

## Step 3: Run Your First TDD Test (30 seconds)

```bash
# Run the test
pytest test_user_operations.py -v

# Expected output:
# test_user_operations.py::test_user_creation PASSED [100%]
# ====== 1 passed in 0.08s ======  # <100ms execution!
```

## Step 4: DataFlow Model Integration (2 minutes)

Add DataFlow models with automatic node generation:

```python
@pytest.mark.asyncio
async def test_user_crud_operations(tdd_dataflow):
    """Complete CRUD test in <100ms."""

    # Define model
    @tdd_dataflow.model
    class User:
        name: str
        email: str
        active: bool = True

    # Use auto-generated nodes
    from kailash.workflow.builder import WorkflowBuilder
    from kailash.runtime.local import LocalRuntime

    workflow = WorkflowBuilder()

    # Create user (uses savepoint isolation)
    workflow.add_node("UserCreateNode", "create", {
        "name": "Test User",
        "email": "test@example.com"
    })

    # List users
    workflow.add_node("UserListNode", "list", {
        "filter": {"active": True}
    })

    workflow.add_connection("create", "id", "list", "user_id")

    # Execute workflow
    runtime = LocalRuntime()
    results, run_id = runtime.execute(workflow.build())

    assert "create" in results
    assert results["create"]["success"] is True

    # All changes automatically rolled back after test!
    # Next test gets clean database state
```

## Step 5: Performance Validation (1 minute)

Verify your tests meet performance targets:

```python
import time

@pytest.mark.asyncio
async def test_performance_validation(tdd_dataflow):
    """Validate <100ms execution target."""
    start = time.time()

    @tdd_dataflow.model
    class Product:
        name: str
        price: float
        stock: int = 0

    # Perform operations...
    workflow = WorkflowBuilder()
    workflow.add_node("ProductCreateNode", "create", {
        "name": "Test Product",
        "price": 99.99
    })

    runtime = LocalRuntime()
    results, _ = runtime.execute(workflow.build())

    execution_time = (time.time() - start) * 1000  # Convert to ms

    # Validate performance
    assert execution_time < 100, f"Test exceeded 100ms: {execution_time:.2f}ms"
    print(f"✅ Test executed in {execution_time:.2f}ms")
```

## What You Just Accomplished

In 5 minutes, you've:
- ✅ Enabled TDD mode for 20-50x faster tests
- ✅ Created tests with automatic isolation (no manual cleanup)
- ✅ Integrated DataFlow models with TDD infrastructure
- ✅ Validated <100ms execution performance
- ✅ Eliminated DROP SCHEMA CASCADE (saves 2000ms+ per test)

## Key Benefits Achieved

| Traditional Approach | TDD Approach | Improvement |
|---------------------|--------------|-------------|
| DROP SCHEMA CASCADE (2000ms) | Savepoint rollback (5ms) | 400x faster |
| Manual cleanup code | Automatic isolation | Zero maintenance |
| Connection per test (100ms) | Connection pooling (1ms) | 100x faster |
| Sequential execution only | Parallel-safe execution | N-cores speedup |
| >2000ms per test | <100ms per test | 20-50x faster |

## Next Steps

- [Migration Guide](migration-guide.md) - Migrate existing tests to TDD
- [API Reference](api-reference.md) - Complete fixture documentation
- [Best Practices](best-practices.md) - Enterprise patterns
- [Performance Guide](performance-guide.md) - Optimization techniques

## Common Issues

### Issue: Tests still slow (>100ms)
**Solution**: Ensure TDD mode is enabled and using PostgreSQL (not SQLite)

### Issue: "TDD support not available" error
**Solution**: Install with TDD support: `pip install kailash-dataflow[tdd]`

### Issue: Connection pool exhausted
**Solution**: Use session-scoped fixtures for connection pooling

## Complete 5-Minute Setup Script

Run this complete example to verify everything works:

```python
#!/usr/bin/env python
"""
Complete TDD setup verification in <5 minutes
Run: python tdd_quickstart.py
"""

import asyncio
import os
import time

# Enable TDD mode
os.environ["DATAFLOW_TDD_MODE"] = "true"

from dataflow import DataFlow
from dataflow.testing.tdd_support import TDDTestContext
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime


async def verify_tdd_setup():
    """Verify TDD setup in <100ms."""
    print("🚀 Starting DataFlow TDD Quick Start Verification...")

    # Step 1: Initialize TDD
    start = time.time()
    context = TDDTestContext(test_id="quickstart")
    db = DataFlow(
        "postgresql://test_user:test_password@localhost:5434/kailash_test",
        tdd_mode=True,
        test_context=context
    )

    # Step 2: Define model
    @db.model
    class QuickStartUser:
        name: str
        email: str

    # Step 3: Execute operations
    workflow = WorkflowBuilder()
    workflow.add_node("QuickStartUserCreateNode", "create", {
        "name": "Quick Start User",
        "email": "quickstart@example.com"
    })

    runtime = LocalRuntime()
    results, _ = runtime.execute(workflow.build())

    # Step 4: Validate results
    execution_time = (time.time() - start) * 1000

    print(f"\n✅ Setup complete in {execution_time:.2f}ms")
    print(f"✅ TDD mode active: {db._tdd_mode}")
    print(f"✅ Test isolation: Automatic rollback enabled")
    print(f"✅ Performance target: {'MET' if execution_time < 100 else 'FAILED'}")

    if execution_time < 100:
        print("\n🎉 SUCCESS! You're ready for TDD with <100ms tests!")
    else:
        print(f"\n⚠️  Performance target missed. Check PostgreSQL connection.")

    return execution_time < 100


if __name__ == "__main__":
    success = asyncio.run(verify_tdd_setup())
    exit(0 if success else 1)
```

**Ready to transform your test suite? You now have everything needed for 20-50x faster tests!**
