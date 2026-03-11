# ADR-018: Pipeline Pattern Architecture for Phase 3

**Status**: PROPOSED

**Date**: 2025-10-27

**Deciders**: Kaizen Framework Team

**Related TODOs**: TODO-174 (Phase 3 - Composable Pipelines with A2A Integration)

---

## Context

Phase 3 of the Unified Agent Framework requires implementing 4 new pipeline patterns (Meta-Controller, Ensemble, Blackboard, Parallel) with A2A integration for semantic agent matching. We need architectural decisions for:

1. **Pattern Implementation Strategy**: How to implement 9 total patterns consistently
2. **A2A Integration Approach**: How to integrate capability-based agent selection
3. **Factory Method Location**: Where to place user-facing API
4. **Error Handling Strategy**: How to handle failures gracefully
5. **Testing Strategy**: How to organize 127+ edge case tests

### Requirements

**Functional**:
- 9 pipeline patterns (5 existing + 4 new)
- A2A integration in 4 patterns (Supervisor-Worker, Router, Ensemble, Blackboard)
- 127+ edge case tests covering all scenarios
- Zero breaking changes to existing code

**Non-Functional**:
- <100ms overhead per pipeline operation
- <50ms A2A matching time
- <512MB memory per pipeline
- 100% backward compatibility

### Constraints

- Must reuse existing pattern implementations (5 patterns already exist)
- Must integrate with existing A2A infrastructure (`kaizen.nodes.ai.a2a`)
- Must maintain 507+ existing tests passing
- Must support 10+ levels of pipeline nesting
- Must work with both sync and async agents

---

## Decision

We will implement Phase 3 using the following architecture:

### 1. Pattern Implementation Strategy: **Hybrid Class + Factory Approach**

**Implementation**:
- Patterns implemented as **classes inheriting from `Pipeline`**
- User-facing API via **static factory methods on `Pipeline` class**
- Existing patterns (5) wrapped with factory methods, keep internal classes unchanged

**Example**:
```python
# Pattern implementation (internal class)
class MetaControllerPipeline(Pipeline):
    """Capability-based routing with A2A."""

    def __init__(self, agents, routing_strategy="semantic"):
        self.agents = agents
        self.routing_strategy = routing_strategy

    def run(self, **inputs):
        if self.routing_strategy == "semantic":
            best_agent = self._select_via_a2a(inputs)
        else:
            best_agent = self.agents[0]
        return best_agent.run(**inputs)

# Factory method (user-facing API)
class Pipeline:
    @staticmethod
    def router(agents, routing_strategy="semantic"):
        """Create meta-controller for intelligent routing.

        Args:
            agents: List of agents to route between
            routing_strategy: "semantic" (A2A), "round-robin", or "random"

        Returns:
            MetaControllerPipeline instance
        """
        return MetaControllerPipeline(agents, routing_strategy)
```

**Usage**:
```python
from kaizen.orchestration.pipeline import Pipeline

# User-friendly API
pipeline = Pipeline.router([agent1, agent2, agent3], routing_strategy="semantic")
result = pipeline.run(task="Analyze sales data")
```

### 2. A2A Integration Approach: **Per-Pattern Logic with Shared Mixin**

**Implementation**:
- Shared `A2APatternMixin` class with reusable capability matching
- Each pattern customizes A2A logic for its specific needs
- Graceful fallback when A2A unavailable

**Shared Mixin**:
```python
class A2APatternMixin:
    """Reusable A2A capability matching for patterns."""

    def select_best_agent(self, task, agents, return_score=False):
        """Select agent with best capability match for task."""
        if not A2A_AVAILABLE:
            # Fallback: return first agent
            return agents[0] if not return_score else {"agent": agents[0], "score": 0.5}

        # Generate A2A cards for all agents
        best_agent, best_score = None, 0.0
        for agent in agents:
            card = agent.to_a2a_card()
            score = max(cap.matches_requirement(task)
                       for cap in card.primary_capabilities)
            if score > best_score:
                best_agent, best_score = agent, score

        if return_score:
            return {"agent": best_agent, "score": best_score}
        return best_agent

    def select_top_k_agents(self, task, agents, k=3):
        """Select top-k agents with best capability matches."""
        if not A2A_AVAILABLE:
            return agents[:k]

        # Score all agents
        scored = []
        for agent in agents:
            card = agent.to_a2a_card()
            score = max(cap.matches_requirement(task)
                       for cap in card.primary_capabilities)
            scored.append((agent, score))

        # Return top-k
        scored.sort(key=lambda x: x[1], reverse=True)
        return [agent for agent, score in scored[:k]]
```

