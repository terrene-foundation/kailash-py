# Workflow Parameter Injection Guide

*Advanced parameter injection patterns for dynamic workflows*

## Overview

Parameter injection allows dynamic configuration of workflows at runtime, enabling flexible, reusable workflow patterns. This guide covers advanced injection techniques and best practices.

## Prerequisites

- Completed [Parameter Passing Guide](11-parameter-passing-guide.md)
- Understanding of [Workflows](02-workflows.md)
- Familiarity with dependency injection concepts

## Important E2E Test Findings

### WorkflowBuilder Parameter Injection

Based on extensive E2E testing, the WorkflowBuilder supports parameter injection through `add_workflow_inputs`:

```python
from kailash.workflow.builder import WorkflowBuilder

# Create workflow
workflow_builder = WorkflowBuilder()

# Add nodes
workflow_builder.add_node("UserManagementNode", "create_user", {
    "operation": "create_user",
    "tenant_id": "default",
    "database_config": db_config
})

# Map workflow-level parameters to node parameters
workflow_builder.add_workflow_inputs("create_user", {
    "user_data": "user_data",      # workflow param -> node param
    "tenant_id": "tenant_id",      # can override node config
    "database_config": "database_config"
})

# Build and execute
workflow = workflow_builder.build("user_workflow")
runtime = LocalRuntime()

# Parameters are injected at runtime
results, _ = runtime.execute(workflow, parameters={
    "user_data": {
        "email": "user@example.com",
        "username": "user123",
        "status": "active"  # Important for permission checks
    },
    "tenant_id": "production"  # Overrides default
})
```

### PythonCodeNode Parameter Access

**CRITICAL**: In PythonCodeNode, parameters are passed directly to the namespace, NOT as `input_data`:

```python
# ❌ WRONG - This will cause "input_data is not defined" error
workflow_builder.add_node("PythonCodeNode", "validator", {
    "code": """
enterprise = input_data.get("enterprise")  # ERROR!
"""
})

# ✅ CORRECT - Parameters are in the namespace directly
workflow_builder.add_node("PythonCodeNode", "validator", {
    "code": """
# Parameters are injected directly into namespace
if not enterprise or not tenant_id:
    raise ValueError("Missing required parameters")

result = {"validated": True, "enterprise": enterprise}
"""
})
```

### Dot Notation for Nested Parameters

The parameter injector supports dot notation for accessing nested data:

```python
# Map nested workflow parameters
workflow_builder.add_workflow_inputs("processor", {
    "user_id": "data.user_id",        # Access nested field
    "role_name": "data.role_name",    # Access nested field
    "config": "settings.processing"    # Deep nesting
})

# Execute with nested parameters
results, _ = runtime.execute(workflow, parameters={
    "data": {
        "user_id": "user123",
        "role_name": "admin"
    },
    "settings": {
        "processing": {"mode": "fast"}
    }
})
```

## Basic Parameter Injection

### Runtime Parameter Injection

```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

# Create parameterizable workflow
workflow = WorkflowBuilder()

# Node that uses injected parameters
workflow.add_node("PythonCodeNode", "configurable_processor", {
    "code": """
# Parameters can be injected at runtime
threshold = config.get("threshold", 0.5)
batch_size = config.get("batch_size", 100)
mode = config.get("mode", "standard")

# Process based on configuration
if mode == "fast":
    result = {"processed": len(data) // 2, "mode": "fast"}
elif mode == "accurate":
    result = {"processed": len(data), "mode": "accurate"}
else:
    result = {"processed": int(len(data) * threshold), "mode": "standard"}
"""
})

# Execute with different configurations
runtime = LocalRuntime()

# Configuration 1: Fast mode
results1, _ = runtime.execute(workflow.build(), parameters={
    "configurable_processor": {
        "data": list(range(1000)),
        "config": {"mode": "fast", "threshold": 0.3}
    }
})

# Configuration 2: Accurate mode
results2, _ = runtime.execute(workflow.build(), parameters={
    "configurable_processor": {
        "data": list(range(1000)),
        "config": {"mode": "accurate", "batch_size": 50}
    }
})
```

### Environment-Based Injection

