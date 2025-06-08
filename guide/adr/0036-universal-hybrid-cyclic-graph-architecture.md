# ADR-0036: Universal Hybrid Cyclic Graph Architecture

## Status
**ACCEPTED & IMPLEMENTED** - Phase 3.2 Complete (Runtime Integration Examples)

## Context

The Kailash Python SDK currently supports only Directed Acyclic Graphs (DAGs) for workflow representation. While this works well for linear data processing pipelines, it creates significant limitations for real-world use cases that require iterative or feedback-driven processes:

### Current Limitations

1. **Agent Coordination**: Multi-agent systems naturally require iterative communication and refinement cycles
2. **ML Training**: Machine learning workflows need training loops with convergence conditions
3. **Data Processing**: ETL processes often require iterative cleaning until quality thresholds are met
4. **Control Systems**: Feedback control loops are fundamental to many automation scenarios
5. **API Integration**: Polling and retry patterns require cyclical execution
6. **Optimization**: Parameter tuning and optimization algorithms are inherently iterative

### Current Workarounds

Users currently must implement iteration logic outside the workflow system:

```python
# Current approach - iteration in Python, not workflow
for iteration in range(max_iterations):
    results = runtime.execute(workflow, parameters)
    if convergence_condition(results):
        break
    # Manually update workflow state
```

This approach:
- Violates the SDK's goal of clean, declarative workflow design
- Forces complex state management outside the workflow engine
- Prevents visualization and monitoring of iterative processes
- Makes workflows non-portable and hard to debug

### Technical Problem

The core issue is in the workflow validation logic (`src/kailash/workflow/graph.py:322-327`):

```python
def get_execution_order(self) -> List[str]:
    try:
        return list(nx.topological_sort(self.graph))
    except nx.NetworkXUnfeasible:
        cycles = list(nx.simple_cycles(self.graph))
        raise WorkflowValidationError(f"Workflow contains cycles: {cycles}")
```

This explicitly prevents any cyclical workflow patterns, forcing all iteration logic outside the workflow system.

## Decision

We will implement a **Universal Hybrid Cyclic Graph Architecture** that supports both traditional DAG workflows and controlled cyclical patterns within a unified framework.

### Core Design Principles

1. **Backward Compatibility**: Existing DAG workflows continue working unchanged
2. **Explicit Cycles**: Cycles must be explicitly marked and intentional
3. **Safety by Design**: Built-in safeguards prevent infinite loops and resource exhaustion
4. **Universal Application**: Works with any node type, not just AI/LLM nodes
5. **Clean API**: Simple, intuitive interface for cycle definition
6. **Composability**: Cycles can be nested and combined with DAG portions

### Architectural Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    Workflow Graph                           │
│                                                             │
│  ┌─────────┐    ┌─────────┐    ┌─────────┐                │
│  │ Node A  │───▶│ Node B  │───▶│ Node C  │                │
│  └─────────┘    └─────────┘    └─────────┘                │
│                       │             │                      │
│                       │         ┌───▼─────┐                │
│                       │         │ Node D  │                │
│                       │         └───┬─────┘                │
│                       │             │                      │
│                   ┌───▼─────┐   ┌───▼─────┐                │
│                   │ Node E  │   │ Node F  │                │
│                   └─────────┘   └─────────┘                │
│                       ▲             │                      │
│                       │             │                      │
│                       └─────────────┘                      │
│                      CYCLE CONNECTION                      │
│                   (max_iterations=10,                      │
│                    convergence_check="quality > 0.9")     │
└─────────────────────────────────────────────────────────────┘
```

## Enhanced Connection API

### Current API
```python
workflow.connect("source", "target")
workflow.connect("source", "target", mapping={"output": "input"})
```

### Enhanced API
```python
# Regular DAG connections (unchanged)
workflow.connect("source", "target")

# Cycle connections (new)
workflow.connect("node_f", "node_e",
                cycle=True,                    # Mark as cyclic
                max_iterations=10,             # Safety limit
                convergence_check="quality > 0.9",  # Stop condition
                cycle_id="optimization_loop")  # Logical grouping