**Pattern Usage**:
```python
class MetaControllerPipeline(Pipeline, A2APatternMixin):
    """Router with A2A capability matching."""

    def run(self, **inputs):
        task = inputs.get("task", str(inputs))
        best_agent = self.select_best_agent(task, self.agents)
        return best_agent.run(**inputs)

class EnsemblePipeline(Pipeline, A2APatternMixin):
    """Ensemble with A2A agent discovery."""

    def run(self, **inputs):
        task = inputs.get("task", str(inputs))
        selected = self.select_top_k_agents(task, self.agents, k=3)
        results = [agent.run(**inputs) for agent in selected]
        return self.synthesizer.run(perspectives=results, task=inputs)
```

### 3. Factory Method Location: **Static Methods on `Pipeline` Class**

**Implementation**:
All 9 factory methods added as `@staticmethod` on `Pipeline` class in `src/kaizen/orchestration/pipeline.py`:

```python
class Pipeline:
    """Base class for composable pipelines."""

    # Existing methods
    def run(self, **inputs): ...
    def to_agent(self, name=None, description=None): ...

    # NEW: Factory methods for all 9 patterns

    @staticmethod
    def sequential(agents):
        """Create sequential pipeline (A → B → C)."""
        return SequentialPipeline(agents)

    @staticmethod
    def supervisor_worker(supervisor, workers, selection_mode="semantic"):
        """Create supervisor-worker with A2A semantic matching."""
        from kaizen.orchestration.patterns import create_supervisor_worker_pattern
        pattern = create_supervisor_worker_pattern(
            num_workers=len(workers),
            shared_memory=SharedMemoryPool()
        )
        pattern.supervisor = supervisor
        pattern.workers = workers
        return pattern

    @staticmethod
    def router(agents, routing_strategy="semantic"):
        """Create meta-controller for intelligent routing."""
        return MetaControllerPipeline(agents, routing_strategy)

    @staticmethod
    def ensemble(agents, synthesizer, discovery_mode="a2a", top_k=3):
        """Create ensemble with multiple perspectives."""
        return EnsemblePipeline(agents, synthesizer, discovery_mode, top_k)

    @staticmethod
    def blackboard(specialists, controller, selection_mode="semantic", max_iterations=10):
        """Create blackboard for dynamic collaboration."""
        return BlackboardPipeline(specialists, controller, selection_mode, max_iterations)

    @staticmethod
    def consensus(agents, threshold=0.5, voting_strategy="majority"):
        """Create consensus pattern with voting."""
        from kaizen.orchestration.patterns.consensus import create_consensus_pattern
        return create_consensus_pattern(agents=agents, threshold=threshold,
                                        voting_strategy=voting_strategy)

    @staticmethod
    def debate(agents, rounds=3, judge=None):
        """Create debate pattern for adversarial analysis."""
        from kaizen.orchestration.patterns.debate import create_debate_pattern
        return create_debate_pattern(agents=agents, num_rounds=rounds, judge=judge)

    @staticmethod
    def handoff(agents, handoff_condition=None):
        """Create handoff pattern for sequential specialists."""
        from kaizen.orchestration.patterns.handoff import create_handoff_pattern
        return create_handoff_pattern(agents=agents, handoff_condition=handoff_condition)

    @staticmethod
    def parallel(agents, aggregator=None, max_workers=10):
        """Create parallel execution pipeline."""
        return ParallelPipeline(agents, aggregator, max_workers)
```

**Benefits**:
- Single import: `from kaizen.orchestration.pipeline import Pipeline`
- IDE autocomplete shows all 9 patterns
- Self-documenting API (docstrings on factory methods)
- Consistent with existing `SequentialPipeline` pattern

### 4. Error Handling Strategy: **Graceful Degradation with Configurable Fail-Fast**

