# Monitoring Workflows

This directory contains comprehensive monitoring and health check workflow patterns using the Kailash SDK.

## Overview

Monitoring workflows provide real-time health checks, system monitoring, and alerting capabilities for enterprise infrastructure. These patterns use real endpoints and services rather than simulated data, making them production-ready for immediate deployment.

## Core Pattern: Health Check Monitoring

The health check monitor workflow demonstrates how to:
- **Monitor real services** using HTTPRequestNode against actual endpoints
- **Check multiple service types** (HTTP, database, file system)
- **Generate alerts** based on configurable thresholds
- **Create comprehensive reports** with health scores and recommendations

### Key Features

✅ **Real Service Monitoring** - Monitors actual HTTP endpoints and services
✅ **Docker Integration** - Works with Docker Compose infrastructure
✅ **Multi-Check Types** - HTTP, database, file system, and custom checks
✅ **Alerting Logic** - Configurable thresholds and notification rules
✅ **Comprehensive Reporting** - Health scores, trends, and recommendations

## Available Scripts

### `scripts/health_check_monitor.py`

**Purpose**: Comprehensive multi-service health monitoring system

**What it does**:
1. Monitors HTTP endpoints (APIs, web services, health checks)
2. Performs database connectivity checks via HTTP health endpoints
3. Monitors file system health and disk usage
4. Generates alerts based on configurable rules
5. Creates comprehensive health dashboard and reports

**Usage**:
```bash
# Run with Docker services
docker-compose -f docker/docker-compose.sdk-dev.yml up -d

# Run the health monitor
python sdk-users/workflows/by-pattern/monitoring/scripts/health_check_monitor.py

# The script will:
# - Check all configured service endpoints
# - Test database connectivity
# - Monitor system resources
# - Generate health report in /data/outputs/monitoring/
```

**Monitored Services**:
- HTTP health endpoints (JSONPlaceholder API, GitHub API)
- Docker PostgreSQL database (via health check endpoint)
- Docker MongoDB service (via health check endpoint)
- Local file system and disk usage

**Output**:
- Individual service health status
- Overall system health score
- Alert notifications for failing services
- Comprehensive monitoring report with recommendations

## Node Usage Patterns

### HTTP Health Checks
```python
# Monitor HTTP API endpoints
api_health_check = HTTPRequestNode(
    name="api_health_check",
    method="GET",
    url="https://jsonplaceholder.typicode.com/posts/1",
    timeout=10.0
)

# Monitor service health endpoints
service_health_check = HTTPRequestNode(
    name="service_health_check",
    method="GET",
    url="http://localhost:8080/health",
    expected_status=200
)

```

### Database Connectivity Monitoring
```python
# Check database health via HTTP endpoint
db_health_check = HTTPRequestNode(
    name="database_health",
    method="GET",
    url="http://localhost:5432/health",  # PostgreSQL health check
    timeout=5.0
)

```

### Alert Integration with Discord
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

# Real-time Discord alerts for critical issues
critical_alert = DiscordAlertNode(
    name="critical_alert",
    webhook_url="${DISCORD_WEBHOOK}",
    alert_type="critical",
    title="🚨 Critical Service Failure",
    mentions=["@everyone"]
)

# System health dashboard updates
health_dashboard = DiscordAlertNode(
    name="health_dashboard",
    webhook_url="${DISCORD_WEBHOOK}",
    alert_type="info",
    title="📊 System Health Report",
    username="Health Monitor",
    footer_text="Updated every 5 minutes"
)

```

### Results Analysis and Alerting
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

# Analyze health check results and generate alerts
health_analyzer = PythonCodeNode.from_function(
    func=analyze_health_results,
    name="health_analyzer"
)

# Generate monitoring report
report_generator = PythonCodeNode.from_function(
    func=generate_monitoring_report,
    name="report_generator"
)

```

## Monitoring Strategies

### Service Health Monitoring
```python
def check_service_health(response_data):
    """Analyze HTTP response for service health"""
    if response_data.get("status_code") == 200:
        response_time = response_data.get("response_time", 0)
        if response_time < 1.0:  # Fast response
            return {"status": "healthy", "score": 100}
        elif response_time < 5.0:  # Acceptable response
            return {"status": "warning", "score": 75}
        else:  # Slow response
            return {"status": "critical", "score": 25}
    else:
        return {"status": "down", "score": 0}

```

### Alert Generation
```python
def generate_alerts(health_results):
    """Generate alerts based on health check results"""
    alerts = []
    for service, result in health_results.items():
        if result["score"] < 50:
            alerts.append({
                "service": service,
                "severity": "critical" if result["score"] == 0 else "warning",
                "message": f"Service {service} health score: {result['score']}"
            })
    return alerts

```

## Integration with Enterprise Systems

### Infrastructure Monitoring
- **Kubernetes**: Monitor pod health and service endpoints
- **Docker Swarm**: Check service availability and load balancer health
- **Cloud Services**: Monitor AWS/Azure/GCP service endpoints

