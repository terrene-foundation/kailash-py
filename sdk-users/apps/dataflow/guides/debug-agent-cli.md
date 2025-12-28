# DataFlow Debug Agent CLI Guide

## Overview

The Debug Agent CLI provides AI-powered error diagnosis with ranked solutions for DataFlow applications. It combines ErrorEnhancer (60+ error types), Inspector (30 introspection methods), and pattern recognition to deliver actionable debugging guidance.

## Installation

```bash
pip install kailash-dataflow
```

The CLI is available immediately after installation as part of the `dataflow` command.

## Basic Usage

### Diagnose Errors from Input

```bash
dataflow diagnose --error-input "Field 'id' is required but not provided"
```

**Output**:
```
=================================================
          DataFlow Error Diagnosis
=================================================

Error Code: DF-101
Category: parameter_errors
Message: Field 'id' is required but not provided

Context:
  - node: UserCreateNode
  - parameter: id

Possible Causes:
  1. Parameter not included in node configuration
  2. Parameter misspelled in configuration
  3. Connection not established from source node

=================================================
          Ranked Solutions (Top 3)
=================================================

Solution 1 (Relevance: 0.9)
Description: Add the required 'id' parameter to the node
Code: workflow.add_node("UserCreateNode", "create", {"id": "user-123", ...})

Solution 2 (Relevance: 0.7)
Description: Check parameter mapping from connected nodes
Code: workflow.add_connection("source", "id", "UserCreateNode", "id")

Solution 3 (Relevance: 0.5)
Description: Verify parameter name spelling in configuration
Code: # Check: "id" not "user_id" or "userId"

=================================================
          Next Steps
=================================================

1. Add the required 'id' parameter to the node
2. Apply the following code:
   workflow.add_node("UserCreateNode", "create", {"id": "user-123", ...})

=================================================
Confidence: 0.85
=================================================
```

### Diagnose with Workflow File

```bash
dataflow diagnose --workflow workflow.py --error-input "Connection parameter type mismatch"
```

Loads workflow context from `workflow.py` to provide more accurate diagnosis.

### JSON Output Format

```bash
dataflow diagnose --error-input "Migration failed" --format json
```

**Output**:
```json
{
  "diagnosis": "Error DF-301 (migration_errors): Migration failed\n\nContext:\n  - table: users\n  - operation: add_column\n\nPossible causes:\n  1. Table does not exist\n  2. Column already exists\n  3. Invalid column type",
  "ranked_solutions": [
    {
      "solution": {
        "description": "Verify table exists before migration",
        "code_template": "await db.ensure_table_exists('users')",
        "priority": 1
      },
      "relevance_score": 0.9,
      "reasoning": "Directly addresses root cause",
      "confidence": 0.85,
      "effectiveness_score": 0.0,
      "combined_score": 0.63
    }
  ],
  "confidence": 0.85,
  "next_steps": [
    "1. Verify table exists before migration",
    "2. Apply the following code:",
    "   await db.ensure_table_exists('users')"
  ]
}
```

### Verbose Mode

```bash
dataflow diagnose --error-input "Node not found" --verbose
```

Shows additional information:
- Full code templates (not truncated)
- Detailed reasoning for each solution
- Effectiveness scores from historical feedback
- Combined scoring breakdown (70% relevance + 30% effectiveness)

### Limit Top Solutions

```bash
dataflow diagnose --error-input "Parameter validation failed" --top-n 5
```

Shows top 5 solutions instead of default 3.

## Command Reference

### `dataflow diagnose`

Diagnose DataFlow errors with AI-powered analysis and ranked solutions.

**Options**:

| Option | Short | Type | Required | Default | Description |
|--------|-------|------|----------|---------|-------------|
| `--error-input` | `-e` | TEXT | Yes* | - | Error message or trace to diagnose |
| `--workflow` | `-w` | PATH | No | - | Path to workflow file for context |
| `--format` | `-f` | CHOICE | No | `plain` | Output format: `plain` or `json` |
| `--verbose` | `-v` | FLAG | No | False | Show detailed diagnosis with full code |
| `--top-n` | `-n` | INT | No | 3 | Number of top solutions to show |

*Either `--error-input` or `--workflow` is required.

## Output Formats

### Plain Text Format

**Structure**:
1. **Header**: Error diagnosis title
2. **Error Details**: Code, category, message, context
3. **Possible Causes**: 3-5 root cause hypotheses
4. **Ranked Solutions**: Top N solutions with relevance scores
5. **Code Templates**: Implementation examples (truncated in normal mode, full in verbose)
6. **Next Steps**: Specific actions to resolve the error
7. **Confidence**: Overall diagnosis confidence (0.0-1.0)

**Truncation Rules**:
- Normal mode: Code templates truncated to 50 characters
- Verbose mode: Full code templates shown

