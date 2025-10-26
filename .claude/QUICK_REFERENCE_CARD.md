# Documentation Update Quick Reference Card

**Print this for quick lookup during updates**

---

## 📋 Required Sections Checklist

Every skill file must have:

```
[ ] YAML frontmatter (name, description)
[ ] # Title
[ ] > **Skill Metadata** block
[ ] ## Quick Reference
[ ] ## Core Pattern
[ ] ## Key Parameters / Options (optional but recommended)
[ ] ## Common Use Cases
[ ] ## Common Mistakes
[ ] ## Related Patterns
[ ] ## When to Escalate to Subagent
[ ] ## Documentation References
[ ] ## Quick Tips (optional but recommended)
[ ] <!-- Trigger Keywords: ... -->
```

---

## 🔑 Critical Patterns (Copy-Paste These)

### String-Based Node API ✅
```python
workflow.add_node("NodeName", "node_id", {"param": "value"})
```

### Execution Pattern ✅
```python
runtime.execute(workflow.build())  # ALWAYS .build()
```

### 4-Parameter Connections ✅
```python
workflow.add_connection(
    "source_node",    # From node ID
    "output_field",   # Output field
    "target_node",    # To node ID
    "input_field"     # Input field
)
```

### Absolute Imports ✅
```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
```

### LocalRuntime Return Value ✅
```python
results, run_id = runtime.execute(workflow.build())
```

### AsyncLocalRuntime Return Value ✅
```python
results = await runtime.execute_workflow_async(workflow.build(), inputs={})
```

---

## ❌ Deprecated Patterns (NEVER USE)

### Instance-Based Nodes ❌
```python
from kailash.nodes import NodeName
workflow.add_node("id", NodeName(param="value"))  # DEPRECATED
```

### Wrong Execution ❌
```python
workflow.execute(runtime)  # WRONG
runtime.execute(workflow)  # Missing .build()
```

### 3-Parameter Connections ❌
```python
workflow.add_connection("source", "target", "field")  # DEPRECATED
```

### Relative Imports ❌
```python
from ..workflow.builder import WorkflowBuilder  # FAILS IN PRODUCTION
```

---

## 📝 Skill Metadata Block Template

```markdown
> **Skill Metadata**
> Category: `category-name`
> Priority: `CRITICAL|HIGH|MEDIUM|LOW`
> SDK Version: `0.9.25+`
> Related Skills: [`skill-name`](path/to/skill.md)
> Related Subagents: `subagent-name` (when to use)
```

**Categories**: `core-sdk`, `dataflow`, `nexus`, `kaizen`, `mcp`, `nodes`, `cheatsheets`, `cross-cutting`, `gold-standards`

---

## 🎯 Quick Reference Section Template

```markdown
## Quick Reference

- **Primary Use**: [One-line description]
- **Import**: `from kailash.x.y import Z`
- **Pattern**: `Pattern() → method() → build()`
- **Execution**: `runtime.execute(workflow.build())`
- **CRITICAL**: [Most important rule]
```

---

## 💻 Core Pattern Section Template

```markdown
## Core Pattern

```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

# Create workflow
workflow = WorkflowBuilder()

# Add nodes (string-based)
workflow.add_node("NodeName", "node_id", {
    "param": "value"
})

# Connect nodes (4 parameters)
workflow.add_connection("source", "output", "target", "input")

# Build and execute
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())
```
```

---

## ❌✅ Common Mistakes Section Template

```markdown
## Common Mistakes

### ❌ Mistake 1: [Description]
```python
# Wrong - [why it's wrong]
[wrong code]
```

### ✅ Fix: [Solution]
```python
# Correct - [why it's correct]
[correct code]
```
```

---

## 📚 Documentation References Template

```markdown
## Documentation References

### Primary Sources
- [`sdk-users/path/to/doc.md`](../../../sdk-users/path/to/doc.md)
- [`CLAUDE.md` (lines 111-177)](../../../CLAUDE.md#L111-L177)

### Related Documentation
- [Topic Guide](path/to/guide.md)

### Advanced References
- `src/module/file.py` - Implementation (XXX lines)
```

**Path Rules**:
- From `.claude/skills/01-core-sdk/` → `../../../sdk-users/`
- From `.claude/skills/02-dataflow/` → `../../../../sdk-users/apps/dataflow/`
- From `.claude/skills/XX-category/` → `../../../sdk-users/`

---

## 🔍 Validation Commands

### Single File
```bash
python .claude/validate_skill.py .claude/skills/01-core-sdk/file.md
```

### Batch Directory
```bash
python .claude/validate_skill.py --batch .claude/skills/01-core-sdk/
```

### Check Deprecated Patterns
```bash
# Should return nothing
grep -r "workflow.execute(" .claude/skills/01-core-sdk/
grep -r "from \.\." .claude/skills/01-core-sdk/
```

