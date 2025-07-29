# Workflow Registration Guide

Master advanced workflow registration patterns, lifecycle management, and dynamic updates in Nexus.

## Overview

This guide covers sophisticated workflow registration techniques that go beyond basic usage. Learn dynamic registration, lifecycle management, versioning, and advanced deployment patterns.

## Core Registration Concepts

### Basic Registration Pattern

```python
from nexus import Nexus
from kailash.workflow.builder import WorkflowBuilder

app = Nexus()

# Build workflow
workflow = WorkflowBuilder()
workflow.add_node("HTTPRequestNode", "api_call", {
    "url": "https://api.example.com/data",
    "method": "GET"
})

# Register with basic metadata
app.register("data-fetcher", workflow.build())
```

### Enhanced Registration with Metadata

```python
from nexus import Nexus
from kailash.workflow.builder import WorkflowBuilder

app = Nexus()

workflow = WorkflowBuilder()
workflow.add_node("HTTPRequestNode", "fetch", {
    "url": "https://jsonplaceholder.typicode.com/posts",
    "method": "GET"
})

# Register with comprehensive metadata
app.register("enhanced-data-fetcher", workflow.build(), metadata={
    "version": "1.0.0",
    "description": "Fetches data from JSON placeholder API",
    "author": "Development Team",
    "tags": ["data", "api", "json"],
    "category": "data-processing",
    "documentation": "https://docs.example.com/workflows/data-fetcher",
    "dependencies": ["requests", "json"],
    "resource_requirements": {
        "memory": "256MB",
        "cpu": "0.5 cores",
        "timeout": "30s"
    },
    "api_schema": {
        "inputs": {
            "limit": {"type": "integer", "default": 10, "description": "Number of posts to fetch"}
        },
        "outputs": {
            "posts": {"type": "array", "description": "Array of post objects"}
        }
    }
})
```

## Dynamic Registration

### Runtime Workflow Discovery

```python
from nexus import Nexus
import os
import importlib.util

app = Nexus()

def discover_and_register_workflows(directory="./workflows"):
    """Dynamically discover and register workflows from directory"""

    workflow_count = 0

    for filename in os.listdir(directory):
        if filename.endswith("_workflow.py"):
            workflow_name = filename[:-12]  # Remove '_workflow.py'

            # Load workflow module
            spec = importlib.util.spec_from_file_location(
                workflow_name,
                os.path.join(directory, filename)
            )
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            # Get workflow and metadata from module
            if hasattr(module, 'create_workflow') and hasattr(module, 'METADATA'):
                workflow = module.create_workflow()
                metadata = module.METADATA

                app.register(workflow_name, workflow, metadata=metadata)
                workflow_count += 1

                print(f"✅ Registered workflow: {workflow_name}")

    print(f"📊 Total workflows registered: {workflow_count}")
    return workflow_count

# Discover and register all workflows
discover_and_register_workflows()
```

### Configuration-Driven Registration

```python
from nexus import Nexus
from kailash.workflow.builder import WorkflowBuilder
import yaml
import json

app = Nexus()

def register_from_config(config_file="workflows.yaml"):
    """Register workflows from configuration file"""

    with open(config_file, 'r') as f:
        config = yaml.safe_load(f)

    for workflow_config in config['workflows']:
        workflow = WorkflowBuilder()

        # Build workflow from configuration
        for node_config in workflow_config['nodes']:
            workflow.add_node(
                node_config['type'],
                node_config['id'],
                node_config['parameters']
            )

        # Add connections
        for conn in workflow_config.get('connections', []):
            workflow.add_connection(conn['from_node'], "result", conn['to_node'], "input"),
                conn.get('to_port', 'input')
            )

        # Register with metadata
        app.register(
            workflow_config['name'],
            workflow,
            metadata=workflow_config.get('metadata', {})
        )

        print(f"✅ Registered from config: {workflow_config['name']}")

# Example configuration usage
config_yaml = """
workflows:
  - name: "config-driven-workflow"
    metadata:
      version: "1.0.0"
      description: "Workflow created from configuration"
    nodes:
      - type: "HTTPRequestNode"
        id: "fetch_data"
        parameters:
          url: "https://httpbin.org/json"
          method: "GET"
      - type: "JSONReaderNode"
        id: "parse_json"
        parameters: {}
    connections:
      - from_node: "fetch_data"
        to_node: "parse_json"
"""

# Save and load configuration
with open("workflows.yaml", "w") as f:
    f.write(config_yaml)

register_from_config()
```

