# Enterprise Monitoring Stack

This directory contains a production-ready monitoring stack built on Prometheus, Grafana, and AlertManager, designed for Kubernetes environments.

## 🏗️ Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                      Monitoring Stack                            │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────┐     ┌──────────────┐     ┌──────────────┐   │
│  │  Prometheus  │────▶│ AlertManager │────▶│   PagerDuty  │   │
│  │   (2 pods)   │     │   (3 pods)   │     │    Slack     │   │
│  └──────────────┘     └──────────────┘     │    Email     │   │
│         │                                   └──────────────┘   │
│         │                                                        │
│         ▼                                                        │
│  ┌──────────────┐     ┌──────────────┐     ┌──────────────┐   │
│  │   Grafana    │     │     Loki     │     │    Tempo     │   │
│  │   (2 pods)   │     │  (optional)  │     │  (optional)  │   │
│  └──────────────┘     └──────────────┘     └──────────────┘   │
│         │                                                        │
│         ▼                                                        │
│  ┌────────────────────────────────────────────────────────┐    │
│  │                    Service Monitors                      │    │
│  ├────────────────────────────────────────────────────────┤    │
│  │ • kube-state-metrics  • node-exporter  • kubelet       │    │
│  │ • ingress-nginx       • cert-manager   • applications  │    │
│  └────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────┘
```

## 📁 Directory Structure

```
monitoring/
├── kustomization.yaml              # Kustomize configuration
├── namespace.yaml                  # Monitoring namespace and policies
├── README.md                       # This file
│
├── prometheus/                     # Prometheus configuration
│   ├── prometheus.yaml            # Prometheus CRD configuration
│   ├── service-monitor-default.yaml
│   └── prometheus-rules.yaml
│
├── grafana/                       # Grafana configuration
│   ├── deployment.yaml
│   ├── service.yaml
│   ├── configmap-datasources.yaml
│   ├── configmap-dashboards.yaml
│   └── configmap-dashboard-providers.yaml
│
├── alertmanager/                  # AlertManager configuration
│   ├── alertmanager.yaml
│   ├── configmap.yaml
│   └── service.yaml
│
├── dashboards/                    # Grafana dashboards (JSON)
│   ├── kubernetes-cluster.json
│   ├── kubernetes-pods.json
│   ├── nginx-ingress.json
│   ├── postgresql.json
│   ├── redis.json
│   └── application-metrics.json
│
├── rules/                         # Prometheus alert rules
│   ├── kubernetes-alerts.yaml
│   ├── application-alerts.yaml
│   └── infrastructure-alerts.yaml
│
└── service-monitors/              # Service monitor definitions
    ├── kube-state-metrics.yaml
    ├── node-exporter.yaml
    └── kubelet.yaml
```

## 🚀 Quick Start

### Prerequisites

1. **Kubernetes cluster** with:
   - Prometheus Operator CRDs installed
   - Storage classes configured
   - Ingress controller deployed

2. **Required tools**:
   ```bash
   # Kustomize
   kubectl kustomize version
   
   # Helm (for dependencies)
   helm version
   ```

### Deploy Monitoring Stack

1. **Deploy Prometheus Operator**:
   ```bash
   # Using Kustomize (included in kustomization.yaml)
   kubectl apply -k deployment/monitoring/
   
   # Or using Helm
   helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
   helm install prometheus-operator prometheus-community/kube-prometheus-stack \
     --namespace monitoring \
     --create-namespace
   ```

2. **Configure secrets**:
   ```bash
   # Create Grafana admin password
   kubectl create secret generic grafana-admin \
     --namespace monitoring \
     --from-literal=admin-user=admin \
     --from-literal=admin-password=$(openssl rand -base64 32)
   
   # Create AlertManager configuration
   kubectl create secret generic alertmanager-config \
     --namespace monitoring \
     --from-file=alertmanager.yaml=alertmanager/alertmanager-secret.yaml
   ```

3. **Deploy the stack**:
   ```bash
   # Deploy using Kustomize
   kubectl apply -k deployment/monitoring/
   
   # Verify deployment
   kubectl get pods -n monitoring
   kubectl get prometheus,alertmanager,servicemonitor -n monitoring
   ```

## 🔧 Configuration

### Prometheus Configuration

**Key settings** in `prometheus/prometheus.yaml`:
- **Retention**: 15 days (configurable)
- **Storage**: 50GB persistent volume
- **Replicas**: 2 for high availability
- **Resources**: 2GB RAM, 2 CPU cores

### Grafana Configuration

**Default credentials**:
- Username: `admin`
- Password: Retrieved from secret

**Pre-configured datasources**:
- Prometheus (default)
- AlertManager
- Loki (optional)
- Tempo (optional)
- PostgreSQL
- Redis

### AlertManager Configuration

**Alert routing example**:
```yaml
route:
  group_by: ['alertname', 'cluster', 'service']
  group_wait: 10s
  group_interval: 10s
  repeat_interval: 12h
  receiver: 'default'
  routes:
    - match:
        severity: critical
      receiver: pagerduty
    - match:
        severity: warning
      receiver: slack
