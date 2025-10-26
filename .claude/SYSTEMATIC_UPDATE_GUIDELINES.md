# Systematic Documentation Update Guidelines

**Purpose**: Enable efficient, accurate, systematic updates of 651 remaining files while maintaining "one mistake = disaster" quality level.

**Context**: 25 CRITICAL files updated successfully. This document extracts patterns for remaining updates.

---

## Section 1: Common Update Patterns

Based on analysis of 25 completed files, these patterns appear consistently:

### Pattern A: Skill Metadata Block (MANDATORY)
**Every skill file MUST have this at the top:**
```markdown
---
name: skill-name
description: "Brief description with trigger keywords"
---

# Skill Title

Brief one-line description.

> **Skill Metadata**
> Category: `category-name`
> Priority: `CRITICAL|HIGH|MEDIUM|LOW`
> SDK Version: `0.9.25+`
> Related Skills: [`skill-ref`](path/to/skill.md)
> Related Subagents: `subagent-name` (when to use)
```

### Pattern B: Quick Reference Section (MANDATORY)
**Every skill must start with Quick Reference:**
```markdown
## Quick Reference

- **Primary Use**: [Clear one-line statement]
- **Import**: `from kailash.x.y import Z`
- **Pattern**: `Pattern() → method() → build()`
- **Execution**: `runtime.execute(workflow.build())`
- **CRITICAL**: [Most critical rule]
```

### Pattern C: Core Pattern Section (MANDATORY)
**Show minimal working example immediately:**
```markdown
## Core Pattern

```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

workflow = WorkflowBuilder()
workflow.add_node("NodeName", "id", {"param": "value"})  # String-based

runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())  # ALWAYS .build()
```
```

### Pattern D: Technical Facts (Canonical)
**Use EXACT wording from these sources:**

#### BaseRuntime Architecture
```markdown
## Shared Architecture (Internal)

Both LocalRuntime and AsyncLocalRuntime inherit from BaseRuntime and use shared mixins:

- **BaseRuntime**: Provides 29 configuration parameters, execution metadata, workflow caching
- **ValidationMixin**: Shared validation logic (workflow validation, connection contracts, conditional execution)
- **ParameterHandlingMixin**: Shared parameter resolution (${param} templates, type preservation, deep merge)

This architecture ensures consistent behavior between sync and async runtimes. All existing usage patterns remain unchanged.
```

#### Runtime Return Values
```markdown
- **LocalRuntime**: Returns tuple `(results, run_id)`
- **AsyncLocalRuntime**: Returns dict `results` (no run_id in return)
```

#### Connection Syntax
```markdown
## 4-Parameter Connection Pattern

workflow.add_connection(
    "source_node",    # From node ID
    "output_field",   # Output field name
    "target_node",    # To node ID
    "input_field"     # Input field name
)
```

### Pattern E: Common Mistakes Section (MANDATORY)
**Always show wrong vs correct:**
```markdown
## Common Mistakes

### ❌ Mistake 1: Missing .build() Call
```python
# Wrong - missing .build()
results, run_id = runtime.execute(workflow)  # ERROR!
```

### ✅ Fix: Always Call .build()
```python
# Correct
results, run_id = runtime.execute(workflow.build())  # ✓
```
```

### Pattern F: Documentation References (MANDATORY)
```markdown
## Documentation References

### Primary Sources
- [`sdk-users/path/to/doc.md`](../../../sdk-users/path/to/doc.md)
- [`CLAUDE.md#L111-177`](../../../CLAUDE.md)

### Related Documentation
- [Topic Guide](../path/to/guide.md)

### Advanced References
- `src/module/file.py` - Implementation (XXX lines)
```

### Pattern G: Related Patterns Navigation
```markdown
## Related Patterns

- **For fundamentals**: See [`workflow-quickstart`](../workflow-quickstart.md)
- **For connections**: See [`connection-patterns`](../connection-patterns.md)
- **For parameters**: See [`param-passing-quick`](../param-passing-quick.md)
```

### Pattern H: When to Escalate Section
```markdown
## When to Escalate to Subagent

Use `pattern-expert` subagent when:
- Implementing complex cyclic workflows
- Designing multi-path conditional logic
- Debugging advanced parameter passing issues
- Creating custom nodes from scratch
- Optimizing workflow performance
```

---

## Section 2: Update Templates by File Type

### Template A: Core SDK Skills (01-core-sdk/*.md)

**Standard Structure:**
```markdown
---
name: skill-name
description: "Description with keywords"
---

# Skill Title

One-line description.

