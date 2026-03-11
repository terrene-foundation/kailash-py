# Kaizen Agent Framework - FINAL Proposal

**Status**: FINAL - Ready for Implementation
**Created**: 2025-10-26
**Version**: 3.0 (Incorporating all feedback)

---

## Executive Summary

This document provides the FINAL framework for Kaizen agent architecture with:

1. ✅ **`.run()` as ONLY execution method** (no backward compatibility - Kaizen not operational)
2. ✅ **`register_agent()` instead of `register_agent_type`** (clearer naming)
3. ✅ **Exhaustive edge case testing for pipeline-as-agent** (core functionality)
4. ✅ **A2A protocol for ALL agent-to-agent intelligence** (mandatory)
5. ✅ **MCP protocol as default tool-calling** (mandatory)
6. ✅ **Decision matrix update POST-implementation** (kaizen-specialist.md)

---

## Part 1: Method Standardization (FINAL)

### 1.1 Decision: `.run()` ONLY

**NO BACKWARD COMPATIBILITY** (Kaizen not operational yet)

```python
# react.py - BEFORE
class ReActAgent(BaseAgent):
    def solve_task(self, task: str, **kwargs):  # ❌ REMOVE
        ...

# react.py - AFTER
class ReActAgent(BaseAgent):
    def run(self, task: str, **kwargs):  # ✅ ONLY METHOD
        """Universal execution method for all agents."""
        return super().run(task=task, **kwargs)
```

**All agents standardized**:
- `ReActAgent.run(task="...")`
- `SimpleQAAgent.run(question="...")`
- `VisionAgent.run(image="...", question="...")`
- `AutonomousAgent.run(objective="...")`

**Benefits**:
- ✅ Single execution method across ALL agents
- ✅ Consistent API surface
- ✅ Simpler documentation
- ✅ No confusion about which method to use

---

## Part 2: Agent Registration (FINAL)

### 2.1 Decision: `register_agent()` (Not `register_agent_type`)

**Why**: "type" is confusing. "register_agent" is clear.

```python
# kaizen/agents/registry.py

def register_agent(
    name: str,
    agent_class: Type[BaseAgent],
    description: str = "",
    default_strategy: Type = None,
    preset_config: Dict[str, Any] = None,
    category: str = "general",
    tags: list = None,
):
    """
    Register agent with DUAL registration:
    1. Agent API: For Agent(agent_type="...")
    2. Core SDK: For WorkflowBuilder (auto-calls @register_node)
    """
    # Step 1: Agent API registration
    _AGENT_REGISTRY[name] = AgentRegistration(...)

    # Step 2: AUTO Core SDK registration
    from kailash.nodes.base import register_node_class
    metadata = NodeMetadata(...)
    register_node_class(agent_class, metadata)
```

### 2.2 Usage

```python
# agents/register_builtin.py

from kaizen.agents.registry import register_agent

register_agent(
    name="react",
    agent_class=ReActAgent,
    description="Reasoning + Acting cycles",
    category="specialized",
    tags=["reasoning", "tool-use"],
)  # ← Auto-registers for BOTH Agent API + Core SDK
```

### 2.3 All Pre-Defined Agents Migration

**Remove all `@register_node()` decorators, use `register_agent()` instead**:

```python
# agents/register_builtin.py

def register_builtin_agents():
    # Specialized
    register_agent(name="simple", agent_class=SimpleQAAgent, ...)
    register_agent(name="react", agent_class=ReActAgent, ...)
    register_agent(name="cot", agent_class=ChainOfThoughtAgent, ...)
    register_agent(name="rag", agent_class=RAGResearchAgent, ...)
    register_agent(name="code", agent_class=CodeGenerationAgent, ...)
    register_agent(name="reflection", agent_class=SelfReflectionAgent, ...)

    # Autonomous
    register_agent(name="autonomous", agent_class=AutonomousAgent, ...)
    register_agent(name="claude_code", agent_class=ClaudeCodeAgent, ...)
    register_agent(name="codex", agent_class=CodexAgent, ...)

    # Multi-modal
    register_agent(name="vision", agent_class=VisionAgent, ...)
    register_agent(name="audio", agent_class=TranscriptionAgent, ...)
    register_agent(name="multimodal", agent_class=MultiModalAgent, ...)

    # Enterprise
    register_agent(name="batch", agent_class=BatchProcessingAgent, ...)
    register_agent(name="approval", agent_class=HumanApprovalAgent, ...)
    register_agent(name="resilient", agent_class=ResilientAgent, ...)
```

