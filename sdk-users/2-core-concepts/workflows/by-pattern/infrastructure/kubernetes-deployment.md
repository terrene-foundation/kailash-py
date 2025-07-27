# Kubernetes Deployment Workflows

Deploy Kailash SDK workflows on Kubernetes for production-grade scalability and reliability.

## Basic Kubernetes Deployment

```python
"""Deploy workflow as Kubernetes Deployment"""
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.kubernetes import KubernetesRuntime

# Create API workflow
workflow = WorkflowBuilder()

# Add HTTP endpoint
workflow.add_node("HTTPEndpointNode", "endpoint", {})

# Kubernetes Deployment manifest
k8s_deployment = """
apiVersion: apps/v1
kind: Deployment
metadata:
  name: kailash-workflow-api
  labels:
    app: workflow-api
spec:
  replicas: 3
  selector:
    matchLabels:
      app: workflow-api
  template:
    metadata:
      labels:
        app: workflow-api
    spec:
      containers:
      - name: workflow
        image: myregistry/kailash-workflow:v1.0.0
        ports:
        - containerPort: 8000
        env:
        - name: WORKFLOW_ID
          value: "api-service"
        - name: DATABASE_URL
          valueFrom:
            secretKeyRef:
              name: workflow-secrets
              key: database-url
        resources:
          requests:
            memory: "256Mi"
            cpu: "250m"
          limits:
            memory: "512Mi"
            cpu: "500m"
        livenessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 30
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /ready
            port: 8000
          initialDelaySeconds: 5
          periodSeconds: 5
---
apiVersion: v1
kind: Service
metadata:
  name: workflow-api-service
spec:
  selector:
    app: workflow-api
  ports:
  - protocol: TCP
    port: 80
    targetPort: 8000
  type: LoadBalancer
"""

```

## Kubernetes Job for Batch Processing

```python
"""Batch processing with Kubernetes Jobs"""
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.kubernetes import KubernetesRuntime

workflow = WorkflowBuilder()

# Add batch processor
workflow.add_node("BatchProcessorNode", "processor", {})

# Kubernetes Job with CronJob
k8s_cronjob = """
apiVersion: batch/v1
kind: CronJob
metadata:
  name: workflow-batch-processor
spec:
  schedule: "0 2 * * *"  # Daily at 2 AM
  jobTemplate:
    spec:
      template:
        spec:
          containers:
          - name: batch-processor
            image: myregistry/kailash-batch:v1.0.0
            env:
            - name: WORKFLOW_CONFIG
              value: |
                {
                  "input_bucket": "s3://data-lake/raw",
                  "output_bucket": "s3://data-lake/processed",
                  "error_bucket": "s3://data-lake/errors"
                }
            volumeMounts:
            - name: workflow-config
              mountPath: /config
            resources:
              requests:
                memory: "2Gi"
                cpu: "1"
              limits:
                memory: "4Gi"
                cpu: "2"
          volumes:
          - name: workflow-config
            configMap:
              name: batch-config
          restartPolicy: OnFailure
      backoffLimit: 3
      activeDeadlineSeconds: 7200  # 2 hour timeout
"""

```

## Horizontal Pod Autoscaling

```python
"""Auto-scaling workflow deployment"""

# HPA configuration
hpa_config = """
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: workflow-api-hpa
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: kailash-workflow-api
  minReplicas: 2
  maxReplicas: 10
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 70
  - type: Resource
    resource:
      name: memory
      target:
        type: Utilization
        averageUtilization: 80
  - type: Pods
    pods:
      metric:
        name: workflow_queue_depth
      target:
        type: AverageValue
        averageValue: "100"
  behavior:
    scaleDown:
      stabilizationWindowSeconds: 300
      policies:
      - type: Percent
        value: 10
        periodSeconds: 60
    scaleUp:
      stabilizationWindowSeconds: 0
      policies:
      - type: Percent
        value: 100
        periodSeconds: 60
      - type: Pods
        value: 4
        periodSeconds: 60
      selectPolicy: Max
"""

# Workflow with metrics
from kailash.workflow.builder import WorkflowBuilder
from kailash.tracking import MetricsCollector

workflow = WorkflowBuilder()
metrics = MetricsCollector()

# Add metrics collection node
workflow.add_node("MetricsCollectorNode", "metrics_collector", {
    "metrics_path": "/metrics",
    "metrics_config": {
        "workflow_queue_depth": "queue_depth",
        "processing_rate": "processing_rate",
        "error_rate": "error_rate"
    }
})

```

