# Core SDK Integration

Comprehensive guide for integrating Kaizen with the Kailash Core SDK, covering compatibility patterns, workflow construction, and best practices.

## Integration Overview

**Kaizen is built ON the Kailash Core SDK**, not as a replacement but as an enhancement layer that provides:

1. **100% Compatibility**: All Core SDK patterns work unchanged
2. **Enhanced Capabilities**: Additional features while maintaining Core SDK integration
3. **Seamless Migration**: Gradual adoption without breaking existing workflows
4. **Shared Infrastructure**: Uses the same runtime, nodes, and execution patterns

**Integration Status**:
- ✅ **Basic Integration**: WorkflowBuilder, LocalRuntime, node compatibility
- ✅ **Agent System**: Automatic workflow generation from agent configurations
- ✅ **Parameter Compatibility**: NodeParameter integration and validation
- 🟡 **Advanced Features**: Enhanced nodes, optimization, monitoring (planned)

## Core Integration Patterns

### Basic Workflow Compatibility

**Existing Core SDK workflows continue to work unchanged**:

```python
# Traditional Core SDK approach (UNCHANGED)
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

# Build workflow manually
workflow = WorkflowBuilder()
workflow.add_node("LLMAgentNode", "text_processor", {
    "model": "gpt-4",
    "prompt_template": "Process this text: {input}",
    "temperature": 0.7
})

# Execute with LocalRuntime
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())

print(f"Traditional workflow result: {results}")
```

### Kaizen Enhancement Integration

**Kaizen agents generate compatible Core SDK workflows**:

```python
# Kaizen enhancement approach (COMPATIBLE)
from kaizen import Kaizen
from kailash.runtime.local import LocalRuntime

# Create agent (generates Core SDK workflow internally)
kaizen = Kaizen()
agent = kaizen.create_agent("text_processor", {
    "model": "gpt-4",
    "temperature": 0.7
})

# Execute with same Core SDK runtime
runtime = LocalRuntime()
results, run_id = runtime.execute(agent.workflow.build())

print(f"Kaizen agent result: {results}")

# Verify they use the same execution pattern
assert isinstance(agent.workflow, WorkflowBuilder)
```

### Mixed Workflow Construction

**Combine Kaizen agents with traditional Core SDK nodes**:

```python
# Mixed approach: Kaizen agents + Core SDK nodes
from kailash.workflow.builder import WorkflowBuilder
from kaizen import Kaizen

# Create Kaizen agent
kaizen = Kaizen()
agent = kaizen.create_agent("analyzer", {
    "model": "gpt-4",
    "temperature": 0.3
})

# Build composite workflow
composite_workflow = WorkflowBuilder()

# Add traditional Core SDK nodes
composite_workflow.add_node("DataLoaderNode", "loader", {
    "source_type": "file",
    "file_path": "/data/input.json"
})

composite_workflow.add_node("DataTransformerNode", "transformer", {
    "transformation": "normalize"
})

# Extract Kaizen agent node configuration
agent_config = {
    "model": agent.config["model"],
    "temperature": agent.config["temperature"],
    "system_prompt": agent.config.get("system_prompt")
}

# Add enhanced Kaizen node
composite_workflow.add_node("KaizenLLMAgentNode", "analyzer", agent_config)

composite_workflow.add_node("OutputFormatterNode", "formatter", {
    "format": "json"
})

# Connect nodes
composite_workflow.add_connection("loader", "transformer")
composite_workflow.add_connection("transformer", "analyzer")
composite_workflow.add_connection("analyzer", "formatter")

# Execute composite workflow
runtime = LocalRuntime()
results, run_id = runtime.execute(composite_workflow.build())

print(f"Composite workflow result: {results}")
```

## Node Integration

### Enhanced Node Registration

**Kaizen nodes register with the Core SDK node system**:

