# Deployment Patterns

Patterns for deploying, configuring, and managing Kailash workflows in various environments.

## 1. Export and Import Pattern

**Purpose**: Export workflows for deployment across different environments

```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.utils.export import WorkflowExporter, WorkflowImporter
from kailash.nodes.data import CSVReaderNode, JSONWriterNode
from kailash.nodes.code import PythonCodeNode

# Create a workflow
workflow = WorkflowBuilder()
workflow.add_node("CSVReaderNode", "reader", {"file_path": "input.csv"})
workflow.add_node("PythonCodeNode", "processor", {
    "code": "result = [{'id': r['id'], 'value': r['value'] * 1.1} for r in data]"
})
workflow.add_node("JSONWriterNode", "writer", {"file_path": "output.json"})

workflow.add_connection("reader", "data", "processor", "data")
workflow.add_connection("processor", "result", "writer", "data")

# Export workflow
exporter = WorkflowExporter(workflow)

# Export to YAML with metadata
exporter.to_yaml("workflow.yaml", config={
    "version": "1.0.0",
    "author": "data-team@company.com",
    "description": "Production ETL pipeline for customer data",
    "environment": {
        "required_env_vars": ["DB_CONNECTION", "API_KEY"],
        "python_version": "3.9+",
        "dependencies": ["pandas>=1.3.0", "numpy>=1.21.0"]
    },
    "deployment": {
        "schedule": "0 2 * * *",  # Daily at 2 AM
        "timeout": 3600,
        "retries": 3
    }
})

# Export to JSON for programmatic use
exporter.to_json("workflow.json", config={
    "include_node_code": True,
    "include_connections": True,
    "include_metadata": True
})

# Export as Python module
exporter.to_python("workflow_module.py", config={
    "class_name": "DataPipelineWorkflow",
    "include_imports": True,
    "make_configurable": True
})

# Import workflow in another environment
importer = WorkflowImporter()

# Import from YAML
imported_workflow = importer.from_yaml("workflow.yaml")

# Import with environment overrides
imported_workflow = importer.from_yaml("workflow.yaml", overrides={
    "nodes": {
        "reader": {"file_path": "/prod/data/input.csv"},
        "writer": {"file_path": "/prod/data/output.json"}
    },
    "environment": {
        "python_version": "3.10"
    }
})

# Validate imported workflow
validation_result = imported_workflow.validate()
if validation_result.is_valid:
    print("Workflow imported successfully")
else:
    print(f"Validation errors: {validation_result.errors}")

```

## 2. Environment-Based Configuration

**Purpose**: Manage different configurations for dev, staging, and production

```python
import os
import yaml
from kailash.workflow.builder import WorkflowBuilder
from kailash.config import ConfigManager

class EnvironmentAwareWorkflow:
    """Workflow that adapts to different environments"""

    def __init__(self, env=None):
        self.env = env or os.getenv('KAILASH_ENV', 'development')
        self.config = self._load_config()
        self.workflow = None

    def _load_config(self):
        """Load environment-specific configuration"""
        # Base configuration
        with open('config/base.yaml', 'r') as f:
            config = yaml.safe_load(f)

        # Environment-specific overrides
        env_config_path = f'config/{self.env}.yaml'
        if os.path.exists(env_config_path):
            with open(env_config_path, 'r') as f:
                env_config = yaml.safe_load(f)
                # Deep merge configurations
                config = self._deep_merge(config, env_config)

        return config

    def _deep_merge(self, base, override):
        """Recursively merge configuration dictionaries"""
        result = base.copy()
        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._deep_merge(result[key], value)
            else:
                result[key] = value
        return result

    def build(self):
        """Build workflow with environment configuration"""
        self.workflow = WorkflowBuilder()

        # Add nodes with environment-specific configuration
        for node_config in self.config['nodes']:
            node_type = node_config['type']
            node_id = node_config['id']

            # Get node class
            node_class = self._get_node_class(node_type)

            # Apply environment-specific parameters
            params = node_config.get('parameters', {})
            env_params = node_config.get(f'{self.env}_parameters', {})
            params.update(env_params)

            # Add node
            self.workflow.add_node(node_id, node_class(), **params)

        # Add connections
        for conn in self.config['connections']:
            self.workflow.add_connection(conn['from'], "result", conn['to'], "input")
            )

        return self.workflow

    def _get_node_class(self, node_type):
        """Get node class from string type"""
        from kailash.nodes import node_registry
        return node_registry.get(node_type)

# Configuration files structure:
# config/base.yaml
"""
workflow:
  id: data_pipeline
  name: Data Processing Pipeline

nodes:
  - id: reader
    type: CSVReaderNode
    parameters:
      delimiter: ","

  - id: processor
    type: PythonCodeNode
    parameters:
      code: |
        result = process_data(data)

  - id: writer
    type: JSONWriterNode
    parameters:
      indent: 2

connections:
  - from: reader
    to: processor
    mapping:
      data: data
  - from: processor
    to: writer
    mapping:
      result: data
"""

# config/production.yaml
"""
nodes:
  - id: reader
    production_parameters:
      file_path: s3://prod-bucket/input/data.csv
      use_ssl: true

  - id: processor
    production_parameters:
      timeout: 300
      memory_limit: 4096

  - id: writer
    production_parameters:
      file_path: s3://prod-bucket/output/results.json
      compression: gzip

monitoring:
  enable: true
  alerts:
    - type: email
      recipients: ["ops-team@company.com"]
    - type: slack
      webhook: ${SLACK_WEBHOOK_URL}
"""

# Usage
workflow_builder = EnvironmentAwareWorkflow(env='production')
production_workflow = workflow_builder.build()

```

