# Mistake #008: Parameter Cache Value Collision

## Issue
The parameter resolution cache had a critical bug where it used object identity (`is`) to map resolved parameters back to their input keys. This caused incorrect parameter mapping when multiple parameters had the same value.

## Example of the Bug
```python
# When a=3 and c=3, the cache would incorrectly map both to the same input
inputs = {"a": 3, "b": 8, "c": 3}
# Cache would create mapping: {"a": "a", "b": "b", "c": "a"} ❌
# This caused c to get value from a instead of its own value
```

## Root Cause
```python
# Buggy implementation
def _extract_mapping_pattern(self, inputs: dict, resolved: dict) -> dict:
    mapping = {}
    for param_name, value in resolved.items():
        for input_key, input_value in inputs.items():
            if value is input_value:  # BUG: Object identity check!
                mapping[param_name] = input_key
                break
    return mapping
```

Python caches small integers (-5 to 256), so `3 is 3` returns True. When both `a` and `c` had value 3, the cache would map both parameters to whichever input key was found first.

## Solution
The fix tracks the actual resolution decisions made by `_resolve_parameters()` instead of trying to reverse-engineer them:

```python
def _extract_mapping_pattern(self, inputs: dict, resolved: dict) -> dict:
    mapping = {}
    for param_name in resolved:
        # Direct match
        if param_name in inputs and inputs[param_name] == resolved[param_name]:
            mapping[param_name] = param_name
        else:
            # Check aliases and auto-mappings based on parameter definition
            # ... proper resolution logic
    return mapping
```

## Impact
- **Severity**: High - Caused incorrect parameter values in cyclic workflows
- **Affected**: Any workflow where multiple parameters had the same value
- **Discovery**: Found during cycle execution tests where `c` parameter was getting wrong value

## Lessons Learned
1. Never use object identity (`is`) for value comparison unless specifically needed
2. Cache implementations should track actual decisions, not reverse-engineer them
3. Test with duplicate values to catch collisions
4. Parameter resolution is complex - caching must preserve exact behavior

## Prevention
- Added specific test case for value collisions
- Comprehensive cache testing including thread safety
- Cache statistics for monitoring
- Environment variable to disable cache for debugging