> **Skill Metadata**
> Category: `core-sdk`
> Priority: `CRITICAL|HIGH|MEDIUM|LOW`
> SDK Version: `0.9.25+`

## Quick Reference

- **Import**: `from kailash.x import Y`
- **Pattern**: Pattern description
- **Execution**: `runtime.execute(workflow.build())`

## Core Pattern

```python
# Minimal working example
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

workflow = WorkflowBuilder()
# ... add nodes using string-based API
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())
```

## Key Parameters / Options

[Table or list of parameters]

## Common Use Cases

- Use case 1
- Use case 2
- Use case 3

## Common Mistakes

### ❌ Mistake 1: [Description]
### ✅ Fix: [Solution]

## Related Patterns

[Links to related skills]

## When to Escalate to Subagent

[Guidance on when to use subagents]

## Documentation References

### Primary Sources
[Links to sdk-users/ docs]

## Quick Tips

- 💡 Tip 1
- 💡 Tip 2

## Keywords for Auto-Trigger

<!-- Trigger Keywords: keyword1, keyword2, keyword3 -->
```

**Key Updates:**
1. Add metadata block if missing
2. Ensure string-based node API (`"NodeName"` not `NodeClass()`)
3. Always show `runtime.execute(workflow.build())`
4. Include BaseRuntime architecture for runtime-related skills
5. Reference sdk-users/ documentation
6. Include "When to Escalate" section

### Template B: DataFlow Skills (02-dataflow/*.md)

**Critical Facts to Include:**
```markdown
- **NOT an ORM**: Workflow-native database framework
- **9 nodes per model**: CREATE, READ, UPDATE, DELETE, LIST, BULK_CREATE, BULK_UPDATE, BULK_DELETE, BULK_UPSERT
- **Zero-config**: `db = DataFlow()` auto-detects SQLite (dev) or PostgreSQL (prod)
- **String IDs**: Fully supported - no forced integer conversion (v0.5.0+)
- **Multi-database**: PostgreSQL, MySQL, SQLite with 100% feature parity
```

**Common Mistakes Section:**
```markdown
## Common Mistakes

### ❌ Mistake 1: Direct Model Instantiation
```python
# Wrong - models are NOT instantiable
user = User(name="John")  # ERROR!
```

### ✅ Fix: Use Generated Nodes
```python
# Correct - use workflow nodes
workflow.add_node("UserCreateNode", "create", {
    "name": "John",
    "email": "john@example.com"
})
```

### ❌ Mistake 2: Wrong Template Syntax
```python
# Wrong - DataFlow uses connections, not {{}} syntax
workflow.add_node("OrderCreateNode", "create", {
    "customer_id": "{{customer.id}}"  # ERROR!
})
```

### ✅ Fix: Use Connections
```python
# Correct - use explicit connections
workflow.add_connection("customer", "id", "create_order", "customer_id")
```
```

**DataFlow + Nexus Integration Warning:**
```markdown
## DataFlow + Nexus Integration

**CRITICAL**: Use these settings to avoid blocking/slow startup:

```python
# Step 1: Create Nexus FIRST with auto_discovery=False
app = Nexus(auto_discovery=False)  # CRITICAL: Prevents blocking

# Step 2: Create DataFlow with skip_registry=True
db = DataFlow(
    "postgresql://user:pass@localhost/db",
    skip_registry=True,           # CRITICAL: Prevents 5-10s delay
    enable_model_persistence=False  # Fast startup
)
```
```

### Template C: Nexus Skills (03-nexus/*.md)

**Key Facts:**
```markdown
- **Zero-config**: `app = Nexus()` - no configuration needed
- **Multi-channel**: Single registration → API + CLI + MCP simultaneously
- **Default ports**: 8000 (API), 3001 (MCP)
- **Always call .build()**: `app.register("name", workflow.build())`
```

**Critical Patterns:**
```markdown
## Critical Patterns

### Always Call .build()
```python
# CORRECT
app.register("workflow-name", workflow.build())

# WRONG - Will fail
app.register("workflow-name", workflow)
```

### Correct Parameter Order
```python
# CORRECT - name first, workflow second
app.register("name", workflow.build())

# WRONG - reversed
app.register(workflow.build(), "name")
```
```

### Template D: Kaizen Skills (04-kaizen/*.md)

**Key Facts:**
```markdown
- **Built on Core SDK**: Signature-based programming + BaseAgent architecture
- **Multi-modal**: Vision (Ollama + OpenAI GPT-4V), Audio (Whisper)
- **Multi-agent**: Google A2A protocol with semantic matching
- **Tool calling**: 12 builtin tools with approval workflows
```

**API Keys Warning:**
```markdown
## ⚠️ CRITICAL: API Keys