## StatefulSet for Stateful Workflows

```python
"""Stateful workflow with persistent storage"""

statefulset_config = """
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: workflow-stateful
spec:
  serviceName: workflow-stateful-service
  replicas: 3
  selector:
    matchLabels:
      app: workflow-stateful
  template:
    metadata:
      labels:
        app: workflow-stateful
    spec:
      containers:
      - name: workflow
        image: myregistry/kailash-stateful:v1.0.0
        ports:
        - containerPort: 8000
        env:
        - name: POD_NAME
          valueFrom:
            fieldRef:
              fieldPath: metadata.name
        - name: WORKFLOW_STATE_PATH
          value: "/data/state"
        volumeMounts:
        - name: workflow-data
          mountPath: /data
        - name: shared-storage
          mountPath: /shared
      volumes:
      - name: shared-storage
        persistentVolumeClaim:
          claimName: shared-workflow-storage
  volumeClaimTemplates:
  - metadata:
      name: workflow-data
    spec:
      accessModes: ["ReadWriteOnce"]
      storageClassName: "fast-ssd"
      resources:
        requests:
          storage: 10Gi
"""

# Workflow with state management
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

workflow = WorkflowBuilder()

# Add stateful nodes
workflow.add_node("AccumulatorNode", "accumulator", {
    "checkpoint_interval": 100,
    "recovery_mode": "continue",
    "state_backend": "disk",
    "state_path": "/data/state"
})

```

## Service Mesh Integration

```python
"""Istio service mesh integration"""

# Istio VirtualService
istio_config = """
apiVersion: networking.istio.io/v1beta1
kind: VirtualService
metadata:
  name: workflow-routing
spec:
  hosts:
  - workflow.example.com
  http:
  - match:
    - headers:
        version:
          exact: v2
    route:
    - destination:
        host: workflow-api-service
        subset: v2
      weight: 100
  - route:
    - destination:
        host: workflow-api-service
        subset: v1
      weight: 90
    - destination:
        host: workflow-api-service
        subset: v2
      weight: 10
---
apiVersion: networking.istio.io/v1beta1
kind: DestinationRule
metadata:
  name: workflow-destination
spec:
  host: workflow-api-service
  subsets:
  - name: v1
    labels:
      version: v1
  - name: v2
    labels:
      version: v2
  trafficPolicy:
    connectionPool:
      tcp:
        maxConnections: 100
      http:
        http1MaxPendingRequests: 50
        http2MaxRequests: 100
    loadBalancer:
      consistentHash:
        httpCookie:
          name: "workflow-session"
          ttl: 3600s
"""

# Workflow with distributed tracing
from kailash.workflow.builder import WorkflowBuilder
from kailash.observability import TracingMiddleware

workflow = WorkflowBuilder()
# In production, configure tracing at runtime level
runtime = LocalRuntime(
    middleware=[TracingMiddleware(
        service_name="workflow-api",
        jaeger_endpoint="http://jaeger-collector:14268/api/traces"
    )]
)

```

## Multi-Environment Configuration

```python
"""Kustomize for multi-environment deployments"""

# base/kustomization.yaml
base_kustomization = """
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization

resources:
  - deployment.yaml
  - service.yaml
  - configmap.yaml

commonLabels:
  app: kailash-workflow

configMapGenerator:
  - name: workflow-config
    files:
      - workflow.yaml
"""

# overlays/production/kustomization.yaml
prod_kustomization = """
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization

bases:
  - ../../base

patchesStrategicMerge:
  - deployment-patch.yaml

replicas:
  - name: kailash-workflow-api
    count: 5

images:
  - name: myregistry/kailash-workflow
    newTag: v1.2.3

secretGenerator:
  - name: workflow-secrets
    envs:
      - secrets.env

namespace: production
"""

# Python configuration
import os
from kailash.workflow.builder import WorkflowBuilder
from kailash.config import KubernetesConfig

# Load environment-specific config
env = os.environ.get("ENVIRONMENT", "development")

config = KubernetesConfig(
    namespace=env,
    config_path=f"k8s/overlays/{env}",
    auto_reload=True
)

# Create workflow using standard builder
workflow = WorkflowBuilder()
# Configure workflow based on Kubernetes config
# Add nodes based on environment configuration

```

