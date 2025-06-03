"""Deployment Pattern Examples for Multi-Workflow Gateway.

This module demonstrates various deployment patterns for the Kailash
workflow gateway, from simple single-instance to complex Kubernetes deployments.
"""




def pattern_1_single_gateway():
    """Pattern 1: Single Gateway (Most Cases).

    Best for:
    - Small to medium deployments
    - All workflows have similar resource requirements
    - Simplicity is preferred
    """
    print("=== Pattern 1: Single Gateway (Recommended for Most Cases) ===\n")

    print("deployment/single_gateway.py:")
    print("-" * 60)
    print(
        """
from kailash.api.gateway import WorkflowAPIGateway
from workflows import (
    create_sales_workflow,
    create_analytics_workflow,
    create_reporting_workflow,
    create_ml_inference_workflow
)

def main():
    # Create single gateway instance
    gateway = WorkflowAPIGateway(
        title="Company Workflow Platform",
        description="All workflows in one place",
        max_workers=10  # Adjust based on expected load
    )
    
    # Register all workflows
    gateway.register_workflow("sales", create_sales_workflow())
    gateway.register_workflow("analytics", create_analytics_workflow())
    gateway.register_workflow("reporting", create_reporting_workflow())
    gateway.register_workflow("ml_inference", create_ml_inference_workflow())
    
    # Add MCP integration
    from mcp_tools import create_company_mcp_server
    mcp = create_company_mcp_server()
    gateway.register_mcp_server("tools", mcp)
    
    # Run on single port
    gateway.run(host="0.0.0.0", port=8000)

if __name__ == "__main__":
    main()
"""
    )

    print("\nDocker Compose Configuration:")
    print("-" * 60)
    print(
        """
# docker-compose.yml
version: '3.8'

services:
  gateway:
    build: .
    ports:
      - "8000:8000"
    environment:
      - WORKERS=10
      - LOG_LEVEL=INFO
    volumes:
      - ./data:/app/data
      - ./workflows:/app/workflows
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
"""
    )

    print("\nProduction Tips:")
    print("- Use environment variables for configuration")
    print("- Mount volumes for data persistence")
    print("- Set appropriate resource limits")
    print("- Enable health checks")


