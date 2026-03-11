# Basic Examples

Working examples to demonstrate Kaizen's core capabilities and integration patterns.

## Quick Reference

- **✅ Available Now**: Basic framework, agent creation, Core SDK integration
- **🟡 In Development**: Signature programming, MCP integration, multi-agent coordination
- **🔵 Planned**: Advanced enterprise features, optimization engine

## Example Categories

### 1. Basic Agent Operations

#### Example 1: Simple Text Processing Agent

**Status**: ✅ Working Implementation

```python
from kaizen import Kaizen
from kailash.runtime.local import LocalRuntime

# Initialize framework
kaizen = Kaizen()

# Create a text processing agent
agent = kaizen.create_agent("text_processor", {
    "model": "gpt-4",
    "temperature": 0.7,
    "max_tokens": 1000
})

# Execute using Core SDK runtime
runtime = LocalRuntime()
results, run_id = runtime.execute(agent.workflow.build())

print(f"✅ Agent executed successfully!")
print(f"📊 Run ID: {run_id}")
print(f"🎯 Results: {results}")
```

**What this demonstrates**:
- Basic Kaizen framework initialization
- Agent creation with configuration
- Core SDK runtime integration
- Standard workflow execution pattern

#### Example 2: Agent with Configuration

**Status**: ✅ Working Implementation

```python
from kaizen import Kaizen

# Framework with global configuration
kaizen = Kaizen(config={
    'default_model': 'gpt-3.5-turbo',
    'temperature': 0.5,
    'performance_tracking': True
})

# Agent with specific overrides
agent = kaizen.create_agent("specialized_processor", {
    "model": "gpt-4",  # Override default
    "temperature": 0.9,  # Override default
    "system_prompt": "You are a creative writing assistant",
    "max_tokens": 2000
})

# Verify configuration
print(f"Agent model: {agent.config.get('model')}")
print(f"Agent temperature: {agent.config.get('temperature')}")
```

**What this demonstrates**:
- Framework-level configuration management
- Agent-specific configuration overrides
- Configuration inheritance patterns

### 2. Framework Integration Patterns

#### Example 3: Manual Workflow Construction

**Status**: ✅ Working Implementation

```python
from kaizen import Kaizen
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

# Traditional Core SDK approach for comparison
workflow = WorkflowBuilder()
workflow.add_node("LLMAgentNode", "agent", {
    "model": "gpt-4",
    "prompt_template": "Process this text: {input}",
    "temperature": 0.7
})

# Kaizen agent approach (current implementation)
kaizen = Kaizen()
agent = kaizen.create_agent("processor", {
    "model": "gpt-4",
    "temperature": 0.7
})

# Both use the same runtime execution
runtime = LocalRuntime()

# Core SDK workflow
results1, run_id1 = runtime.execute(workflow.build())

# Kaizen agent workflow
results2, run_id2 = runtime.execute(agent.workflow.build())

print("✅ Both approaches work with the same runtime!")
```

**What this demonstrates**:
- Core SDK compatibility maintained
- Kaizen as enhancement layer, not replacement
- Consistent execution patterns

#### Example 4: Development Testing Pattern

**Status**: ✅ Working Implementation

```python
import pytest
from kaizen import Kaizen
from kailash.runtime.local import LocalRuntime

class TestKaizenAgent:
    def setup_method(self):
        """Setup for each test"""
        self.kaizen = Kaizen()
        self.runtime = LocalRuntime()

    def test_agent_creation(self):
        """Test basic agent creation"""
        agent = self.kaizen.create_agent("test_agent", {
            "model": "gpt-3.5-turbo"
        })
        assert agent is not None
        assert hasattr(agent, 'workflow')
        assert hasattr(agent, 'config')

    def test_workflow_execution(self):
        """Test agent workflow execution"""
        agent = self.kaizen.create_agent("test_agent", {
            "model": "gpt-3.5-turbo"
        })

        # Execute the workflow
        results, run_id = self.runtime.execute(agent.workflow.build())

        # Verify execution
        assert run_id is not None
        assert results is not None
        print(f"✅ Test execution successful: {run_id}")

# Run tests
if __name__ == "__main__":
    test_instance = TestKaizenAgent()
    test_instance.setup_method()
    test_instance.test_agent_creation()
    test_instance.test_workflow_execution()
```