---

## Part 3: Pipeline-as-Agent Edge Cases (EXHAUSTIVE TESTING)

### 3.1 Critical Importance

**Pipeline-as-agent is CORE FUNCTIONALITY that CANNOT BREAK.**

We need exhaustive edge case testing before production.

### 3.2 Edge Case Categories

**Category 1: Nesting Depth**
- [ ] 1-level nesting (pipeline → agent)
- [ ] 2-level nesting (pipeline → pipeline → agent)
- [ ] 3-level nesting (pipeline → pipeline → pipeline → agent)
- [ ] 5-level nesting (stress test)
- [ ] 10-level nesting (extreme stress test)

**Category 2: Pipeline Type Combinations**
- [ ] Sequential containing Sequential
- [ ] Sequential containing Supervisor-Worker
- [ ] Sequential containing Ensemble
- [ ] Supervisor-Worker with Sequential workers
- [ ] Supervisor-Worker with Ensemble workers
- [ ] Supervisor-Worker with Supervisor-Worker workers (nested coordination)
- [ ] Ensemble containing Sequential agents
- [ ] Ensemble containing Supervisor-Worker agents
- [ ] Blackboard containing Sequential specialists
- [ ] All 9 patterns × all 9 patterns (81 combinations)

**Category 3: Error Handling**
- [ ] Agent failure in nested pipeline (should propagate correctly)
- [ ] Pipeline failure in nested pipeline (should propagate correctly)
- [ ] Timeout in deeply nested pipeline
- [ ] Memory limit exceeded in nested pipeline
- [ ] Circular dependency detection (A contains B, B contains A)
- [ ] Null/None agents in pipeline
- [ ] Empty pipeline converted to agent

**Category 4: State Management**
- [ ] Memory propagation through nested pipelines
- [ ] Session ID continuity through nesting
- [ ] Context passing through multiple nesting levels
- [ ] Shared memory pool access from nested agents
- [ ] Memory isolation between parallel nested pipelines

**Category 5: Performance**
- [ ] Overhead of .to_agent() conversion
- [ ] Memory usage with deep nesting
- [ ] Execution time scaling with nesting depth
- [ ] Concurrent nested pipeline execution
- [ ] Resource cleanup after nested execution

**Category 6: A2A Integration**
- [ ] A2A capability matching with pipeline-as-agent
- [ ] A2A task delegation to nested pipelines
- [ ] A2A agent cards from pipeline agents
- [ ] Nested Supervisor-Worker with A2A (3 levels deep)

**Category 7: MCP Integration**
- [ ] MCP tool calling from nested pipeline agents
- [ ] MCP server exposure from pipeline-as-agent
- [ ] MCP resource access through nesting levels

**Category 8: Special Cases**
- [ ] Pipeline containing itself (should error gracefully)
- [ ] Pipeline with no agents (should error gracefully)
- [ ] Pipeline with single agent (should work)
- [ ] Pipeline switching mid-execution
- [ ] Hot-swap pipeline components

**Category 9: Serialization/Deserialization**
- [ ] Save nested pipeline state
- [ ] Restore nested pipeline state
- [ ] Checkpoint mid-execution in nested pipeline
- [ ] Resume from checkpoint in nested structure

**Category 10: Observability**
- [ ] Tracing through nested pipelines
- [ ] Metrics collection from nested agents
- [ ] Logging context propagation through nesting
- [ ] Audit trail through nested execution

### 3.3 Test Implementation Plan

