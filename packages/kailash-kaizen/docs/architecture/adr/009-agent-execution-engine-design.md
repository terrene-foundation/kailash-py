# ADR-010: Agent Execution Engine Design

## Status
**Accepted** - 2025-09-24

## Context

Kaizen agents currently lack a comprehensive execution engine (BLOCKER-003), preventing direct agent execution, workflow integration, and multi-agent coordination. The current implementation only provides basic agent creation without execution capabilities.

### Problem Statement
- Agents cannot execute tasks directly (`agent.execute()` missing)
- No agent-to-workflow conversion for seamless Core SDK integration
- Multi-agent coordination patterns (debate, pipeline, consensus) not implemented
- No agent state management or context persistence
- Missing performance optimization and execution monitoring

### Decision Drivers
1. **Direct Execution**: `agent.execute()` for immediate task completion
2. **Workflow Integration**: Seamless conversion to WorkflowBuilder nodes
3. **Multi-Agent Coordination**: Built-in patterns for agent collaboration
4. **State Management**: Persistent context across executions
5. **Performance**: <200ms execution target with optimization
6. **Core SDK Compatibility**: Perfect integration with existing patterns

### Constraints
- Must integrate with signature programming system (ADR-008)
- Must support MCP integration (ADR-009)
- Cannot break Core SDK execution patterns
- Must work with existing Kailash runtime infrastructure
- Need enterprise features (monitoring, security, audit)

## Decision

Implement a multi-layered agent execution engine with direct execution, workflow integration, and coordination capabilities:

### Layer 1: Direct Agent Execution
```python
# Simple direct execution
agent = kaizen.create_agent("researcher", config={"model": "gpt-4"})
result = agent.execute(
    task="Research machine learning trends",
    context={"focus": "enterprise applications"}
)

# Signature-based execution
signature = kaizen.create_signature("question: str -> answer: str, confidence: float")
agent = kaizen.create_agent("qa_agent", signature=signature)
result = agent.execute(question="What is machine learning?")
print(result.answer, result.confidence)  # Structured output

# Stateful execution with memory
agent.enable_memory(provider="vector_db")
result1 = agent.execute(task="Remember: User prefers technical details")
result2 = agent.execute(task="Explain neural networks")  # Uses remembered context
```

### Layer 2: Workflow Integration
```python
# Agent to workflow node conversion
agent = kaizen.create_agent("processor", signature=signature)
workflow = WorkflowBuilder()

# Convert agent to workflow node
agent_node = agent.to_workflow_node("processing_step")
workflow.add_node_instance(agent_node)

# Direct agent workflow generation
agent_workflow = agent.to_workflow()
results, run_id = runtime.execute(agent_workflow.build())

# Multiple agents in workflow
workflow = WorkflowBuilder()
workflow.add_agent(research_agent, "research")
workflow.add_agent(analysis_agent, "analysis")
workflow.add_connection("research", "analysis")
```

### Layer 3: Multi-Agent Coordination
```python
# Debate pattern
debate_result = kaizen.create_debate_workflow(
    agents=["optimist", "pessimist", "moderator"],
    topic="AI adoption strategy",
    rounds=3
)

# Pipeline pattern
pipeline = kaizen.create_pipeline([
    ("data_collector", {"source": "web"}),
    ("analyzer", {"depth": "detailed"}),
    ("reporter", {"format": "executive_summary"})
])

# Consensus pattern
consensus = kaizen.create_consensus_workflow(
    agents=["expert1", "expert2", "expert3"],
    decision_criteria="majority_vote",
    confidence_threshold=0.8
)

# Supervisor-worker pattern
supervisor = kaizen.create_supervisor_agent("manager", {
    "workers": ["researcher", "analyst", "writer"],
    "task_allocation": "automatic",
    "quality_control": True
})
```

### Layer 4: Enterprise Execution Management
```python
# Execution monitoring
execution_monitor = agent.get_execution_monitor()
execution_monitor.enable_real_time_tracking()
execution_monitor.set_performance_alerts(latency_threshold=5000)

# Execution optimization
optimizer = agent.get_execution_optimizer()
optimizer.enable_auto_optimization()
optimizer.set_optimization_targets(["latency", "accuracy", "cost"])

# Security and audit
agent.enable_audit_logging()
agent.set_access_policy("team_lead_approval_required")
```

