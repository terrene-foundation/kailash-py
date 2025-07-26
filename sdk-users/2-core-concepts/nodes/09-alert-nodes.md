# Alert Nodes - Kailash SDK

Alert nodes provide purpose-built interfaces for sending notifications through various channels. These nodes abstract the complexity of different notification APIs while providing consistent interfaces and built-in best practices.

## Overview

Alert nodes are designed to make it easy to add notifications to your workflows without dealing with:
- Complex webhook payload formatting
- Rate limiting and retry logic
- Authentication and security
- Channel-specific formatting requirements

## Available Alert Nodes

### DiscordAlertNode

Send rich notifications to Discord channels using webhooks.

**Key Features:**
- Simple text messages or rich embeds
- Automatic color coding based on alert severity
- User/role mentions with proper formatting
- Thread support for organized discussions
- Built-in rate limiting (30 requests/minute)
- Retry logic with exponential backoff

**Parameters:**
```python
# Common alert parameters (inherited from AlertNode)
alert_type: str = "info"  # success, warning, error, critical, info
title: str  # Required - Alert title
message: str = ""  # Alert message body
context: dict = {}  # Additional context data

# Discord-specific parameters
webhook_url: str  # Required - Discord webhook URL (supports ${ENV_VAR})
username: str = None  # Override webhook bot username
avatar_url: str = None  # Override webhook bot avatar
embed: bool = True  # Send as rich embed or plain text
color: int = None  # Override embed color (decimal)
fields: list = []  # Additional embed fields
mentions: list = []  # User/role mentions
thread_id: str = None  # Thread ID to post in
footer_text: str = None  # Footer text for embeds
timestamp: bool = True  # Include timestamp

```

## Basic Usage

### Simple Discord Alert

```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.nodes.alerts import DiscordAlertNode

workflow = WorkflowBuilder()

alert = workflow.add_node(
    DiscordAlertNode(
        id="discord_alert",
        webhook_url="${DISCORD_WEBHOOK}"  # From environment variable
    )
)

results = workflow.run(
    discord_alert={
        "title": "Deployment Complete",
        "message": "Version 1.2.3 deployed successfully",
        "alert_type": "success"
    }
)

```

### Alert with Context Data

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

workflow = WorkflowBuilder()
workflow.add_node(
    DiscordAlertNode(
        id="error_alert",
        webhook_url="${DISCORD_WEBHOOK}"
    )
)

workflow = WorkflowBuilder()
# Workflow setup goes here  # Method signature

```

## Alert Severity Levels

Alert nodes support five standard severity levels, each with associated colors:

| Severity | Color | Use Case |
|----------|-------|----------|
| `success` | Green (#28A745) | Successful operations, completions |
| `warning` | Yellow (#FFC107) | Non-critical issues, warnings |
| `error` | Red (#DC3545) | Errors, failures |
| `critical` | Dark Red (#8B0000) | Critical failures requiring immediate attention |
| `info` | Blue (#007BFF) | General information, status updates |

## Advanced Features

### Rich Embeds with Custom Fields

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

workflow = WorkflowBuilder()
workflow.add_node(
    DiscordAlertNode(
        id="metrics_alert",
        webhook_url="${DISCORD_WEBHOOK}",
        username="Metrics Bot",
        embed=True,
        footer_text="Updated every 5 minutes"
    )
)

workflow = WorkflowBuilder()
# Workflow setup goes here  # Method signature

```

### Mentions and Notifications

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

workflow = WorkflowBuilder()
workflow.add_node(
    DiscordAlertNode(
        id="critical_alert",
        webhook_url="${DISCORD_WEBHOOK}"
    )
)

workflow = WorkflowBuilder()
# Workflow setup goes here  # Method signature

```

### Thread Posting

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

workflow = WorkflowBuilder()
workflow.add_node(
    DiscordAlertNode(
        id="thread_update",
        webhook_url="${DISCORD_WEBHOOK}",
        thread_id="1234567890123456789"  # Discord thread ID
    )
)

workflow = WorkflowBuilder()
# Workflow setup goes here  # Method signature

```

