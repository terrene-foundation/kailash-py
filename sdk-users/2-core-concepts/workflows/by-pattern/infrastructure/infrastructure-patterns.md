# Infrastructure Patterns for Kailash Workflows

Common infrastructure patterns and best practices for deploying Kailash SDK workflows.

## Local Development Infrastructure

### Quick Start with Docker Compose

```bash
# Clone your project
git clone <your-project>
cd <your-project>

# Set up infrastructure
./infrastructure/scripts/setup.sh

# Start services
docker compose -f infrastructure/docker/docker-compose.yml up -d

# Check health
curl http://localhost:8889/health

# Run your workflow
python src/solutions/my_workflow.py
```

### Development Environment Configuration

```python
"""Development environment setup"""
import os
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.config import EnvironmentConfig

# Auto-detect environment
if os.getenv("SDK_DEV_MODE") == "true":
    # Use Docker services
    config = EnvironmentConfig(
        database_url=os.getenv("DATABASE_URL", "postgresql://localhost:5432/dev"),
        redis_url=os.getenv("REDIS_URL", "redis://localhost:6379"),
        use_docker_services=True
    )
else:
    # Use lightweight alternatives
    config = EnvironmentConfig(
        database_url="sqlite:///local.db",
        use_docker_services=False
    )

# Create workflow with environment config
workflow = WorkflowBuilder()
# Add nodes as needed
# workflow.add_node("NodeType", "node_id", {})

# Execute workflow
runtime = LocalRuntime(config=config)
results, run_id = runtime.execute(workflow.build())

```

## Cloud Deployment Patterns

### AWS Deployment

```python
"""AWS ECS Fargate deployment"""

# CloudFormation template
aws_infrastructure = """
AWSTemplateFormatVersion: '2010-09-09'
Description: 'Kailash Workflow Infrastructure'

Resources:
  WorkflowCluster:
    Type: AWS::ECS::Cluster
    Properties:
      ClusterName: kailash-workflows

  WorkflowTaskDefinition:
    Type: AWS::ECS::TaskDefinition
    Properties:
      Family: kailash-workflow
      Cpu: '512'
      Memory: '1024'
      NetworkMode: awsvpc
      RequiresCompatibilities:
        - FARGATE
      ContainerDefinitions:
        - Name: workflow
          Image: !Sub '${AWS::AccountId}.dkr.ecr.${AWS::Region}.amazonaws.com/kailash-workflow:latest'
          PortMappings:
            - ContainerPort: 8000
          Environment:
            - Name: DATABASE_URL
              Value: !Sub '${RDSEndpoint}'
            - Name: REDIS_URL
              Value: !Sub '${ElastiCacheEndpoint}'
          LogConfiguration:
            LogDriver: awslogs
            Options:
              awslogs-group: !Ref LogGroup
              awslogs-region: !Ref AWS::Region
              awslogs-stream-prefix: workflow

  WorkflowService:
    Type: AWS::ECS::Service
    Properties:
      ServiceName: kailash-workflow-service
      Cluster: !Ref WorkflowCluster
      TaskDefinition: !Ref WorkflowTaskDefinition
      DesiredCount: 3
      LaunchType: FARGATE
      NetworkConfiguration:
        AwsvpcConfiguration:
          Subnets: !Ref PrivateSubnets
          SecurityGroups:
            - !Ref WorkflowSecurityGroup
      LoadBalancers:
        - ContainerName: workflow
          ContainerPort: 8000
          TargetGroupArn: !Ref TargetGroup
"""

# Python deployment script
from kailash.deployment import AWSDeployment

deployment = AWSDeployment(
    region="us-east-1",
    cluster_name="kailash-workflows"
)

# Deploy with auto-scaling
deployment.deploy_workflow(
    workflow_path="workflows/production.yaml",
    min_tasks=2,
    max_tasks=10,
    cpu_threshold=70,
    memory_threshold=80
)

```

### Google Cloud Platform

