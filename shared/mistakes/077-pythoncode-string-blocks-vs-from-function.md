# Mistake #077: PythonCodeNode String Blocks vs from_function()

## Problem
Many examples used multi-line string code blocks for PythonCodeNode, missing out on IDE support benefits like syntax highlighting, auto-completion, and debugging.

### Bad Example
```python
# BAD - No IDE support, hard to debug
node = PythonCodeNode(
    name="processor",
    code="""
import pandas as pd
import numpy as np

# Complex processing logic
df = pd.DataFrame(input_data)
df['calculated'] = df['value'].apply(lambda x: np.log(x + 1))

# More processing...
result = {
    'processed_data': df.to_dict('records'),
    'stats': {
        'mean': df['calculated'].mean(),
        'std': df['calculated'].std()
    }
}
"""
)
```

### Good Example
```python
# GOOD - Full IDE support with from_function()
def process_data(input_data: list) -> dict:
    """Process data with full IDE support."""
    import pandas as pd
    import numpy as np

    # Complex processing logic (with syntax highlighting!)
    df = pd.DataFrame(input_data)
    df['calculated'] = df['value'].apply(lambda x: np.log(x + 1))

    # More processing...
    return {
        'processed_data': df.to_dict('records'),
        'stats': {
            'mean': df['calculated'].mean(),
            'std': df['calculated'].std()
        }
    }

node = PythonCodeNode.from_function(
    func=process_data,
    name="processor"
)
```

## Solution
**Default to `.from_function()` for any code longer than 3 lines**

### When to use string code:
1. **Dynamic code generation** - Code constructed at runtime
2. **User-provided code** - From UI or config files
3. **Template-based code** - With variable substitution
4. **Simple one-liners** - e.g., `"result = data * 2"`
5. **Serialization requirements** - When saving to YAML/JSON

### Benefits of from_function():
- ✅ Full syntax highlighting
- ✅ Auto-completion and IntelliSense
- ✅ Debugging with breakpoints
- ✅ Type hints and static analysis
- ✅ Refactoring support
- ✅ Test coverage tracking

## Impact
- Loss of developer productivity without IDE support
- Harder to debug string-based code
- More syntax errors that could be caught by IDE
- Difficult to refactor or analyze code

## Lesson Learned
PythonCodeNode.from_function() should be the default choice for any substantial code. String code should only be used in specific scenarios where dynamic generation is required.

## Fixed In
- Session 062 - Created refactoring tool and updated all examples
- Added to developer best practices documentation

## Categories
api-design, best-practices, developer-experience

---