## Integration Patterns

### Error Handling in Workflows

```python
from kailash.nodes.logic import SwitchNode
from kailash.nodes.code import PythonCodeNode

# Process data with error handling
processor = workflow.add_node(
    PythonCodeNode.from_function(
        id="process",
        func=lambda data: {
            "status": "error" if data.get("invalid") else "success",
            "message": "Processing failed" if data.get("invalid") else "Success"
        }
    )
)

# Switch based on status
switch = workflow.add_node(
    SwitchNode(id="check_status", switch_on="status")
)

# Error alert
error_alert = workflow.add_node(
    DiscordAlertNode(
        id="error_alert",
        webhook_url="${DISCORD_WEBHOOK}",
        mentions=["@here"]
    )
)

# Connect error path
workflow.add_connection(processor, "result", switch, "input")
workflow.add_connection(switch, "result", error_alert, "input")

```

### Scheduled Status Reports

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

# Generate daily report
workflow = WorkflowBuilder()
# Workflow setup goes here  # Method signature.strftime("%Y-%m-%d"),
                "Uptime": "99.9%",
                "Requests": "45,231",
                "Errors": "12"
            }
        }
    )
)

# Send report
workflow = WorkflowBuilder()
workflow.add_node(
    DiscordAlertNode(
        id="daily_report",
        webhook_url="${DISCORD_WEBHOOK}",
        username="Report Bot"
    )
)

workflow = WorkflowBuilder()
# Workflow setup goes here  # Method signature

```

## Security Best Practices

### Webhook URL Management

1. **Never hardcode webhook URLs** in your code
2. **Use environment variables** for webhook URLs:
   ```bash
   export DISCORD_WEBHOOK="https://discord.com/api/webhooks/..."
   ```
3. **Use configuration management** for different environments:
   ```python
   webhook_url = os.getenv(f"DISCORD_{ENVIRONMENT}_WEBHOOK")

   ```

### Sensitive Data

- Be careful about what data you include in alerts
- Avoid sending passwords, API keys, or PII
- Use context fields for structured data that can be filtered

## Rate Limiting

Discord webhooks are limited to 30 requests per minute. The DiscordAlertNode handles this automatically:

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

# Send multiple alerts - rate limiting applied automatically
for i in range(50):
workflow = WorkflowBuilder()
workflow.add_node(
        DiscordAlertNode(
            id=f"alert_{i}",
            webhook_url="${DISCORD_WEBHOOK}"
        )
    )

```

## Error Handling

Alert nodes include automatic retry logic:
- 3 retry attempts with exponential backoff
- Handles rate limit responses (429)
- Provides detailed error messages

```python
try:
    results = workflow.run(discord_alert={...})
    if results['discord_alert']['success']:
        print("Alert sent successfully")
except NodeExecutionError as e:
    print(f"Failed to send alert: {e}")

```

## Upcoming Alert Nodes

Future alert nodes planned for the SDK:

- **SlackAlertNode**: Slack webhook/API integration
- **EmailAlertNode**: SMTP email notifications
- **WebhookAlertNode**: Generic webhook support
- **PagerDutyAlertNode**: Incident management integration
- **TeamsAlertNode**: Microsoft Teams notifications

## Best Practices

1. **Use appropriate severity levels** - Don't cry wolf with critical alerts
2. **Include relevant context** - Make alerts actionable
3. **Set up alert channels** - Different channels for different severities
4. **Test your alerts** - Ensure they work before you need them
5. **Document alert meanings** - Help your team understand what each alert means
6. **Avoid alert fatigue** - Only alert on actionable items

## Examples

For complete examples, see:
- `examples/node_examples/alerts/discord_basic.py` - Basic Discord alerts
- `examples/node_examples/alerts/discord_rich_embed.py` - Advanced formatting
- `examples/feature_examples/workflows/alert_on_error.py` - Error handling patterns