```python
"""GCP Cloud Run deployment"""

# Terraform configuration
gcp_infrastructure = """
resource "google_cloud_run_service" "workflow" {
  name     = "kailash-workflow"
  location = var.region

  template {
    spec {
      containers {
        image = "gcr.io/${var.project_id}/kailash-workflow:latest"

        resources {
          limits = {
            cpu    = "2"
            memory = "2Gi"
          }
        }

        env {
          name = "DATABASE_URL"
          value_from {
            secret_key_ref {
              name = google_secret_manager_secret.db_url.secret_id
              key  = "latest"
            }
          }
        }
      }

      service_account_name = google_service_account.workflow.email
    }

    metadata {
      annotations = {
        "autoscaling.knative.dev/minScale" = "2"
        "autoscaling.knative.dev/maxScale" = "100"
      }
    }
  }

  traffic {
    percent         = 100
    latest_revision = true
  }
}

resource "google_cloud_scheduler_job" "workflow_batch" {
  name             = "workflow-batch-processor"
  schedule         = "0 2 * * *"
  time_zone        = "America/New_York"
  attempt_deadline = "1800s"

  http_target {
    http_method = "POST"
    uri         = "${google_cloud_run_service.workflow.status[0].url}/batch"

    oidc_token {
      service_account_email = google_service_account.scheduler.email
    }
  }
}
"""

```

### Azure Container Instances

```python
"""Azure deployment pattern"""

# ARM template
azure_infrastructure = {
    "$schema": "https://schema.management.azure.com/schemas/2019-04-01/deploymentTemplate.json#",
    "contentVersion": "1.0.0.0",
    "resources": [{
        "type": "Microsoft.ContainerInstance/containerGroups",
        "apiVersion": "2021-09-01",
        "name": "kailash-workflow",
        "location": "[resourceGroup().location]",
        "properties": {
            "containers": [{
                "name": "workflow",
                "properties": {
                    "image": "myregistry.azurecr.io/kailash-workflow:latest",
                    "ports": [{"port": 8000}],
                    "resources": {
                        "requests": {
                            "cpu": 1,
                            "memoryInGb": 1.5
                        }
                    },
                    "environmentVariables": [{
                        "name": "DATABASE_URL",
                        "secureValue": "[parameters('databaseUrl')]"
                    }]
                }
            }],
            "osType": "Linux",
            "restartPolicy": "OnFailure",
            "ipAddress": {
                "type": "Public",
                "ports": [{"protocol": "tcp", "port": 8000}]
            }
        }
    }]
}

```

## Hybrid Infrastructure Patterns

### Multi-Cloud Deployment

```python
"""Deploy across multiple cloud providers"""
from kailash.deployment import MultiCloudDeployment

deployment = MultiCloudDeployment()

# Primary in AWS
deployment.add_region(
    provider="aws",
    region="us-east-1",
    config={
        "service": "ecs-fargate",
        "replicas": 3,
        "is_primary": True
    }
)

# DR in GCP
deployment.add_region(
    provider="gcp",
    region="us-central1",
    config={
        "service": "cloud-run",
        "replicas": 2,
        "is_standby": True
    }
)

# Deploy with failover
deployment.deploy_with_failover(
    workflow_path="workflows/critical.yaml",
    health_check_interval=30,
    failover_threshold=3
)

```

### Edge Computing Pattern

```python
"""Deploy workflows at the edge"""
from kailash.workflow.builder import WorkflowBuilder
from kailash.deployment import EdgeDeployment

# Lightweight workflow for edge
edge_workflow = WorkflowBuilder()

# Configure for resource constraints
edge_config = {
    "max_memory": "512MB",
    "cpu_limit": "0.5",
    "enable_caching": True,
    "offline_mode": True
}

# Deploy to edge locations
deployment = EdgeDeployment()

locations = ["store-001", "store-002", "warehouse-west"]
for location in locations:
    deployment.deploy_edge(
        workflow=edge_workflow.build(),
        location=location,
        config=edge_config,
        sync_interval=300  # Sync with cloud every 5 minutes
    )

```

## Security Patterns

### Zero-Trust Architecture

```python
"""Implement zero-trust security"""
from kailash.security import ZeroTrustConfig
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

# Configure zero-trust
security = ZeroTrustConfig(
    require_authentication=True,
    require_encryption=True,
    verify_every_request=True,
    audit_all_actions=True
)

# Create workflow with security configuration
workflow = WorkflowBuilder()

# Configure runtime with security
runtime = LocalRuntime(security_config=security)

# Add nodes with security policies
workflow.add_node("SecureDatabaseNode", "secure_db", {
    "policies": [{
        "effect": "Allow",
        "principal": {"groups": ["data-scientists"]},
        "action": ["read", "process"],
        "resource": "s3://secure-bucket/*",
        "condition": {
            "IpAddress": {"aws:SourceIp": ["10.0.0.0/8"]}
        }
    }]
})

```