### APM Integration
- **New Relic**: Export health metrics to APM platforms
- **Datadog**: Send monitoring data to external dashboards
- **Prometheus**: Expose metrics in Prometheus format

### Alerting Systems
- **PagerDuty**: Trigger incidents for critical service failures
- **Slack/Teams**: Send notifications to communication channels
- **Email**: Send detailed health reports to operations teams

## Monitoring Configuration

### Service Definitions
```python
MONITORED_SERVICES = {
    "api_services": [
        {"name": "JSONPlaceholder", "url": "https://jsonplaceholder.typicode.com/posts/1"},
        {"name": "GitHub API", "url": "https://api.github.com/zen"}
    ],
    "databases": [
        {"name": "PostgreSQL", "url": "http://localhost:5432/health"},
        {"name": "MongoDB", "url": "http://localhost:27017/health"}
    ],
    "internal_services": [
        {"name": "Mock API", "url": "http://localhost:8888/health"}
    ]
}

```

### Alert Thresholds
```python
ALERT_THRESHOLDS = {
    "response_time": {
        "warning": 2.0,   # seconds
        "critical": 5.0   # seconds
    },
    "health_score": {
        "warning": 75,    # percentage
        "critical": 50    # percentage
    },
    "availability": {
        "warning": 95,    # percentage
        "critical": 90    # percentage
    }
}

```

## Best Practices

### Monitoring Frequency
- **Critical Services**: Every 30 seconds
- **Important Services**: Every 1-2 minutes
- **Supporting Services**: Every 5 minutes
- **Background Services**: Every 15 minutes

### Error Handling
- Implement retry logic for transient failures
- Set appropriate timeouts for different service types
- Log all monitoring attempts and results
- Gracefully handle network connectivity issues

### Performance Optimization
- Run health checks in parallel when possible
- Cache results for frequently checked endpoints
- Use connection pooling for HTTP requests
- Implement circuit breaker patterns for failing services

## Common Use Cases

### Infrastructure Monitoring
- **Web Services**: Monitor API endpoints and web applications
- **Databases**: Check database connectivity and performance
- **Message Queues**: Monitor queue health and message processing
- **Cache Systems**: Check Redis/Memcached availability

### Application Monitoring
- **Microservices**: Monitor service mesh health and dependencies
- **APIs**: Check REST/GraphQL endpoint availability
- **Background Jobs**: Monitor queue processors and scheduled tasks
- **External Dependencies**: Track third-party service availability

### Business Process Monitoring
- **Order Processing**: Monitor e-commerce transaction flows
- **Payment Systems**: Check payment gateway availability
- **Data Pipelines**: Monitor ETL job health and data freshness
- **Compliance**: Track regulatory and audit requirements

## Advanced Patterns

### Cascading Health Checks
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

# Check dependent services in sequence
workflow = WorkflowBuilder()
workflow.add_connection("database_check", "result", "api_check", "input")  # API depends on DB
workflow = WorkflowBuilder()
workflow.add_connection("api_check", "result", "frontend_check", "input")  # Frontend depends on API

```

### Conditional Alerting
```python
# Only alert if multiple consecutive checks fail
alert_filter = SwitchNode(
    name="alert_filter",
    condition_# mapping removed,
        "continue_monitoring": "consecutive_failures < 3"
    }
)

```

### Health Score Aggregation
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

# Calculate overall system health from individual service scores
health_aggregator = PythonCodeNode.from_function(
    func=calculate_system_health,
    name="health_aggregator"
)

```

## Dashboards and Reporting

### Real-Time Dashboard
- Current service status (Green/Yellow/Red)
- Response time trends and histograms
- Availability percentages over time
- Active alerts and incident timeline

### Historical Reports
- Monthly availability reports
- Performance trend analysis
- SLA compliance tracking
- Incident root cause analysis

### Automated Responses
- Auto-scaling based on health metrics
- Failover to backup services
- Circuit breaker activation
- Incident ticket creation

## Related Patterns

- **[API Integration](../api-integration/)** - For external service monitoring
- **[Data Processing](../data-processing/)** - For metrics data processing
- **[Security](../security/)** - For security health monitoring

## Production Checklist

- [ ] All monitored services use real endpoints (no mocks)
- [ ] Alert thresholds configured for business requirements
- [ ] Error handling covers network timeouts and service failures
- [ ] Monitoring data stored with proper retention policies
- [ ] Dashboard and reporting accessible to operations team
- [ ] Integration with existing alerting and incident management
- [ ] Performance tested under various failure scenarios
- [ ] Security credentials properly managed and rotated

---

**Next Steps**:
- Review `scripts/health_check_monitor.py` for implementation details
- Configure monitoring for your specific infrastructure
- Set up alerting integration with your notification systems
- See the Kailash SDK repository for training examples