## 3. Container Deployment Pattern

**Purpose**: Deploy workflows as containerized applications

```python
# Dockerfile generation
from kailash.deployment import DockerfileGenerator

generator = DockerfileGenerator(workflow)

# Generate Dockerfile
dockerfile_content = generator.generate(
    base_image="python:3.9-slim",
    working_dir="/app",
    include_dependencies=True,
    optimize_layers=True
)

with open("Dockerfile", "w") as f:
    f.write(dockerfile_content)

# Generate docker-compose.yaml
compose_content = generator.generate_compose(
    services={
        "workflow": {
            "build": ".",
            "environment": {
                "KAILASH_ENV": "production",
                "LOG_LEVEL": "INFO"
            },
            "volumes": [
                "./data:/app/data",
                "./logs:/app/logs"
            ],
            "restart": "unless-stopped"
        },
        "redis": {
            "image": "redis:alpine",
            "volumes": ["redis_data:/data"]
        },
        "postgres": {
            "image": "postgres:13",
            "environment": {
                "POSTGRES_DB": "kailash",
                "POSTGRES_USER": "kailash",
                "POSTGRES_PASSWORD": "${DB_PASSWORD}"
            },
            "volumes": ["postgres_data:/var/lib/postgresql/data"]
        }
    },
    networks=["kailash_network"],
    volumes=["redis_data", "postgres_data"]
)

with open("docker-compose.yaml", "w") as f:
    f.write(compose_content)

# Kubernetes deployment
from kailash.deployment import KubernetesManifestGenerator

k8s_generator = KubernetesManifestGenerator(workflow)

# Generate Kubernetes manifests
manifests = k8s_generator.generate(
    namespace="kailash-workflows",
    replicas=3,
    resources={
        "requests": {"cpu": "500m", "memory": "1Gi"},
        "limits": {"cpu": "2000m", "memory": "4Gi"}
    },
    autoscaling={
        "enabled": True,
        "min_replicas": 2,
        "max_replicas": 10,
        "cpu_threshold": 70
    },
    ingress={
        "enabled": True,
        "host": "workflows.company.com",
        "tls": True
    }
)

# Write manifests
for name, content in manifests.items():
    with open(f"k8s/{name}.yaml", "w") as f:
        f.write(content)

```

## 4. Serverless Deployment Pattern

**Purpose**: Deploy workflows as serverless functions