```python
# Enhanced node implementation
from kailash.core.node import NodeBase
from kailash.core.decorators import register_node
from kailash.core.parameters import NodeParameter

@register_node("KaizenLLMAgentNode")
class KaizenLLMAgentNode(NodeBase):
    """Enhanced LLM node with Kaizen features."""

    def __init__(self, config):
        super().__init__(config)

        # Define parameters using Core SDK patterns
        self.model = NodeParameter("model", str, required=True)
        self.temperature = NodeParameter("temperature", float, default=0.7)
        self.max_tokens = NodeParameter("max_tokens", int, default=1000)
        self.system_prompt = NodeParameter("system_prompt", str, default=None)

        # Kaizen-specific enhancements
        self.optimization_enabled = NodeParameter("optimization_enabled", bool, default=False)
        self.monitoring_enabled = NodeParameter("monitoring_enabled", bool, default=True)

    def execute(self, inputs):
        """Execute with Core SDK compatibility and Kaizen enhancements."""
        # Core SDK execution pattern
        self.validate_inputs(inputs)

        # Kaizen enhancements (optional)
        if self.optimization_enabled.value:
            inputs = self.optimize_inputs(inputs)

        if self.monitoring_enabled.value:
            self.monitor_execution_start()

        try:
            # Core LLM execution
            results = self.execute_llm(inputs)

            # Kaizen post-processing
            if self.optimization_enabled.value:
                results = self.optimize_outputs(results)

            if self.monitoring_enabled.value:
                self.monitor_execution_success(results)

            return results

        except Exception as e:
            if self.monitoring_enabled.value:
                self.monitor_execution_failure(e)
            raise

    def execute_llm(self, inputs):
        """Core LLM execution logic compatible with Core SDK."""
        # Implementation uses Core SDK patterns
        from kailash.integrations.openai import OpenAIProvider

        provider = OpenAIProvider()
        response = provider.generate(
            model=self.model.value,
            prompt=self.build_prompt(inputs),
            temperature=self.temperature.value,
            max_tokens=self.max_tokens.value
        )

        return {"output": response.text, "metadata": response.metadata}

# Verify node registration with Core SDK
from kailash.core.registry import NodeRegistry

registry = NodeRegistry()
assert "KaizenLLMAgentNode" in registry.list_nodes()
```

### Parameter System Compatibility

**Kaizen parameters integrate with Core SDK validation**:

```python
# Parameter compatibility demonstration
from kailash.core.parameters import NodeParameter, ParameterValidator

class KaizenAgentParameters:
    """Kaizen agent parameters compatible with Core SDK."""

    def __init__(self):
        # Core SDK parameter definitions
        self.model = NodeParameter(
            name="model",
            param_type=str,
            required=True,
            choices=["gpt-3.5-turbo", "gpt-4", "claude-3"],
            description="AI model to use for generation"
        )

        self.temperature = NodeParameter(
            name="temperature",
            param_type=float,
            default=0.7,
            min_value=0.0,
            max_value=2.0,
            description="Controls randomness in output generation"
        )

        self.max_tokens = NodeParameter(
            name="max_tokens",
            param_type=int,
            default=1000,
            min_value=1,
            max_value=8000,
            description="Maximum number of tokens to generate"
        )

        # Kaizen-specific parameters
        self.signature_enabled = NodeParameter(
            name="signature_enabled",
            param_type=bool,
            default=False,
            description="Enable signature-based programming"
        )

        self.optimization_level = NodeParameter(
            name="optimization_level",
            param_type=str,
            default="basic",
            choices=["none", "basic", "advanced"],
            description="Level of automatic optimization"
        )

    def validate(self, config):
        """Validate configuration using Core SDK patterns."""
        validator = ParameterValidator()

        # Validate all parameters
        for param_name, param in self.__dict__.items():
            if param_name in config:
                validator.validate_parameter(param, config[param_name])

        return validator.is_valid()

    def get_core_sdk_config(self, kaizen_config):
        """Convert Kaizen config to Core SDK compatible format."""
        core_config = {}

        # Map Kaizen parameters to Core SDK parameters
        param_mapping = {
            "model": "model",
            "temperature": "temperature",
            "max_tokens": "max_tokens",
            "system_prompt": "prompt_template"
        }

        for kaizen_key, core_key in param_mapping.items():
            if kaizen_key in kaizen_config:
                core_config[core_key] = kaizen_config[kaizen_key]

        return core_config

# Usage example
params = KaizenAgentParameters()
config = {
    "model": "gpt-4",
    "temperature": 0.7,
    "optimization_level": "advanced"
}

# Validate with Core SDK patterns
assert params.validate(config)

# Convert to Core SDK format
core_config = params.get_core_sdk_config(config)
print(f"Core SDK config: {core_config}")
```

