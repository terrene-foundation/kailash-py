# Kaizen API Reference

Complete API reference for the Kaizen Framework, providing detailed documentation for all classes, methods, and interfaces.

## Core Classes

### Kaizen
**Primary framework interface**

```python
class Kaizen:
    """Main Kaizen framework interface."""

    def __init__(self, config: Optional[Dict] = None):
        """Initialize Kaizen framework.

        Args:
            config: Framework configuration dictionary
        """

    def create_agent(self, name: str, config: Dict) -> Agent:
        """Create a new agent with specified configuration.

        Args:
            name: Agent identifier
            config: Agent configuration including model, signature, etc.

        Returns:
            Configured Agent instance
        """

    def get_transparency_interface(self) -> TransparencyInterface:
        """Get transparency interface for monitoring.

        Returns:
            TransparencyInterface instance
        """

### Agent
**Individual agent representation**

```python
class Agent:
    """Individual Kaizen agent."""

    def __init__(self, name: str, config: Dict):
        """Initialize agent with configuration."""

    @property
    def workflow(self) -> WorkflowBuilder:
        """Get agent's workflow builder."""

    def execute(self, inputs: Dict) -> Tuple[Dict, str]:
        """Execute agent with inputs.

        Args:
            inputs: Input data for agent

        Returns:
            Tuple of (results, run_id)
        """

### Signature
**Type-safe input/output definitions**

```python
import dspy

class Signature(dspy.Signature):
    """Base signature class for Kaizen agents."""

    # Input fields
    input_field: str = dspy.InputField(desc="Description")

    # Output fields
    output_field: str = dspy.OutputField(desc="Description")
```

## Configuration Reference

### Framework Configuration

```python
framework_config = {
    # Core settings
    "signature_programming_enabled": True,
    "performance_tracking": True,
    "transparency_enabled": True,

    # Caching settings
    "cache_enabled": True,
    "cache_backend": "memory",  # memory, redis, database
    "cache_ttl": 3600,

    # Monitoring settings
    "monitoring_level": "basic",  # basic, detailed, comprehensive
    "metrics_retention": "7d",
    "real_time_metrics": False,

    # Enterprise settings
    "security_profile": "standard",  # standard, enterprise
    "audit_enabled": False,
    "compliance_mode": False
}
```

### Agent Configuration

```python
agent_config = {
    # LLM settings
    "model": "gpt-4",
    "temperature": 0.7,
    "max_tokens": 1000,
    "system_prompt": "You are a helpful assistant",

    # Signature programming
    "signature": YourSignature,

    # Performance settings
    "timeout": 30,
    "retry_attempts": 3,
    "stream": False,

    # Memory settings (planned)
    "memory_enabled": False,
    "memory_type": "vector",  # vector, episodic, semantic
    "memory_capacity": 10000,

    # Caching settings
    "caching": {
        "enable_response_cache": True,
        "cache_key_strategy": "content_hash",
        "similarity_threshold": 0.9
    },

    # MCP integration (planned)
    "mcp_capabilities": ["search", "calculate"],
    "auto_discovery": True,

    # Monitoring
    "transparency": {
        "monitoring_level": "basic",
        "decision_tracing": False,
        "performance_profiling": False
    }
}
```

## Error Codes Reference

### Framework Errors

| Error Code | Description | Resolution |
|------------|-------------|------------|
| `KAIZEN_001` | Framework initialization failed | Check configuration validity |
| `KAIZEN_002` | Invalid configuration provided | Review configuration schema |
| `KAIZEN_003` | Required dependency missing | Install missing dependencies |

### Agent Errors

| Error Code | Description | Resolution |
|------------|-------------|------------|
| `AGENT_001` | Agent creation failed | Check agent configuration |
| `AGENT_002` | Invalid signature provided | Verify signature definition |
| `AGENT_003` | Execution timeout | Increase timeout or optimize |
| `AGENT_004` | Model API error | Check API credentials and limits |

### Execution Errors

| Error Code | Description | Resolution |
|------------|-------------|------------|
| `EXEC_001` | Invalid input format | Check input against signature |
| `EXEC_002` | Workflow build failed | Verify workflow configuration |
| `EXEC_003` | Runtime execution error | Check runtime setup and resources |

## Performance Reference

### Benchmarks

