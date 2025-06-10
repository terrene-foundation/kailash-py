# PythonCodeNode Refactoring Tool

## Overview
The `refactor-pythoncode-strings.py` script automatically converts PythonCodeNode instances with multi-line string code blocks to use the `.from_function()` pattern, following the best practices established in Session 062.

## What It Does
1. **Finds** PythonCodeNode instances with string code blocks longer than 3 lines
2. **Extracts** the code and converts it to a standalone function
3. **Analyzes** the code to determine appropriate function parameters
4. **Replaces** the PythonCodeNode with `.from_function()` pattern
5. **Formats** the resulting code using black (if installed)

## Usage

### Single File
```bash
python scripts/refactor-pythoncode-strings.py path/to/your/file.py
```

### Entire Directory
```bash
python scripts/refactor-pythoncode-strings.py examples/
```

### Specific Feature Tests
```bash
python scripts/refactor-pythoncode-strings.py examples/feature-tests/workflows/cyclic/
```

## Example Transformation

### Before:
```python
processor = PythonCodeNode(
    name="data_processor",
    code="""
import pandas as pd

# Process the input data
data = input_data.get('data', [])
df = pd.DataFrame(data)

# Calculate statistics
mean_value = df['value'].mean()
result = {'mean': mean_value, 'count': len(df)}
""",
    description="Process data"
)
```

### After:
```python
def process_data(input_data: dict, **kwargs):
    """Auto-converted from PythonCodeNode string code."""
    import pandas as pd
    
    # Process the input data
    data = input_data.get('data', [])
    df = pd.DataFrame(data)
    
    # Calculate statistics
    mean_value = df['value'].mean()
    result = {'mean': mean_value, 'count': len(df)}
    
    return result

processor = PythonCodeNode.from_function(
    func=process_data,
    name="data_processor",
    description="Process data"
)
```

## Features
- **Smart Parameter Detection**: Automatically detects common parameters like `input_data`, `data`, `iteration`, `model`, etc.
- **Import Handling**: Moves imports inside functions to avoid global namespace pollution
- **Return Value Detection**: Identifies `result`, `output`, or the last assigned variable
- **Preserves Parameters**: Maintains all original PythonCodeNode parameters
- **Skip Short Code**: Only converts code blocks longer than 3 lines (per best practices)

## Requirements
- Python 3.7+
- Optional: `black` for code formatting (`pip install black`)

## When NOT to Use
The script will NOT convert:
- Single-line code blocks
- Code blocks with 3 or fewer lines
- Dynamic code generation patterns
- Template-based code

## Best Practices
According to Session 062 guidelines, use `.from_function()` for:
- Complex logic (more than 3-5 lines)
- Code requiring IDE support
- Testable functions
- Reusable logic

Keep string code for:
- Dynamic code generation
- User-provided code
- Simple one-liners
- Runtime variable access
- Template-based generation

## Safety
- The script creates backups of your original code structure
- Review changes before committing
- Test your workflows after refactoring

## Limitations
- Complex regex-based parsing (not full AST)
- May need manual adjustment for edge cases
- Formatting requires black to be installed

## Related Documentation
- [PythonCodeNode Best Practices](../sdk-users/essentials/cheatsheet/032-pythoncode-best-practices.md)
- [Mistake #077: String Blocks vs from_function](../shared/mistakes/077-pythoncode-string-blocks-vs-from-function.md)
- [Developer Guide: PythonCodeNode](../sdk-users/developer/04-pythoncode-node.md)