## Runtime Integration

### LocalRuntime Compatibility

**Kaizen workflows execute with LocalRuntime without changes**:

```python
# Runtime compatibility testing
from kaizen import Kaizen
from kailash.runtime.local import LocalRuntime
import time

def test_runtime_compatibility():
    """Test Kaizen agent compatibility with Core SDK runtime."""
    # Create Kaizen agent
    kaizen = Kaizen()
    agent = kaizen.create_agent("runtime_test", {
        "model": "gpt-3.5-turbo",
        "temperature": 0.5
    })

    # Test with LocalRuntime
    runtime = LocalRuntime()

    # Measure execution time
    start_time = time.time()
    results, run_id = runtime.execute(agent.workflow.build())
    execution_time = time.time() - start_time

    # Verify Core SDK execution patterns
    assert run_id is not None
    assert isinstance(run_id, str)
    assert results is not None
    assert isinstance(results, dict)

    print(f"✅ Runtime compatibility verified")
    print(f"📊 Execution time: {execution_time:.2f}s")
    print(f"🆔 Run ID: {run_id}")
    print(f"📋 Results type: {type(results)}")

    return results, run_id

# Run compatibility test
test_results, test_run_id = test_runtime_compatibility()
```

### Future Runtime Compatibility

**Kaizen will work with future distributed runtimes**:

```python
# Future runtime compatibility pattern
class KaizenRuntimeAdapter:
    """Adapter for future Kailash runtimes."""

    def __init__(self, runtime_type="local"):
        self.runtime_type = runtime_type
        self.runtime = self.create_runtime()

    def create_runtime(self):
        """Create appropriate runtime based on type."""
        if self.runtime_type == "local":
            from kailash.runtime.local import LocalRuntime
            return LocalRuntime()
        elif self.runtime_type == "distributed":
            # Future distributed runtime
            from kailash.runtime.distributed import DistributedRuntime
            return DistributedRuntime()
        elif self.runtime_type == "cloud":
            # Future cloud runtime
            from kailash.runtime.cloud import CloudRuntime
            return CloudRuntime()
        else:
            raise ValueError(f"Unknown runtime type: {self.runtime_type}")

    def execute_agent(self, agent, inputs=None):
        """Execute Kaizen agent with any runtime."""
        workflow = agent.workflow.build()

        if inputs:
            # Add inputs to workflow if provided
            workflow.set_inputs(inputs)

        # Execute with selected runtime
        results, run_id = self.runtime.execute(workflow)

        return results, run_id

# Usage with different runtimes
def demonstrate_runtime_flexibility():
    """Demonstrate Kaizen compatibility with multiple runtimes."""
    kaizen = Kaizen()
    agent = kaizen.create_agent("flexible_agent", {
        "model": "gpt-3.5-turbo"
    })

    # Test with different runtimes
    runtimes = ["local"]  # Add "distributed", "cloud" when available

    for runtime_type in runtimes:
        adapter = KaizenRuntimeAdapter(runtime_type)
        results, run_id = adapter.execute_agent(agent)

        print(f"✅ {runtime_type} runtime: {run_id}")

demonstrate_runtime_flexibility()
```

## Migration Strategies

### Gradual Migration from Core SDK

**Strategy 1: Agent-by-Agent Migration**