## Consequences

### Positive
- **Intuitive Execution**: Direct `agent.execute()` for immediate results
- **Seamless Integration**: Perfect WorkflowBuilder compatibility
- **Rich Coordination**: Built-in multi-agent patterns
- **Enterprise Ready**: Monitoring, optimization, security built-in
- **State Management**: Persistent context across executions
- **Performance Optimized**: Auto-optimization and caching

### Negative
- **Implementation Complexity**: Four-layer architecture requires careful design
- **Memory Overhead**: State management and monitoring increase memory usage
- **Execution Latency**: Additional layers may impact performance
- **Debugging Complexity**: Multi-layer execution makes debugging more complex

### Risks
- **State Corruption**: Persistent state may become corrupted
- **Coordination Deadlocks**: Multi-agent patterns may create deadlocks
- **Performance Degradation**: Optimization overhead may impact simple cases
- **Memory Leaks**: State management may lead to memory accumulation

## Alternatives Considered

### Option 1: Simple Execution Only
- **Pros**: Low complexity, fast implementation, easy debugging
- **Cons**: No workflow integration, no multi-agent support, limited enterprise features
- **Why Rejected**: Insufficient for Kaizen's enterprise goals

### Option 2: Workflow-Only Execution
- **Pros**: Perfect Core SDK integration, proven execution patterns
- **Cons**: No direct execution, poor developer experience for simple tasks
- **Why Rejected**: Doesn't meet direct execution requirement

### Option 3: External Coordination Service
- **Pros**: Clean separation, scalable, service-oriented architecture
- **Cons**: Additional infrastructure, network latency, complexity overhead
- **Why Rejected**: Increases deployment complexity, doesn't align with framework goals

### Option 4: Actor Model Implementation
- **Pros**: Proven concurrency model, excellent for multi-agent systems
- **Cons**: Steep learning curve, complex debugging, doesn't align with Core SDK patterns
- **Why Rejected**: Too different from Kailash patterns, high adoption barrier

## Implementation Plan

### Phase 1: Direct Execution Foundation (Week 1-2)
```python
# Core execution interfaces
class AgentExecutor:
    def __init__(self, agent: Agent):
        self.agent = agent
        self.execution_context = ExecutionContext()
        self.state_manager = StateManager(agent)

    def execute(self, **inputs) -> ExecutionResult:
        # Validate inputs with signature if available
        validated_inputs = self._validate_inputs(inputs)

        # Execute with context and state
        result = self._execute_with_context(validated_inputs)

        # Update state and return structured result
        self.state_manager.update_state(inputs, result)
        return ExecutionResult(data=result, metadata=self._get_execution_metadata())

class ExecutionContext:
    def __init__(self):
        self.memory: Dict[str, Any] = {}
        self.conversation_history: List[Dict] = []
        self.execution_history: List[ExecutionRecord] = []
        self.performance_metrics: PerformanceTracker = PerformanceTracker()

class ExecutionResult:
    def __init__(self, data: Dict[str, Any], metadata: ExecutionMetadata):
        self.data = data
        self.metadata = metadata
        self.success = metadata.success
        self.error = metadata.error

    def __getattr__(self, name):
        # Allow direct access to result fields: result.answer, result.confidence
        if name in self.data:
            return self.data[name]
        raise AttributeError(f"ExecutionResult has no attribute '{name}'")
```

### Phase 2: Workflow Integration (Week 3-4)
```python
# Agent to workflow conversion
class AgentWorkflowConverter:
    def agent_to_workflow_node(self, agent: Agent, node_id: str) -> WorkflowNode:
        # Create custom node that wraps agent execution
        return AgentWrapperNode(
            node_id=node_id,
            agent=agent,
            parameters=self._extract_agent_parameters(agent)
        )

    def agent_to_workflow(self, agent: Agent) -> WorkflowBuilder:
        workflow = WorkflowBuilder()

        if agent.signature:
            # Signature-based workflow generation
            workflow = agent.signature.compile_to_workflow()
            # Inject agent-specific configuration
            self._inject_agent_config(workflow, agent)
        else:
            # Basic agent workflow
            workflow.add_node("LLMAgentNode", "agent_exec", {
                "model": agent.config.get("model", "gpt-4"),
                "temperature": agent.config.get("temperature", 0.7),
                "system_prompt": agent.config.get("system_prompt", ""),
                **agent.config
            })

        return workflow

class AgentWrapperNode(Node):
    def __init__(self, node_id: str, agent: Agent, **kwargs):
        super().__init__(node_id, **kwargs)
        self.agent = agent

    def run(self, **inputs) -> Dict[str, Any]:
        # Execute agent and return results compatible with workflow
        result = self.agent.execute(**inputs)
        return result.data if hasattr(result, 'data') else result
```