def pattern_2_hybrid_deployment():
    """Pattern 2: Gateway + Separate Services for Heavy Workloads.

    Best for:
    - Mix of lightweight and compute-intensive workflows
    - Need to scale different workflows independently
    - Isolation of resource-heavy processes
    """
    print("\n\n=== Pattern 2: Hybrid Deployment (Heavy Workloads) ===\n")

    print("deployment/hybrid_gateway.py:")
    print("-" * 60)
    print(
        """
from kailash.api.gateway import WorkflowAPIGateway
from kailash.api.workflow_api import WorkflowAPI
import multiprocessing

def run_ml_service():
    \"\"\"Run ML workflows in separate process.\"\"\"
    from workflows.ml_workflows import create_training_workflow, create_inference_workflow
    
    # Create dedicated API for ML workflows
    ml_gateway = WorkflowAPIGateway(
        title="ML Workflow Service",
        max_workers=4  # Fewer workers, but dedicated to ML
    )
    
    ml_gateway.register_workflow("train", create_training_workflow())
    ml_gateway.register_workflow("inference", create_inference_workflow())
    
    # Run on different port
    ml_gateway.run(host="0.0.0.0", port=8001)

def run_main_gateway():
    \"\"\"Run main gateway with lightweight workflows.\"\"\"
    gateway = WorkflowAPIGateway(
        title="Main Workflow Gateway",
        max_workers=20  # More workers for high-throughput workflows
    )
    
    # Register lightweight workflows
    from workflows.light_workflows import create_data_processing_workflow
    gateway.register_workflow("process", create_data_processing_workflow())
    
    # Proxy heavy workflows to ML service
    gateway.proxy_workflow(
        "ml_training",
        "http://ml-service:8001",
        health_check="/health",
        description="ML training workflows (proxied)"
    )
    
    gateway.run(host="0.0.0.0", port=8000)

if __name__ == "__main__":
    # Start ML service in separate process
    ml_process = multiprocessing.Process(target=run_ml_service)
    ml_process.start()
    
    # Run main gateway
    run_main_gateway()
"""
    )

    print("\nDocker Compose with Service Separation:")
    print("-" * 60)
    print(
        """
# docker-compose.yml
version: '3.8'

services:
  # Main gateway for lightweight workflows
  gateway:
    build: 
      context: .
      dockerfile: Dockerfile.gateway
    ports:
      - "8000:8000"
    environment:
      - SERVICE_TYPE=gateway
      - MAX_WORKERS=20
    depends_on:
      - ml-service
      - gpu-service

  # ML service with GPU support
  ml-service:
    build:
      context: .
      dockerfile: Dockerfile.ml
    ports:
      - "8001:8001"
    environment:
      - SERVICE_TYPE=ml
      - MAX_WORKERS=4
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]

  # Heavy computation service
  gpu-service:
    build:
      context: .
      dockerfile: Dockerfile.gpu
    ports:
      - "8002:8002"
    environment:
      - SERVICE_TYPE=gpu
      - MAX_WORKERS=2
    deploy:
      resources:
        limits:
          cpus: '4'
          memory: 16G
"""
    )

    print("\nNginx Configuration for Unified Access:")
    print("-" * 60)
    print(
        """
# nginx.conf
upstream gateway_backend {
    server gateway:8000;
}

upstream ml_backend {
    server ml-service:8001;
}

server {
    listen 80;
    
    # Route to main gateway
    location / {
        proxy_pass http://gateway_backend;
    }
    
    # Direct routes to ML service
    location /ml/ {
        proxy_pass http://ml_backend/;
    }
    
    # WebSocket support
    location /ws {
        proxy_pass http://gateway_backend;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
"""
    )


def pattern_3_high_availability():
    """Pattern 3: High Availability with Load Balancer.

    Best for:
    - Production environments requiring high uptime
    - Large scale deployments
    - Geographic distribution
    """
    print("\n\n=== Pattern 3: High Availability Deployment ===\n")

    print("deployment/ha_setup.py:")
    print("-" * 60)
    print(
        """
import os
from kailash.api.gateway import WorkflowAPIGateway

def create_gateway_instance():
    \"\"\"Create a gateway instance with instance-specific config.\"\"\"
    instance_id = os.environ.get('INSTANCE_ID', '1')
    
    gateway = WorkflowAPIGateway(
        title=f"Workflow Gateway Instance {instance_id}",
        max_workers=15
    )
    
    # Register all workflows
    from workflows import load_all_workflows
    for name, workflow in load_all_workflows().items():
        gateway.register_workflow(name, workflow)
    
    # Configure based on instance role
    if os.environ.get('PRIMARY_INSTANCE') == 'true':
        # Primary instance handles scheduled tasks
        from schedulers import setup_scheduled_workflows
        setup_scheduled_workflows(gateway)
    
    return gateway

def main():
    gateway = create_gateway_instance()
    
    # Use different ports for local testing
    port = 8000 + int(os.environ.get('INSTANCE_ID', '0'))
    
    gateway.run(host="0.0.0.0", port=port)

if __name__ == "__main__":
    main()
"""
    )

    print("\nHAProxy Load Balancer Configuration:")
    print("-" * 60)
    print(
        """
# haproxy.cfg
global
    maxconn 4096
    log stdout local0

defaults
    mode http
    timeout connect 5000ms
    timeout client 50000ms
    timeout server 50000ms
    option httplog

frontend gateway_frontend
    bind *:80
    
    # Health check endpoint
    acl health_check path /health
    
    # Sticky sessions for WebSocket
    stick-table type string len 32 size 100k expire 30m
    stick on cookie(session_id)
    
    default_backend gateway_backend

backend gateway_backend
    balance roundrobin
    option httpchk GET /health
    
    # Multiple gateway instances
    server gateway1 gateway1:8000 check weight 100
    server gateway2 gateway2:8000 check weight 100
    server gateway3 gateway3:8000 check weight 100
    
    # Backup instances
    server gateway4 gateway4:8000 check weight 50 backup
    server gateway5 gateway5:8000 check weight 50 backup
"""
    )

    print("\nDocker Swarm Deployment:")
    print("-" * 60)
    print(
        """
# docker-stack.yml
version: '3.8'

services:
  gateway:
    image: company/kailash-gateway:latest
    deploy:
      replicas: 5
      update_config:
        parallelism: 1
        delay: 10s
        failure_action: rollback
      restart_policy:
        condition: on-failure
        delay: 5s
        max_attempts: 3
      placement:
        constraints:
          - node.role == worker
        preferences:
          - spread: node.id
    environment:
      - REDIS_URL=redis://redis:6379
      - DB_URL=postgresql://db:5432/kailash
    networks:
      - gateway-net
      - data-net

  haproxy:
    image: haproxy:2.4
    ports:
      - "80:80"
      - "443:443"
    deploy:
      replicas: 2
      placement:
        constraints:
          - node.role == manager
    configs:
      - source: haproxy_config
        target: /usr/local/etc/haproxy/haproxy.cfg
    networks:
      - gateway-net

  redis:
    image: redis:7-alpine
    deploy:
      replicas: 1
    networks:
      - data-net

networks:
  gateway-net:
    driver: overlay
  data-net:
    driver: overlay
    
configs:
  haproxy_config:
    file: ./haproxy.cfg
"""
    )