**Implementation**:
- Default: **Graceful degradation** (production-friendly)
- Optional: **Fail-fast mode** (debugging-friendly)
- Errors reported in results, not raised

**Base Pipeline Class**:
```python
class Pipeline:
    def __init__(self, error_handling="graceful"):
        """Initialize pipeline with error handling mode.

        Args:
            error_handling: "graceful" (default) or "fail-fast"
        """
        self.error_handling = error_handling

    def _handle_agent_error(self, agent, error):
        """Handle agent execution error based on configured mode."""
        if self.error_handling == "fail-fast":
            raise error
        else:
            # Graceful: return error info, continue execution
            return {
                "error": str(error),
                "agent_id": agent.agent_id,
                "status": "failed",
                "traceback": traceback.format_exc()
            }
```

**Pattern Usage**:
```python
class MetaControllerPipeline(Pipeline):
    def run(self, **inputs):
        try:
            best_agent = self.select_best_agent(inputs["task"], self.agents)
            return best_agent.run(**inputs)
        except Exception as e:
            return self._handle_agent_error(best_agent, e)
```

**User Control**:
```python
# Production: graceful degradation (default)
pipeline = Pipeline.router(agents)
result = pipeline.run(task="...")
if "error" in result:
    print(f"Agent failed: {result['error']}")

# Development: fail-fast for debugging
pipeline = Pipeline.router(agents)
pipeline.error_handling = "fail-fast"
result = pipeline.run(task="...")  # Raises exception on error
```

### 5. Testing Strategy: **Category-Based Organization with Parametrization**

**Implementation**:
- 10 test categories in single file: `tests/core/pipelines/test_pipeline_as_agent_edge_cases.py`
- Parametrized tests for 81 pattern combinations
- Clear category structure for maintainability

**Test File Structure**:
```python
# tests/core/pipelines/test_pipeline_as_agent_edge_cases.py

import itertools
import pytest
from kaizen.orchestration.pipeline import Pipeline

# Test fixtures
@pytest.fixture
def mock_agents():
    """Create mock agents for testing."""
    pass

ALL_PATTERNS = [
    "sequential", "supervisor_worker", "router", "ensemble",
    "blackboard", "consensus", "debate", "handoff", "parallel"
]

# Category 1: Nesting Depth (5 tests)
class TestNestingDepth:
    def test_nesting_1_level(self, mock_agents):
        """Pipeline contains agents, no nesting."""
        pass

    def test_nesting_2_levels(self, mock_agents):
        """Pipeline contains pipeline."""
        pass

    def test_nesting_3_levels(self, mock_agents):
        """3-level nesting."""
        pass

    def test_nesting_5_levels(self, mock_agents):
        """5-level nesting (stress)."""
        pass

    def test_nesting_10_levels(self, mock_agents):
        """10-level nesting (max depth)."""
        pass

# Category 2: Pipeline Combinations (81 tests, parametrized)
class TestPipelineCombinations:
    @pytest.mark.parametrize("pattern1,pattern2",
        itertools.product(ALL_PATTERNS, ALL_PATTERNS))
    def test_pattern_combination(self, pattern1, pattern2, mock_agents):
        """Test all 9x9 = 81 pattern combinations."""
        # Create outer pipeline of type pattern1
        outer = self._create_pattern(pattern1, mock_agents)
        # Create inner pipeline of type pattern2
        inner = self._create_pattern(pattern2, mock_agents)
        # Compose and execute
        result = outer.run(data="test")
        assert result is not None

# Category 3: Error Handling (7 tests)
class TestErrorHandling:
    def test_agent_failure_graceful(self): pass
    def test_agent_failure_fail_fast(self): pass
    def test_timeout_handling(self): pass
    def test_cascading_failures(self): pass
    def test_partial_results(self): pass
    def test_retry_logic(self): pass
    def test_circuit_breaker(self): pass

# Category 4: State Management (5 tests)
class TestStateManagement:
    def test_stateful_pipelines(self): pass
    def test_shared_memory_isolation(self): pass
    def test_concurrent_executions(self): pass
    def test_state_reset(self): pass
    def test_persistent_state(self): pass

# Category 5: Performance (5 tests)
class TestPerformance:
    def test_large_agent_counts(self): pass  # 100+ agents
    def test_deep_nesting_performance(self): pass  # 10 levels
    def test_parallel_scalability(self): pass
    def test_memory_usage(self): pass
    def test_a2a_matching_speed(self): pass  # <50ms

# Category 6: A2A Integration (4 tests)
class TestA2AIntegration:
    def test_a2a_unavailable_fallback(self): pass
    def test_a2a_matching_accuracy(self): pass
    def test_a2a_zero_score(self): pass
    def test_a2a_conflicting_capabilities(self): pass

# Category 7: MCP Integration (3 tests)
class TestMCPIntegration:
    def test_pipeline_as_mcp_tool(self): pass
    def test_mcp_agents_in_pipeline(self): pass
    def test_mcp_resource_access(self): pass

# Category 8: Special Cases (5 tests)
class TestSpecialCases:
    def test_empty_agent_list(self): pass
    def test_single_agent_pipeline(self): pass
    def test_circular_dependencies(self): pass
    def test_duplicate_agent_ids(self): pass
    def test_none_inputs_outputs(self): pass

# Category 9: Serialization (4 tests)
class TestSerialization:
    def test_pipeline_to_json(self): pass
    def test_pipeline_from_json(self): pass
    def test_nested_pipeline_serialization(self): pass
    def test_a2a_card_serialization(self): pass

# Category 10: Observability (4 tests)
class TestObservability:
    def test_execution_tracing(self): pass
    def test_metrics_collection(self): pass
    def test_logging_output(self): pass
    def test_error_reporting(self): pass

# Total: 5 + 81 + 7 + 5 + 5 + 4 + 3 + 5 + 4 + 4 = 127 tests
```

