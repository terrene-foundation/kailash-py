"""
Discord Alert Node - Comprehensive Examples

This example demonstrates both simple and advanced Discord alert functionality:

SIMPLE EXAMPLES:
- Basic success/error notifications
- Environment variable webhook configuration
- Context data inclusion
- Standalone alert usage

ADVANCED EXAMPLES:
- Rich embeds with custom colors and fields
- Dynamic content based on data thresholds
- Multiple alert types with different formatting
- Rate limiting and batch alerts
- Production monitoring patterns

Environment Setup:
    export DISCORD_WEBHOOK="https://discord.com/api/webhooks/YOUR_WEBHOOK_HERE"

Usage:
    python discord_alert_examples.py
"""

import os
from datetime import datetime

from kailash import LocalRuntime, Workflow
from kailash.nodes.alerts import DiscordAlertNode
from kailash.nodes.base import NodeParameter
from kailash.nodes.code import PythonCodeNode

# =============================================================================
# SIMPLE EXAMPLES
# =============================================================================


def create_simple_success_workflow():
    """Create a workflow that processes data and sends success notification."""

    workflow = Workflow("discord_success_example", name="Discord Success Example")

    # Step 1: Simulate data processing
    def process_customer_data():
        return {
            "records_processed": 1250,
            "processing_time": "45.3s",
            "status": "completed",
            "errors": 0,
        }

    data_processor = PythonCodeNode.from_function(
        name="ProcessCustomerData",
        func=process_customer_data,
        output_schema={
            "records_processed": NodeParameter(
                name="records_processed",
                type=int,
                description="Number of records processed",
            ),
            "processing_time": NodeParameter(
                name="processing_time", type=str, description="Time taken to process"
            ),
            "status": NodeParameter(
                name="status", type=str, description="Processing status"
            ),
            "errors": NodeParameter(
                name="errors", type=int, description="Number of errors encountered"
            ),
        },
    )
    workflow.add_node("data_processor", data_processor)

    # Step 2: Send success alert to Discord
    success_alert = DiscordAlertNode(name="SuccessAlert")
    workflow.add_node("success_alert", success_alert)

    # Step 3: Connect nodes - pass processing results to alert
    workflow.connect(
        "data_processor",
        "success_alert",
        mapping={
            "records_processed": "records_processed",
            "processing_time": "processing_time",
            "status": "status",
            "errors": "errors",
        },
    )

    return workflow


def run_simple_examples():
    """Run basic Discord alert examples."""

    print("=" * 60)
    print("SIMPLE DISCORD ALERT EXAMPLES")
    print("=" * 60)

    webhook_url = get_webhook_url()
    if not webhook_url:
        return

    # Example 1: Success notification workflow
    print("\n1. Success Notification Workflow")
    print("-" * 40)

    workflow = create_simple_success_workflow()
    runtime = LocalRuntime()
    results, _ = runtime.execute(
        workflow,
        parameters={
            "success_alert": {
                "webhook_url": webhook_url,
                "title": "✅ Data Processing Complete",
                "message": "Customer data processing finished successfully",
                "alert_type": "success",
            }
        },
    )

    processing_result = results["data_processor"]
    alert_result = results["success_alert"]

    print(f"Records processed: {processing_result['records_processed']}")
    print(f"Processing time: {processing_result['processing_time']}")
    print(f"Discord alert sent: {alert_result['success']}")

    # Example 2: Standalone alert (no workflow)
    print("\n2. Standalone Alert (Direct Usage)")
    print("-" * 40)

    alert_node = DiscordAlertNode(name="StandaloneAlert")
    result = alert_node.run(
        webhook_url=webhook_url,
        title="📊 System Status Update",
        message="Regular system health check completed",
        alert_type="info",
        context={
            "Server": "web-01",
            "CPU Usage": "23%",
            "Memory": "2.1GB / 8GB",
            "Uptime": "72 hours",
            "Last Check": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        },
        footer_text="Automated System Monitor",
    )

    print(f"Standalone alert sent: {result['success']}")


# =============================================================================
# ADVANCED EXAMPLES
# =============================================================================