**Framework Initialization:**
- Cold start: ~1116ms (current), target: <100ms
- Warm start: ~50ms

**Agent Creation:**
- Simple agent: <50ms average
- Complex agent with signature: <100ms average

**Execution Performance:**
- Simple Q&A: <2 seconds (95th percentile)
- Complex reasoning: <10 seconds (95th percentile)
- Multi-agent coordination: <30 seconds (95th percentile)

### Optimization Guidelines

**Memory Usage:**
- Framework overhead: ~50MB
- Per-agent overhead: ~10MB
- Model context: Variable based on model

**Throughput:**
- Single agent: >100 queries/minute
- Multi-agent: >20 coordinated tasks/minute

**Cost Optimization:**
- Use appropriate model for task complexity
- Enable caching for repeated queries
- Implement batch processing where possible

## Integration Patterns

### Kailash Core SDK Integration

```python
# Standard Core SDK pattern
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

workflow = WorkflowBuilder()
workflow.add_node("LLMAgentNode", "agent", config)
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())

# Enhanced Kaizen pattern
from kaizen import Kaizen

kaizen = Kaizen()
agent = kaizen.create_agent("enhanced_agent", config)
runtime = LocalRuntime()
results, run_id = runtime.execute(agent.workflow.build())
```

### DataFlow Integration (Planned)

```python
# Future DataFlow integration
from dataflow import db

@db.model
class AgentInput:
    query: str
    context: str

@db.model
class AgentOutput:
    response: str
    confidence: float

@kaizen.signature("input -> output")
def database_aware_agent(input: AgentInput) -> AgentOutput:
    """Agent with automatic database context."""
    pass
```

### Nexus Integration (Planned)

```python
# Future Nexus multi-channel deployment
agent = kaizen.create_agent("service_agent", config)

service = agent.deploy_as_nexus(
    name="service-v1",
    channels=["api", "cli", "mcp"],
    monitoring=True
)
```

## Migration Guide

### From Core SDK to Kaizen

**Basic Migration:**
```python
# Before: Core SDK
workflow = WorkflowBuilder()
workflow.add_node("LLMAgentNode", "agent", {
    "model": "gpt-4",
    "prompt_template": "Answer: {query}"
})

# After: Kaizen with signature programming
class QASignature(dspy.Signature):
    query: str = dspy.InputField()
    answer: str = dspy.OutputField()

agent = kaizen.create_agent("qa_agent", {
    "model": "gpt-4",
    "signature": QASignature
})
```

**Runtime Compatibility:**
- Same LocalRuntime usage
- Same workflow.build() pattern
- Same results format

### Version Compatibility

| Kaizen Version | Core SDK Version | Python Version |
|----------------|------------------|----------------|
| 1.0.0 (planned) | >=0.9.19 | >=3.8 |
| 0.1.0 (current) | >=0.9.19 | >=3.8 |

## Advanced Features Reference

### Signature Programming (Available)

```python
# Input/Output type definitions
class AdvancedSignature(dspy.Signature):
    """Complex signature with multiple fields."""

    # Input fields with validation
    user_query: str = dspy.InputField(desc="User question")
    context: Optional[str] = dspy.InputField(desc="Additional context")
    complexity_level: int = dspy.InputField(desc="1-5 complexity rating")

    # Output fields with constraints
    response: str = dspy.OutputField(desc="Detailed response")
    confidence: float = dspy.OutputField(desc="Confidence 0.0-1.0")
    citations: List[str] = dspy.OutputField(desc="Source citations")
    follow_up_questions: List[str] = dspy.OutputField(desc="Suggested follow-ups")
```

### Memory System (Planned)

```python
# Future memory configuration
memory_config = {
    "type": "hybrid",  # episodic + semantic
    "capacity": 10000,
    "decay_function": "exponential",
    "retrieval_strategy": "similarity",
    "embedding_model": "text-embedding-ada-002"
}
```

### Multi-Agent Coordination (Planned)

```python
# Future coordination patterns
coordination_config = {
    "pattern": "supervisor_worker",
    "agents": ["supervisor", "worker1", "worker2"],
    "communication": "message_passing",
    "consensus_threshold": 0.75
}
```

---

**📚 Complete API Reference**: This comprehensive reference provides all necessary information for developing with the Kaizen Framework, from basic usage to advanced enterprise features.