**Benefits**:
- **Organized**: Clear categories for 127+ tests
- **Maintainable**: Easy to add new edge cases
- **Efficient**: 81 combination tests from single parametrized test
- **Comprehensive**: All edge cases documented in test names

---

## Consequences

### Positive

1. **Clear API**: `Pipeline.pattern_name()` is intuitive and self-documenting
2. **Composable**: All patterns return `Pipeline`, can nest infinitely via `.to_agent()`
3. **Testable**: 127+ edge cases ensure robustness and prevent regressions
4. **A2A Ready**: 4 patterns use semantic capability matching out of the box
5. **Backward Compatible**: Existing code works unchanged (507+ tests pass)
6. **Flexible Error Handling**: Graceful degradation for production, fail-fast for development
7. **Reusable A2A Logic**: Shared mixin prevents duplication across patterns
8. **Single Import**: `Pipeline` class provides all patterns via one import
9. **IDE Support**: Autocomplete shows all 9 patterns with docstrings
10. **Maintainable Tests**: Category-based organization with parametrization

### Negative

1. **Pipeline Class Size**: 9 factory methods add ~200 lines to `Pipeline` class
2. **Complexity**: A2A mixin adds abstraction layer, learning curve for contributors
3. **Test Maintenance**: 127+ tests require ongoing maintenance and updates
4. **Performance**: A2A matching adds ~50ms overhead per operation
5. **Backward Compatibility Burden**: Must maintain existing factory functions (`create_*_pattern()`)

### Mitigation

1. **Class Size**: Use `@staticmethod` to keep methods lightweight, delegate to pattern classes
2. **Complexity**: Comprehensive documentation, examples, and docstrings for A2A usage
3. **Test Maintenance**: Parametrized tests (81 from 1 test function) reduce duplication
4. **Performance**: Cache A2A cards per agent, optimize matching algorithm, target <50ms
5. **Backward Compatibility**: Keep existing factory functions, mark as deprecated in docs

### Risks

**Critical Risks**:
- A2A integration failures (HIGH probability, HIGH impact)
  - Mitigation: Comprehensive A2A tests, graceful fallback, reuse existing patterns
- Backward compatibility breaks (MEDIUM probability, HIGH impact)
  - Mitigation: Run full test suite after each change, explicit backward compat tests

**Medium Risks**:
- Performance degradation (MEDIUM probability, MEDIUM impact)
  - Mitigation: Cache A2A cards, benchmark before/after, performance tests
