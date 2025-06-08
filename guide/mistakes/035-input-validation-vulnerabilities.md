# Mistake #035: Input Validation Vulnerabilities

## Problem
Not properly validating user inputs.

### Bad Example
```python
# BAD - No input validation
def execute_code(code_string):
    exec(code_string)  # Dangerous!

# GOOD - Input validation and sandboxing
def execute_code(code_string):
    if not isinstance(code_string, str):
        raise ValueError("Code must be string")
    if len(code_string) > MAX_CODE_LENGTH:
        raise ValueError("Code too long")
    # Execute in sandboxed environment

```

## Solution


## Status
Security review still needed for PythonCodeNode

## Categories
security

---