**Location**: `.env` file in project root

**Available Keys** (DO NOT ask user):
- `OPENAI_API_KEY` - OpenAI API
- `ANTHROPIC_API_KEY` - Anthropic API

**Always load .env**:
```python
from dotenv import load_dotenv
load_dotenv()  # ALWAYS first
```
```

### Template E: Node Reference Skills (08-nodes-reference/*.md)

**Standard Structure:**
```markdown
---
name: nodes-category-reference
description: "Category nodes reference"
---

# Category Nodes Reference

Complete reference for [category] nodes.

> **Skill Metadata**
> Category: `nodes`
> Priority: `HIGH`
> SDK Version: `0.9.25+`

## Quick Reference

```python
from kailash.nodes.category import NodeName
```

## Core Nodes

### NodeName1
```python
workflow.add_node("NodeName1", "id", {
    "param1": "value1",
    "param2": "value2"
})
```

[Repeat for each node]

## Related Skills

[Links]

## Documentation

- [`sdk-users/2-core-concepts/nodes/category.md`](path)

<!-- Trigger Keywords: keywords -->
```

### Template F: Error Troubleshooting Skills (15-error-troubleshooting/*.md)

**Standard Structure:**
```markdown
---
name: error-error-name
description: "Fix [error name] errors"
---

# Error: [Error Name]

Fix [description of error].

> **Skill Metadata**
> Category: `cross-cutting` (error-resolution)
> Priority: `CRITICAL|HIGH`
> SDK Version: `0.9.0+`

## The Error

### Common Error Messages
```
[Actual error messages]
```

### Root Cause
[Explanation]

## Quick Fix

### ❌ **WRONG** - [What causes error]
```python
[Wrong code]
```

### ✅ **CORRECT** - [Solution]
```python
[Correct code]
```

## Common Variations

[List variations]

## Why [Solution] is Required

[Explanation]

## Related Patterns

[Links]

## Quick Diagnostic

- [ ] Checklist item 1
- [ ] Checklist item 2

## Prevention Tips

- 💡 Tip 1
- 💡 Tip 2
```

### Template G: Gold Standards Skills (17-gold-standards/*.md)

**Standard Structure:**
```markdown
---
name: gold-standard-name
description: "Gold standard for [topic]"
---

# Gold Standard: [Topic]

Mandatory best practices for [topic].

> **Skill Metadata**
> Category: `gold-standards`
> Priority: `HIGH|CRITICAL`
> SDK Version: `0.9.25+`

## Quick Reference

[Summary of standard]

## Core Pattern

```python
[Minimal example following standard]
```

## Violations to Avoid

### ❌ Violation 1: [Description]
### ✅ Correct Approach: [Solution]

## Validation Checklist

- [ ] Check 1
- [ ] Check 2

## Related Standards

[Links]

## Documentation References

- [`sdk-users/7-gold-standards/standard-name.md`](path)
```

---

## Section 3: Technical Facts (Canonical Descriptions)

### Fact 1: BaseRuntime Architecture
```markdown
Both LocalRuntime and AsyncLocalRuntime inherit from BaseRuntime and use shared mixins:

- **BaseRuntime**: Provides 29 configuration parameters, execution metadata, workflow caching
- **ValidationMixin**: Shared validation logic (workflow validation, connection contracts, conditional execution)
- **ParameterHandlingMixin**: Shared parameter resolution (${param} templates, type preservation, deep merge)

This architecture ensures consistent behavior between sync and async runtimes.
```

### Fact 2: ValidationMixin Methods
```markdown
**ValidationMixin provides**:
- Workflow structure validation
- Connection contract verification
- Conditional execution validation
- Node parameter validation
- Cycle detection (for non-cyclic workflows)
```

### Fact 3: ParameterHandlingMixin Methods
```markdown
**ParameterHandlingMixin provides**:
- Template resolution (${param} syntax)
- Type preservation during resolution
- Deep merge of parameter dictionaries
- Runtime parameter override support
```

### Fact 4: Runtime Return Values
```markdown
**LocalRuntime**: Returns tuple `(results, run_id)`
```python
results, run_id = runtime.execute(workflow.build())
```

**AsyncLocalRuntime**: Returns dict `results` (no run_id)
```python
results = await runtime.execute_workflow_async(workflow.build(), inputs={})
```
```

### Fact 5: String-Based Node API
```markdown
**Current Production Pattern** (v0.9.20+):
```python
workflow.add_node("NodeName", "node_id", {"config": "value"})  # String-based
```