## Production Helm Chart

```yaml
# helm/kailash-workflow/values.yaml
replicaCount: 3

image:
  repository: myregistry/kailash-workflow
  pullPolicy: IfNotPresent
  tag: "v1.0.0"

service:
  type: ClusterIP
  port: 80

ingress:
  enabled: true
  className: "nginx"
  annotations:
    cert-manager.io/cluster-issuer: "letsencrypt-prod"
  hosts:
    - host: workflow.example.com
      paths:
        - path: /
          pathType: Prefix
  tls:
    - secretName: workflow-tls
      hosts:
        - workflow.example.com

resources:
  limits:
    cpu: 1000m
    memory: 1Gi
  requests:
    cpu: 500m
    memory: 512Mi

autoscaling:
  enabled: true
  minReplicas: 2
  maxReplicas: 10
  targetCPUUtilizationPercentage: 80

persistence:
  enabled: true
  storageClass: "fast-ssd"
  size: 10Gi

postgresql:
  enabled: true
  auth:
    database: workflows
    existingSecret: postgres-secret

redis:
  enabled: true
  auth:
    enabled: true
    existingSecret: redis-secret

monitoring:
  enabled: true
  serviceMonitor:
    enabled: true
  prometheusRule:
    enabled: true
```

## Monitoring and Observability

```python
"""Complete observability stack"""

# Prometheus ServiceMonitor
monitoring_config = """
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata:
  name: workflow-metrics
spec:
  selector:
    matchLabels:
      app: workflow-api
  endpoints:
  - port: metrics
    interval: 30s
    path: /metrics
---
apiVersion: monitoring.coreos.com/v1
kind: PrometheusRule
metadata:
  name: workflow-alerts
spec:
  groups:
  - name: workflow.rules
    interval: 30s
    rules:
    - alert: WorkflowHighErrorRate
      expr: rate(workflow_errors_total[5m]) > 0.05
      for: 10m
      labels:
        severity: warning
      annotations:
        summary: High error rate detected
    - alert: WorkflowHighLatency
      expr: histogram_quantile(0.95, workflow_duration_seconds_bucket) > 1
      for: 10m
      labels:
        severity: warning
"""

# Grafana Dashboard
from kailash.observability import GrafanaDashboard

dashboard = GrafanaDashboard(
    title="Kailash Workflow Metrics",
    refresh="30s"
)

dashboard.add_panel(
    title="Request Rate",
    query="rate(workflow_requests_total[5m])",
    panel_type="graph"
)

dashboard.add_panel(
    title="Error Rate",
    query="rate(workflow_errors_total[5m])",
    panel_type="graph",
    alert_threshold=0.05
)

dashboard.add_panel(
    title="P95 Latency",
    query="histogram_quantile(0.95, workflow_duration_seconds_bucket)",
    panel_type="graph"
)

dashboard.export_to_k8s_configmap("grafana-dashboards")

```

## Best Practices

1. **Resource Management**
   - Set appropriate resource requests/limits
   - Use PodDisruptionBudgets for availability
   - Implement proper health checks

2. **Security**
   - Use NetworkPolicies to restrict traffic
   - Store secrets in Kubernetes Secrets
   - Enable RBAC for service accounts
   - Use PodSecurityPolicies/Standards

3. **Scalability**
   - Use HPA for automatic scaling
   - Implement proper caching strategies
   - Design stateless workflows when possible

4. **Observability**
   - Export metrics to Prometheus
   - Use distributed tracing
   - Centralize logs with Fluentd/Fluent Bit
   - Create comprehensive dashboards

5. **Deployment Strategy**
   - Use GitOps with ArgoCD/Flux
   - Implement blue-green deployments
   - Use canary releases for safety
   - Automate with CI/CD pipelines
