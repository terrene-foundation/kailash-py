# Access Control & Multi-Tenancy

```python
from kailash.access_control import UserContext
from kailash.runtime.access_controlled import AccessControlledRuntime

# Define user context
user = UserContext(
    user_id="user_001",
    tenant_id="company_abc",
    email="analyst@company.com",
    roles=["analyst", "viewer"]
)

# Create secure runtime
secure_runtime = AccessControlledRuntime(user_context=user)

# Execute with automatic permission checks
results, run_id = secure_runtime.execute(workflow)
```
