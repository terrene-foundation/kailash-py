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
from kailash import Workflow
from kailash.nodes.alerts import DiscordAlertNode

workflow = Workflow(name="simple_alert")

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
alert = workflow.add_node(
    DiscordAlertNode(
        id="error_alert",
        webhook_url="${DISCORD_WEBHOOK}"
    )
)

results = workflow.run(
    error_alert={
        "title": "Processing Error",
        "message": "Failed to process customer data",
        "alert_type": "error",
        "context": {
            "File": "customers.csv",
            "Line": 42,
            "Error": "Invalid date format",
            "Time": "2024-01-15 10:30:00"
        }
    }
)
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
alert = workflow.add_node(
    DiscordAlertNode(
        id="metrics_alert",
        webhook_url="${DISCORD_WEBHOOK}",
        username="Metrics Bot",
        embed=True,
        footer_text="Updated every 5 minutes"
    )
)

results = workflow.run(
    metrics_alert={
        "title": "System Metrics",
        "alert_type": "info",
        "fields": [
            {"name": "CPU Usage", "value": "67%", "inline": True},
            {"name": "Memory", "value": "4.2GB / 8GB", "inline": True},
            {"name": "Active Users", "value": "1,234", "inline": True},
            {"name": "Response Time", "value": "125ms avg", "inline": False}
        ]
    }
)
```

### Mentions and Notifications

```python
alert = workflow.add_node(
    DiscordAlertNode(
        id="critical_alert",
        webhook_url="${DISCORD_WEBHOOK}"
    )
)

results = workflow.run(
    critical_alert={
        "title": "Database Connection Lost",
        "message": "Primary database is unreachable",
        "alert_type": "critical",
        "mentions": ["@everyone"],  # Notify everyone
        "context": {
            "Database": "prod-db-01",
            "Last Seen": "10:45:00",
            "Attempts": 5
        }
    }
)
```

### Thread Posting

```python
alert = workflow.add_node(
    DiscordAlertNode(
        id="thread_update",
        webhook_url="${DISCORD_WEBHOOK}",
        thread_id="1234567890123456789"  # Discord thread ID
    )
)

results = workflow.run(
    thread_update={
        "title": "Bug Fix Update",
        "message": "Issue has been resolved in latest commit",
        "alert_type": "success"
    }
)
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
workflow.connect(processor, switch)
workflow.connect(
    switch,
    error_alert,
    output_key="error",
    mapping={"outputs.error": "input"}
)
```

### Scheduled Status Reports

```python
# Generate daily report
report_gen = workflow.add_node(
    PythonCodeNode.from_function(
        id="generate_report",
        func=lambda: {
            "title": "Daily Status Report",
            "alert_type": "info",
            "context": {
                "Date": datetime.now().strftime("%Y-%m-%d"),
                "Uptime": "99.9%",
                "Requests": "45,231",
                "Errors": "12"
            }
        }
    )
)

# Send report
alert = workflow.add_node(
    DiscordAlertNode(
        id="daily_report",
        webhook_url="${DISCORD_WEBHOOK}",
        username="Report Bot"
    )
)

workflow.connect(report_gen, alert, mapping={"output": "input"})
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
# Send multiple alerts - rate limiting applied automatically
for i in range(50):
    alert = workflow.add_node(
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