- Nested pipeline complexity (MEDIUM probability, MEDIUM impact)
  - Mitigation: Observability tests, clear error messages, limit max nesting depth

---

## Alternatives Considered

### Alternative 1: Separate Factory Module

**Approach**: Create `orchestration/factories.py` with all factory functions:

```python
# factories.py
def create_sequential_pipeline(agents): pass
def create_supervisor_worker_pipeline(supervisor, workers): pass
def create_router_pipeline(agents): pass
# ... 6 more
```

**Pros**:
- Keeps `Pipeline` class small and focused
- Separation of concerns (class vs factories)
- Easier to test factories independently

**Cons**:
- Two imports needed: `from kaizen.orchestration.pipeline import Pipeline` AND `from kaizen.orchestration.factories import create_*`
- Less discoverable (users must know about factories module)
- Inconsistent with existing `SequentialPipeline` pattern
- Worse ergonomics (longer import path)

**Rejected Reason**: Ergonomics and discoverability more important than class size. Single import point (`Pipeline`) provides better developer experience.

### Alternative 2: Centralized A2A Coordinator

**Approach**: Create single `A2ACoordinator` class used by all patterns:

```python
class A2ACoordinator:
    def select_agent(self, task, agents, mode): pass
    def route_task(self, task, agents): pass
    def discover_agents(self, criteria): pass
    def select_specialist(self, blackboard_state, specialists): pass
```

**Pros**:
- Single source of truth for all A2A logic
- Consistent behavior across patterns
- Easier to update A2A algorithm globally

**Cons**:
- Tight coupling between patterns and coordinator
- Patterns can't customize A2A behavior for their needs
- One-size-fits-all approach may not fit all patterns
- Harder to test pattern-specific A2A logic

**Rejected Reason**: Per-pattern flexibility more important. Different patterns need different A2A strategies (e.g., Router selects 1 agent, Ensemble selects top-k agents, Blackboard selects iteratively).

### Alternative 3: Function-Based Patterns

**Approach**: Implement patterns as pure functions, not classes:

```python
def router_pipeline(agents, routing_strategy):
    """Create router pipeline (function-based)."""
    def run(**inputs):
        # Routing logic here
        pass
    return run

# Usage
pipeline = router_pipeline([agent1, agent2], "semantic")
result = pipeline(data="test")  # Call function directly
```

**Pros**:
- Simpler, more functional style
- Less boilerplate (no class definition)
- Easier to reason about (pure functions)

