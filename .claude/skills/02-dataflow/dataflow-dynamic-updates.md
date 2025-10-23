# DataFlow Dynamic Updates with PythonCodeNode

**New in Core SDK v0.9.28**: Multi-output PythonCodeNode enables natural, intuitive dynamic update patterns.

## TL;DR

```python
# NEW (Core SDK v0.9.28+): Multi-output pattern
workflow.add_node("PythonCodeNode", "prepare", {
    "code": """
filter_data = {"id": summary_id}
summary_markdown = updated_text
edited_by_user = True
"""
})

workflow.add_node("SummaryUpdateNode", "update", {})
workflow.add_connection("prepare", "filter_data", "update", "filter")
workflow.add_connection("prepare", "summary_markdown", "update", "summary_markdown")
workflow.add_connection("prepare", "edited_by_user", "update", "edited_by_user")
```

## What Changed

**Core SDK v0.9.28** enables PythonCodeNode to export multiple variables without nesting in `result`.

### Before (v0.9.27 and earlier)
```python
# Forced to nest everything in 'result'
result = {
    "filter": {"id": summary_id},
    "fields": {"summary_markdown": updated_text}
}
```

### After (v0.9.28+)
```python
# Natural variable definitions
filter_data = {"id": summary_id}
summary_markdown = updated_text
```

## Full Example

```python
from dataflow import DataFlow
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime import AsyncLocalRuntime

db = DataFlow("postgresql://...")

@db.model
class ConversationSummary:
    id: str
    summary_markdown: str
    topics_json: str
    edited_by_user: bool

# Dynamic update workflow
workflow = WorkflowBuilder()

workflow.add_node("PythonCodeNode", "prepare_update", {
    "code": """
import json

# Prepare filter
filter_data = {"id": summary_id}

# Prepare updated fields with business logic
summary_markdown = generate_markdown(raw_text)
topics_json = json.dumps(extract_topics(raw_text))
edited_by_user = True
"""
})

workflow.add_node("ConversationSummaryUpdateNode", "update", {})

# Clean, direct connections
workflow.add_connection("prepare_update", "filter_data", "update", "filter")
workflow.add_connection("prepare_update", "summary_markdown", "update", "summary_markdown")
workflow.add_connection("prepare_update", "topics_json", "update", "topics_json")
workflow.add_connection("prepare_update", "edited_by_user", "update", "edited_by_user")

runtime = AsyncLocalRuntime()
result = await runtime.execute_workflow_async(workflow.build(), {
    "summary_id": "summary-123",
    "raw_text": "Conversation text..."
})
```

## Backward Compatibility

Old patterns still work 100%:

```python
# This still works fine
result = {"filter": {...}, "fields": {...}}
workflow.add_connection("prepare", "result.filter", "update", "filter")
workflow.add_connection("prepare", "result.fields", "update", "fields")
```

## Benefits

✅ Natural variable naming
✅ Matches developer mental model
✅ Less nesting, cleaner code
✅ Full DataFlow benefits retained (no SQL needed!)

## Requirements

- Core SDK >= v0.9.28
- DataFlow >= v0.6.6

## See Also

- OPTIMAL_SOLUTION_MULTI_OUTPUT.md
- STRATEGIC_SOLUTION_DYNAMIC_UPDATES.md