**What this demonstrates**:
- Testing patterns for Kaizen agents
- Framework reliability validation
- Integration test approaches

### 3. Future API Examples

**Note**: These examples show the target API - not currently implemented.

#### Example 5: Signature-Based Programming (Target)

**Status**: 🟡 Not Implemented - Interface Designed

```python
from kaizen import Kaizen

kaizen = Kaizen(config={'signature_programming_enabled': True})

# Define AI workflow with function signature
@kaizen.signature("question -> answer")
def research_assistant(question: str) -> str:
    """Intelligent research assistant that provides comprehensive answers"""
    pass

@kaizen.signature("document, query -> summary")
def document_analyzer(document: str, query: str) -> Dict[str, str]:
    """Analyzes documents and provides structured summaries"""
    pass

# Usage becomes simple function calls
answer = research_assistant("What are the benefits of renewable energy?")
summary = document_analyzer(document_text, "Key financial insights")

print(f"Research result: {answer}")
print(f"Document analysis: {summary}")
```

**What this will demonstrate**:
- Declarative AI workflow definition
- Automatic optimization and compilation
- Simple function-call interface

#### Example 6: MCP First-Class Integration (Target)

**Status**: 🟡 Not Implemented - Architecture Designed

```python
from kaizen import Kaizen

# Capability-based auto-configuration
agent = kaizen.create_agent("research_assistant", {
    'mcp_capabilities': ['search', 'calculate', 'analyze'],
    'model': 'gpt-4'
})

# Or explicit MCP server management
agent.expose_as_mcp_server(
    port=8080,
    auth="api_key",
    tools=["research", "analyze"]
)

agent.connect_to_mcp_servers([
    "search-service",
    "http://external-api:8080"
])

# Auto-discovery of MCP tools
available_tools = kaizen.discover_mcp_tools(
    capabilities=["search", "calculate"],
    location="auto"
)
```

**What this will demonstrate**:
- Simplified MCP server configuration
- Automatic capability discovery
- First-class tool integration

#### Example 7: Multi-Agent Coordination (Target)

**Status**: 🟡 Not Implemented - Architecture Designed

```python
from kaizen import Kaizen

kaizen = Kaizen(config={'multi_agent_enabled': True})

# Create specialized agents
researcher = kaizen.create_specialized_agent(
    name="researcher",
    role="information_gathering",
    config={"model": "gpt-4", "tools": ["search", "analyze"]}
)

analyst = kaizen.create_specialized_agent(
    name="analyst",
    role="data_analysis",
    config={"model": "gpt-4", "tools": ["calculate", "visualize"]}
)

writer = kaizen.create_specialized_agent(
    name="writer",
    role="content_creation",
    config={"model": "gpt-4", "style": "professional"}
)

# Create coordination workflow
debate_team = kaizen.create_debate_workflow(
    agents=[researcher, analyst],
    topic="renewable energy investment",
    rounds=3
)

# Execute multi-agent collaboration
result = debate_team.execute()
final_report = writer.synthesize(result)
```

**What this will demonstrate**:
- Specialized agent creation
- Multi-agent coordination patterns
- Complex workflow orchestration

### 4. Performance and Monitoring Examples

#### Example 8: Performance Tracking (Current)

**Status**: ✅ Working Implementation

```python
import time
from kaizen import Kaizen

# Measure framework import performance
start_time = time.time()
kaizen = Kaizen()
import_time = (time.time() - start_time) * 1000

print(f"Framework import time: {import_time:.0f}ms")
print(f"Target: <100ms | Current: {'✅ GOOD' if import_time < 100 else '🟡 NEEDS OPTIMIZATION'}")

# Measure agent creation performance
start_time = time.time()
agent = kaizen.create_agent("perf_test", {"model": "gpt-3.5-turbo"})
creation_time = (time.time() - start_time) * 1000

print(f"Agent creation time: {creation_time:.0f}ms")
print(f"Target: <50ms | Current: {'✅ GOOD' if creation_time < 50 else '🟡 SLOW'}")
```