## Workflow Versioning

### Version Management

```python
from nexus import Nexus
from kailash.workflow.builder import WorkflowBuilder

app = Nexus()

class WorkflowVersionManager:
    """Manage workflow versions and updates"""

    def __init__(self, nexus_app):
        self.app = nexus_app
        self.versions = {}

    def register_version(self, name, workflow, version, metadata=None):
        """Register a specific version of a workflow"""

        versioned_name = f"{name}:v{version}"

        # Enhanced metadata with version info
        version_metadata = {
            "version": version,
            "workflow_name": name,
            "registered_at": __import__('datetime').datetime.now().isoformat(),
            **(metadata or {})
        }

        self.app.register(versioned_name, workflow, metadata=version_metadata)

        # Track versions
        if name not in self.versions:
            self.versions[name] = []
        self.versions[name].append(version)

        # Also register as latest if it's the highest version
        latest_version = max(self.versions[name])
        if version == latest_version:
            self.app.register(f"{name}:latest", workflow, metadata=version_metadata)
            self.app.register(name, workflow, metadata=version_metadata)  # Default to latest

        print(f"✅ Registered {name} version {version}")

    def get_versions(self, name):
        """Get all versions of a workflow"""
        return sorted(self.versions.get(name, []))

    def rollback(self, name, target_version):
        """Rollback to a specific version"""
        if name in self.versions and target_version in self.versions[name]:
            # Re-register the target version as current
            versioned_workflow = self.app.workflows.get(f"{name}:v{target_version}")
            if versioned_workflow:
                self.app.register(name, versioned_workflow.workflow)
                print(f"✅ Rolled back {name} to version {target_version}")
                return True
        return False

# Usage example
version_manager = WorkflowVersionManager(app)

# Register multiple versions
for version in ["1.0.0", "1.1.0", "2.0.0"]:
    workflow = WorkflowBuilder()
    workflow.add_node("HTTPRequestNode", "api_call", {
        "url": f"https://api.example.com/v{version.split('.')[0]}/data",
        "method": "GET"
    })

    version_manager.register_version(
        "data-api",
        workflow,
        version,
        metadata={"api_version": version.split('.')[0]}
    )

# Check versions
print(f"Available versions: {version_manager.get_versions('data-api')}")

# Rollback example
version_manager.rollback("data-api", "1.1.0")
```

### Blue-Green Deployment