```python
import os

# Workflow that uses environment variables
workflow = WorkflowBuilder()

workflow.add_node("PythonCodeNode", "env_aware", {
    "code": """
import os

# Get configuration from environment
db_host = os.environ.get("DB_HOST", "localhost")
db_port = int(os.environ.get("DB_PORT", "5432"))
api_key = os.environ.get("API_KEY", "")
environment = os.environ.get("ENVIRONMENT", "development")

# Use environment-specific logic
if environment == "production":
    cache_ttl = 3600  # 1 hour
    log_level = "WARNING"
else:
    cache_ttl = 60    # 1 minute
    log_level = "DEBUG"

result = {
    "db_config": {"host": db_host, "port": db_port},
    "cache_ttl": cache_ttl,
    "log_level": log_level,
    "has_api_key": bool(api_key)
}
"""
})

# Set environment variables before execution
os.environ["ENVIRONMENT"] = "production"
os.environ["DB_HOST"] = "prod-db.example.com"

results, _ = runtime.execute(workflow.build())
```

## Advanced Injection Patterns

### Dependency Injection Container

```python
class DependencyContainer:
    """Container for workflow dependencies."""

    def __init__(self):
        self._services = {}
        self._factories = {}
        self._singletons = {}

    def register(self, name: str, factory: callable, singleton: bool = False):
        """Register a service factory."""
        self._factories[name] = factory
        if singleton:
            self._singletons[name] = None

    def get(self, name: str):
        """Get a service instance."""
        if name not in self._factories:
            raise KeyError(f"Service '{name}' not registered")

        # Return singleton if exists
        if name in self._singletons:
            if self._singletons[name] is None:
                self._singletons[name] = self._factories[name]()
            return self._singletons[name]

        # Create new instance
        return self._factories[name]()

    def inject_into_workflow(self, workflow: WorkflowBuilder):
        """Inject container into workflow."""
        workflow.set_context("container", self)

# Create container
container = DependencyContainer()

# Register services
container.register("database", lambda: DatabaseConnection(), singleton=True)
container.register("cache", lambda: CacheClient(), singleton=True)
container.register("logger", lambda: Logger())

# Workflow using dependency injection
workflow = WorkflowBuilder()

workflow.add_node("PythonCodeNode", "service_user", {
    "code": """
# Get services from container
container = context.get("container")
db = container.get("database")
cache = container.get("cache")
logger = container.get("logger")

# Use services
logger.info("Processing started")
data = await db.query("SELECT * FROM items")
await cache.set("items", data, ttl=300)

result = {"items_processed": len(data)}
"""
})

# Inject container
container.inject_into_workflow(workflow)
```

### Configuration Injection

```python
from dataclasses import dataclass
from typing import Dict, Any

@dataclass
class WorkflowConfig:
    """Strongly-typed workflow configuration."""
    processing_mode: str = "standard"
    batch_size: int = 100
    retry_attempts: int = 3
    timeout_seconds: float = 30.0
    feature_flags: Dict[str, bool] = None

    def __post_init__(self):
        if self.feature_flags is None:
            self.feature_flags = {}

class ConfigurableWorkflowBuilder:
    """Builder with configuration injection."""

    def __init__(self, config: WorkflowConfig):
        self.config = config
        self.workflow = WorkflowBuilder()

    def build(self) -> Workflow:
        """Build workflow with injected configuration."""

        # Add processor with config
        self.workflow.add_node("PythonCodeNode", "processor", {
            "code": f"""
# Injected configuration
batch_size = {self.config.batch_size}
retry_attempts = {self.config.retry_attempts}
timeout = {self.config.timeout_seconds}
mode = "{self.config.processing_mode}"

# Feature flags
features = {self.config.feature_flags}

# Process with configuration
if features.get("parallel_processing", False):
    result = await process_parallel(data, batch_size)
else:
    result = await process_sequential(data, batch_size)

result["mode"] = mode
"""
        })

        return self.workflow.build()

# Use with different configurations
dev_config = WorkflowConfig(
    processing_mode="development",
    batch_size=10,
    feature_flags={"debug_mode": True}
)

prod_config = WorkflowConfig(
    processing_mode="production",
    batch_size=1000,
    timeout_seconds=60.0,
    feature_flags={"parallel_processing": True, "caching": True}
)

dev_workflow = ConfigurableWorkflowBuilder(dev_config).build()
prod_workflow = ConfigurableWorkflowBuilder(prod_config).build()
```

### Dynamic Parameter Resolution

