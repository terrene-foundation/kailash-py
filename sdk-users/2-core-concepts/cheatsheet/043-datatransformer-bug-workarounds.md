# DataTransformer Bug Workarounds

## 🎯 Issue Overview
**DataTransformer Dict Output Bug**: DataTransformer sometimes passes only dictionary keys as a list instead of the full dictionary when data flows between nodes.

## 🐛 Bug Symptoms
```python
# Expected input to DataTransformer
data = {"files": [...], "count": 5}

# What actually arrives (BUG)
data = ["files", "count"]  # List of keys only!

```

## ✅ **STATUS: FULLY RESOLVED**
The bug has been **completely fixed** as of Session 070:
1. **DataTransformer** now correctly accepts arbitrary parameters via `validate_inputs()`
2. **LocalRuntime** now supports nested path mapping (e.g., `"result.files": "files"`)
3. All test scenarios pass successfully

### What Was Fixed
- **LocalRuntime** `_prepare_node_inputs()` method now handles nested path navigation
- Supports dot notation for mapping nested fields: `# mapping removed)}, Content: {data}")

if isinstance(data, list):
    print("WORKAROUND: DataTransformer bug detected - got list of keys")
    # Create fallback data or use default values
    files_by_type = {"csv": [], "json": []}  # Fallback
    bug_detected = True
else:
    # Normal processing
    files_by_type = data.get("files_by_type", {})
    bug_detected = False

# Continue with processing...
result = {"processed": files_by_type, "bug_detected": bug_detected}
"""

```

### Pattern 2: Key-Based Reconstruction
```python
transformation = """
# WORKAROUND: Reconstruct data from known keys
if isinstance(data, list):
    print("WORKAROUND: Reconstructing data from keys")
    # Map known keys to expected data structure
    if "health_checks" in data:
        # Reconstruct health monitoring data
        health_checks = [
            {"service": "api", "status": "healthy", "response_time": 45}
        ]
        summary = {"total_services": 1, "healthy": 1}
    else:
        # Default reconstruction
        health_checks = []
        summary = {}
    bug_detected = True
else:
    health_checks = data.get("health_checks", [])
    summary = data.get("summary", {})
    bug_detected = False

result = {"health_checks": health_checks, "summary": summary}
"""

```

### Pattern 3: globals() Variable Access
```python
transformation = """
# WORKAROUND: Use globals() to access mapped variables
print(f"Available variables: {list(globals().keys())}")

# Access mapped variables directly from globals()
files_by_type = globals().get("files_by_type", {})
directory_stats = globals().get("directory_stats", {})

# Check if variables were properly mapped
if files_by_type:
    csv_files = files_by_type.get("csv", [])
    result = {"csv_files": csv_files, "source": "mapped_correctly"}
else:
    result = {"csv_files": [], "source": "fallback_data"}
"""

```

## 🚨 Bug Detection Strategies

### Logging for Debugging
```python
transformation = """
# Comprehensive debug logging
print(f"=== DATATRANSFORMER DEBUG ===")
print(f"Input type: {type(data)}")
print(f"Input content: {data}")
print(f"Available locals: {list(globals().keys())}")

# Check for each expected variable
expected_vars = ["files_by_type", "summary", "results"]
for var in expected_vars:
    if var in globals():
        print(f"✅ {var}: {type(globals()[var])}")
    else:
        print(f"❌ {var}: MISSING")

# Determine bug status
bug_detected = isinstance(data, list) and len(data) > 0 and all(isinstance(x, str) for x in data)
print(f"Bug detected: {bug_detected}")
"""

```

### Validation Functions
```python
transformation = """
def detect_datatransformer_bug(data, expected_keys=None):
    '''Detect if DataTransformer bug occurred'''
    if not isinstance(data, list):
        return False

    if expected_keys:
        return all(key in data for key in expected_keys)

    # Generic detection: list of strings that look like dict keys
    return len(data) > 0 and all(isinstance(x, str) for x in data)

def create_fallback_data(keys, data_type="health_monitoring"):
    '''Create reasonable fallback data based on keys and context'''
    if data_type == "health_monitoring":
        return {
            "health_checks": [],
            "summary": {"total_services": 0, "healthy": 0},
            "timestamp": datetime.now().isoformat()
        }
    # Add more fallback patterns as needed
    return {}

# Use the functions
bug_detected = detect_datatransformer_bug(data, ["health_checks", "summary"])
if bug_detected:
    data = create_fallback_data(data, "health_monitoring")
"""

```

## 📋 Prevention Strategies

### Direct Variable Mapping
```python
# SDK Setup for example
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = WorkflowBuilder()
# Runtime should be created separately
runtime = LocalRuntime()

# ❌ Avoid complex dict through 'data'
workflow = WorkflowBuilder()
# Workflow setup goes here  # Method signature

# ✅ Use specific variable mapping
workflow = WorkflowBuilder()
# Workflow setup goes here  # Method signature

```

### Simplify Transformations
```python
# SDK Setup for example
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = WorkflowBuilder()
# Runtime should be created separately
runtime = LocalRuntime()

# ✅ Break complex transformations into simple steps
file_extractor = DataTransformer(transformations=["""
files = files_by_type.get("csv", [])
result = {"csv_files": files}
"""])

file_processor = DataTransformer(transformations=["""
processed = [process_file(f) for f in csv_files]
result = {"processed_files": processed}
"""])

# Chain them instead of one complex transformation
workflow = WorkflowBuilder()
workflow.add_connection("extractor", "result", "processor", "input")

```

## 🔗 Workflow Integration

### Robust Error Handling
```python
error_tolerant_transform = DataTransformer(transformations=["""
try:
    # Primary processing path
    if isinstance(data, dict):
        result = process_normal_data(data)
    else:
        # Fallback processing
        result = process_with_workaround(data)
        result["workaround_applied"] = True

except Exception as e:
    # Graceful degradation
    result = {
        "error": str(e),
        "fallback_data": create_minimal_result(),
        "processing_failed": True
    }
"""])

```

### Testing for Bug Presence
```python
# SDK Setup for example
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = WorkflowBuilder()
# Runtime should be created separately
runtime = LocalRuntime()

# Test workflow to detect if bug is present in your environment
test_workflow = WorkflowBuilder()

# Create test data
test_data = DirectoryReaderNode(directory_path="./test_data")
workflow = WorkflowBuilder()
workflow.add_node("data_source", test_data)

# Test transformer
bug_tester = DataTransformer(transformations=["""
bug_detected = isinstance(data, list) and "files_by_type" in data
result = {"bug_present": bug_detected, "data_type": type(data).__name__}
"""])

workflow = WorkflowBuilder()
workflow.add_node("bug_tester", bug_tester)
workflow = WorkflowBuilder()
# Workflow setup goes here  # Method signature

```

## ⚠️ Best Practices

### ✅ Do
- Always include bug detection in DataTransformer code
- Log input types and content for debugging
- Provide meaningful fallback data
- Test workflows with both correct and buggy data
- Use direct variable mapping when possible

### ❌ Don't
- Assume DataTransformer inputs are always correctly typed
- Ignore the bug in production workflows
- Create brittle transformations that fail on list inputs
- Use complex nested data structures unnecessarily

## 🔗 Related Patterns
- **[Error Handling](007-error-handling.md)**
- **[DataTransformer Usage](004-common-node-patterns.md#datatransformer)**
- **[Debugging Workflows](022-cycle-debugging-troubleshooting.md)**

---
**Created**: Session 060 | **Status**: Critical Fix Applied | **Bug Status**: Fixed in SDK v0.1.6+