### Phase 3: Multi-Agent Coordination (Week 5-6)
```python
# Multi-agent coordination patterns
class MultiAgentCoordinator:
    def create_debate_workflow(self, agents: List[Agent], topic: str, rounds: int = 3) -> WorkflowBuilder:
        workflow = WorkflowBuilder()

        # Add debate initialization
        workflow.add_node("ConstantNode", "topic", {"value": topic})

        # Add agents as debate participants
        for i, agent in enumerate(agents):
            workflow.add_agent(agent, f"debater_{i}")

        # Add debate coordination logic
        workflow.add_node("DebateCoordinatorNode", "coordinator", {
            "participants": [f"debater_{i}" for i in range(len(agents))],
            "rounds": rounds,
            "topic": "${topic.value}"
        })

        return workflow

    def create_pipeline(self, agent_configs: List[Tuple[str, Dict]]) -> WorkflowBuilder:
        workflow = WorkflowBuilder()

        for i, (agent_name, config) in enumerate(agent_configs):
            agent = kaizen.create_agent(agent_name, config)
            node_id = f"step_{i}_{agent_name}"
            workflow.add_agent(agent, node_id)

            # Connect to previous step
            if i > 0:
                prev_node = f"step_{i-1}_{agent_configs[i-1][0]}"
                workflow.add_connection(prev_node, node_id)

        return workflow

    def create_consensus_workflow(self, agents: List[Agent], **config) -> WorkflowBuilder:
        workflow = WorkflowBuilder()

        # Add all agents as parallel processors
        for i, agent in enumerate(agents):
            workflow.add_agent(agent, f"agent_{i}")

        # Add consensus aggregation
        workflow.add_node("ConsensusAggregatorNode", "consensus", {
            "input_agents": [f"agent_{i}" for i in range(len(agents))],
            "decision_criteria": config.get("decision_criteria", "majority_vote"),
            "confidence_threshold": config.get("confidence_threshold", 0.8)
        })

        # Connect all agents to consensus node
        for i in range(len(agents)):
            workflow.add_connection(f"agent_{i}", "consensus")

        return workflow
```

### Phase 4: Enterprise Features (Week 7-8)
```python
# Performance monitoring and optimization
class ExecutionMonitor:
    def __init__(self, agent: Agent):
        self.agent = agent
        self.metrics = MetricsCollector()
        self.alerts = AlertManager()

    def track_execution(self, execution_id: str, inputs: Dict, result: ExecutionResult):
        metrics = {
            "execution_time": result.metadata.execution_time,
            "token_usage": result.metadata.token_usage,
            "cost": result.metadata.cost,
            "success": result.success
        }
        self.metrics.record(execution_id, metrics)

        # Check for performance alerts
        if metrics["execution_time"] > self.alerts.latency_threshold:
            self.alerts.trigger_latency_alert(execution_id, metrics)

class ExecutionOptimizer:
    def __init__(self, agent: Agent):
        self.agent = agent
        self.optimization_history = []

    def optimize_execution(self, execution_history: List[ExecutionRecord]) -> OptimizationSuggestions:
        # Analyze execution patterns
        patterns = self._analyze_execution_patterns(execution_history)

        # Generate optimization suggestions
        suggestions = []

        if patterns.avg_execution_time > 1000:  # ms
            suggestions.append(OptimizationSuggestion(
                type="model_selection",
                description="Consider using faster model for simple tasks",
                expected_improvement="50% latency reduction"
            ))

        if patterns.repetitive_inputs:
            suggestions.append(OptimizationSuggestion(
                type="caching",
                description="Enable result caching for repetitive inputs",
                expected_improvement="90% latency reduction for cached results"
            ))

        return OptimizationSuggestions(suggestions)

# State management
class AgentStateManager:
    def __init__(self, agent: Agent, memory_provider: MemoryProvider):
        self.agent = agent
        self.memory_provider = memory_provider
        self.state_key = f"agent_state_{agent.id}"

    def load_state(self) -> AgentState:
        state_data = self.memory_provider.retrieve(self.state_key)
        return AgentState.from_dict(state_data) if state_data else AgentState()

    def save_state(self, state: AgentState):
        self.memory_provider.store(self.state_key, state.to_dict())

    def update_state_from_execution(self, inputs: Dict, result: ExecutionResult):
        state = self.load_state()

        # Update conversation history
        state.conversation_history.append({
            "timestamp": datetime.now(),
            "inputs": inputs,
            "outputs": result.data,
            "success": result.success
        })

        # Update learned patterns
        if result.success:
            state.successful_patterns.append({
                "input_pattern": self._extract_input_pattern(inputs),
                "output_pattern": self._extract_output_pattern(result.data)
            })

        # Maintain state size limits
        state.cleanup_old_data(max_history=1000)

        self.save_state(state)
```