```

### Connection Types

1. **DAG Connections**: Traditional acyclic connections
2. **Cycle Connections**: Explicitly marked cyclical connections with:
   - **Safety Limits**: `max_iterations`, `timeout`, `memory_limit`
   - **Convergence Conditions**: Expression-based or callback-based termination
   - **Cycle Identity**: Logical grouping for nested cycles

## Implementation Architecture

### 1. Enhanced Graph Model

```python
class CyclicConnection(Connection):
    """Extended connection supporting cycle metadata."""
    cycle: bool = False
    max_iterations: Optional[int] = None
    convergence_check: Optional[str] = None
    cycle_id: Optional[str] = None
    timeout: Optional[float] = None
    memory_limit: Optional[int] = None

class CyclicWorkflow(Workflow):
    """Workflow supporting both DAG and cyclic patterns."""

    def connect(self, source: str, target: str,
                cycle: bool = False, **cycle_options):
        """Enhanced connect method supporting cycles."""

    def get_execution_plan(self) -> ExecutionPlan:
        """Generate execution plan handling cycles."""

    def validate_cycles(self) -> None:
        """Validate cycle safety and feasibility."""
```

### 2. Cycle-Aware Execution Engine

```python
class CyclicExecutionEngine:
    """Execution engine supporting cyclic workflows."""

    def execute(self, workflow: CyclicWorkflow) -> ExecutionResult:
        """Execute workflow with cycle support."""
        # 1. Separate DAG and cycle edges
        dag_edges, cycle_edges = self.analyze_graph(workflow)

        # 2. Create execution plan
        plan = self.create_execution_plan(dag_edges, cycle_edges)

        # 3. Execute with cycle awareness
        return self.execute_plan(plan)

    def execute_cycle(self, cycle_group: CycleGroup) -> CycleResult:
        """Execute a single cycle group."""
        state = CycleState()

        for iteration in range(cycle_group.max_iterations):
            # Execute cycle iteration
            results = self.execute_cycle_iteration(cycle_group, state)

            # Check convergence
            if self.check_convergence(results, cycle_group.convergence):
                break

            # Update cycle state
            state.update(results, iteration)

        return CycleResult(state, results)
```

### 3. Convergence Framework

```python
class ConvergenceCondition:
    """Base class for cycle convergence conditions."""

    def evaluate(self, results: Dict[str, Any],
                 cycle_state: CycleState) -> bool:
        """Evaluate if cycle should terminate."""
        raise NotImplementedError

class ExpressionCondition(ConvergenceCondition):
    """Expression-based convergence (e.g., 'quality > 0.9')."""

    def __init__(self, expression: str):
        self.expression = expression

    def evaluate(self, results: Dict[str, Any],
                 cycle_state: CycleState) -> bool:
        # Safe expression evaluation with context
        context = {
            'results': results,
            'iteration': cycle_state.iteration,
            'history': cycle_state.history
        }
        return eval(self.expression, {"__builtins__": {}}, context)

class CallbackCondition(ConvergenceCondition):
    """Callback-based convergence for complex logic."""

    def __init__(self, callback: Callable):
        self.callback = callback

    def evaluate(self, results: Dict[str, Any],
                 cycle_state: CycleState) -> bool:
        return self.callback(results, cycle_state)
```

### 4. Cycle State Management

```python
class CycleState:
    """Manages state across cycle iterations."""

    def __init__(self):
        self.iteration = 0
        self.history = []
        self.metadata = {}
        self.start_time = time.time()

    def update(self, results: Dict[str, Any], iteration: int):
        """Update state with iteration results."""
        self.iteration = iteration
        self.history.append({
            'iteration': iteration,
            'results': results,
            'timestamp': time.time()
        })

    def get_convergence_context(self) -> Dict[str, Any]:
        """Provide context for convergence evaluation."""
        return {
            'iteration': self.iteration,
            'history': self.history,
            'elapsed_time': time.time() - self.start_time,
            'trend': self.calculate_trend()
        }
```

### 5. Safety Framework

```python
class CycleSafetyManager:
    """Manages cycle execution safety."""

    def __init__(self):
        self.active_cycles = {}
        self.resource_monitor = ResourceMonitor()

    def validate_cycle_safety(self, cycle_group: CycleGroup) -> bool:
        """Validate cycle safety before execution."""
        # Check for resource limits
        # Validate convergence conditions
        # Detect potential infinite loops

    def monitor_cycle_execution(self, cycle_id: str,
                               state: CycleState) -> bool:
        """Monitor cycle during execution."""
        # Check resource usage
        # Validate iteration limits
        # Detect deadlocks

    def terminate_unsafe_cycle(self, cycle_id: str, reason: str):
        """Safely terminate problematic cycles."""