```python
from nexus import Nexus
from kailash.workflow.builder import WorkflowBuilder
import time

app = Nexus()

class BlueGreenDeployment:
    """Implement blue-green deployment for workflows"""

    def __init__(self, nexus_app):
        self.app = nexus_app
        self.deployments = {}

    def deploy_blue(self, name, workflow, metadata=None):
        """Deploy to blue environment"""
        blue_name = f"{name}-blue"
        self.app.register(blue_name, workflow, metadata=metadata)

        self.deployments[name] = {
            "blue": {"deployed_at": time.time(), "active": False},
            "green": self.deployments.get(name, {}).get("green", {"active": False})
        }

        print(f"✅ Blue deployment ready: {blue_name}")
        return blue_name

    def deploy_green(self, name, workflow, metadata=None):
        """Deploy to green environment"""
        green_name = f"{name}-green"
        self.app.register(green_name, workflow, metadata=metadata)

        if name not in self.deployments:
            self.deployments[name] = {}
        self.deployments[name]["green"] = {"deployed_at": time.time(), "active": False}

        print(f"✅ Green deployment ready: {green_name}")
        return green_name

    def switch_traffic(self, name, target_environment):
        """Switch traffic to target environment (blue or green)"""
        if target_environment not in ["blue", "green"]:
            raise ValueError("Environment must be 'blue' or 'green'")

        target_name = f"{name}-{target_environment}"

        if target_name in self.app.workflows:
            # Point main name to target environment
            target_workflow = self.app.workflows[target_name]
            self.app.register(name, target_workflow.workflow, metadata=target_workflow.metadata)

            # Update deployment status
            self.deployments[name][target_environment]["active"] = True
            other_env = "green" if target_environment == "blue" else "blue"
            if other_env in self.deployments[name]:
                self.deployments[name][other_env]["active"] = False

            print(f"✅ Traffic switched to {target_environment} environment")
            return True

        return False

    def get_deployment_status(self, name):
        """Get deployment status"""
        return self.deployments.get(name, {})

# Usage example
bg_deployment = BlueGreenDeployment(app)

# Current production workflow
prod_workflow = WorkflowBuilder()
prod_workflow.add_node("HTTPRequestNode", "api_call", {
    "url": "https://api.example.com/v1/data",
    "method": "GET"
})

# Deploy to blue
bg_deployment.deploy_blue("data-service", prod_workflow)
bg_deployment.switch_traffic("data-service", "blue")

# New version for green deployment
new_workflow = WorkflowBuilder()
new_workflow.add_node("HTTPRequestNode", "api_call", {
    "url": "https://api.example.com/v2/data",  # New version
    "method": "GET"
})

# Deploy to green and test
bg_deployment.deploy_green("data-service", new_workflow)

# After testing, switch traffic
bg_deployment.switch_traffic("data-service", "green")

print(f"Deployment status: {bg_deployment.get_deployment_status('data-service')}")
```

## Lifecycle Management

### Workflow Lifecycle Hooks

```python
from nexus import Nexus
from kailash.workflow.builder import WorkflowBuilder

app = Nexus()

class WorkflowLifecycleManager:
    """Manage workflow lifecycle events"""

    def __init__(self, nexus_app):
        self.app = nexus_app
        self.hooks = {
            "pre_register": [],
            "post_register": [],
            "pre_execute": [],
            "post_execute": [],
            "pre_unregister": [],
            "post_unregister": []
        }

    def add_hook(self, event, hook_function):
        """Add lifecycle hook"""
        if event in self.hooks:
            self.hooks[event].append(hook_function)

    def trigger_hooks(self, event, context):
        """Trigger all hooks for an event"""
        for hook in self.hooks.get(event, []):
            try:
                hook(context)
            except Exception as e:
                print(f"Hook error in {event}: {e}")

    def register_with_lifecycle(self, name, workflow, metadata=None):
        """Register workflow with full lifecycle management"""

        # Pre-registration hooks
        context = {
            "name": name,
            "workflow": workflow,
            "metadata": metadata,
            "timestamp": time.time()
        }
        self.trigger_hooks("pre_register", context)

        # Perform registration
        self.app.register(name, workflow, metadata=metadata)

        # Post-registration hooks
        context["registered"] = True
        self.trigger_hooks("post_register", context)

        print(f"✅ Registered with lifecycle: {name}")

# Define lifecycle hooks
def log_registration(context):
    """Log workflow registration"""
    print(f"📝 Logging registration: {context['name']} at {context['timestamp']}")

def validate_workflow(context):
    """Validate workflow before registration"""
    workflow = context['workflow']
    if not workflow.nodes:
        raise ValueError(f"Workflow {context['name']} has no nodes")
    print(f"✅ Validation passed: {context['name']}")

def send_notification(context):
    """Send notification after registration"""
    print(f"📧 Notification: Workflow {context['name']} registered successfully")

# Set up lifecycle management
lifecycle_mgr = WorkflowLifecycleManager(app)
lifecycle_mgr.add_hook("pre_register", validate_workflow)
lifecycle_mgr.add_hook("pre_register", log_registration)
lifecycle_mgr.add_hook("post_register", send_notification)

# Register with lifecycle
workflow = WorkflowBuilder()
workflow.add_node("HTTPRequestNode", "test", {
    "url": "https://httpbin.org/get",
    "method": "GET"
})

lifecycle_mgr.register_with_lifecycle("lifecycle-test", workflow)
```