**What this demonstrates**:
- Performance baseline measurement
- Framework optimization opportunities
- Development performance tracking

#### Example 9: Error Handling Patterns

**Status**: ✅ Working Implementation

```python
from kaizen import Kaizen
from kaizen.core.exceptions import KaizenError, ConfigurationError

def robust_agent_creation():
    """Demonstrates proper error handling"""
    try:
        # Framework initialization with validation
        kaizen = Kaizen(config={
            'default_model': 'gpt-4',
            'temperature': 0.7
        })

        # Agent creation with error handling
        agent = kaizen.create_agent("robust_agent", {
            "model": "gpt-4",
            "temperature": 0.5,
            "max_tokens": 1000
        })

        print("✅ Agent created successfully")
        return agent

    except ConfigurationError as e:
        print(f"❌ Configuration error: {e}")
        return None

    except KaizenError as e:
        print(f"❌ Kaizen framework error: {e}")
        return None

    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return None

# Usage with proper error handling
agent = robust_agent_creation()
if agent:
    print(f"Ready to execute workflows with agent: {agent.name}")
```

**What this demonstrates**:
- Comprehensive error handling
- Framework reliability patterns
- Production-ready error management

## Running the Examples

### Setup Environment

```bash
# Install Kaizen with development dependencies
pip install -e .[dev]

# Verify installation
python -c "from kaizen import Kaizen; print('✅ Kaizen available')"
```

### Execute Examples

```bash
# Run basic examples
cd examples/
python basic_agent_example.py
python configuration_example.py
python testing_example.py

# Run performance tests
python performance_tracking.py

# Run error handling demo
python error_handling_example.py
```

### Testing Examples

```bash
# Run example validation tests
pytest examples/test_examples.py -v

# Run full framework tests
pytest tests/ -v
```

## Example Status Summary

| Example | Status | Description | Implementation |
|---------|--------|-------------|----------------|
| Basic Agent | ✅ Working | Simple agent creation and execution | Complete |
| Configuration | ✅ Working | Framework and agent configuration | Complete |
| Core SDK Integration | ✅ Working | Workflow compatibility demonstration | Complete |
| Testing Patterns | ✅ Working | Development testing approaches | Complete |
| Performance Tracking | ✅ Working | Performance measurement and baselines | Complete |
| Error Handling | ✅ Working | Robust error management patterns | Complete |
| Signature Programming | 🟡 Planned | Declarative workflow definition | Interface designed |
| MCP Integration | 🟡 Planned | First-class MCP support | Architecture ready |
| Multi-Agent | 🟡 Planned | Agent coordination patterns | Requirements defined |

## Next Steps

### Immediate Next Steps
1. **Try Working Examples**: Run the ✅ working examples above
2. **Explore Framework**: See [Complete Examples](../../examples/README.md) directory
3. **Understand Architecture**: Review [Core Concepts](concepts.md) for deeper understanding

### Development Path
1. **Implementation Status**: Check [Gap Analysis](../../tracking/KAIZEN_GAPS_ANALYSIS.md) for current limitations
2. **Integration Patterns**: Study [Integration Strategy](../KAIZEN_INTEGRATION_STRATEGY.md)
3. **Advanced Features**: Explore [Development Roadmap](../KAIZEN_IMPLEMENTATION_ROADMAP.md)

### Production Readiness
1. **Testing Strategy**: Review [Testing Guide](../development/testing.md)
2. **Enterprise Features**: Study [Enterprise Documentation](../enterprise/)
3. **Performance Optimization**: See [Optimization Guide](../advanced/optimization.md)

---

**🎯 Examples Mastered**: You now understand Kaizen's current capabilities and future direction. Ready for [development guides](../development/) or [advanced topics](../advanced/)!