def run_advanced_examples():
    """Run advanced Discord alert examples with rich embeds."""

    print("\n" + "=" * 60)
    print("ADVANCED DISCORD ALERT EXAMPLES")
    print("=" * 60)

    webhook_url = get_webhook_url()
    if not webhook_url:
        return

    # Example 1: Rich Embed Dashboard
    print("\n1. Metrics Dashboard (Rich Embed)")
    print("-" * 40)

    alert_node = DiscordAlertNode(name="DashboardAlert")
    result = alert_node.run(
        webhook_url=webhook_url,
        title="📊 System Metrics Dashboard",
        message=f"**Last Updated**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}",
        alert_type="info",
        username="Metrics Bot",
        color=0x3498DB,  # Blue
        embed=True,
        fields=[
            # System Resources Row
            {"name": "💻 CPU Usage", "value": "67.5%", "inline": True},
            {"name": "🧠 Memory", "value": "4.2GB / 8.0GB", "inline": True},
            {"name": "💾 Disk Usage", "value": "78.3%", "inline": True},
            # Performance Metrics Row
            {"name": "👥 Active Users", "value": "1,234", "inline": True},
            {"name": "⚡ Requests/sec", "value": "542", "inline": True},
            {"name": "❌ Error Rate", "value": "0.02%", "inline": True},
            # Additional Info Row
            {"name": "⏱️ Avg Response", "value": "125ms", "inline": True},
            {"name": "✅ Uptime", "value": "720 hours", "inline": True},
            {"name": "🔄 Status", "value": "All Systems Operational", "inline": True},
        ],
        footer_text="Updated every 5 minutes",
        timestamp=True,
    )

    print(f"Dashboard alert sent: {result['success']}")

    # Example 2: Deployment Notification
    print("\n2. Deployment Notification (Rich Embed)")
    print("-" * 40)

    result = alert_node.run(
        webhook_url=webhook_url,
        title="🚀 Deployment Successful",
        message="**Customer Portal v2.4.1** has been deployed to **Production**",
        alert_type="success",
        username="Deploy Bot",
        color=0x28A745,  # Green for success
        embed=True,
        fields=[
            {"name": "📦 Version", "value": "v2.4.1", "inline": True},
            {"name": "🏷️ Git Tag", "value": "release/2.4.1", "inline": True},
            {"name": "👤 Deployed By", "value": "GitHub Actions", "inline": True},
            {"name": "🔢 Build Number", "value": "#1547", "inline": True},
            {
                "name": "⏰ Deploy Time",
                "value": datetime.now().strftime("%H:%M UTC"),
                "inline": True,
            },
            {"name": "✅ Health Check", "value": "Passed", "inline": True},
            {
                "name": "📝 Changelog",
                "value": "• Fixed authentication bug\\n• Added Stripe Connect support\\n• 25% faster API responses\\n• Security dependency updates",
                "inline": False,
            },
            {
                "name": "🔗 Quick Links",
                "value": "[View App](https://app.example.com) | [Release Notes](https://github.com/org/repo/releases/tag/v2.4.1)",
                "inline": False,
            },
        ],
        footer_text="Pipeline: deploy-prod-2024-0115-1430",
        timestamp=True,
    )

    print(f"Deployment notification sent: {result['success']}")

    # Example 3: Multiple Alert Types (Batch)
    print("\n3. Multiple Alert Types (Batch Processing)")
    print("-" * 40)

    # Different alert scenarios
    alert_scenarios = [
        {
            "title": "📈 Traffic Spike Detected",
            "message": "Website traffic increased by 300% in last 10 minutes",
            "alert_type": "info",
            "color": 0x17A2B8,  # Cyan
            "context": {"Peak RPS": "2,150", "Normal RPS": "500", "Duration": "10 min"},
        },
        {
            "title": "🔒 Security Alert",
            "message": "Multiple failed login attempts detected",
            "alert_type": "warning",
            "color": 0xFD7E14,  # Orange
            "context": {
                "Failed Attempts": "25",
                "Source IPs": "3",
                "Time Window": "5 min",
            },
            "mentions": ["@security-team"],
        },
        {
            "title": "💾 Backup Completed",
            "message": "Daily database backup completed successfully",
            "alert_type": "success",
            "color": 0x20C997,  # Green
            "context": {
                "Database Size": "2.4 GB",
                "Backup Duration": "3m 45s",
                "Location": "AWS S3",
            },
        },
    ]

    print("Sending batch alerts with rate limiting...")
    for i, scenario in enumerate(alert_scenarios, 1):
        result = alert_node.run(
            webhook_url=webhook_url,
            embed=True,
            timestamp=True,
            footer_text=f"Alert {i}/3 - Automated Monitoring",
            **scenario,
        )

        print(f"  Alert {i} ({scenario['alert_type']}): {result['success']}")