```python
# tests/core/pipelines/test_pipeline_as_agent_edge_cases.py

class TestPipelineAsAgentEdgeCases:
    """EXHAUSTIVE edge case testing for pipeline-as-agent core functionality."""

    # Category 1: Nesting Depth (5 tests)
    def test_one_level_nesting(self): ...
    def test_two_level_nesting(self): ...
    def test_three_level_nesting(self): ...
    def test_five_level_nesting_stress(self): ...
    def test_ten_level_nesting_extreme(self): ...

    # Category 2: Pipeline Type Combinations (81 tests - parameterized)
    @pytest.mark.parametrize("outer,inner", [
        (Pipeline.sequential, Pipeline.sequential),
        (Pipeline.sequential, Pipeline.supervisor_worker),
        # ... all 81 combinations
    ])
    def test_pipeline_combination(self, outer, inner): ...

    # Category 3: Error Handling (7 tests)
    def test_agent_failure_propagation(self): ...
    def test_pipeline_failure_propagation(self): ...
    def test_timeout_in_nested_pipeline(self): ...
    def test_memory_limit_in_nested_pipeline(self): ...
    def test_circular_dependency_detection(self): ...
    def test_null_agents_handling(self): ...
    def test_empty_pipeline_conversion(self): ...

    # Category 4: State Management (5 tests)
    def test_memory_propagation(self): ...
    def test_session_id_continuity(self): ...
    def test_context_passing_multi_level(self): ...
    def test_shared_memory_pool_access(self): ...
    def test_memory_isolation_parallel(self): ...

    # Category 5: Performance (5 tests)
    def test_to_agent_overhead(self): ...
    def test_memory_usage_deep_nesting(self): ...
    def test_execution_time_scaling(self): ...
    def test_concurrent_nested_execution(self): ...
    def test_resource_cleanup(self): ...

    # Category 6: A2A Integration (4 tests)
    def test_a2a_capability_matching_pipeline_agent(self): ...
    def test_a2a_task_delegation_nested(self): ...
    def test_a2a_agent_cards_from_pipeline(self): ...
    def test_nested_supervisor_worker_a2a(self): ...

    # Category 7: MCP Integration (3 tests)
    def test_mcp_tool_calling_nested(self): ...
    def test_mcp_server_from_pipeline_agent(self): ...
    def test_mcp_resource_access_nesting(self): ...

    # Category 8: Special Cases (5 tests)
    def test_pipeline_contains_itself(self): ...
    def test_pipeline_no_agents(self): ...
    def test_pipeline_single_agent(self): ...
    def test_pipeline_switching_mid_execution(self): ...
    def test_hot_swap_components(self): ...

    # Category 9: Serialization (4 tests)
    def test_save_nested_pipeline_state(self): ...
    def test_restore_nested_pipeline_state(self): ...
    def test_checkpoint_mid_execution_nested(self): ...
    def test_resume_from_checkpoint_nested(self): ...

    # Category 10: Observability (4 tests)
    def test_tracing_through_nesting(self): ...
    def test_metrics_collection_nested(self): ...
    def test_logging_context_propagation(self): ...
    def test_audit_trail_nested_execution(self): ...

# TOTAL: 127+ edge case tests
```

---

## Part 4: MCP and A2A Compliance Audit

### 4.1 Mandatory Protocols

**RULE 1: Default tool-calling = MCP**
**RULE 2: Default agent-to-agent = A2A**

**DO NOT create custom implementations unless:**
- Massive performance gains (>10x faster)
- Massive maintainability gains
- Use-case is extremely specific and well-justified

### 4.2 Current Implementation Status

**✅ COMPLIANT**:
- BaseAgent has MCP integration (`discover_mcp_tools`, `execute_mcp_tool`, etc.)
- BaseAgent has A2A integration (`to_a2a_card()` method)
- Supervisor-Worker uses A2A for capability matching
- Tool calling infrastructure supports MCP

**⚠️ REVIEW NEEDED**:
- `kaizen/tools/registry.py` - Custom ToolRegistry (check if should use MCP instead)
- `kaizen/tools/builtin/*` - 12 builtin tools (check if should be MCP tools)
- Ensemble pattern - No A2A for agent discovery (should add)
- Meta-Controller pattern - No A2A for routing (should add)

### 4.3 Audit Checklist

**Tool-Calling Audit**:
- [ ] Verify all tools use MCP protocol (not custom implementations)
- [ ] Check if ToolRegistry should delegate to MCP
- [ ] Verify builtin tools are MCP-compatible
- [ ] Check ReActAgent tool calling (should use MCP)
- [ ] Check AutonomousAgent tool calling (should use MCP)