## Implementation Guidance

### Core Components

#### 1. Enhanced Agent Class
```python
class Agent:
    def __init__(self, agent_id: str, **config):
        super().__init__(agent_id, **config)

        # Execution components
        self.executor = AgentExecutor(self)
        self.workflow_converter = AgentWorkflowConverter()
        self.state_manager = AgentStateManager(self, memory_provider)

        # Monitoring and optimization
        self.monitor = ExecutionMonitor(self)
        self.optimizer = ExecutionOptimizer(self)

        # MCP integration (from ADR-009)
        self.mcp_server_manager = MCPServerManager(self)
        self.mcp_client_manager = MCPClientManager(self)

    def execute(self, **inputs) -> ExecutionResult:
        """Execute agent with comprehensive execution engine."""
        return self.executor.execute(**inputs)

    def to_workflow_node(self, node_id: str) -> WorkflowNode:
        """Convert agent to workflow node for Core SDK integration."""
        return self.workflow_converter.agent_to_workflow_node(self, node_id)

    def to_workflow(self) -> WorkflowBuilder:
        """Convert agent to complete workflow."""
        return self.workflow_converter.agent_to_workflow(self)

    def enable_memory(self, provider: str = "default"):
        """Enable persistent state management."""
        self.state_manager.enable(provider)

    def get_execution_monitor(self) -> ExecutionMonitor:
        """Get execution monitoring interface."""
        return self.monitor

    def get_execution_optimizer(self) -> ExecutionOptimizer:
        """Get execution optimization interface."""
        return self.optimizer
```

#### 2. Execution Context Management
```python
class ExecutionContext:
    def __init__(self, agent: Agent):
        self.agent = agent
        self.session_id = str(uuid.uuid4())
        self.conversation_history = []
        self.execution_metadata = {}
        self.performance_tracker = PerformanceTracker()

    def add_to_history(self, interaction: Dict):
        self.conversation_history.append({
            **interaction,
            "timestamp": datetime.now(),
            "session_id": self.session_id
        })

    def get_relevant_context(self, inputs: Dict, max_context: int = 5) -> List[Dict]:
        # Retrieve most relevant historical context
        if not self.conversation_history:
            return []

        # Simple relevance: recent interactions
        return self.conversation_history[-max_context:]

    def format_context_for_prompt(self, context: List[Dict]) -> str:
        if not context:
            return ""

        formatted = "Previous conversation:\n"
        for item in context:
            formatted += f"User: {item.get('inputs', {})}\n"
            formatted += f"Assistant: {item.get('outputs', {})}\n"

        return formatted
```