### JSON Format

**Structure**:
```json
{
  "diagnosis": "string",           // Full diagnosis text
  "ranked_solutions": [            // Top N solutions
    {
      "solution": {
        "description": "string",
        "code_template": "string",
        "priority": "int"
      },
      "relevance_score": "float",  // 0.0-1.0
      "reasoning": "string",
      "confidence": "float",        // 0.0-1.0
      "effectiveness_score": "float", // -1.0 to 1.0
      "combined_score": "float"    // 0.7*relevance + 0.3*effectiveness
    }
  ],
  "confidence": "float",           // 0.0-1.0
  "next_steps": ["string"]         // Actionable steps
}
```

## Common Patterns

### Pattern 1: Quick Error Diagnosis

```bash
# Copy error message from terminal
dataflow diagnose --error-input "ValueError: Table 'users' not found"
```

Use when you encounter an error and need immediate guidance.

### Pattern 2: Workflow-Aware Diagnosis

```bash
# Provide workflow file for context
dataflow diagnose --workflow my_workflow.py --error-input "Connection failed"
```

Use when error is related to specific workflow structure.

### Pattern 3: Automated Error Handling

```python
import subprocess
import json

try:
    # Your DataFlow code
    pass
except Exception as e:
    # Call diagnose command
    result = subprocess.run([
        "dataflow", "diagnose",
        "--error-input", str(e),
        "--format", "json"
    ], capture_output=True, text=True)

    diagnosis = json.loads(result.stdout)
    print(f"Top solution: {diagnosis['ranked_solutions'][0]['solution']['description']}")
```

Use in automated systems for self-healing workflows.

### Pattern 4: Debugging Workflow Files

```bash
# Analyze workflow structure
dataflow diagnose --workflow complex_workflow.py --error-input "Cycle detected"
```

Use when debugging complex workflow structures with Inspector integration.

## Architecture

### Components

1. **ErrorAnalysisEngine**:
   - Analyzes errors using ErrorEnhancer (60+ error types)
   - Extracts error code, message, context, causes, solutions

2. **PatternRecognitionEngine**:
   - Generates pattern keys from error analysis
   - Queries KnowledgeBase for similar patterns
   - Calculates pattern similarity scores

3. **SolutionRankingEngine**:
   - Uses LLM (gpt-4o-mini) to rank solutions by relevance
   - Integrates historical effectiveness from KnowledgeBase
   - Calculates combined score: 0.7 * relevance + 0.3 * effectiveness

4. **DebugAgent**:
   - Orchestrates all components
   - Delegates to ErrorEnhancer, Inspector, KnowledgeBase
   - Returns Diagnosis with top 3 ranked solutions

### Data Flow

```
Error Input → ErrorAnalysisEngine → ErrorAnalysis
                                      ↓
                                PatternRecognitionEngine → Pattern Key
                                      ↓
                                SolutionRankingEngine → Ranked Solutions
                                      ↓
                                  DebugAgent → Diagnosis
                                      ↓
                                  CLI Formatter → Output
```

### Performance

- **Target**: <5 seconds per diagnosis (95th percentile)
- **LLM calls**: 1-2 per diagnosis (minimize latency)
- **Caching**: Pattern cache for 90%+ hit rate on common errors

## Integration with ErrorEnhancer

### Error Codes Supported

**60+ error types** across 8 categories:

- **DF-1XX**: Parameter errors (missing, type mismatch, validation)
- **DF-2XX**: Connection errors (missing, circular, type mismatch)
- **DF-3XX**: Migration errors (schema, table not found, constraints)
- **DF-4XX**: Configuration errors (database URL, environment vars)
- **DF-5XX**: Runtime errors (event loop, timeouts, resources)
- **DF-6XX**: Model errors (primary key, field types)
- **DF-7XX**: Node errors (not found, generation failed)
- **DF-8XX**: Workflow errors (build failed, cycles, structure)

### Enhanced Error Format

```python
# Errors are automatically enhanced with:
- error_code: DF-XXX format
- category: Error category
- context: What failed (node, parameter, table)
- causes: 3-5 possible root causes
- solutions: 3-5 ranked solutions with code examples
- documentation_link: Detailed troubleshooting guide
```

## Integration with Inspector

### Workflow Introspection

When `--workflow` is provided, Inspector API is used to:
- List all connections
- Trace parameter flows
- Find broken connections
- Validate workflow structure
- Detect circular dependencies

### Inspector Methods Used

- `connections()`: List all workflow connections
- `trace_parameter(node_id, param)`: Trace parameter back to source
- `validate_connections()`: Check connection validity
- `find_broken_connections()`: Detect missing connections

## Troubleshooting

### Issue: "Missing Authorization header"

**Cause**: KnowledgeBase or LLM requires authentication (not yet implemented).