```

## Use Case Examples

### 1. Agent Coordination (AI/LLM)
```python
workflow = Workflow("agent-coordination")

# Setup agents and shared memory
workflow.add_node("coordinator", A2ACoordinatorNode())
workflow.add_node("search_agent", A2AAgentNode())
workflow.add_node("synthesis_agent", A2AAgentNode())
workflow.add_node("validator", A2AAgentNode())

# Regular DAG flow
workflow.connect("coordinator", "search_agent")
workflow.connect("search_agent", "synthesis_agent")
workflow.connect("synthesis_agent", "validator")

# Cycle: Iterate until quality threshold met
workflow.connect("validator", "coordinator",
                cycle=True,
                max_iterations=5,
                convergence_check="quality_score > 85",
                cycle_id="agent_refinement")
```

### 2. ML Training Loop
```python
workflow = Workflow("ml-training")

workflow.add_node("data_loader", DataLoaderNode())
workflow.add_node("model_trainer", MLTrainerNode())
workflow.add_node("validator", ModelValidatorNode())
workflow.add_node("optimizer", OptimizerNode())

# Training cycle
workflow.connect("data_loader", "model_trainer")
workflow.connect("model_trainer", "validator")
workflow.connect("validator", "optimizer")
workflow.connect("optimizer", "model_trainer",
                cycle=True,
                max_iterations=1000,
                convergence_check="loss_improvement < 0.001",
                timeout=3600)  # 1 hour limit
```

### 3. Data Quality Processing
```python
workflow = Workflow("data-quality")

workflow.add_node("data_reader", CSVReaderNode())
workflow.add_node("cleaner", DataCleanerNode())
workflow.add_node("quality_checker", DataQualityNode())
workflow.add_node("writer", CSVWriterNode())

# Cleaning cycle
workflow.connect("data_reader", "cleaner")
workflow.connect("cleaner", "quality_checker")
workflow.connect("quality_checker", "cleaner",
                cycle=True,
                max_iterations=10,
                convergence_check="quality_score > 0.95")
workflow.connect("quality_checker", "writer")
```

### 4. API Polling with Retry
```python
workflow = Workflow("api-polling")

workflow.add_node("poller", HTTPClientNode())
workflow.add_node("processor", DataProcessorNode())
workflow.add_node("condition_check", ConditionalNode())

# Polling cycle
workflow.connect("poller", "processor")
workflow.connect("processor", "condition_check")
workflow.connect("condition_check", "poller",
                cycle=True,
                max_iterations=100,
                convergence_check="status == 'complete'",
                cycle_id="polling_loop")
```

### 5. Control System Feedback
```python
workflow = Workflow("pid-controller")

workflow.add_node("sensor", SensorNode())
workflow.add_node("controller", PIDControllerNode())
workflow.add_node("actuator", ActuatorNode())
workflow.add_node("stability_check", StabilityNode())

# Control loop
workflow.connect("sensor", "controller")
workflow.connect("controller", "actuator")
workflow.connect("actuator", "stability_check")
workflow.connect("stability_check", "sensor",
                cycle=True,
                convergence_check="abs(error) < tolerance",
                timeout=60)
```

## Advanced Features

### 1. Nested Cycles
```python
# Outer optimization cycle
workflow.connect("outer_validator", "hyperparameter_tuner",
                cycle=True,
                cycle_id="optimization",
                max_iterations=20)

# Inner training cycle
workflow.connect("training_validator", "model_trainer",
                cycle=True,
                cycle_id="training",
                parent_cycle="optimization",
                max_iterations=1000)
```

### 2. Conditional Cycle Routing
```python
# Different cycle paths based on conditions
workflow.connect("validator", "processor_a",
                cycle=True,
                condition="data_type == 'image'",
                convergence_check="processed_count >= batch_size")

workflow.connect("validator", "processor_b",
                cycle=True,
                condition="data_type == 'text'",
                convergence_check="quality_score > threshold")
```

### 3. Dynamic Convergence
```python
def adaptive_convergence(results, cycle_state):
    """Dynamic convergence based on iteration progress."""
    if cycle_state.iteration < 5:
        return results.get("accuracy", 0) > 0.8
    else:
        return results.get("accuracy", 0) > 0.95

workflow.connect("validator", "trainer",
                cycle=True,
                convergence_check=adaptive_convergence)