```

## 📊 Dashboards

### Pre-built Dashboards

1. **Kubernetes Cluster Overview**
   - Node metrics
   - Resource utilization
   - Pod distribution

2. **Application Metrics**
   - Request rates
   - Error rates
   - Latency (RED metrics)

3. **Infrastructure**
   - PostgreSQL performance
   - Redis metrics
   - Ingress statistics

### Custom Dashboards

Add JSON files to `dashboards/` directory and they'll be automatically loaded.

## 🚨 Alert Rules

### Kubernetes Alerts
- Node down
- High CPU/memory usage
- Pod crash loops
- PVC almost full

### Application Alerts
- High error rate (>1%)
- Slow response time (>1s)
- Service unavailable

### Infrastructure Alerts
- Database connection pool exhausted
- Redis memory pressure
- Certificate expiration

## 🔒 Security

### Network Policies
- Restricted ingress/egress
- Namespace isolation
- Explicit service communication

### RBAC
- Minimal permissions
- Service accounts per component
- No cluster-admin usage

### Data Protection
- Encrypted storage
- TLS for all connections
- No sensitive data in ConfigMaps

## 📈 Scaling

### Horizontal Scaling
```yaml
# Increase Prometheus replicas
spec:
  replicas: 3
  
# Enable sharding
spec:
  shards: 2
```

### Vertical Scaling
```yaml
resources:
  requests:
    memory: 4Gi
    cpu: 2
  limits:
    memory: 8Gi
    cpu: 4
```

## 🔗 Integrations

### Expose Metrics

For applications to be monitored:

```yaml
apiVersion: v1
kind: Service
metadata:
  labels:
    prometheus: kailash  # Important!
  annotations:
    prometheus.io/scrape: "true"
    prometheus.io/port: "8080"
    prometheus.io/path: "/metrics"
```

### ServiceMonitor Example

```yaml
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata:
  name: myapp
  labels:
    prometheus: kailash  # Must match Prometheus selector
spec:
  selector:
    matchLabels:
      app: myapp
  endpoints:
    - port: metrics
      interval: 30s
```

## 🛠️ Troubleshooting

### Common Issues

1. **Prometheus not scraping targets**:
   ```bash
   # Check ServiceMonitor labels
   kubectl get servicemonitor -n monitoring --show-labels
   
   # Verify in Prometheus UI
   kubectl port-forward -n monitoring svc/prometheus 9090:9090
   # Visit http://localhost:9090/targets
   ```

2. **Grafana datasource errors**:
   ```bash
   # Check datasource configuration
   kubectl describe configmap grafana-datasources -n monitoring
   
   # Test connection in Grafana UI
   kubectl port-forward -n monitoring svc/grafana 3000:3000
   ```

3. **AlertManager not sending alerts**:
   ```bash
   # Check configuration
   kubectl logs -n monitoring alertmanager-0
   
   # Verify webhook URLs
   curl -X POST https://your-webhook-url/test
   ```

## 📝 Maintenance

### Backup Procedures

1. **Grafana dashboards**:
   ```bash
   # Export all dashboards
   kubectl exec -n monitoring grafana-0 -- \
     grafana-cli admin export-dashboard --all
   ```

2. **Prometheus data**:
   ```bash
   # Snapshot creation
   curl -X POST http://prometheus:9090/api/v1/admin/tsdb/snapshot
   ```

### Upgrade Process

1. **Test in staging first**
2. **Backup configurations**
3. **Rolling update**:
   ```bash
   kubectl set image deployment/grafana \
     grafana=grafana/grafana:10.2.3 \
     -n monitoring
   ```

## 🔍 Useful Commands

```bash
# View Prometheus targets
kubectl port-forward -n monitoring svc/prometheus 9090:9090

# Access Grafana
kubectl port-forward -n monitoring svc/grafana 3000:3000

# Check AlertManager
kubectl port-forward -n monitoring svc/alertmanager 9093:9093

# View logs
kubectl logs -n monitoring -l app.kubernetes.io/name=prometheus
kubectl logs -n monitoring -l app.kubernetes.io/name=grafana

# Get metrics
curl -s http://localhost:9090/api/v1/query?query=up

# Test alerts
curl -H "Content-Type: application/json" -d '[
  {
    "labels": {
      "alertname": "TestAlert",
      "severity": "info"
    }
  }
]' http://localhost:9093/api/v1/alerts
```

## 📚 References

- [Prometheus Documentation](https://prometheus.io/docs/)
- [Grafana Documentation](https://grafana.com/docs/)
- [AlertManager Documentation](https://prometheus.io/docs/alerting/latest/alertmanager/)
- [Prometheus Operator](https://github.com/prometheus-operator/prometheus-operator)