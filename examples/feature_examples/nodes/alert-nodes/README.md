# Alert Nodes Feature Examples

This directory contains feature tests and examples for alert nodes in the Kailash SDK.

## Discord Alert Examples

### File: `discord_alert_examples.py`

A comprehensive example demonstrating both simple and advanced Discord alert functionality.

**Features Covered:**

#### Simple Examples
- ✅ Basic success/error notifications
- ✅ Environment variable webhook configuration
- ✅ Context data inclusion
- ✅ Standalone alert usage (no workflow required)

#### Advanced Examples
- ✅ Rich embeds with custom colors and fields
- ✅ Metrics dashboard with structured data
- ✅ Deployment notifications with changelog
- ✅ Batch alerting with rate limiting
- ✅ All severity levels (success, info, warning, error, critical)

**Setup Required:**
```bash
export DISCORD_WEBHOOK="https://discord.com/api/webhooks/YOUR_WEBHOOK_HERE"
```

**Usage:**
```bash
python discord_alert_examples.py
```

## Discord Alert Node Features

The `DiscordAlertNode` provides enterprise-grade Discord integration with:

- **Rich Embeds**: Custom colors, fields, footers, timestamps
- **Rate Limiting**: Built-in 30 requests/minute sliding window
- **Retry Logic**: Exponential backoff with 3 attempts
- **Security**: Environment variable webhook URLs
- **Mentions**: User/role mentions with proper formatting
- **Context Data**: Automatic formatting as embed fields
- **Multiple Formats**: Plain text and rich embed modes
- **Production Ready**: Error handling, validation, logging

## Integration Patterns

### Workflow Integration
```python
from kailash import create_workflow
from kailash.nodes.alerts import DiscordAlertNode

workflow = create_workflow("monitoring")
alert = DiscordAlertNode(name="StatusAlert")
workflow.add_node(alert)

# Connect to data processing nodes
workflow.add_edge(processor, alert, mapping={
    "result": "context"
})
```

### Standalone Usage
```python
from kailash.nodes.alerts import DiscordAlertNode

alert = DiscordAlertNode(name="DirectAlert")
result = alert.run(
    webhook_url="${DISCORD_WEBHOOK}",
    title="System Alert",
    message="Status update",
    alert_type="info"
)
```

### Environment Variables
Always use environment variables for webhook URLs:
```python
# ✅ Secure - uses environment variable
webhook_url="${DISCORD_WEBHOOK}"

# ❌ Insecure - hardcoded webhook
webhook_url="https://discord.com/api/webhooks/..."
```

## Alert Severity Levels

| Level | Color | Use Case |
|-------|--------|----------|
| `success` | Green | Successful operations, completions |
| `info` | Blue | Status updates, informational |
| `warning` | Orange | Degraded performance, thresholds |
| `error` | Red | Service failures, errors |
| `critical` | Dark Red | Critical system failures, data loss |

## Production Considerations

1. **Rate Limiting**: Discord allows 30 requests/minute per webhook
2. **Embed Limits**: Maximum 25 fields per embed, 6000 characters total
3. **Mentions**: Use `@here` instead of `@everyone` to reduce noise
4. **Error Handling**: Always check the `success` field in results
5. **Webhook Security**: Rotate webhook URLs regularly
6. **Context Size**: Limit context data to essential information

## Troubleshooting

Common issues and solutions:

- **Webhook not found (404)**: Verify webhook URL is correct and active
- **Rate limited (429)**: Built-in rate limiting handles this automatically
- **Embed too large**: Reduce field count or content length
- **Mentions not working**: Check user/role IDs are correct
- **No alerts received**: Verify Discord channel permissions

## Related Documentation

- [Alert Nodes User Guide](../../../../sdk-users/nodes/09-alert-nodes.md)
- [Discord API Documentation](https://discord.com/developers/docs/resources/webhook)
- [Comprehensive Node Catalog](../../../../sdk-users/nodes/comprehensive-node-catalog.md)