---

## 🎨 Canonical BaseRuntime Description

**Copy this EXACTLY for runtime-related files:**

```markdown
## Shared Architecture (Internal)

Both LocalRuntime and AsyncLocalRuntime inherit from BaseRuntime and use shared mixins:

- **BaseRuntime**: Provides 29 configuration parameters, execution metadata, workflow caching
- **ValidationMixin**: Shared validation logic (workflow validation, connection contracts, conditional execution)
- **ParameterHandlingMixin**: Shared parameter resolution (${param} templates, type preservation, deep merge)

This architecture ensures consistent behavior between sync and async runtimes. All existing usage patterns remain unchanged.
```

---

## 📊 Batch Processing Priority

1. ✅ **Batch 4**: Error Troubleshooting (7 files) - COMPLETED
2. ✅ **Batch 5**: Gold Standards (10 files) - COMPLETED
3. **Batch 1**: Core SDK (14 files) - HIGH PRIORITY ← START HERE
4. **Batch 2**: DataFlow (25 files) - HIGH PRIORITY
5. **Batch 3**: Nexus (24 files) - HIGH PRIORITY
6. **Batch 6**: Node References (10 files) - MEDIUM
7. **Batch 7**: Cheatsheets (35 files) - MEDIUM
8. **Batch 8**: Workflow Patterns (15 files) - LOW
9. **Batch 9**: Development Guides (30 files) - LOW
10. **Batch 10**: Other (remaining) - MIXED

---

## 🚦 5 Quality Gates (Before Merging)

```bash
# Gate 1: Structural Validation
grep -q "## Quick Reference" file.md
grep -q "## Core Pattern" file.md
grep -q "## Common Mistakes" file.md

# Gate 2: Technical Accuracy
grep "workflow.execute(" file.md  # Should be empty
grep "from \.\." file.md          # Should be empty

# Gate 3: Code Example Validation
python extract_and_test_examples.py file.md

# Gate 4: Link Validation
python validate_links.py file.md

# Gate 5: Consistency Check
grep "pipeline" file.md  # Should use "workflow"
```

---

## 📝 File Update Workflow

```
1. Read current file
2. Apply template from guidelines Section 2
3. Insert canonical facts from guidelines Section 3
4. Add all required sections
5. Validate: python .claude/validate_skill.py file.md
6. Fix errors
7. Extract and test code examples
8. Verify links work
9. Commit: git add file.md && git commit -m "docs: Update file.md"
10. Repeat for next file
```

---

## 🎯 Current Versions (Always Use These)

```markdown
- **Core SDK**: `0.9.25+`
- **DataFlow**: `0.7.1+`
- **Nexus**: `1.1.1+`
- **Kaizen**: `0.4.0+`
```

---

## 🔗 File Type → Template Mapping

| File Category | Template | Key Focus |
|---------------|----------|-----------|
| 01-core-sdk | Template A | LocalRuntime, WorkflowBuilder |
| 02-dataflow | Template B | 9 nodes, NOT ORM, zero-config |
| 03-nexus | Template C | Multi-channel, .build() |
| 04-kaizen | Template D | BaseAgent, API keys |
| 08-nodes-reference | Template E | Node listings |
| 15-error-troubleshooting | Template F | Error + fix |
| 17-gold-standards | Template G | Standards + violations |

---

## ⚠️ Top 5 Mistakes to Avoid

1. **Missing .build()** in examples
   - Every `runtime.execute()` needs `workflow.build()`

2. **Inconsistent BaseRuntime description**
   - Copy canonical version exactly

3. **Instance-based nodes**
   - Use `"NodeName"` not `NodeName()`

4. **3-parameter connections**
   - Must be 4 parameters: (from_node, output, to_node, input)

5. **Relative imports**
   - Always absolute: `from kailash.x.y import Z`

---

## 💡 Quick Tips

- ✅ **Copy-paste** canonical facts (don't paraphrase)
- ✅ **Validate immediately** after each file update
- ✅ **Test examples** before committing
- ✅ **Check links** are valid
- ✅ **Follow templates** exactly
- ✅ **Process sequentially** (avoid merge conflicts)
- ✅ **Run quality gates** before merging batch
- ✅ **Update progress** after each batch

---

## 📞 Help Resources

- **Main guidelines**: `.claude/SYSTEMATIC_UPDATE_GUIDELINES.md`
- **System overview**: `.claude/DOCUMENTATION_UPDATE_SYSTEM.md`
- **Detailed summary**: `.claude/UPDATE_SUMMARY.md`
- **This card**: `.claude/QUICK_REFERENCE_CARD.md`

---

## 🎓 Remember

**"One mistake = disaster"**

Quality > Speed | Triple-check everything | Validate before commit

---

**Print this card and keep it next to you while updating files**

**Key**: Follow templates → Use canonical facts → Validate everything → Test examples
