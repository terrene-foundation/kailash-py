# Action Plan: Fix Run vs Execute Violations

## Summary of Violations Found

### Production Code (15+ violations)
1. **API Module** - `custom_nodes_secure.py`: 3 violations
2. **Middleware** - `realtime.py`: 1 violation
3. **Admin Nodes** - `audit_log.py`, `permission_check.py`: 10+ violations
4. **RAG Module** - `advanced.py`: 4 violations

### Test Code (12+ violations)
- `test_pythoncode_parameter_injection.py`: 12 violations

### Technical Debt
- 3 nodes still implement `.process()` method
- Workflow graph supports deprecated `.process()` calls

## Priority Fixes

### 🔴 P0 - Critical Production Fixes

#### 1. Fix custom_nodes_secure.py
```python
# Line 320 - Change:
result = python_node.run(**test_data)
# To:
result = python_node.execute(**test_data)
```

#### 2. Fix realtime.py
```python
# Line 381 - Change:
response = self.http_node.run(url=url, method="POST", json_data=payload, headers=headers)
# To:
response = self.http_node.execute(url=url, method="POST", json_data=payload, headers=headers)
```

### 🟡 P1 - Test Fixes

Fix all occurrences in `test_pythoncode_parameter_injection.py`:
```python
# Change all:
result = node.run(...)
# To:
result = node.execute(...)
```

### 🟠 P2 - Technical Debt

1. Deprecate `.process()` method support in workflow graph
2. Update nodes implementing `.process()` to use standard pattern
3. Add linting rules to prevent future violations

## Verification Script

```python
#!/usr/bin/env python3
"""Verify all run() calls are fixed."""
import subprocess
import sys

def check_violations():
    # Check for .run() calls (excluding legitimate uses)
    cmd = ['rg', r'\.run\(', '--type', 'py', '-g', '!**/migrations/**']
    result = subprocess.run(cmd, capture_output=True, text=True)

    violations = []
    for line in result.stdout.split('\n'):
        if line and not any(ok in line for ok in ['asyncio.run', 'uvicorn.run', 'def run(']):
            violations.append(line)

    return violations

if __name__ == "__main__":
    violations = check_violations()
    if violations:
        print(f"Found {len(violations)} potential violations:")
        for v in violations[:10]:  # Show first 10
            print(f"  {v}")
        sys.exit(1)
    else:
        print("✅ No violations found!")
        sys.exit(0)
```

## Implementation Steps

1. **Create feature branch**: `fix/run-execute-violations`
2. **Fix production code first** (highest risk)
3. **Fix test code** (ensure tests still pass)
4. **Add pre-commit hook** to prevent future violations
5. **Update developer documentation**
6. **Create ADR** documenting the policy enforcement

## Expected Impact

- **Improved Security**: All node executions will have proper validation
- **Better Debugging**: Consistent logging and error handling
- **Performance Monitoring**: All executions tracked properly
- **Code Consistency**: Single execution pattern across codebase