### Secrets Management

```python
"""Secure secrets handling"""
from kailash.secrets import SecretsManager
import os

# Initialize secrets manager
secrets = SecretsManager(
    provider=os.getenv("SECRETS_PROVIDER", "aws-secrets-manager"),
    region=os.getenv("AWS_REGION", "us-east-1")
)

# Workflow with secrets
workflow = WorkflowBuilder()

# Add node with secret reference
workflow.add_node("DatabaseNode", "db_query", {
    "query": "SELECT * FROM sensitive_data",
    "connection_string_secret": "db/prod/connection_string"
})

# Rotate secrets automatically
secrets.enable_auto_rotation(
    secret_name="db/prod/connection_string",
    rotation_days=30,
    rotation_function="arn:aws:lambda:us-east-1:123456789:function:rotate-db-secret"
)

```

## Cost Optimization Patterns

### Spot Instance Usage

```python
"""Use spot instances for batch processing"""

# Kubernetes configuration for spot instances
spot_config = """
apiVersion: v1
kind: ConfigMap
metadata:
  name: cluster-autoscaler-status
  namespace: kube-system
data:
  nodes.max-node-provision-time: "15m"
  scale-down-delay-after-add: "10m"
  scale-down-unneeded-time: "10m"
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: workflow-batch-spot
spec:
  template:
    spec:
      nodeSelector:
        node.kubernetes.io/lifecycle: spot
      tolerations:
      - key: "spot-instance"
        operator: "Equal"
        value: "true"
        effect: "NoSchedule"
      affinity:
        nodeAffinity:
          preferredDuringSchedulingIgnoredDuringExecution:
          - weight: 1
            preference:
              matchExpressions:
              - key: node.kubernetes.io/instance-type
                operator: In
                values:
                - m5.large
                - m5.xlarge
"""

```

### Serverless Pattern

```python
"""Serverless workflow execution"""
from kailash.serverless import LambdaWorkflow

# Create serverless workflow
serverless_workflow = LambdaWorkflow(
    "event-processor",
    "Event-Driven Processor"
)

# Configure for Lambda
serverless_workflow.configure(
    memory_size=512,
    timeout=300,
    reserved_concurrency=10,
    environment={
        "LOG_LEVEL": "INFO",
        "STAGE": "production"
    }
)

# Deploy with API Gateway
serverless_workflow.deploy_with_api_gateway(
    stage="prod",
    throttle_rate=1000,
    throttle_burst=2000,
    api_key_required=True
)

```

## Monitoring and Maintenance

### Automated Maintenance

```python
"""Automated infrastructure maintenance"""
from kailash.maintenance import MaintenanceScheduler

scheduler = MaintenanceScheduler()

# Database maintenance
scheduler.add_task(
    name="database-vacuum",
    schedule="0 3 * * 0",  # Weekly Sunday 3 AM
    command="VACUUM ANALYZE;",
    target="postgresql"
)

# Log rotation
scheduler.add_task(
    name="log-rotation",
    schedule="0 0 * * *",  # Daily midnight
    command="logrotate /etc/logrotate.d/workflow",
    target="all-nodes"
)

# Backup workflow data
scheduler.add_task(
    name="workflow-backup",
    schedule="0 2 * * *",  # Daily 2 AM
    script="""
    pg_dump $DATABASE_URL | gzip > /backup/workflow-$(date +%Y%m%d).sql.gz
    aws s3 cp /backup/workflow-$(date +%Y%m%d).sql.gz s3://backups/
    find /backup -name "*.sql.gz" -mtime +7 -delete
    """,
    target="backup-node"
)

```

## Best Practices Summary

1. **Environment Parity**
   - Keep development, staging, and production as similar as possible
   - Use infrastructure as code for reproducibility
   - Version control all infrastructure configurations

2. **Scalability Design**
   - Design for horizontal scaling from the start
   - Use stateless workflows when possible
   - Implement proper caching strategies

3. **Security First**
   - Never hardcode secrets
   - Use least privilege access
   - Encrypt data in transit and at rest
   - Regular security audits

4. **Cost Management**
   - Use auto-scaling to match demand
   - Leverage spot/preemptible instances
   - Monitor and optimize resource usage
   - Set up billing alerts

5. **Operational Excellence**
   - Automate everything possible
   - Implement comprehensive monitoring
   - Plan for disaster recovery
   - Document runbooks and procedures
