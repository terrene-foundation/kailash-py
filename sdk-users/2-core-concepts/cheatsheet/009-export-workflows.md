# Workflow Export & Import

## Basic Export Patterns
```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.utils.export import export_workflow, import_workflow

# Export to YAML (recommended for version control)
export_workflow(workflow, "my_workflow.yaml", format="yaml")

# Export to JSON (good for APIs and web interfaces)
export_workflow(workflow, "my_workflow.json", format="json")

# Export to Python code (for sharing as standalone scripts)
export_workflow(workflow, "my_workflow.py", format="python")

```

## Dictionary-Based Export/Import
```python
# Export to dictionary (in-memory operations)
workflow = WorkflowBuilder()
workflow_dict = workflow.to_dict()

# Save dictionary manually
import json
with open("workflow.json", "w") as f:
    json.dump(workflow_dict, f, indent=2)

# Load from dictionary
loaded_workflow = Workflow.from_dict(workflow_dict)

# Verify loaded workflow
print(f"Original nodes: {len(workflow.nodes)}")
print(f"Loaded nodes: {len(loaded_workflow.nodes)}")

```

## Advanced Export Options
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

# Export with configuration parameters
export_workflow(workflow, "workflow_with_config.yaml",
    format="yaml",
    include_node_config=True,    # Include node configurations
    include_metadata=True,      # Include workflow metadata
    include_runtime_info=False, # Exclude runtime-specific data
    compress=True               # Compress large workflows
)

# Export with execution results
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())
export_workflow(workflow, "workflow_with_results.json",
    format="json",
    include_execution_results=True,
    execution_data=results,
    run_id=run_id
)

```

## Selective Export
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

# Export only specific nodes
node_subset = ["reader", "processor", "writer"]
export_workflow(workflow, "workflow_subset.yaml",
    format="yaml",
    include_nodes=node_subset,
    maintain_connections=True
)

# Export workflow template (without specific parameters)
export_workflow(workflow, "workflow_template.yaml",
    format="yaml",
    parameterize_values=True,    # Remove specific file paths, etc.
    create_template=True,       # Add placeholder parameters
    include_documentation=True  # Add parameter descriptions
)

```

## Import with Validation
```python
# Safe import with validation
try:
    imported_workflow = import_workflow("workflow.yaml")

    # Validate imported workflow
    imported_workflow.validate()

    # Check compatibility
    if imported_workflow.version != workflow.version:
        print(f"Version mismatch: {imported_workflow.version} vs {workflow.version}")

    print("✅ Workflow imported successfully")

except Exception as e:
    print(f"❌ Import failed: {e}")

```

## Version Control Integration
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

# Export for Git version control
export_workflow(workflow, "workflows/production/data_pipeline_v1.yaml",
    format="yaml",
    include_version=True,
    include_git_hash=True,
    include_timestamp=True,
    normalize_paths=True        # Use relative paths
)

# Create workflow changelog
changelog_entry = {
    "version": "1.2.0",
    "date": "2024-01-15",
    "changes": [
        "Added error handling to data processor",
        "Updated LLM model to gpt-4",
        "Improved memory optimization"
    ],
    "breaking_changes": [],
    "migration_notes": "No migration required"
}

export_workflow(workflow, "workflow_v1.2.0.yaml",
    format="yaml",
    include_changelog=True,
    changelog=changelog_entry
)

```

## Environment-Specific Exports
```python
# Export for different environments
environments = ["development", "staging", "production"]

for env in environments:
    # Environment-specific parameter overrides
    env_params = {
        "development": {
            "database_url": "localhost:5432/dev_db",
            "debug_mode": True,
            "max_retries": 1
        },
        "staging": {
            "database_url": "staging-db:5432/staging_db",
            "debug_mode": False,
            "max_retries": 3
        },
        "production": {
            "database_url": "prod-cluster:5432/prod_db",
            "debug_mode": False,
            "max_retries": 5
        }
    }

    export_workflow(workflow, f"workflow_{env}.yaml",
        format="yaml",
        environment_overrides=env_params[env],
        environment_name=env
    )

```

## Batch Export Operations
```python
# Export multiple workflows
workflows = {
    "data_pipeline": data_workflow,
    "ml_training": ml_workflow,
    "api_processing": api_workflow
}

# Batch export to directory
import os
export_dir = "exported_workflows"
os.makedirs(export_dir, exist_ok=True)

for name, wf in workflows.items():
    export_workflow(wf, f"{export_dir}/{name}.yaml",
        format="yaml",
        include_metadata=True
    )

    # Also export as Python for standalone execution
    export_workflow(wf, f"{export_dir}/{name}.py",
        format="python",
        include_execution_example=True
    )