**Deprecated Pattern** (pre-v0.9.20):
```python
from kailash.nodes import NodeName
workflow.add_node("node_id", NodeName(config="value"))  # Instance-based (deprecated)
```
```

### Fact 6: Connection Syntax (4-Parameter)
```markdown
**Current Pattern** (v0.8.0+):
```python
workflow.add_connection(
    "source_node",    # From node ID
    "output_field",   # Output field name
    "target_node",    # To node ID
    "input_field"     # Input field name
)
```

**Deprecated Pattern** (pre-v0.8.0):
```python
workflow.add_connection("source", "target", "field")  # 3 parameters (deprecated)
```
```

### Fact 7: Workflow Execution Pattern
```markdown
**CRITICAL**: Always call `.build()` before execution

```python
# ✅ CORRECT
results, run_id = runtime.execute(workflow.build())

# ❌ WRONG - Missing .build()
results, run_id = runtime.execute(workflow)  # ERROR!

# ❌ WRONG - Backwards
workflow.execute(runtime)  # ERROR!
```
```

### Fact 8: DataFlow Node Generation
```markdown
Each `@db.model` automatically generates 9 node types:
- `{Model}CreateNode` - Single insert
- `{Model}ReadNode` - Single select
- `{Model}UpdateNode` - Single update
- `{Model}DeleteNode` - Single delete
- `{Model}ListNode` - Query with filters
- `{Model}BulkCreateNode` - Bulk insert
- `{Model}BulkUpdateNode` - Bulk update
- `{Model}BulkDeleteNode` - Bulk delete
- `{Model}BulkUpsertNode` - Insert or update
```

### Fact 9: Import Patterns (Absolute)
```markdown
**ALWAYS use absolute imports** (from repo root):

```python
# ✅ CORRECT - Absolute imports
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from dataflow import DataFlow
from nexus import Nexus

# ❌ WRONG - Relative imports (fails in production)
from ..workflow.builder import WorkflowBuilder  # Don't use
```
```

### Fact 10: SDK Version References
```markdown
**Current Versions**:
- Core SDK: `0.9.25+`
- DataFlow: `0.7.1+`
- Nexus: `1.1.1+`
- Kaizen: `0.4.0+`
```

---

## Section 4: Validation Criteria

### Validation Checklist Per File

```markdown
## File Validation Checklist

### Structure ✅
- [ ] Has YAML frontmatter with name and description
- [ ] Has "Skill Metadata" block with category, priority, SDK version
- [ ] Has "Quick Reference" section at top
- [ ] Has "Core Pattern" with working code example
- [ ] Has "Common Mistakes" section with ❌/✅ examples
- [ ] Has "Related Patterns" section
- [ ] Has "Documentation References" section
- [ ] Has "Keywords for Auto-Trigger" comment at bottom

### Technical Accuracy ✅
- [ ] Uses string-based node API (`"NodeName"` not `NodeClass()`)
- [ ] Shows `runtime.execute(workflow.build())` pattern
- [ ] Uses 4-parameter connection syntax
- [ ] References correct SDK versions
- [ ] Uses absolute imports (not relative)
- [ ] Links to correct sdk-users/ documentation paths
- [ ] Includes correct BaseRuntime architecture (if runtime-related)

### Code Examples ✅
- [ ] All code examples are syntactically valid Python
- [ ] Examples use current API patterns (not deprecated)
- [ ] Examples include necessary imports
- [ ] Examples are minimal but complete
- [ ] Examples follow gold standards (absolute imports, .build(), etc.)

### Documentation Links ✅
- [ ] All internal links are valid (point to existing files)
- [ ] Links use relative paths from skill file location
- [ ] Links to sdk-users/ documentation are correct
- [ ] Links to source code include line numbers if specific
- [ ] No broken links to non-existent files

### Consistency ✅
- [ ] Tone matches other skills (concise, authoritative)
- [ ] Uses consistent terminology (e.g., "workflow" not "pipeline")
- [ ] Uses consistent emoji patterns (❌ for wrong, ✅ for correct)
- [ ] Follows section ordering from templates
- [ ] Uses consistent code formatting (triple backticks with python)
```

### Code Example Test Strategy

For each code example:
1. **Extract code block** from markdown
2. **Create temp test file**: `/tmp/test_skill_[name].py`
3. **Add imports and setup**:
   ```python
   import sys
   import os
   sys.path.insert(0, "./repos/dev/kailash_dataflow")

   # Actual example code here
   ```
4. **Run with pytest**: `pytest /tmp/test_skill_[name].py -v`
5. **Verify output** matches documented behavior

### Infrastructure Testing Requirements

**For integration examples** (require real infrastructure):
```bash
# Ensure Docker services running
cd tests/utils
./test-env up && ./test-env status