**Cons**:
- No state management (can't store config)
- No inheritance (can't share behavior via mixins)
- Harder to extend (can't subclass)
- No `.to_agent()` method (breaks composability)
- Inconsistent with existing OOP patterns

**Rejected Reason**: OOP benefits (inheritance, composition, state management) more valuable for complex patterns. `.to_agent()` composability is critical requirement.

### Alternative 4: Fail-Fast by Default

**Approach**: Raise exceptions on agent failure by default, opt-in graceful degradation:

```python
class Pipeline:
    def __init__(self, error_handling="fail-fast"):  # Default fail-fast
        self.error_handling = error_handling
```

**Pros**:
- Catches bugs early in development
- Explicit error handling (no silent failures)
- Consistent with Python's default behavior

**Cons**:
- Production-unfriendly (single agent failure breaks entire pipeline)
- Cascading failures in multi-agent patterns
- Users must explicitly opt-in to graceful degradation
- Harder to build resilient systems

**Rejected Reason**: Production-friendliness more important. Default graceful degradation prevents cascading failures, while fail-fast mode available for debugging.

---

## Implementation Plan

### Phase 3.1: Core Patterns (Days 1-2, 16 hours)

**Day 1 Morning (4 hours)**: Meta-Controller (Router) with A2A
- Create `MetaControllerPipeline` class
- Implement A2A capability-based routing
- Add `Pipeline.router()` factory method
- Write 10+ unit tests

**Day 1 Afternoon (4 hours)**: Parallel Pattern
- Create `ParallelPipeline` class
- Implement async concurrent execution
- Add `Pipeline.parallel()` factory method
- Write 10+ unit tests

**Day 2 Morning (4 hours)**: Ensemble Pattern with A2A
- Create `EnsemblePipeline` class
- Implement A2A agent discovery (top-k selection)
- Add `Pipeline.ensemble()` factory method
- Write 10+ unit tests

**Day 2 Afternoon (4 hours)**: Blackboard Pattern with A2A
- Create `BlackboardPipeline` class
- Implement iterative A2A specialist selection
- Add `Pipeline.blackboard()` factory method
- Write 10+ unit tests

**Deliverables**: 4 new patterns, 40+ unit tests

### Phase 3.2: Integration & Wrappers (Day 3, 8 hours)

**Day 3 Morning (4 hours)**: Factory Method Wrappers
- Add `Pipeline.sequential()` (wrap `SequentialPipeline`)
- Add `Pipeline.supervisor_worker()` (wrap `create_supervisor_worker_pattern()`)
- Add `Pipeline.consensus()` (wrap `create_consensus_pattern()`)
- Add `Pipeline.debate()` (wrap `create_debate_pattern()`)
- Add `Pipeline.handoff()` (wrap `create_handoff_pattern()`)

**Day 3 Afternoon (4 hours)**: Integration Testing
- Create `tests/integration/test_pipeline_integration.py`
- Test each pattern with real agents (Tier 2)
- Test A2A integration with real LLM calls
- Test pipeline composition (nested pipelines)
- Verify backward compatibility (507+ tests pass)

**Deliverables**: 9 factory methods complete, integration tests passing

### Phase 3.3: EXHAUSTIVE Testing (Days 4-5, 16 hours)

**Day 4 Morning (4 hours)**: Test Infrastructure
- Create `tests/core/pipelines/test_pipeline_as_agent_edge_cases.py`
- Set up test fixtures and utilities
- Implement Category 1: Nesting Depth (5 tests)

**Day 4 Afternoon (4 hours)**: Combination Tests
- Implement Category 2: Pipeline Combinations (81 tests, parametrized)

**Day 5 Morning (4 hours)**: Error & State Tests
- Implement Category 3: Error Handling (7 tests)
- Implement Category 4: State Management (5 tests)

**Day 5 Afternoon (4 hours)**: Remaining Categories
- Implement Category 5: Performance (5 tests)
- Implement Category 6: A2A Integration (4 tests)
- Implement Category 7: MCP Integration (3 tests)
- Implement Category 8: Special Cases (5 tests)
- Implement Category 9: Serialization (4 tests)
- Implement Category 10: Observability (4 tests)

**Deliverables**: 127+ edge case tests, all passing

---

## Success Metrics

### Functional Metrics
- [ ] 9 pipeline patterns implemented and working
- [ ] A2A integration in 4 patterns (Supervisor-Worker, Router, Ensemble, Blackboard)
- [ ] 127+ edge case tests passing (127/127)
- [ ] 507+ existing tests passing (507/507)
- [ ] Zero breaking changes

### Performance Metrics
- [ ] <100ms overhead per pipeline operation
- [ ] <50ms A2A matching time (0-100 agents)
- [ ] <512MB memory per pipeline instance
- [ ] Support 10+ levels of nesting
- [ ] Support 100+ agents in ensemble/blackboard

### Quality Metrics
- [ ] 100% code coverage for new patterns
- [ ] Zero linting errors
- [ ] Complete type hints
- [ ] Complete docstrings
- [ ] 9 example files (one per pattern)

---

## References

- **TODO-174**: Phase 3 requirements (`todos/active/TODO-174-unified-agent-framework-phase3.md`)
- **TODO-173**: Phase 2 completion report (`todos/completed/TODO-173-unified-agent-framework-phase2.md`)
- **Existing A2A Implementation**: `src/kaizen/nodes/ai/a2a.py`
- **Existing Pipeline Infrastructure**: `src/kaizen/orchestration/pipeline.py`
- **Existing Pattern Tests**: `tests/unit/agents/coordination/*.py` (6,500 lines)

---

## Approval

**Proposed By**: Requirements Analysis Specialist

**Review Status**: PENDING

**Approvers**:
- [ ] Technical Lead
- [ ] Architecture Team
- [ ] Test Lead

---

**Last Updated**: 2025-10-27
