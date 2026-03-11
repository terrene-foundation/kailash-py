# Orchestration Runtime Patterns

Production-ready patterns demonstrating multi-agent orchestration with the OrchestrationRuntime system.

## Overview

OrchestrationRuntime provides enterprise-grade multi-agent orchestration with:
- Automatic agent registration and lifecycle management
- Multiple routing strategies (semantic, round-robin, random)
- Budget tracking and enforcement
- Health monitoring and failure recovery
- Google A2A protocol for capability-based routing

## Patterns

### 1. Basic Multi-Agent Task Distribution

**File**: `1_basic_orchestration.py`

Demonstrates fundamental orchestration patterns with simple workload balancing.

**Features**:
- Agent registration and deregistration
- Round-robin task distribution
- Concurrent task routing
- Basic lifecycle management

**Use Case**: Simple workload balancing across a pool of agents

**Cost**: $0 (uses Ollama llama3.2:1b)

```bash
python 1_basic_orchestration.py
```

**Expected Output**:
```
Registering agents...
✓ Registered 3 agents
  - CodeAgent
  - DataAgent
  - WritingAgent

Routing tasks with round-robin strategy...

Routing Results:
1. 'Generate hello world program' → CodeAgent
2. 'Analyze sales data' → DataAgent
3. 'Write blog post introduction' → WritingAgent
4. 'Create sorting algorithm' → CodeAgent
5. 'Calculate statistics' → DataAgent
6. 'Edit article for clarity' → WritingAgent

Distribution Summary:
  CodeAgent: 2 tasks
  DataAgent: 2 tasks
  WritingAgent: 2 tasks
```

---

### 2. Semantic Routing with A2A Capability Matching

**File**: `2_semantic_routing.py`

Demonstrates intelligent task routing based on agent capabilities using the Google A2A protocol.

**Features**:
- A2A capability card generation
- Semantic capability matching
- Best-fit agent selection
- Concurrent semantic routing

**Use Case**: Intelligent task routing where agents have specialized skills

**Cost**: $0 (uses Ollama llama3.2:1b)

```bash
python 2_semantic_routing.py
```

**Expected Output**:
```
Registering specialized agents...
✓ Registered 4 agents:
  - PythonExpert: Python code generation and debugging
  - JavaScriptExpert: JavaScript and frontend development
  - DataScientist: Data analysis and machine learning
  - TechnicalWriter: Technical documentation and API docs

======================================================================
Routing tasks with SEMANTIC strategy (A2A capability matching)
======================================================================

Task: 'Write a Python function to sort a list'
  Expected type: Python task
  Selected agent: PythonExpert
  Agent capability: Python code generation and debugging

Task: 'Create React component for user profile'
  Expected type: JavaScript task
  Selected agent: JavaScriptExpert
  Agent capability: JavaScript and frontend development

Task: 'Analyze sales data and create visualization'
  Expected type: Data science task
  Selected agent: DataScientist
  Agent capability: Data analysis and machine learning

Task: 'Write API documentation for REST endpoint'
  Expected type: Technical writing task
  Selected agent: TechnicalWriter
  Agent capability: Technical documentation and API docs
```

**How Semantic Routing Works**:
1. Each agent has an A2A capability card with name, capability, and description
2. When routing a task, runtime compares task description against all agent capabilities
3. Best-matching agent is automatically selected via semantic similarity
4. No hardcoded routing logic needed - fully automatic

---

### 3. Budget-Controlled Orchestration

**File**: `3_budget_controlled.py`

Demonstrates cost tracking and budget enforcement for production environments.

**Features**:
- Per-agent budget limits
- Runtime budget tracking
- Budget exhaustion handling
- Cost monitoring dashboard

**Use Case**: Cost-controlled production environments with spending limits

**Cost**: ~$0.01 (uses OpenAI gpt-5-nano-2025-08-07)

**Requirements**: `OPENAI_API_KEY` in `.env` file

```bash
python 3_budget_controlled.py
```

**Expected Output**:
```
Registering agents with budget limits...
✓ Registered 2 agents:
  - CheapAgent: $0.05 budget limit
  - PremiumAgent: $0.20 budget limit

Initial Budget State:
  Total runtime budget: $0.000000
  CheapAgent: $0.000000 / $0.05
  PremiumAgent: $0.000000 / $0.20

======================================================================
Budget State After Routing:
======================================================================
  Total runtime budget: $0.000000

  CheapAgent:
    Spent: $0.000000 / $0.05
    Remaining: $0.050000 (100.0%)
    Status: active
    Tasks completed: 0

  PremiumAgent:
    Spent: $0.000000 / $0.20
    Remaining: $0.200000 (100.0%)
    Status: active
    Tasks completed: 0
```

**Note**: Budget is tracked during agent execution, not routing. The pattern demonstrates the monitoring infrastructure.

---

### 4. Health Monitoring and Failure Recovery

**File**: `4_health_monitoring.py`

Demonstrates resilient orchestration with health checks and automatic recovery.

**Features**:
- Real LLM-based health checks
- Agent status monitoring (ACTIVE, UNHEALTHY, DEGRADED)
- Error counting and failure detection
- Automatic health check intervals
- Agent replacement and recovery

**Use Case**: Production orchestration requiring high reliability

**Cost**: ~$0.01 (uses OpenAI gpt-5-nano-2025-08-07)