**Agent-to-Agent Audit**:
- [ ] Verify Supervisor-Worker uses A2A (✅ already does)
- [ ] Verify Blackboard uses A2A for specialist selection
- [ ] Add A2A to Ensemble for agent discovery
- [ ] Add A2A to Meta-Controller for capability-based routing
- [ ] Verify Consensus pattern doesn't need custom agent selection
- [ ] Verify Debate pattern doesn't need custom agent selection
- [ ] Check all coordination patterns for A2A compliance

**Custom Implementation Review**:
- [ ] Document why ToolRegistry exists (if not using MCP)
- [ ] Document why builtin tools exist (if not using MCP)
- [ ] Justify any custom agent-to-agent logic
- [ ] Performance benchmarks for custom implementations
- [ ] Maintainability analysis for custom implementations

### 4.4 MCP/A2A Integration Architecture

```
Agent Architecture:
┌─────────────────────────────────────────┐
│             Agent (User API)             │
│                                          │
│  ┌────────────────────────────────────┐ │
│  │         BaseAgent (Core)            │ │
│  │                                     │ │
│  │  ┌──────────────┐  ┌─────────────┐ │ │
│  │  │ MCP Client   │  │ A2A Card    │ │ │
│  │  │ (Tool Call)  │  │ (Agent-2-A) │ │ │
│  │  └──────────────┘  └─────────────┘ │ │
│  └────────────────────────────────────┘ │
└─────────────────────────────────────────┘
         ↓                        ↓
    ┌─────────┐             ┌──────────┐
    │   MCP   │             │   A2A    │
    │Protocol │             │ Protocol │
    └─────────┘             └──────────┘
         ↓                        ↓
  ┌──────────────┐        ┌─────────────────┐
  │ MCP Server   │        │ A2A Coordinator │
  │ (Kailash SDK)│        │ (Kailash SDK)   │
  └──────────────┘        └─────────────────┘
```

**Key Principle**: BaseAgent handles MCP and A2A. Specialized agents inherit for free.

---

## Part 5: Pipeline Pattern Decision Matrix (FINAL)

### 5.1 When to Use Which Pattern

| Pattern | Use When | When NOT to Use | A2A Mandatory? |
|---------|----------|-----------------|----------------|
| **Sequential** | Linear dependencies (A→B→C), predictable workflow | Need parallelism, dynamic routing, or iteration | No |
| **Supervisor-Worker** | Complex tasks needing intelligent delegation, unknown specialist requirements | Simple tasks, deterministic workflows | **YES** - For worker selection |
| **Meta-Controller** | Known request categories, deterministic routing | Tasks requiring multiple specialists, dynamic needs | **YES** - For capability-based routing |
| **Ensemble** | High-stakes decisions, multiple perspectives needed | Simple tasks, time-sensitive operations (slow) | **YES** - For agent discovery |
| **Blackboard** | Emergent solutions, opportunistic collaboration | Known workflows, deterministic execution | **YES** - For dynamic specialist selection |
| **Consensus** | Group agreement required, compliance/governance | Individual decisions, time-sensitive tasks | Optional |
| **Debate** | Adversarial analysis (pros/cons), challenge assumptions | Consensus-building, routine tasks | No |
| **Handoff** | Sequential specialists with clear handoff points | Tasks requiring iteration back to previous steps | No |
| **Parallel** | Independent concurrent tasks, order doesn't matter | Tasks with dependencies, sequential results needed | No |

### 5.2 A2A Integration Points

**PRIMARY (Mandatory A2A)**:
1. **Supervisor-Worker**: Worker selection based on task-capability matching
2. **Blackboard**: Dynamic specialist selection based on blackboard state
3. **Meta-Controller**: Intelligent routing based on capability matching
4. **Ensemble**: Agent discovery and capability assessment

**Example - Supervisor-Worker with A2A**:
```python
# supervisor_worker.py (CURRENT - ALREADY USING A2A!)

class SupervisorAgent(BaseAgent):
    def select_worker_for_task(
        self,
        task: Dict[str, Any],
        available_workers: List[BaseAgent],
    ) -> BaseAgent:
        """
        Select best worker using A2A capability matching.
        NO hardcoded if/else logic!
        """
        # Get A2A cards from workers
        worker_cards = [w.to_a2a_card() for w in available_workers]

        # A2A semantic matching
        from kailash.nodes.ai.a2a import A2ACoordinatorNode
        coordinator = A2ACoordinatorNode()

        best_worker = coordinator.match_task_to_agent(
            task_description=task["description"],
            agent_cards=worker_cards,
        )

        return best_worker  # Selected via A2A, not hardcoded routing!
```