```python
from kailash.deployment import ServerlessDeployment

# AWS Lambda deployment
lambda_deployment = ServerlessDeployment(
    provider="aws",
    runtime="python3.9"
)

# Package workflow for Lambda
lambda_package = lambda_deployment.package_workflow(
    workflow,
    handler_name="workflow_handler",
    memory=1024,
    timeout=300,
    environment={
        "KAILASH_ENV": "production",
        "S3_BUCKET": "workflow-data"
    }
)

# Generate SAM template
sam_template = lambda_deployment.generate_sam_template(
    workflow,
    triggers=[
        {
            "type": "schedule",
            "schedule": "rate(1 hour)"
        },
        {
            "type": "s3",
            "bucket": "input-bucket",
            "prefix": "data/",
            "suffix": ".csv"
        }
    ]
)

# Azure Functions deployment
azure_deployment = ServerlessDeployment(
    provider="azure",
    runtime="python"
)

# Generate function app configuration
function_config = azure_deployment.generate_config(
    workflow,
    triggers={
        "timer": "0 */5 * * * *",  # Every 5 minutes
        "blob": {
            "path": "input/{name}",
            "connection": "AzureWebJobsStorage"
        }
    }
)

# Google Cloud Functions
gcp_deployment = ServerlessDeployment(
    provider="gcp",
    runtime="python39"
)

# Generate Cloud Function
cf_config = gcp_deployment.generate_cloud_function(
    workflow,
    trigger="http",
    memory="512MB",
    max_instances=10
)

```

## 5. Multi-Tenant Deployment

**Purpose**: Deploy isolated workflow environments for multiple tenants

```python
from kailash.deployment import MultiTenantDeployment

class TenantManager:
    """Manage multi-tenant workflow deployments"""

    def __init__(self, base_config):
        self.base_config = base_config
        self.tenants = {}

    def create_tenant(self, tenant_id, config):
        """Create isolated tenant environment"""
        tenant_config = {
            **self.base_config,
            **config,
            "tenant_id": tenant_id,
            "isolation": {
                "database_schema": f"tenant_{tenant_id}",
                "storage_prefix": f"tenants/{tenant_id}/",
                "resource_namespace": f"kailash-{tenant_id}",
                "network_policy": "isolated"
            }
        }

        # Create tenant deployment
        deployment = MultiTenantDeployment(tenant_config)

        # Initialize tenant resources
        deployment.create_database_schema()
        deployment.create_storage_buckets()
        deployment.configure_network_isolation()
        deployment.set_resource_quotas({
            "cpu": config.get("cpu_quota", "4"),
            "memory": config.get("memory_quota", "8Gi"),
            "storage": config.get("storage_quota", "100Gi")
        })

        self.tenants[tenant_id] = deployment
        return deployment

    def deploy_workflow_for_tenant(self, tenant_id, workflow):
        """Deploy workflow in tenant's isolated environment"""
        if tenant_id not in self.tenants:
            raise ValueError(f"Tenant {tenant_id} not found")

        deployment = self.tenants[tenant_id]

        # Add tenant-specific configuration
        tenant_workflow = self._configure_for_tenant(workflow, tenant_id)

        # Deploy with isolation
        deployment.deploy_workflow(
            tenant_workflow,
            isolation_level="strict",
            security_context={
                "run_as_user": 1000,
                "run_as_group": 1000,
                "fs_group": 1000,
                "read_only_root_filesystem": True
            }
        )

    def _configure_for_tenant(self, workflow, tenant_id):
        """Add tenant-specific configuration to workflow"""
        # Clone workflow
        tenant_workflow = workflow.clone()

        # Add tenant context
        for node in tenant_workflow.nodes:
            node.add_context({
                "tenant_id": tenant_id,
                "tenant_storage": f"s3://tenants/{tenant_id}/",
                "tenant_database": f"postgresql://db/tenant_{tenant_id}"
            })

        return tenant_workflow

# Usage
tenant_manager = TenantManager({
    "cluster": "production-k8s",
    "region": "us-east-1",
    "base_image": "kailash/workflow-runtime:latest"
})

# Create tenants
tenant_manager.create_tenant("acme-corp", {
    "tier": "enterprise",
    "cpu_quota": "16",
    "memory_quota": "32Gi",
    "features": ["advanced_analytics", "custom_nodes"]
})

tenant_manager.create_tenant("startup-inc", {
    "tier": "starter",
    "cpu_quota": "2",
    "memory_quota": "4Gi",
    "features": ["basic"]
})

# Deploy workflows
tenant_manager.deploy_workflow_for_tenant("acme-corp", enterprise_workflow)
tenant_manager.deploy_workflow_for_tenant("startup-inc", basic_workflow)

```

## 6. CI/CD Pipeline Integration

**Purpose**: Integrate workflow deployment with CI/CD pipelines