# Required services:
# ✅ PostgreSQL: Ready
# ✅ Redis: Ready
# ✅ MinIO: Ready
# ✅ Elasticsearch: Ready
```

**For DataFlow examples**:
```python
# Use SQLite for skill examples (no Docker needed)
db = DataFlow()  # Defaults to SQLite in-memory
```

---

## Section 5: Batch Update Strategy

### Batch 1: Core SDK Skills (HIGH PRIORITY) - 14 files
**Group**: 01-core-sdk/*.md

**Shared characteristics:**
- All show LocalRuntime + WorkflowBuilder patterns
- All need BaseRuntime architecture (if runtime-related)
- All need string-based node API
- All need 4-parameter connections

**Update approach:**
1. Process files sequentially (not parallel - prevent merge conflicts)
2. Apply Template A from Section 2
3. Include canonical BaseRuntime description (Fact 1)
4. Add Quick Reference section
5. Add Common Mistakes section
6. Validate all code examples work

**Files:**
- async-workflow-patterns.md
- connection-patterns.md
- cycle-workflows-basics.md
- error-handling-patterns.md
- kailash-imports.md
- kailash-installation.md
- mcp-integration-guide.md
- node-patterns-common.md
- param-passing-quick.md
- pythoncode-best-practices.md
- switchnode-patterns.md
- async-pythoncode-patterns.md
- [others in directory]

### Batch 2: DataFlow Skills (HIGH PRIORITY) - 25 files
**Group**: 02-dataflow/*.md

**Shared characteristics:**
- All explain DataFlow-specific features
- All need "NOT an ORM" clarification
- All need 9 nodes per model fact
- All need DataFlow + Nexus integration warning

**Update approach:**
1. Apply Template B from Section 2
2. Include Fact 8 (node generation)
3. Add Common Mistakes (template syntax, direct instantiation)
4. Add DataFlow + Nexus warning
5. Show zero-config pattern
6. Include string ID preservation fact

**Files:**
- dataflow-quickstart.md ✅ (already updated)
- dataflow-models.md
- dataflow-queries.md
- dataflow-crud-operations.md
- dataflow-bulk-operations.md
- [others in directory]

### Batch 3: Nexus Skills (HIGH PRIORITY) - 24 files
**Group**: 03-nexus/*.md

**Shared characteristics:**
- All show Nexus() zero-config setup
- All need .build() reminder
- All show multi-channel patterns

**Update approach:**
1. Apply Template C from Section 2
2. Show zero-config pattern first
3. Add .build() critical pattern section
4. Include multi-channel benefits
5. Show API/CLI/MCP access examples

### Batch 4: Error Troubleshooting (CRITICAL) - 7 files
**Group**: 15-error-troubleshooting/*.md

**Shared characteristics:**
- All show specific error + fix
- All need error message examples
- All need root cause explanation

**Update approach:**
1. Apply Template F from Section 2
2. Show actual error messages
3. Explain root cause clearly
4. Show wrong vs correct code
5. Add diagnostic checklist

**Files:**
- error-missing-build.md ✅ (already updated)
- error-runtime-execution.md ✅ (already updated)
- error-connection-params.md ✅ (already updated)
- error-parameter-validation.md ✅ (already updated)
- error-cycle-convergence.md ✅ (already updated)
- error-dataflow-template-syntax.md ✅ (already updated)
- error-nexus-blocking.md ✅ (already updated)

### Batch 5: Gold Standards (CRITICAL) - 10 files
**Group**: 17-gold-standards/*.md

**Shared characteristics:**
- All define mandatory practices
- All show violations vs correct approach
- All link to detailed docs

**Update approach:**
1. Apply Template G from Section 2
2. Define standard clearly
3. Show violation examples
4. Provide validation checklist
5. Link to detailed sdk-users/ docs

**Files:**
- gold-absolute-imports.md ✅ (already updated)
- gold-parameter-passing.md ✅ (already updated)
- gold-error-handling.md ✅ (already updated)
- gold-workflow-design.md ✅ (already updated)
- gold-testing.md ✅ (already updated)
- gold-mocking-policy.md ✅ (already updated)
- gold-custom-nodes.md ✅ (already updated)
- gold-security.md ✅ (already updated)
- gold-documentation.md ✅ (already updated)
- gold-test-creation.md ✅ (already updated)

### Batch 6: Node References (MEDIUM PRIORITY) - 10 files
**Group**: 08-nodes-reference/*.md

**Files:**
- nodes-ai-reference.md ✅ (already updated)
- nodes-api-reference.md
- nodes-code-reference.md
- nodes-data-reference.md
- nodes-database-reference.md
- nodes-file-reference.md
- nodes-logic-reference.md
- nodes-transform-reference.md
- nodes-transaction-reference.md
- nodes-quick-index.md

### Batch 7: Cheatsheets (MEDIUM PRIORITY) - 35+ files
**Group**: 06-cheatsheets/*.md

**Approach:** Process by sub-category (cycles, production, security, etc.)

### Batch 8: Workflow Patterns (LOW PRIORITY) - 15+ files
**Group**: 09-workflow-patterns/*.md

### Batch 9: Development Guides (LOW PRIORITY) - 30+ files
**Group**: 07-development-guides/*.md

### Batch 10: Other Categories (LOW PRIORITY) - Remaining files
**Groups**: 04-kaizen, 05-mcp, 10-deployment-git, 11-frontend-integration, 12-testing-strategies, 13-architecture-decisions, 14-code-templates, 16-validation-patterns

---

## Section 6: Quality Gates Between Batches

### Gate 1: Structural Validation
```bash
# Check all files in batch have required sections
for file in batch/*.md; do
  grep -q "## Quick Reference" "$file" || echo "MISSING: Quick Reference in $file"
  grep -q "## Core Pattern" "$file" || echo "MISSING: Core Pattern in $file"
  grep -q "## Common Mistakes" "$file" || echo "MISSING: Common Mistakes in $file"
  grep -q "## Documentation References" "$file" || echo "MISSING: Documentation References in $file"
done
```

### Gate 2: Technical Accuracy
```bash
# Check for deprecated patterns
grep -r "workflow.add_node(\"id\"," batch/*.md && echo "ERROR: Instance-based nodes found"
grep -r "workflow.execute(" batch/*.md && echo "ERROR: Wrong execution pattern"
grep -r "from \.\." batch/*.md && echo "ERROR: Relative imports found"
```

### Gate 3: Code Example Validation
```bash
# Extract and test all code examples
for file in batch/*.md; do
  python extract_and_test_examples.py "$file"
done
```

### Gate 4: Link Validation
```bash
# Check all internal links work
for file in batch/*.md; do
  python validate_links.py "$file"
done
```

### Gate 5: Consistency Check
```bash
# Verify consistent terminology
grep -r "pipeline" batch/*.md && echo "WARNING: Use 'workflow' not 'pipeline'"
grep -r "execute_workflow" batch/*.md && echo "WARNING: Use 'execute' not 'execute_workflow'"
```

---

## Section 7: Common Mistakes to Avoid

### Mistake 1: Inconsistent Technical Facts
**Problem**: Different skills say different things about BaseRuntime

**Solution**: Copy-paste canonical descriptions from Section 3

### Mistake 2: Missing .build() in Examples
**Problem**: Code examples show `runtime.execute(workflow)` without `.build()`

**Solution**: ALWAYS include `.build()` in every execution example

### Mistake 3: Using Deprecated API Patterns
**Problem**: Showing instance-based nodes or 3-parameter connections

**Solution**: Use string-based nodes and 4-parameter connections everywhere

### Mistake 4: Broken Documentation Links
**Problem**: Links to sdk-users/ documentation use wrong paths

**Solution**: Verify paths relative to skill file location:
- From `.claude/skills/01-core-sdk/file.md` → `../../../sdk-users/`
- From `.claude/skills/02-dataflow/file.md` → `../../../../sdk-users/apps/dataflow/`

### Mistake 5: Missing Common Mistakes Section
**Problem**: Skills don't show what NOT to do

**Solution**: Always include ❌ Wrong / ✅ Correct examples

### Mistake 6: Outdated SDK Versions
**Problem**: Referencing old SDK versions in metadata

**Solution**: Use current versions from Fact 10

### Mistake 7: No Quick Reference
**Problem**: Users can't quickly find what they need

**Solution**: Every skill starts with Quick Reference section

### Mistake 8: Untested Code Examples
**Problem**: Examples don't actually work

**Solution**: Extract and test every code example before committing

### Mistake 9: Missing Keywords
**Problem**: Skills don't auto-trigger for relevant queries

**Solution**: Include comprehensive trigger keywords at bottom

### Mistake 10: Relative Imports in Examples
**Problem**: Examples use relative imports that fail in production

**Solution**: Always use absolute imports (from repo root)

---

## Section 8: Automated Validation Script

```python
#!/usr/bin/env python3
"""
Validate skill file compliance with update guidelines.
"""

import re
import sys
from pathlib import Path

def validate_skill_file(file_path: Path) -> list[str]:
    """Return list of validation errors (empty if valid)."""
    errors = []
    content = file_path.read_text()

    # Check 1: YAML frontmatter
    if not content.startswith("---\n"):
        errors.append("Missing YAML frontmatter")

    # Check 2: Skill Metadata block
    if "> **Skill Metadata**" not in content:
        errors.append("Missing Skill Metadata block")

    # Check 3: Required sections
    required_sections = [
        "## Quick Reference",
        "## Core Pattern",
        "## Common Mistakes",
        "## Related Patterns",
        "## Documentation References"
    ]
    for section in required_sections:
        if section not in content:
            errors.append(f"Missing section: {section}")

    # Check 4: No deprecated patterns
    if re.search(r'workflow\.add_node\("[\w_]+",\s*\w+\(', content):
        errors.append("Found instance-based node pattern (deprecated)")

    # Check 5: Correct execution pattern
    if "workflow.execute(" in content:
        errors.append("Found workflow.execute() (should be runtime.execute())")

    # Check 6: No relative imports in examples
    if re.search(r'from \.\.', content):
        errors.append("Found relative imports (use absolute)")

    # Check 7: Keywords at bottom
    if "<!-- Trigger Keywords:" not in content:
        errors.append("Missing trigger keywords comment")

    # Check 8: .build() in execution examples
    exec_patterns = re.findall(r'runtime\.execute\([^)]+\)', content)
    for pattern in exec_patterns:
        if ".build()" not in pattern:
            errors.append(f"Missing .build() in: {pattern}")

    return errors

if __name__ == "__main__":
    file_path = Path(sys.argv[1])
    errors = validate_skill_file(file_path)

    if errors:
        print(f"❌ VALIDATION FAILED: {file_path}")
        for error in errors:
            print(f"  - {error}")
        sys.exit(1)
    else:
        print(f"✅ VALIDATION PASSED: {file_path}")
        sys.exit(0)
```

**Usage:**
```bash
# Validate single file
python validate_skill.py .claude/skills/01-core-sdk/workflow-quickstart.md

# Validate batch
for file in .claude/skills/01-core-sdk/*.md; do
  python validate_skill.py "$file"
done
```

---

## Section 9: Execution Strategy

### Phase 1: Preparation (1 hour)
1. Create validation script from Section 8
2. Create test extraction script
3. Set up Docker test environment
4. Create batch tracking spreadsheet

### Phase 2: Batch Processing (systematic)
For each batch:
1. **Identify files** in batch
2. **Create branch**: `update/batch-[N]-[category]`
3. **Process files sequentially**:
   - Apply template from Section 2
   - Insert canonical facts from Section 3
   - Validate structure
   - Test code examples
   - Check links
4. **Run quality gates** from Section 6
5. **Commit batch**: Clear commit message
6. **Verify** no other changes affected
7. **Merge to main**

### Phase 3: Validation (continuous)
After each batch:
1. Run full validation suite
2. Check no regressions in other files
3. Verify documentation links still work
4. Test random sample of code examples
5. Update progress tracking

---

## Section 10: Progress Tracking Template

```markdown
# Documentation Update Progress

## Completed Batches

### Batch 1: Core SDK Skills ✅ (14/14 files)
- [x] async-workflow-patterns.md
- [x] connection-patterns.md
- [x] workflow-quickstart.md
- [x] runtime-execution.md
[... rest of files]

**Validation**: ✅ All quality gates passed
**Code Examples**: ✅ All tested and working
**Links**: ✅ All verified

### Batch 2: DataFlow Skills 🔄 (5/25 files)
- [x] dataflow-quickstart.md
- [x] dataflow-models.md
- [ ] dataflow-queries.md
- [ ] dataflow-crud-operations.md
[... rest of files]

**Status**: In progress
**Issues**: None yet

## Quality Metrics

### Overall Progress
- **Total files**: 676
- **Completed**: 25 (3.7%)
- **Remaining**: 651 (96.3%)
- **Current batch**: Batch 2 (DataFlow)

### Validation Results
- **Structure compliance**: 100% (25/25)
- **Code examples tested**: 100% (48/48)
- **Broken links found**: 0
- **Deprecated patterns found**: 0

### Issues Log
| Date | File | Issue | Status |
|------|------|-------|--------|
| - | - | - | - |

## Next Actions
1. Complete Batch 2 (DataFlow Skills)
2. Quality gate validation
3. Merge and start Batch 3 (Nexus Skills)
```

---

## Section 11: Emergency Rollback Procedure

If batch introduces issues:

```bash
# 1. Immediately create new branch from before batch
git checkout main
git checkout -b rollback/batch-[N] [commit-before-batch]

# 2. Identify problematic files
git diff [commit-before-batch]..HEAD --name-only

# 3. Cherry-pick good changes if any
git cherry-pick [commit-hash]

# 4. Force push rollback
git push origin main --force

# 5. Document issue
echo "Batch [N] rolled back due to [reason]" >> ROLLBACK_LOG.md

# 6. Fix issues in new branch
git checkout -b fix/batch-[N]-issues

# 7. Reapply with fixes
[apply updates with corrections]

# 8. Re-validate before merge
python validate_all.py
```

---

## Section 12: Success Criteria

### Per-Batch Success
- [ ] All files have required sections
- [ ] All code examples tested and working
- [ ] All links verified
- [ ] No deprecated patterns
- [ ] Consistent terminology
- [ ] Quality gates passed

### Overall Success
- [ ] 676 files updated
- [ ] 100% structural compliance
- [ ] 100% code examples tested
- [ ] Zero broken links
- [ ] Zero deprecated patterns
- [ ] Consistent technical facts throughout

---

## Appendix A: File Count by Category

```bash
# Count files per directory
.claude/skills/01-core-sdk/          14 files (CRITICAL)
.claude/skills/02-dataflow/          25 files (HIGH)
.claude/skills/03-nexus/             24 files (HIGH)
.claude/skills/04-kaizen/            25 files (MEDIUM)
.claude/skills/05-mcp/               6 files (MEDIUM)
.claude/skills/06-cheatsheets/       35 files (MEDIUM)
.claude/skills/07-development-guides/ 30 files (LOW)
.claude/skills/08-nodes-reference/   10 files (MEDIUM)
.claude/skills/09-workflow-patterns/ 15 files (LOW)
.claude/skills/10-deployment-git/    2 files (LOW)
.claude/skills/11-frontend-integration/ 2 files (LOW)
.claude/skills/12-testing-strategies/ 1 file (MEDIUM)
.claude/skills/13-architecture-decisions/ 5 files (MEDIUM)
.claude/skills/14-code-templates/    7 files (MEDIUM)
.claude/skills/15-error-troubleshooting/ 7 files (CRITICAL) ✅
.claude/skills/16-validation-patterns/ 6 files (HIGH)
.claude/skills/17-gold-standards/    10 files (CRITICAL) ✅

Total: ~224 skill files + 452 other documentation files = 676 total
```

---

## Appendix B: Quick Reference Card

**Print this for quick lookup during updates:**

```
╔════════════════════════════════════════════════════════════════╗
║           SKILL FILE UPDATE QUICK REFERENCE                    ║
╠════════════════════════════════════════════════════════════════╣
║ 1. Add YAML frontmatter (name, description)                    ║
║ 2. Add Skill Metadata block (category, priority, SDK version)  ║
║ 3. Start with Quick Reference section                          ║
║ 4. Show Core Pattern with working code                         ║
║ 5. Include Common Mistakes (❌ Wrong / ✅ Correct)             ║
║ 6. Add Related Patterns section                                ║
║ 7. Add Documentation References section                        ║
║ 8. Add trigger keywords comment at bottom                      ║
║                                                                 ║
║ CRITICAL PATTERNS TO INCLUDE:                                  ║
║ • String-based nodes: "NodeName" not NodeClass()               ║
║ • Always .build(): runtime.execute(workflow.build())           ║
║ • 4-param connections: (from_node, output, to_node, input)     ║
║ • Absolute imports: from kailash.x.y import Z                  ║
║ • LocalRuntime returns: (results, run_id)                      ║
║ • AsyncLocalRuntime returns: results                           ║
║                                                                 ║
║ VALIDATION BEFORE COMMIT:                                      ║
║ ✓ Run python validate_skill.py [file]                          ║
║ ✓ Extract and test code examples                               ║
║ ✓ Verify all links work                                        ║
║ ✓ Check no deprecated patterns                                 ║
║ ✓ Ensure consistent terminology                                ║
╚════════════════════════════════════════════════════════════════╝
```

---

**END OF SYSTEMATIC UPDATE GUIDELINES**

**Next Steps:**
1. Use validation script to check any file
2. Apply templates systematically
3. Use canonical facts for consistency
4. Validate each batch before moving to next
5. Track progress in spreadsheet
6. One mistake = disaster - triple-check everything
