# Kaizen AI - Production Monitoring

This directory contains the complete monitoring stack for Kaizen AI in production environments.

## Components

- **Prometheus**: Metrics collection and alerting
- **Grafana**: Visualization and dashboards
- **Alertmanager**: Alert routing and notification

## Quick Start

### 1. Start Monitoring Stack

```bash
cd monitoring
docker-compose up -d
```

### 2. Access Dashboards

- **Grafana**: http://localhost:3000
  - Username: `admin`
  - Password: `admin` (change on first login)
- **Prometheus**: http://localhost:9090
- **Alertmanager**: http://localhost:9093

### 3. Configure Kaizen Application

Ensure your Kaizen application exposes metrics on port 9090:

```python
from kaizen.production.metrics import MetricsCollector
from kaizen.production.health import HealthCheck

# Initialize metrics
metrics = MetricsCollector()

# Track operations
metrics.track_request("qa_agent", "success")
metrics.track_duration("qa_agent", 0.5)

# Expose metrics endpoint
from flask import Flask
app = Flask(__name__)

@app.route('/metrics')
def metrics_endpoint():
    return metrics.export_prometheus(), 200, {'Content-Type': 'text/plain'}

@app.route('/health')
def health_endpoint():
    health = HealthCheck()
    return health.check()
```

## Metrics Available

### RED Metrics (Rate, Errors, Duration)

- **kaizen_requests_total**: Total number of requests by agent type and status
- **kaizen_errors_total**: Total number of errors by agent type and error type
- **kaizen_request_duration_seconds**: Request duration histogram

### Custom Metrics

You can define custom gauge metrics:

```python
metrics.define_gauge("active_agents", "Number of active agents")
metrics.set_gauge("active_agents", 5)
```

## Alerts Configured

### Warning Alerts (5min threshold)
- **HighErrorRate**: Error rate > 5%
- **HighLatency**: P95 latency > 5 seconds
- **LowRequestRate**: Request rate < 0.1 req/s

### Critical Alerts (2min threshold)
- **CriticalErrorRate**: Error rate > 20%
- **VeryHighLatency**: P95 latency > 10 seconds
- **ServiceDown**: Service unreachable

## Dashboards

### Kaizen AI - Production Overview

Located at: `grafana/dashboards/kaizen-overview.json`

Panels:
1. **Request Rate**: Requests per second by agent type
2. **Error Rate**: Errors per second by agent type and error type
3. **Request Duration**: P50, P95, P99 latency percentiles
4. **Success Rate**: Overall success rate percentage
5. **Total Requests**: Request count in last 5 minutes
6. **Active Agents**: Number of currently active agents

## Customization

### Adding New Alerts

Edit `prometheus/alerts.yml`:

```yaml
- alert: CustomAlert
  expr: your_metric > threshold
  for: 5m
  labels:
    severity: warning
  annotations:
    summary: "Alert summary"
    description: "Alert description"
```

### Adding New Dashboards

1. Create dashboard in Grafana UI
2. Export as JSON
3. Save to `grafana/dashboards/`
4. Restart Grafana: `docker-compose restart grafana`

### Configuring Alertmanager

Edit `alertmanager/alertmanager.yml` to configure notification channels (email, Slack, PagerDuty, etc.)

## Production Deployment

### Kubernetes

See `../k8s/` directory for Kubernetes manifests that include:
- Service monitors for Prometheus
- Grafana deployment with persistent storage
- Alertmanager configuration

### Security

For production:
1. Change default Grafana password
2. Enable TLS for all services
3. Configure authentication (OAuth, LDAP)
4. Restrict network access using network policies
5. Enable audit logging

## Troubleshooting

### Prometheus Not Scraping Kaizen

1. Check Kaizen service is exposing `/metrics` endpoint
2. Verify network connectivity: `docker-compose exec prometheus wget -O- kaizen:9090/metrics`
3. Check Prometheus targets: http://localhost:9090/targets

### Grafana Not Showing Data

1. Verify Prometheus datasource is configured
2. Check Prometheus is receiving data: http://localhost:9090/graph
3. Check dashboard query syntax

### Alerts Not Firing

1. Check alert rules: http://localhost:9090/alerts
2. Verify Alertmanager is running: http://localhost:9093
3. Check Alertmanager configuration in `prometheus/prometheus.yml`

## References

- [Prometheus Documentation](https://prometheus.io/docs/)
- [Grafana Documentation](https://grafana.com/docs/)
- [Alertmanager Documentation](https://prometheus.io/docs/alerting/latest/alertmanager/)