```python
class ParameterResolver:
    """Resolve parameters from multiple sources."""

    def __init__(self):
        self.sources = []

    def add_source(self, source: callable, priority: int = 0):
        """Add parameter source with priority."""
        self.sources.append((priority, source))
        self.sources.sort(key=lambda x: x[0], reverse=True)

    def resolve(self, key: str, default=None):
        """Resolve parameter from sources."""
        for _, source in self.sources:
            try:
                value = source(key)
                if value is not None:
                    return value
            except:
                continue
        return default

# Create resolver with multiple sources
resolver = ParameterResolver()

# Add sources (higher priority first)
resolver.add_source(lambda k: os.environ.get(k), priority=10)  # Environment
resolver.add_source(lambda k: config_file.get(k), priority=5)   # Config file
resolver.add_source(lambda k: defaults.get(k), priority=0)      # Defaults

# Workflow using resolver
workflow = WorkflowBuilder()

workflow.add_node("PythonCodeNode", "dynamic_config", {
    "code": """
# Resolve parameters dynamically
resolver = context["resolver"]

# Get configuration from best available source
db_host = resolver.resolve("DB_HOST", "localhost")
api_timeout = resolver.resolve("API_TIMEOUT", 30)
feature_x = resolver.resolve("FEATURE_X_ENABLED", False)

result = {
    "resolved_config": {
        "db_host": db_host,
        "api_timeout": api_timeout,
        "feature_x": feature_x
    }
}
"""
})

# Inject resolver
workflow.set_context("resolver", resolver)
```

## Conditional Injection

### Feature Flag Injection

```python
class FeatureFlagWorkflow:
    """Workflow with feature flag injection."""

    def __init__(self, feature_flags: dict):
        self.flags = feature_flags

    def build(self) -> Workflow:
        workflow = WorkflowBuilder()

        # Conditionally add nodes based on flags
        if self.flags.get("data_validation", True):
            workflow.add_node("DataValidatorNode", "validator", {
                "strict_mode": self.flags.get("strict_validation", False)
            })

        # Main processor
        workflow.add_node("PythonCodeNode", "processor", {
            "code": f"""
# Feature flags injected
flags = {self.flags}

# Conditional logic based on flags
if flags.get("experimental_algorithm", False):
    result = experimental_process(data)
else:
    result = standard_process(data)

if flags.get("detailed_logging", False):
    result["debug_info"] = generate_debug_info(data)

result["features_enabled"] = list(flags.keys())
"""
        })

        # Conditional connections
        if self.flags.get("data_validation", True):
            workflow.add_connection("validator", "result", "processor", "data")

        return workflow.build()

# Create workflows with different features
basic_workflow = FeatureFlagWorkflow({
    "data_validation": False
}).build()

full_workflow = FeatureFlagWorkflow({
    "data_validation": True,
    "strict_validation": True,
    "experimental_algorithm": True,
    "detailed_logging": True
}).build()
```

### Strategy Pattern Injection

```python
from abc import ABC, abstractmethod

class ProcessingStrategy(ABC):
    """Abstract processing strategy."""

    @abstractmethod
    def process(self, data: list) -> dict:
        pass

class FastStrategy(ProcessingStrategy):
    def process(self, data: list) -> dict:
        return {"result": data[::2], "strategy": "fast"}

class AccurateStrategy(ProcessingStrategy):
    def process(self, data: list) -> dict:
        return {"result": data, "strategy": "accurate"}

class AdaptiveStrategy(ProcessingStrategy):
    def process(self, data: list) -> dict:
        if len(data) > 1000:
            return FastStrategy().execute(data)
        else:
            return AccurateStrategy().execute(data)

# Workflow with strategy injection
workflow = WorkflowBuilder()

# Inject strategy at runtime
workflow.add_node("PythonCodeNode", "strategy_processor", {
    "code": """
# Get injected strategy
strategy = context["strategy"]

# Process using strategy
result = strategy.execute(data)
result["data_size"] = len(data)
"""
})

# Execute with different strategies
runtime = LocalRuntime()

# Fast processing
workflow.set_context("strategy", FastStrategy())
fast_results, _ = runtime.execute(workflow.build(), parameters={
    "strategy_processor": {"data": list(range(10000))}
})

# Adaptive processing
workflow.set_context("strategy", AdaptiveStrategy())
adaptive_results, _ = runtime.execute(workflow.build(), parameters={
    "strategy_processor": {"data": list(range(500))}
})
```

## Testing with Parameter Injection

### Parameterized Tests