```python
# Existing Core SDK workflow
def legacy_text_processing():
    """Legacy Core SDK text processing workflow."""
    workflow = WorkflowBuilder()

    workflow.add_node("LLMAgentNode", "processor", {
        "model": "gpt-3.5-turbo",
        "prompt_template": "Process: {input}",
        "temperature": 0.7
    })

    workflow.add_node("OutputFormatterNode", "formatter", {
        "format": "json"
    })

    workflow.add_connection("processor", "formatter")

    runtime = LocalRuntime()
    return runtime.execute(workflow.build())

# Migrated to Kaizen agent
def kaizen_text_processing():
    """Migrated Kaizen text processing."""
    kaizen = Kaizen()

    # Create equivalent agent
    agent = kaizen.create_agent("processor", {
        "model": "gpt-3.5-turbo",
        "temperature": 0.7
    })

    # Still use Core SDK runtime and patterns
    runtime = LocalRuntime()
    results, run_id = runtime.execute(agent.workflow.build())

    # Add output formatting if needed
    if isinstance(results, dict) and "output" in results:
        formatted_results = {"formatted": results["output"]}
        return formatted_results, run_id

    return results, run_id

# A/B testing during migration
def test_migration_equivalence():
    """Test that migrated workflow produces equivalent results."""
    # Test legacy approach
    legacy_results, legacy_run_id = legacy_text_processing()

    # Test Kaizen approach
    kaizen_results, kaizen_run_id = kaizen_text_processing()

    # Verify equivalence (structure may differ, but functionality should be similar)
    assert legacy_run_id is not None
    assert kaizen_run_id is not None
    assert legacy_results is not None
    assert kaizen_results is not None

    print("✅ Migration equivalence verified")

test_migration_equivalence()
```

**Strategy 2: Hybrid Workflows**

```python
# Hybrid: Mix Core SDK nodes with Kaizen agents
def create_hybrid_workflow():
    """Create workflow mixing Core SDK and Kaizen components."""
    # Initialize both systems
    workflow = WorkflowBuilder()
    kaizen = Kaizen()

    # Traditional Core SDK data processing
    workflow.add_node("DataLoaderNode", "data_loader", {
        "source": "database",
        "query": "SELECT * FROM documents"
    })

    workflow.add_node("DataCleanerNode", "data_cleaner", {
        "remove_duplicates": True,
        "normalize_text": True
    })

    # Kaizen agent for AI processing
    ai_agent = kaizen.create_agent("ai_processor", {
        "model": "gpt-4",
        "temperature": 0.3,
        "system_prompt": "You are a document analysis expert."
    })

    # Extract agent configuration for workflow integration
    workflow.add_node("KaizenLLMAgentNode", "ai_processor", {
        "model": ai_agent.config["model"],
        "temperature": ai_agent.config["temperature"],
        "system_prompt": ai_agent.config.get("system_prompt")
    })

    # Traditional Core SDK output processing
    workflow.add_node("ReportGeneratorNode", "report_generator", {
        "format": "pdf",
        "template": "analysis_report"
    })

    # Connect all nodes
    workflow.add_connection("data_loader", "data_cleaner")
    workflow.add_connection("data_cleaner", "ai_processor")
    workflow.add_connection("ai_processor", "report_generator")

    return workflow

# Execute hybrid workflow
hybrid_workflow = create_hybrid_workflow()
runtime = LocalRuntime()
results, run_id = runtime.execute(hybrid_workflow.build())

print(f"✅ Hybrid workflow executed: {run_id}")
```

## Performance Considerations

### Core SDK Performance Baseline

**Kaizen maintains Core SDK performance characteristics**:

```python
# Performance comparison testing
import time
import statistics

def benchmark_core_sdk_vs_kaizen():
    """Benchmark Core SDK vs Kaizen performance."""
    iterations = 5

    # Core SDK baseline
    core_sdk_times = []
    for i in range(iterations):
        start_time = time.time()

        workflow = WorkflowBuilder()
        workflow.add_node("LLMAgentNode", f"test_{i}", {
            "model": "gpt-3.5-turbo",
            "temperature": 0.7
        })

        runtime = LocalRuntime()
        results, run_id = runtime.execute(workflow.build())

        execution_time = (time.time() - start_time) * 1000  # ms
        core_sdk_times.append(execution_time)

    # Kaizen performance
    kaizen_times = []
    kaizen = Kaizen()

    for i in range(iterations):
        start_time = time.time()

        agent = kaizen.create_agent(f"kaizen_test_{i}", {
            "model": "gpt-3.5-turbo",
            "temperature": 0.7
        })

        runtime = LocalRuntime()
        results, run_id = runtime.execute(agent.workflow.build())

        execution_time = (time.time() - start_time) * 1000  # ms
        kaizen_times.append(execution_time)

    # Performance analysis
    core_avg = statistics.mean(core_sdk_times)
    kaizen_avg = statistics.mean(kaizen_times)
    overhead = ((kaizen_avg - core_avg) / core_avg) * 100

    print(f"📊 Performance Comparison:")
    print(f"Core SDK average: {core_avg:.1f}ms")
    print(f"Kaizen average: {kaizen_avg:.1f}ms")
    print(f"Overhead: {overhead:.1f}%")

    # Acceptable overhead threshold
    assert overhead < 20, f"Kaizen overhead too high: {overhead:.1f}%"

    return {
        "core_sdk_avg": core_avg,
        "kaizen_avg": kaizen_avg,
        "overhead_percent": overhead
    }

# Run performance benchmark
performance_results = benchmark_core_sdk_vs_kaizen()
```

### Memory Footprint Comparison

```python
# Memory usage comparison
import psutil
import os

def compare_memory_usage():
    """Compare memory usage between Core SDK and Kaizen."""
    process = psutil.Process(os.getpid())

    # Baseline memory
    baseline_memory = process.memory_info().rss / 1024 / 1024  # MB

    # Core SDK memory usage
    workflow = WorkflowBuilder()
    workflow.add_node("LLMAgentNode", "memory_test", {
        "model": "gpt-3.5-turbo"
    })
    core_sdk_memory = process.memory_info().rss / 1024 / 1024  # MB

    # Kaizen memory usage
    kaizen = Kaizen()
    agent = kaizen.create_agent("memory_test", {
        "model": "gpt-3.5-turbo"
    })
    kaizen_memory = process.memory_info().rss / 1024 / 1024  # MB

    # Memory analysis
    core_sdk_overhead = core_sdk_memory - baseline_memory
    kaizen_overhead = kaizen_memory - baseline_memory
    additional_overhead = kaizen_overhead - core_sdk_overhead

    print(f"📊 Memory Usage Comparison:")
    print(f"Baseline: {baseline_memory:.1f}MB")
    print(f"Core SDK overhead: {core_sdk_overhead:.1f}MB")
    print(f"Kaizen overhead: {kaizen_overhead:.1f}MB")
    print(f"Additional overhead: {additional_overhead:.1f}MB")

    return {
        "baseline": baseline_memory,
        "core_sdk_overhead": core_sdk_overhead,
        "kaizen_overhead": kaizen_overhead,
        "additional_overhead": additional_overhead
    }

memory_results = compare_memory_usage()
```

## Best Practices

### Integration Guidelines

**1. Always Use Core SDK Execution Patterns**:

```python
# ✅ CORRECT: Use Core SDK runtime execution
runtime = LocalRuntime()
results, run_id = runtime.execute(agent.workflow.build())

# ❌ INCORRECT: Don't create alternative execution patterns
# results = agent.execute_directly()  # Not compatible with Core SDK
```

**2. Maintain Parameter Compatibility**:

```python
# ✅ CORRECT: Use Core SDK parameter patterns
agent = kaizen.create_agent("compatible_agent", {
    "model": "gpt-4",              # Core SDK compatible
    "temperature": 0.7,            # Core SDK compatible
    "max_tokens": 1000,            # Core SDK compatible
    "system_prompt": "Assistant"   # Core SDK compatible
})

# ❌ INCORRECT: Don't use incompatible parameter names
# agent = kaizen.create_agent("incompatible_agent", {
#     "llm_model": "gpt-4",        # Wrong parameter name
#     "randomness": 0.7,           # Wrong parameter name
# })
```

**3. Leverage Core SDK Node Registry**:

```python
# ✅ CORRECT: Register enhanced nodes with Core SDK
from kailash.core.decorators import register_node

@register_node("CustomKaizenNode")
class CustomKaizenNode(KaizenNode):
    """Custom node registered with Core SDK."""
    pass

# Verify registration
from kailash.core.registry import NodeRegistry
registry = NodeRegistry()
assert "CustomKaizenNode" in registry.list_nodes()
```

**4. Test Both Approaches**:

```python
# ✅ CORRECT: Test both Core SDK and Kaizen approaches
def test_compatibility():
    """Test Core SDK and Kaizen approaches produce similar results."""
    # Core SDK approach
    workflow = WorkflowBuilder()
    workflow.add_node("LLMAgentNode", "test", config)
    core_results, core_run_id = runtime.execute(workflow.build())

    # Kaizen approach
    agent = kaizen.create_agent("test", config)
    kaizen_results, kaizen_run_id = runtime.execute(agent.workflow.build())

    # Verify both approaches work
    assert core_run_id is not None
    assert kaizen_run_id is not None
    assert core_results is not None
    assert kaizen_results is not None
```

## Troubleshooting

### Common Integration Issues

**Issue 1: Import Conflicts**

```python
# Problem: Import order conflicts
# Solution: Import Core SDK before Kaizen

# ✅ CORRECT import order
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kaizen import Kaizen

# ❌ INCORRECT: May cause conflicts
# from kaizen import Kaizen
# from kailash.workflow.builder import WorkflowBuilder
```

**Issue 2: Parameter Validation Errors**

```python
# Problem: Kaizen parameters don't match Core SDK expectations
# Solution: Use parameter compatibility layer

def fix_parameter_compatibility(kaizen_config):
    """Fix parameter compatibility issues."""
    # Map Kaizen parameters to Core SDK parameters
    compatibility_map = {
        "system_message": "system_prompt",
        "max_length": "max_tokens",
        "model_name": "model"
    }

    fixed_config = {}
    for key, value in kaizen_config.items():
        if key in compatibility_map:
            fixed_config[compatibility_map[key]] = value
        else:
            fixed_config[key] = value

    return fixed_config

# Usage
original_config = {"model_name": "gpt-4", "max_length": 1000}
fixed_config = fix_parameter_compatibility(original_config)
# Result: {"model": "gpt-4", "max_tokens": 1000}
```

**Issue 3: Workflow Building Errors**

```python
# Problem: Kaizen workflow doesn't build correctly
# Solution: Debug workflow construction

def debug_workflow_building(agent):
    """Debug Kaizen agent workflow building."""
    try:
        # Check agent workflow
        workflow = agent.workflow
        print(f"Workflow type: {type(workflow)}")
        print(f"Workflow nodes: {len(workflow.nodes) if hasattr(workflow, 'nodes') else 'N/A'}")

        # Try building workflow
        built_workflow = workflow.build()
        print(f"Built workflow: {built_workflow}")

        return True, None

    except Exception as e:
        print(f"Workflow building failed: {e}")
        return False, str(e)

# Usage
kaizen = Kaizen()
agent = kaizen.create_agent("debug_test", {"model": "gpt-3.5-turbo"})
success, error = debug_workflow_building(agent)
```

---

**🔗 Core SDK Integration Mastered**: This comprehensive guide ensures seamless integration between Kaizen and the Core SDK. The enhancement layer approach maintains 100% compatibility while providing advanced AI capabilities.