### Health Monitoring and Auto-Recovery

```python
from nexus import Nexus
from kailash.workflow.builder import WorkflowBuilder
import time
import threading

app = Nexus()

class WorkflowHealthMonitor:
    """Monitor workflow health and auto-recovery"""

    def __init__(self, nexus_app):
        self.app = nexus_app
        self.monitoring = False
        self.health_checks = {}
        self.recovery_strategies = {}

    def add_health_check(self, workflow_name, check_function, interval=60):
        """Add health check for a workflow"""
        self.health_checks[workflow_name] = {
            "function": check_function,
            "interval": interval,
            "last_check": 0,
            "status": "unknown"
        }

    def add_recovery_strategy(self, workflow_name, recovery_function):
        """Add recovery strategy for a workflow"""
        self.recovery_strategies[workflow_name] = recovery_function

    def start_monitoring(self):
        """Start health monitoring"""
        self.monitoring = True
        monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        monitor_thread.start()
        print("🩺 Health monitoring started")

    def stop_monitoring(self):
        """Stop health monitoring"""
        self.monitoring = False
        print("🩺 Health monitoring stopped")

    def _monitor_loop(self):
        """Main monitoring loop"""
        while self.monitoring:
            current_time = time.time()

            for workflow_name, check_config in self.health_checks.items():
                if current_time - check_config["last_check"] >= check_config["interval"]:
                    try:
                        # Run health check
                        is_healthy = check_config["function"](workflow_name)
                        check_config["status"] = "healthy" if is_healthy else "unhealthy"
                        check_config["last_check"] = current_time

                        # If unhealthy, try recovery
                        if not is_healthy and workflow_name in self.recovery_strategies:
                            print(f"🚨 Workflow {workflow_name} is unhealthy, attempting recovery")
                            try:
                                self.recovery_strategies[workflow_name](workflow_name)
                                print(f"✅ Recovery completed for {workflow_name}")
                            except Exception as e:
                                print(f"❌ Recovery failed for {workflow_name}: {e}")

                    except Exception as e:
                        print(f"❌ Health check failed for {workflow_name}: {e}")
                        check_config["status"] = "error"

            time.sleep(10)  # Check every 10 seconds

    def get_health_status(self):
        """Get current health status of all monitored workflows"""
        status = {}
        for workflow_name, check_config in self.health_checks.items():
            status[workflow_name] = {
                "status": check_config["status"],
                "last_check": check_config["last_check"]
            }
        return status

# Health check functions
def check_api_workflow_health(workflow_name):
    """Check if API workflow is responding"""
    try:
        import requests
        response = requests.post(
            f"http://localhost:8000/workflows/{workflow_name}/execute",
            json={"inputs": {}},
            timeout=5
        )
        return response.status_code == 200
    except:
        return False

def recover_api_workflow(workflow_name):
    """Recovery strategy for API workflow"""
    # Re-register the workflow
    if workflow_name in app.workflows:
        workflow_registration = app.workflows[workflow_name]
        app.register(workflow_name, workflow_registration.workflow)
        print(f"Re-registered workflow: {workflow_name}")

# Set up health monitoring
health_monitor = WorkflowHealthMonitor(app)

# Register a workflow for monitoring
workflow = WorkflowBuilder()
workflow.add_node("HTTPRequestNode", "health_test", {
    "url": "https://httpbin.org/get",
    "method": "GET"
})

app.register("monitored-workflow", workflow.build())

# Add health check and recovery
health_monitor.add_health_check("monitored-workflow", check_api_workflow_health, interval=30)
health_monitor.add_recovery_strategy("monitored-workflow", recover_api_workflow)

# Start monitoring
health_monitor.start_monitoring()
```

## Advanced Registration Patterns

### Conditional Registration

