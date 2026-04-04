---
name: dataflow-compliance
description: "GDPR compliance patterns in DataFlow. Use when asking 'GDPR dataflow', 'data compliance', or 'right to be forgotten'."
---

# DataFlow GDPR Compliance

> **Skill Metadata**
> Category: `dataflow`
> Priority: `MEDIUM`
> SDK Version: `0.9.25+`

## GDPR Delete (Right to be Forgotten)

```python
from dataflow import DataFlow
from kailash.workflow.builder import WorkflowBuilder

db = DataFlow("postgresql://localhost/app")

@db.model
class User:
    id: str
    email: str
    gdpr_deleted: bool = False

# GDPR deletion workflow
workflow = WorkflowBuilder()

# 1. Mark as deleted (soft delete)
workflow.add_node("UserUpdateNode", "mark_deleted", {
    "id": "{{input.user_id}}",
    "gdpr_deleted": True,
    "email": "[REDACTED]"
})

# 2. Anonymize related data
workflow.add_node("SQLDatabaseNode", "anonymize_logs", {
    "query": "UPDATE audit_logs SET user_email = '[REDACTED]' WHERE user_id = ?",
    "parameters": ["{{input.user_id}}"]
})

# 3. Delete from external systems
workflow.add_node("HTTPRequestNode", "delete_external", {
    "url": "https://analytics.example.com/users/{{input.user_id}}",
    "method": "DELETE"
})

workflow.add_connection("mark_deleted", "result", "anonymize_logs", "user_id")
workflow.add_connection("anonymize_logs", "result", "delete_external", "trigger")
```

## Documentation

<!-- Trigger Keywords: GDPR dataflow, data compliance, right to be forgotten, data privacy -->
