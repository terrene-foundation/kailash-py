# Mistake 078: Not Using PythonCodeNode.from_function for Complex Code

**FREQUENCY: Every new session** - This is the #1 recurring mistake!

## Problem
Developers consistently use inline code strings for PythonCodeNode even when the code exceeds 3 lines, making it hard to read, test, and maintain. Despite documentation and training, this mistake occurs in EVERY new development session.

## Example of the Mistake
```python
# ❌ WRONG - Long inline code string
fraud_enricher = PythonCodeNode(
    name="fraud_enricher",
    code="""
import pandas as pd
from datetime import datetime, timedelta
import numpy as np

# 100+ lines of complex fraud detection logic...
# No IDE support, hard to test, difficult to maintain

result = enriched_transactions
"""
)
```

## Why This Happens
1. **Examples show inline code** - Documentation examples use inline for brevity
2. **Organic growth** - Code starts simple and grows over time
3. **Copy-paste habit** - Copying from Jupyter notebooks or scripts
4. **Unawareness** - Developers don't know about from_function pattern

## Correct Approach
```python
# ✅ CORRECT - Use from_function for code > 3 lines
def enrich_fraud_indicators(transaction_data: dict, customer_data: list) -> list:
    """Enrich transactions with fraud indicators.

    Args:
        transaction_data: Transaction records
        customer_data: Customer baseline data

    Returns:
        List of enriched transactions with fraud scores
    """
    import pandas as pd
    from datetime import datetime, timedelta
    import numpy as np

    # Your complex logic here with full IDE support
    # ...

    return enriched_transactions

# Create node from function
fraud_enricher = PythonCodeNode.from_function(
    name="fraud_enricher",
    func=enrich_fraud_indicators
)
```

## Guidelines
- **≤ 3 lines**: Inline code is fine
- **> 3 lines**: Always use from_function
- **Complex logic**: Always use from_function
- **Reusable code**: Always use from_function

## Benefits
1. **IDE Support**: Autocomplete, type checking, refactoring
2. **Testability**: Can unit test functions directly
3. **Reusability**: Import and reuse across workflows
4. **Maintainability**: Easier to read and modify
5. **Documentation**: Proper docstrings and type hints

## Session 064 Examples

### Finance Workflows - Before Refactoring
```python
# Credit Risk Assessment - 130+ lines inline!
fraud_enricher = PythonCodeNode(
    name="fraud_enricher",
    code="""
    import pandas as pd
    # ... 130+ lines of complex fraud detection logic
    # No IDE support for any of this!
    """
)
```

### After Refactoring
```python
def enrich_fraud_indicators(transaction_data: Any, customer_data: list) -> dict:
    """Enrich transactions with fraud indicators."""
    # Full IDE support for 130+ lines of logic
    # ...
    return {'result': enriched_transactions}

fraud_enricher = PythonCodeNode.from_function(
    name="fraud_enricher",
    func=enrich_fraud_indicators
)
```

## Prevention
- **CHECK EVERY PYTHONCODENODE** - Make it a habit
- Code review checklist should include this check
- Linting rule for PythonCodeNode code length
- Template examples should demonstrate from_function
- Developer onboarding should emphasize this pattern
- Reference this as "Mistake #078" in code reviews