```python
import pytest

class TestParameterInjection:
    """Test workflows with parameter injection."""

    @pytest.mark.parametrize("config,expected", [
        ({"mode": "fast", "threshold": 0.5}, {"processed": 50}),
        ({"mode": "accurate", "threshold": 0.8}, {"processed": 100}),
        ({"mode": "standard", "threshold": 0.3}, {"processed": 30}),
    ])
    def test_configurable_workflow(self, config, expected):
        """Test workflow with different configurations."""
        workflow = create_configurable_workflow()

        results, _ = runtime.execute(workflow, parameters={
            "processor": {
                "data": list(range(100)),
                "config": config
            }
        })

        assert results["processor"]["processed"] == expected["processed"]

    def test_dependency_injection(self):
        """Test workflow with dependency injection."""
        # Create test doubles
        mock_db = Mock()
        mock_cache = Mock()

        # Create container with mocks
        container = DependencyContainer()
        container.register("database", lambda: mock_db)
        container.register("cache", lambda: mock_cache)

        # Test workflow
        workflow = create_workflow_with_dependencies()
        container.inject_into_workflow(workflow)

        results, _ = runtime.execute(workflow.build())

        # Verify interactions
        mock_db.query.assert_called_once()
        mock_cache.set.assert_called_once()
```

### Injection Fixtures

```python
@pytest.fixture
def test_config():
    """Provide test configuration."""
    return WorkflowConfig(
        processing_mode="test",
        batch_size=10,
        retry_attempts=1,
        timeout_seconds=5.0,
        feature_flags={"test_mode": True}
    )

@pytest.fixture
def test_container():
    """Provide test dependency container."""
    container = DependencyContainer()

    # Register test services
    container.register("database", lambda: InMemoryDatabase())
    container.register("cache", lambda: InMemoryCache())
    container.register("logger", lambda: TestLogger())

    return container

def test_with_fixtures(test_config, test_container):
    """Test using injection fixtures."""
    workflow = ConfigurableWorkflowBuilder(test_config).build()
    test_container.inject_into_workflow(workflow)

    results, _ = runtime.execute(workflow.build())
    assert results["status"] == "success"
```

## Best Practices

### 1. Type Safety

```python
from typing import TypedDict, Literal

class ProcessingConfig(TypedDict):
    mode: Literal["fast", "accurate", "standard"]
    threshold: float
    batch_size: int
    retry_policy: dict

def validate_config(config: ProcessingConfig) -> None:
    """Validate configuration before injection."""
    if not 0 <= config["threshold"] <= 1:
        raise ValueError("Threshold must be between 0 and 1")
    if config["batch_size"] < 1:
        raise ValueError("Batch size must be positive")
```

### 2. Configuration Isolation

```python
class IsolatedConfig:
    """Isolated configuration to prevent mutations."""

    def __init__(self, config: dict):
        self._config = deepcopy(config)

    def get(self, key: str, default=None):
        """Get configuration value (read-only)."""
        return self._config.get(key, default)

    def to_dict(self) -> dict:
        """Get configuration copy."""
        return deepcopy(self._config)
```

### 3. Injection Documentation

```python
class DocumentedWorkflow:
    """Workflow with clear injection requirements."""

    REQUIRED_CONFIG = {
        "processing_mode": "Mode of processing (fast/accurate/standard)",
        "threshold": "Processing threshold (0.0-1.0)",
        "batch_size": "Size of processing batches (>0)"
    }

    REQUIRED_SERVICES = {
        "database": "Database connection for data access",
        "cache": "Cache client for result caching",
        "logger": "Logger for operation tracking"
    }

    @classmethod
    def validate_injection(cls, config: dict, container: DependencyContainer):
        """Validate all required injections are present."""
        # Check config
        for key in cls.REQUIRED_CONFIG:
            if key not in config:
                raise ValueError(f"Missing required config: {key}")

        # Check services
        for service in cls.REQUIRED_SERVICES:
            try:
                container.get(service)
            except KeyError:
                raise ValueError(f"Missing required service: {service}")
```

## Related Guides

**Prerequisites:**
- [Parameter Passing Guide](11-parameter-passing-guide.md) - Basic parameters
- [Workflows](02-workflows.md) - Workflow fundamentals

**Advanced Topics:**
- [Testing Guide](12-testing-production-quality.md) - Testing patterns
- [Production](04-production.md) - Production configuration

---

**Build flexible, configurable workflows with advanced parameter injection techniques!**