def pattern_4_kubernetes():
    """Pattern 4: Kubernetes with Horizontal Pod Autoscaling.

    Best for:
    - Cloud-native environments
    - Automatic scaling based on load
    - Complex orchestration requirements
    """
    print("\n\n=== Pattern 4: Kubernetes Deployment ===\n")

    print("kubernetes/gateway-deployment.yaml:")
    print("-" * 60)
    print(
        """
apiVersion: apps/v1
kind: Deployment
metadata:
  name: kailash-gateway
  namespace: workflows
spec:
  replicas: 3
  selector:
    matchLabels:
      app: kailash-gateway
  template:
    metadata:
      labels:
        app: kailash-gateway
    spec:
      containers:
      - name: gateway
        image: company/kailash-gateway:v2.0.0
        ports:
        - containerPort: 8000
          name: http
        - containerPort: 8080
          name: metrics
        env:
        - name: MAX_WORKERS
          value: "15"
        - name: LOG_LEVEL
          value: "INFO"
        - name: REDIS_URL
          valueFrom:
            secretKeyRef:
              name: redis-secret
              key: url
        resources:
          requests:
            memory: "512Mi"
            cpu: "500m"
          limits:
            memory: "2Gi"
            cpu: "2000m"
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
        volumeMounts:
        - name: workflow-storage
          mountPath: /data
      volumes:
      - name: workflow-storage
        persistentVolumeClaim:
          claimName: workflow-pvc
---
apiVersion: v1
kind: Service
metadata:
  name: kailash-gateway
  namespace: workflows
spec:
  selector:
    app: kailash-gateway
  ports:
  - port: 80
    targetPort: 8000
    name: http
  type: ClusterIP
"""
    )

    print("\nHorizontal Pod Autoscaler:")
    print("-" * 60)
    print(
        """
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: kailash-gateway-hpa
  namespace: workflows
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: kailash-gateway
  minReplicas: 3
  maxReplicas: 20
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
        averageValue: "30"
  behavior:
    scaleDown:
      stabilizationWindowSeconds: 300
      policies:
      - type: Percent
        value: 50
        periodSeconds: 60
    scaleUp:
      stabilizationWindowSeconds: 60
      policies:
      - type: Percent
        value: 100
        periodSeconds: 60
      - type: Pods
        value: 4
        periodSeconds: 60
"""
    )

    print("\nIngress Configuration:")
    print("-" * 60)
    print(
        """
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: kailash-gateway-ingress
  namespace: workflows
  annotations:
    kubernetes.io/ingress.class: nginx
    cert-manager.io/cluster-issuer: letsencrypt-prod
    nginx.ingress.kubernetes.io/proxy-body-size: "50m"
    nginx.ingress.kubernetes.io/proxy-read-timeout: "300"
    nginx.ingress.kubernetes.io/enable-cors: "true"
spec:
  tls:
  - hosts:
    - workflows.company.com
    secretName: workflows-tls
  rules:
  - host: workflows.company.com
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: kailash-gateway
            port:
              number: 80
"""
    )

    print("\nStatefulSet for ML Workflows:")
    print("-" * 60)
    print(
        """
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: ml-workflow-service
  namespace: workflows
spec:
  serviceName: ml-workflow
  replicas: 2
  selector:
    matchLabels:
      app: ml-workflow
  template:
    metadata:
      labels:
        app: ml-workflow
    spec:
      containers:
      - name: ml-gateway
        image: company/kailash-ml-gateway:v2.0.0
        resources:
          requests:
            memory: "4Gi"
            cpu: "2000m"
            nvidia.com/gpu: 1
          limits:
            memory: "8Gi"
            cpu: "4000m"
            nvidia.com/gpu: 1
        volumeMounts:
        - name: model-cache
          mountPath: /models
  volumeClaimTemplates:
  - metadata:
      name: model-cache
    spec:
      accessModes: ["ReadWriteOnce"]
      resources:
        requests:
          storage: 100Gi
"""
    )

    print("\nKustomization for Different Environments:")
    print("-" * 60)
    print(
        """
# kustomization.yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization

resources:
- gateway-deployment.yaml
- gateway-service.yaml
- gateway-hpa.yaml
- gateway-ingress.yaml

configMapGenerator:
- name: gateway-config
  literals:
  - MAX_WORKERS=20
  - LOG_LEVEL=INFO

secretGenerator:
- name: gateway-secrets
  envs:
  - secrets.env

replicas:
- name: kailash-gateway
  count: 5

images:
- name: company/kailash-gateway
  newTag: v2.1.0

patchesStrategicMerge:
- |-
  apiVersion: apps/v1
  kind: Deployment
  metadata:
    name: kailash-gateway
  spec:
    template:
      spec:
        nodeSelector:
          workload-type: general
"""
    )