```

## Implementation Phases

### Phase 1: Core Infrastructure
1. **Enhanced Connection API**: Extend `connect()` method with cycle parameters
2. **Graph Model Updates**: Support cycle metadata in graph structure
3. **Basic Cycle Execution**: Simple cycle execution without advanced features

### Phase 2: Safety & Convergence
1. **Convergence Framework**: Expression and callback-based convergence
2. **Safety Framework**: Resource limits, timeouts, deadlock detection
3. **Cycle State Management**: State tracking across iterations

### Phase 3: Advanced Features
1. **Nested Cycles**: Support for cycles within cycles
2. **Conditional Cycles**: Dynamic cycle routing
3. **Performance Optimization**: Efficient cycle execution

### Phase 4: Integration & UX
1. **Runtime Integration**: Update all runtime engines
2. **Visualization**: Cycle-aware workflow diagrams
3. **Documentation**: Comprehensive guides and examples

## Risk Mitigation

### 1. Performance Risks
- **Risk**: Long-running cycles consuming resources
- **Mitigation**: Built-in resource monitoring and limits
- **Monitoring**: Real-time cycle performance dashboards

### 2. Infinite Loop Risks
- **Risk**: Poorly designed cycles never converging
- **Mitigation**: Mandatory safety limits (iterations, time, memory)
- **Detection**: Automatic deadlock and infinite loop detection

### 3. Complexity Risks
- **Risk**: Complex cycle designs being hard to debug
- **Mitigation**: Comprehensive logging and cycle state visualization
- **Support**: Rich debugging tools and best practice guides

### 4. Backward Compatibility Risks
- **Risk**: Breaking existing DAG workflows
- **Mitigation**: Cycles are opt-in; existing workflows unchanged
- **Testing**: Comprehensive regression testing

## Success Metrics

### 1. Functional Metrics
- All existing DAG workflows continue working unchanged
- New cycle features work reliably across all node types
- Performance overhead < 5% for DAG workflows

### 2. Developer Experience Metrics
- Cycle API is intuitive and well-documented
- Migration from external iteration to cycles is straightforward
- Debugging and monitoring tools are effective

### 3. Use Case Coverage
- Support for all identified use cases (ML, data processing, control systems, etc.)
- Community adoption of cycle patterns
- Reduction in external iteration code

## Alternative Considered

### Alternative 1: External Iteration Framework
- **Description**: Keep DAG-only workflows, provide iteration wrapper
- **Rejected**: Doesn't solve fundamental expressiveness limitation
- **Problems**: Still requires external state management

### Alternative 2: Special Iteration Nodes
- **Description**: Create specialized nodes that handle iteration internally
- **Rejected**: Limited composability and expressiveness
- **Problems**: Doesn't enable arbitrary cycle patterns

### Alternative 3: Full Cyclic Graph (No Safety)
- **Description**: Allow arbitrary cycles without safety constraints
- **Rejected**: Too dangerous for production use
- **Problems**: Risk of infinite loops and resource exhaustion

## Conclusion

The Universal Hybrid Cyclic Graph Architecture represents a fundamental enhancement to the Kailash SDK that:

1. **Maintains backward compatibility** while adding powerful new capabilities
2. **Enables natural expression** of iterative and feedback-driven processes
3. **Works universally** across all node types and use cases
4. **Provides safety by design** with built-in safeguards and monitoring
5. **Offers clean APIs** that are intuitive and easy to use

This architecture transforms Kailash from a DAG workflow engine into a universal process engine capable of handling any iterative pattern, from simple data processing loops to complex multi-agent coordination systems.

The implementation will be done in careful phases to ensure stability, safety, and backward compatibility while providing immediate value to users who need iterative workflow patterns.

## References

- [ADR-0023: A2A Communication Architecture](./0023-a2a-communication-architecture.md)
- [ADR-0030: Self-Organizing Agent Pool Architecture](./0030-self-organizing-agent-pool-architecture.md)
- [Agent Coordination Patterns Guide](../features/agent_coordination_patterns.md)
- [Workflow A2A MacBook Review Example](../../examples/workflow_examples/workflow_a2a_macbook_review.py)

---
*ADR-0036 | Universal Hybrid Cyclic Graph Architecture*
*Author: Claude Code | Date: 2025-06-07*
*Status: PROPOSED | Priority: High*