```

## Docker Integration
```python
# Export workflow for Docker deployment
export_workflow(workflow, "docker_workflow.yaml",
    format="yaml",
    docker_ready=True,
    normalize_paths=True,       # Use container paths
    include_requirements=True,  # Add Python dependencies
    include_dockerfile=True     # Generate Dockerfile
)

# Create Docker Compose configuration
docker_config = {
    "services": {
        "kailash-workflow": {
            "build": ".",
            "volumes": ["./data:/app/data"],
            "command": ["python", "-m", "kailash", "run", "workflow.yaml"],
            "ports": ["8000:8000"]
        }
    }
}

with open("docker/docker-compose.yml", "w") as f:
    import yaml
    yaml.dump(docker_config, f)

```

## Kubernetes Deployment Export
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

# Export for Kubernetes deployment
export_workflow(workflow, "k8s/workflow-configmap.yaml",
    format="kubernetes",
    resource_type="configmap",
    namespace="production",
    labels={"app": "kailash", "version": "1.0.0"}
)

# Create Kubernetes deployment manifest
k8s_deployment = {
    "apiVersion": "apps/v1",
    "kind": "Deployment",
    "metadata": {
        "name": "kailash-workflow",
        "namespace": "production"
    },
    "spec": {
        "replicas": 3,
        "selector": {"matchLabels": {"app": "kailash"}},
        "template": {
            "metadata": {"labels": {"app": "kailash"}},
            "spec": {
                "containers": [{
                    "name": "kailash",
                    "image": "kailash:latest",
                    "command": ["python", "-m", "kailash", "run", "workflow.yaml"]
                }]
            }
        }
    }
}

with open("k8s/deployment.yaml", "w") as f:
    yaml.dump(k8s_deployment, f)

```

## Security & Compliance
```python
# Export with security considerations
export_workflow(workflow, "secure_workflow.yaml",
    format="yaml",

    # Security options
    redact_secrets=True,        # Remove sensitive data
    encrypt_parameters=True,    # Encrypt sensitive parameters
    include_checksums=True,     # Add integrity verification

    # Compliance
    include_audit_trail=True,   # Who exported when
    compliance_mode="hipaa",    # HIPAA/GDPR compliance
    data_classification="internal"
)

# Verify exported workflow integrity
from kailash.utils.security import verify_workflow_integrity
is_valid = verify_workflow_integrity("secure_workflow.yaml")
print(f"Workflow integrity: {'✅ Valid' if is_valid else '❌ Invalid'}")

```

## Import Troubleshooting
```python
# Debug import issues
def debug_import(file_path):
    """Debug workflow import problems"""
    try:
        # Try basic import
        workflow = import_workflow(file_path)
        print("✅ Basic import successful")

        # Validate structure
        workflow.validate()
        print("✅ Structure validation passed")

        # Check for missing dependencies
        missing_deps = workflow.check_dependencies()
        if missing_deps:
            print(f"⚠️ Missing dependencies: {missing_deps}")

        # Check parameter completeness
        incomplete_params = workflow.check_parameter_completeness()
        if incomplete_params:
            print(f"⚠️ Incomplete parameters: {incomplete_params}")

        return workflow

    except Exception as e:
        print(f"❌ Import failed: {e}")

        # Provide helpful suggestions
        if "version" in str(e):
            print("💡 Try updating Kailash SDK or check version compatibility")
        elif "node" in str(e):
            print("💡 Check if all required node types are available")
        elif "parameter" in str(e):
            print("💡 Verify all required parameters are provided")

        return None

# Usage
imported_workflow = debug_import("problematic_workflow.yaml")

```

## Best Practices
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

# Recommended export workflow
def export_workflow_properly(workflow, name, version="1.0.0"):
    """Export workflow following best practices"""

    # 1. Validate before export
    workflow.validate()

    # 2. Export multiple formats
    base_name = f"{name}_v{version}"

    # YAML for version control
    export_workflow(workflow, f"{base_name}.yaml",
        format="yaml", include_metadata=True)

    # JSON for APIs
    export_workflow(workflow, f"{base_name}.json",
        format="json", include_metadata=True)

    # Python for standalone execution
    export_workflow(workflow, f"{base_name}.py",
        format="python", include_execution_example=True)

    # 3. Create documentation
    export_workflow(workflow, f"{base_name}_docs.md",
        format="markdown", include_diagrams=True)

    print(f"✅ Workflow '{name}' exported in multiple formats")

# Usage
export_workflow_properly(workflow, "data_pipeline", "2.1.0")

```

## Quick Export Commands
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

# One-liner exports
workflow.export("workflow.yaml")                    # Quick YAML export
workflow.export("workflow.json", include_params=True) # JSON with parameters
workflow.export("workflow.py", standalone=True)     # Standalone Python script

```

## Next Steps
- [Visualization](010-visualization.md) - Visualize exported workflows
- [Version Control](../developer/pre-commit-hooks.md) - Git integration
- [Production Deployment](../production-patterns/) - Deploy exported workflows