**Requirements**: `OPENAI_API_KEY` in `.env` file

```bash
python 4_health_monitoring.py
```

**Expected Output**:
```
======================================================================
Registering Agents with Health Monitoring
======================================================================

✓ Registered 2 agents:
  - StableAgent
  - MonitoredAgent

Health check interval: 5.0s

======================================================================
Performing Health Checks (Real LLM Inference)
======================================================================
Note: Health checks use actual LLM inference to verify agent health

Checking StableAgent...
  Health check: ✓ PASSED
  Status: active
  Error count: 0
  ✓ Agent remains ACTIVE

Checking MonitoredAgent...
  Health check: ✓ PASSED
  Status: active
  Error count: 0
  ✓ Agent remains ACTIVE

======================================================================
Health Monitoring Dashboard:
======================================================================

StableAgent:
  Status: active
  Health: ✓ Healthy
  Error count: 0
  Task metrics:
    - Completed: 0
    - Failed: 0
    - Active: 0
    - Success rate: 0.0%
  Budget:
    - Spent: $0.000000 / $0.00
  Last health check: 2025-01-06 12:00:00
```

**Health Check Process**:
1. Runtime automatically performs health checks at configured intervals
2. Each check executes the agent with a test task using real LLM inference
3. Failed checks increment error count and may mark agent UNHEALTHY
4. Unhealthy agents are automatically excluded from task routing
5. Agents can be deregistered and replaced without downtime

---

## Running the Examples

### Prerequisites

1. **Install dependencies**:
   ```bash
   pip install kailash-kaizen
   ```

2. **Set up environment**:
   - Copy `.env.example` to `.env`
   - Add `OPENAI_API_KEY` for patterns 3 and 4

3. **Install Ollama** (for patterns 1 and 2):
   ```bash
   # macOS
   brew install ollama

   # Pull required model
   ollama pull llama3.2:1b
   ```

### Running Patterns

```bash
# Pattern 1: Basic orchestration (free)
python 1_basic_orchestration.py

# Pattern 2: Semantic routing (free)
python 2_semantic_routing.py

# Pattern 3: Budget control (~$0.01)
python 3_budget_controlled.py

# Pattern 4: Health monitoring (~$0.01)
python 4_health_monitoring.py
```

---

## Key Concepts

### OrchestrationRuntime

Central orchestration system managing multiple agents:

```python
from kaizen.orchestration import (
    OrchestrationRuntime,
    OrchestrationRuntimeConfig,
    RoutingStrategy,
)

# Configure runtime
config = OrchestrationRuntimeConfig(
    max_concurrent_agents=5,
    enable_health_monitoring=True,
    health_check_interval=10.0,  # seconds
    enable_budget_enforcement=True,
)

# Create runtime
runtime = OrchestrationRuntime(config=config)
await runtime.start()

# Register agents
agent_id = await runtime.register_agent(my_agent)

# Route tasks
selected_agent = await runtime.route_task(
    "Analyze data",
    strategy=RoutingStrategy.SEMANTIC
)

# Shutdown
await runtime.shutdown()
```

### Routing Strategies

**1. SEMANTIC** (A2A Protocol):
- Automatic capability matching
- Best-fit agent selection
- No hardcoded logic needed

**2. ROUND_ROBIN**:
- Even distribution across agents
- Simple load balancing
- Predictable allocation

**3. RANDOM**:
- Random agent selection
- Uniform distribution
- Chaos testing

### Agent Status

- **ACTIVE**: Agent is healthy and available
- **UNHEALTHY**: Agent has failed health checks
- **DEGRADED**: Agent is experiencing issues
- **OFFLINE**: Agent is not responding

### Budget Tracking

Per-agent and runtime-wide budget monitoring:

```python
# Set agent budget limit
runtime.agents[agent_id].budget_limit_usd = 0.10  # $0.10

# Track runtime budget
total_spent = runtime._total_budget_spent

# Check agent budget
agent_spent = runtime.agents[agent_id].budget_spent_usd
```

---

## Production Deployment

### Best Practices

1. **Use SEMANTIC routing** for specialized agent pools
2. **Set budget limits** for cost control
3. **Enable health monitoring** for reliability
4. **Configure health check intervals** based on workload
5. **Monitor agent metrics** for performance optimization

### Scaling Considerations

- **10-50 agents**: Single runtime instance
- **50-100 agents**: Multiple runtime instances with load balancing
- **100+ agents**: Distributed orchestration with Agent Registry

### Monitoring

Track these metrics:
- Agent status distribution (active/unhealthy/degraded)
- Task completion rates
- Budget spend per agent
- Error rates and recovery time
- Health check success rates

---

## Next Steps

1. **Explore Agent Registry** (TODO-179): Centralized agent lifecycle management
2. **Review test suites**:
   - Unit tests: `tests/unit/orchestration/`
   - Integration tests: `tests/integration/orchestration/`
   - E2E tests: `tests/e2e/orchestration/`

3. **Check documentation**:
   - OrchestrationRuntime architecture
   - A2A protocol integration
   - Budget enforcement design

---

## Support

For issues or questions:
- GitHub Issues: [kailash-kaizen/issues](https://github.com/kailash/kailash-kaizen/issues)
- Documentation: `docs/features/orchestration-runtime.md`
- Test examples: `tests/e2e/orchestration/`