def deployment_comparison():
    """Show comparison of deployment patterns."""
    print("\n\n=== Deployment Pattern Comparison ===\n")

    comparison = """
| Pattern | Use Case | Complexity | Scale | Cost |
|---------|----------|------------|-------|------|
| Single Gateway | Small-Medium deployments | Low | 1-100 workflows | $ |
| Hybrid (Gateway + Services) | Mixed workloads | Medium | 10-500 workflows | $$ |
| High Availability | Production, High uptime | High | 100-1000 workflows | $$$ |
| Kubernetes + HPA | Cloud-native, Auto-scale | Very High | Unlimited | $$$$ |

Key Considerations:
- Single Gateway: Simplest, good for most cases
- Hybrid: When you have specific resource-intensive workflows
- HA: When downtime is not acceptable
- K8s: When you need automatic scaling and have K8s expertise
"""
    print(comparison)


def main():
    """Demonstrate all deployment patterns."""
    pattern_1_single_gateway()
    pattern_2_hybrid_deployment()
    pattern_3_high_availability()
    pattern_4_kubernetes()
    deployment_comparison()

    print("\n\n=== Deployment Best Practices ===")
    print(
        """
1. Start Simple: Begin with Pattern 1, evolve as needed
2. Monitor First: Add monitoring before scaling
3. Gradual Migration: Move from Pattern 1 → 2 → 3 → 4
4. Resource Planning: Profile workflows before deployment
5. Security: Always use HTTPS, authenticate endpoints
6. Backup Strategy: Regular backups of workflow definitions
7. Version Control: Tag all deployments, enable rollbacks
8. Documentation: Document your deployment architecture
"""
    )


if __name__ == "__main__":
    main()