#### 3. Multi-Agent Coordination Primitives
```python
class CoordinationPattern(ABC):
    @abstractmethod
    def create_workflow(self, agents: List[Agent], **config) -> WorkflowBuilder:
        pass

class DebatePattern(CoordinationPattern):
    def create_workflow(self, agents: List[Agent], topic: str, rounds: int = 3) -> WorkflowBuilder:
        workflow = WorkflowBuilder()

        # Initialize debate
        workflow.add_node("ConstantNode", "topic", {"value": topic})
        workflow.add_node("ConstantNode", "rounds", {"value": rounds})

        # Add debaters
        for i, agent in enumerate(agents):
            agent_node = agent.to_workflow_node(f"debater_{i}")
            workflow.add_node_instance(agent_node)

        # Add debate controller
        workflow.add_node("DebateControllerNode", "controller", {
            "debaters": [f"debater_{i}" for i in range(len(agents))],
            "topic": "${topic.value}",
            "rounds": "${rounds.value}"
        })

        return workflow

class PipelinePattern(CoordinationPattern):
    def create_workflow(self, agents: List[Agent], **config) -> WorkflowBuilder:
        workflow = WorkflowBuilder()

        previous_node = None
        for i, agent in enumerate(agents):
            node_id = f"pipeline_step_{i}"
            agent_node = agent.to_workflow_node(node_id)
            workflow.add_node_instance(agent_node)

            if previous_node:
                workflow.add_connection(previous_node, node_id)
            previous_node = node_id

        return workflow

class ConsensusPattern(CoordinationPattern):
    def create_workflow(self, agents: List[Agent], **config) -> WorkflowBuilder:
        workflow = WorkflowBuilder()

        # Add all agents in parallel
        agent_nodes = []
        for i, agent in enumerate(agents):
            node_id = f"consensus_agent_{i}"
            agent_node = agent.to_workflow_node(node_id)
            workflow.add_node_instance(agent_node)
            agent_nodes.append(node_id)

        # Add consensus aggregator
        workflow.add_node("ConsensusAggregatorNode", "consensus", {
            "input_nodes": agent_nodes,
            "decision_criteria": config.get("decision_criteria", "majority"),
            "confidence_threshold": config.get("confidence_threshold", 0.8)
        })

        # Connect all agents to consensus
        for node_id in agent_nodes:
            workflow.add_connection(node_id, "consensus")

        return workflow
```

### Integration Patterns

#### 1. Direct Execution Pattern
```python
# Simple execution
agent = kaizen.create_agent("assistant", {"model": "gpt-4"})
result = agent.execute(task="Summarize this document", document=doc_content)
print(result.summary)

# Signature-based execution
signature = kaizen.create_signature("document: str -> summary: str, key_points: List[str]")
agent = kaizen.create_agent("summarizer", signature=signature)
result = agent.execute(document=doc_content)
print(result.summary, result.key_points)

# Stateful execution
agent.enable_memory()
agent.execute(task="Remember: User prefers bullet points")
result = agent.execute(task="Summarize the quarterly report")  # Uses memory
```

#### 2. Workflow Integration Pattern
```python
# Agent as workflow node
workflow = WorkflowBuilder()
research_node = research_agent.to_workflow_node("research")
analysis_node = analysis_agent.to_workflow_node("analysis")

workflow.add_node_instance(research_node)
workflow.add_node_instance(analysis_node)
workflow.add_connection("research", "analysis")

# Direct workflow generation
agent_workflow = agent.to_workflow()
results, run_id = runtime.execute(agent_workflow.build())

# Mixed workflow with agents and regular nodes
workflow = WorkflowBuilder()
workflow.add_node("DataLoaderNode", "load", {"source": "database"})
workflow.add_node_instance(agent.to_workflow_node("process"))
workflow.add_node("OutputFormatterNode", "format", {"format": "json"})
workflow.add_connections([
    ("load", "process"),
    ("process", "format")
])
```

#### 3. Multi-Agent Coordination Pattern
```python
# Debate workflow
debate = kaizen.create_debate_workflow(
    agents=[optimist_agent, pessimist_agent, moderator_agent],
    topic="Should we adopt AI in healthcare?",
    rounds=3
)
results, run_id = runtime.execute(debate.build())

# Pipeline workflow
pipeline = kaizen.create_pipeline([
    (research_agent, {"focus": "technical"}),
    (analysis_agent, {"depth": "detailed"}),
    (summary_agent, {"format": "executive"})
])
results, run_id = runtime.execute(pipeline.build())

# Consensus workflow
consensus = kaizen.create_consensus_workflow(
    agents=[expert1, expert2, expert3],
    decision_criteria="weighted_vote",
    confidence_threshold=0.85
)
final_decision = runtime.execute(consensus.build())
```

This comprehensive agent execution engine provides direct execution capabilities, seamless workflow integration, and sophisticated multi-agent coordination while maintaining perfect Kailash SDK compatibility.
