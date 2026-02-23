# Maintenance Scripts

Code quality, cleanup, and refactoring scripts for the Kailash SDK codebase.

## 📁 Scripts Overview

| Script                   | Purpose                            | Scope              | Safe to Run       |
| ------------------------ | ---------------------------------- | ------------------ | ----------------- |
| `fix-imports.py`         | Fix import errors and code issues  | Examples directory | ✅ Yes            |
| `refactor-pythoncode.py` | Convert string code to functions   | Specific files     | ⚠️ Review changes |
| `consolidate-outputs.py` | Merge scattered output directories | Project-wide       | ✅ Yes            |
| `fix-hardcoded-paths.py` | Replace hardcoded paths            | Examples directory | ✅ Yes            |

## 🚀 Quick Start

### Daily Maintenance

```bash
# Fix common import and code issues
./fix-imports.py

# Consolidate scattered output files
./consolidate-outputs.py

# Check for hardcoded paths
./fix-hardcoded-paths.py --dry-run
```

### Code Refactoring

```bash
# Refactor PythonCodeNode patterns (review changes!)
./refactor-pythoncode.py examples/feature_examples/ai/

# Check what would be changed first
./refactor-pythoncode.py --dry-run examples/
```

## 📋 Detailed Script Documentation

### `fix-imports.py`

**Purpose**: Comprehensive fixing of common import errors and code issues

**What It Fixes**:

- **MonitoredLLMAgentNode** → `LLMAgentNode(enable_monitoring=True)`
- **LocalWorkflowRunner** → `LocalRuntime`
- **EnhancedAccessControlManager** → `AccessControlManager`
- **Duplicate imports** - Removes redundant import statements
- **Logger formatting** - Secures logger calls with f-strings
- **Data path utilities** - Corrects import paths
- **Deprecated parameters** - Removes obsolete route parameters

**Features**:

- Dry run mode to preview changes
- Verbose output showing all modifications
- File-specific targeting
- Comprehensive change tracking
- Regex-based pattern matching

**Usage**:

```bash
# Fix all examples
./fix-imports.py

# Fix specific file
./fix-imports.py --file examples/ai/llm_example.py

# See what would be changed
./fix-imports.py --dry-run

# Verbose output
./fix-imports.py --verbose

# Custom directory
./fix-imports.py --directory examples/feature_examples/security/
```

**Example Output**:

```
🔧 Fixing Common Import Errors and Code Issues
============================================================
Found 47 Python files to process

✅ Fixed: examples/ai/llm_agent_example.py
   - Replaced: MonitoredLLMAgentNode( → LLMAgentNode(enable_monitoring=True,
   - Replaced: from kailash.runtime import LocalWorkflowRunner → from kailash.runtime import LocalRuntime
   - Fixed duplicate imports in line: from kailash.nodes.ai import LLMAgentNode

Summary:
  ✅ Fixed: 12 files
  🔧 Total changes: 28
  ❌ Errors: 0 files
  ⏭️ No changes needed: 35 files
```

**Safe Patterns Fixed**:
All replacements are safe and backward-compatible, following SDK best practices established in recent sessions.

### `refactor-pythoncode.py`

**Purpose**: Convert PythonCodeNode string code blocks to `.from_function()` pattern

**⚠️ Important**: This script makes significant code changes. Always review results before committing.

**What It Does**:

1. Finds PythonCodeNode instances with multi-line string code (>3 lines)
2. Extracts code and converts to standalone function
3. Analyzes code to determine function parameters
4. Replaces with `.from_function()` pattern
5. Formats result with black (if available)

**Features**:

- Smart parameter detection (`input_data`, `iteration`, `model`, etc.)
- Import handling (moves imports inside functions)
- Return value detection
- Preserves all original PythonCodeNode parameters
- Automatic code formatting

**Usage**:

```bash
# Refactor specific file
./refactor-pythoncode.py examples/ai/complex_workflow.py

# Refactor entire directory
./refactor-pythoncode.py examples/feature_examples/workflows/

# See what would be changed
./refactor-pythoncode.py --dry-run examples/

# Custom line threshold
./refactor-pythoncode.py --min-lines 5 examples/
```

**Before/After Example**:

_Before_:

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

_After_:

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

**When NOT to Use**:

- Single-line code blocks
- Code blocks ≤ 3 lines
- Dynamic code generation
- Template-based code

### `consolidate-outputs.py`

**Purpose**: Consolidate scattered output directories into centralized `data/outputs/` structure

**What It Consolidates**:

- `outputs/` (root level)
- `examples/outputs/`
- `examples/workflow_examples/outputs/`
- `examples/cycle_analysis_output/`
- `examples/feature-tests/*/outputs/`
- Any other scattered output directories

**Organization Strategy**:

- **cycle_analysis/** - Cycle analysis outputs
- **visualizations/** - Visualization outputs
- **workflows/** - Workflow outputs
- **misc/** - Other outputs

**Features**:

- Safe file moving (preserves relative structure)
- Automatic directory creation
- File count reporting
- Empty directory cleanup

**Usage**:

```bash
# Consolidate all outputs
./consolidate-outputs.py

# The script is fully automatic - no options needed
```

**Example Output**:

```
🔄 Consolidating output directories to data/outputs/
============================================================

📁 Found: examples/outputs
   Moving: analysis.json -> workflows/analysis.json
   Moving: chart.png -> workflows/chart.png
   ✅ Moved 15 files and removed examples/outputs

📁 Found: examples/cycle_analysis_output
   Moving: cycles.json -> cycle_analysis/cycles.json
   ✅ Moved 3 files and removed examples/cycle_analysis_output

============================================================
✅ Consolidation complete!

All outputs are now in: /path/to/data/outputs
Organized into:
  - workflows/: 15 files
  - cycle_analysis/: 3 files
  - visualizations/: 8 files
```

### `fix-hardcoded-paths.py`

**Purpose**: Replace hardcoded file paths with proper data path utilities

**What It Fixes**:

- `data/` → `get_input_data_path()`
- `examples/data/` → `get_input_data_path()`
- `../data/` → `get_input_data_path()`
- `outputs/` → `get_output_data_path()`
- Hardcoded absolute paths

**Features**:

- Preserves URLs and Docker paths
- Smart context detection
- Dry run mode
- Detailed change reporting

**Usage**:

```bash
# Fix all hardcoded paths
./fix-hardcoded-paths.py

# See what would be changed
./fix-hardcoded-paths.py --dry-run

# Fix specific file
./fix-hardcoded-paths.py --file examples/data_processing.py
```

## 🔧 Best Practices

### Before Running Scripts

**1. Always backup important work**:

```bash
git add -A
git commit -m "Before maintenance scripts"
```

**2. Use dry-run mode first**:

```bash
./fix-imports.py --dry-run
./refactor-pythoncode.py --dry-run examples/
```

**3. Run tests after changes**:

```bash
# After maintenance
python -m pytest tests/
```

### Script Usage Guidelines

**fix-imports.py**:

- ✅ Safe to run anytime
- ✅ Run before commits
- ✅ Part of daily workflow

**refactor-pythoncode.py**:

- ⚠️ Review all changes
- ⚠️ Test thoroughly after running
- ⚠️ Use on one file at a time initially

**consolidate-outputs.py**:

- ✅ Safe to run
- ✅ Run when outputs are scattered
- ✅ Improves project organization

**fix-hardcoded-paths.py**:

- ✅ Safe to run with dry-run first
- ✅ Follow up with path validation
- ✅ Part of code quality workflow

### Maintenance Workflow

**Daily** (as needed):

```bash
./fix-imports.py
```

**Weekly** (code quality):

```bash
./fix-imports.py --verbose
./consolidate-outputs.py
./fix-hardcoded-paths.py --dry-run
```

**Before Release** (comprehensive):

```bash
./fix-imports.py
./consolidate-outputs.py
./fix-hardcoded-paths.py
./refactor-pythoncode.py --dry-run examples/
# Review refactoring suggestions manually
```

## 🐛 Troubleshooting

### Common Issues

**Permission errors**:

```bash
# Ensure files are writable
chmod u+w examples/**/*.py
```

**Encoding issues**:

```bash
# Scripts handle UTF-8 encoding
# Ensure your files are UTF-8 encoded
file examples/some_file.py
```

**Git conflicts after changes**:

```bash
# Review changes carefully
git diff

# Stage changes selectively
git add -p
```

### Script-Specific Issues

**fix-imports.py fails**:

- Check file permissions
- Verify Python syntax before running
- Use `--verbose` to see detailed errors

**refactor-pythoncode.py breaks code**:

- Always use `--dry-run` first
- Review generated functions manually
- Test examples after refactoring

**consolidate-outputs.py moves wrong files**:

- Check that files are actually output files
- Verify no important source files in output directories

## 📊 Integration with Testing

### Automated Workflow

```bash
# 1. Fix imports and common issues
./fix-imports.py

# 2. Test that fixes work
python -m pytest tests/ -x

# 3. If tests pass, run full suite
python -m pytest tests/

# 4. Clean up outputs
./consolidate-outputs.py
```

### CI/CD Integration

```yaml
# GitHub Actions example
- name: Fix Common Issues
  run: |
    ./scripts/maintenance/fix-imports.py
    ./scripts/maintenance/consolidate-outputs.py

- name: Test After Fixes
  run: python -m pytest tests/
```

## 🤝 Contributing

### Adding New Fixes

1. Add patterns to appropriate script's fix list
2. Test with various examples
3. Ensure changes are safe and reversible
4. Update documentation

### Creating New Maintenance Scripts

1. Follow existing script patterns
2. Include dry-run mode
3. Add comprehensive error handling
4. Document all changes made

### Modifying Existing Scripts

- Maintain backward compatibility
- Test with edge cases
- Update help text and documentation
- Consider performance impact

---

**Safety Level**: fix-imports.py and consolidate-outputs.py are safe. refactor-pythoncode.py requires review.
**Frequency**: fix-imports.py daily, others weekly or as needed
**Last Updated**: Scripts directory reorganization
