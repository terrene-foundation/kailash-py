# DataFlow Debug Agent User Guide

**Complete guide to using the Debug Agent for intelligent error analysis and solutions**

Version: 1.0.0
Last Updated: 2025-01-13

---

## Table of Contents

### Part 1: Introduction
1. [What is the Debug Agent?](#what-is-the-debug-agent)
2. [How It Works - The 5-Stage Pipeline](#how-it-works---the-5-stage-pipeline)
3. [Quick Start](#quick-start)
4. [Installation](#installation)
5. [System Requirements](#system-requirements)

### Part 2: CLI Command Usage
6. [Running the Debug Agent](#running-the-debug-agent)
7. [Command Options](#command-options)
8. [Understanding the Output](#understanding-the-output)
9. [Output Formats](#output-formats)
10. [Advanced CLI Usage](#advanced-cli-usage)

### Part 3: Common Error Scenarios
11. [Parameter Errors](#parameter-errors)
12. [Connection Errors](#connection-errors)
13. [Migration Errors](#migration-errors)
14. [Runtime Errors](#runtime-errors)
15. [Configuration Errors](#configuration-errors)

### Part 4: Programmatic Usage
16. [Python API](#python-api)
17. [Integration with DataFlow](#integration-with-dataflow)
18. [Custom Error Handlers](#custom-error-handlers)
19. [JSON Export and Automation](#json-export-and-automation)

---

# Part 1: Introduction

## What is the Debug Agent?

The **DataFlow Debug Agent** is an intelligent error analysis system that automatically diagnoses DataFlow errors and provides ranked, actionable solutions with code examples. Instead of manually searching documentation or debugging errors, the Debug Agent:

1. **Captures** error details with full stack traces
2. **Categorizes** errors into 5 categories (50+ patterns)
3. **Analyzes** workflow context using the Inspector
4. **Suggests** ranked solutions with code examples
5. **Formats** results for terminal or JSON output

### Key Features

**Intelligent Error Categorization**
- 50+ error patterns across 5 categories
- 92%+ confidence scoring with regex + semantic features
- Automatic pattern matching and confidence calculation

**Context-Aware Analysis**
- Identifies affected nodes, models, and connections
- Extracts missing parameters and type mismatches
- Provides root cause analysis with detailed context

**Ranked Solutions**
- 60+ solutions mapped to error patterns
- Relevance scoring (0.0-1.0) based on context
- Code examples with before/after comparisons
- Difficulty and time estimates

**Multiple Output Formats**
- Rich CLI output with colors and box drawing
- JSON export for automation and logging
- Programmatic Python API for custom integration

### Why Use the Debug Agent?

**Without Debug Agent:**
```python
try:
    runtime.execute(workflow.build())
except Exception as e:
    print(e)  # "NOT NULL constraint failed: users.id"
    # Now what? Search docs? Check stack trace? Trial and error?
```

**With Debug Agent:**
```python
try:
    runtime.execute(workflow.build())
except Exception as e:
    report = debug_agent.debug(e)
    print(report.to_cli_format())
    # Clear diagnosis: Missing 'id' parameter in CreateNode
    # 3 ranked solutions with code examples
    # 23ms execution time
```

### Supported Error Categories

| Category | Pattern Count | Examples |
|----------|---------------|----------|
| **PARAMETER** | 15 patterns | Missing `id`, type mismatch, invalid values, reserved fields |
| **CONNECTION** | 10 patterns | Missing source node, circular dependency, type incompatibility |
| **MIGRATION** | 8 patterns | Schema conflicts, missing table, constraint violations |
| **RUNTIME** | 10 patterns | Transaction timeout, event loop collision, node execution failed |
| **CONFIGURATION** | 7 patterns | Invalid database URL, missing environment variables, auth failed |

### Performance

- **Execution time**: 5-50ms per error
- **Accuracy**: 92%+ confidence for known patterns
- **Coverage**: 50+ patterns, 60+ solutions
- **Overhead**: <1KB memory per report

---

## How It Works - The 5-Stage Pipeline

The Debug Agent orchestrates 5 specialized components in a sequential pipeline:

### Stage 1: CAPTURE (ErrorCapture)

**Purpose**: Extract complete error details

**Captures**:
- Exception type and message
- Full stack trace with file:line references
- Error context (node names, parameters, etc.)
- Timestamp and execution metadata

**Example**:
```python
CapturedError(
    exception=ValueError(...),
    error_type="ValueError",
    message="NOT NULL constraint failed: users.id",
    stacktrace=[...],
    context={"node": "create_user", "operation": "CREATE"},
    timestamp=datetime(2025, 1, 13, 10, 30, 0)
)
```

### Stage 2: CATEGORIZE (ErrorCategorizer)

**Purpose**: Identify error pattern and category

**Process**:
1. Load 50+ patterns from `patterns.yaml`
2. Match error message against regex patterns
3. Check semantic features (error type, context)
4. Calculate confidence score (0.0-1.0)
5. Return ErrorCategory with pattern_id

**Example**:
```python
ErrorCategory(
    category="PARAMETER",
    pattern_id="PARAM_001",
    confidence=0.95,
    features={
        "missing_field": "id",
        "node_type": "CreateNode",
        "is_primary_key": True
    }
)
```

### Stage 3: ANALYZE (ContextAnalyzer)

**Purpose**: Extract workflow context and root cause

**Uses Inspector to**:
- Identify affected nodes by name
- Identify affected models by table name
- Extract missing parameters from node signatures
- Trace parameter connections and data flow
- Build context data for solution ranking

**Example**:
```python
AnalysisResult(
    root_cause="Node 'create_user' is missing required parameter 'id' (primary key)",
    affected_nodes=["create_user"],
    affected_models=["User"],
    affected_connections=[],
    context_data={
        "missing_parameter": "id",
        "is_primary_key": True,
        "node_operation": "CREATE"
    }
)
```

### Stage 4: SUGGEST (SolutionGenerator)

**Purpose**: Generate ranked solutions with code examples

**Process**:
1. Load 60+ solutions from `solutions.yaml`
2. Get solutions mapped to pattern_id
3. Calculate relevance scores based on context
4. Rank solutions by relevance
5. Filter by min_relevance threshold
6. Limit to max_solutions count

**Example**:
```python
[
    SuggestedSolution(
        solution_id="SOL_001",
        title="Add Missing 'id' Parameter to CreateNode",
        category="QUICK_FIX",
        description="Add required 'id' field to CreateNode operation",
        code_example='workflow.add_node("UserCreateNode", "create", {\n    "id": "user-123",\n    "name": "Alice"\n})',
        explanation="DataFlow requires 'id' for all CREATE operations...",
        relevance_score=0.95,
        confidence=0.95,
        difficulty="easy",
        estimated_time=1
    ),
    # ... more solutions ...
]
```

### Stage 5: FORMAT (DebugReport)

**Purpose**: Package results for output

**Creates DebugReport**:
- Captured error details
- Error category and confidence
- Analysis result with root cause
- Ranked suggested solutions
- Execution time tracking

**Output Formats**:
- `report.to_cli_format()` - Rich terminal output
- `report.to_json()` - JSON export
- `report.to_dict()` - Python dictionary

---

## Quick Start

### Basic Usage

```python
from dataflow import DataFlow
from dataflow.debug.debug_agent import DebugAgent
from dataflow.debug.knowledge_base import KnowledgeBase
from dataflow.platform.inspector import Inspector
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime import LocalRuntime

# Initialize DataFlow
db = DataFlow("postgresql://localhost/mydb")

@db.model
class User:
    id: str
    name: str
    email: str

# Initialize Debug Agent
knowledge_base = KnowledgeBase(
    "src/dataflow/debug/patterns.yaml",
    "src/dataflow/debug/solutions.yaml"
)
inspector = Inspector(db)
debug_agent = DebugAgent(knowledge_base, inspector)

# Create workflow with intentional error
workflow = WorkflowBuilder()
workflow.add_node("UserCreateNode", "create", {
    "name": "Alice"
    # Missing required 'id' parameter
})

# Execute and debug
runtime = LocalRuntime()
try:
    results, _ = runtime.execute(workflow.build())
except Exception as e:
    # Debug the error
    report = debug_agent.debug(e, max_solutions=5, min_relevance=0.3)

    # Display rich CLI output
    print(report.to_cli_format())
```

### Expected Output

```
╔════════════════════════════════════════════════════════════════════════════╗
║                           DataFlow Debug Agent                             ║
║                   Intelligent Error Analysis & Suggestions                 ║
╚════════════════════════════════════════════════════════════════════════════╝

┌─ ERROR DETAILS ────────────────────────────────────────────────────────────┐
│ Type: ValueError                                                           │
│ Category: PARAMETER (Confidence: 95%)                                      │
└────────────────────────────────────────────────────────────────────────────┘

ERROR MESSAGE:
  Missing required parameter 'id' in CreateNode

┌─ ROOT CAUSE ANALYSIS ──────────────────────────────────────────────────────┐
│ Root Cause:                                                                │
│   Node 'create' is missing required parameter 'id' (primary key)          │
│                                                                            │
│ Affected Components:                                                       │
│   • Nodes: create                                                          │
│   • Models: User                                                           │
│   • Parameters: id (primary key)                                           │
└────────────────────────────────────────────────────────────────────────────┘

┌─ SUGGESTED SOLUTIONS ──────────────────────────────────────────────────────┐
│                                                                            │
│ [1] Add Missing 'id' Parameter to CreateNode (QUICK_FIX)                  │
│     Relevance: 95% | Difficulty: easy | Time: 1 min                       │
│                                                                            │
│     Description:                                                           │
│     Add required 'id' field to CreateNode operation                       │
│                                                                            │
│     Code Example:                                                          │
│     workflow.add_node("UserCreateNode", "create", {                       │
│         "id": "user-123",  # Add missing parameter                        │
│         "name": "Alice"                                                    │
│     })                                                                     │
│                                                                            │
├────────────────────────────────────────────────────────────────────────────┤
│                                                                            │
│ [2] Use UUID for Automatic ID Generation (BEST_PRACTICE)                  │
│     Relevance: 85% | Difficulty: easy | Time: 2 min                       │
│                                                                            │
│     Description:                                                           │
│     Generate unique IDs using uuid4() for all records                     │
│                                                                            │
│     Code Example:                                                          │
│     import uuid                                                            │
│     workflow.add_node("UserCreateNode", "create", {                       │
│         "id": str(uuid.uuid4()),  # Auto-generate UUID                    │
│         "name": "Alice"                                                    │
│     })                                                                     │
│                                                                            │
└────────────────────────────────────────────────────────────────────────────┘

┌─ SUMMARY ──────────────────────────────────────────────────────────────────┐
│ Execution Time: 23.5ms                                                     │
│ Documentation: https://docs.dataflow.dev/debug-agent                       │
└────────────────────────────────────────────────────────────────────────────┘
```

---

## Installation

The Debug Agent is included with DataFlow v0.8.0+.

### Install DataFlow

```bash
# Install latest version
pip install kailash-dataflow

# Or upgrade existing installation
pip install --upgrade kailash-dataflow

# Verify version (requires v0.8.0+)
python -c "import dataflow; print(dataflow.__version__)"
```

### Verify Installation

```python
from dataflow.debug.debug_agent import DebugAgent
from dataflow.debug.knowledge_base import KnowledgeBase

# Check if Debug Agent is available
kb = KnowledgeBase(
    "src/dataflow/debug/patterns.yaml",
    "src/dataflow/debug/solutions.yaml"
)
print(f"Loaded {len(kb.get_all_patterns())} error patterns")
print(f"Loaded {len(kb.get_all_solutions())} solutions")
```

**Expected Output**:
```
Loaded 50 error patterns
Loaded 60 solutions
```

---

## System Requirements

### Python Version
- **Required**: Python 3.10+
- **Recommended**: Python 3.12 for best performance

### Dependencies
- `dataflow>=0.8.0` (includes all Debug Agent components)
- `kailash>=0.10.0` (Core SDK with Inspector)
- `pyyaml>=6.0` (for patterns.yaml and solutions.yaml)

### Database Support
The Debug Agent works with all DataFlow-supported databases:
- PostgreSQL 12+
- MySQL 8.0+
- SQLite 3.35+

### Optional Dependencies
- `colorama` (for Windows color support)
- `pytest` (for running tests)

---

# Part 2: CLI Command Usage

## Running the Debug Agent

The Debug Agent can be used in three ways:

### 1. Interactive Mode (Python REPL)

```python
from dataflow import DataFlow
from dataflow.debug.debug_agent import DebugAgent
from dataflow.debug.knowledge_base import KnowledgeBase
from dataflow.platform.inspector import Inspector

# Initialize components
db = DataFlow("postgresql://localhost/mydb")
kb = KnowledgeBase("patterns.yaml", "solutions.yaml")
inspector = Inspector(db)
agent = DebugAgent(kb, inspector)

# Debug an exception
try:
    # Your code here
    pass
except Exception as e:
    report = agent.debug(e)
    print(report.to_cli_format())
```

### 2. Script Mode

```python
# debug_script.py
import sys
from dataflow import DataFlow
from dataflow.debug.debug_agent import DebugAgent
from dataflow.debug.knowledge_base import KnowledgeBase
from dataflow.platform.inspector import Inspector
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime import LocalRuntime

def main():
    # Initialize DataFlow and Debug Agent
    db = DataFlow("postgresql://localhost/mydb")

    @db.model
    class User:
        id: str
        name: str

    kb = KnowledgeBase("patterns.yaml", "solutions.yaml")
    inspector = Inspector(db)
    agent = DebugAgent(kb, inspector)

    # Create workflow
    workflow = WorkflowBuilder()
    workflow.add_node("UserCreateNode", "create", {"name": "Alice"})

    # Execute and debug
    runtime = LocalRuntime()
    try:
        results, _ = runtime.execute(workflow.build())
    except Exception as e:
        report = agent.debug(e, max_solutions=5, min_relevance=0.3)
        print(report.to_cli_format())
        sys.exit(1)

if __name__ == "__main__":
    main()
```

**Run**:
```bash
python debug_script.py
```

### 3. Integrated Mode (Production Code)

```python
# app.py
from dataflow import DataFlow
from dataflow.debug.debug_agent import DebugAgent
from dataflow.debug.knowledge_base import KnowledgeBase
from dataflow.platform.inspector import Inspector
import logging

# Initialize Debug Agent once
db = DataFlow("postgresql://localhost/mydb")
kb = KnowledgeBase("patterns.yaml", "solutions.yaml")
inspector = Inspector(db)
agent = DebugAgent(kb, inspector)

logger = logging.getLogger(__name__)

def process_request(data):
    """Process request with automatic error debugging."""
    try:
        # Your workflow logic
        workflow = build_workflow(data)
        runtime = LocalRuntime()
        results, _ = runtime.execute(workflow.build())
        return results
    except Exception as e:
        # Debug error automatically
        report = agent.debug(e, max_solutions=3, min_relevance=0.5)

        # Log structured error report
        logger.error(f"Workflow failed: {report.captured_error.message}")
        logger.error(f"Category: {report.error_category.category}")
        logger.error(f"Root cause: {report.analysis_result.root_cause}")

        # Log as JSON for external systems
        logger.error(report.to_json())

        # Re-raise with enhanced context
        raise
```

---

## Command Options

The `debug()` method accepts several parameters to control analysis:

### debug(exception, max_solutions=5, min_relevance=0.3)

**Parameters**:

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `exception` | Exception | Required | Exception object to debug |
| `max_solutions` | int | 5 | Maximum solutions to return |
| `min_relevance` | float | 0.3 | Minimum relevance score (0.0-1.0) |

**Examples**:

```python
# Default settings (5 solutions, 30% relevance threshold)
report = agent.debug(exception)

# Get only top 3 solutions
report = agent.debug(exception, max_solutions=3)

# Higher relevance threshold (50%+)
report = agent.debug(exception, max_solutions=5, min_relevance=0.5)

# Show all solutions (0% threshold)
report = agent.debug(exception, max_solutions=10, min_relevance=0.0)

# Only show perfect matches (95%+)
report = agent.debug(exception, max_solutions=3, min_relevance=0.95)
```

### debug_from_string(error_message, error_type="RuntimeError", max_solutions=5, min_relevance=0.3)

**Debug error messages without exception objects** (useful for logs).

**Parameters**:

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `error_message` | str | Required | Error message string |
| `error_type` | str | "RuntimeError" | Error type name |
| `max_solutions` | int | 5 | Maximum solutions to return |
| `min_relevance` | float | 0.3 | Minimum relevance score |

**Examples**:

```python
# Debug from log message
report = agent.debug_from_string(
    "NOT NULL constraint failed: users.id",
    error_type="DatabaseError"
)

# Debug from user report
report = agent.debug_from_string(
    "Source node 'create_user' not found in workflow",
    error_type="ValueError",
    max_solutions=3,
    min_relevance=0.5
)
```

---

## Understanding the Output

The CLI output is organized into 5 sections:

### Section 1: Header

```
╔════════════════════════════════════════════════════════════════════════════╗
║                           DataFlow Debug Agent                             ║
║                   Intelligent Error Analysis & Suggestions                 ║
╚════════════════════════════════════════════════════════════════════════════╝
```

**Purpose**: Banner identifying the Debug Agent output

### Section 2: Error Details

```
┌─ ERROR DETAILS ────────────────────────────────────────────────────────────┐
│ Type: ValueError                                                           │
│ Category: PARAMETER (Confidence: 95%)                                      │
└────────────────────────────────────────────────────────────────────────────┘

ERROR MESSAGE:
  Missing required parameter 'id' in CreateNode
```

**Fields**:
- **Type**: Original exception class name (e.g., ValueError, KeyError, IntegrityError)
- **Category**: Error category (PARAMETER, CONNECTION, MIGRATION, RUNTIME, CONFIGURATION)
- **Confidence**: Categorization confidence (0-100%)
- **ERROR MESSAGE**: Full error message from exception

**Interpreting Confidence**:
- **90-100%**: Perfect match, high confidence
- **70-89%**: Good match, likely correct
- **50-69%**: Possible match, review solutions
- **< 50%**: Low confidence, may be UNKNOWN category

### Section 3: Root Cause Analysis

```
┌─ ROOT CAUSE ANALYSIS ──────────────────────────────────────────────────────┐
│ Root Cause:                                                                │
│   Node 'create' is missing required parameter 'id' (primary key)          │
│                                                                            │
│ Affected Components:                                                       │
│   • Nodes: create                                                          │
│   • Models: User                                                           │
│   • Parameters: id (primary key)                                           │
└────────────────────────────────────────────────────────────────────────────┘
```

**Fields**:
- **Root Cause**: Human-readable explanation of why the error occurred
- **Affected Components**: Nodes, models, connections, or parameters involved

**Using This Information**:
1. **Nodes**: Which workflow nodes are failing
2. **Models**: Which DataFlow models are involved
3. **Parameters**: Which parameters are missing, invalid, or incorrect

### Section 4: Suggested Solutions

```
┌─ SUGGESTED SOLUTIONS ──────────────────────────────────────────────────────┐
│                                                                            │
│ [1] Add Missing 'id' Parameter to CreateNode (QUICK_FIX)                  │
│     Relevance: 95% | Difficulty: easy | Time: 1 min                       │
│                                                                            │
│     Description:                                                           │
│     Add required 'id' field to CreateNode operation                       │
│                                                                            │
│     Code Example:                                                          │
│     workflow.add_node("UserCreateNode", "create", {                       │
│         "id": "user-123",  # Add missing parameter                        │
│         "name": "Alice"                                                    │
│     })                                                                     │
│                                                                            │
└────────────────────────────────────────────────────────────────────────────┘
```

**Fields**:
- **[N]**: Solution ranking (1 = most relevant)
- **Title**: Short solution description
- **Category**: Solution type (QUICK_FIX, BEST_PRACTICE, REFACTORING, DOCUMENTATION)
- **Relevance**: How relevant this solution is (0-100%)
- **Difficulty**: Implementation difficulty (easy, medium, hard)
- **Time**: Estimated implementation time (minutes)
- **Description**: Detailed explanation
- **Code Example**: Working code snippet

**Solution Categories**:
- **QUICK_FIX**: Fast fix for immediate issue (1-5 min)
- **BEST_PRACTICE**: Recommended pattern for this scenario (5-15 min)
- **REFACTORING**: Structural improvement (15+ min)
- **DOCUMENTATION**: Reference to docs/guides (0 min)

**Interpreting Relevance**:
- **90-100%**: Perfect match, apply immediately
- **70-89%**: Good match, review code example
- **50-69%**: Possible solution, adapt to your case
- **< 50%**: Generic solution, may not apply

### Section 5: Summary

```
┌─ SUMMARY ──────────────────────────────────────────────────────────────────┐
│ Execution Time: 23.5ms                                                     │
│ Documentation: https://docs.dataflow.dev/debug-agent                       │
└────────────────────────────────────────────────────────────────────────────┘
```

**Fields**:
- **Execution Time**: Debug Agent execution time (milliseconds)
- **Documentation**: Link to comprehensive documentation

**Execution Time Benchmarks**:
- **< 10ms**: Excellent (cached patterns)
- **10-50ms**: Normal (pattern matching + analysis)
- **50-100ms**: Slow (complex workflow analysis)
- **> 100ms**: Very slow (check Inspector performance)

---

## Output Formats

The Debug Agent supports three output formats:

### 1. CLI Format (Rich Terminal Output)

**Method**: `report.to_cli_format()`

**Features**:
- ANSI color codes (red errors, green solutions, blue info)
- Box drawing characters (borders, separators)
- Readable formatting with proper spacing
- Optimized for 80-column terminals

**Example**:
```python
report = agent.debug(exception)
print(report.to_cli_format())
```

**Color Support**:
- **Linux/macOS**: Native support
- **Windows**: Install `colorama` for color support
  ```bash
  pip install colorama
  ```

### 2. JSON Format (Machine-Readable)

**Method**: `report.to_json()`

**Features**:
- Standard JSON format
- All report fields included
- Easy parsing for automation
- Logging and monitoring integration

**Example**:
```python
report = agent.debug(exception)
json_output = report.to_json()

# Parse JSON
import json
data = json.loads(json_output)
print(data["error_category"]["category"])  # "PARAMETER"
print(data["execution_time"])  # 23.5
```

**JSON Structure**:
```json
{
  "captured_error": {
    "error_type": "ValueError",
    "message": "Missing required parameter 'id'",
    "stacktrace": ["line 1", "line 2", "..."],
    "context": {},
    "timestamp": "2025-01-13T10:30:00"
  },
  "error_category": {
    "category": "PARAMETER",
    "pattern_id": "PARAM_001",
    "confidence": 0.95,
    "features": {}
  },
  "analysis_result": {
    "root_cause": "Node 'create' is missing required parameter 'id'",
    "affected_nodes": ["create"],
    "affected_models": ["User"],
    "affected_connections": [],
    "context_data": {"missing_parameter": "id"}
  },
  "suggested_solutions": [
    {
      "solution_id": "SOL_001",
      "title": "Add Missing 'id' Parameter",
      "category": "QUICK_FIX",
      "description": "Add required 'id' field",
      "code_example": "...",
      "explanation": "...",
      "relevance_score": 0.95,
      "confidence": 0.95,
      "difficulty": "easy",
      "estimated_time": 1
    }
  ],
  "execution_time": 23.5
}
```

### 3. Dictionary Format (Programmatic Access)

**Method**: `report.to_dict()`

**Features**:
- Python dictionary (not JSON string)
- Same structure as JSON format
- Direct field access without parsing

**Example**:
```python
report = agent.debug(exception)
data = report.to_dict()

# Direct field access
category = data["error_category"]["category"]
root_cause = data["analysis_result"]["root_cause"]
solutions = data["suggested_solutions"]

# Filter solutions by relevance
high_relevance = [s for s in solutions if s["relevance_score"] >= 0.9]
```

---

## Advanced CLI Usage

### 1. Redirect Output to File

```bash
python debug_script.py > debug_report.txt 2>&1
```

**Result**: Plain text file with ANSI color codes

**Remove colors**:
```bash
python debug_script.py 2>&1 | sed 's/\x1b\[[0-9;]*m//g' > debug_report.txt
```

### 2. JSON Output to File

```python
# debug_script.py
report = agent.debug(exception)
with open("debug_report.json", "w") as f:
    f.write(report.to_json())
```

**Run**:
```bash
python debug_script.py
cat debug_report.json | jq '.'  # Pretty-print JSON
```

### 3. Filter Solutions by Relevance

```python
# Only show solutions >= 80% relevance
report = agent.debug(exception, max_solutions=10, min_relevance=0.8)
print(report.to_cli_format())
```

### 4. Combine Multiple Error Reports

```python
# Collect multiple error reports
reports = []

for workflow in workflows:
    try:
        runtime.execute(workflow.build())
    except Exception as e:
        report = agent.debug(e, max_solutions=3, min_relevance=0.5)
        reports.append(report.to_dict())

# Export all reports
import json
with open("all_errors.json", "w") as f:
    json.dump(reports, f, indent=2)
```

### 5. Integration with Logging

```python
import logging

logger = logging.getLogger(__name__)

try:
    runtime.execute(workflow.build())
except Exception as e:
    report = agent.debug(e)

    # Log structured data
    logger.error("Debug Agent Report", extra={
        "category": report.error_category.category,
        "confidence": report.error_category.confidence,
        "root_cause": report.analysis_result.root_cause,
        "solutions_count": len(report.suggested_solutions),
        "execution_time_ms": report.execution_time
    })

    # Log full JSON report
    logger.error(report.to_json())
```

### 6. Custom Output Formatting

```python
def format_summary(report):
    """Create custom summary of debug report."""
    return f"""
Debug Report Summary
====================
Category: {report.error_category.category} ({report.error_category.confidence * 100:.0f}%)
Root Cause: {report.analysis_result.root_cause}
Solutions: {len(report.suggested_solutions)} found
Top Solution: {report.suggested_solutions[0].title if report.suggested_solutions else 'None'}
Execution Time: {report.execution_time:.1f}ms
"""

report = agent.debug(exception)
print(format_summary(report))
```

---

# Part 3: Common Error Scenarios

## Parameter Errors

### Scenario 1: Missing Required 'id' Parameter

**Error Message**:
```
ValueError: Missing required parameter 'id' in CreateNode
```

**Cause**:
DataFlow requires `id` field for all CREATE operations.

**Example Code (ERROR)**:
```python
workflow = WorkflowBuilder()
workflow.add_node("UserCreateNode", "create", {
    "name": "Alice",
    "email": "alice@example.com"
    # Missing 'id' parameter
})
```

**Debug Agent Output**:
```
Category: PARAMETER (Confidence: 95%)
Root Cause: Node 'create' is missing required parameter 'id' (primary key)

[1] Add Missing 'id' Parameter (QUICK_FIX) - 95%
    workflow.add_node("UserCreateNode", "create", {
        "id": "user-123",  # Add missing parameter
        "name": "Alice",
        "email": "alice@example.com"
    })

[2] Use UUID for Automatic ID Generation (BEST_PRACTICE) - 85%
    import uuid
    workflow.add_node("UserCreateNode", "create", {
        "id": str(uuid.uuid4()),  # Auto-generate UUID
        "name": "Alice",
        "email": "alice@example.com"
    })
```

**Solution**:
```python
import uuid

workflow = WorkflowBuilder()
workflow.add_node("UserCreateNode", "create", {
    "id": str(uuid.uuid4()),  # ✅ Add required 'id'
    "name": "Alice",
    "email": "alice@example.com"
})
```

---

### Scenario 2: Type Mismatch - Integer Expected

**Error Message**:
```
TypeError: expected int, got str '25'
```

**Cause**:
Parameter value type doesn't match model field type.

**Example Code (ERROR)**:
```python
@db.model
class User:
    id: str
    age: int  # Integer field

workflow = WorkflowBuilder()
workflow.add_node("UserCreateNode", "create", {
    "id": "user-123",
    "age": "25"  # String instead of int
})
```

**Debug Agent Output**:
```
Category: PARAMETER (Confidence: 92%)
Root Cause: Field 'age' expects int but received str

[1] Convert String to Integer (QUICK_FIX) - 93%
    workflow.add_node("UserCreateNode", "create", {
        "id": "user-123",
        "age": 25  # Use int, not str
    })

[2] Validate Input Types Before Workflow (BEST_PRACTICE) - 78%
    def validate_user_data(data):
        data["age"] = int(data["age"])  # Convert
        return data

    validated = validate_user_data(user_data)
    workflow.add_node("UserCreateNode", "create", validated)
```

**Solution**:
```python
workflow = WorkflowBuilder()
workflow.add_node("UserCreateNode", "create", {
    "id": "user-123",
    "age": 25  # ✅ Use int type
})
```

---

### Scenario 3: Reserved Field Used

**Error Message**:
```
ValueError: cannot manually set 'created_at' - auto-managed field
```

**Cause**:
DataFlow auto-manages `created_at` and `updated_at` fields.

**Example Code (ERROR)**:
```python
from datetime import datetime

workflow = WorkflowBuilder()
workflow.add_node("UserCreateNode", "create", {
    "id": "user-123",
    "name": "Alice",
    "created_at": datetime.now()  # Reserved field
})
```

**Debug Agent Output**:
```
Category: PARAMETER (Confidence: 89%)
Root Cause: Field 'created_at' is auto-managed and cannot be set manually

[1] Remove Reserved Field (QUICK_FIX) - 95%
    workflow.add_node("UserCreateNode", "create", {
        "id": "user-123",
        "name": "Alice"
        # Remove 'created_at' - auto-managed
    })

[2] Use Custom Timestamp Field (BEST_PRACTICE) - 82%
    @db.model
    class User:
        id: str
        name: str
        custom_timestamp: datetime  # Use custom field

    workflow.add_node("UserCreateNode", "create", {
        "id": "user-123",
        "name": "Alice",
        "custom_timestamp": datetime.now()
    })
```

**Solution**:
```python
workflow = WorkflowBuilder()
workflow.add_node("UserCreateNode", "create", {
    "id": "user-123",
    "name": "Alice"
    # ✅ Remove 'created_at' - DataFlow manages it
})
```

---

### Scenario 4: CreateNode vs UpdateNode Confusion

**Error Message**:
```
ValueError: UPDATE request must contain 'filter' field
```

**Cause**:
UpdateNode requires `{"filter": {...}, "fields": {...}}` structure.

**Example Code (ERROR)**:
```python
# Applying CreateNode pattern to UpdateNode
workflow = WorkflowBuilder()
workflow.add_node("UserUpdateNode", "update", {
    "id": "user-123",  # Wrong structure
    "name": "Alice Updated"
})
```

**Debug Agent Output**:
```
Category: PARAMETER (Confidence: 93%)
Root Cause: UpdateNode requires 'filter' and 'fields' structure

[1] Use Correct UpdateNode Structure (QUICK_FIX) - 96%
    workflow.add_node("UserUpdateNode", "update", {
        "filter": {"id": "user-123"},  # Which record
        "fields": {"name": "Alice Updated"}  # What to update
    })

[2] Reference UpdateNode Documentation (DOCUMENTATION) - 72%
    See: docs/nodes/update-node.md
```

**Solution**:
```python
workflow = WorkflowBuilder()
workflow.add_node("UserUpdateNode", "update", {
    "filter": {"id": "user-123"},  # ✅ Which record
    "fields": {"name": "Alice Updated"}  # ✅ What to update
})
```

---

### Scenario 5: Empty Parameter Value

**Error Message**:
```
ValueError: parameter 'email' cannot be empty
```

**Cause**:
Required field has empty value.

**Example Code (ERROR)**:
```python
workflow = WorkflowBuilder()
workflow.add_node("UserCreateNode", "create", {
    "id": "user-123",
    "name": "Alice",
    "email": ""  # Empty string
})
```

**Debug Agent Output**:
```
Category: PARAMETER (Confidence: 87%)
Root Cause: Required field 'email' has empty value

[1] Provide Non-Empty Value (QUICK_FIX) - 93%
    workflow.add_node("UserCreateNode", "create", {
        "id": "user-123",
        "name": "Alice",
        "email": "alice@example.com"  # Valid value
    })

[2] Add Input Validation (BEST_PRACTICE) - 81%
    def validate_not_empty(data, field):
        if not data.get(field):
            raise ValueError(f"{field} cannot be empty")
        return data

    validated = validate_not_empty(user_data, "email")
    workflow.add_node("UserCreateNode", "create", validated)
```

**Solution**:
```python
workflow = WorkflowBuilder()
workflow.add_node("UserCreateNode", "create", {
    "id": "user-123",
    "name": "Alice",
    "email": "alice@example.com"  # ✅ Non-empty value
})
```

---

## Connection Errors

### Scenario 6: Source Node Not Found

**Error Message**:
```
ValueError: Source node 'create_user' not found in workflow
```

**Cause**:
Connection references non-existent source node.

**Example Code (ERROR)**:
```python
workflow = WorkflowBuilder()
workflow.add_node("UserReadNode", "read", {"id": "user-123"})

# Connection to non-existent node
workflow.add_connection("create_user", "id", "read", "id")
```

**Debug Agent Output**:
```
Category: CONNECTION (Confidence: 96%)
Root Cause: Connection references source node 'create_user' which doesn't exist

[1] Add Missing Source Node (QUICK_FIX) - 95%
    workflow.add_node("UserCreateNode", "create_user", {
        "id": "user-123",
        "name": "Alice"
    })
    workflow.add_node("UserReadNode", "read", {"id": "user-123"})
    workflow.add_connection("create_user", "id", "read", "id")

[2] Fix Node ID Typo (QUICK_FIX) - 88%
    # Check if node ID has typo
    workflow.add_node("UserCreateNode", "create", {"id": "user-123"})
    workflow.add_connection("create", "id", "read", "id")  # Use correct ID
```

**Solution**:
```python
workflow = WorkflowBuilder()
workflow.add_node("UserCreateNode", "create_user", {  # ✅ Add source node
    "id": "user-123",
    "name": "Alice"
})
workflow.add_node("UserReadNode", "read", {"id": "user-123"})
workflow.add_connection("create_user", "id", "read", "id")  # ✅ Now works
```

---

### Scenario 7: Circular Dependency

**Error Message**:
```
ValueError: Circular dependency detected: create -> update -> create
```

**Cause**:
Workflow has circular connection forming infinite loop.

**Example Code (ERROR)**:
```python
workflow = WorkflowBuilder()
workflow.add_node("UserCreateNode", "create", {"id": "user-123", "name": "Alice"})
workflow.add_node("UserUpdateNode", "update", {
    "filter": {"id": "user-123"},
    "fields": {"name": "Alice Updated"}
})

# Creates cycle: create -> update -> create
workflow.add_connection("create", "id", "update", "filter.id")
workflow.add_connection("update", "id", "create", "id")  # Circular!
```

**Debug Agent Output**:
```
Category: CONNECTION (Confidence: 94%)
Root Cause: Circular dependency creates infinite loop: create -> update -> create

[1] Remove Circular Connection (QUICK_FIX) - 96%
    # Keep only forward flow
    workflow.add_connection("create", "id", "update", "filter.id")
    # Remove: workflow.add_connection("update", "id", "create", "id")

[2] Redesign Workflow Structure (REFACTORING) - 73%
    # Use separate workflows for create and update
    create_wf = WorkflowBuilder()
    create_wf.add_node("UserCreateNode", "create", {...})

    update_wf = WorkflowBuilder()
    update_wf.add_node("UserUpdateNode", "update", {...})
```

**Solution**:
```python
workflow = WorkflowBuilder()
workflow.add_node("UserCreateNode", "create", {"id": "user-123", "name": "Alice"})
workflow.add_node("UserUpdateNode", "update", {
    "filter": {"id": "user-123"},
    "fields": {"name": "Alice Updated"}
})

# ✅ Only forward flow, no circular dependency
workflow.add_connection("create", "id", "update", "filter.id")
```

---

### Scenario 8: Type Incompatibility in Connection

**Error Message**:
```
TypeError: Cannot connect int output to str input
```

**Cause**:
Source output type doesn't match destination input type.

**Example Code (ERROR)**:
```python
@db.model
class User:
    id: str
    age: int

workflow = WorkflowBuilder()
workflow.add_node("UserCreateNode", "create", {"id": "user-123", "age": 25})
workflow.add_node("UserReadNode", "read", {"id": "user-123"})

# Connecting int (age) to str (id) - type mismatch
workflow.add_connection("create", "age", "read", "id")
```

**Debug Agent Output**:
```
Category: CONNECTION (Confidence: 91%)
Root Cause: Type mismatch: connecting int field 'age' to str field 'id'

[1] Connect Correct Fields (QUICK_FIX) - 94%
    # Connect id to id (both str)
    workflow.add_connection("create", "id", "read", "id")

[2] Add Type Conversion Node (REFACTORING) - 68%
    # Use PythonCode node for conversion
    workflow.add_node("PythonCodeNode", "convert", {
        "code": "output = {'id': str(input['age'])}"
    })
    workflow.add_connection("create", "age", "convert", "input")
    workflow.add_connection("convert", "id", "read", "id")
```

**Solution**:
```python
workflow = WorkflowBuilder()
workflow.add_node("UserCreateNode", "create", {"id": "user-123", "age": 25})
workflow.add_node("UserReadNode", "read", {"id": "user-123"})

# ✅ Connect matching types (str to str)
workflow.add_connection("create", "id", "read", "id")
```

---

## Migration Errors

### Scenario 9: Schema Conflict - Table Already Exists

**Error Message**:
```
OperationalError: table 'users' already exists
```

**Cause**:
Attempting to create table that already exists in database.

**Example Code (ERROR)**:
```python
db = DataFlow("postgresql://localhost/mydb", auto_migrate=False)

@db.model
class User:
    id: str
    name: str

# Table 'users' already exists in database
await db.initialize()  # Attempts to create table
```

**Debug Agent Output**:
```
Category: MIGRATION (Confidence: 93%)
Root Cause: Table 'users' already exists in database

[1] Enable existing_schema_mode (QUICK_FIX) - 95%
    db = DataFlow(
        "postgresql://localhost/mydb",
        existing_schema_mode=True  # Skip table creation
    )

[2] Enable auto_migrate (BEST_PRACTICE) - 88%
    db = DataFlow(
        "postgresql://localhost/mydb",
        auto_migrate=True  # Handle schema changes automatically
    )

[3] Drop Existing Table (CAUTION) - 62%
    # WARNING: Data loss!
    await db._engine.execute("DROP TABLE IF EXISTS users CASCADE")
    await db.initialize()
```

**Solution**:
```python
db = DataFlow(
    "postgresql://localhost/mydb",
    existing_schema_mode=True  # ✅ Use existing table
)

@db.model
class User:
    id: str
    name: str

await db.initialize()  # ✅ No error, uses existing table
```

---

### Scenario 10: Missing Table

**Error Message**:
```
OperationalError: no such table: users
```

**Cause**:
Query references table that doesn't exist.

**Example Code (ERROR)**:
```python
db = DataFlow("sqlite:///mydb.db", auto_migrate=False)

@db.model
class User:
    id: str
    name: str

# Table not created yet
workflow = WorkflowBuilder()
workflow.add_node("UserReadNode", "read", {"id": "user-123"})

runtime = LocalRuntime()
results, _ = runtime.execute(workflow.build())  # Error!
```

**Debug Agent Output**:
```
Category: MIGRATION (Confidence: 94%)
Root Cause: Table 'users' does not exist - initialize() not called

[1] Call initialize() Before Operations (QUICK_FIX) - 97%
    db = DataFlow("sqlite:///mydb.db")

    @db.model
    class User:
        id: str
        name: str

    await db.initialize()  # Create tables

    # Now operations work
    workflow = WorkflowBuilder()
    workflow.add_node("UserReadNode", "read", {"id": "user-123"})

[2] Enable auto_migrate (BEST_PRACTICE) - 86%
    db = DataFlow("sqlite:///mydb.db", auto_migrate=True)
```

**Solution**:
```python
db = DataFlow("sqlite:///mydb.db")

@db.model
class User:
    id: str
    name: str

await db.initialize()  # ✅ Create tables first

workflow = WorkflowBuilder()
workflow.add_node("UserReadNode", "read", {"id": "user-123"})

runtime = LocalRuntime()
results, _ = runtime.execute(workflow.build())  # ✅ Works
```

---

### Scenario 11: Constraint Violation

**Error Message**:
```
IntegrityError: foreign key constraint 'fk_order_user' violated
```

**Cause**:
Foreign key references non-existent record.

**Example Code (ERROR)**:
```python
@db.model
class User:
    id: str
    name: str

@db.model
class Order:
    id: str
    user_id: str  # Foreign key
    total: float

await db.initialize()

# Create order for non-existent user
workflow = WorkflowBuilder()
workflow.add_node("OrderCreateNode", "create", {
    "id": "order-123",
    "user_id": "user-999",  # User doesn't exist
    "total": 99.99
})

runtime = LocalRuntime()
results, _ = runtime.execute(workflow.build())  # Error!
```

**Debug Agent Output**:
```
Category: MIGRATION (Confidence: 91%)
Root Cause: Foreign key violation - referenced user 'user-999' doesn't exist

[1] Create Parent Record First (QUICK_FIX) - 94%
    workflow = WorkflowBuilder()

    # Create user first
    workflow.add_node("UserCreateNode", "create_user", {
        "id": "user-999",
        "name": "Bob"
    })

    # Then create order
    workflow.add_node("OrderCreateNode", "create_order", {
        "id": "order-123",
        "user_id": "user-999",
        "total": 99.99
    })

    # Connect to ensure order
    workflow.add_connection("create_user", "id", "create_order", "user_id")

[2] Validate Foreign Keys Before INSERT (BEST_PRACTICE) - 83%
    # Check if user exists
    check_workflow = WorkflowBuilder()
    check_workflow.add_node("UserReadNode", "check", {"id": "user-999"})

    result, _ = runtime.execute(check_workflow.build())
    if result.get("check"):
        # User exists, proceed with order creation
        pass
```

**Solution**:
```python
workflow = WorkflowBuilder()

# ✅ Create parent record first
workflow.add_node("UserCreateNode", "create_user", {
    "id": "user-999",
    "name": "Bob"
})

# ✅ Then create child record
workflow.add_node("OrderCreateNode", "create_order", {
    "id": "order-123",
    "user_id": "user-999",
    "total": 99.99
})

# ✅ Connect to ensure order
workflow.add_connection("create_user", "id", "create_order", "user_id")

runtime = LocalRuntime()
results, _ = runtime.execute(workflow.build())  # ✅ Works
```

---

## Runtime Errors

### Scenario 12: Transaction Timeout

**Error Message**:
```
OperationalError: query canceled due to statement timeout
```

**Cause**:
Query takes too long and exceeds timeout.

**Example Code (ERROR)**:
```python
db = DataFlow("postgresql://localhost/mydb", query_timeout=5)  # 5 second timeout

# Query that takes > 5 seconds
workflow = WorkflowBuilder()
workflow.add_node("UserListNode", "list", {
    "limit": 1000000  # Huge limit causes slow query
})

runtime = LocalRuntime()
results, _ = runtime.execute(workflow.build())  # Timeout!
```

**Debug Agent Output**:
```
Category: RUNTIME (Confidence: 92%)
Root Cause: Query exceeded 5 second timeout

[1] Increase Query Timeout (QUICK_FIX) - 87%
    db = DataFlow(
        "postgresql://localhost/mydb",
        query_timeout=30  # Increase to 30 seconds
    )

[2] Optimize Query with Smaller Limit (BEST_PRACTICE) - 91%
    workflow.add_node("UserListNode", "list", {
        "limit": 100,  # Smaller limit
        "offset": 0
    })
    # Paginate large result sets

[3] Add Database Index (REFACTORING) - 78%
    # Create index on frequently queried columns
    await db._engine.execute(
        "CREATE INDEX idx_users_created_at ON users(created_at)"
    )
```

**Solution**:
```python
# ✅ Solution 1: Increase timeout
db = DataFlow("postgresql://localhost/mydb", query_timeout=30)

# ✅ Solution 2: Use pagination (better)
workflow = WorkflowBuilder()
workflow.add_node("UserListNode", "list", {
    "limit": 100,  # Reasonable limit
    "offset": 0
})

runtime = LocalRuntime()
results, _ = runtime.execute(workflow.build())  # ✅ Works
```

---

### Scenario 13: Event Loop Collision (AsyncLocalRuntime)

**Error Message**:
```
RuntimeError: This event loop is already running
```

**Cause**:
Attempting to run AsyncLocalRuntime in an existing event loop.

**Example Code (ERROR)**:
```python
import asyncio
from kailash.runtime import AsyncLocalRuntime

async def main():
    db = DataFlow("postgresql://localhost/mydb")

    @db.model
    class User:
        id: str
        name: str

    await db.initialize()

    workflow = WorkflowBuilder()
    workflow.add_node("UserCreateNode", "create", {
        "id": "user-123",
        "name": "Alice"
    })

    runtime = AsyncLocalRuntime()

    # Error: Already in async context
    results, _ = runtime.execute_workflow_async(workflow.build(), inputs={})

# Run with asyncio.run()
asyncio.run(main())  # Error!
```

**Debug Agent Output**:
```
Category: RUNTIME (Confidence: 93%)
Root Cause: AsyncLocalRuntime used in existing event loop

[1] Use await Instead of execute_workflow_async (QUICK_FIX) - 96%
    async def main():
        runtime = AsyncLocalRuntime()
        results, _ = await runtime.execute_workflow_async(
            workflow.build(),
            inputs={}
        )

[2] Use LocalRuntime in Sync Context (ALTERNATIVE) - 82%
    def main():
        runtime = LocalRuntime()
        results, _ = runtime.execute(workflow.build())

    # Call without asyncio
    main()
```

**Solution**:
```python
import asyncio
from kailash.runtime import AsyncLocalRuntime

async def main():
    db = DataFlow("postgresql://localhost/mydb")

    @db.model
    class User:
        id: str
        name: str

    await db.initialize()

    workflow = WorkflowBuilder()
    workflow.add_node("UserCreateNode", "create", {
        "id": "user-123",
        "name": "Alice"
    })

    runtime = AsyncLocalRuntime()

    # ✅ Use await
    results, _ = await runtime.execute_workflow_async(
        workflow.build(),
        inputs={}
    )

# ✅ Run with asyncio.run()
asyncio.run(main())
```

---

## Configuration Errors

### Scenario 14: Invalid Database URL

**Error Message**:
```
ValueError: Invalid database URL format 'postgres:/localhost/db'
```

**Cause**:
Database URL has incorrect format.

**Example Code (ERROR)**:
```python
# Missing '//' after protocol
db = DataFlow("postgres:/localhost/mydb")
```

**Debug Agent Output**:
```
Category: CONFIGURATION (Confidence: 95%)
Root Cause: Database URL missing '//' after protocol

[1] Fix URL Format (QUICK_FIX) - 97%
    # Correct format: protocol://host:port/database
    db = DataFlow("postgresql://localhost:5432/mydb")

[2] Use Standard PostgreSQL URL (BEST_PRACTICE) - 89%
    # Full format with credentials
    db = DataFlow(
        "postgresql://user:password@localhost:5432/mydb"
    )

[3] Reference URL Format Documentation (DOCUMENTATION) - 71%
    # PostgreSQL: postgresql://user:password@host:port/database
    # MySQL: mysql://user:password@host:port/database
    # SQLite: sqlite:///path/to/database.db
```

**Solution**:
```python
# ✅ Correct format
db = DataFlow("postgresql://localhost:5432/mydb")

# ✅ With credentials
db = DataFlow("postgresql://user:password@localhost:5432/mydb")

# ✅ SQLite
db = DataFlow("sqlite:///path/to/database.db")
```

---

### Scenario 15: Missing Environment Variable

**Error Message**:
```
KeyError: Environment variable 'DATABASE_URL' not set
```

**Cause**:
Required environment variable is missing.

**Example Code (ERROR)**:
```python
import os

# DATABASE_URL not set in environment
db_url = os.environ["DATABASE_URL"]  # KeyError!
db = DataFlow(db_url)
```

**Debug Agent Output**:
```
Category: CONFIGURATION (Confidence: 94%)
Root Cause: Environment variable 'DATABASE_URL' not set

[1] Set Environment Variable (QUICK_FIX) - 96%
    # In shell
    export DATABASE_URL="postgresql://localhost:5432/mydb"

    # Or in .env file
    DATABASE_URL=postgresql://localhost:5432/mydb

[2] Use Default Value with os.getenv() (BEST_PRACTICE) - 88%
    import os

    db_url = os.getenv(
        "DATABASE_URL",
        "postgresql://localhost:5432/mydb"  # Default
    )
    db = DataFlow(db_url)

[3] Load .env File with python-dotenv (BEST_PRACTICE) - 83%
    from dotenv import load_dotenv
    import os

    load_dotenv()  # Load .env file
    db_url = os.environ["DATABASE_URL"]
    db = DataFlow(db_url)
```

**Solution**:
```python
import os
from dotenv import load_dotenv

# ✅ Load .env file
load_dotenv()

db_url = os.environ["DATABASE_URL"]
db = DataFlow(db_url)
```

**.env file**:
```bash
DATABASE_URL=postgresql://localhost:5432/mydb
```

---

# Part 4: Programmatic Usage

## Python API

### Basic Usage

```python
from dataflow.debug.debug_agent import DebugAgent
from dataflow.debug.knowledge_base import KnowledgeBase
from dataflow.platform.inspector import Inspector
from dataflow import DataFlow

# Initialize Debug Agent once (singleton pattern)
db = DataFlow("postgresql://localhost/mydb")
kb = KnowledgeBase("patterns.yaml", "solutions.yaml")
inspector = Inspector(db)
agent = DebugAgent(kb, inspector)

# Use in exception handlers
def execute_workflow(workflow):
    """Execute workflow with automatic error debugging."""
    from kailash.runtime import LocalRuntime

    runtime = LocalRuntime()
    try:
        results, run_id = runtime.execute(workflow.build())
        return results
    except Exception as e:
        # Debug error automatically
        report = agent.debug(e, max_solutions=5, min_relevance=0.3)

        # Log structured report
        print(f"Error Category: {report.error_category.category}")
        print(f"Root Cause: {report.analysis_result.root_cause}")
        print(f"Solutions: {len(report.suggested_solutions)} found")

        # Display CLI output
        print(report.to_cli_format())

        # Re-raise exception
        raise
```

---

## Integration with DataFlow

### Pattern 1: Global Error Handler

```python
from dataflow import DataFlow
from dataflow.debug.debug_agent import DebugAgent
from dataflow.debug.knowledge_base import KnowledgeBase
from dataflow.platform.inspector import Inspector
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime import LocalRuntime

class DataFlowWithDebugAgent:
    """DataFlow wrapper with integrated Debug Agent."""

    def __init__(self, database_url: str):
        self.db = DataFlow(database_url)

        # Initialize Debug Agent
        kb = KnowledgeBase("patterns.yaml", "solutions.yaml")
        inspector = Inspector(self.db)
        self.debug_agent = DebugAgent(kb, inspector)

    def execute(self, workflow: WorkflowBuilder):
        """Execute workflow with automatic error debugging."""
        runtime = LocalRuntime()

        try:
            results, run_id = runtime.execute(workflow.build())
            return results
        except Exception as e:
            # Debug error
            report = self.debug_agent.debug(e, max_solutions=5)

            # Log report
            print(report.to_cli_format())

            # Store report for analysis
            self._store_debug_report(report)

            # Re-raise
            raise

    def _store_debug_report(self, report):
        """Store debug report for analysis."""
        import json
        from datetime import datetime

        filename = f"debug_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(filename, "w") as f:
            f.write(report.to_json())

# Usage
db = DataFlowWithDebugAgent("postgresql://localhost/mydb")

@db.db.model
class User:
    id: str
    name: str

workflow = WorkflowBuilder()
workflow.add_node("UserCreateNode", "create", {"name": "Alice"})

results = db.execute(workflow)  # Automatic error debugging
```

---

### Pattern 2: Decorator-Based Error Handling

```python
from functools import wraps
from dataflow.debug.debug_agent import DebugAgent
from dataflow.debug.knowledge_base import KnowledgeBase
from dataflow.platform.inspector import Inspector

def debug_on_error(agent: DebugAgent):
    """Decorator to debug exceptions automatically."""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                # Debug error
                report = agent.debug(e, max_solutions=5, min_relevance=0.3)

                # Log report
                print(report.to_cli_format())

                # Re-raise
                raise
        return wrapper
    return decorator

# Initialize Debug Agent
db = DataFlow("postgresql://localhost/mydb")
kb = KnowledgeBase("patterns.yaml", "solutions.yaml")
inspector = Inspector(db)
agent = DebugAgent(kb, inspector)

# Apply decorator
@debug_on_error(agent)
def create_user(user_data):
    """Create user with automatic error debugging."""
    workflow = WorkflowBuilder()
    workflow.add_node("UserCreateNode", "create", user_data)

    runtime = LocalRuntime()
    results, _ = runtime.execute(workflow.build())
    return results

# Usage
try:
    create_user({"name": "Alice"})  # Missing 'id' - automatic debugging
except Exception as e:
    pass  # Report already printed by decorator
```

---

### Pattern 3: Context Manager

```python
from contextlib import contextmanager
from dataflow.debug.debug_agent import DebugAgent
from dataflow.debug.knowledge_base import KnowledgeBase
from dataflow.platform.inspector import Inspector

@contextmanager
def debug_context(db: DataFlow):
    """Context manager for automatic error debugging."""
    kb = KnowledgeBase("patterns.yaml", "solutions.yaml")
    inspector = Inspector(db)
    agent = DebugAgent(kb, inspector)

    try:
        yield agent
    except Exception as e:
        # Debug error
        report = agent.debug(e, max_solutions=5)

        # Print report
        print(report.to_cli_format())

        # Re-raise
        raise

# Usage
db = DataFlow("postgresql://localhost/mydb")

@db.model
class User:
    id: str
    name: str

with debug_context(db) as agent:
    workflow = WorkflowBuilder()
    workflow.add_node("UserCreateNode", "create", {"name": "Alice"})

    runtime = LocalRuntime()
    results, _ = runtime.execute(workflow.build())  # Auto-debug on error
```

---

## Custom Error Handlers

### Pattern 4: Custom Solution Filtering

```python
from dataflow.debug.debug_agent import DebugAgent
from dataflow.debug.suggested_solution import SuggestedSolution

def filter_solutions_by_category(
    report,
    categories: list[str] = ["QUICK_FIX"]
):
    """Filter solutions by category."""
    filtered = [
        s for s in report.suggested_solutions
        if s.category in categories
    ]
    return filtered

# Usage
try:
    runtime.execute(workflow.build())
except Exception as e:
    report = agent.debug(e, max_solutions=10, min_relevance=0.0)

    # Only show QUICK_FIX solutions
    quick_fixes = filter_solutions_by_category(report, ["QUICK_FIX"])

    print(f"Found {len(quick_fixes)} quick fixes:")
    for solution in quick_fixes:
        print(f"- {solution.title} ({solution.relevance_score * 100:.0f}%)")
```

---

### Pattern 5: Custom Report Formatting

```python
def format_slack_message(report):
    """Format debug report for Slack."""
    emoji_map = {
        "PARAMETER": ":warning:",
        "CONNECTION": ":link:",
        "MIGRATION": ":database:",
        "RUNTIME": ":zap:",
        "CONFIGURATION": ":gear:"
    }

    emoji = emoji_map.get(report.error_category.category, ":x:")

    message = f"""
{emoji} *DataFlow Error Detected*

*Category:* {report.error_category.category} ({report.error_category.confidence * 100:.0f}% confidence)
*Root Cause:* {report.analysis_result.root_cause}

*Top Solutions:*
"""

    for i, solution in enumerate(report.suggested_solutions[:3], 1):
        message += f"\n{i}. *{solution.title}* ({solution.relevance_score * 100:.0f}%)"
        message += f"\n   Difficulty: {solution.difficulty} | Time: {solution.estimated_time} min"

    message += f"\n\n*Execution Time:* {report.execution_time:.1f}ms"

    return message

# Usage
try:
    runtime.execute(workflow.build())
except Exception as e:
    report = agent.debug(e)

    # Send to Slack
    slack_message = format_slack_message(report)
    send_to_slack(slack_message)
```

---

## JSON Export and Automation

### Pattern 6: Batch Error Analysis

```python
import json
from pathlib import Path
from dataflow.debug.debug_agent import DebugAgent
from dataflow.debug.knowledge_base import KnowledgeBase
from dataflow.platform.inspector import Inspector

def analyze_error_logs(log_file: Path, output_dir: Path):
    """Analyze error logs and generate debug reports."""
    # Initialize Debug Agent
    db = DataFlow("postgresql://localhost/mydb")
    kb = KnowledgeBase("patterns.yaml", "solutions.yaml")
    inspector = Inspector(db)
    agent = DebugAgent(kb, inspector)

    # Parse error log
    with open(log_file, "r") as f:
        error_lines = [line.strip() for line in f if "ERROR" in line]

    # Analyze each error
    reports = []
    for i, error_message in enumerate(error_lines):
        # Debug from string
        report = agent.debug_from_string(
            error_message,
            error_type="RuntimeError",
            max_solutions=5,
            min_relevance=0.3
        )

        # Export to JSON
        output_file = output_dir / f"report_{i:03d}.json"
        with open(output_file, "w") as f:
            f.write(report.to_json())

        reports.append(report.to_dict())

    # Generate summary
    summary = {
        "total_errors": len(reports),
        "categories": {},
        "average_execution_time_ms": sum(r["execution_time"] for r in reports) / len(reports)
    }

    for report in reports:
        category = report["error_category"]["category"]
        summary["categories"][category] = summary["categories"].get(category, 0) + 1

    with open(output_dir / "summary.json", "w") as f:
        json.dump(summary, f, indent=2)

    print(f"Analyzed {len(reports)} errors")
    print(f"Output directory: {output_dir}")

# Usage
analyze_error_logs(
    log_file=Path("app.log"),
    output_dir=Path("debug_reports")
)
```

---

### Pattern 7: Continuous Monitoring

```python
import json
import time
from datetime import datetime
from dataflow.debug.debug_agent import DebugAgent
from dataflow.debug.knowledge_base import KnowledgeBase
from dataflow.platform.inspector import Inspector

class ErrorMonitor:
    """Continuous error monitoring with Debug Agent."""

    def __init__(self, db: DataFlow, report_dir: Path):
        self.db = db
        self.report_dir = report_dir

        # Initialize Debug Agent
        kb = KnowledgeBase("patterns.yaml", "solutions.yaml")
        inspector = Inspector(db)
        self.agent = DebugAgent(kb, inspector)

        # Error statistics
        self.error_count = 0
        self.category_counts = {}

    def log_error(self, exception: Exception):
        """Log error with debug report."""
        self.error_count += 1

        # Debug error
        report = self.agent.debug(exception, max_solutions=5, min_relevance=0.3)

        # Update statistics
        category = report.error_category.category
        self.category_counts[category] = self.category_counts.get(category, 0) + 1

        # Save report
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = self.report_dir / f"error_{timestamp}_{self.error_count:04d}.json"
        with open(filename, "w") as f:
            f.write(report.to_json())

        # Print summary
        print(f"[{timestamp}] Error #{self.error_count}: {category}")
        print(f"  Root Cause: {report.analysis_result.root_cause}")
        print(f"  Solutions: {len(report.suggested_solutions)} found")

    def get_statistics(self):
        """Get error statistics."""
        return {
            "total_errors": self.error_count,
            "category_counts": self.category_counts
        }

# Usage
monitor = ErrorMonitor(db, Path("error_reports"))

# Log errors as they occur
for workflow in workflows:
    try:
        runtime.execute(workflow.build())
    except Exception as e:
        monitor.log_error(e)

# Print statistics
stats = monitor.get_statistics()
print(f"Total errors: {stats['total_errors']}")
print(f"By category: {stats['category_counts']}")
```

---

## Advanced API Usage

### Accessing Report Components

```python
# Debug error
report = agent.debug(exception, max_solutions=5, min_relevance=0.3)

# Access captured error
print(f"Error Type: {report.captured_error.error_type}")
print(f"Message: {report.captured_error.message}")
print(f"Timestamp: {report.captured_error.timestamp}")

# Access error category
print(f"Category: {report.error_category.category}")
print(f"Pattern ID: {report.error_category.pattern_id}")
print(f"Confidence: {report.error_category.confidence:.2%}")

# Access analysis
print(f"Root Cause: {report.analysis_result.root_cause}")
print(f"Affected Nodes: {report.analysis_result.affected_nodes}")
print(f"Affected Models: {report.analysis_result.affected_models}")
print(f"Context Data: {report.analysis_result.context_data}")

# Access solutions
for solution in report.suggested_solutions:
    print(f"\nSolution: {solution.title}")
    print(f"  Category: {solution.category}")
    print(f"  Relevance: {solution.relevance_score:.2%}")
    print(f"  Difficulty: {solution.difficulty}")
    print(f"  Time: {solution.estimated_time} min")
    print(f"  Code Example: {solution.code_example[:100]}...")

# Access metadata
print(f"\nExecution Time: {report.execution_time:.1f}ms")
```

---

## Best Practices

### 1. Initialize Debug Agent Once

```python
# ✅ GOOD - Initialize once (singleton)
kb = KnowledgeBase("patterns.yaml", "solutions.yaml")
inspector = Inspector(db)
agent = DebugAgent(kb, inspector)

# Use agent multiple times
for workflow in workflows:
    try:
        runtime.execute(workflow.build())
    except Exception as e:
        report = agent.debug(e)

# ❌ BAD - Initialize every time (slow)
for workflow in workflows:
    try:
        runtime.execute(workflow.build())
    except Exception as e:
        kb = KnowledgeBase("patterns.yaml", "solutions.yaml")
        inspector = Inspector(db)
        agent = DebugAgent(kb, inspector)
        report = agent.debug(e)  # Overhead: 20-50ms per init
```

### 2. Tune Relevance Threshold

```python
# Development - show all solutions
report = agent.debug(exception, max_solutions=10, min_relevance=0.0)

# Production - only high-confidence solutions
report = agent.debug(exception, max_solutions=3, min_relevance=0.7)

# Critical systems - only perfect matches
report = agent.debug(exception, max_solutions=1, min_relevance=0.95)
```

### 3. Store Reports for Analysis

```python
import json
from pathlib import Path
from datetime import datetime

def store_debug_report(report, error_dir: Path = Path("errors")):
    """Store debug report for later analysis."""
    error_dir.mkdir(exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    category = report.error_category.category
    filename = error_dir / f"{timestamp}_{category}.json"

    with open(filename, "w") as f:
        f.write(report.to_json())

    return filename

# Usage
try:
    runtime.execute(workflow.build())
except Exception as e:
    report = agent.debug(e)
    filename = store_debug_report(report)
    print(f"Report saved to: {filename}")
```

### 4. Integrate with Logging

```python
import logging
from dataflow.debug.debug_agent import DebugAgent

logger = logging.getLogger(__name__)

def execute_with_debug_logging(workflow, agent: DebugAgent):
    """Execute workflow with structured debug logging."""
    from kailash.runtime import LocalRuntime

    runtime = LocalRuntime()
    try:
        results, run_id = runtime.execute(workflow.build())
        logger.info("Workflow executed successfully", extra={"run_id": run_id})
        return results
    except Exception as e:
        # Debug error
        report = agent.debug(e, max_solutions=5)

        # Structured logging
        logger.error("Workflow execution failed", extra={
            "error_category": report.error_category.category,
            "confidence": report.error_category.confidence,
            "root_cause": report.analysis_result.root_cause,
            "affected_nodes": report.analysis_result.affected_nodes,
            "affected_models": report.analysis_result.affected_models,
            "solutions_found": len(report.suggested_solutions),
            "execution_time_ms": report.execution_time
        })

        # Log full JSON report
        logger.debug("Full debug report", extra={"report_json": report.to_json()})

        # Re-raise
        raise
```

---

## Summary

The DataFlow Debug Agent provides:

1. **Intelligent Error Categorization**: 50+ patterns across 5 categories
2. **Context-Aware Analysis**: Root cause with affected components
3. **Ranked Solutions**: Code examples with relevance scores
4. **Multiple Output Formats**: CLI, JSON, Python dictionary
5. **Programmatic API**: Easy integration with existing code

**Next Steps**:
- Try the Quick Start example
- Explore common error scenarios
- Integrate with your DataFlow application
- Review the 5-stage pipeline architecture

**Support**:
- Documentation: https://docs.dataflow.dev/debug-agent
- GitHub Issues: https://github.com/dataflow/debug-agent/issues
- Community: https://discord.gg/dataflow

---

**End of Debug Agent User Guide**