```python
from nexus import Nexus
from kailash.workflow.builder import WorkflowBuilder
import os

app = Nexus()

def conditional_register(name, workflow_factory, condition_func, metadata=None):
    """Register workflow only if condition is met"""

    if condition_func():
        workflow = workflow_factory()
        app.register(name, workflow, metadata=metadata)
        print(f"✅ Conditionally registered: {name}")
        return True
    else:
        print(f"⏭️  Skipped registration: {name} (condition not met)")
        return False

# Condition functions
def is_production_environment():
    return os.getenv("ENVIRONMENT") == "production"

def has_database_access():
    # Check database connectivity
    return True  # Simplified for example

def is_feature_enabled(feature_name):
    return os.getenv(f"FEATURE_{feature_name.upper()}", "false").lower() == "true"

# Workflow factories
def create_production_workflow():
    workflow = WorkflowBuilder()
    workflow.add_node("HTTPRequestNode", "prod_api", {
        "url": "https://api.production.com/data",
        "method": "GET"
    })
    return workflow

def create_database_workflow():
    workflow = WorkflowBuilder()
    workflow.add_node("SQLDatabaseNode", "db_query", {
        "connection_string": "postgresql://localhost/prod",
        "query": "SELECT * FROM users",
        "operation": "select"
    })
    return workflow

# Conditional registrations
conditional_register(
    "production-api",
    create_production_workflow,
    is_production_environment,
    metadata={"environment": "production"}
)

conditional_register(
    "database-query",
    create_database_workflow,
    has_database_access,
    metadata={"requires": "database"}
)

conditional_register(
    "experimental-feature",
    lambda: WorkflowBuilder().add_node("PythonCodeNode", "test", {"code": "result = {'experimental': True}"}).build(),
    lambda: is_feature_enabled("experimental"),
    metadata={"experimental": True}
)
```

### Dependency-Based Registration

```python
from nexus import Nexus
from kailash.workflow.builder import WorkflowBuilder

app = Nexus()

class DependencyManager:
    """Manage workflow dependencies and registration order"""

    def __init__(self, nexus_app):
        self.app = nexus_app
        self.pending = {}
        self.registered = set()

    def register_with_dependencies(self, name, workflow, dependencies=None, metadata=None):
        """Register workflow with dependency resolution"""
        dependencies = dependencies or []

        # Check if all dependencies are satisfied
        if all(dep in self.registered for dep in dependencies):
            # All dependencies satisfied, register immediately
            self.app.register(name, workflow, metadata=metadata)
            self.registered.add(name)
            print(f"✅ Registered: {name}")

            # Check if any pending workflows can now be registered
            self._process_pending()
        else:
            # Store for later registration
            self.pending[name] = {
                "workflow": workflow,
                "dependencies": dependencies,
                "metadata": metadata
            }
            missing = [dep for dep in dependencies if dep not in self.registered]
            print(f"⏳ Pending: {name} (waiting for: {missing})")

    def _process_pending(self):
        """Process pending workflows that may now be ready"""
        ready_to_register = []

        for name, config in self.pending.items():
            if all(dep in self.registered for dep in config["dependencies"]):
                ready_to_register.append(name)

        for name in ready_to_register:
            config = self.pending.pop(name)
            self.app.register(name, config["workflow"], metadata=config["metadata"])
            self.registered.add(name)
            print(f"✅ Registered (dependency resolved): {name}")

        # Recursively process in case new registrations unlock more workflows
        if ready_to_register:
            self._process_pending()

    def get_registration_status(self):
        """Get status of all workflows"""
        return {
            "registered": list(self.registered),
            "pending": list(self.pending.keys())
        }

# Usage example
dep_manager = DependencyManager(app)

# Base workflow (no dependencies)
base_workflow = WorkflowBuilder()
base_workflow.add_node("HTTPRequestNode", "fetch_config", {
    "url": "https://api.example.com/config",
    "method": "GET"
})

dep_manager.register_with_dependencies("config-loader", base_workflow)

# Dependent workflow
data_workflow = WorkflowBuilder()
data_workflow.add_node("HTTPRequestNode", "fetch_data", {
    "url": "https://api.example.com/data",
    "method": "GET"
})

dep_manager.register_with_dependencies(
    "data-processor",
    data_workflow,
    dependencies=["config-loader"]
)

# Complex dependency chain
analytics_workflow = WorkflowBuilder()
analytics_workflow.add_node("PythonCodeNode", "analyze", {
    "code": "return {'analysis': 'complete'}"
})

dep_manager.register_with_dependencies(
    "analytics-engine",
    analytics_workflow,
    dependencies=["config-loader", "data-processor"]
)

print(f"Registration status: {dep_manager.get_registration_status()}")
```

