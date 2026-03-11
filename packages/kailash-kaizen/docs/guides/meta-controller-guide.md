# Meta-Controller System User Guide

**Version**: 1.0.0
**Module**: `kaizen.orchestration`
**Purpose**: Intelligent agent routing and multi-agent coordination

## Table of Contents

1. [Introduction](#introduction)
2. [When to Use Meta-Controller](#when-to-use-meta-controller)
3. [Core Concepts](#core-concepts)
4. [Basic Usage](#basic-usage)
5. [Routing Strategies](#routing-strategies)
6. [Error Handling](#error-handling)
7. [Production Patterns](#production-patterns)
8. [Pipeline Composition](#pipeline-composition)
9. [Testing Meta-Controllers](#testing-meta-controllers)
10. [Troubleshooting](#troubleshooting)

---

## Introduction

The **Meta-Controller** is an intelligent routing system that automatically selects the best agent to handle a given task. Instead of hardcoding if/else logic to route tasks, the meta-controller uses semantic matching via the Google A2A (Agent-to-Agent) protocol to find the most capable agent for each request.

### What is a Meta-Controller?

A meta-controller is a coordination pattern where:
1. **User submits a task** to the meta-controller
2. **Meta-controller analyzes task requirements** using A2A capability matching
3. **Best agent is selected** based on capability scores
4. **Selected agent executes** the task
5. **Result is returned** to the user

### Why Use Meta-Controller?

**Without Meta-Controller** (Manual Routing):
```python
# ❌ Hardcoded routing logic - brittle and hard to maintain
if "code" in task or "python" in task or "function" in task:
    result = code_agent.run(task=task)
elif "data" in task or "analyze" in task or "visualization" in task:
    result = data_agent.run(task=task)
elif "write" in task or "documentation" in task:
    result = writing_agent.run(task=task)
else:
    result = general_agent.run(task=task)
```

**With Meta-Controller** (Semantic Routing):
```python
# ✅ Automatic semantic routing - robust and maintainable
router = Pipeline.router(
    agents=[code_agent, data_agent, writing_agent, general_agent],
    routing_strategy="semantic"
)
result = router.run(task=task, input=data)
# Automatically selects best agent based on A2A capability matching!
```

### Key Benefits

1. **No Hardcoded Logic**: Routing decisions based on semantic understanding, not keyword matching
2. **Automatic Capability Discovery**: Agents advertise their capabilities via A2A cards
3. **Dynamic Agent Selection**: Add/remove agents without changing routing code
4. **Graceful Error Handling**: Continue execution even when agents fail
5. **Composable Pipelines**: Convert routers to agents for nested coordination
6. **Production Ready**: 100% test coverage with real multi-agent workflows

---

## When to Use Meta-Controller

### Decision Matrix

| Use Meta-Controller When | Use Direct Agent When |
|--------------------------|----------------------|
| Multiple specialist agents available | Single agent handles all tasks |
| Task requirements vary significantly | Task requirements are uniform |
| Need dynamic agent selection | Agent selection is predetermined |
| Want semantic capability matching | Simple round-robin sufficient |
| Building multi-agent system | Building single-agent system |
| Need graceful error handling | Fail-fast behavior acceptable |

### Use Case Examples

**✅ Good Use Cases for Meta-Controller**:

1. **Multi-Specialist Systems**
   - Routing to coding, data, writing, DevOps, security specialists
   - Each specialist has distinct capabilities
   - Task requirements determine best-fit agent

2. **Dynamic Agent Pools**
   - Agents can be added/removed at runtime
   - Capability-based selection without code changes
   - A/B testing different agent configurations

3. **Load Balancing**
   - Distribute tasks across multiple identical agents
   - Round-robin or random routing strategies
   - Horizontal scaling for high-throughput systems

4. **Fault Tolerance**
   - Graceful error handling with fallback agents
   - Continue processing despite individual agent failures
   - Retry logic with different agents

**❌ Avoid Meta-Controller When**:

1. **Single Agent Sufficient**
   - One agent handles all task types effectively
   - No need for specialization or routing

2. **Predetermined Routing**
   - Agent selection known at compile time
   - No need for dynamic routing logic

3. **Ultra-Low Latency Required**
   - Routing overhead (A2A matching) not acceptable
   - Direct agent calls more appropriate

---

## Core Concepts

### 1. Google A2A Protocol

The **Agent-to-Agent (A2A) Protocol** is Google's standard for agent capability discovery and coordination.

**Key Components**:

- **Capability Cards**: Agents advertise their capabilities
- **Semantic Matching**: Match task requirements to agent capabilities
- **Capability Scores**: Quantify how well an agent matches a task (0.0 to 1.0)

**Example A2A Card**:
```python
{
    "agent_id": "data_specialist",
    "description": "Expert in data analysis, visualization, and statistical insights",
    "primary_capabilities": [
        {
            "capability": "Data analysis and insights",
            "examples": [
                "Analyze sales trends",
                "Identify patterns in user behavior",
                "Perform statistical analysis"
            ]
        },
        {
            "capability": "Data visualization",
            "examples": [
                "Create charts and dashboards",
                "Generate visualizations",
                "Build interactive plots"
            ]
        }
    ]
}
```

**Capability Matching**:
```python
# Task: "Analyze sales data and create visualization"
# A2A matching scores:
#   - data_specialist: 0.92 (exact match - data analysis + visualization)
#   - code_specialist: 0.35 (partial match - could write analysis code)
#   - writing_specialist: 0.15 (weak match - could document results)
#
# Result: data_specialist selected
```

### 2. Routing Strategies

Three routing strategies available:

1. **Semantic Routing** (Default)
   - Uses A2A capability matching
   - Selects best-fit agent for each task
   - Recommended for production

2. **Round-Robin**
   - Rotates through agents sequentially
   - Use for load balancing identical agents
   - Predictable distribution pattern

3. **Random**
   - Randomly selects agent from pool
   - Use for A/B testing or unpredictable distribution
   - No state maintained between requests

### 3. Error Handling Modes

Two error handling modes available:

1. **Graceful Mode** (Default)
   - Continue execution on agent failure
   - Return error info in result dict
   - Suitable for production systems

2. **Fail-Fast Mode**
   - Stop immediately on first error
   - Raise exception to caller
   - Suitable for critical workflows

---

## Basic Usage

### Creating a Meta-Controller

**Step 1**: Import required modules
```python
from kaizen.core.base_agent import BaseAgent, BaseAgentConfig
from kaizen.orchestration.pipeline import Pipeline
from kaizen.signatures import Signature, InputField, OutputField
```

**Step 2**: Define signatures for specialist agents
```python
class CodingSignature(Signature):
    """Signature for coding tasks."""
    task: str = InputField(description="Coding task to perform")
    code: str = OutputField(description="Generated code")

class DataSignature(Signature):
    """Signature for data analysis tasks."""
    task: str = InputField(description="Data analysis task")
    analysis: str = OutputField(description="Analysis results")

class WritingSignature(Signature):
    """Signature for writing tasks."""
    task: str = InputField(description="Writing task")
    content: str = OutputField(description="Written content")
```

**Step 3**: Create specialist agents
```python
# Configure agents
config = BaseAgentConfig(
    llm_provider="openai",
    model="gpt-4"
)

# Create specialists with clear descriptions
code_specialist = BaseAgent(
    config=config,
    signature=CodingSignature(),
    agent_id="code_specialist",
    description="Expert in Python programming, algorithms, and code generation"
)

data_specialist = BaseAgent(
    config=config,
    signature=DataSignature(),
    agent_id="data_specialist",
    description="Expert in data analysis, visualization, and statistical insights"
)

writing_specialist = BaseAgent(
    config=config,
    signature=WritingSignature(),
    agent_id="writing_specialist",
    description="Expert in technical writing, documentation, and content creation"
)
```

**Step 4**: Create meta-controller
```python
# Create router with semantic routing (recommended)
router = Pipeline.router(
    agents=[code_specialist, data_specialist, writing_specialist],
    routing_strategy="semantic",
    error_handling="graceful"
)
```

**Step 5**: Execute tasks
```python
# Coding task - routes to code_specialist
coding_result = router.run(
    task="Write a Python function to calculate fibonacci numbers",
    input="generate_fibonacci"
)
print(f"Routed to: {coding_result.get('agent_id')}")
print(f"Code: {coding_result.get('code')}")

# Data task - routes to data_specialist
data_result = router.run(
    task="Analyze sales trends and identify seasonal patterns",
    input="sales_data.csv"
)
print(f"Routed to: {data_result.get('agent_id')}")
print(f"Analysis: {data_result.get('analysis')}")

# Writing task - routes to writing_specialist
writing_result = router.run(
    task="Write technical documentation for API endpoints",
    input="api_spec.yaml"
)
print(f"Routed to: {writing_result.get('agent_id')}")
print(f"Content: {writing_result.get('content')}")
```

**Output**:
```
Routed to: code_specialist
Code: def fibonacci(n):
    if n <= 1:
        return n
    return fibonacci(n-1) + fibonacci(n-2)

Routed to: data_specialist
Analysis: Sales show strong Q4 seasonal pattern with 35% increase...

Routed to: writing_specialist
Content: # API Documentation

## Endpoints

### GET /users
Returns list of users...
```

---

## Routing Strategies

### 1. Semantic Routing (Recommended)

**Purpose**: Select best agent based on A2A capability matching

**When to Use**:
- Multiple specialist agents with distinct capabilities
- Task requirements vary significantly
- Want automatic best-fit selection
- Production systems requiring intelligent routing

**How It Works**:
1. Extract task description from inputs
2. Generate A2A capability cards for all agents
3. Calculate capability match scores
4. Select agent with highest score (> 0)
5. Fallback to first agent if no matches

**Configuration**:
```python
router = Pipeline.router(
    agents=[code_agent, data_agent, writing_agent],
    routing_strategy="semantic"  # Default
)
```

**Example**:
```python
from kaizen.orchestration.pipeline import Pipeline

# Create router with semantic routing
router = Pipeline.router(
    agents=[
        code_specialist,    # "Expert in Python programming and algorithms"
        data_specialist,    # "Expert in data analysis and visualization"
        writing_specialist  # "Expert in technical writing and documentation"
    ],
    routing_strategy="semantic"
)

# Test semantic routing with various tasks
tasks = [
    ("Implement binary search algorithm", "code_specialist"),
    ("Analyze user engagement metrics", "data_specialist"),
    ("Write API reference documentation", "writing_specialist"),
    ("Debug Python function", "code_specialist"),
    ("Create sales dashboard", "data_specialist"),
]

for task, expected_agent in tasks:
    result = router.run(task=task, input="test")
    actual_agent = result.get("agent_id", "unknown")

    match = "✓" if actual_agent == expected_agent else "✗"
    print(f"{match} Task: {task[:40]:<40} → {actual_agent}")
```

**Output**:
```
✓ Task: Implement binary search algorithm         → code_specialist
✓ Task: Analyze user engagement metrics           → data_specialist
✓ Task: Write API reference documentation         → writing_specialist
✓ Task: Debug Python function                     → code_specialist
✓ Task: Create sales dashboard                    → data_specialist
```

**Capability Matching Details**:
```python
# Behind the scenes (simplified):
best_score = 0.0
best_agent = None

for agent in agents:
    # Generate A2A card with capabilities
    card = agent.to_a2a_card()

    # Calculate match score for each capability
    for capability in card.primary_capabilities:
        score = capability.matches_requirement(task)

        if score > best_score:
            best_score = score
            best_agent = agent

# Select best match or fallback
if best_agent and best_score > 0:
    return best_agent
else:
    return agents[0]  # Fallback to first agent
```

---

### 2. Round-Robin Routing

**Purpose**: Distribute load evenly across all agents

**When to Use**:
- All agents have equal capability
- Need predictable load distribution
- Load balancing for horizontal scaling
- Testing multiple agents with same workload

**How It Works**:
1. Maintain current index (starts at 0)
2. Select agent at current index
3. Increment index (wrap around after last agent)
4. Repeat for each request

**Configuration**:
```python
router = Pipeline.router(
    agents=[agent1, agent2, agent3],
    routing_strategy="round-robin"
)
```

**Example**:
```python
from kaizen.orchestration.pipeline import Pipeline

# Create 3 identical agents
agents = [
    BaseAgent(config, QASignature(), f"qa_agent_{i}", "Question answering expert")
    for i in range(3)
]

# Create round-robin router
router = Pipeline.router(
    agents=agents,
    routing_strategy="round-robin"
)

# Execute 9 requests - distributed evenly
for i in range(9):
    result = router.run(
        task=f"Question {i+1}",
        input=f"data_{i+1}"
    )

    agent_id = result.get("agent_id")
    print(f"Request {i+1}: {agent_id}")
```

**Output**:
```
Request 1: qa_agent_0
Request 2: qa_agent_1
Request 3: qa_agent_2
Request 4: qa_agent_0  (wrapped around)
Request 5: qa_agent_1
Request 6: qa_agent_2
Request 7: qa_agent_0
Request 8: qa_agent_1
Request 9: qa_agent_2
```

**Use Case - Load Balancing**:
```python
# Horizontal scaling for high-throughput systems
high_capacity_agents = [
    create_qa_agent(agent_id=f"qa_{i}")
    for i in range(10)  # 10 identical agents
]

router = Pipeline.router(
    agents=high_capacity_agents,
    routing_strategy="round-robin"
)

# Process 1000 requests - distributed evenly (100 requests per agent)
results = []
for i in range(1000):
    result = router.run(task=f"Request {i}", input=f"data_{i}")
    results.append(result)
```

---

### 3. Random Routing

**Purpose**: Random agent selection for unpredictable distribution

**When to Use**:
- A/B testing with multiple agent configurations
- Simulating non-deterministic systems
- Quick prototyping without capability matching
- Need unpredictable distribution pattern

**How It Works**:
1. Randomly select agent from pool
2. Execute selected agent
3. Return result
4. No state maintained between requests

**Configuration**:
```python
router = Pipeline.router(
    agents=[agent_a, agent_b, agent_c],
    routing_strategy="random"
)
```

**Example - A/B Testing**:
```python
from kaizen.orchestration.pipeline import Pipeline
from collections import Counter

# Create 3 agents with different configurations
agent_a = BaseAgent(config_a, signature, "agent_a", "Configuration A")
agent_b = BaseAgent(config_b, signature, "agent_b", "Configuration B")
agent_c = BaseAgent(config_c, signature, "agent_c", "Configuration C")

# Create random router
router = Pipeline.router(
    agents=[agent_a, agent_b, agent_c],
    routing_strategy="random"
)

# Execute 300 requests to test distribution
agent_selections = []
for i in range(300):
    result = router.run(task="Test task", input=f"data_{i}")
    agent_selections.append(result.get("agent_id"))

# Analyze distribution
distribution = Counter(agent_selections)
print("Agent selection distribution:")
for agent_id, count in distribution.items():
    percentage = (count / 300) * 100
    print(f"  {agent_id}: {count} requests ({percentage:.1f}%)")
```

**Output** (approximate):
```
Agent selection distribution:
  agent_a: 98 requests (32.7%)
  agent_b: 104 requests (34.7%)
  agent_c: 98 requests (32.7%)
```

---

## Error Handling

### Graceful Mode (Default)

**Purpose**: Continue execution even when agents fail

**Behavior**:
- Agent execution failures are caught
- Error information returned in result dict
- Pipeline continues processing subsequent requests
- Suitable for production systems where partial failure is acceptable

**Error Result Format**:
```python
{
    "error": "Exception message",
    "agent_id": "failed_agent_id",
    "status": "failed",
    "traceback": "Full traceback string"
}
```

**Configuration**:
```python
router = Pipeline.router(
    agents=[agent1, agent2, agent3],
    routing_strategy="semantic",
    error_handling="graceful"  # Default
)
```

**Example**:
```python
from kaizen.orchestration.pipeline import Pipeline

# Create router with graceful error handling
router = Pipeline.router(
    agents=[reliable_agent, flaky_agent, stable_agent],
    routing_strategy="round-robin",
    error_handling="graceful"
)

# Process batch of requests
requests = [
    {"task": "Task 1", "input": "good_data"},
    {"task": "Task 2", "input": "bad_data"},    # Will fail
    {"task": "Task 3", "input": "good_data"},
    {"task": "Task 4", "input": "invalid"},      # Will fail
    {"task": "Task 5", "input": "good_data"},
]

# Process all requests - gracefully handle errors
results = []
for req in requests:
    result = router.run(**req)

    if result.get("status") == "failed":
        print(f"❌ {req['task']} failed: {result['error']}")
        results.append(None)
    else:
        print(f"✓ {req['task']} succeeded")
        results.append(result)

# Continue processing successful results
successful_results = [r for r in results if r is not None]
print(f"\n✓ Processed {len(successful_results)}/{len(requests)} successfully")
```

**Output**:
```
✓ Task 1 succeeded
❌ Task 2 failed: Invalid input format
✓ Task 3 succeeded
❌ Task 4 failed: Data validation error
✓ Task 5 succeeded

✓ Processed 3/5 successfully
```

**Production Pattern - Retry on Error**:
```python
def execute_with_retry(router, task, input_data, max_retries=3):
    """Execute with retry on graceful errors."""
    for attempt in range(max_retries):
        result = router.run(task=task, input=input_data)

        # Check if execution succeeded
        if result.get("status") != "failed":
            return result

        # Log retry
        print(f"Attempt {attempt + 1} failed: {result['error']}")
        print(f"Retrying in {2 ** attempt}s...")
        time.sleep(2 ** attempt)  # Exponential backoff

    # All retries exhausted
    raise Exception(f"Failed after {max_retries} attempts")

# Usage
result = execute_with_retry(
    router=my_router,
    task="Critical task",
    input_data="important_data",
    max_retries=3
)
```

---

### Fail-Fast Mode

**Purpose**: Stop immediately on first error

**Behavior**:
- Agent execution failures raise exceptions
- Pipeline execution halts
- Error propagates to caller
- Suitable for critical workflows where partial failure is unacceptable

**Configuration**:
```python
router = Pipeline.router(
    agents=[agent1, agent2],
    routing_strategy="semantic",
    error_handling="fail-fast"
)
```

**Example**:
```python
from kaizen.orchestration.pipeline import Pipeline

# Create router with fail-fast error handling
router = Pipeline.router(
    agents=[critical_agent_1, critical_agent_2],
    routing_strategy="semantic",
    error_handling="fail-fast"
)

# Execute critical workflow
try:
    result = router.run(
        task="Critical financial transaction",
        input={"amount": 1000000, "account": "12345"}
    )

    # Process result only if no errors
    print(f"✓ Transaction succeeded: {result}")

except Exception as e:
    print(f"❌ Critical failure: {e}")

    # Handle failure immediately
    # - Rollback transaction
    # - Alert operations team
    # - Log to audit trail
    rollback_transaction()
    alert_ops_team(error=str(e))
    log_audit_trail(event="transaction_failed", error=str(e))
```

**Output** (on error):
```
❌ Critical failure: Agent execution failed: Invalid account number
```

**Production Pattern - Transaction Workflow**:
```python
def execute_transaction_workflow(router, transaction_data):
    """Execute transaction with fail-fast behavior."""
    try:
        # Step 1: Validate transaction
        validation_result = router.run(
            task="Validate transaction",
            input=transaction_data
        )

        # Step 2: Process transaction
        processing_result = router.run(
            task="Process transaction",
            input=validation_result
        )

        # Step 3: Record transaction
        recording_result = router.run(
            task="Record transaction",
            input=processing_result
        )

        return recording_result

    except Exception as e:
        # Any failure rolls back entire transaction
        print(f"Transaction failed at step: {e}")
        rollback_transaction(transaction_data)
        raise

# Usage
try:
    result = execute_transaction_workflow(
        router=financial_router,
        transaction_data=transaction
    )
    print("✓ Transaction completed successfully")
except Exception as e:
    print(f"❌ Transaction failed: {e}")
```

---

## Production Patterns

### Pattern 1: Multi-Specialist Support System

**Scenario**: Customer support system with coding, data, and writing specialists

**Implementation**:
```python
from kaizen.core.base_agent import BaseAgent, BaseAgentConfig
from kaizen.orchestration.pipeline import Pipeline
from kaizen.signatures import Signature, InputField, OutputField

# Define signatures
class TechnicalSupportSignature(Signature):
    ticket: str = InputField(description="Support ticket description")
    response: str = OutputField(description="Support response")
    resolution: str = OutputField(description="Resolution steps")

# Create specialist agents
config = BaseAgentConfig(
    llm_provider="openai",
    model="gpt-4",
    temperature=0.7
)

coding_specialist = BaseAgent(
    config=config,
    signature=TechnicalSupportSignature(),
    agent_id="coding_specialist",
    description="Expert in debugging code, API issues, and technical troubleshooting"
)

data_specialist = BaseAgent(
    config=config,
    signature=TechnicalSupportSignature(),
    agent_id="data_specialist",
    description="Expert in database issues, data pipeline problems, and ETL debugging"
)

writing_specialist = BaseAgent(
    config=config,
    signature=TechnicalSupportSignature(),
    agent_id="writing_specialist",
    description="Expert in documentation questions, how-to guides, and product explanations"
)

general_specialist = BaseAgent(
    config=config,
    signature=TechnicalSupportSignature(),
    agent_id="general_specialist",
    description="General support for billing, account issues, and other questions"
)

# Create meta-controller
support_router = Pipeline.router(
    agents=[
        coding_specialist,
        data_specialist,
        writing_specialist,
        general_specialist
    ],
    routing_strategy="semantic",
    error_handling="graceful"
)

# Handle support tickets
tickets = [
    "My API request returns 401 error",
    "How do I export data from the dashboard?",
    "Where is the authentication documentation?",
    "I can't access my billing information",
]

for ticket in tickets:
    result = support_router.run(
        ticket=ticket,
        input=ticket
    )

    print(f"\nTicket: {ticket}")
    print(f"Routed to: {result.get('agent_id')}")
    print(f"Response: {result.get('response')[:100]}...")
    print(f"Resolution: {result.get('resolution')[:100]}...")
```

**Output**:
```
Ticket: My API request returns 401 error
Routed to: coding_specialist
Response: This is an authentication error. The 401 status code indicates that your API key is either...
Resolution: 1. Check your API key in .env file\n2. Verify API key is active in dashboard\n3. Ensure...

Ticket: How do I export data from the dashboard?
Routed to: data_specialist
Response: You can export data using the Export button in the top-right corner of the dashboard...
Resolution: 1. Navigate to Dashboard\n2. Click Export button\n3. Select format (CSV, JSON, Excel)...

Ticket: Where is the authentication documentation?
Routed to: writing_specialist
Response: The authentication documentation is located in the API Reference section under Security...
Resolution: 1. Visit docs.example.com/api-reference\n2. Navigate to Security section\n3. Review...

Ticket: I can't access my billing information
Routed to: general_specialist
Response: Billing information is accessible from your account settings. If you're unable to access...
Resolution: 1. Go to Account Settings\n2. Click Billing tab\n3. If still unable, contact support...
```

---

### Pattern 2: DevOps Pipeline Orchestration

**Scenario**: DevOps pipeline with deployment, monitoring, and incident response specialists

**Implementation**:
```python
from kaizen.orchestration.pipeline import Pipeline

# Define DevOps specialist signatures
class DeploymentSignature(Signature):
    task: str = InputField(description="Deployment task")
    deployment_plan: str = OutputField(description="Deployment plan")
    commands: list = OutputField(description="Shell commands to execute")

class MonitoringSignature(Signature):
    task: str = InputField(description="Monitoring task")
    metrics: dict = OutputField(description="Metric queries")
    alerts: list = OutputField(description="Alert configurations")

class IncidentSignature(Signature):
    task: str = InputField(description="Incident response task")
    diagnosis: str = OutputField(description="Problem diagnosis")
    remediation: str = OutputField(description="Remediation steps")

# Create DevOps specialists
deployment_agent = BaseAgent(
    config=config,
    signature=DeploymentSignature(),
    agent_id="deployment_agent",
    description="Expert in Kubernetes deployments, CI/CD pipelines, and infrastructure provisioning"
)

monitoring_agent = BaseAgent(
    config=config,
    signature=MonitoringSignature(),
    agent_id="monitoring_agent",
    description="Expert in Prometheus metrics, Grafana dashboards, and alert configuration"
)

incident_agent = BaseAgent(
    config=config,
    signature=IncidentSignature(),
    agent_id="incident_agent",
    description="Expert in incident response, system diagnostics, and troubleshooting"
)

# Create DevOps router
devops_router = Pipeline.router(
    agents=[deployment_agent, monitoring_agent, incident_agent],
    routing_strategy="semantic"
)

# Execute DevOps tasks
devops_tasks = [
    "Deploy new API version to production",
    "Create dashboard for application latency",
    "Investigate high memory usage on prod servers",
    "Set up blue-green deployment pipeline",
    "Configure alert for 5xx errors exceeding threshold",
]

for task in devops_tasks:
    result = devops_router.run(task=task, input="devops_request")

    print(f"\nTask: {task}")
    print(f"Assigned to: {result.get('agent_id')}")
    print(f"Result: {list(result.keys())}")
```

**Output**:
```
Task: Deploy new API version to production
Assigned to: deployment_agent
Result: ['agent_id', 'deployment_plan', 'commands']

Task: Create dashboard for application latency
Assigned to: monitoring_agent
Result: ['agent_id', 'metrics', 'alerts']

Task: Investigate high memory usage on prod servers
Assigned to: incident_agent
Result: ['agent_id', 'diagnosis', 'remediation']

Task: Set up blue-green deployment pipeline
Assigned to: deployment_agent
Result: ['agent_id', 'deployment_plan', 'commands']

Task: Configure alert for 5xx errors exceeding threshold
Assigned to: monitoring_agent
Result: ['agent_id', 'metrics', 'alerts']
```

---

### Pattern 3: Research & Analysis Pipeline

**Scenario**: Research pipeline with web search, data analysis, and report writing

**Implementation**:
```python
from kaizen.orchestration.pipeline import Pipeline
from kaizen.tools import WebSearchTool, FileReadTool, WriteFileTool

# Define research specialist signatures
class ResearchSignature(Signature):
    topic: str = InputField(description="Research topic")
    findings: str = OutputField(description="Research findings")
    sources: list = OutputField(description="Source URLs")

class AnalysisSignature(Signature):
    data: str = InputField(description="Data to analyze")
    insights: str = OutputField(description="Analysis insights")
    recommendations: str = OutputField(description="Recommendations")

class ReportSignature(Signature):
    content: str = InputField(description="Content to format")
    report: str = OutputField(description="Formatted report")
    summary: str = OutputField(description="Executive summary")

# Create research specialists with tools
research_agent = BaseAgent(
    config=config,
    signature=ResearchSignature(),
    agent_id="research_agent",
    description="Expert in web research, information gathering, and source validation",
    tools=[WebSearchTool(), FileReadTool()]
)

analysis_agent = BaseAgent(
    config=config,
    signature=AnalysisSignature(),
    agent_id="analysis_agent",
    description="Expert in data analysis, statistical insights, and pattern recognition"
)

report_agent = BaseAgent(
    config=config,
    signature=ReportSignature(),
    agent_id="report_agent",
    description="Expert in technical writing, report formatting, and executive summaries",
    tools=[WriteFileTool()]
)

# Create research router
research_router = Pipeline.router(
    agents=[research_agent, analysis_agent, report_agent],
    routing_strategy="semantic"
)

# Execute research workflow
workflow_steps = [
    ("Research latest trends in quantum computing", "research"),
    ("Analyze collected research findings", "analysis"),
    ("Write comprehensive report", "report"),
]

workflow_results = []
for step, expected_agent in workflow_steps:
    result = research_router.run(
        topic=step if "research" in expected_agent else None,
        data=step if "analysis" in expected_agent else None,
        content=step if "report" in expected_agent else None,
        input=step
    )

    actual_agent = result.get("agent_id")
    workflow_results.append(result)

    print(f"\nStep: {step}")
    print(f"Assigned to: {actual_agent} ({'✓' if expected_agent in actual_agent else '✗'})")
```

**Output**:
```
Step: Research latest trends in quantum computing
Assigned to: research_agent ✓

Step: Analyze collected research findings
Assigned to: analysis_agent ✓

Step: Write comprehensive report
Assigned to: report_agent ✓
```

---

### Pattern 4: Monitoring and Metrics

**Scenario**: Track routing decisions for observability and optimization

**Implementation**:
```python
from collections import defaultdict
from datetime import datetime
from kaizen.orchestration.pipeline import Pipeline

class MonitoredRouter:
    """Router with built-in metrics tracking."""

    def __init__(self, agents, routing_strategy="semantic"):
        self.router = Pipeline.router(
            agents=agents,
            routing_strategy=routing_strategy
        )
        self.metrics = defaultdict(int)
        self.routing_history = []
        self.start_time = datetime.now()

    def run(self, **inputs):
        """Execute with comprehensive metrics tracking."""
        request_start = datetime.now()

        # Execute routing
        result = self.router.run(**inputs)

        # Calculate latency
        latency_ms = (datetime.now() - request_start).total_seconds() * 1000

        # Track metrics
        agent_id = result.get("agent_id", "unknown")
        self.metrics[f"routed_to_{agent_id}"] += 1
        self.metrics["total_requests"] += 1

        if result.get("status") == "failed":
            self.metrics["total_errors"] += 1
            self.metrics[f"errors_{agent_id}"] += 1
        else:
            self.metrics["total_success"] += 1

        # Track latency
        self.metrics["total_latency_ms"] += latency_ms

        # Record routing history
        self.routing_history.append({
            "timestamp": datetime.now().isoformat(),
            "task": inputs.get("task", "unknown"),
            "agent_id": agent_id,
            "latency_ms": latency_ms,
            "status": result.get("status", "success")
        })

        return result

    def get_metrics(self):
        """Get comprehensive routing metrics."""
        total_requests = self.metrics["total_requests"]
        uptime_seconds = (datetime.now() - self.start_time).total_seconds()

        return {
            "total_requests": total_requests,
            "total_success": self.metrics["total_success"],
            "total_errors": self.metrics["total_errors"],
            "success_rate": (self.metrics["total_success"] / total_requests * 100) if total_requests > 0 else 0,
            "avg_latency_ms": (self.metrics["total_latency_ms"] / total_requests) if total_requests > 0 else 0,
            "requests_per_second": total_requests / uptime_seconds if uptime_seconds > 0 else 0,
            "routing_distribution": {
                agent: count
                for agent, count in self.metrics.items()
                if agent.startswith("routed_to_")
            },
            "error_distribution": {
                agent: count
                for agent, count in self.metrics.items()
                if agent.startswith("errors_")
            },
        }

    def get_routing_history(self, limit=10):
        """Get recent routing history."""
        return self.routing_history[-limit:]

# Usage
router = MonitoredRouter(
    agents=[code_agent, data_agent, writing_agent],
    routing_strategy="semantic"
)

# Execute 100 requests
for i in range(100):
    router.run(
        task=f"Task {i}: Generate code" if i % 3 == 0 else
             f"Task {i}: Analyze data" if i % 3 == 1 else
             f"Task {i}: Write documentation",
        input=f"data_{i}"
    )

# Get comprehensive metrics
metrics = router.get_metrics()
print("\n=== Routing Metrics ===")
print(f"Total Requests: {metrics['total_requests']}")
print(f"Success Rate: {metrics['success_rate']:.2f}%")
print(f"Avg Latency: {metrics['avg_latency_ms']:.2f}ms")
print(f"Requests/sec: {metrics['requests_per_second']:.2f}")

print("\n=== Routing Distribution ===")
for agent, count in metrics['routing_distribution'].items():
    percentage = (count / metrics['total_requests']) * 100
    print(f"{agent}: {count} ({percentage:.1f}%)")

# Get recent routing history
print("\n=== Recent Routing History ===")
for entry in router.get_routing_history(limit=5):
    print(f"{entry['timestamp']}: {entry['task'][:30]} → {entry['agent_id']} ({entry['latency_ms']:.2f}ms)")
```

**Output**:
```
=== Routing Metrics ===
Total Requests: 100
Success Rate: 100.00%
Avg Latency: 245.32ms
Requests/sec: 8.45

=== Routing Distribution ===
routed_to_code_specialist: 34 (34.0%)
routed_to_data_specialist: 33 (33.0%)
routed_to_writing_specialist: 33 (33.0%)

=== Recent Routing History ===
2025-10-27T14:32:15: Task 99: Write documentation → writing_specialist (238.45ms)
2025-10-27T14:32:14: Task 98: Analyze data → data_specialist (251.23ms)
2025-10-27T14:32:14: Task 97: Generate code → code_specialist (242.67ms)
2025-10-27T14:32:13: Task 96: Write documentation → writing_specialist (239.88ms)
2025-10-27T14:32:13: Task 95: Analyze data → data_specialist (248.91ms)
```

---

## Pipeline Composition

### Converting Router to Agent

Meta-controllers can be converted to agents using `.to_agent()`, allowing them to be used in nested coordination patterns.

**Why Convert to Agent?**
- **Composability**: Use router as a worker in another router
- **Hierarchical Routing**: Create multi-level routing systems
- **Pattern Integration**: Integrate with supervisor-worker patterns
- **Encapsulation**: Hide internal routing logic from consumers

**Basic Usage**:
```python
from kaizen.orchestration.pipeline import Pipeline

# Create routing pipeline
router_pipeline = Pipeline.router(
    agents=[code_agent, data_agent, writing_agent],
    routing_strategy="semantic"
)

# Convert to agent
router_agent = router_pipeline.to_agent(
    name="specialist_router",
    description="Routes to appropriate specialist"
)

# Use in another router
top_level_router = Pipeline.router(
    agents=[router_agent, other_agent],
    routing_strategy="semantic"
)
```

### Pattern: Hierarchical Routing

**Scenario**: Two-level routing system with category and specialist levels

**Implementation**:
```python
from kaizen.orchestration.pipeline import Pipeline

# Level 2: Specialist routers (leaf level)
code_router = Pipeline.router(
    agents=[
        python_expert,
        javascript_expert,
        java_expert,
        rust_expert
    ],
    routing_strategy="semantic"
).to_agent(
    name="code_router",
    description="Expert in programming across multiple languages"
)

data_router = Pipeline.router(
    agents=[
        sql_expert,
        visualization_expert,
        ml_expert,
        etl_expert
    ],
    routing_strategy="semantic"
).to_agent(
    name="data_router",
    description="Expert in data analysis, pipelines, and machine learning"
)

devops_router = Pipeline.router(
    agents=[
        kubernetes_expert,
        cicd_expert,
        monitoring_expert,
        security_expert
    ],
    routing_strategy="semantic"
).to_agent(
    name="devops_router",
    description="Expert in DevOps, infrastructure, and deployment"
)

# Level 1: Top-level router (category level)
top_router = Pipeline.router(
    agents=[code_router, data_router, devops_router],
    routing_strategy="semantic"
)

# Execute hierarchical routing
tasks = [
    "Write Python function to parse JSON",              # → code_router → python_expert
    "Create Grafana dashboard for API latency",         # → devops_router → monitoring_expert
    "Build ML model for churn prediction",              # → data_router → ml_expert
    "Set up GitHub Actions CI/CD pipeline",             # → devops_router → cicd_expert
    "Optimize SQL query performance",                   # → data_router → sql_expert
]

for task in tasks:
    result = top_router.run(task=task, input="hierarchical_routing")

    # Result includes both router and specialist info
    print(f"\nTask: {task}")
    print(f"Routed through: {result.get('agent_id')} (category router)")
    print(f"Executed by: {result.get('specialist_id', 'unknown')} (specialist)")
```

**Output**:
```
Task: Write Python function to parse JSON
Routed through: code_router (category router)
Executed by: python_expert (specialist)

Task: Create Grafana dashboard for API latency
Routed through: devops_router (category router)
Executed by: monitoring_expert (specialist)

Task: Build ML model for churn prediction
Routed through: data_router (category router)
Executed by: ml_expert (specialist)

Task: Set up GitHub Actions CI/CD pipeline
Routed through: devops_router (category router)
Executed by: cicd_expert (specialist)

Task: Optimize SQL query performance
Routed through: data_router (category router)
Executed by: sql_expert (specialist)
```

### Pattern: Router in Supervisor-Worker

**Scenario**: Router as a worker in supervisor-worker pattern

**Implementation**:
```python
from kaizen.agents.coordination.supervisor_worker import SupervisorWorkerPattern
from kaizen.orchestration.pipeline import Pipeline

# Create specialist router
specialist_router = Pipeline.router(
    agents=[code_agent, data_agent, writing_agent],
    routing_strategy="semantic"
).to_agent(
    name="specialist_router",
    description="Routes to code, data, or writing specialists"
)

# Create general worker
general_worker = BaseAgent(
    config=config,
    signature=GeneralSignature(),
    agent_id="general_worker",
    description="Handles general tasks not requiring specialization"
)

# Create supervisor-worker pattern with router as worker
pattern = SupervisorWorkerPattern(
    supervisor=supervisor_agent,
    workers=[specialist_router, general_worker],
    coordinator=coordinator_agent,
    shared_pool=shared_memory_pool
)

# Execute multi-agent workflow
result = pattern.execute_task(
    "Analyze codebase and generate documentation"
)

# Workflow:
# 1. Supervisor decomposes task into subtasks
# 2. Subtasks routed to specialist_router or general_worker
# 3. Specialist_router internally routes to code_agent or writing_agent
# 4. Coordinator aggregates results
```

---

## Testing Meta-Controllers

### Unit Tests

**Purpose**: Test routing logic without real LLM calls

**Pattern**: Mock agents, verify routing decisions

```python
import pytest
from unittest.mock import Mock, MagicMock
from kaizen.orchestration.pipeline import Pipeline
from kaizen.core.base_agent import BaseAgent

@pytest.mark.unit
def test_semantic_routing_selects_best_agent():
    """Test A2A semantic routing selects correct agent."""
    # Create mock agents
    code_agent = Mock(spec=BaseAgent)
    code_agent.agent_id = "coder"
    code_agent.description = "Python programming expert"
    code_agent.run = MagicMock(return_value={"agent_id": "coder", "code": "def foo(): pass"})
    code_agent.to_a2a_card = MagicMock(return_value={
        "agent_id": "coder",
        "primary_capabilities": [{"capability": "Code generation"}]
    })

    data_agent = Mock(spec=BaseAgent)
    data_agent.agent_id = "data"
    data_agent.description = "Data analysis expert"
    data_agent.run = MagicMock(return_value={"agent_id": "data", "analysis": "Trends identified"})
    data_agent.to_a2a_card = MagicMock(return_value={
        "agent_id": "data",
        "primary_capabilities": [{"capability": "Data analysis"}]
    })

    # Create router
    router = Pipeline.router(
        agents=[code_agent, data_agent],
        routing_strategy="semantic"
    )

    # Test coding task routing
    result = router.run(task="Write Python function", input="test")
    assert result.get("agent_id") == "coder"
    code_agent.run.assert_called_once()

    # Test data task routing
    result = router.run(task="Analyze sales data", input="test")
    assert result.get("agent_id") == "data"
    data_agent.run.assert_called_once()

@pytest.mark.unit
def test_round_robin_distributes_evenly():
    """Test round-robin rotates through agents."""
    # Create mock agents
    agents = [
        Mock(spec=BaseAgent, agent_id=f"agent_{i}")
        for i in range(3)
    ]

    for agent in agents:
        agent.run = MagicMock(return_value={"agent_id": agent.agent_id})

    # Create router
    router = Pipeline.router(
        agents=agents,
        routing_strategy="round-robin"
    )

    # Execute 6 requests
    for i in range(6):
        result = router.run(task=f"Task {i}", input="data")
        expected_agent = agents[i % 3].agent_id
        assert result.get("agent_id") == expected_agent

@pytest.mark.unit
def test_graceful_error_handling():
    """Test graceful mode returns error info."""
    # Create failing agent
    failing_agent = Mock(spec=BaseAgent)
    failing_agent.agent_id = "failing"
    failing_agent.run = MagicMock(side_effect=Exception("Test error"))

    # Create router with graceful error handling
    router = Pipeline.router(
        agents=[failing_agent],
        routing_strategy="round-robin",
        error_handling="graceful"
    )

    # Execute - should not raise exception
    result = router.run(task="Test task", input="data")

    # Verify error info in result
    assert result.get("status") == "failed"
    assert "Test error" in result.get("error", "")
    assert result.get("agent_id") == "failing"

@pytest.mark.unit
def test_fail_fast_error_handling():
    """Test fail-fast mode raises exception."""
    # Create failing agent
    failing_agent = Mock(spec=BaseAgent)
    failing_agent.agent_id = "failing"
    failing_agent.run = MagicMock(side_effect=Exception("Test error"))

    # Create router with fail-fast error handling
    router = Pipeline.router(
        agents=[failing_agent],
        routing_strategy="round-robin",
        error_handling="fail-fast"
    )

    # Execute - should raise exception
    with pytest.raises(Exception, match="Test error"):
        router.run(task="Test task", input="data")
```

---

### Integration Tests

**Purpose**: Test routing with real agents (Ollama - free)

**Pattern**: Real LLM calls, verify routing behavior

```python
import pytest
from kaizen.orchestration.pipeline import Pipeline
from kaizen.core.base_agent import BaseAgent, BaseAgentConfig
from kaizen.signatures import Signature, InputField, OutputField

@pytest.mark.integration
@pytest.mark.asyncio
async def test_router_with_real_ollama_agents():
    """Test router with real Ollama agents."""
    # Define signatures
    class CodingSignature(Signature):
        task: str = InputField(description="Coding task")
        code: str = OutputField(description="Generated code")

    class DataSignature(Signature):
        task: str = InputField(description="Data analysis task")
        analysis: str = OutputField(description="Analysis results")

    # Create real agents (Ollama - free)
    config = BaseAgentConfig(
        llm_provider="ollama",
        model="llama3.2:1b"  # Small, fast model
    )

    code_agent = BaseAgent(
        config=config,
        signature=CodingSignature(),
        agent_id="code_agent",
        description="Python programming expert"
    )

    data_agent = BaseAgent(
        config=config,
        signature=DataSignature(),
        agent_id="data_agent",
        description="Data analysis expert"
    )

    # Create router
    router = Pipeline.router(
        agents=[code_agent, data_agent],
        routing_strategy="semantic"
    )

    # Test routing with real LLM
    result = router.run(
        task="Write a function to sort a list",
        input="sorting_task"
    )

    # Verify result structure
    assert isinstance(result, dict)
    assert "agent_id" in result
    assert result.get("status") != "failed" or "error" in result

@pytest.mark.integration
def test_round_robin_load_balancing():
    """Test round-robin distributes load evenly."""
    # Create 3 identical agents
    agents = [
        BaseAgent(
            config=BaseAgentConfig(llm_provider="ollama", model="llama3.2:1b"),
            signature=QASignature(),
            agent_id=f"qa_agent_{i}",
            description="Question answering expert"
        )
        for i in range(3)
    ]

    # Create router
    router = Pipeline.router(
        agents=agents,
        routing_strategy="round-robin"
    )

    # Execute 9 requests
    agent_counts = {f"qa_agent_{i}": 0 for i in range(3)}

    for i in range(9):
        result = router.run(task=f"Question {i}", input=f"data_{i}")
        agent_id = result.get("agent_id")
        agent_counts[agent_id] += 1

    # Verify even distribution
    assert all(count == 3 for count in agent_counts.values())
```

---

### E2E Tests

**Purpose**: Test full routing workflow with real OpenAI agents

**Pattern**: Real production scenarios, comprehensive validation

```python
import os
import pytest
from kaizen.orchestration.pipeline import Pipeline
from kaizen.core.base_agent import BaseAgent, BaseAgentConfig
from kaizen.signatures import Signature, InputField, OutputField

@pytest.mark.e2e
@pytest.mark.asyncio
@pytest.mark.skipif(
    not os.getenv("OPENAI_API_KEY"),
    reason="OPENAI_API_KEY not set"
)
async def test_semantic_routing_to_correct_specialist_e2e():
    """
    Test meta-controller routes tasks to correct specialists.

    Validates:
    - Coding tasks route to coding specialist
    - Data tasks route to data specialist
    - Writing tasks route to writing specialist
    """
    # Define signatures
    class CodingSignature(Signature):
        task: str = InputField(description="Coding task")
        code: str = OutputField(description="Generated code")

    class DataSignature(Signature):
        task: str = InputField(description="Data analysis task")
        analysis: str = OutputField(description="Analysis results")

    class WritingSignature(Signature):
        task: str = InputField(description="Writing task")
        content: str = OutputField(description="Written content")

    # Create real OpenAI agents
    config = BaseAgentConfig(
        llm_provider="openai",
        model="gpt-4o-2024-08-06"
    )

    coding_agent = BaseAgent(
        config=config,
        signature=CodingSignature(),
        agent_id="coding_specialist",
        description="Expert in Python programming and algorithms"
    )

    data_agent = BaseAgent(
        config=config,
        signature=DataSignature(),
        agent_id="data_specialist",
        description="Expert in data analysis and visualization"
    )

    writing_agent = BaseAgent(
        config=config,
        signature=WritingSignature(),
        agent_id="writing_specialist",
        description="Expert in technical writing and documentation"
    )

    # Create meta-controller
    router = Pipeline.router(
        agents=[coding_agent, data_agent, writing_agent],
        routing_strategy="semantic"
    )

    # Test 1: Coding task
    coding_result = router.run(
        task="Write a Python function to calculate fibonacci",
        input="fib"
    )

    assert "error" not in coding_result
    assert coding_result.get("agent_id") == "coding_specialist"
    assert "code" in coding_result

    # Test 2: Data task
    data_result = router.run(
        task="Analyze sales trends and identify patterns",
        input="sales.csv"
    )

    assert "error" not in data_result
    assert data_result.get("agent_id") == "data_specialist"
    assert "analysis" in data_result

    # Test 3: Writing task
    writing_result = router.run(
        task="Write a technical blog post about machine learning",
        input="ML topic"
    )

    assert "error" not in writing_result
    assert writing_result.get("agent_id") == "writing_specialist"
    assert "content" in writing_result

@pytest.mark.e2e
@pytest.mark.asyncio
async def test_hierarchical_routing_e2e():
    """Test two-level hierarchical routing."""
    # Create specialist routers (level 2)
    code_router = Pipeline.router(
        agents=[python_expert, java_expert],
        routing_strategy="semantic"
    ).to_agent(name="code_router")

    data_router = Pipeline.router(
        agents=[sql_expert, ml_expert],
        routing_strategy="semantic"
    ).to_agent(name="data_router")

    # Create top-level router (level 1)
    top_router = Pipeline.router(
        agents=[code_router, data_router],
        routing_strategy="semantic"
    )

    # Test hierarchical routing
    result = top_router.run(
        task="Build ML model for recommendation system",
        input="model_requirements"
    )

    assert "error" not in result
    # Should route: top_router → data_router → ml_expert
```

---

## Troubleshooting

### Issue 1: No Agent Selected / Routes to First Agent

**Symptoms**:
- All tasks route to first agent in list
- A2A capability matching not working
- Expected semantic routing, getting round-robin behavior

**Common Causes**:

1. **Missing task parameter**:
```python
# ❌ WRONG: No task parameter
result = router.run(input="data")

# ✅ CORRECT: Include task parameter
result = router.run(task="Analyze data", input="data")
```

2. **Vague agent descriptions**:
```python
# ❌ WRONG: Generic descriptions
agent = BaseAgent(
    config=config,
    signature=signature,
    agent_id="agent_1",
    description="Helper agent"  # Too vague!
)

# ✅ CORRECT: Specific, detailed descriptions
agent = BaseAgent(
    config=config,
    signature=signature,
    agent_id="data_specialist",
    description="Expert in data analysis, statistical insights, and visualization with Pandas, NumPy, and Matplotlib"
)
```

3. **A2A nodes unavailable**:
```bash
# Check if A2A nodes installed
python -c "from kailash.nodes.ai.a2a import A2ACapabilityMatchNode; print('OK')"

# If error, reinstall Kailash SDK
pip install --upgrade kailash
```

**Solution**: Ensure task parameter provided and agent descriptions are specific and detailed.

---

### Issue 2: Routing Latency Too High

**Symptoms**:
- Slow response times (> 500ms per request)
- A2A matching taking too long
- System unresponsive under load

**Common Causes**:

1. **Semantic routing overhead**:
```python
# A2A capability matching adds 100-300ms latency
# For latency-sensitive applications, use round-robin
router = Pipeline.router(
    agents=agents,
    routing_strategy="round-robin"  # < 1ms latency
)
```

2. **Too many agents**:
```python
# ❌ WRONG: 50 agents = 50× A2A calls
router = Pipeline.router(
    agents=fifty_agents,
    routing_strategy="semantic"
)

# ✅ CORRECT: Use hierarchical routing
category_router = Pipeline.router(
    agents=[code_router, data_router, devops_router],
    routing_strategy="semantic"
)
# Each router handles 10-15 agents = 3× faster
```

3. **Network latency (OpenAI API)**:
```python
# Use local models for routing decision
routing_config = BaseAgentConfig(
    llm_provider="ollama",  # Local, fast
    model="llama3.2:1b"
)

# Keep OpenAI for actual task execution
task_config = BaseAgentConfig(
    llm_provider="openai",
    model="gpt-4"
)
```

**Solution**: Use round-robin for load balancing, hierarchical routing for many agents, or local models for routing decisions.

---

### Issue 3: Routing to Wrong Agent

**Symptoms**:
- Tasks consistently routed to incorrect agent
- Semantic matching scores inverted
- Expected agent not selected

**Common Causes**:

1. **Agent description conflicts**:
```python
# ❌ WRONG: Overlapping descriptions
code_agent = BaseAgent(
    description="Expert in coding and data analysis"  # Overlaps with data_agent
)

data_agent = BaseAgent(
    description="Expert in data analysis and code generation"  # Overlaps with code_agent
)

# ✅ CORRECT: Distinct, non-overlapping descriptions
code_agent = BaseAgent(
    description="Expert in Python/Java programming, algorithms, and software architecture"
)

data_agent = BaseAgent(
    description="Expert in statistical analysis, visualization, and data insights"
)
```

2. **Insufficient examples in A2A cards**:
```python
# Provide multiple examples in agent descriptions
agent = BaseAgent(
    description="Expert in DevOps: Kubernetes deployment, CI/CD pipelines (GitHub Actions, Jenkins), infrastructure as code (Terraform, Ansible), and monitoring (Prometheus, Grafana)"
)
```

3. **Task description too vague**:
```python
# ❌ WRONG: Vague task
result = router.run(task="Do something", input="data")

# ✅ CORRECT: Specific task
result = router.run(
    task="Analyze user engagement metrics and create dashboard",
    input="engagement_data.csv"
)
```

**Solution**: Ensure agent descriptions are distinct, provide detailed examples, and use specific task descriptions.

---

### Issue 4: Graceful Error Handling Not Working

**Symptoms**:
- Exceptions raised despite `error_handling="graceful"`
- Application crashes on agent failure
- Error info not in result dict

**Common Causes**:

1. **Incorrect error handling mode**:
```python
# ❌ WRONG: Default to fail-fast
router = Pipeline.router(agents=agents)

# ✅ CORRECT: Explicitly set graceful mode
router = Pipeline.router(
    agents=agents,
    error_handling="graceful"
)
```

2. **Checking wrong error format**:
```python
# ❌ WRONG: Checking for 'error' key existence
if "error" in result:
    handle_error()

# ✅ CORRECT: Check status field
if result.get("status") == "failed":
    error_msg = result.get("error")
    handle_error(error_msg)
```

3. **Exception raised outside agent execution**:
```python
# Graceful mode only catches agent.run() exceptions
# Exceptions in routing logic still propagate

try:
    result = router.run(task=task, input=data)

    if result.get("status") == "failed":
        handle_graceful_error(result)

except Exception as e:
    # Routing infrastructure error (not agent error)
    handle_infrastructure_error(e)
```

**Solution**: Explicitly set graceful mode, check `status` field, and handle routing infrastructure errors separately.

---

### Issue 5: Pipeline Composition Not Working

**Symptoms**:
- `.to_agent()` returns error
- Nested routers not routing correctly
- Hierarchical routing fails

**Common Causes**:

1. **Missing name/description**:
```python
# ❌ WRONG: No name/description
router_agent = router_pipeline.to_agent()

# ✅ CORRECT: Provide descriptive metadata
router_agent = router_pipeline.to_agent(
    name="code_router",
    description="Routes to Python, Java, or Rust specialists"
)
```

2. **Circular routing**:
```python
# ❌ WRONG: Router A contains Router B, Router B contains Router A
router_a = Pipeline.router(agents=[agent1, router_b.to_agent()])
router_b = Pipeline.router(agents=[agent2, router_a.to_agent()])

# ✅ CORRECT: Hierarchical, not circular
level2_router_a = Pipeline.router(agents=[agent1, agent2])
level2_router_b = Pipeline.router(agents=[agent3, agent4])
level1_router = Pipeline.router(agents=[
    level2_router_a.to_agent(),
    level2_router_b.to_agent()
])
```

3. **Wrong routing strategy at levels**:
```python
# Use semantic routing at top level, specialized routing at leaf level
top_router = Pipeline.router(
    agents=[category_routers],
    routing_strategy="semantic"  # Semantic for category selection
)

code_router = Pipeline.router(
    agents=[language_experts],
    routing_strategy="round-robin"  # Round-robin for load balancing
)
```

**Solution**: Provide descriptive metadata, avoid circular routing, and use appropriate routing strategies at each level.

---

### Issue 6: Memory Leaks / High Memory Usage

**Symptoms**:
- Memory usage grows over time
- Application becomes sluggish after many requests
- Out of memory errors

**Common Causes**:

1. **Routing history accumulation**:
```python
# ❌ WRONG: Unbounded history storage
class MonitoredRouter:
    def __init__(self):
        self.routing_history = []  # Grows indefinitely!

    def run(self, **inputs):
        self.routing_history.append(entry)  # Memory leak

# ✅ CORRECT: Bounded history with rotation
from collections import deque

class MonitoredRouter:
    def __init__(self, max_history=1000):
        self.routing_history = deque(maxlen=max_history)  # Auto-rotation

    def run(self, **inputs):
        self.routing_history.append(entry)  # Bounded storage
```

2. **Agent instance accumulation**:
```python
# ❌ WRONG: Creating new agents on every request
def handle_request(task):
    agents = [create_agent() for _ in range(10)]  # Memory leak!
    router = Pipeline.router(agents=agents)
    return router.run(task=task)

# ✅ CORRECT: Reuse agent instances
agents = [create_agent() for _ in range(10)]  # Create once
router = Pipeline.router(agents=agents)

def handle_request(task):
    return router.run(task=task)  # Reuse router
```

3. **Result caching without eviction**:
```python
# ❌ WRONG: Unbounded cache
results_cache = {}  # Grows indefinitely

# ✅ CORRECT: LRU cache with eviction
from functools import lru_cache

@lru_cache(maxsize=1000)
def execute_routing(task, input_hash):
    return router.run(task=task, input=input_hash)
```

**Solution**: Use bounded data structures, reuse agent instances, and implement cache eviction policies.

---

## Related Documentation

- **[Planning Agents Guide](./planning-system-guide.md)**: PlanningAgent and PEVAgent for complex task orchestration
- **[Coordination API Reference](../reference/coordination-api.md)**: Complete API documentation for Pipeline.router()
- **[BaseAgent Architecture](./baseagent-architecture.md)**: Core agent system and A2A protocol
- **[Multi-Agent Coordination](./multi-agent-coordination.md)**: Supervisor-worker and other coordination patterns
- **[Tools API Reference](../reference/tools-api.md)**: Tool calling and approval workflows

---

## Version History

**v1.0.0** (2025-10-27):
- Initial release with comprehensive user guide
- Semantic routing via A2A protocol
- Round-robin and random fallback strategies
- Graceful and fail-fast error handling modes
- Pipeline composition patterns
- Production-ready examples and troubleshooting

---

**Complete Meta-Controller User Guide** | Intelligent agent routing with A2A capability matching
