---
name: workflow-industry-manufacturing
description: "Manufacturing workflows (production, quality, inventory). Use when asking 'manufacturing workflow', 'production line', 'quality control', or 'inventory management'."
---

# Manufacturing Industry Workflows

> **Skill Metadata**
> Category: `industry-workflows`
> Priority: `MEDIUM`
> SDK Version: `0.9.25+`

## Pattern: Quality Control Workflow

```python
from kailash.workflow.builder import WorkflowBuilder

workflow = WorkflowBuilder()

# 1. Production item check
workflow.add_node("DatabaseQueryNode", "get_item", {
    "query": "SELECT * FROM production_items WHERE batch_id = ?",
    "parameters": ["{{input.batch_id}}"]
})

# 2. Run quality tests
workflow.add_node("APICallNode", "quality_test", {
    "url": "{{sensors.quality_api}}",
    "method": "POST",
    "body": {"item_id": "{{get_item.id}}"}
})

# 3. Evaluate results
workflow.add_node("ConditionalNode", "check_quality", {
    "condition": "{{quality_test.score}} >= 95",
    "true_branch": "approve",
    "false_branch": "reject"
})

# 4. Update inventory
workflow.add_node("DatabaseExecuteNode", "approve", {
    "query": "UPDATE production_items SET status = 'approved', quality_score = ? WHERE id = ?",
    "parameters": ["{{quality_test.score}}", "{{get_item.id}}"]
})

workflow.add_node("DatabaseExecuteNode", "reject", {
    "query": "UPDATE production_items SET status = 'rejected', rejection_reason = ? WHERE id = ?",
    "parameters": ["{{quality_test.failure_reason}}", "{{get_item.id}}"]
})

workflow.add_connection("get_item", "id", "quality_test", "item_id")
workflow.add_connection("quality_test", "score", "check_quality", "condition")
workflow.add_connection("check_quality", "output_true", "approve", "trigger")
workflow.add_connection("check_quality", "output_false", "reject", "trigger")
```

<!-- Trigger Keywords: manufacturing workflow, production line, quality control, inventory management -->
