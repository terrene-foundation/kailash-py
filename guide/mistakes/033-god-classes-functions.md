# Mistake #033: God Classes/Functions

## Problem
Classes or functions doing too many things.

### Bad Example
```python
# BAD - God class
class WorkflowManager:
    def parse_config(self): pass
    def validate_nodes(self): pass
    def execute_workflow(self): pass
    def generate_reports(self): pass
    def send_notifications(self): pass
    # ... 20 more methods

# GOOD - Single responsibility
class WorkflowExecutor:
    def execute_workflow(self): pass

class ReportGenerator:
    def generate_reports(self): pass

class NotificationService:
    def send_notifications(self): pass

```

## Solution


## Lesson Learned
Follow single responsibility principle.

---