```python
# .github/workflows/deploy-workflow.yml
"""
name: Deploy Kailash Workflow

on:
  push:
    branches: [main]
    paths:
      - 'workflows/**'
      - 'config/**'

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2

      - name: Setup Python
        uses: actions/setup-python@v2
        with:
          python-version: '3.9'

      - name: Install dependencies
        run: |
          pip install kailash
          pip install -r requirements.txt

      - name: Validate workflows
        run: |
          python -m kailash.cli validate workflows/

      - name: Run workflow tests
        run: |
          pytest tests/workflows/

  deploy:
    needs: test
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2

      - name: Configure AWS credentials
        uses: aws-actions/configure-aws-credentials@v1
        with:
          aws-access-key-id: ${{ secrets.AWS_ACCESS_KEY_ID }}
          aws-secret-access-key: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
          aws-region: us-east-1

      - name: Build and push Docker image
        run: |
          docker build -t kailash-workflow:${{ github.sha }} .
          docker tag kailash-workflow:${{ github.sha }} \
            ${{ secrets.ECR_REGISTRY }}/kailash-workflow:latest
          docker push ${{ secrets.ECR_REGISTRY }}/kailash-workflow:latest

      - name: Deploy to Kubernetes
        run: |
          kubectl apply -f k8s/
          kubectl set image deployment/workflow-deployment \
            workflow=${{ secrets.ECR_REGISTRY }}/kailash-workflow:latest
          kubectl rollout status deployment/workflow-deployment
"""

# Automated deployment script
from kailash.deployment import DeploymentPipeline

pipeline = DeploymentPipeline()

# Add validation stage
pipeline.add_stage("validate", lambda: {
    "workflows_valid": validate_all_workflows("workflows/"),
    "configs_valid": validate_configs("config/"),
    "dependencies_resolved": check_dependencies()
})

# Add build stage
pipeline.add_stage("build", lambda: {
    "docker_image": build_docker_image(workflow),
    "artifacts": package_artifacts()
})

# Add test stage
pipeline.add_stage("test", lambda: {
    "unit_tests": run_unit_tests(),
    "integration_tests": run_integration_tests(),
    "performance_tests": run_performance_tests()
})

# Add deploy stage
pipeline.add_stage("deploy", lambda env: {
    "deployment": deploy_to_environment(env),
    "health_check": verify_deployment_health(env),
    "rollback_on_failure": True
})

# Execute pipeline
result = pipeline.execute(environment="production")

```

## 7. Workflow Versioning Pattern

**Purpose**: Manage workflow versions and rollbacks

```python
from kailash.versioning import WorkflowVersionManager

# Initialize version manager
version_manager = WorkflowVersionManager(
    storage_backend="s3",
    bucket="workflow-versions"
)

# Save workflow version
version = version_manager.save_version(
    workflow,
    version="2.1.0",
    metadata={
        "author": "data-team",
        "changes": [
            "Added new data validation step",
            "Improved error handling",
            "Performance optimizations"
        ],
        "breaking_changes": False
    }
)

# List versions
versions = version_manager.list_versions("data_pipeline")
for v in versions:
    print(f"{v.version} - {v.created_at} - {v.metadata['author']}")

# Deploy specific version
deployed = version_manager.deploy_version(
    workflow_id="data_pipeline",
    version="2.0.0",
    environment="production"
)

# Rollback to previous version
if deployment_failed:
    version_manager.rollback(
        workflow_id="data_pipeline",
        environment="production"
    )

# Compare versions
diff = version_manager.compare_versions(
    workflow_id="data_pipeline",
    version1="2.0.0",
    version2="2.1.0"
)
print(f"Changes: {diff.summary}")

```

## Best Practices

1. **Environment Management**:
   - Use separate configurations for each environment
   - Never hardcode credentials or secrets
   - Validate configurations before deployment
   - Use environment variables for sensitive data

2. **Version Control**:
   - Tag workflow versions appropriately
   - Document breaking changes
   - Maintain backward compatibility
   - Test rollback procedures

3. **Monitoring**:
   - Include health checks in deployments
   - Set up appropriate logging
   - Monitor resource usage
   - Configure alerts for failures

4. **Security**:
   - Use least-privilege principles
   - Encrypt sensitive data
   - Audit workflow executions
   - Implement network isolation

## See Also
- [Security Patterns](10-security-patterns.md) - Secure deployment practices
- [Best Practices](11-best-practices.md) - General deployment guidelines
- [Error Handling Patterns](05-error-handling-patterns.md) - Deployment failure handling