**Example - Meta-Controller with A2A (NEW)**:
```python
class MetaControllerPipeline:
    def route(self, request: str) -> BaseAgent:
        """Route request to best specialist using A2A."""
        # Get A2A cards from all specialists
        specialist_cards = [s.to_a2a_card() for s in self.specialists]

        # A2A capability-based routing
        from kailash.nodes.ai.a2a import A2ACoordinatorNode
        coordinator = A2ACoordinatorNode()

        best_specialist = coordinator.match_task_to_agent(
            task_description=request,
            agent_cards=specialist_cards,
        )

        return best_specialist  # NO if/else routing logic!
```

---

## Part 6: Implementation Roadmap (FINAL)

### Phase 1: Standardization & Audit (Week 1)

**1.1 Method Standardization**
- [ ] Update ALL agents to use ONLY `.run()` method
- [ ] Remove all domain-specific methods (`.solve_task()`, `.ask()`, `.analyze()`)
- [ ] Update all examples and tests
- [ ] Update documentation

**1.2 Registration System**
- [ ] Rename `register_agent_type` → `register_agent`
- [ ] Implement dual registration (Agent API + Core SDK)
- [ ] Remove all `@register_node()` decorators from agent classes
- [ ] Migrate all agents to `register_agent()` in `register_builtin.py`
- [ ] Test both Agent API and Core SDK access

**1.3 MCP/A2A Compliance Audit**
- [ ] Audit ToolRegistry vs MCP (document why custom if needed)
- [ ] Audit builtin tools vs MCP (migrate if needed)
- [ ] Verify all agent-to-agent uses A2A
- [ ] Add A2A to Ensemble pattern
- [ ] Add A2A to Meta-Controller pattern
- [ ] Document any custom implementations with justification

### Phase 2: Reorganization (Week 2)

**2.1 Directory Restructure**
- [ ] Move `agents/coordination/` → `orchestration/patterns/`
- [ ] Move `coordination/` → `orchestration/core/`
- [ ] Keep `agents/specialized/`, `agents/autonomous/`, `agents/multi_modal/`
- [ ] Update all imports
- [ ] Test backward compatibility

**2.2 Pipeline Infrastructure**
- [ ] Create `orchestration/pipeline.py` base class
- [ ] Implement `.to_agent()` method
- [ ] Create PipelineAgent wrapper class

### Phase 3: Composable Pipelines (Week 3)

**3.1 Pipeline Implementations**
- [ ] Implement `Pipeline.sequential()` with composability
- [ ] Implement `Pipeline.supervisor_worker()` with A2A
- [ ] Implement `Pipeline.ensemble()` with A2A
- [ ] Implement `Pipeline.router()` (Meta-Controller) with A2A
- [ ] Implement `Pipeline.blackboard()` with A2A
- [ ] Implement `Pipeline.consensus()`
- [ ] Implement `Pipeline.debate()`
- [ ] Implement `Pipeline.handoff()`
- [ ] Implement `Pipeline.parallel()`

**3.2 EXHAUSTIVE Edge Case Testing**
- [ ] Create `test_pipeline_as_agent_edge_cases.py`
- [ ] Implement all 127+ edge case tests (see Part 3.3)
- [ ] Nesting depth tests (1, 2, 3, 5, 10 levels)
- [ ] Pipeline combinations (81 tests)
- [ ] Error handling (7 tests)
- [ ] State management (5 tests)
- [ ] Performance (5 tests)
- [ ] A2A integration (4 tests)
- [ ] MCP integration (3 tests)
- [ ] Special cases (5 tests)
- [ ] Serialization (4 tests)
- [ ] Observability (4 tests)
- [ ] **ALL tests must pass before production**

### Phase 4: Missing Patterns (Week 4)

**4.1 Single-Agent Patterns**
- [ ] Implement Planning agent
- [ ] Implement PEV (Planner-Executor-Verifier)
- [ ] Implement Tree-of-Thoughts
- [ ] Enhance Self-Reflection with loops

**4.2 Multi-Agent Patterns**
- [ ] Complete Blackboard with full A2A
- [ ] Complete Meta-Controller with full A2A
- [ ] Complete Ensemble with full A2A