## Registration Best Practices

### Workflow Validation

```python
from nexus import Nexus
from kailash.workflow.builder import WorkflowBuilder

app = Nexus()

class WorkflowValidator:
    """Validate workflows before registration"""

    @staticmethod
    def validate_workflow(workflow, name):
        """Comprehensive workflow validation"""
        errors = []
        warnings = []

        # Check basic structure
        if not workflow.nodes:
            errors.append("Workflow has no nodes")

        if len(workflow.nodes) == 1:
            warnings.append("Workflow has only one node")

        # Check node configurations
        for node_id, node in workflow.nodes.items():
            if not node.parameters:
                warnings.append(f"Node {node_id} has no parameters")

            # Check for required parameters
            if hasattr(node, 'required_parameters'):
                missing = set(node.required_parameters) - set(node.parameters.keys())
                if missing:
                    errors.append(f"Node {node_id} missing required parameters: {missing}")

        # Check connections
        if len(workflow.nodes) > 1 and not workflow.connections:
            warnings.append("Multi-node workflow has no connections")

        # Check for isolated nodes
        connected_nodes = set()
        for conn in workflow.connections:
            connected_nodes.add(conn.from_node)
            connected_nodes.add(conn.to_node)

        isolated = set(workflow.nodes.keys()) - connected_nodes
        if isolated and len(workflow.nodes) > 1:
            warnings.append(f"Isolated nodes detected: {isolated}")

        return {"errors": errors, "warnings": warnings}

    @staticmethod
    def safe_register(nexus_app, name, workflow, metadata=None, strict=False):
        """Register with validation"""
        validation_result = WorkflowValidator.validate_workflow(workflow, name)

        # Print warnings
        for warning in validation_result["warnings"]:
            print(f"⚠️  Warning in {name}: {warning}")

        # Check errors
        if validation_result["errors"]:
            for error in validation_result["errors"]:
                print(f"❌ Error in {name}: {error}")

            if strict:
                raise ValueError(f"Workflow validation failed for {name}")
            else:
                print(f"⏭️  Skipping registration of {name} due to errors")
                return False

        # Register if validation passed
        nexus_app.register(name, workflow, metadata=metadata)
        print(f"✅ Validated and registered: {name}")
        return True

# Example usage
validator = WorkflowValidator()

# Valid workflow
good_workflow = WorkflowBuilder()
good_workflow.add_node("HTTPRequestNode", "fetch", {"url": "https://api.example.com", "method": "GET"})
good_workflow.add_node("JSONReaderNode", "parse", {})

validator.safe_register(app, "good-workflow", good_workflow)

# Invalid workflow (will show warnings)
bad_workflow = WorkflowBuilder()
bad_workflow.add_node("HTTPRequestNode", "fetch", {"url": "https://api.example.com"})  # Missing method

validator.safe_register(app, "bad-workflow", bad_workflow, strict=False)
```

## Next Steps

Explore advanced workflow topics:

1. **[Session Management](session-management.md)** - Cross-channel session handling
2. **[Enterprise Features](enterprise-features.md)** - Production workflow management
3. **[Performance Guide](../technical/performance-guide.md)** - Optimize workflow performance
4. **[Architecture Overview](../technical/architecture-overview.md)** - Deep platform understanding

## Key Takeaways

✅ **Dynamic Registration** → Runtime workflow discovery and loading
✅ **Version Management** → Blue-green deployment and rollback strategies
✅ **Lifecycle Hooks** → Pre/post registration event handling
✅ **Health Monitoring** → Automatic workflow recovery
✅ **Dependency Resolution** → Ordered registration with dependency management
✅ **Validation Framework** → Comprehensive workflow validation before registration

Advanced workflow registration enables sophisticated deployment patterns, automated management, and production-grade reliability for your Nexus platform.