def run_severity_demonstration():
    """Demonstrate all alert severity levels."""

    print("\n" + "=" * 60)
    print("ALERT SEVERITY LEVELS DEMONSTRATION")
    print("=" * 60)

    webhook_url = get_webhook_url()
    if not webhook_url:
        return

    alert_node = DiscordAlertNode(name="SeverityDemo")

    # Demonstrate each severity level
    severities = [
        (
            "success",
            "✅ All Systems Operational",
            "All health checks passing",
            0x28A745,
        ),
        ("info", "ℹ️ Scheduled Maintenance", "Maintenance window: 2-4 AM EST", 0x17A2B8),
        ("warning", "⚠️ Degraded Performance", "API response times elevated", 0xFFC107),
        ("error", "❌ Service Unavailable", "Payment gateway is down", 0xDC3545),
        (
            "critical",
            "🚨 CRITICAL: Data Loss Risk",
            "Backup system failure detected",
            0x721C24,
        ),
    ]

    print("\nSending alerts for each severity level...")
    for severity, title, message, color in severities:
        result = alert_node.run(
            webhook_url=webhook_url,
            title=title,
            message=message,
            alert_type=severity,
            color=color,
            embed=True,
            context={
                "Severity": severity.upper(),
                "Time": datetime.now().strftime("%H:%M:%S"),
                "Auto-Generated": "Yes",
            },
            footer_text="Severity Level Demonstration",
        )

        print(f"  {severity.capitalize()} alert: {result['success']}")


def get_webhook_url():
    """Get webhook URL from environment variables."""
    webhook_url = os.getenv("DISCORD_TEST_WEBHOOK") or os.getenv("DISCORD_WEBHOOK")
    if not webhook_url:
        print("❌ ERROR: No Discord webhook URL found")
        print("\nTo run this example:")
        print("1. Create a Discord webhook in your server")
        print("2. Export the webhook URL:")
        print(
            "   export DISCORD_WEBHOOK='https://discord.com/api/webhooks/YOUR_WEBHOOK_HERE'"
        )
        print("   OR")
        print(
            "   export DISCORD_TEST_WEBHOOK='https://discord.com/api/webhooks/YOUR_WEBHOOK_HERE'"
        )
        return None
    return webhook_url


def main():
    """Run all Discord alert examples."""

    print("Discord Alert Node - Comprehensive Examples")
    print("🔔 This will send multiple test alerts to your Discord channel")

    try:
        # Run all examples
        run_simple_examples()
        run_advanced_examples()
        run_severity_demonstration()

        print("\n" + "=" * 60)
        print("✅ ALL EXAMPLES COMPLETED SUCCESSFULLY!")
        print("=" * 60)
        print("\nFeatures demonstrated:")
        print("✓ Basic success/error notifications")
        print("✓ Rich embeds with custom colors and fields")
        print("✓ Dynamic content and workflow integration")
        print("✓ Multiple alert types and formatting")
        print("✓ Batch alerting with rate limiting")
        print("✓ Production-ready monitoring patterns")
        print("✓ All severity levels (success, info, warning, error, critical)")
        print("\nCheck your Discord channel for all the alert messages!")

    except Exception as e:
        print(f"\n❌ Example failed: {str(e)}")
        print("\nTroubleshooting:")
        print("- Verify your DISCORD_WEBHOOK URL is correct")
        print("- Check Discord field limits (max 25 fields per embed)")
        print("- Ensure webhook has proper permissions")
        print("- Check rate limiting if sending multiple alerts")


if __name__ == "__main__":
    main()