**4.3 Documentation**
- [ ] Write nested pipeline examples
- [ ] Write decision matrix (POST-implementation)
- [ ] Update `kaizen-specialist.md` with decision matrix
- [ ] Write MCP/A2A integration guide

---

## Part 7: Key Decisions for Approval

Please confirm:

1. **✅ `.run()` ONLY**: Remove all domain-specific methods (no backward compatibility)?

2. **✅ `register_agent()`**: Rename from `register_agent_type`, migrate all pre-defined agents?

3. **✅ Exhaustive Testing**: 127+ edge case tests for pipeline-as-agent before production?

4. **✅ A2A Mandatory**: ALL agent-to-agent intelligence must use A2A protocol?

5. **✅ MCP Mandatory**: All tool-calling should use MCP (audit custom implementations)?

6. **✅ Decision Matrix POST-Implementation**: Update `kaizen-specialist.md` after learning from implementation?

---

## Appendix A: Code Examples

### A.1 Standardized Execution

```python
# ALL AGENTS - AFTER standardization

class ReActAgent(BaseAgent):
    def run(self, task: str, **kwargs) -> Dict[str, Any]:
        """Universal execution method."""
        return super().run(task=task, **kwargs)

class SimpleQAAgent(BaseAgent):
    def run(self, question: str, **kwargs) -> Dict[str, Any]:
        """Universal execution method."""
        return super().run(question=question, **kwargs)

class VisionAgent(BaseAgent):
    def run(self, image: str, question: str, **kwargs) -> Dict[str, Any]:
        """Universal execution method."""
        return super().run(image=image, question=question, **kwargs)

# Usage
agent.run(task="...")        # ReActAgent
agent.run(question="...")    # SimpleQAAgent
agent.run(image="...", question="...")  # VisionAgent
```

### A.2 Agent Registration

```python
# agents/registry.py

def register_agent(
    name: str,
    agent_class: Type[BaseAgent],
    description: str = "",
    category: str = "general",
    tags: list = None,
):
    """Register agent with dual registration (Agent API + Core SDK)."""
    # Agent API
    _AGENT_REGISTRY[name] = AgentRegistration(...)

    # Core SDK (automatic)
    from kailash.nodes.base import register_node_class
    register_node_class(agent_class, NodeMetadata(...))
```

### A.3 Nested Pipeline with A2A

```python
# Complex nested pipeline with A2A integration

from kaizen import Agent
from kaizen.orchestration import Pipeline

# Step 1: Create specialist workers (each is a sequential pipeline)
data_pipeline = Pipeline.sequential([
    Agent(model="gpt-4", agent_type="data_extractor"),
    Agent(model="gpt-4", agent_type="data_validator"),
    Agent(model="gpt-4", agent_type="data_analyzer"),
])

code_pipeline = Pipeline.sequential([
    Agent(model="gpt-4", agent_type="code_analyzer"),
    Agent(model="gpt-4", agent_type="code_optimizer"),
])

# Step 2: Supervisor-Worker with pipeline workers (A2A matching)
supervisor = Agent(model="gpt-4", agent_type="coordinator")

analysis = Pipeline.supervisor_worker(
    supervisor=supervisor,
    workers=[
        data_pipeline.to_agent(),  # Pipeline as agent!
        code_pipeline.to_agent(),
    ],
    selection_mode="semantic",  # A2A capability matching
)

# Step 3: Ensemble decision (A2A agent discovery)
decision = Pipeline.ensemble(
    agents=[
        Agent(model="gpt-4", agent_type="optimistic"),
        Agent(model="gpt-4", agent_type="pessimistic"),
        Agent(model="gpt-4", agent_type="neutral"),
    ],
    synthesizer=Agent(model="gpt-4", agent_type="decision_maker"),
    discovery_mode="a2a",  # A2A for agent discovery
)

# Step 4: Final sequential pipeline
final = Pipeline.sequential([
    Agent(model="gpt-4", agent_type="requirements"),
    analysis.to_agent(),   # Nested Supervisor-Worker
    decision.to_agent(),   # Nested Ensemble
    Agent(model="gpt-4", agent_type="report"),
])

# Execute entire nested structure
result = final.run(task="Analyze system and recommend architecture")
```

---

**END OF FINAL PROPOSAL**
