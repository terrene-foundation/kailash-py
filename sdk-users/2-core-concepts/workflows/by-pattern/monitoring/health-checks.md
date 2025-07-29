# Monitoring and Observability Patterns Guide

## Overview

This guide provides comprehensive monitoring and observability patterns for DevOps and SRE engineers using the Kailash SDK. Each pattern is production-ready with robust error handling, alerting, and real-world scenarios.

## Table of Contents

1. [Health Check Patterns](#health-check-patterns)
2. [Performance Tracking](#performance-tracking)
3. [Alerting Systems](#alerting-systems)
4. [System Monitoring](#system-monitoring)
5. [Log Aggregation](#log-aggregation)
6. [Uptime Monitoring](#uptime-monitoring)
7. [Production Dashboards](#production-dashboards)

## Health Check Patterns

### Basic Service Health Check

```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.nodes.api import RESTClientNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.runtime.local import LocalRuntime
from datetime import datetime
import json

def create_health_check_workflow():
    """
    Multi-service health check with retry logic and detailed status reporting.
    """
    workflow = WorkflowBuilder()

    # Define services to monitor
    services_config = PythonCodeNode(
        name="services_config",
        code="""
import json
services = [
    {
        "name": "API Gateway",
        "url": "https://api.example.com/health",
        "timeout": 5,
        "expected_status": 200,
        "critical": True
    },
    {
        "name": "Auth Service",
        "url": "https://auth.example.com/health",
        "timeout": 3,
        "expected_status": 200,
        "critical": True
    },
    {
        "name": "Database API",
        "url": "https://db-api.example.com/health",
        "timeout": 10,
        "expected_status": 200,
        "critical": True
    },
    {
        "name": "Cache Service",
        "url": "https://cache.example.com/health",
        "timeout": 2,
        "expected_status": 200,
        "critical": False
    }
]
result = {"services": services, "timestamp": datetime.now().isoformat()}
"""
    )
    workflow.add_node("PythonCodeNode", "services_config", {"code": services_config.code})

    # Health check executor
    health_checker = PythonCodeNode(
        name="health_checker",
        code="""
import asyncio
import aiohttp
import time
from datetime import datetime

async def check_service(session, service):
    start_time = time.time()
    try:
        async with session.get(
            service['url'],
            timeout=aiohttp.ClientTimeout(total=service['timeout'])
        ) as response:
            elapsed = time.time() - start_time
            status_ok = response.status == service['expected_status']

            # Parse response body for detailed health info
            try:
                body = await response.json()
                details = body.get('details', {})
            except:
                details = {}

            return {
                'name': service['name'],
                'url': service['url'],
                'status': 'healthy' if status_ok else 'unhealthy',
                'status_code': response.status,
                'response_time': round(elapsed * 1000, 2),  # ms
                'critical': service['critical'],
                'details': details,
                'checked_at': datetime.now().isoformat()
            }
    except asyncio.TimeoutError:
        return {
            'name': service['name'],
            'url': service['url'],
            'status': 'timeout',
            'response_time': service['timeout'] * 1000,
            'critical': service['critical'],
            'error': f'Timeout after {service["timeout"]}s',
            'checked_at': datetime.now().isoformat()
        }
    except Exception as e:
        return {
            'name': service['name'],
            'url': service['url'],
            'status': 'error',
            'critical': service['critical'],
            'error': str(e),
            'checked_at': datetime.now().isoformat()
        }

async def check_all_services():
    services = input_data['services']

    async with aiohttp.ClientSession() as session:
        tasks = [check_service(session, service) for service in services]
        results = await asyncio.gather(*tasks)

    # Calculate overall health
    critical_services = [r for r in results if r.get('critical', False)]
    critical_healthy = [r for r in critical_services if r['status'] == 'healthy']
    all_healthy = all(r['status'] == 'healthy' for r in results)
    critical_all_healthy = len(critical_healthy) == len(critical_services)

    health_summary = {
        'overall_status': 'healthy' if critical_all_healthy else 'unhealthy',
        'total_services': len(results),
        'healthy_services': len([r for r in results if r['status'] == 'healthy']),
        'critical_issues': len(critical_services) - len(critical_healthy),
        'avg_response_time': round(
            sum(r.get('response_time', 0) for r in results) / len(results), 2
        ),
        'services': results,
        'timestamp': input_data['timestamp']
    }

    result = health_summary

# Run async function
try:
    import nest_asyncio
    nest_asyncio.apply()
except:
    pass

loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)
result = loop.run_until_complete(check_all_services())
loop.close()
"""
    )
    workflow.add_node("PythonCodeNode", "health_checker", {"code": health_checker.code})
    workflow.add_connection("services_config", "result", "health_checker", "input")

    # Alert decision node
    alert_decision = SwitchNode(
        name="alert_decision",
        condition_field="overall_status"
    )
    workflow.add_node("SwitchNode", "alert_decision", {"condition_field": "overall_status"})
    workflow.add_connection("health_checker", "result", "alert_decision", "input")

    # Alert formatter for critical issues
    alert_formatter = PythonCodeNode(
        name="alert_formatter",
        code="""
health_data = input_data
critical_issues = [
    s for s in health_data['services']
    if s['critical'] and s['status'] != 'healthy'
]

alert_message = f"🚨 CRITICAL HEALTH CHECK ALERT\\n\\n"
alert_message += f"Time: {health_data['timestamp']}\\n"
alert_message += f"Critical Services Down: {len(critical_issues)}\\n\\n"

for issue in critical_issues:
    alert_message += f"❌ {issue['name']}\\n"
    alert_message += f"   Status: {issue['status']}\\n"
    if 'error' in issue:
        alert_message += f"   Error: {issue['error']}\\n"
    alert_message += f"   URL: {issue['url']}\\n\\n"

alert_message += f"\\nTotal Services: {health_data['total_services']}\\n"
alert_message += f"Healthy Services: {health_data['healthy_services']}\\n"
alert_message += f"Average Response Time: {health_data['avg_response_time']}ms"

result = {
    "alert": alert_message,
    "severity": "critical",
    "channels": ["slack", "pagerduty", "email"],
    "health_data": health_data
}
"""
    )
    workflow.add_node("PythonCodeNode", "alert_formatter", {"code": alert_formatter.code})
    workflow.add_connection("alert_decision", "result", "alert_formatter", "input")

    # Success formatter
    success_formatter = PythonCodeNode(
        name="success_formatter",
        code="""
health_data = input_data

message = f"✅ All critical services healthy\\n\\n"
message += f"Time: {health_data['timestamp']}\\n"
message += f"Total Services: {health_data['total_services']}\\n"
message += f"Average Response Time: {health_data['avg_response_time']}ms\\n\\n"

# Add any warnings for non-critical services
warnings = [
    s for s in health_data['services']
    if not s['critical'] and s['status'] != 'healthy'
]

if warnings:
    message += "⚠️  Non-critical issues:\\n"
    for w in warnings:
        message += f"- {w['name']}: {w['status']}\\n"

result = {
    "message": message,
    "severity": "info",
    "health_data": health_data
}
"""
    )
    workflow.add_node("PythonCodeNode", "success_formatter", {"code": success_formatter.code})
    workflow.add_connection("alert_decision", "result", "success_formatter", "input")

    # Convergence for results
    workflow.add_node("MergeNode", "results_merger", {})
    workflow.add_connection("alert_formatter", "result", "results_merger", "input")
    workflow.add_connection("success_formatter", "result", "results_merger", "input")

    return workflow

# Execute health check
runtime = LocalRuntime()
workflow = create_health_check_workflow()
results, run_id = runtime.execute(workflow.build())
print(json.dumps(results["results_merger"], indent=2))

```

### Advanced API Health Check with Dependencies

```python
def create_dependency_aware_health_check():
    """
    Health check that understands service dependencies and cascading failures.
    """
    workflow = WorkflowBuilder()

    # Service dependency graph
    dependency_config = PythonCodeNode(
        name="dependency_config",
        code="""
# Define service dependencies
services = {
    "api_gateway": {
        "url": "https://api.example.com/health",
        "depends_on": ["auth_service", "database"],
        "timeout": 5
    },
    "auth_service": {
        "url": "https://auth.example.com/health",
        "depends_on": ["database", "cache"],
        "timeout": 3
    },
    "database": {
        "url": "https://db.example.com/health",
        "depends_on": [],
        "timeout": 10
    },
    "cache": {
        "url": "https://cache.example.com/health",
        "depends_on": [],
        "timeout": 2
    },
    "notification_service": {
        "url": "https://notify.example.com/health",
        "depends_on": ["message_queue"],
        "timeout": 3
    },
    "message_queue": {
        "url": "https://mq.example.com/health",
        "depends_on": [],
        "timeout": 5
    }
}

result = {"services": services, "check_time": datetime.now().isoformat()}
"""
    )
    workflow.add_node("PythonCodeNode", "dependency_config", {"code": dependency_config.code})

    # Dependency-aware health checker
    dep_health_checker = PythonCodeNode(
        name="dep_health_checker",
        code="""
import asyncio
import aiohttp
from collections import defaultdict
import networkx as nx

async def check_service_health(session, name, config):
    try:
        async with session.get(
            config['url'],
            timeout=aiohttp.ClientTimeout(total=config['timeout'])
        ) as response:
            return {
                'name': name,
                'healthy': response.status == 200,
                'status_code': response.status,
                'response_time': 0  # Would measure in real implementation
            }
    except:
        return {
            'name': name,
            'healthy': False,
            'status_code': 0,
            'error': 'Connection failed'
        }

async def check_all_with_dependencies():
    services = input_data['services']

    # Create dependency graph
    G = nx.DiGraph()
    for service, config in services.items():
        G.add_node(service)
        for dep in config['depends_on']:
            G.add_edge(dep, service)  # dep -> service

    # Check all services
    async with aiohttp.ClientSession() as session:
        tasks = {
            name: check_service_health(session, name, config)
            for name, config in services.items()
        }
        results = {}
        for name, task in tasks.items():
            results[name] = await task

    # Analyze cascading failures
    impact_analysis = {}
    for service in services:
        if not results[service]['healthy']:
            # Find all services that depend on this failed service
            impacted = list(nx.descendants(G, service))
            impact_analysis[service] = {
                'direct_impact': [
                    s for s in G.successors(service)
                ],
                'total_impact': impacted,
                'impact_count': len(impacted)
            }

    # Calculate overall system health
    total_services = len(services)
    healthy_services = sum(1 for r in results.values() if r['healthy'])
    health_percentage = (healthy_services / total_services) * 100

    # Determine critical path failures
    critical_paths = []
    for service in services:
        if not results[service]['healthy'] and not services[service]['depends_on']:
            # This is a root service that failed
            affected_paths = nx.single_source_shortest_paths(G, service)
            critical_paths.append({
                'root_failure': service,
                'affected_services': list(affected_paths.keys())
            })

    result = {
        'health_percentage': round(health_percentage, 2),
        'service_status': results,
        'impact_analysis': impact_analysis,
        'critical_paths': critical_paths,
        'total_services': total_services,
        'healthy_services': healthy_services,
        'check_time': input_data['check_time']
    }

# Execute async
try:
    import nest_asyncio
    nest_asyncio.apply()
except:
    pass

loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)
result = loop.run_until_complete(check_all_with_dependencies())
loop.close()
"""
    )
    workflow.add_node("PythonCodeNode", "dep_health_checker", {"code": dep_health_checker.code})
    workflow.add_connection("dependency_config", "result", "dep_health_checker", "input")

    return workflow

```

## Performance Tracking

### Real-time Performance Metrics Collection

```python
def create_performance_tracking_workflow():
    """
    Collects and analyzes performance metrics from multiple sources.
    """
    workflow = WorkflowBuilder()

    # Metrics collector configuration
    metrics_config = PythonCodeNode(
        name="metrics_config",
        code="""
import time

# Define metrics to collect
metrics_endpoints = [
    {
        "service": "api_gateway",
        "metrics_url": "https://api.example.com/metrics",
        "type": "prometheus"
    },
    {
        "service": "database",
        "metrics_url": "https://db.example.com/stats",
        "type": "custom"
    },
    {
        "service": "cache",
        "metrics_url": "https://cache.example.com/stats",
        "type": "redis"
    }
]

# Define performance thresholds
thresholds = {
    "response_time_ms": {
        "warning": 200,
        "critical": 500
    },
    "error_rate": {
        "warning": 0.01,  # 1%
        "critical": 0.05  # 5%
    },
    "cpu_usage": {
        "warning": 70,
        "critical": 90
    },
    "memory_usage": {
        "warning": 80,
        "critical": 95
    },
    "queue_depth": {
        "warning": 1000,
        "critical": 5000
    }
}

result = {
    "endpoints": metrics_endpoints,
    "thresholds": thresholds,
    "collection_time": time.time()
}
"""
    )
    workflow.add_node("PythonCodeNode", "metrics_config", {"code": metrics_config.code})

    # Metrics collector
    metrics_collector = PythonCodeNode(
        name="metrics_collector",
        code="""
import asyncio
import aiohttp
import statistics
from datetime import datetime, timedelta

async def collect_prometheus_metrics(session, url):
    try:
        async with session.get(url) as response:
            text = await response.text()

        # Parse Prometheus format
        metrics = {}
        for line in text.split('\\n'):
            if line and not line.startswith('#'):
                parts = line.split()
                if len(parts) >= 2:
                    metric_name = parts[0]
                    metric_value = float(parts[1])
                    metrics[metric_name] = metric_value

        return metrics
    except:
        return {}

async def collect_custom_metrics(session, url):
    try:
        async with session.get(url) as response:
            return await response.json()
    except:
        return {}

async def collect_all_metrics():
    endpoints = input_data['endpoints']
    thresholds = input_data['thresholds']

    async with aiohttp.ClientSession() as session:
        tasks = []
        for endpoint in endpoints:
            if endpoint['type'] == 'prometheus':
                tasks.append(collect_prometheus_metrics(session, endpoint['metrics_url']))
            else:
                tasks.append(collect_custom_metrics(session, endpoint['metrics_url']))

        raw_metrics = await asyncio.gather(*tasks)

    # Process and normalize metrics
    processed_metrics = []
    alerts = []

    for i, endpoint in enumerate(endpoints):
        service = endpoint['service']
        metrics = raw_metrics[i]

        if not metrics:
            alerts.append({
                'service': service,
                'type': 'collection_failure',
                'severity': 'warning',
                'message': f'Failed to collect metrics from {service}'
            })
            continue

        # Extract key metrics (adapt based on actual metrics)
        processed = {
            'service': service,
            'timestamp': datetime.now().isoformat(),
            'response_time_ms': metrics.get('http_request_duration_ms', 0),
            'error_rate': metrics.get('http_requests_errors_total', 0) / max(metrics.get('http_requests_total', 1), 1),
            'cpu_usage': metrics.get('cpu_usage_percent', 0),
            'memory_usage': metrics.get('memory_usage_percent', 0),
            'queue_depth': metrics.get('queue_size', 0),
            'active_connections': metrics.get('connections_active', 0),
            'requests_per_second': metrics.get('requests_per_second', 0)
        }

        # Check thresholds
        for metric, value in processed.items():
            if metric in thresholds and isinstance(value, (int, float)):
                if value >= thresholds[metric]['critical']:
                    alerts.append({
                        'service': service,
                        'metric': metric,
                        'value': value,
                        'threshold': thresholds[metric]['critical'],
                        'severity': 'critical',
                        'message': f'{service}: {metric} is {value} (critical threshold: {thresholds[metric]["critical"]})'
                    })
                elif value >= thresholds[metric]['warning']:
                    alerts.append({
                        'service': service,
                        'metric': metric,
                        'value': value,
                        'threshold': thresholds[metric]['warning'],
                        'severity': 'warning',
                        'message': f'{service}: {metric} is {value} (warning threshold: {thresholds[metric]["warning"]})'
                    })

        processed_metrics.append(processed)

    # Calculate aggregate metrics
    if processed_metrics:
        aggregates = {
            'avg_response_time': statistics.mean([m['response_time_ms'] for m in processed_metrics if m['response_time_ms'] > 0]),
            'max_error_rate': max([m['error_rate'] for m in processed_metrics]),
            'avg_cpu_usage': statistics.mean([m['cpu_usage'] for m in processed_metrics if m['cpu_usage'] > 0]),
            'total_active_connections': sum([m['active_connections'] for m in processed_metrics])
        }
    else:
        aggregates = {}

    result = {
        'metrics': processed_metrics,
        'aggregates': aggregates,
        'alerts': alerts,
        'collection_time': input_data['collection_time']
    }

# Execute
try:
    import nest_asyncio
    nest_asyncio.apply()
except:
    pass

loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)
result = loop.run_until_complete(collect_all_metrics())
loop.close()
"""
    )
    workflow.add_node("PythonCodeNode", "metrics_collector", {"code": metrics_collector.code})
    workflow.add_connection("metrics_config", "result", "metrics_collector", "input")

    # Performance analyzer
    performance_analyzer = PythonCodeNode(
        name="performance_analyzer",
        code="""
import statistics
from datetime import datetime, timedelta

metrics_data = input_data

# Analyze performance trends (would use historical data in production)
analysis = {
    'timestamp': datetime.now().isoformat(),
    'summary': {},
    'recommendations': [],
    'predicted_issues': []
}

# Analyze each service
for metric in metrics_data['metrics']:
    service = metric['service']

    # Calculate performance score (0-100)
    scores = []
    if metric['response_time_ms'] > 0:
        rt_score = max(0, 100 - (metric['response_time_ms'] / 5))  # 500ms = 0 score
        scores.append(rt_score)

    if metric['error_rate'] >= 0:
        err_score = max(0, 100 - (metric['error_rate'] * 2000))  # 5% = 0 score
        scores.append(err_score)

    if metric['cpu_usage'] > 0:
        cpu_score = max(0, 100 - metric['cpu_usage'])
        scores.append(cpu_score)

    performance_score = statistics.mean(scores) if scores else 0

    analysis['summary'][service] = {
        'performance_score': round(performance_score, 2),
        'status': 'good' if performance_score > 80 else 'degraded' if performance_score > 60 else 'poor'
    }

    # Generate recommendations
    if metric['response_time_ms'] > 300:
        analysis['recommendations'].append({
            'service': service,
            'type': 'performance',
            'recommendation': f'Consider caching or optimizing {service} - response time is {metric["response_time_ms"]}ms'
        })

    if metric['cpu_usage'] > 80:
        analysis['recommendations'].append({
            'service': service,
            'type': 'scaling',
            'recommendation': f'Scale up {service} - CPU usage at {metric["cpu_usage"]}%'
        })

    if metric['error_rate'] > 0.02:
        analysis['recommendations'].append({
            'service': service,
            'type': 'reliability',
            'recommendation': f'Investigate errors in {service} - error rate at {metric["error_rate"]*100:.2f}%'
        })

# Predict potential issues
if metrics_data['aggregates']:
    if metrics_data['aggregates']['avg_cpu_usage'] > 70:
        analysis['predicted_issues'].append({
            'type': 'capacity',
            'severity': 'warning',
            'prediction': 'System may experience capacity issues in next 2-4 hours based on CPU trends'
        })

    if metrics_data['aggregates']['max_error_rate'] > 0.03:
        analysis['predicted_issues'].append({
            'type': 'reliability',
            'severity': 'warning',
            'prediction': 'Error rate trending upward - potential cascade failure risk'
        })

result = {
    'analysis': analysis,
    'metrics_data': metrics_data,
    'requires_immediate_action': len(metrics_data['alerts']) > 0
}
"""
    )
    workflow.add_node("PythonCodeNode", "performance_analyzer", {"code": performance_analyzer.code})
    workflow.add_connection("metrics_collector", "result", "performance_analyzer", "input")

    return workflow

```

## Alerting Systems

### Intelligent Alert Routing and Escalation

```python
def create_alert_management_workflow():
    """
    Sophisticated alert routing with deduplication, correlation, and escalation.
    """
    workflow = WorkflowBuilder()

    # Alert ingestion
    alert_ingestion = PythonCodeNode(
        name="alert_ingestion",
        code="""
import hashlib
import json
from datetime import datetime

# Sample incoming alerts (would come from monitoring systems)
raw_alerts = [
    {
        "source": "prometheus",
        "service": "api_gateway",
        "metric": "response_time",
        "value": 850,
        "threshold": 500,
        "severity": "critical",
        "timestamp": datetime.now().isoformat()
    },
    {
        "source": "prometheus",
        "service": "api_gateway",
        "metric": "error_rate",
        "value": 0.08,
        "threshold": 0.05,
        "severity": "critical",
        "timestamp": datetime.now().isoformat()
    },
    {
        "source": "custom_monitor",
        "service": "database",
        "metric": "connection_pool",
        "value": 95,
        "threshold": 80,
        "severity": "warning",
        "timestamp": datetime.now().isoformat()
    }
]

# Generate alert IDs for deduplication
processed_alerts = []
for alert in raw_alerts:
    # Create unique alert fingerprint
    fingerprint = f"{alert['service']}:{alert['metric']}:{alert['severity']}"
    alert_id = hashlib.md5(fingerprint.encode()).hexdigest()[:8]

    alert['alert_id'] = alert_id
    alert['fingerprint'] = fingerprint
    alert['processed_at'] = datetime.now().isoformat()
    processed_alerts.append(alert)

result = {
    "alerts": processed_alerts,
    "alert_count": len(processed_alerts),
    "ingestion_time": datetime.now().isoformat()
}
"""
    )
    workflow.add_node("PythonCodeNode", "alert_ingestion", {"code": alert_ingestion.code})

    # Alert correlation and deduplication
    alert_processor = PythonCodeNode(
        name="alert_processor",
        code="""
from datetime import datetime, timedelta
from collections import defaultdict

alerts_data = input_data
current_time = datetime.now()

# Alert history for deduplication (would be persistent in production)
alert_history = {}  # Would load from database

# Group alerts by service for correlation
service_alerts = defaultdict(list)
for alert in alerts_data['alerts']:
    service_alerts[alert['service']].append(alert)

# Process alerts with correlation
processed_groups = []
notifications = []

for service, alerts in service_alerts.items():
    # Check for correlated issues
    critical_count = sum(1 for a in alerts if a['severity'] == 'critical')
    warning_count = sum(1 for a in alerts if a['severity'] == 'warning')

    if critical_count >= 2:
        # Multiple critical alerts - likely service failure
        group = {
            'group_id': f"{service}_failure_{current_time.timestamp()}",
            'type': 'service_failure',
            'service': service,
            'severity': 'critical',
            'alerts': alerts,
            'summary': f"{service} experiencing multiple critical issues",
            'requires_escalation': True
        }
        processed_groups.append(group)

        # Create high-priority notification
        notifications.append({
            'type': 'immediate',
            'channels': ['pagerduty', 'slack_critical', 'sms'],
            'group': group,
            'escalation_level': 1
        })

    elif critical_count == 1:
        # Single critical alert
        group = {
            'group_id': f"{service}_critical_{current_time.timestamp()}",
            'type': 'single_critical',
            'service': service,
            'severity': 'critical',
            'alerts': [a for a in alerts if a['severity'] == 'critical'],
            'summary': f"{service} has a critical issue",
            'requires_escalation': False
        }
        processed_groups.append(group)

        notifications.append({
            'type': 'standard',
            'channels': ['slack_critical', 'email'],
            'group': group,
            'escalation_level': 0
        })

    elif warning_count >= 3:
        # Multiple warnings might indicate developing issue
        group = {
            'group_id': f"{service}_warnings_{current_time.timestamp()}",
            'type': 'multiple_warnings',
            'service': service,
            'severity': 'warning',
            'alerts': alerts,
            'summary': f"{service} showing multiple warning signs",
            'requires_escalation': False
        }
        processed_groups.append(group)

        notifications.append({
            'type': 'informational',
            'channels': ['slack_warnings'],
            'group': group,
            'escalation_level': 0
        })

# Check for system-wide issues
all_critical = [a for a in alerts_data['alerts'] if a['severity'] == 'critical']
if len(all_critical) >= 3 and len(service_alerts) >= 2:
    # Multiple services affected - potential system-wide issue
    notifications.insert(0, {
        'type': 'emergency',
        'channels': ['pagerduty', 'slack_critical', 'sms', 'phone'],
        'summary': 'SYSTEM-WIDE CRITICAL ISSUE DETECTED',
        'affected_services': list(service_alerts.keys()),
        'escalation_level': 2
    })

result = {
    'processed_groups': processed_groups,
    'notifications': notifications,
    'correlation_summary': {
        'total_alerts': len(alerts_data['alerts']),
        'affected_services': len(service_alerts),
        'critical_groups': len([g for g in processed_groups if g['severity'] == 'critical']),
        'requires_escalation': any(g.get('requires_escalation', False) for g in processed_groups)
    },
    'processing_time': datetime.now().isoformat()
}
"""
    )
    workflow.add_node("PythonCodeNode", "alert_processor", {"code": alert_processor.code})
    workflow.add_connection("alert_ingestion", "result", "alert_processor", "input")

    # Notification dispatcher
    notification_dispatcher = PythonCodeNode(
        name="notification_dispatcher",
        code="""
import json
from datetime import datetime

notification_data = input_data

# Route notifications to appropriate channels
dispatched = []

for notif in notification_data['notifications']:
    channels = notif.get('channels', [])

    for channel in channels:
        dispatch_record = {
            'channel': channel,
            'timestamp': datetime.now().isoformat(),
            'status': 'dispatched'
        }

        if channel == 'pagerduty':
            # Format for PagerDuty
            dispatch_record['payload'] = {
                'routing_key': 'YOUR_ROUTING_KEY',
                'event_action': 'trigger',
                'dedup_key': notif.get('group', {}).get('group_id', ''),
                'payload': {
                    'summary': notif.get('summary', notif.get('group', {}).get('summary', '')),
                    'severity': 'critical' if notif['type'] == 'emergency' else 'error',
                    'source': 'kailash_monitoring',
                    'custom_details': notif
                }
            }

        elif channel.startswith('slack'):
            # Format for Slack
            severity_emoji = {
                'emergency': '🚨🚨🚨',
                'immediate': '🚨',
                'standard': '⚠️',
                'informational': 'ℹ️'
            }

            dispatch_record['payload'] = {
                'channel': '#alerts-critical' if 'critical' in channel else '#alerts-general',
                'text': f"{severity_emoji.get(notif['type'], '⚠️')} {notif.get('summary', '')}",
                'attachments': [
                    {
                        'color': 'danger' if 'critical' in str(notif) else 'warning',
                        'fields': [
                            {
                                'title': 'Details',
                                'value': json.dumps(notif, indent=2)[:500]  # Truncate for Slack
                            }
                        ]
                    }
                ]
            }

        elif channel == 'email':
            # Format for email
            dispatch_record['payload'] = {
                'to': ['sre-team@example.com'],
                'subject': f"[{notif['type'].upper()}] {notif.get('summary', 'Alert')}",
                'body': json.dumps(notif, indent=2)
            }

        elif channel == 'sms':
            # Format for SMS (keep it short)
            dispatch_record['payload'] = {
                'to': ['+1234567890'],  # On-call number
                'message': f"{notif['type'].upper()}: {notif.get('summary', 'Critical Alert')[:140]}"
            }

        dispatched.append(dispatch_record)

# Summary of dispatched notifications
summary = {
    'total_notifications': len(notification_data['notifications']),
    'total_dispatches': len(dispatched),
    'channels_used': list(set(d['channel'] for d in dispatched)),
    'highest_severity': notification_data['notifications'][0]['type'] if notification_data['notifications'] else None,
    'dispatch_time': datetime.now().isoformat()
}

result = {
    'dispatched': dispatched,
    'summary': summary,
    'original_data': notification_data
}
"""
    )
    workflow.add_node("PythonCodeNode", "notification_dispatcher", {"code": notification_dispatcher.code})
    workflow.add_connection("alert_processor", "result", "notification_dispatcher", "input")

    return workflow

```

## System Monitoring

### Comprehensive Resource and Infrastructure Monitoring

```python
def create_system_monitoring_workflow():
    """
    Monitors system resources, infrastructure health, and capacity planning.
    """
    workflow = WorkflowBuilder()

    # System inventory
    system_inventory = PythonCodeNode(
        name="system_inventory",
        code="""
# Define systems to monitor
systems = [
    {
        "hostname": "api-server-01",
        "type": "application",
        "ip": "10.0.1.10",
        "metrics_port": 9090,
        "ssh_port": 22
    },
    {
        "hostname": "api-server-02",
        "type": "application",
        "ip": "10.0.1.11",
        "metrics_port": 9090,
        "ssh_port": 22
    },
    {
        "hostname": "db-primary",
        "type": "database",
        "ip": "10.0.2.10",
        "metrics_port": 9091,
        "ssh_port": 22
    },
    {
        "hostname": "cache-01",
        "type": "cache",
        "ip": "10.0.3.10",
        "metrics_port": 9092,
        "ssh_port": 22
    },
    {
        "hostname": "lb-01",
        "type": "load_balancer",
        "ip": "10.0.0.10",
        "metrics_port": 9093,
        "ssh_port": 22
    }
]

# Resource thresholds by system type
thresholds = {
    "application": {
        "cpu": {"warning": 70, "critical": 85},
        "memory": {"warning": 75, "critical": 90},
        "disk": {"warning": 80, "critical": 95},
        "load_avg": {"warning": 4.0, "critical": 8.0}
    },
    "database": {
        "cpu": {"warning": 60, "critical": 80},
        "memory": {"warning": 85, "critical": 95},
        "disk": {"warning": 70, "critical": 85},
        "connections": {"warning": 80, "critical": 95}
    },
    "cache": {
        "cpu": {"warning": 50, "critical": 70},
        "memory": {"warning": 90, "critical": 98},
        "hit_rate": {"warning": 70, "critical": 50}  # Lower is worse
    },
    "load_balancer": {
        "cpu": {"warning": 40, "critical": 60},
        "connections": {"warning": 8000, "critical": 10000},
        "bandwidth_mbps": {"warning": 800, "critical": 950}
    }
}

result = {
    "systems": systems,
    "thresholds": thresholds,
    "scan_time": datetime.now().isoformat()
}
"""
    )
    workflow.add_node("PythonCodeNode", "system_inventory", {"code": system_inventory.code})

    # Resource collector
    resource_collector = PythonCodeNode(
        name="resource_collector",
        code="""
import asyncio
import aiohttp
import random  # Simulating metrics
from datetime import datetime

async def collect_system_metrics(session, system):
    # In production, would SSH or use agent APIs
    # Simulating realistic metrics here

    base_metrics = {
        "timestamp": datetime.now().isoformat(),
        "hostname": system["hostname"],
        "type": system["type"],
        "status": "online"
    }

    # Simulate different metrics by system type
    if system["type"] == "application":
        metrics = {
            **base_metrics,
            "cpu_percent": random.uniform(40, 80),
            "memory_percent": random.uniform(50, 85),
            "disk_percent": random.uniform(30, 70),
            "load_avg_1m": random.uniform(1.0, 6.0),
            "load_avg_5m": random.uniform(1.0, 5.0),
            "load_avg_15m": random.uniform(1.0, 4.0),
            "network_in_mbps": random.uniform(10, 100),
            "network_out_mbps": random.uniform(20, 150),
            "open_files": random.randint(1000, 5000),
            "threads": random.randint(100, 500)
        }

    elif system["type"] == "database":
        metrics = {
            **base_metrics,
            "cpu_percent": random.uniform(30, 70),
            "memory_percent": random.uniform(60, 90),
            "disk_percent": random.uniform(40, 80),
            "connections_active": random.randint(50, 200),
            "connections_idle": random.randint(10, 50),
            "queries_per_second": random.uniform(100, 1000),
            "slow_queries": random.randint(0, 10),
            "replication_lag_seconds": random.uniform(0, 2),
            "cache_hit_ratio": random.uniform(0.85, 0.99)
        }

    elif system["type"] == "cache":
        metrics = {
            **base_metrics,
            "cpu_percent": random.uniform(20, 60),
            "memory_percent": random.uniform(70, 95),
            "hit_rate": random.uniform(0.80, 0.98),
            "evictions_per_minute": random.randint(0, 100),
            "keys_total": random.randint(100000, 1000000),
            "connections_current": random.randint(100, 500),
            "ops_per_second": random.uniform(1000, 10000)
        }

    elif system["type"] == "load_balancer":
        metrics = {
            **base_metrics,
            "cpu_percent": random.uniform(20, 50),
            "memory_percent": random.uniform(30, 60),
            "connections_active": random.randint(1000, 9000),
            "bandwidth_in_mbps": random.uniform(100, 900),
            "bandwidth_out_mbps": random.uniform(100, 900),
            "requests_per_second": random.uniform(1000, 5000),
            "ssl_handshakes_per_second": random.uniform(10, 100),
            "backend_health": {
                "healthy": random.randint(8, 10),
                "unhealthy": random.randint(0, 2)
            }
        }

    else:
        metrics = base_metrics

    # Simulate occasional issues
    if random.random() < 0.1:  # 10% chance of issues
        if system["type"] == "application":
            metrics["cpu_percent"] = random.uniform(80, 95)
        elif system["type"] == "database":
            metrics["slow_queries"] = random.randint(20, 50)

    return metrics

async def collect_all_systems():
    systems = input_data["systems"]
    thresholds = input_data["thresholds"]

    # Collect metrics from all systems
    async with aiohttp.ClientSession() as session:
        tasks = [collect_system_metrics(session, system) for system in systems]
        all_metrics = await asyncio.gather(*tasks)

    # Analyze metrics against thresholds
    issues = []
    capacity_warnings = []

    for metrics in all_metrics:
        system_type = metrics["type"]
        hostname = metrics["hostname"]
        system_thresholds = thresholds.get(system_type, {})

        # Check each metric against thresholds
        for metric, value in metrics.items():
            if metric in system_thresholds and isinstance(value, (int, float)):
                thresh = system_thresholds[metric]

                if "critical" in thresh and value >= thresh["critical"]:
                    issues.append({
                        "hostname": hostname,
                        "metric": metric,
                        "value": value,
                        "threshold": thresh["critical"],
                        "severity": "critical",
                        "message": f"{hostname}: {metric} at {value:.2f} (critical: {thresh['critical']})"
                    })
                elif "warning" in thresh and value >= thresh["warning"]:
                    issues.append({
                        "hostname": hostname,
                        "metric": metric,
                        "value": value,
                        "threshold": thresh["warning"],
                        "severity": "warning",
                        "message": f"{hostname}: {metric} at {value:.2f} (warning: {thresh['warning']})"
                    })

        # Capacity planning checks
        if system_type == "application":
            if metrics.get("cpu_percent", 0) > 60 and metrics.get("memory_percent", 0) > 70:
                capacity_warnings.append({
                    "hostname": hostname,
                    "type": "scaling_needed",
                    "reason": "High CPU and memory usage",
                    "recommendation": "Consider horizontal scaling"
                })

        elif system_type == "database":
            if metrics.get("connections_active", 0) > 150:
                capacity_warnings.append({
                    "hostname": hostname,
                    "type": "connection_pool",
                    "reason": "High connection count",
                    "recommendation": "Increase connection pool size or add read replicas"
                })

    # Calculate fleet-wide statistics
    fleet_stats = {}
    for system_type in set(m["type"] for m in all_metrics):
        type_metrics = [m for m in all_metrics if m["type"] == system_type]
        if type_metrics:
            fleet_stats[system_type] = {
                "count": len(type_metrics),
                "avg_cpu": sum(m.get("cpu_percent", 0) for m in type_metrics) / len(type_metrics),
                "avg_memory": sum(m.get("memory_percent", 0) for m in type_metrics) / len(type_metrics),
                "healthy": len([m for m in type_metrics if m["status"] == "online"])
            }

    result = {
        "metrics": all_metrics,
        "issues": issues,
        "capacity_warnings": capacity_warnings,
        "fleet_stats": fleet_stats,
        "collection_time": input_data["scan_time"]
    }

# Execute
try:
    import nest_asyncio
    nest_asyncio.apply()
except:
    pass

loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)
result = loop.run_until_complete(collect_all_systems())
loop.close()
"""
    )
    workflow.add_node("PythonCodeNode", "resource_collector", {"code": resource_collector.code})
    workflow.add_connection("system_inventory", "result", "resource_collector", "input")

    # Capacity analyzer
    capacity_analyzer = PythonCodeNode(
        name="capacity_analyzer",
        code="""
from datetime import datetime, timedelta
import statistics

monitoring_data = input_data

# Analyze capacity trends and predict future needs
analysis = {
    "timestamp": datetime.now().isoformat(),
    "current_state": {},
    "predictions": [],
    "recommendations": []
}

# Analyze by system type
for system_type, stats in monitoring_data["fleet_stats"].items():
    analysis["current_state"][system_type] = {
        "total_systems": stats["count"],
        "healthy_systems": stats["healthy"],
        "average_cpu": round(stats["avg_cpu"], 2),
        "average_memory": round(stats["avg_memory"], 2),
        "health_percentage": round((stats["healthy"] / stats["count"]) * 100, 2)
    }

    # Simple linear projection (would use ML in production)
    if stats["avg_cpu"] > 60:
        days_until_critical = int((85 - stats["avg_cpu"]) / 0.5)  # Assuming 0.5% daily growth
        analysis["predictions"].append({
            "system_type": system_type,
            "metric": "cpu",
            "prediction": f"CPU likely to reach critical levels in {days_until_critical} days",
            "confidence": "medium"
        })

    if stats["avg_memory"] > 70:
        days_until_critical = int((90 - stats["avg_memory"]) / 0.3)  # Assuming 0.3% daily growth
        analysis["predictions"].append({
            "system_type": system_type,
            "metric": "memory",
            "prediction": f"Memory likely to reach critical levels in {days_until_critical} days",
            "confidence": "medium"
        })

# Generate recommendations
critical_issues = [i for i in monitoring_data["issues"] if i["severity"] == "critical"]
if critical_issues:
    analysis["recommendations"].append({
        "priority": "immediate",
        "action": "Address critical issues",
        "details": f"{len(critical_issues)} systems have critical metrics",
        "affected_systems": list(set(i["hostname"] for i in critical_issues))
    })

if monitoring_data["capacity_warnings"]:
    scaling_needed = [w for w in monitoring_data["capacity_warnings"] if w["type"] == "scaling_needed"]
    if scaling_needed:
        analysis["recommendations"].append({
            "priority": "high",
            "action": "Plan scaling",
            "details": f"{len(scaling_needed)} systems need scaling",
            "systems": [w["hostname"] for w in scaling_needed]
        })

# Overall system health score
total_systems = sum(s["count"] for s in monitoring_data["fleet_stats"].values())
total_healthy = sum(s["healthy"] for s in monitoring_data["fleet_stats"].values())
health_score = (total_healthy / total_systems) * 100 if total_systems > 0 else 0

# Adjust for issues
health_score -= len(critical_issues) * 5
health_score -= len([i for i in monitoring_data["issues"] if i["severity"] == "warning"]) * 2
health_score = max(0, min(100, health_score))

analysis["system_health_score"] = round(health_score, 2)
analysis["status"] = "healthy" if health_score > 80 else "degraded" if health_score > 60 else "critical"

result = {
    "analysis": analysis,
    "raw_data": monitoring_data,
    "requires_action": len(critical_issues) > 0 or health_score < 70
}
"""
    )
    workflow.add_node("PythonCodeNode", "capacity_analyzer", {"code": capacity_analyzer.code})
    workflow.add_connection("resource_collector", "result", "capacity_analyzer", "input")

    return workflow

```

## Log Aggregation

### Intelligent Log Analysis and Pattern Detection

```python
def create_log_aggregation_workflow():
    """
    Aggregates logs from multiple sources, detects patterns, and identifies anomalies.
    """
    workflow = WorkflowBuilder()

    # Log sources configuration
    log_sources = PythonCodeNode(
        name="log_sources",
        code="""
from datetime import datetime, timedelta

# Define log sources
sources = [
    {
        "name": "application_logs",
        "type": "elasticsearch",
        "url": "https://es.example.com",
        "index": "app-logs-*",
        "query_window": "5m"
    },
    {
        "name": "nginx_logs",
        "type": "elasticsearch",
        "url": "https://es.example.com",
        "index": "nginx-*",
        "query_window": "5m"
    },
    {
        "name": "database_logs",
        "type": "postgresql",
        "connection": "postgresql://localhost/logs",
        "table": "db_logs",
        "query_window": "5m"
    },
    {
        "name": "kubernetes_logs",
        "type": "kubernetes",
        "api_endpoint": "https://k8s.example.com",
        "namespace": "production",
        "query_window": "5m"
    }
]

# Define patterns to look for
patterns = {
    "errors": [
        r"ERROR|CRITICAL|FATAL",
        r"Exception|Error|Failed",
        r"5\\d{2}\\s",  # 5xx status codes
        r"timeout|timed out"
    ],
    "security": [
        r"unauthorized|forbidden|denied",
        r"invalid.{0,20}token|invalid.{0,20}auth",
        r"SQL injection|XSS|CSRF",
        r"brute.{0,20}force|suspicious"
    ],
    "performance": [
        r"slow query|slow request",
        r"high latency|performance degradation",
        r"memory leak|out of memory",
        r"connection pool exhausted"
    ],
    "availability": [
        r"service unavailable|down|offline",
        r"cannot connect|connection refused",
        r"circuit breaker open",
        r"health check failed"
    ]
}

result = {
    "sources": sources,
    "patterns": patterns,
    "query_time": datetime.now().isoformat(),
    "window_start": (datetime.now() - timedelta(minutes=5)).isoformat(),
    "window_end": datetime.now().isoformat()
}
"""
    )
    workflow.add_node("PythonCodeNode", "log_sources", {"code": log_sources.code})

    # Log collector and parser
    log_collector = PythonCodeNode(
        name="log_collector",
        code="""
import re
import asyncio
import aiohttp
from datetime import datetime
from collections import defaultdict, Counter
import json

async def collect_elasticsearch_logs(session, source):
    # Simulate ES query (would use actual ES client)
    # Returning sample logs for demo
    logs = []

    # Simulate various log entries
    sample_logs = [
        {
            "@timestamp": datetime.now().isoformat(),
            "level": "ERROR",
            "service": "api-gateway",
            "message": "Connection timeout to database after 30s",
            "request_id": "req-123",
            "user_id": "user-456"
        },
        {
            "@timestamp": datetime.now().isoformat(),
            "level": "ERROR",
            "service": "api-gateway",
            "message": "HTTP 500 Internal Server Error",
            "request_id": "req-124",
            "path": "/api/users"
        },
        {
            "@timestamp": datetime.now().isoformat(),
            "level": "WARN",
            "service": "auth-service",
            "message": "Multiple failed login attempts from IP 192.168.1.100",
            "ip": "192.168.1.100",
            "attempts": 5
        },
        {
            "@timestamp": datetime.now().isoformat(),
            "level": "ERROR",
            "service": "payment-service",
            "message": "Payment processing failed: Gateway timeout",
            "transaction_id": "txn-789",
            "amount": 99.99
        },
        {
            "@timestamp": datetime.now().isoformat(),
            "level": "INFO",
            "service": "api-gateway",
            "message": "Request completed successfully",
            "request_id": "req-125",
            "duration_ms": 45
        }
    ]

    # Add more logs to simulate volume
    for i in range(100):
        if i % 20 == 0:
            logs.append(sample_logs[0])  # Error logs
        elif i % 15 == 0:
            logs.append(sample_logs[2])  # Security logs
        else:
            logs.append(sample_logs[4])  # Normal logs

    return logs

async def collect_all_logs():
    sources = input_data["sources"]
    patterns = input_data["patterns"]

    # Collect logs from all sources
    all_logs = []
    async with aiohttp.ClientSession() as session:
        for source in sources:
            if source["type"] == "elasticsearch":
                logs = await collect_elasticsearch_logs(session, source)
                all_logs.extend(logs)

    # Analyze logs
    pattern_matches = defaultdict(list)
    service_errors = defaultdict(int)
    error_patterns = Counter()
    timeline = defaultdict(lambda: {"errors": 0, "warnings": 0, "total": 0})

    for log in all_logs:
        log_message = log.get("message", "")
        log_level = log.get("level", "INFO")
        service = log.get("service", "unknown")
        timestamp = log.get("@timestamp", "")

        # Count by service and level
        if log_level in ["ERROR", "CRITICAL"]:
            service_errors[service] += 1

        # Match against patterns
        for pattern_type, pattern_list in patterns.items():
            for pattern in pattern_list:
                if re.search(pattern, log_message, re.IGNORECASE):
                    pattern_matches[pattern_type].append({
                        "log": log,
                        "pattern": pattern,
                        "matched_at": datetime.now().isoformat()
                    })

                    if pattern_type == "errors":
                        error_patterns[log_message[:50]] += 1

        # Build timeline
        if timestamp:
            minute_key = timestamp[:16]  # Group by minute
            timeline[minute_key]["total"] += 1
            if log_level == "ERROR":
                timeline[minute_key]["errors"] += 1
            elif log_level == "WARN":
                timeline[minute_key]["warnings"] += 1

    # Identify anomalies
    anomalies = []

    # Check for error spikes
    error_counts = [v["errors"] for v in timeline.values()]
    if error_counts:
        avg_errors = sum(error_counts) / len(error_counts)
        for minute, stats in timeline.items():
            if stats["errors"] > avg_errors * 3:  # 3x average
                anomalies.append({
                    "type": "error_spike",
                    "time": minute,
                    "error_count": stats["errors"],
                    "severity": "high",
                    "message": f"Error spike detected: {stats['errors']} errors (avg: {avg_errors:.1f})"
                })

    # Check for security patterns
    security_matches = len(pattern_matches.get("security", []))
    if security_matches > 5:
        anomalies.append({
            "type": "security_alert",
            "count": security_matches,
            "severity": "critical",
            "message": f"Multiple security-related log entries detected: {security_matches} matches"
        })

    # Find most common errors
    top_errors = error_patterns.most_common(5)

    result = {
        "summary": {
            "total_logs": len(all_logs),
            "error_logs": sum(service_errors.values()),
            "services_with_errors": len(service_errors),
            "pattern_matches": {k: len(v) for k, v in pattern_matches.items()},
            "anomalies_detected": len(anomalies)
        },
        "service_errors": dict(service_errors),
        "top_errors": [{"pattern": k, "count": v} for k, v in top_errors],
        "anomalies": anomalies,
        "timeline": dict(timeline),
        "pattern_matches": {k: v[:10] for k, v in pattern_matches.items()},  # Limit to 10 per pattern
        "analysis_time": datetime.now().isoformat()
    }

# Execute
try:
    import nest_asyncio
    nest_asyncio.apply()
except:
    pass

loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)
result = loop.run_until_complete(collect_all_logs())
loop.close()
"""
    )
    workflow.add_node("PythonCodeNode", "log_collector", {"code": log_collector.code})
    workflow.add_connection("log_sources", "result", "log_collector", "input")

    # Intelligent log analyzer
    log_analyzer = PythonCodeNode(
        name="log_analyzer",
        code="""
from datetime import datetime
import json

log_data = input_data

# Advanced analysis
analysis = {
    "timestamp": datetime.now().isoformat(),
    "insights": [],
    "action_items": [],
    "correlation_findings": []
}

# Analyze error patterns
if log_data["top_errors"]:
    most_common = log_data["top_errors"][0]
    if most_common["count"] > 10:
        analysis["insights"].append({
            "type": "recurring_error",
            "severity": "high",
            "finding": f"Error '{most_common['pattern']}' occurred {most_common['count']} times",
            "recommendation": "Investigate root cause of recurring error"
        })

# Analyze service health
unhealthy_services = [
    service for service, count in log_data["service_errors"].items()
    if count > 5
]
if unhealthy_services:
    analysis["insights"].append({
        "type": "service_health",
        "severity": "medium",
        "finding": f"{len(unhealthy_services)} services showing elevated error rates",
        "affected_services": unhealthy_services,
        "recommendation": "Review service logs and recent deployments"
    })

# Correlate patterns
if "security" in log_data["pattern_matches"] and "errors" in log_data["pattern_matches"]:
    if log_data["pattern_matches"]["security"] and log_data["pattern_matches"]["errors"]:
        # Check if security issues correlate with errors
        analysis["correlation_findings"].append({
            "type": "security_error_correlation",
            "finding": "Security events detected alongside error spikes",
            "severity": "critical",
            "recommendation": "Investigate potential security incident"
        })

# Generate action items based on findings
for anomaly in log_data["anomalies"]:
    if anomaly["severity"] == "critical":
        analysis["action_items"].append({
            "priority": "immediate",
            "action": f"Investigate {anomaly['type']}",
            "details": anomaly["message"],
            "assigned_to": "on-call-sre"
        })
    elif anomaly["severity"] == "high":
        analysis["action_items"].append({
            "priority": "high",
            "action": f"Review {anomaly['type']}",
            "details": anomaly["message"],
            "assigned_to": "sre-team"
        })

# Calculate log health score
total_logs = log_data["summary"]["total_logs"]
error_logs = log_data["summary"]["error_logs"]
error_rate = (error_logs / total_logs * 100) if total_logs > 0 else 0

health_score = 100
health_score -= min(error_rate * 10, 50)  # High error rate reduces score
health_score -= len(log_data["anomalies"]) * 5  # Each anomaly reduces score
health_score -= len(unhealthy_services) * 3  # Each unhealthy service reduces score
health_score = max(0, health_score)

analysis["log_health_score"] = round(health_score, 2)
analysis["status"] = "healthy" if health_score > 80 else "concerning" if health_score > 60 else "unhealthy"

# Add summary
analysis["summary"] = {
    "error_rate": round(error_rate, 2),
    "anomaly_count": len(log_data["anomalies"]),
    "unhealthy_services": len(unhealthy_services),
    "requires_immediate_action": any(a["priority"] == "immediate" for a in analysis["action_items"])
}

result = {
    "analysis": analysis,
    "raw_data": log_data
}
"""
    )
    workflow.add_node("PythonCodeNode", "log_analyzer", {"code": log_analyzer.code})
    workflow.add_connection("log_collector", "result", "log_analyzer", "input")

    return workflow

```

## Uptime Monitoring

### Multi-Region Uptime Monitoring with SLA Tracking

```python
def create_uptime_monitoring_workflow():
    """
    Monitors service uptime from multiple regions with SLA compliance tracking.
    """
    workflow = WorkflowBuilder()

    # Uptime configuration
    uptime_config = PythonCodeNode(
        name="uptime_config",
        code="""
from datetime import datetime, timedelta

# Services to monitor with SLA targets
services = [
    {
        "name": "Main Website",
        "url": "https://www.example.com",
        "sla_target": 99.9,  # Three nines
        "check_interval": 60,  # seconds
        "timeout": 10
    },
    {
        "name": "API Service",
        "url": "https://api.example.com/health",
        "sla_target": 99.95,  # Higher SLA for API
        "check_interval": 30,
        "timeout": 5
    },
    {
        "name": "Admin Portal",
        "url": "https://admin.example.com",
        "sla_target": 99.5,
        "check_interval": 120,
        "timeout": 10
    },
    {
        "name": "Mobile API",
        "url": "https://mobile-api.example.com/health",
        "sla_target": 99.9,
        "check_interval": 30,
        "timeout": 5
    }
]

# Monitor from multiple regions
regions = [
    {"name": "us-east-1", "location": "Virginia"},
    {"name": "eu-west-1", "location": "Ireland"},
    {"name": "ap-southeast-1", "location": "Singapore"},
    {"name": "us-west-2", "location": "Oregon"}
]

# Calculate time windows
now = datetime.now()
result = {
    "services": services,
    "regions": regions,
    "check_time": now.isoformat(),
    "sla_window": {
        "daily": (now - timedelta(days=1)).isoformat(),
        "weekly": (now - timedelta(days=7)).isoformat(),
        "monthly": (now - timedelta(days=30)).isoformat()
    }
}
"""
    )
    workflow.add_node("PythonCodeNode", "uptime_config", {"code": uptime_config.code})

    # Multi-region uptime checker
    uptime_checker = PythonCodeNode(
        name="uptime_checker",
        code="""
import asyncio
import aiohttp
import time
from datetime import datetime
import random  # Simulating region checks

async def check_from_region(session, service, region):
    start_time = time.time()

    # Simulate regional checks (in production, would use regional endpoints)
    # Add slight variation by region to simulate network differences
    region_latency = {
        "us-east-1": 0,
        "eu-west-1": 50,
        "ap-southeast-1": 100,
        "us-west-2": 30
    }

    try:
        # Simulate check with 95% success rate
        if random.random() < 0.95:
            response_time = random.uniform(50, 300) + region_latency.get(region["name"], 0)
            await asyncio.sleep(response_time / 1000)  # Simulate network delay

            return {
                "service": service["name"],
                "region": region["name"],
                "status": "up",
                "response_time": round(response_time, 2),
                "status_code": 200,
                "checked_at": datetime.now().isoformat()
            }
        else:
            # Simulate various failure modes
            failure_type = random.choice(["timeout", "500", "503", "connection_error"])
            return {
                "service": service["name"],
                "region": region["name"],
                "status": "down",
                "error": failure_type,
                "checked_at": datetime.now().isoformat()
            }

    except Exception as e:
        return {
            "service": service["name"],
            "region": region["name"],
            "status": "down",
            "error": str(e),
            "checked_at": datetime.now().isoformat()
        }

async def check_all_services():
    services = input_data["services"]
    regions = input_data["regions"]

    # Check all services from all regions
    async with aiohttp.ClientSession() as session:
        tasks = []
        for service in services:
            for region in regions:
                tasks.append(check_from_region(session, service, region))

        results = await asyncio.gather(*tasks)

    # Aggregate results by service
    service_results = {}
    for service in services:
        service_name = service["name"]
        service_checks = [r for r in results if r["service"] == service_name]

        # Calculate uptime (majority voting across regions)
        up_count = len([c for c in service_checks if c["status"] == "up"])
        total_count = len(service_checks)

        # Service is considered up if majority of regions report it as up
        is_up = up_count > total_count / 2

        # Average response time from successful checks
        successful_checks = [c for c in service_checks if c["status"] == "up"]
        avg_response_time = (
            sum(c.get("response_time", 0) for c in successful_checks) / len(successful_checks)
            if successful_checks else 0
        )

        service_results[service_name] = {
            "current_status": "up" if is_up else "down",
            "regions_up": up_count,
            "regions_total": total_count,
            "availability_percentage": round((up_count / total_count) * 100, 2),
            "avg_response_time": round(avg_response_time, 2),
            "regional_status": service_checks,
            "sla_target": service["sla_target"]
        }

    # Calculate historical uptime (simulated)
    historical_uptime = {}
    for service in services:
        # Simulate historical data
        daily_uptime = random.uniform(99.0, 100.0)
        weekly_uptime = random.uniform(99.0, 100.0)
        monthly_uptime = random.uniform(98.5, 100.0)

        historical_uptime[service["name"]] = {
            "daily": round(daily_uptime, 3),
            "weekly": round(weekly_uptime, 3),
            "monthly": round(monthly_uptime, 3),
            "sla_compliant": {
                "daily": daily_uptime >= service["sla_target"],
                "weekly": weekly_uptime >= service["sla_target"],
                "monthly": monthly_uptime >= service["sla_target"]
            }
        }

    result = {
        "current_status": service_results,
        "historical_uptime": historical_uptime,
        "check_results": results,
        "summary": {
            "total_services": len(services),
            "services_up": len([s for s in service_results.values() if s["current_status"] == "up"]),
            "services_down": len([s for s in service_results.values() if s["current_status"] == "down"]),
            "check_time": input_data["check_time"]
        }
    }

# Execute
try:
    import nest_asyncio
    nest_asyncio.apply()
except:
    pass

loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)
result = loop.run_until_complete(check_all_services())
loop.close()
"""
    )
    workflow.add_node("PythonCodeNode", "uptime_checker", {"code": uptime_checker.code})
    workflow.add_connection("uptime_config", "result", "uptime_checker", "input")

    # SLA compliance analyzer
    sla_analyzer = PythonCodeNode(
        name="sla_analyzer",
        code="""
from datetime import datetime

uptime_data = input_data

analysis = {
    "timestamp": datetime.now().isoformat(),
    "sla_compliance": {},
    "alerts": [],
    "recommendations": []
}

# Analyze SLA compliance
for service_name, data in uptime_data["current_status"].items():
    historical = uptime_data["historical_uptime"][service_name]

    # Check current status
    if data["current_status"] == "down":
        analysis["alerts"].append({
            "type": "service_down",
            "severity": "critical",
            "service": service_name,
            "message": f"{service_name} is currently DOWN in {data['regions_total'] - data['regions_up']} regions",
            "affected_regions": [
                r["region"] for r in data["regional_status"] if r["status"] == "down"
            ]
        })

    # Check SLA compliance
    sla_status = {
        "daily": historical["sla_compliant"]["daily"],
        "weekly": historical["sla_compliant"]["weekly"],
        "monthly": historical["sla_compliant"]["monthly"],
        "current_availability": data["availability_percentage"]
    }

    analysis["sla_compliance"][service_name] = sla_status

    # Generate alerts for SLA violations
    if not historical["sla_compliant"]["monthly"]:
        analysis["alerts"].append({
            "type": "sla_violation",
            "severity": "high",
            "service": service_name,
            "message": f"{service_name} SLA violation: {historical['monthly']}% (target: {data['sla_target']}%)",
            "period": "monthly"
        })
    elif not historical["sla_compliant"]["weekly"]:
        analysis["alerts"].append({
            "type": "sla_warning",
            "severity": "medium",
            "service": service_name,
            "message": f"{service_name} approaching SLA limit: {historical['weekly']}% (target: {data['sla_target']}%)",
            "period": "weekly"
        })

    # Performance recommendations
    if data["avg_response_time"] > 500:
        analysis["recommendations"].append({
            "service": service_name,
            "type": "performance",
            "recommendation": f"Optimize {service_name} - average response time is {data['avg_response_time']}ms",
            "priority": "medium"
        })

    # Regional issues
    regional_failures = [r for r in data["regional_status"] if r["status"] == "down"]
    if 0 < len(regional_failures) < data["regions_total"]:
        affected_regions = [r["region"] for r in regional_failures]
        analysis["recommendations"].append({
            "service": service_name,
            "type": "regional",
            "recommendation": f"Investigate regional issues for {service_name} in: {', '.join(affected_regions)}",
            "priority": "high"
        })

# Calculate overall system availability
total_monthly_uptime = sum(
    h["monthly"] for h in uptime_data["historical_uptime"].values()
) / len(uptime_data["historical_uptime"])

analysis["overall_availability"] = {
    "monthly_average": round(total_monthly_uptime, 3),
    "services_meeting_sla": len([
        s for s in analysis["sla_compliance"].values()
        if s["monthly"]
    ]),
    "total_services": len(analysis["sla_compliance"])
}

# Prioritize alerts
critical_alerts = [a for a in analysis["alerts"] if a["severity"] == "critical"]
analysis["requires_immediate_action"] = len(critical_alerts) > 0

result = {
    "analysis": analysis,
    "uptime_data": uptime_data,
    "dashboard_url": "https://status.example.com"
}
"""
    )
    workflow.add_node("PythonCodeNode", "sla_analyzer", {"code": sla_analyzer.code})
    workflow.add_connection("uptime_checker", "result", "sla_analyzer", "input")

    return workflow

```

## Production Dashboards

### Comprehensive Production Monitoring Dashboard

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
def create_production_dashboard_workflow():
    """
    Unified dashboard workflow that combines all monitoring data into actionable insights.
    """
    workflow = WorkflowBuilder()

    # Dashboard configuration
    dashboard_config = PythonCodeNode(
        name="dashboard_config",
        code="""
from datetime import datetime

# Define dashboard components
components = {
    "health_check": {
        "enabled": True,
        "refresh_interval": 60,
        "priority": "critical"
    },
    "performance_metrics": {
        "enabled": True,
        "refresh_interval": 30,
        "priority": "high"
    },
    "system_resources": {
        "enabled": True,
        "refresh_interval": 120,
        "priority": "medium"
    },
    "log_analysis": {
        "enabled": True,
        "refresh_interval": 300,
        "priority": "medium"
    },
    "uptime_sla": {
        "enabled": True,
        "refresh_interval": 300,
        "priority": "high"
    },
    "alerts": {
        "enabled": True,
        "refresh_interval": 10,
        "priority": "critical"
    }
}

# Define thresholds for dashboard status
dashboard_thresholds = {
    "critical_alerts_max": 0,
    "high_alerts_max": 2,
    "error_rate_max": 0.05,
    "uptime_min": 99.5,
    "response_time_max": 500
}

result = {
    "components": components,
    "thresholds": dashboard_thresholds,
    "dashboard_time": datetime.now().isoformat(),
    "dashboard_version": "2.0"
}
"""
    )
    workflow.add_node("PythonCodeNode", "dashboard_config", {"code": dashboard_config.code})

    # Collect all monitoring data (would run sub-workflows in production)
    data_collector = PythonCodeNode(
        name="data_collector",
        code="""
import random
from datetime import datetime, timedelta

# Simulate collecting data from various monitoring workflows
# In production, this would call the actual monitoring workflows

# Health check data
health_data = {
    "overall_status": "healthy" if random.random() > 0.1 else "unhealthy",
    "services": {
        "api_gateway": {"status": "healthy", "response_time": random.uniform(50, 200)},
        "database": {"status": "healthy", "response_time": random.uniform(10, 50)},
        "cache": {"status": "healthy" if random.random() > 0.05 else "unhealthy", "response_time": random.uniform(1, 10)},
        "auth_service": {"status": "healthy", "response_time": random.uniform(20, 100)}
    }
}

# Performance metrics
performance_data = {
    "avg_response_time": random.uniform(100, 400),
    "requests_per_second": random.uniform(1000, 5000),
    "error_rate": random.uniform(0, 0.05),
    "cpu_usage": random.uniform(40, 80),
    "memory_usage": random.uniform(50, 85)
}

# System resources
system_data = {
    "fleet_health": {
        "application": {"count": 10, "healthy": 9 + int(random.random() > 0.3)},
        "database": {"count": 3, "healthy": 3},
        "cache": {"count": 4, "healthy": 4},
        "load_balancer": {"count": 2, "healthy": 2}
    }
}

# Log analysis
log_data = {
    "error_count": random.randint(0, 50),
    "warning_count": random.randint(10, 100),
    "anomalies": random.randint(0, 3),
    "top_errors": [
        "Connection timeout",
        "Invalid authentication token",
        "Database connection pool exhausted"
    ][:random.randint(0, 3)]
}

# Uptime/SLA
uptime_data = {
    "current_uptime": random.uniform(99.0, 100.0),
    "monthly_uptime": random.uniform(99.5, 99.99),
    "sla_compliant": random.random() > 0.2,
    "services_down": 0 if random.random() > 0.1 else 1
}

# Active alerts
alerts = []
if random.random() > 0.7:
    alerts.append({
        "type": "performance",
        "severity": "warning",
        "message": "Response time elevated",
        "service": "api_gateway"
    })
if random.random() > 0.9:
    alerts.append({
        "type": "error_rate",
        "severity": "critical",
        "message": "Error rate above threshold",
        "service": "payment_service"
    })

result = {
    "health": health_data,
    "performance": performance_data,
    "system": system_data,
    "logs": log_data,
    "uptime": uptime_data,
    "alerts": alerts,
    "collection_time": datetime.now().isoformat()
}
"""
    )
    workflow.add_node("PythonCodeNode", "data_collector", {"code": data_collector.code})
    workflow.add_connection("dashboard_config", "result", "data_collector", "input")

    # Dashboard analyzer and formatter
    dashboard_analyzer = PythonCodeNode(
        name="dashboard_analyzer",
        code="""
from datetime import datetime
import json

config = input_data["components"]
thresholds = input_data["thresholds"]
data = input_data

# Calculate overall system status
status_scores = {
    "health": 100,
    "performance": 100,
    "reliability": 100,
    "capacity": 100
}

# Health score
unhealthy_services = [
    s for s, d in data["health"]["services"].items()
    if d["status"] != "healthy"
]
status_scores["health"] -= len(unhealthy_services) * 25

# Performance score
if data["performance"]["avg_response_time"] > thresholds["response_time_max"]:
    status_scores["performance"] -= 30
if data["performance"]["error_rate"] > thresholds["error_rate_max"]:
    status_scores["performance"] -= 40

# Reliability score
if data["uptime"]["current_uptime"] < thresholds["uptime_min"]:
    status_scores["reliability"] -= 50
if not data["uptime"]["sla_compliant"]:
    status_scores["reliability"] -= 30

# Capacity score
if data["performance"]["cpu_usage"] > 80:
    status_scores["capacity"] -= 20
if data["performance"]["memory_usage"] > 85:
    status_scores["capacity"] -= 20

# Overall status
overall_score = sum(status_scores.values()) / len(status_scores)
overall_status = "healthy" if overall_score > 80 else "degraded" if overall_score > 60 else "critical"

# Alert summary
critical_alerts = [a for a in data["alerts"] if a["severity"] == "critical"]
high_alerts = [a for a in data["alerts"] if a["severity"] == "high"]
warning_alerts = [a for a in data["alerts"] if a["severity"] == "warning"]

# Generate dashboard
dashboard = {
    "metadata": {
        "generated_at": datetime.now().isoformat(),
        "version": input_data["dashboard_version"],
        "refresh_needed": any(
            a["severity"] == "critical" for a in data["alerts"]
        )
    },
    "overall_status": {
        "status": overall_status,
        "score": round(overall_score, 2),
        "scores": {k: round(v, 2) for k, v in status_scores.items()}
    },
    "key_metrics": {
        "uptime": f"{data['uptime']['current_uptime']:.2f}%",
        "response_time": f"{data['performance']['avg_response_time']:.0f}ms",
        "error_rate": f"{data['performance']['error_rate']*100:.2f}%",
        "requests_per_second": f"{data['performance']['requests_per_second']:.0f}",
        "services_healthy": f"{len(data['health']['services']) - len(unhealthy_services)}/{len(data['health']['services'])}"
    },
    "alerts_summary": {
        "critical": len(critical_alerts),
        "high": len(high_alerts),
        "warning": len(warning_alerts),
        "total": len(data["alerts"])
    },
    "components_status": {
        "health_check": {
            "status": "healthy" if len(unhealthy_services) == 0 else "unhealthy",
            "details": f"{len(unhealthy_services)} services unhealthy" if unhealthy_services else "All services healthy"
        },
        "performance": {
            "status": "good" if status_scores["performance"] > 80 else "degraded",
            "details": f"Avg response time: {data['performance']['avg_response_time']:.0f}ms"
        },
        "system_resources": {
            "status": "good" if status_scores["capacity"] > 80 else "warning",
            "details": f"CPU: {data['performance']['cpu_usage']:.0f}%, Memory: {data['performance']['memory_usage']:.0f}%"
        },
        "logs": {
            "status": "normal" if data["logs"]["anomalies"] == 0 else "anomalies_detected",
            "details": f"{data['logs']['error_count']} errors, {data['logs']['anomalies']} anomalies"
        },
        "uptime": {
            "status": "compliant" if data["uptime"]["sla_compliant"] else "violation",
            "details": f"Monthly: {data['uptime']['monthly_uptime']:.2f}%"
        }
    },
    "action_items": [],
    "trends": {
        "performance": "stable",  # Would calculate from historical data
        "errors": "increasing" if data["logs"]["error_count"] > 20 else "stable",
        "capacity": "adequate" if status_scores["capacity"] > 70 else "concerning"
    }
}

# Generate action items
if overall_status == "critical":
    dashboard["action_items"].append({
        "priority": "immediate",
        "action": "Investigate critical system issues",
        "reason": f"System status is {overall_status}"
    })

if critical_alerts:
    dashboard["action_items"].append({
        "priority": "immediate",
        "action": "Address critical alerts",
        "alerts": critical_alerts
    })

if not data["uptime"]["sla_compliant"]:
    dashboard["action_items"].append({
        "priority": "high",
        "action": "Review SLA compliance",
        "reason": "Monthly SLA target not met"
    })

if data["performance"]["cpu_usage"] > 80:
    dashboard["action_items"].append({
        "priority": "medium",
        "action": "Plan capacity increase",
        "reason": f"CPU usage at {data['performance']['cpu_usage']:.0f}%"
    })

# Dashboard visualization data
dashboard["visualizations"] = {
    "status_grid": {
        "type": "grid",
        "data": dashboard["components_status"]
    },
    "metrics_chart": {
        "type": "timeseries",
        "data": dashboard["key_metrics"]
    },
    "alerts_feed": {
        "type": "feed",
        "data": data["alerts"]
    },
    "health_map": {
        "type": "service_map",
        "data": data["health"]["services"]
    }
}

result = {
    "dashboard": dashboard,
    "raw_data": data,
    "requires_attention": overall_status != "healthy" or len(critical_alerts) > 0
}
"""
    )
    workflow.add_node("PythonCodeNode", "dashboard_analyzer", {"code": dashboard_analyzer.code})
    workflow.add_connection("data_collector", "result", "dashboard_analyzer", "input")

    # Dashboard publisher
    dashboard_publisher = PythonCodeNode(
        name="dashboard_publisher",
        code="""
import json
from datetime import datetime

dashboard_data = input_data

# Format for different output channels
outputs = []

# Web dashboard JSON
web_output = {
    "channel": "web",
    "endpoint": "https://dashboard.example.com/api/update",
    "payload": dashboard_data["dashboard"],
    "published_at": datetime.now().isoformat()
}
outputs.append(web_output)

# Slack summary (if critical issues)
if dashboard_data["requires_attention"]:
    slack_summary = f"""
🚨 *Production Dashboard Alert*

*Overall Status:* {dashboard_data['dashboard']['overall_status']['status'].upper()}
*Score:* {dashboard_data['dashboard']['overall_status']['score']}/100

*Key Metrics:*
• Uptime: {dashboard_data['dashboard']['key_metrics']['uptime']}
• Response Time: {dashboard_data['dashboard']['key_metrics']['response_time']}
• Error Rate: {dashboard_data['dashboard']['key_metrics']['error_rate']}

*Alerts:* {dashboard_data['dashboard']['alerts_summary']['total']} active
• Critical: {dashboard_data['dashboard']['alerts_summary']['critical']}
• High: {dashboard_data['dashboard']['alerts_summary']['high']}

*Action Required:* {len(dashboard_data['dashboard']['action_items'])} items
"""

    for item in dashboard_data['dashboard']['action_items'][:3]:  # Top 3
        slack_summary += f"\\n• [{item['priority'].upper()}] {item['action']}"

    slack_output = {
        "channel": "slack",
        "webhook": "https://hooks.slack.com/services/xxx",
        "payload": {
            "text": slack_summary,
            "channel": "#prod-alerts"
        },
        "published_at": datetime.now().isoformat()
    }
    outputs.append(slack_output)

# Email report (daily summary)
email_output = {
    "channel": "email",
    "recipients": ["sre-team@example.com"],
    "subject": f"Production Dashboard - {datetime.now().strftime('%Y-%m-%d')}",
    "body": json.dumps(dashboard_data["dashboard"], indent=2),
    "published_at": datetime.now().isoformat()
}
outputs.append(email_output)

# Metrics for monitoring the monitoring system
meta_metrics = {
    "dashboard_generation_time": 0.5,  # seconds
    "data_freshness": "current",
    "components_checked": len(dashboard_data["dashboard"]["components_status"]),
    "alerts_processed": dashboard_data["dashboard"]["alerts_summary"]["total"]
}

result = {
    "outputs": outputs,
    "meta_metrics": meta_metrics,
    "dashboard_url": "https://dashboard.example.com",
    "api_endpoints": {
        "current": "https://api.example.com/dashboard/current",
        "historical": "https://api.example.com/dashboard/history",
        "alerts": "https://api.example.com/dashboard/alerts"
    },
    "next_refresh": datetime.now().isoformat()
}
"""
    )
    workflow.add_node("PythonCodeNode", "dashboard_publisher", {"code": dashboard_publisher.code})
    workflow.add_connection("dashboard_analyzer", "result", "dashboard_publisher", "input")

    return workflow

# Example usage of all monitoring workflows
if __name__ == "__main__":
    runtime = LocalRuntime()

    # Run health check
    print("=== HEALTH CHECK ===")
    health_workflow = create_health_check_workflow()
    health_results, run_id = runtime.execute(health_workflow.build())
    print(json.dumps(health_results["results_merger"], indent=2))

    # Run performance monitoring
    print("\\n=== PERFORMANCE MONITORING ===")
    perf_workflow = create_performance_tracking_workflow()
    perf_results, run_id = runtime.execute(perf_workflow.build())
    print(json.dumps(perf_results["performance_analyzer"]["analysis"], indent=2))

    # Run production dashboard
    print("\\n=== PRODUCTION DASHBOARD ===")
    dashboard_workflow = create_production_dashboard_workflow()
    dashboard_results, run_id = runtime.execute(dashboard_workflow.build())
    print(json.dumps(dashboard_results["dashboard_publisher"]["dashboard_url"], indent=2))

```

## Best Practices and Implementation Notes

### 1. Error Handling
- Always implement comprehensive try-except blocks
- Use exponential backoff for retries
- Log all errors with context for debugging
- Implement circuit breakers for external services

### 2. Performance Optimization
- Use async operations for concurrent checks
- Implement caching for frequently accessed data
- Batch API calls where possible
- Use connection pooling for database/HTTP connections

### 3. Alerting Strategy
- Implement alert deduplication to prevent spam
- Use severity levels appropriately
- Include runbooks in critical alerts
- Implement escalation policies

### 4. Data Retention
- Store raw metrics for debugging
- Aggregate older data to save space
- Implement data lifecycle policies
- Use time-series databases for metrics

### 5. Security Considerations
- Use secure connections (HTTPS/TLS)
- Implement authentication for monitoring endpoints
- Sanitize sensitive data in logs
- Use service accounts with minimal permissions

### 6. Scalability
- Design for horizontal scaling
- Use message queues for decoupling
- Implement rate limiting
- Consider regional distribution

### 7. Integration Tips
- Standardize metric formats
- Use common tagging strategies
- Implement webhook receivers
- Support multiple output formats

This comprehensive guide provides production-ready monitoring patterns that can be adapted to specific infrastructure needs and scaled according to requirements.