**Solution**: Debug Agent currently works in offline mode using priority-based ranking. LLM integration is Phase 2.

### Issue: "No solutions found"

**Cause**: Error message not recognized by ErrorEnhancer.

**Solution**: Ensure error message contains DataFlow error code (DF-XXX) or recognizable patterns. Check ErrorEnhancer documentation for supported errors.

### Issue: Slow diagnosis (>10 seconds)

**Cause**: LLM call or pattern matching taking too long.

**Solution**:
1. Check network connectivity for LLM calls
2. Use `--format json` for faster processing
3. Report performance issue with error details

### Issue: JSON output parsing error

**Cause**: LLM returned malformed JSON or unexpected format.

**Solution**: Use `--format plain` as fallback and report the issue.

## Examples

### Example 1: Parameter Error

```bash
$ dataflow diagnose --error-input "DF-101: Field 'email' is required"

=================================================
          DataFlow Error Diagnosis
=================================================

Error Code: DF-101
Category: parameter_errors
Message: Field 'email' is required

Ranked Solutions (Top 3):
1. Add 'email' parameter to node configuration (Relevance: 0.9)
   Code: {"id": "...", "email": "user@example.com"}

2. Connect 'email' from source node (Relevance: 0.7)
   Code: workflow.add_connection("source", "email", "target", "email")

3. Check parameter name spelling (Relevance: 0.5)
   Code: # "email" not "Email" or "user_email"

Confidence: 0.85
```

### Example 2: Migration Error

```bash
$ dataflow diagnose --error-input "DF-301: Table 'orders' does not exist" --verbose

=================================================
          DataFlow Error Diagnosis
=================================================

Error Code: DF-301
Category: migration_errors
Message: Table 'orders' does not exist

Context:
  - table: orders
  - operation: select
  - database: postgresql://localhost/mydb

Ranked Solutions (Top 3):
1. Run migrations to create table (Relevance: 0.95)
   Code: await db.initialize()  # Creates all registered models
   Reasoning: Directly addresses missing table by running schema creation
   Effectiveness: 0.85 (based on 42 successful resolutions)

2. Check model registration (Relevance: 0.8)
   Code: @db.model
         class Order:
             id: str
             amount: float
   Reasoning: Table is created when model is registered
   Effectiveness: 0.6 (based on 18 successful resolutions)

3. Verify database connection (Relevance: 0.6)
   Code: print(db._database_url)  # Check connection string
   Reasoning: Connection issues can prevent table detection
   Effectiveness: 0.3 (based on 8 successful resolutions)

Next Steps:
1. Run migrations to create table
2. Apply the following code:
   await db.initialize()
3. If that doesn't work, try alternative solutions (ranked #2-#3)

Confidence: 0.90
```

### Example 3: Workflow Structure Error

```bash
$ dataflow diagnose --workflow complex_workflow.py --error-input "Cycle detected"

=================================================
          DataFlow Error Diagnosis
=================================================

Error Code: DF-801
Category: workflow_errors
Message: Cycle detected in workflow

Workflow Context:
  - Node type: UserCreateNode
  - Connections: 15

Possible Causes:
  1. Node connected back to itself (self-loop)
  2. Circular dependency between nodes (A→B→C→A)
  3. Connection direction reversed

Ranked Solutions (Top 3):
1. Use Inspector to visualize connections (Relevance: 0.95)
   Code: from dataflow.platform.inspector import Inspector
         inspector = Inspector(workflow)
         print(inspector.connections())

2. Remove circular connection (Relevance: 0.85)
   Code: # Identify cycle: A→B→C→A
         # Remove one connection to break cycle

3. Use conditional execution (Relevance: 0.7)
   Code: runtime = LocalRuntime(conditional_execution="skip_branches")

Confidence: 0.88
```

## Best Practices

1. **Always provide error codes**: Include DF-XXX codes for accurate diagnosis
2. **Use workflow context**: Provide `--workflow` for structure-related errors
3. **Start with plain format**: Use human-readable output first, switch to JSON for automation
4. **Verbose for complex errors**: Use `--verbose` when solutions need detailed code examples
5. **Limit solutions appropriately**: Use `--top-n` based on error complexity (3 for simple, 5+ for complex)

## Next Steps

- **Task 4.7**: Integration Tests (verify CLI with real DebugAgent)
- **Task 4.8**: Documentation (expand examples, troubleshooting scenarios)
- **Phase 2**: LLM integration for real-time solution ranking
- **Phase 3**: Feedback loop for effectiveness tracking

## Related Documentation

- **ErrorEnhancer**: `sdk-users/apps/dataflow/guides/error-handling.md`
- **Inspector**: `sdk-users/apps/dataflow/guides/inspector-debugging-guide.md`
- **Troubleshooting**: `sdk-users/apps/dataflow/troubleshooting/common-errors.md`
